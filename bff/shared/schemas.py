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
    file-backed (bff/shared/user_store.py), not a database -- see
    CLAUDE.md "資料庫"."""

    sub: str
    """Google account id (the ID token's `sub` claim) -- primary key."""
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    # 下面兩個是登入後可略過的偏好調查欄位，沒填就是 None／空陣列。
    age_range: Optional[str] = None
    style_preferences: list[str] = Field(default_factory=list)
    onboarding_completed: bool = False
    created_at: str
    """ISO 8601 timestamp."""


class ProfileUpdate(BaseModel):
    """Partial update for PUT /profile. Every field is optional so a user
    clicking "skip" can just send onboarding_completed=True with nothing else."""

    # 三個欄位都選填：前端只送有要更新的欄位，其餘留 None，
    # 後端（main.py 的 put_profile）看到 None 就跳過、不覆蓋原本的值。
    age_range: Optional[str] = None
    style_preferences: Optional[list[str]] = None
    onboarding_completed: Optional[bool] = None


class GoogleAuthRequest(BaseModel):
    # 前端 Google 登入按鈕成功後拿到的那個已簽章 JWT，原封不動轉送給後端驗證，
    # 後端自己不簽發這個 token，只負責驗證它是不是 Google 真的發的。
    id_token: str
    """The `credential` JWT returned by Google Identity Services on the frontend."""


class AuthResponse(BaseModel):
    # session_token 是我們自己簽的（見 bff/shared/auth.py），
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


# ── 回饋迴圈相關（ENGINE03 會用到，ENGINE01 這邊先定義好介面）──────────


class AttributeScore(BaseModel):
    # 針對某個具體屬性（顏色／版型／圖案／領子）的評分，不是打一個總分，
    # 這樣 ENGINE03 才知道要調整哪個維度的權重。
    attribute: str
    score: float
    comment: Optional[str] = None


class FeedbackInput(BaseModel):
    session_id: str
    round: int
    # 推薦商品跟生成概念圖分開打分，所以要標明這次評分是對哪一邊。
    target: Literal["recommended", "generated"]
    attribute_scores: list[AttributeScore] = Field(default_factory=list)
    free_text: Optional[str] = None
    selected_option_id: Optional[str] = None


class WeightAdjustment(BaseModel):
    # ENGINE03 把回饋轉換成的具體權重調整，field 對應 Intent 或排序訊號的名稱，
    # delta 是調整量（正負皆可），reason 是給前端顯示的說明文字。
    field: str
    delta: float
    reason: Optional[str] = None


class FeedbackResult(BaseModel):
    session_id: str
    round: int
    updated_intent: Intent
    weight_adjustments: list[WeightAdjustment] = Field(default_factory=list)


# ── ENGINE02／生成模組的輸出（ENGINE01 這邊先定義好介面，實際邏輯不在這裡）──


class ProductCard(BaseModel):
    # 檢索出來的單一商品卡片。
    product_id: str
    image_url: str
    title: str
    attributes: dict[str, str] = Field(default_factory=dict)
    score: float
    reason: str


class ConceptImage(BaseModel):
    image_url: str
    prompt_used: str
    response_id: Optional[str] = None
    """OpenAI Responses API id, passed as previous_response_id on the next round."""


class RetrievalResult(BaseModel):
    session_id: str
    round: int
    products: list[ProductCard]
    concept_image: ConceptImage
    match_score: float
    """The on-stage "符合度分數" shown before/after feedback (e.g. 62% -> 89%)."""
