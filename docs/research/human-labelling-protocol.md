# 人工標註回合設計：把 ENGINE 02 的「模型對模型」換成有人類標準答案的評估

> **這份文件解決的問題**：`docs/engine02-design.md` §3.3b／§3.3c 的每一個 AUROC，標準答案都來自 **LLM 標註員**（`data/labels/labels_part_a.csv`／`_b.csv`，420 筆）。§3.3b 自己已經寫明「**不是人工標註**」。所以目前為止，「設計要素分數真的在量那個要素」這句話，量的是一個模型和另一個模型有多像。
>
> **這份文件的範圍**：只設計一個**兩小時內、2–3 個組員做得完**的人工標註回合，並附一份可直接貼進群組的說明書（`docs/research/human-labelling-instructions.md`）。不改任何既有檔案，不動 lab server，不跑 GPU。
>
> **既有 vs 待寫**（照 `docs/engine02-design.md` 的慣例先講清楚）：
> - **既有、可直接用**：`scripts/eval_human_agreement.py`（抽樣＋人類 vs LLM 的 Cohen's κ＋雙邊 na 率＋同一批 item 在人類／LLM 兩套標準答案下的 AUROC）、`data/labels/human_tasks.csv`（已抽好的 140 題）、`data/labels/visual_label_tasks.csv`（420 題母池）、`data/catalog/kagl/vlm_attributes_Qwen3-VL-8B-Instruct.parquet`（Qwen3-VL-8B 的 c(i,d)）。
> - **這份文件建議新寫**：富集抽樣的抽題程式（§1.4 有可直接貼的 code block）、Krippendorff α／多數決／IPW-AUROC 的計分函式（§3.5）、第二標註員的跑分腳本（§6.3）。本文件**只提供內容**，沒有代為新增檔案。
> - **驗證標記**：`[V]` = 本庫內可核對或原文可查；`[U]` = 未在本輪驗證。

---

## 0. 一頁結論

| 問題 | 答案 |
| --- | --- |
| 140 題對嗎？ | **不對，形狀先錯、大小再錯**。20 題 × 7 要素，其中 2 個要素在 420 筆 LLM 標註裡是 **0 正例**（κ、AUROC 都無定義），另 2 個要素兩個評分器都已經 ≥0.90（資訊量低）。真正想問的 3 個要素，每個的有效 n 是 20 不是 140，而且正例期望值只有 2–3 個。 |
| 那要幾題？ | **每人 330 題**：亮面材質 80、寬鬆版型 80、挺版領子 80、明顯 logo 30（錨點）、強烈圖案 30（錨點）、肩線挺 30（**只問適用性**）。三個人**標同一份 330 題**。 |
| 為什麼是 80？ | 盛行率富集到約 1:1 後，n=80 在 κ=0.6 時 95% CI 是 **±0.175**，且有 >80% 檢力在真實 κ=0.7 時拒絕 H₀:κ≤0.4（Fleiss–Cohen–Everitt 變異數；Sim & Wright 2005；Bujang & Baharum 2017）。AUROC 在 40/40、A=0.90 時 95% CI 是 **±0.071**——這是 §3.3 的 AUROC 第一次有窄到能講話的區間。 |
| 砍掉哪些要素？ | **柔軟針織完全不標**（KAGL 幾乎沒有針織衫，0 正例，要標得先從 `kagl_polyvore` 重抽池）；**肩線挺只標適用性、不標 1/0**（0 正例，但 §3.13 量到 VLM 對肩線回答「不適用」46%，適用性遮罩是已出貨功能，值得驗）。 |
| 幾個標註員、怎麼合併？ | **3 人全標同一批、事後不開會裁決**。主要統計量 **Krippendorff's α（名目尺度、3 類含 na、bootstrap CI）**；次要報**兩兩 Cohen's κ（只用雙方都給 1/0 的）**以便和 §3.3b 對照；低盛行率要素另報 **PABAK 與 Gwet's AC₁**（κ 的盛行率悖論）。標準答案＝3 人多數決；三人三答＝「爭議」，不進 AUROC，但**爭議率本身是要報的結果**。 |
| 今天就能跑、不用人的第二個檢查？ | 兩層：**6-A（零成本）** 把已算好的 Qwen3-VL-8B c(i,d) 轉成硬標籤，和 420 筆 LLM 標籤算 α／κ——這是把 §3.3c 的 AUROC 換個角度讀，**不是**第二個標準答案（Qwen 正是被評的評分器，會循環）。**6-B（約 US$0.2–0.5 或 CPU 背景跑）** 找一個**不同家族、不同預訓練語料**的 VLM 重標同一批 420 件，只給圖不給標題，報 α／κ／na-κ／反轉率／要素排名的 Spearman。它能**界定任務本身的標籤雜訊下界**，**不能**偵測共同盲點。 |

---

## 頂層決策表：要素 → 值不值得人工標 → 理由 → 建議樣本數

盛行率欄位是 `labels_part_a.csv` ＋ `_b.csv` 實際數出來的（每要素 60 筆）。

| 要素 | LLM 標註盛行率（正/負/na） | 值不值得人工標 | 理由（引用） | 建議樣本數（每位標註員） |
| --- | --- | --- | --- | --- |
| **亮面材質** `glossy_fabric` | 9 / 51 / 0 | **最值得（第一優先）** | §3.3c 裡 VLM 勝過 CLIP 最大的一格（0.90 vs 0.71），`full_concept_hybrid` 的路由決策就靠這一格；但兩邊的標準答案都是 LLM 標的，§3.3c 自己寫「**對 VLM 可能偏寬**」。T16（§3.24）量到材質光澤 \|Δz\|=0.496，是同一件衣服換拍法第二不穩的要素。文獻上材質是公認最難：MODA crop track material 0.41、Fashion Florence material 63.0%（`engine02-method-inventory.md` §1.3）[V]；caller 引 iFashion-Attribute material 52.2% [U，本輪 WebSearch 配額已耗盡，未能核對]。 | **80**（富集到約 40 正 / 40 負） |
| **寬鬆版型** `relaxed_fit` | 7 / 47 / 6 | **最值得（第一優先）** | §3.3c 裡**唯一** CLIP（0.86）贏過 VLM（0.77）的一格，也是 CI 最寬的一格（0.71–0.98，只有 7 個正例）。一個結論如果只靠 7 個正例、而且和其他 4 格方向相反，它需要人類來裁。T16 量到版型 \|Δz\|=0.585，是**最不穩**的要素。§3.13 量到 VLM 對版型回答不適用 26%。 | **80**（富集到約 40 / 40） |
| **挺版領子** `crisp_collar` | 27 / 33 / 0 | **值得（兼作校準組）** | 盛行率最接近 1:1 → 同樣人力買到最窄的 κ 信賴區間（見 §1.2）。同時它是一個有趣的矛盾：T16 說領型 \|Δz\|=0.493（第三不穩），但兩個評分器都 ≥0.97——「換一張照片會翻」和「在這批照片上很好測」可以同時成立，正好用人來拆開。它也是**幾何屬性 vs 抽象屬性**對照的那一端（caller 引 iFashion-Attribute neckline 66.0% vs material 52.2% / style 28.8% [U]；庫內可核對的同向證據是 GPT-4o-mini 的 neckline 只有 15.07%，`engine02-method-inventory.md` §1.3 [V]）。 | **80** |
| **明顯 logo** `visible_logo` | 17 / 43 / 0 | **少量（錨點）** | 兩個評分器都 ≥0.96，T16 不穩前三名沒有它 → 對模型比較的資訊量低。但它是**流程對照組**：logo 是「看得見就是有」的二元事實，如果三個人在這裡的 α 都 <0.8，那問題出在標註流程（說明書、疲勞、介面），不是模型。先驗證工具再相信結果。 | **30** |
| **強烈圖案** `bold_pattern` | 20 / 40 / 0 | **少量（錨點）** | 同上（CLIP 0.90 / VLM 0.94，盛行率 20/40 已算健康）。第二個錨點，用來確認第一個錨點不是僥倖。 | **30** |
| **肩線挺** `structured_shoulders` | **0 / 56 / 4** | **只標「適用 / 不適用」，不標 1/0** | 60 筆 LLM 標註 **0 正例** → Cohen's κ 和 AUROC 在數學上都無定義（`eval_human_agreement.py` 的 `cohens_kappa` 正確地回傳 nan 而不是 0）。§3.3b 已經寫明「KAGL 幾乎沒有西裝外套」。但 §3.13 量到 VLM 對肩線回答「不適用」**46%**，並據此出貨了適用性遮罩——**這個 46% 從來沒有人類對照**。標「適用性」是二元的、快的，而且驗的是已出貨的功能。 | **30**（只問適用性） |
| **柔軟針織** `soft_knit` | **0 / 60 / 0** | **本輪不標** | 60 筆 0 正例，且 §3.3b 已指出原因是 KAGL 沒有針織衫。在這個池子上標 30 題只會得到 30 個 0 和一個 nan。**先決條件**：要標就得先從 `kagl_polyvore`（已在 nycu 併好）重抽母池，那是另一回合的事。 | **0**（本輪） |
| 其餘 8 個要素（深色調、鮮豔色彩、極簡設計、合身剪裁、正式感、休閒感、霧面材質……） | 不在 `visual_label_tasks.csv` 母池內 | **不標** | 深色／鮮豔／正式／休閒這 4 個在 §3.3 T3 已經有**不靠 CLIP 的資料集屬性**當標準答案（AUROC 0.848–0.981），人工標註在這裡買不到新資訊。霧面／合身／極簡是亮面／寬鬆／強烈圖案的反義極，同一題問兩次。 | **0** |

