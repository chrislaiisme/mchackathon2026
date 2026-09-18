# ENGINE 02 完整度複審（第二次）：哪些承諾真的有程式＋證據，哪些沒有

> 稽核日期：2026-09-18 晚間｜分支 `engine02-research`｜**稽核基準 commit `fc88439`**
> （`fix(integration): the colour check must allow the colour-family comparator`，2026-09-18 19:04）
> 方法：**不信文件，一律讀程式、開 report 檔、在本機實跑**。沒有動伺服器、沒有跑 GPU。
> 本次只新增這一個檔案，沒有修改任何既有檔案。
>
> **兩個必須先講的免責**：
> 1. 稽核進行中 `engine02/contracts.py` 在 18:56 被 coordinator 改過（commit `28cd8df` 的 shorthand validator）。
>    §3 的整合清單是**改完之後**重跑的結果，所以 shorthand 那幾條已經是最新狀態。
> 2. 我跑 `scripts/api_check.py --catalog data/catalog/kagl --encoder hash` 時，它的預設 `--out`
>    **覆寫了 `reports/server/api_check/*.json`**（原本是 cfda4 上 Marqo＋OT 的驗收結果）。
>    那個目錄在 `.gitignore` 裡、git 沒有受影響，但**伺服器上的那份驗收 JSON 已經被本機 hash 版蓋掉**，
>    要用的話請在 cfda4 重跑一次（約 1 分鐘）。`reports/server/api_check_local/` 沒有被動到。

---

## 0. 先回答三個問題

| 問題 | 答案 |
|---|---|
| §0 有幾條是 stale 或無證據？ | 18 條裡 **3 條**：①BM25 閘門（§3.29）——結論正確但支撐表格混了兩個不同實驗的數字，而且**上線後的端到端數字在 repo 裡找不到任何 report**；②LLM 改寫「講反」的觀察（一次性、無存檔，`reproduce.py` 自己標 MISSING）；③感性表 v1 的文獻編碼（人工，無法機器重現，同樣自標 MISSING）。另有 1 條（卡片內 z-score → 商品池 z-score）是設計決定、**沒有做過對照實驗**。 |
| 最嚴重的整合失效模式 | **`needs` 裡的 `need_id` 對不上感性表時，整批設計要素項會靜靜消失，回應是 200、`input_warnings` 是空的、卡片照樣給出一份「忠實」的分數分解。** 系統賣點的一半（隱性需求）被關掉，而畫面上完全看不出來。 |
| 前三優先 | ①補 §3.22 缺口盤（簡報主標）在真 encoder／44k 上的 report——目前**只有 hash/5k/12 trial、p=0.126 不顯著**的那一份；②未知 `need_id`／未知設計要素要回報成 `input_warnings`；③把 §3.29 表格裡混進來的 hash/5k 數字換掉，並補一份上線後的端到端 report。 |

---

## 1. 承諾 → 程式 → 證據 → 狀態

「證據」欄若是報表路徑，代表我**開檔比對過數字**；若是程式路徑，代表我讀過該行並（在標註處）本機實跑過。

### 1.1 `docs/engine02-design.md` §0 一頁結論（18 條）

