# ENGINE 02 完整度稽核：需求矩陣、今晚補上的缺口、仍然缺的東西

> 稽核日期：2026-09-18，分支 `engine02-research`，稽核基準 commit `f6355c8`。
> 稽核對象：PRD（HackMD）ENGINE 02 M3–M7 與 §7 畫面、贊助商命題（可理解／可解釋／可變強、
> 「在約束下維持推薦品質」）、`docs/engine02-literature-review.md` 與
> `docs/research/engine02-method-inventory.md` 已採納的建議、交付物（可跑的原型、英文 README、可重現）。
> **本次稽核只新增檔案，沒有修改任何既有檔案，也沒有改動任何已被量測過的預設值。**

---

## 0. 一頁結論

**整體完成度**：核心鏈路（硬條件過濾 → 兩路檢索 → RRF → 可加總 reranker → 忠實理由）**做完而且有配對統計**，
比 PRD 原設計多了 12 個實驗（T1–T12）。真正的缺口集中在四個地方：

1. **PRD 寫了但程式從來沒被觸發的分支**：趨勢關鍵字（`set_trends` 沒有任何呼叫者）、
   生成概念圖併入查詢（`full_concept_image` 從未跑過）、概念圖接回最近商品。
   → **今晚三項全部補上並量測**（§2、§3）。
2. **前端要的資料在回傳裡「算得出來但沒算」**：「你說的 vs 你沒說的」、需求面板、兩輪並排的 diff、
   資料來源標示。→ **今晚以回傳擴充模型補上**（`engine02/panels.py`），不動 `contracts.py`。
3. **跨引擎握手只有文字約定、沒有實作**：`choice_history` / `critique` / `design_adjust_steps` 要怎麼
   累積、什麼只有當輪有效、誰換算權重。→ **今晚補上參考實作、測試與 JSON 往返範例**
   （`engine02/handshake.py`、`docs/contract/example_engine03_handshake.json`）。
4. **PRD §8 必做的「斷網重播模式」整個專案都沒有**。→ **今晚補上 ENGINE 02 這一半**
   （`engine02/replay.py`：彩排時錄、現場離線逐字重播）。

**兩個最重要的量化結論**（細節 §3）：

- **趨勢關鍵字不要進排序**。任何測到的權重（0.05／0.1／0.2／0.5）、任何關鍵字來源（手動／商品庫推導）、
  任何商品庫規模（17.8k／44k）、有沒有 z 截斷，NDCG@5 的代價都是 **−0.16 到 −0.38（p≈1e-4）**，
  而手動清單和**隨機字詞對照組**的差距很小（44k：−0.266 vs −0.301）。z 截斷也救不回來（§3.1b）。
  → 改用 `trends.trend_badges()`：卡片照樣顯示「趨勢」標籤，但不進分數，**代價 0**。
- **生成概念圖融合是真的有用**，而且有對照組撐著：使用者講不出話時（模糊查詢），
  權重 0.2 讓 NDCG@5 從 0.078 升到 0.325（44k，p≈1e-4），
  而**隨機概念圖對照組 −0.004（p=0.71，無效果）**，所以那是資訊不是雜訊。

**稽核期間發現的程式問題**：`ArmConfig.z_clip` 的註解說要截斷 dense/bm25/**trend**/**penalty** 四項，
但 `pipeline.Engine02._terms` 只把 `clip` 傳給前兩項。實測顯示它不是趨勢項代價大的主因，
但仍是「註解說一套、程式做一套」。修法是 pipeline 兩行，**我不改，附上包裝版與量測**。

> **coordinator 後續處理（2026-09-18 凌晨，commit `144d98e`…`5515664`）**：稽核交回後，以下項目已經關掉——
> `z_clip` 已套到 trend／penalty 四項；概念圖權重 0.2 成為服務預設 arm `full_zclip3`（`full` 保持 0 當重現基準）；
> `POST /view`、`POST /concept-image/nearest`、`GET /needs/supply`、`GET /trends` 四個 endpoint 已接出並有測試；
> `feedback_violations` 口徑裁定為**累計所有先前輪次**，並拆出 `rejected_item_hits` 讓畫面數字可逐項核對；
> `retrieval_text` 否定詞檢查改以 `constraint_report.input_warnings` 回報（中英都抓）；
> `full_concept_vlm` 消融已隨全量標註自動納入 `abl_filled`（`run_ablation.py` 偵測到 VLM parquet 就會加入 T3）；
> 人工標註缺口補上工具側 `scripts/eval_human_agreement.py`（盲標抽樣＋Cohen's κ＋人工標準答案下的 AUROC），
> 但**數字仍待真人標註**；K 表的不確定性補上 `scripts/eval_kansei_sensitivity.py`（T13）。
> 仍然缺人／缺 key 的是：真人盲標、價格資料、ENGINE 01／03 的重播、LLM 幻覺率。

**還沒關、而且會影響評分的**（詳見 §4，按優先序）：

| 優先 | 缺口 | 影響 | 建議 owner | 估時 |
|---|---|---|---|---|
| P0 | **沒有任何人工／LLM 分級標註**（PRD §9.3 的 NDCG@5 盲標＋Cohen's κ） | 所有排序品質數字都是 metadata 代理指標；評審問「這個 0.84 的標準答案是誰定的」時只能回答「資料集屬性」 | 兩位組員 + coordinator | 2–3 h |
| P0 | **價格欄位全為 null** | 評分項「完整可購買」；畫面無法顯示價格，預算硬條件永遠被放寬 | coordinator（找贊助商資料或明確標示合成） | 1 h（標示）／不定（真資料） |
| P0 | **斷網重播模式只做了 ENGINE 02 這一半**（PRD §8 必做） | `engine02/replay.py` 讓彩排過的請求可以離線逐字重播；ENGINE 01／03 與生圖分支還沒有對應機制，前端也還沒有重播開關 | coordinator / 前端 | 1–2 h |
| P1 | **M3 感性對照表沒有 PRD 承諾的「GPT 多次取樣＋分歧格子人工校正」** | K[n,d] 目前是文獻編碼版（比 GPT 可辯護），但沒有變異數 v[n,d]，也沒有人工校正紀錄 | E2 owner + 全組 1 小時標註 | 2 h |
| P1 | **`full_concept_vlm` / `full_concept_hybrid` 消融未跑** | 標註已完成（§3.13），但「用 VLM 分數排序會不會更好」還是空白 | E2 owner（GPU） | 1 h |
| P1 | **API 沒有把 §7 面板、概念圖最近商品接出去** | 前端要自己重算聚合值，容易算錯 | coordinator（3 個 endpoint） | 1 h |
| P1 | **`z_clip` 沒有套到 trend／penalty 項**（`ArmConfig.z_clip` 的註解說要套四項，`pipeline._terms` 只套了 dense 與 bm25） | 註解與程式不一致。實測（§3.1b）顯示它**不是**趨勢項代價大的主因（−0.275 → −0.254），但只要日後把趨勢項打開、或換成 BM25 更重尾的商品庫就會咬人 | coordinator（pipeline 兩行；包裝版與量測見 `engine02/trends.py::TrendClippedEngine02`） | 15 min |
| P2 | LLM 改寫的事實檢查沒有用真 LLM 實測 | 程式與單元測試都有，但沒有真實幻覺率數字 | E2 owner（需要 OpenAI key） | 1 h |
| P2 | `retrieval_text` 的「不得含否定詞」只是約定，程式沒檢查 | ENGINE 01 送進否定詞時會靜默污染 dense 查詢 | E2 owner | 15 min |
| P2 | 趨勢項與概念圖項的預設值 | 已量測（§3），但**依規則我不改預設**，等 coordinator 決定 | coordinator | 15 min |

