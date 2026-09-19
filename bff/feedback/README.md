# bff/feedback/

負責線：線 4｜Runtime、回饋迴圈與打包
對應功能：FR-008 Preference Feedback Loop

## 負責內容

- 接收分維度評分（商品與概念圖分開）、圖片選擇題答案、自由回饋
- 搭配 `agent/skills/feedback-interpreter/`，把回饋轉成偏好調整或意圖修正
- 選擇題答案直接更新屬性偏好
- 計算回饋前後的符合度分數
- 每次偏好變動都記下是哪一筆回饋造成的

## 介面

- 需要：使用者的評分、選擇與回饋（線 5）
- 提供：偏好權重（線 2）、回饋後的意圖修正（線 3）

目前狀態：尚未開始。

---

（以下併自搬移前的 `bff/feedback/README.md`）

# ENGINE03 — 偏好回饋迴圈

**負責人：待確認。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

把自由文字回饋加上分項評分（顏色／版型／圖案／領子——推薦商品跟生成概念圖分開打分）透過 GPT structured output（不用 LangChain）轉成結構化的權重調整／意圖修正。結果會觸發 ENGINE01／02／生成模組跑下一輪。這個迴圈就是要在台上明確被量化證明有效的那一塊——看 `RetrievalResult` 裡的 `match_score` 欄位（回饋前 → 回饋後）。

完整規格：[../../docs/engine03-feedback.md](../../docs/engine03-feedback.md)。輸入輸出 JSON：[../../docs/interface-contract.md](../../docs/interface-contract.md)（`FeedbackInput` 進、`FeedbackResult` 出）。

需要 `OPENAI_API_KEY`（見根目錄 `CLAUDE.md` 的「P0 現況」）。

---

## 怎麼接（已實作並驗證）

`main.py` 是 ENGINE 03 的服務。一輪的流向：

1. 前端把該輪回饋 POST 到 `/feedback`：分維度評分、自由文字、按讚／倒讚的卡片 id
2. 服務回傳 `feedback` 物件（`FeedbackInput` 格式）
3. 呼叫端把它原樣放進 ENGINE 02 `/retrieve` 的 `feedback` 欄位，跑下一輪

```bash
uvicorn bff.feedback.main:app --port 8003 --reload
```

實測結果（`engine02.intent_adapter.feedback_from_engine03` 轉換）：

| 前端送的 | ENGINE 02 轉成 |
|---|---|
| 顏色 −1 | `design_adjust_steps: {dark_tone: -1}` |
| 版型 +1 | `design_adjust_steps: {relaxed_fit: +1}` |
| 按讚某張卡 | `chosen_item_ids` |
| 對不到設計軸的屬性 | 回報在 `unresolved`，不會靜默丟掉 |

可用的評分維度（對應表在 `engine02/intent_adapter.py::FEEDBACK_ATTRIBUTE_TO_ELEMENT`）：
顏色、版型、圖案、領子、材質、正式感、風格、logo、運動。

## 兩個要注意的地方

1. **不可以混格式。** ENGINE 02 看到 `chosen_item_ids`、`design_adjust_steps` 這類欄位，就會判定
   payload 已經是它自己的格式而整包放行，`attribute_scores` 會被靜默忽略。所以這裡只送
   `FeedbackInput` 宣告的欄位。

2. **倒讚傳不過去。** `FeedbackInput` 沒有對應欄位，倒讚只會進本地帳本。要讓倒讚影響排序，
   得跟 ENGINE 02 擴充契約（他們的 `FeedbackState` 有 `rejected_item_ids`，但混格式會踩到第 1 點）。
