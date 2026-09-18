# ENGINE03 — 偏好回饋迴圈

**負責人：待確認。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

把自由文字回饋加上分項評分（顏色／版型／圖案／領子——推薦商品跟生成概念圖分開打分）透過 GPT structured output（不用 LangChain）轉成結構化的權重調整／意圖修正。結果會觸發 ENGINE01／02／生成模組跑下一輪。這個迴圈就是要在台上明確被量化證明有效的那一塊——看 `RetrievalResult` 裡的 `match_score` 欄位（回饋前 → 回饋後）。

完整規格：[../../docs/engine03-feedback.md](../../docs/engine03-feedback.md)。輸入輸出 JSON：[../../docs/interface-contract.md](../../docs/interface-contract.md)（`FeedbackInput` 進、`FeedbackResult` 出）。

需要 `OPENAI_API_KEY`（見根目錄 `CLAUDE.md` 的「P0 現況」）。