**合計：每位標註員 330 題。**

---

## 1. 140 題是對的大小嗎？——完整的樣本數計算

### 1.1 先說結論：形狀錯得比大小嚴重

`data/labels/human_tasks.csv` 是 `eval_human_agreement.py sample --n 140` 抽出來的，做法是**依要素平均分層**（`per = n // n_elements`），7 個要素各 20 題。這個抽法對「每個要素都要有人類覆蓋」是對的，對「要能算出有用的數字」是錯的，理由有三：

1. **兩個要素的期望正例是 0。** 肩線挺、柔軟針織在 420 筆 LLM 標註裡各是 0 正例。抽 20 題進去，得到 20 個 0 和一個 nan。這不是估不準，是無定義。（`eval_human_agreement.py` 的註解已經預先處理了這件事：`a constant rater makes kappa undefined, not zero`。）
2. **兩個要素已經沒有爭議。** logo（0.91→0.96 / VLM 0.98）和強烈圖案（0.85→0.90 / VLM 0.94）在兩個評分器上都很高、盛行率也健康。花 40 題確認「本來就準的東西很準」，買到的是信心不是資訊。
3. **真正該問的 3 個要素，每個只有 20 題，而且天生稀疏。** 以 LLM 標註的盛行率外推，20 題裡的期望正例是：亮面材質 **3.0**、寬鬆版型 **2.3**、挺版領子 9.0。

所以「140 題」聽起來是一個像樣的預算，實際上分給關鍵問題的是 20 題、其中 2–3 個正例。

### 1.2 κ 的樣本數：假設與計算

**方法**：兩位評分者、二元標籤、邊際相等為 π（正例盛行率），真實一致度 κ。聯合機率為
`p₁₁ = π² + κπ(1−π)`，`p₀₀ = (1−π)² + κπ(1−π)`，`p₁₀ = p₀₁ = (1−κ)π(1−π)`。
以 **Fleiss, Cohen & Everitt (1969)** 的大樣本變異數求 `SE(κ)`，再解出 (a) 給定 95% CI 半寬所需的 n、(b) 給定對立假設所需的檢力 n。這正是 **Sim & Wright (2005)** 建議的兩種樣本數依據（信賴區間寬度 vs 假設檢定檢力），也是 **Bujang & Baharum (2017)** 表格的產生方式。

**假設（必須寫進報告）**：
- 評分者數 = 2（兩兩配對；3 人時見 §3.3）
- 類別 = 二元（1/0），na 另計
- 期望 κ = 0.6（「中等偏上」；文獻上影像屬性標註的典型值 [U]）
- 盛行率 π = 抽樣後的實際盛行率（見富集設計 §1.4）
- α = 0.05；檢力 = 0.80（單尾，方向已知：我們預期 κ>0）

**(a) 達到指定 95% CI 半寬所需的 n**

| π | κ | 半寬 ±0.10 | ±0.15 | ±0.20 | ±0.25 |
| --- | --- | --- | --- | --- | --- |
| 0.50 | 0.40 | 323 | 144 | 81 | 52 |
| 0.50 | 0.60 | 246 | 110 | **62** | 40 |
| 0.50 | 0.80 | 139 | 62 | 35 | 23 |
| 0.30 | 0.60 | 296 | 132 | 74 | 48 |
| 0.20 | 0.60 | 392 | 174 | 98 | 63 |
| **0.10** | 0.60 | **705** | 314 | 177 | 113 |

**(b) 80% 檢力、單尾 α=0.05 所需的 n**

| π | H₀ | H₁ | n |
| --- | --- | --- | --- |
| 0.50 | 0.00 | 0.60 | 15 |
| 0.50 | **0.40** | **0.70** | **50** |
| 0.50 | 0.40 | 0.80 | 26 |
| 0.50 | 0.60 | 0.80 | 83 |
| 0.30 | 0.40 | 0.70 | 59 |
| 0.10 | 0.40 | 0.70 | 134 |
| 0.10 | 0.60 | 0.80 | 239 |

**(c) 我們負擔得起的 n，實際買到多寬的區間**

| 設定 | n=20 | n=40 | n=60 | **n=80** | n=100 |
| --- | --- | --- | --- | --- | --- |
| π=0.50, κ=0.60 | ±0.351 | ±0.248 | ±0.202 | **±0.175** | ±0.157 |
| π=0.30, κ=0.60 | ±0.384 | ±0.272 | ±0.222 | ±0.192 | ±0.172 |
| **π=0.15, κ=0.60**（= 現在的亮面材質） | **±0.497** | ±0.351 | ±0.287 | ±0.248 | ±0.222 |

**讀法**：現行設計（亮面材質 n=20、π≈0.15）的 95% CI 半寬是 **±0.497**——區間涵蓋 [0.10, 1.00]，無法區分「很差」和「幾乎完美」。這不是「估計比較粗」，是這個測量在該設定下**沒有鑑別力**。

### 1.3 不要報 Landis & Koch 的等級，要報一個事先登記的決策

Landis & Koch (1977) 的分級（0.41–0.60 中等、0.61–0.80 高度）每一帶寬 0.2。要把 κ 放進一個帶裡，半寬得 ≲0.10 → π=0.5、κ=0.6 時需要 **n≈246**。每個要素 246 題 × 5 要素 = 1230 題，兩小時做不完，也不該為了一個習慣性的形容詞去買。

**改成事先登記的二元決策**（這是這份協定的核心）：

> **決策規則（在看到資料之前定死）**：某要素的 Krippendorff α ≥ 0.40 → 該要素的人類多數決可以當標準答案，重算 §3.3 的 AUROC 並取代原數字；α < 0.40 → **不當標準答案**，該要素在報告中改寫成「在單張商品照的條件下，人類自己也無法一致定義」，並比照 §3.24 的處置在 `element_profile` 標 `reliable=false`。

n=80、π≈0.5 時，這個決策有 **>80% 檢力**在真實 κ=0.7 的情況下拒絕 H₀: κ≤0.4（表 (b)：n=50 就夠）。這是一個 n=80 撐得住的宣稱；「κ 落在 0.61–0.80 高度一致」不是。

### 1.4 AUROC 才是綁住手腳的那個限制——以及富集抽樣

人工標籤最終要餵回 `eval_human_agreement.py score --encoder ...`，去重算 §3.3 的 AUROC。AUROC 的精度由**兩類的數量**決定，不是總數。用 Hanley & McNeil (1982) 的 SE：

