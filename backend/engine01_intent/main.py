"""ENGINE01 FastAPI service: one sentence -> structured intent.

Run locally:
    uvicorn backend.engine01_intent.main:app --reload
"""

from __future__ import annotations

from dotenv import load_dotenv

# 一定要在 import 其他自家模組之前呼叫，因為 llm_client.py 有幾個模組層級的
# 常數是 import 當下就讀環境變數的（例如 CODEX_MODEL），load_dotenv() 沒先跑完，
# 那些常數就會讀到預設值，等於 .env 的設定沒生效。
load_dotenv()  # must run before importing modules that read env vars at import time (llm_client)

import os
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.engine01_intent import gating, llm_client, recommend, session_store, style_me
from backend.pinterest import client as pinterest_client
from backend.shared import user_store
from backend.shared.auth import create_session_token, get_current_user, verify_google_id_token
from backend.shared.schemas import (
    AuthResponse,
    GoogleAuthRequest,
    IntentRequest,
    IntentResponse,
    ProfileUpdate,
    RecommendRequest,
    StyledComplement,
    StyleMeRequest,
    UserProfile,
    ZonedRecommendationResult,
)
# 2026-09-19：把「生成新單品」（Design for Me 按鈕）接進 ENGINE01。`bff/images/concept.py`
# 的 generate_concepts() 是一支不依賴 FastAPI／BFF 自己 session 狀態的純函式（只吃
# session_id/round/intent，跨行程 shell out 給 agent/scripts/ 那條線），可以直接重用，
# 不需要整套搬進來 bff/main.py 的 /round /feedback 那些跟 ENGINE01 現有流程重複的部分——
# 詳細評估見跟使用者的討論記錄，這裡故意只借這一支函式，不是整層 BFF 都接。
from bff.images.concept import GENERATED_ROOT, ConceptImageUnavailable, generate_concepts

app = FastAPI(title="ENGINE01 - Intent Understanding")

# Same origins as the Google OAuth Client ID's "Authorized JavaScript origins"
# (see CLAUDE.md "Google OAuth Client ID") -- the browser blocks the frontend's
# calls to this API otherwise, regardless of auth. Comma-separated env override
# for whatever port/domain a given frontend actually runs on.
# （CORS：瀏覽器預設不准網頁呼叫「不同來源」的 API，這裡明確允許哪些網址
# 可以呼叫這個後端，不然不管登入對不對，瀏覽器都會直接擋掉請求。）
# 預設同時開 5173（scripts/engine01-test-page/ 這個舊測試頁用的 Vite port）跟
# 3000（實際蓋出來的前端 IntentWeave 是 Next.js，預設 port 是 3000，不是原本
# 規劃的 Vite）——2026-09-19 前端技術棧確定跟原計畫不同之後才發現要補這個。
_CORS_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 使用者上傳的參考圖存放位置：本機資料夾，不進資料庫、已被 .gitignore 排除
# （見 docs/engine01-intent.md「圖片上傳功能」這條待辦事項的既定方向）。磁碟目錄
# 還是叫 data/uploads/，但對外掛成 /files（不是 /uploads）——Starlette 的
# app.mount() 是照路徑前綴整段吃下去，不會管 HTTP method，如果掛在 /uploads，
# 會連 POST /uploads/image 這個上傳端點本身都被 StaticFiles 攔截（只支援
# GET/HEAD，會回 405），所以刻意讓「上傳端點」跟「靜態檔案掛載點」用不同前綴。
_UPLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=_UPLOADS_DIR), name="uploaded-files")

# 「生成新單品」（Design for Me）輸出的六宮格＋切好的六張單品圖，generate_concepts()
# 存在這裡、manifest 裡的 image_url 也是指向這個掛載點的相對路徑（見 concept.py 的
# _served()）——跟上面 /files 是同一種模式，只是這次資料夾由 bff/images/concept.py
# 決定（GENERATED_ROOT），不是這支檔案自己定。
GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=GENERATED_ROOT), name="generated-images")

# 允許的圖片格式／大小上限——避免使用者（或惡意呼叫）塞一個超大檔案或非圖片
# 檔案進來，本機儲存又沒有資料庫可以做額外檢查，這裡先擋在端點入口。
_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB


@app.post("/auth/google", response_model=AuthResponse)
def post_auth_google(request: GoogleAuthRequest) -> AuthResponse:
    # 步驟：驗證前端傳來的 Google ID token → 用 Google 帳號 sub 找或建立使用者
    # → 簽一個我們自己的 session token 回傳（後續請求都用這個 token，不用 Google 的）。
    claims = verify_google_id_token(request.id_token)
    profile = user_store.get_or_create_user(
        sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name"),
        picture=claims.get("picture"),
    )
    return AuthResponse(session_token=create_session_token(profile.sub), profile=profile)


