# T10 學習排序權重：可加總（可解釋）前提下取代手調權重

作者：sub-agent `ltr`｜程式：`engine02/ltr.py`、`scripts/eval_ltr.py`、`tests/test_ltr.py`｜原始結果：`reports/agents/ltr/{kagl,kagl_full}/`

## 1. 一句話結論
- **只學一組全域權重沒辦法兩種用詞都顧到。** 用詞和商品庫相同時要 BM25，換句話說時要純 dense，兩者方向相反。
- 能兩邊都顧到的方法是**依查詢用詞命中率（coverage）分流**：兩組權重都非負而且可加總。
- 在 5k 商品庫，分流幾乎就是全部的收益：未經學習的「命中率 < 1 就只用 dense」對照組已經拿到 0.639，學到的權重只再加 +0.009。
- 在 44k 全庫，75% 換句話說的查詢 coverage = 1（大詞庫把 tee、azure 這類同義詞也收進去了），所以**命中率分流失效**。學到的權重是在兩種用詞之間取捨：整體 NDCG@5 從 0.446 升到 0.547，用詞相同時差異不顯著（−0.008），換句話說時 +0.21，但仍低於純 dense 的 0.399。
- 所有學到的模型都**非負，而且 contributions 加總 = score**；理由覆蓋率 99–100%，沒有破壞解釋。

## 2. 方法
可加總分數 S(i)=Σ_t w_t·x_t(i)，x_t 是 pipeline 算出的標準化項（`norm_scope="pool"` 的 z-score）。學習時只允許 w ≥ 0，理由是：
(1) 貢獻仍然加總成分數；
(2) 「證據越多分數越高」的語意不會被負權重反轉；
(3) sufficient-reason 的挑選邏輯（依正貢獻排序）仍然成立。

| 代號 | 方法 | 出處 |
|---|---|---|
| `grid_rrf_k` / `grid_convex_alpha` | 只調候選融合：RRF k ∈{1…200}；convex α ∈[0,1] | Cormack+ SIGIR'09；Bruch+ TOIS'23 |
| `grid_full` | 格點：候選階段（dense top-100 或 RRF k）× w_bm25/(w_dense+w_bm25) ∈{0,.05,…,1} | — |
| `ca_*` | 座標上升直接最大化 NDCG@5，L1 正規化，5 次 random restart，限制 w≥0 | Metzler & Croft, Inf. Retr. 2007 |
| `ranknet_*` | 線性 RankNet pairwise logistic；Adam 加投影 w←max(w,0) | Burges+ ICML'05 |
| `ranx_*` | ranx 0.3.21 `optimize_fusion`（wsum、rrf）；CombSUM、CombMNZ（min-max）| ranx（MIT） |
| `*_typeaware` | 依 `bm25.coverage(text) ≥ θ` 分兩組各學一套；θ ∈{.5,…,1} 也只在訓練 fold 上選 | 本研究 |
| `full_route_dense`（對照，**不學**） | coverage = 1 時用手調 full，否則只用 dense | 本研究 |

特徵集：`core` = {dense_z, bm25_z}，直接對應 ArmConfig；`ext` 再加上排名式特徵 {(k+1)/(k+rank_dense), (k+1)/(k+rank_bm25)}，pipeline 需要新增 Term 才能使用。

實作重點：
- `CapturingEngine02` 是 Engine02 的子類別，覆寫 `_terms` 攔截 pool 分數、候選和 `sc.norm`，**沒有修改 pipeline.py**。
- 每個查詢保存 dense/BM25 各自 top-500 的聯集，之後可以離線重算任何 k、α、w 的排序。
- **離線模擬與真實 `engine.run` 的 top-10 完全一致**：full 550/550（kagl）、1370/1370（kagl_full）；hybrid_rrf、hybrid_convex、dense、bm25、full_adaptive_bm25 在 kagl 與 kagl_full 各 120/120（見 `t10_validation.json`）。
- 過程中發現一個細節：`hybrid_rrf` 在 `_terms` 重新計分時**沒有**套用 rrf_depth=200，模擬已照此處理。

