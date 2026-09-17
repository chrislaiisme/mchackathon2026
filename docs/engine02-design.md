# ENGINE 02｜檢索、排序與可驗證解釋 — 設計與實驗報告

> 狀態：2026-09-17，分支 `engine02-research`。程式在 `engine02/`，測試 `tests/`（138 項全過），實驗腳本 `scripts/run_ablation.py`。
> 本文件取代原 PRD「ENGINE 02」小節裡**尚未經過驗證的部分**；PRD 原本的設計（M3–M7）全部保留成可切換的對照組 `prd_original`，所以任何修改都有數據對照。
> 原始實驗數據（CSV、embedding 快取）只存在本機 `reports/ablation/`、`data/`，不進 git。

---

## 0. 一頁結論

| 決定 | 依據 |
|---|---|
| Dense encoder 用 **Marqo-FashionSigLIP**，fashion-clip 當 CPU 備援 | 7 個模型實測都能跑；KAGL 上換句話說的查詢 dense NDCG@5：0.463 vs 0.426（差距在信賴區間內）；Marqo 的授權是 Apache-2.0 |
| **硬條件用過濾，不進分數**；過濾後沒結果就依固定順序放寬，並寫進理由 | Taobao MGDSPR（KDD 2021）、Vespa；T2：沒放寬的查詢 100% 滿足條件，有放寬的 40%，而且都會標示出來 |
| 混合檢索的前提是 **ENGINE 01 把屬性值正規化成商品庫詞彙** | T1：用詞相同時混合檢索 0.84–0.87 ≫ 純 dense 0.57–0.61；換句話說時混合檢索掉到 0.09–0.21 ≪ 純 dense 0.43–0.46 |
| 設計要素分數 c(i,d) 改用**反義詞成對打分**，並做分布正規化 | T3：隨機字詞對照組的 AUROC 只有 0.33–0.70，證明 c(i,d) 真的在量東西；反義詞版在休閒感、深色上明顯優於 PRD 原版（Marqo：0.72→0.98、0.84→0.98），鮮豔色彩略低（0.88→0.85） |
| 理由改用**最小充分集合**，不用 PRD 的「拿掉就掉出前 5」 | T4：PRD 原版有 10–20% 的卡片沒有任何理由，只有 66–68% 的理由組合本身足以讓商品留在前 5；新版 100% 有理由、100% 足以，隨機理由只有 12–16% |
| 隱性需求權重維持 **γ=1** | T6：γ=1 讓前 5 名換掉 19–26%，NDCG@5 下降不顯著（−0.011～−0.027）；γ≥2 顯著犧牲品質 |
| 在卡片內 z-score 改成**用整個過濾後商品池的統計量**標準化 | 候選數量改變時，理由不會跟著變（method inventory §11） |
| 穿搭相容性**只在有錨點商品時才啟用**，而且要用**商品層級**模型（OutfitTransformer） | 文獻中所有相容性任務都需要錨點；FITB 200 題：品類 NPMI 25%（＝隨機）、embedding 相似度 48%、OutfitTransformer 54.5% |
| 回饋：批評回饋效果大；Rocchio 單獨**沒有效果**，改加 **Bayes 偏好學習＋κ=1 縮減**（勝過 PRD ±1 規則，且不會一次點選就暴衝） | T5：4 輪成功率 1–2% → 39–44%（p<0.001）；Rocchio 相對只用批評多 3 個百分點，p≈0.54–0.60，**不顯著** |
| 推薦理由**預設用模板**，LLM 改寫要通過程式事實檢查 | 本地 Qwen3-1.7B 實測會把「盛夏偏熱」講反；有 OpenAI key 時才開改寫 |
| 圖文 reranker（Qwen3-VL-Reranker-2B）**預設不開** | CPU 每個 pair 21.6 秒；4090 上加了它，用詞相同的查詢反而變差（0.840→0.797，p=0.001），每次查詢多約 1 秒 |
| 7 個 encoder 之間：時尚／SigLIP 系列**彼此無顯著差異**，但都顯著勝過通用 CLIP | 換句話說的查詢 dense NDCG@5：Marqo-FashionSigLIP 0.463、fashion-clip 0.426（p=0.21）、OpenAI CLIP 0.334（p<0.001） |
| 材質光澤類的設計要素改用 **VLM 標註**（混合模式） | 目視標註 AUROC：亮面材質 CLIP 0.71 → Qwen3-VL-8B 0.90；logo／領子／圖案 VLM 也略高；寬鬆版型 CLIP 較好 |
| 感性對照表改用**有文獻依據的 v1**，成對反義要素合併成一條軸 | 32 篇文獻，50 個非零格，強證據 3 格；正式／休閒兩極分開給值會重複計算 |
| 缺屬性的商品用**校準後的模型補值**，補不到門檻就留 unknown | 全量 25,000 件標註（格式正確率 100%）：性別補到 99.97%、顏色 83.6%、場合 70.5%、季節不補；四條件查詢需要放寬的比例 92.3% → **3.8%**（§3.17） |
| 趨勢關鍵字**只當展示標籤**，不進分數 | 28 組設定全部變差，−0.16～−0.38 NDCG@5（p≈1e-4）（§3.15） |
| 生成概念圖以 **w=0.2** 融入查詢（沒有圖時是 no-op） | 使用者講不出話時 NDCG@5 0.078 → 0.278（44k，p≈1e-4），隨機概念圖對照組無效果（−0.004，p=0.71）（§3.16） |
| `/complete-look` 用 **OutfitTransformer 互補頭**，真實 API 已實測 | T5 互補頭 MRR 0.277 > 相容性頭 0.216 > 圖片相似度 0.185；API 端單／雙錨點與性別硬過濾都通過（§3.14） |

---

## 1. 介面規格（要和 ENGINE 01／03 負責人確認）

完整定義見 `engine02/contracts.py`（Pydantic），版本 `0.1.0`。

### 1.1 輸入 `Engine02Request`

