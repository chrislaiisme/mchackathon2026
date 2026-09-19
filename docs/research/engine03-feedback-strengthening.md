# ENGINE 03 回饋迴圈：文獻說該做什麼、我們沒做什麼、哪些能在上台前量出來

> 範圍：只談**回饋迴圈**（ENGINE 03 ＋ ENGINE 02 的接收端）。本文**沒有改任何程式、沒有跑任何實驗**。
> 已讀：`docs/engine02-design.md` §3.5／§3.7／§3.12／§3.23–§3.25／§3.32／§3.33／§3.35／§3.36、
> `docs/research/{recsys-preference, implicit-negative-feedback, novelty-and-profile, industry-recsys-practice}.md`、
> `engine02/{contracts,preference,handshake,intent_adapter,constraints,pipeline,panels,service}.py`、
> `origin/engine03-feedback:backend/engine03_feedback/*`（commit `e697d8d`，單一 commit、3 個測試）、
> `origin/main:docs/engine03-feedback.md`。
> 本 session 的 WebSearch 配額在開工前已用盡（200/200），所有核實都靠 WebFetch arXiv／export.arxiv.org API／
> OpenAlex／Semantic Scholar 完成；ACM DL、Springer、CACM 對本機回 403，受影響的條目全部列在 §11。
> **程式的判讀對到 `e08c1a4`**（撰寫期間 repo 前進了 `9cc9a2a`、`e08c1a4` 兩個 commit，
> 已確認 `handshake.py`／`constraints.py`／`contracts.py`／`preference.py`／`service.py`／`pipeline.py` **都沒有變動**，
> §2 的七個發現全部仍然成立）。

---

## 0. 一頁結論

| # | 提案 | 判定 | 一句話理由 |
|---|---|---|---|
| **P1** | **矛盾偵測與修復**：算最小衝突集，給使用者一個具名的修復選項 | **SHIP** | 這不是加值是**補洞**：`require ∩ exclude` 會讓候選池歸零，放寬階梯結構上救不了（§2.3）。文獻上這是 constraint-based recommender 的標準動作（FastDiag, AIEDAM 2012），而**對話式推薦這一側文獻幾乎是空白的**（§6） |
| **P2** | **提問策略**：用既有的 11×11 Laplace 後驗共變異數決定「問哪一軸」與「何時停」 | **MEASURE FIRST** | 後驗共變異數**每輪都已經算出來然後丟掉**（§2.5）。EAR 自己寫出的三條停止條件我們三個都算得出來（§3） |
| **P3** | **ENGINE 03 的 `reasoning` 納入事實檢查** | **SHIP** | 畫面上唯一沒被檢查的那段字，就是最可能說謊的那段字（§2.4）。`explain.verify_paraphrase` 已存在 |
| **P4** | **複合批評（compound critique）一次送多條** | **MEASURE FIRST** | 現在第二個 `CritiqueOp` 會**靜默覆蓋**第一個（§2.7）。文獻最強效果量在這裡：互動輪數 **29 → 6** |
| **P5** | **明確索取否決理由**取代推論隱性負回饋 | **MEASURE FIRST** | 見 §5 |
| **P6** | **近因 vs 一致性加權**（`choice_history` 指數衰減） | **MEASURE FIRST** | 見 §6 |
| — | Thompson／LinUCB／IPS／dwell time／位置偏差估計 | **REJECT** | 已經量過或結構上量不了（§7、§10） |

**排名與「先做哪一個」：見 §9。先做 P1。**

---

## 1. 我們已經有的（不要重複提案）

| 已上線 | 出處 | 已量到的效果 |
|---|---|---|
| 批評回饋（exclude／require／critique）＋三具名角色 | §3.33 | 4 輪成功率 1% → 39–44%（p<0.001）；三角色 ΔNDCG@10 **+0.0635**（p=0.00005） |
| Bayes 成對 logistic 偏好學習 ＋ κ=1 縮減 | §3.7、§3.12 | 第 5 輪效用 +0.18–0.20 勝過 PRD 規則（p<0.001）；點一次 \|Δβ\| 0.23→0.11 |
| 新鮮度項（眼動加權曝光，正向表述）／曝光硬上限 | §3.23、§3.25 | 末輪新穎度 0.007→**0.237**（p<1e-4），最佳卡片效用 **+0.18**（p=0.008）；硬上限量了但**決定不開**（效用 2.543→2.313，p=0.0066） |
| 當輪否定解析（「不要黑色」） | §3.35 | violation@5 0.214→**0.000**，NDCG@5 **+0.045**（p=0.0007） |
| 開場三題先驗（κ₀=3）／Rocchio | §3.32、§3.5 | 第一輪 MRR +0.0096（p=0.0003）但 +0.0072 被洗牌版複製；**Rocchio 不顯著**（p=0.52–0.60），簡報不得宣稱有效 |
| `round_diff` 面板、`match_score` 三重防作弊、`feedback_violations` 累計指標 | §3.36 | 已上線 |

**「回饋有效」我們已經證明了。本文補的是「回饋迴圈作為一個對話」的那一半。**

---

## 2. 讀完 ENGINE 03 程式後的七個結構性缺口

ENGINE 03（`e697d8d`）的實際行為：一次 `gpt-4o-mini` structured output（temp 0.1）把 `FeedbackInput`＋`UserInteraction`
轉成封閉 op 集，逐 op 對詞彙表與本輪展示 id 驗證，輸出 `FeedbackRound`。**它是一個純翻譯器。**
以下七點都是從程式讀出來的，不是推測。

**2.1 它從來不「問」任何問題。** op 集（`Exclude/Require/Adjust/Choice/Feeling/Critique/Anchor/ExcludeItem`）
裡沒有任何一個是提問；`SYSTEM_PROMPT` 的 9 條硬規則沒有一條提到提問。§3.32 的開場三題是**第 1 輪之前、離線、固定題數**。
資訊流是單向的：使用者說 → 系統做。

**2.2 沒有停止準則。** `docs/engine03-feedback.md` 寫「迴圈會一直跑到使用者滿意為止」，程式裡沒有任何對應判斷——
沒有信心度、沒有收斂偵測。現場由評審控制輪數所以不會壞，但「我們知道什麼時候該閉嘴」說不出來。

**2.3 ⚠️ 沒有撤回 op —— 矛盾會把候選池清空（最嚴重的一個）。**
封閉 op 集有 `exclude`／`require`，**沒有 `unexclude`／`unrequire`**。`handshake.apply_round` 對兩者都是單調累加，
`constraints.build_mask` 把它們當成 AND，兩者註解都寫「永不放寬」。而 `DEFAULT_LADDER` 的 key 是
`("color","season","occasion","budget")`，require／exclude 寫進 `applied` 的 key 是 `require_color`／`not_color`
——**放寬階梯結構上碰不到它們**。所以：

> 第 1 輪「不要黑色」→ `excluded_values.color=["Black"]`
> 第 3 輪「這件，但換成黑色」→ `CritiqueOp` 把 `Black` 寫進 `required_values.color`
> → `mask` 全 False → `pool = np.flatnonzero(fr.mask)` 為空 → **0 張卡，而且沒有一行字說明為什麼**

