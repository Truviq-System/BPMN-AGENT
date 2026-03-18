import re
import io
import json
import uuid
from datetime import datetime
from collections import Counter

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from flask import Blueprint, request, jsonify, send_file

from .claude_client import call_claude
from .session_store import get_xml
from .rag.pipeline import run as rag_run

tests_bp = Blueprint("tests", __name__)


# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────
def build_test_prompt(xml: str, rag_context: str = "") -> str:
    context = f"\nQA BEST PRACTICES:\n{rag_context}\n" if rag_context else ""

    return f"""You are a BPMN QA expert. Analyze the BPMN 2.0 XML and generate test cases covering all possible execution paths.
{context}

BPMN XML:
{xml}

OUTPUT RULES
Return ONLY a valid JSON array (no markdown, no explanation).

Each object must contain exactly:
suite
id
name
description
path
preconditions
steps
expected_result
test_type

FIELD RULES
suite ∈ ["Happy Path","Gateway Branches","Boundary Events","Exception Handling","Negative Tests"]
id format: TC-001, TC-002 sequential
name: ≤60 characters
path: ordered array of BPMN element names exactly as defined in XML
steps: numbered instructions in one string separated by newline
test_type: "Positive" or "Negative"

COVERAGE REQUIREMENTS
Generate 8–20 tests total including:
- 1 main Happy Path covering start → end
- All branches of every exclusiveGateway
- Parallel paths if parallelGateway exists
- Boundary events (timer/error/message) if present
- Exception handling flows
- At least 2 negative tests (invalid input, missing data, unauthorized action)

VALIDATION RULES
- Use ONLY element names present in BPMN
- Paths must represent valid execution flows
- Each gateway branch must have at least one test
- Boundary events must trigger alternative paths
- Do not invent tasks, events, or gateways

Return the JSON array only.
"""

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@tests_bp.route('/generate-tests', methods=['POST'])
def generate_tests():
    data = request.get_json()
    session_id = data.get('session_id', '')
    xml = data.get('xml', '').strip()

    # Fall back to session store if no XML supplied directly
    if not xml and session_id:
        xml = get_xml(session_id) or ''

    if not xml:
        return jsonify({"error": "No BPMN XML provided"})

    # ── Agentic RAG: retrieve QA patterns for this process type ───────────────
    rag_context, rag_meta = rag_run(xml, context_type="test")
    # ─────────────────────────────────────────────────────────────────────────

    raw = call_claude(build_test_prompt(xml, rag_context))
    if not raw:
        return jsonify({"error": "Failed to reach Claude API"})

    try:
        raw = re.sub(r'```json\s*', '', raw)
        raw = re.sub(r'```\s*', '', raw)
        raw = raw.strip()
        start = raw.find('[')
        end   = raw.rfind(']') + 1
        if start == -1 or end == 0:
            return jsonify({"error": "No JSON array found in response", "raw": raw[:300]})
        test_cases = json.loads(raw[start:end])
        return jsonify({"success": True, "test_cases": test_cases, "rag": rag_meta})
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Failed to parse test cases: {e}", "raw": raw[:300]})


