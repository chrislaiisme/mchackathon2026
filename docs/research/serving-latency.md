# 上線延遲：ENGINE 02 的服務端延遲預算、業界證據與逐檔改法

> 範圍：`/rank`、`/view`、`/complete-look` 的**服務端**延遲，以及現場 demo 的冷啟動與風險。
> 分工：本文只做研究與提案，**沒有改任何既有檔案**；所有程式修改以 `檔案:函式` 形式描述，由 coordinator 實作。
> 量測基準線（coordinator 提供，cfda4 V100，`kagl_polyvore_filled` 17,783 件，Marqo-FashionSigLIP，arm `full_zclip3`，單次 `/rank`）：
> `{"filter": 241.65, "retrieve": 44.28, "fuse": 1.18, "rerank": 0.84, "counterfactual": 0.35, "explain": 10.17}` ms，合計約 298 ms。
> 本文另附**我自己在本機（Windows、CPU-only、Python 3.12、kagl 5,000 件平舖到 17,783 列）跑的微量測**，它們只能用來比較「同一台機器上改法前後的比值」，不能當成伺服器上的絕對值。第 §7 節把「引用的數字」和「我量的數字」分開列。

---

## 0. 一頁摘要

| 階段 | 目前（cfda4，17,783 件） | 可辯護目標 | 達成目標的那**一個**改動 |
| --- | --- | --- | --- |
| `filter` | **241.65 ms** | **≤ 5 ms** | `engine02/constraints.py` 改用「每個商品庫預先算好的正規化 categorical codes」取代每列都跑一次的 `Series.map(_norm)`（本機量測：46.1 → 0.55 ms／段，120/120 遮罩完全相同） |
| `retrieve` | 44.28 ms | **≤ 12 ms** | 兩件事：(a) BM25 換成 scipy CSC 預算權重矩陣（本機 11.4 → 0.24 ms，分數差 5.7e-14、top-50 順序全同）；(b) `pipeline.py:run` 的 `image_emb[pool] @ q` 改成「全庫一次矩陣乘、之後才切 pool」並避免 float32→float64 升型（本機 13.2 → 3.1 ms，top-50 完全相同） |
| `fuse` | 1.18 ms | **≤ 0.2 ms** | `np.argsort(-fused)` 全池排序換成 `np.argpartition` + 只排前 50（本機 1.68 → 0.061 ms，top-50 完全相同） |
| `rerank` | 0.84 ms | 維持 | 不動。已經不是瓶頸 |
| `counterfactual` | 0.35 ms | 維持 | 不動 |
| `explain` | 10.17 ms | **≤ 3 ms** | `pipeline.py:run` 的深層（depth=20+1）那一輪不要產生理由字串與 `Contribution` 物件驗證，只回分數與 contribution 矩陣；理由只為使用者真正看到的 k 張卡產生 |
| **`_metrics`（目前完全沒被計時）** | **約 40 ms（本機量測推估）** | **≤ 1 ms** | `pipeline.py:_metrics` 裡的 `satisfies()` 逐件呼叫 `build_mask`（每件 ~2 ms × 21 件），改成對 `shown_pos` 做一次向量化遮罩後取值 |
| **合計（服務端）** | **約 298 ms +未計時的 ~40 ms** | **約 25–35 ms** | 上面六項；不需要任何新的第三方套件、不需要網路 |
| 冷啟動（首次） | 約 119 s | **≤ 5 s，且不由評審承擔** | `api.py:lifespan` 結尾加一段 warm-up：強制跑 `design_matrix(serving_arm)`、一次假 `/rank`、一次假 `/complete-look`，並讓 `/health` 在 warm-up 完成前回 503 |
| LLM 改寫（`explain_with_llm` 預設 True） | 網路不通時可能**卡數十秒到數分鐘** | 0 ms（現場關掉） | `api.py:rank` 在現場模式強制 `explain_with_llm=False`；若要留，`llm.py:openai_llm` 必須給 `timeout=1.5, max_retries=0` |

**一句話**：`filter` 這 242 ms **完全不是演算法成本，是每次請求在 Python 層對 17,783 列跑了大約 20 萬次 `_norm()` 的成本**。把它換成預先算好的整數碼，整條 pipeline 就會落在業界公開的同量級預算內（Etsy 生產環境 P99 18 ms、Taobao ANN 10 ms），而且**不改變任何排序結果**（我已逐一驗證 bit-level 相同，見 §3）。

---

## 1. 什麼樣的延遲預算是可辯護的

### 1.1 人類感知的門檻（決定「像不像即時」）

- **0.1 s / 1.0 s / 10 s** 三個門檻：0.1 秒以內使用者覺得系統「即時反應」、不需要任何回饋；1.0 秒是「思緒不中斷」的上限（使用者會察覺延遲、失去直接操控感）；超過 10 秒就需要進度指示。源自 Miller (1968)，由 Nielsen 在 *Usability Engineering* (1993) 整理並持續沿用。（<https://www.nngroup.com/articles/response-times-3-important-limits/>，1993 原始、頁面標示 2014 再確認）
  - **對我們的意義**：評審按下 enter 到看到卡片的**整段**（瀏覽器 → HTTP → 服務端 → JSON → 前端 render）要壓在 1 s 內才不會斷思緒；要「感覺即時」則整段 < 100 ms 不現實（圖片載入就不只 100 ms），但**服務端 < 50 ms** 讓整段幾乎一定落在 300 ms 以內，這是可辯護的目標。
- **0.1 秒的商業效果**：Deloitte × Google《Milliseconds Make Millions》（2020-03-24）在歐美零售／旅遊／精品／名單開發品牌的行動站上測 0.1 秒的速度改善：零售轉換率 +8.4%、客單價 +9.2%；旅遊轉換 +10.1%。（<https://www.deloitte.com/ie/en/services/consulting/research/milliseconds-make-millions.html>，2020-03-24）
  - **可信度標註**：這是顧問公司 × 平台商的產業報告，方法只有高層描述、非同儕審查，屬「可信但偏行銷」。**不要**在簡報上當成因果證據。
- **「Google 慢 0.5 秒流量掉 20%」**：出自 Greg Linden 轉述 Marissa Mayer 在 Web 2.0 的演講（2006-11-09），**二手來源、無 Google 原始發表**。同一篇也提到 Amazon「每 100 ms 延遲都造成可觀營收損失」，但**原文沒有「1%」這個數字**；廣為流傳的「100 ms = 1% sales」在我能取得的原始來源裡查不到出處。（<http://glinden.blogspot.com/2006/11/marissa-mayer-at-web-20.html>，2006-11-09）
  - **建議**：簡報只引 Nielsen 的門檻與 Deloitte 的方向性結果，**不要**引「100ms = 1%」。它是坊間傳說。

### 1.2 真實電商／時尚系統公布的服務端數字

| 系統 | 數字 | 量的是什麼 | 來源與日期 |
| --- | --- | --- | --- |
| **Etsy** 統一 embedding 個人化檢索（UEPPR） | **P99 = 18 ms**；另述「recall 損失 < 4% 的同時把 **P99 壓在 20 ms 以下**」 | 明確標示 P99，服務端＝**查詢編碼 inference + ANN 查詢**合計 | Jha et al., arXiv:2306.04833（v1 2023-06-07、v2 2024-09-25）。我親自從 ar5iv 全文取得逐字句 |
| Etsy 同篇 | 「在取回所需 K 的 **5 倍**之後再做 re-ranking」；索引為 **Faiss 4-bit product quantizer fastscan**（查表放在 register） | 候選預算與索引型態 | 同上 |
| **Alibaba / Taobao** MGDSPR | ANN 階段：6 個 column 的索引分散取 **top-K = 9,600**，索引檢索準確率 **98%**，**檢索延遲 10 ms** | 服務端單階段；論文未標 percentile（讀起來是典型值／平均） | Li, Lv et al., KDD 2021, arXiv:2106.09297（2021-06-17） |
| Taobao 同篇 | 候選漏斗：約 **1 億**件在架商品 → match → pre-rank → rank → re-rank → 「數十件」呈現 | 多階段候選預算 | 同上（各中間層的精確數字只出現在圖裡、不可靠，故不引） |
| **Alibaba** TDM（展示廣告） | 部署後的 TDM DNN **平均約 6 ms** 產生一次推薦；論文自述「比後面的 CTR 預測模組還短，不是系統瓶頸」 | 明確標示平均（mean），單一階段的模型推論 | Zhu et al., KDD 2018, arXiv:1801.02294（2018-01-08） |
| **Amazon** Semantic Product Search | 架構選擇受限於「每查詢成本」與「在 **20 ms** 內回應、每秒數千查詢」的能力 | 這是論文陳述的**設計約束**，不是量測到的分佈，也沒標 percentile | Nigam et al., KDD 2019, arXiv:1907.00937（2019-07-01） |
| **Uber** Michelangelo（通用 ML 服務平台，非時尚，但是唯一有完整 P95 的） | 不查 Cassandra 特徵時 **P95 < 5 ms**；查一次線上特徵時 **P95 < 10 ms**；最高流量模型 > 250,000 預測/秒 | 明確 P95，服務端 | <https://www.uber.com/blog/michelangelo-machine-learning-platform/>（2017-09-05） |
| **Vespa** phased ranking（架構，非 benchmark） | 三段排序：first-phase 對每個召回文件都算；second-phase **預設只重排每個 content node 的前 100 筆**（`total-rerank-count`）；global-phase **預設只重排全域前 100 筆**（`rerank-count`） | 各階段候選預算的**預設值** | <https://docs.vespa.ai/en/phased-ranking.html>（無版本日期，2026-09-18 取得）。此頁**不含任何絕對延遲數字** |

**查不到的（誠實標記）**：Zalando 工程 blog 目前的 search 標籤下**沒有**任何公布搜尋排序延遲的文章（只有 LLM-as-a-judge 的搜尋品質評估與一篇 Elasticsearch 事故檢討）（<https://engineering.zalando.com/tags/search.html>，2026-09-18 取得）。ASOS、Instacart、Myntra、Flipkart、Shopify、Walmart、eBay、Algolia 的對應數字**本次沒有取得**（Medium／CDN 回 403，且本 session 的 WebSearch 額度已耗盡，無法做發現式搜尋）。**Facebook KDD 2020 "Embedding-based Retrieval in Facebook Search" 全文裡沒有任何延遲數字**，只有「pq_bytes 越大→精度越高但記憶體與延遲也越高」的定性敘述；網路上流傳的該論文延遲數字是假的。**Pinterest ItemSage (KDD 2022) 也沒有延遲數字**，只有一句設計說明：embedding 走**每日離線批次**，「以確保模型推論延遲不影響端到端延遲」（arXiv:2205.11728，2022-05-24）。**Amazon P-Companion (CIKM 2020) 沒有延遲數字**。

### 1.3 我們該立什麼目標

把上面的證據攤開，**同量級的系統把「查詢編碼 + 檢索」放在 10–20 ms（Etsy P99 18 ms、Taobao 10 ms、Amazon 設計上限 20 ms）**，而重排只重排前 100 筆（Vespa 預設）。我們的商品庫是 17,783 件（可能長到 44k+），**比他們小三到四個數量級**，卻花 298 ms —— 這個對比就是我們該用的論證方式，而不是「我們比較慢但我們有解釋性」。

建議對外可辯護的三行目標：

1. **服務端 p50 ≤ 35 ms、p95 ≤ 60 ms**（`/rank`，17,783 件）。依據：Etsy P99 18 ms 是「編碼 + ANN」；我們多了硬條件過濾、可加總 rerank、反事實與忠實理由三件他們沒有的事，給 2× 的餘裕仍遠低於他們的 P99。
2. **整段（評審按 enter → 看到卡片）p95 ≤ 500 ms**。依據：Nielsen 的 1 s「思緒不中斷」門檻，留 2× 餘裕給 HTTP、JSON、圖片與前端 render。
3. **44k 商品庫時服務端 p95 ≤ 100 ms**。依據：我們所有熱點都是 O(N) 線性掃描，N 從 17.8k 到 50k 只放大 2.8×（我在本機直接量了 50k 的 dense 與遮罩成本，見 §3）。

