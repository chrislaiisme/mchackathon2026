# 介面契約 — ENGINE01 ↔ ENGINE02 ↔ ENGINE03 ↔ 前端

**狀態：draft v1，由 ENGINE01 負責人先寫，目的是讓其他線可以馬上平行開發。ENGINE02/03／前端的負責人確認過、簽核過才算定案——有想改欄位名稱或想加欄位，請直接提出。**

Python 版的真相來源是 [`backend/shared/schemas.py`](../backend/shared/schemas.py)（Pydantic models）。這份文件是講「為什麼」有這些欄位、附上範例 JSON；如果兩邊有出入，一律以程式碼為準。

## 為什麼要有這份文件

依規劃文件的分工段落：五條線要真的能平行開發，前提是動工前把彼此之間的 JSON 長相談好，因為現場兩天沒有餘裕邊寫邊改介面。這份文件就是那個「先談好」的初版。

## 0. 使用者身分（`UserProfile`）

必須登入才能用 `/intent`（Google OAuth，見根目錄 `CLAUDE.md` 的「Google OAuth Client ID」與 [engine01-intent.md](engine01-intent.md) 的「登入」）。登入流程：前端拿到 Google 的 `credential`（ID token）→ `POST /auth/google`（`GoogleAuthRequest`）→ 後端回傳 `AuthResponse`（`session_token` ＋ `profile`）→ 之後每個 API 呼叫都帶 `Authorization: Bearer <session_token>`。

```json
{
  "sub": "1234567890",
  "email": "user@example.com",
  "name": "王小明",
  "picture": "https://...",
  "age_range": "25-34",
  "style_preferences": ["韓系", "簡約"],
  "gender": "女",
  "contexts": ["日常", "上班"],
  "onboarding_completed": true,
  "created_at": "2026-09-18T07:00:00+00:00"
}
```

- `sub` 是 Google 帳號 ID，當這個使用者的主鍵，同時也是 `data/users/<sub>.json` 的檔名。
- `age_range`／`style_preferences` 來自登入後的偏好調查（`PUT /profile`，`ProfileUpdate`——五個欄位在 request body 上都是選填，方便 partial update，但**2026-09-19 起整份調查改成註冊時必填，不能再略過**：後端會擋下「`onboarding_completed=true` 但 `age_range`／`gender`／`style_preferences`／`contexts` 任一個是空的」這種請求，回 400；前端也拿掉了原本的「Skip」按鈕）。目前只是存起來，還沒接進 ENGINE01 抽取 prompt；`gender`／`style_preferences` 已經接進 `POST /recommend` 送給 ENGINE02 的 payload，見下面第 6 節。
- `gender`／`contexts` 是 2026-09-19 新增的欄位，對齊實際蓋出來的前端（IntentWeave）onboarding 畫面實際蒐集的題目——原始 draft v1 沒有這兩個欄位，前端已經改成真的呼叫 `PUT /profile`（見 [frontend.md](frontend.md)），後端這次跟著補上。
- `Intent` 相關的呼叫（下面第 1–5 節）現在全部要掛在登入使用者底下：後端用 `(user_id, session_id)` 當 session 的 key，`user_id` 從驗證過的 token 解出來，不是前端自己傳的。

## 1. 結構化意圖（`Intent`）

由 ENGINE01 產出，ENGINE02（用來組檢索條件）和 ENGINE03（用來知道要修正什麼）都會用到。

```json
{
  "item_type": "外套",
  "colors": ["黑色"],
  "occasion": "正式場合",
  "budget_min": null,
  "budget_max": 3000,
  "style_keywords": ["簡約", "剪裁俐落"],
  "material": "秋冬材質",
  "season": "秋冬",
  "fit": null,
  "pattern": null,
  "collar": null,
  "outfit_requested": false,
  "inferred_fields": ["season"],
  "notes": null
}
```