---

## 1. 需求矩陣

狀態定義：**done** = 有程式、有測試或有實驗數據；**partial** = 有程式但缺驗證／缺 PRD 承諾的一部分；
**missing** = 沒有。「今晚」= 本次稽核新增。

### 1.1 PRD §6.3 ENGINE 02 模組 M3–M7

| # | 需求（PRD 原文） | 狀態 | 證據 | partial／missing 的影響 |
|---|---|---|---|---|
| A1 | **M3 感性對照表**：需求 × 設計要素權重 K[n,d] ∈ [−1,1]，GPT 填初值、人工校正 | **partial** | `engine02/resources/kansei_v1_literature.json`（15 要素 × 10 需求，50 個非零格）、`engine02/kansei.py`、`docs/research/kansei-evidence.md` | 改成**文獻編碼**而非 GPT 填值（更可辯護，且成對反義要素合併成一條軸避免重複計算）；但 PRD 的「5 次取樣取中位數、變異數大的格子交人工」沒做，所以沒有 v[n,d] 當 Bayes 先驗變異數。Demo 影響小，評分「技術方案」會被問「K 從哪來」→ 有文獻答案，但沒有人工校正紀錄。 |
| A2 | **M4 設計要素打分** c(i,d)：零樣本 concept bottleneck，可視描述子，庫內 z 標準化，離線預算 | **done**（CLIP 路徑）／**partial**（VLM 路徑） | `engine02/concepts.py`；T3（§3.3）、3.3b 420 件目視標註、3.3c VLM vs CLIP；隨機字詞對照組 | 反義詞成對＋DN＋適用性遮罩全部上線且有 AUROC。**缺口**：`full_concept_vlm` / `full_concept_hybrid` 兩個 arm 的排序消融還沒跑（§3.6 待辦），所以「材質光澤改用 VLM 會不會讓排序更好」未知。 |
| A3 | **M5 兩路檢索＋RRF(k=60)** → top-50 | **done** | `engine02/fusion.py`、`engine02/sparse.py`、T1（§3.1）；`n_candidates=50` 為預設 | 偏離 PRD：**沒有用 Chroma**，改 numpy 精確內積＋`rank_bm25`（method inventory §4 明確支持，≤10 萬件不需要向量 DB）。凸組合融合也一併量了。 |
| A4 | **M5 硬條件用 `where` 過濾**（`$in`、`$lte`） | **done** | `engine02/constraints.py`、`engine02/taxonomy.py`（L2→L1 階層放寬）；T2（§3.2） | 比 PRD 多做：放寬階梯會記錄、寫進理由、而且品類／性別／排除值永不放寬。預算條件因為沒有價格欄位一律被放寬（見 E5）。 |
| A5 | **M6 可加總 reranker**：`w_dense·sim + w_bm25·BM25 + w_comp·相容 + w_trend·趨勢 + Σβ_d·c(i,d) − 負例懲罰` | **partial → 今晚補齊** | `engine02/rerank.py`、`engine02/pipeline.py::_terms`；T1、T6、T10 | 五項裡 **trend 從第一版起就是死碼**：`Engine02.set_trends()` 存在，但整個 repo 沒有任何呼叫者，所以 `w_trend=0.2` 從未生效，過去所有數字都是「沒有趨勢項」的數字。今晚補 `engine02/trends.py` 與 T11 實驗（§3.1）。compat 只在有錨點時啟用（文獻要求），已接 OutfitTransformer。 |
| A6 | **M7 反事實檢查**：每項歸零後重排，掉出前 5 才算有效理由 | **done** | `engine02/rerank.py::counterfactual_ranks`；arm `full_reason_necessity`、`prd_original`；T4（§3.4） | PRD 原版保留成對照組；預設改成最小充分集合（覆蓋率 80.5%→100%、充分性 66%→100%）。 |
| A7 | **M7 GPT 轉白話**，prompt 明訂不得新增理由 | **partial** | `engine02/explain.py::verify_paraphrase` + 單元測試；`engine02/llm.py` | 程式層的事實檢查（數字與標籤必須出現在 facts 裡）完成，且失敗就退回模板。**沒有用真 LLM 跑過幻覺率**（只有本地 Qwen3-1.7B 的一次觀察）。 |
| A8 | **公式③：所有項加總剛好等於總分** | **done** | `tests/test_engine02.py::test_contributions_sum_to_score`、`tests/test_audit.py`（加了趨勢項後仍成立） | — |
| A9 | **需求 n 對商品 i 的貢獻 = p(n)·Σ_d K[n,d]·c(i,d)** | **done** | `Contribution.need_shares`、`RankedItem.need_contributions`；測試強制 `Σ need_shares == contribution` | — |
| A10 | **§6.6 趨勢關鍵字**：即時呼叫 Pinterest trends 端點、不存檔、當小權重加分、卡片顯示「趨勢」 | **missing → 今晚補上（Pinterest-free）** | `engine02/trends.py`、`scripts/build_trend_keywords.py`、`scripts/eval_trends.py`；卡片文案早就有（`explain.py` 的 `"trend": "符合近期趨勢關鍵字"`） | Pinterest 開發者規範禁止儲存 API 資訊，所以 repo 裡不放任何 Pinterest 內容：關鍵字改成①手動維護清單、②從商品庫的策展穿搭推導；即時 API 走 `from_live_fetch()`，回傳物件標記 `ephemeral` 而且**拒絕被存檔**。 |
| A11 | **§6.5 生成概念圖併入查詢**（文獻要求權重 ≤0.2） | **missing → 今晚量測** | `ArmConfig.concept_image_weight`、`FeedbackState.concept_image_embedding`、arm `full_concept_image` 都存在但**從未執行過**（§3.6 自己也這樣寫）；今晚 `scripts/eval_concept_image.py`（T12，§3.2） | 沒量過就上線的風險：BMVC 2025 顯示天真融合比純文字**更差**（62.7→61.0 mAP）。 |
| A12 | **§6.5 接回推薦**：每張概念圖找最接近的 3 件商品 | **missing → 今晚補上** | `engine02/panels.py::concept_image_neighbors` | 刻意**不走 reranker**，避免把生成圖說成「造成排序的原因」。還缺一個 API endpoint（見 E1）。 |
| A13 | **§6.7 感性缺口地圖**供給側 `Sup(n)` | **missing → 今晚補上（只有 E2 能算的那一半）** | `engine02/panels.py::need_supply` | 需求側 `D(場合,n) = Σ_sessions p(n)` 與 Gap 乘積屬 ENGINE 03／M13。 |

### 1.2 PRD §7 畫面與前後指標（ENGINE 02 要餵的部分）

