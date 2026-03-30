import re

from flask import Blueprint, request, jsonify

from .claude_client import call_claude
from .session_store import get_xml, strip_bpmndi
from .rag.pipeline import run as rag_run

springboot_bp = Blueprint("springboot", __name__)

# ─────────────────────────────────────────────
# STATIC SYSTEM PROMPT  (cached after first call)
# ─────────────────────────────────────────────
_SB_SYSTEM = """Senior Java architect for Camunda 8 (Zeebe) + Spring Boot 3.

Analyze the BPMN XML, then produce ONE copy-paste IDE prompt that builds a full production-ready Spring Boot application.
Output ONLY the IDE prompt text — no explanation, no markdown wrapper.
Prompt must begin exactly: "Generate a complete, production-ready Spring Boot 3 application for a Camunda 8 (Zeebe) BPM process with the following exact specifications:"
Prompt must be fully self-contained (do not reference the XML by name; embed all extracted values directly).

The IDE prompt must instruct generation of:

PROCESS INFO: extract process id/name, collaboration participants, lanes, lane→task mapping.

SERVICE TASK WORKERS — for each serviceTask (id, name, zeebe:taskDefinition type, lane, ioMapping variables):
One complete @JobWorker class per type:
1. @JobWorker(type="<type>") with ActivatedJob + JobClient params
2. Read inputs: job.getVariablesAsMap()
3. FULL business logic — NO TODOs, NO stubs, NO empty methods.
   validation→null/empty checks; notification→log-simulated send; approval→rule-based logic; calculation→actual compute; database→repository call
4. Output: client.newCompleteCommand(job.getKey()).variables(outputMap).send().join()
5. Business errors: client.newThrowErrorCommand
6. @Slf4j with entry/exit logging including variable values
Every worker must be a complete, runnable class.

USER TASK APIS — per userTask: REST endpoints to fetch and complete the task.

GATEWAYS — map exclusiveGateway conditions to if/else logic in relevant workers.

EVENTS — boundary event handlers (timer/error).

DATABASE — infer entities from tasks/lanes/variables:
JPA @Entity + CREATE TABLE DDL + Spring Data repositories.

POM.XML dependencies: spring-boot-starter-web, spring-boot-starter-data-jpa, spring-boot-starter-validation, io.camunda:spring-zeebe-starter, io.camunda:zeebe-client-java, postgresql, lombok, springdoc-openapi-starter-webmvc-ui, mapstruct, spring-boot-starter-test

APPLICATION.PROPERTIES: zeebe.client.*, spring.datasource.*(PostgreSQL), spring.jpa.*, server.port=8081, logging.level.*, springdoc.swagger-ui.path

CONTROLLERS:
ProcessController: POST /api/process/start · GET /api/process/instances · GET /api/process/instances/{key} · DELETE /api/process/instances/{key}
TaskController: GET /api/tasks · GET /api/tasks/{id} · POST /api/tasks/{id}/complete · GET /api/tasks/process/{key}
Entity Controllers: full CRUD per entity.

SERVICES: ProcessService (ZeebeClient — start/cancel/query), TaskService, entity services (@Transactional).

DTOs: StartProcessRequest, CompleteTaskRequest, ProcessInstanceResponse, TaskResponse, entity request/response DTOs.

EXCEPTION HANDLER (@ControllerAdvice): 404 ResourceNotFound, 400 Validation, 502 ZeebeClient, 500 Generic.

PROJECT STRUCTURE:
src/main/java/com/example/{process}/ → controller/, service/, repository/, model/entity/, model/dto/, worker/, config/, exception/
src/main/resources/ → application.properties, schema.sql, data.sql

Java 17. @Valid bodies. @Operation Swagger. Lombok. Startup runner listing registered workers. README with all APIs.

CRITICAL: every @JobWorker body has real working code; all workers call completeCommand or throwErrorCommand; include gateway if/else where decisions depend on worker output."""


# ─────────────────────────────────────────────
# PROMPT BUILDER  (user message — dynamic only)
# ─────────────────────────────────────────────

def build_springboot_prompt(xml: str, rag_context: str = "") -> str:
    parts = []
    if rag_context:
        parts.append(f"REFERENCE:\n{rag_context}")
    # Strip BPMNDi (visual coords) — irrelevant for code generation, saves ~40-60% of XML tokens.
    parts.append(f"BPMN XML:\n{strip_bpmndi(xml)}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@springboot_bp.route('/generate-springboot-prompt', methods=['POST'])
def generate_springboot_prompt():
    data       = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    xml        = data.get('xml', '').strip()

    if not xml and session_id:
        xml = get_xml(session_id) or ''
    if not xml:
        return jsonify({"error": "No BPMN XML provided"})

    rag_context, rag_meta = rag_run(xml, context_type="springboot")

    raw = call_claude(
        prompt=build_springboot_prompt(xml, rag_context),
        system=_SB_SYSTEM,
        max_tokens=6000,
    )
    if not raw:
        return jsonify({"error": "Failed to reach Claude API"})

    raw = re.sub(r'^```[a-z]*\s*', '', raw.strip())
    raw = re.sub(r'\s*```$',       '', raw.strip())
    return jsonify({"success": True, "prompt": raw.strip(), "rag": rag_meta})