| # | §0 的承諾 | 程式在哪 | 證據在哪 | 狀態 |
|---|---|---|---|---|
| 1 | Marqo-FashionSigLIP 為 dense encoder（0.463 vs fashion-clip 0.426） | `engine02/models.py`、`encoders.py` | `reports/server/kagl5k_marqo-fashionSigLIP/t1_summary.csv` dense 0.6144/0.4626；`kagl5k_fashion-clip/` 0.5695/0.4260 | **done**（逐位數相符） |
| 2 | 硬條件用過濾＋固定放寬階梯，並寫進理由 | `constraints.py:22-32,131-151`、`taxonomy.py:454-503` | `reports/ablation/kagl_marqo-fashionSigLIP/t2_constraints.csv`（無放寬列 satisfaction=1.0、有放寬列 0.4 且記 `occasion:drop`） | **done** |
| 3 | 違約時 BM25 閘門把換句話說 0.111 → **0.308**（+0.197, p<1e-5），用詞相同 −0.002 | `config.py:73-89`、`pipeline.py:307-318`、`sparse.py::match_stats` | `reports/server/gate/bm25_gate_kagl_polyvore_filled_marqo-fashionSigLIP.json`：閘門選型與門檻 0.1217 ✅；**但 0.308／0.7338 這兩個端到端數字在 `reports/` 裡不存在**（`reports/server/kaglpoly_filled/t1_summary.csv` 的 `full_zclip3` 仍是**閘門前**的 0.1106／0.7361）。§3.29 訊號表另有兩格取自別的實驗（見 §2.1） | **stale / partial** |
| 4 | c(i,d) 改反義詞成對＋分布正規化 | `concepts.py`、`config.py:34-36` | `reports/ablation/kagl_marqo-fashionSigLIP/t3_concepts.csv`（descriptor 0.9766/0.7215/0.8378/0.8831、random 0.523/0.638/0.484/0.466） | **done** |
| 5 | 理由用最小充分集合（覆蓋率 100%、充分 100%、隨機 16%） | `rerank.py::cutoff_explanations`、`pipeline.py:373-402` | `reports/ablation/kagl_marqo-fashionSigLIP/t4_summary.csv`：full 1.000/1.000/0.160；prd_original 0.805/0.658/0.118 | **done** |
| 6 | γ=1（前 5 換掉 19–26%，NDCG 下降不顯著） | `config.py:64`（`need_scale`） | `reports/server/kaglfull_marqo_t6/t6_summary.csv`：γ=0 0.8371 → γ=1 0.8260（−0.011）、changed 0.264 | **done** |
| 7 | 卡片內 z-score 改成商品池 z-score | `config.py:32`、`pipeline.py:475-479` | 只有 method inventory §11 的論述，**沒有對照實驗**（`full_norm_candidates` arm 存在但 §3 沒有它的表） | **partial（設計決定，無實驗）** |
| 8 | 相容性只在有錨點時啟用，且用商品層級（OutfitTransformer） | `pipeline.py:517-530`、`compat_ot.py` | `reports/server/compat_fitb.json`（200 題：0.25/0.48/0.545）＋`reports/agents/bench/polyvore_compat.json`（n=2000：NPMI 0.250、embedding 0.521、OT 0.6275、互補頭 0.6605） | **done** |
| 9 | 批評回饋大、Rocchio 不顯著；改用 Bayes＋κ=1 | `service.py:65-86`、`preference.py` | `reports/ablation/kagl_marqo-fashionSigLIP/t5_summary.csv`（1/1/1/1、1/3/3/4、1/8/36/39、1/11/36/42）；`reports/agents/preference/{kagl,kagl_full,damping}` | **done** |
| 10 | 理由預設模板，LLM 改寫要過事實檢查（本地 Qwen3-1.7B 曾把「盛夏偏熱」講反） | `explain.py:70-141`、`llm.py` | 程式與單元測試有；**那次觀察沒有存下 prompt／輸出**，`scripts/reproduce.py` 的 CLAIMS 自己標 `MISSING` | **unbacked（已自陳）** |
| 11 | 圖文 reranker 預設不開（用詞相同 0.840→0.797, p=0.001） | `config.py:21,125`、`models.py::CrossEncoderReranker` | `reports/server/kagl5k_marqo-fashionSigLIP/t1_summary.csv`：`full` 0.8401 vs `full_cross_reranker` 0.7968 | **done** |
| 12 | encoder 選型結論（外部四語料八個檢定全勝） | — | `reports/agents/bench/{t2i_kagl,t2i_dfinshop,t2i_hm,t2i_polyvore25k,esci_*}.json`；ESCI 服飾切片 BM25 0.71691／dense 0.76478／RRF 0.75708／convex 0.75318 與 §3.20 逐位相符 | **done** |
| 13 | 材質光澤改用 VLM 標註 | `concepts.py::vlm_design_scores`、`config.py:39-40` | `reports/ablation/visual_label_auroc_with_vlm.csv`、`reports/server/visual_label_auroc_v100_fp16.csv` | **done** |
| 14 | 感性表用有文獻依據的 v1（32 篇、50 個非零格） | `engine02/resources/kansei_v1_literature.json`、`kansei.py` | JSON 內 `sources` 剛好 **32** 筆、K 的非零格剛好 **50** ✅。但文獻編碼是人工的，`reproduce.py` 標 `MISSING`。另注意：**載入後折疊成 15 條正規軸，`KanseiTable.K` 只剩 38 個非零格**——引用「50」時要說明是折疊前 | **partial（數字對，但不可機器重現）** |
| 15 | 補值後四條件查詢放寬比例 92.3% → 3.8% | `attribute_fill.py`、`pipeline.py:122-127` | `reports/agents/classify/cfda4/t2/t2_summary.csv`：relaxation_rate 0.9231 → 0.0385 ✅、satisfaction 0.2923 → 0.9231 ✅。**但同表的「過濾後候選數」報表是 16.31 → 67.46，設計文件 §3.17 寫的是 16.3 → 76.3**（疑似 67.5 打成 76.3） | **done（§3.17 表內一個數字打錯）** |
| 16 | 趨勢關鍵字只當展示標籤，28 組全部變差 | `trends.py::trend_badges`、`api.py:118-125`（**刻意不呼叫** `attach_trends`） | `reports/agents/audit/out/trends_{kagl_full,kagl_polyvore}/`、`trends_clip_*/` | **done** |
| 17 | 概念圖 w=0.2 融入查詢（無圖時 no-op） | `config.py:27,113`、`pipeline.py:240-242` | `reports/agents/audit/out/concept_image_kagl_full/t12_summary.json` | **done** |
| 18 | `/complete-look` 用 OT 互補頭，真實 API 已實測 | `complete_look.py`、`service.py:103-138`、`api.py:93-116` | `reports/server/complete_look_api.json`、`complete_look_api_2anchor.json`、`compat_fitb.json` | **done** |

### 1.2 `docs/engine02-pipeline.md`（現況總覽）

| 文件段落 | 文件說 | 程式做 | 狀態 |
|---|---|---|---|
| §2 第 3 層負回饋 | 「看過但沒選＝被動忽略 → **疲勞項 −0.15**（服務預設）；對照 arm **`full_zclip3_nofatigue`**」 | 已改成**正向「新鮮度」項 `+0.5`**（`config.py:47-48` `use_freshness/w_freshness`、`pipeline.py:543-563`）；對照 arm 叫 **`full_zclip3_nofresh`**（`config.py:120`）。`ARMS` 裡**沒有** `full_zclip3_nofatigue` | **stale（符號、數值、arm 名三處都錯）** |
| §3.1 延遲表註腳 | 「疲勞項已開啟」 | 同上 | **stale（用詞）** |
| §4 端點表 | 列 12 個端點 | 實際多了 `POST /visual-search`（`api.py:420`）與 `GET /gap/elements/change`（`api.py:242`） | **stale（漏兩個）** |
| §7 誠實清單「疲勞項是否該成為預設」 | 「剛實作，還沒跑 T5/T7 對照」 | §3.23／§3.25 已經跑完，而且**它已經是服務預設** | **stale** |
| §7 誠實清單「以圖搜圖」 | 「端點只收 embedding，還沒收圖檔」 | `POST /visual-search` 收 base64 圖檔、做 EXIF／alpha／尺寸正規化（`api.py:170-203`） | **stale（已完成卻列在未完成）** |
| §9 demo 腳本收尾 | 「`/rank` 服務端 p50 ~50 ms」 | 同一份文件 §3.1 寫 12.8 ms，`reports/server/latency/latency_kagl_polyvore_filled_marqo-fashionSigLIP.json` 也是 12.8/14.1 | **stale（自我矛盾，講稿會低估自己 4 倍）** |
| §3.1 延遲表 | `/rank` 12.8/14.1、44k 15.7/19.7、`/view` 12.5/14.4、`/complete-look` 33.3/87.8 | 報表逐格相符（`/view` 報表是 12.7/14.2，文件寫 12.5/14.4，差異在容許內） | **done** |
| §6「缺口盤真的在找缺口」 | 44k、45 trial、MRR 0.381→0.509、p<1e-4、對照 0.380 p=1.00 | 見 §2.2 —— **repo 裡唯一的 gap 報表是 hash/5k/12 trial、p=0.126** | **unbacked** |
| §3.3 降級階梯六層 | 全部「已實作，不是計畫」 | 逐條讀過：LLM→模板 ✅（`explain.py:92-116`）、OT 缺 checkpoint→相似度 ✅（`service.py:103-110`）、對不上詞彙→關 BM25 ✅（`pipeline.py:307-318`，本機實跑見 §2.1）、過濾空→放寬 ✅、缺屬性→補值或 unknown ✅、分類體系對不到→退回精確比對 ✅（`taxonomy.py:465-481`） | **done** |
| §1 表格 ⑦ 回饋 | `service.py`、`preference.py`、`composed.py` | 端到端實跑見 §2，全部生效 | **done** |
| 交付物 §8.2 上台前檢查 | 「再跑一次完整端點驗收（**15 項斷言**）」 | `scripts/api_check.py` 本機跑出 **22 項** 全過 | **stale（數字）** |
| `docs/engine02-design.md` 檔頭 | 「測試 `tests/`（**138 項**全過）」 | `python -m pytest -q` → **236 passed**（36.9 s） | **stale（數字）** |
| `engine02/README.md` Quick start | 「`pytest -q tests` # **20 tests**, model-free」 | 236 | **stale（數字）** |
| `engine02/README.md`「Round 2 was replaying round 1」 | 「at **w=0.15** it is **0.213** (p<1e-4)」 | 0.213 是**舊的 fatigue 實驗**的值（`reports/server/fatigue/...json` w=0.15 → 0.2133）；上線的 freshness 在 w=0.15 是 **0.1667**、上線值是 **w=0.5 → 0.2367**（`reports/server/fresh_nocap/...json`） | **stale（拿被否決的實驗數字描述上線的項）** |