@tests_bp.route('/export-tests', methods=['POST'])
def export_tests():
    data = request.get_json()
    test_cases   = data.get('test_cases', [])
    process_name = data.get('process_name', 'BPMN Process')

    if not test_cases:
        return jsonify({"error": "No test cases provided"})

    wb = openpyxl.Workbook()

    # ── Helpers ────────────────────────────────────
    purple_fill = PatternFill("solid", fgColor="FF667EEA")
    green_fill  = PatternFill("solid", fgColor="FF28A745")
    white_bold  = Font(color="FFFFFF", bold=True, size=11)
    bold        = Font(bold=True)

    status_fills = {
        'Pass':    PatternFill("solid", fgColor="FFD4EDDA"),
        'Fail':    PatternFill("solid", fgColor="FFF8D7DA"),
        'Blocked': PatternFill("solid", fgColor="FFFFF3CD"),
        'Not Run': PatternFill("solid", fgColor="FFF8F9FA"),
    }
    alt_fill = PatternFill("solid", fgColor="FFF2F3FF")

    # ── Test Cases Sheet (FIRST — opens by default) ─
    ws = wb.active
    ws.title = "Test Cases"

    headers = [
        'TC ID', 'Suite', 'Test Name', 'Type', 'Description',
        'Path', 'Preconditions', 'Steps', 'Expected Result',
        'Status', 'Notes', 'Executed By', 'Date'
    ]

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = purple_fill
        cell.font = white_bold
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[1].height = 32

    for row_idx, tc in enumerate(test_cases, 2):
        status   = tc.get('status', 'Not Run')
        path_val = tc.get('path', [])
        path_str = ' → '.join(path_val) if isinstance(path_val, list) else str(path_val or '')
        steps_str = (tc.get('steps', '') or '').replace('\\n', '\n')

        values = [
            tc.get('id', ''),
            tc.get('suite', ''),
            tc.get('name', ''),
            tc.get('test_type', ''),
            tc.get('description', ''),
            path_str,
            tc.get('preconditions', ''),
            steps_str,
            tc.get('expected_result', ''),
            status,
            tc.get('notes', ''),
            tc.get('executed_by', ''),
            tc.get('date', ''),
        ]

        max_lines = max(
            len(str(v).split('\n')) for v in values if v
        ) if any(values) else 1
        ws.row_dimensions[row_idx].height = max(18, min(max_lines * 15, 200))

        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=str(val) if val is not None else '')
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if col_idx == 10:
                cell.fill = status_fills.get(status, status_fills['Not Run'])
            elif row_idx % 2 == 0:
                cell.fill = alt_fill

    col_widths = [10, 20, 30, 12, 42, 35, 32, 52, 42, 12, 30, 18, 14]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = 'A2'

    # ── Summary Sheet ──────────────────────────────
    ws_sum = wb.create_sheet("Summary")

    ws_sum['A1'] = "BPMN Process Test Report"
    ws_sum['A1'].font = Font(bold=True, size=16)
    ws_sum['A2'] = f"Process: {process_name}"
    ws_sum['A3'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws_sum['A4'] = f"Total Test Cases: {len(test_cases)}"
    ws_sum['A4'].font = bold

    for cell_ref, val in [('A6', 'Suite'), ('B6', 'Count')]:
        ws_sum[cell_ref] = val
        ws_sum[cell_ref].fill = green_fill
        ws_sum[cell_ref].font = white_bold
        ws_sum[cell_ref].alignment = Alignment(horizontal='center')

    suites = Counter(tc.get('suite', 'Unknown') for tc in test_cases)
    row = 7
    for suite, count in suites.items():
        ws_sum[f'A{row}'] = suite
        ws_sum[f'B{row}'] = count
        row += 1

    row += 1
    for cell_ref, val in [(f'A{row}', 'Status'), (f'B{row}', 'Count')]:
        ws_sum[cell_ref] = val
        ws_sum[cell_ref].fill = purple_fill
        ws_sum[cell_ref].font = white_bold
        ws_sum[cell_ref].alignment = Alignment(horizontal='center')

    status_counts = Counter(tc.get('status', 'Not Run') for tc in test_cases)
    row += 1
    for status, count in status_counts.items():
        ws_sum[f'A{row}'] = status
        ws_sum[f'B{row}'] = count
        fill = status_fills.get(status)
        if fill:
            ws_sum[f'A{row}'].fill = fill
            ws_sum[f'B{row}'].fill = fill
        row += 1

    ws_sum.column_dimensions['A'].width = 30
    ws_sum.column_dimensions['B'].width = 12

    wb.active = 0

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"test_cases_{uuid.uuid4().hex[:6]}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