| n_pos / n_neg | A=0.70 | A=0.80 | **A=0.90** | A=0.95 |
| --- | --- | --- | --- | --- |
| 3 / 17（= 現行設計的亮面材質） | ±0.357 | ±0.319 | **±0.244** | ±0.178 |
| 9 / 51（= §3.3b 現在的亮面材質） | ±0.203 | ±0.181 | ±0.138 | ±0.101 |
| 7 / 47（= §3.3b 現在的寬鬆版型） | ±0.229 | ±0.205 | ±0.157 | ±0.115 |
| 20 / 20 | ±0.163 | ±0.139 | ±0.101 | ±0.071 |
| 30 / 30 | ±0.133 | ±0.113 | ±0.082 | ±0.058 |
| **40 / 40** | ±0.115 | ±0.098 | **±0.071** | ±0.050 |

（旁證：§3.3b 報的亮面材質 CI 是 0.52–0.89（半寬 0.185，9 正例、A=0.71），與本表 9/51 那列一致——說明這個解析近似和腳本裡的 bootstrap 對得上，可以拿來做規劃。）

**所以必須做盛行率富集**：自然盛行率下，亮面材質要拿到 40 個正例得標 **267 題**（40/0.15）。做不到。改成分層過抽。

**但富集會偏掉 AUROC**——而且 §3.3b 已經踩過一次這個坑（「依 Marqo 反義詞分數的高／中／低三層各抽 20 件，**對該評分方式可能稍微有利**」）。這次要做對三件事：

1. **不要只用一個評分器分層。** 用 **Marqo 反義詞＋DN** 與 **Qwen3-VL-8B** 的 c(i,d) 做 2×2 分層（各自以中位數切高／低），從四個格子各抽 25%：
   - 兩者都高 → 幾乎確定是正例（撐住正例數）
   - 兩者都低 → 幾乎確定是負例
   - **A 高 B 低 / A 低 B 高 → 兩個評分器不同意的地方**
   後兩格是整個回合資訊量最高的地方：§3.3c 的「哪個評分器該用在哪個要素」這個決策，答案就藏在那裡。這也避免了「只對其中一個評分器有利」。（分層抽樣造成的池偏差是檢索評估的老問題：Zobel 1998；Voorhees 2000。）
2. **把抽樣機率寫進題目檔。** 新增 `stratum` 與 `incl_prob` 兩欄。
3. **AUROC 報兩個數字**：(i) 富集樣本上的原始 AUROC，標明「這是富集樣本上的值，不是型錄層級的估計」；(ii) 以 `1/incl_prob` 加權的 **Horvitz–Thompson 加權 AUROC**，那才是可以和 §3.3b 的數字並排的東西。κ 同理受盛行率影響，所以除了 κ 一定要附**原始 3×3 表**，讀者才能自己重算。

**可直接貼的抽題程式**（新檔案建議命名 `data/labels/human_tasks_v2.csv`；本文件不代為建立）：

```python
# 在 repo root 執行；只讀不寫既有檔案
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(".")
SEED = 20260918

PLAN = {"glossy_fabric": 80, "relaxed_fit": 80, "crisp_collar": 80,
        "visible_logo": 30, "bold_pattern": 30}          # structured_shoulders 另抽，見下
NA_ONLY = {"structured_shoulders": 30}

tasks = pd.read_csv(ROOT/"data/labels/visual_label_tasks.csv", dtype=str)
items = pd.read_parquet(ROOT/"data/catalog/kagl/items.parquet")
pos = {str(i): p for p, i in enumerate(items["item_id"].astype(str))}

# 評分器 A：Marqo 反義詞＋DN（§3.3b 的新預設）
from engine02.kansei import KanseiTable
tab = KanseiTable.load()
A = np.load(ROOT/f"data/catalog/kagl/index/design_marqo-fashionSigLIP_{tab.version}_antonym_dn1_mask0.npy")
# 評分器 B：Qwen3-VL-8B 的 c(i,d)（§3.13／§3.17 已算好，不需要 GPU）
vdf = pd.read_parquet(ROOT/"data/catalog/kagl/vlm_attributes_Qwen3-VL-8B-Instruct.parquet").set_index("item_id")

rng = np.random.default_rng(SEED)
out = []
for el, n in {**PLAN, **NA_ONLY}.items():
    g = tasks[tasks["element"] == el].copy()
    j = tab.element_ids.index(el)
    idx = np.array([pos[i] for i in g["item_id"]])
    g["sa"] = A[idx, j]
    g["sb"] = vdf[f"c_{el}"].reindex(g["item_id"]).to_numpy(dtype=float)
    hi_a, hi_b = g["sa"] > g["sa"].median(), g["sb"] > np.nanmedian(g["sb"])
    g["stratum"] = np.where(hi_a & hi_b, "both_hi",
                     np.where(~hi_a & ~hi_b, "both_lo",
                       np.where(hi_a, "A_hi_B_lo", "A_lo_B_hi")))
    per = n // 4
    take = []
    for s, gg in g.groupby("stratum"):
        k = min(per, len(gg))
        sel = gg.sample(k, random_state=int(rng.integers(1 << 31))).copy()
        sel["incl_prob"] = k / len(gg)          # 給 Horvitz–Thompson 用
        take.append(sel)
    take = pd.concat(take)
    take["mode"] = "na_only" if el in NA_ONLY else "full"
    out.append(take)

out = pd.concat(out).sample(frac=1, random_state=SEED)   # 打散：避免同要素連續出現造成的順序效應
out = out[["task_id","element","item_id","category","image_path","stratum","incl_prob","mode"]]
out["label"] = ""; out["confidence"] = ""; out["note"] = ""   # 標註員填這三欄
out.to_csv("data/labels/human_tasks_v2.csv", index=False)
print(len(out), out["element"].value_counts().to_dict())
```

> **母池夠不夠？** `visual_label_tasks.csv` 每個要素 60 題，而我們要抽 80。**不夠**——所以抽題時要把母池擴到型錄全庫（對每個要素依 `applies_to` 過濾後重新分層），或把 80 降成 60。兩個選項的後果：80 題（需擴池）→ κ ±0.175、AUROC(40/40) ±0.071；60 題（沿用現有池）→ κ ±0.202、AUROC(30/30) ±0.082。**建議擴池到全庫**，順帶好處是新抽的 item 沒有被 LLM 標註員看過，人類標籤不會和既有標籤共用同一批圖的特殊性。若時間緊，用 60 題版本也在可接受範圍。

### 1.5 兩小時的預算怎麼算出 330

| 項目 | 時間 |
| --- | --- |
| 讀說明書 + 3 人一起做 20 題練習並當場對答案（校準） | 20 分 |
| 正式標註 330 題 @ 10 秒/題 | 55 分 |
| 中場休息（第 165 題處，防疲勞漂移） | 5 分 |
| 收檔、跑 §7 的三行指令、看數字 | 15 分 |
| 緩衝 | 25 分 |
| **合計** | **120 分** |

每題 10 秒的依據：題目是單一屬性的 3 選 1，圖已在本機、說明書就在旁邊。若實測是 15 秒/題，90 分鐘可做 360 題，仍然涵蓋 330。（群眾外包的相關性判斷文獻在 10–20 秒/判斷的量級 [U]；這裡先用 10 秒規劃，**在校準階段實測 20 題的秒數再決定要不要砍量**——這一步寫進 §7 步驟 3。）

### 1.6 如果只剩一小時，砍到哪裡、損失什麼

| 預算 | 設計 | κ 95% CI（π≈0.5, κ=0.6） | AUROC CI（A=0.90） | 失去什麼 |
| --- | --- | --- | --- | --- |
| 330 題（建議） | 3 主 + 2 錨 + 1 na 塊 | ±0.175 | ±0.071（40/40） | — |
| 180 題（1 小時） | 亮面 60 / 版型 60 / 領子 60 | ±0.202 | ±0.082（30/30） | 錨點沒了 → **無法分辨「標註員不可靠」和「這題本來就難」**；肩線適用性沒驗到 |
| 120 題 | 亮面 40 / 版型 40 / 領子 40 | ±0.248 | ±0.098（20/20） | 同上，且 κ 的區間比 Landis–Koch 整個「中等」帶（寬 0.19）還寬 |
| < 120 題 | — | > ±0.25 | > ±0.10 | **不要做**。得到的數字無法支撐 §1.3 的決策規則，只會在簡報上多一個看起來像證據的東西 |