---

## 2. §0／pipeline 文件逐條查核：三個要修的地方

### 2.1 BM25 閘門（§0 第 3 條、§3.29）：**結論成立，但表格混了兩個實驗，而且上線數字沒有 report**

**(a) 混表。** §3.29「有效的訊號是計數，不是離散度」那張表，五列裡有兩列不是同一個實驗跑出來的：

| §3.29 訊號 | 文件寫 | `reports/server/gate/bm25_gate_kagl_polyvore_filled_marqo-fashionSigLIP.json`（Marqo、17.8k、100 句） | `reports/ablation/bm25_gate_kagl_hash-256.json`（**hash encoder、KAGL 5k、只有 8 句**） |
|---|---|---|---|
| 覆蓋率 | 1.00 / 0.85 | **1.00 / 0.8502** ✅ | 1.00 / 0.677 |
| BM25 最高分 z | 8.6 / 13.1 | **8.6248 / 13.0992** ✅ | 6.01 / 15.94 |
| **碰到的商品比例** | **0.51 / 0.05** | 0.2393 / 0.0993 ❌ | **0.5115 / 0.0523** ← 文件抄的是這一份 |
| **命中詞 df 中位數佔比** | **0.104 / 0.001** | 0.0485 / 0.0047 ❌ | **0.1038 / 0.0014** ← 同上 |
| gold 在 BM25 前 50 | 0.93 / 0.13 | **0.93 / 0.13** ✅ | 1.00 / 0.125 |
| 閘門後 test NDCG@5（五列） | 0.5043 / 0.4001 / 0.5148 / 0.5041 / 0.5301 | **全部相符** ✅ | — |

也就是說：**上線門檻那一列的訊號值，來自一個 8 句、hash encoder、5k 商品庫的煙霧測試。**
這不是抄寫潔癖的問題，它會改變讀者對安全邊界的判斷：文件讓人以為「用詞一致 0.51 vs 門檻 0.12」有四倍餘裕，
實際在服務商品庫上是 **0.239（中位數 0.227）vs 0.12**，**不到兩倍**。

**(b) 觸發率。** §3.29 說換句話說觸發 94%。用同一份 CSV 我自己算是 **89%**（用詞一致 **2%** ✅ 相符）。
差距可能是文件只報 test 半邊，但文件沒寫，讀者無從分辨。

**(c) 上線後的端到端數字沒有 report。** `reports/server/kaglpoly_filled/t1_summary.csv` 裡 `full_zclip3`
是 **lexical 0.7361 / paraphrase 0.11065**——正好等於 gate JSON 裡的**閘門前**數值。§3.29 宣稱的
**0.7338 / 0.3080** 在整個 `reports/` 底下找不到（我也 grep 過 `nogate`，沒有任何報表含這個 arm）。

**(d) 但機制是真的——我自己在本機重跑驗證了。**
KAGL 5k、Marqo-FashionSigLIP、40 句查詢（`engine02.eval.tasks.make_queries`）、配對置換 10,000 次：

| 切片 | `full_zclip3_nogate` | `full_zclip3`（閘門） | `dense` | Δ（閘門 − 無閘門） | p |
|---|---|---|---|---|---|
| 用詞一致（閘門觸發 0%） | 0.8479 | 0.8479 | 0.6183 | **0.0000** | 1.00 |
| 換句話說（閘門觸發 100%） | 0.1895 | **0.4897** | 0.4897 | **+0.3002** | **0.0001** |

方向、量級與「降級到與純 dense 完全同分」的行為都與 §0 一致。**所以要修的是舉證，不是設計。**

### 2.2 缺口盤（§3.22 T14）：**簡報指定的主標，卻是全文件唯一「宣稱數字與唯一報表不符」的一條**

`docs/engine02-pipeline.md` §7b 明寫這一條「**當主標，這是今天的上限**」。文件宣稱：
KAGL 44k、真 encoder、45 次試驗，該要素在缺口榜的 MRR **0.381 → 0.509**、排第一 28.9% vs 對照 15.6%、
注入 vs 對照 **p < 1e-4**、對照 vs 基線 p=1.00。

repo 裡唯一的 gap 報表是 `reports/ablation/gap_kagl_hash-256.json`：

```
catalog=data/catalog/kagl, encoder=hash-256, trials=12,
mrr_base=0.3863, mrr_injected=0.4480, mrr_control=0.3863,
first_place_injected=0.25, first_place_control=0.1667,
p_injected_vs_control=0.1259, p_control_vs_base=1.0
```

對照組那半（0.386 ≈ 0.380、p=1.00）確實成立，但**注入效果在這份報表上是 0.448 且 p=0.126，不顯著**。
0.509 與 p<1e-4 需要那份 44k／真 encoder／45 trial 的執行結果，而它不在 repo 裡（`reports/` 下
`find -iname "*gap*"` 只有 hash 這一份與 `api_check` 的端點回應）。
**簡報主標目前站在一份 12 trial、p=0.126 的煙霧測試上。**

### 2.3 `ground_query`：**有程式、有 arm、研究文件有數字，但上線實作重現不出那些數字（而且會變差）**

