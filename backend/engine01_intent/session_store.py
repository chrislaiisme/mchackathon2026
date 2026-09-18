"""In-memory per-(user, session) state for ENGINE01.

A hackathon-scale FastAPI process only needs to survive one demo run, so
this is a plain in-process dict, not a database. Restarting the server
clears all sessions. Keyed by (user_id, session_id) rather than a bare
session_id since login is required -- a session only ever belongs to the
logged-in user who created it.
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


_sessions: dict[tuple[str, str], SessionState] = {}


def get_or_create(user_id: str, session_id: str | None) -> SessionState:
    key_session_id = session_id or str(uuid.uuid4())
    key = (user_id, key_session_id)
    if key in _sessions:
        return _sessions[key]
    state = SessionState(session_id=key_session_id)
    _sessions[key] = state
    return state


def save(user_id: str, state: SessionState) -> None:
    _sessions[(user_id, state.session_id)] = state