---

## 2. 哪些要素值得花人力？

決策表在最上面，這一節補理由的交叉論證。

### 2.1 三條證據線交叉後的結論

| 證據線 | 說的是什麼 | 指向 |
| --- | --- | --- |
| **T16（§3.24）跨拍法穩定度** | 同一件衣服的平拍 vs 模特兒照，**每十個要素就有一個會講反**（9.7%）。最不穩：版型 0.585、材質光澤 0.496、領型 0.493；最穩：深色調 0.205、針織 0.234、正式／休閒 0.240 | 版型／材質／領型 = **人類最可能吵架的地方** → 值得量 |
| **§3.3c VLM vs CLIP** | VLM 在材質（0.71→0.90）、logo、領子、圖案上贏；**唯獨版型輸**（0.86 vs 0.77） | 材質、版型 = **決策懸而未決的地方** → 值得量 |
| **幾何 vs 抽象屬性的可預測性** | 幾何／部位類屬性遠比抽象材質／風格好預測。caller 引 iFashion-Attribute：sleeve 86.2% / neckline 66.0% / material 52.2% / style 28.8% [U]。庫內可核對的同向證據：MODA crop material 0.41；Fashion Florence material 63.0%；GPT-4o-mini neckline 15.07%；WACV 2026（arXiv 2601.15711）細粒度 70.8% F1 但「屬性是否適用」只有 **34.1% NA-F1** [V] | 材質＝抽象端、領子＝幾何端 → **兩端都要有樣本才能講「難度隨抽象度上升」** |

三條線的交集就是：**亮面材質（抽象、不穩、決策懸而未決）**、**寬鬆版型（最不穩、唯一反向結論）**、**挺版領子（幾何端對照、盛行率最好）**。

### 2.2 為什麼砍掉柔軟針織與肩線挺（的 1/0 部分）

不是因為它們不重要——它們是 PRD 核心要素，面試情境要推西裝外套和針織衫。是因為**在這個母池上，它們在數學上沒有可測量的東西**：

```
element                  0   1  na      (labels_part_a.csv + _b.csv，各 60 筆)
soft_knit               60   0   0      → 常數評分者，κ = nan
structured_shoulders    56   0   4      → 常數評分者，κ = nan
```

`eval_human_agreement.py` 的 `cohens_kappa()` 對這個情況回傳 nan 而不是 0，而且腳本輸出裡有一行提醒：「kappa = nan means one rater never used both classes on that element (undefined, not perfect agreement)」。這是對的行為。人工標註不會改變這件事——**問題在母池，不在標註員**。

- **柔軟針織**：`kagl_polyvore`（17,783 件，已在 nycu 併好、§3.13 已全標）裡有針織衫。要標針織，先用那個型錄重抽母池。這是下一回合。
- **肩線挺**：1/0 標不了，但**適用性可以標，而且必須標**。§3.13 說「模型也會誠實回答『不適用』：肩線 46%、領子 61%、版型 26%（多為鞋包配件），**適用性遮罩因此有實際依據**」——這句話目前的「依據」是模型自己說的。WACV 2026 那篇正好指出 NA 判斷是 VLM 最弱的一環（NA-F1 34.1%）。所以 30 題的適用性 mini-block 是這回合 CP 值最高的一小塊。

### 2.3 為什麼保留兩個「已經很準」的錨點

logo 和強烈圖案對模型比較沒有資訊量。保留它們的理由是**測量工具的效度檢查**：

> 如果三位標註員在「這件衣服上有沒有一個大 logo」上的 α < 0.8，那麼他們在「這塊布是不是亮面」上算出來的任何 α 都不可信——差的是人、說明書或疲勞，不是任務。

這是把「α 低是任務的發現」（§5.3）這個說法變得可證偽的唯一辦法。沒有錨點，低 α 永遠可以被解釋成「這題很難」，那就不是發現，是藉口。各 30 題：n=30、π≈0.3、預期 κ≈0.85 → 95% CI 約 ±0.19，足以區分「≥0.8」和「≤0.5」。

---

## 3. 幾個標註員？怎麼合併？該報哪個統計量？

### 3.1 建議：3 人全標同一批 330 題，事後不開會裁決

| 選項 | 每人題數（2 小時內） | 買到什麼 | 代價 |
| --- | --- | --- | --- |
| 2 人獨立 + 第 3 人裁決 | 330 | 一個「乾淨」的標準答案 | 裁決會議 20–40 分鐘（照 15–25% 歧異率、每題 20 秒估）；而且**裁決後的標籤不能拿來算信度**——信度必須算在裁決前的獨立標籤上 |
| **3 人全標同一批、多數決** | **330** | 同樣的題數（三人同時標，牆鐘時間不變）、可算 Fleiss κ／Krippendorff α、彙總標籤誤差更低、**不用開會** | 無法用同樣人力覆蓋更多題目 |
| 3 人分工標不同題 | 990 | 題目數 × 3 | **完全沒有信度數字**——這正是我們要修的問題。不可選 |

三人同標**不花額外牆鐘時間**（三個人平行作業），省下的是裁決會議。而且裁決會把標準答案變成一個「協商出來的產物」，破壞 α 假設的獨立性。

**彙總誤差的量化**（Spearman–Brown 預言公式，彙總的信度 `R_m = m·r / (1 + (m−1)·r)`）：

| 單人信度 r | 2 人彙總 | **3 人彙總** | 5 人彙總 |
| --- | --- | --- | --- |
| 0.40 | 0.571 | **0.667** | 0.769 |
| 0.50 | 0.667 | **0.750** | 0.833 |
| 0.60 | 0.750 | **0.818** | 0.882 |

2→3 人把彙總信度推高約 0.07–0.10；3→5 再多 0.06–0.10，但需要 5 個組員。3 人是這個團隊規模下的甜蜜點。

**多數決的誤差下降**（三人多數決 vs 單人，e = 單人錯誤率，ρ = 標註員錯誤的相關係數）：

| e | 錯誤獨立 ρ=0 | ρ=0.2 | ρ=0.4 | ρ=0.6 |
| --- | --- | --- | --- | --- |
| 0.10 | 0.028 | 0.062 | 0.081 | 0.093 |
| 0.20 | 0.104 | 0.149 | 0.175 | 0.190 |
| 0.30 | 0.216 | 0.255 | 0.278 | 0.292 |

**誠實的但書**：同一個團隊、同一份說明書、同一天標完，錯誤幾乎必然相關（ρ 大概在 0.3–0.6，[U]）。所以真實的誤差下降接近表格右側，不是左側。**不要在報告裡用 ρ=0 那一欄。**（非專家共識可逼近專家標註，是群眾外包標註的標準論證，Snow et al. 2008；但那篇的前提是標註員彼此獨立、來自不同背景，我們的三個組員不滿足這個前提。）

### 3.2 合併規則（先定死）

1. **標準答案 = 3 人多數決**（2/3 即可）。
2. **三人三答（1 / 0 / na 各一）= 「爭議」**：不進 AUROC，**但要逐要素報爭議率**。爭議率本身是結果。
3. **不做事後裁決**。若真的要裁決（例如爭議率 >15% 讓樣本數掉太多），**所有信度統計量一律報裁決前的版本**，裁決版只用來算 AUROC，並在表註寫明。

### 3.3 該報哪個統計量：α 是主、κ 是輔

**主要統計量：Krippendorff's α（名目尺度、3 類 {1, 0, na}、3 位標註員、bootstrap 95% CI）**