## 3. 實驗設定
- 伺服器 nycu，encoder Marqo-FashionSigLIP。
- 查詢：`eval/tasks.make_queries`。seed 只會打亂分組順序，所以取 seed 0–2 的聯集後去重，取全部可換句話說的分組：kagl 275 句、kagl_full 685 句。每句都有「用詞相同」和「換句話說」兩個版本，所以 kagl 有 550 筆、kagl_full 有 1370 筆。
- **5-fold 交叉驗證，以查詢為單位切分**：同一查詢的兩種用詞一定在同一 fold；所有超參數（含 θ）只在 4 個訓練 fold 上選；測試 fold 的預測拼回完整集合後才算指標。
- 訓練目標：兩種用詞混合的平均 NDCG@5（假設兩者各半）。
- 統計：以查詢為單位的配對置換檢定（10,000 次），p 值對 21 個方法做 Holm 校正；bootstrap 95% CI。
- 候選數 100、top-k 10，和 T1 相同。
- **標準答案**：metadata 等級（子類＋顏色＋性別＋場合 = 3；子類＋顏色 = 2；子類 = 1），是代理指標。

## 4. 結果（held-out NDCG@5；括號內為對手調 `full` 的差，Holm 校正後 p 值）

### 4.1 kagl（5k，275 句）
| 方法 | 用詞相同 | 換句話說 | 整體 [95% CI] |
|---|---|---|---|
| full（手調） | 0.862 | 0.091 | 0.477 [0.442, 0.512] |
| hybrid_rrf | 0.850 | 0.176 | 0.513 |
| dense | 0.601 | 0.440 | 0.521 |
| full_adaptive_bm25 | 0.862 | 0.170 | 0.516 |
| **full_route_dense（不學，對照）** | 0.862 (±0, p=1) | 0.416 (+0.325, p<.01) | 0.639 [0.613, 0.666] |
| grid_full（全域） | 0.777 (−0.086, p<.01) | 0.361 | 0.569 |
| ca_core（全域） | 0.750 (−0.113, p<.01) | 0.383 | 0.567 |
| ranx_wsum（全域） | 0.847 (−0.016, p<.01) | 0.412 | 0.629 |
| **grid_full_typeaware** | **0.867** (+0.004, p=1) | **0.429** (+0.338, p<.01) | **0.648** [0.623, 0.673] |
| ca_core_typeaware | 0.872 (+0.010, p=.056) | 0.412 | 0.642 |
| ranknet_core_typeaware | 0.862 | 0.416 | 0.639 |
| ranx_wsum_typeaware | 0.848 | 0.429 | 0.639 |

- NDCG@10 與 MRR（grade 3）的排序相同。例如 grid_full_typeaware 的整體 NDCG@10 = 0.665、MRR = 0.672，full 則是 0.494 和 0.483。
- grid_full_typeaware 對 full_route_dense 的差：整體 +0.009（p=.002）、換句話說 +0.013（p<.001）、用詞相同 +0.004（p=.29）。**收益幾乎全部來自分流，學習只多一點點。**

### 4.2 kagl_full（44k，685 句）
| 方法 | 用詞相同 | 換句話說 | 整體 [95% CI] |
|---|---|---|---|
| full（手調） | 0.791 | 0.102 | 0.446 [0.426, 0.467] |
| hybrid_rrf | 0.780 | 0.200 | 0.490 |
| dense | 0.532 | **0.399** | 0.465 |
| full_route_dense（不學） | 0.791 | 0.167 (+0.065) | 0.479 |
| grid_convex_alpha（α=0.85，5 fold 一致） | 0.739 (−0.051, p<.01) | 0.339 | 0.539 |
| ranx_wsum（0.6/0.4） | 0.721 (−0.069, p<.01) | 0.370 | 0.546 |
| ranknet_ext | 0.782 (−0.009, p=.21) | 0.303 | 0.543 |
| **grid_full_typeaware** | **0.782** (−0.008, p=.21) | 0.312 (+0.209, p<.01) | **0.547** [0.530, 0.565] |
| ca_core_typeaware | 0.669 (−0.121, p<.01) | 0.371 | 0.520 |