`docs/engine02-pipeline.md` §3.3 的降級階梯宣稱「過濾後沒有結果 → 固定順序放寬」，**這一條正好落在階梯外**。
`grep -rn "contradict\|conflict\|矛盾" tests/ engine02/` **零命中**。
`panels.round_diff` 有 `constraints_removed` 欄位，但因為沒有任何 op 會移除條件，**它永遠是空的**。
`e08c1a4` 新增的 `POST /handshake` 把 `apply_round` 直接掛上 HTTP，所以這條路徑現在**從 API 就打得到**。

**2.4 ENGINE 03 的 `reasoning` 不受任何事實檢查。** `Engine3Response.reasoning` 是 GPT 自由文字，直接回前端。
ENGINE 02 自己的 LLM 改寫要過 `explain.verify_paraphrase`（不得引用 `facts[]` 以外的數字或標籤；
§0 記載本地 Qwen3-1.7B 會把「盛夏偏熱」講反），ENGINE 03 的 `reasoning` 走另一條路，**沒有對應機制**。
`generation_prompt` 同理。

**2.5 後驗共變異數算了就丟。** `preference.BayesLogistic.update` 回傳 `PreferenceUpdate(delta, mean, cov)`，
`cov` 是完整的 11×11 Laplace 後驗共變異數。`service._learn_preferences` 只記 `delta`：

```python
return new, {"method": "bayes_pairwise_logistic", "shrink_kappa": 1.0, "rounds": len(hist),
             "design_weight_delta": new.feedback.design_weight_delta}      # cov 被丟掉
```

「該問哪一軸」＝後驗變異數最大那一軸；「該不該再問」＝最大後驗標準差是否低於門檻。**這兩個量每輪都已免費算出。**

