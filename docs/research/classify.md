# 類別標籤雜訊稽核與缺值屬性補值（agent `classify`）

> 作者：sub-agent `classify`，2026-09-17，分支 `engine02-research`，實驗機 cfda4（V100，Qwen3-VL-8B 以 fp16 推論）。
> 程式：`engine02/attribute_fill.py`、`tests/test_attribute_fill.py`（8 項全過，HashEncoder）、`scripts/eval_classify.py`。
> 原始結果：本機 `reports/agents/classify/cfda4/`（不進 git）；cfda4 `/tmp2/mzjiang/Research_Project/agents/classify/out/`。
> **標註聲明**：本文所有「視覺標註」（Polyvore 102 件遷移樣本、T2 顯示的 115 件 Polyvore 商品、60 件類別不一致樣本的判定）都是本 agent（LLM）看拼圖後的判讀，**不是人工標註**，只能當粗略參考。

## 1. 一句話結論

- **補值方法**：顏色（色系）與性別用 **凍結 Marqo-FashionSigLIP 圖片向量上的 logistic regression**（在 KAGL 訓練），依 dev 精度門檻設定信心門檻，低於門檻不補（維持 null）。零樣本 CLIP 與 Qwen3-VL-8B 在 KAGL test 上所有屬性都顯著較差（p<0.001）。
- **場合（occasion）不要用 LR 補**：KAGL 上 LR 準確率 0.927，但遷移到 Polyvore 只有 0.74，且幾乎全部猜 Casual（macro-F1 0.47），信心分數失準。**Qwen3-VL-8B** 在 KAGL 較差（0.840）卻能遷移（Polyvore 0.894，門檻下覆蓋 62%、53/53 全對）；若要補 occasion 應用 Qwen（本次未全量執行）。
- **季節（season）從商品照片幾乎無法預測**：最佳 LR 準確率 0.66，只比「全猜多數類」的 0.48 高一些；零樣本 0.30（比多數類還差）。不建議補。
- **對 ENGINE 02 的影響**（outerwear／dress，26 個「類別＋顏色＋性別」查詢）：hard-constraint satisfaction 由 **0.29 → 0.92**（p<0.001），relaxation rate 由 0.92 → 0.04，color:drop 由 92% → 0%。Polyvore 商品在顏色／性別過濾下可觸及的比例由 0% → 顏色 84%、性別 89%。
- **類別對照表的雜訊**：KAGL 的 metadata 與 Marqo 零樣本一致率 96.3%，Polyvore 91.7%。agent 目視 60 件不一致樣本（非人工）：KAGL 30 件中 metadata 錯 5、模型錯 9、分類邊界／多件商品 16；Polyvore 30 件中 metadata 錯 11、模型錯 9、邊界 10。

## 2. 設定

### 2.1 資料與切分
- `data/catalog/kagl_full`（44,434 件；有 gender/baseColour/usage/season），`data/catalog/polyvore_big`（25,000 件；無屬性），`data/catalog/kagl_polyvore`（合併；17,783 件，其中 Polyvore 12,289 件）。
- 屬性評估範圍：KAGL 中合併型錄保留的 6 類（top/bottom/outerwear/dress/shoes/bag）。
- **group-aware 切分**：把標題去掉顏色字與性別字當成「同款群組」（例如同一款 T-shirt 的不同顏色），整組只進一個 split，避免同款不同色洩漏；依 subcategory 分層抽樣。test 2,655 件、dev 1,193 件、train 23,324 件（test/dev 每組最多 3 件，其餘 3,454 件不使用）。seed 0。
- 顏色：KAGL baseColour 對應 12 個色系（`attribute_fill.COLOR_FAMILIES`；Multi 不評）；另報 40 個出現 ≥20 次的精確顏色。
- gender5＝Men/Women/Unisex/Boys/Girls；gender2＝只看標 Men/Women 的商品；occasion＝Casual/Formal/Sports/Ethnic；season＝Summer/Fall/Winter/Spring。

