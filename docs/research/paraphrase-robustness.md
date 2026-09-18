# 「換句話說」的查詢（paraphrase robustness）：損失出在哪、怎麼修、值不值得修

> 調查日期：2026-09-18｜分支 `engine02-research`｜**本檔只新增，不改任何既有檔案**
> 標記：**MEAS** = 我本輪在本機實際跑出來的數字（重現資訊見 §9，跑在 `E:\mchackathon2026\.venv`，CPU，**沒有動 nycu server**）｜**V** = 一手來源已核對｜**U** = 只看到摘要／二手，引用要保守｜**INF** = 我的推論，不是文獻結論｜**CODE** = 直接讀本 repo 的程式碼，附行號可複核｜**NOT REACHED** = 這輪載不到，不代表不存在
> 本輪限制：三個文獻子代理**開工時 WebSearch 配額已耗盡（200/200）**，全部改走 arXiv API／Crossref／OpenAlex／定點 WebFetch。**ACM DL、Springer、Etsy Code as Craft、eBay/Amazon 工程部落格索引全部 403 或 CAPTCHA**，所以「產業部落格」那一欄大量是 NOT REACHED — 請一律讀成「我載得到的那幾頁上沒有」，不要讀成「不存在」。
> 對照文件：`docs/engine02-design.md` §3.1／§3.10／§3.20／§3.21／§3.27、`docs/engine02-literature-review.md` §2、`docs/research/engine02-method-inventory.md` §4、`docs/research/external-benchmarks.md` §2.1b、`docs/research/taxonomy.md`。

---

## 總表：候選方法一覽

| 方法 | 作用在哪一側 | 已發表的效果（出處） | 我們的實作成本 | 我們的實測 | 建議 |
|---|---|---|---|---|---|
| **A. 閘門改用「商品屬性值詞彙」而非全文詞彙** | 融合／閘門 | Bruch TOIS 2023 §3 逐字：某一路變異數→0 時「可以整個跳過融合」，且明說他們不研究這個情況（V）；**沒有任何論文做過這件事**（子代理四組 arXiv 全文搜尋 0 筆）；選擇性套用的機制來自 Cronen-Townsend CIKM 2004、Amati ECIR 2004（U） | `sparse.py` +6 行，**0.003 ms/query** | **MEAS** 換句話說 `full_zclip3_adaptive` 0.223→0.463（＝純 dense），用詞相同 **Δ=0.000, p=1.0** | **做**（最低風險，先做這個） |
| **B. 查詢詞彙接地到商品庫詞彙（gated，只餵 BM25）** | 稀疏側 | QUEACO（CIKM 2021）NER+AVN，線上 coverage +38.2%→NDCG@16 +0.36%（V）；BEQUE（WWW 2024）零結果查詢 GMV **+18.66%**（V） | 新模組 ~80 行＋一份 60 條屬性同義詞表；**1.07 ms/query**，只在違約時觸發 | **MEAS** `full_zclip3` 換句話說 0.186→**0.556**（+0.370, p=0.0001），用詞相同 Δ=0.000 | **做**（主推，見 §7 建議 #2） |
| **B′. 接地詞「附加」到 dense 查詢（不是取代）** | dense 側 | 無直接對應（INF：等價於把不確定的同義詞當作額外訊號而非改寫） | 在 B 之上 +2 行 | **MEAS** `full_zclip3` 換句話說 0.556→**0.601**（對 off 是 +0.415, p=0.0001）；純 dense 0.463→0.575 | **做**（跟 B 同一個 PR） |
| C. 用 SigLIP text tower 把詞接到最近的商品屬性值（免人工同義詞表） | 稀疏側 | 無（Q2E-PECOS 是同形狀的 XMC 做法，KDD 2021，U） | 免人工表，但每查詢多 ~5 次 text encode | **MEAS** 換句話說 `full_zclip3` 0.186→0.475（+0.289, p=0.0001），但**接錯的相似度和接對的重疊**（§2.2） | **當 fallback**，不要當主路徑 |
| D. 分數分布閘門（「BM25 前 k 名是不是都接近 0」／NQC／σ50%／WIG） | 融合 | Bruch TOIS 2023 §3 明寫「變異數為 0 時可以整個跳過融合」，但**也明說接近 0 的情況他們不研究**（V）；NQC 是文獻最佳的分數離散度預測器（Cummins SIGIR 2011：r 0.523–0.527，V） | 幾乎 0 | **MEAS 全部在我們資料上失效**：max_score AUC 0.678、σ50% 0.698、n(σ50%) 0.792、WIG 0.644、**NQC AUC 0.001＝完全反向**（§5.1） | **不做**（被自己的資料否掉；改用「命中文件數」，AUC 0.994） |
| E. RRF → convex combination | 融合 | Bruch TOIS 2023：CC 在每個資料集 NDCG 都 ≥ RRF，p<0.01（V） | 已實作（`hybrid_convex`） | 我們 §3.1 既有數字：換句話說 convex **0.119 < RRF 0.191** | **不做**（我們的資料與該論文方向相反，§5.2） |
| F. SPLADE / uniCOIL / DeepImpact（學習式稀疏） | 稀疏側 | SPLADE-v3 BEIR-13 51.7 vs BM25 43.7（V）；SPLADE-v3-Doc 47.0，**query 端免推論**（V） | SPLADE v3 權重 **CC BY-NC-SA 4.0＝非商用**（repo 既有查證，V）；要訓練／要重建索引 | 未測 | **不做**（授權＋工期；替代品見 §3.1） |
| G. doc2query / docTTTTTquery 文件擴展 | 稀疏側（索引時） | doc2query MS MARCO MRR@10 18.4→21.5，但**其中「新詞」只貢獻 18.4→18.8**（V） | 索引時 GPU；query 端 0 | 未測 | **不做**（作者自己的消融顯示詞彙橋接貢獻 ≈ +0.4） |
| G′. Doc2Token（Walmart, 2024） | 稀疏側（索引時） | 新詞率 ~100%（vs doc2query ~20%）；線上 A/B 營收 **+0.28% (p=0.013)**（V） | 要 query log 訓練（我們沒有） | 未測 | **不做**（沒有 query log） |
| H. 字元 n-gram／模糊比對／詞幹還原 | 稀疏側 | 處理的是**拼寫**變異不是同義詞（Zhuang & Zuccon EMNLP 2021 量的是 typo）；IIR §2.2.4：英文詞幹還原「aggregate 上幫助不大」（V） | 低 | 未測 | **不做**（機制不對，§3.3） |
| I. 查詢的 prompt ensembling（多模板平均） | dense 側 | CLIP ICML 2021 §3.1.4：80 模板在 ImageNet **零樣本分類**上 +3.5%（V）；**檢索的評測慣例是完全不用模板**（V，CLIP_benchmark 與 Marqo 自己的 eval 原始碼） | 幾乎 0 | **MEAS 無效**：換句話說 6 模板平均 **d=+0.000, p=0.954**；用詞相同 +0.019, p=0.18 | **不做** |
| J. 查詢擴展／DBA／diffusion | 兩側 | Revisiting Oxford/Paris (CVPR 2018)：對「只有少數正解」的查詢會**變差**；我們 §3.27 已採納 | — | — | **不做**（既有決定，理由不變） |

---

## 0. 三個直接回答

### (1) 損失 **91% 在稀疏側**，而且不是「BM25 算不到分」，是「BM25 很有自信地算錯」

**MEAS**，2×2 oracle 歸因（60 句 T1 查詢、KAGL 5k、Marqo-FashionSigLIP、**只有換句話說的查詢**、NDCG@5、配對置換檢定 10,000 次）：

| `hybrid_rrf` | dense 側用換句話說 | dense 側用原詞（oracle） |
|---|---|---|
| **BM25 側用換句話說** | 0.191（現況） | 0.220（+0.029, **p=0.0625，不顯著**） |
| **BM25 側用原詞（oracle）** | **0.773（+0.581, p=0.0001）** | 0.830（+0.639） |

可回收的損失是 0.639；單修稀疏側就回收 0.581，**佔 90.9%**。單修 dense 側買到 +0.029 且不顯著。`full_zclip3` 同形狀（+0.549 vs +0.014）。

而稀疏側崩盤的機制**不是文獻預設的「詞彙不匹配 → 分數 0 → 隨機排序」**。**MEAS**，逐詞歸因：換句話說的查詢裡，BM25 第 1 名有 **37/60 是被 `everyday` 這一個詞推上去的，而 `everyday` 在 5,000 件商品庫裡只出現在 1 件商品的標題裡**（Nike Women's Free Everyday White Orange Shoe，df=1，idf=8.112 — 整句查詢裡最高的 idf）。再加上 `workout`（12/60，df=2）就是 49/60。`emerald`（df=1）把第 1 名送給了一支 **Revlon 眼線筆**。

也就是說：**讓 BM25 在用詞相同時很強的那個性質（稀有詞 = 高 idf = 強訊號），在換句話說時就是災難本身** — 一個湊巧在商品庫裡出現過一次的同義詞會拿到最高 idf，然後把整張榜單綁架。NDCG 0.034 **比隨機還差**，因為排序不是隨機，是被系統性地推向與查詢反相關的商品。

### (2) 最推薦的一招：**gated vocabulary grounding — 只在合約被違反時，把查詢接地到商品庫詞彙，接地後的字串只餵 BM25，另外附加給 dense**

**MEAS**，同一組 60 句查詢：

| arm | 用詞相同（off → grounded） | 換句話說（off → grounded） |
|---|---|---|
| `dense` | 0.614 → 0.614（p=1.0） | 0.463 → **0.575**（+0.112, p=0.0002） |
| `hybrid_rrf` | 0.830 → 0.830（**p=1.0**） | 0.191 → **0.602**（+0.410, p=0.0001） |
| **`full_zclip3`（服務預設）** | **0.821 → 0.821（d=0.000, p=1.0）** | **0.186 → 0.601（+0.415, p=0.0001）** |
| oracle（完美接地）上界 | 0.821 | 0.735 |

換句話說的成績從 0.186 變成 0.601，**比純 dense（0.463）還高 0.14**，而用詞相同那一欄**一格都沒動**（逐查詢完全相同，d=0.000, p=1.0）。延遲 **+1.07 ms/query**，而且只在違約查詢上付。可加總的解釋結構**完全沒動**（`_terms` 的項目清單不變，只是 BM25 這一項的輸入字串換了）。

### (3) 值不值得修？**值得，但要修的是「把違約情況處理得體面」，不是「追求對換句話說也很強」**

論據在 §6。一句話版本：我們**已經**在合約裡要求 ENGINE 01 正規化詞彙（`GET /vocabulary` + `retrieval_text_normalized`），而現在的違約處置是「BM25 權重歸零，退回純 dense」— 問題是**那個路由幾乎不會觸發**（**MEAS**：換句話說的查詢有 **93.3% 通過現行 `bm25_min_coverage=0.5` 的閘門**，§5.1）。所以現在的狀態不是「合約嚴格、違約降級」，而是「合約寫了、違約時系統靜靜地變得比什麼都不做還糟」。