**要說清楚「量的是什麼」**：上表的 298 ms 是 `pipeline.run()` 內部 `lap()` 的總和，**不含** `_metrics()`、pydantic 序列化、diversification 後處理、HTTP 與 JSON。這是常見的自我欺騙來源；§3.7 有具體修法。

---

## 2. 他們是怎麼做到的（機制，不是口號）

### 2.1 哪些東西是離線預算好的

- **Pinterest ItemSage**：商品 embedding 走**每日離線批次工作流**算好，只存一個共用的 HNSW 索引，明文理由是「確保模型推論延遲不影響端到端延遲」。（arXiv:2205.11728，2022-05-24）
- **Spotify** 自然語言 podcast 搜尋：episode embedding **離線批次**算好後灌進 Vespa 做 ANN；**只有查詢**在線上用 Vertex AI 上的 transformer 即時編碼。他們的負載測試顯示 T4 GPU 做查詢編碼相對 CPU 有「6 倍成本下降」，所以線上那一腳選 GPU。（<https://engineering.atspotify.com/2022/03/introducing-natural-language-search-for-podcast-episodes/>，2022-03-17）
- **Uber Michelangelo**：約 10,000 個特徵放共享 Feature Store；批次特徵（如「餐廳 7 天平均備餐時間」）以小時／日為週期從 HDFS 預算進 Cassandra；近即時特徵（如「過去一小時…」）由 Samza streaming job 從 Kafka 算、以分鐘為週期寫進同一個 store。**線上只做查表**，所以 P95 能壓在 5–10 ms。（同上 URL，2017-09-05）

**對映到我們**：我們的 image embedding、`design_matrix`、category NPMI 都已經是離線預算好的（`engine02/encoders.py:cached_image_embeddings`、`pipeline.py:design_matrix` 的 `.npy` 快取）——這部分做對了。**沒有**預算的是「屬性過濾用的正規化字串」與「BM25 的 (doc, term) 權重」，而那正好就是 242 ms 與 44 ms 的來源。這不是演算法問題，是**把離線該做的事放到線上做了**。

### 2.2 兩段／多段排序與候選預算

- **Vespa** 的預設就是一個很好的預算範本：first-phase 便宜函數掃全部召回，second-phase 只重排**每個 node 前 100 筆**，global-phase 只重排**全域前 100 筆**。文件明說成本上界是「暴露的文件數 × 函數複雜度」，要求開發者針對自己的 SLA 去調 first-phase。（<https://docs.vespa.ai/en/phased-ranking.html>，2026-09-18 取得）
- **Etsy**：在取「所需 K 的 5 倍」之後才做 re-ranking。（arXiv:2306.04833）
- **Taobao**：1 億 → ANN top-9,600 → pre-rank → rank → re-rank → 數十件。（arXiv:2106.09297）

**對映到我們**：`options.n_candidates = 50`、`top_k = 5`、`diversify_depth = 20`（`engine02/contracts.py:134-143`）。這個預算**本身就很節制**，符合 Vespa 的 100 量級。問題在 first-phase：我們的 first-phase 是「對整個 pool 算 dense + BM25」，而 pool 在沒有條件時就是全庫 —— 這是**精確（exhaustive）檢索**，在我們的規模下是對的選擇（見 §2.3），只是實作上把 O(N) 的常數搞爛了。

### 2.3 ANN 還是精確搜尋？我們這個規模**精確就好**

- Faiss 官方選型指南明確建議：查詢次數很少（1,000–10,000 量級）或需要精確結果、且資料放得進 RAM 時就用 `Flat`；它的規模階梯從 **< 1M** 才開始建議 `IVF`。（<https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index>，2026-09-18 取得）
- Qdrant 文件給了明確的數值規則：**當過濾後的候選集小於門檻（預設 10,000 KB）時，自動改用全掃描（brute force）而不是 HNSW**。（<https://qdrant.tech/documentation/concepts/indexing/>，2026-09-18 取得）
- Pinecone 的向量索引說明（**廠商內容**，文末在推銷自家產品，但附了實質 benchmark 表）：Sift1M（1M × 128 維 fp32）上 Flat 約 18 ms/查詢、recall 1.0；HNSW 在 recall 0.5–0.95 時 0.6–2.1 ms。同頁給的經驗法則是 **< 10K 向量時 flat 就夠**。（<https://www.pinecone.io/learn/vector-indexes/>，頁面無日期，2026-09-18 取得）
- **我自己量的**（本機 CPU，float32，768 維）：17,783 × 768 的矩陣向量乘 **1.44 ms**；50,000 × 768 **4.46 ms**。float64 分別 3.1 / 9.0 ms。

**結論**：在 17,783（甚至 50,000）件的規模上**引入 HNSW / IVF 是淨負分**——建索引要時間、要新依賴（現場無網路）、會引入 recall 損失，而省下的是 1–4 ms。而且 Qdrant 自己文件就說了 HNSW 在**過濾太嚴格時圖會「解體」**（graph falls apart），我們的 pipeline 又是重度屬性過濾。**我們的答案是精確搜尋 + 把常數修好**，而且這句話有 Faiss 與 Qdrant 官方文件背書。

### 2.4 過濾：pre-filter / post-filter / filtered ANN，以及 bitmap

- **Vespa**：過濾就是 YQL 裡的邏輯 AND（`nearestNeighbor(...) and in_stock:true`），屬 **pre-filtering**，布林條件先縮小候選集再算距離。文件同時提醒 exact nearestNeighbor「隨執行緒數近線性擴展」但「因為要對每一個通過布林過濾的文件算距離，計算上很貴」。（<https://docs.vespa.ai/en/querying/nearest-neighbor-search.html>，2026-09-18 取得）
- **Weaviate**：ACORN 之前用 `flatSearchCutOff` 在兩種策略間切換 —— 過濾後 brute force（pre-filter，只在過濾集很小時快）與 sweeping（post-filter：不管過濾走完 HNSW，每個候選再檢查是否符合過濾，浪費距離計算）。ACORN（v1.27 起可選）在低選擇性（約 20%）過濾下比 sweeping 吞吐約 2×，在查詢與過濾相關性極低時「快一個數量級」；但在高相關性時反而是單純 sweeping 勝。（<https://weaviate.io/blog/speed-up-filtered-vector-search>，benchmark 標示 2024-11）
- **Qdrant filterable HNSW**：為每個 category 額外建圖邊（總邊數最多 2×，不隨 category 數成長），讓貪婪搜尋能留在過濾後的子圖內；數值區間／geohash 則分桶後連接相鄰桶。理論依據是 percolation theory 的臨界門檻 p_c = 1/⟨k⟩。（<https://qdrant.tech/articles/filterable-hnsw>，2019-11-24）
- **Lucene** 的過濾骨幹是 `DocIdSetIterator`：`nextDoc()` 走遞增 doc id、`advance(target)` 跳到第一個 ≥ target 的 id（讓 skip-list 式跳過被過濾掉的區段）、`cost()` 給查詢規劃器估上界；materialize 成 bitmap 時用 `BitSetIterator` / `DocBaseBitSetIterator`。（<https://lucene.apache.org/core/9_11_0/core/org/apache/lucene/search/DocIdSetIterator.html>，2026-09-18 取得）
- **Roaring bitmap**：Chambi, Lemire, Kaser, Godin, *Software: Practice and Experience* 46(11):1547–1569（2016-11）；自述比傳統 RLE 方案（WAH、Concise、EWAH）「快數倍、最多兩個數量級」且壓得更小，並已被 Apache Lucene / Spark / Kylin / Druid 採用。（arXiv:1603.06549，2016-11）Druid 文件確認現況：「Druid 用 Roaring 壓縮 string 欄與 numeric null 的 bitmap」，並指出「Roaring 在**命中很多值**的過濾上明顯較快」。（<https://druid.apache.org/docs/latest/design/segments/>，2026-09-18 取得）

**對映到我們 —— 這裡要說一句反直覺但重要的話**：**我們不需要 roaring bitmap，也不需要倒排索引。** 理由是 N 太小。pyroaring 自己的 benchmark 是在 **100 萬**元素、密度 0.125 下量的：交集 600 µs（vs Python `set` 46.6 ms）。（<https://github.com/RoaringBitmap/PyRoaringBitMap>，2026-09-18 取得）而我們只有 17,783 個位元；**numpy 的布林 `&` 在這個尺寸本機量到 0.005 ms（5 µs）**，已經比 pyroaring 在 1M 上的交集還快兩個數量級（因為元素少 56 倍）。Roaring 的價值在「稀疏、超大、要壓縮」的集合，我們三個條件都不符合。**正確的對照是 Lucene 的「把過濾預先 materialize 成 bitset」這個概念**，而在 numpy 裡那就是「每個 (欄位, 值) 一個預先算好的 `np.ndarray[bool]`」——這正是 §3.1 的提案。

### 2.5 快取層

- **Algolia** 自己的《Inside the Algolia Engine Part 1》裡**沒有**描述查詢結果快取；他們講的是 search process 與 indexing process 分離 + `nice` 層級的 CPU 優先權，加上**整個索引常駐記憶體以避免磁碟 I/O**，以及 Linux deadline scheduler 調校（讀 100 ms、寫 10 s timeout）。此頁**沒有任何 cache-hit-rate 數字**。（<https://www.algolia.com/blog/engineering/inside-the-algolia-engine-part-1-indexing-vs-search/>，2024-01-22）
- **Elasticsearch** shard request cache：預設只快取 `hits.total`／aggregation／suggestion（`size=0` 時），LRU 淘汰，shard refresh 或 mapping 變更時自動失效；官方文件**沒有給命中率或延遲數字**。（<https://www.elastic.co/guide/en/elasticsearch/reference/current/shard-request-cache.html>，2026-09-18 取得）filter context 的文件只說「會自動快取以加速後續搜尋」，同樣無數字。（<https://www.elastic.co/guide/en/elasticsearch/reference/current/query-filter-context.html>，2026-09-18 取得）
- **Feast** 文件描述 online/offline store 分離（線上後端可用 Postgres、Milvus、Elasticsearch、SQLite、ScyllaDB），但**現行公開頁沒有 p99 數字**；Tecton 的舊 benchmark 文章因併購已 301 導向 Databricks。（<https://docs.feast.dev/reference/alpha-vector-database>，2026-09-18 取得）

**對映到我們**：Algolia 那句「索引常駐記憶體」才是對我們有用的一句。**不要為 demo 加查詢結果快取**：評審會在每輪改條件與給回饋，命中率接近 0，還會製造「明明改了條件卻回一樣的卡」這種舞台上最難解釋的 bug。我們該做的是**預算（precompute）而不是快取（cache）**——前者對每個查詢都有效，後者只對重複查詢有效。

### 2.6 蒸餾 / 量化 / ONNX

- Hugging Face Optimum 官方 benchmark（RoBERTa、extractive QA、m5.xlarge、2 physical cores、10 次 warm-up 後量 100 次、約 128 token）：原始 **117.61 ± 8.48 ms** → ONNX Runtime + 動態 int8 量化 **64.94 ± 3.65 ms**（約 1.8×，官方文字寫「roughly 2x」），F1 保留 99.61%，模型 473.31 MB → 291.77 MB（−38%）。（<https://huggingface.co/blog/optimum-inference>，2022-05-10）
- sentence-transformers 的效率文件引用 Flash-Attention-2 benchmark（fp16 + FA2 + unpadded 是量到最快的組合，相對 fp32 為 3.87×），但**沒有**單查詢 ms 的 ONNX/int8 表格。（<https://www.sbert.net/docs/sentence_transformer/usage/efficiency.html>，2026-09-18 取得）

**對映到我們**：我們的 `retrieve` 44 ms 裡，查詢文字編碼在 V100 上大概只佔個位數 ms（SigLIP text tower 一次一句、GPU），**不是瓶頸**，所以 **ONNX／int8 對我們沒有價值，還會多一個現場會壞的依賴**。我把它列在「不要做」清單。