@app.get("/profile", response_model=UserProfile)
def get_profile(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    # get_current_user 這個 dependency 已經驗證過登入、拿到使用者資料了，
    # 這裡不用再做任何事，直接回傳即可。
    return user


@app.put("/profile", response_model=UserProfile)
def put_profile(
    update: ProfileUpdate, user: UserProfile = Depends(get_current_user)
) -> UserProfile:
    # 只更新前端有明確傳值的欄位（不是 None 的），沒傳的欄位保持原樣，
    # 這樣「略過」偏好調查時只送 onboarding_completed=True 也不會把其他欄位洗成空的。
    if update.age_range is not None:
        user.age_range = update.age_range
    if update.style_preferences is not None:
        user.style_preferences = update.style_preferences
    if update.gender is not None:
        user.gender = update.gender
    if update.contexts is not None:
        user.contexts = update.contexts
    if update.onboarding_completed is not None:
        user.onboarding_completed = update.onboarding_completed

    # 2026-09-19 起 onboarding 改成註冊時必填，不能再略過（原本允許前端傳
    # onboarding_completed=True 但欄位留空當作「跳過」）。套用完這次更新後，
    # 如果結果會是「已完成」卻有必填欄位是空的，直接拒絕——防止有人繞過
    # 前端（前端已經拿掉 Skip 按鈕）直接打 API 把 onboarding 標記完成。
    if user.onboarding_completed and not (
        user.age_range and user.gender and user.style_preferences and user.contexts
    ):
        raise HTTPException(
            400,
            "onboarding 必填：age_range／gender／style_preferences／contexts 都要有值才能標記完成",
        )

    user_store.save_user(user)
    return user


@app.post("/uploads/image")
async def upload_image(
    file: UploadFile, user: UserProfile = Depends(get_current_user)
) -> dict[str, str]:
    # 使用者自己上傳的參考圖：檔名副檔名／大小先擋一輪，通過才寫進
    # data/uploads/<sub>/<uuid>.<ext>，避免路徑穿越（用 uuid 產生檔名，
    # 完全不使用使用者原始檔名）跟塞入非圖片/過大檔案。
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, f"不支援的圖片格式：{suffix or '(無副檔名)'}")

    content = await file.read()
    if len(content) > _MAX_IMAGE_BYTES:
        raise HTTPException(400, "圖片檔案過大（上限 5MB）")

    user_dir = _UPLOADS_DIR / user.sub
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    (user_dir / filename).write_bytes(content)

    return {"image_url": f"/files/{user.sub}/{filename}"}


@app.post("/intent", response_model=IntentResponse)
def post_intent(
    request: IntentRequest, user: UserProfile = Depends(get_current_user)
) -> IntentResponse:
    # 核心流程：拿這個使用者、這個 session 目前累積的意圖 → 丟給 codex exec
    # 併入這一輪新說的話 → 把更新後的意圖存回去 → 回傳給前端。
    state = session_store.get_or_create(user.sub, request.session_id)
    extraction = llm_client.extract_intent(request.message, state.intent)

    state.intent = extraction.intent
    state.round += 1
    state.message_history.append(request.message)

    # 核心欄位把關（代辦事項 2）：LLM 這輪吐出的問題先經過 gating.py 過濾——
    # 只留核心欄位、同一欄位不重複問、全部題數不超過 5 題，見 gating.py 的說明。
    clarifying_questions = gating.filter_clarifying_questions(
        extraction.clarifying_questions, state.asked_core_fields
    )

    # 參考圖解析（代辦事項 2）：使用者這次有上傳就優先用使用者的；沒上傳
    # 就用這輪更新後的 Intent 去比對團隊的 Pinterest 板子；兩者都沒有就
    # 維持 None，不帶圖片繼續跑（不擋主流程）。這個值刻意不放進下面回傳
    # 給前端的 IntentResponse——見 session_store.SessionState 的欄位註解。
    if request.reference_image_url:
        state.reference_image_url = request.reference_image_url
        state.reference_image_source = "user_upload"
    else:
        pinterest_image = pinterest_client.find_reference_image(state.intent)
        if pinterest_image:
            state.reference_image_url = pinterest_image
            state.reference_image_source = "pinterest"
        else:
            state.reference_image_url = None
            state.reference_image_source = "none"

    session_store.save(user.sub, state)

    return IntentResponse(
        session_id=state.session_id,
        round=state.round,
        intent=state.intent,
        clarifying_questions=clarifying_questions,
    )


@app.post("/recommend", response_model=ZonedRecommendationResult)
def post_recommend(
    request: RecommendRequest, user: UserProfile = Depends(get_current_user)
) -> ZonedRecommendationResult:
    # 前端預期在 IntentResponse.clarifying_questions 變空之後才呼叫這支
    # （核心欄位都問完，或已經問滿 5 題預算），但這裡不強制擋——跟 /intent
    # 的澄清問題邏輯一樣，是前端流程上的約定，不是後端的硬性關卡。
    state = session_store.get(user.sub, request.session_id)
    if state is None:
        raise HTTPException(404, "找不到這個 session，請先呼叫過 /intent")

    result = recommend.build_zoned_recommendation(
        state.intent,
        state.session_id,
        state.round,
        state.message_history,
        recommend.resolve_reference_image_for_retrieval(
            state.reference_image_url, state.reference_image_source
        ),
        user,
    )
    # ENGINE02 沒有 OPENAI_API_KEY 時，reason 是樣板句，會露出內部分數／備註
    # （例如「整體風格和你描述的相近（+1.44）」）——比照 style_me.py 既有的
    # LLM 改寫模式，批次（一次 codex exec 呼叫）把這輪要顯示的理由都改寫成
    # 自然語句，失敗就原樣返回樣板句，不擋主流程。
    return recommend.apply_natural_language_reasons(result, " ".join(state.message_history))