| # | 畫面區塊 / 指標 | 狀態 | 證據 | 影響 |
|---|---|---|---|---|
| B1 | 商品卡：圖、**價格**、分數拆解條、一句理由 | **partial** | `RankedItem.{image_path,price,contributions,reasons,explanation}` | 圖／拆解／理由完整；**`price` 永遠是 null**（公開商品庫沒有價格）。今晚 `panels.provenance()` 會把這件事寫成畫面可顯示的 caveat。 |
| B2 | 意圖 JSON，本輪變動標色 | **partial** | `ConstraintReport.applied` / `.relaxed`；今晚 `RoundDiff.constraints_added/removed/excluded_added/required_added/needs_delta` | 意圖本身的 diff 是 ENGINE 01 的責任（PRD 明說只回傳變動量）；ENGINE 02 這側現在會告訴前端「這輪實際套用了什麼、放寬了什麼、和上一輪差在哪」。 |
| B3 | **兩輪並排＋標出改了什麼** | **missing → 今晚補上** | `engine02/panels.py::round_diff`（保留／新進／掉出、名次位移、分數差、被引用理由的增減、放寬差異） | 之前前端只能自己 diff 兩份 JSON，很容易把「因為回饋而改變」和「因為放寬而改變」混在一起。 |
| B4 | 前後三項規則指標：硬條件滿足率、違反回饋件數、被否決屬性出現件數 | **partial** | `RoundMetrics`（`hard_constraint_satisfaction`、`excluded_value_hits`、`feedback_violations`） | 三項都是用**商品屬性以規則算的**，不是排序分數 ✅。但口徑要確認：目前 `feedback_violations = excluded_value_hits + 出現在前 k 的被否決／被排除商品數`，PRD 寫的是「第二輪違反第一輪回饋的件數」。兩者在多輪時不完全一樣（例如第 3 輪違反第 1 輪回饋）。**需 coordinator 裁定口徑**，15 分鐘。 |
| B5 | **「你說的 vs 你沒說的」卡** | **missing → 今晚補上（E2 這側的資料）** | `engine02/panels.py::stated_vs_unstated`：四態槽位攤開＋「你沒說但真的在加分的需求」＋該需求是靠哪個設計要素加分 | RSA 機率本身是 ENGINE 01 M2；ENGINE 02 能提供的是「這個沒說出口的需求，在這張卡上加了 +0.61 分，主要靠肩線挺」——這正好是評審會追問的那一層。 |
| B6 | 帳本：每條回饋改了哪個需求多少 | **missing → 今晚補上（E2 這側的資料）** | `engine02/handshake.py::LedgerEntry`（op、原句、target、before、after、note）；範例見 `docs/contract/example_engine03_handshake.json` | 例如「太像上班族」→ `avoid_tryhard 0.30 → 0.53`、`trustworthy 0.55 → 0.36`，帶 PRD 公式④ 的註記。 |
| B7 | 設計師看板：感性缺口地圖、缺口款卡片 | **partial** | `panels.need_supply()`（供給側） | 需求側聚合與缺口款卡片屬 ENGINE 03／M13，本次不越界。 |
| B8 | 生成區：概念圖＋最接近 3 件＋評分 | **partial** | `panels.concept_image_neighbors()`（最接近 3 件）、T12（概念圖融合的代價） | 生圖本身屬生成分支 owner。 |

### 1.3 贊助商命題

| # | 要求 | 狀態 | 證據 |
|---|---|---|---|
| C1 | **可理解**：消費者看得懂的理由 | **done** | 模板句（`explain.py`）＋需求標籤（K 表）＋LLM 改寫但只能改寫已驗證事實；負權重要素一律寫成「避開〇〇」避免讀反 |
| C2 | **可解釋**：不是事後編故事 | **done** | 分數分解**就是**理由（加總等於總分，測試強制）；T4 的 comprehensiveness／sufficiency 都有隨機對照（100% vs 16%）；三種理由判定同時給，卡片上標明用了哪幾項 |
| C3 | **可變強**：回饋讓結果變好 | **done** | T5：4 輪成功率 1%→39–44%（p<0.001）；T7 從點選學偏好顯著勝過 PRD ±1 規則；T8 批評式檢索 NDCG@10 0.347→0.610 |
| C4 | **在約束下維持推薦品質** | **done** | T2（滿足率＋放寬照實記錄）、T6（γ=1 讓前 5 名換掉 19–26%，屬性相符度下降不顯著）、T9（DPP 近似重複 2.45%→0.35%，NDCG −0.005 n.s.）、T8（修掉放寬階梯吃掉 46% 顏色批評的 bug）。**這是本專案最紮實的一塊**，四個實驗都是「加了限制之後品質掉多少」的直接量測。 |
| C5 | 誠實揭露（哪些是資料集真值、哪些是模型判讀） | **done** | `attr_source`、`RankedItem.attribute_notes`、`provenance_filter`；今晚 `panels.provenance()` 把它整理成畫面可用的一塊 |

### 1.4 文獻回顧與方法盤點已採納的建議

| # | 建議（出處） | 狀態 | 證據／備註 |
|---|---|---|---|
| D1 | 硬條件用 filter 不進分數（Taobao MGDSPR、Vespa） | **done** | T2 |
| D2 | RRF 當免調參 baseline＋正規化凸組合（Bruch TOIS 2023） | **done** | T1 兩者都報 |
| D3 | 忠實理由：PN＋PS、最小充分集合（LENS、ERASER、CountER） | **done** | T4 |
| D4 | 批評式回饋、composed retrieval（CIReVL ICLR 2024） | **done** | T8；批評目標值改成永不放寬 |
| D5 | 多樣化（MMR／DPP NeurIPS 2018／xQuAD） | **done** | T9，三種都實作，DPP θ=0.9 為預設，被提前的卡片會標示 |
| D6 | 相容性只在有錨點時啟用、且要商品層級（OutfitTransformer） | **done** | §3.5c FITB 200 題：NPMI 25%（＝隨機）→ OT 54.5% |
| D7 | 材質光澤改用 VLM 標註（OVAD、MODA、WACV 2026） | **partial** | 標註完成（AUROC 0.71→0.90），**排序消融未跑** |
| D8 | 分類體系放寬（L2→L1） | **done** | §3.8，覆蓋率 95.3%／85.9% |
| D9 | 權重用非負 pairwise logistic 學，不要手調 | **done（結論是不採用）** | T10：只比「依查詢類型分流」多 +0.009；改成 ENGINE 01 回傳 `retrieval_text_normalized` |
| D10 | **LLM-as-judge 的防呆**：pooling、不同模型家族、人工抽驗 κ、paired test（Bing UMBRELA、Clarke & Dietz EVIA 2025） | **missing** | 目前**完全沒有**分級標註：所有排序數字的標準答案是資料集屬性（代理指標），目視標註是 LLM 標的、不是人標的。paired permutation／bootstrap 有做。這是最大的方法論缺口，見 §4 P0。 |
| D11 | 隨機描述子對照組（WaffleCLIP ICCV 2023） | **done** | T3、3.3b 都有 random 對照（0.33–0.70 vs 0.98） |
| D12 | 否定詞不進 CLIP 文字編碼器（NegBench CVPR 2025） | **partial** | 介面上約定 `retrieval_text` 不得含否定詞、否定進 `excluded_values`；**程式沒有檢查**，ENGINE 01 送進來也不會被擋 |
| D13 | Distribution Normalization＋只做一次 z-score | **done** | `concept_dn=True`、`norm_scope="pool"`；§3.10 再加 ±3 截斷 |
| D14 | applicability mask | **done** | `concept_applicability=True`；VLM 的 NA 比例（肩線 46%、領子 61%）給了實際依據 |
| D15 | `bm25s`（`weight_mask` 前置過濾）／`ranx`／`bge-m3 sparse` | **不採用** | `rank_bm25` + numpy 已足夠（17.7k–44k 件、每查詢 ~95 ms）；可接受的偏離，記錄在此 |
| D16 | HyDE／Query2doc 查詢擴寫 | **not done**（P1 加分項） | 需要強 LLM；與 ENGINE 01 的 `retrieval_text` 職責重疊 |
| D17 | xQuAD over needs（最有本題特色的多樣化） | **done（非預設）** | 實作在 `diversify.py`，預設是 DPP（有數據），xQuAD 當對照 |
| D18 | EBM／SpLiCE／Loom 式多目標打分 | **not done**（P2） | 標註太少會過擬合；不影響 demo |
| D19 | 圖文 cross-encoder reranker（Qwen3-VL-Reranker-2B） | **done（預設關）** | 用詞相同的查詢反而變差（0.840→0.797，p=0.001） |
| D20 | 模擬使用者要標明是模擬、引 ConvApparel 說明偏樂觀 | **partial** | 設計文件有標「模擬」；**簡報稿還沒寫**，且 T5 的模擬使用者是規則式而非 LLM（比 PRD §9.2 的計畫更保守，要說明） |