- grid_full_typeaware 與 ranx_wsum 整體打平（+0.001，p=.82），但兩者在兩種用詞上的取捨方向相反。
- 換句話說時仍然輸純 dense −0.087（p<.001）。
- 在 44k，coverage 分流只抓得到 25% 的換句話說查詢，所以 θ 選出 0.9，實質上仍是一組全域的取捨。

### 4.3 權重穩定性（5 fold；w_dense + w_bm25 固定縮放為 1.5）
| 商品庫 / 方法 | 組別 | 候選階段 | w_dense | w_bm25 |
|---|---|---|---|---|
| kagl grid_full_typeaware | covered（θ=0.9，5 fold 相同） | dense top-100 | 0.72 ± 0.10 | 0.78 ± 0.10 |
|  | uncovered | dense top-100 | 1.50 ± 0 | 0 ± 0 |
| kagl ca_core_typeaware | covered / uncovered | RRF 60 | 0.86±.01 / 1.49±.02 | 0.65±.01 / 0.01±.02 |
| kagl_full grid_full_typeaware | covered | dense top-100 | 1.10 ± 0.07 | 0.40 ± 0.07 |
|  | uncovered | dense top-100 | 1.50 ± 0 | 0 |
| kagl_full ranknet_core | 全域 | RRF 60 | 1.37 ± .003 | 0.13 ± .003 |
| kagl_full ranknet_ext | 全域 | RRF 60 | 0.52, dense_rrf 0 | bm25_z **0**, bm25_rrf 0.98 |

- core 特徵的權重在各 fold 之間非常穩定（sd ≤ 0.1）。
- ext 特徵的座標上升不穩定（kagl_full uncovered 組的 w_dense 在 0 到 1.49 之間跳動）。原因是 dense_z 和 dense_rrf 高度共線，所以不建議採用。
- 兩個有趣的一致現象：
  - (a) 各方法都偏好**以 dense 取候選，再用 BM25 重排**，而不是以 RRF 取候選。
  - (b) ext 特徵中，BM25 的**排名式**特徵完全取代了 z-score，代表 BM25 分數尺度（多數為 0、長尾）不適合直接 z-score 相加。
- **所有 fold、所有方法的權重都 ≥ 0**（`nonneg` 欄位全為 True）。

### 4.4 跨庫遷移（用 A 庫全部查詢訓練，在 B 庫全部查詢上測試）
- kagl 權重用在 kagl_full：用詞相同 0.790（對 full p=.92）、換句話說 0.295（對 full 的 0.102，p<.001）。
- kagl_full 權重用在 kagl：用詞相同 0.850（對 full 的 0.863，p<.001，變差）、換句話說 0.429（對 0.091）。
- 結論：權重會隨商品庫規模和詞庫改變，換庫時要重新學。

### 4.5 真實引擎整合與解釋完整性
- 設定：`LearnedWeightsEngine` 載入 kagl_full 的 JSON，跑 60 句 × 2 種用詞 × 有／無隨機隱性需求；T4 式的隨機需求讓 design 項確實存在。
- 性質：contributions 加總 = score 100%；dense/bm25 權重非負 100%；至少有 1 個理由的卡片比例為 0.993–1.000（full 為 1.000）；平均引用理由數相近（2.88 vs 2.85）。
- NDCG@5：
  - 換句話說 0.328 vs 0.093（無需求，p<.001）、0.308 vs 0.094（有需求，p<.001）。
  - 用詞相同 0.761 vs 0.788（p=.094）、0.717 vs 0.735（p=.18），都不顯著。
- 注意：這 60 句包含在訓練集裡，這一節只是**完整性檢查**，不能當成效能證據；效能證據請看 §4.2 的 CV 結果。
- 換句話說時 w_bm25 = 0，design 項佔 |contribution| 的比例由 6.0% 升到 10.1%。原因是總權重固定為 1.5，BM25 貢獻消失。這會稍微改變 T6 的需求／相關性取捨，γ 可能要重新確認。

