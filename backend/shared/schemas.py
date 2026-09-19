"""Cross-engine data contract.

Source of truth for the JSON shapes flowing between ENGINE01/02/03, the
generation module, and the frontend. See docs/interface-contract.md for the
rationale and example payloads behind each model; keep the two in sync when
either changes.

Draft v1 — written by the ENGINE01 owner to unblock parallel development.
Needs sign-off from ENGINE02/03/frontend owners before it's final.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# 偏好調查用的固定選項清單，前端畫勾選框／下拉選單時直接照這個清單畫，
# 後端目前不強制檢查一定要是這幾個值（partial update 允許任意字串），
# 純粹是給前端一個統一的預設選項來源，避免前後端各自硬編碼一份不同步。
STYLE_PREFERENCE_OPTIONS = ["日系", "韓系", "美式", "歐美", "街頭", "簡約", "正式", "其他"]
AGE_RANGE_OPTIONS = ["18-24", "25-34", "35-44", "45+"]


# ── 使用者身分／登入相關 model ──────────────────────────────────────────
# 這幾個 model 是 Google 登入流程在用的：GoogleAuthRequest 是前端傳給
# POST /auth/google 的請求體，AuthResponse 是後端登入成功後的回應，
# UserProfile 是實際存進 data/users/<sub>.json 的使用者資料。


class UserProfile(BaseModel):
    """Persisted per-user record, created on first Google login. JSON
    file-backed (backend/shared/user_store.py), not a database -- see
    CLAUDE.md "資料庫"."""

    sub: str
    """Google account id (the ID token's `sub` claim) -- primary key."""
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    # 下面四個是登入後可略過的偏好調查欄位，沒填就是 None／空陣列。
    age_range: Optional[str] = None
    style_preferences: list[str] = Field(default_factory=list)
    # gender／contexts 是 2026-09-19 為了對齊前端 IntentWeave（Next.js）
    # onboarding 畫面實際蒐集的欄位才加的，原始設計裡沒有——前端 onboarding 已經
    # 有這兩題（性別、使用情境），後端要能接住，不然 PUT /profile 會丟掉這兩個值。
    gender: Optional[str] = None
    contexts: list[str] = Field(default_factory=list)
    # 根據跨對話的明確喜歡／不喜歡回饋累積的風格訊號。保留 onboarding 的
    # style_preferences 當初始偏好；這個欄位才是會隨使用者實際選擇而變動的
    # 長期輪廓，寫進同一份 user JSON，重啟 ENGINE01 也不會消失。
    style_affinities: dict[str, float] = Field(default_factory=dict)
    onboarding_completed: bool = False
    created_at: str
    """ISO 8601 timestamp."""


class ProfileUpdate(BaseModel):
    """Partial update for PUT /profile. Every field is optional so a user
    clicking "skip" can just send onboarding_completed=True with nothing else."""

    # 五個欄位都選填：前端只送有要更新的欄位，其餘留 None，
    # 後端（main.py 的 put_profile）看到 None 就跳過、不覆蓋原本的值。
    age_range: Optional[str] = None
    style_preferences: Optional[list[str]] = None
    gender: Optional[str] = None
    contexts: Optional[list[str]] = None
    onboarding_completed: Optional[bool] = None


class GoogleAuthRequest(BaseModel):
    # 前端 Google 登入按鈕成功後拿到的那個已簽章 JWT，原封不動轉送給後端驗證，
    # 後端自己不簽發這個 token，只負責驗證它是不是 Google 真的發的。
    id_token: str
    """The `credential` JWT returned by Google Identity Services on the frontend."""


class AuthResponse(BaseModel):
    # session_token 是我們自己簽的（見 backend/shared/auth.py），
    # 前端登入成功後要存起來，之後每次打 API 都帶在 Authorization header 裡。
    session_token: str
    profile: UserProfile


# ── 結構化意圖（ENGINE01 的核心輸出）──────────────────────────────────


class Intent(BaseModel):
    """Structured consumer intent extracted from a one-sentence request."""

    # 品項、顏色、場合...這些是「一句話」要被拆解出來的結構化欄位，
    # 全部選填，因為一句模糊的話本來就不會每個欄位都填得出來。
    item_type: Optional[str] = None
    colors: list[str] = Field(default_factory=list)
    occasion: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    style_keywords: list[str] = Field(default_factory=list)
    material: Optional[str] = None
    season: Optional[str] = None
    fit: Optional[str] = None
    pattern: Optional[str] = None
    collar: Optional[str] = None
    outfit_requested: bool = False
    """2026-09-19 新增：使用者是不是要一整套穿搭（「一套」「整套」「幫我搭配」），
    不是單一品項。True 時 item_type 可以維持 None——套裝請求本來就不是在問單一
    品項，見 backend/engine01_intent/prompts.py 的抽取規則、zones.py 的兩分區
    orchestration（ENGINE02 taxonomy 的「套裝」節點筆記本來就預期 ENGINE01 會
    明確標示這件事，見 docs/interface-contract.md 第 6 節）。"""
    inferred_fields: list[str] = Field(default_factory=list)
    """Names of the fields above that GPT filled in by contextual inference
    (weather, season, etc.) rather than the user stating them. The frontend
    must render these as visibly system-inferred, not as the user's own words."""
    notes: Optional[str] = None


# ── 澄清問題：意圖太模糊時，ENGINE01 額外出的選擇題 ────────────────────


class ClarifyingOption(BaseModel):
    # 選擇題的其中一個選項，id 給前端點擊時回傳用，label 是顯示文字。
    id: str
    label: str


class ClarifyingQuestion(BaseModel):
    field: str
    """Which Intent field this question is trying to fill in."""
    question: str
    options: list[ClarifyingOption]
    # 除了選項之外一定要留自由輸入的空間，這個欄位理論上一直是 True，
    # 保留起來是以防哪天真的想出一題純選項、不給自由輸入。
    allow_free_text: bool = True


# ── POST /intent 的請求／回應格式 ──────────────────────────────────────


class IntentRequest(BaseModel):
    session_id: Optional[str] = None
    """Omit to start a new session."""
    message: str
    # 選填的參考圖網址；目前只接受網址字串，還沒有真正的檔案上傳端點。
    reference_image_url: Optional[str] = None


class IntentResponse(BaseModel):
    session_id: str
    round: int
    intent: Intent
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)