### 1.5 PRD §9.3 量化驗證指標中，ENGINE 02 要產出的那些

| 指標（PRD §9.3） | 狀態 | 證據 | 缺口 |
|---|---|---|---|
| **NDCG@5（消融）**：候選池盲標 0/1/2＋Cohen's κ | **partial** | T1（`ndcg5`／`ndcg10`，7 個 arm × 2 種用詞 × 2 個商品庫規模，配對置換＋bootstrap CI） | **標準答案不是盲標，是資料集屬性**（subcategory 3 級分級）。PRD 承諾的兩人盲標與 κ 沒做 → §4 P0 |
| **HitRate@5** | **partial** | T5 的 SR@t 就是「t 輪內推中隱藏目標的累積比例」（＝HitRate 的多輪版）；T12 另外報 `hit5` | 沒有單輪、跨 4 組對照（A 完整／B 無回饋／C 只用最新一句／D ChatGPT）的 HitRate@5；C 與 D 兩組需要 ENGINE 01／03 與 OpenAI key |
| **Div@5**：前 5 名涵蓋的設計要素類別（版型／色系） | **substituted → 今晚補上畫面用的版本** | T9 報的是 ILD（1−平均成對 cosine）、近似重複率（cosine>0.95）、α-NDCG@5；今晚 `panels.slate_diversity()` 依 PRD 定義用**商品屬性以規則**算 Div@k（涵蓋幾個品類／色系，和 §7 三項指標同一個哲學），已併進 `Engine02View.diversity` | 離線消融仍用 T9 的 ILD／近似重複率（研究上更嚴謹）；兩者並存，簡報要說清楚哪個是哪個 |
| **SR@t（t=1–4）** | **done** | T5（§3.5、§3.5b） | 對照組只有 4 種回饋開關，不是 PRD 的 A/B/C/D 四組系統 |
| **每輪 HitRate 變化＋收斂曲線（相似度用 FashionSigLIP 另一個模型量）** | **partial** | T5 逐輪 SR；encoder 比較用了 7 個模型 | 沒有「用另一個模型量相似度」的收斂曲線（PRD 要求排序與評分模型分離）；T12 的 `cos_to_concept` 是同一個模型，屬於循環，已標註 |
| **Comprehensiveness／Sufficiency（名次版）＋隨機對照** | **done** | T4（100% vs 隨機 16–20%） | — |
| **Cohen's κ（標註者間、LLM vs 人）** | **missing** | `engine02/eval/metrics.py::cohen_kappa` 已實作但**沒有任何標註資料可餵** | §4 P0 |
| **交換順序不一致率（LLM 評分兩種順序）** | **N/A** | 目前沒有用 LLM 當 judge，所以不存在這個問題 | 若補上 LLM judge（P0）就必須一起做 |
| **ECE／Brier（需求機率校準，加分）** | **N/A for E2** | `docs/research/classify.md` 有屬性分類器的 ECE | 需求機率是 ENGINE 01／03 的輸出，校準要他們量 |

### 1.6 交付物

| # | 交付物 | 狀態 | 證據 | 缺口 |
|---|---|---|---|---|
| E1 | 可跑的原型（FastAPI） | **partial** | `engine02/api.py`：`POST /rank`、`/rank/plain`、`GET /vocabulary`、`/kansei`、`/items`、`/images`、`/arms`、`/health`、`POST /complete-look` | 今晚新增的三塊沒有 endpoint：`GET /view`（§7 面板）、`POST /concept-image/nearest`、`GET /needs/supply`；趨勢關鍵字也還沒在 startup 掛上。整合 hook 見 §2.5。 |
| E2 | 英文 README | **done** | `engine02/README.md`（pipeline、quick start、endpoints、key results、limitations 都有） | 尚未提到今晚新增的 `trends` / `panels` / `handshake` / `reproduce`（依規則我不改既有檔案，請 coordinator 補三行，§2.5 有現成文字）。 |
| E3 | 可重現 | **partial → 今晚補上** | `scripts/reproduce.py`（16 個 stage、固定 seed、manifest、`--check-claims`） | `--check-claims`：**29 個聲明裡 26 個有腳本，3 個沒有**（§5）。 |
| E4 | **斷網重播模式**（PRD §8 必做） | **missing → 今晚補上 ENGINE 02 這一半** | `engine02/replay.py`（`ReplayStore` 包住 `Engine02.run` 或 `Engine02Service.rank`，record／replay／auto 三種模式，key 是請求內容的 SHA-256 但忽略 `session_id`）＋5 個測試 | ENGINE 02 本身斷網本來就可跑（模型與 embedding 在本機、LLM 改寫失敗會退回模板），現在再加上「彩排過的請求可以逐字重播」，連 LLM 改寫過的句子也一起重播。**還缺**：ENGINE 01／03 與生圖分支的對應機制、以及前端的重播開關。Owner：coordinator／前端，1–2 h。 |
| E5 | 完整可購買（價格） | **missing** | `price` 一律 null；`docs/research/catalog-options.md` 已查證公開商品庫沒有價格 | 評分項直接相關。最低成本做法：明確標示「商品庫無價格」（`panels.provenance().caveats` 已經會產生這句話）＋畫面顯示。 |
| F1 | 介面規格檔 | **done** | `docs/contract/`：request／response JSON Schema、第 1／2 輪範例；今晚新增 `engine03_feedback.schema.json`、`example_engine03_handshake.json`、`example_view_round2.json` | — |
| F2 | 給 ENGINE 01 的需求（詞彙正規化、`retrieval_text`） | **done** | `GET /vocabulary`（含 taxonomy 封閉詞彙表）、`retrieval_text_normalized` 路由 | 見 D12（否定詞沒有程式檢查） |
| F3 | 給 ENGINE 03 的握手實作 | **missing → 今晚補上** | `engine02/handshake.py`＋17 個測試＋JSON 往返範例 | — |

---

## 2. 今晚關掉的缺口（全部是新檔案）

