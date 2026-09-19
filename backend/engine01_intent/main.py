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

import concurrent.futures
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.engine01_intent import (
    engine03_client,
    gating,
    llm_client,
    recommend,
    session_store,
    style_me,
    zones,
)
from backend.pinterest import client as pinterest_client
from backend.shared import user_store
from backend.shared.auth import create_session_token, get_current_user, verify_google_id_token
from backend.shared.schemas import (
    AuthResponse,
    FeedbackRequest,
    FeedbackResponse,
    GoogleAuthRequest,
    Intent,
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

    # 2026-09-19 新增：更新 state.intent 之前先把舊值存起來，餵給下一次
    # /recommend 呼叫 intent_rank() 的 prev_intent（ENGINE02 用來算「用上一輪
    # 意圖評」的對照分數）。第一輪（round 0）沒有「上一輪」，維持 None。
    state.prev_intent = state.intent.model_dump() if state.round > 0 else None
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
        feedback=state.pending_engine02_feedback,
        prev_intent=state.prev_intent,
    )
    # ENGINE02 沒有 OPENAI_API_KEY 時，reason 是樣板句，會露出內部分數／備註
    # （例如「整體風格和你描述的相近（+1.44）」）——比照 style_me.py 既有的
    # LLM 改寫模式，批次（一次 codex exec 呼叫）把這輪要顯示的理由都改寫成
    # 自然語句，失敗就原樣返回樣板句，不擋主流程。2026-09-20：多帶一份
    # profile_context（onboarding 長期偏好＋這輪結構化 Intent），讓改寫出來的
    # 句子能點名使用者自己的偏好，不是只靠原始對話字串籠統判斷語氣。
    result = recommend.apply_natural_language_reasons(
        result,
        " ".join(state.message_history),
        recommend.build_profile_context(state.intent, user),
    )

    # 2026-09-19 新增：記下這輪兩分區攤平後實際展示過的商品 id，/feedback
    # 驗證要用——不能信瀏覽器自己講的它看過什麼。這支端點原本完全沒有把
    # 狀態存回去（唯讀），這裡是第一次新增 save() 呼叫。
    state.shown_item_ids = [card.product_id for slate in result.zones for card in slate.products]
    session_store.save(user.sub, state)

    return result