| 欄位 | 來源 | 說明 |
|---|---|---|
| `constraints.{category,color,occasion,season,gender,style_keywords}` | ENGINE 01 M1 | 每欄 `state` ∈ `unmentioned / value / dont_care / inferred`（PRD 四態）。**`value` 才當硬過濾**，`inferred` 只當軟訊號。值必須是商品庫詞彙（見 §4.1）。 |
| `constraints.budget` | ENGINE 01 M1 | `max_price / min_price`；目前商品庫沒有價格，會自動放寬並標示 |
| `constraints.excluded_values` | ENGINE 03 `exclude(屬性,值)` | 永遠不放寬 |
| `needs[] = {need_id, prob}` | ENGINE 01 M2 | p(n)，`need_id` 必須存在於感性對照表 |
| `retrieval_text`（**新增提議**） | ENGINE 01 | 一句**英文、不含否定詞**的短描述。原因：商品庫是英文、使用者講中文；CLIP 類模型對否定詞接近隨機（CVPR 2025 NegBench，本機實測差距 ≤0.03） |
| `feedback.design_adjust_steps` | ENGINE 03 `adjust(d,±1)` | 每步 0.25，上限 ±3 步，由 ENGINE 02 換算成 Δβ |
| `feedback.chosen_item_ids / rejected_item_ids` | ENGINE 03 choice | Rocchio 正例／負例，加上「和否決商品相似」的懲罰項 |
| `feedback.excluded_item_ids` | ENGINE 03 | 不再出現 |
| `feedback.anchor_item_ids` | ENGINE 01／03 | 使用者要拿來一起穿的商品；**有值才會計算穿搭相容性** |
| `feedback.concept_image_embedding`（提議） | 生成分支 | 預設權重 0（對照組 0.2），理由見 §3.6 |

### 1.2 輸出 `Engine02Response`

每張卡片 `RankedItem`：
- `score` = Σ `contributions[].contribution`（**加總完全等於總分**，測試強制檢查）
- `contributions[]`：每一項的 `raw / normalized / weight / contribution`，設計要素項另外附 `need_shares`（哪個需求貢獻多少，加總等於該項貢獻）
- 三種理由判定一次全給：`rank_without / necessary`（PRD 反事實）、`diff_vs_cutoff`（和第 k+1 名的對比）、`sufficient`（最小充分集合），`cited` 標出**卡片上實際顯示的**那幾項
- `design_scores`：這件商品所有 c(i,d)，**ENGINE 03 算 S(i|n)=Σ_d K[n,d]·c(i,d) 直接用**
- `reasons`（模板句，每條都對應一個 cited 項）、`explanation`、`explanation_source`（llm／template）

整輪的回傳：
- `constraint_report`：套用了哪些條件、依序放寬了哪些
- `metrics`：規則計算的硬條件滿足率、被排除值出現次數、違反回饋次數（PRD §7，**不是用排序分數算的**）
- `query_embedding`：本輪查詢向量，提供給 ENGINE 03 或下一輪做 Rocchio

---

## 2. 架構

```
Engine02Request
  │
  ├─ 1. 硬條件過濾（pandas mask）→ 結果不足 k 件時依序放寬：
  │     顏色允許缺值 → 季節允許缺值 → 場合允許缺值 → 拿掉季節 → 拿掉場合 → 預算×1.2 → 拿掉顏色 → 拿掉預算
  │     （品類、性別、排除值永遠不放寬；只記錄真的讓結果變多的步驟）
  │
  ├─ 2. 候選召回（過濾後的商品池內精確計算）
  │     dense：Marqo-FashionSigLIP 圖片向量 · 查詢向量（有回饋時做 Rocchio）
  │     sparse：BM25（rank_bm25）over title＋subcategory＋color
  │     融合：RRF(k=60) / 正規化 convex / 依查詢詞命中率調整的 RRF → top-50
  │
  ├─ 3. 可加總 reranker（用商品池統計量標準化）
  │     S(i) = w_dense·z(dense) + w_bm25·z(bm25)
  │          + Σ_d β_d · c(i,d)          β_d = Σ_n p(n)K[n,d] + 0.25·steps_d
  │          + w_compat·compat(商品, 錨點)       ← 只在有錨點時；OutfitTransformer，無模型時退回品類 NPMI
  │          + w_trend·z(趨勢 BM25) − w_pen·z(和否決商品的最大相似度)
  │          [+ w_rerank·z(cross-encoder)]       ← GPU 才開
  │     [MMR 多樣化（對照組）]
  │
  ├─ 4. 理由判定：必要性（PRD）／對比邊際／最小充分集合（預設）
  └─ 5. 模板理由 →（有 key 時）LLM 改寫 → 數字與標籤事實檢查 → 失敗就用模板
```

商品資料：`Marqo/KAGL`（公開、卡片標 MIT、有顏色／季節／場合／性別，**沒有價格**）目前 5,000 件；穿搭共現統計來自 `Marqo/polyvore` 的 21,587 組穿搭。細節見 `docs/research/catalog-options.md`。

---

## 3. 實驗

### 3.0 設定與限制（先讀）
- 商品庫是 KAGL 的 5,000 件（shuffle buffer 抽樣，不是真正的隨機樣本）；筆電 CPU。
- **不用 LLM，也沒有人工標註**：標準答案全部來自資料集屬性，image encoder 看不到這些屬性。所以這些都是**代理指標**，簡報上要照實說明。
- 60 句查詢、100 個模擬目標；統計用 query 層級配對置換檢定（10,000 次）與 bootstrap 95% 信賴區間。
- 原始檔在 `reports/ablation/kagl_<encoder>/`，指令：`python scripts/run_ablation.py --encoder <name>`。

### 3.1 T1 檢索品質（NDCG@5；等級：子類＋顏色＋性別＋場合全對 3，子類＋顏色 2，子類 1）

