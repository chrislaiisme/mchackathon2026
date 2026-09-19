# 製造商後台分析控制台｜可執行規格（THREAD / STUDIO 後台）

> 角色：本文件是**規格**，不是提案。每一個面板都必須指名 `檔案:函式` 或 `HTTP 端點:欄位`；
> 指不出來的一律降級到 (c)「我們沒有這份資料」或直接列進 §6「我拒絕做」。
> 範圍：只讀 `engine02/panels.py`、`engine02/api.py`、`engine02/contracts.py`、`engine02/kansei.py`、
> `engine02/concepts.py`、`engine02/config.py` 與 `docs/engine02-design.md` §3.3 / §3.3b / §3.3c /
> §3.13 / §3.14b / §3.15 / §3.22 / §3.31 / §3.32。不改任何程式。

---

## 0. 一頁結論

1. **唯一值得放在正中央的是需求–供給缺口盤**（`GET /gap/elements`，`panels.py::element_gap`）。
   它是全專案唯一「只有製造商會在意、而且只有 ENGINE 02 算得出來、而且已經被否證式驗證過」的輸出
   （§3.22：遮掉表現該要素的商品 → 該要素在缺口榜的 MRR 0.381→0.509、排第一 28.9%；
   遮掉同件數隨機商品 → 0.380、p=1.00；注入 vs 對照 p<1e-4，45 次試驗）。
2. **後台的分母是「本服務啟動後收到的請求數」，不是市場、不是使用者數。**
   需求 log 在 `api.py::_record_demand`，是一個 in-memory `deque(maxlen=ENGINE02_DEMAND_LOG，預設 500)`，
   **重啟即清空、沒有持久化、沒有 session 去重**。`GapReport.n_sessions` 是**請求數**不是對話數，
   這個欄位名稱本身會誤導評審，畫面上必須改標成「本場請求數 n」。
3. **七條設計軸裡，`/gap/elements` 永遠只吐得出五條。** `kansei.py::KanseiTable.load(fold_antonyms=True)`
   把 `glossy_fabric→matte_fabric`、`tailored_fit→relaxed_fit`、`bold_pattern→minimal_design`、
   `casual_style→formal_style` 折成同一條雙極軸並把被折那一極的 `K[:, b]` 歸零；
   `element_gap` 又有 `if abs(demand[j]) < 1e-9: continue`。
   所以**「亮面材質」與「合身剪裁」不可能出現在缺口榜上**，把它們畫成兩根獨立的長條就是造假。
4. **布料面板只有在 `full_concept_hybrid` / `full_concept_vlm` arm 下才誠實**（§3.3c/§3.13：
   亮面材質 CLIP AUROC 0.71、CI 0.52–0.89 幾乎壓到隨機；Qwen3-VL-8B 0.90–0.911）。
   **肩線挺與柔軟針織在 420 件盲標裡是 0 個正例（§3.3b），今天不能做成任何一個數字。**
5. **價格欄位不存在**（`Provenance.price_available`、`panels.py::provenance` 的 caveat
   「商品庫無價格資料，預算條件不做過濾」），所以任何營收、毛利、庫存金額面板一律 (c)。
6. **Like / Dislike / Superlike 的計數 ENGINE 02 不存**。它只在請求當下以
   `FeedbackState.design_adjust_steps / chosen_item_ids / rejected_item_ids / choice_history` 的形式
   經過 `POST /handshake`。要做排行榜必須 ENGINE 03 持久化，見 (c)。

---

## 1. 面板逐一規格

### (a) 今天就能做，不用寫任何新程式

#### A1. 設計要素需求–供給缺口盤（主面板）

| 項目 | 內容 |
|---|---|
| 一句話問題 | 「顧客一直在要、而我們目錄給不出來的設計要素是哪一條？」 |
| 端點 | `GET /gap/elements?arm=full_zclip3&threshold=0.5` |
| 欄位 | `GapReport.n_sessions`、`threshold`、`arm`、`note`；每列 `ElementGap.element / label / demand / demand_share / direction / supply / gap / n_items_above` |
| 後端 | `panels.py::element_gap`（需求 = Σ over requests 的 `KanseiTable.beta(probs, steps)`，正負分開不相消；供給 = `(design_matrix(arm) > τ).mean()`；`gap = |demand_share| × (1 − supply)`，`direction=="avoided"` 時乘 `supply`） |
| 圖表 | 水平**發散**長條：左軸為 `direction=="avoided"`、右軸為 `"wanted"`，長度 = `gap`，長條上疊一個細標記表示 `supply`。每列下方一行小字：`demand_share` 與 `n_items_above / n_catalog` |
| 必須不能宣稱 | 不能說「市場需求」「消費者趨勢」「下一季」。需求側是**本服務收到的查詢**（`note` 欄位已經寫死這句，畫面必須照顯示）。§3.22 明寫：「它沒有證明缺口能預測真實銷售」。 |