`config.py:85`（`ground_query: "none"|"bm25"|"both"`）＋ `pipeline.py:290-299` ＋ `taxonomy.ground_query`，
兩個 arm `full_zclip3_ground` / `full_zclip3_ground_both`（`config.py:115-119`），
commit `c2a28de`／`7b365b2`。`docs/engine02-design.md` **完全沒有這一節**，`reproduce.py` 也沒有對應 stage。
唯一的數字在 `docs/research/paraphrase-robustness.md` §0(2)（KAGL 5k、Marqo、60 句，標 **MEAS**）：
`full_zclip3` 用詞一致 0.821 → 0.821（d=0.000, p=1.0）、換句話說 0.186 → **0.601**（+0.415）。

我在同一個商品庫、同一個 encoder、40 句上跑**上線的實作**：

| 切片 | `full_zclip3`（現行預設） | `full_zclip3_ground` | `full_zclip3_ground_both` | Δ(ground − 預設) | p |
|---|---|---|---|---|---|
| 用詞一致 | 0.8479 | 0.8205 | 0.8015 | **−0.0274** | **0.047** |
| 換句話說 | 0.4897 | 0.4389 | 0.4441 | −0.0509 | 0.13 |

兩個差異的來源很清楚，而且都值得寫進文件：

1. **研究文件的基準是「沒有閘門」的 0.186**，而閘門已經上線並且自己就把換句話說推到 0.4897。
   接地要贏的對手已經換人了。
2. **上線實作是「無條件接地」，不是研究文件說的「只在合約被違反時」**：`pipeline.py:290` 只看
   `arm.ground_query != "none"`，所以我的 40 句用詞一致查詢**全部 40/40 都產生了 `grounded_terms`**，
   這就是那 −0.027（p=0.047）的來源。而且接地把 catalog 詞加進 BM25 字串之後
   `share_docs_touched` 上升，**閘門反而不會觸發**——兩個功能會互相抵銷。

兩個 arm 都不是預設，所以現在沒有生產影響；但任何人照 `paraphrase-robustness.md` 的 0.601 把它打開，
拿到的會是小幅退步。`config.py:82-84` 的註解還寫「The mapping is shown on the card」——實際上
`grounded_terms` 只進 `ConstraintReport`（`contracts.py:234`），**卡片理由與任何面板都沒有顯示它**。

---

## 3. 回饋迴圈端到端：每一個 op 都改到東西了嗎？

我用 `handshake.apply_round` → `Engine02Request` → `service.rank` → `pipeline.run` → `panels.round_diff`
跑了完整的第二輪，**hash 與 Marqo-FashionSigLIP 兩個 encoder 各跑一次，結論一致**
（KAGL 5k、`full_zclip3`、第一輪查詢「black formal shirt for men」＋ category=top、gender=Men）。

| ENGINE 03 op | 進到 request 的哪裡 | 排序真的變了嗎 | 回應看得見嗎 | 判定 |
|---|---|---|---|---|
| `exclude(color, Black)` | `constraints.excluded_values`（`handshake.py:233-242`）→ `constraints.py:117-124` 永不放寬 | ✅ turnover 1.0 | ✅ `round_diff.excluded_added`、`metrics.excluded_value_hits` | **有效且可見** |
| `require(color, Navy Blue)` | `required_values`＋正向槽位（`handshake.py:243-254`）→ `constraints.py:106-114` | ✅ turnover 1.0 | ✅ `constraints_added` ＋ `required_added` | **有效且可見** |
| `adjust(元素, +1)` | `design_adjust_steps` → `kansei.beta` → `pipeline.py:483,501-516` | ⚠️ **一步（0.25）沒有改變前 5 名**（兩個 encoder 都一樣）。weight 從 0.315 → 0.065；要 **+2 步**才換人 | ✅ `round_diff.design_adjust_delta`，weight 也在 `contributions[].weight` 裡 | **有效但現場可能「看起來沒反應」**（見 §3.1） |
| `adjust(未知元素)` | 被 `handshake.py:256-258` 擋下並寫進 `rejected_ops` | — | ✅ `rejected_ops` | **有效**（但只在走 handshake 時，見 §4） |
| `choice(chosen=#3)` | `choice_history`＋`chosen_item_ids` | ✅ turnover 0.8；新增 `freshness:not_yet_seen` 與 6 個 design 項（Bayes 學到的 Δβ） | ⚠️ `round_diff` **沒有任何欄位**反映它；但卡片理由會出現「這件你這輪還沒看過」，`ServiceResponse.learned_preferences` 也帶 Δβ | **有效、部分可見** |
| `choice(什麼都沒選)` | 同上，`outside_option_kappa=0.5` | ✅ turnover 0.6，只新增 freshness 項 | 同上 | **有效**（這就是上一次稽核說「`shown_item_ids` 被接受但被忽略」的那條，**已經關掉**） |
| `exclude_item(#1,#2)` | `excluded_item_ids` → `pipeline.py:258` 從候選池剔除 | ✅ turnover 0.4，兩件確實不再出現 | ⚠️ `round_diff` 只看得到 `dropped_items`，**沒有欄位說「因為你排除了它」** | **有效、理由不可見** |
| `anchor(#1)` | `anchor_item_ids` → `pipeline.py:517-530` | ✅ 新增 `compat` 項（名次此例未變） | ⚠️ `round_diff` 無欄位；卡片有 `GROUP_LABEL["compat"]` | **有效、部分可見** |
| `anchor(不存在的 id)` | 同上 | ❌ 靜默無效果 | ❌ **完全看不出來**（`/complete-look` 對同樣的錯誤會回 400） | **接受但靜默忽略** |
| `critique(#1 → Navy Blue)` | `reference_item_id`＋`critique`＋`required_values` → `service.py:40-63` | ✅ turnover 1.0 | ✅ `required_added`；`ServiceResponse.composed` 記錄合成細節 | **有效且可審計**（但 `/rank/plain` **不做** critique，`api.py:372-378`） |
| `feeling`（沒給 likelihood） | 被 `handshake.py:291-294` 擋下 | — | ✅ `rejected_ops` | **有效** |
| `feeling`（給了 likelihood） | `update_needs` 公式④ → `req.needs` → β_d | ✅ 名次此例未變，但被引用的理由變了 | ✅ `round_diff.needs_delta` | **有效且可見** |

**合併輪（demo 腳本那一句）**：`exclude(black) + adjust(casual,+1) + choice(#3)` → turnover 1.0、
`round_diff` 同時顯示 `excluded_added` 與 `design_adjust_delta`、`metrics` 前後都可逐項核對、
`learned_preferences.design_weight_delta` 有 11 個非零軸（單次點選最大 |Δβ|=0.325，與 §3.12 的 κ=1 抑制量級相符）。

### 3.1 兩個要處理的