| 設定 | fashion-clip 用詞相同 | fashion-clip 換句話說 | Marqo 用詞相同 | Marqo 換句話說 |
|---|---|---|---|---|
| BM25 | 0.758 | 0.034 | 0.758 | 0.034 |
| dense | 0.569 | **0.426** | 0.614 | **0.463** |
| hybrid RRF | 0.821 | 0.193 | 0.830 | 0.191 |
| hybrid convex | **0.868** | 0.110 | **0.865** | 0.119 |
| full（可加總，無需求） | 0.842 | 0.093 | 0.840 | 0.093 |
| RRF＋依命中率調整 BM25 | 0.821 | 0.195 | 0.830 | 0.206 |
| full＋依命中率調整 BM25 | 0.842 | 0.169 | 0.840 | 0.175 |

換句話說的查詢把子類、顏色、性別、場合都換成同義詞（tee、midnight、guy's、workout），用來模擬 ENGINE 01 **沒有**做詞彙正規化的情況。

解讀：
- 用詞和商品庫一致時，混合檢索比純 dense 高 0.22–0.30（p<0.001）。
- 用詞不一致時，BM25 只會帶進雜訊，連依命中率調整權重都救不回來。
- **所以詞彙正規化是 ENGINE 01 的硬性需求**，不是加分項。
- Marqo 和 fashion-clip 在這份 5,000 件的資料上差距不顯著，44k 全庫跑完再下定論。

每次查詢延遲（筆電 CPU，不含 LLM）：fashion-clip 約 60 ms，Marqo 約 95 ms。

### 3.2 T2 硬條件（同時指定品類、顏色、性別、場合 4 個條件）
- 23% 的查詢需要放寬條件（5,000 件的商品庫太小）；沒放寬的查詢 100% 滿足全部條件，有放寬的查詢平均只有 40% 的商品滿足**原始**條件，而且放寬了什麼都有寫進理由。
- 所有查詢都回傳滿 5 件。

### 3.3 T3 設計要素分數是否真的在量該要素（AUROC，標準答案來自資料集屬性）

| 設計要素（標準答案） | PRD 原版描述子 | 隨機字詞對照 | 反義詞成對＋分布正規化（新預設） |
|---|---|---|---|
| 正式感（usage=Formal vs Casual/Sports） | 0.978 | 0.523 | **0.981** |
| 休閒感（反向） | 0.718 | 0.638 | **0.981** |
| 低明度深色（黑、藏青…… vs 白、米……） | 0.839 | 0.484 | **0.981** |
| 鮮豔色彩（紅黃橙粉綠 vs 無彩色） | **0.884** | 0.466 | 0.848 |

表中是 Marqo 的數字；fashion-clip 的趨勢相同，隨機字詞對照在 0.33–0.70。

限制：
- 只有 4 個要素找得到不靠 CLIP 的標準答案。**肩線、霧面／亮面、領型、logo 這些 PRD 核心要素目前沒有驗證**，要靠 VLM 標註或人工標 40 件。
- 這 4 個要素都適用所有品類，所以適用性遮罩在這裡看不出效果。

### 3.3b PRD 核心設計要素的目視標註驗證（420 件盲標）
- **標註方式**：由 LLM 標註員逐張看圖，看不到任何模型分數，標籤只有 1／0／不適用。**不是人工標註**。
- **抽樣**：依 Marqo 反義詞分數的高／中／低三層各抽 20 件，對該評分方式可能稍微有利；fashion-clip 那組不受這個抽樣影響，趨勢一致。
- **檔案**：`data/labels/`（只存在本機），`scripts/eval_visual_labels.py`。

| 設計要素 | 正／負例 | PRD 原版描述子 | 隨機字詞 | 反義詞＋分布正規化 |
|---|---|---|---|---|
| 明顯 logo | 17／43 | 0.91 | 0.48 | **0.96** |
| 挺版領子 | 27／33 | 0.92 | 0.17 | **0.97** |
| 強烈圖案 | 20／40 | 0.85 | 0.36 | **0.90** |
| 寬鬆版型 | 7／47 | 0.84 | 0.65 | 0.86（CI 0.71–0.98） |
| 亮面材質 | 9／51 | 0.75 | 0.56 | 0.71（CI 0.52–0.89） |
| 肩線挺、柔軟針織 | **0 正例** | — | — | — |

表中是 Marqo-FashionSigLIP 的數字。

解讀：
- logo、領子、圖案用 CLIP 就夠準。
- **材質光澤不可靠**，跟 OVAD、MODA 的文獻一致。這一類要素要等 VLM 標註（`full_concept_vlm`）的結果。
- **KAGL 幾乎沒有西裝外套和針織衫**，所以「肩線挺」「柔軟針織」無法驗證，面試情境也沒有商品可推。已在 nycu 上把 Polyvore 服飾併入商品庫（`kagl_polyvore`）。

### 3.3c VLM 標註 vs CLIP（同一批 397 件的目視標註）

| 設計要素 | 正／負例 | CLIP（Marqo 反義詞＋分布正規化） | Qwen3-VL-8B（逗號分隔作答、讀選項機率） |
|---|---|---|---|
| 亮面材質 | 9／51 | 0.71（0.52–0.89） | **0.90**（0.80–0.98） |
| 明顯 logo | 17／43 | 0.96 | **0.98** |
| 挺版領子 | 27／33 | 0.97 | **0.98** |
| 強烈圖案 | 20／40 | 0.90 | **0.94** |
| 寬鬆版型 | 7／47 | **0.86** | 0.77（0.60–0.93） |

- **對 VLM 可能偏寬**：目視標註員也是 LLM，和 VLM 的判斷偏差可能相近。
- **VLM 標註第一版有 bug**：`BBB` 會被 BPE 合成一個 token，導致每題的機率對錯位置，已修正。修正後 397 件的答案格式 100% 正確。
- **混合模式** `full_concept_hybrid`：材質、logo、圖案、領子用 VLM，其他用 CLIP。

