# ENGINE 02｜檢索、排序與可驗證解釋 — 設計與實驗報告

> 狀態：2026-09-17，分支 `engine02-research`。程式在 `engine02/`，測試 `tests/`（15 項全過），實驗腳本 `scripts/run_ablation.py`。
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
| 在卡片內 z-score 改成**用整個過濾後商品池的統計量**標準化 | 候選數量改變時，理由不會跟著變（method inventory §11） |
| 穿搭相容性**只在有錨點商品時才啟用** | 文獻中所有相容性任務都需要錨點；T 測試：沒錨點時不會出現 compat 項 |
| 回饋：批評回饋效果大，Rocchio **尚未證明有效** | T5：4 輪成功率 1–2% → 39–44%（p<0.001）；Rocchio 相對只用批評多 3 個百分點，p≈0.54–0.60，**不顯著** |
| 推薦理由**預設用模板**，LLM 改寫要通過程式事實檢查 | 本地 Qwen3-1.7B 實測會把「盛夏偏熱」講反；有 OpenAI key 時才開改寫 |
| 圖文 reranker（Qwen3-VL-Reranker-2B）**只在 GPU 上開** | CPU 上每個 pair 要 21.6 秒 |

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
  │          + w_compat·NPMI(類別, 錨點類別)     ← 只在有錨點時
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

### 3.6 還沒跑的對照組
- `full_concept_vlm`：Qwen3-VL 標註出的設計要素，需要 GPU（`scripts/vlm_tag_attributes.py`）。
- `full_cross_reranker`：Qwen3-VL-Reranker-2B／8B，需要 GPU。
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
  - `POST /rank`：主要排序
  - `GET /vocabulary`：ENGINE 01 正規化要用的商品庫詞彙
  - `GET /kansei`：need 與 design element 的 id
  - `GET /items/{id}`、`GET /images/{id}`：商品資料與圖片
  - `GET /arms`、`GET /health`
- **規格檔**：`docs/contract/`，含 request／response 的 JSON Schema，以及第 1、2 輪的範例 request／response；範例是 ENGINE 03 把「太像上班族，不要黑色＋點選第 3 件」轉成回饋之後的真實輸出。
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