# ── 回饋迴圈相關（POST /feedback，接 backend/engine03_feedback/ 的真實實作）──────────
# 2026-09-19：這裡原本是 ENGINE01 自己從零設計的提案（free_text + GPT structured
# output，AttributeScore／FeedbackInput／WeightAdjustment／FeedbackResult 四個型別），
# 但 ENGINE03 實際上線的是完全不同、純規則式（不吃自由文字、不用 LLM）的設計——
# 星等打分＋收藏／不喜歡＋整套喜歡，見 backend/engine03_feedback/contracts.py。
# Grep 確認過整個程式碼庫沒有任何地方 import 舊的那四個型別（只有已知是孤兒程式碼的
# bff/shared/schemas.py／bff/feedback/main.py 提到過），直接換成跟真實契約對齊的形狀，
# 不需要保留舊提案或寫轉換層。


class AttributeRating(BaseModel):
    # attribute 直接收前端 PreferenceRatingDimension 的值（"visual_impact"／
    # "polished_formality"／"soft_energy"），跟 ENGINE03 的 ATTRIBUTE_IDS
    # 一模一樣，兩邊不用另外對一份映射表。
    attribute: str
    stars: int = Field(ge=1, le=5)


class ItemFeedbackRequest(BaseModel):
    item_id: str
    source: Literal["catalog", "generated"] = "catalog"
    favorited: bool = False
    disliked: bool = False
    attribute_ratings: list[AttributeRating] = Field(default_factory=list)
    # design_attributes 故意不開放前端傳——ENGINE03 的驗證規則要求這個欄位只能由
    # 「受信任」的一方填（生成 manifest 的真實內容），前端不算，source="generated"
    # 的回饋今天整批跳過，見 main.py::post_feedback()。


class OutfitItemRequest(BaseModel):
    # 2026-09-19 修正：欄位形狀改成跟團隊另一份「Frontend → BFF 回饋 JSON 規格」
    # 文件的 outfit_feedbacks[].items[] 一致（zone／source／item_id 三欄，不是
    # 原本 top_item_id／bottom_item_id 兩個扁平欄位）——那份規格明確允許整套裡
    # 一件資料庫商品配一件生成商品，前端如果照那份規格寫，不應該因為打的是
    # ENGINE01 而要重寫一次資料形狀。
    zone: Literal["top", "bottom"]
    source: Literal["catalog", "generated"] = "catalog"
    item_id: str


