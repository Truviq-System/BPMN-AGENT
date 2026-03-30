import re
import uuid

from flask import Blueprint, request, jsonify

from .claude_client import call_claude
from .session_store import create_session
from .rag.pipeline import run as rag_run
from .document_extractor import extract_document

bpmn_bp = Blueprint("bpmn", __name__)

# ─────────────────────────────────────────────
# STATIC SYSTEM PROMPT  (cached after first call)
# ─────────────────────────────────────────────
_BPMN_SYSTEM = """You generate BPMN 2.0 XML for Camunda Modeler / BPMN.js. Return ONLY raw XML — no markdown, no explanation.

STRUCTURE
- 1 startEvent id=StartEvent_1; ≥1 endEvent id=EndEvent_1
- userTask=human actions; serviceTask=automated actions
- Every serviceTask: <bpmn:extensionElements><zeebe:taskDefinition type="..."/></bpmn:extensionElements>
- Roles present → collaboration + participants + laneSet with flowNodeRef per lane
- exclusiveGateway=decisions (label each outgoing flow); parallelGateway=parallel work; splits must merge unless all branches end
- Boundary timer: <bpmn:timerEventDefinition><bpmn:timeDuration>P2D</bpmn:timeDuration></bpmn:timerEventDefinition>
- subProcess: <bpmn:subProcess> with isExpanded="true" in BPMNDI; interior elements use absolute coords
- Cross-participant flows: <bpmn:messageFlow>

LAYOUT
Col x-coords: col0=150 col1=300 col2=500 col3=700 (+200 each); EndEvent x=last_col_x+250
Two elements same x only if in different lanes (parallel branch).

Sizes (w×h): startEvent/endEvent/intermediateEvent 36×36 | userTask/serviceTask 100×80 | exclusiveGW/parallelGW 50×50 | subProcess 350×200
Pool header w=30. Lane h=160 (200 if lane has boundary events or subProcess).
Lane absolute y: lane_N_abs = 80 + (N−1)×160

Vertical center per lane: cy = lane_abs_y + lane_h/2
  startEvent/endEvent y=cy−18 | task y=cy−40 | gateway y=cy−25

Edge reference points from (x,y):
  startEvent/endEvent: center=(x+18,y+18)
  task: center=(x+50,y+40) · left=(x,y+40) · right=(x+100,y+40)
  gateway: center=(x+25,y+25) · left=(x,y+25) · right=(x+50,y+25) · top=(x+25,y) · bottom=(x+25,y+50)

Waypoints — same lane: Start→Task: start_center→task.left | Task/GW→next: src.right→tgt.left | anything→End: src.right→end.left
Waypoints — cross-lane: src.right → (src.right.x+20, tgt.left.y) → tgt.left
  GW cross-lane: use gw.bottom (lower target) or gw.top (upper target) as first waypoint

Exclusive GW branches: main→gw.right; lower lane→(gw.x+25,gw.y+50)→horizontal→tgt.left; upper lane→(gw.x+25,gw.y)→horizontal→tgt.left
Parallel GW split: same-lane exits right; cross-lane exits bottom/top. Merge: same-lane enters left; cross-lane enters top/bottom.

Boundary event: x=task.x+(task.w/2)−18, y=task.y+task.h−18; outgoing flow exits bottom=(bnd.x+18,bnd.y+36)

NAMESPACES: bpmn, bpmndi, dc, di, zeebe, modeler
VALIDATION: every sequenceFlow→BPMNEdge+waypoints; every element→BPMNShape+x,y,w,h; no overlapping shapes; unique IDs; valid bpmnElement refs; all coords derived from formulas above"""


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
        tag = f'bpmn:{gtype}Gateway'
        for gid in re.findall(rf'<{tag} id="([^"]+)"', xml):
            if len(re.findall(rf'sourceRef="{re.escape(gid)}"', xml)) == 0:
                print(f"  Removing orphan gateway: {gid}")
                xml = re.sub(rf'<{tag} id="{re.escape(gid)}".*?</{tag}>', '', xml, flags=re.DOTALL)
    return xml