### 3.3d Encoder 比較（KAGL 5k，4090）
- 用詞相同的查詢，dense NDCG@5：Marqo-FashionSigLIP 0.614、zooclaw 0.612、siglip2 0.601、marqo-fashionCLIP 0.585、fashion-clip 0.569、LAION 0.537、OpenAI CLIP 0.499。
- 換句話說的查詢：0.463／0.436／0.431／0.433／0.426／0.388／0.334。
- **SigLIP 系列要把文字轉小寫**（模型卡明寫）。沒轉小寫時，用詞相同的查詢 dense 只有 0.04，已修正。

### 3.4 T4 理由忠實度（40 句查詢 × 5 張卡，每句隨機給 3 個需求機率）

| 理由判定方式 | 有理由的卡片 | 平均理由數 | 拿掉理由就掉出前 5（隨機） | 只留理由仍在前 5（隨機） |
|---|---|---|---|---|
| PRD 原版（必要性＋卡片內 z-score＋原版描述子） | 80.5% | 1.6 | 100%（55%） | 66%（12%） |
| 必要性（新標準化） | 96.5% | 2.2 | 100%（73%） | 49%（9%） |
| 對比邊際 | 57% | 1.0 | 96%（68%） | 11%（4%） |
| **最小充分集合（預設）** | **100%** | 3.5 | 100%（77%） | **100%**（16%） |

表中是 Marqo 的數字。「只留理由仍在前 5」在充分集合模式下依定義就是 100%，所以真正的證據是對照「隨機挑同樣數量的項」（括號內），以及其他模式做不到的覆蓋率。

### 3.5 T5 回饋迴圈（規則模擬使用者，100 個隱藏目標，4 輪）

| 模式 | 第 1 輪 | 第 2 輪 | 第 3 輪 | 第 4 輪 |
|---|---|---|---|---|
| 無回饋 | 1% | 1% | 1% | 1% |
| 只點選（Rocchio） | 1% | 3% | 3% | 4% |
| 只批評（每輪多說出一個屬性） | 1% | 8% | 36% | 39% |
| 批評＋Rocchio | 1% | 11% | 36% | 42% |

表中是 Marqo 的數字；fashion-clip 是 2 / 15 / 42 / 44%。

- 批評回饋比無回饋 p<0.001。
- **Rocchio 相對只批評 p=0.54（fashion-clip p=0.60），不顯著。**
- 模擬使用者是規則式的，不是 LLM，也不是真人，簡報上要標示「模擬」。

### 3.5b 44k 全庫複核（KAGL 44,434 件，Marqo-FashionSigLIP，100 句查詢，200 個模擬目標，nycu）

| 結論 | 5k | 44k | 是否一致 |
|---|---|---|---|
| T1 用詞相同：完整版 > 混合 > BM25 > dense | 0.840 / 0.830 / 0.758 / 0.614 | 0.814 / 0.801 / 0.641 / 0.528 | ✅ |
| T1 換句話說：dense ≫ 混合 | 0.463 vs 0.191 | 0.432 vs 0.205 | ✅ |
| T2 需要放寬的比例／條件滿足率 | 23% / 86% | 11% / 93% | ✅（商品庫越大越少放寬） |
| T3 反義詞打分：休閒感／深色 | 0.72→0.98 / 0.84→0.98 | 0.66→0.98 / 0.86→0.985 | ✅ |
| T4 充分集合：覆蓋率／足以留在前 5（隨機） | 100% / 100%（16%） | 100% / 100%（20%） | ✅ |
| T4 充分集合：拿掉理由就掉出前 5（隨機） | 100%（77%） | **98.5%**（82%） | ⚠️ 充分集合只保證「足以」，不保證每條都「必要」 |
| T4 PRD 原版：沒有理由的卡片 | 19.5% | 10.5% | ✅ |
| T5 批評＋Rocchio vs 只批評（第 4 輪） | 42% vs 39%，p=0.54 | 15.5% vs 17.5%，p=0.52 | ✅ **Rocchio 兩個規模都沒有效果** |

- 44k 上每次查詢約 92–97 ms（伺服器 CPU，BM25 佔大部分）。
- T5 在 44k 上成功率明顯變低：同一品類裡相似的商品太多，只揭露 3 個屬性不夠定位到目標商品。

### 3.5c 穿搭相容性：填空測驗（FITB，Polyvore 真實穿搭 200 題，每題 4 個同品類候選，隨機 25%）

| 打分方式 | 準確率（95% CI） |
|---|---|
| 品類共現 NPMI（原 PRD／原實作） | 25%（同品類分數全部相同，只能平手） |
| 圖片 embedding 平均相似度（Marqo-FashionSigLIP） | 48%（41–55%） |
| **OutfitTransformer**（owj0421 重實作，CLIP 版權重） | **54.5%**（47.5–61.5%） |

- **品類層級的相容性在「要搭我的牛仔褲」這種情境完全沒有作用**，必須做到商品層級。`Engine02(compat_model=OutfitTransformerCompat(...))` 已接上，有錨點時會使用。
- **可能高估**：OutfitTransformer 的訓練資料 Polyvore Outfits 和這份測驗資料（Maryland Polyvore）可能有圖片重疊。
- **和 embedding 相似度的差距還不顯著**：信賴區間重疊。
- **延遲**：4090 上每個候選約 102 ms（和 VLM 共用 GPU 時量的），現場只建議對前 10 名計算。

### 3.5d T6 隱性需求 vs 檢索品質的取捨（「在約束下維持推薦品質」）

設計要素權重 β_d 乘上 γ，對每句查詢隨機給 3 個需求機率，量三件事：
1. NDCG@5（屬性相符，同 T1）
2. 需求契合度：前 5 名的 Σ_d β_d·c(i,d)
3. 前 5 名相對 γ=0 被換掉的比例

| γ | 5k NDCG@5 變化（p） | 5k 換掉比例 | 44k NDCG@5 變化（p） | 44k 換掉比例 |
|---|---|---|---|---|
| 0.5 | −0.014（0.21） | 13% | −0.002（0.78） | 16% |
| **1（預設）** | **−0.027（0.06）** | **19%** | **−0.011（0.21）** | **26%** |
| 2 | −0.070（0.001） | 34% | −0.044（0.003） | 39% |
| 4 | −0.192（<0.001） | 49% | −0.107（<0.001） | 54% |
| 8 | −0.342（<0.001） | 67% | −0.193（<0.001） | 67% |