### 2.2 方法
| 代號 | 方法 | 文獻 |
|---|---|---|
| `zs_marqo`／`zs_fclip` | CLIP 零樣本，prompt ensemble（每個標籤 2 個同義詞×3 個模板，帶入該商品的 coarse 類別名詞），softmax(cos·100) | Radford et al., ICML 2021 (arXiv:2103.00020) |
| `lr_marqo`／`lr_fclip` | 凍結圖片向量上的 multinomial logistic regression（sklearn lbfgs；C∈{0.3,1,3,10} 以 dev NLL 選） | 同上 linear probe |
| `qwen` | Qwen3-VL-8B-Instruct（fp16），一張圖一次回答 5 題，每題一個字母、逗號分隔；讀每個答題步驟的字母 logits 得到選項機率 | Robinson & Wingate, ICLR 2023 (arXiv:2210.12353) |

- 校準：在 dev 上做 temperature scaling（Guo et al., ICML 2017, arXiv:1706.04599），報告 raw 與校準後的 ECE（15 bins）。
- 放棄預測（abstention）：在 dev 上找「選擇性準確率 ≥ 目標」的最低信心門檻，再報告 test 上的覆蓋率與選擇性準確率（Geifman & El-Yaniv, NeurIPS 2017）。
- 統計：準確率 bootstrap 95% CI（2,000 次）；方法間以逐件對錯做配對置換檢定（10,000 次），基準為 `lr_marqo`。
- **ground truth 的限制**：KAGL metadata 本身有雜訊（見 §3，例如童裝裙標 Women），所以準確率上限不是 1。season/occasion 是商家標記，很多是「上架季」而不是可從照片看出的屬性。

## 3. 實驗 1：coarse 類別對照表與來源標籤的雜訊稽核

### 3.1 零樣本類別與 metadata 的一致率（全量）
| 型錄 | Marqo-FashionSigLIP | fashion-clip | 兩個 encoder 一致但都跟 metadata 不同 |
|---|---|---|---|
| KAGL 44,434 | **0.963** [0.961, 0.965] | 0.946 [0.944, 0.949] | 2.4% |
| Polyvore 25,000 | **0.917** [0.914, 0.921] | 0.835 [0.831, 0.840] | 4.6% |

各類一致率（Marqo）：KAGL dress 0.80、other 0.87 最低，shoes 0.999、bag 0.99 最高；Polyvore accessory 0.80、other 0.80、dress 0.82 最低。混淆矩陣：`reports/agents/classify/cfda4/audit/confusion_*.csv`。主要混淆方向：
- KAGL：other→top 266、other→accessory 184、other→bottom 126、other→outerwear 103（innerwear vest、nightwear、tracksuit 被歸 other）；top→outerwear 118（Sweatshirts 裡的拉鍊外套）；dress→other 47。
- Polyvore：other→top 253、other→accessory 211（generic「Clothing」類別直接被對照表丟進 other）；dress→top 169；accessory→other 187／→jewelry 131。

**Qwen3-VL-8B（fp16）對 60 件不一致樣本的第三方判讀**（`vlm/*.parquet`；只跑這 60 件）：
| 型錄 | agent 判定 | n | Qwen 同意 metadata | Qwen 同意 Marqo |
|---|---|---|---|---|
| KAGL | M（metadata 錯） | 5 | 0 | 4 |
|  | X（模型錯） | 9 | 5 | 2 |
|  | A（邊界） | 16 | 4 | 12 |
| Polyvore | M | 11 | 0 | 10 |
|  | X | 9 | 6 | 3 |
|  | A | 10 | 5 | 5 |

Qwen 在 16 件 metadata 錯的樣本裡**從不**站在 metadata 那邊（14 件同意 Marqo）；在 18 件模型錯的樣本裡 11 件同意 metadata。因此「Marqo 與 Qwen 一致且都不同意 metadata」（36/60 件）可當複核清單：其中模型錯的只有 5 件（14%），而全部不一致樣本中模型錯的是 18/60（30%）。