### 2.7 Batching 與 warm-up

- NVIDIA Triton 對 `ModelWarmup` 的官方理由就是我們的問題：「對某些 backend，部分或全部初始化會延到模型收到**第一個推論請求**時才做…因此最初的（幾個）推論請求會因為延後初始化而明顯較慢。」Warmup 的做法是在模型被標為 ready 之前先送合成請求進去。（<https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/model_configuration.html>，2026-09-18 取得）
- 為什麼第一次特別慢的底層原因之一（kernel launch 成本）：NVIDIA CUDA Graphs blog 量到 kernel 本身執行約 2.9 µs，但**帶同步的每次 launch 約 9.6 µs（純 overhead 約 6.7 µs）**；用 stream 重疊後約 3.8 µs／kernel；CUDA Graphs 約 3.4 µs／kernel 但有一次性約 400 µs 的 graph instantiation。（<https://developer.nvidia.com/blog/cuda-graphs/>，2019-09-05）
- Kubernetes 的 `startupProbe` 就是為「初始化很慢的容器（例如載入 ML 模型）」設計的：它先擋住 liveness／readiness 檢查（文件範例 `failureThreshold: 30`、`periodSeconds: 10`，等於最多 300 s 寬限），避免 kubelet 在模型載入中途把容器殺掉；readiness probe 再分開控制何時開始導流量。（<https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>，2026-09-18 取得）
- safetensors 官方定位是「安全且快（zero-copy）」，靠 mmap 載入，對比 pickle 的 `.bin`。（<https://huggingface.co/docs/safetensors/index>，2026-09-18 取得）

**對映到我們**：我們**不需要** Triton、不需要 k8s，但需要它們背後那一條原則：**「ready」必須代表「已經跑完一次完整的真實請求」**。§4 給具體做法。

---

## 3. 我們程式碼的逐檔計畫

以下每一項都附：我在本機量到的前後數字（**同一台機器、同一份資料、同一個函式**，所以比值可信）、正確性風險、以及「怎麼驗證排序沒變」。

### 3.1 `filter` 242 ms 的真正來源（已用 cProfile 定位）

我在本機用 `cProfile` 跑 10 次 `taxonomy.filter_with_category_relaxation`（17,783 列、4 個硬條件、走到第 4 個 rung），結果：

```
ncalls  tottime  cumtime  function
    10    0.012    4.192   taxonomy.py:394(filter_with_category_relaxation)
    10    0.000    3.501   attribute_fill.py(filter_fn)
    10    0.001    3.224   constraints.py:110(filter_with_relaxation)
    40    0.042    3.221   constraints.py:59(build_mask)          ← 77% 的時間
   110    0.015    3.162   constraints.py:48(_slot_mask)
   110    0.002    3.028   pandas Series.map
1956130   1.303   2.140   constraints.py:42(_norm)               ← 每 10 次請求 196 萬次呼叫
    20    0.093    0.480   taxonomy.py:178(category_mask)
```

**成因，一句話**：`constraints.py:_slot_mask` 每次被呼叫都做 `col.map(_norm)` —— 對**整欄 17,783 列**跑一次 Python 函式。一次 `build_mask` 會對 2–5 個 slot 各做一次，而 relaxation ladder 每一級都會**整個重算** `build_mask`（`constraints.py:110-130` 的 `for slot, action in ladder` 迴圈裡 `mask, applied = build_mask(...)`），`taxonomy.py:filter_with_category_relaxation` 外面又套了一層 rung 迴圈。所以每個請求會跑約 **11 × 17,783 ≈ 20 萬次** `_norm()`，每次 `_norm` 裡有 `str()`、`.strip()`、`.lower()` 和一個 `isinstance` + `np.isnan`。

**這是純 Python 解譯器成本，和商品庫內容無關、和演算法無關。**

#### 提案 A（最高價值）：`engine02/constraints.py` 增加一個「每商品庫預算一次」的欄位索引

機制（就是 Lucene 把 filter materialize 成 bitset 的 numpy 版）：

1. 對每個過濾用欄位（`category` `subcategory` `color` `occasion` `season` `gender`），開服務時做一次 `pd.factorize(col)` 拿到 raw codes 與 uniques（C 層），**只對 uniques（幾百個）呼叫 `_norm`**，再把正規化後相同的 unique 合併，得到 `codes: np.int32[N]` + `index: dict[str, int]` + `isnull: np.bool_[N]`。
2. 查詢時的 slot mask 變成 `np.isin(codes, want_codes)`（`want_codes` 由 `index` 查表得到），`allow_unknown` 就是 `|= isnull`。
3. `build_mask` 的其餘語意（`also=subcategory` 的 OR、budget 的 `x1.2`、`required_values`、`excluded_values`、`excluded_positions`）逐條照搬。

**我實作了這個原型並驗證**（原型在我的 scratchpad，不在 repo 內）：

| 項目 | 現況 | 原型 | 驗證 |
| --- | --- | --- | --- |
| `build_mask` 一次 | **46.12 ms** | **0.547 ms**（84×） | **120/120** 組隨機條件組合（含 relaxation state、`excluded_values`、`required_values`、隨機 `excluded_positions`）的 `mask` 與 `applied` **完全相同** |
| 索引建立 | — | **7.1 ms**（每商品庫一次） | — |

**預期省下**：`filter` 從 241.65 ms 降到 **< 5 ms**（約 −237 ms）。這一項單獨就把總延遲從 298 ms 打到 61 ms。

**正確性風險（三個，都有解）**：
1. **欄位不在預建清單裡**：原 `build_mask` 對 `required_values` / `excluded_values` 會接受**任何**存在於 `items.columns` 的欄位。→ 解法：`ColumnIndex` 改成**用到才建、建完快取**（lazy + dict），而不是固定六欄。不然「ENGINE 03 送一個 `required_values={"material": [...]}`」會被靜默忽略。
2. **`excluded_values` 的空白處理不同**：原碼在 `excluded_values` 分支只做 `v.lower()`（沒有 `.strip()`），slot 分支才做 `v.strip().lower()`。→ 解法：原型要保留這個不對稱，或明確決定統一並在 CHANGELOG 記一筆。
3. **框架同一性**：索引是綁在某個 `DataFrame` 上的。`attribute_fill.provenance_filter` 會回傳一個**改過 `color` 欄的 view**（`_view()`），所以**要對「原框架」與「family view」各建一份索引**（現行 `_view` 已經用 `(id(items), len(items), family)` 當 key 快取，沿用同一把鑰匙即可）。

**怎麼驗證排序沒變**：
- 單元測試：對 500 組隨機 `HardConstraints`（含所有 relaxation state）比對 `build_mask` 的 `mask` 與 `applied`，`np.array_equal` 必須全真。我已用 120 組跑過，全過。
- 端到端：`scripts/api_check.py` 已有的斷言全跑一次；另外對 `docs/contract/example_round1_request.json` 與 round2，比對改動前後 `Engine02Response` 的 `items[].item_id`、`items[].score`（到小數 12 位）、`constraint_report.relaxed` 逐項相同。

#### 提案 B：`engine02/taxonomy.py:Taxonomy.category_mask` 改用預算的 node code

現況（`taxonomy.py:190-200`）是一個 Python list comprehension 對 17,783 列逐列做 tuple-in-set 檢查，外加 `_source_key` 每列一次（profile 顯示 355,660 次呼叫）。

機制：開服務時對商品庫算一次 `tax.item_node_ids(items, catalog)` → 每件一個 node id → 映成 `node_codes: np.int32[N]`；查詢時 `np.isin(node_codes, target_codes)`，`target_codes` 由 `{nid} ∪ descendants(nid)` 查表得到。collection（`catalog_pairs` 帶 `extra_source_values`）語意較複雜，保留慢路徑（罕用）。

**我量到的**：`category_mask` **8.08 ms → 0.067 ms**（120×），對 8 個類別值（`dress`、`上衣`、`外套`、`鞋`、`褲`、`Topwear`、`Shirts`、`裙子`）中可解析的 **7/7 完全相同**。索引建立 `item_node_ids` **512 ms**，每商品庫一次（可以順手存成 `index/nodes_<catalog>.npy`）。

**預期省下**：relaxation ladder 每個 rung 一次 → 約 **−25 ms**（含在 §3.1 的 −237 ms 內，兩者相加不重複計算：提案 A 省 build_mask、提案 B 省 category_mask）。

**正確性風險**：`item_node_ids` 的 per-item node 是**單一** node（`next(...)` 取第一個命中的 source），而 `category_mask` 的 `mask_for` 是用 `(source, subcategory)` pair 集合比對。當一個 `subcategory` 值在兩個 vocabulary（kagl / polyvore）裡對到**不同** node、而商品沒有 `source` 欄時，兩者可能不一致。→ 解法：只在 `"source" in items.columns` 或 `len(sources_for(catalog)) == 1` 時走快路徑，否則退回慢路徑；並在單元測試裡對 `kagl_polyvore` 這個混合庫全類別值做一次 parity 掃描。

#### 提案 C：`engine02/taxonomy.py:filter_with_category_relaxation` 停止用 Python list 傳遞排除集

現況第 449–451 行：

```python
excl = sorted(base_excl | set(np.flatnonzero(~cat_mask).tolist()))
fr = filter_with_relaxation(items, c_no_cat, min_results, excl, ...)
```

當類別很窄（例如只剩 160 件洋裝），`~cat_mask` 就有 **17,623** 個位置，程式把它們轉成 Python list → set → sorted list，然後在 `build_mask` 裡用 `mask[excluded_positions] = False` 做 fancy-index 賦值。**我量到**：`sorted(set(tolist()))` 往返 **1.675 ms**、`mask[python_list] = False` **1.328 ms**，合計 ~3 ms × rung 數。等價的布林 AND 是 **0.005 ms**。

機制：`build_mask` 的 `excluded_positions` 參數改為接受 `np.ndarray[bool]`（或多一個 `excluded_mask` 參數），內部直接 `mask &= ~excluded_mask`。

**預期省下**：約 **−10 ms**（4 rung）。**正確性風險：零**（集合運算等價）。**驗證**：同 §3.1 的 mask parity 測試。

#### 提案 D：`engine02/attribute_fill.py:provenance_filter._view` 的 `color_family` 改成讀預算好的欄

`_view()` 在 `family` 模式下做 `view["color"] = [color_family(v) for v in view["color"]]` —— 17,783 次 Python 呼叫。但 `attribute_fill.py` 的 `fill_attributes()` **已經寫出一個 `color_family` 欄**（`out["color_family"] = [color_family(c) for c in out["color"]]`）。

機制：`_view` 先檢查 `"color_family" in items.columns`，有就直接 `view["color"] = items["color_family"]`。

**預期省下**：在**已加上 `_view` 快取的目前版本**下，這只影響**每個商品庫第一次**（約 −20 ms 的一次性成本），不影響穩態延遲。**但**它是個重要的正確性對齊點：現在有兩份 `color_family` 計算路徑（離線寫欄 + 線上重算），若 `COLOR_TO_FAMILY` 改過就會不一致。**優先度低，但值得順手做。**
（註：coordinator 已在未 commit 的 `attribute_fill.py` 裡加了 `_PRED_CACHE` 與 `views` 快取，把 `is_predicted` 的 711k 次 `json.loads` 與整框 copy 都拿掉了。我 profile 到 `_prepare` 現在只佔 **2.8 ms/次**。**這一項已經做完了，本文不重複提案。**）

### 3.2 `retrieve` 44 ms：BM25 是主因，dense 的 dtype 是次因

#### 提案 E：`engine02/sparse.py:BM25Index` 換掉 `rank_bm25`

`rank_bm25.BM25Okapi.get_scores(q)` 對**每個 query token** 都在**整個語料**上做一次 numpy 運算。套件作者自己在 README 裡寫：「For those looking to use this in large scale production environments, I'd recommend you take a look at something like retriv, which is a much more performant python retrieval package.」（<https://github.com/dorianbrown/rank_bm25>，2026-09-18 取得）

