import uuid

_store: dict[str, dict] = {}


def create_session(xml: str) -> str:
    """Store XML and return a fresh session_id."""
    session_id = uuid.uuid4().hex
    _store[session_id] = {"xml": xml}
    return session_id


def get_xml(session_id: str) -> str | None:
    """Return XML for the given session, or None if not found."""
    session = _store.get(session_id)
    return session["xml"] if session else None


def clear_session(session_id: str) -> None:
    _store.pop(session_id, None)
