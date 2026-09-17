# ENGINE 02｜從選擇學偏好（「愈用愈懂你」）— T7 模擬實驗報告

> 狀態：2026-09-17，分支 `engine02-research`，作者：preference sub-agent。
> 程式：`engine02/preference.py`（方法）、`tests/test_preference.py`（9 項，HashEncoder，本機全過）、`scripts/eval_preference.py`（實驗）。
> 原始結果（只在本機，不進 git）：`reports/agents/preference/{kagl,kagl_full}/`（`summary.csv`、`curves.csv`、`rounds_*.csv`、`best.json`、`tune_scores.csv`）。
> **全部是模擬使用者的結果，不是真人。** 標準答案是模擬器裡的隱藏效用，下面 §5 會說明它和模型共用特徵（循環性）的問題，以及用來檢查這一點的對照實驗。

---

## 0. 一頁結論

| 結論 | 數據（第 5 輪、200 位模擬使用者、配對置換檢定） |
|---|---|
| **推薦預設：Bayes 成對 logistic（Laplace 後驗平均）＋既有 Rocchio 一起開** | 主設定平均效用：5k 2.48 vs 只有 Rocchio 2.29（+0.19，95% CI [0.12, 0.27]，p<0.001）；44k 2.36 vs 2.14（+0.22 [0.14, 0.30]，p<0.001） |
| 跟**不共用特徵**的隱藏口味（metadata 顏色系／場合／季節）比，設計權重學習**單獨用**輸給 Rocchio；和 Rocchio 合用時打平（44k）或略輸（5k） | Bayes 單獨 vs Rocchio：5k 1.79 vs 2.06、44k 1.74 vs 1.91（都是 p<0.001）；Bayes＋Rocchio vs Rocchio：5k −0.12（p=0.002）、44k −0.02（p=0.75） |
| PRD 規則式 adjust(d,±1) 贏過「不學」，但**不如 Bayes** | Bayes − RuleStep(0.25)：5k +0.18（p<0.001）、44k +0.20（p<0.001）；metadata 口味下 +0.08（p=0.02）／+0.16（p<0.001） |
| Thompson 取樣、LinUCB 在 5 輪內**都沒有贏過單純用後驗平均** | Bayes − Thompson：5k +0.13（p=0.001）、44k +0.02（p=0.67）；Bayes − LinUCB：+0.03（p=0.30）／−0.03（p=0.30）。LinUCB 的探索加分沒辦法拆成 Δβ，會破壞「貢獻加總＝總分」 |
| 用 Kansei 表結構當先驗共變異，**沒有差別** | 5k 2.43 vs 2.43；44k 2.27 vs 2.23（Bayes，同一批使用者） |
| 學習設計權重會**稍微犧牲屬性相符度**，和 Rocchio 合用就不會 | 屬性 NDCG@5，44k：不學 0.242、Rocchio 0.335、Bayes 0.307（vs Rocchio p=0.026）、Bayes＋Rocchio 0.328（vs Rocchio p=0.60） |
| **真正的瓶頸是 top-100 候選集**，不是學習方法 | 在候選集裡直接挑最高效用的前 5 件（上限）：5k 3.11、44k 3.05；最好的方法只有 2.48／2.36 |
| 和 T5 的「Rocchio 無效」**並不矛盾** | T5 的目標是單一商品、成功與否二元判定；T7 的效用是平滑的屬性口味，Rocchio 在這裡 +0.72～+0.74（p<0.001） |

---

## 1. 方法（`engine02/preference.py`）

輸入是 ENGINE 03 的帳本 `ChoiceRound(shown, chosen, rejected)`。所有方法都輸出**標準設計要素**上的連續 Δβ：反義成對的要素已經合併成一條軸（`casual_style`→`formal_style`、`bold_pattern`→`minimal_design`、`tailored_fit`→`relaxed_fit`、`glossy_fabric`→`matte_fabric`），共 11 維。
在 pool 標準化範圍內，設計項不會再做 z-score，所以「在分數上加 Δβ·c(i)」和「改 β」**數學上完全相同**（測試 `test_hook_matches_fast_rerank_and_keeps_additivity` 有檢查）。

