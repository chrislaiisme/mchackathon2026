# ENGINE02 — 檢索與排序

**負責人：待確認。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

Hybrid search（FashionCLIP dense embedding ＋ BM25／屬性 sparse 過濾），在 [Polyvore Outfits Dataset](https://huggingface.co/datasets/mvasil/polyvore-outfits) 上跑，用風格相似度分數、Polyvore 式穿搭相容性分數、ENGINE03 學到的偏好權重合併重新排序。GPT（chat completions，不用 LangChain）把最終排序寫成一句根據商品真實屬性的自然語言理由。生成模組產出的概念圖也會轉成向量併入 dense 側分數，讓檢索跟生成互相加強。

完整規格：[../../docs/engine02-retrieval.md](../../docs/engine02-retrieval.md)。輸入輸出 JSON：[../../docs/interface-contract.md](../../docs/interface-contract.md)（`Intent` 進、`RetrievalResult` 出——看 `ProductCard`）。

推薦理由生成這一步需要 `OPENAI_API_KEY`（見根目錄 `CLAUDE.md` 的「P0 現況」）。