**建議 #1（§7）把閘門修對，就足以讓違約情況退回到 dense（0.463），成本 0.003 ms、零風險。** 建議 #2 的接地再往上推到 0.60。兩者都**不是**在「投資 robustness」，是在「讓已經寫好的降級路徑真的會啟動」。真正的 robustness 投資（SPLADE、doc2query、learned tagger）我全部建議不做，理由在 §3 和 §8。

---

## 1. Q1：損失來自哪一側？可歸因的診斷

### 1.1 2×2 oracle 歸因（已跑，數字在 §0(1)）

設計：對**同一句**換句話說的查詢，分別把 BM25 那一路和 dense 那一路的輸入文字換成「原詞版」（＝完美接地的 oracle），得到 2×2。這是**歸因**不是量測，因為每一格都是同一組查詢的配對觀測，差值可以直接做配對置換檢定。

要點：
- **融合本身沒有額外的損失可以撿**。單修稀疏側 0.773 已經是「兩側都修」0.830 的 93.1%。所以「RRF 讓一份崩掉的名單投票」這個描述是對的，但**修的地方應該在源頭，不在融合器**。把融合器換掉（§5.2）在我們的資料上是負向的。
- dense 側自己確實有損失（0.614 → 0.463，−0.151），但那個損失**幾乎傳不進混合結果**（+0.029，n.s.），因為在混合裡 dense 的名次早就被稀疏側的錯誤壓住了。

### 1.2 逐詞歸因：BM25 不是算不到分，是算錯分

**MEAS**，換句話說的查詢在 5k 商品庫上，所有「有進商品庫詞彙表」的 token 與其 df / idf：

| token | df | idf | | token | df | idf |
|---|---|---|---|---|---|---|
| `s`（所有格被切出來的） | 249 | 2.947 | | `midnight` | 2 | 7.601 |
| `pants` | 36 | 4.913 | | `workout` | 2 | 7.601 |
| `blush` | 26 | 5.235 | | `rucksack` | 2 | 7.601 |
| `purse` | 19 | 5.543 | | `everyday` | **1** | **8.112** |
| `tee` | 5 | 6.812 | | `jet` | **1** | **8.112** |
| `crimson` | 5 | 6.812 | | `emerald` | **1** | **8.112** |

而商品庫裡真正的屬性值（`Tshirts`、`Black`、`Men`、`Casual`）df 是幾百到幾千（**MEAS**：用詞相同的查詢，命中 token 的 df 中位數是 **392.8**；換句話說是 **5.0**）。

BM25 的第 1 名被哪個詞推上去（**MEAS**，60 句換句話說查詢）：

| 主推 token | 次數 | BM25 第 1 名 |
|---|---|---|
| `everyday` | 37 | Nike Women's Free Everyday White Orange Shoe |
| `workout` | 12 | Puma Women's Essential Workout Black Track Pant |
| `jet` | 3 | — |
| `emerald` | 2 | Revlon Grow Luscious Emerald Lash Liner |
| 其他（`office`/`lady`/`violet`/`pants`） | 6 | — |

**這張表就是簡報上該放的那張圖**：60 句查詢裡有 49 句，整份排序被 1–2 件商品名稱裡的巧合綁架。

### 1.3 為什麼我們的崩盤比文獻嚴重那麼多 —— 這個落差要先解釋掉

**Penha, Câmara & Hauff, "Evaluating the Robustness of Retrieval Pipelines with Query Variation Generators", ECIR 2022（arXiv:2111.13057）**（V，子代理讀到表格）量到的相對衰退：TREC-DL-2019 上，**回譯改寫 BM25 −17%**、**WordNet 同義詞替換 BM25 −17%**、拼字錯誤 −47%、詞序 <0.01 NDCG@10。BERT/T5 在同義詞替換下反而掉更多（−31% / −22%）。

我們是 **−95%**（0.758 → 0.034）。落差的三個成因（**INF**，但每一條都有我們自己的數字支撐）：

1. **我們的「換句話說」是 100% 內容詞替換**（`eval/tasks.py::Query.text`：gender、color、subcategory、occasion 四個全換）。回譯改寫通常保留大部分內容詞。所以我們測的不是「paraphrase」，是**零內容詞重疊**的極端情況 — 比文獻的 paraphrase 嚴苛得多。這一點在簡報上必須講明，否則 −95% 會被當成誇大。
2. **我們每句查詢的正解只有 ~1 件**（NDCG@5 幾乎是二元的），TREC 是分級、多正解。二元指標在崩盤區的動態範圍大得多。
3. **我們的 ground truth 不是 BM25 pool 出來的**。BEIR（Thakur et al., NeurIPS 2021 D&B, arXiv:2104.08663，V）自己承認 qrels 有 lexical bias（TREC-COVID 補標後 ANCE 0.654→0.735，詞彙法幾乎沒動）。我們的標準答案來自資料集屬性，**沒有這個偏差**，所以 BM25 看起來會比在公開基準上更差 — 這是我們的數字比較誠實，不是比較糟。

> 簡報用語建議：不要說「BM25 崩盤 95%」，說「**在內容詞完全不重疊時** BM25 的 NDCG@5 從 0.758 掉到 0.034，而且它掉下去的方式是**自信地排錯**，不是沒有意見」。

### 1.4 建議加進 T1 harness 的診斷（可歸因，不只可量測）

三個，都不需要新模型，跑在既有 60/100 句查詢上：

**D1 — 2×2 oracle 歸因（§1.1）**：`scripts/eval_paraphrase_attribution.py`（新檔），對每句查詢跑 4 個條件（sparse×dense ∈ {para, lex}²），輸出每個 arm 的 2×2 與配對 p 值。**判讀**：`sparse=lex` 那一格的增益 ÷ `both=lex` 的增益 ＝ 稀疏側佔比。我們現在是 0.909。
**D2 — 逐詞歸因**：對 BM25 第 1 名的商品，單獨用每個 query token 算一次 BM25，報「主推 token、它的貢獻佔比、它的 df/idf、那件商品的標題」。**判讀**：主推 token 的 df 若 < 10，就是 §1.2 的 idf 病理。
**D3 — 閘門分辨力**：對每個候選閘門統計量（§5.1 那七個），報用詞相同 vs 換句話說的 AUC。**判讀**：AUC < 0.9 的統計量不要拿來當閘門。

⚠️ D1 的 `dense=lex` 那一格需要在 dense 那一路換文字，這在現行 `pipeline.py` 裡沒有掛鉤點 — 我是用 instance 上包一層 `query_embedding` 做到的（§7.6）。整進 repo 時建議在 `Engine02.run` 把 `bm25_text` 和 `dense_text` 拆成兩個區域變數（見建議 #2），D1 就自然可寫。

---

## 2. Q2：詞彙接地（vocabulary grounding）

### 2.1 我們的資源已經夠了 —— 而且已經寫好，只是在會壞掉的那條路上被繞過

**CODE**，`engine02/pipeline.py:47-62 build_retrieval_text()`：

```python
def build_retrieval_text(req, catalog=None) -> str:
    if req.retrieval_text:
        return req.retrieval_text      # ← 這一行就是繞過點
    ...
    ids = [i for i in resolve_category_values([v], tax) if i in tax.nodes]
    parts += [tax.retrieval_terms(i, catalog) for i in ids]
```

也就是說：**當 ENGINE 01 只填 `constraints` 時，我們會走 taxonomy 把值接到商品庫詞彙；當 ENGINE 01 填了自由文字 `retrieval_text`（＝實際上的主路徑，也正是會違約的那條路）時，taxonomy 一次都不會被查。**

而 taxonomy 已經認得 T1 用到的**每一個**子類同義詞（**MEAS**，`taxonomy.normalize_category`）：

```
tee → tops.tshirts          joggers → bottoms.track_pants   purse → bags.handbags
trainers → shoes.athletic   pullover → tops.sweaters        tunic → tops.tunics
pumps → shoes.heels         rucksack → bags.backpacks       slippers → shoes.slippers
blouse → tops.blouses       jumper → tops.sweaters          pants → bottoms.trousers
```

而且 `Taxonomy.retrieval_terms(nid, "kagl")` 會把 node 換回商品庫的 `subcategory` 值（`tops.tshirts` → `"T-shirts Tshirts"`）。**這條路整條都已經有了，只差被叫到。**

缺的只有**顏色／性別／場合**的同義詞 — taxonomy 是品類體系，沒有這三個。這是一份 ~60 條的 JSON（`midnight→Navy Blue`、`guy's→Men`、`workout→Sports`…），對應的封閉值集已經由 `GET /vocabulary` 提供。

### 2.2 我們量到什麼（三個變體，循環性依序遞減再遞增）

**MEAS**，60 句查詢、NDCG@5、配對置換 10,000 次、bootstrap 95% CI：

| 接地方式 | 用詞相同 `hybrid_rrf` | 換句話說 `hybrid_rrf` | 換句話說 `full_zclip3` | 循環性 |
|---|---|---|---|---|
| off（現況） | 0.830 | 0.191 | 0.186 | — |
| **只用既有 taxonomy（品類同義詞）** | 0.790（−0.040, p=0.0012） | 0.332（+0.141, p=0.0016） | 0.353（+0.168, p=0.0004） | **無**（資源是先前建的，我沒碰） |
| **taxonomy + SigLIP 接到最近屬性值** | 0.830（p=1.0） | 0.462（+0.270, p=0.0001） | 0.475（+0.289, p=0.0001） | **無**（沒有人工表） |
| **taxonomy + 人工 60 條同義詞表** | 0.830（p=1.0） | 0.578（+0.387, p=0.0001） | 0.556（+0.370, p=0.0001） | **有**（表是我看過 T1 的 paraphrase 才寫的） |
| ＋接地詞附加給 dense（B′） | 0.830（p=1.0） | **0.602（+0.410）** | **0.601（+0.415）** | 同上 |
| oracle（完美接地） | 0.830 | 0.773 | 0.735 | 上界 |

**兩個必須講清楚的方法細節：**

**(a) 「gated」是關鍵，沒有它就要付代價。** 第二列（只用 taxonomy、無條件接地）在**用詞相同**那欄掉了 0.040（p=0.0012）。原因是 taxonomy 會把一個 node 展開成多個商品庫值（`shoes` → `Casual Shoes Flats Flip Flops Formal Shoes`），對本來就講對詞的查詢那是純雜訊。加上閘門（**查詢對屬性值詞彙的覆蓋率 ≥ 0.5 就完全不碰這句查詢**）之後，用詞相同那欄變成**逐查詢完全相同**（d=0.000, p=1.0）。這正是 Amati (ECIR 2004) / Cronen-Townsend (CIKM 2004) 那一系「選擇性套用」的機制（U，子代理只核到 DOI 與主張，沒讀到數字）。

**(b) 接地字串只餵 BM25；dense 那一路是「附加」不是「取代」。** **MEAS**，只看純 dense arm，換句話說：原字串 0.463 / 只用接地字串 0.529（+0.067, **p=0.098 不顯著**）/ **原字串＋接地字串 0.575（+0.112, p=0.0002）** / oracle 0.614。取代會把 dense 本來就抓得到的語意訊號丟掉；附加不會。

### 2.3 失敗模式：用 embedding 接地時，接錯的相似度和接對的**重疊**

**MEAS**，把每個 query token 用 Marqo-FashionSigLIP text tower 接到 156 個商品庫屬性值裡最近的那一個：