- 除了容器本身，每個欄位都是選填——一句模糊或講不清楚的話，就只會產出大部分是 null 的意圖，再搭配澄清問題。
- `inferred_fields` 列出上面哪些欄位是 GPT 用情境合理推斷出來的（天氣、季節等），不是使用者親口說的。前端一定要用不同的視覺樣式呈現這些欄位（例如標上「系統推斷」）——這就是「可解釋」要求的具體實作，意圖面板裡沒有任何一個欄位是不標明來源的。
- `colors` ／ `style_keywords` 用陣列，因為一句話裡可能不只講一個。
- `outfit_requested`（2026-09-19 新增）：使用者要的是一整套穿搭（「一套」「整套」「幫我搭配」）還是單一品項。`true` 時 `item_type` 可以是 `null`，不代表抽取失敗。
- **核心欄位把關（2026-09-19 新增）**：`item_type`（`outfit_requested=true` 時不算）、`colors`、`occasion`、`material`、`season`、`style_keywords` 是核心欄位，ENGINE01 會優先針對還缺的核心欄位出選擇題，直到都有值或這個 session 已經問滿 5 題為止（`backend/engine01_intent/gating.py`，決定性把關，不只是拜託 LLM）；`budget_min`／`budget_max`／`fit`／`pattern`／`collar` 不主動問，使用者自己提到才記錄。

## 2. 澄清問題（`ClarifyingQuestion`）

只要目前的 `Intent` 太模糊、不夠拿去搜尋，ENGINE01 就會產出這個。同一個格式每一輪都會重用，不只是第一輪才有。

```json
{
  "field": "occasion",
  "question": "這件外套主要會在什麼場合穿？",
  "options": [
    {"id": "casual", "label": "日常休閒"},
    {"id": "work", "label": "上班／正式"},
    {"id": "date", "label": "約會／社交"}
  ],
  "allow_free_text": true
}
```

前端每次都要在選項旁邊附一個自由輸入欄（`allow_free_text` 實務上應該一直是 `true`，但這個欄位還是保留，以防哪一題設計成純選項）。

## 3. 回饋輸入（`FeedbackInput`）

由前端（使用者／評審）產出，ENGINE03 消費。推薦商品和生成概念圖**分開**打分——這是刻意設計，這樣 ENGINE03 才能知道要調整的是檢索分支還是生成分支。

```json
{
  "session_id": "abc123",
  "round": 1,
  "target": "recommended",
  "attribute_scores": [
    {"attribute": "color", "score": 0.8, "comment": null},
    {"attribute": "fit", "score": 0.3, "comment": "太正式了"}
  ],
  "free_text": "整體不錯，但希望休閒一點",
  "selected_option_id": null
}
```

`target` 是 `"recommended"` 或 `"generated"`——使用者兩邊都打分時，前端就送兩個各自的 `FeedbackInput`。

## 4. 回饋結果（`FeedbackResult`）

由 ENGINE03 產出，ENGINE01（更新後的意圖）和 ENGINE02／生成模組（權重調整）拿去跑下一輪。

```json
{
  "session_id": "abc123",
  "round": 2,
  "updated_intent": { "...": "跟 Intent 同樣的格式，套用修正後" },
  "weight_adjustments": [
    {"field": "fit", "delta": -0.4, "reason": "使用者覺得太正式，降低正式風格權重"}
  ]
}
```

## 5. 檢索結果（`RetrievalResult`）

由 ENGINE02 和生成模組一起產出（兩者同一輪並行執行，結果合併成一個回應給前端）。

```json
{
  "session_id": "abc123",
  "round": 1,
  "products": [
    {
      "product_id": "polyvore_123",
      "image_url": "https://...",
      "title": "Slim wool blazer",
      "attributes": {"color": "black", "material": "wool"},
      "score": 0.91,
      "reason": "符合你要求的黑色、正式場合，剪裁俐落",
      "reason_contributions": [
        {"term": "dense", "group": "dense", "contribution": 0.5, "cited": true},
        {"term": "design:formal_style", "group": "design", "contribution": 0.41, "cited": true}
      ],
      "explanation_source": "template"
    }
  ],
  "concept_image": {
    "image_url": "https://...",
    "prompt_used": "一件簡約風格的黑色正式場合外套，剪裁俐落，秋冬材質",
    "response_id": "resp_abc"
  },
  "match_score": 0.62
}
```