### 3.2 目視判讀 60 件不一致樣本（agent 判讀，非人工）
抽樣：Marqo 零樣本與 metadata 不一致的商品，依 metadata 類別輪流分層抽樣，KAGL、Polyvore 各 30 件；看拼圖 `audit/sheets/dis_*.jpg` 並對照 metadata 判定。
M＝metadata 錯（圖片明顯是模型說的類別或根本不是商品），X＝模型錯，A＝兩者都說得通（對照表邊界、一張圖多件商品）。

| 型錄 | metadata 錯 M | 模型錯 X | 邊界／多件 A |
|---|---|---|---|
| KAGL（n=30） | 5（17% [3%, 30%]） | 9（30% [13%, 47%]） | 16（53% [37%, 70%]） |
| Polyvore（n=30） | 11（37% [20%, 53%]） | 9（30% [13%, 47%]） | 10（33% [17%, 50%]） |

逐件判讀：`audit/disagreement_judgement_agent.csv`。重要發現：
- **KAGL metadata 真的錯**：標「Formal Shoes」「Heels」的商品圖是運動內衣（#17、#26）；標「Casual Shoes」的是洋裝（#8）；拉鍊運動外套被標 Sweatshirts→top（#9）；帶鍊條的手拿包被標 Wallets（#28）。
- **Polyvore 來源標籤雜訊更多**：「Bags」是筆電、「Pumps」是廣告橫幅／項鍊、「Sandals」是耳環、「Jewelry」是太陽眼鏡、「Pants」是襪子、「Day Dresses」是海灘拍照現場。
- **對照表本身的問題**（`scripts/prepare_catalog.py`）：Polyvore「Vests」幾乎都是背心上衣而不是外套；「Clothing」整類（286 件）被丟進 other，其實多半是正常衣物；KAGL「Sweatshirts」混有拉鍊外套；Cufflinks 在 KAGL 是 jewelry，模型常判 accessory；Wallets 與 Clutches 的界線不清。
- **模型錯的典型**：一張圖穿整套（kurta+salwar、tracksuit）時，模型判的是上衣而不是被販售的下身；手機殼、雨傘、胸針這類「other／accessory」細類。
- 推估：不一致率 × M 比例，KAGL 約 3.7%×17% ≈ **0.6%** 的商品 coarse 類別是錯的，Polyvore 約 8.3%×37% ≈ **3%**（樣本小且按類別分層，未依母體加權，只能當量級參考）。另有 KAGL 約 2%、Polyvore 約 3% 是對照表邊界問題，這部分交給 `taxonomy` agent 處理較合適。

## 4. 實驗 2：屬性補值（KAGL held-out test；ground truth＝KAGL metadata）

### 4.1 主表（test；[95% bootstrap CI]；ECE 為 dev 溫度校準後；覆蓋率／選擇性準確率用 dev 精度 0.9 門檻）
Qwen3-VL-8B（fp16，V100，0.32 秒／件，valid_rate 1.00）只跑 test＋dev（3,848 件），不跑精確顏色（選項太多）。