**接對的（可用）**：`tee→Tshirts` 0.939、`joggers→Track Pants` 0.936、`purse→Handbags` 0.947、`pumps→Heels` 0.939、`rucksack→Rucksacks` 0.962、`tunic→Tunics` 0.972、`workout→Sports` 0.893、`traditional→Ethnic` 0.895、`crimson→Red` 0.907、`violet→Purple` 0.927、`blush→Pink` 0.874、`chocolate→Brown` 0.845、`army→Olive` 0.823、`ash→Grey` 0.786、`guy→Men` 0.869。

**接錯的（危險）**：

| token | 接到 | cos | 正解 | 錯法 |
|---|---|---|---|---|
| `midnight` | **Rose** | 0.822 | Navy Blue | 顏色接到另一個顏色 |
| `jet` | **Travel** | 0.853 | Black | 顏色接到**場合** |
| `azure` | **Travel** | 0.735 | Blue | 同上 |
| `everyday` | **Travel** | 0.828 | Casual | 場合接到場合，但錯 |
| `snow` | **Skin** | 0.862 | White | 顏色接到顏色，但錯 |
| `lemon` | **Orange** | 0.850 | Yellow | 鄰近色錯接 |
| `lady` | **Girls** | 0.866 | Women | 性別接到未成年 |
| `anyone` | **Formal** | 0.788 | Unisex | 性別接到場合 |
| `button`（來自 button-up） | **Pendant** | 0.807 | — | 多詞片語被拆碎後的碎片 |
| `high` / `long` / `open` / `summer` | **Formal / Formal / Travel / Travel** | 0.83–0.88 | — | 同上 |

**這是本節最重要的一句**：`guy→Men`（0.869，對）和 `kid→Boys`（0.866，對）的相似度，**和 `jet→Travel`（0.853，錯）、`midnight→Rose`（0.822，錯）完全重疊**。所以 **「設一個 cosine 門檻就好」是行不通的** — **MEAS**：τ ∈ {0.0, 0.5, 0.6} 三個門檻跑出來的 NDCG **完全相同**（0.462 / 0.475），因為錯的那些也都在門檻以上。這就是「過度正規化把一個罕見但正確的詞碾掉」的具體形狀，我們自己量到了。

兩個可做的緩解（**INF**，未測）：
- **按屬性分池接地**：顏色只跟顏色比、場合只跟場合比，再用「哪一個屬性的 top-1 margin 最大」決定這個 token 屬於哪個屬性。現在 156 個值混在一池，所以顏色詞會掉進 `Travel`。
- **只接地 ENGINE 01 沒填的槽位**：如果 `constraints.color` 已經有值，就不要讓 query token 去接顏色。

### 2.4 文獻怎麼說這一家（以及它會給你多少）

這一家在產業文獻裡有名字：**query attribute value extraction（NER + AVN）** 或 **query entity linking**。

- **QUEACO（Amazon, CIKM 2021 Applied, arXiv:2108.08468）**（V）：明說前人「只做 NER 而忽略同樣重要的 AVN（把表面形式正規化成商品庫的標準值）」— 那正是我們要做的第二步。NER F1 **75.44**（最佳基線 74.97）；AVN F1 **83.08**（US）/ **86.74**（DE）。**線上：token 級 coverage +38.2%（span 精確度 97%），下游商品重排 NDCG@16 只有 +0.36%。**
- **Amazon brand entity linking（arXiv:2502.01555, CIKM）**（V）：兩種設計正面對打 —「NER→KB 精確比對」vs「端到端極多類分類（Q2E-PECOS）」。NER+exact：Coverage 58.28 / Recall 64.66 / **Precision 97.22**；Q2E-PECOS：Coverage 75.31 / Recall 77.35 / Precision 94.93。**關鍵的失敗模式數字：在「根本沒有品牌」的查詢上，誤標率 NER+exact 1.177% vs Q2E-PECOS 6.550%** — 拿 11 點 recall 換 5.6 倍的假警報。線上 A/B：品牌 recall +11.00%，但**顧客互動只有 +0.02%**。
- **BEQUE（Taobao, WWW 2024, arXiv:2311.03758）**（V）：**這是最能決定我們該不該做的數字。** 線上 A/B，長尾查詢 GMV +1.57%；**零結果查詢 GMV +18.66%、成交數 +5.90%**。**12 倍的差距。** 我們 NDCG 0.034 就是零結果／近零結果的狀態 — 文獻說這正是唯一會大賺的區間，其他地方都不會。
- **DeepCAT（Home Depot, arXiv:2104.11760，venue 未證實，U）**：長尾 F1@3 +7.1% 相對，**head 只是「與基線相當」**。**JointMap（SIGIR 2020, arXiv:2005.13783）**（U）：商品類別對應 +10%。兩篇獨立的產業論文都說這一家是**尾部限定**。
- **QueryNER（LREC-COLING 2024, arXiv:2405.09507）**（V）：公開資料集，17 種 chunk（含 `core_product_type` / `color` / `material` / `occasion`，和我們的 schema 幾乎一樣）。最佳 F1 **61.29**。**唯一一個直接量「過度正規化傷害」的實驗**：在 5,471 句零／低召回查詢上，「隨機丟 2 個 token」vs「丟掉一個已標註實體但**保留 core_product_type**」，後者在同樣的 recall 增益下相關性下降更小。**結論：絕對不要改寫或丟掉中心名詞。**
- **標籤數 vs 標註器品質**（V，跨兩篇）：12 種窄標籤 → F1 74；17 種寬標籤 → F1 61。**我們的 89 個 node 在這條曲線的壞邊**，建議先只接地到 12 個 L1。
- **Rakuten（NAACL 2024 Industry, 2024.naacl-industry.39）**（V）：日文電商，**查詢端 refinement +3.5 點，下游 NER +11.7 點**（相對於用 MeCab 前處理）。CJK 情境下「先把查詢端切詞／正規化做好」比標註器本身更值錢 — 對我們的中文側直接相關。
- **方法學（Hagen et al., arXiv:1111.1497 / arXiv:1312.0182，U）**：查詢切分必須**用檢索效果評估，不是用切分正確率**。→ 我們報 NDCG，不報接地 F1。
- **Hull, JASIS 1996（DOI 10.1002/(SICI)1097-4571(199601)47:1<70::AID-ASI7>3.0.CO;2-#）**（引用已核、**全文 NOT REACHED**）：詞幹還原的經典結論是「平均值會蓋掉傷害」— 方法學上的先例是**逐查詢報 win/loss 次數，不是只報平均 NDCG**。我們建議 T1 也這樣報。
- **Gross & Taylor, College & Research Libraries 66(3), 2005（DOI 10.5860/crl.66.3.212）**（V，子代理讀了 OA PDF）：反向的證據 —— 186 句真實關鍵字查詢，若拿掉 controlled vocabulary 的主題欄，**平均 35.9% 的命中會消失，31.7% 的查詢會掉一半以上**。這是「受控詞彙有價值」最強的量化論據，但它是 20 年前的圖書館學，不是電商，引用時要說清楚。

**沒有到手的（NOT REACHED，不要引用）**：Amazon「Advancing search using synonyms」部落格、eBay query rewriting 系列、Etsy Code as Craft 的 query-to-taxonomy、Taobao CIKM 2022「Query Rewriting in TaoBao Search」的內部數字、Hasibi 的 ICTIR 2015/2016 與 ECIR 2017 的內部數字（DOI 已核，數字沒到手）。

**期望值校準（這段要寫進簡報的風險欄）**：QUEACO +38.2% coverage → **NDCG@16 +0.36%**；brand linking +11% recall → **engagement +0.02%**。**產業界在「已經調好的排序器」上，這一家的平均效果是小數點後兩位。** 我們量到 +0.41 NDCG@5，差了兩個數量級 — 唯一合理的解釋是**我們現在的違約行為壞得離譜**（§1.2 的 idf 病理），我們修的是自己的 bug，不是在追 SOTA。這一點如果不講，數字看起來會像造假。

---

## 3. Q3：稀疏側、非查詢擴展的修法

### 3.1 學習式稀疏檢索（SPLADE / uniCOIL / DeepImpact）

| 模型 | 要訓練？ | query 端成本 | 索引端成本 | OOV／同義詞的已發表增益 |
|---|---|---|---|---|
| SPLADE-v3（arXiv:2403.06789，V） | 是 | 需 transformer forward | 重建索引 | MS MARCO MRR@10 40.2；**BEIR-13 51.7 vs BM25 43.7** |
| **SPLADE-v3-Doc**（同上，V） | 是（只訓 doc encoder） | **query 端純查表，和 BM25 同級** | 每份文件一次 forward | BEIR-13 **47.0** vs BM25 43.7 |
| Two-Step SPLADE（ECIR 2024, arXiv:2404.13357，V） | 是 | **2.4 ms（MS MARCO）/ 4.3 ms（BEIR）**，1.4–1.8× BM25 | 兩份倒排索引 | MS MARCO 40.0，BEIR 47.6 |
| uniCOIL（arXiv:2106.14807，V） | 是 | 中 | 需搭 doc2query 才有擴展 | MRR@10 0.315（無擴展）/ 0.352（有） |
| DeepImpact（SIGIR 2021, arXiv:2104.12016，V） | 是 | **58.64 ms/query**（BM25 13.24 ms） | — | MRR@10 0.326 |

三個決定性的細節：
1. **延遲的殺手是 query encoder，不是檢索**。Lassance & Clinchant, SIGIR 2022（arXiv:2207.03834，V）：**DistilBERT query encoder 平均 45.3 ms，BERT-tiny 0.7 ms**，差距只值 ~1.0 MRR@10。我們 `/rank` 全程 12.8 ms（§3.21），DistilBERT 一個就吃掉三倍預算。
2. **query 端擴展根本不值錢**。Nguyen, MacAvaney & Yates, ECIR 2023（arXiv:2303.13416，V）：把 MLM query encoder 換成一個 MLP（＝取消 query 端擴展），**延遲降 >74%，MRR 38.0 與 R@1k 97.0 完全不變**。文件端加權才是主力（≥11 點），query 端只值 1–4 點。
3. **SPLADE 的優勢是不是「同義詞」其實有爭議**。SPRINT（SIGIR 2023, arXiv:2307.10488，V）把 SPLADEv2 限制在 passage 內的 token 時，**8 個資料集有 6 個輸給 uniCOIL** — 優勢確實由擴展 token 撐著；但 arXiv:2306.16680（V）發現拿掉最常被擴展的 top-100 個詞，RR@10 只從 35.5 掉到 35.2，而用 768 個**隨機** token 就能拿到 28.4。**詞彙表的大小比組成重要** — SPLADE 比較像披著倒排索引外衣的 dense 檢索器，不是一本可解釋的同義詞典。這對我們的「可解釋加總」立場是負面的。

**我們的結論：不做。** 三個 blocker，任一個單獨就足夠：
- **授權**：SPLADE v3 權重是 **CC BY-NC-SA 4.0＝非商用**（`docs/research/engine02-method-inventory.md` §4 已查證，V）。贊助商是 Makalot，非商用授權直接出局。商用可行的替代是 **OpenSearch neural sparse doc-v3-distill（Apache-2.0，query 端免推論）**（同上，授權 V／「免推論」U），如果之後真的要做，這是唯一該評估的那一個。
- **工期與風險**：要訓練、要重建索引、要重跑所有 §3.1–3.20 的數字。
- **它解不了我們的問題**：我們的問題已經被歸因成「一個 df=1 的巧合詞拿到最高 idf」（§1.2），那是**我們自己沒有把查詢接地**造成的，不是 BM25 的表達力不足。