需求契合度從 γ=0.5 起每一檔都顯著上升（p<0.001）。

- **預設 γ=1 落在轉折點**：前 5 名有 19–26% 換成更符合隱性需求的商品，屬性相符度的下降不顯著。γ≥2 開始顯著犧牲品質。
- **商品庫越大，取捨越有空間**：同樣 γ=1，44k 的品質代價（−0.011）比 5k（−0.027）小。
- **限制**：NDCG 用屬性當標準答案，量不到需求本身。需求契合度是用我們自己的 K 表和 c(i,d) 算的，會偏向系統，只能當作「需求確實有影響排序」的證據，**不能當作「推薦更符合使用者需求」的證據**。

### 3.7 推薦系統元件（4 個 sub-agent，nycu，配對統計；詳見 `docs/research/recsys-*.md`）

| 元件 | 方法（文獻） | 關鍵結果 | 採用 |
|---|---|---|---|
| 從點選學偏好（T7） | Bayes 成對 logistic／Bradley–Terry（reward-rational choice, NeurIPS 2020）、Thompson、LinUCB（WWW 2010）、PRD ±1 規則 | 200 位模擬使用者 × 5 輪：Bayes+Rocchio 隱藏效用 2.48（5k）／2.36（44k），顯著勝過 PRD 規則約 0.18–0.20（p<0.001）；**勝過 Rocchio 的部分有循環性**（改用 metadata 口味時打平或小輸）；Thompson／LinUCB 沒有更好 | ✅ `choice_history` → Δβ |
| 「這件但換成 X」（T8） | 組合式檢索 CIReVL（ICLR 2024）、CLIP4Cir、向量加減（latent linear critiquing） | 44k NDCG@10：只加硬條件 0.347 → 參考商品＋改寫文字＋新值過濾＋RRF **0.610**（p<0.001）；**放寬規則原本會吃掉 46% 的顏色批評** | ✅ `reference_item_id`＋`critique`；批評值改成永不放寬 |
| 清單多樣化（T9） | MMR、DPP（NeurIPS 2018／YouTube CIKM 2018）、xQuAD | DPP θ=0.9（top-20）：44k 近似重複 2.45% → 0.35%，NDCG@5 −0.005（p=0.22）；被提前的卡片標「為了多樣性而納入」，忠實度檢查 300/300 | ✅ 預設 |
| 搭配推薦 | P-Companion 先品類後商品（CIKM 2020）＋OutfitTransformer 互補頭 | Polyvore 100 選 1：MRR 0.277（互補頭）vs 0.216（相容性頭）vs 0.185（圖片相似度），p<0.001；**可能有訓練資料重疊** | ✅ `POST /complete-look`，已在真實 API 上以互補頭實測（§3.14） |
| 排序權重學習（T10） | coordinate ascent、pairwise logistic（非負、保持可加總）、ranx fusion | 5-fold CV：學權重只比「依查詢類型分流」多 +0.009；以詞彙覆蓋率分流在 44k 失效 | ✅ 改由 ENGINE 01 回傳 `retrieval_text_normalized`，未正規化時只用 dense |

**服務層** `engine02/service.py`（`POST /rank`）：點選歷史 → Δβ → 批評組合 → 加總排序與理由 → DPP 多樣化。`POST /rank/plain` 保留純 pipeline 供對照。

### 3.8 服裝分類體系（taxonomy sub-agent，`docs/research/taxonomy.md`）

- **結構**：12 個 L1（對應搭配槽位）→ 89 個 L2，每個節點附中文同義詞（「短T」「西裝外套」「瑜珈褲」…）、針織／梭織先驗與 HS 61/62 章。
  - 運動機能、印度民族服飾做成**橫切集合**（`coll.activewear`、`coll.ethnic`），不當 L1。
- **覆蓋率**（L2／含 L1）：KAGL 44k 95.3%／99.7%；Polyvore 25k 85.9%／91.5%。沒對到的主要是居家家具與泛用桶。
- **現行粗分類驗證**：沒有系統性錯誤；但 KAGL 44k 的 `other` 混了 2,276 件**內著／睡衣**（聚陽產品線）和 2,400 件美妝，已拆開。
- **流程整合**：
  - 品類值接受 taxonomy id、中文或 catalog 詞，放寬改成 L2 → L1，而且先放寬類別、再丟顏色。
  - taxonomy 對不到的商品庫退回原本的精確比對。
  - 硬條件滿足率改由 taxonomy 判定。
  - `GET /vocabulary` 附上封閉詞彙表，給 ENGINE 01 的 GPT 使用。
- **實測**：「西裝外套＋藏青」→ KAGL 沒有男生西裝外套，放寬為「外套」後，第 1 名是藏青外套，理由寫明「西裝外套→外套」。滿足率照實記 0。

### 3.9 跨硬體重現（cfda4 V100）
- **環境**：torch 2.14 + CUDA 12.6，支援 sm_70；132 項測試通過。KAGL 5k 重建後與本地 5000/5000 相同。
- **VLM 標註在 V100 上改用 fp16**（V100 沒有原生 bf16）：答案格式正確率 100%，AUROC 與 4090 bf16 幾乎一致。
  - 強烈圖案 0.945／0.944、挺版領子 0.983／0.984、亮面材質 0.911／0.908、寬鬆版型 0.775／0.769、明顯 logo 0.981／0.977。

### 3.10 z-score 截斷（服務預設 `full_zclip3`）
- 商品池層級的 BM25 分布極度偏斜：大部分商品是 0 分，少數關鍵字命中的商品 z 值可以到 +7，壓過所有其他理由。
- 截斷在 ±3（100 句查詢，配對檢定）：