已發表的替代品速度（BM25S 論文 Table 1／同 repo README，Intel Xeon @2.70 GHz、單執行緒、10 次平均，單位 QPS）：

| 語料（文件數） | BM25S | Elasticsearch | BM25-PT | rank-bm25 |
| --- | --- | --- | --- | --- |
| nfcorpus (3.6K) | 1196.16 | 45.84 | 256.67 | 224.66 |
| scifact (5K) | 952.92 | 20.81 | 184.30 | 47.60 |
| arguana (8.67K) | 573.91 | 13.67 | 110.51 | 2.00 |
| scidocs (25K) | 767.05 | 17.93 | 41.34 | 9.01 |
| fiqa (57K) | 507.03 | 16.96 | 20.52 | 4.46 |
| trec-covid (171K) | 85.64 | 7.34 | 3.73 | 1.48 |

（Xing Han Lù, "BM25S: Orders of magnitude faster lexical search via eager sparse scoring", arXiv:2407.03618，2024-07-04；同表在 <https://github.com/xhluca/bm25s> README。論文摘要自述相對 rank-bm25「最高 500× 加速」、14 個資料集有 10 個吞吐量高 100× 以上。BM25-PT 在多數非小語料 OOM。**注意：該論文並未和 PISA 比較**，網路上說它 benchmark 過 PISA 的說法是錯的。）

**BM25S 的機制就是 `scipy.sparse.csc_matrix` 預存 eager 算好的 BM25 權重 + Quickselect 取 top-k。** 既然機制這麼簡單、而現場又不保證能 `pip install`，**我建議不要加新依賴，而是把這個機制寫進 `engine02/sparse.py`（約 40 行）**。

**我實作了並驗證**（17,783 篇短文件、`title + subcategory + color + occasion`）：

| 項目 | `rank_bm25.BM25Okapi` | scipy CSC 原型 |
| --- | --- | --- |
| `scores(query)`（6 句查詢平均） | **11.41 ms** | **0.238 ms**（48×） |
| 建索引（一次） | 120.0 ms | 185.6 ms |
| 記憶體 | — | 1.6 MB（nnz 133,542、vocab 2,194） |
| **分數最大絕對誤差** | — | **5.68e-14**（浮點捨入） |
| **6 句查詢的 top-50 順序** | — | **全部完全相同** |

原型與 `rank_bm25.BM25Okapi` 使用完全相同的 k1=1.5、b=0.75 與 idf 公式（含 `epsilon=0.25` 的負 idf 下限 `eps = epsilon * avg_idf`）。

**預期省下**：`retrieve` 內約 **−11 ms**（伺服器上 BM25 佔比可能更高，因為 `rank_bm25` 是純 Python/numpy、V100 幫不上忙；若伺服器上 BM25 是 25–30 ms，省下就是 −25～−30 ms）。另外 `pipeline.py:_terms` 在 `use_trend` 開啟時會**再呼叫一次** `self.bm25.scores()`，同樣受益。

**正確性風險**：
- idf 的 `epsilon` floor 必須逐字照抄 `rank_bm25` 的行為（負 idf 用 `eps` 取代，`avg_idf` 是**全 vocab** 的平均，不是正 idf 的平均）。我原型已對齊並驗證到 5.7e-14。
- `bm25.vocab` 與 `coverage()` 的語意要保留（`pipeline.py:run` 的 `bm25_adaptive` 靠它）。原型保留了 `vocab` dict。
- 浮點差 5.7e-14 理論上能翻轉**完全同分**的兩件商品的次序。實務上 BM25 同分的商品本來就由 `np.argsort(kind="stable")` 決定，仍然是確定性的，只是可能和舊版不同。→ 驗證方式：對 T1 的 40–100 句查詢跑 NDCG@5 的**配對**比較，要求 Δ = 0（不是「不顯著」，是**完全相同**）。

**為什麼不用 `bm25s` 套件**：現場無網路保證，而 `bm25s` 只帶來「已經被我們用 40 行寫出來」的同一個機制。若 coordinator 想留下升級路徑，可以把新的 `BM25Index` 介面做成和 `bm25s` 相容（`retrieve`/`get_scores`），但**預設實作不要依賴它**。

#### 提案 F：`engine02/pipeline.py:run` 修掉 dense 的 fancy-index + dtype 升型

現況：

```python
q = self.query_embedding(req, arm, text)          # → np.float64（l2n 內部 float32，最後 .astype(np.float64)）
dense_all = self.image_emb[pool] @ q              # image_emb 是 float32
```

兩個問題：(1) `self.image_emb[pool]` 對最多 17,783 × 768 做一次 fancy-index **複製**；(2) float32 矩陣 @ float64 向量 → numpy 把整個複製出來的矩陣**升型成 float64**（記憶體翻倍、頻寬翻倍）。

**我量到**（768 維、pool = 全庫的 35%）：

| 作法 | 17,783 件 | 50,000 件 | top-50 與現況相同？ |
| --- | --- | --- | --- |
| 現況 `E64[pool] @ q` | **13.16 ms** | **44.72 ms** | （基準） |
| 預存 float64 全庫、`(E64 @ q)[pool]` | **3.10 ms** | **9.04 ms** | **是（完全相同）** |
| 保持 float32、`(E32 @ q.astype(f32))[pool]` | **1.44 ms** | **4.46 ms** | **是（完全相同，最大值差 3.4e-08）** |

記憶體代價：float64 全庫副本 109 MB（17.8k）／307 MB（50k）；float32 不需要副本。

**建議**：**選 float32 全庫路線**，並把 `encoders.py:l2n` 已經是 float32 這件事一路保持到底（也就是 `query_embedding` 不要 `.astype(np.float64)`）。理由：(a) 省最多；(b) 不多花記憶體，44k+ 商品庫仍安全；(c) top-50 順序實測完全相同。若 coordinator 不接受 3.4e-08 的數值差，退而用 float64 全庫預存版（仍省 −10 / −36 ms，且**位元相同**）。

**預期省下**：17,783 件 **−11.7 ms**；50,000 件 **−40 ms**。

**正確性風險**：float32 累加順序不同，會讓分數在第 8 位小數後不同。這會傳到 `RankedItem.score`、`Contribution.raw`、以及 `rerank.py` 的 z-score 統計。**同分翻轉的可能性存在但極低**（cosine 同分到 1e-8 的兩件商品本來就等價）。
**怎麼驗證**：(1) 對 T1 的查詢集，要求 `items[].item_id` 序列**逐句完全相同**；(2) 對 `docs/contract/example_round*.json` 要求 `score` 差 < 1e-6 且 `contributions` 加總仍等於 `score`（`scripts/api_check.py` 已有這個斷言）；(3) 若任何查詢的順序改變，改用 float64 全庫版。

同一個修法要套用在 `pipeline.py:_terms` 的 penalty 項（`self.image_emb[pool] @ self.image_emb[neg].T` 也吃同一個 fancy-index 複製）。

### 3.3 `fuse` 1.18 ms → 0.2 ms

#### 提案 G：`engine02/pipeline.py:run` 的 `np.argsort(-fused, kind="stable")[:n_cand]`

現況對整個 pool（最多 17,783）做穩定完整排序，只為了取前 50。

**我量到**：全排序 **1.678 ms** → `np.argpartition(-s, 50)[:50]` 再對這 50 個做穩定排序 **0.061 ms**（27×），**top-50 順序完全相同**（同一組隨機分數下驗證）。

**正確性風險**：`argpartition` 不穩定，**當第 50 名與第 51 名同分時**，被選入的那一個可能和 `kind="stable"` 選的不同。我們的 fused 分數是浮點 RRF 或 convex sum，完全同分罕見但非不可能（例如 `candidate_fusion="bm25"` 且很多商品 BM25 = 0 時**極常見**）。
**解法（必要）**：取 `n_cand + tie_slack` 個（例如 `n_cand` 和「所有等於第 n_cand 名分數的索引」），再對這批做 `kind="stable"` 排序取前 `n_cand`。或者更簡單：只在 `len(pool) > 4 * n_cand` 時走 argpartition，並在同分邊界時退回全排序。
**驗證**：對 `candidate_fusion` 的每個值（`bm25`/`dense`/`rrf`/`convex`）跑 T1 查詢集，要求 `cand` 陣列逐元素相同。

**預期省下**：−1 ms。**低優先度**（絕對值小），但幾乎零成本，順手做。

### 3.4 `explain` 10.17 ms

`service.py:rank` 走 `deep_request(req2, cfg.depth)`（`diversify.py:189`），把 `top_k` 設成 `max(20, k) + 1 = 21`。於是 `pipeline.py:run` 的最後那個大迴圈為 **21 張卡**建了 21 × 約 17 個 `Contribution` pydantic 物件（≈357 次 model 驗證）、21 次 `template_reasons`、21 次 `explain`、21 個 `design_scores` dict —— 但 `diversify.py:diversify_response` **只用 `it.score` 和 `it.contributions`**，理由與 `explanation` 全部重新產生。

#### 提案 H：`engine02/pipeline.py:run` 加一個「只要分數」的路徑

機制：`Engine02Request.options` 多一個內部欄位（或 `run()` 多一個 `scores_only: bool` 參數），為真時跳過 `template_reasons` / `explain` / `attribute_notes` / `design_scores`，並用 `Contribution.model_construct(...)` 取代 `Contribution(...)`（pydantic 的 `model_construct` 跳過驗證）。`diversify.py:deep_request` 設定它。

**預期省下**：約 **−7 ms**。
**正確性風險**：中等。`diversify_response` 目前從 `deep.items` 讀 `it.attribute_notes`（第 261 行 `reasons += [f"注意：{n}" for n in it.attribute_notes]`）與 `it.need_contributions`（做 aspect 矩陣），以及 `it.model_dump()` 之後 `update(...)` 剩下的欄位（`design_scores` 會被原封不動帶到最終卡片上）。**所以不能全部跳掉**：`need_contributions`、`attribute_notes`、`design_scores` 都還要。真正可以安全跳掉的只有 `template_reasons` + `explain` + `cut`／`cf` 的理由判定（`diversify_response` 自己重算 `cutoff_explanations`）。
**建議**：先只做「跳過 `template_reasons` 與 `explain`」＋「`Contribution.model_construct`」這兩個最安全的，量一下還剩多少。
**驗證**：比對最終 `ServiceResponse.items[].reasons`、`explanation`、`explanation_source`、`design_scores` 逐字相同。

### 3.5 `/complete-look` 的 OutfitTransformer：**需要離線預算 embedding，現在沒有**

`complete_look.py:FastOutfitTransformer.ensure_embeddings` 對還沒見過的 position 逐批 `_raw_item(p)`（**開啟 PIL 圖檔**）→ `precompute_clip_embedding`。`recommend()` 每個互補類別取 `prefilter=50` 件，`n_categories=2` → 首次約 **100 件要開圖 + 跑 CLIP**。

關鍵發現：**`api.py:lifespan` 建 `FastOutfitTransformer(...)` 時沒有傳 `cache_file`**（`complete_look.py:108` 的參數預設 `None`），所以 `self.cache_file is None` → `save_cache()` 是 no-op，`_emb` 只活在記憶體、每次重啟歸零。類別 docstring 說「so scoring 100 candidates is one small transformer batch instead of 100 image encodings」—— **這個承諾目前只在同一個 process 的第二次之後才成立。**

#### 提案 I：`engine02/api.py:lifespan` 傳 `cache_file`，並在離線預算全庫

1. `api.py:lifespan`：`ot = FastOutfitTransformer(..., cache_file=engine.cache / f"ot_{'-'.join(heads)}.npz")`。
2. 新腳本（coordinator 決定要不要寫）：載入 OT、`ot.ensure_embeddings(range(len(catalog)))`、`ot.save_cache()`。17,783 件在 V100 上按設計文件 §4.4 的「Qwen3-VL-8B 每件 0.1–0.18 s」量級**不能類推**（CLIP item encoder 小得多），但即使每件 10 ms 也只要約 3 分鐘，**在 demo 前跑一次就好**。
3. `api.py:lifespan` 的 warm-up 階段呼叫一次 `/complete-look`（見 §4）。

