import re

from flask import Blueprint, request, jsonify

from .claude_client import call_claude
from .session_store import get_xml
from .rag.pipeline import run as rag_run

react_bp = Blueprint("react", __name__)

# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────

def build_react_prompt_generator(xml: str, rag_context: str = "") -> str:
    context = f"\nBEST PRACTICES:\n{rag_context}\n" if rag_context else ""

    return f"""You are a senior React architect for Camunda 8 (Zeebe) + Spring Boot apps.{context}

Analyze the BPMN XML and infer API + UI. Generate ONE copy-paste IDE prompt.

BPMN XML:
{xml}

OUTPUT RULES
- Output ONLY prompt text
- No markdown/explanations
- Must start exactly with:
"Generate a complete, production-ready React 18 TypeScript frontend for a Camunda 8 (Zeebe) BPM process with the following exact specifications:"
- Must be self-contained (no XML reference later)
- Use exact processId, task names, lanes, participants, entities

## PROCESS MAPPING
- process id/name → app title
- participants → top nav
- lanes → sidebar groups
- userTasks → form pages
- serviceTasks → monitoring views
- infer entities → CRUD modules (match Spring Boot)

## STACK
React 18 + TS, Vite, Router v6, TanStack Query v5, Axios, React Hook Form + Zod
Tailwind + shadcn/ui, Lucide icons, Recharts

## API (src/api)
Axios baseURL http://localhost:8081 with interceptors
Modules:
- processApi (start/list/get/delete instances)
- taskApi (list/get/complete/by process)
- <Entity>Api (CRUD)

Types:
StartProcessRequest, ProcessInstanceResponse, TaskResponse, CompleteTaskRequest + entity DTOs

## USER TASK PAGES
For each userTask:
- page: src/pages/tasks/<TaskName>Form.tsx
- RHF + Zod form (fields inferred from BPMN variables)
- submit → POST /api/tasks/{{id}}/complete {{ variables }}
- show metadata (name, instance, assignee, due)
- loading, success/error toast, redirect inbox

## ENTITY PAGES
For each entity:
- List (table + search + pagination)
- Create/Edit (form + validation)
- Delete dialog
- useMutation + cache invalidation

## DASHBOARD
- KPIs: total/active/completed/failed
- Bar (daily instances), Pie (status)
- recent activity
- start process modal
- data from process API

## TASK INBOX
- list tasks (poll 30s)
- filters (type, search, status)
- task cards (name, assignee, due, process)
- click → task form
- empty state + pagination

## LAYOUT
components/layout:
AppLayout, Sidebar, Topbar

Sidebar:
- Dashboard
- Task Inbox (badge count)
- Processes (instances + start)
- Entities (grouped)
- Settings

## ROUTES
/ → Dashboard
/tasks → Inbox
/tasks/<type>/:id → form
/processes → list
/processes/:key → detail
/<entity> → list
/<entity>/new → create
/<entity>/:id/edit → edit

## STRUCTURE
src/
api/, pages/, components/, hooks/, types/, lib/

## CONFIG
- proxy /api → backend
- alias @ → src
- strict TS
- env base URL

## RULES
- all async states handled
- toast for all mutations
- responsive UI
- add comments explaining:
  - process start → variables shared
  - task complete → updates flow
  - variables must match backend

## DEPENDENCIES
react, router, query, axios, RHF, zod, recharts, lucide, tailwind, shadcn, clsx, date-fns, sonner

Generate final prompt using exact extracted BPMN names.
"""


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@react_bp.route('/generate-react-prompt', methods=['POST'])
def generate_react_prompt():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    xml = data.get('xml', '').strip()

    if not xml and session_id:
        xml = get_xml(session_id) or ''

    if not xml:
        return jsonify({"error": "No BPMN XML provided"})

    # ── Agentic RAG: retrieve React / frontend implementation patterns ────────
    rag_context, rag_meta = rag_run(xml, context_type="react")
    # ─────────────────────────────────────────────────────────────────────────

    raw = call_claude(build_react_prompt_generator(xml, rag_context))
    if not raw:
        return jsonify({"error": "Failed to reach Claude API"})

    raw = re.sub(r'^```[a-z]*\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())

    return jsonify({"success": True, "prompt": raw.strip(), "rag": rag_meta})