| 任務 | 方法 | 準確率 | macro-F1 | ECE raw → 校準 | 覆蓋率@0.9 | 選擇性準確率@0.9 | 多數類基準 |
|---|---|---|---|---|---|---|---|
| gender5 (n=2,655) | zs_marqo | 0.793 [0.779, 0.809] | 0.631 | 0.023 → 0.033 | 0.654 | 0.915 | 0.501 |
|  | zs_fclip | 0.690 [0.672, 0.708] | 0.516 | 0.093 → 0.075 | 0.303 | 0.937 | |
|  | **lr_marqo** | **0.935 [0.925, 0.944]** | **0.820** | 0.015 → 0.015 | 0.997 | 0.937 | |
|  | lr_fclip | 0.927 [0.918, 0.937]（p=0.057） | 0.799 | 0.008 → 0.008 | 1.000 | 0.927 | |
|  | qwen | 0.844 [0.830, 0.858] | 0.685 | 0.144 → 0.065 | 0.871 | 0.894 | |
| gender2 (n=2,378) | zs_marqo | 0.971 [0.964, 0.978] | 0.970 | 0.004 → 0.008 | 0.995 | 0.974 | 0.559 |
|  | **lr_marqo** | **0.981 [0.976, 0.987]** | 0.981 | 0.005 → 0.005 | 0.999 | 0.982 | |
|  | qwen | 0.961 [0.953, 0.969] | 0.961 | 0.036 → 0.010 | 1.000 | 0.961 | |
| 色系 12 類 (n=2,619) | zs_marqo | 0.765 [0.748, 0.781] | 0.700 | 0.063 → 0.014 | 0.514 | 0.920 | 0.222 |
|  | zs_fclip | 0.718 [0.701, 0.735] | 0.665 | 0.137 → 0.020 | 0.397 | 0.926 | |
|  | **lr_marqo** | **0.838 [0.823, 0.852]** | **0.786** | 0.028 → 0.021 | 0.850 | 0.900 | |
|  | lr_fclip | 0.823 [0.808, 0.838]（p=0.008） | 0.771 | 0.024 → 0.031 | 0.862 | 0.877 | |
|  | qwen | 0.739 [0.722, 0.756] | 0.664 | 0.234 → 0.049 | 0.569 | 0.911 | |
| 精確顏色 40 類 (n=2,611) | zs_marqo | 0.560 [0.542, 0.578] | 0.393 | 0.102 → 0.030 | 0.024 | 0.937 | 0.223 |
|  | **lr_marqo** | **0.769 [0.753, 0.785]** | 0.450 | 0.022 → 0.030 | 0.703 | 0.889 | |
| occasion (n=2,635) | zs_marqo | 0.644 [0.625, 0.662] | 0.605 | 0.135 → 0.070 | 0.066 | 0.919 | 0.748 |
|  | zs_fclip | 0.524 [0.504, 0.545] | 0.496 | 0.272 → 0.044 | 0.050 | 0.932 | |
|  | **lr_marqo** | **0.927 [0.917, 0.937]** | **0.880** | 0.008 → 0.014 | 0.999 | 0.927 | |
|  | qwen | 0.840 [0.826, 0.854] | 0.703 | 0.154 → 0.048 | 0.812 | 0.900 | |
| season (n=2,652) | zs_marqo | 0.303 [0.286, 0.321] | 0.202 | 0.260 → 0.009 | 0 | — | **0.484** |
|  | zs_fclip | 0.299 [0.281, 0.317] | 0.200 | 0.398 → 0.042 | 0 | — | |
|  | **lr_marqo** | 0.659 [0.641, 0.678] | 0.509 | 0.023 → 0.023 | 0.125 | 0.873 | |
|  | lr_fclip | 0.666 [0.647, 0.685]（p=0.44） | 0.515 | 0.030 → 0.026 | 0.174 | 0.850 | |
|  | qwen | 0.490 [0.472, 0.509] | 0.193 | 0.496 → 0.056 | 0 | — | |

- 配對置換檢定（相對 `lr_marqo`）：所有零樣本方法與 Qwen 在所有任務都顯著較差（p≤0.0003；Qwen 差 −2.0 到 −16.9 個百分點）；`lr_fclip` 在 gender2（p=0.03）、色系（p=0.008）、occasion（p=0.004）顯著稍差，gender5（p=0.06）、season（p=0.44）、精確顏色（p=0.14）無顯著差異。檔案：`attr_metrics.csv`、`attr_paired_tests.csv`、`attr_risk_coverage.csv`。
- 零樣本 ECE raw 很大（CLIP 的 logit scale 不是機率），但一個溫度參數就能校準到 ≤0.07；然而校準後它的信心分數很難把對錯分開（occasion 在精度 0.9 門檻下只剩 5–7% 覆蓋率）。
- **季節**：零樣本比全猜 Summer 還差；LR 的 0.66 有一部分可能來自學到「品類／材質→上架季」的相關性，而不是真正可見的季節特徵。精度 0.9 只能覆蓋 12–17%。**結論：季節不應從商品照片補值。**
- **occasion 在 KAGL 上看起來很好（0.93），但 KAGL 的 occasion 高度跟 subcategory 綁在一起**（Kurtas→Ethnic、Sports Shoes→Sports），LR 很可能學的是品類而不是風格；§5 的 Polyvore 遷移結果證實它不遷移。