| 檔案 | 內容 | 行為變更？ |
|---|---|---|
| `engine02/trends.py` | 趨勢關鍵字來源（手動清單／策展穿搭 log-odds lift／穿搭夥伴 PMI／即時 API 且拒絕存檔）、`attach_trends()` 整合 hook、`trend_coverage()` 健檢、**`trend_badges()`（把趨勢做成純展示標籤，不進排序）**、`TrendClippedEngine02`（把 `z_clip` 也套到 trend／penalty 的包裝，用來量測 §3.1 的 bug） | **沒有**。不呼叫 `attach_trends()` 的話趨勢項仍然不存在，所有既有數字不受影響；`trend_badges()` 是唯讀的。 |
| `engine02/resources/trend_keywords_v0.json` | 手動維護的 20 個服飾趨勢詞＋出處註記（明確寫「非 Pinterest 資料」） | 新資源檔，預設不載入 |
| `engine02/panels.py` | PRD §7 面板的**回傳擴充模型**：`StatedVsUnstated`、`NeedPanel`、`SlateDiversity`（PRD §9.3 的 Div@k，用商品屬性以規則算）、`RoundDiff`、`Provenance`、`Engine02View`；加上 `need_supply()`（M13 供給側）與 `concept_image_neighbors()`（§6.5 接回推薦）。卡片文字沿用設計文件 §4.3 的方向規則：K[n,d]<0 一律寫「避開〇〇」，貢獻為負則寫「有〇〇（扣分）」，不會被讀反 | **沒有**。純粹是既有回傳的投影，不重新排序、不重新計分。 |
| `engine02/handshake.py` | ENGINE 03 的固定操作集（`FeedbackRound`，可直接當 structured-output schema）、`apply_round()`（累積規則）、`LedgerEntry`（帳本列）、PRD 公式④ `update_needs()`、選擇概似 `need_likelihood()` | **沒有**。ENGINE 02 的行為不變，只是把「下一輪 request 要怎麼組」寫成程式。 |
| `scripts/build_trend_keywords.py` | 從商品庫推導趨勢關鍵字並存檔（資料，不進 git） | — |
| `scripts/eval_trends.py` | **T11**：趨勢項對排序的代價（NDCG@5／@10、前 5 名換掉比例、趨勢被引用比例、趨勢對齊度），三種關鍵字來源含**隨機字詞對照組**，配對置換檢定＋bootstrap CI | — |
| `scripts/eval_concept_image.py` | **T12**：概念圖分支的替身實驗（保留原圖當「生成圖」，三種概念來源 oracle／neighbour／mismatched × 權重 0／0.1／0.2／0.5） | — |
| `scripts/reproduce.py` | 整條離線評估鏈的單一入口（固定 seed、manifest、跳過缺輸入的 stage）＋`--check-claims` 稽核設計文件的每個數字 | — |
| `scripts/export_handshake_example.py` | 產生 `docs/contract/engine03_feedback.schema.json`、`example_engine03_handshake.json`、`example_view_round2.json` | — |
| `engine02/replay.py` | PRD §8 斷網重播（ENGINE 02 這一半）：`ReplayStore(path, mode="off"/"record"/"replay"/"auto")`，`wrap(fn)` 是 `Engine02.run` / `Engine02Service.rank` 的 drop-in；`mode="off"` 直接回傳原函式，排序路徑上完全沒有它 | **沒有** |
| `tests/test_audit.py` | 31 個測試，HashEncoder、本機可跑。重點：趨勢項在未掛載前必須不存在、掛載後加總仍等於總分、即時清單不可存檔、趨勢標籤是唯讀的、`z_clip` 包裝真的把 z 夾在 ±3；四態槽位、`soft_only`（沒被當硬條件的槽位）、需求面板一致性、卡片方向詞不會讀反、Div@k 是規則算的、兩輪 diff、provenance caveat、面板可讀 `Engine02Service` 的回傳；離線重播逐字還原（含 `ServiceResponse` 欄位）、嚴格模式 miss 會丟例外、key 忽略 `session_id` 但不忽略 round／arm；`exclude` 永久且會從正向條件移除、`adjust` 累積與上限、critique 只有當輪有效、`choice_history` 累積、公式④ 正規化、選擇概似對稱性、JSON 往返後排序完全相同、操作集是封閉集合 | — |

### 2.1 趨勢關鍵字：為什麼不碰 Pinterest

Pinterest 開發者規範（PRD [108]）禁止**儲存**從 API 取得的資訊、禁止用於 AI/ML、禁止從 Pin 創作新內容，
顯示時必須連回原 Pin。因此：

- repo 裡**不放任何 Pinterest 內容**；離線評估若重播一份存下來的 Pinterest 清單，正好就是被禁止的「儲存」。
- 預設來源是①`engine02/resources/trend_keywords_v0.json`（手動維護）、②從商品庫的策展穿搭推導。
- 若真要接 Pinterest 的 `GET /v5/trends/keywords/{region}/top/{trend_type}`（只回關鍵字、不回圖），
  走 `trends.from_live_fetch(fetch_fn)`：回傳物件標記 `ephemeral=True`，`save()` 會直接
  `raise PermissionError`。**規範被寫成程式，不是寫成註解。**
- 主辦方已有內部趨勢平台，且明確排除趨勢預測系統 → 這一項永遠只當小權重的平手打破者。

兩個商品庫推導來源（兩者都**不是趨勢預測**，是「造型師在這份資料裡常放進穿搭的詞」）：

- `curated_lift`：詞在「有被放進策展穿搭的商品」裡相對整個商品庫的 log-odds lift，
  統計用 Monroe, Colaresi & Quinn（*Political Analysis* 2008）的 informative Dirichlet prior 版本，
  避免低頻詞排前面。**已知混淆**：在 `kagl_polyvore` 上，策展組 14,289 件全部來自 Polyvore、
  非策展組 3,494 件全部來自 KAGL，所以這個 lift 同時混了「策展 vs 零售」與「Polyvore vs KAGL 用語」兩件事。
  簡報上要照實說：它是**贊助商內部趨勢訊號的替身**，不是 2026 年的流行證據。
- `outfit_partner`：和錨點品類同一套穿搭的單品用詞（PMI lift），情境相依（「現在大家用什麼配西裝外套」）。
  **實測結果不堪用**：在 `polyvore_big` 上跑出來的前 20 名是 `frye / roger vivier / amanda / pamela / leigh`
  這類**品牌與人名**，因為 Polyvore 標題以品牌開頭。要用這個來源必須先加品牌黑名單（可從 `title` 的第一個
  token 統計出來），大約 30 分鐘。`curated_lift` 沒有這個問題（它比的是相對頻率，品牌被基準率抵銷掉一部分），
  但仍有「Polyvore vs KAGL 用語」的混淆。

### 2.2 概念圖分支：替身實驗的設計

生成分支還沒有圖，所以用**保留法**：目標商品自己的圖片 embedding 當「生成的概念圖」，
同時把目標商品放進 `excluded_item_ids`（概念圖不可能靠「回傳它自己」得分）。三種概念來源：

- `oracle`（目標自己的圖）＝完美生成器的**上界**；
- `neighbour`（和目標最像的另一件）＝方向抓對的現實生成器；
- `mismatched`（隨機另一件）＝**對照組**：如果 oracle 和 mismatched 把排序推動同樣多，那這個權重加的是雜訊不是資訊。

必須寫在簡報上的限制：商品庫是白底商品照，真的生成圖是模特兒／生活照，而 FashionCLIP 系模型偏好白底
（模型卡，PRD [112]）。所以 `oracle` 是**上界**：負結果可以下定論，正結果不能。

### 2.3 ENGINE 03 握手：七條容易搞錯的規則

`engine02/handshake.py` 的 docstring 是規格本體，摘要：

1. **不要傳權重數字**：`adjust(要素, ±1)` 只傳步數，ENGINE 02 乘 `step_size=0.25`、對**累積值**夾在 ±3。
2. **`exclude` 是永久的**：進 `constraints.excluded_values`（放寬階梯永不碰），同時從正向槽位移除該值，
   查詢文字才會停止要求它。
3. **批評的目標值是 `required_value`**，不是可放寬的槽位值（否則放寬階梯會吃掉 46% 的顏色批評）。
4. **`reference_item_id` / `critique` 只有當輪有效**，下一輪由 `apply_round` 清掉；效果以 `required_value` 留存。
5. **點選累積成 history，不是累積成權重**：Δβ 由 `Engine02Service` 擬合（Bayes 成對 logistic＋κ=1 縮減）。
6. **選擇概似要用回傳的 `design_scores`**（`need_likelihood()`），不要自己重算 c(i,d)。
7. **p(n) 是 ENGINE 01／03 的**：`feeling` 必須帶 `need_log_likelihood`（公式④）或 `needs_override`，
   否則 `apply_round` 會把這個操作放進 `rejected_ops` 而**不是**靜默忽略。