| 商品庫 | 用詞相同 NDCG@5（full → zclip3） | 換句話說 |
|---|---|---|
| KAGL 5k | 0.837 → 0.819（−0.018，p=0.036） | 0.099 → 0.197（p<0.001） |
| KAGL 44k | 0.814 → 0.808（−0.006，p=0.65） | 0.112 → 0.213（p<0.001） |

- 在接近真實規模的 44k 上幾乎沒有代價，而且卡片理由比較均衡，所以 API 與 demo 預設改用 `full_zclip3`。原本的 `full` 保留，先前所有數字都可重現。

### 3.11 屬性補值與資料來源標示（classify sub-agent，`docs/research/classify.md`）

問題：合併商品庫裡 Polyvore 的 14,289 件**沒有顏色、性別、場合、季節**，硬條件一來就只能靠放寬把它們放進來。

| 屬性 | 最佳方法（KAGL test 2,655 件） | 準確率 | 決定 |
|---|---|---|---|
| 性別（5 類） | Marqo embedding＋logistic regression | 0.935 | ✅ 補，信心 ≥0.65 |
| 色系（12 類） | 同上 | 0.838 | ✅ 補，信心 ≥0.64；遷移到 Polyvore 0.918 |
| 場合 | 同上在 KAGL 0.927，但**遷移到 Polyvore 只有 0.74**（幾乎全猜 Casual）；Qwen3-VL 0.894 | — | ⚠️ 只用 Qwen 高信心（≥0.86），尚未全量 |
| 季節 | 最佳 0.66（多數類 0.48） | — | ❌ **不補**，照片看不出季節 |

- **對 ENGINE 02 的效果**（外套／洋裝 26 個查詢）：硬條件滿足度 0.29 → **0.92**（p=0.0001）、需要放寬的比例 0.92 → 0.04；Polyvore 商品顏色非空比例 0% → 84%、性別 0% → 89%。
- **資料來源不混用**：`fill_attributes` 不覆寫資料集原值，寫入 `attr_source="predicted:<model>"` 與信心欄位；卡片上會加註「顏色為模型判讀」。
- **只在有補值的商品庫啟用**：pipeline 偵測到 `attr_source` 含 predicted 才改用 `provenance_filter("family")`。**副作用**：該商品庫的顏色比對會整體放寬到色系（查 Navy Blue 也會命中一般藍色），原始 KAGL 不受影響。
- **分類雜訊稽核**：Marqo 零樣本與資料集標籤一致率 KAGL 0.963、Polyvore 0.917。抽 60 件不一致樣本目視判讀（**agent 判讀，非人工**）：Polyvore 有 11 件是資料集標錯、KAGL 5 件，其餘是模型錯或分類邊界。對照表已修：Vests 應歸上衣。

### 3.12 偏好學習的抑制（T7b）
點一次就大幅改變排序會讓第二輪的理由被「你上一輪的回饋」主導。200 位模擬使用者 × 5 輪比較 6 種抑制方式：

| 設定 | 點 1 次後 \|Δβ\| 平均／最大 | 第 2 輪以回饋為首的理由 | 第 5 輪效用 |
|---|---|---|---|
| 原版 | 0.23／0.82 | 48%（5k）／53%（44k） | 基準 |
| **κ=1 縮減（Δβ·n/(n+1)，新預設）** | **0.11／0.41** | **36%／45%**（p<0.001） | −0.009～+0.023（p≥0.38） |
| κ=2 縮減 | 更低 | 更低 | 44k 小輸 0.04（p=0.038） |
| 縮小先驗 σ=0.3 | — | — | 明顯變差（−0.13～−0.17） |

κ=1 仍顯著勝過 PRD 的 ±1 規則（+0.07～+0.23，p≤0.033）。**比例下限**：需求平均分配時，連 PRD 規則都有 22–27% 的理由以回饋為首，再往下要在畫面呈現層處理。

### 3.13 合併商品庫的 VLM 標註（cfda4 V100 fp16）
17,783 件全部標註完成，答案格式正確率 99.99%，每件 0.39 秒。在 397 件目視標註上的 AUROC 與 4090 一致（logo 0.981、領子 0.983、圖案 0.945、亮面 0.911、版型 0.775）。模型也會誠實回答「不適用」：肩線 46%、領子 61%、版型 26%（多為鞋包配件），適用性遮罩因此有實際依據。

### 3.14 OutfitTransformer 接進 `/complete-look` 的實測（cfda4 V100）
先前 `/complete-look` 在真實 API 上一律 500：服務層選的方法是 `ot_cir`（互補頭，T5 最佳 MRR 0.277），但 API 只載入相容性頭，`models["complementary"]` 直接 KeyError。修法是讓 `FastOutfitTransformer.checkpoints()` 回報這台機器有哪些頭、API 依 `ENGINE02_OT_HEADS`（預設 `complementary,compatibility`）載入、缺的頭只記警告不讓服務起不來，服務再依實際載到的頭選 `ot_cir > ot_sim > similarity`，`/health` 也把狀態吐出來：

```json
"complete_look": {"available": true, "method": "ot_cir", "ot_heads": ["complementary", "compatibility"]}
```

修好後在 `kagl_polyvore`（17,783 件）上實測（`.runtime/logs/api_ot_retest.log`，結果存 `reports/server/complete_look_api*.json`）：

| 請求 | 結果 |
| --- | --- |
| 單錨點（藍色牛仔褲 `kagl:29178`），`n_categories=3, k=5` | `method=ot_cir`，三個品類都滿版：top（NPMI 0.127）、shoes（0.046）、outerwear（0.041），每格 5 件 |
| 雙錨點（牛仔褲＋上衣）＋`filters={"gender":["Women"]}` | shoes（0.049）、bag（0.036）各 5 件，回傳商品全部是女裝，硬過濾有生效 |
| 同一個服務的 `POST /rank` | 5 件全為 Navy Blue，理由如「整體風格和你描述的相近（+2.99）」「商品描述直接提到你要的關鍵字（+1.47）」 |

兩件事要跟 ENGINE 03 講清楚：