```
α = 1 − D_o / D_e

名目尺度（δ²(c,k) = 0 若 c=k，否則 1）下可化簡為：

           (n − 1) · Σ_{c≠k} o_ck
α = 1 − ───────────────────────────
              Σ_{c≠k} n_c · n_k

o_ck : 重合矩陣（coincidence matrix）中類別 c 與 k 的配對次數
n_c  : 類別 c 的邊際總數
n    : 可配對值的總數
```

CI 用 **bootstrap**（對 item 重抽，不是對配對重抽），照 Hayes & Krippendorff (2007) 的建議；α 的抽樣分布不對稱，解析式 SE 不可靠。

**為什麼是 α 不是 κ**（四個理由，每一個在我們的資料上都成立）：

1. **3 位標註員**。Cohen's κ 只定義在兩位之間。（Fleiss' κ 可以吃多位，但見下。）
2. **3 個類別，而 na 不是「缺值」是「答案」**。`eval_human_agreement.py` 目前算 κ 時做的是 `both = g[label_h.isin(["0","1"]) & label_llm.isin(["0","1"])]`——也就是**一方說 na、一方說 1 的情況會被直接刪掉**。那是這個任務裡最重要的一種歧異（「你看得到這件衣服的肩線嗎」），刪掉它會讓 κ 虛高。α 把它當成一次真正的不一致來算。
3. **容忍缺漏**。若有人少標幾題（會發生），α 照樣可算，不需要把那幾題整列丟掉。
4. **有原則性的 CI**。

**次要統計量（一定要一起報）**：

| 統計量 | 為什麼 |
| --- | --- |
| **兩兩 Cohen's κ（只用雙方都給 1/0 的子集）** | 和 §3.3b、和 `eval_human_agreement.py` 現有輸出、和 κ 文獻的基準（Landis & Koch 1977）可對照。κ = nan 時照腳本規則報 nan，**絕對不要當 0** |
| **Fleiss' κ（3 類、3 位、完全交叉）** | 交叉檢查；資料完整時 α 與 Fleiss κ 會很接近，差很多就是有 bug |
| **κ_na：只看「有答案 vs na」的二元 κ** | 適用性遮罩是已出貨功能（`applies_to`、§3.13 的 46%）。它的信度是獨立的問題，值得獨立的數字 |
| **PABAK 與 Gwet's AC₁**（低盛行率要素） | κ 的盛行率悖論：高一致率也可能配上很低的 κ（Feinstein & Cicchetti 1990；Byrt, Bishop & Carlin 1993）。亮面材質富集後 π≈0.5 沒問題，但肩線適用性那塊很可能是 90/10。**不附 AC₁ 就等於在報告裡說「標註員很爛」，而實際上是類別很稀有**（Gwet 2008） |
| **原始 3×3 重合表** | 任何人都能自己重算。這是對抗「我們算出來是 0.43」這種不可稽核數字的唯一辦法 |
| **每要素爭議率、每人 na 率** | 見 §3.2 |

---

## 4. 說明書

完整內容在 **`docs/research/human-labelling-instructions.md`**，可直接貼進群組。設計重點摘要於此，理由留在這裡、指令留在那邊：

- **每個要素**：一句定義 + 一個正例描述 + 一個負例描述 + 明確的 na 規則。
- **na 的三分法**（最關鍵的一段）：
  - (a) **這個品類根本沒有這個部位** → na（鞋子問領子、包包問版型）
  - (b) **有這個部位但照片看不到** → na（平拍摺起來、只有背面、特寫裁掉了）
  - (c) **看得到，但在灰色地帶、兩邊都說得通** → **不是 na**，要選 1 或 0 並把 `confidence` 填 `low`
  - 理由：na 如果吞掉所有難題，α 會虛高而樣本數會崩掉。**na 是「無法判斷」，不是「難以判斷」。**
- **兩個會毀掉這批標籤的偏誤**：
  1. **標題錨定**：題目檔只給 `image_path`，刻意不給商品標題。不准去查 `item_id`、不准開 `items.parquet`、不准猜品牌。（§3.24 的整個論證建立在「要素是從圖上讀出來的」；一旦標籤來自文字，人類標籤就和 CLIP 的文字塔共用同一個捷徑，AUROC 會假性變高。）
  2. **從品類推構造**：看到 `category=top` 就預設有領子、看到「襯衫」就預設是挺版領。每題先問自己「我在這張圖上**看見**了什麼」，不是「這類衣服**通常**是什麼」。（唯一允許用 category 的時機是判 na 的 (a) 情況。）
- **不要互相討論**，直到三個人的檔案都交出來為止（校準階段的 20 題練習除外——那 20 題**不計入**正式樣本）。
- 中場休息點寫在檔案第 165 列。

---

## 5. 標完之後，哪些話可以講、哪些不行

### 5.1 可以直接寫進報告的句子（填空版）

> 「§3.3b／§3.3c 的所有 AUROC，標準答案來自 LLM 標註員。我們另外抽了 330 題（依兩個評分器的 2×2 一致／歧異分層富集），由 3 位標註員在只看圖、看不到任何模型分數與商品標題的條件下獨立盲標。**亮面材質的三人 Krippendorff α = ___（95% CI ___–___）**；以三人多數決為標準答案，Marqo 反義詞＋DN 的 AUROC 是 ___（CI ___），Qwen3-VL-8B 是 ___（CI ___）。」

> 「§3.3c 的『VLM 在材質上勝過 CLIP』這個結論，在人類標準答案下**（成立／不成立）**。這決定 `full_concept_hybrid` 的材質路由要不要保留。」

> 「寬鬆版型是 §3.3c 裡唯一 CLIP 贏過 VLM 的一格，原本只有 7 個正例。富集到 40 個正例、換上人類標準答案後，這個反向結論**（維持／翻轉／落在 CI 內無法判定）**。」

> 「人類彼此的 α 是 ___。這個數字同時是**任何評分器在這個要素上能拿到的 AUROC 的上限來源**：在對稱標籤雜訊率 η 下，對雜訊標籤量到的 AUROC 是真實 AUROC 對 0.5 的線性收縮（收縮因子 1−2η）。所以我們量到的 ___ 對應的真實 AUROC 至少是 ___。」

| η（標籤雜訊） | 真實 A=0.80 | 0.90 | 0.95 | 1.00 |
| --- | --- | --- | --- | --- |
| 0.05 | 0.770 | 0.860 | 0.905 | 0.950 |
| 0.10 | 0.740 | 0.820 | 0.860 | 0.900 |
| 0.15 | 0.710 | 0.780 | 0.815 | 0.850 |
| 0.20 | 0.680 | 0.740 | 0.770 | 0.800 |

（形式引自 Menon et al., ICML 2015 的 AUC-under-label-noise 結果 [V-摘要／U-確切常數，用前請核對原文]。方向是確定的：**對雜訊標籤量到的 AUROC 系統性低估**，所以這個修正只會讓我們的數字變好，用它來自誇不誠實、用它來說「我們的 0.82 其實不比 0.90 差」才是它的正當用途。）

> 「適用性判斷：§3.13 報告 VLM 對肩線回答『不適用』46%，並據此出貨適用性遮罩。人類在同一批題目上的 na 率是 ___%，三人之間的 κ_na = ___。」

### 5.2 就算標完也**不能**講的話

| 不能講 | 為什麼 |
| --- | --- |
| 任何關於 44k 全庫、Polyvore 端、或補值商品的敘述 | 樣本全部來自 KAGL 的 420 題母池（或其全庫擴充），品類分布是 top 283 / shoes 64 / bottom 37 / bag 26 / outerwear 7 / dress 3。外套 7 件、洋裝 3 件 |
| 「Marqo 比 fashion-clip 好」這類 encoder 的一般性宣稱 | 單一資料集、單一抽樣設計、單一標註團隊。§3.20 的外部基準複核才是那個宣稱的依據 |
| 柔軟針織、肩線挺的任何 AUROC | 0 正例。本回合肩線只標適用性 |
| 「使用者上傳的照片也會這樣」 | T16 的域差還在：同一件衣服換拍法 9.7% 的要素會講反；買家實拍→店家照在文獻上是完全沒解決的問題（FashionNet 18.8% top-20） |
| 「人類標註是真值（ground truth）」 | 三個組員不是服裝領域專家。正確的說法是「**非專家共識標註**」（non-expert consensus）。它相對於 LLM 標註是進步，不是絕對真理。TREC 的經驗是：換一組評審，系統的**絕對分數會變**，但**系統之間的排名相當穩定**（Voorhees 2000）——我們能借的是後者 |
| 「α 高，所以模型的 AUROC 可信」 | α 高只代表標籤穩定。標籤可以穩定地錯（§6.4 的共同盲點） |

