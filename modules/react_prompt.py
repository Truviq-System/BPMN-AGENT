import re

from flask import Blueprint, request, jsonify

from .claude_client import call_claude
from .session_store import get_xml, strip_bpmndi
from .rag.pipeline import run as rag_run

react_bp = Blueprint("react", __name__)

# ─────────────────────────────────────────────
# STATIC SYSTEM PROMPT  (cached after first call)
# ─────────────────────────────────────────────
_REACT_SYSTEM = """Senior React architect for Camunda 8 (Zeebe) + Spring Boot apps.

Analyze the BPMN XML, then produce ONE copy-paste IDE prompt for a full production-ready React frontend.
Output ONLY the IDE prompt text — no explanation, no markdown wrapper.
Prompt must begin exactly: "Generate a complete, production-ready React 18 TypeScript frontend for a Camunda 8 (Zeebe) BPM process with the following exact specifications:"
Prompt must be fully self-contained (no XML reference). Use exact processId, task names, lanes, participants, entities extracted from the XML.

The IDE prompt must specify:

PROCESS MAPPING: process id/name→app title; participants→top nav; lanes→sidebar groups; userTasks→form pages; serviceTasks→monitoring views; infer entities→CRUD modules (match Spring Boot).

STACK: React 18+TS, Vite, Router v6, TanStack Query v5, Axios, RHF+Zod, Tailwind+shadcn/ui, Lucide, Recharts.

API (src/api): Axios baseURL http://localhost:8081 + interceptors.
Modules: processApi (start/list/get/delete instances), taskApi (list/get/complete/byProcess), <Entity>Api (CRUD per entity).
Types: StartProcessRequest, ProcessInstanceResponse, TaskResponse, CompleteTaskRequest + entity request/response DTOs.

USER TASK PAGES — per userTask: src/pages/tasks/<Name>Form.tsx
RHF+Zod form (fields inferred from BPMN variables); POST /api/tasks/{id}/complete {variables}; show metadata (name, instance, assignee, due); loading/success-toast/redirect to inbox.

ENTITY PAGES — per entity: List (table+search+pagination), Create/Edit (form+validation), Delete confirmation dialog; useMutation + query cache invalidation.

DASHBOARD: KPIs (total/active/completed/failed instances), bar chart (daily instances), pie chart (status distribution), recent activity feed, start-process modal.

TASK INBOX: poll every 30s; filter by type/search/status; task cards (name, assignee, due, processKey); click→task form; empty state + pagination.

LAYOUT (components/layout): AppLayout, Sidebar, Topbar.
Sidebar items: Dashboard · Task Inbox (live badge count) · Processes (list + start) · Entities (grouped) · Settings.

ROUTES: /→Dashboard · /tasks→Inbox · /tasks/<type>/:id→form · /processes→list · /processes/:key→detail · /<entity>→list · /<entity>/new · /<entity>/:id/edit

PROJECT STRUCTURE: src/ → api/, pages/, components/, hooks/, types/, lib/

CONFIG: Vite proxy /api→http://localhost:8081; path alias @→src; strict TypeScript; VITE_API_BASE_URL env var.

DEPENDENCIES: react, react-router-dom, @tanstack/react-query, axios, react-hook-form, zod, recharts, lucide-react, tailwindcss, shadcn/ui, clsx, date-fns, sonner.

All async states handled (loading/error/empty). Toast notifications for all mutations. Fully responsive layout. Add inline comments explaining: how process-start variables flow through tasks, how task-complete updates the BPMN process, and which variable names must match the backend.

Generate using exact names extracted from the BPMN XML."""


# ─────────────────────────────────────────────
# PROMPT BUILDER  (user message — dynamic only)
# ─────────────────────────────────────────────

def build_react_prompt(xml: str, rag_context: str = "") -> str:
    parts = []
    if rag_context:
        parts.append(f"REFERENCE:\n{rag_context}")
    # Strip BPMNDi (visual coords) — irrelevant for UI generation, saves ~40-60% of XML tokens.
    parts.append(f"BPMN XML:\n{strip_bpmndi(xml)}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@react_bp.route('/generate-react-prompt', methods=['POST'])
def generate_react_prompt():
    data       = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    xml        = data.get('xml', '').strip()

    if not xml and session_id:
        xml = get_xml(session_id) or ''
    if not xml:
        return jsonify({"error": "No BPMN XML provided"})

    rag_context, rag_meta = rag_run(xml, context_type="react")

    raw = call_claude(
        prompt=build_react_prompt(xml, rag_context),
        system=_REACT_SYSTEM,
        max_tokens=5000,
    )
    if not raw:
        return jsonify({"error": "Failed to reach Claude API"})

    raw = re.sub(r'^```[a-z]*\s*', '', raw.strip())
    raw = re.sub(r'\s*```$',       '', raw.strip())
    return jsonify({"success": True, "prompt": raw.strip(), "rag": rag_meta})
