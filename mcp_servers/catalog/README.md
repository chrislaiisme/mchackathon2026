# mcp_servers/catalog/

負責線：線 2｜商品推薦與流行趨勢
對應功能：FR-005 Product Recommendation；FR-010 中的三種推薦做法比較

## 負責內容

- 以 Polyvore Outfits Dataset 為商品庫
- 依風格相似度與精確條件（顏色、價格區間、季節、尺寸）檢索
- 合併風格、穿搭相容性、使用者偏好與流行趨勢重新排序，並保留排序依據
- 圖片相似度計算：概念圖併入推薦、驗證流程使用

## 介面

- 需要：結構化意圖（線 1）、概念圖（線 3）、偏好權重（線 4）
- 提供：推薦結果與排序依據（線 4）、圖片相似度計算（線 1）

## 整合前先用

手寫的結構化意圖與固定的偏好權重（`contracts/samples/`）。

資料集本體放在 `data/polyvore/`（本機，不進版控）。

目前狀態：尚未開始。

---

（以下併自搬移前的 `mcp_servers/catalog/README.md`）

# ENGINE02 — 檢索與排序

**負責人：待確認。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

Hybrid search（FashionCLIP dense embedding ＋ BM25／屬性 sparse 過濾），在 [Polyvore Outfits Dataset](https://huggingface.co/datasets/mvasil/polyvore-outfits) 上跑，用風格相似度分數、Polyvore 式穿搭相容性分數、ENGINE03 學到的偏好權重合併重新排序。GPT（chat completions，不用 LangChain）把最終排序寫成一句根據商品真實屬性的自然語言理由。生成模組產出的概念圖也會轉成向量併入 dense 側分數，讓檢索跟生成互相加強。

完整規格：[../../docs/engine02-retrieval.md](../../docs/engine02-retrieval.md)。輸入輸出 JSON：[../../docs/interface-contract.md](../../docs/interface-contract.md)（`Intent` 進、`RetrievalResult` 出——看 `ProductCard`）。

推薦理由生成這一步需要 `OPENAI_API_KEY`（見根目錄 `CLAUDE.md` 的「P0 現況」）。