1. **`adjust` 一步在真 encoder 上看不出變化。** 這是現場「休閒一點」那句話會走的路徑。
   `step_size=0.25` 相對於第 1 名與第 6 名約 0.5 的分數差（`config.py:57-61` 的註解自己寫過這件事）
   本來就偏小。**不建議動 step_size**（那會推翻 §3.12 的量測），建議改成畫面層：
   既然 weight 的確從 0.315 變成 0.065，`/view` 應該把「這條回饋把 formal_style 的權重從 X 改成 Y，
   前 5 名這次沒有換人」講出來——說得出「沒有換人」比換人更有說服力，也避免評審以為系統沒收到回饋。
2. **`round_diff` 只 diff request 的「條件」半邊。** `panels.py:320-334` 只讀 `_slot_map`、
   `excluded_values`、`required_values`、`design_adjust_steps`、`needs`。
   `excluded_item_ids` / `anchor_item_ids` / `choice_history` 三個**改了排序卻不進 diff**，
   前端要靠 handshake 的 ledger 才講得出來。加三個欄位大約 10 行。

---

## 4. 整合者（LLM 驅動的 ENGINE 01／03）會踩到什麼

全部在本機用 `Engine02Request.model_validate` 與 `fastapi.testclient` 實跑過（基準 `fc88439`，
已包含 coordinator 18:56 的 shorthand validator）。

### 4.1 必填 vs 選填

- **唯一必填**：`session_id`（`contracts.py:151`）。其餘全部有預設，`{"session_id": "x"}` 就會回 200 並給卡片。
- `contract_version` 有預設值且**從來沒有被檢查**——送 `"9.9.9"` 照樣 200。
- `options.arm` 預設 `"full_zclip3"`（`contracts.py:136`），所以 `api.py:363/375` 的
  `req.options.arm or os.environ.get("ENGINE02_ARM", ...)` **永遠走左邊**：
  **`ENGINE02_ARM` 對 `/rank` 與 `/rank/plain` 完全沒有效果**（對 `/visual-search` 與暖機有效）。

### 4.2 會被擋下（422／400）且訊息可行動的

| 送進來的東西 | 結果 | 訊息品質 |
|---|---|---|
| `state: "VALUE"`／`"有值"` | 422 | ✅ `Input should be 'unmentioned', 'value', 'dont_care' or 'inferred'` + `loc` |
| `options.diversify: "DPP"` | 422 | ✅ 列出合法值 |
| `needs[].prob = 1.4` | 422 | ✅ |
| `design_adjust_steps: {"formal_style": 1.5}` | 422 | ✅ `got a number with a fractional part` |
| `critique.attribute: "fit"` | 422 | ✅ 列出合法值 |
| `options.arm: "no_such_arm"` | **400**（`api.py:364`） | ✅ `unknown arm 'x'; see GET /arms` |
| `session_id` 缺或 null | 422 | ✅ |
| 上傳的不是圖／base64 壞掉／> 12 MB | 400／413（`api.py:436-445`） | ✅ 含型別與大小 |
| `/complete-look` 的 `anchor_item_ids` 不存在 | 400（`service.py:116-118`） | ✅ 列出哪幾個 id |

### 4.3 型別對不上、但 LLM 很容易這樣寫 → 422（訊息夠但形狀不對稱）

| 形狀 | 結果 |
|---|---|
| `{"category": "top"}`（裸字串） | ✅ **接受**（`contracts.py:44-60` shorthand） |
| `{"category": ["top"]}` | ✅ 接受 |
| `{"category": {"values": ["top"]}}`（沒給 state） | ✅ 接受 |
| `"needs": {"trustworthy": 0.6}`（字典） | ✅ 接受（`contracts.py:192-199`） |
| `{"category": {"state": "value", "values": "top"}}`（**給了 state，values 卻是裸字串**） | ❌ 422 —— shorthand validator 只在**沒有 state** 時才收字串 |
| `excluded_values: {"color": "Black"}` | ❌ 422 |
| `required_values: {"color": "Navy Blue"}` | ❌ 422 |
| `feedback.chosen_item_ids: "123"` | ❌ 422 |

四個「裸字串該被當成單元素 list」的位置只修了一個。同一個 LLM 在同一份 JSON 裡
`"category": "top"` 會過、`"excluded_values": {"color": "Black"}` 會 422，這種不一致特別難教。

### 4.4 **被接受、但靜默改變（或關閉）行為** ← 最危險的一類

| 送進來的東西 | 實際發生什麼 | 有沒有告訴對方 |
|---|---|---|
| **`need_id` 不在感性表**（例如 `"看起來很帥"`） | **所有 `design:*` 項消失**，`β_d` 全零；HTTP 200，卡片只剩 dense＋bm25，理由照樣「忠實」 | ❌ **完全沒有**。`input_warnings` 是空的（`pipeline.py:79-91` 只檢查否定詞與 `retrieval_text_normalized`） |
| `design_adjust_steps` 的 key 不是設計要素 | 靜默丟掉（`kansei.beta`）——注意 `handshake.apply_round` **會**擋（`handshake.py:256`），但只有走 handshake 且有傳 `kansei` 時 | ❌ |
| `design_weight_prior` 的 key 不是設計要素 | 靜默丟掉（`pipeline.py:495-500`） | ❌ |
| `feedback.anchor_item_ids` 是不存在的 id | 相容性項靜默不出現（`pipeline.py:517-521`） | ❌（同樣的錯誤 `/complete-look` 會 400） |
| `chosen/rejected/excluded_item_ids` 是不存在的 id | `catalog.positions` 靜默略過 → Rocchio／懲罰／排除全部失效 | ❌ |
| `critique` 有但 `reference_item_id` 沒有（或相反） | `service.py:41-42` 直接原樣返回，批評整個消失 | ❌ |
| **顏色／場合／季節送中文值**（`"黑色"`） | 過濾器清空 → 放寬階梯 `color:drop` → 滿足率 **0.0** | ⚠️ 只有 `constraint_report.relaxed` 與滿足率 0.0；**沒有一句話說「這個值不在商品庫詞彙裡」**。**品類**送中文（`"襯衫"`）則正常（taxonomy 有中文同義詞，`n_after_filter=522`、滿足率 1.0）——**同一份 JSON 裡品類吃中文、顏色不吃**，這是最容易踩的不對稱 |
| 多餘欄位（頂層／`constraints` 內／`Slot` 內） | 全部忽略（pydantic 預設） | ❌（`integration_check.py` 把這個列為期望行為，合理，但要在契約文件講明） |
| `budget` 有值 | 商品庫沒有 price → `budget:drop` 每次都放寬 | ⚠️ `relaxed` 有寫、`panels.provenance().caveats` 有一句 |