`FeedbackRound.model_json_schema()` 就是 M8 的 structured-output schema，已匯出成
`docs/contract/engine03_feedback.schema.json`；`docs/contract/example_engine03_handshake.json`
是「太像上班族，不要黑色＋點選第 3 件」的真實往返（round 1 request → 卡片 → 4 個操作 → 帳本 → round 2 request →
round 2 卡片與指標），可以直接拿去和另一位引擎 owner 的實作對帳。

### 2.4 測試

```
E:/mchackathon2026/.venv/Scripts/python.exe -m pytest -q tests/test_audit.py   # 31 passed
```
伺服器（cfda4）上同樣全數通過。沒有修改既有檔案，所以既有的 138 項測試不受影響
（`git status` 只有新增檔案，沒有任何 modified）。

### 2.5 給 coordinator 的整合 hook（三行以內）

```python
# 趨勢：建議只做展示標籤（§3.1 顯示進排序的代價太大），不呼叫 attach_trends()
from .trends import load_trends, trend_badges
badges = trend_badges(engine, resp, load_trends().keywords(30))   # 唯讀，不影響分數與名次

# 若 coordinator 仍決定讓趨勢進排序：務必先修 z_clip（§3.1），再把權重調小
from .trends import attach_trends, TrendClippedEngine02
attach_trends(engine, load_trends())          # 或 load_trends("data/catalog/<cat>/trend_keywords_curated_lift.json")

# 斷網重播（PRD §8）：彩排時錄，現場離線重播
from .replay import ReplayStore
store = ReplayStore("artifacts/replay/demo", mode=os.environ.get("ENGINE02_REPLAY", "off"))
service.rank = store.wrap(service.rank)        # mode="record" 彩排 →「auto」現場最保險
# print(store.manifest()) 會列出彩排過哪些請求

# engine02/api.py，新增三個端點
from .panels import build_view, concept_image_neighbors, need_supply, view_labels
@app.post("/view")   # body: {request, response, prev_request?, prev_response?} → Engine02View
@app.post("/concept-image/nearest")   # body: {embedding: [...], k: 3}
@app.get("/needs/supply")             # query: threshold=0.5 → Sup(n)
```

README 可以加的三行（英文）：

```
| `engine02/trends.py`    | trend-keyword term for the reranker, derived from the catalog (no Pinterest data stored) |
| `engine02/panels.py`    | response extension for the PRD screens: said-vs-unsaid, per-need panel, round diff, provenance |
| `engine02/handshake.py` | reference implementation of one ENGINE 03 feedback round (ops → next request + ledger) |
```

---

## 3. 新實驗結果

設定：cfda4、CPU（`OMP_NUM_THREADS=8`，刻意不碰 GPU）、Marqo-FashionSigLIP、
基礎 arm `full_zclip3`（服務預設）、seed 0、100 句查詢／150 個目標、配對置換檢定 10,000 次＋bootstrap 95% CI。
原始檔：`reports/agents/audit/`（`out/trends_*`、`out/trends_clip_*`、`out/concept_image_*`、
`out/trend_keywords_*.json`、`logs/`、以及重跑用的 `run_all.sh` / `run_clip.sh`；raw 檔不進 git）。
重跑：`python scripts/reproduce.py --stage audit --catalog data/catalog/kagl_polyvore --encoder marqo-fashionSigLIP`。

### 3.1 T11 趨勢關鍵字：代價很大，而且幾乎和隨機字詞一樣

`eval_trends.py`。同一批查詢、同一條 pipeline，只改 `w_trend`。標準答案是屬性分級（同 T1），
**趨勢詞不在標準答案裡，所以 NDCG 的變化只會是代價、不會是收益**；另外報「趨勢對齊度」
（前 5 名的趨勢 BM25 z 平均）確認這個項真的有買到趨勢。

**KAGL 44k（服務用商品庫）**：

| 關鍵字來源 | w_trend | NDCG@5 | Δ vs 0 | p | 前 5 名換掉 | 趨勢被引用為理由 | 趨勢對齊 z |
|---|---|---|---|---|---|---|---|
| 手動清單 | 0 | 0.808 | — | — | 0% | 0% | 0.23 |
| 手動清單 | 0.1 | 0.577 | **−0.232** | 1e-4 | 33% | 17% | 2.11 |
| 手動清單 | **0.2（arm 預設值）** | 0.542 | **−0.266** | 1e-4 | 38% | 24% | 2.43 |
| 手動清單 | 0.5 | 0.492 | −0.316 | 1e-4 | 44% | 47% | 2.81 |
| **隨機字詞（對照組）** | 0.2 | 0.507 | −0.301 | 1e-4 | 60% | 23% | 2.10 |

**合併商品庫 kagl_polyvore 17.8k**（另外有 `curated_lift` 來源）：

| 關鍵字來源 | w_trend | NDCG@5 | Δ vs 0 | p | 前 5 名換掉 |
|---|---|---|---|---|---|
| 手動清單 | 0.2 | 0.523 | −0.275 | 1e-4 | 35% |
| curated_lift（商品庫推導） | 0.2 | 0.415 | −0.383 | 1e-4 | 58% |
| **隨機字詞（對照組）** | 0.2 | 0.270 | −0.528 | 1e-4 | 86% |
| （w_trend=0 三者相同） | 0 | 0.797 | — | — | 0% |

**關鍵字覆蓋率**（kagl_polyvore）：手動清單 20 個詞有 19 個在商品庫詞彙裡，但只有 **10.0%** 的商品
BM25 分數 > 0；`curated_lift` 30 個詞覆蓋 53.1%；隨機字詞 48.3%。30.3% 的查詢本身就含有趨勢詞
（也就是說趨勢項有三成的時間在和 BM25 項講同一件事，這正是方法盤點 §11 M6-2 警告的共線性）。

### 3.1b 先懷疑的原因（z 沒有截斷）不是主因 —— 但那仍然是個真的 bug

趨勢項用的是商品池層級的 BM25 z 分數，分布極度偏斜（大部分商品 0 分，命中的商品 z 可以到 +8），
這正是 §3.10 當初把 dense／BM25 截斷在 ±3 的原因。稽核時發現：
`ArmConfig.z_clip` 的註解寫「clip normalised **dense/bm25/trend/penalty** terms」，但
`pipeline.Engine02._terms` **只把 `clip=arm.z_clip` 傳給 dense 和 bm25**。所以在服務預設 `full_zclip3` 裡，
趨勢項會是加總中唯一沒被截斷的重尾 z。

於是用 `engine02.trends.TrendClippedEngine02`（包裝，沒動 pipeline）把 `z_clip=3` 也套到趨勢項重測
（kagl_polyvore 17.8k，同一批 100 句查詢）：

| 商品庫 | 關鍵字來源 | w_trend | NDCG@5（截斷後） | Δ vs 0 | 未截斷時的 Δ |
|---|---|---|---|---|---|
| kagl_polyvore 17.8k | 手動清單 | 0.05 | 0.589 | −0.209 | —（未測） |
| kagl_polyvore | 手動清單 | 0.1 | 0.572 | −0.225 | −0.245 |
| kagl_polyvore | 手動清單 | 0.2 | 0.544 | −0.254 | −0.275 |
| kagl_polyvore | curated_lift | 0.2 | 0.415 | −0.383 | −0.383 |
| kagl_polyvore | 隨機字詞 | 0.2 | 0.279 | −0.519 | −0.528 |
| **KAGL 44k** | 手動清單 | **0.05** | 0.646 | **−0.163**（最好的一格） | —（未測） |
| KAGL 44k | 手動清單 | 0.1 | 0.627 | −0.182 | −0.232 |
| KAGL 44k | 手動清單 | 0.2 | 0.598 | −0.211 | −0.266 |
| KAGL 44k | 隨機字詞 | 0.2 | 0.525 | −0.283 | −0.301 |

