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

    return f"""You are a senior React architect specializing in Camunda 8 process-driven applications with Spring Boot backends.{context}

Analyze the BPMN 2.0 XML and the Spring Boot API structure it implies, then generate ONE copy-paste prompt for an AI IDE (Cursor, Copilot, JetBrains AI) that builds a complete, production-ready React frontend application.

BPMN XML:
{xml}

OUTPUT RULES
- Output ONLY the IDE prompt text
- No explanations or markdown wrapping
- Prompt must start with:
  "Generate a complete, production-ready React 18 TypeScript frontend for a Camunda 8 (Zeebe) BPM process with the following exact specifications:"
- Prompt must be fully self-contained (do not require the XML)
- Use exact task names, entity names, lane names, and process IDs extracted from the XML

The IDE prompt must instruct generation of the following:
2
## PROCESS INFO
Extract from XML:
- process id and name → use as application title
- collaboration participants → top-level navigation sections
- lanes → sidebar menu groups
- userTask names → dedicated form page per task
- serviceTask names → status/monitoring views

## TECH STACK
React 18 + TypeScript
Vite build tool
React Router v6
TanStack Query (React Query) v5
Axios HTTP client
React Hook Form + Zod validation
Tailwind CSS + shadcn/ui components
Lucide React icons
Recharts for dashboard charts

## API CLIENT LAYER (src/api/)
Axios instance config:
- baseURL: http://localhost:8080
- Request interceptor: attach Content-Type header
- Response interceptor: extract data, normalise errors

Generate one API module per concern:
- processApi.ts  → POST /api/process/start, GET /api/process/instances, GET /api/process/instances/{key}, DELETE /api/process/instances/{key}
- taskApi.ts     → GET /api/tasks, GET /api/tasks/{taskId}, POST /api/tasks/{taskId}/complete, GET /api/tasks/process/{instanceKey}
- One <Entity>Api.ts per entity inferred from the BPMN → full CRUD matching Spring Boot controllers

TypeScript interfaces must mirror Spring Boot DTOs:
- StartProcessRequest, ProcessInstanceResponse
- TaskResponse, CompleteTaskRequest
- Entity request/response interfaces

## USER TASK FORMS
For each userTask extracted from the BPMN:
- Dedicated page component: src/pages/tasks/<TaskName>Form.tsx
- Zod schema with fields inferred from task name, lane, and likely Zeebe variable names
- React Hook Form hooked to the Zod schema
- On submit: POST /api/tasks/{taskId}/complete with { variables: formData }
- Show task metadata header: task name, process instance key, assignee, due date
- Loading skeleton while fetching task details
- Success toast → redirect to Task Inbox
- Error toast on failure

## ENTITY CRUD PAGES (src/pages/<Entity>/)
For each entity inferred from the BPMN (same entities as Spring Boot JPA layer):
- <Entity>List.tsx   → shadcn DataTable with search, sort, pagination via TanStack Query
- <Entity>Create.tsx → React Hook Form + Zod, calls POST /api/<entities>
- <Entity>Edit.tsx   → pre-populated form, calls PUT /api/<entities>/{id}
- DeleteConfirmDialog component → calls DELETE /api/<entities>/{id}
- All mutations use TanStack Query useMutation with cache invalidation

## PROCESS DASHBOARD (src/pages/Dashboard.tsx)
KPI cards row:
- Total Instances | Active | Completed | Failed
Bar chart (Recharts BarChart): instances created per day (last 30 days)
Pie chart (Recharts PieChart): status distribution
Recent activity table: last 10 process events
Quick-start button → opens StartProcessDialog modal
All data sourced from GET /api/process/instances with TanStack Query

## TASK INBOX (src/pages/TaskInbox.tsx)
- List all pending tasks via GET /api/tasks (TanStack Query, poll every 30 s)
- Filter bar: task type dropdown, process instance search, status tabs
- Task card: task name, assignee, due date chip (overdue = red), process name
- Click card → navigate to matching UserTask form page
- Empty state illustration when no tasks
- Pagination

## CAMUNDA DATA FLOW COMMENTS
Add JSDoc/inline comments in every API call explaining:
- POST /api/process/start → variables become Zeebe process variables available to all tasks
- POST /api/tasks/{id}/complete → variables are written back to the process scope and unblock the next element
- Variable names in form fields MUST match exactly the variable names expected by downstream service tasks
- Service task job workers read variables via @Variable annotations in Spring Boot

## APP LAYOUT & NAVIGATION
src/components/layout/
- AppLayout.tsx   → outer shell with sidebar + topbar + <Outlet>
- Sidebar.tsx     → collapsible on mobile, groups by BPMN lane/participant names
- Topbar.tsx      → breadcrumb, user avatar, notification bell (pending task count)

Sidebar links (use exact names from BPMN):
- Dashboard
- Task Inbox  (badge: pending task count)
- Process Management  (sub: All Instances, Start New)
- One group per entity (sub: List, New)
- Settings

React Router v6 routes in App.tsx:
/ → Dashboard
/tasks → TaskInbox
/tasks/<taskType>/:taskId → Task form
/processes → ProcessList
/processes/:key → ProcessDetail
/<entity> → Entity list
/<entity>/new → Entity create
/<entity>/:id/edit → Entity edit

## PROJECT STRUCTURE
src/
├── App.tsx
├── main.tsx
├── api/
│   ├── axios.ts
│   ├── processApi.ts
│   ├── taskApi.ts
│   └── <entity>Api.ts          (one per entity)
├── pages/
│   ├── Dashboard.tsx
│   ├── TaskInbox.tsx
│   ├── ProcessList.tsx
│   ├── ProcessDetail.tsx
│   ├── tasks/
│   │   └── <TaskName>Form.tsx  (one per userTask)
│   └── <Entity>/
│       ├── <Entity>List.tsx
│       ├── <Entity>Create.tsx
│       └── <Entity>Edit.tsx
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx
│   │   ├── Sidebar.tsx
│   │   └── Topbar.tsx
│   ├── tasks/
│   │   └── TaskCard.tsx
│   └── ui/                     (shadcn generated)
├── hooks/
│   ├── useProcessInstances.ts
│   ├── useTasks.ts
│   └── use<Entity>.ts
├── types/
│   └── index.ts
└── lib/
    ├── queryClient.ts
    ├── axios.ts
    └── utils.ts

## DEPENDENCIES (package.json)
react: ^18.3.0
react-dom: ^18.3.0
react-router-dom: ^6.26.0
@tanstack/react-query: ^5.51.0
@tanstack/react-query-devtools: ^5.51.0
axios: ^1.7.0
react-hook-form: ^7.53.0
zod: ^3.23.0
@hookform/resolvers: ^3.9.0
recharts: ^2.12.0
lucide-react: ^0.441.0
tailwindcss: ^3.4.0
@radix-ui/react-* (via shadcn/ui init)
clsx: ^2.1.0
date-fns: ^3.6.0
sonner: ^1.5.0

devDependencies:
typescript: ^5.5.0
vite: ^5.4.0
@types/react: ^18.3.0
@vitejs/plugin-react: ^4.3.0
eslint + prettier

## CONFIGURATION
vite.config.ts:
- server.proxy: {{ '/api': 'http://localhost:8080' }}
- resolve aliases: @ → src

tailwind.config.js:
- content: ['./index.html','./src/**/*.{{ts,tsx}}']
- shadcn/ui preset

.env:
VITE_API_BASE_URL=http://localhost:8080

tsconfig.json:
- strict: true
- paths: {{ "@/*": ["./src/*"] }}

## ADDITIONAL
- All async states: loading skeleton → data → error boundary
- Sonner toasts for every mutation success and error
- Mobile-responsive sidebar (Sheet from shadcn on small screens)
- README.md listing all pages, API endpoints consumed, and setup steps (npm install, npm run dev)
- shadcn/ui components used: Button, Card, Badge, Table, Dialog, Form, Input, Select, Skeleton, Sheet, Separator, DropdownMenu, Tooltip

Generate the final IDE prompt using exact userTask names, lane names, entity names, and process IDs extracted from the BPMN XML above.
"""


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@react_bp.route('/generate-react-prompt', methods=['POST'])
def generate_react_prompt():
    data = request.get_json()
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