### 4.5 會變成 500 的一個

`api.py:463-464`：

```python
constraints=HardConstraints(**body.constraints) if body.constraints else HardConstraints(),
```

`VisualSearchRequest.constraints` 宣告成 `dict`（`api.py:414`），所以 FastAPI 不驗證它；
形狀錯誤（例如 `{"category": {"state": "VALUE"}}`）會在 handler 內部丟出 **未被接住的 `ValidationError`
→ 500**，而不是 422。本機實測確認會拋。`/rank` 走同樣資料只會回乾淨的 422。

### 4.6 否定詞警告會誤報

`pipeline.py:83` 用 **子字串**比對 `NEGATION_WORDS`（`pipeline.py:70-76`）：

| `retrieval_text` | 觸發的詞 |
|---|---|
| `sleeveless monochrome top` | `no`（在 mo**no**chrome）、`less`（在 sleeve**less**） |
| `a note on denim` | `not`（在 **not**e）、`no`（在 **no**te） |
| `black shirt` | （正確地沒有） |

`sleeveless` 是服飾詞彙的核心字。ENGINE 01 每次送 sleeveless／monochrome／turtleneck 這類詞，
我們就回一句「你送了否定詞，請改用 excluded_values」——這會讓對方的 agent 去修一個不存在的問題。
改成 token 比對即可（`sparse.tokenize` 現成）。

---

## 5. 未完成／死碼／設定開關沒有效果

| 項目 | 位置 | 現況 |
|---|---|---|
| **`scripts/reproduce.py` 的 `fatigue` stage 指向一個不存在的腳本** | `reproduce.py:130-134` 寫 `"eval_fatigue.py"`，實際檔名是 `scripts/eval_freshness.py` | `python scripts/reproduce.py --stage fatigue` 會直接失敗。重新命名時漏掉的 |
| **`reproduce.py --check-claims` 本身過期** | `reproduce.py:165-203` | 只涵蓋到 §3.23；**§3.20（外部基準）、§3.24 T16、§3.25 T15-B/C、§3.26、§3.27 T17、§3.28 T18、§3.29 T19 全部不在 CLAIMS 裡**。而且 §3.16 那一列還寫著「full_concept_image (**never run**)」——它早就是服務預設。目前輸出「37/40 有腳本」，分母本身漏了七節 |
| **`ENGINE02_ARM` 對 `/rank`、`/rank/plain` 無效** | `api.py:363,375`；`contracts.py:136` 有非空預設 | 設定開關沒有效果（見 §4.1） |
| **`engine02/replay.py` 沒有被任何地方接上** | `api.py`／`service.py`／`scripts/demo_run.py` 都沒有 `ReplayStore` | PRD §8「斷網重播」ENGINE 02 這半有程式、有 5 個測試，但**現場沒有開關可以打開**，要改 code。上一次稽核的 §2.5 hook 沒有被採用 |
| `use_trend` / `w_trend=0.2` 永遠不生效 | `pipeline.py:531`（需要 `self.trend_keywords`）；`api.py:119` 刻意只載 badge | **這是刻意的**（§3.15），但 `/arms` 會把 `w_trend: 0.2` 吐給整合者看，容易被誤讀成「趨勢有進分數」 |
| `bm25_adaptive` / `bm25_gate="coverage"` | `config.py:87-88,103-106` | 只給舊 arm 重現用，已被 `docs_touched` 取代 —— 這是正確的保留 |
| `exposure_cap` | `config.py:62`、`pipeline.py:270-279` | 實作＋量測＋預設關（§3.25），正確 |
| 未使用的 import（生產程式） | `pipeline.py:24` 的 `filter_with_relaxation`、`satisfies` | 兩個都沒有被 `pipeline.py` 用到（實際用的是 `taxonomy.filter_with_category_relaxation` 與 `satisfies_positions`） |
| 未使用的區域變數 | `pipeline.py:357` `probs = {...}`（`run()` 內），真正用到的是 `_terms` 裡的 `pipeline.py:482` | 無害，但會讓讀 code 的人以為 `run()` 用得到 |
| 未使用的 import（腳本） | `bench_latency.py:70,72`、`check_parity.py:28`、`eval_external.py:547`、`eval_kansei_sensitivity.py:36`、`eval_llm_paraphrase.py:45`、`eval_ltr.py:24`、`prepare_catalog.py:350`、`vlm_tag_attributes.py:72` | 全部無害 |
| `ConstraintReport` 的註解錯位 | `contracts.py:255-262`：`exposure_excluded` 的說明文字被 `grounded_terms` 的說明切成兩半 | 只是可讀性 |
| `ground_query` 註解與行為不符 | `config.py:82-84`「The mapping is shown on the card」 | 卡片上沒有（見 §2.3） |
| `ltr.py`（476 行）只被 `scripts/eval_ltr.py` 與測試用到 | — | 這是**正確的**：T10 的結論是不採用，程式留著當證據 |

**測試**：`python -m pytest -q` → **236 passed, 2 warnings, 36.94 s**（本機 CPU，無外部相依）。
`scripts/api_check.py --catalog data/catalog/kagl --encoder hash` → 22 項斷言全過。
`scripts/integration_check.py --catalog data/catalog/kagl --encoder hash` → 24 項全過。

### 5.1 契約檔（`docs/contract/`）的三個小問題

| 檔案 | 問題 |
|---|---|
| `engine02_request.schema.json`、`engine02_response.schema.json` | ✅ 與現行 pydantic model **完全同步**（我逐一比對過每個 `$defs` 的 property 集合） |
| `example_round1_response.json`、`example_round2_response.json` | ❌ **無法通過自己的 schema**：`query_embedding` 第 5 個元素是字串 `"...truncated"`。當範例讀沒問題，當 fixture 會炸 |
| 同上 | ⚠️ 是用 **`arm="full"` ＋ `encoder="hash-256"`** 產生的，不是服務預設 `full_zclip3` ＋ Marqo。所以範例裡**沒有 `freshness` 群組、沒有 `input_warnings` 的實例、`design_scores` 是 hash encoder 的值**。ENGINE 03 照著這份寫，第一次看到 `"group": "freshness"` 會是在現場 |
| `example_view_round2.json` | ❌ **過期**：缺 `diversity` 欄位，`Engine02View.model_validate()` 直接 `Field required`。`RoundDiff` 的欄位倒是完全一致 |
| `engine03_feedback.schema.json`、`example_engine03_handshake.json` | ✅ 兩個 request 與 feedback 都通過驗證 |