**預期省下**：首次 `/complete-look` 從「約 1–3 s（100 張圖 I/O + CLIP）」降到「一次 transformer batch（< 50 ms）」。**這是舞台上最可能被看見的那個卡頓**，因為評審一定會點「幫我配整套」。
**正確性風險：零**（embedding 是確定性的，預算與線上算出同一個值）。
**驗證**：`np.allclose(precomputed[p], ot._emb[head][p])` 對隨機 50 個 position；以及 `/complete-look` 的 slates（`item_id` 序列）在有無快取下相同。

### 3.6 DPP（depth 20）值不值得？**值得，而且幾乎免費**

- 演算法成本有公開依據：Chen, Zhang & Zhou, "Fast Greedy MAP Inference for Determinantal Point Process to Improve Recommendation Diversity"（NeurIPS 2018, arXiv:1709.05135）證明 exact greedy 可以做到 **O(k²N)**（N = 候選池、k = 選出數），並在真實資料上量到：Netflix Prize（436,674 users、11,551 movies、每人候選中位數 735–811）**平均 0.73 ms、P99 1.75 ms**；Million Song Dataset **平均 0.76 ms、P99 1.46 ms**。論文自述「99% 機率在 2 ms 內完成，可用於即時場景」。
- **我們的規模是他們的 1/40**：N = 20（不是 735–811）、k = 5（不是 20 或 100）。k²N = 500 對比他們的 ~8,000,000。
- **我量到**：DPP 之前要算的 21 × 768 cosine 核矩陣 **0.0315 ms**；貪婪選擇本身在這個尺寸是微秒級。

**結論**：**DPP 本身的成本可以忽略（< 0.1 ms），保留。** 真正的成本是「為了給 DPP 20 個候選，pipeline 產生了 21 張完整解釋卡」——那是 §3.4 的問題，不是 DPP 的問題。效益端在 `docs/engine02-design.md` 已有量測（近重複 2.45% → 0.35%、NDCG 無顯著代價），對舞台效果直接可見（設計文件 §3.14b 記到「五件都是藍色洋裝、Div@5 = 0.2」這種畫面）。

**唯一建議**：`diversify.py:_cosine_matrix` 和 `diversify_response` 各做了一次 `engine.catalog.positions([...])` + `image_emb[pos]`（第 201 與 207 行，同一批 21 個 item 算了兩次 embedding 取值），順手合併，省不到 0.1 ms，但少一次重複。

### 3.7 `_metrics` 是沒有被計時的 40 ms

`pipeline.py:run` 的計時在 `lap("explain")` 就結束，然後才：

```python
return Engine02Response(..., metrics=self._metrics(req, shown_pos), ...)
```

`_metrics`（`pipeline.py:Engine02._metrics`）做了三件重的事：
1. `prep(items, c)` —— 現在有快取，便宜。
2. `tax.category_mask(items, roots, self.catalog.name)` —— **又一次全庫 category mask**（我量到 8.08 ms）。
3. `[satisfies(items, p, c_eval) for p in shown_pos]` —— **每件商品**呼叫 `constraints.satisfies`，而 `satisfies` 做 `items.iloc[[pos]]` + `reset_index` + `build_mask`（一個 1 列的 DataFrame，但 pandas 的固定成本在那裡）。

**我量到**：`satisfies` 單件 **1.952 ms**、21 件 **44.15 ms**。

#### 提案 J：`engine02/pipeline.py:_metrics` 向量化

機制：用 §3.1 的 `CatalogIndex` 對**全庫**算一次 `mask`（0.5 ms），然後 `sat = mask[shown_pos].mean()`。`category_mask` 用 §3.2 提案 B 的快路徑。`excluded_value_hits` 的迴圈也改成 `codes` 查表。

**預期省下**：約 **−45 ms**（而且這 45 ms 目前在任何 dashboard 上都看不到）。
**正確性風險**：低。`satisfies` 的語意就是「對一列跑 `build_mask(state={})`」，對全庫跑一次再取 `shown_pos` 是等價的（`build_mask` 逐列獨立，唯一的跨列項是 `excluded_positions`，而 `satisfies` 沒傳）。
**驗證**：對 200 組隨機 (constraints, shown_pos) 比對 `hard_constraint_satisfaction`、`match_policy`、`excluded_value_hits`、`rejected_item_hits` 完全相同。

#### 提案 K：把計時補完

`pipeline.py:run` 在 `return` 前加 `lap("metrics")`，並在 `service.py:rank` 記 `diversify` 與 `learn_preferences` 的時間，`api.py` 記整個 handler 的 wall clock 進 `timings_ms["total_server"]`。**現在的 298 ms 是低估值**，舞台上會被抓到。零風險。

### 3.8 不建議做的事（以及理由）

| 提議 | 為什麼不做 |
| --- | --- |
| HNSW / IVF / faiss ANN | 17.8k–50k 規模下精確搜尋只要 1.4–4.5 ms（我量的）。Faiss 官方指南的 IVF 建議從 < 1M 才開始；Qdrant 在過濾後集合小於門檻時自己就改走 brute force。新依賴 + recall 損失 + 現場無網路 = 淨負分 |
| roaring bitmap / `pyroaring` | pyroaring 自己的 benchmark 是 1M 元素（交集 600 µs）。我們 17,783 個位元的 numpy 布林 AND 是 **5 µs**。Roaring 解的是「稀疏大集合的壓縮」，不是我們的問題 |
| ONNX / int8 量化查詢編碼器 | HF Optimum 官方量到 int8+ORT 對 RoBERTa 是 1.8×（117.6 → 64.9 ms，CPU 2 核）。我們的 text tower 在 V100 上本來就只佔個位數 ms，1.8× 省不到 5 ms，卻多一個匯出步驟與一個現場會壞的 runtime |
| 查詢結果快取 | 評審每輪都改條件與給回饋，命中率接近 0；還會製造「改了條件卻回一樣卡片」的舞台 bug。Algolia 自己的引擎文章講的是「索引常駐記憶體」，不是查詢快取 |
| `mmap` 載 embedding 快取 | 我量到：136 MB 的 `.npy`，`np.load` 70.8 ms vs `mmap_mode='r'` 1.7 ms —— 但 mmap 之後**第一次**全庫 matvec 要 17.8 ms（page fault 現形）。對「常駐 process + 先 warm-up」的 demo，mmap 只是把成本從啟動搬到第一個查詢，**方向錯了** |
| Qwen3-VL-Reranker 2B | 設計文件 §0／§3.20 已量到 NDCG@5 −0.043（p=0.001）且 +~0.5–1 s/query。排序更差、延遲更高 |

---

## 4. 冷啟動：現場怎麼讓「第一個查詢」不慢

### 4.1 業界的原則

- Triton 的 `ModelWarmup` 官方理由逐字就是我們的問題：「對某些 backend，部分或全部初始化會延到模型收到第一個推論請求時才做…最初的（幾個）推論請求會明顯較慢」，做法是**在模型被標為 ready 之前**送合成請求。（NVIDIA Triton 文件，2026-09-18 取得）
- Kubernetes `startupProbe` 存在的理由就是「初始化很慢的容器（例如載入 ML 模型）」，文件範例給到 300 s 寬限；readiness probe 再分開決定何時開始導流量。（K8s 文件，2026-09-18 取得）
- 第一次 CUDA 呼叫貴的底層成因之一是 kernel launch overhead：帶同步的 launch 約 9.6 µs／kernel（純 overhead 6.7 µs），CUDA Graph 要一次性 400 µs instantiation。（NVIDIA CUDA Graphs blog，2019-09-05）

**共同原則一句話：「ready」不該代表「程式啟動了」，該代表「已經成功跑完一次完整的真實請求」。** 我們現在的 `/health` 只要 `STATE["engine"]` 存在就回 `"status": "ok"` —— 這對現場是危險的。

### 4.2 我們的冷啟動成本在哪

coordinator 的量測：首次約 **119 s**，設計／圖片快取熱了之後約 **2 s**。我在本機量到的分項（CPU-only，只能解釋「2 s」那一段）：

| 項目 | 本機量測 |
| --- | --- |
| `import numpy, pandas` | 820 ms |
| `import fastapi, uvicorn` | 839 ms |
| `import engine02`（含 pipeline） | 236 ms |
| `load_taxonomy()` 首次 | 80.7 ms（之後 `lru_cache` 0.002 ms） |
| `np.load` 136 MB 的 embedding 快取（OS cache 熱） | 70.8 ms |
| `BM25Index` 建索引（17,783 篇） | 120 ms（scipy 版 186 ms） |
| `CatalogIndex` 建索引（提案 A） | 7.1 ms |
| `item_node_ids`（提案 B） | 512 ms |

也就是說**約 2 s 幾乎全是 Python import**，這條線降不下去也不必降。**119 s 的那 117 s 在 GPU 路徑上**：torch/CUDA context + transformers 載 SigLIP + 首次 CUDA kernel。

### 4.3 更危險的：`design_matrix` 是**在第一個請求裡**才載入的

`pipeline.py:run` 第 264 行才呼叫 `self.design_matrix(arm)`，而 `design_matrix`（第 143–177 行）在快取檔不存在或 shape 不符時會**整個重算** `design_scores(self.encoder, self.image_emb, ...)`。

**舞台情境**：換了商品庫、或換了 `kansei.version`、或換了 arm（檔名含 `concept_mode`／`dn`／`mask`），快取 miss → **第一個查詢在評審面前重算整個設計矩陣**。`concept_mode` 若是 `vlm`/`hybrid` 更慘，會去 glob `vlm_attributes_*.parquet`，找不到就直接 `FileNotFoundError` → 500。

#### 提案 L：`engine02/api.py:lifespan` 加 warm-up，並讓 `/health` 誠實

具體做法（全部在 `api.py`，不動 pipeline）：

1. `STATE["ready"] = False`；建完 engine 後跑 warm-up：
   - `engine.design_matrix(ARMS[serving_arm])` —— 強制把設計矩陣載進來（或**在快取 miss 時大聲失敗**，讓我們在 demo 前而不是台上發現）。
   - 用 `docs/contract/example_round1_request.json` 跑 2 次 `service.rank(...)`（第一次含首次 CUDA kernel，第二次確認穩態），**丟棄結果**。
   - 用 round2 的 request 跑 1 次（有回饋、有 critique、有 `choice_history` → 會觸發 `preference.BayesLogistic` 與 `composed` 路徑，這兩條路徑的 lazy import 也要在這裡付掉）。
   - 若 `ctl` 存在，用商品庫裡的第一個 item 跑 1 次 `complete_look`（觸發 OT 的首次 forward）。
   - `STATE["ready"] = True`，並把每一步的 ms 記進 `STATE["warmup_ms"]`。
2. `/health` 在 `ready` 為 False 時回 **503**，body 帶 `{"status": "warming", "step": ...}`；為 True 時把 `warmup_ms` 一起吐出來。
3. `/rank`、`/view`、`/complete-look` 在 `not STATE["ready"]` 時回 **503 + Retry-After**，而不是排隊等（FastAPI 的 lifespan 其實會擋住第一個請求，但 `design_matrix` 的 lazy 路徑不會）。
4. 前端的「送出」按鈕在 `/health` 回 200 之前保持 disabled。**這是唯一能保證評審看不到 119 s 的作法。**

**預期效果**：評審看到的第一個查詢和第一千個一樣快。**風險：零**（只是把既有工作提前）。
**驗證**：`scripts/bench_latency.py` 已經有 `--cold`；加一個斷言「warm-up 之後的第一次 `/rank` 與第 10 次的差 < 2×」。

#### 提案 M：程式常駐 + 不要在 demo 中重啟

