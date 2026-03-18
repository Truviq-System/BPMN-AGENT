import re
import uuid

from flask import Blueprint, request, jsonify

from .claude_client import call_claude
from .session_store import create_session
from .rag.pipeline import run as rag_run

bpmn_bp = Blueprint("bpmn", __name__)


# ─────────────────────────────────────────────
# POST-PROCESSING FIXES
# ─────────────────────────────────────────────

def fix_zeebe_task_definition(xml: str) -> str:
    def wrap_zeebe(match):
        tag_open  = match.group(1)
        inner     = match.group(2)
        tag_close = match.group(3)

        if '<bpmn:extensionElements>' in inner:
            return match.group(0)

        zeebe_match = re.search(r'(<zeebe:taskDefinition[^/]*/?>)', inner)
        if not zeebe_match:
            return match.group(0)

        zeebe_tag   = zeebe_match.group(1)
        inner_clean = re.sub(r'<zeebe:taskDefinition[^/]*/?>',  '', inner).strip()
        ext         = f'<bpmn:extensionElements>{zeebe_tag}</bpmn:extensionElements>'
        return f'{tag_open}\n      {ext}\n      {inner_clean}\n    {tag_close}'

    return re.sub(
        r'(<bpmn:serviceTask\b[^>]*>)(.*?)(</bpmn:serviceTask>)',
        wrap_zeebe, xml, flags=re.DOTALL
    )


def fix_orphan_gateways(xml: str) -> str:
    for gtype in ('exclusive', 'parallel'):
        tag   = f'bpmn:{gtype}Gateway'
        ids   = re.findall(rf'<{tag} id="([^"]+)"', xml)
        for gid in ids:
            outgoing = len(re.findall(rf'sourceRef="{re.escape(gid)}"', xml))
            if outgoing == 0:
                print(f"  Removing orphan gateway: {gid}")
                xml = re.sub(
                    rf'<{tag} id="{re.escape(gid)}".*?</{tag}>',
                    '', xml, flags=re.DOTALL
                )
    return xml


def fix_missing_bpmn_plane(xml: str) -> str:
    if '<bpmndi:BPMNDiagram' not in xml or '<bpmndi:BPMNPlane' in xml:
        return xml

    pid_match    = re.search(r'<bpmn:process id="([^"]+)"', xml)
    collab_match = re.search(r'<bpmn:collaboration id="([^"]+)"', xml)
    if collab_match:
        element_id = collab_match.group(1)
    elif pid_match:
        element_id = pid_match.group(1)
    else:
        element_id = "Process_1"
    print(f"  Adding missing BPMNPlane (bpmnElement={element_id})")

    def wrap_plane(m):
        return (
            f'{m.group(1)}\n'
            f'<bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{element_id}">\n'
            f'{m.group(2).strip()}\n'
            f'</bpmndi:BPMNPlane>\n'
            f'{m.group(3)}'
        )

    return re.sub(
        r'(<bpmndi:BPMNDiagram\b[^>]*>)(.*?)(</bpmndi:BPMNDiagram>)',
        wrap_plane, xml, flags=re.DOTALL
    )


def fix_partial_tags(xml: str) -> str:
    xml = re.sub(r'<\/[^>]{0,80}$',                              '', xml).strip()
    xml = re.sub(r'<(?:bpmn:|bpmndi:|dc:|di:|zeebe:)[^>]{0,80}$','', xml).strip()
    lines = xml.split('\n')
    while lines:
        last = lines[-1].strip()
        if last and '<' in last and '>' not in last:
            print(f"  Dropping incomplete line: {last[:60]}")
            lines.pop()
        else:
            break
    return '\n'.join(lines).strip()


def fix_missing_closing_tags(xml: str) -> str:
    pairs = [
        ("</bpmndi:BPMNEdge>",    r'<bpmndi:BPMNEdge\b'),
        ("</bpmndi:BPMNShape>",   r'<bpmndi:BPMNShape\b'),
        ("</bpmndi:BPMNPlane>",   r'<bpmndi:BPMNPlane\b'),
        ("</bpmndi:BPMNDiagram>", r'<bpmndi:BPMNDiagram\b'),
        ("</bpmn:process>",       r'<bpmn:process\b'),
        ("</bpmn:definitions>",   r'<bpmn:definitions\b'),
    ]
    for close_tag, open_pattern in pairs:
        diff = len(re.findall(open_pattern, xml)) - xml.count(close_tag)
        for _ in range(max(0, diff)):
            print(f"  Auto-closing: {close_tag}")
            xml += f'\n{close_tag}'
    return xml.strip()


def post_process(xml: str) -> str:
    xml = fix_partial_tags(xml)
    xml = fix_zeebe_task_definition(xml)
    xml = fix_orphan_gateways(xml)
    xml = fix_missing_bpmn_plane(xml)
    xml = fix_missing_closing_tags(xml)
    return xml