---

## 6. 誠實的缺口清單（依對評分的影響排序）

評分權重：問題理解 35%、技術方案 35%、呈現完整度 20%、表達與應變 10%。

### A. 只需要你一小時（不需要別人）

| # | 缺口 | 擋住哪個評分項 | 要動的檔案 | 估時 |
|---|---|---|---|---|
| A1 | **§3.22 缺口盤沒有真 encoder／44k 的 report**（唯一那份是 hash/5k/12 trial、p=0.126） | **問題理解 35%＋呈現 20%**：pipeline 文件指定它當主標，評審一問「這個 0.509 哪來的」就沒有檔案可開 | 在 cfda4 跑 `scripts/eval_gap.py --catalog data/catalog/kagl_full --encoder marqo-fashionSigLIP --trials 45 --sessions 60`，輸出進 `reports/server/gap/` | 20 分鐘掛上去 |
| A2 | **未知 `need_id` 靜默關掉所有設計要素項** | **技術方案 35%＋表達 10%**：現場如果 ENGINE 01 送錯一個 id，整個「隱性需求」敘事會安靜消失，而我們還會自信地解釋 | `pipeline.py::input_warnings`（+3 行，比對 `self.kansei.need_ids`）；同理 `design_adjust_steps`、`design_weight_prior` 的未知 key | 20 分鐘 |
| A3 | **§3.29 表格混了 hash/5k/8 句的數字**，且上線後的端到端數字沒有 report | **技術方案 35%**：這是今天最強的新結果，卻是唯一「數字對不上報表」的一節 | `docs/engine02-design.md` §3.29 換成 0.239/0.099 與 0.0485/0.0047，觸發率註明 dev/test；另跑一次 T1（`full_zclip3` vs `full_zclip3_nogate`）存檔 | 15 分鐘改文件＋一次 T1 |
| A4 | **`reproduce.py` 的 `fatigue` stage 叫不存在的 `eval_fatigue.py`**，且 CLAIMS 少了七節 | 呈現 20%：「可重現」是交付物，`--check-claims` 的 37/40 分母本身是錯的 | `reproduce.py:133` 改檔名；CLAIMS 補 §3.20/3.24/3.25/3.26/3.27/3.28/3.29；§3.16 那列拿掉「never run」 | 20 分鐘 |
| A5 | **pipeline 文件六處 stale**（疲勞項 −0.15／`full_zclip3_nofatigue`／端點表漏 `/visual-search`＋`/gap/elements/change`／§7 兩條已完成卻列未完成／§9 講稿寫 50 ms） | **表達 10%**：§9 是上台講稿，把自己的 12.8 ms 講成 50 ms | `docs/engine02-pipeline.md` §2、§3.1、§4、§7、§9 | 20 分鐘 |
| A6 | **`/visual-search` 的 `constraints` 形狀錯會 500** | 技術方案 35%：demo 新功能的第一個整合點 | `api.py:414` 把 `constraints: dict` 改成 `HardConstraints`，或 try/except 轉 422 | 10 分鐘 |
| A7 | **否定詞警告誤報**（`sleeveless`／`monochrome`／`note`） | 表達 10%：會讓 ENGINE 01 去修不存在的問題 | `pipeline.py:83` 改成 token 比對 | 10 分鐘 |
| A8 | **三個裸字串位置仍 422**（`excluded_values` / `required_values` / `feedback.*_item_ids`），`{"state":"value","values":"top"}` 也 422 | 技術方案 35%：和已修好的 shorthand 不一致，最難教 | `contracts.py` 三個 `field_validator(mode="before")` | 15 分鐘 |
| A9 | **`round_diff` 看不到 `exclude_item`／`anchor`／`choice`** | 呈現 20%：第二輪並排是 demo 第 2 段的畫面 | `panels.py:324-338` 加三個欄位 | 15 分鐘 |
| A10 | **契約範例過期**：`example_view_round2.json` 缺 `diversity`、兩份 response 範例無法通過自己的 schema、且是 `full`＋hash 產生的 | 呈現 20%＋整合風險 | 用 `full_zclip3`＋Marqo 重跑 `scripts/export_handshake_example.py`；`query_embedding` 改成截短但仍是數字（或直接 `null`） | 20 分鐘 |
| A11 | **`ground_query` 上線實作重現不出研究文件的數字，而且是無條件接地** | 技術方案 35%（若被問到）：目前沒有生產影響，但研究文件寫著 +0.415，任何人打開都會拿到 −0.03 | 要嘛在 `docs/engine02-design.md` 補一節寫清楚「閘門上線後接地不再有增益」，要嘛把接地改成只在閘門觸發時才做 | 30 分鐘 |
| A12 | **`ENGINE02_ARM` 對 `/rank` 無效**、`replay.py` 沒有接上 | 應變 10%：現場想換 arm 或開重播時，以為有開關其實沒有 | `api.py:363,375` 改成 `req.options.arm if "arm" in req.options.model_fields_set else env`；replay 依上次稽核 §2.5 的三行接上 | 20 分鐘 |
| A13 | **`adjust` 一步在真 encoder 上不換人** | 表達 10%：現場「休閒一點」可能看起來沒反應 | 不要改 `step_size`（會推翻 §3.12）；在 `/view` 把權重前後值講出來 | 20 分鐘 |
| A14 | 小數字：設計文件檔頭 138→236 測試、§8.2 15→22 項、§3.17 的 76.3→67.5、README 的 20 tests 與 w=0.15/0.213 | 呈現 20% | `docs/engine02-design.md`、`engine02/README.md` | 10 分鐘 |

### B. 需要別人（人工標註／價格／帳號／另一個 owner）

