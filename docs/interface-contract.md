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
  "onboarding_completed": true,
  "created_at": "2026-09-18T07:00:00+00:00"
}
```

- `sub` 是 Google 帳號 ID，當這個使用者的主鍵，同時也是 `data/users/<sub>.json` 的檔名。
- `age_range`／`style_preferences` 來自登入後可略過的偏好調查（`PUT /profile`，`ProfileUpdate`——三個欄位都選填，略過就整包留空、只把 `onboarding_completed` 設成 `true`）。目前只是存起來，還沒接進 ENGINE01 抽取 prompt 或 ENGINE02/03 的排序邏輯，是後續要討論的個人化加分項。
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
  "inferred_fields": ["season"],
  "notes": null
}
```

- 除了容器本身，每個欄位都是選填——一句模糊或講不清楚的話，就只會產出大部分是 null 的意圖，再搭配澄清問題。
- `inferred_fields` 列出上面哪些欄位是 GPT 用情境合理推斷出來的（天氣、季節等），不是使用者親口說的。前端一定要用不同的視覺樣式呈現這些欄位（例如標上「系統推斷」）——這就是「可解釋」要求的具體實作，意圖面板裡沒有任何一個欄位是不標明來源的。
- `colors` ／ `style_keywords` 用陣列，因為一句話裡可能不只講一個。

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
      "reason": "符合你要求的黑色、正式場合，剪裁俐落"
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

## 給其他引擎負責人的待確認事項

- `ProductCard` 的 `attributes` 具體要放哪些 key——要看 Polyvore 資料集實際能乾淨拿到哪些欄位，ENGINE02 負責人請確認／擴充。
- `weight_adjustments` 的 `field` 要不要固定成一個 enum，還是維持自由文字、對應 `Intent`／排序訊號的名稱——目前是自由格式，如果 ENGINE02/03 需要更嚴格的比對再收緊。
- `AttributeScore.score` 和 `RetrievalResult.match_score` 的單位／範圍——目前都是 0–1 的浮點數，請確認這樣是否適合 ENGINE03 實際的權重運算方式。
- `FeedbackInput.target` 未來可能要加第三種值（目前只有 `"recommended"`／`"generated"`）：規劃中的「虛擬形象試穿」延伸功能（見 [pinterest-and-generation.md](pinterest-and-generation.md#虛擬形象試穿延伸功能2026-09-18-使用者口頭補充不在原始簡報或-hackathon-briefmd-裡)）如果最後走細項打分的回饋方式，可以直接沿用這個結構加一個 `"tryon"` 選項，不用另外開一套——確切要不要走這個方向還沒定案。