### 5.3 α 低的時候要講的話——**現在就寫好，不要等看到數字**

按 §3.24 的證據推，**寬鬆版型和亮面材質的 α 很可能落在 0.3–0.5**（T16 說這兩個是換張照片就會翻的前兩名，人類看同一張照片也只是換了誤差來源）。先把句子寫死：

> **預先承諾**：如果某個要素的三人 α < 0.40，我們會在報告與簡報上寫：
>
> 「**這不是一次失敗的實驗，這是關於這個任務的一個發現。**在只有一張商品照的條件下，三位受過同一份說明書訓練的標註員，對『這件衣服是不是寬鬆版型』無法達成一致（α = ___）。這代表這個要素在這個資料形態下**沒有一個穩定的標準答案可言**，因此：
> (a) §3.3 在該要素上的任何 AUROC 都不應被引用為模型能力的證據——包括對我們有利的那些；
> (b) 該要素在 `element_profile` 標 `reliable=false`，`/visual-search` 已經會把它列為『只當參考不要當事實』（§3.24 已實作的處置，這裡是它的第二份獨立證據）；
> (c) 這與 T16 的量測互相印證：版型的 \|Δz\| 是 15 個要素裡最大的（0.585）。兩個完全不同的方法（換拍法 vs 換標註員）指向同一個結論，比其中任何一個單獨出現更有份量。」

再加一句擋住「那乾脆不要報」的誘惑：

> 錨點要素（logo、強烈圖案）的 α 是這個說法的可證偽性來源。如果錨點 α ≥ 0.8 而版型 α < 0.4，「任務難」成立；如果錨點 α 也 < 0.8，那是我們的標註流程壞了，必須先修流程再重標，不能把它寫成發現。

---

## 6. 今天就能跑、不需要人的第二個檢查

### 6.1 兩層，不是一層

| | 做什麼 | 成本 | 回答什麼 | **不**回答什麼 |
| --- | --- | --- | --- | --- |
| **6-A** | 把已算好的 Qwen3-VL-8B c(i,d) 轉成硬標籤，和 420 筆 LLM 標籤算 α／κ | **零**（parquet 已存在，不用 GPU） | §3.3c 的 0.90 裡，有多少是「標註員和評分器意見一致」 | 不是第二個標準答案——Qwen 正是被評的評分器，會**循環** |
| **6-B** | 找一個**不同家族、不同預訓練語料**的 VLM，用完全相同的 10 題 prompt 重標同一批 420 件 | US$0.2–0.5（API）或 CPU 背景跑數小時 | 任務本身的標籤雜訊**下界**；哪些要素的人類 α 會低（可用來重排人工標註優先序） | **共同盲點**。A=B 不表示 A 對 |

### 6.2 6-A：把 §3.3c 的 AUROC 換個角度讀（先跑這個）

`data/catalog/kagl/vlm_attributes_Qwen3-VL-8B-Instruct.parquet` 裡的 `c_<element>` 已經是 `P(正選項) − P(負選項)`（`scripts/vlm_tag_attributes.py` 的 `ELEMENT_MAP`），第三個選項「not applicable」就是適用性遮罩。轉硬標籤：

```
label = 1    if c > +τ
        0    if c < −τ
        na   if |c| ≤ τ 或 P(not applicable) 最大
```

τ 用 `τ = 0`（純 argmax，最少假設）先跑一次，再用「讓 na 率等於 §3.13 報的 46%/61%/26%」校準的 τ 跑一次，兩個都報。

**為什麼這個不是浪費時間**：§3.3c 的 AUROC 只用到**排序**，κ 用的是**決策**。兩者可以嚴重不一致——一個評分器可以把正例全排在前面（AUROC 0.98）卻在絕對門檻上和標註員大量不同意。混合模式 `full_concept_hybrid` 出貨的是**決策**（哪個要素用 VLM），所以決策層的一致度是目前完全沒量過、而且該量的東西。

**這一層一定要在報告裡標註循環性**：Qwen3-VL-8B 是 §3.3c 的被評對象。6-A 的 κ 是**診斷**，不是驗證。（§3.19 已經有一次「差點寫錯的結論（循環性）」，同一個坑不踩第二次。）

### 6.3 6-B：真正的第二標註員

**第 0 步（必要，而且是一個 provenance 缺口）**：`labels_part_a.csv` / `_b.csv` **沒有記錄是哪個模型標的**——只有 `label, confidence, note` 三欄。跑 6-B 之前必須先確認並補一份 `labels_part_*.meta.json`（模型 id、日期、prompt、是否看得到標題／category）。不知道 A 是誰，就無法宣稱 B 和 A「架構不同」。

**選 B 的規則**（三條硬性約束）：
1. **不可以是 Qwen3-VL-8B**（它是被評的評分器 → 循環）。
2. **不可以和標註員 A 同家族**（否則量到的是同一家模型的兩次抽樣，不是架構差異）。
3. **本機沒有 CUDA**（已確認 `torch.cuda.is_available() == False`），而且**不准用 lab server**。所以 B 必須是 API 模型，或 CPU 跑得動的小模型。

| 情況 | 建議的 B | 依據 |
| --- | --- | --- |
| A **不是** Claude 家族 | `claude-haiku-4-5`（$1 / $5 per MTok）。420 張小圖 × 約 900 input tokens ≈ 0.38M input / 13K output ≈ **US$0.45**；走 Batches API 再打 5 折 ≈ **US$0.22**，十分鐘內跑完 | 不同家族、不同預訓練語料、視覺能力足夠、無需 GPU |
| A **是** Claude 家族 | 開源非 Qwen、CPU 跑得動：`microsoft/Phi-3.5-vision-instruct`（**MIT**，4.2B，CLIP ViT-L/14-336 視覺塔 + Phi-3.5-mini）；次選 `HuggingFaceTB/SmolVLM2-2.2B-Instruct`（**Apache-2.0**）。420 件在 CPU 上屬於背景工作，不佔 GPU、不動 lab server | 授權乾淨（照本庫慣例先看 license）、架構與預訓練語料都和 Qwen／Claude 不同 |
| 兩者都跑得起來 | **都跑**。三個標註員（A、B_api、B_local）比兩個好，而且可以算三方 α | 見 §3.1 的 Spearman–Brown |

**額外一個便宜的量**（值得單獨列）：用**同一個家族但不同 prompt 協定**的 A′ 重跑一次（單題單呼叫、只給圖、不給 category）。A vs A′ 量到的是**協定變異**，A vs B 量到的是**架構變異**。兩個分開才知道歧異該怪誰。

**跑法（必須逐字照抄，否則不可比）**：
- prompt 用 `scripts/vlm_tag_attributes.py` 的 `build_prompt()` 原文，10 題、逗號分隔、三選項、最後一個選項是 not applicable。
- **只給圖**。不給商品標題、不給 `category`、不給任何 metadata——和人類標註員拿到的資訊完全相同，三邊才可比（也是 §4 的錨定控制）。
- item 清單用 `visual_label_tasks.csv` 的 420 筆（或 §3.3c 用的 397 筆子集，兩者擇一並寫明）。
- 輸出存成 `data/labels/labels_part_b2_<model>.csv`，欄位和 `labels_part_*.csv` 相同，**另存 meta.json**（模型 id、日期、prompt hash、n_items、格式正確率）。

### 6.4 6-B 要報的統計量（逐項、可直接實作）