| # | 缺口 | 擋住哪個評分項 | 誰 | 估時 |
|---|---|---|---|---|
| B1 | **沒有任何真人分級標註與 Cohen's κ** | 問題理解 35%：所有 NDCG 的標準答案都是資料集屬性；§3.3b 的「目視標註」也是 LLM 標的 | 兩位組員（題本 `data/labels/human_tasks.csv` 140 題已備好，`scripts/eval_human_agreement.py` 已可跑） | 1–2 h |
| B2 | **LLM 改寫的幻覺率沒有實測數字** | 技術方案 35%：§0 的「LLM 只能改寫已驗證事實」目前只有單元測試 | 一位組員用 ChatGPT agent 貼 `reports/llm_paraphrase/paste_me.txt`（100 張卡已產生），再跑 `eval_llm_paraphrase.py score` | 1 h |
| B3 | **價格永遠 null** | 呈現 20%（「完整可購買」） | coordinator 找贊助商資料，或明確標示為合成 | 1 h（標示） |
| B4 | **M3 感性表沒有人工校正紀錄與 v[n,d]** | 技術方案 35%：K 表是核心敘事；§3.18 已指出該校的是**正負號與是否為零** | 全組 1 小時，只校正符號 | 2 h |
| B5 | **斷網重播只有 ENGINE 02 這半，而且沒接上** | 應變 10%（PRD §8 必做） | ENGINE 01／03 owner ＋前端開關 | 1–2 h |
| B6 | §3.24 T16、§3.27 T17、§3.28 T18 的結果**在 `reports/` 裡找不到輸出檔** | 技術方案 35%：這三節都是「我們量過所以不做」的論據，現場被追問時要拿得出檔案 | 需要 GPU／DeepFashion 語料，只能在伺服器重跑並把 JSON 存進 `reports/server/` | 伺服器 1–2 h |
| B7 | 模擬使用者是規則式、不是 LLM／真人 | 表達 10% | 簡報 owner 寫清楚並引 ConvApparel | 30 min |

---

## 7. 給 coordinator 的優先清單

1. **`scripts/eval_gap.py` 在 cfda4 跑 44k＋Marqo＋45 trial，把 JSON 存進 `reports/server/gap/`** —— 簡報主標目前只有一份 p=0.126 的 hash 煙霧測試撐著。
2. **`engine02/pipeline.py::input_warnings`**：未知 `need_id`／未知設計要素要回報，別再靜默關掉整個設計要素層。
3. **`docs/engine02-design.md` §3.29**：把「0.51 / 0.05」「0.104 / 0.001」換成服務商品庫的 0.239/0.099 與 0.0485/0.0047，並補一份閘門上線後的 T1 report。
4. **`docs/engine02-pipeline.md`**（§2 疲勞項／§4 端點表／§7 兩條／§9 的 50 ms）：一次改完六處 stale。
5. **`scripts/reproduce.py:133`**：`eval_fatigue.py` → `eval_freshness.py`；CLAIMS 補上 §3.20/3.24/3.25/3.26/3.27/3.28/3.29。
6. **`engine02/api.py:414`**：`VisualSearchRequest.constraints` 改型別，讓形狀錯誤變 422 不是 500。
7. **`engine02/pipeline.py:83`**：否定詞改 token 比對，`sleeveless` 不該觸發警告。
8. **`engine02/contracts.py`**：`excluded_values`／`required_values`／`feedback.*_item_ids` 也收裸字串，和已修好的 `category` shorthand 對齊。
9. **`engine02/panels.py:324`**：`round_diff` 補 `excluded_items_added` / `anchors_added` / `choices_added` 三個欄位。
10. **`scripts/export_handshake_example.py`**：用 `full_zclip3`＋Marqo 重產 `docs/contract/` 的四份範例；`example_view_round2.json` 現在連自己的 model 都驗不過。
11. **`engine02/api.py:363,375`**：`ENGINE02_ARM` 對 `/rank` 目前完全無效。
12. **`engine02/replay.py`**：依上次稽核 §2.5 的三行接進 `api.py` 的 lifespan，PRD §8 才算能在現場開。
13. **`docs/engine02-design.md`** 補一節 `ground_query`（或把它改成只在閘門觸發時接地）—— 上線實作在我本機重跑是 **−0.027（用詞一致, p=0.047）**，不是研究文件的 +0.415。
14. **`engine02/pipeline.py:24,357`**：兩個未使用 import 與一個未使用區域變數。
15. **`reports/server/api_check/`**：被我用本機 hash 版蓋掉了，上台前請在 cfda4 重跑一次 `scripts/api_check.py`。

---

## 8. 我驗證不了的

| 項目 | 為什麼 |
|---|---|
| 所有 **44k（`data/catalog/kagl_full`）與 17.8k（`kagl_polyvore_filled`）** 的數字 | 本機 `data/catalog/` 只有 `kagl`(5k)、`kagl_polyvore`、`polyvore`。我只能核對這兩個商品庫的**報表檔**，不能重跑 |
| §3.29 的端到端 0.3080 / 0.7338 | 需要 `kagl_polyvore_filled`。我改用 KAGL 5k＋Marqo 重跑，**確認了機制與方向**（換句話說 +0.3002, p=0.0001；用詞一致 Δ=0.0000），但那不是文件宣稱的那個數字 |
| §3.22 的 0.509 / p<1e-4 | 需要 44k＋真 encoder；本機唯一那份是 hash/5k/12 trial |
| §3.24 T16、§3.27 T17 | 需要 DeepFashion-InShop 語料（不在本機） |
| §3.28 T18（文字 cross-encoder） | 需要下載 bge-reranker-v2-m3 / Qwen3-Reranker-0.6B 並在 17.8k 上跑；而且 repo 裡找不到它的輸出檔 |
| §3.13／§3.17 的 VLM 標註吞吐（0.39 s、0.164 s／件） | 需要 GPU |
| §3.14／§3.14b 的 `ot_cir` 實測、`/health` 的 `complete_look.method` | 需要 OutfitTransformer checkpoint（本機 `/health` 回 `method=similarity`、`ot_heads=[]`） |
| 延遲數字 12.8 ms / 33.3 ms | 我只核對了 `reports/server/latency/*.json` 的內容，沒有在同等硬體上重跑 |
| 真人標註的 κ、LLM 改寫幻覺率、價格資料 | 需要人 |
| ENGINE 01／03 真正送出來的 JSON 長什麼樣 | 只能列舉可能的形狀（§4），不能替代一次真正的三引擎串接彩排 |

---

### 附：本次用到的本機執行

```bash
python -m pytest -q                                   # 236 passed
python scripts/reproduce.py --check-claims            # 37/40（分母本身過期，見 §5）
python scripts/api_check.py --catalog data/catalog/kagl --encoder hash        # 22/22
python scripts/integration_check.py --catalog data/catalog/kagl --encoder hash # 24/24
```

另外三支一次性稽核腳本（寫在 scratchpad，未進 repo）：契約失效模式列舉、
第二輪逐 op 追蹤（hash 與 Marqo 各一次）、以及 §2.1／§2.3 的
`full_zclip3` vs `full_zclip3_nogate` vs `full_zclip3_ground(_both)` vs `dense`
在 KAGL 5k＋Marqo-FashionSigLIP、40 句查詢、配對置換 10,000 次下的 NDCG@5 比較。