### 3.2 文件擴展（doc2query 家族）

**doc2query（arXiv:1904.08375，V）自己的消融，是本節最重要的數字**：預測出來的非停用詞裡 **69% 是文件裡已有的詞，只有 31% 是新詞**；**只用新詞 MRR@10 18.8、只用複製詞 19.7、兩者都用 21.5**（BM25 基線 18.4）。也就是**詞彙橋接本身只值 +0.4**，doc2query 的價值主要在**詞權重重估**。

**Doc2Token（Walmart, arXiv:2406.19647，V）**是針對這個問題做的：只預測**缺少的 token**，新詞率 **~100%**（doc2query ~20%）；索引時 76 分鐘/10 萬件、**query 端零成本**；**線上 A/B 營收 +0.28%（p=0.013）、NDCG@10 +0.49%（p=0.066），已全量上線**。Doc2Query--（ECIR 2023, arXiv:2301.03266，V）用 ELECTRA 過濾掉爛的擴展：RR@10 0.279→0.323，**索引小 33%、延遲快 23%**。

**我們的結論：不做。** Doc2Token 需要 **1030 萬對 product–token 的 query log** 來訓練，我們沒有 query log（`docs/research/catalog-options.md` 裡的資料集都沒有）。doc2query 家族本身按它自己的消融只值 +0.4 MRR。而且它是索引時的方案 — 對 demo 時評審現場打的字沒有幫助。

### 3.3 字元 n-gram／模糊比對／詞幹還原

**機制不對**。這一家處理的是**正字法變異**（拼錯、字形、複合詞），不是同義詞。
- Zhuang & Zuccon, EMNLP 2021（arXiv:2108.12139，V）量的是 typo：MS MARCO 上 BM25 0.187→0.120（−35.8%），**dense 掉得更多**（0.296→0.141，−52.3%）。注意方向與 paraphrase 相反。
- Manning, Raghavan & Schütze, IIR §2.2.4（V，子代理直接讀到）：英文詞幹還原「aggregate 上傾向於不改善檢索效果 —— 至少改善不多」，「對某些查詢幫很大，對另一些傷害同樣大」，且「提高 recall、傷害 precision」。形態豐富的語言（西/德/芬）才有大增益。
- Harman 1991、Hull 1996、Krovetz 1993、McNamee & Mayfield 2004：引用與 DOI 已核，**全文 NOT REACHED**，不要引數字。

**我們的資料直接否掉這一家**：`tee` 和 `Tshirts`、`midnight` 和 `Navy Blue` 之間**沒有任何字元重疊**。字串相似度在我們的 paraphrase 集上結構性無效（**INF**，但從 §2.2 的對照表可以直接看出來）。

**唯一值得做的一件小事**：`engine02/sparse.py:_TOKEN = re.compile(r"[a-z0-9]+")` 會把 `guy's` 切成 `guy` + **`s`**，而 `s` 在商品庫裡 df=249（來自 `Men's`／`Women's`），idf 2.947 —— **一個純粹的切詞產物拿到了真實的分數，而且它還把現行的 coverage 閘門撐過門檻**（§5.1）。把單字元 token 丟掉（或把所有格 `'s` 併入前一個詞）是 1 行的修正。**MEAS**：換句話說的查詢平均有 1/6 到 1/8 的「覆蓋率」是 `s` 貢獻的。

---

## 4. Q4：dense 側

### 4.1 我們有沒有違反 Marqo-FashionSigLIP 的 model card 要求？**目前看起來沒有，而且有兩個獨立證據**

1. **CODE**：`engine02/models.py::TorchEncoder._txt` 對 `open_clip` backend（Marqo 走這條）直接呼叫 `self.model.encode_text(self.tok(texts))`。open_clip 的 tokenizer **自己會 lowercase**（`whitespace_clean(basic_clean(text)).lower()`）。**MEAS**：把整句查詢改成全大寫再跑，NDCG@5 **逐查詢完全相同**（d=+0.000, p=1.0000，用詞相同與換句話說都是）。所以我們沒有重蹈 `hf_siglip` 那條路的 0.04→0.61 大小寫 bug（那條路 `models.py` 裡已經明確 `texts = [t.lower() for t in texts]` 並 `padding="max_length", max_length=64`）。
2. **既有證據**：`docs/research/external-benchmarks.md` §2.1b — Marqo 官方 fashion benchmark 的 **18 格公布數字全部落在我們的 95% CI 內**（KAGL SigLIP R@1 0.178 vs 公布 0.179；InShop MRR 0.330 vs 0.330），而且 `dense` arm 與純 encoder **逐條完全相同**。若我們的 tokenizer／正規化有錯，這 18 格不可能同時對上。

### 4.1b Marqo-FashionSigLIP 的 model card 逐條（子代理直接抓 HF 上的原始 config，V）

| 項目 | 事實 | 我們有沒有違反 |
|---|---|---|
| 基礎模型 | `ViT-B-16-SigLIP`（webli），224px，embed_dim 768 | — |
| Tokenizer | **T5Tokenizer / SentencePiece Unigram，32k vocab — 不是 CLIP BPE** | 我們走 `open_clip.get_tokenizer("hf-hub:Marqo/...")`，拿到的就是對的那一個 ✅ |
| `context_length` | **64**（`open_clip_config.json`、`model_max_length`、padding、truncation 四處一致） | **MEAS** 我們的 T1 查詢 tokenize 後是 **4–8 個詞**，離 64 很遠 ✅（這也直接排除了「其實是截斷 bug」的假設） |
| 文字前處理 | `tokenizer_kwargs: {"clean": "canonicalize"}` → `canonicalize_text`：**轉小寫、把標點整個刪掉（不是換成空白）、`_`→空白、壓縮空白** | 大小寫我們沒問題（**MEAS** 全大寫查詢逐查詢結果相同）✅ |
| padding | SigLIP 訓練時是 `padding='max_length'`（HF SigLIP 文件明寫） | open_clip 路徑的 tokenizer 已經 `Fixed 64` padding ✅。⚠️ **但 `MarqoFashionSigLIPProcessor.__call__` 的 `padding` 預設是 `False`** — 如果之後有人改走 HF `AutoModel` 路徑而沒有明寫 `padding='max_length'`，會靜默地訓練／推論不一致 |
| L2 正規化 | `get_text_features(..., normalize=False)` 是**預設** | 我們在 `encoders.l2n` 自己做 ✅ |
| caption 模板 | **完全沒有文件記載**。model card 的範例全是裸標籤（`["a hat", "a t-shirt", "shoes"]`）；Marqo 自己的 benchmark 程式 `eval.py` 的 `--query-prefix` **預設是空字串** | 我們也是裸查詢 ✅ |
| 圖片端 | `resize_mode: "squash"`（不是 letterbox／center-crop） | 未查（本輪不碰圖片端） |

⚠️ **一個之前沒注意到、值得記一筆的機制（INF）**：canonicalize **把標點刪掉而不是換成空白**，所以 dense 那一路實際收到的是 `guys midnight tee for workout`、`ladys jet highheeled pumps for everyday`、`buttonup`、`opentoe`。也就是說**我們的 paraphrase 查詢裡的連字號片語在進 text tower 之前就被黏成了一個罕見字串**。這很可能是 dense 側 0.614→0.463 的一部分原因，而且**和 BM25 那一路的切法完全不同**（`sparse.py::tokenize` 用 `[a-z0-9]+`，會切成 `button` + `up`）。兩側對同一句話的切法不一致，是一個未量測的隱性風險 — 建議 #3 的診斷可以順手印出兩側實際看到的字串。

⚠️ **SigLIP 論文（Zhai et al., ICCV 2023, arXiv:2303.15343）§4.2 與 checkpoint 不一致**（V）：論文寫「English C4 訓練的 32k sentencepiece tokenizer，**最多保留 16 個 text token**」，但**所有釋出的 checkpoint（含 Marqo 的）ship 的是 64**。子代理找不到任何調和兩者的來源。**以 config 的 64 為準**（那是實際生效的值）。另外論文**沒有**提 lowercase／canonicalize — 那只存在於 big_vision / open_clip 的程式碼裡，不是論文主張。

### 4.2 Prompt ensembling：**我們量了，無效**

**MEAS**，純 dense（image emb 快取 × text tower），60 句查詢：

| 查詢模板 | 用詞相同 | 換句話說 |
|---|---|---|
| `{q}`（現況） | 0.614 | 0.463 |
| `a photo of {q}` | 0.644（+0.030, p=0.074） | 0.458（−0.005, p=0.686） |
| 3 模板平均 | 0.633（+0.018, p=0.146） | 0.460（−0.003, p=0.639） |
| 6 模板平均 | 0.634（+0.019, p=0.182） | 0.463（**+0.000, p=0.954**） |

文獻怎麼說（V，子代理逐字核對 CLIP 論文 §3.1.4）：CLIP 的模板是**零樣本分類**的招 —「只用 `a photo of a {}` 這個 prompt 就讓 ImageNet 準確率 +1.3%」、「ensemble 80 個 context prompt 再 +3.5%」、「兩者合起來將近 +5%」，而且是**在 embedding 空間平均**（所以攤提後成本等同單一分類器）。

**但檢索的評測慣例是完全不用模板**（V，子代理直接讀原始碼）：LAION `CLIP_benchmark/metrics/zeroshot_retrieval.py` 把 caption 原封不動丟給 tokenizer，函式簽名**根本沒有 `templates` 參數**；相對地 `zeroshot_classification.py` 的 `templates` 是**必填位置參數**。Marqo 自己的 benchmark（`marqo-ai/marqo-FashionCLIP`）也一樣，`--query-prefix` 預設空字串 — **也就是說 model card 上那些公布數字就是用裸查詢量的。**

機制上的理由是站得住腳的：分類時你要從一個裸標籤（`crane`）合成一句查詢，所以必須補句子脈絡；檢索時查詢本來就是自然語言、和訓練 caption 同分布，沒有要補的落差。

⚠️ **但要講精確**：子代理查不到任何一篇論文或 benchmark 量過「prompt ensembling 對檢索**有害**」。「檢索不用模板」是**慣例的證據，不是消融的證據**。所以 **§4.2 這張表是我們自己量的、而且據我們所知是這個問題上少見的直接量測** — 可以放進簡報，但要說明它是我們的 null result，不是在複現別人的。

另外一個 Marqo 特有的機制（**INF**）：canonicalize 會把標點刪掉，所以 `"A photo of a {}."` 和 `"a photo of a {}"` **會塌成同一個字串** — 80 個模板裡有效不同的比計數少得多，ensemble 的多樣性先天就被砍掉一截。加上 GCL 是用**真實搜尋查詢**（不是 caption）訓練的，短的裸查詢本來就在分布內。

**不做。**

### 4.3 「只用 LLM 正規化查詢，不用來改寫解釋」