**2.6 我們的評估方法正被 2025 的文獻點名。** `eval/tasks.py::t5_feedback` 是「隱藏一件目標商品，模擬使用者依
**固定順序** subcategory → color → occasion 每輪多揭露一個屬性」。PEPPER（Kim et al., **EMNLP 2025 Findings**,
[arXiv:2411.16160](https://arxiv.org/abs/2411.16160)）把這種 target-biased 模擬器直接稱為 *"simplistic guessing game"*，
並批評評估只看 *"single-turn recall of target items, neglecting the intermediate processes of preference elicitation"*。
**這段話逐字描述我們的 T5。** 重點不是丟掉 T5，而是：**T5 的模擬使用者不聽系統問什麼**（揭露順序寫死），
所以任何提問策略的提案都不能只用 T5 驗收——P2 的實驗必須先改這一點。

**2.7 複合批評會被靜默吃掉。** `FeedbackState.critique` 是**單一物件**不是 list，`apply_round` 每遇到一個
`CritiqueOp` 就 `req.feedback.critique = Critique(...)`——**同一輪第二條批評覆蓋第一條**，
只有 `required_values` 累積，`direction` 直接消失。「這件，但換成海軍藍，而且要更休閒」會丟掉後半句，
而且不會出現在 `rejected_ops` 裡（它通過了驗證），使用者與評審都看不到。

### 提案 P3：ENGINE 03 的 `reasoning` 納入事實檢查（🥈）

這一項不屬於下面任何一個文獻主題——它直接來自 §2.4 的程式稽核，所以放在這裡。
(a) **機制**：把 ENGINE 02 回應的 `contributions[]`／`facts[]`／ledger 當成**允許清單**，
`Engine3Response.reasoning` 與 `generation_prompt` 走 `explain.verify_paraphrase`：引用了清單外的數字或標籤就
**退回模板版本**（由 ledger 逐條生成「你說 X → 我做了 Y」），並在回應標 `reasoning_source="template"`。
(b) **最強公開數字**：沒有外部引用，也不需要——可引的是**我們自己的**：§3.19b 的 LLM 幻覺率量法
（不需要 API key）、§0 記載本地 Qwen3-1.7B 會把「盛夏偏熱」講反、§3.4 的忠實度檢查（隨機理由只有 12–16% 足以）。
(c) **成本**：一個函式呼叫 ＋ 一條模板降級路徑 ＋ 一個測試。延遲 <1 ms。**一小時。**
(d) **可加總？** ✅ 它本身不是分數項；它是**保護**可加總性的機制——確保畫面上的字不會宣稱分數分解裡沒有的東西。
(e) **判定：SHIP。**
(f) **殺掉它的實驗**：用 `scripts/eval_llm_paraphrase.py` 的同一套量法，跑 N 段真實回饋，量
**(i) 幻覺率**（`reasoning` 引用了 `facts[]` 以外的數字／標籤的比例）與 **(ii) 退回模板的比例**。
**若 (i) 本來就是 0，這個提案是多餘的，不要做**；若 (ii) 高到讓 `reasoning` 幾乎總是模板，
那就應該**直接拿掉 LLM 的 `reasoning`**，而不是保留一個永遠被否決的路徑——兩種結果都是有用的結論。

---

## 3. 對話式推薦／偏好誘導：問什麼、什麼時候停

| 方法 | 場域／年份 | URL | 最強公開數字 |
|---|---|---|---|
| CRM（Sun & Zhang） | SIGIR 2018 | [1806.03277](https://arxiv.org/abs/1806.03277) | **線上真人 208 段對話：成功率 28.85% vs MaxEnt 22.12%，平均輪數 3.79 vs 4.58** |
| EAR（Lei, He, Miao et al.） | WSDM 2020 | [2002.09102](https://arxiv.org/abs/2002.09102) | LastFM SR@15 **0.429 vs CRM 0.325**（+32% 相對），AT 13.43→12.45；**拿掉 entropy 狀態特徵 SR@15 掉到 0.346（−19.3%）** |
| SCPR ／ **UNICORN**（Deng, Li, Sun et al.） | KDD 2020 ／ **SIGIR 2021**（不是 KDD） | [2007.00194](https://arxiv.org/abs/2007.00194) ／ [2105.09710](https://arxiv.org/abs/2105.09710) | SCPR LastFM SR@15 0.465 vs EAR 0.429；**UNICORN 0.535**、AT 12.86→11.82；**線上電商 SR@15 +18%、AT −2 輪、hDCG +30%** |
| Qrec（Zou, Chen & Kanoulas） | SIGIR 2020 | [2005.14255](https://arxiv.org/abs/2005.14255) | 10 題後 Recall@5 **0.943 vs NeuMF 0.222**；原文「reaches very good performance already, within the first 10 questions」；真人平均答 15 題、**中位數 5 秒/題** |
| Q&R（Christakopoulou et al.） | KDD 2018 | [10.1145/3219819.3219894](https://doi.org/10.1145/3219819.3219894) | YouTube 線上 **通知開啟率 >+1%**。⚠️ 它只做「一輪對話的兩個階段」，**不處理何時停止**，不要拿來當停止準則的引用 |
| ConUCB（Zhang, Xie, Li & Lui） | WWW 2020 | [1906.01219](https://arxiv.org/abs/1906.01219) | 唯一**帶定理的「多久問一次」旋鈕**：conversation-frequency function b(t)；提問把 regret 的 `d·log T` 項降成 `d + log T` |
| COPE／InPE（Xia, Zhang & Wang） | **SIGIR 2026** | [2607.06765](https://arxiv.org/abs/2607.06765) | 「最佳提問策略是**階段相依**的：早期問屬性，偏好變清楚後問商品」 |
| iEvaLM（Wang, Tang, Zhao et al.） | EMNLP 2023 | [2305.13112](https://arxiv.org/abs/2305.13112) | ChatGPT 在 ReDial 上 Recall@10 **0.174 → 0.570**（五輪互動，摘要宣稱，見 §11） |
| 決策樹 CRS（Haque & Wang） | arXiv 2022 | [2208.14614](https://arxiv.org/abs/2208.14614) | 用**候選集的商品多樣度當提前停止準則**；宣稱勝過深度 RL SOTA（數字未取得） |

**政策問題的答案：有可辯護的規則，而且 EAR 把它寫成三句話。** 原文：*"A good timing to push recommendations
should be when 1) the candidate space is small enough; when 2) asking additional questions is determined to be less
useful or helpful, from the perspective of either information gain or user patience; and when 3) the RC is confident
that the top recommendations will be accepted."* **這三個條件我們都算得出來，而且都已經在記憶體裡**：
(1) `ConstraintReport.n_after_filter`；(2) 後驗變異數縮減（§2.5 的 `cov`）；
(3) 後驗標準差／top-1 與 top-6 的分數差（§3.25 已量到中位數 0.496）。
**它買到了什麼**：EAR 的 entropy 狀態特徵消融是最接近的證據——拿掉它 SR@15 −19.3%。
但 EAR／UNICORN 都是訓練在數萬段對話上的 **RL policy**；我們是 4 輪、一個人，**學不起來**，只能做規則版。

### 提案 P2：把「該問哪一軸／該不該再問」變成三個查得到的數字

(a) **機制**：每輪 `service._learn_preferences` 把 `upd.cov` 一起回傳；`GET /profile/questions` 的選題邏輯
（已存在，依商品庫離散度＋軸間相關性 <0.5 挑軸）改成吃後驗變異數，回傳**一題**成對圖片二選一。
停止規則＝EAR 三條件的門檻版：候選池 < N、或最大後驗標準差 < τ、或 top1−top6 分數差 > δ 就**不問，直接出卡**。
(b) **最強公開數字**：UNICORN 線上電商 SR@15 +18%／AT −2 輪；EAR 拿掉 entropy 特徵 −19.3% 相對 SR@15。
(c) **成本**：`cov` 已算好，選題重用既有 `panels.profile_questions`，延遲 ≈0（`/rank` 12.8 ms 不變）；
真正的成本在**前端多一個問句元件**與 demo 腳本多 10 秒。工程約 1 檔案 + 1 端點。
(d) **可加總？** ✅ 問句本身不進分數；答案走既有 `ProfilePrior`／`design_adjust_steps`，
加法不變式完全不動。**「我們為什麼問這一題」本身也是一個可核對的數字**（該軸的後驗標準差），這是額外的解釋素材。
(e) **判定：MEASURE FIRST。**
(f) **殺掉它的實驗**：改寫 `t5_feedback`，讓模擬使用者**只回答系統問的那一軸**（而不是固定順序揭露），
跑三個 arm：`ask_maxvar`（問後驗變異數最大軸）／`ask_fixed`（現行固定順序）／`ask_random`（隨機挑軸）。
指標＝4 輪內找到目標的比例與平均輪數，配對置換檢定。
**若 `ask_maxvar` 贏不過 `ask_random`，提案就死**——那代表贏的是「有問」而不是「問對」，
和 §3.32 開場三題被 `p3_shuffled` 複製掉四分之三是同一個陷阱。

---

## 4. 批評（critiquing）：單一 vs 複合

| 方法 | 場域／年份 | URL／DOI | 最強公開數字 |
|---|---|---|---|
| 動態批評／複合批評生成（機制） | Reilly et al., ECCBR 2004 pp. 763–777 ／ McCarthy et al., AH 2004 pp. 176–184 | [_55](https://doi.org/10.1007/978-3-540-28631-8_55) ／ [_21](https://doi.org/10.1007/978-3-540-27780-4_21) | 機制論文，本身沒有可引的輪數 |
| **複合批評的真人試驗** | **AAAI 2005 / IUI 2005**，經 Chen & Pu, UMUAI 22(1–2):125–150, 2012 轉述 | [10.1007/s11257-011-9108-6](https://doi.org/10.1007/s11257-011-9108-6) | **38 位真人：使用者主動選複合批評時，互動輪數從 29 降到 6**（−79%）；Incremental Critiquing **省下至多 34% 的互動輪數** |
| 潛在線性批評 LLC（Luo, **Sanner, Wu**, Li, Yang） | WWW 2020 | [10.1145/3366423.3380003](https://doi.org/10.1145/3366423.3380003) | BeerAdvocate **SR@5 0.2847（UAC）→ 0.3391（LP1）**，+19.1% 相對，CI 不重疊；平均會話長度@5 **5.39 → 4.99 輪** |
| M&Ms-VAE（Antognini & Faltings） | RecSys 2021 | [2105.00774](https://arxiv.org/abs/2105.00774) | 批評處理**快至 25.6×** |
| CIReVL（Karthik, Roth, Mancini & Akata） | **ICLR 2024** | [2310.09291](https://arxiv.org/abs/2310.09291) | **免訓練**，CIRCO mAP@5 **18.57 vs SEARLE 11.68**（+59% 相對） |
| MulVec（Zhang, Wu, Liu et al.） | **arXiv preprint，2026-08-26，未經同儕審查** | [2608.25305](https://arxiv.org/abs/2608.25305) | 摘要宣稱 CIRCO mAP@5「up to +23.0%」 |

**我們已經有什麼（§3.33）**：三具名角色（你要出現的／你要保留的／你要消失的），ΔNDCG@10 +0.0635（p=0.00005），
而且「只有三角色、拿掉硬條件」會掉 −0.1159——角色項補的是硬條件之外那半句。**這一塊做得比文獻還誠實。**

**真正額外的只有一件事：複合批評。** 上表最大的效果量（29 → 6 輪）來自**單一批評 vs 複合批評**，
不是來自向量怎麼融合。而我們的 `Critique` 是 `Literal` 單屬性＋單 `to_value`，`FeedbackState.critique` 是單一物件，
同輪第二條會靜默覆蓋（§2.7）。**MulVec 的引用要降級**：它是 3 週前的未審查 preprint，
§3.33 目前的寫法（「MulVec 的角色拆分指出…」）在方法論審查下會被問「這篇過審了嗎」，答案是沒有。
建議改寫成「我們的三角色拆分**獨立於** MulVec（preprint, 2026）提出的同一個觀察，而我們自己量了 600 triplet」。

### 提案 P4：複合批評當成一個具名的多條件 op

(a) **機制**：`FeedbackState.critique` 改成 `list[Critique]`（或至少在 `apply_round` 偵測到第二條時進 `rejected_ops`
而不是靜默覆蓋）；卡片上把每一條批評顯示成**各自一行、各自一個貢獻值**，三角色 × k 條批評 = 3k 個具名項。
(b) **最強公開數字**：互動輪數 **29 → 6**（38 位真人，AAAI/IUI 2005，經 Chen & Pu UMUAI 2012）；
LLC 的 SR@5 +19.1%／會話長度 5.39 → 4.99 輪。
(c) **成本**：每多一條批評多兩次文字編碼。§3.33 實測單條批評 13.9 ms → 27.0 ms，所以 3 條約 55 ms，
仍遠在 1.5 秒預算內。工程：contract 改 list ＋ `service._apply_critique` 迴圈 ＋ `composer` 多值合併。**半天。**
(d) **可加總？** ✅ 三角色本來就精確加總等於總分（§3.33 已有測試釘住）；k 條批評只是 3k 個項，不變式不動。
(e) **判定：MEASURE FIRST。**（覆蓋 bug 本身應該**立刻修成 `rejected_ops`**，那是 SHIP；擴成真正的多條批評才需要量。）
(f) **殺掉它的實驗**：`scripts/eval_composed.py` 現成的 600 triplet 改成 **double-critique triplet**
（同時換顏色＋換場合）。arm：`single_last_wins`（現行）／`single_first_wins`／`compound`。
指標 ΔNDCG@10 ＋ 兩個屬性的**同時**滿足率，配對置換檢定 20,000 次。
**若 `compound` 的 NDCG@10 不顯著勝過 `single_last_wins`，或同時滿足率沒有明顯提升，就不做。**
第二個殺手：若加第二條批評讓候選池歸零的比例上升（因為 `required_values` 疊了兩個永不放寬的條件），
它就必須和 P1 綁在一起才能上，不能單獨上。

---

## 5. 隱性訊號：沒有 live telemetry 時還剩下什麼

| 訊號／方法 | 場域／年份 | URL／DOI | 最強公開數字 |
|---|---|---|---|
| 停留時間 dwell（Yi, Hong, Zhong et al., Yahoo Labs） | RecSys 2014 | [10.1145/2645710.2645724](https://doi.org/10.1145/2645710.2645724)／[PDF](http://www.hongliangjie.com/publications/recsys2014.pdf) | 離線最好的一列：dwell 當**樣本權重** MAP 0.4111→**0.4232**（+2.9% 相對）、NDCG@10 0.5680→0.5820。**線上數字作者刻意不公開**，原文：*"Without disclosing the absolute numbers"* |
| 跳過 skip（Brost, Mehrotra & Jehan, Spotify） | WWW 2019 | [1901.09851](https://arxiv.org/abs/1901.09851) | **1.6 億段聆聽 session／約 370 萬首曲目**；其中一個子集是**刻意用均勻隨機策略**收的，專為反事實評估。WSDM Cup 2019 最佳跳過預測 **MAA 0.648** |
| 位置偏差／眼動（Joachims, Granka, Pan et al.） | SIGIR 2005 | [PDF](https://www.cs.cornell.edu/people/tj/publications/joachims_etal_05a.pdf) | Phase I **34 人招募、29 人資料可用**。Table 4：`Click > Skip Above` 的成對偏好準確率 **80.8% ± 3.6**（隨機 50%，人類評審者間一致度 89.5% 是上界）；在排序被打亂（79.6%）與反轉（83.0%）下仍然穩定 |
| Unbiased LTR（Joachims, Swaminathan & Schnabel） | WSDM 2017 | [1608.04468](https://arxiv.org/abs/1608.04468) | arXiv 搜尋線上 interleaving：Propensity SVM-Rank **87 勝 48 負（p=0.001）** 勝過手工生產排序器；訓練只用了 **5,437 次點擊**、驗證 1,755 次 |
| **明確 dislike vs 推論負例**（Xie, Ling, Wang et al., **騰訊**） | **IJCAI 2020** | [PDF](https://www.ijcai.org/proceedings/2020/0349.pdf) | **DIN 0.7147 → DIN+ 0.7749**（同一個模型，只多加一條明確 dislike 的 loss）；明確 dislike 只佔全部回饋的 **0.15%**；線上 A/B **87 萬人**：CTR +1.17%、**dislike-through rate −33.17%** |

**我們已經有的**：眼動加權曝光機率 ε=(1.00, 0.85, 0.71, 0.47, 0.37) 進新鮮度項（§3.23），
而且 §3.25 證明了加權**有價值**（同權重下改成平權曝光，效用從 2.313 掉到 2.094）。

**兩件新事實**：

**(1) ⚠️ 我們的 ε 來自一張沒有公布數值的圖，而同一篇論文有一張有數值的表。**
本次核實比 `implicit-negative-feedback.md` §8 的自陳更嚴重：**Joachims 2005 的 Figure 1 在正文與所有表格裡
都沒有對應數值**，只有 0–80% 的軸。但 **Table 2 是有數值的**：點擊排名 1 時看過排名 1–5 的比例是
**90.6 / 56.8 / 30.2 / 17.3 / 8.6**——比我們用的曲線**陡得多**（雖然它條件在點擊位置上，不能直接當 ε）。
這給我們一個**零成本的穩健性檢查**，不是一個新功能。

**(2) 「明確問」可以直接繞過我們判定為不可辨識的那個問題。**
§3.23 的核心困難是「沒被選＝沒看到 ∪ 看到但不喜歡」無法分離，而那是決定性排序的結構問題，
**再多模擬使用者也不會解決它**。DFN 的 DIN → DIN+ 消融給出文獻上最乾淨的反向答案：**只要拿到明確的負回饋，
同一個模型的 dislike AUC 就從 0.7147 跳到 0.7749，而那個訊號只佔全部回饋量的 0.15%。**
少量的明確訊號 ≫ 大量的推論訊號。我們的 `rejected_item_ids` 記了「哪一件」**但沒記「為什麼」**——最便宜的那一格。

**dwell 與 skip：REJECT。** 沒有 live telemetry，而且**模擬器產不出停留時間**（`t5_feedback` 與
`eval_preference.py` 的模擬使用者都是一次性 Boltzmann 選擇，沒有時間維度）。加一個永遠是 `None` 的欄位不是功能。
IPS／SNIPS／DR／regression-EM／intervention harvesting 已在 `implicit-negative-feedback.md` §2 判死，不重複。

### 提案 P5：否決要附理由（reason-tagged rejection）

(a) **機制**：新增 `RejectOp{item_id, reason: attribute:value | design_element | "just_no"}`；UI 上按「不喜歡」
時跳一排 chips（顏色／版型／太正式／太花…），選了就走**既有**路徑——屬性理由進 `excluded_values`（硬條件）、
設計軸理由進 `stated_design_steps` −1 步，沒選就退回現行的相似度懲罰。
卡片文案是事實陳述：「你說第 2 件『太正式』，所以正式感 −1 步（−0.25）」，而不是對使用者口味的推論。
(b) **最強公開數字**：DIN → DIN+ dislike AUC **0.7147 → 0.7749**，而明確 dislike 只佔回饋量的 **0.15%**
（Xie et al., IJCAI 2020，騰訊）；同篇線上 87 萬人 dislike-through rate **−33.17%**。
(c) **成本**：contract 1 個 op、前端 1 排 chips、後端**完全重用** `negation.py` 與 `design_adjust_steps` 路徑。
延遲 0（不多做任何編碼）。**半天。**
(d) **可加總？** ✅ 而且比現況**更**可分解：現在「否決」只產生一個匿名的 `penalty` 項
（`GROUP_LABEL["penalty"] = "和你否決過的商品不同"`），加了理由之後它變成一個具名的設計軸項或一條硬條件，
歸因走 §3.36 已經釘住的區分：**「你這句話裡說的」而不是「你上一輪的回饋」**。
(e) **判定：MEASURE FIRST。**
(f) **殺掉它的實驗**：`t5_feedback` 加兩個 arm：`reject_plain`（現行）vs `reject_reasoned`，
模擬使用者否決時**只有 p 的機率給出正確的理由屬性**，其餘給錯（掃 p ∈ {1.0, 0.7, 0.5}）。
指標：4 輪成功率、空結果率、`match_score`（本輪意圖／上一輪意圖各評一次）。
**殺掉它的條件**：若在 p=0.5 時 `reject_reasoned` 比 `reject_plain` 差，提案必須降級成
「理由只進設計軸 −1 步，**永遠不進硬排除**」——因為 §3.35 的排除是**永不放寬**的，
把一個猜錯的理由變成永不放寬的硬條件是我們已知最危險的操作，而且它會直接餵給 P1 的矛盾偵測。
**若連降級版在 p=0.7 都贏不了，就不做。**

**順手的穩健性檢查（不是提案，是一次重跑）**：`scripts/eval_freshness.py` 已支援 `--flat-exposure` 與
`ArmConfig.exposure_weights` 覆寫。用 Joachims 2005 **Table 2**（有數值）推一條較陡的 ε 重跑 w-sweep，一次 job。
若 §3.23 的結論（w=0.5 時新穎度 0.237、最佳卡片效用 +0.18）在較陡的曲線下翻掉，簡報就必須把
「我們借了一條已發表的曲線」改成「我們借了一條**讀圖近似**的曲線，而它很敏感」。**這不加功能，只把已知弱點量出來。**

---

## 6. 偏好漂移與矛盾：第 3 輪推翻第 1 輪

**先講結論：這是一塊薄文獻，而我們正好站在洞口上。**

| 主題 | 出處 | 能給我們什麼 |
|---|---|---|
| 概念漂移的遺忘機制分類（滑動視窗／指數衰減／漂移偵測） | Gama, Žliobaitė, Bifet et al., **ACM Computing Surveys 46(4):1–37, 2014**, [10.1145/2523813](https://doi.org/10.1145/2523813) | **分類法**，不是數字論文 |
| 近因加權（時序動態／時間加權 CF） | Koren, **KDD 2009** [10.1145/1557019.1557072](https://doi.org/10.1145/1557019.1557072)（CACM 2010 版 [10.1145/1721654.1721677](https://doi.org/10.1145/1721654.1721677)）；Ding & Li, **CIKM 2005** [10.1145/1099554.1099689](https://doi.org/10.1145/1099554.1099689) | 機制的經典引用。**兩篇的數字本次都核實不到（付費牆），不要引數字**（§11） |
| 模糊／雜訊回饋的使用者模擬器；把矛盾列為挑戰的綜述 | Shen, Wu, Zhang et al., **ACM TORS 2023**, [10.1145/3616379](https://doi.org/10.1145/3616379)；Gao, Lei, He et al., **AI Open 2021**, [10.1016/j.aiopen.2021.06.002](https://doi.org/10.1016/j.aiopen.2021.06.002) | 最接近「使用者回答不一致」的真實建模；綜述提出挑戰但**沒有矛盾指標** |
| **不一致需求的診斷與修復** | **FastDiag**：Felfernig, Schubert & Zehentner, **AIEDAM 26(1):53–62, 2012**, [2102.09005](https://arxiv.org/abs/2102.09005)；WeeVis 直接診斷與修復環境：Felfernig et al., **DX 2014**, [2102.12327](https://arxiv.org/abs/2102.12327) | **這才是對的文獻家族。** 原文：「in such situations we are in the need of techniques that support the identification of **minimal sets of faulty constraints that have to be deleted in order to restore consistency**」 |
| 可讀、可編輯的使用者側寫 | Ramos, Rahmani, Wang et al., **ACL 2024**, [2402.05810](https://arxiv.org/abs/2402.05810) | 定性證據：讓使用者看到並編輯自己的側寫 → 「greater autonomy over users' received recommendations」。**沒有可引的數字** |

**「近因 vs 一致性」有沒有原則性的答案？有，但要分成兩層，而文獻把它們混為一談。**
(1) **口味是連續的 → 近因加權**（Koren／Ding & Li／Gama 的指數衰減）。我們的 `choice_history` 目前**完全無衰減**：
Bradley–Terry likelihood 對所有輪一視同仁，`design_adjust_steps` 是純累加（±3 clamp），第 1 輪的 +1 與第 3 輪的 −1
剛好抵銷。這在 4 輪內**大概是對的**，而且有 §3.12 的 κ=1 縮減撐著。
(2) **硬條件是離散的 → 不能衰減，只能診斷。** 「不要黑色」不是會慢慢淡掉的權重，是布林約束；
對布林約束，正確操作是**算最小衝突集並提出修復**（FastDiag）。**我們的程式正好是這個家族的實例**：
`excluded_values`/`required_values` 是約束集，`build_mask` 是一致性檢查，`n_after_filter == 0` 是 over-constrained 的信號。

**我找不到的東西（要照講）**：沒有任何一篇論文做到「在推薦對話中偵測使用者推翻自己 → 主動請使用者裁決 → 回報數字」。
這是真空。所以 P1 的定位是**「把 constraint-based recommender 的標準做法搬進對話式推薦」**，
不是「我們發明了新方法」——後者站不住，前者站得住而且有引用。

### 提案 P1：矛盾偵測與具名修復（🥇 先做這一個）

(a) **機制**：每次 `apply_round` 之後跑一次一致性檢查——對每個屬性算
`required_values[attr] ∩ excluded_values[attr]`（以及色系展開後的交集，因為 §3.35 的排除是整個色系），
非空就是一個**最小衝突集**（我們的約束是扁平的值集合，所以衝突集就是交集本身，不需要 FastDiag 的分治）。
不自動解決，而是產生一個 `ConflictReport{attribute, value, excluded_at_round, required_at_round, 原話 quote 兩句}`，
UI 顯示一句：**「你第 1 輪說『不要黑色』，這一輪說『要黑色』。我先照最新的做，並把第 1 輪那條標成已撤回——不對的話按這裡改回來。」**
預設策略＝**近因優先**（撤回舊的那一條），因為對硬條件而言這是唯一能保證候選池非空的選擇，而且它是可被使用者一鍵推翻的。
同時新增 `RetractOp`（或讓 `ExcludeOp` 接受 `retract: bool`）把撤回寫成一個**在 ledger 裡看得見的操作**。
(b) **最強公開數字**：沒有可引的效果量——這是真空（見上）。能引的是**機制的正當性**：FastDiag 明文說
over-constrained 的處置是「identification of minimal sets of faulty constraints that have to be deleted to restore consistency」
（AIEDAM 2012）；以及我們**自己**量得出來的數字：目前這條路徑下候選池 = 0、卡片 = 0。
(c) **成本**：純規則、零估計器。`O(屬性數 × 值數)` 的集合交集，**延遲 <0.1 ms**。
工程：`handshake.py` 加一個檢查函式 ＋ `ConstraintReport` 加一個欄位 ＋ `panels.round_diff` 把
`constraints_removed` 接上（它已經存在、目前永遠是空的）＋ ENGINE 03 contract 加一個 op。**半天到一天。**
(d) **可加總？** ✅ **它完全不碰分數**。它改的是候選池與 ledger，和 §3.15 趨勢關鍵字「不進排序、只當展示」、
§3.35 替代品「是報告不是排序決定」同一個處理原則。加法不變式零風險。
(e) **判定：SHIP。**
(f) **殺掉它的實驗**：寫一個 `eval_contradiction.py`：從 `kagl_polyvore_filled` 取 N 句查詢，
第 1 輪硬排除某個值、第 3 輪用 `CritiqueOp` 要求同一個值，量三個 arm：
`current`（現行）／`retract_old`（近因優先，提案）／`retract_new`（一致性優先）。
指標：**空結果率**、4 輪內找到目標的比例、`match_score`（用本輪意圖與上一輪意圖各評一次，§3.36 的防作弊）。
**殺掉它的條件有兩個**：(i) 若 `current` 的空結果率本來就是 0（代表我對 `build_mask` 的讀法錯了），整個提案作廢；
(ii) 若 `retract_old` 與 `retract_new` 在找到目標的比例上沒有差別，那「該撤哪一條」就沒有內容，
應該降級成**只報告不決定**（顯示衝突、讓使用者選），而不是宣稱我們有一個聰明的策略。
第 (ii) 種結果**仍然值得上**，但簡報話術必須跟著改。

### 提案 P6：`choice_history` 的指數衰減

(a) **機制**：Bradley–Terry likelihood 對第 t 輪的 `ChoiceRound` 乘上 `ρ^(T−t)`（ρ∈(0,1]，ρ=1 = 現狀）；
卡片上「你上一輪的回饋」那一格拆成「最近一輪」與「較早幾輪」兩個 need share。
(b) **最強公開數字**：Gama et al. (CSUR 2014) 的遺忘機制分類法；Koren KDD 2009／Ding & Li CIKM 2005
的近因加權傳統。**這三個我都沒拿到可引的數字**（§11），所以誠實說法是「文獻支持這個機制存在，但我引不出效果量」。
(c) **成本**：`preference.py` 的 likelihood 多一個權重向量，**<1 ms**。工程：1 個參數 + 1 個 arm。**一小時。**
(d) **可加總？** ✅ 仍然是 Δβ，和 §3.7 的 hook 完全一樣。
(e) **判定：MEASURE FIRST。**
(f) **殺掉它的實驗**：`scripts/eval_preference.py` 現成的 200 人 × 5 輪，加一個**口味會在第 3 輪翻轉**的
模擬使用者變體（現在的模擬使用者口味是固定的，所以**現行實驗結構上量不到這件事**），掃 ρ∈{1.0, 0.8, 0.5}。
**若在口味固定的使用者上 ρ<1 顯著變差，而在口味翻轉的使用者上贏不到顯著，就不做**——
那代表我們只是在付一個沒有回報的保險費。這個提案最大的風險是：4 輪之內衰減根本來不及發揮作用，
κ=1 縮減（§3.12）已經把第 1 輪的影響力砍半了，兩者可能在打同一場仗。

---

## 7. Bandit／主動學習：我們已經量過，而且文獻站在我們這邊

| 方法 | 場域／年份 | URL | 最強公開數字 |
|---|---|---|---|
| LinUCB（Li, Chu, Langford & Schapire） | WWW 2010 | [1003.0146](https://arxiv.org/abs/1003.0146) | Yahoo! 首頁 **3,300 萬次事件，+12.5% click lift**。但：**資料降到 1% 時，disjoint 版 learning bucket 的 lift 從 24.2% 掉到 5.1%**；只有跨 arm 共享特徵的 hybrid 版才撐得住 |
| Thompson Sampling（Chapelle & Li） | NIPS 2011 | [proceedings](https://papers.nips.cc/paper_files/paper/2011/hash/e53a0a2978c28872a4505bdb51db06dc-Abstract.html) | 延遲 δ=1000 時 UCB regret 是 TS 的 **3.82×**。但同一篇：**exploit-only 的 CTR regret 5.00% 與 ε-greedy 的 4.98–5.22% 難以區分**，作者原文「Exploit-only does pretty well」；且「the regret in the first hour is large, around 0.3, because the algorithms predict randomly (no initial model provided)」 |
| OFUL regret bound（Abbasi-Yadkori, Pál & Szepesvári） | NIPS 2011 | [proceedings](https://papers.nips.cc/paper_files/paper/2011/hash/e1d5be1c7f2f456670de3d53c7b54f4a-Abstract.html) | `R_n ≤ 4√(n·d·log(λ+nL/d))·(λ^½S + R√(2log(1/δ)+d·log(1+nL/(λd))))`，即 **Õ(d√n)** |
| 互動式推薦的 Thompson Sampling（Christakopoulou, Radlinski & Hofmann） | KDD 2016 | [PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/06/rfp0063-christakopoulou.pdf) | 摘要原文：**「improving personalized recommendations over a static model by 25% after asking only 2 questions」** |
| ConUCB（Zhang, Xie, Li & Lui） | WWW 2020 | [1906.01219](https://arxiv.org/abs/1906.01219) | 提問把 regret 的 `d·log T` 項降成 `d + log T` |

**我們自己的數字比文獻更直接**（§3.7、`recsys-preference.md`，200 位模擬使用者 × 5 輪、配對置換檢定）：
Bayes − Thompson **+0.13（5k, p=0.001）／+0.02（44k, p=0.67）**；Bayes − LinUCB **+0.03（p=0.30）／−0.03（p=0.30）**。
而且 LinUCB 的探索加分是**商品層級**的，拆不成 Δβ，**會直接破壞「貢獻加總＝總分」**——一票否決。

**d=11、T=4 時 bound 是空的（這是我的推導，不是論文宣稱）**：n=4、d=11 時，OFUL bound 的前置因子
`4√(n·d·log(...)) ≥ 4√44 ≈ 26.5`，而 4 輪內獎勵落在 [−1,1] 的**最大可能** regret 只有 8。
**保證值比最壞情況還大三倍以上，等於什麼都沒保證。** bound 要變得有意義大約需要 `n ≳ d²`（此處約 121 輪）。
文獻裡**沒有**一篇誠實地寫「bandit 在 4 輪、一個使用者上沒用」——最接近的是 Chapelle & Li 的
exploit-only ≈ ε-greedy，以及 ConUCB 家族「contextual bandit 學得太慢，所以要靠提問補側資訊」的整個前提。

**判定：Thompson／LinUCB REJECT**（已量、無收益、破壞可加總性，§3.7 的結論不需要改）。
**唯一值得看的 bandit 分支是 ConUCB**：它不是拿 bandit 排序，而是拿 bandit 決定**要不要問**——
這一條已經併進 P2，不另開提案。

---

## 8. 業界實際做了什麼（同儕審查 vs 部落格，逐項標示）

`industry-recsys-practice.md` 與 `industry-fashion-brands.md` 已經盤過公司清單，本節**只補回饋迴圈這一格**，
並且把「這是不是論文」這件事逐項標出來——因為這正是方法論審查會問的第一個問題。

| 公司 | 來源 | 類型 | 回饋迴圈相關的最強數字 |
|---|---|---|---|
| **Spotify** | McInerney, Lacker, Hansen et al., *Explore, Exploit, and Explain*, **RecSys 2018**, [10.1145/3240323.3240354](https://doi.org/10.1145/3240323.3240354) | **同儕審查** | 原文：*"Bart provides **more than a 20% improvement in stream rates** compared with statically ordering explanations"*；線上 380 萬 impression／56 萬使用者／23 萬 item，探索率上限 10%。⚠️ 第一作者是 **McInerney**，不是 Mehrotra |
| **Spotify** | Hansen, Mehrotra, Hansen et al., *Shifting Consumption towards Diverse Content*, **WSDM 2021** | **同儕審查** | **摘要沒有任何數字，全文付費牆、無 preprint。不要引數字** |
| **Netflix** | Gomez-Uribe & Hunt, **ACM TMIS 6(4), 2015** | **同儕審查** | 「$1B/年」「80% 觀看來自推薦」——**原文付費牆本次讀不到**，只能透過 Smith & Linden 2017 轉引（該文逐字引述 Hunt） |
| **Netflix** | *Artwork Personalization*：TechBlog 2017 **部落格** ／ Amat, Chandrashekar, Jebara & Basilico, **RecSys 2018 industry track** | 兩者都有 | 部落格**抓不到（403，archive.org 被擋）**；RecSys 2018 摘要是定性的。**兩邊都沒有可引的 lift** |
| **Amazon** | Smith & Linden, *Two Decades of RecSys at Amazon.com*, **IEEE Internet Computing 21(3), 2017**, [PDF](https://cdn.amazon.science/76/9e/7eac89c14a838746e91dde0a5e9f/two-decades-of-recommender-systems-at-amazon.pdf) | **同儕審查（雜誌）** | 「30% 的頁面瀏覽來自推薦」（轉引 MSR 報告）。**回饋迴圈本身沒有任何量化內容**——只有一句設計性質的「item-based CF 會依新資訊立即更新」 |
| **Alibaba** | DIN, Zhou, Song, Zhu et al., **KDD 2018**, [1706.06978](https://arxiv.org/abs/1706.06978)；Virtual-Taobao, Shi, Yu, Da et al., **AAAI 2019**, [1805.10000](https://arxiv.org/abs/1805.10000) | **同儕審查** | DIN 線上 A/B 一個月：**CTR +10.0%、RPM +3.8%**（20 億訓練樣本）。Virtual-Taobao 用「數億筆客戶記錄」建模擬器但**沒有公布線上營收數字** |
| **Zalando** | Wu, Sánchez Rodríguez & Corona Pampín, *Session-based Complementary Fashion Recommendations*, **recsysXfashion'19 workshop**, [1908.08327](https://arxiv.org/abs/1908.08327) | **工作坊** | **線上購買商品數 +3.24%**（2,800 萬活躍客戶）；離線 Orders Recall@5 +8.2% |
| **Zalando** | Sánchez Rodríguez, Wu & Khandwawala, *Two-Stage Session-based Recommendations*, **recsysXfashion'19 workshop**, [1908.08284](https://arxiv.org/abs/1908.08284) | **工作坊** | 線上 **CTR +2.84%（p≤0.05）**。⚠️ 同篇：**STAMP（0.7244）與 NARM（0.6989）在這份時尚資料上都輸給 I2I-CF 基線**——引用 session-based 模型做時尚時要一起講 |
| **Myntra** | Jaiswal, Malayil, Jawaid & Vempati, **fashionXrecsys@RecSys 2023 workshop**, [2309.14046](https://arxiv.org/abs/2309.14046) | **工作坊** | 每人首頁點擊 **+0.24%**；流量規模未揭露，護欄指標未量化——**弱數字，要用就標弱** |
| **Stitch Fix** | Colson, *Using Human and Machine Processing in Recommendation Systems*, **AAAI HCOMP 2013**, [PDF](https://ojs.aaai.org/index.php/HCOMP/article/download/13100/12948) | **同儕審查** | **零量化結果。** 純案例描述：機器排序、單一真人造型師選最後 5 件 |
| **Stitch Fix** | Algorithms Tour ／ MultiThreaded | **部落格／行銷頁** | **零數字。** 只定性描述迴圈（「她留下想要的、退回其餘，然後逐件告訴我們她的想法」） |
| **騰訊** | DFN, Xie, Ling, Wang et al., **IJCAI 2020** | **同儕審查** | 87 萬人線上：CTR +1.17%、**dislike-through rate −33.17%**（見 §5） |

**三句話結論**：

1. **時尚業回饋迴圈最厚的公開記錄是 Zalando 的兩篇 workshop 論文**，數字都是**線上**的（購買 +3.24%、CTR +2.84%）。
   `implicit-negative-feedback.md` §0.1 把它們標成 [T]，本次已逐篇核到原文，可升 [V] 並補上 +2.84%。
2. **Stitch Fix 是最常被引用、也最沒有數字的那一家。** HCOMP 2013 零量化結果，Algorithms Tour 是行銷頁。
   要講「真人在環」就只講機制，**任何 Stitch Fix 的數字都不要引**。
3. **沒有任何一家公開了「使用者的回饋如何讓下一輪變準」的直接量測。** 最接近的是騰訊 DFN 的
   dislike-through rate −33.17%，而那是廣告版面不是造型。所以我們的 T5（4 輪 1% → 39–44%，p<0.001）
   在公開文獻裡**沒有直接對手**——這句話可以講，但同一口氣必須講完「它是規則式模擬使用者，不是真人，也沒有線上 A/B」。
   §3.7 的「我們一個線上 A/B 都沒有」仍是整份報告最大的弱點。

**對 P1–P6 的意義**：業界在這一格給不了效果量，只給得了正當性。所以所有提案的驗收**必須**靠我們自己的模擬器與
配對統計，而這正是 §2.6（PEPPER 對 target-biased 模擬器的批評）必須被認真對待的原因——
**我們的驗收工具就是我們最大的循環性風險來源。**

---

## 9. Top 3（judge-visible value ÷ risk）

| 排名 | 提案 | judge-visible value | risk | 為什麼 |
|---|---|---|---|---|
| 🥇 | **P1 矛盾偵測與具名修復** | **高** | **低** | 台上講得出一句評審一定記得的話（「你第 1 輪說不要黑色，這一輪說要黑色」）；同時**修掉一個會讓現場出現 0 張卡的洞**；純規則、零估計器、不碰分數、延遲 <0.1 ms；文獻家族清楚（FastDiag, AIEDAM 2012）而對話式推薦那一側是真空，所以它**同時是創意分也是穩健分** |
| 🥈 | **P3 ENGINE 03 `reasoning` 的事實檢查** | 中高 | **極低** | 我們整個賣點是「解釋＝分數分解」，而畫面上唯一沒被檢查的字串正是 ENGINE 03 產生的。`explain.verify_paraphrase` 已經存在，套過去是**一個函式呼叫**；驗收就用 §3.19b 那套不需要 API key 的幻覺率量法 |
| 🥉 | **P2 提問策略＋停止準則** | **最高** | 中 | 「知道什麼時候該閉嘴」是全場最有記憶點的一句，而且後驗共變異數**已經算好被丟掉**，成本近乎零。但它需要**先改模擬器**（§2.6）才量得出來，而改模擬器本身有把答案送進題目的循環性風險——所以排第三，不是因為價值低，是因為它的**驗收比做它還難** |

**先做 P1。** 三個理由：(1) 它是唯一一個**不做就會在台上壞掉**的；(2) 它落在既有的 `ConstraintReport` ／
`round_diff` ／ ledger 三個已經上線的機制上，改動面積最小；(3) 它的失敗模式是「量出來發現沒差」，
而不是「上了之後排序變差」——因為它根本不進分數。

**P3 可以和 P1 同一天做完**（它是一個函式呼叫加一個測試），所以實務上是「P1 + P3 當成一包，P2 排下一輪」。

---

## 10. 裝飾品（直說）

| 東西 | 為什麼是裝飾 |
|---|---|
| **Thompson／LinUCB** | 我們自己 200 人 × 5 輪量過，**沒有贏**（p=0.30–0.67），而且探索加分拆不成 Δβ。再做一次只是重複一個 null result |
| **IPS／SNIPS／DR／regression-EM／intervention harvesting** | `implicit-negative-feedback.md` §2 已經把這條路判死：我們的排序是決定性的，propensity 不存在；Agarwal et al. (WSDM 2019) 在**一次 5 筆**的版面上要 877,689 次查詢，我們有 240 個 ranking event |
| **dwell time／skip 訊號** | 我們沒有任何 live telemetry，而且**模擬器產不出 dwell**——沒有真人就是沒有這個欄位。加一個永遠是 `None` 的欄位不是功能 |
| **ENGINE 03 的 `generation_prompt`** | 目前沒有任何檢查、沒有任何驗收指標、也沒有接到量過的東西上。在一個「不能量的東西不能上」的 repo 裡（§3.15／§3.26／§3.27／§3.28／§3.30 同一條標準），它現在就是裝飾 |
| **把 ENGINE 03 的 `reasoning` 直接顯示在畫面上** | 比裝飾更糟，是負債：它是唯一一段沒過事實檢查的字（見 P3） |
| **「這個迴圈會一直跑到使用者滿意為止」** | 程式裡沒有任何對應判斷（§2.2）。這句話目前是文案，不是功能 |
| **把 MulVec 當成三角色拆分的權威來源** | 它是 3 週前的未審查 preprint（§4）。我們自己的 600 triplet 實測（ΔNDCG@10 +0.0635, p=0.00005）比它有說服力得多，主從關係要倒過來寫 |

---

## 11. 我無法核實的部分

**本 session 的 WebSearch 配額在開工前已用盡（200/200）**；所有核實都靠 WebFetch（arXiv abs／export.arxiv.org API／
ar5iv／NeurIPS proceedings PDF／OpenAlex／Semantic Scholar）。ACM DL、Springer、CACM、dblp 對本機回 403/404。

**完全沒拿到數字、不要在簡報引數字的**（括號內是原因）：
Koren KDD 2009／CACM 2010 的 timeSVD++ Netflix RMSE（付費牆；常見的 0.8799 **我沒核實**）；
Ding & Li CIKM 2005 的改善幅度（付費牆）；Deep Critiquing SIGIR 2020 的任何數字（付費牆，摘要無數字）；
ConUCB 在 Yelp／今日頭條的實驗數值（只有圖）；Christakopoulou KDD 2016 的分策略數字與使用者研究 N；
Reilly ECCBR 2004／McCarthy AH 2004 各自論文裡的輪數；Kim et al. WSDM 2014 的任何準確率（付費牆）；
Hansen et al. WSDM 2021（Spotify 多樣性）的任何數字（封閉取用、無 preprint）；
Virtual-Taobao AAAI 2019 的任何線上／營收數字；**Stitch Fix 的任何數字**（HCOMP 2013 零量化，Tour 是行銷頁）；
**Netflix 的 $1B/年 與 80%**（TMIS 2015 付費牆，只能經 Smith & Linden 2017 轉引）與
**artwork personalization 的任何 lift**（部落格 403、RecSys 2018 摘要無數字）。

三個需要特別說明的：
- **Yi et al. RecSys 2014 的線上 lift**——**不是我們查不到，是作者刻意不公布**（原文 *"Without disclosing the
  absolute numbers"*）。只有離線的 MAP 0.4111→0.4232 可引。
- **Joachims 2005 Figure 1 的逐位置注視比例**：本次確認 **Fig 1 是一張沒有公布數值的條形圖**，正文與所有表格
  都沒有對應數字。我們 `ArmConfig.exposure_weights` 的 (1.00, 0.85, 0.71, 0.47, 0.37) 是讀圖近似
  （`implicit-negative-feedback.md` §8 已自陳）。**有數值的是 Table 2**，而且更陡（90.6/56.8/30.2/17.3/8.6），
  但它**條件在點擊位置上**，不能直接當 ε——所以 §5 只把它當敏感度檢查，不換預設值。
- **「明確問使用者為什麼不喜歡」**：本次**未查到**任何有數字的已發表研究（cs.IR 上 0 命中，但 WebSearch 不可用，
  應說「未查到」而非「不存在」）。P5 唯一可引的是 DFN 內部的 DIN vs DIN+ **消融**，要當消融引。
  同理 **「偵測使用者推翻自己」是真空**（§6），P1 不得宣稱有文獻效果量支持。

**引用歸屬的更正（我們自己文件若要引，請照這個寫）**：
- **「29 → 6 輪」屬於 McCarthy et al., AAAI 2005 與 IUI 2005**，不是 2004 那兩篇；我是從 Chen & Pu,
  UMUAI 22(1–2):125–150, 2012 的全文轉述取得（逐字為 "the total number of recommendation cycles decreases
  from 29 to 6"，38 位受試者）。**我沒有打開 AAAI 2005 原文。**
- **LLC 的作者順序是 Luo, Sanner, Wu, Li, Yang**；**UNICORN 是 SIGIR 2021** 不是 KDD；
  **Spotify bandits 第一作者是 McInerney** 不是 Mehrotra（Mehrotra 是第七作者）。
- `implicit-negative-feedback.md` §0.1 的兩篇 Zalando 目前標 **[T]**，本次已核到原文可升 **[V]**，
  並可補上 1908.08284 的 **線上 CTR +2.84%（p≤0.05）** 與「STAMP／NARM 輸給 I2I-CF」這個反面結果。

**單一來源、信心較低的數字**：CIReVL 的 CIRR／FashionIQ／CIRCO 表值只從 arXiv HTML render 取得（書目可靠、
表值請再核）；M&Ms-VAE 的 7.5×／3.1×／5.3× 是單一來源（只有 25.6× 雙來源確認）；
**iEvaLM 的 0.174 → 0.570** 是摘要宣稱，表 5 的自由對話列是 0.440——要引就引成「摘要宣稱」，
且該論文另有一處印出的百分比與自己的數字對不上，**不要轉引那個百分比**；
**MulVec 的任何逐表數字**——抓 `arxiv.org/html/2608.25305v2` 回傳的是**另一篇論文**，只有摘要的 +23.0% 是確認的。

**venue 沒核到的**：Handa et al.（arXiv:2403.05534）、Li et al. *GATE*（arXiv:2310.11589）、
Haque & Wang（arXiv:2208.14614）在 arXiv comments 欄都沒有 venue，**只能當 preprint 引**；
Haque & Wang 我**只取得機制描述、沒有數字**。

**我自己的推導（不是任何論文的宣稱）**：§7 的「d=11、T=4 時 OFUL bound 是空的」是我代數字算的，
**論文沒講過這件事**。要講就要標明是我們的推導。

**基準線數字不可混表**：Abs Greedy／Max Entropy／CRM／EAR 的數字在 EAR 原文與 SCPR／UNICORN 原文之間不一致
（LastFM Abs Greedy 0.209 vs 0.222），因為各自重跑。§3 的表全部取自 UNICORN 那一版，**不要混列**。

**所有工程量與延遲估計**（P1 <0.1 ms、P2 ≈0、P4 約 55 ms、P6 <1 ms）**都是估計，沒有實測**。
所有提案的效果宣稱**都是假設**，六個殺手實驗一個都還沒跑。
