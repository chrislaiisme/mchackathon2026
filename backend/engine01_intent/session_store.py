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
    # 一個對話串目前的狀態：session_id 是識別碼，intent 是累積到目前為止的
    # 結構化意圖，round 是已經跑了幾輪（每呼叫一次 /intent 就 +1）。
    session_id: str
    intent: Intent = field(default_factory=Intent)
    round: int = 0


# 純記憶體字典，key 是 (user_id, session_id) 這組 tuple，代表「哪個使用者的哪個對話串」，
# 伺服器重啟就會全部清空——這是刻意的取捨，demo 中途重啟本來就是問題，
# 落不落地存檔案都一樣，沒必要為了這個加資料庫。
_sessions: dict[tuple[str, str], SessionState] = {}


def get_or_create(user_id: str, session_id: str | None) -> SessionState:
    # 前端沒帶 session_id（第一次對話）就用 uuid4 開一個新的；
    # 有帶但字典裡查不到（例如伺服器剛重啟過）也一樣視為新開一個，不會噴錯。
    key_session_id = session_id or str(uuid.uuid4())
    key = (user_id, key_session_id)
    if key in _sessions:
        return _sessions[key]
    state = SessionState(session_id=key_session_id)
    _sessions[key] = state
    return state


def save(user_id: str, state: SessionState) -> None:
    # 每次 /intent 處理完一輪都要呼叫這個，把更新後的狀態（新的 intent、round+1）存回去。
    _sessions[(user_id, state.session_id)] = state