這是 §2 接地的 LLM 版本，而且是**產業主流**：Musinsa 用 Bedrock Nova Lite 做 query rewriting（`docs/research/industry-fashion-brands.md`，V）；Taobao BEQUE 用 LLM 改寫長尾查詢（V）。

**但我們的建議是：先做規則版（§7 建議 #2），LLM 版留給 ENGINE 01。** 理由：
- **延遲**：`/rank` 是 12.8 ms，LLM 一次呼叫 ≥ 幾百 ms。§3.21 已經明寫 LLM 只用在解釋且共用 1.5 秒預算、失敗即退模板；把 LLM 放進**檢索路徑**會讓 12.8 ms 的成績整個作廢。
- **職責**：把自由文字變成商品庫詞彙**就是 ENGINE 01 的工作**（§4.1「硬性需求」）。我們在 ENGINE 02 做的應該是**便宜的、確定性的、可解釋的兜底**，不是第二套 NLU。
- **可驗證性**：規則接地的每一步都可以寫進卡片（「你說的『tee』對到商品庫的『Tshirts』」）；LLM 接地要再做一層 fact-check（我們已經為解釋做了一次，`explain.py::verify_paraphrase`）。
- OptAgent（arXiv:2510.03771，U）自己也說「改寫有沒有抓到意圖，演算法上極難判斷」，產業的答案是**要一個驗證器**，不是一個改寫器。

### 4.4 文字側多向量（multi-vector）

**不建議**，兩個理由：(a) 會直接破壞 `_terms` 的可加總結構（一個 MaxSim 項沒辦法拆成「這個詞貢獻多少」）；(b) `docs/research/engine02-method-inventory.md` 已經對 ColPali/ColQwen 下過判斷 —「為**文件頁面**設計，商品圖用多向量很浪費，**不建議**」（V）。

---

## 5. Q5：融合端的閘門

### 5.1 我們的 `bm25_adaptive` 閘門為什麼救不動，以及哪一個統計量才對

**CODE**，`engine02/sparse.py::BM25Index.coverage`：

```python
def coverage(self, query: str) -> float:
    q = tokenize(query)
    return sum(t in self.vocab for t in q) / len(q) if q else 0.0
```

`self.vocab` 是 **title + description + subcategory + color 全文的 token 集合**（`catalog.py::TEXT_FIELDS`）。於是 `everyday`（因為一雙 Nike 鞋）、`jet`、`emerald`（因為一支眼線筆）、`s`（因為 `Men's`）**全部算「有覆蓋」**。

**MEAS**，換句話說的 60 句查詢：平均 coverage **0.668**，**93.3% 通過 `bm25_min_coverage = 0.5`**。閘門幾乎不觸發 —— 這就是 `full_adaptive_bm25` 只從 0.093 到 0.175 的全部原因。

七個候選閘門統計量的分辨力（**MEAS**，AUC＝隨機抽一句用詞相同、一句換句話說，前者統計量較大的機率；1.0 完美、0.5 無資訊、0.0 完美反向）：

| 統計量 | 家族 | AUC | 用詞相同中位數 | 換句話說中位數 |
|---|---|---|---|---|
| **命中 token 的屬性值覆蓋率**（建議 #1） | 詞彙 | **1.000** | 1.000 | **0.000** |
| **BM25 分數非零的商品比例** | 計數 | **1.000** | 0.549 | 0.051 |
| 命中 token 的 df 中位數 | 詞彙 | 0.999 | 392.8 | 5.0 |
| **σ50% 的 N（分數 ≥ 最高分 50% 的文件數，Cummins 2011）** | 計數 | **0.994** | 149 | 10 |
| `coverage`（現行，全文詞彙） | 詞彙 | 0.975 | 1.000 | 0.667 |
| BM25 前 10 名的平均分 | 分數 | 0.972 | 9.92 | 6.72 |
| **n(σ50%)**（Cummins SIGIR 2011 的推薦預測器） | 分數離散度 | **0.792** | 0.608 | 0.422 |
| σ50%（未長度正規化） | 分數離散度 | 0.698 | 1.280 | 0.991 |
| **BM25 最高分**（＝題目問的「是不是都接近 0」） | 分數 | **0.678** | 11.55 | **9.59** |
| WIG（Zhou & Croft 2007） | 分數 | 0.644 | 3.250 | 2.825 |
| **NQC（Shtok et al. TOIS 2012；文獻最佳的分數離散度預測器）** | 分數離散度 | **0.001（完全反向）** | 0.301 | **1.763** |
| 命中 token 的最高 idf | 詞彙 | **0.030（完全反向）** | 3.88 | 8.11 |

**直接回答題目的第 5 題（兩層）：**

**(a) 「檢查 BM25 前 k 名的分數是不是都接近 0」在我們的資料上是最差的候選之一（AUC 0.678）。** 原因就是 §1.2 —— 換句話說的查詢**分數一點都不低**（中位數 9.59 vs 11.55），只是分給了錯的商品。

**(b) 更強的結論：整個「分數離散度」家族 —— 也就是文獻裡證據最好的那一家 —— 在我們這裡不是弱，就是反向。** 子代理找到的最佳可及證據是 **Cummins, Jose & O'Riordan, SIGIR 2011**（V，讀到全文表格）：在 TREC News 上 NQC 的 Pearson r 是 0.523/0.527，他們提出的 **n(σ50%) 是 0.569/0.604**，且相對 NQC 顯著（Wilcoxon p=0.012）；**Meng et al., SIGIR 2023（arXiv:2305.10923）**（V）還特別指出 NQC/σmax/SMV「**對各種 query rewrite 是不變的，因為它們只依賴檢索分數**」—— 聽起來正是我們要的性質。

**我們量了，結果是：n(σ50%) AUC 0.792（普通），NQC AUC 0.001（完全反向）。**

NQC 反向的機制很清楚（**INF**，但可以從定義直接推）：`NQC = std(top-100) / mean(top-1000)`。換句話說的查詢只有 ~250 件商品拿到非零分數，所以**分母（top-1000 的平均）幾乎是 0**，比值就爆掉。若照文獻的方向解讀（NQC 高＝查詢容易／檢索器有信心），**我們會把崩盤的那些查詢判成最健康的一批** —— 這是一個會直接製造事故的誤用。

同一篇 Meng et al. 自己給了判準（V，逐字）：「score-based 方法有沒有效，取決於**該檢索器的分數分布**」。我們的 BM25 在商品庫上是極度偏斜的（§3.10 已記載：大部分商品 0 分、少數命中的 z 值可到 +7），這個分布讓所有以「top-k 分散度 ÷ 背景」為形式的預測器失去意義。**Faggioli et al., ECIR 2023（arXiv:2302.09947）**（V）也量到 QPP 在神經檢索器上顯著更差，且「對 bi-encoder，post-retrieval 預測器不是表現極好就是完全失效」。

**真正有效的是「計數」不是「離散度」**：非零分數的文件比例（AUC 1.000）、σ50% 的 N（AUC 0.994）、命中 token 的 df（0.999）。三個講的是同一件事 —— **這句查詢到底碰到了商品庫的多少東西**。而「命中 token 的最高 idf」是完美的**反向**偵測器（AUC 0.030）：換句話說的查詢命中的是**更稀有**的詞。

⚠️ **AUC 1.000 要打折看**（下一段），而且 NQC 的 AUC 0.001 同樣是在我們合成的兩個極端之間量的。真實的「半正規化」查詢會落在中間，反向的方向性應該會保留，但強度不會。

⚠️ **AUC 1.000 要打折看**：我們的 paraphrase 集是**合成的、而且是全部內容詞都換**，所以兩群完全不重疊。真實世界的「半正規化」查詢會落在中間。這些 AUC 應該讀成「**在我們自己定義的兩個極端之間，哪個統計量有機制上的分辨力**」，不是「線上會有多準」。上線前要在真實查詢上重驗閾值。

### 5.2 「換個融合函數」在我們的資料上是**反向**的

文獻很一致地說 convex combination ≥ RRF：
- **Bruch, Gai & Ingber, TOIS 2023（arXiv:2210.11934）**（V，repo 既有引用 `engine02-literature-review.md:78`）：證明 convex combination **對正規化方式不變**（Lemma 4.2 / Theorem 4.5）；**RRF 並非無參數**（Eq. 8 的 η_Lex/η_Sem 可調，自由度比 CC 的 α 還多）；**RRF 只用名次、丟掉分數分布，不滿足 Lipschitz 連續性**（footnote 9）—— 這就是「一份分數全≈0 的名單仍然以第 1 名、第 2 名的身分投滿票」的形式化陳述。Table 2：CC（TM2C2）在**九個資料集**的 NDCG 全部 ≥ RRF。
  **而這一段是本檔最重要的一則引用**（V，逐字，§3）：
  > *"in cases where the variance of lexical (semantic) scores in the union set is 0, **we may skip the fusion step altogether** because retrieval quality will be unaffected... **The case where the variance is arbitrarily close to 0, however, creates challenges for certain normalization functions.** While this would make for an interesting theoretical analysis, **we do not study this particular setting in this work**, as empirically we do observe a reasonably large variance among scores in the union set on all datasets."*

  也就是：**這個領域最新的融合分析論文，明確點名了我們所在的狀況、明確建議了我們要做的處置（整個跳過融合）、明確警告正規化在那裡會壞掉，然後說他們不研究它。** 這同時是建議 #1 最好的文獻靠山，也是「沒有人解過這題」的證明。
  另外兩個可直接用的結論：(a) **推薦 TMM（理論 min-max）而不是觀測 min-max**，理由是「**少一個依賴資料的統計量**」—— 而那個統計量正好是崩掉的名單會汙染的那一個；(b) **per-query 的 α oracle 還值 +0.035 ～ +0.093 NDCG（相對 7–20%）**，作者明說留給未來研究、且「相當不簡單」。這是「逐查詢 gating 有多少上限」的已發表數字。