class OutfitFeedbackRequest(BaseModel):
    # 只支援「喜歡」——對應 ENGINE03 OutfitFeedback.favorited 寫死 Literal[True]，
    # 沒有「整套不喜歡」這個概念，backend 本身沒做這一半。
    outfit_id: str
    favorited: Literal[True] = True
    items: list[OutfitItemRequest] = Field(min_length=2, max_length=2)
    """一定剛好兩件，一件 top 一件 bottom——驗證邏輯見 main.py::post_feedback()。
    generated 那一件今天一律跳過整筆 outfit（見 post_feedback() 的說明），
    不是因為規格不允許，是 design_attributes 詞彙映射還沒有人跟 ENGINE02／
    生成模組負責人確認過，不能自己瞎猜著送。"""


class FeedbackRequest(BaseModel):
    session_id: str
    round: int
    item_feedbacks: list[ItemFeedbackRequest] = Field(default_factory=list)
    outfit_feedbacks: list[OutfitFeedbackRequest] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    session_id: str
    round: int
    engine02_feedback: dict
    attribute_evidence: list[dict] = Field(default_factory=list)
    generated_attribute_evidence: list[dict] = Field(default_factory=list)
    outfit_evidence: list[dict] = Field(default_factory=list)
    skipped_generated_item_feedbacks: list[str] = Field(default_factory=list)
    """source="generated" 的單品回饋今天整批跳過，這裡誠實列出被跳過的 item_id，
    不是默默丟掉裝作沒發生——見 docs 記錄的已知落差（design_attributes 詞彙映射
    需要跨負責人確認）。"""
    skipped_generated_outfit_feedbacks: list[str] = Field(default_factory=list)
    """整套裡有任何一件是 source="generated" 就整筆 outfit 跳過（同一個落差，
    不是只挑資料庫那一件單獨送——半套的「整套喜歡」語意會失真），這裡列出
    被跳過的 outfit_id。"""


# ── ENGINE02／生成模組的輸出（ENGINE01 這邊先定義好介面，實際邏輯不在這裡）──


class ReasonContribution(BaseModel):
    """一個評分項目對 ProductCard.score 的貢獻量——ENGINE02 的排序是逐項加總算出總分的
    （dense／bm25／設計要素／相容性／新鮮度／批評…），這裡就是那個加總的其中一項，
    全部 ReasonContribution 的 contribution 加起來要等於對應的 score。
    這是 ENGINE02 可解釋性設計的核心（見 docs/engine02-design.md）：`reason` 只能塞一句話，
    但逐項貢獻需要有欄位才不會被 FastAPI 的 response_model 悄悄丟掉。"""

    term: str
    """貢獻項目名稱，例如 "dense" 或 "design:structured_shoulders"。"""
    group: str
    """這項貢獻屬於哪一類，例如 dense／bm25／design／compat／freshness／critique／penalty。"""
    contribution: float
    """不變式：同一張卡片的所有 contribution 加總 == ProductCard.score。"""
    cited: bool = False
    """這項有沒有被寫進 reason 那句話裡。"""


class ProductCard(BaseModel):
    # 檢索出來的單一商品卡片。
    product_id: str
    image_url: str
    title: str
    attributes: dict[str, str] = Field(default_factory=dict)
    score: float
    reason: str
    reason_contributions: list[ReasonContribution] = Field(default_factory=list)
    """選填，ENGINE02 用來把 score 逐項拆解回傳——沒有這個欄位的引擎可以不填，
    保持空陣列即可，不影響既有行為。"""
    explanation_source: Optional[str] = None
    """這句 reason 是怎麼來的，例如 "llm"（通過事實查核的改寫）或 "template"（樣板句）。"""


class ConceptImage(BaseModel):
    image_url: str
    prompt_used: str
    response_id: Optional[str] = None
    """OpenAI Responses API id, passed as previous_response_id on the next round."""