@app.post("/style-me", response_model=StyledComplement)
def post_style_me(
    request: StyleMeRequest, user: UserProfile = Depends(get_current_user)
) -> StyledComplement:
    # 「我們幫你搭」——不是隨機配，見 style_me.py 的說明。
    state = session_store.get(user.sub, request.session_id)
    if state is None:
        raise HTTPException(404, "找不到這個 session，請先呼叫過 /intent")

    result = style_me.build_styled_complement(
        state.session_id,
        state.round,
        state.message_history,
        state.intent,
        user,
        request.anchor_product_id,
        request.anchor_zone,
    )
    if result is None:
        raise HTTPException(404, "這個分區目前找不到可以搭配的商品")

    zone, complement = result
    return StyledComplement(
        session_id=state.session_id, round=state.round, zone=zone, complement=complement
    )


class ConceptImageRequest(BaseModel):
    # 故意不放進 backend/shared/schemas.py——這支端點只有 ENGINE01 跟生成模組
    # 兩邊在用，不是 ENGINE02／ENGINE03／前端都要遵守的介面契約，放在這裡改動
    # 不用知會其他引擎負責人。形狀照抄 bff/main.py 的 ConceptImageRequest，
    # 兩邊維持一致純粹是方便，不是強制。
    session_id: str
    cells: int = 6
    model: Optional[str] = None
    """生圖模型，省略用 generate_grid.py 的預設（gpt-image-2-low）。"""
    dry_run: bool = False
    """2026-09-19：Hermes Agent 這套外部工具還沒在這台機器裝好之前，先用這個模式
    驗證整條管線接不接得通——只組 prompt 與 manifest，不會真的呼叫 Hermes、
    不花任何生圖額度。Hermes 裝好、確認能跑之後，前端把這個 flag 關掉即可，
    不用再改這支端點或呼叫方式。"""


@app.post("/concept-image")
def post_concept_image(
    request: ConceptImageRequest, user: UserProfile = Depends(get_current_user)
) -> dict[str, Any]:
    """「生成新單品」（Design for Me 按鈕）：使用者對這一輪 ENGINE02 撈到的東西不滿意，
    按下去用目前的 Intent 生一張六宮格、切成六件新單品讓他挑。**明確觸發，不是每輪
    自動跑**——這是前端獨立按鈕的動作，跟 /intent、/recommend 分開呼叫，見
    docs/frontend.md 代辦事項 3。

    這裡直接重用 bff/images/concept.py 的 generate_concepts()（見檔案開頭 import 處的
    說明），不透過 bff/main.py 那層 BFF——那層是給整條 Hermes app 技術棧用的獨立
    orchestration（有自己的 /round /feedback，會跟 ENGINE01 這裡的 session_store
    重複），目前只需要借生圖這一支功能，不需要整層都接。
    """
    state = session_store.get(user.sub, request.session_id)
    if state is None:
        raise HTTPException(404, "找不到這個 session，請先呼叫過 /intent")
    if not state.intent.item_type and not state.intent.outfit_requested:
        # generate_grid.py 需要一個具體的 item_type 才知道要畫什麼類別的單品；
        # outfit_requested=True 時 item_type 可能還是空的（套裝請求本來就不強制問），
        # 這種情況目前還沒設計「該生上衣還是下身」，先明確擋掉、給前端看得懂的錯誤，
        # 不要讓它一路傳到 generate_grid.py 才用一句 SystemExit 爆掉。
        raise HTTPException(
            409, "這一輪意圖還沒有明確的品項（item_type），生圖需要先知道要畫哪一類單品"
        )

    try:
        result = generate_concepts(
            state.session_id,
            state.round,
            state.intent.model_dump(),
            cells=request.cells,
            model=request.model,
            dry_run=request.dry_run,
        )
    except ConceptImageUnavailable as exc:
        # 生圖那條線還沒到位（例如 Hermes Agent 沒裝好）或這次執行失敗——
        # 跟 bff/main.py 的 /concept-image 一樣回 502，不是整個 API 掛掉，
        # 前端可以照常讓使用者留在對話畫面，只是生圖沒有成功。
        raise HTTPException(502, f"生成單品失敗：{exc}")

    return {"session_id": state.session_id, "round": state.round, "concepts": result}


@app.get("/health")
def health() -> dict[str, str]:
    # 純粹給人／監控工具確認服務有沒有活著，不需要登入。
    return {"status": "ok"}