- **RRF 的原論文其實沒測過「一份爛名單」**（V，子代理讀了 2 頁 PDF 全文）：Cormack, Clarke & Büttcher, SIGIR 2009 的 k=60 是「pilot 定下來就沒再動」，敏感度表 k∈[10,100] 的 MAP 只在 .2123–.2147 之間浮動（「near-optimal, but the choice was not critical」）。k 的作用他們寫成 *"mitigates the impact of high rankings by outlier systems"* —— 但**全文沒有任何一個刻意注入壞的／隨機的／空的 run 的實驗**。而他們宣傳的優點「一兩個系統把某文件排很高就能大幅提升它的名次」，**逐字就是我們的失敗模式被當成特色在講**。→ **「RRF 對壞的 run 有韌性」是民間傳說，不是 Cormack 他們量過的東西。**
- **最乾淨的實證對照：Ma, Sun, Pradeep & Lin, "A Replication Study of Dense Passage Retriever"（arXiv:2104.05740）**（V）。看 SQuAD 那一列：DPR 崩了（top-20 52.0，BM25 71.1）；用原論文**固定**的融合權重，hybrid 得到 **66.2 —— 比健康的那一路單獨還差**；重調 α 之後回到 75.1。而五個資料集的最佳 α 從 **0.3 到 28，擺盪約 90 倍**。**這是「不 gating 的代價」最直接的已發表量測，而且和我們 §3.1 的形狀一模一樣。**
- **"Balancing the Blend"（arXiv:2508.01405）**（V）把我們的現象命名為 **weakest link phenomenon**：Touché 上 dense 單獨 0.390、全文單獨 0.650、融合 0.604（**比較強的那一路單獨還差**）；MS MARCO 上 dense 單獨 0.830、FTS+DVS 0.816。機制就是弱路徑「用不相關文件污染候選池」，而「**RRF 這種依賴文件出現在多份名單裡的方法受害最深**」。他們的建議是 **runtime 的 path-wise 品質評估／動態剪枝**，不是靜態全收。
- ⚠️ **但學界的路由器目前全部失敗，這是決定「做 on/off 而不是做權重回歸」的關鍵證據**：
  - Bruch 自己的 per-query α oracle 有 7–20% 的空間，但他們沒做。
  - **Wu & Lin, arXiv:2608.00183**（V，逐字）：oracle headroom **21.8%**，但三個輕量自適應路由器（分數信心啟發式、query 特徵 random forest、query embedding ridge）**沒有一個在 company-grouped 交叉驗證下顯著贏過固定混合**。
  - **Genc, Korukluoglu & Allan, arXiv:2606.25249**（V，逐字）：per-query routing「**從有限監督學起來並不簡單**」，實測落在 **−17.5% ～ +4.0% nDCG@10**。
  - **能成功的先例都是二元 on/off，而且用的是「結果集之間的比較」不是「查詢本身的特徵」**：Cronen-Townsend et al., CIKM 2004 的選擇性 QE 是「比較擴展前後兩個結果集的語言模型」；Arabzadeh, Yan & Clarke, CIKM 2021（arXiv:2109.10739）較強的那個分類器用的是**檢索後的證據（sparse 的 top-1 文件）**，不是查詢文字，在 50% dense 預算下 Recall@1000 0.95 vs 隨機路由 0.91。
  - **Liang, McDonald & Ounis, arXiv:2607.12098**（V，逐字）：108 位使用者、43 句 TREC DL 2019 查詢，**只有 20.9% 的查詢因 PRF 受益、25.6% 受害**，而且「**避免傷害的價值幾乎是利用成功擴展的兩倍**」→ 主張**不對稱的路由損失**。他們還警告：既有的選擇性 PRF 方法「用的 QPP 來自**和排序器同一組分數統計量**，所以是繼承而不是解決那個不透明性」。
  → **對我們的意義**：建議 #1 的閘門用的是**詞彙統計量（token 在不在屬性值詞彙裡）**，不是 BM25 自己的分數統計量 —— 正好避開 Liang et al. 警告的那個循環。這是它比分數閘門更該被採用的第二個理由（第一個是 AUC）。

**但我們的 §3.1 既有數字方向相反**：換句話說時 `hybrid_convex` **0.119 < hybrid_rrf 0.191**；用詞相同時 convex 0.865 > RRF 0.830。**INF** 的機制解釋：min-max 正規化會把 BM25 那一個 df=1 的巨大 outlier 拉成 1.0、其他全部壓到接近 0，等於把病理**放大**；RRF 的名次化反而把它壓成「只有一個第 1 名」。所以在**我們這個特定的 idf 病理**下，RRF 的分數失明反而是保護。

**結論**：不要因為 Bruch 就把預設換成 convex。Bruch 的前提是「兩路都載有訊號、只是尺度不同」；我們的情況是「一路載的是系統性的錯訊號」。**融合函數不是修這個問題的地方**（§1.1 已量到融合可撿的空間只有 7%）。

### 5.3 實務界怎麼做

子代理直接 WebFetch 各家官方文件（V，除非另註）：

| 產品 | 融合選項 | 預設 | 版本 |
|---|---|---|---|
| **Weaviate** | `rankedFusion`（1/(rank+60)）、`relativeScoreFusion`（min-max） | **v1.24 起預設 `relativeScoreFusion`**，alpha 預設 0.75 | v1.24+ |
| **Elasticsearch** | `rrf` retriever、`linear` retriever | RRF `rank_constant`=60；linear `weight`=1.0，normalizer `none`/`minmax`/`l2_norm` | linear 9.1 GA，per-sub-retriever normalizer 9.2 |
| **Vespa** | `normalize_linear`、`reciprocal_rank`(k=60)、`reciprocal_rank_fusion`、atan squash、乘法式 | **沒有預設** —— 全部提供，叫你自己量 | current |
| **Qdrant** | `rrf`、`dbsf`（distribution-based，3σ 端點） | RRF；**weighted RRF 從 v1.17.0** | v1.10/1.11/1.17 |
| **Milvus** | `RRFRanker`(k=60)、`WeightedRanker`（**arctan 壓到 [0,1]**） | — | v3.0.x |
| **OpenSearch** | norm `min_max`/`l2`/`z_score` × comb `arithmetic`/`geometric`/`harmonic_mean` | min_max + arithmetic_mean，等權 | 3.5 |

**四個對我們有用的具體發現：**

1. **Vespa 是唯一一家在官方文件裡明白處理「某一路貢獻 0」的**（V，逐字，`docs.vespa.ai/en/learn/tutorials/hybrid-search.html`）：他們的乘法式 baseline 是 `closeness(...) * (1 + (bm25(title) + bm25(text)))`，並解釋 *"We add a bias constant (1) to avoid the overall score becoming 0 if the document does not match any query terms, as the BM25 scores would be 0."* 這處理的是「BM25 全 0」而不是我們的「BM25 全錯」，但它是唯一一家承認這個情境存在的。
2. **OpenSearch 是唯一出貨了「絕對分數閘門」的**（V）：`min_max` normalizer 接受 per-subquery 的 `lower_bounds`/`upper_bounds`，各自有 `mode ∈ apply/clip/ignore` 和 `min_score`。「若沒給 `lower_bounds`，OpenSearch 使用結果中實際的最小分數」—— 也就是你可以把某一路的下限釘在一個**絕對**分數上，讓崩掉的那一路的雜訊沒辦法被 rescale 上來。他們自己沒有這樣描述它，但機制就是這個。
3. **Milvus 的 arctan 在架構上最穩健**（V）：arctan 是 **batch-independent 且單調**的，崩掉的檢索器分數會**留在低處**，而不是像 min-max 那樣被拉成 1.0。**這正是我們 §3.1 `hybrid_convex`（min-max）在換句話說時比 RRF 還差的機制。**
4. **Qdrant 最直白地點名這個機制**（V，逐字）：DBSF「**單一的主導性 outlier 會扭曲該查詢的正規化。如果看到排名不穩，增加 prefetch `limit`**」；以及「**DBSF 與 weighted RRF 誰也沒有主宰對方**」。

⚠️ **更正一個題目裡的前提**：我原本以為 Weaviate 把 `relativeScoreFusion` 設為預設的理由是「對 outlier／對某一路回傳無關結果更穩健」。**子代理自己抓了那篇 blog（weaviate.io/blog/hybrid-search-fusion-algorithms，2023-08-29，Dirk Kulawiak & JP Hwang）＋兩次定點查證，都沒有這句話。** 官方給的理由是「**relativeScoreFusion 比只保留名次的 rankedFusion 保留了更多原始搜尋的資訊**」＋內部 benchmark 的「recall 改善約 6%」。**這個記憶是 UNCONFIRMED，不要寫進簡報。** Weaviate 唯一承認正規化不穩的地方在 GraphQL 參考文件：limit 小的時候 `relativeScoreFusion` 對 limit 極度敏感，所以他們**自動先用 limit=100 搜再裁切**。

**最重要的一句**（子代理的結論，我同意）：**針對「某一路完全沒有可用結果」這件事，所有廠商的文件基本上都沒有指引。** Weaviate、Elastic、Milvus、OpenSearch 全都沒有記載任何關於某個 subquery 回傳空的或退化結果的處理。每一家用 batch-relative 正規化的廠商，給的緩解都一樣（**把候選池加大**：Weaviate 自動 oversearch 到 100、Qdrant 叫你加 prefetch limit）—— **沒有一家出貨我們真正需要的東西，也就是絕對分數（或絕對詞彙）的閘門。**

**文獻缺口（子代理的 arXiv 全文搜尋全部 0 筆）**：`abstention retrieval confidence reject ranked list`、`rank fusion robustness poorly performing run detect discard`、`selective retrieval predict when dense retriever fails`、`"query performance prediction" "rank fusion"`。**看起來沒有任何一篇論文專門處理「在融合時偵測並丟棄一份失敗的名單」。** 這對我們是好消息（建議 #1 有新意，而且 Bruch §3 逐字說了該這麼做），也是壞消息（沒有前人數字可借，我們自己的 AUC 就是全部的證據）。

其他 repo 既有的二手條目：`engine02-literature-review.md:80`（Qdrant 電商稀疏 embedding，V）ESCI nDCG@10 BM25 0.305 / SPLADE 0.326 / 微調 SPLADE 0.389；`:81`（U）Elastic／Weaviate 都強制先正規化。
**NOT REACHED（不要引用）**：「Announcing the Vespa reciprocal rank fusion」找不到這篇；一個 Elastic Search Labs 的「RRF vs linear」blog URL 404；Shtok TOIS 2012、Cronen-Townsend SIGIR 2002、Zhou & Croft SIGIR 2007、Zhao ECIR 2008 的**原始相關係數全部付費牆擋住** —— 本檔引用的 QPP 數字一律來自 Cummins SIGIR 2011 這篇可及的全文。

---

## 6. Q6：誠實的天花板 —— 這到底該不該是我們的問題？

### 6.1 論「不該投資 robustness」的那一邊（我大部分同意）

1. **合約已經寫了，而且是硬性需求。** `docs/engine02-design.md` §4.1 第 1 條：「詞彙對不上會直接造成 T1 那種崩盤」。`GET /vocabulary` 連**封閉詞彙表**（`closed_vocabulary`，含 zh 同義詞與三條給 GPT 的規則）都準備好了。`retrieval_text_normalized` 旗標也在合約裡。這不是我們沒把介面講清楚。
2. **混合檢索的真實價值遠比 T1 顯示的小。** §3.20，Amazon ESCI（**唯一有分級人工標註**的資料）：**BM25 相對純 dense 的邊際貢獻只有 +0.003 nDCG@10**（服飾切片 −0.003 p=0.33、完整集 +0.003 p=0.0001）。§3.1「用詞相同」那 0.22–0.30 的差距是**字面洩漏的上界情境**（查詢字面就取自商品屬性），我們自己的文件已經這樣標註。**所以「保住 BM25 在換句話說下的貢獻」這個目標，在真實查詢上值 0.003。**
3. **產業文獻說這一家的平均效果是小數點後兩位**（§2.4：QUEACO +0.36% NDCG@16、brand linking +0.02% engagement），而且**只在尾部有效**（DeepCAT、BEQUE 兩篇獨立確認）。
4. **每一分投在這裡的工，都不會出現在評分表上。** Demo 的情境是「評審出題 → 看結果 → 給回饋」，而 ENGINE 01 會把評審的自然語言轉成我們要的欄位。如果 ENGINE 01 做對了，這一節整個不存在。

### 6.2 論「還是要修」的那一邊（我認為決定性）

**現在的違約行為不是「降級」，是「劣化到比什麼都不做還糟」。**