| 方法 | 做法 | 出處（已開原文或摘要確認） |
|---|---|---|
| `NoLearning` | Δβ=0 | — |
| `RuleStep` | PRD 規則：每次選擇，在 \|c(選中)−mean c(展示)\| 最大的要素上依正負走 ±1 步；否決的商品在它偏離最大的要素上走反方向 1 步。步長 0.25（PRD），上限 ±3 步；另外調過一版步長 0.5 | PRD |
| `BayesLogistic` | 把選擇當成 Boltzmann-rational choice：P(i≻j)=σ(λ·w·(c_i−c_j))，選中的商品 ≻ 其他展示商品，未否決的商品 ≻ 被否決的商品。先驗 N(β0, σ²I)，β0=γ·p(n)·K；用 Newton 法求 MAP，加回溯線搜尋，再用 Hessian 逆矩陣當 Laplace 共變異。另有 `likelihood="mnl"`（展示集合上的多項 logit）與 `prior="kansei"`（先驗共變異 ∝ Kᵀ Cov_Dirichlet(p) K ＋ σ²I/4） | Jeon, Milli & Dragan, *Reward-rational (implicit) choice*, NeurIPS 2020（arXiv:2002.04833） |
| `ThompsonLogistic` | 同一個後驗，每輪抽一組 w 來排序；第 1 輪不擾動 | Chapelle & Li, *An Empirical Evaluation of Thompson Sampling*, NeurIPS 2011（原文用對角 Laplace 後驗；本實作用完整 11×11 共變異） |
| `LinUCB` | 以「每輪置中」的特徵，對「每輪置中」的獎勵（選中 +r、否決 −r）做 ridge 回歸，先驗平均 β0，再加樂觀加分 α·√(fᵀA⁻¹f) | Li, Chu, Langford & Schapire, WWW 2010（arXiv:1003.0146）。對話式推薦用 bandit 的先例：Christakopoulou, Radlinski & Hofmann, KDD 2016（摘要確認：線上偏好引導、潛在因子模型） |
| Rocchio | 既有的 `Engine02.query_embedding`（圖片向量 a=0.5、b=0.25）＋否決相似度懲罰項（arm `full`） | 既有實作 |

超參數**只在 5k、主設定、60 位調參使用者**上用網格搜尋（和評估用的 200 位使用者是不同批），指標是第 2–5 輪的平均效用。44k 和所有敏感度條件都**直接沿用、不再重調**。
結果（`best.json`）：
- RuleStep：步長 0.5
- Bayes：λ=0.5、σ=1.0（MNL 版相同）
- Thompson：λ=0.5、σ=1.0、變異縮放 0.25（網格最小值，代表探索越少越好）
- LinUCB：α=0.1、r=2

## 2. 實驗設定（T7，`scripts/eval_preference.py`）

- **商品庫與模型**：
  - KAGL 5k 與 44k，Marqo-FashionSigLIP，nycu RTX 4090。
  - 候選集 top-100，展示前 5 件，共 5 輪。
  - 每個商品庫 200 位模擬使用者，所有方法用同一批使用者和同一組亂數種子。
- **查詢**：
  - 從 `eval/tasks.make_queries` 取一個（性別、顏色、子類、品類、場合）組合當目標。
  - 系統只收到硬條件「品類＋性別」和文字「{gender} {subcategory}」。
  - 過濾後商品池的中位數：5k 383 件，44k 2,072 件。
- **隱藏口味**：p*(n) ~ Dirichlet(0.3)，w̃ = p*·K ＋ noise·η（η ~ N(0,I)）。
- **隱藏效用**：u(i) = relevance(i) ＋ strength·z_pool(w̃·c(i))
  - relevance 就是 `Query.grades`：4 項屬性全對 3、子類＋顏色 2、子類 1、其他 0。
  - strength=1。
  - **系統不知道 p\***：主設定給的是均勻 p(n)。
- **使用者行為**：
  - 選擇：argmax(u/τ ＋ Gumbel)，也就是 softmax／Bradley–Terry 選擇，主設定 τ=0.5。Gumbel 雜訊依（使用者、輪次、商品）固定，所以各方法之間是共同亂數。τ=0 時直接選 argmax u。
  - 否決：展示商品中效用最低的那件，而且不能是選中的那件。
- **指標**（每輪算一次，比較第 5 輪）：
  - 前 5 件的平均 u
  - hit@5：是否命中商品池中效用前 10 名
  - NDCG@5：用 u 在商品池內的分位數分級（前 1%／5%／20% 分別給 3／2／1 分）
  - cos(ŵ, w̃)
  - 屬性 NDCG@5：和 T1 相同的屬性分級