## 5. 標準答案的偏差：為什麼可能高估 BM25 權重
1. 等級完全由 subcategory/color/gender/occasion 決定。BM25 文字欄位是 title＋description＋subcategory＋color，KAGL 的 title 常含 “Men … Tshirt”，所以「用詞相同」的查詢等於把標籤原字丟給 BM25，BM25 近乎**直接讀到答案**。
2. 用詞相同的查詢 coverage 恆為 1.0，因為查詢是由 metadata 值組出來的。真實 ENGINE 01 產出的字串不會這麼乾淨，實際的 covered 組會混進較難的查詢。
3. image encoder 看不到這些欄位，所以 dense 反而被系統性低估，例如看起來正式但標註 Casual 的商品。
4. 訓練目標假設兩種用詞各半，實際比例未知。比例改變時，最佳全域權重會移動，分流版本受影響較小。

整體來說，covered 組學到的 w_bm25（kagl 0.78、kagl_full 0.40）應視為**上限**。在沒有人工標註或點擊資料之前，不建議再調高。

## 6. 建議與整合 hook
**建議預設（kagl_full 44k，Marqo）**：採用 `grid_full_typeaware` 的學習結果，JSON 在 `reports/agents/ltr/kagl_full/learned_weights_grid_full_typeaware.json`：

```json
{"schema":"engine02.ltr/v1","coverage_threshold":0.9,
 "groups":{"covered":  {"w_dense":1.125,"w_bm25":0.375,"candidate_fusion":"dense","rrf_k":60,"convex_alpha":0.5,"additive_rerank":true},
           "uncovered":{"w_dense":1.5,  "w_bm25":0.0,  "candidate_fusion":"dense","rrf_k":60,"convex_alpha":0.5,"additive_rerank":true}}}
```

理由：
- 在 CV 中整體最佳或並列最佳（0.547）；用詞相同沒有顯著損失（−0.008，p=.21），換句話說 +0.21。
- 只有 2 個可解釋的非負權重、跨 fold 穩定；不需要新增 Term。
- 相較 ranx_wsum（整體打平）：用詞相同時高 0.061（p<.001）。依 ENGINE 01 應做詞彙正規化的前提，用詞相同的情況才是主要流量。

**整合方式**（二選一）：
1. **零改動**：用 `engine02.ltr.LearnedWeightsEngine(catalog, encoder, ..., learned="<json>")` 取代 `Engine02`。每次請求先算 `bm25.coverage(retrieval_text)`，再依 θ 用 `dataclasses.replace` 換掉 arm 的 `w_dense / w_bm25 / candidate_fusion / rrf_k / convex_alpha`。只作用在 `additive_rerank=True` 的 arm，其他項權重不變。
2. **併入 config**：在 `ARMS` 新增 `full_ltr = replace(FULL, name="full_ltr", candidate_fusion="dense", w_dense=1.125, w_bm25=0.375)`，並在 `Engine02.run` 的 `bm25_adaptive` 區塊加入「coverage < 0.9 → w_bm25 = 0、w_dense = 1.5」。

換商品庫或 encoder 時要重跑：`scripts/eval_ltr.py --stage capture → ranx → learn → final`。

**更重要的建議**：44k 的結果顯示，coverage 已無法辨識「沒正規化的用詞」。與其繼續調權重，不如讓 ENGINE 01 回傳「是否已正規化成商品庫詞彙」的旗標，拿它取代 coverage 做分流。在 5k 的實驗中，只要分流正確，未學習的對照組就能拿到 0.639，對手調 full 是 +0.16。

## 7. 限制
- 只做了 T1 型查詢（沒有硬條件、需求、錨點、回饋），所以 compat、trend、penalty、design 的權重沒有學。這些項需要 T5/T6 式的模擬使用者資料，而那同樣是代理指標。
- 只測了 Marqo-FashionSigLIP 一種 encoder。
- 換句話說是用固定的同義詞表產生，詞表有限，而且 44k 的詞庫恰好涵蓋其中多數詞。
- ranx 的 min-max 是對每個 retriever 的 top-100 做，而 pipeline 的 convex 是對整個 pool 做，所以 `ranx_wsum` 與 `grid_convex_alpha` 不等價。