- `match_score` 就是現場 demo 上、回饋前後都會顯示的「符合度分數」（例如「62% → 89%」）——這是舞台上真實可見、證明回饋迴圈有效的關鍵欄位，不要拿掉。
- `concept_image.response_id` 是 OpenAI Responses API 的 id，留著讓生成模組下一輪可以當 `previous_response_id` 接續，不用每次從頭生成。
- `concept_image` 是**選填**——生成模組還沒做出來之前，ENGINE02 單獨測試時填不出這個欄位，回 `null` 是合法的。
- `reason_contributions`／`explanation_source` 是選填欄位（2026-09-19 因應 ENGINE02 的實作加進來）：ENGINE02 的排序是逐項加總算出 `score` 的，`reason_contributions` 把每一項的貢獻量都列出來，加總會等於 `score`，這個分解本身就是可解釋性的核心證據，不是另外生成的說明文字。沒有這個資訊的引擎（或還沒實作的模組）可以留空陣列，不影響既有欄位。

## 6. 兩分區推薦（`POST /recommend`，2026-09-19 已實作）

補上 ENGINE01 之前完全沒有程式碼呼叫 ENGINE02 這個缺口。整合端點是 ENGINE02 負責人在交接文件（HackMD）裡指名的 `POST /intent/rank`（"the single touchpoint for ENGINE01 team"），透過既有介接層掛在 `{ENGINE02_BASE_URL}/engine02/intent/rank`——跟 `backend/engine02_retrieval/main.py` 的 `POST /retrieve` 呼叫的是同一套 `engine02/intent_adapter.py` 邏輯、回傳同一個 `RetrievalResult` 形狀，兩者功能等價，這次選 `/intent/rank` 是照 ENGINE02 負責人的直接指示。

實作在 `backend/engine01_intent/`：`zones.py`（兩分區對照表跟預設品項）、`engine02_client.py`（`intent_rank()`／`visual_search()` 兩支 HTTP client，防禦性寫法，失敗一律回 `None`）、`query_text.py`（把 `Intent` 組成 `visual_search` 要的 `retrieval_text`）、`recommend.py`（`build_zoned_recommendation()` orchestration）。

```json
{
  "session_id": "abc123",
  "round": 2,
  "outfit_requested": false,
  "zones": [
    {"zone": "bottom", "requested": false, "products": []},
    {"zone": "top", "requested": true, "products": [ "...ProductCard[]，最多 6 件..." ]}
  ]
}
```

- **`ZoneSlate`／`ZonedRecommendationResult`（ENGINE01 提案，尚未經 ENGINE02／前端負責人確認欄位命名）**：`zone` 只有 `"top"`／`"bottom"` 兩種（使用者這次的要求，不是三分區）；`requested` 標示這區是不是使用者這輪明確要的（單品命中的那區、或整套請求時的兩區），`false` 代表是代進代表性品項猜的預設，不是查詢失敗。
- **兩分區對照表**（`zones.py::zone_of()`）：ENGINE02 `legacy_coarse` 的 9 分類裡，只有 `bottom` 歸下身區，其餘（`top`／`outerwear`／`dress`／`shoes`／`bag`／`accessory`／`jewelry`／`other`）一律歸上衣區——刻意簡化的暫定慣例，之後要更細緻分類要跟前端／ENGINE02 負責人一起談。
- **連身裙規則**（`zones.py::is_dress()`）：`category == "dress"` 時歸上衣區顯示，下身區整個留空（`requested=false, products=[]`），不會再代查一次。
- **參考圖／視覺特徵串接**：有參考圖（使用者上傳或 Pinterest 比對到的）時，改呼叫 ENGINE02 的 `POST /visual-search`（base64 圖片＋非空 `retrieval_text`）決定主分區結果。**兩個重要限制要記住**：(1) ENGINE02 自己的研究文件（`docs/research/visual-search-gaps.md` 缺口 #1）記錄一個已知 bug——`retrieval_text` 是空字串時查詢向量會被稀釋成「80% 通用詞彙＋20% 照片」，`query_text.py` 一定帶非空文字繞開它，不是等 ENGINE02 修好；(2) `/visual-search` 回的是 ENGINE02 原始排序結果，不是 `/intent/rank` 那樣經過完整可解釋性轉換的形狀，所以這條路徑組出來的 `ProductCard.reason` 只有一句固定說明（`explanation_source="visual_search"`），沒有逐項貢獻拆解——這是真實的能力落差。
- **核心欄位把關**：呼叫 `/recommend` 之前，前端預期 `POST /intent` 的 `clarifying_questions` 已經變空（核心欄位都問完，或已經問滿 5 題預算，見 `backend/engine01_intent/gating.py`），但後端不強制擋這件事。
- **onboarding 資料併入**：`UserProfile.gender` 一律塞進送出給 ENGINE02 的 `intent` dict（`engine02/intent_adapter.py:288-291` 有處理這個 key）；`style_keywords` 這輪是空的時候，退回 `UserProfile.style_preferences` 當這次送出去的值，不寫回 session；`age_range` 沒有對應的 ENGINE02 掛勾，這次不傳。
- **還沒接的下一步方向**：ENGINE02 的 `engine02/outfit_budget.py`（多選背包演算法，`/complete-look` 的 `budget` 參數會用到）可以做到「給預算，直接規劃一套含上衣/下身/外套/鞋的完整穿搭」，比現在「兩分區各自代表性品項各查一次」更貼近使用者要套裝時的真實需求，`POST /recommend` 目前沒有用到這個能力（`POST /style-me`，見下面 §6a，有實際接上 `/complete-look`，但沒有用到 `budget` 參數），之後接手的人可以考慮換過去。