- **統計**：以使用者為單位做配對置換檢定（10,000 次），差值用 bootstrap 95% CI。
- **兩個參考上限**：
  - `oracle_w`：知道 w̃，只加上口味項（不知道 relevance）
  - `oracle_cand`：在 top-100 候選中直接挑效用最高的 5 件

## 3. 結果

### 3.1 主設定（τ=0.5、noise=0.1、有否決、均勻需求），第 5 輪

| 方法 | 5k 效用 | vs 不學 | vs Rocchio（CI；p） | 44k 效用 | vs Rocchio（CI；p） | 44k hit@5 | 44k 屬性 NDCG |
|---|---|---|---|---|---|---|---|
| 不學 | 1.55 | — | −0.74 | 1.42 | −0.72 | 0.285 | 0.242 |
| Rocchio（既有） | 2.29 | +0.74*** | — | 2.14 | — | 0.470 | 0.335 |
| RuleStep（PRD 0.25） | 2.25 | +0.70*** | −0.05 [−0.12, 0.03]；0.23 | 2.03 | −0.11 [−0.18, −0.04]；0.004 | 0.455 | 0.294 |
| RuleStep（0.5） | 2.27 | +0.71*** | −0.03；0.53 | 2.09 | −0.05；0.28 | 0.460 | 0.292 |
| **Bayes（成對）** | 2.43 | +0.88*** | **+0.14 [0.07, 0.22]；<0.001** | 2.23 | **+0.10 [0.02, 0.17]；0.015** | 0.510 | 0.307 |
| Bayes（MNL） | 2.42 | +0.87*** | +0.13；0.001 | 2.28 | +0.14；0.001 | 0.520 | 0.315 |
| Thompson | 2.31 | +0.75*** | +0.01；0.75 | 2.22 | +0.08；0.061 | **0.570** | 0.302 |
| LinUCB | 2.40 | +0.85*** | +0.11；0.003 | 2.26 | +0.12；0.001 | 0.505 | 0.324 |
| **Bayes＋Rocchio** | **2.48** | +0.93*** | **+0.19 [0.12, 0.27]；<0.001** | **2.36** | **+0.22 [0.14, 0.30]；<0.001** | 0.565 | 0.328 |
| oracle_w（知道口味） | 2.48 | | | 2.43 | | 0.560 | 0.222 |
| oracle_cand（候選上限） | 3.11 | | | 3.05 | | 0.750 | 0.609 |

\*** 表示 p<0.001。

補充：
- **口味方向 cos(ŵ, w̃)**：44k 從 0.45（先驗）升到 Bayes 0.51（p=0.025）、Thompson 0.54（p<0.001）；RuleStep 0.43，沒有改善。5 輪只帶來小幅回升，**排序變好主要不是因為把口味向量估準了**，而是抓到了和 relevance 相關的方向。
- **每輪效用曲線**（44k，第 1→5 輪）：Bayes＋Rocchio 1.42→1.85→2.12→2.28→2.36；Rocchio 1.42→1.75→1.91→2.04→2.14；RuleStep PRD 1.42→1.67→1.86→2.02→2.03。**差距從第 2 輪就開始出現。**
- **方法之間的直接比較**（第 5 輪效用）：
  - Bayes − RuleStep PRD：5k +0.18 [0.12, 0.25]、44k +0.20 [0.14, 0.28]，p 都 <0.001
  - Bayes＋Rocchio − Bayes：5k +0.05（p=0.07）、44k +0.12（p=0.001）
  - 成對 vs MNL：沒有顯著差異（5k p=0.66、44k p=0.08）

### 3.2 敏感度（第 5 輪效用；括號內是 Bayes＋Rocchio − Rocchio 的 p 值）