| # | 統計量 | 粒度 | 為什麼 |
| --- | --- | --- | --- |
| 1 | **Krippendorff's α**（3 類，A vs B） | 每要素 + 彙總 | 主要一致度；和人工回合用同一把尺，數字可以直接並排 |
| 2 | **Cohen's κ**（只用雙方都給 1/0 的） | 每要素 | 和 §3.3b、和 `eval_human_agreement.py` 對照。**κ = nan 時報 nan 不報 0** |
| 3 | **κ_na**：只看「有答案 vs na」的二元一致度 + 雙方 na 率 | 每要素 | 適用性遮罩的第一個獨立證據。和 §3.13 的 46%/61%/26% 並排 |
| 4 | **Spearman ρ** 與**正負反轉率**（兩邊的連續 c(i,d)，若 B 能輸出機率） | 每要素 | 直接和 T16 的 **9.7% 反轉率**放同一張表。若「換一個標註模型」的反轉率 ≫ 9.7%，那 §3.24 的不穩定歸因（歸給拍法）就少了一塊 |
| 5 | **同一個評分器在 A 標籤 vs B 標籤下的 AUROC** | 每要素 | 這是整個檢查的重點 |
| 6 | **要素排名的 Spearman**（A 標籤下的 AUROC 排名 vs B 標籤下的排名） | 彙總，一個數字 | **Voorhees (2000) 的論證形式**：換一組評審，絕對分數會動，但系統／要素之間的排名穩不穩，才決定結論能不能活。若排名 ρ ≥ 0.8，則「logo/領子/圖案好測、材質/版型難測」這個結論不依賴標註員是誰 |
| 7 | **三方一致率**（A、B、Qwen 硬標籤） | 每要素 | 「三方全一致」的比例是人工標註難度的**事前預測子**。今天跑，明天照這個排人工標註的優先序 |

### 6.5 6-B 界定了什麼、界定不了什麼（這一段要原樣寫進報告）

**能界定的**：
- **任務歧義造成的標籤雜訊下界**。兩個獨立系統都說 1 的地方，人類大概率也說 1；A 和 B 不一致的那些 item，就是「這張照片本身沒有答案」的候選集。這些 item 可以優先送進人工回合（資訊量最高）。
- **η 的一個估計值**，可以餵進 §5.1 的 AUROC 衰減修正。
- **人工回合的優先序與樣本配置**。若某要素連 A-B 都只有 α=0.35，人類幾乎必然更低——這是把它從人工回合砍掉、或反過來加大樣本的正當理由。

**界定不了的**（三個，都要明講）：
1. **共同盲點。** A 和 B 都在網路商品圖＋alt-text 上訓練，都繼承同一套商品攝影與文案慣例。兩個模型同時把一張平拍襯衫的版型讀成 slim（因為平拍的衣服看起來就是平的），**不會在 A-B 一致率上留下任何痕跡**。T16 已經量到這類系統性偏差確實存在（同一件衣服換拍法 9.7% 的要素會講反），而這個偏差對 A 和 B 是**同向**的。
2. **所以 A-B 的 α 是人類 α 的樂觀上界，不是估計值。** 一致不等於正確。
3. **它不能取代人工回合。** 它能做的是讓人工回合花在對的地方、並在人工回合之前就知道該預期什麼。§3.3b 說的問題（「標準答案來自 LLM」）在 6-B 之後依然成立——只是從「一個 LLM」變成「兩個 LLM」。

---

## 7. 給 coordinator 的建議

### 7.1 協定（編號步驟）

1. **（今天，5 分鐘，零成本）補 provenance。** 確認 `labels_part_a.csv` / `_b.csv` 是哪個模型、哪天、用什麼 prompt 標的，寫成 `data/labels/labels_part_ab.meta.json`。沒有這一步，§6 的「不同架構」無法宣稱，§3.3b 的「LLM 標註員」也無法被別人複核。
2. **（今天，10 分鐘，零 GPU）跑 6-A。** 把 `vlm_attributes_Qwen3-VL-8B-Instruct.parquet` 轉硬標籤，對 420 筆算 α／κ／κ_na／三方一致率。輸出逐要素的「三方全一致率」。**這張表決定步驟 4 的樣本配置**。
3. **（今天，10 分鐘 + 背景）啟動 6-B。** 依 §6.3 的規則選 B（不可 Qwen、不可與 A 同家族、不可用 lab server）。API 路線十分鐘出結果；CPU 路線丟到背景跑。
4. **（人工回合前）抽題。** 用 §1.4 的 code block 產 `data/labels/human_tasks_v2.csv`：330 題，5 要素標 1/0/na + 肩線只標適用性，依兩個評分器的 2×2 分層富集，記 `stratum` 與 `incl_prob`，全檔打散。母池擴到型錄全庫（每要素 60 題的現有池不夠抽 80）；若不擴池，改成每要素 60 題（κ ±0.202，仍可用）。
5. **（人工回合，20 分鐘）校準。** 三人一起做**同樣的 20 題**，當場對答案、把歧異寫進說明書的備註欄。**這 20 題不計入正式樣本。** 同時實測秒數：若 >15 秒/題，把 330 砍成 240（亮面 60 / 版型 60 / 領子 60 / logo 30 / 圖案 30），不要砍時間。
6. **（人工回合，60 分鐘）三人獨立標同一份 330 題。** 各自存 `data/labels/human_labels_<name>.csv`。**交檔前不討論。** 第 165 題處休息 5 分鐘。
7. **（15 分鐘）計分。** 見 §7.2 的指令。
8. **（不做）事後裁決會議。** 三人三答的題目記為「爭議」，逐要素報爭議率。

### 7.2 指令

```bash
# --- 步驟 2：6-A，零 GPU，只讀已存在的 parquet ---
# （需新寫一小段；輸入是 data/catalog/kagl/vlm_attributes_Qwen3-VL-8B-Instruct.parquet
#   與 data/labels/labels_part_*.csv，輸出 reports/ablation/annotator_vs_scorer.csv）

# --- 步驟 4：抽題（§1.4 的 code block）---
python - <<'PY'
# 貼 §1.4 的程式
PY

# --- 步驟 7a：每位標註員 vs 既有 LLM 標註員（既有腳本，可直接跑）---
for who in alice bob carol; do
  python scripts/eval_human_agreement.py score \
    --human data/labels/human_labels_$who.csv \
    --encoder marqo-fashionSigLIP
done
# 這會給：逐要素 Cohen's κ（人類 vs LLM）、雙邊 na 率、
#         同一批 item 在人類 / LLM 兩套標準答案下的 AUROC 並排

# --- 步驟 7b：三人之間的 α / 多數決 / IPW-AUROC（需新寫）---
# 建議加在 scripts/eval_human_agreement.py 裡當第三個 subcommand `consensus`，
# 沿用該檔既有的 auroc() 與 cohens_kappa()（含 nan 規則），新增：
#   krippendorff_alpha(units: dict[item -> list[label]], categories=("1","0","na")) -> float
#   bootstrap_ci(fn, units, B=2000)   # 對 item 重抽，不是對配對重抽
#   majority(labels) -> "1" | "0" | "na" | "contested"
#   auroc_ipw(scores, y, w=1/incl_prob)
# 輸出一張表：element, n, alpha, alpha_ci, mean_pairwise_kappa, fleiss_kappa,
#            kappa_na, pabak, gwet_ac1, contested_rate, na_rate_per_rater,
#            auroc_raw, auroc_ipw, auroc_llm_same_items
```

### 7.3 拿到數字之後怎麼辦（事先登記的分支）

