# bff/images/

負責線：線 3｜概念圖與選項圖
對應功能：FR-004 Choice Image Generation and Check；FR-007 Concept Image Generation；FR-010 中的選項圖檢查通過率

## 負責內容

- 選項圖：先生成基準圖，每個選項從基準圖只修改一個屬性
- 選項圖自動檢查：明示條件是否仍在、目標屬性是否確實改變；不通過時重生，多次不通過改用文字選項
- 已生成的選項圖固定保存，同一題不重新生成
- 概念圖生成與依回饋的多輪調整
- 生圖服務切換與額度控管（驗證流程與 demo 共用額度）

## 介面

- 需要：結構化意圖與選擇題規格（線 1）、回饋後的意圖修正（線 4）
- 提供：選項圖檢查結果與可出題的屬性清單（線 1）、選項圖（線 4）、概念圖（線 2、線 4）

## 比賽前準備

- 整理先前的生圖可行性驗證結果（褲口、腰線可守住固定條件），放進 `evals/choice_images/`
- 準備 demo 情境的基準圖（放在 `data/demo_cache/`）

目前狀態：尚未開始。

---

（以下併自搬移前的 `bff/images/README.md`）

# 生成模組 — 概念圖

**負責人：待確認（提議跟 `pinterest/` 合併，見 docs/pinterest-and-generation.md）。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

用 OpenAI Responses API 的 `image_generation` tool，從目前的 `Intent` 每一輪產出一張原創概念圖（`action: "auto"`，用 `previous_response_id` 跨輪銜接，讓模型看得到上一輪的圖加上這輪回饋，不用整張重生成）。Prompt 要維持抽象（顏色／剪裁／場合／材質），避免點名真實品牌或設計師。現場 demo 跑幾輪完全由使用者回饋決定（不是模型自己決定要不要停）；離線驗證迴圈則固定跑 2–4 輪，用 FashionCLIP 相似度當量化停止依據。

完整規格：[../../docs/pinterest-and-generation.md](../../docs/pinterest-and-generation.md)。輸出 JSON：`RetrievalResult` 裡的 `ConceptImage`，見 [../../docs/interface-contract.md](../../docs/interface-contract.md)。

需要 `OPENAI_API_KEY`（見根目錄 `CLAUDE.md` 的「P0 現況」）。範例程式碼在 [../../docs/hackathon-brief.md](../../docs/hackathon-brief.md) 的「評分怎麼具體變成下一次生成的修正」段落。