@app.post("/feedback", response_model=FeedbackResponse)
def post_feedback(
    request: FeedbackRequest,
    user: UserProfile = Depends(get_current_user),
    authorization: Optional[str] = Header(default=None),
) -> FeedbackResponse:
    """接上 ENGINE03（backend/engine03_feedback/）的真實回饋迴圈——2026-09-19 新增。

    只吃 `source="catalog"`（資料庫商品）的回饋：單品收藏／不喜歡／三個具名
    維度打分，跟整套喜歡（`OutfitFeedback`，只有「喜歡」這個方向，ENGINE03
    本身沒有「整套不喜歡」的概念）。`source="generated"` 的單品回饋今天整批
    跳過（`skipped_generated_item_feedbacks` 誠實列出，不是默默丟掉）——
    ENGINE03 要求這種回饋的 `design_attributes` 由「受信任」的一方提供，
    生成模組的 `keywords` 詞彙目前沒有對應到 ENGINE03 屬性 id 的轉換邏輯，
    需要跨負責人確認才能做，見 docs 記錄的已知落差。

    ENGINE03 的 `/feedback` 掛了跟 ENGINE01 共用同一把 `SESSION_SECRET` 的
    `Depends(get_current_user)`，一定要把這裡收到的 `Authorization` header
    原樣轉發，不然 `DEV_BYPASS_AUTH=false` 時 ENGINE03 那邊會直接 401——
    見 `engine03_client.py` 的說明，這跟完全不驗證的 ENGINE02 不一樣。
    """
    state = session_store.get(user.sub, request.session_id)
    if state is None:
        raise HTTPException(404, "找不到這個 session，請先呼叫過 /intent")
    if request.round != state.round:
        raise HTTPException(409, f"round 不一致：session 目前是 {state.round}，收到 {request.round}")
    if not state.shown_item_ids and not state.shown_generated_item_ids:
        raise HTTPException(409, "這一輪還沒有展示過任何商品，沒有東西可以回饋")

    catalog_feedbacks: list[dict[str, Any]] = []
    skipped_generated: list[str] = []
    for item_feedback in request.item_feedbacks:
        if item_feedback.source == "generated":
            skipped_generated.append(item_feedback.item_id)
            continue
        if item_feedback.item_id not in state.shown_item_ids:
            raise HTTPException(422, f"item_id {item_feedback.item_id!r} 不是這輪展示過的商品")
        catalog_feedbacks.append(
            {
                "item_id": item_feedback.item_id,
                "source": "catalog",
                "favorited": item_feedback.favorited,
                "disliked": item_feedback.disliked,
                "attribute_ratings": [rating.model_dump() for rating in item_feedback.attribute_ratings],
            }
        )

    outfit_feedbacks: list[dict[str, Any]] = []
    skipped_generated_outfits: list[str] = []
    for outfit_feedback in request.outfit_feedbacks:
        # 整套裡只要有一件是 source="generated"，整筆 outfit 都跳過（不是只挑
        # 資料庫那一件單獨送）——「半套的整套喜歡」語意會失真，而且
        # design_attributes 詞彙映射還沒人跟 ENGINE02／生成模組負責人確認過，
        # 不能自己瞎猜著送，見 backend/shared/schemas.py::OutfitFeedbackRequest。
        if any(item.source == "generated" for item in outfit_feedback.items):
            skipped_generated_outfits.append(outfit_feedback.outfit_id)
            continue

        for item in outfit_feedback.items:
            if item.item_id not in state.shown_item_ids:
                raise HTTPException(422, f"item_id {item.item_id!r} 不是這輪展示過的商品")

        outfit_feedbacks.append(
            {
                "outfit_id": outfit_feedback.outfit_id,
                "favorited": True,
                "items": [
                    {"zone": item.zone, "source": item.source, "item_id": item.item_id}
                    for item in outfit_feedback.items
                ],
            }
        )

    if not catalog_feedbacks and not outfit_feedbacks:
        raise HTTPException(422, "沒有可送出的回饋（generated 來源今天還不支援）")

    current_round = {
        "round": state.round,
        "shown_item_ids": state.shown_item_ids,
        "shown_generated_item_ids": state.shown_generated_item_ids,
        "item_feedbacks": catalog_feedbacks,
        "outfit_feedbacks": outfit_feedbacks,
    }
    result = engine03_client.submit_feedback(
        state.session_id, state.feedback_rounds, current_round, authorization
    )
    if result is None:
        raise HTTPException(502, "呼叫 ENGINE03 /feedback 失敗")

    # ENGINE03 的 previous_rounds 最多 3 筆、必須比本輪 round 舊——這裡把這輪
    # 送出去的原始輸入累加進去，只留最近 3 筆，下一輪 /feedback 才有正確的
    # 回饋窗口可以送。
    state.pending_engine02_feedback = result["engine02_feedback"]
    state.feedback_rounds = (state.feedback_rounds + [current_round])[-3:]
    session_store.save(user.sub, state)

    return FeedbackResponse(
        session_id=state.session_id,
        round=state.round,
        engine02_feedback=result["engine02_feedback"],
        attribute_evidence=result.get("attribute_evidence") or [],
        generated_attribute_evidence=result.get("generated_attribute_evidence") or [],
        outfit_evidence=result.get("outfit_evidence") or [],
        skipped_generated_item_feedbacks=skipped_generated,
        skipped_generated_outfit_feedbacks=skipped_generated_outfits,
    )


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

    intent = state.intent

    if intent.item_type:
        # 單品請求——2026-09-19 改成跟 recommend.py::build_zoned_recommendation()
        # 一樣的三分支判斷：連身裙、單品＋填充另一區、（不是連身裙也不是整套的）
        # 純單品都要先問過 zones.resolve_zone_for_item_type()，不能再像原本
        # 那樣不管三七二十一都走扁平單品生成——連身裙的 item_type 本來就有值
        # （例如「連身裙」），原本的邏輯完全沒有意識到這件事，一律當普通單品生。
        primary_zone, dress = zones.resolve_zone_for_item_type(intent.item_type)
        other_zone = "bottom" if primary_zone == "top" else "top"
        try:
            if dress:
                # 連身裙：只生使用者真正問的那一區（維持原始 item_type，
                # 不能被 default_category_for_zone() 蓋掉），另一區留空、
                # 不呼叫生成管線——連身裙本身就涵蓋下半身。
                primary_result = _generate_concepts_for_zone(
                    state.session_id, state.round, intent, primary_zone,
                    request.cells, request.model, request.dry_run, keep_item_type=True,
                )
                other_result = _empty_zone_result()
            else:
                # 不是連身裙：要問的那一區真的生成（維持原始 item_type），
                # 另一區也生成一個代表性品項當填充，讓單品請求也有兩分區可以
                # 看——跟資料庫推薦 _assemble_single_item_result() 的既有行為
                # 一致，不是只有整套請求才有兩分區展示。
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    future_primary = executor.submit(
                        _generate_concepts_for_zone, state.session_id, state.round, intent,
                        primary_zone, request.cells, request.model, request.dry_run,
                        keep_item_type=True,
                    )
                    future_other = executor.submit(
                        _generate_concepts_for_zone, state.session_id, state.round, intent,
                        other_zone, request.cells, request.model, request.dry_run,
                    )
                    primary_result = future_primary.result()
                    other_result = future_other.result()
        except ConceptImageUnavailable as exc:
            # 生圖那條線還沒到位（例如 Hermes Agent 沒裝好）或這次執行失敗——
            # 跟 bff/main.py 的 /concept-image 一樣回 502，不是整個 API 掛掉，
            # 前端可以照常讓使用者留在對話畫面，只是生圖沒有成功。
            raise HTTPException(502, f"生成單品失敗：{exc}")

        zone_results = {primary_zone: primary_result, other_zone: other_result}
        return _assemble_concept_zone_response(state, zone_results, state.message_history, request.dry_run, user)

    if not intent.outfit_requested:
        # 沒有品項、也不是整套請求——現在還沒設計這種情況該生什麼，先明確擋掉，
        # 給前端看得懂的錯誤，不要讓它一路傳到 generate_grid.py 才用一句
        # SystemExit 爆掉。
        raise HTTPException(
            409, "這一輪意圖還沒有明確的品項（item_type），生圖需要先知道要畫哪一類單品"
        )

    # 整套請求（outfit_requested=True 且沒有單一 item_type）——比照
    # recommend.py::build_zoned_recommendation() 的兩分區模式，上衣／下身
    # 各生一組六格，跟資料庫推薦「上衣＋下身各 6 件」的展示邏輯一致。
    # 先試平行執行（兩個 ThreadPoolExecutor worker 各自呼叫一次
    # generate_concepts()，各自是獨立的 subprocess，互不共用狀態）；如果現場
    # 撞到 WSL2/Hermes 的 session 衝突，再改成循序執行，不會兩種都寫進程式碼
    # 用旗標切換——這是「試了才知道」的東西，不是能先預留兩條路的那種決定。
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_top = executor.submit(
                _generate_concepts_for_zone, state.session_id, state.round, intent,
                "top", request.cells, request.model, request.dry_run,
            )
            future_bottom = executor.submit(
                _generate_concepts_for_zone, state.session_id, state.round, intent,
                "bottom", request.cells, request.model, request.dry_run,
            )
            zone_results = {"top": future_top.result(), "bottom": future_bottom.result()}
    except ConceptImageUnavailable as exc:
        raise HTTPException(502, f"生成單品失敗：{exc}")

    return _assemble_concept_zone_response(state, zone_results, state.message_history, request.dry_run, user)