## 5. 遷移到 Polyvore 圖片（agent 視覺標註 102 件；每類 17 件）

標註檔：`reports/agents/classify/transfer/polyvore_labels_agent.csv`（`?`＝看不出來，不評）。**這些標籤是本 agent 看圖判讀的，不是人工，也不是 Polyvore 原始資料。** 標註時看過其中 4 件的標題，其餘只看圖。

| 任務 | 方法 | n | 準確率 [95% CI] | macro-F1 | ECE | 覆蓋率 / 選擇性準確率（KAGL dev 門檻@0.9） |
|---|---|---|---|---|---|---|
| gender2 | zs_marqo | 93 | 1.000 [1.00, 1.00] | 1.000 | 0.053 | 1.00 / 1.00 |
|  | lr_marqo | 93 | 0.957 [0.91, 0.99] | 0.739 | 0.075 | 0.99 / 0.97 |
|  | qwen | 93 | 0.989 [0.97, 1.00] | 0.897 | 0.028 | 1.00 / 0.99 |
| 色系 | zs_marqo | 85 | 0.906 [0.85, 0.97] | 0.873 | 0.114 | 0.60 / 1.00 |
|  | **lr_marqo** | 85 | **0.918 [0.86, 0.97]** | 0.864 | 0.095 | **0.82 / 0.99** |
|  | lr_fclip | 85 | 0.929 [0.87, 0.98] | 0.852 | 0.089 | 0.88 / 0.97 |
|  | qwen | 85 | 0.871 [0.80, 0.94] | 0.862 | 0.139 | 0.69 / 0.98 |
| occasion | zs_marqo | 85 | 0.765 [0.68, 0.85] | **0.780** | 0.178 | 0 / — |
|  | lr_marqo | 85 | 0.741 [0.65, 0.84] | 0.466 | 0.195 | 1.00 / **0.74** |
|  | **qwen** | 85 | **0.894 [0.82, 0.95]** | **0.885** | 0.130 | **0.62 / 1.00** |

- **Qwen 的 occasion 可遷移、LR 不行**：Qwen 在 KAGL 上 occasion 只有 0.840（比 LR 差 8.7 個百分點，p<0.001），但換到 Polyvore 是 0.894、macro-F1 0.885；用 KAGL dev 門檻（T=6.67，conf ≥ 0.864）覆蓋 62%，那 53 件全對。這與「LR 在 KAGL 學到品類捷徑」的解讀一致。n=85，CI [0.82, 0.95]，仍需更多標註確認。

- **gender2 的遷移結果沒有鑑別力**：102 件裡 91 件是女裝（Polyvore 是女性時尚網站），Men 只有 2 件、Unisex 4 件、看不出來 5 件；gender2 全猜 Women 就有 0.978，所以 zs_marqo 的 1.000 與 lr_marqo 的 0.957 都不代表真的會分男女。實際補值時用的 gender5→{Men, Women, Unisex}，Unisex 的判斷在 KAGL 上本來就弱（gender5 macro-F1 0.82）。
- **色系可遷移**：LR 在 KAGL 門檻下覆蓋 82%、選擇性準確率 0.99（n=70 左右，CI 寬）。
- **occasion 不遷移**：LR 在 KAGL 門檻下覆蓋 100%、準確率只有 0.74，macro-F1 0.47（幾乎全猜 Casual；agent 標註中 23/85＝27% 是 Formal）。LR 在 KAGL 上的高信心是品類捷徑造成的，換到 Polyvore 就失準。零樣本 macro-F1 較高（0.78），但信心分數在 KAGL 門檻下覆蓋 0%。