def fix_missing_bpmn_plane(xml: str) -> str:
    if '<bpmndi:BPMNDiagram' not in xml or '<bpmndi:BPMNPlane' in xml:
        return xml
    collab_match = re.search(r'<bpmn:collaboration id="([^"]+)"', xml)
    pid_match    = re.search(r'<bpmn:process id="([^"]+)"', xml)
    element_id   = (collab_match or pid_match)
    element_id   = element_id.group(1) if element_id else "Process_1"
    print(f"  Adding missing BPMNPlane (bpmnElement={element_id})")
    def wrap_plane(m):
        return (f'{m.group(1)}\n'
                f'<bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{element_id}">\n'
                f'{m.group(2).strip()}\n</bpmndi:BPMNPlane>\n{m.group(3)}')
    return re.sub(r'(<bpmndi:BPMNDiagram\b[^>]*>)(.*?)(</bpmndi:BPMNDiagram>)',
                  wrap_plane, xml, flags=re.DOTALL)


def fix_partial_tags(xml: str) -> str:
    xml = re.sub(r'<\/[^>]{0,80}$', '', xml).strip()
    xml = re.sub(r'<(?:bpmn:|bpmndi:|dc:|di:|zeebe:)[^>]{0,80}$', '', xml).strip()
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
        for _ in range(max(0, len(re.findall(open_pattern, xml)) - xml.count(close_tag))):
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
    return post_process(xml_content)


# ─────────────────────────────────────────────
# PROMPT BUILDER  (user message only — system is _BPMN_SYSTEM above)
# ─────────────────────────────────────────────

def build_prompt(description: str, rag_context: str = "",
                 app_name: str = "", app_industry: str = "",
                 app_purpose: str = "",
                 document_context: str = "",
                 existing_bpmn_xml: str = "") -> str:
    parts = []

    # App context (only include non-empty fields)
    app_parts = []
    if app_name:     app_parts.append(f"Name: {app_name}")
    if app_industry: app_parts.append(f"Industry: {app_industry}")
    if app_purpose:  app_parts.append(f"Purpose: {app_purpose}")
    if app_parts:
        parts.append("APP: " + " | ".join(app_parts))

    parts.append(f"PROCESS:\n{description}")

    if existing_bpmn_xml:
        # Strip BPMNDi from existing XML — Claude regenerates layout anyway.
        # This removes ~50% of the existing XML's tokens.
        lean_xml = re.sub(r'\s*<bpmndi:BPMNDiagram[\s\S]*?</bpmndi:BPMNDiagram>', '',
                          existing_bpmn_xml).strip()
        parts.append(
            "UPDATE THIS EXISTING BPMN (preserve element IDs and unchanged elements; "
            "apply PROCESS description as modifications/extensions):\n" + lean_xml
        )
    elif document_context:
        parts.append(
            "DOCUMENT CONTEXT (use for business rules, roles, data):\n"
            + document_context[:4000]
        )

    if rag_context:
        parts.append(f"REFERENCE PATTERNS:\n{rag_context}")

    return "\n\n".join(parts)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

def _generate_bpmn(description: str, app_name: str = "", app_industry: str = "",
                   app_purpose: str = "", document_context: str = "",
                   existing_bpmn_xml: str = "") -> dict:
    print(f"\nGenerating BPMN for: {description[:80]}...")
    if document_context:    print(f"  + doc context:  {len(document_context)} chars")
    if existing_bpmn_xml:   print(f"  + existing BPMN: {len(existing_bpmn_xml)} chars")

    rag_context, rag_meta = rag_run(description)

    raw = call_claude(
        prompt=build_prompt(description, rag_context,
                            app_name=app_name, app_industry=app_industry,
                            app_purpose=app_purpose,
                            document_context=document_context,
                            existing_bpmn_xml=existing_bpmn_xml),
        system=_BPMN_SYSTEM,
        max_tokens=8000,
    )
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
    data = request.get_json(silent=True) or {}
    description       = data.get('description', '')
    app_name          = data.get('app_name', '')
    app_industry      = data.get('app_industry', '')
    app_purpose       = data.get('app_purpose', '')
    document_context  = data.get('document_context', '')
    existing_bpmn_xml = data.get('existing_bpmn_xml', '')

    if not description.strip():
        return jsonify({"error": "Please enter a process description"})

    result = _generate_bpmn(
        description,
        app_name=app_name, app_industry=app_industry,
        app_purpose=app_purpose,
        document_context=document_context,
        existing_bpmn_xml=existing_bpmn_xml,
    )

    if result.get("success"):
        result["session_id"] = create_session(result["xml"])

    return jsonify(result)


@bpmn_bp.route('/extract-document', methods=['POST'])
def extract_document_route():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"})
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "No file selected"})
    return jsonify(extract_document(f.read(), f.filename))


@bpmn_bp.route('/save', methods=['POST'])
def save():
    data = request.get_json(silent=True) or {}
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