這是關鍵的不對稱：
- 如果違約時我們退回純 dense，換句話說 NDCG@5 是 **0.463**。可以接受。
- 但我們**實際上**退不回去（閘門 93.3% 不觸發，§5.1），實際值是 **0.186**。
- 而「什麼都不做」——也就是**隨機**——在這個 grade 分布下也不會是 0.034。**BM25 單獨的 0.034 比隨機還差**，因為它系統性地把眼線筆和一雙 Nike 鞋推到第一。

**在 live demo 上，這不是一個指標問題，是一個舞台事故。** 評審打「我想要一件深藍色的T」，如果 ENGINE 01 那一輪沒把「深藍」正規化成 `Navy Blue`，現在的系統會很有自信地推薦一支 Revlon 眼線筆，而且**還會用可加總的解釋告訴評審「因為它的 BM25 分數很高」**。這是我們整個「可驗證解釋」敘事最糟的一種死法 —— 解釋是忠實的，忠實地解釋了一個 bug。

### 6.3 結論：**把合約「執行」得更嚴，而不是把系統做得更 robust**

我同意題目自己提的那個答案，但要加一個條件：

> **正確的工程答案是「讓合約更嚴格、違約時路由到 dense」—— 而我們現在並沒有真的在做這件事。** 建議 #1 花 6 行程式碼、0.003 ms，把這條路由從「寫在文件上」變成「真的會觸發」。這不是投資 robustness，是修一個**降級路徑失效**的 bug。

在那之上，建議 #2 的接地是一個**可選的加值**：它把違約情況從 0.463（dense）推到 0.601，成本 1.07 ms 且用詞相同零代價。我認為值得做，理由不是分數，是**它讓卡片能說一句真話**：「你說的『tee』，我對到了商品庫的『Tshirts』」。那句話同時是降級的說明、是可解釋性的加分、也是給 ENGINE 01 的除錯訊號 —— 三個用途一份成本。

**我不建議**做的是任何需要訓練、需要新模型、需要重建索引的方案（§3、§8）。理由不是它們沒用，是它們在**我們量到的病理**上不對症：我們的病不是 BM25 表達力不足，是我們自己把沒接地的字串直接餵給了一個對稀有詞極度敏感的評分函數。

---

## 7. 給 coordinator 的建議（排序）

### 建議 #1（先做）：閘門改用「商品屬性值詞彙」，而不是全文詞彙

**為什麼第一**：6 行程式碼、**0.003 ms**、用詞相同**零代價（逐查詢相同）**、把已經寫在合約裡但不會觸發的降級路徑變成會觸發。沒有任何新資源、新模型、新相依。

**文獻靠山**：Bruch, Gai & Ingber, TOIS 2023 §3 逐字說「union set 裡某一路的分數變異數為 0 時，**我們可以整個跳過融合步驟**」，並警告「變異數任意接近 0 時會對某些正規化函數造成困難」，然後明說他們不研究那個情況。我們做的就是那個他們沒做的情況，而且用的是**詞彙**訊號而不是分數訊號 —— 這同時避開了 Liang et al.（arXiv:2607.12098）警告的「路由器和排序器共用同一組分數統計量，等於繼承而非解決問題」。

**`檔案:函式`**
- `engine02/sparse.py::BM25Index.__init__` — 新增參數 `attr_tokens: set[str] | None = None`，存成 `self.attr_tokens = attr_tokens or self.vocab`（`None` 時行為與現在完全相同，向後相容）。
- `engine02/sparse.py::BM25Index.coverage` — `sum(t in self.vocab ...)` 改成 `sum(t in self.attr_tokens ...)`。
- `engine02/sparse.py::tokenize` — 丟掉長度 1 的 token（`s`／`t`），或把 `'s` 併入前一個詞。**MEAS**：`s` 是換句話說查詢裡撐過閘門的主要貢獻者之一。
- `engine02/pipeline.py::Engine02.__init__:118` — `self.bm25 = BM25Index(catalog.texts())` 改成傳入 `attr_tokens`，用 `catalog.items` 的 `category/subcategory/color/occasion/season/gender` 六欄的唯一值 tokenize 後的聯集建（5k 上是 156 個值 → 幾百個 token，建構 <1 ms）。
- `engine02/config.py::ArmConfig` — 把 `bm25_adaptive=True` 加進 `full_zclip3`（或新增 `full_zclip3_adaptive` 先當對照 arm）。

**實作草圖**
```python
# catalog.py 已有 ATTR_FIELDS = ("category","subcategory","color","season","occasion","gender")
attr_tokens = {tok for f in ATTR_FIELDS if f in items.columns
                   for v in items[f].dropna().astype(str).unique()
                   for tok in tokenize(v)}
```

**要跑的實驗**：T1，arms `{dense, hybrid_rrf, full_zclip3, full_zclip3_adaptive}` × `{lexical, paraphrase}`，KAGL 5k **和** 44k，配對置換 10,000 次。
**預期效果量（MEAS，5k）**：用詞相同 **Δ=0.000（p=1.0，逐查詢相同）**；換句話說 `full_zclip3_adaptive` **0.223 → 0.463**（＝純 dense，+0.239, p=0.0001）。
**什麼會推翻它**：(a) 用詞相同的屬性值覆蓋率在 44k 上出現 <0.5 的查詢（→ 正常查詢會被誤關 BM25）。**先跑這個檢查再跑 T1**：印出用詞相同查詢的 `attr_coverage` 分布，最小值必須遠大於 0.5（5k 上是 1.000）。(b) 用詞相同 NDCG@5 掉超過 0.01 且 p<0.05 → 閾值要調低或改用「屬性值覆蓋率 ≥ 1 個 token」而不是比例。

---

### 建議 #2（主推）：gated vocabulary grounding，接地字串只餵 BM25、另外附加給 dense

**`檔案:函式`**

1. **新檔 `engine02/grounding.py`**
   ```python
   def attr_coverage(text, attr_tokens) -> float: ...
   def ground_to_catalog(text, tax, attr_tokens, attr_syn, catalog) -> tuple[str, dict[str,str]]:
       """回傳 (接地後的 BM25 字串, {原詞: 商品庫值} 供解釋用)。
       1. tax.normalize_category(text) → node ids（跳過 collection，見下方警告）
          → tax.retrieval_terms(nid, catalog)
       2. 逐 token：本來就是屬性值 → 留；在 attr_syn 裡 → 換成商品庫值；否則 → 丟掉（絕不擴展）
       """
   ```
   ⚠️ **必須跳過 collection**：`coll.activewear` 會把 `workout` 展開成 `Leggings Sports Sandals Sports Shoes Tights`，對「拖鞋 for workout」是災難。**MEAS**：跳過 collection 與不跳過在 5k 上差異 ≤0.001，但機制上是明確的過度正規化風險，先關掉。

2. **新資源 `engine02/resources/attr_synonyms_v1.json`** — 顏色／性別／場合的同義詞 → 商品庫值。**taxonomy 已經涵蓋品類，不要重做。** 建議來源：KAGL `baseColour` 的 46 個值各配 2–4 個常見英文同義詞，`gender` 5 值，`occasion` 8 值。約 60–150 條。
   ⚠️ 我本輪用的那份表是**看過 T1 的 paraphrase 才寫的**，所以 §2.2 第 4 列的 0.556/0.578 是**樂觀的上界**。非循環的下界是 §2.2 第 2、3 列（只用既有 taxonomy：+0.141；taxonomy+SigLIP 接地：+0.270）。建表時請由 `GET /vocabulary` 的值出發、**不要看 T1 的 paraphrase 表**，並且把 T1 的 paraphrase 詞留作 held-out 檢查。

3. **`engine02/pipeline.py::Engine02.run:286-301`** — 把單一的 `text` 拆成兩個：
   ```python
   text = build_retrieval_text(req, self.catalog.name)
   bm25_text, gmap = text, {}
   if arm.ground_offvocab and attr_coverage(text, self.bm25.attr_tokens) < arm.ground_min_coverage:
       bm25_text, gmap = ground_to_catalog(text, load_taxonomy(), self.bm25.attr_tokens,
                                           ATTR_SYN, self.catalog.name)
       timings["grounded"] = 1.0
   dense_text = text if not gmap else f"{text} {bm25_text}"   # 附加，不是取代
   q = self.query_embedding(req, arm, dense_text)
   bm25_all = self.bm25.scores(bm25_text)[pool]
   ```
   **順序很重要**：接地在 `retrieval_text_normalized is False` 的路由**之前**判斷還是之後？建議是 —— `normalized=False` 時**一定接地**（明示違約），`normalized` 未給時用覆蓋率閘門判斷。接地成功後 BM25 就不必再關掉了（這正是它比純路由好的地方）。

4. **`engine02/config.py::ArmConfig`** — 新增 `ground_offvocab: bool = False`、`ground_min_coverage: float = 0.5`；新增 arm `full_zclip3_grounded = replace(ARMS["full_zclip3"], ground_offvocab=True)`。**先當對照 arm，量完再考慮改預設。**

5. **解釋（不改 schema 的做法）**：`gmap` 寫進 `constraint_report.input_warnings`，例如「本輪 `retrieval_text` 未使用商品庫詞彙，已接地：tee→Tshirts、midnight→Navy Blue；未能接地而略過：guy」。這同時是給 ENGINE 01 的除錯訊號。
   之後若要放到卡片上（「你說的『tee』對到商品庫的『Tshirts』」），才需要新欄位 `Engine02Response.query_grounding`，那是**合約變更**，要和 ENGINE 01/03 談。
   ⚠️ **可加總性不受影響**：`_terms` 的項目清單、權重、正規化全部沒動，只有 `bm25` 這一項的**輸入字串**換了。`tests/test_audit.py` 的加總不變性測試應該全部照過。

**要跑的實驗**：T1，arms `{dense, hybrid_rrf, full_zclip3, full_zclip3_grounded}` × `{lexical, paraphrase}`，5k 與 44k，配對置換 + bootstrap CI，**外加逐查詢 win/loss 次數**（Hull 1996 的方法學先例，§2.4）。
**預期效果量（MEAS，5k、Marqo、n=60）**：

| | 用詞相同 | 換句話說 |
|---|---|---|
| `full_zclip3` | 0.821 | 0.186 |
| `full_zclip3_grounded`（只餵 BM25） | 0.821（d=0.000, p=1.0） | 0.556 [0.469, 0.640]（+0.370, p=0.0001） |
| `full_zclip3_grounded` + dense 附加 | 0.821（d=0.000, p=1.0） | **0.601 [0.509, 0.688]**（+0.415, p=0.0001） |
| oracle 上界 | 0.821 | 0.735 |

**什麼會推翻它**：
- 用詞相同掉超過 0.01 且 p<0.05 → 閘門沒擋住該擋的，把 `ground_min_coverage` 調高或改成「只接地 `attr_tokens` 命中率為 0 的 token」。
- 44k 上換句話說的增益 <+0.15 → 大商品庫裡 df=1 的巧合詞變多、taxonomy 展開的值也變多，接地的雜訊比可能不同。**這是最需要複驗的一格。**
- 逐查詢 win/loss 出現「輸的查詢 > 贏的查詢」但平均是正的 → 表示少數大贏蓋掉多數小輸，要看那些輸的查詢是不是 §2.2 的接錯類型。
- 延遲：`/rank` p50 超過 15 ms → `retrieval_terms` 要 memoise（`@lru_cache` per node）。**MEAS** 目前 1.07 ms/query（筆電 CPU，只在違約時付）。