## 6. 實驗 3：對 ENGINE 02 硬條件的影響

### 6.1 補值（寫入型錄的**副本** `/tmp2/.../agents/classify/catalog_kagl_polyvore_filled/`）
| 屬性 | 方法 | 溫度 T | 信心門檻（dev 目標精度） | Polyvore 補上比例（全部／outerwear／dress） |
|---|---|---|---|---|
| color（寫入色系代表色，如 `Blue`；另加 `color_family` 欄） | lr_marqo | 0.86 | 0.641（0.90） | 83.6% / 82.8% / 79.2% |
| gender（Men/Women/Unisex） | lr_marqo（gender5 機率縮到 3 類） | 1.00 | 0.653（0.95） | 89.3% / 87.4% / 91.6% |
| occasion、season | 不補 | — | — | 0% |

補值前 Polyvore 在 color/gender/occasion/season 的非 null 比例都是 0%。

### 6.2 T2 式查詢（outerwear＋dress；Marqo-FashionSigLIP；arm `full`；top-5）
- 查詢：outerwear×{Men, Women}×8 色系、dress×Women×10 色系，共 26 個；硬條件＝category＋color＋gender；兩組都用 `provenance_filter("family")`（顏色以色系比對），差別只有型錄是否補值。
- 滿足度的 ground truth：KAGL 商品用 metadata；Polyvore 商品用**本 agent 對畫面中 115 件的視覺標註**（`t2/shown_polyvore_labels_agent.csv`；顏色看不出來的 2 件算不滿足）。

| arm | 滿足度（逐查詢平均）[95% CI] | 顏色滿足度 | relaxation rate | color:drop 比例 | 過濾後候選數（平均） | 顯示中 Polyvore 比例 |
|---|---|---|---|---|---|---|
| 補值前 | 0.292 [0.177, 0.415] | 0.292 | 0.923 | 0.923 | 16.3（放寬後） | 0% |
| **補值後** | **0.923 [0.862, 0.977]** | 0.969 | 0.038 | 0.000 | 67.5 | 88.5% |

配對置換檢定（26 個查詢）p=0.0001。

- 補值前：合併型錄的 KAGL outerwear 只有 42 件、dress 19 件；性別永遠不放寬，所以 Polyvore 完全進不來；顏色一過濾就沒貨，92% 的查詢直接把顏色條件丟掉，顯示的商品 71% 顏色不對。
- 補值後：Polyvore 顯示商品滿足度 0.913（105/115）：顏色 0.965、性別 0.957、類別 0.991。**錯誤集中在 outerwear×Men**（滿足度 0.77，性別 0.84）：Polyvore 男裝很少，男裝紅色／米色外套的查詢被 LR 判成 Men 的女裝或中性外套填滿。Women 的 outerwear 0.975、dress 0.955。
- 注意：滿足度用的是 agent 視覺標註，而標註者看得到商品圖；這是「看起來符不符合」而不是商品真實屬性。

## 7. 建議

| 屬性 | 建議 | 門檻 | 依據 |
|---|---|---|---|
| color | **lr_marqo 補色系**，寫代表色＋`color_family` | T=0.86；conf ≥ **0.64**（dev 精度 0.90；Polyvore 視覺樣本 0.99） | KAGL 0.838；遷移 0.918；T2 顏色滿足度 0.97 |
| gender | **lr_marqo 補 Men/Women/Unisex** | conf ≥ **0.65**（dev 精度 0.95）；查詢為 Men 且品類以女裝為主（Polyvore outerwear/dress）時，建議 conf ≥ 0.9 或把 predicted gender 當軟條件 | KAGL gender5 0.935；T2 Men 查詢性別錯 16% |
| occasion | **不用 LR 補**；若要補，用 **Qwen3-VL-8B 多選題**（離線，V100 約 0.32 秒／件，1.23 萬件 Polyvore 約 65 分鐘，**本次未跑全量、未進 T2**） | Qwen T=6.67；conf ≥ **0.86**（dev 精度 0.90） | LR 遷移 0.74／macro-F1 0.47；Qwen 遷移 0.89／macro-F1 0.89、門檻下 53/53 全對 |
| season | **不補** | — | 照片近乎不可預測（最佳 0.66 vs 多數類 0.48） |
| category | 不自動改寫；把模型與 metadata 不一致的商品列入人工複核清單 | Marqo 零樣本 conf ≥0.9 且 fashion-clip 同意 | M 比例 KAGL 17%、Polyvore 37% |