| 結果 | 動作 |
| --- | --- |
| **錨點（logo／圖案）α < 0.8** | **先不要看其他數字。** 標註流程壞了。找出是說明書不清楚、疲勞、還是有人誤解 na 規則，修完重標。這一條優先於下面所有分支 |
| 某要素 **α ≥ 0.6** | 人類多數決當標準答案。用 IPW-AUROC 取代 §3.3b／§3.3c 該要素的數字，並在表註寫「標準答案＝3 位非專家標註員的多數決，α=___」 |
| 某要素 **0.40 ≤ α < 0.6** | 一樣採用，但 AUROC 一律附 §5.1 的雜訊衰減修正，且明講「這個 AUROC 的天花板被標籤信度限制住」 |
| 某要素 **α < 0.40** | 執行 §5.3 的預先承諾原文。該要素**不產生新的 AUROC**，改標 `reliable=false`，並在報告裡和 T16 的 \|Δz\| 並列為互相印證的兩個獨立證據 |
| **人類 AUROC 遠低於 LLM AUROC**（同一批 item） | 這正是 `eval_human_agreement.py` 檔頭預告的情況：「LLM 標註員和評分器共用盲點，§3.3 的每一個 AUROC 都偏樂觀——**簡報上要說**」。照做 |
| 6-B 的**要素排名 Spearman ≥ 0.8** | 可以寫：「『logo／領子／圖案好測、材質／版型難測』這個結論不依賴標註員是誰」 |
| 6-B 的某要素 **α < 0.5** | 那個要素在人工回合的樣本要加倍，或直接砍掉（§6.5）。**這個決定要在人工回合開始前做完** |

### 7.4 三件不要做的事

1. **不要把 κ=nan 當成 0，也不要當成 1。** 既有腳本已經做對了（`a constant rater makes kappa undefined, not zero`），不要在新寫的計分函式裡退步。
2. **不要在富集樣本上直接報 AUROC 而不標註。** §3.3b 已經因為分層抽樣留下一條「對該評分方式可能稍微有利」的但書，這次要用 IPW 把它修掉，不要再留一條但書。
3. **不要用 Qwen3-VL-8B 當第二標註員。** 它是 §3.3c 的被評對象。§3.19 已經有過一次「差點寫錯的結論（循環性）」。

---

## 8. 參考文獻

**一致度統計**
- Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement* 20(1), 37–46. doi:10.1177/001316446002000104
- Fleiss, J.L. (1971). Measuring nominal scale agreement among many raters. *Psychological Bulletin* 76(5), 378–382. doi:10.1037/h0031619
- Fleiss, J.L., Cohen, J., & Everitt, B.S. (1969). Large sample standard errors of kappa and weighted kappa. *Psychological Bulletin* 72(5), 323–327. doi:10.1037/h0028106 —— §1.2 的變異數公式出處
- Landis, J.R., & Koch, G.G. (1977). The measurement of observer agreement for categorical data. *Biometrics* 33(1), 159–174. doi:10.2307/2529310 —— 分級表；§1.3 論證為何不用它
- Krippendorff, K. (2018). *Content Analysis: An Introduction to Its Methodology* (4th ed.), Sage. —— α 的定義與名目尺度化簡
- Hayes, A.F., & Krippendorff, K. (2007). Answering the call for a standard reliability measure for coding data. *Communication Methods and Measures* 1(1), 77–89. doi:10.1080/19312450709336664 —— α 的 bootstrap CI、為何優於 κ
- Feinstein, A.R., & Cicchetti, D.V. (1990). High agreement but low kappa: I. The problems of two paradoxes. *Journal of Clinical Epidemiology* 43(6), 543–549. doi:10.1016/0895-4356(90)90158-L —— 盛行率悖論
- Byrt, T., Bishop, J., & Carlin, J.B. (1993). Bias, prevalence and kappa. *Journal of Clinical Epidemiology* 46(5), 423–429. doi:10.1016/0895-4356(93)90018-V —— PABAK
- Gwet, K.L. (2008). Computing inter-rater reliability and its variance in the presence of high agreement. *British Journal of Mathematical and Statistical Psychology* 61(1), 29–48. doi:10.1348/000711006X126600 —— AC₁

**κ 的樣本數**
- Sim, J., & Wright, C.C. (2005). The kappa statistic in reliability studies: use, interpretation, and sample size requirements. *Physical Therapy* 85(3), 257–268. doi:10.1093/ptj/85.3.257 —— §1.2 的兩種樣本數依據（CI 寬度 vs 檢力）
- Bujang, M.A., & Baharum, N. (2017). Guidelines of the minimum sample size requirements for Kappa agreement test. *Epidemiology, Biostatistics and Public Health* 14(2), e12267. doi:10.2427/12267
- Donner, A., & Eliasziw, M. (1992). A goodness-of-fit approach to inference procedures for the kappa statistic. *Statistics in Medicine* 11(11), 1511–1519. doi:10.1002/sim.4780111109

**AUROC**
- Hanley, J.A., & McNeil, B.J. (1982). The meaning and use of the area under a ROC curve. *Radiology* 143(1), 29–36. doi:10.1148/radiology.143.1.7063747 —— §1.4 的 SE
- DeLong, E.R., DeLong, D.M., & Clarke-Pearson, D.L. (1988). Comparing the areas under two or more correlated ROC curves. *Biometrics* 44(3), 837–845. doi:10.2307/2531595 —— 比較同一批 item 上兩個評分器時用
- Menon, A.K., van Rooyen, B., Ong, C.S., & Williamson, R.C. (2015). Learning from corrupted binary labels via class-probability estimation. *ICML 2015*. —— §5.1 的 AUC-under-label-noise 收縮 [V-摘要／U-確切常數]

**標註實務、群眾外包、檢索評估**
- Voorhees, E.M. (2000). Variations in relevance judgments and the measurement of retrieval effectiveness. *Information Processing & Management* 36(5), 697–716. doi:10.1016/S0306-4573(00)00010-8 —— 換評審會改變絕對分數、但系統排名穩定；§6.4 第 6 項的論證形式
- Zobel, J. (1998). How reliable are the results of large-scale information retrieval experiments? *SIGIR '98*, 307–314. doi:10.1145/290941.291014 —— 池化／分層抽樣的偏差
- Carterette, B., & Soboroff, I. (2010). The effect of assessor errors on IR system evaluation. *SIGIR '10*, 539–546. doi:10.1145/1835449.1835540 —— 標註員錯誤如何傳遞到評估結果
- Alonso, O., & Mizzaro, S. (2012). Using crowdsourcing for TREC relevance assessment. *Information Processing & Management* 48(6), 1053–1066. doi:10.1016/j.ipm.2012.01.004
- Snow, R., O'Connor, B., Jurafsky, D., & Ng, A.Y. (2008). Cheap and fast — but is it good? Evaluating non-expert annotations for natural language tasks. *EMNLP 2008*, 254–263. —— 非專家共識可逼近專家；但前提是標註員彼此獨立（見 §3.1 的但書）
- Nowak, S., & Rüger, S. (2010). How reliable are annotations via crowdsourcing? *MIR '10*, 557–566. doi:10.1145/1743384.1743478 —— 影像標註的一致度量級

**庫內來源**
- `docs/engine02-design.md` §3.3（T3 AUROC）、§3.3b（420 件盲標）、§3.3c（VLM vs CLIP，397 件）、§3.13（適用性 46%/61%/26%）、§3.17（全量補值）、§3.19（循環性）、§3.24（T16 跨拍法穩定度）
- `docs/research/engine02-method-inventory.md` §1.3（OVAD、ARO、WACV 2026 arXiv 2601.15711 的 NA-F1 34.1%、MODA material 0.41、Fashion Florence material 63.0%、GPT-4o-mini neckline 15.07%）
- `scripts/eval_human_agreement.py`、`scripts/eval_visual_labels.py`、`scripts/vlm_tag_attributes.py`
- `data/labels/labels_part_a.csv`、`_b.csv`、`visual_label_tasks.csv`、`human_tasks.csv`
- `engine02/resources/kansei_v1_literature.json`（15 個設計要素與描述子）

**未驗證**
- iFashion-Attribute 的 top-1 準確率（sleeve 86.2% / neckline 66.0% / material 52.2% / style 28.8%）為 caller 提供，本輪 **WebSearch 配額已耗盡（200/200）**，無法核對出處。在庫內找不到這組數字。引用時請標 [U]，或改引上面「庫內來源」那組可核對的同向證據。