#### A2. 品類 × 顏色缺口格

| 項目 | 內容 |
|---|---|
| 一句話問題 | 「他們一直問藏青外套，而我們只有四件——是哪幾格？」 |
| 端點 | `GET /gap/cells?top=20` |
| 欄位 | `n_sessions`、`cells[].category / color / requests / catalog_items / items_per_request / gap`（`gap = requests / (1 + catalog_items)`） |
| 後端 | `panels.py::category_color_gap` |
| 圖表 | 熱區表格（不是熱力圖，格數太少）：每列一格，`requests` 用實心點陣，`catalog_items` 用空心點陣，右側 `items_per_request` 一個數字 |
| 必須不能宣稱 | `_record_demand` 只記 `c.category.values[0]` 與 `c.color.values[0]`——**每個請求只記第一個值**。多值查詢（「藍或黑」）會被截斷成「藍」。`requests` 是請求數不是人數。沒有顏色或品類其中之一的請求**完全不進這張表**（`if a and b`）。 |

#### A3. 隱性需求供給率（Sup(n)）

| 項目 | 內容 |
|---|---|
| 一句話問題 | 「我們的目錄，有多少比例撐得起『怕顯得太用力』這種需求？」 |
| 端點 | `GET /needs/supply?arm=full_zclip3&threshold=0.5` |
| 欄位 | `arm`、`threshold`、`n_items`、`supply{need_id: 比例}`；需求中文名取自 `GET /kansei` 的 `needs` |
| 後端 | `panels.py::need_supply`（`(design_matrix @ K.T)[:, n] > τ` 的比例） |
| 圖表 | 十條水平條（10 個 need），單位是「目錄佔比」 |
| 必須不能宣稱 | 這**只有供給側**。需求側 D(場合, n) 是 ENGINE 03 的，缺口乘積今天沒人算。端點預設 `arm=full`、`/gap/elements` 預設 `full_zclip3`；`pipeline.py::design_matrix` 的快取鍵是 `(concept_mode, concept_dn, concept_applicability, vlm_elements)`，這四項兩個 arm 相同，所以 c(i,d) 是同一份——但 UI 仍必須把 `arm` 明寫在卡片上，否則讀者無從判斷。 |

#### A4. 單場對話拆解（Case Study 抽屜）

| 項目 | 內容 |
|---|---|
| 一句話問題 | 「這一位顧客，嘴上說的和真正讓他點下去的，差在哪？」 |
| 端點 | `POST /view`（body：`ViewRequest{request, prev_request, prev_response}`） |
| 欄位 | `view.said_vs_unsaid.stated / inferred / dont_care / unmentioned / soft_only / sentence / unstated_drivers[].{need_id,label,prob,contribution,share_of_positive,top_elements[].phrase}`、`view.needs.{total_positive_contribution, design_share_of_positive, feedback_share_of_positive, unserved_needs}`、`view.diversity.div_at_k`、`view.round_diff.{turnover, metrics_before, metrics_after}`、`view.provenance.*` |
| 後端 | `panels.py::stated_vs_unstated / need_panel / slate_diversity / round_diff / provenance / build_view` |
| 圖表 | 左：說了什麼（slot chips，`soft_only` 的 chip 要有明顯的「未過濾」記號）；右：真正加分的需求（橫條 = `contribution`，下面掛 `top_elements[0].phrase`）；底部一行 `sentence` 原文 |
| 必須不能宣稱 | 這是 **n=1**。不可以把多場 `/view` 的 `contribution` 直接平均後當成「族群洞察」——`contribution` 的尺度依賴該輪候選池的 z-score，跨對話不可加。`soft_only` 存在就是在說：`style_keywords` 只進檢索文字、`budget` 在無價格目錄上完全惰性（`HARD_FILTER_SLOTS` 只有五個 slot）。 |

#### A5. 誠實度 / 資料來源條（永遠釘在頁尾）

| 項目 | 內容 |
|---|---|
| 一句話問題 | 「這一頁的每個數字，是資料集原值還是模型判讀的？」 |
| 端點 | `POST /view` 的 `view.provenance`；`GET /health` |
| 欄位 | `provenance.{arm, encoder, kansei_version, contract_version, n_catalog, n_after_filter, relaxed_human, model_filled_attributes, price_available, explanation_sources, reason_modes, caveats, timings_ms}`；`RoundMetrics.{hard_constraint_satisfaction, match_policy, excluded_value_hits, rejected_item_hits, feedback_violations}` |
| 圖表 | 一條細長的 glass bar，三段：資料來源 / 放寬了什麼 / 延遲。`caveats` 逐條列出 |
| 必須不能宣稱 | `hard_constraint_satisfaction` **必須和 `match_policy` 同框顯示**。§3.14b 記錄過一個直接誤導評審的 bug：指標用嚴格字串比對、過濾器用色系比對，畫面顯示滿足度 0.0 而那五件正是色系比對放進來的——兩把尺。現在同一把尺了，但 `match_policy` 是 `exact` 還是 `color_family` 仍必須寫在旁邊。 |