1. **互補頭的分數是負距離**（實測約 −136.04 ～ −136.09），只在同一個品類格內可比較，**不能**跨格比、也不該直接顯示給使用者；卡片要排序用它，要顯示信心就用格內排名。
2. **錨點 id 打錯現在會回 400** 並列出不存在的 id；以前會被靜默丟掉、回一份空的 slates。壞掉的模型頭也不再是沒訊息的 500，而是帶型別與訊息的 500（伺服器端同時記 traceback）。

### 3.17 全量屬性補值（cfda4，Qwen3-VL-8B 25,000 件）
先前只在小樣本驗證過補值，這次跑完整個合併商品庫：Qwen3-VL-8B 標註 **25,000 件，答案格式正確率 100%，0.164 秒/件**，再依 §3.11 的校準門檻補值（dev 目標精確率 0.9）：

| 屬性 | 方法 | 溫度 T | 門檻 | Polyvore 端補值覆蓋率（補前 → 補後） |
| --- | --- | --- | --- | --- |
| 顏色 | 凍結 embedding 上的 logistic probe | 0.86 | 0.64 | 0% → **83.6%**（外套 82.8%、洋裝 79.2%） |
| 性別 | 同上 | 1.00 | 0.37 | 0% → **99.97%** |
| 場合 | Qwen3-VL-8B | 6.67 | 0.86 | 0% → **70.5%**（外套 70.3%、洋裝 63.4%） |
| 季節 | 不補（沒有可信來源） | — | — | 0% → 0%，維持 unknown |

補值一律不覆蓋原始 metadata，並寫入 `attr_source="predicted:<model>"` 與信心值，卡片上標「顏色為模型判讀」。溫度校準後仍達不到門檻的就**棄權**，這就是場合只補到 70.5% 的原因——寧可留 unknown 也不要假裝知道。

**下游效果（T2：同時指定品類＋顏色＋性別＋場合四個硬條件）**：

| | 過濾後候選數 | 其中 Polyvore 商品 | 需要放寬條件的查詢比例 |
| --- | --- | --- | --- |
| 補值前 | 16.3 | 0.0 | **92.3%** |
| 補值後 | **76.3** | 4.3 | **3.8%** |

也就是說，補值前幾乎每一句四條件的查詢都得動用放寬階梯（先放顏色、再放場合……），補值後只剩 3.8%。Polyvore 端的外套／洋裝／針織原本因為沒有屬性而永遠進不了候選池，現在平均每次會進來 4.3 件——這正是 KAGL 缺品類的補救效果。

### 3.15 趨勢關鍵字：量測後決定「不進排序」（T11，稽核 sub-agent）
PRD §6.6 要把趨勢關鍵字當小權重加分項。實際上 `set_trends()` 從第一版起就**沒有任何呼叫者**，所以過去所有數字都是「沒有趨勢項」的數字。補上並量測 28 組設定（3 種關鍵字來源 × 4 種權重 × 2 個商品庫 × 有無 z 截斷）後：**全部顯著變差**，NDCG@5 −0.16 ～ −0.38（p≈1e-4），手動維護清單只比隨機字詞好一點（44k −0.266 vs −0.301）。

決定：趨勢**只做展示標籤**（`trends.trend_badges()`），不進分數，代價 0；卡片照樣能寫「符合近期趨勢」。另外不接 Pinterest（開發者規範禁止儲存），關鍵字來源是手動清單或從策展穿搭推導，即時抓取的物件標記 `ephemeral` 且拒絕存檔。詳見 `docs/research/engine02-completeness.md` §3.1。

### 3.16 生成概念圖併入查詢：有效，已設為服務預設（T12）
情境是 PRD 生成分支被觸發的前提——**使用者講不出話**（模糊查詢，純文字 NDCG@5 只有 0.078/44k）。以保留法做替身實驗（目標商品自己的圖當「生成圖」，同時把目標放進 `excluded_item_ids`）：

| 概念圖來源 | w=0.2 的 NDCG@5（44k） | Δ vs 不用 | p |
| --- | --- | --- | --- |
| oracle（完美生成器上界） | 0.325 | +0.247 | 1e-4 |
| neighbour（方向抓對的現實生成器） | 0.278 | +0.200 | 1e-4 |
| **mismatched（隨機概念圖＝對照組）** | 0.074 | −0.004 | **0.71（無效果）** |

對照組是關鍵：隨機圖在同一權重下毫無幫助，所以那 +0.20 是資訊而不是「擾動查詢就會變好」。realistic ≈ oracle（0.278 vs 0.325）對生成分支是好消息。

決定：服務預設 arm `full_zclip3` 把 `concept_image_weight` 設為 **0.2**（文獻上限，BMVC 2025／IP-CIR）；**沒有概念圖時完全是 no-op**，`full` 仍維持 0 當 §3.1–3.13 的重現基準。限制要寫進簡報：商品庫是白底商品照、真實生成圖是模特兒照，FashionCLIP 系模型偏好白底，所以 oracle 是上界，**不能宣稱真圖也會 +0.20**。

同時修掉一個註解與程式不一致的 bug：`ArmConfig.z_clip` 寫的是截斷 dense/bm25/trend/penalty 四項，`pipeline._terms` 卻只傳給前兩項；現在四項都套用（趨勢項不進排序，實質影響的是第二輪的負例懲罰）。

### 3.6 還沒跑的對照組
- `full_concept_vlm` / `full_concept_hybrid`：修正版 VLM 全量標註完成後，重跑 T3（已排在 nycu 的 job4）。
- 合併商品庫 `kagl_polyvore`（KAGL＋Polyvore 服飾，補外套、洋裝、針織）：VLM 標註加消融實驗（已排在 job3）。
- `Qwen3-VL-Reranker-8B`：sentence-transformers 和官方 repo 兩條路徑都還沒跑通，暫停。
- `full_concept_image`：生成概念圖併入查詢（權重 0.2）。文獻顯示天真融合會變差（BMVC 2025），等生成分支有圖再測。
- `full_mmr`：多樣化。

---

## 4. 給其他引擎的需求

