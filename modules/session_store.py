import re
import uuid

_store: dict[str, dict] = {}


def create_session(xml: str) -> str:
    session_id = uuid.uuid4().hex
    _store[session_id] = {"xml": xml}
    return session_id


def get_xml(session_id: str) -> str | None:
    session = _store.get(session_id)
    return session["xml"] if session else None


def clear_session(session_id: str) -> None:
    _store.pop(session_id, None)


def strip_bpmndi(xml: str) -> str:
    """Remove BPMNDi diagram section (visual coords) — not needed for test/code generation.
    Cuts XML size by ~40-60%, reducing input tokens for downstream calls."""
    return re.sub(r'\s*<bpmndi:BPMNDiagram[\s\S]*?</bpmndi:BPMNDiagram>', '', xml).strip()