#### A6. 「同一批結果，讀出幾種意思」分面卡

| 項目 | 內容 |
|---|---|
| 一句話問題 | 「同一句需求，其實分成幾種款式取向？」 |
| 端點 | `POST /facets`（`FacetRequest{request, n_pool=50, n_groups=3, examples=2}`） |
| 欄位 | `facets.{axis, axis_label, high_label, low_label, eta_squared, corr_with_score, category_confound, n_pool, note}`、`facets.groups[].{label, n, mean_z, categories, examples}`、`facets.considered[].{axis, spread_z, corr_with_score, category_confound, balance, gain}` |
| 後端 | `panels.py::facet_slices`（軸的選法：離散度 × (1−|與分數相關|) × (1−Cramér's V) × 平衡度） |
| 圖表 | 一條軸、2–3 個群的 dot-strip，每群兩張商品縮圖；右上角三個小數字 `eta_squared / corr_with_score / category_confound` |
| 必須不能宣稱 | 這**不是重排序**（§3.31，`tests/test_silent_failures.py::test_facets_do_not_change_the_ranking` 釘住）。`category_confound ≥ 0.5` 時 `note` 會自己說「這個切分有一部分其實是在分品類」，UI 必須原樣顯示而不是藏起來。GenFacet 的 +42.0% 是**線上 CTR**，不能拿來宣稱我們的 NDCG 會變好。**呼叫一次 `/facets` 會在需求 log 多記一筆**（`facets()` 內部呼叫 `rank()`，而 `rank()` 呼叫 `_record_demand`），所以 A1/A2 的分母會被後台自己的操作汙染。 |

#### A7. 本場需求位移（唯一可以帶「變化」兩個字的面板）

| 項目 | 內容 |
|---|---|
| 一句話問題 | 「這場 demo 進行到一半，大家問的東西變了嗎？」 |
| 端點 | `GET /gap/elements/change?arm=full_zclip3&threshold=0.5&min_per_window=30` |
| 欄位 | `status`（`ok` / `insufficient_data`）、`n_early`、`n_late`、`window_seconds`、`elements[].{element,label,share_early,share_late,delta}`、`note` |
| 後端 | `api.py::gap_elements_change`（前半 vs 後半，`len(buf) < 2*min_per_window` 直接拒答） |
| 圖表 | Slope chart（兩點一線），只畫 `|delta|` 最大的五條 |
| 必須不能宣稱 | 端點的 docstring 已經自己寫了：「這是刻意**不是**趨勢也不是預測」「描述的是這個房間，不是市場」「敵意解讀是正確的：有人多打幾句查詢就能移動它」。UI 必須把這三句照抄。`status=="insufficient_data"` 時**顯示拒答狀態，不准退化成畫一條線**。 |

### (b) 需要補一個小端點（每一個都指名改哪裡）

#### B1. 需求側漏掉了使用者「直接說出口」的版型偏好

`api.py::_record_demand` 只記 `{n.need_id: n.prob}` 與 `req.feedback.design_adjust_steps` 兩樣。
但 `pipeline.py` 613–654 行，實際進 β 的來源有**五個**：`feedback.design_adjust_steps`、
`feedback.design_weight_delta`（偏好學習器的 Bradley–Terry Δβ）、`design_weight_prior`（企劃／外部先驗）、
`profile.weights`（開場三題，§3.32）、`stated_design_steps`（使用者**本輪打的字**，例如「版型要修身」）。

**這正是製造商最在意的那一類需求，而缺口盤看不到它。**

- 要改的地方：`_record_demand` 的 tuple 多記一個 `dict`，把 `stated_design_steps` 與
  `feedback.design_weight_delta` 併進去；`element_gap` 的 `sessions` 參數已經是
  `(probs, steps)` 的序列，加一個 `extra_delta` 參數把它加進 `demand` 即可。
- **不要把 `design_weight_prior` 併進去**：那是企劃自己的先驗，把它算進「顧客需求」等於自證預言。
  它必須是缺口盤上另一條對照線。
- 新端點不需要，改現有函式簽名即可，約 15 行。

#### B2. 供給側的分母沒有扣掉「這條軸根本不適用」的商品

`concepts.py::applicability_mask`：`structured_shoulders` 只適用 `top/outerwear/dress`、
`relaxed_fit` 適用 `top/bottom/outerwear/dress`、`crisp_collar` 適用 `top/outerwear/dress`；
不適用的商品在 `design_scores` 裡被設成 **0**（中位，不是 NaN）。
所以「肩線挺的供給只有 12%」的分母**包含全部的鞋和包**，而它們在數學上不可能超過 τ=0.5。

- `panels.py::element_gap` 與 `need_supply` **本來就有 `mask: np.ndarray | None` 參數**
  （`scripts/eval_gap.py` 在用），但 `api.py::gap_elements` 與 `needs_supply` 沒有把它開出來。
- 要改的地方：兩個端點各加一個 `category: str | None = None` query param，
  在 endpoint 內從 `engine().catalog.items["category"]` 組 bool mask 傳進去；
  回應多回一個 `mask_note`（例如「供給分母＝上衣／外套／洋裝 8,412 件」）。約 12 行。
- 沒有這個參數，供給數字就只能寫成「佔全目錄」，不能寫成「佔上衣」。

#### B3. 缺口盤沒有不確定度

`ElementGap.demand_share` 是 n 筆請求的 β 加總後正規化，**沒有任何區間**。
在 10–100 次請求的規模下，第 1 名和第 3 名很可能互換。

- 要改的地方：新增 `GET /gap/elements/ci?n_boot=2000`，對**請求**做 bootstrap 重抽
  （不是對商品），每次重抽跑一遍 `element_gap`，回傳每個 element 的
  `demand_share_ci=[lo, hi]`、`gap_ci=[lo, hi]`、`rank_ci=[lo, hi]`。
  直接沿用 `engine02/eval/metrics.py::bootstrap_ci`（`n_boot=10000, alpha=0.05`，
  Smucker, Allan & Carterette CIKM 2007），**不要自己發明一套**。
- 供給側**不需要** CI：它是目錄在給定 τ 下的普查，沒有抽樣誤差；它的不確定度在
  c(i,d) 的量測品質（§3.3 的 AUROC CI），屬於另一種東西，兩者不可混在同一根誤差棒裡。

#### B4. 需求 log 沒有持久化，也沒有分母的來源拆解

重啟即清空、`maxlen=500`、`/rank`、`/view`、`/facets`、`/intent/rank`、`/visual-search`
全都會寫進同一個 buffer（`/rank/plain` 不會；`_warmup()` 直接呼叫 `svc.rank` 也不會）。

- 要改的地方：`GET /gap/provenance`，回傳 `{n_records, maxlen, truncated: bool, first_ts, last_ts,
  by_endpoint: {...}}`。`by_endpoint` 需要 `_record_demand` 多收一個 `source` 參數。約 20 行。
- 沒有這個，後台自己按幾次 `/facets` 就會污染主面板，而畫面上看不出來。

### (c) 需要我們沒有的資料（說清楚跟誰要）

| 面板 | 缺什麼 | 跟誰要 |
|---|---|---|
| Like / Dislike / Superlike 排行榜 | ENGINE 02 **不存任何回饋**。`ChoiceRecord`、`FeedbackState` 只在單一請求裡過境；`POST /handshake` 回傳 `ledger` 後就丟掉。`Superlike` 在 `contracts.py` 裡**根本沒有對應欄位**（只有 `chosen_item_ids` / `rejected_item_ids` / `excluded_item_ids` 三級） | ENGINE 03：要一個持久化的 ledger store，並且要先定義 Superlike 對應到哪個欄位（建議 `chosen_item_ids` + 一個 `intensity`，需改 contract） |
| 任何金額（營收、毛利、庫存價值、客單價） | `RankedItem.price` 在 KAGL 目錄全為 `None`，`Provenance.price_available=False` | 聚陽：要一份帶價格的商品主檔；在那之前預算 slot 是惰性的（`stated_vs_unstated` 的 `soft_only` 會把 budget 列進去） |
| 真實需求（而非查詢）隨時間變化 | 需求 log 沒有時間軸也不持久（`docs/research/forecast-evaluation.md` §0.1 已判定） | 帶 `t_dat` 的成交資料。該文件核實過 H&M 鏡像（31,788,324 筆、2018-09-20～2020-09-22）可做**離線評測**，但授權未標示，**不可出貨** |
| 使用者輪廓（年齡、地區、性別族群） | 契約裡完全沒有人的欄位。`constraints.gender` 是**商品的**性別分類，不是使用者的 | 沒有人可以給，也不該要。見 §6 |
| 場合 × 需求的需求側 D(場合, n) | `need_supply` 只算供給；`GET /needs/supply` 的 docstring 明寫「ENGINE 03 owns demand D(occasion, n) and the Gap product」 | ENGINE 03 |
| 生產可行性（打樣成本、布料庫存、MOQ） | 完全不在任何契約裡 | 聚陽的 ERP。沒有它，缺口盤只能說「被問到而目錄沒有」，不能說「值得做」 |

---

## 2. 布料與版型：這個面板能不能誠實地做？

**能，但只能做成兩條軸、一個 arm 註記、兩個空欄位。**

### 2.1 七個 id 實際上只有五條軸，而且其中兩條今天是空的

`kansei.py::KanseiTable.load` 的反義詞折疊（`fold_antonyms=True`，服務端唯一路徑）產生
`folded = {glossy_fabric: matte_fabric, bold_pattern: minimal_design, tailored_fit: relaxed_fit,
casual_style: formal_style}`，被折那一極的 `K[:, b]` 歸零。

| 你列的 id | 實際狀態 | 在 `/gap/elements` 會不會出現 |
|---|---|---|
| `matte_fabric` 霧面材質 | 雙極軸 **霧面 ↔ 亮面** 的正極 | 會 |
| `glossy_fabric` 亮面材質 | **被折進 `matte_fabric`**，demand 恆為 0 | **永遠不會**（`element_gap` 的 `if abs(demand[j]) < 1e-9: continue`） |
| `relaxed_fit` 寬鬆版型 | 雙極軸 **寬鬆 ↔ 合身** 的正極 | 會 |
| `tailored_fit` 合身剪裁 | **被折進 `relaxed_fit`**，demand 恆為 0 | **永遠不會** |
| `crisp_collar` 挺版領子 | 獨立軸（反義極是「無領／軟領」，未另立 element） | 會 |
| `structured_shoulders` 肩線挺 | 獨立軸 | 會出現，但**無驗證**（見下） |
| `soft_knit` 柔軟針織 | 獨立軸 | 會出現，但**無驗證** |

再往下一層：`concepts.py::design_scores` 的 antonym 模式下
`score_glossy = sigmoid((sp_glossy − sn_glossy)/T)`，而 `sp_glossy = sn_matte`、`sn_glossy = sp_matte`，
所以 `score_glossy = 1 − score_matte` **在數值上完全成立**，z-score 後
`c(i, glossy) = −c(i, matte)` 精確成立。**它們不是兩個量測，是同一把尺的兩端。**
畫成兩根並排的長條，等於把同一個數字算兩次。

### 2.2 每條軸的證據強度（§3.3b / §3.3c / §3.13）

| 軸 | 盲標正／負例 | CLIP（反義詞＋分布正規化）AUROC | Qwen3-VL-8B AUROC | 17,783 件複核 | 判定 |
|---|---|---|---|---|---|
| 挺版領子 `crisp_collar` | 27／33 | 0.97 | 0.98 | 0.983 | **可以出數字** |
| 霧面／亮面 `matte_fabric` | 9／51 | 0.71（CI 0.52–0.89） | 0.90（CI 0.80–0.98） | 0.911 | **只有 `full_concept_hybrid` / `full_concept_vlm` 可以出數字**；CLIP arm 的 CI 下界 0.52 幾乎等於擲骰子 |
| 寬鬆／合身 `relaxed_fit` | **7**／47 | 0.86（CI 0.71–0.98） | 0.77（CI 0.60–0.93） | 0.775 | 可以出數字，但**必須帶 CI，而且正例只有 7 件**——這個 CI 寬到不能拿來排名 |
| 肩線挺 `structured_shoulders` | **0 正例** | — | — | 不適用率 46% | **不能出任何數字** |
| 柔軟針織 `soft_knit` | **0 正例** | — | — | — | **不能出任何數字** |

`config.py::ArmConfig.vlm_elements` 的預設值是
`("matte_fabric", "glossy_fabric", "visible_logo", "minimal_design", "bold_pattern", "crisp_collar")`
——**刻意不含 `relaxed_fit` 與 `structured_shoulders`**，因為 §3.3c 量到 VLM 在寬鬆版型上反而比 CLIP 差
（0.77 vs 0.86）。面板不可以自作主張把它們加進去。

### 2.3 最強的誠實句子

> 「在本服務收到的 **n = 137 次請求**裡，『霧面 ↔ 亮面』這條軸的需求有 **68% 偏向霧面**
> （`demand_share = 0.31`，方向 `wanted`），而目錄裡 c(i, matte) > 0.5 的商品只佔
> **上衣／外套／洋裝的 14%**（`n_items_above = 1,178 / 8,412`），缺口 `gap = 0.27`，在 11 條軸裡排第 1。
> 這條軸的分數是 Qwen3-VL-8B 標註（`arm=full_concept_hybrid`），在 397 件盲標上的 AUROC 是
> 0.90（CI 0.80–0.98）。**這句話描述的是這個目錄被問到什麼，不是市場，也不是下一季。**」

這句話的每一個成分都指得出來源，而且每一個都可以被反駁。

### 2.4 什麼會讓它變成謊話

1. **把 `glossy_fabric` 和 `tailored_fit` 畫成獨立長條**——它們是被折掉的極，恆為 0；
   要嘛你畫的是假資料，要嘛你繞過了 `fold_antonyms` 而把同一個量測算了兩次。
2. **在 CLIP arm（`full` / `full_zclip3`）上談布料**——AUROC 0.71、CI 下界 0.52。
   §3.3b 的原話是「**材質光澤不可靠**，跟 OVAD、MODA 的文獻一致」。
3. **給肩線挺或柔軟針織一個百分比**——0 個正例，這個數字沒有被任何獨立標準答案檢驗過，
   而且 §3.13 量到 VLM 對肩線有 46% 回答「不適用」。
4. **把 `supply` 說成「我們的產線做不出來」**——`supply` 是**目錄中被 CLIP／VLM 判為有此特徵的商品比例**，
   不是產能、不是布料庫存、不是打樣紀錄。
5. **說「68% 的使用者想要霧面」**——分母是請求不是使用者，而且 `demand` 是 β 加總（連續權重），
   不是投票數，除不出百分比人數。
6. **把 `/gap/elements/change` 的 `delta` 講成「趨勢」**——端點自己拒絕這個說法。
7. **用單場 `/view` 的 `contribution` 平均出族群結論**——那個數字在候選池內 z-score 過，跨對話不可加。

---

## 3. 樣本數誠實：每個面板的最小 n，與 UI 怎麼表示不確定

黑客松規模是 10–100 場對話；每場 2–4 輪，所以請求數大約 **20–400**，
但 `deque(maxlen=500)` 會在 500 筆截斷，而後台自己按 `/facets`、`/view` 也會記帳。

| 面板 | 最小可信 n | 低於門檻時要怎麼做 | 不確定度怎麼畫 |
|---|---|---|---|
| A1 缺口盤（前 3 名排序） | **n ≥ 60 請求**（`scripts/eval_gap.py` 的驗證本身用 `--sessions 60`，45 次試驗；低於這個數我們沒有任何證據說排名穩定） | 顯示「證據不足以排名」，只列 element 名稱與 `n_items_above`（供給側是普查，永遠有效），**不列 `gap`** | B3 的 bootstrap CI（`eval/metrics.py::bootstrap_ci`，n_boot=10000、alpha=0.05，對**請求**重抽）畫成誤差棒；名次用 `rank_ci` 畫成帶狀而不是「第 1 名」 |
| A1 缺口盤（單一要素 yes/no） | **n ≥ 30** | 同上 | 同上 |
| A2 品類×顏色格 | **單格 requests ≥ 5** 才進榜（1–4 次就是一個人打了四句話） | `requests < 5` 的列變灰、排在下面、不參與排序 | 對 `requests` 做 Poisson 式的 bootstrap CI；`catalog_items` 是普查，不畫 CI |
| A3 Sup(n) | **不適用**——它是目錄普查，n 就是 `n_items`（44,434 或 17,783） | — | 不畫抽樣 CI。改畫 τ 敏感度：τ ∈ {0.3, 0.5, 1.0} 三條細線。這是唯一誠實的「這個數字有多軟」 |
| A4 單場拆解 | **n = 1，這是設計** | — | 不畫 CI，畫「這是一場對話」的明確標籤。**禁止在這個面板上做任何平均** |
| A6 分面 | `n_pool ≥ n_groups × min_group`（`facet_slices` 自己會回 `note="結果太少，不切分面"`） | 照顯示 `note` | 顯示 `eta_squared`、`corr_with_score`、`category_confound` 三個原始數字，不要換算成星等 |
| A7 本場位移 | **硬門檻 60 請求**（`min_per_window=30`，`2 × 30`） | 端點回 `status="insufficient_data"`，UI 原樣顯示拒答卡 | 兩半各自 bootstrap CI；若兩個 CI 重疊，slope 線畫成虛線並標「重疊」 |
| 任何「A 比 B 高」的比較 | 兩組同分母 | — | **配對排列檢定**（`eval/metrics.py::paired_permutation_test`，10,000 次符號翻轉，two-sided）。畫面寫 `p = 0.03`，不寫「顯著提升」四個字 |

**詞彙紀律**：這個 repo 已經有 `bootstrap_ci` 與 `paired_permutation_test`（Smucker, Allan & Carterette,
CIKM 2007），後台一律沿用這兩個詞與這兩個函式，**不准發明「信心分數」「可信度星等」這類新名詞**。
畫面上出現的統計字眼只有三個：`n`、`95% bootstrap CI`、`paired permutation p`。

---

## 4. 設計語言（短）

沿用 THREAD / STUDIO：深色底（近黑，非純黑）、玻璃卡（背景模糊 + 1px 半透明邊）、大量留白、
一張卡一個數字、數字下面就是它的證據。

- **卡片三層**：(1) 巨大的單一數字（缺口值 / 供給比例 / n）；(2) 一行中文問句，就是本規格每個面板的
  「一句話問題」；(3) 證據列——`n=137`、`95% CI [0.21, 0.34]`、`arm=full_concept_hybrid`、
  `AUROC 0.90`。第三層用等寬字，**永遠不摺疊、不藏在 tooltip 裡**。
- **顏色只有三種語意**：`wanted`（暖）、`avoided`（冷）、`insufficient_data`（無彩度、降低不透明度）。
  不要用紅綠當好壞，缺口大不等於壞消息。
- **拒答是一級狀態**：`status="insufficient_data"` 的卡片和有數字的卡片**同樣大、同樣亮**，
  上面寫「本場請求數 42，需要 60」。它不是錯誤狀態，是產品的一部分。
- **與前台的呼應**：左側沿用 Style Journey 的分支樹，但節點是**設計要素軸**而不是對話輪次；
  點一條軸，右側換成該軸的缺口卡 + `/facets` 的 dot-strip + 兩張真實商品縮圖
  （縮圖直接用 `GET /images/{item_id}`）。
- **動效**：只有數字跑動與卡片淡入，reduced-motion 下全部關掉。後台是拿來讀數字的。

---

## 5. 一螢幕、60 秒的 demo 腳本

| 秒 | 畫面 | 講稿要點 |
|---|---|---|
| 0–10 | 進場即是 **A1 缺口盤**，11 條軸的發散長條，正中央一張巨卡：「被問到最多、目錄最給不出來的設計要素」 | 「這是製造商那一頁。左邊是顧客想避開的，右邊是想要的。」 |
| 10–25 | 點第一名那條軸 → 展開證據列：`n_sessions` / `demand_share` 95% CI / `supply` / `n_items_above` / `arm` / AUROC | 「n 是 137 次請求，不是 137 個人，也不是市場。供給側是這個目錄的普查。這條軸的分數在 397 件盲標上 AUROC 0.90。」 |
| 25–40 | 切到 **A2 品類×顏色格**，指第一列 | 「最粗但最直觀的一格：他們問了 23 次藏青外套，我們有 4 件。」 |
| 40–50 | 切到 **A7 本場位移**，**刻意讓它顯示 `insufficient_data`** | 「本場只有 42 次請求，需要 60。所以它不畫線——我們寧可讓面板拒答，也不畫一條沒有的趨勢。」 |
| 50–60 | 回到 A1，疊上 §3.22 的驗證數字（MRR 0.381 → 0.509、對照組 0.380、p=1.00 / p<1e-4） | 「這個缺口指標是可以被否證的：遮掉表現該要素的商品，它會爬上榜；遮掉同樣件數的隨機商品，榜完全不動。它在回應『特定要素的供給』，不是在回應『目錄變小』。」 |

**為製造商撐起整個案子的是 A1 缺口盤。** 理由三個，缺一不可：

1. **只有 ENGINE 02 算得出來**：需求側要 β_d（`KanseiTable.beta`），供給側要 c(i,d)（`design_matrix`）。
   ENGINE 01 沒有 c，ENGINE 03 沒有 c，沒有 CLIP／VLM 分數的人一格都算不出來。
2. **它是唯一被否證式驗證過的製造商指標**（§3.22 / `scripts/eval_gap.py`，45 次試驗，
   注入 vs 對照 p<1e-4、對照 vs 基線 p=1.00）。對照組 p=1.00 這件事比 p<1e-4 更重要：
   它證明這個指標**不會**因為目錄變小就亂動。
3. **它說的話製造商當場能接**：「被問到、但我們做不出來」這句話直接對應打樣決策，
   而且它**不含任何預測成分**，所以聚陽既有的趨勢平台不會和它撞車
   （`docs/research/engine02-completeness.md` §2.1 記錄主辦方已明確排除趨勢預測系統）。

第 40–50 秒那段拒答是**故意的**。一個會拒答的面板，才有資格讓人相信它不拒答時說的話。

---

## 6. 我拒絕做的面板

| 面板 | 為什麼是謊 |
|---|---|
| 「下一季流行預測」「新品成功率」「預估銷量」 | 我們沒有任何帶時間軸的成交資料。`docs/research/forecast-evaluation.md` §0.1：需求 log 沒有時間戳、重啟即清空，**任何用它做的預測都是在預測自己的輸入分布**。§0.2 另記：就算拿到 Visuelle，單品新品預測 SOTA 是 WAPE 54.2%（Visuelle 1.0）／85.65%（2.0 item-shop），也就是「誤差等於銷量本身」 |
| 「趨勢雷達」「本季熱門關鍵字」 | §3.15：28 組設定全部顯著變差（NDCG@5 −0.16～−0.38，p≈1e-4），趨勢**只做展示標籤**。`GET /trends` 自己回 `used_in_ranking: false`。做成一個會動的雷達圖就是在暗示它進了排序 |
| 「顧客輪廓 / 客群分佈」（年齡、地區、族群） | 契約裡沒有任何關於人的欄位。`constraints.gender` 是**商品**的性別分類。要畫這張圖只能靠編造 |
| 「AI 信心指數 92%」 | 我們有的是 AUROC 與 bootstrap CI。把它壓成一個沒有定義的百分比，等於把 §3.3b 那些 0 正例的空格也一起塗滿 |
| 「營收影響 / 導入本系統可提升 X% 轉換」 | 沒有價格（`price_available=False`）、沒有轉換事件、沒有對照組。GenFacet 的 +42.0% 是**別人的**線上 CTR（§3.31 明寫不能外推到我們） |
| 「Superlike 熱門商品排行榜」 | `contracts.py` 裡沒有 Superlike 這個概念，ENGINE 02 也不持久化任何回饋。這張榜今天只能是假的 |
| 「亮面材質 vs 霧面材質 雙長條對比」 | `c(i, glossy) = −c(i, matte)` 精確成立。這是把同一個數字畫兩次 |
| 「肩線挺需求指數」「針織需求指數」 | 420 件盲標裡 **0 個正例**。這兩個數字沒有被任何獨立標準答案檢驗過 |
| 「即時需求熱力圖（按地區／時段）」 | 需求 log 只有一個 `time.time()`，沒有地區、沒有使用者、`maxlen=500`、重啟清空 |
| 「本系統推薦準確率 96%」 | 96.5% 是 §3.4 表裡「有理由的卡片比例」，不是準確率。把它搬到後台當成推薦準確率是換了名字的造假 |

---

## 7. 我無法核實的部分

1. **前台 THREAD / STUDIO 的實際實作**：`E:\mchackathon2026` 下只有 `backend/engine02_retrieval`，
   我沒有找到前端專案，所以「同一套設計語言」是依照任務敘述（深色、玻璃感、分支樹、三按鈕）
   推的，沒有比對過任何 token、字體或間距值。§4 的建議需要拿到前端的設計 token 後重寫。
2. **Dislike / Like / Superlike 三個按鈕各自對應到 contract 的哪個欄位**：契約只有
   `chosen_item_ids` / `rejected_item_ids` / `excluded_item_ids` 與 `design_adjust_steps`，
   三按鈕到四欄位的映射沒有寫在我讀過的任何檔案裡，要問 ENGINE 03 的負責人。
3. **§2.3 範例句裡的具體數字（n=137、0.31、14%、1,178/8,412、gap 0.27）是版型示意，不是實測值。**
   我沒有起服務、沒有跑 `/gap/elements`。那段文字示範的是**句型與必要的欄位**，
   實際數字要在 demo 當下由端點產生。
4. **`profile_stability_v1.json` 的實際內容**：我只讀到 `concepts.py::load_profile_stability` 的
   docstring 與 `/visual-search` 的 `profile_caveat` 文案（T16：平均 |Δz| > 0.4、9.7% 的要素會正負反轉），
   沒有逐項核對哪些要素被標成 `reliable=false`。若後台要做「上傳一張照片看它落在哪條軸」的面板，
   必須先核對這個檔，把不穩定的要素標出來。
5. **`kagl_polyvore_filled`（17,783 件）在 demo 當天會不會是實際載入的目錄**：
   §3.3b 記錄「KAGL 幾乎沒有西裝外套和針織衫」，所以肩線與針織的供給數字在
   `ENGINE02_CATALOG` 指向哪一份目錄時差異極大。面板上的 `n_catalog` 必須從
   `GET /health` 的 `catalog` / `n_items` 現場讀，不可寫死。
6. **`/gap/elements` 的 `threshold` 預設 0.5 在真 encoder 上會選出多少件**：
   c(i,d) 是目錄內 z-score，τ=0.5 約等於「比目錄平均高半個標準差」，
   但實際落在上面的件數我沒有量。§3 建議的 τ 敏感度三條線就是為了不必先知道這個答案。