（所有 p 值都是 1e-4。）截斷在 44k 上救回一部分（−0.266 → −0.211），在 17.8k 上幾乎沒差
（−0.275 → −0.254），而**所有格子都還是顯著變差**，最好的一格（44k、手動清單、w=0.05、有截斷）
仍然是 −0.163。所以主因不是離群值，而是這個項的本質：
在過濾後的商品池裡，前 50 名候選的其他項差距本來就很小（同品類、同性別、屬性相近），
而趨勢項近似一個「有沒有命中任一關鍵字」的二元加分（只有約 10% 的商品有分），
所以即使 w=0.05 也足以把前 5 名洗掉三成。**這不是調權重能解決的問題。**

`z_clip` 的不一致仍然要修（兩行，見 §4 P1）：它是「註解說一套、程式做一套」，
而且只要有人日後把趨勢項打開、或商品庫換成 BM25 更重尾的資料，它就會咬人。

### 3.1c 結論與建議：趨勢當標籤，不要當分數

三個來源、四個權重、兩個商品庫、截斷與不截斷共 28 組設定，**沒有任何一組讓 NDCG@5 不掉**
（最好的一格仍是 −0.163，p=1e-4），
而且手動清單和隨機字詞的差距（44k：−0.266 vs −0.301）遠小於兩者各自的代價。
以「在約束下維持推薦品質」這個命題來看，把趨勢放進排序就是在賣掉品質換一個沒有標準答案的訊號。

**建議（coordinator 決定）**：

1. **預設不要呼叫 `attach_trends()`**。不呼叫的話趨勢項就不存在，所有既有數字與結論都不變，
   也不需要改任何 arm 或權重。
2. **畫面上的「趨勢」標籤改用 `trends.trend_badges()`**：從商品文字比對趨勢關鍵字，
   回傳 `{item_id: {matched, z, affects_score: False}}`。PRD §6.6 要的畫面元素有了，排序不動，代價 0，
   而且卡片上可以誠實寫「這件商品含有近期趨勢詞：oversized」，而不是假裝趨勢造成了排名。
3. 如果贊助商堅持要趨勢進排序，**先修 `z_clip`（§3.1b）、權重 ≤0.05、而且只在「查詢很模糊」時開**
   （和概念圖同樣的情境判斷），並且要在簡報上報這裡的代價數字，不要只報「我們有趨勢訊號」。
4. Pinterest 只能即時呼叫、不能存檔（§2.1）；上線版應該直接接聚陽內部趨勢平台。

### 3.2 T12 生成概念圖分支：有真的訊號，而且有對照組證明不是雜訊

`eval_concept_image.py`。使用者的話刻意**模糊**（`"{性別} {品類}"`，硬條件只有品類＋性別，
等於 T5 的第 1 輪設定，也就是「都不是我要的 → 去生成概念圖」的那一刻）；概念圖用保留的商品圖替身，
目標商品本身放進 `excluded_item_ids`。

**合併商品庫 kagl_polyvore 17.8k，150 個目標**：

| 概念圖來源 | 權重 | NDCG@5 | Δ vs 0 | p | NDCG@10 | HitRate@5 |
|---|---|---|---|---|---|---|
| — | 0（今日預設） | 0.132 | — | — | 0.130 | 0.227 |
| **oracle**（目標自己的圖＝完美生成器上界） | 0.1 | 0.255 | **+0.123** | 1e-4 | 0.262 | 0.420 |
| **oracle** | **0.2**（`full_concept_image`） | 0.344 | **+0.212** | 1e-4 | 0.348 | 0.567 |
| **oracle** | 0.5 | 0.385 | +0.253 | 1e-4 | 0.388 | 0.620 |
| **neighbour**（最像目標的另一件＝現實生成器） | 0.1 | 0.255 | +0.123 | 1e-4 | 0.248 | 0.413 |
| **neighbour** | 0.2 | 0.333 | **+0.201** | 1e-4 | 0.328 | 0.533 |
| **neighbour** | 0.5 | 0.368 | +0.236 | 1e-4 | 0.369 | 0.593 |
| **mismatched**（隨機另一件＝對照組） | 0.1 | 0.119 | −0.013 | 0.17 | 0.123 | 0.213 |
| **mismatched** | 0.2 | 0.108 | **−0.024** | **0.040** | 0.119 | 0.160 |
| **mismatched** | 0.5 | 0.115 | −0.017 | 0.29 | 0.117 | 0.167 |

**KAGL 44k（服務用商品庫），150 個目標**（對照組在大商品庫上更乾淨）：

| 概念圖來源 | 權重 | NDCG@5 | Δ vs 0 | p |
|---|---|---|---|---|
| — | 0 | 0.078 | — | — |
| **oracle** | 0.1 | 0.193 | +0.115 | 1e-4 |
| **oracle** | **0.2** | 0.325 | **+0.247** | 1e-4 |
| **neighbour** | 0.1 | 0.170 | +0.092 | 1e-4 |
| **neighbour** | **0.2** | 0.278 | **+0.200** | 1e-4 |
| **mismatched（對照組）** | 0.1 | 0.071 | −0.007 | 0.36 |
| **mismatched（對照組）** | 0.2 | 0.074 | −0.004 | **0.71（無效果）** |

解讀：

- **對照組是關鍵**：隨機概念圖在同一個權重下沒有幫助（44k：−0.004，p=0.71；17.8k：−0.024，p=0.04），
  所以 oracle／neighbour 的 +0.20 是**資訊**，不是「擾動查詢就會變好」的假象。
- **realistic ≈ oracle**（0.333 vs 0.344）：生成器只要方向抓對（最近鄰等級），效果就幾乎追平完美生成器。
  這對生成分支是好消息。
- **和文獻不衝突**：BMVC 2025 的負面結果是在「文字查詢本來就很強」（62.7 mAP）的情況下做 0.5/0.5 天真融合；
  這裡的前提相反——使用者講不出話，純文字只有 0.132。這正好是 PRD 生成分支被觸發的條件。
- **必須寫在簡報上的限制**：商品庫是白底商品照，真的生成圖是模特兒／生活照，FashionCLIP 系模型偏好白底
  （模型卡，PRD [112]）。所以 oracle 是**上界**：這個正結果不能直接宣稱「真的生成圖也會 +0.20」。
  另外 `cos_to_concept` 是用排序同一個模型量的，屬循環指標，只當 sanity check。

---

## 4. 仍然缺的東西，按優先序

