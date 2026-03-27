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

LAYOUT — COORDINATES (read carefully, apply exactly)

COLUMN SPACING SYSTEM
Assign every element a column index (col) starting at 0, incrementing left-to-right:
  col 0 → StartEvent      x = 150
  col 1 → first Task/GW   x = 300
  col 2 → next Task/GW    x = 500
  col 3 → next Task/GW    x = 700
  ...each col adds 200px
  EndEvent → x = last_col_x + 250

Never place two elements at the same x unless they are in DIFFERENT lanes on a parallel branch.
Parallel branches that run simultaneously share the same column index but sit in different lanes.

ELEMENT SIZES
  startEvent / endEvent:   width=36,  height=36
  intermediateEvent:       width=36,  height=36
  userTask / serviceTask:  width=100, height=80
  exclusiveGateway:        width=50,  height=50
  parallelGateway:         width=50,  height=50
  subProcess:              width=350, height=200

LANE / POOL DIMENSIONS
  Pool header width: 30
  Lane height: 160  (use 200 if the lane has boundary events or sub-processes)
  Lane y positions (inside the pool, top-to-bottom):
    Lane 1: y=0
    Lane 2: y=160
    Lane 3: y=320
    Lane 4: y=480
    ...
  Pool y offset from canvas top: 80
  So absolute y of lane N = 80 + (N-1)*160

ELEMENT VERTICAL CENTERING (per lane)
Place every element at the vertical center of its lane:
  element_center_y = lane_absolute_y + (lane_height / 2)
  startEvent/endEvent cy = element_center_y  →  y = cy - 18
  task cy = element_center_y                 →  y = cy - 40
  gateway cy = element_center_y             →  y = cy - 25

SEQUENCE FLOW WAYPOINTS (use exact center points of source and target)

Define center points first:
  startEvent center:  (x+18, y+18)
  endEvent center:    (x+18, y+18)
  task center:        (x+50, y+40)
  task left edge:     (x,    y+40)
  task right edge:    (x+100,y+40)
  gateway center:     (x+25, y+25)
  gateway left edge:  (x,    y+25)
  gateway right edge: (x+50, y+25)
  gateway top:        (x+25, y)
  gateway bottom:     (x+25, y+50)

CONNECTION RULES (same lane — horizontal flow)
  Start → Task:       waypoints: [start.rightCenter → task.leftEdge]
  Task → Task:        waypoints: [src.rightEdge → tgt.leftEdge]
  Task → Gateway:     waypoints: [task.rightEdge → gw.leftEdge]
  Gateway → Task:     waypoints: [gw.rightEdge → tgt.leftEdge]
  Gateway → End:      waypoints: [gw.rightEdge → end.leftCenter]
  Task → End:         waypoints: [task.rightEdge → end.leftCenter]

CONNECTION RULES (cross-lane — vertical + horizontal)
  Route via a mid-point to avoid overlaps:
    Step 1: exit source right edge (src.rightEdge)
    Step 2: add intermediate waypoint at (src.rightEdge.x + 20, tgt.leftEdge.y)  ← drops/rises to target lane
    Step 3: enter target left edge (tgt.leftEdge)
  For gateway cross-lane exit from bottom: use gateway.bottom as first waypoint
  For gateway cross-lane exit from top:    use gateway.top as first waypoint

EXCLUSIVE GATEWAY BRANCH ROUTING
  Default/main branch:  exits gateway RIGHT  → use gw.rightEdge
  Alternate branch(es): exit gateway BOTTOM or TOP depending on target lane direction
    - Target is in a lower lane → exit BOTTOM: (gw.x+25, gw.y+50)
    - Target is in a higher lane → exit TOP:   (gw.x+25, gw.y)
    - Then travel horizontally to target column before entering target element

PARALLEL GATEWAY RULES
  Split: all outgoing flows exit from RIGHT if same-lane, BOTTOM/TOP if cross-lane
  Merge: all incoming flows enter from LEFT if same-lane, TOP/BOTTOM if cross-lane

BOUNDARY EVENT PLACEMENT
  Attach to host task bottom edge:
    boundary.x = task.x + (task.width/2) - 18   (centered on task)
    boundary.y = task.y + task.height - 18
  Sequence flow from boundary: exit BOTTOM → (boundary.x+18, boundary.y+36)

SUBPROCESS BPMNDI
  isExpanded="true"
  Interior elements use absolute coordinates (not relative)
  Ensure interior elements fit within subprocess bounds

VALIDATION
- Proper BPMN namespaces (bpmn,bpmndi,dc,di,zeebe,modeler)
- All sequenceFlows have BPMNEdge with correct waypoints
- All elements have BPMNShape with correct x,y,width,height
- No two shapes overlap (check x ranges: elements at same y must have non-overlapping x ranges)
- IDs unique
- bpmnElement references valid
- Every waypoint coordinate must be derived from the formulas above — do not guess or reuse coordinates from other elements
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
