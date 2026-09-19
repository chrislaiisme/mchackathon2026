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
from typing import Literal, Optional

from backend.shared.schemas import Intent


@dataclass
class SessionState:
    # 一個對話串目前的狀態：session_id 是識別碼，intent 是累積到目前為止的
    # 結構化意圖，round 是已經跑了幾輪（每呼叫一次 /intent 就 +1）。
    session_id: str
    intent: Intent = field(default_factory=Intent)
    round: int = 0
    # 這輪解析出來的參考圖網址（使用者上傳優先，沒上傳就用 Pinterest 板子比對）。
    # 刻意只留在這個內部狀態裡、不透過 IntentResponse 回傳給前端：使用者自己
    # 上傳的圖前端本來就知道網址，不用後端回傳；Pinterest 比對到的圖依規則
    # 不能顯示在畫面上，只能留給將來呼叫 ENGINE02 時內部使用（見
    # docs/pinterest-and-generation.md、docs/interface-contract.md 待確認事項）。
    reference_image_url: Optional[str] = None
    reference_image_source: Literal["user_upload", "pinterest", "none"] = "none"
    # 2026-09-19 新增，兩個都是跨輪次累加、不會重置：
    # asked_core_fields 記錄這個 session 已經正式問過（送給前端）的核心欄位，
    # 給 gating.py 的 filter_clarifying_questions() 用，避免同一欄位被問兩次、
    # 也用來算 5 題預算還剩多少。
    asked_core_fields: set[str] = field(default_factory=set)
    # message_history 存每一輪使用者的原始訊息，供之後呼叫 ENGINE02
    # 的 /intent/rank 時組成完整的 message——ENGINE02 的否定語意偵測
    # （engine02/negation.py）是讀 message 原句判斷的，只傳最新一句會
    # 漏掉前幾輪講過的排除條件（例如「不要太正式」）。
    message_history: list[str] = field(default_factory=list)
    # 2026-09-19 新增，接上 ENGINE03 回饋迴圈用：
    # shown_item_ids 是上一輪 /recommend 兩分區攤平後實際展示過的商品 id，
    # /feedback 驗證用——不能信瀏覽器自己講的它看過什麼，只信這裡記錄的。
    shown_item_ids: list[str] = field(default_factory=list)
    # 生成單品這輪實際展示過的 id。這個 id 由 ENGINE01 回傳給前端，而不是讓
    # 瀏覽器自己拿 cell index 組字串；/feedback 會用它驗證回饋確實屬於本輪。
    shown_generated_item_ids: list[str] = field(default_factory=list)
    # 生成 manifest 中、由伺服器信任的設計屬性。前端只能送 item_id 和動作，
    # ENGINE01 依 id 從這裡補回 design_attributes 後才會轉送 ENGINE03，避免
    # 瀏覽器偽造屬性權重。
    generated_item_design_attributes: dict[str, dict[str, str]] = field(default_factory=dict)
    # 最近一次 /feedback 拿到的 engine02_feedback（chosen_item_ids／
    # rejected_item_ids／choice_history／design_weight_delta），每輪 /recommend
    # 原樣夾帶給 intent_rank() 的 feedback 參數——ENGINE03 自己已經把最近幾輪
    # 聚合成一個值，這裡不再自己累加，整包替換即可。
    pending_engine02_feedback: Optional[dict] = None
    # 最近 3 輪送去 ENGINE03 的原始輸入（FeedbackRound 形狀），ENGINE03 的
    # Engine3Request.previous_rounds 規定最多 3 筆、必須比本輪 round 舊。
    feedback_rounds: list[dict] = field(default_factory=list)
    # 上一輪的 Intent（呼叫 /intent 覆寫前的舊值），餵給 intent_rank() 的
    # prev_intent，讓 ENGINE02 同時算「用本輪意圖評」跟「用上一輪意圖評」
    # 兩個 match_score 做誠實度對照。
    prev_intent: Optional[dict] = None
    # ENGINE02 的 /explain/rewrite 只記住「該 session 最後一個 slate」。同一輪
    # 的 top/bottom 查詢因此各用一個 deterministic child session，並記在這裡
    # 讓稍後的背景改寫端點只取回真正展示過的那些卡片。
    engine02_rewrite_session_ids: list[str] = field(default_factory=list)


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


def get(user_id: str, session_id: str) -> Optional[SessionState]:
    # 跟 get_or_create 不同：查不到就回 None，不會偷偷開一個新的空 session。
    # 給 POST /recommend 用——那支端點只該用「已經跑過幾輪 /intent」的既有
    # session，不該無中生有接住一個亂打的 session_id。
    return _sessions.get((user_id, session_id))


def save(user_id: str, state: SessionState) -> None:
    # 每次 /intent 處理完一輪都要呼叫這個，把更新後的狀態（新的 intent、round+1）存回去。
    _sessions[(user_id, state.session_id)] = state