- 用 tmux（或 systemd user unit）讓 uvicorn 常駐，**demo 前 30 分鐘就起好並 warm 完**。
- `--workers 1`。多 worker 會讓每個 worker 各自載一份模型與 embedding（記憶體 ×N），而且**第一個查詢落到哪個 worker 是隨機的** —— 只有一個被 warm 過的話，評審有 1/N 機率撞到冷的那個。
- 不要用 `--reload`（檔案監看會在你不小心 `touch` 檔案時重啟整個服務）。

### 4.4 為什麼 mmap 不是答案（反直覺，已量測）

136 MB 的 `.npy`：`np.load` 70.8 ms、`np.load(mmap_mode='r')` 1.7 ms。**但** mmap 後第一次全庫 matvec 要 **17.8 ms**（vs 常駐記憶體的 1.4 ms），因為 page fault 在第一次觸碰時才付。對「先 warm-up 再開門」的 demo，**mmap 只是把成本搬到第一個真實查詢上**。結論：**用普通 `np.load`，然後 warm-up**。這也和 Algolia 那句「整個索引常駐記憶體以避免磁碟 I/O」一致。

---

## 5. 現場 demo 風險清單（每一條配一個具體護欄）

按「會在台上炸掉的機率 × 難以解釋的程度」排序。

| # | 風險 | 具體機制 | 護欄（`檔案:函式` + 做法） |
| --- | --- | --- | --- |
| **1** | **LLM 改寫沒有 timeout，斷網時整個請求掛住** | `contracts.py:137` `explain_with_llm` **預設 True**；`api.py:build_engine` 只要 `.env` 有 `OPENAI_API_KEY` 就掛上 LLM；`explain.py:explain` **對使用者看到的每一張卡各呼叫一次**、**序列**、**沒有 timeout**。OpenAI Python SDK 預設 timeout 600 s、retry 2 次 → 最壞情況一張卡 30 分鐘。`except Exception` 只在 timeout **到期後**才接到 | (a) `api.py:rank` / `rank_plain` / `view`：讀一個 `ENGINE02_DEMO=1` 環境變數，為真時**強制** `req.options.explain_with_llm = False`；(b) 若一定要留 LLM，`llm.py:openai_llm` 改成 `OpenAI(timeout=1.5, max_retries=0)`；(c) demo 前把 `.env` 的 key 拿掉最乾淨（`explanation_source` 會誠實回 `"template"`） |
| **2** | **第一個查詢重算 `design_matrix`** | `pipeline.py:run:264` 才 lazy 載入；快取檔名綁 `encoder`／`kansei.version`／`concept_mode`／`dn`／`mask`，任一改動就 miss → 在評審面前重算 | 提案 L 的 warm-up 強制載入；另外在 `api.py:lifespan` 明確檢查 `f.exists()` 並在缺檔時**啟動就失敗**（fail fast 遠勝台上 fail） |
| **3** | **`/complete-look` 首次要開 100 張圖跑 CLIP** | `complete_look.py:ensure_embeddings`；`api.py:lifespan` 沒傳 `cache_file` → 每次重啟歸零 | 提案 I（傳 `cache_file` + 離線預算全庫）＋ warm-up 先打一次 |
| **4** | **tokenizer / model 首次下載打網路** | `models.py:TorchEncoder` 走 HF hub；若 `HF_HOME` 指到沒有預熱的位置、或 `~/.cache/huggingface` 被清過，就會在啟動時嘗試連線 | demo 前設 `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` 並實測啟動成功；`HF_HOME` 指到本機磁碟（不是 NFS、不是家目錄——這也符合我們既有的伺服器規則）。這樣「會不會下載」在 demo 前就有答案，而不是台上才知道 |
| **5** | **NFS／網路磁碟上的快取** | `catalog.root / "index"` 的 `.npy`（44k 時 136 MB）與 17,783 張圖檔。若在 NFS 上，`np.load` 與 `/images/{id}` 的 `FileResponse` 會隨機出現數百 ms 的尖峰 | demo 用的商品庫與 index 全部先 `cp` 到本機 SSD（伺服器上按既有規則放 `/tmp2`）；`/images` 端點在 warm-up 時先各讀 20 張讓 OS page cache 熱起來 |
| **6** | **GPU 被別的 job 搶** | cfda4 是共用機。別人一個 job 起來，我們的 SigLIP forward 會從個位數 ms 變成數百 ms，且**沒有任何錯誤訊息** | (a) demo 前 `nvidia-smi` 確認獨佔並設 `CUDA_VISIBLE_DEVICES` 鎖定一張卡；(b) **準備 CPU 後備**：本機量到全庫 dense matvec 只要 1.4 ms，`retrieve` 的 GPU 需求只有「一句查詢的 text tower」，CPU 上約 10–50 ms（依 §2.6 的 HF Optimum 數字外推），**總延遲仍在 100 ms 內**。所以「GPU 掛了就改 `ENGINE02_DEVICE=cpu`」是可行的降級，值得先實測一次並記下數字 |
| **7** | **首次 CUDA context / cuDNN autotune** | 第一個 CUDA 呼叫要建 context；kernel launch 本身也有 ~6.7 µs 的同步 overhead（NVIDIA CUDA Graphs blog, 2019-09-05） | 提案 L 的 warm-up 跑兩次真實請求就付掉了 |
| **8** | **thread contention：BLAS 執行緒 × uvicorn worker** | numpy/BLAS 預設開滿核心；FastAPI 的同步 handler 跑在 threadpool（預設 40 個 thread）。兩個並行請求 × 每個開 N 個 BLAS thread → 超訂、context switch 暴增，p95 會比 p50 差好幾倍 | demo 前設 `OMP_NUM_THREADS=4`、`MKL_NUM_THREADS=4`（或和核心數對齊的固定值），並用 `scripts/bench_latency.py` 量**並行 2–4 個請求**下的 p95。單人 demo 其實沒有併發，所以更重要的是**不要**讓一個請求把整台機器的核心吃光後互相打 |
| **9** | **lazy import 在請求路徑上** | `pipeline.py` 的 `from .attribute_fill import provenance_note`（在 `attribute_notes` 裡）、`from .taxonomy import legacy_constraints`（在 `_metrics` 裡）、`service.py` 的 `from .preference import BayesLogistic`、`api.py:view` 的 `from .panels import build_view`、`api.py` 的 `from .trends import ...`。第一次走到的那個請求要付 import 成本 | warm-up 必須**打到每一條分支**：round1（無回饋）、round2（有 critique + `choice_history` + `rejected_item_ids`）、`/view`、`/complete-look`、`/needs/supply`。提案 L 已含前四個 |
| **10** | **`/vocabulary` 在請求時做全庫 `value_counts` + `closed_vocabulary`** | `api.py:vocabulary` 對 6 欄各做 `dropna().astype(str).value_counts()` 再組 taxonomy payload。ENGINE 01 若在 demo 中呼叫它就會吃到這個成本 | 在 `lifespan` 裡算好一次放 `STATE["vocabulary"]`（它只依賴商品庫，不依賴請求），`/vocabulary` 直接回。零風險 |
| **11** | **44k 商品庫時的線性放大** | 我們所有熱點都是 O(N)。我實測 50k 的 dense matvec 4.46 ms（f32）、遮罩仍是微秒級 | 在 demo 用的商品庫上**實際跑一次** `scripts/bench_latency.py`，不要用 17.8k 的數字去承諾 44k 的延遲 |
| **12** | **`_metrics` 的 40 ms 不在任何計時裡** | §3.7 | 提案 K（補 `lap("metrics")` 與 `total_server`）。沒有這個，我們對評審報的延遲是錯的 |

---

## 6. 給 coordinator 的實作清單

按 **(預期省下 ÷ 風險)** 排序。所有 ms 數字：來源標 **[伺服器]** 的是 coordinator 在 cfda4 量的，標 **[本機]** 的是我在 Windows CPU 上量的同一個函式前後比（見 §7 的免責）。

