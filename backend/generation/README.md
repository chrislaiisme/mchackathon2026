# 生成模組 — 概念圖

**負責人：待確認（提議跟 `pinterest/` 合併，見 docs/pinterest-and-generation.md）。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

用 OpenAI Responses API 的 `image_generation` tool，從目前的 `Intent` 每一輪產出一張原創概念圖（`action: "auto"`，用 `previous_response_id` 跨輪銜接，讓模型看得到上一輪的圖加上這輪回饋，不用整張重生成）。Prompt 要維持抽象（顏色／剪裁／場合／材質），避免點名真實品牌或設計師。現場 demo 跑幾輪完全由使用者回饋決定（不是模型自己決定要不要停）；離線驗證迴圈則固定跑 2–4 輪，用 FashionCLIP 相似度當量化停止依據。

完整規格：[../../docs/pinterest-and-generation.md](../../docs/pinterest-and-generation.md)。輸出 JSON：`RetrievalResult` 裡的 `ConceptImage`，見 [../../docs/interface-contract.md](../../docs/interface-contract.md)。

需要 `OPENAI_API_KEY`（見根目錄 `CLAUDE.md` 的「P0 現況」）。範例程式碼在 [../../docs/hackathon-brief.md](../../docs/hackathon-brief.md) 的「評分怎麼具體變成下一次生成的修正」段落。
