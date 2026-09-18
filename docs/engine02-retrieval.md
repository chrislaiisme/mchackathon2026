# ENGINE02 — 檢索與排序

**負責人：待確認。** 這份是從 [hackathon-brief.md](hackathon-brief.md) 抄出來的骨架摘要——正式負責人接手後應該把這裡展開成真正的規格（Polyvore 資料集實際的欄位名稱、reranker 的權重公式等），不要直接把這份當成定案。

## 目標

拿到 ENGINE01 產出的目前 `Intent`，檢索並排序出符合的商品，並為每個結果生成有根據的自然語言理由。核心不是 GPT 驅動的——這是自己實作的 hybrid search ＋ reranker，GPT 只在最後一步負責把理由講出來。

## 資料

Polyvore Outfits Dataset（[huggingface.co/datasets/mvasil/polyvore-outfits](https://huggingface.co/datasets/mvasil/polyvore-outfits)）當核心商品庫。

## 做法（依簡報內容）

- **Dense 側**：FashionCLIP embedding 抓語意風格相似度（例如「簡約」「正式」「防水」）。
- **Sparse 側**：屬性過濾／BM25（`rank_bm25`）抓精確條件（顏色、價格區間、季節、尺寸）。
- **Reranker**：合併 dense/sparse 相似度分數、Polyvore 式的穿搭相容性分數、ENGINE03 學到的偏好權重，決定最終排序——因為每個訊號都可追溯，每個結果都能講出「為什麼排在這裡」（呼應「可解釋」要求）。
- 生成模組（`bff/images/`）產出的概念圖，也會轉成 FashionCLIP 向量併入 dense 側分數，讓檢索和生成互相加強，不是各跑各的兩套系統。
- 向量儲存：Chroma 或 FAISS，嵌在 Python process 裡——兩天的開發時程用不到另外開一套資料庫服務。
- 推薦理由生成：排序後的商品屬性 → GPT chat completions → 一句根據真實檢索屬性寫成的自然語言句子，不是憑空生成。

## 介面

輸入：`Intent`（來自 ENGINE01）＋權重調整（來自 ENGINE03）。輸出：`RetrievalResult`（`products: ProductCard[]`、`concept_image`、`match_score`）——見 [interface-contract.md](interface-contract.md)。

## 離線驗證

Ablation 實驗：同一批測試 query，分別跑純關鍵字搜尋、純 embedding 搜尋、hybrid+rerank 三種，比較 Precision@5／NDCG@5，證明 hybrid 方案的優勢。見 [validation-plan.md](validation-plan.md)。

## 依賴

`OPENAI_API_KEY`（只有推薦理由生成這一步需要——檢索／排序本身的運算不呼叫 GPT）。