- 為什麼顏色與性別不用 Qwen：在 KAGL 上 Qwen 顏色 0.739、性別 0.844，都顯著低於 LR（p<0.001）；在 Polyvore 樣本上顏色 0.871 也不比 LR 好，而且推論成本高兩個數量級。Qwen 的長處是 occasion 這種「風格判斷」與類別稽核的第三意見。
- 季節：Qwen 0.490（等於多數類基準），再次確認照片裡沒有可靠的季節訊號。

## 8. provenance 規則與整合 hook（給 coordinator）

1. **prepare / merge 寫入**（`scripts/merge_catalogs.py` 合併之後呼叫）：
   ```python
   from engine02.attribute_fill import fill_attributes, LinearProbePredictor, decide, restrict, FAMILY, FAMILY_CANONICAL
   filled = fill_attributes(items, predictions, thresholds={"color": 0.64, "gender": 0.65})
   ```
   `predictions[attr]` 欄位＝`item_id, value, confidence, model`。規則：metadata 永不覆寫；低於門檻不寫（null）；`attr_source[attr] = "predicted:logreg-marqo-fashionSigLIP"`；新增 `color_confidence`、`gender_confidence`、`color_family` 欄。LR 權重需在 KAGL 全部訓練資料上重訓一次並存檔（本實驗的 `stage_linear` 可直接沿用）。
2. **硬過濾**：`engine02/pipeline.py` 中 `filter_with_relaxation` 換成 `attribute_fill.provenance_filter(predicted_policy="family", min_confidence=0.0)`。
   - `family`：顏色一律在色系層級比對（「Navy Blue」也能配到預測的 `Blue`）；
   - `min_confidence`：查詢時把低信心的預測值視為 null（例如 Men 查詢設 0.9）；
   - `unknown`：完全忽略預測值（等同補值前）。
   `constraints.satisfies`（metrics 用）目前仍是字串精確比對，對 predicted 顏色會低估滿足度；若要一致，metrics 也應用同一個 view。
3. **解釋文字**：`attribute_fill.provenance_note(items, pos)` 回傳 `{"color": "顏色為模型判讀", ...}`；explain 模組在引用 predicted 屬性作為理由時必須附上這句話，且 predicted 屬性不應單獨當成「符合您指定的顏色」的唯一理由而不加註。
4. **放寬 ladder 不變**：predicted 值被視為已知值，所以 `color:allow_unknown` 不再把 Polyvore 未知顏色商品放進來；若日後要更保守，可在 ladder 前加一步 `("color", "predicted_as_unknown")`。

## 9. 限制
- 所有視覺標註都是 LLM agent 判讀，數量小（102、115、60），CI 寬。
- KAGL metadata 有雜訊（§3），屬性準確率的上限不是 1；occasion/season 標籤與品類高度相關，KAGL 上的數字高估了可遷移性。
- T2 查詢只有 26 個，只涵蓋 outerwear/dress 與顏色＋性別。
- nycu 上較早的一輪（含 Qwen bf16 全量 Polyvore）因連線中斷未取回，本文所有數字都來自 cfda4 重算。Qwen 在 V100 上以 fp16 推論（sanity：48 件 valid_rate 1.00、類別與 metadata 一致 48/48），可能與 bf16 略有差異。