class RetrievalResult(BaseModel):
    session_id: str
    round: int
    products: list[ProductCard]
    concept_image: Optional[ConceptImage] = None
    """選填——生成模組還沒做出來之前，ENGINE02 填不出這個欄位，不能寫死必填，
    不然單獨測 ENGINE02 時就會直接 ValidationError。等生成模組上線後，
    Live 流程應該每輪都會有值，這裡選填只是讓還沒做完的模組也能先跑。"""
    match_score: float
    """The on-stage "符合度分數" shown before/after feedback (e.g. 62% -> 89%)."""


# ── 兩分區推薦（ENGINE01 提案，2026-09-19，尚未經 ENGINE02／前端負責人確認 ──
# 欄位命名，見 docs/interface-contract.md 第 6 節）：POST /recommend 的回應
# 形狀。跟上面的 RetrievalResult 是兩回事——RetrievalResult 是單一份平坦的
# 商品清單，這裡是「上衣一份、下身一份」固定兩分區的展示邏輯，是 ENGINE01
# 自己在既有的 ENGINE02 檢索能力之上組出來的，不是 ENGINE02 原生就有的形狀。


class ZoneSlate(BaseModel):
    zone: Literal["top", "bottom"]
    requested: bool
    """True＝使用者這輪明確要這個分區（單品命中的那區，或整套請求時的兩區）；
    False＝使用者沒特別要求，是代進代表性品項猜的預設，見 zones.py。"""
    products: list[ProductCard] = Field(default_factory=list)
    """最多 6 件；連身裙情境下的下身區會是空列表且 requested=False（見 zones.py
    的 is_dress 規則），不是查詢失敗。"""
    match_score: float = 0.0
    """2026-09-19 新增：這區的意圖符合度（來自 ENGINE02 RetrievalResult.match_score），
    讓現場能秀出「回饋前 62% → 回饋後 89%」這種量化證明——之前兩分區格式沒有把
    ENGINE02 早就算好的這個分數帶出來。連身裙留空的那一區、或 ENGINE02 連不上時，
    沒有真的查詢過，維持預設值 0.0，不是查詢結果。"""


class ZonedRecommendationResult(BaseModel):
    session_id: str
    round: int
    outfit_requested: bool
    zones: list[ZoneSlate]


class RecommendRequest(BaseModel):
    session_id: str


class RecommendationReasonRewriteRequest(BaseModel):
    """Ask ENGINE01 to proxy ENGINE02's fact-checked card-copy rewrite.

    The browser never talks to ENGINE02 directly: ENGINE01 owns the authenticated
    conversation and has the namespaced session ids that ENGINE02 used to retain
    the card facts for this exact recommendation round.
    """

    session_id: str


class RecommendationReasonRewriteCard(BaseModel):
    product_id: str
    reason: str
    explanation_source: str = "template"


class RecommendationReasonRewriteResponse(BaseModel):
    session_id: str
    round: int
    cards: list[RecommendationReasonRewriteCard] = Field(default_factory=list)


# ── 「幫你搭」（POST /style-me，ENGINE01 提案，2026-09-19，尚未經 ENGINE02／前端 ──
# 負責人確認）：不是隨機配對，是拿一件錨點商品去問 ENGINE02 的
# POST /complete-look 要真的相容性排序＋理由；錨點不在商品庫（例如生圖）時
# 退回 LLM 生一句理由，見 backend/engine01_intent/style_me.py。


class StyleMeRequest(BaseModel):
    session_id: str
    anchor_product_id: str
    """使用者畫面上已經看到的一件商品／生圖 id，當搭配的起點。"""
    anchor_zone: Literal["top", "bottom"]
    """錨點是在哪一區——前端本來就知道（正在顯示哪一區），要求明講，
    這裡不會另外呼叫 ENGINE02 去查這件商品屬於哪一區。"""


class StyledComplement(BaseModel):
    session_id: str
    round: int
    zone: Literal["top", "bottom"]
    """這是「錨點的另一區」——跟 anchor_zone 相反那一區的搭配建議。"""
    complement: ProductCard
    """`complement.reason` 帶搭配理由：ENGINE02 `/complete-look` 算出來的真實
    相容性理由，或錨點不在商品庫時的 LLM 備援理由（`explanation_source` 會
    標明是 "complete_look" 還是 "llm_fallback"）。"""