def clean_xml_response(xml_content: str) -> str | None:
    if not xml_content:
        return None

    xml_content = re.sub(r'```xml\s*', '', xml_content)
    xml_content = re.sub(r'```\s*',    '', xml_content)
    xml_content = xml_content.strip()

    if not (xml_content.startswith('<?xml')
            or xml_content.startswith('<bpmn:definitions')
            or xml_content.startswith('<definitions')):
        return None

    xml_content = post_process(xml_content)
    return xml_content


# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────
def build_prompt(description: str, rag_context: str = "",
                 app_name: str = "", app_industry: str = "",
                 app_purpose: str = "") -> str:
    context = f"\nDOMAIN REFERENCE:\n{rag_context}\n" if rag_context else ""

    app_context_parts = []
    if app_name:
        app_context_parts.append(f"Application Name: {app_name}")
    if app_industry:
        app_context_parts.append(f"Industry: {app_industry}")
    if app_purpose:
        app_context_parts.append(f"Application Purpose: {app_purpose}")

    app_context = ""
    if app_context_parts:
        app_context = "\nAPPLICATION CONTEXT:\n" + "\n".join(app_context_parts) + "\n"

    return f"""
Generate VALID BPMN 2.0 XML that opens correctly in Camunda Modeler and renders in BPMN.js.
Return ONLY raw XML.
{app_context}
PROCESS:
{description}
{context}

RULES
- Exactly one startEvent (StartEvent_1)
- At least one endEvent (EndEvent_1)
- Use correct task types:
  userTask → human actions
  serviceTask → automated actions
- Every serviceTask MUST include:
  <bpmn:extensionElements>
    <zeebe:taskDefinition type="..."/>
  </bpmn:extensionElements>

POOLS / LANES
- If roles exist → create collaboration + participants
- Define laneSet with lanes and flowNodeRef

GATEWAYS
- exclusiveGateway → decisions (label outgoing flows)
- parallelGateway → parallel work
- Splits must merge unless branches end

EVENTS
- Boundary timers must include:
  <bpmn:timerEventDefinition>
    <bpmn:timeDuration>P2D</bpmn:timeDuration>
  </bpmn:timerEventDefinition>

SUBPROCESS
- Use <bpmn:subProcess>
- Expanded in BPMNDI (isExpanded="true")

MESSAGE FLOWS
- Use <bpmn:messageFlow> between participants

LAYOUT
Lane height: 150  
Lane y positions: 150, 300, 450...

Element placement inside lanes:
StartEvent → x=100  
Tasks → x=300,500,700... (100x80)  
Gateways → x=400,600,800... (50x50)  
EndEvent → last_x+200  

Edge waypoints:
Start→Task: (start.x+36,start.y+18) → (task.x,task.y+40)
Task→Task: (task.x+100,task.y+40) → (next.x,next.y+40)
Task→Gateway: (task.x+100,task.y+40) → (gw.x,gw.y+25)
Gateway→Task: (gw.x+50,gw.y+25) → (task.x,task.y+40)
Task→End: (task.x+100,task.y+40) → (end.x,end.y+18)

VALIDATION
- Proper BPMN namespaces (bpmn,bpmndi,dc,di,zeebe,modeler)
- All sequenceFlows have BPMNEdge
- All elements have BPMNShape
- IDs unique
- bpmnElement references valid
"""


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

def _generate_bpmn(description: str, app_name: str = "", app_industry: str = "",
                   app_purpose: str = "") -> dict:
    print(f"\nGenerating BPMN for: {description[:80]}...")

    # ── Agentic RAG: decide whether to retrieve, then augment prompt ──────────
    rag_context, rag_meta = rag_run(description)
    # ─────────────────────────────────────────────────────────────────────────

    raw = call_claude(build_prompt(
        description, rag_context,
        app_name=app_name, app_industry=app_industry,
        app_purpose=app_purpose
    ))
    if not raw:
        return {"error": "Request failed", "details": "Could not reach Claude API"}

    xml = clean_xml_response(raw)
    if not xml:
        return {"error": "Failed to generate valid BPMN XML", "details": raw[:500]}

    print(f"✓ Done ({len(xml)} chars)")
    return {"success": True, "xml": xml, "rag": rag_meta}


@bpmn_bp.route('/')
def index():
    from flask import render_template
    return render_template('index.html')


@bpmn_bp.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    description   = data.get('description', '')
    app_name      = data.get('app_name', '')
    app_industry  = data.get('app_industry', '')
    app_purpose   = data.get('app_purpose', '')

    if not description.strip():
        return jsonify({"error": "Please enter a process description"})

    result = _generate_bpmn(
        description,
        app_name=app_name, app_industry=app_industry,
        app_purpose=app_purpose
    )

    # Store XML in session store so test/springboot routes can reuse it
    if result.get("success"):
        session_id = create_session(result["xml"])
        result["session_id"] = session_id

    return jsonify(result)


@bpmn_bp.route('/save', methods=['POST'])
def save():
    data = request.get_json()
    xml = data.get('xml', '').strip()
    if not xml:
        return jsonify({"error": "No XML provided"})
    filename = f"process_{uuid.uuid4().hex[:6]}.bpmn"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(xml)
        return jsonify({"success": True, "filename": filename})
    except Exception as e:
        return jsonify({"error": f"Could not save file: {e}"})