---

### 建議 #3：新增 `scripts/eval_paraphrase_attribution.py`（診斷，不是修法）

實作 §1.4 的 D1/D2/D3。**價值在簡報**：它讓「BM25 崩盤」從一個數字變成一張可以指著講的因果圖（「60 句裡有 49 句被 1 個 df=1 的詞綁架」）。
**`檔案:函式`**：新檔；需要 `Engine02.run` 把 `bm25_text`/`dense_text` 拆開（建議 #2 已經做了），或用 `engine02/ltr.py::CapturingEngine02` 的同款 subclass 手法。

---

### 建議 #4（低優先，可選）：embedding 接地當 fallback

當 `attr_synonyms_v1.json` 查不到時，用 Marqo text tower 接到最近的商品庫屬性值。**MEAS** 它自己就值 +0.270（`hybrid_rrf` 換句話說 0.191→0.462），而且**不需要人工表**。
**但**（§2.2）接錯的相似度與接對的重疊，門檻無效。所以只建議：
- **按屬性分池**（顏色只跟顏色比），用「哪個屬性的 top-1 margin 最大」決定歸屬；
- 只接地 ENGINE 01 沒填的槽位；
- 接地結果一律寫進 `input_warnings`，讓人看得到。
**`檔案:函式`**：`engine02/grounding.py::ground_by_embedding(tokens, enc, attr_values_by_field)`；屬性值 embedding 在 `Engine02.__init__` 算一次快取（156 個值，一次 batch）。每查詢多 ~5 次 token encode → GPU 上一次 batched forward，**先量再上**。

---

### 建議 #5（一行，隨手做）：`engine02/sparse.py::tokenize` 丟掉單字元 token

`guy's` → `guy` + `s`，而 `s` 在 5k 裡 df=249、idf 2.947。純粹的切詞產物拿到真分數，還撐起了閘門的覆蓋率。

### 建議 #6（防守性，不改行為）：把 Marqo 的兩個 footgun 寫進 `engine02/models.py` 的註解或測試

兩個都是**目前沒有踩到、但很容易被下一個人踩到**的（§4.1b，V）：
1. **`MarqoFashionSigLIPProcessor.__call__` 的 `padding` 預設是 `False`**，而 SigLIP 是用 `padding='max_length'`（64）訓練的。我們現在走 `open_clip` 路徑（tokenizer 已經是 `Fixed 64`）所以沒事，但 `models.py::EMBEDDERS` 只要有人把 `marqo-fashionSigLIP` 改成 `hf_siglip` backend，就會靜默地訓練／推論不一致。`_txt` 的 `hf_siglip` 分支已經寫對了（`padding="max_length", max_length=64`）—— 建議在 `EMBEDDERS` 旁邊加一行註解說明**為什麼 Marqo 必須走 open_clip**。
2. **`get_text_features(..., normalize=False)` 是 HF 路徑的預設**；我們在 `encoders.l2n` 自己做了，但值得在 `tests/` 加一條「text embedding 的 L2 norm ≈ 1」的斷言。

順帶：`tokenizer_kwargs: {"clean": "canonicalize"}` 會**刪掉標點**（`button-up` → `buttonup`），而 `sparse.py::tokenize` 會**切開**（`button` + `up`）。兩側對同一句話的切法不一致，目前沒有量過影響 —— 建議 #3 的診斷順手把兩側實際看到的字串印出來。

---

## 8. 不建議做（附 blocker）

| 不做 | Blocker |
|---|---|
| **SPLADE v3** | 權重 **CC BY-NC-SA 4.0＝非商用**（repo 既有查證，V），贊助商情境直接出局。即使換成 Apache-2.0 的 OpenSearch neural sparse：要訓練、要重建索引、要重跑所有既有數字，而且 query encoder 是延遲殺手（DistilBERT 45.3 ms vs 我們全程 12.8 ms，arXiv:2207.03834）。 |
| **uniCOIL / DeepImpact** | DeepImpact 實測 **58.64 ms/query**（同篇 BM25 13.24 ms）。SPRINT（arXiv:2307.10488）：uniCOIL、DeepImpact、TILDEv2 在 BEIR 上**沒有一個**顯著贏過 BM25。 |
| **doc2query / docTTTTTquery** | 作者自己的消融：新詞只貢獻 MRR@10 18.4→**18.8**。詞彙橋接不是它的價值所在。 |
| **Doc2Token** | 需要 1030 萬對 product–token 的 **query log**，我們沒有。而且是索引時方案，對 demo 當場打的字無幫助。 |
| **字元 n-gram／模糊比對／編輯距離** | 機制不對：處理正字法變異（typo），不是同義詞。`tee` 與 `Tshirts`、`midnight` 與 `Navy Blue` 零字元重疊。 |
| **詞幹還原／lemmatisation** | IIR §2.2.4：英文 aggregate 上幫助不大，且「幫一些查詢、同樣傷害另一些」。Hull 1996 的經典結論就是平均值會蓋掉傷害。**如果還是要做，請逐查詢報 win/loss。** |
| **Prompt ensembling** | **我們量了：換句話說 d=+0.000, p=0.954。** CLIP 的 80 模板是零樣本分類的招，不是檢索的招。 |
| **RRF → convex combination（為了修 paraphrase）** | 我們 §3.1 的既有數字方向相反：換句話說 convex 0.119 < RRF 0.191。min-max 會把那個 df=1 的 outlier 放大成 1.0。Bruch TOIS 2023 的前提（兩路都載訊號、只是尺度不同）在我們這裡不成立。 |
| **分數分布閘門（「前 k 名是不是都接近 0」）** | **我們量了：AUC 0.678，十二個候選裡倒數第三。** 換句話說的 BM25 最高分中位數 9.59，用詞相同 11.55 —— 分數一點都不低，只是分錯人。 |
| **NQC / n(σ50%) / WIG（文獻證據最好的 QPP 家族）** | **我們量了：n(σ50%) AUC 0.792、WIG 0.644、NQC AUC 0.001＝完全反向。** NQC 的分母（top-1000 平均分）在崩盤查詢上趨近 0，比值會爆掉，照文獻方向解讀會**把崩盤的查詢判成最健康的一批**。Meng et al. SIGIR 2023 自己給的判準就是「取決於該檢索器的分數分布」，而我們的 BM25 分布極度偏斜（§3.10）。**要用的是「計數」不是「離散度」。** |
| **學習式的逐查詢權重路由（regression on α）** | Bruch TOIS 2023 的 per-query α oracle 值 +0.035～+0.093 NDCG，但 **Wu & Lin（arXiv:2608.00183）三個輕量路由器沒有一個顯著贏過固定混合**，**Genc et al.（arXiv:2606.25249）實測 −17.5%～+4.0%**。要做就做**二元 on/off**，而且訊號要來自結果集比較或詞彙，不要來自排序器自己的分數統計量（Liang et al., arXiv:2607.12098 的警告）。 |
| **把 LLM 放進檢索路徑做 query rewriting** | 12.8 ms 的 `/rank` 成績會整個作廢（§3.21）。而且那是 ENGINE 01 的職責（§4.1）。要做請做在 ENGINE 01，或做成離線的同義詞表擴充。 |
| **文字側 multi-vector（ColBERT 式）** | 破壞 `_terms` 的可加總解釋（MaxSim 拆不出逐詞貢獻）；method-inventory 已對 ColPali/ColQwen 下過「商品圖用多向量很浪費，不建議」。 |
| **查詢擴展／DBA／α-QE／diffusion** | 既有決定（§3.27）：Revisiting Oxford/Paris (CVPR 2018) 明寫對「只有少數正解」的查詢會變差，我們每句查詢 ~1 個正解。本輪沒有找到任何理由改變這個判斷。 |
| **把 `bm25_min_coverage` 從 0.5 往上調（不改統計量）** | **治標且會誤傷**：現行統計量的 AUC 是 0.975，但用詞相同那群的值全部是 1.000、換句話說是 0.667 —— 要把閾值調到 >0.667 才有效，那等於要求查詢的每一個 token 都在全文詞彙裡，真實查詢（含品牌、修飾詞）會大量誤觸。改統計量（建議 #1）比改閾值乾淨。 |

---

## 9. 本輪量測的可重現資訊

- **環境**：`E:\mchackathon2026\.venv\Scripts\python.exe`，torch 2.14+cpu、open_clip 3.3.0，**本機 CPU，未使用 nycu server**。
- **資料**：`data/catalog/kagl`（5,000 件），image embedding 直接用既有快取 `data/catalog/kagl/index/img_marqo-fashionSigLIP.npy`（**唯讀，沒有覆寫任何快取**）。
- **查詢**：`engine02.eval.tasks.make_queries(items, n=60, seed=0)`，與 §3.1 同一組；`Query.text(paraphrase)` 未改。
- **基線複現**：`mode=off` 逐格重現 §3.1 —— BM25 0.758/0.034、dense 0.614/0.463、hybrid_rrf 0.830/0.191、full_adaptive_bm25 0.840/0.175。`full_zclip3` 我量到 0.821/0.186（§3.10 用 100 句查詢報 0.819/0.197；題目給的 0.736/0.111 應該是另一個商品庫，**請 coordinator 確認那一欄的出處**）。
- **統計**：`engine02.eval.metrics.paired_permutation_test`（10,000 次）與 `bootstrap_ci`，全部在 query 層級配對。
- **腳本**：本輪的實驗腳本寫在 session scratchpad（`…/scratchpad/{exp,decomp,gates,gmap,qpp,prompt_ens,dense_ground,combo}.py`），**沒有寫進 repo**，因為本檔的硬規則是只新增一個檔。建議 #2/#3 落地時，把 `combo.py`（gated grounding 端到端）與 `decomp.py`（2×2 歸因）整理成 `scripts/eval_paraphrase_attribution.py`。需要的話我可以把每一支腳本的完整內容貼出來。
- **文獻檢索的限制**：三個子代理開工時 WebSearch 配額已滿（200/200），全部改走 arXiv API / Crossref / OpenAlex / Unpaywall / 定點 WebFetch。**付費牆擋掉的原始數字**（Shtok TOIS 2012 的 NQC、Cronen-Townsend SIGIR 2002 的 Clarity、Zhou & Croft SIGIR 2007 的 WIG、Zhao ECIR 2008 的 SCQ、Hull 1996、Harman 1991、Hasibi ICTIR 2015/2016/ECIR 2017、Amati ECIR 2004、TaoBao CIKM 2022）一律標 NOT REACHED，本檔**沒有**引用任何一個我們沒讀到的數字。所有工程部落格（Amazon「Advancing search using synonyms」、eBay query rewriting 系列、Etsy Code as Craft）都 403 或找不到 —— **不要在簡報上引用它們。**
- **本輪修正掉的一個錯誤前提**：Weaviate 把 `relativeScoreFusion` 設為預設，官方理由是「保留更多原始搜尋資訊」＋內部 benchmark recall 約 +6%，**不是**「對 outlier 更穩健」。那個說法查不到來源，標為 UNCONFIRMED。
- **未觸及**：nycu server、44k 商品庫、合併商品庫、任何既有檔案。