## 6a. 「幫你搭」（`POST /style-me`，2026-09-19 已實作）

使用者明確要求「不能隨機配，要有理由」。這支端點給一件使用者已經在畫面上看到的商品（`anchor_product_id`＋`anchor_zone`，錨點在哪一區前端自己標明，不會另外查），回傳「錨點的另一區」一件有理由的搭配建議。

```json
{
  "session_id": "abc123",
  "round": 2,
  "zone": "bottom",
  "complement": {
    "product_id": "...",
    "image_url": "...",
    "title": "...",
    "score": 0.91,
    "reason": "顏色跟你選的上衣很搭",
    "explanation_source": "complete_look"
  }
}
```

實作在 `backend/engine01_intent/style_me.py`，依序嘗試兩條路：

1. **ENGINE02 的 `POST /complete-look`**（`engine02_client.complete_look()`）：拿錨點商品去查真正依相容性排序過的互補商品，`reason` 直接是 ENGINE02 算出來的（`engine02/service.py::_slate_reason()`，根據 contributions／category_score／price 組字），`explanation_source="complete_look"`。HTTP 層的 `n_categories` 沒辦法直接指定「我要 bottom 分類」，這裡固定要 8 個（等於 ENGINE02 粗分類的數量）換取目標分區幾乎一定出現在回傳的 slates 裡，再用 `zones.zone_of()` 挑出來。
2. **錨點不在 ENGINE02 商品庫**（最典型的情況：錨點其實是生圖，生成模組還沒做出來，但這條路將來一定會發生——ENGINE02 完全沒有生圖的相容性資料，`/complete-look` 會回 400）：退回代表性品項查詢（沿用 `/recommend` 同一套 `zones.default_category_for_zone()`＋`engine02_client.intent_rank()`），理由交給 `llm_client.generate_freeform_text()`（`codex exec`，跟 ENGINE01 抽取意圖同一套零成本機制，純文字輸出、不用 `--output-schema`）生一句，帶入目前 `Intent`（顏色／風格關鍵字／場合／季節）跟這幾輪對話文字當上下文，`explanation_source="llm_fallback"`。LLM 也失敗（`codex` 沒裝、逾時）就用固定文案「依你的風格偏好推薦這個搭配」，不會讓端點掛掉。
3. 兩條路都拿不到任何候選商品（該分區在商品庫裡真的沒有東西）→ 回 404，不是空的 200。

**標記提案，尚未經 ENGINE02／前端負責人確認欄位命名。**

## 7. 待其他負責人落地的規格（前端／ENGINE02／ENGINE03，尚未寫進 `schemas.py`）

2026-09-19 使用者確認了三項規格（詳細背景見 [frontend.md](frontend.md) 代辦事項 3／4／5），這裡先記錄需要新增的欄位草案，**命名跟型別都還沒定案，要跟相關負責人確認後才落地到 `backend/shared/schemas.py`**：