| 條件 | 5k 不學／Rocchio／RuleStep PRD／Bayes／Bayes＋Rocchio | 44k 不學／Rocchio／RuleStep PRD／Bayes／Bayes＋Rocchio |
|---|---|---|
| 主設定 τ=0.5 | 1.55／2.29／2.25／2.43／**2.48**（<0.001） | 1.42／2.14／2.03／2.23／**2.36**（<0.001） |
| τ=0（選最大值） | 1.55／2.32／2.25／2.49／**2.59**（<0.001） | 1.42／2.20／2.08／2.37／**2.55**（<0.001） |
| τ=0.25 | 1.55／2.33／2.27／2.52／**2.58**（<0.001） | 1.42／2.17／2.09／2.32／**2.46**（<0.001） |
| τ=1 | 1.55／2.21／2.14／2.29／**2.35**（0.001） | 1.42／2.05／1.93／2.08／**2.20**（0.002） |
| τ=2（很隨機） | 1.55／2.14／2.09／2.18／2.16（0.59） | 1.42／1.99／1.85／1.91／2.07（0.10） |
| 口味 noise=0 | 1.66／2.35／2.23／2.38／**2.53**（<0.001） | 1.57／2.15／2.03／2.21／**2.40**（<0.001） |
| 口味 noise=0.3 | 1.39／2.19／2.17／2.39／**2.43**（<0.001） | 1.27／2.10／2.10／2.32／**2.41**（<0.001） |
| 不否決 | 1.55／1.89／2.01／2.16／**2.19**（<0.001） | 1.42／1.69／1.78／1.96／**1.97**（<0.001） |
| 系統拿到有雜訊的 p(n) | 1.68／2.37／2.30／2.45／**2.53**（<0.001） | 1.66／2.30／2.15／2.32／**2.46**（<0.001） |
| Kansei 結構先驗 | 1.55／2.29／2.25／2.43／2.48（<0.001） | 1.42／2.14／2.03／2.27／2.41（<0.001） |

解讀：
- 使用者越隨機（τ 越大），所有學習方法的優勢都縮小；τ=2 時 Bayes＋Rocchio 和 Rocchio 已經沒有顯著差異。
- **沒有否決時 Rocchio 的效果大幅減弱**：44k 從 2.14 掉到 1.69（不學是 1.42）。這時設計權重學習的相對優勢最大，Bayes 比 Rocchio 高 0.27（p<0.001）。所以「否決」這個操作值得在 UI 上保留。
- 給系統有雜訊的需求估計，第 1 輪就比較好（1.42→1.66），但第 5 輪的排名順序不變。

### 3.3 泛化檢查：隱藏口味改用 metadata（不使用任何 c(i,d)）

u(i) = relevance(i) ＋ z_pool(v*·m(i))，m = 顏色系（深／淺／鮮豔／無彩）、場合（Casual／Formal／Sports／Ethnic）、季節（4 季）的 one-hot，v* ~ N(0,I)。這組超參數沒有針對這個條件調過。

| 第 5 輪效用 | 5k τ=0.5 | 5k τ=0 | 44k τ=0.5 | 44k τ=0 |
|---|---|---|---|---|
| 不學 | 1.31 | 1.31 | 1.17 | 1.17 |
| **Rocchio** | **2.06** | **2.07** | **1.91** | **1.94** |
| RuleStep PRD | 1.71*** | 1.69*** | 1.57*** | 1.60*** |
| Bayes | 1.79*** | 1.82*** | 1.74*** | 1.74*** |
| LinUCB | 1.87*** | 1.88*** | 1.77** | 1.75*** |
| Thompson | 1.72*** | 1.75*** | 1.59*** | 1.65*** |
| Bayes＋Rocchio | 1.94（p=0.002） | 1.99（p=0.027） | 1.90（p=0.75） | 1.88（p=0.10） |
| 候選上限 | 3.00 | 3.00 | 3.00 | 3.00 |

星號是 vs Rocchio 的 p 值：*** p<0.001，** p<0.01。

解讀：
- 口味不在設計要素空間裡時，**只調 11 個設計權重不夠**。能部分捕捉到，是因為深色、正式感和 metadata 相關：Bayes 比不學高 0.48～0.57，p<0.001。但 Rocchio 在完整的 768 維圖片空間裡移動，表達力比較強。
- 兩者合用在 44k 和 Rocchio 打平，在 5k 小輸 0.08～0.12。
- **所以 3.1 裡 Bayes 贏 Rocchio 的幅度，有一部分來自循環性**。能穩定成立的結論只有：
  1. Bayes ＞ RuleStep（兩種口味、兩個商品庫都成立）
  2. Bayes＋Rocchio 不會比 Rocchio 差很多，在口味和設計要素相關時明顯比較好

## 4. 建議預設

1. **ENGINE 02 預設同時開**：
   - `BayesLogistic(rationality=0.5, prior_sd=1.0, likelihood="pairwise", prior="isotropic")` 的後驗平均 Δβ
   - 既有 Rocchio＋否決懲罰（arm `full`）

   PRD 的 `RuleStep` 保留給使用者**明說**「再正式一點」這種 adjust 指令；從**點選**推論的部分交給 Bayes。