def _generate_concepts_for_zone(
    session_id: str,
    round: int,
    intent: Intent,
    zone: str,
    cells: int,
    model: Optional[str],
    dry_run: bool,
    *,
    keep_item_type: bool = False,
) -> dict[str, Any]:
    """幫某一區（上衣／下身）生成六格——比照 recommend.py 的 `_with_item_type()`
    模式，把 item_type 換成這一區的代表品項（`zones.default_category_for_zone()`），
    其餘欄位（顏色／風格／場合／季節）維持使用者這輪講的原話。

    `keep_item_type=True`（2026-09-19 新增，單品請求裡「使用者真的問的那一區」用）：
    不覆寫 `item_type`，維持使用者的原話——跟整套請求／單品請求的「填充區」
    不一樣，那兩種情境要換成這一區的代表品項，這種情境要保留使用者真正問的
    那個品項，不能被 `default_category_for_zone()` 蓋掉。

    `session_id` 加 `__top`／`__bottom` 尾綴（不能用冒號——Windows 檔案系統的
    冒號是保留字元，`generate_concepts()` 會拿 session_id 當資料夾名稱的一部分，
    真的用冒號會直接寫檔失敗），確保兩區各自的輸出目錄
    （`data/generated/<session_id>__<zone>/r<round>/`）不會互相覆蓋。
    """
    zone_intent = intent if keep_item_type else intent.model_copy(
        update={"item_type": zones.default_category_for_zone(zone, intent)}
    )
    return generate_concepts(
        f"{session_id}__{zone}", round, zone_intent.model_dump(),
        cells=cells, model=model, dry_run=dry_run,
    )