- **生圖獨立觸發（代辦 3）**：目前 `RetrievalResult.concept_image` 的假設是「跟這一輪的推薦商品同時並行產出、一起回傳」。新規格是使用者要主動按按鈕才觸發生圖，且生圖期間對話框要鎖定。這代表生圖可能需要拆成一支獨立的請求／端點，而不是掛在同一輪的 `RetrievalResult` 裡自動夾帶——確切怎麼調整，需要生成模組負責人／前端負責人一起確認。
- **每張卡片的回饋（代辦 4）**：`FeedbackInput` 目前是「整輪一份」，沒有欄位指出這是對哪一張 `ProductCard`（或哪一張 `concept_image`）的回饋。草案方向：`ProductCard` 需要加 `favorited: bool`／`disliked: bool` 這類欄位（或者回饋改成前端只送「使用者實際做過動作」的項目、每項都帶一個卡片識別碼，而不是像現在整輪送一份）；試穿的 LIKE IT／NOT FOR ME 是另一種獨立訊號，不是細項打分，可能需要 `FeedbackInput.target` 增加一個新值（例如 `"tryon"`）或另外開一個更簡單的 model（不需要 `AttributeScore` 那麼細的結構，就是一個布林值）。**沒有任何動作的卡片不應該出現在送出的回饋資料裡**（配合 [engine03-feedback.md](engine03-feedback.md) 新增的「未互動不計權重」規則）。**2026-09-19 補充規則：只有虛擬形象穿上「一整套」（上衣區＋下身區都試穿上了）才能按 LIKE IT／NOT FOR ME，只穿單一單品沒有這兩個按鈕**——所以這個 tryon 訊號的資料形狀至少要帶 `top_product_id`＋`bottom_product_id` 兩個 id（不是單一 `product_id`），前端也要在只穿一件的狀態下把這兩個按鈕藏起來，不是禁用。
- **收藏小屋（代辦 5）**：目前的 model 裡沒有「使用者收藏了哪些商品／概念圖」這個持久清單的容身之處——`UserProfile` 是使用者設定，`SessionState`（ENGINE01 內部，不是共用 schema）是單一對話的暫存狀態，收藏清單性質上比較像前者（per-user、跨 session 持久），但要不要併進 `UserProfile` 還是另開一個 model，留給前端／ENGINE01 負責人一起談。分類可以直接沿用 ENGINE02 既有的 `category`/`subcategory`／taxonomy 欄位；生成出來的概念圖沒有這個欄位，需要額外設計怎麼打分類標籤。

## 給其他引擎負責人的待確認事項

- `weight_adjustments` 的 `field` 要不要固定成一個 enum，還是維持自由文字、對應 `Intent`／排序訊號的名稱——目前是自由格式，如果 ENGINE02/03 需要更嚴格的比對再收緊。
- `AttributeScore.score` 和 `RetrievalResult.match_score` 的單位／範圍——目前都是 0–1 的浮點數，請確認這樣是否適合 ENGINE03 實際的權重運算方式。
- `FeedbackInput.target` 未來可能要加第三種值（目前只有 `"recommended"`／`"generated"`）：虛擬形象試穿的 LIKE IT／NOT FOR ME 回饋（見上面第 7 節、[pinterest-and-generation.md](pinterest-and-generation.md#虛擬形象試穿延伸功能2026-09-18-使用者口頭補充不在原始簡報或-hackathon-briefmd-裡)）2026-09-19 已經定案走簡單的二選一，不是細項打分——`"tryon"` 這個值該怎麼設計（沿用 `FeedbackInput` 加值，還是另開更簡單的 model）還沒定案。
- **參考圖欄位——已經找到接的方法，不再是空白待辦**：ENGINE01 現在會解析出一張參考圖（使用者上傳或 Pinterest 板子比對，見 [pinterest-and-generation.md](pinterest-and-generation.md)），`POST /recommend` 呼叫時會直接送進 ENGINE02 的 `POST /visual-search`（base64 圖片），不是透過 `Intent` model 的欄位傳遞，所以不需要在共用 schema 加欄位——細節見上面第 6 節。這張圖只能給 ENGINE02 內部參考，不會透過任何回應欄位讓前端顯示出來。
