import re

from flask import Blueprint, request, jsonify

from .claude_client import call_claude
from .session_store import get_xml
from .rag.pipeline import run as rag_run

springboot_bp = Blueprint("springboot", __name__)

# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────

def build_springboot_prompt_generator(xml: str, rag_context: str = "") -> str:
    context = f"\nBEST PRACTICES:\n{rag_context}\n" if rag_context else ""

    return f"""You are a senior Java architect specializing in Camunda 8 (Zeebe) and Spring Boot 3.{context}

Analyze the BPMN 2.0 XML and generate ONE copy-paste prompt for an AI IDE (Cursor, Copilot, JetBrains AI) that builds a full production-ready Spring Boot application.

BPMN XML:
{xml}

OUTPUT RULES
- Output ONLY the IDE prompt text
- No explanations or markdown
- Prompt must start with:
  "Generate a complete, production-ready Spring Boot 3 application for a Camunda 8 (Zeebe) BPM process with the following exact specifications:"
- Prompt must be fully self-contained (do not require the XML)

The IDE prompt must instruct generation of the following:

## PROCESS INFO
Extract from XML:
- process id and name
- collaboration participants
- lanes and which tasks belong to each lane

## SERVICE TASK WORKERS
For each serviceTask extract:
- id, name
- zeebe:taskDefinition type
- lane
Generate one @JobWorker per task type with variable handling.

## USER TASK APIs
For each userTask extract id and name.
Generate REST endpoints to fetch and complete tasks.

## GATEWAYS
Extract exclusiveGateway conditions and map them to if/else logic.

## EVENTS
Extract boundary events (timer/error) and generate handlers.

## DATABASE
Infer entities from tasks, lanes, and variables.
Generate:
- JPA @Entity classes
- CREATE TABLE DDL
- Spring Data repositories

## DEPENDENCIES (pom.xml)
spring-boot-starter-web  
spring-boot-starter-data-jpa  
spring-boot-starter-validation  
io.camunda:spring-zeebe-starter  
io.camunda:zeebe-client-java  
postgresql  
lombok  
springdoc-openapi-starter-webmvc-ui  
mapstruct  
spring-boot-starter-test

## CONFIG (application.properties)
Include:
zeebe.client.*  
spring.datasource.* (PostgreSQL)  
spring.jpa.*  
server.port  
logging.level.*  
springdoc.swagger-ui.path

## REST CONTROLLERS

ProcessController
POST   /api/process/start  
GET    /api/process/instances  
GET    /api/process/instances/{{key}}  
DELETE /api/process/instances/{{key}}

TaskController
GET    /api/tasks  
GET    /api/tasks/{{taskId}}  
POST   /api/tasks/{{taskId}}/complete
GET    /api/tasks/process/{{instanceKey}}

Entity Controllers
Full CRUD for each entity.

## SERVICES
ProcessService → start/cancel/query instances using ZeebeClient  
TaskService → manage user tasks  
Entity services with @Transactional

## DTOs
StartProcessRequest  
CompleteTaskRequest  
ProcessInstanceResponse  
TaskResponse  
Entity request/response DTOs

## EXCEPTION HANDLER
@ControllerAdvice with:
404 ResourceNotFoundException  
400 ValidationException  
502 ZeebeClientException  
500 Generic Exception

## PROJECT STRUCTURE
src/main/java/com/example/{{processname}}/
 controller/
 service/
 repository/
 model/entity/
 model/dto/
 worker/
 config/
 exception/

src/main/resources/
 application.properties
 schema.sql
 data.sql

## ADDITIONAL
Java 17  
Swagger annotations (@Operation)  
@Valid request bodies  
Lombok annotations  
Startup runner printing registered Zeebe workers  
README listing all APIs

Generate the final IDE prompt using exact values extracted from the BPMN XML.
"""


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@springboot_bp.route('/generate-springboot-prompt', methods=['POST'])
def generate_springboot_prompt():
    data = request.get_json()
    session_id = data.get('session_id', '')
    xml = data.get('xml', '').strip()

    # Fall back to session store if no XML supplied directly
    if not xml and session_id:
        xml = get_xml(session_id) or ''

    if not xml:
        return jsonify({"error": "No BPMN XML provided"})

    # ── Agentic RAG: retrieve Spring Boot implementation patterns ─────────────
    rag_context, rag_meta = rag_run(xml, context_type="springboot")
    # ─────────────────────────────────────────────────────────────────────────

    raw = call_claude(build_springboot_prompt_generator(xml, rag_context))
    if not raw:
        return jsonify({"error": "Failed to reach Claude API"})

    raw = re.sub(r'^```[a-z]*\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())

    return jsonify({"success": True, "prompt": raw.strip(), "rag": rag_meta})