### 4.1 ENGINE 01
1. 硬條件的值要對到商品庫詞彙：品類是 `top/bottom/outerwear/dress/shoes/bag/accessory/jewelry/other` 或子類名稱（如 `Shirts`）；顏色是 KAGL `baseColour`（如 `Navy Blue`）；場合是 `Casual/Formal/Sports/Ethnic/...`；性別是 `Men/Women/Unisex/Boys/Girls`。詞彙對不上會直接造成 T1 那種崩盤。
2. 另外產生一句英文 `retrieval_text`，**不含否定詞**；否定一律放進 `excluded_values`。
3. `need_id` 使用 `engine02/resources/kansei_v0.json` 裡的 id（目前是草稿，M3 要用 GPT 填值、人工校正）。

### 4.2 ENGINE 03
1. `adjust` 只傳步數（±1），不要傳權重數字；換算在 ENGINE 02 做，這樣同一句回饋的結果可以重現。
2. choice 的 S(i|n) 請直接用回傳的 `design_scores`，不要自己重算 c(i,d)。
3. Rocchio 目前沒有顯著效果，**不要在簡報上宣稱它有效**；批評回饋（exclude／require）才是主要的進步來源。

---

## 4.3 串接方式
- **API**：`uvicorn engine02.api:app --port 8002`。環境變數 `ENGINE02_ENCODER` 可設 `marqo-fashionSigLIP`、`fashion-clip`，或 `hash`（不載模型，用於測試）。
- **端點**：
  - `POST /rank`：主要排序（`POST /rank/plain` 是不做 critique 與多樣化的純管線，給消融用）
  - `POST /view`：排序＋PRD §7 的所有面板（你說的 vs 你沒說的、需求面板、Div@k、資料來源、兩輪 diff、趨勢標籤）。**前端不要自己從卡片重算這些聚合值**，它們是用產生排序的同一組 contribution 算的
  - `POST /complete-look`：搭配推薦（品類用 NPMI，商品用 OutfitTransformer 互補頭；分數是負距離，只在同一格內可比）
  - `POST /concept-image/nearest`：概念圖最近的 3 件（純展示，刻意不走 reranker）
  - `GET /needs/supply`：Sup(n)，ENGINE 03 算缺口乘積要用的供給側
  - `GET /trends`：趨勢標籤關鍵字（`ENGINE02_TRENDS=1` 才載入），`used_in_ranking` 永遠是 false
  - `GET /vocabulary`：ENGINE 01 正規化要用的商品庫詞彙
  - `GET /kansei`：need 與 design element 的 id
  - `GET /items/{id}`、`GET /images/{id}`：商品資料與圖片
  - `GET /arms`、`GET /health`（含載到哪些 OutfitTransformer 頭）
- **規格檔**：`docs/contract/`，含 request／response 的 JSON Schema，以及第 1、2 輪的範例 request／response；範例是 ENGINE 03 把「太像上班族，不要黑色＋點選第 3 件」轉成回饋之後的真實輸出。
- **回傳的輸入警告**：`constraint_report.input_warnings` 會回報 ENGINE 01 該修的問題——`retrieval_text` 殘留否定詞（中英都抓；CLIP 系對否定接近隨機，NegBench ICML 2025，否定請放 `excluded_values`）、以及 `retrieval_text_normalized=false` 導致本輪只走 dense。
- **三個規則指標**：`metrics.feedback_violations` 現在剛好等於 `excluded_value_hits + rejected_item_hits`（口徑：**累計所有先前輪次**的回饋，不只第 1→2 輪；兩者在第 2 輪相同，累計版只會多報不會漏報）。
- **理由方向**：權重為負的設計要素一律寫成「避開〇〇」。例如「避開正式感（+0.93），對應你想要的『你上一輪的回饋、怕顯得太用力』」，避免被讀成「因為很正式才推薦」。

## 4.4 GPU 實測（nycu，RTX 4090）
- **Qwen3-VL-Reranker-2B**（bf16）：每個 pair 9.6 ms，4.25 GB VRAM。48 張圖的 MRR 0.74（隨機 0.09）。top-50 重排約 0.5 秒，**可以在 demo 現場開**。
- **Qwen3-VL-Reranker-8B**：sentence-transformers 路徑載入失敗（`LogitScore` 缺 `true_token_id`），已排程改用官方 repo 的類別重測。
- **Qwen3-1.7B**：bf16、3.4 GB VRAM，這次改寫正確保留了「長袖可能稍熱」的注意事項，但仍然要做事實檢查。
- **Qwen3-VL-8B 屬性標註**：每件約 0.1–0.18 秒，5,000 件約 15 分鐘。
- **商品庫一致性**：伺服器上重建的 KAGL 5,000 件與本地完全相同（5000/5000 ID 一致），結果可以直接比對。

## 5. 待辦與 GPU 計畫

| 項目 | 需要 | 狀態 |
|---|---|---|
| 44k 全庫 KAGL＋7 個 encoder 重跑 T1–T5 | 伺服器 CPU／GPU | 環境建置中（SSH 暫時連不上） |
| Qwen3-VL-8B 設計要素標註 → `full_concept_vlm` | V100 fp16 | 腳本已寫好，還沒在 GPU 上跑 |
| Qwen3-VL-Reranker 2B／8B 延遲與 T1 | V100 fp16 | 還沒跑 |
| 肩線／霧面／領型／logo 人工標 40 件 → AUROC | 組員 1 小時 | 還沒做 |
| M3 感性對照表：GPT 多次取樣填值，意見分歧的格子交人工 | OpenAI key | 還沒做 |
| LLM 改寫的事實檢查實測 | OpenAI key | 程式與單元測試已完成 |
| 價格欄位 | 需要贊助商資料，或明確標示為合成 | 目前一律 null |

相關文件：`docs/engine02-literature-review.md`（文獻對照）、`docs/research/engine02-method-inventory.md`（方法清單）、`docs/research/industry-fashion-brands.md`（業界採用）、`docs/research/catalog-options.md`（資料集）、`reports/model_verification.md`（模型實測）。
