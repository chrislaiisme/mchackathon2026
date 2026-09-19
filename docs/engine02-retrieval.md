# ENGINE02 — 檢索與排序

**這份文件已經過時，留著只是給歷史脈絡用。** 底下原本是賽前依 [hackathon-brief.md](hackathon-brief.md) 寫的骨架猜測（Polyvore Outfits Dataset、FashionCLIP、Chroma/FAISS 等），ENGINE02 實際做出來的方向不一樣（KAGL 商品庫、自寫的 BM25、逐項加總可解釋分數、taxonomy），比賽前的猜測不再準確，不要照這份施工。

真正的規格在這幾份文件：

- [`docs/engine02-design.md`](engine02-design.md) — 完整設計與所有實驗結果（§3.1–§3.35，每個結論都有對照組跟統計檢定）。
- [`docs/engine02-pipeline.md`](engine02-pipeline.md) — 管線、現場 demo 腳本、上台前檢查清單。
- [`docs/engine02-literature-review.md`](engine02-literature-review.md) — 文獻回顧。
- [`../backend/engine02_retrieval/README.md`](../backend/engine02_retrieval/README.md) — 怎麼跑、端點清單、跟團隊介面的整合細節。
- [`docs/research/`](research/) — 專題研究報告（人類標註協議、外部 benchmark、視覺搜尋落差分析等）。

跨引擎 JSON 契約（`Intent` 進、`RetrievalResult` 出）見 [`interface-contract.md`](interface-contract.md)；ENGINE02 額外用到的請求／回應細節見 [`docs/contract/`](contract/) 底下的 JSON Schema 跟範例。