2. **Thompson／LinUCB 不開**：5 輪內沒有收益。LinUCB 的加分是商品層級，不能寫成可解釋的設計項；Thompson 會讓同一個帳本每次重跑得到不同結果，不利重現和解釋。
3. **理由顯示**：學到的 Δβ 掛在 need share 的 `feedback_adjust`，卡片上會顯示「你上一輪的回饋」，貢獻加總仍然等於總分（測試有檢查）。
4. **簡報措辭**：只能說「模擬使用者上，5 輪內前 5 名的隱藏效用提高，而且優於 PRD 規則與單純 Rocchio（口味和設計要素相關時）」，不能說「真人更滿意」。
5. **下一步最有價值的是擴大候選集**，或讓 Δβ 也參與召回：上限 3.05，目前最好的方法 2.36。

## 5. 限制與注意事項（簡報必讀）

- **循環性**：主設定的隱藏效用用的是模型自己的 c(i,d) 和 K 表，對設計權重學習有利。§3.3 的 metadata 對照組就是為了檢查這一點，結論也因此收斂。
- **relevance 用 metadata 當代理指標**：顏色和場合標籤是 KAGL 的欄位，不是使用者真正的判斷。
- **模擬使用者的行為**是 Boltzmann 選擇加上固定否決最差的一件。真人會有位置偏差、不選、同時否決多件等行為，都沒有模擬到。
- **超參數只在 5k 主設定上調過**，對主設定下的 Bayes、LinUCB 略有利。44k 和 metadata 口味都沒有重調，所以那兩組是比較乾淨的測試。
- **不排除已展示過的商品**：指標衡量的是「當輪推薦品質」，不是「是否發現新商品」。
- **5 輪、200 位使用者**：多重比較沒有校正；主要結論的 p 值都在 0.001 以下，但 p 在 0.01～0.05 之間的差異要保守看待。
- **Jeon 等人的論文作者**是 Jeon、Milli、Dragan（不是 Russell）；Chapelle & Li 只看了摘要和 Laplace 段落。

## 6. 給協調者的整合點（exact hook）

**新增契約欄位**（`engine02/contracts.py` 的 `FeedbackState`）：

```python
# proposed: continuous Δβ learned from choices by ENGINE 02/03 (engine02.preference); element ids,
# antonym poles allowed (folded with sign flip). Added to β on top of design_adjust_steps.
design_weight_delta: dict[str, float] = Field(default_factory=dict)
```

**`engine02/pipeline.py` 的 `Engine02._terms`**：在 `beta_needs, beta_fb = self.kansei.beta(...)` 的下一行加上：

```python
for d, v in req.feedback.design_weight_delta.items():
    canon = self.kansei.folded.get(d, d)
    if canon in self.kansei.element_ids:
        beta_fb[self.kansei.element_ids.index(canon)] += (-v if d in self.kansei.folded else v)
```

`beta_fb` 已經會被寫進 `per_unit["feedback_adjust"]`，所以理由與 need share 不需要改動。

**Δβ 由誰計算**：

```python
from engine02.preference import BayesLogistic, ChoiceRound, DesignSpace
space = DesignSpace.from_kansei(engine.kansei)
F = space.features(engine.design_matrix(arm))
beta0 = space.prior_mean({n.need_id: n.prob for n in req.needs}, arm.need_scale)
hist = [ChoiceRound(shown=catalog.positions(r.shown_ids), chosen=catalog.pos(r.chosen_id),
                    rejected=catalog.positions(r.rejected_ids)) for r in ledger]
delta = BayesLogistic(rationality=0.5, prior_sd=1.0).update(hist, F, beta0).delta
req.feedback.design_weight_delta = space.to_dict(delta)
```

計算量是 11 維、每輪最多約 7 組比較，Newton 法 1 ms 以內。帳本需要記錄**每輪展示了哪些商品**（`shown_item_ids`），目前的 `FeedbackState` 還沒有這個欄位，要請 ENGINE 03 補上。

在 hook 加上之前，可以直接用 `engine02.preference.PreferenceEngine02(...).run(req, arm, design_weight_delta=...)`（子類別實作，行為相同）。

**重現實驗**：

```
python scripts/eval_preference.py --catalog data/catalog/kagl --device cuda --cache-dir <dir> --stage tune --out <out>/kagl
python scripts/eval_preference.py --catalog data/catalog/kagl[_full] --device cuda --cache-dir <dir> --stage main \
    --best <out>/kagl/best.json --users 200 --out <out>/<catalog>
```

在 4090 上約需 31 分鐘（5k）／40 分鐘（44k）。