| # | `檔案:函式` | 具體做法 | 預期省下 | 正確性風險 | 如何驗證排序沒變 |
| --- | --- | --- | --- | --- | --- |
| **1** | `engine02/constraints.py:_slot_mask` / `build_mask`（新增 `CatalogIndex` / `ColumnIndex`，在 `pipeline.py:Engine02.__init__` 建一次） | 對每個過濾欄做一次 `pd.factorize` → 只對 uniques 呼叫 `_norm` → 合併同義 unique → 存 `codes:int32[N]`、`index:dict[str,int]`、`isnull:bool[N]`。slot mask = `np.isin(codes, want)`，`allow_unknown` = `|= isnull`。欄位**用到才建**（lazy dict），不要固定六欄 | **[伺服器] 約 −200 ms**（`filter` 242 → < 5）。[本機] `build_mask` 46.12 → 0.547 ms；索引建立 7.1 ms 一次 | **低**。我已對 **120/120** 組隨機條件（含 relaxation state、`required_values`、`excluded_values`、隨機 `excluded_positions`）驗證 `mask` 與 `applied` 完全相同。要注意：(a) `excluded_values` 原碼沒做 `.strip()`，要保留這個不對稱；(b) `provenance_filter._view` 回傳的是改過 `color` 的 view，要對它另建一份索引 | 500 組隨機 `HardConstraints` × 所有 relaxation state 的 `np.array_equal(mask_old, mask_new)` 全真；再對 `docs/contract/example_round{1,2}_*.json` 比對 `items[].item_id` 序列、`score`（12 位小數）、`constraint_report.relaxed` 逐項相同；`scripts/api_check.py` 15 項全過 |
| **2** | `engine02/pipeline.py:_metrics` | 用 #1 的 `CatalogIndex` 對全庫算一次 mask，`sat = mask[shown_pos].mean()`；`category_mask` 走 #4 的快路徑；`excluded_value_hits` 改成 codes 查表 | **[本機] 約 −45 ms**（目前**完全沒被計時**：`satisfies` 單件 1.952 ms × 21 件 = 44.15 ms） | **低**。`satisfies` 就是「對一列跑 `build_mask(state={})`」，逐列獨立，對全庫算一次再取值等價 | 200 組隨機 (constraints, shown_pos) 比對 `hard_constraint_satisfaction`、`match_policy`、`excluded_value_hits`、`rejected_item_hits`、`feedback_violations` 完全相同 |
| **3** | `engine02/sparse.py:BM25Index` | 換成 scipy CSC 預算 (doc, term) BM25 權重矩陣（BM25S 的核心機制，約 40 行，**不加新依賴**）。保留 `vocab` 與 `coverage()`。k1/b/idf（含 `epsilon=0.25` 的負 idf floor、`avg_idf` 取全 vocab 平均）逐字照抄 `rank_bm25.BM25Okapi` | **[本機] 約 −11 ms**（11.41 → 0.238 ms，48×）。伺服器上可能更多（純 Python，GPU 幫不上）。`use_trend` 開啟時再省一次 | **低**。我量到分數最大絕對誤差 **5.68e-14**、6 句查詢 **top-50 順序全部相同**。理論上能翻轉完全同分的兩件 | 對 T1 的 40–100 句查詢跑 NDCG@5 **配對**比較，要求 **Δ = 0**（不是「不顯著」）；並比對每句的 `cand` 陣列逐元素相同 |
| **4** | `engine02/taxonomy.py:Taxonomy.category_mask`（＋在 `__init__` 預算 `node_codes`） | 開服務時算一次 `item_node_ids` → `node_codes:int32[N]`；查詢時 `np.isin(node_codes, target_codes)`。**只在 `"source" in items.columns` 或該 catalog 只有一個 source 時走快路徑**，collection 保留慢路徑 | **[本機] 約 −25 ms**（8.08 → 0.067 ms，每 rung 一次 × 約 4 rung，加上 `_metrics` 裡那一次）。索引建立 512 ms 一次（可存成 `index/nodes_<catalog>.npy`） | **中**。`item_node_ids` 每件只取**一個** node（`next(...)`），而 `category_mask` 用 `(source, value)` pair 集合；混合 vocabulary 且無 `source` 欄時可能不一致 → 用上述條件守住 | 對 `kagl_polyvore`（混合庫）的**全部**類別值與 collection 做一次 parity 掃描，要求 `np.array_equal` 全真；不成立的值自動退回慢路徑並記 log |
| **5** | `engine02/pipeline.py:run`（dense）＋`_terms`（penalty） | `dense_all = (self.image_emb @ q32)[pool]`，全程 float32（`query_embedding` 不要 `.astype(np.float64)`）。penalty 的 `image_emb[pool] @ image_emb[neg].T` 同樣改成全庫一次再切 | **[本機] −11.7 ms**（17.8k：13.16 → 1.44）／**−40 ms**（50k：44.72 → 4.46） | **中**。float32 累加順序不同 → 分數第 8 位小數後改變（最大值差 3.4e-08）。我實測 top-50 順序**完全相同**（17.8k 與 50k 各一組） | T1 查詢集逐句比對 `items[].item_id` 序列完全相同；`score` 差 < 1e-6；`contributions` 加總仍等於 `score`。**若任何一句順序改變，改用「預存 float64 全庫、全庫一次再切」版**（仍省 −10 / −36 ms，且位元相同） |
| **6** | `engine02/api.py:lifespan`（warm-up）＋ `api.py:health` | `STATE["ready"]` 旗標；warm-up 依序做：`design_matrix(serving_arm)` → `rank(round1)` ×2 → `rank(round2 含 critique + choice_history)` → `/view` → `/complete-look`；記 `warmup_ms`。`/health` 在 ready 前回 **503**；`/rank` 等端點回 503 + `Retry-After`；前端按鈕在 `/health` 200 前 disabled | **[伺服器] 把 119 s 從評審身上移走**（穩態不變） | **零**（只是把既有工作提前）。副作用是啟動變慢約 1–2 s + OT 首次 forward | `scripts/bench_latency.py --cold` 加斷言「warm-up 後第 1 次 `/rank` 與第 10 次的差 < 2×」；`/health` 在 warm 前確實回 503 |
| **7** | `engine02/api.py:rank` / `rank_plain` / `view`（＋`llm.py:openai_llm`） | `ENGINE02_DEMO=1` 時強制 `options.explain_with_llm=False`；`openai_llm` 改成 `OpenAI(timeout=1.5, max_retries=0)` | **把「斷網時卡住數十秒到數分鐘」變成 0 ms**。有網路時省 5 次序列 API 呼叫（數百 ms 到數秒） | **零**（排序完全不受影響，只影響 `explanation` 的文字與 `explanation_source`） | 比對 `items[].item_id`、`score`、`reasons`、`contributions` 完全相同；只有 `explanation` 從 LLM 句變回模板句、`explanation_source` 從 `"llm"` 變 `"template"`。`scripts/api_check.py` 的忠實度斷言仍過 |
| **8** | `engine02/taxonomy.py:filter_with_category_relaxation` | `excl = sorted(base_excl | set(...tolist()))` 改成布林陣列；`constraints.build_mask` 的 `excluded_positions` 改接受 `np.ndarray[bool]` | **[本機] 約 −10 ms**（往返 1.675 ms + fancy 賦值 1.328 ms，× 約 4 rung） | **零**（集合運算等價） | 同 #1 的 mask parity 測試（我的 120 組已含隨機 `excluded_positions`） |
| **9** | `engine02/api.py:lifespan` + `complete_look.py`（OT 快取） | `FastOutfitTransformer(..., cache_file=engine.cache / f"ot_{heads}.npz")`；另寫一支離線腳本對全庫 `ensure_embeddings` + `save_cache()` | **首次 `/complete-look` 從約 1–3 s 降到 < 50 ms** | **零**（embedding 確定性） | 隨機 50 個 position 的 `np.allclose(cached, online)`；`/complete-look` 的 slates `item_id` 序列在有無快取下相同 |
| **10** | `engine02/api.py:vocabulary` | 在 `lifespan` 算好放 `STATE["vocabulary"]`，端點直接回 | 把一個「ENGINE 01 一呼叫就吃到」的全庫 `value_counts` 從請求路徑移除 | **零**（只依賴商品庫） | 回傳 JSON 與現況逐鍵相同 |
| **11** | `engine02/pipeline.py:run`（計時）＋`service.py:rank` | `return` 前加 `lap("metrics")`；`service.rank` 記 `learn_preferences` 與 `diversify` 的 ms；`api.py` 記 handler wall clock 進 `timings_ms["total_server"]` | **0 ms**，但讓報出去的數字是真的（目前 298 ms 是低估） | **零** | `sum(timings_ms 的階段) ≈ total_server`（差 < 5 ms）成為 `scripts/api_check.py` 的新斷言 |
| **12** | `engine02/pipeline.py:run`（候選選取） | `np.argsort(-fused)` → `np.argpartition` + 對取出的批做 `kind="stable"`；**必須處理第 n_cand／n_cand+1 名同分**（取所有等於邊界分數的索引再穩定排序），或只在 `len(pool) > 4*n_cand` 時啟用 | **[本機] −1.6 ms**（1.678 → 0.061 ms） | **中**（同分邊界；`candidate_fusion="bm25"` 時大量商品分數為 0，同分**極常見**） | 對 `bm25`/`dense`/`rrf`/`convex` 四種 fusion 各跑 T1 查詢集，要求 `cand` 陣列逐元素相同 |
| **13** | `engine02/pipeline.py:run`（深層那一輪）＋`diversify.py:deep_request` | 深層輪跳過 `template_reasons` 與 `explain`，`Contribution` 改用 `model_construct`。**`need_contributions`、`attribute_notes`、`design_scores` 不能跳**（`diversify_response` 要用） | **約 −7 ms** | **中**。要逐一確認 `diversify_response` 讀了 `deep.items` 的哪些欄位（`score`、`contributions`、`need_contributions`、`attribute_notes`、以及 `model_dump()` 帶過去的 `design_scores`） | 最終 `ServiceResponse.items[].reasons`、`explanation`、`explanation_source`、`design_scores`、`margin_vs_cutoff` 逐字相同 |
| **14** | `engine02/attribute_fill.py:provenance_filter._view` | `color_family` 改成讀商品庫已有的 `color_family` 欄（`fill_attributes` 已經寫出來了），沒有該欄才回退到 list comprehension | 只影響每商品庫第一次（約 −20 ms 一次性）。**真正價值是消除兩份 `color_family` 計算路徑** | **低**（若 `COLOR_TO_FAMILY` 改過，欄位與函式可能不一致 → 加一個一致性斷言） | 對全庫比對 `items["color_family"]` 與 `[color_family(v) for v in items["color"]]` 完全相同，否則記 warning 並用函式版 |
| **15** | 環境（不是程式） | demo 前：`OMP_NUM_THREADS`/`MKL_NUM_THREADS` 固定；`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 並實測啟動成功；商品庫與 index 複製到本機 SSD；`CUDA_VISIBLE_DEVICES` 鎖卡；`uvicorn --workers 1`、不用 `--reload`；tmux 常駐並提前 30 分鐘 warm 完 | 防的是 p95 尖峰與「台上才發現要下載模型」 | **零** | `scripts/bench_latency.py` 在**併發 2–4** 下量 p95，並記錄 CPU-only 降級模式下的 p50/p95 各是多少 |

**做完 #1–#5 就夠了**：預期 `/rank` 服務端從 298 ms（+未計時的 40 ms）降到 **約 25–35 ms**，44k 商品庫時仍在 **60–80 ms**。#6 與 #7 不省穩態延遲，但它們防的是**唯一會讓 demo 當場失敗的兩件事**，所以請和 #1 一起做。

---

## 7. 「我沒有量測、只是引用」

### 7.1 引用的數字（別人的量測，我沒有重現）

| 數字 | 來源 | 我對它的可信度判斷 |
| --- | --- | --- |
| Etsy P99 18 ms（編碼+ANN）、P99 < 20 ms、Faiss 4-bit PQ fastscan、取所需 K 的 5 倍再 rerank | arXiv:2306.04833（2023-06-07 / 2024-09-25）。**我親自從 ar5iv 全文取得逐字句** | **最可信**。明確標 P99、明說量什麼、同儕審查 |
| Taobao ANN top-9,600、98% 準確率、10 ms | arXiv:2106.09297（2021-06-17） | 可信，但**沒標 percentile**，讀起來是典型值 |
| Taobao TDM 平均約 6 ms | arXiv:1801.02294（2018-01-08） | 可信，明確標「平均」，但只是單一階段 |
| Amazon Semantic Product Search「20 ms 內、每秒數千查詢」 | arXiv:1907.00937（2019-07-01） | 可信但精度低：這是論文**陳述的設計約束**，不是量測分佈 |
| Uber Michelangelo P95 < 5 ms（無特徵查詢）／< 10 ms（有） | uber.com/blog（2017-09-05） | 可信，明確 P95；但是通用 ML 平台、非時尚檢索 |
| Nielsen 0.1 / 1.0 / 10 s 門檻 | nngroup.com（1993，2014 再確認） | 可信；是認知研究綜述，不是 A/B 測試 |
| Deloitte 0.1 s → 零售轉換 +8.4% 等 | deloitte.com（2020-03-24） | **偏行銷**。顧問 × 平台商報告，方法只有高層描述、非同儕審查。方向性可用，因果不可用 |
| Google「0.5 s → 流量 −20%」 | glinden.blogspot.com（2006-11-09） | **二手**。轉述演講，無 Google 原始發表 |
| Amazon「100 ms = 1% sales」 | — | **查不到出處。當成坊間傳說，不要引用。** 原始 blog 只說「可觀營收損失」，沒有百分比 |
| BM25S vs rank-bm25 的 QPS 表（14 個 BEIR 語料） | arXiv:2407.03618（2024-07-04）＋ github.com/xhluca/bm25s README | 可信，方法明確（Intel Xeon 2.70 GHz、單執行緒、10 次平均）。**注意：該論文沒有和 PISA 比較** |
| rank_bm25 作者自己建議改用 retriv | github.com/dorianbrown/rank_bm25 README（2026-09-18 取得） | 可信（作者自述） |
| DPP fast greedy O(k²N)；Netflix 平均 0.73 ms / P99 1.75 ms、MSD 0.76 / 1.46 ms | arXiv:1709.05135（NeurIPS 2018） | 可信，同儕審查、有 Table |
| Faiss「Flat 適用於少量查詢或需精確結果」、IVF 建議從 < 1M 起 | faiss wiki（2026-09-18 取得） | 可信（官方選型文件） |
| Qdrant「過濾後集合小於門檻（預設 10,000 KB）自動改全掃描」、「過濾太嚴格時 HNSW 圖會解體」 | qdrant.tech 文件（2026-09-18 取得） | 可信（廠商官方文件，但描述的是自家實作行為，不是中立 benchmark） |
| Qdrant filterable HNSW 的機制（每 category 加邊、≤2× 邊數、percolation p_c = 1/⟨k⟩） | qdrant.tech/articles/filterable-hnsw（2019-11-24） | 機制可信；**此文沒有吞吐量數字** |
| Weaviate ACORN：低選擇性（~20%）過濾下比 sweeping 吞吐約 2×；低相關性時快一個數量級 | weaviate.io blog（benchmark 標 2024-11） | **廠商自家 benchmark**，方向可信、絕對值打折 |
| Vespa phased ranking 預設 second-phase 100 / global-phase 100 | docs.vespa.ai（2026-09-18 取得） | 可信（官方預設值）。**此頁沒有任何絕對延遲數字** |
| Pinecone Sift1M：Flat ~18 ms/查詢 recall 1.0；HNSW 0.6–2.1 ms；「< 10K 用 flat」 | pinecone.io/learn/vector-indexes（無日期，2026-09-18 取得） | **廠商行銷內容**（文末推銷自家產品），但附了實質 benchmark 表。當成量級參考 |
| Roaring bitmap 比 WAH/Concise/EWAH 快數倍到兩個數量級；Lucene/Spark/Kylin/Druid 採用 | Chambi et al., SPE 46(11):1547–1569（2016-11），arXiv:1603.06549 | 可信（同儕審查）。Druid 文件（2026-09-18 取得）從系統方確認現況 |
| pyroaring：1M 元素、密度 0.125 下交集 600 µs vs Python set 46.6 ms | github.com/RoaringBitmap/PyRoaringBitMap README（2026-09-18 取得） | 可信（專案自家 benchmark，環境有寫）。**但規模是 1M，不是我們的 17.8k；該 benchmark 也完全沒有和 numpy 布林陣列比較** |
| HF Optimum：RoBERTa 117.61 → 64.94 ms（ONNX+int8，1.8×），F1 保留 99.61%，模型 −38% | huggingface.co/blog/optimum-inference（2022-05-10） | 可信，方法明確（m5.xlarge、2 核、10 warm-up + 100 次） |
| Triton `ModelWarmup` 的理由與做法 | NVIDIA 文件（2026-09-18 取得） | 可信（官方文件，定性） |
| CUDA kernel launch：執行 2.9 µs、帶同步 launch 9.6 µs、CUDA Graph 3.4 µs + 400 µs instantiation | developer.nvidia.com/blog/cuda-graphs（2019-09-05） | 可信（廠商工程 blog，有具體數字） |
| K8s `startupProbe` 用於「載入 ML 模型」等慢啟動容器，範例 300 s 寬限 | kubernetes.io 文件（2026-09-18 取得） | 可信（官方文件） |
| Pinterest ItemSage：embedding 走每日離線批次「以確保推論延遲不影響端到端延遲」 | arXiv:2205.11728（2022-05-24） | 可信（定性）。**此論文沒有任何延遲數字** |
| Spotify：episode embedding 離線批次 + 只有查詢線上編碼；T4 GPU 相對 CPU「6 倍成本下降」 | engineering.atspotify.com（2022-03-17） | 可信（定性 + 一個成本比值）。**無絕對 ms** |
| pandas `.apply()` 111 ms → Cython+ndarray 887 µs（125×）；20,000×100 上 `pd.eval()` 反而更慢 | pandas.pydata.org「Enhancing performance」（2026-09-18 取得） | 可信（官方文件的 timeit 數字），但**不是我們的資料形狀**，只用來支持「Python-per-row 是量級問題」這個論點 |
| Algolia：搜尋與索引 process 分離、整個索引常駐記憶體、deadline scheduler 調校 | algolia.com/blog（2024-01-22） | 可信（工程 blog）。**此頁沒有 cache-hit-rate 也沒有 p95 數字** |
| Elasticsearch shard request cache / filter context 會自動快取 | elastic.co 文件（2026-09-18 取得） | 可信（定性）。**官方頁沒有命中率或延遲數字** |
| Feast online/offline store 分離 | docs.feast.dev（2026-09-18 取得） | 可信（定性）。**現行公開頁沒有 p99 數字**；Tecton 舊 benchmark 文已因併購 301 導向 Databricks |

### 7.2 明確查不到 / 不能引用的

- **Zalando**：工程 blog 的 search 標籤下**沒有**任何公布搜尋排序延遲的文章（<https://engineering.zalando.com/tags/search.html>，2026-09-18 取得）。
- **Facebook KDD 2020 "Embedding-based Retrieval in Facebook Search"**：全文**沒有任何延遲數字**，只有「pq_bytes 越大 → 精度越高但記憶體與延遲也越高」的定性句。網路上流傳的該論文延遲數字**是假的**。
- **Amazon P-Companion (CIKM 2020)**：沒有延遲數字（只有「服務 2 億商品」的規模）。
- **ASOS、Instacart、Myntra、Flipkart、Shopify、Walmart Global Tech、eBay、Wayfair、Coveo、Netflix、Etsy Code as Craft、Airbnb**：本次無法取得（Medium／CDN 回 403），且本 session 的 WebSearch 額度耗盡，無法做發現式搜尋。**沒有為它們編造任何數字。**
- **Algolia 公布的 p95 與其量測方法**：未取得。
- **Kohavi 的 Bing 延遲實驗（KDD 2013）**：PDF 取得但無法解析文字，無法確認「100 ms / 1%」的文字出處。
- **`torch.compile` 首次編譯的具體 ms/s**：未取得可引用來源，**本文沒有引用任何 `torch.compile` 數字**。
- **ClickHouse 的 bitmap 是否為 Roaring**：官方函式頁未說明，**未能證實**。
- **`DataFrame.copy()` 在 20k×20 的官方 timing**：官方文件沒有。（我自己量到 0.141 ms，見下）
- **YouTube / Netflix / Pinterest / Hulu 的 DPP 上線成本 blog**：全部 403 或 404，**未能取得**。本文對 DPP 的成本論證只用 NeurIPS 2018 論文 + 我自己的量測。

### 7.3 我自己量的數字（以及它們的限制）

**環境**：Windows 11、本機 `.venv`（Python 3.12）、**CPU-only**、`data/catalog/kagl/items.parquet`（5,000 列）用 `pd.concat` 平舖到 **17,783 列**（15 欄，含 Arrow-backed string dtype），`attr_source` 填成合法 JSON 以觸發 `provenance_filter("family")`。dense 部分用隨機 L2-normalised float32 矩陣。每項 3–5 次 warm-up 後取 10–500 次平均。

**限制（請認真對待）**：
1. **這台機器不是 cfda4**。CPU 型號、記憶體頻寬、BLAS 都不同 → **絕對值不可移植**。
2. 商品庫是**平舖複製**的，不是真的 `kagl_polyvore_filled`。欄位的 unique 值數（影響 `factorize` 與 `np.isin`）與真實庫不同，`subcategory` 的 taxonomy 命中率也不同。
3. `pandas` 版本在本機是 Arrow-backed string dtype，伺服器上若是 object dtype，`Series.map` 的常數會不同（可能更快或更慢）。
4. 所有「省下 X ms」都是**把本機的前後比值套到伺服器的絕對值上**，屬推論。**請在 cfda4 上用 `scripts/bench_latency.py` 重量一次再對外報數字。**
5. 這些原型程式在我的 scratchpad，**沒有進 repo**，也沒有跑過 repo 的測試套件。

| 我量的項目 | 結果 |
| --- | --- |
| `constraints.build_mask`（17,783 列、4 個硬條件） | **46.12 ms** → 提案原型 **0.547 ms**（84×）；**120/120 組隨機條件的 mask 與 applied 完全相同** |
| cProfile 歸因（10 次 `filter_with_category_relaxation`，4.192 s） | `build_mask` 佔 cumtime **77%**；`constraints._norm` 被呼叫 **1,956,130 次**（每請求約 20 萬次） |
| `taxonomy.Taxonomy.category_mask` | **8.08 ms** → 原型 **0.067 ms**（120×）；8 個類別值中可解析的 **7/7 完全相同**；`item_node_ids` 索引建立 **512 ms**（一次） |
| `CatalogIndex` 索引建立 | **7.1 ms**（一次） |
| `Series.map(_norm)` 單欄 17,783 列 | **7.30 ms** |
| `sorted(base_excl | set(np.flatnonzero(~cat_mask).tolist()))`（17,623 個位置） | **1.675 ms**；`mask[python_list] = False` **1.328 ms**；等價布林 AND **0.005 ms** |
| `DataFrame.copy()`（17,783 × 15） | **0.141 ms** —— **便宜，不是問題**（pandas CoW）。原先的假設「整框 copy 很貴」是錯的 |
| `rank_bm25.BM25Okapi.get_scores`（17,783 篇短文件、6 句查詢平均） | **11.41 ms** → scipy CSC 原型 **0.238 ms**（48×）；**分數最大絕對誤差 5.68e-14、6 句查詢 top-50 順序全部相同**；索引 120 → 186 ms（一次）、矩陣 1.6 MB（nnz 133,542、vocab 2,194） |
| dense：`E64[pool] @ q`（pool = 35% 全庫，768 維） | 17,783：**13.16 ms**；50,000：**44.72 ms** |
| dense：`(E64 @ q)[pool]`（預存 float64 全庫） | **3.10 / 9.04 ms**，top-50 **完全相同**；記憶體 109 / 307 MB |
| dense：`(E32 @ q32)[pool]`（全 float32） | **1.44 / 4.46 ms**，top-50 **完全相同**，最大值差 3.4e-08 |
| `image_emb[pool]` 單獨的 fancy-index 複製（全池） | f32 **15.03 ms**、f64 **29.67 ms** |
| `np.argsort(-s, kind="stable")[:50]`（17,783） | **1.678 ms** → `argpartition` **0.061 ms**（27×），top-50 完全相同（同一組隨機分數） |
| `constraints.satisfies` × 21 件（`_metrics` 的路徑） | **44.15 ms**（單件 1.952 ms）—— **目前完全沒被任何 `lap()` 計到** |
| DPP 前置：21 × 768 cosine 核矩陣 | **0.0315 ms** → DPP depth 20 的成本可忽略 |
| `import numpy, pandas` / `fastapi, uvicorn` / `engine02` | **820 / 839 / 236 ms** |
| `load_taxonomy()` 首次 / 之後（`lru_cache`） | **80.7 ms** / **0.002 ms** |
| `np.load` 136 MB `.npy`（OS cache 熱） | **70.8 ms**；`mmap_mode='r'` **1.7 ms**，但 mmap 後首次全庫 matvec **17.8 ms**（vs 常駐 1.4 ms） |
| numpy 布林 AND（17,783 元素） | **0.005 ms** —— 這就是為什麼我們不需要 roaring bitmap |

### 7.4 我推論但沒量的

- **伺服器上 `filter` 從 242 ms 降到 < 5 ms**：這是把本機 84× / 120× 的比值套到 242 ms 上。合理但未驗證。
- **伺服器上 BM25 佔 `retrieve` 的多少**：`retrieve` 44.28 ms = 查詢文字編碼（GPU）+ dense matvec + BM25 + coverage。我推論 BM25 是最大一塊（本機 11.4 ms，且是純 Python/numpy，V100 幫不上），但**沒有在伺服器上分項量過**。建議 coordinator 在 `pipeline.py:run` 把 `retrieve` 拆成 `encode_query` / `dense` / `bm25` 三個 lap 再量一次。
- **CPU-only 降級模式的實際延遲**：我推論「約 100 ms 內」，依據是本機 dense 1.4 ms + 遮罩微秒級 + 依 HF Optimum 外推的 text tower 10–50 ms。**沒有實測**。這是 demo 的 GPU 後備方案，值得在 demo 前實測一次並記下數字。
- **`/complete-look` 首次的 1–3 s**：從「100 張圖 I/O + CLIP forward」推的量級，沒有實測。設計文件 §3.14 只記了功能正確，沒記延遲。
- **`explain` 10.17 ms 裡 pydantic 驗證佔多少**：我推論 357 個 `Contribution` 的驗證是主因，**沒有 profile 過**。所以 #13 的「−7 ms」是最不可靠的一個估計。

---

## 8. 一句總結

我們的 298 ms 裡，**大約 250 ms 是「本來該在開服務時算一次的東西，被放在每個請求裡對 17,783 列重算」**。修法不需要新演算法、不需要新依賴、不需要網路、不改變任何排序結果（我已對過濾遮罩、BM25 分數、dense top-50、候選選取逐一驗證等價）。修完之後我們的服務端延遲會落在 Etsy（P99 18 ms）與 Taobao（10 ms）公布的同一個量級，而我們的商品庫比他們小三到四個數量級 —— 這才是我們該對評審說的那句話。

剩下的兩個真正的 demo 風險和延遲無關：**LLM 改寫沒有 timeout**（斷網時會卡住整個請求），以及 **`design_matrix` 與 OutfitTransformer embedding 是 lazy 載入的**（第一個查詢在評審面前付冷啟動）。這兩個各只要改十幾行，但不改就可能整場 demo 只剩一句「等一下，它平常很快的」。