def _empty_zone_result() -> dict[str, Any]:
    """連身裙的另一區——概念上跟 ZoneSlate(requested=False, products=[]) 一致，
    保留 cells/prompt_used/grid_image 三個鍵讓前端不用處理 undefined，只是
    內容是空的：連身裙本身涵蓋下半身，不用也不該幫下身區另外生一張圖。"""
    return {"cells": [], "prompt_used": "", "grid_image": None}


def _assemble_concept_zone_response(
    state: session_store.SessionState,
    zone_results: dict[str, dict[str, Any]],
    message_history: list[str],
    dry_run: bool,
    user_profile: UserProfile,
) -> dict[str, Any]:
    """統一組裝 /concept-image 的兩分區回應——Top Pick 理由沿用既有邏輯
    （上衣格、下身格各自第一格位置性配對，套用跟 /recommend 一樣的自然語句
    改寫；dry_run 沒有實際內容可以改寫，維持 None）。"""
    top_pick_reason = None
    if not dry_run:
        top_cells = zone_results["top"].get("cells") or []
        bottom_cells = zone_results["bottom"].get("cells") or []
        if top_cells and bottom_cells:
            draft = (
                f"上衣：{top_cells[0].get('prompt_fragment') or ''}；"
                f"下身：{bottom_cells[0].get('prompt_fragment') or ''}"
            )
            # 2026-09-20：跟 /recommend 的 apply_natural_language_reasons() 一樣
            # 多帶 profile_context，生圖的 Top Pick 理由也不該只是通用台詞。
            rewritten = llm_client.rewrite_recommendation_reasons(
                [("top-pick", draft)],
                " ".join(message_history),
                recommend.build_profile_context(state.intent, user_profile),
            )
            top_pick_reason = (rewritten or {}).get("top-pick")

    return {
        "session_id": state.session_id,
        "round": state.round,
        "zones": {"top": zone_results["top"], "bottom": zone_results["bottom"]},
        "top_pick_reason": top_pick_reason,
    }


@app.get("/health")
def health() -> dict[str, str]:
    # 純粹給人／監控工具確認服務有沒有活著，不需要登入。
    return {"status": "ok"}
