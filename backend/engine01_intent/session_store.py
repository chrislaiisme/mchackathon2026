"""In-memory per-session state for ENGINE01.

A hackathon-scale FastAPI process only needs to survive one demo run, so
this is a plain in-process dict, not a database. Restarting the server
clears all sessions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from backend.shared.schemas import Intent


@dataclass
class SessionState:
    session_id: str
    intent: Intent = field(default_factory=Intent)
    round: int = 0


_sessions: dict[str, SessionState] = {}


def get_or_create(session_id: str | None) -> SessionState:
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    new_id = session_id or str(uuid.uuid4())
    state = SessionState(session_id=new_id)
    _sessions[new_id] = state
    return state


def save(state: SessionState) -> None:
    _sessions[state.session_id] = state