| 優先 | 缺口 | 為什麼重要 | 建議 owner | 估時 |
|---|---|---|---|---|
| **P0** | **沒有分級標註與 κ**（PRD §9.3：每句測試句把各方法前 10 名併成候選池、兩位隊員盲標 0/1/2、回報 Cohen's κ） | 現在所有 NDCG 的標準答案都是資料集屬性（subcategory／color／gender／occasion），量的是「有沒有找到同屬性的商品」，**量不到隱性需求**。評審問「誰說這是對的答案」時，只有代理指標可答。做 40 句 × top-10 併集 ≈ 300 筆，兩人盲標約 2 小時就能補上一個真正的品質指標，而且可以直接拿 `--check-claims` 缺的那一格。 | 兩位組員 + coordinator 出 pooling 腳本 | 2–3 h |
| **P0** | **價格全為 null** | 評分項「完整可購買」；畫面沒有價格、預算條件永遠被放寬 | coordinator | 標示 1 h／換資料不定 |
| **P0** | **斷網重播模式只剩另外兩個引擎與前端**（PRD §8 必做） | ENGINE 02 這一半今晚做完（`engine02/replay.py`：彩排時 `mode="record"`，現場 `mode="replay"`，同一個請求逐字重播，連 LLM 改寫過的句子都一致；`mode="auto"` 是最保險的現場設定）。剩下：ENGINE 01 的意圖抽取、ENGINE 03 的回饋解析、生圖分支都要有對應的錄放，前端要有開關 | coordinator／前端 | 1–2 h |
| **P1** | **M3 K 表沒有 PRD 承諾的人工校正與變異數** | 「感性對照表」是本專案的核心敘事；目前是文獻編碼（可辯護），但缺 v[n,d]（本來要當 Bayes 先驗變異數）與人工校正紀錄 | E2 owner + 全組 1 小時 SD 評分 | 2 h |
| **P1** | **`full_concept_vlm` / `full_concept_hybrid` 消融未跑** | VLM 標註已經花掉一晚 GPU（17,783 件），但「用它排序會不會更好」還是空白；材質光澤是 PRD 的核心要素之一 | E2 owner（GPU，1 小時） | 1 h |
| **P1** | **API 沒有接出 §7 面板／概念圖最近商品／需求供給** | 前端得自己重算聚合，容易把 need_shares 加錯；今晚的程式已經寫好，只差 3 個 endpoint | coordinator | 1 h |
| **P1** | **`feedback_violations` 口徑要裁定** | PRD 說「第二輪違反第一輪回饋的件數」，程式算的是「被排除值 + 被否決商品出現次數」（跨所有輪累積）。兩者在第 3 輪之後會不一樣，畫面上是對評審報的三個指標之一 | coordinator | 15 min |
| **P1** | **`z_clip` 沒有套到 trend／penalty**（註解與程式不一致） | §3.1b 顯示它不是趨勢代價的主因（−0.275 → −0.254），但這是「文件說一套、程式做一套」，而且換商品庫或日後打開趨勢項就會咬人。修法：`pipeline._terms` 裡那兩個 `Term(...)` 補上 `clip=arm.z_clip`（`engine02/trends.py::TrendClippedEngine02` 的 docstring 有現成的兩行） | coordinator | 15 min |
| **P2** | **概念圖權重要不要改成預設 0.2** | §3.2 證據足夠，而且改了對一般查詢是 no-op（沒有 `concept_image_embedding` 就不融合）；但依規則我不動預設 | coordinator | 5 min |
| **P2** | LLM 改寫沒有真 LLM 幻覺率 | 程式檢查與單元測試都有；缺一個「100 張卡片裡有幾張被退回模板」的數字 | E2 owner（OpenAI key） | 1 h |
| **P2** | `retrieval_text` 否定詞沒有程式檢查 | NegBench 顯示 CLIP 對否定接近隨機；介面只有文字約定 | E2 owner（15 分鐘：在 `Engine02Request` 加 validator 或在 pipeline 記一個 warning 欄位） | 15 min |
| **P2** | 模擬使用者是規則式、不是 LLM（PRD §9.2 原計畫用 Claude 扮演） | 比計畫保守，結論更可信，但簡報要說清楚差異並引 ConvApparel（所有模擬器與真人都有顯著落差） | 簡報 owner | 30 min |
| **P3** | HyDE／query2doc、EBM、SpLiCE、`bm25s`／`ranx` | 方法盤點列為 P1–P2 的加分項，不影響 demo | — | — |
| **P3** | 真人小樣本（PRD §9.1 第三層：5–10 人 SUS、解釋品質 Likert） | PRD 的 ⑦⑧ 指標；黑客松當天才可能做 | 全組 | 當天 |

---

## 5. 重現性稽核

`python scripts/reproduce.py --check-claims` 會印出 `docs/engine02-design.md` 每個數字對應的 stage。
結果：**30 個聲明裡 27 個有腳本可重現**。沒有腳本的三個：

| 聲明 | 為什麼沒有腳本 | 建議 |
|---|---|---|
| §3.3b 的**盲標標籤本身**（`data/labels/labels_part_*.csv`、`visual_label_tasks.csv`） | 抽樣與 LLM 標註是一次性手動流程；`scripts/eval_visual_labels.py` 只讀標籤、不產生標籤 | 補一支 `scripts/build_visual_label_tasks.py`（抽樣邏輯：依反義詞分數高／中／低三層各 20 件，seed 固定）＋標註 prompt 存檔。30 分鐘，而且是 P0 標註工作的前置。 |
| §0／§3.3 感性對照表 v1（32 篇文獻、50 個非零格、強證據 3 格） | 文獻編碼是人工的 | `docs/research/kansei-evidence.md` 已記錄來源；建議在 JSON 裡為每格加 `evidence_ids`，讓「哪一格出自哪篇」可機器驗證。 |
| §0 LLM 改寫的事實檢查觀察（本地 Qwen3-1.7B 把「盛夏偏熱」講反） | 一次性觀察，沒有存下 prompt／輸出 | 併入 P2 的「真 LLM 幻覺率」實驗，順手把 case 存成 fixture。 |

另外兩個 stage 在自動鏈之外（參數太專案特定）：`scripts/prepare_catalog.py` / `merge_catalogs.py`（商品庫建置）、
`scripts/build_taxonomy_v1.py`（分類體系與覆蓋率報告）。兩者都列在 `--check-claims` 的輸出裡，不是漏掉。

固定 seed 的做法：`reproduce.py` 對每個 stage 帶 `--seed 0`（腳本支援時）、設 `PYTHONHASHSEED=0`、
把 catalog 與 encoder 寫在命令列，並把 git commit、命令、回傳碼、耗時、輸出檔寫進
`<out-root>/reproduce_manifest.json`。缺輸入的 stage（沒 GPU、沒 VLM 標註、沒盲標）會**標記跳過並附原因**，
不會讓整條鏈失敗。

---

## 6. 我量了但沒有改的預設（留給 coordinator）

依規則，**不靜默改動已被量測的預設（arm、權重、門檻）**。以下是我量到的事實與建議，改與不改請 coordinator 決定：

| 預設 | 現值 | 我量到的 | 建議（coordinator 決定） |
|---|---|---|---|
| `w_trend` | 0.2（但趨勢項從未被餵，實際等於 0） | §3.1／§3.1b：0.05–0.5 全部 −0.21～−0.38 NDCG@5（p≈1e-4），和隨機字詞差距很小 | **不要呼叫 `attach_trends()`**，改用 `trend_badges()` 做展示標籤（§3.1c）。`w_trend` 的值本身可以不動。 |
| `use_trend` | True | 只有呼叫 `attach_trends()` 才生效 | 不上趨勢項就不要呼叫 hook，**不必改 arm**；既有數字不受影響 |
| `z_clip` 是否套到 trend／penalty | 只套 dense／bm25（與註解不符） | §3.1b | 只要趨勢項會被啟用，就**一定要先修**；penalty 不修影響也很小 |
| `concept_image_weight` | 0（`full_concept_image` arm 是 0.2） | §3.2：oracle +0.247、neighbour +0.200、**mismatched 對照組 −0.004（p=0.71）**（44k） | **建議把預設 arm 改成 0.2**。這是安全的：`pipeline.query_embedding` 只有在 `concept_image_weight > 0` **且** `feedback.concept_image_embedding` 有值時才融合，所以沒有生成圖的一般查詢**完全不受影響**，既有所有數字都不會變。0.5 在替身實驗裡更好，但替身是白底商品照的上界，且 BMVC 2025 對天真融合的警告就是針對過高權重，所以停在文獻建議的 ≤0.2。 |
