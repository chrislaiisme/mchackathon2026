# 推薦清單多樣化（T9）與整套穿搭推薦（complete-the-look）

> 作者：sub-agent `slate`，2026-09-17，分支 `engine02-research`。
> 程式：`engine02/diversify.py`、`engine02/complete_look.py`；測試：`tests/test_slate.py`（12 項，本機 HashEncoder 全過）；
> 實驗腳本：`scripts/eval_slate.py`、`scripts/eval_complete_look.py`（nycu，RTX 4090）。
> 原始結果：本機 `reports/agents/slate/{t9_kagl,t9_kagl_full,complete_look}/`（不進 git）。
> **沒有修改任何既有檔案**；整合需要的掛鉤列在 §3。

---

## 0. 一頁結論

| 決定 | 依據 |
|---|---|
| 多樣化預設用 **DPP（fast greedy MAP），θ=0.9，只在前 20 名候選內重排** | 近似重複（兩張卡圖片 cosine>0.95）的比例：44k 從 2.45% 降到 0.35%（差值 95% CI [−3.1, −1.2] 個百分點），5k 從 1.66% 降到 1.01%；NDCG@5 的變化 44k −0.005 [−0.014, 0.003]、5k +0.003 [−0.002, 0.008]，**都不顯著** |
| 保守的替代選項：MMR λ=0.6 | 兩個商品庫的 NDCG@5 都沒有下降（+0.004／+0.001），但近似重複只降到 1.41%／1.80% |
| xQuAD（以隱性需求為 aspect）**不當預設** | 需求覆蓋 α-NDCG 提升很多（λ=0.3：+0.08／+0.06，p<0.001），但它直接最佳化的就是這個自己定義的指標；NDCG@5 λ≥0.3 就顯著下降（−0.011／−0.008），圖片多樣性幾乎沒變 |
| **θ≤0.7／λ≤0.3 開始顯著犧牲品質** | DPP θ=0.7：NDCG −0.015（5k）／−0.012（44k），p<0.05；θ=0.5：−0.044／−0.040 |
| 解釋保持忠實 | 20 句查詢 × 3 種方法 × 5 張卡共 300 張卡（兩個商品庫各一次）：分數加總 = 總分、沒被提前的卡其引用理由單獨就能贏過相關度第 6 名、被提前的卡第一條理由是「為了多樣性而納入」→ **300/300、300/300 通過** |
| 整套穿搭的單品排序預設用 **OutfitTransformer 的互補檢索頭（`ot_cir`）** | 500 題、100 選 1：MRR 0.277，R@10 0.530；相容性頭（`ot`）0.216／0.466；圖片相似度 0.185／0.346；隨機 0.057／0.118。`ot_cir` 相對 `ot` 的 MRR +0.061 [0.037, 0.086]，p<0.001 |
| **不要**把 OT 和相似度混合 | 在 dev 選出權重 w=1 後，混合版的 MRR 0.201，比單用 OT 還低（−0.015，p=0.25；R@5 −0.044，p=0.045） |
| 品類選擇（先選品類）用 NPMI 可以，但**沒有比「最熱門的品類」好** | 前 2 名命中率：NPMI 80.0% [76.9, 83.1]、熱門度 78.6%、隨機 56.0%；NPMI 相對熱門度 p=0.45 |

---

## 1. 目標 A：推薦清單多樣化

### 1.1 方法（`engine02/diversify.py`）

三種方法都只在 additive reranker 已經打過分的**前 `depth`=20 名候選裡重新挑 k=5 件**，不會加入新商品，也不改任何商品的分數或 contributions。

| 方法 | 選下一件的準則 | 參數（等於純相關度的值） | 文獻 |
|---|---|---|---|
| MMR | λ·rel(i) − (1−λ)·max_{j∈S} cos(i,j) | λ（1） | Carbonell & Goldstein, SIGIR 1998；直接重用 `fusion.mmr` |
| DPP | θ·r_i + (1−θ)·log d_i² | θ（1） | Chen, Zhang & Zhou, NeurIPS 2018（arXiv 1709.05135）Algorithm 1 加上 Eq.(13) 的取捨參數；YouTube 上線：Wilhelm et al., CIKM 2018 |
| xQuAD | (1−λ)·rel(i) + λ·Σ_n P(n)·P(i\|n)·Π_{j∈S}(1−P(j\|n)) | λ（0） | Santos, Macdonald & Ounis, WWW 2010 |

各方法的輸入定義：
- **rel**：pipeline 的總分 S(i)，在候選內做 min-max 正規化。
- **DPP**：
  - 相似度 S_ij = (1+cos_ij)/2，cos 用 Marqo-FashionSigLIP 圖片 embedding。這是論文 §6 用來確保 S 半正定且落在 [0,1] 的映射。
  - d_i² 是增量 Cholesky 的殘差。
  - 單元測試確認結果和暴力計算 log det 的貪婪法完全一致。
- **xQuAD**：
  - aspect = 使用者 p(n) 最高的 3 個需求，P(n) 依 p(n) 正規化。
  - P(i|n) = max(0, share_n(i)) / 候選中最大的 share_n。
  - share_n(i) = Σ_d γ·p(n)·K[n,d]·c(i,d)，也就是 `RankedItem.need_contributions[n]`。

**忠實解釋的做法**：`run_diversified` 包在 `Engine02.run` 外面，是後處理，不需要改 pipeline。
1. 先用 `deep_request` 請 pipeline 回傳前 depth+1 名；這一輪關掉 LLM 和反事實計算。
2. 挑出 k 件後，每張卡片 `DiversifiedRankedItem` 多出下列欄位：
   - `relevance_rank`：純相關度的名次。
   - `promoted_by_diversity`：`relevance_rank > k`。
   - `max_similarity_to_higher`：和排在它前面的卡片的最高圖片相似度。
   - `new_aspects`：xQuAD 新覆蓋到的需求。
3. **沒有被提前的卡**：用「相關度第 k+1 名的總分」當門檻，重新計算最小充分集合（直接呼叫 `rerank.cutoff_explanations`），保證和原本 pipeline 一樣：引用的理由單獨就足以讓它進入相關度前 k 名。
4. **被提前的卡**：純相關度的理由本來就不足以讓它進榜，所以 `sufficient` 一律 False。第一條理由固定是「為了多樣性而納入（純相關度排第 N 名，和前面卡片的最高圖片相似度 x.xx［，補上需求「…」］）」，後面列出它最強的 3 個正向項，當作優點。
5. `response.diversification` 記錄 `promoted` 和 `displaced`。`displaced` 列出被擠掉的相關度前 k 名商品、和它最像的已顯示商品，以及兩者的 cosine，所以「因為和 X 太像才被拿掉」這句話可以驗證。

### 1.2 實驗設定（T9）

- **資料與模型**：nycu，Marqo-FashionSigLIP；KAGL 5k（199 句查詢，1 句過濾後候選不足 6 件被略過）和 KAGL 44k（200 句）。
- **查詢**：`eval.tasks.make_queries(n=200, seed=0)`，和 T1／T6 同一族，用詞和商品庫一致；硬過濾品類＋性別；每句隨機給 3 個需求機率（seed 0）；arm `full`，`n_candidates=50`，depth 20，k=5。
- **標準答案**：NDCG@5 的等級和 T1 相同（子類＋顏色＋性別＋場合全對 3，子類＋顏色 2，子類 1），來自資料集屬性，是**代理指標**。
- **統計**：每句查詢和「不多樣化」配對，做配對置換檢定（10,000 次）與 bootstrap 95% CI。
- **其他指標的限制**：
  - **ILD@5 = 1 − 平均兩兩圖片 cosine**：用的是 MMR／DPP 最佳化時的同一個 embedding 空間，**有自我參照**。
  - **不同子類數／顏色數**：來自資料集屬性，和 embedding 無關。但品類和性別已經硬過濾，子類本來就很難分散，所以上限很低。
  - **近似重複率**：前 5 名的 10 組配對中，cosine>0.95 的比例。
  - **α-NDCG@5**（α=0.5，依 P(n) 加權；判定 J(i,n)=1 ⇔ P(i|n)≥0.5）：用我們自己的 K 表和 c(i,d) 算，xQuAD 直接最佳化它，**只能當作「需求覆蓋有被改變」的證據，不能當作「使用者覺得更多元」的證據**。
- **一致性檢查**：
  - 前 20 句查詢中，`diversify` 的 MMR（λ=0.7，depth 20）和 pipeline 既有 arm `full_mmr` 的結果：**20/20、20/20 完全一致**。
  - `full_mmr` 這個 arm 過去從未評估過，本實驗等於補上它的數字：5k NDCG +0.002（p=0.35），44k +0.001（p=0.76）；近似重複 1.66→1.51%、2.45→2.00%。

### 1.3 結果（Δ 相對不多樣化；[ ] 為 95% bootstrap CI；p 為配對置換檢定）

不多樣化的基準：5k NDCG@5 0.820、ILD 0.244、近似重複 1.66%、α-NDCG 0.610；44k 0.808、0.236、2.45%、0.692。

**KAGL 5k（199 句）**

| 設定 | ΔNDCG@5 | p | ΔILD | Δ子類數 | 近似重複 | Δα-NDCG | 被提前的卡 |
|---|---|---|---|---|---|---|---|
| MMR λ=0.7（`full_mmr`） | +0.002 [−0.002, 0.005] | 0.35 | +0.007 | +0.04 | 1.51% | +0.001 | 4.0% |
| MMR λ=0.6 | +0.004 [−0.001, 0.009] | 0.14 | +0.012 | +0.07 | 1.41% | +0.006 | 7.4% |
| MMR λ=0.5 | +0.001 [−0.005, 0.007] | 0.76 | +0.018 | +0.08 | 1.26% | +0.009 | 10.3% |
| MMR λ=0.3 | **−0.020** [−0.032, −0.008] | 0.001 | +0.042 | +0.15 | 0.45% | +0.033 | 21.0% |
| **DPP θ=0.9** | +0.003 [−0.002, 0.008] | 0.25 | +0.012 | +0.05 | **1.01%** | +0.005 | 6.6% |
| DPP θ=0.8 | −0.004 [−0.012, 0.003] | 0.30 | +0.024 | +0.08 | 0.45% | +0.011 | 13.3% |
| DPP θ=0.7 | **−0.015** [−0.026, −0.004] | 0.008 | +0.039 | +0.13 | 0.10% | +0.024 | 20.1% |
| DPP θ=0.5 | **−0.044** [−0.061, −0.029] | <0.001 | +0.066 | +0.21 | 0% | +0.041 | 33.6% |
| xQuAD λ=0.1 | −0.001 [−0.004, 0.002] | 0.51 | +0.001 | +0.01 | 1.66% | +0.020 | 1.1% |
| xQuAD λ=0.3 | **−0.011** [−0.018, −0.004] | <0.001 | +0.003 | +0.04 | 1.61% | +0.080 | 4.2% |
| xQuAD λ=0.5 | **−0.044** [−0.058, −0.032] | <0.001 | +0.006 | +0.08 | 1.61% | +0.158 | 6.9% |

**KAGL 44k（200 句）**

| 設定 | ΔNDCG@5 | p | ΔILD | Δ子類數 | 近似重複 | Δα-NDCG | 被提前的卡 |
|---|---|---|---|---|---|---|---|
| MMR λ=0.7（`full_mmr`） | +0.001 [−0.004, 0.005] | 0.76 | +0.006 | −0.01 | 2.00% | +0.002 | 4.1% |
| MMR λ=0.6 | +0.001 [−0.004, 0.007] | 0.65 | +0.010 | 0 | 1.80% | +0.003 | 6.5% |
| MMR λ=0.5 | −0.003 [−0.010, 0.004] | 0.38 | +0.015 | +0.04 | 1.75% | +0.007 | 9.8% |
| MMR λ=0.3 | **−0.014** [−0.025, −0.002] | 0.019 | +0.033 | +0.09 | 0.85% | +0.014 | 19.3% |
| DPP θ=0.95 | −0.006 [−0.014, 0.002] | 0.15 | +0.009 | 0 | 0.45% | +0.004 | 5.8% |
| **DPP θ=0.9** | −0.005 [−0.014, 0.003] | 0.22 | +0.014 | 0 | **0.35%** | +0.004 | 8.9% |
| DPP θ=0.8 | −0.008 [−0.019, 0.002] | 0.10 | +0.024 | +0.04 | 0.20% | +0.010 | 14.5% |
| DPP θ=0.7 | **−0.012** [−0.024, −0.001] | 0.043 | +0.036 | +0.08 | 0.05% | +0.012 | 20.7% |
| DPP θ=0.5 | **−0.040** [−0.056, −0.023] | <0.001 | +0.060 | +0.17 | 0% | +0.020 | 33.0% |
| xQuAD λ=0.1 | **−0.002** [−0.003, −0.000] | 0.019 | +0.000 | +0.01 | 2.40% | +0.016 | 0.7% |
| xQuAD λ=0.3 | **−0.008** [−0.014, −0.004] | 0.002 | +0.001 | +0.02 | 2.35% | +0.062 | 3.1% |
| xQuAD λ=0.5 | **−0.027** [−0.036, −0.017] | <0.001 | +0.004 | +0.06 | 2.35% | +0.128 | 6.2% |

- 完整的取捨曲線（MMR λ 0.9–0.1、DPP θ 0.95–0.1、xQuAD λ 0.1–0.9）在 `reports/agents/slate/t9_*/summary.csv`。
- **延遲**：每次重排 0.1–0.25 ms（20 件候選，伺服器 CPU），可以忽略。

### 1.4 解讀（照實說）

1. **「前 5 名是五件幾乎一樣的衣服」在這兩個商品庫其實不嚴重**：
   - 不多樣化時，平均兩兩 cosine 約 0.76；近似重複的配對只有 1.7%（5k）／2.5%（44k）。
   - 商品庫越大，重複越多。KAGL 常見同款不同色，也有幾乎相同的商品照。
2. **DPP 對「真正的重複」最有效**：同樣只提前約 7–9% 的卡片，DPP θ=0.9 在 44k 把近似重複降到原本的 1/7（2.45→0.35%）。MMR λ=0.6 只降到 1.80%，因為 MMR 只看和已選商品的**最大**相似度，而 min-max 後的相關度差距通常比 cosine 差距大，所以它很少真的拿掉一件重複商品。
3. **屬性層級的多樣性（子類、顏色）幾乎沒變**：品類和性別已經硬過濾，而且查詢指定了子類和顏色。NDCG 的等級就是獎勵「同子類同顏色」，多樣化和這個代理指標本質上衝突。所以 θ≤0.7 的 NDCG 下降，一部分是指標本身的偏差，**不能直接等同於使用者覺得變差**，但也不能宣稱變好。
4. **xQuAD 的需求覆蓋提升是自我參照的**：J(i,n) 和 xQuAD 的 P(i|n) 是同一個量。它讓前 5 名同時照顧到 3 個需求，但需要真人或模擬使用者研究來證明這件事有價值。目前看到的是：xQuAD 付出的 NDCG 代價比 DPP 大，圖片多樣性卻幾乎沒有增加。
5. **建議預設 DPP θ=0.9，depth=20**：兩個規模的 NDCG 變化都不顯著，近似重複顯著下降（CI 不含 0）。卡片上約每 12 張有 1 張會標示「為了多樣性而納入」。如果 demo 更在意「NDCG 絕對不能降」，就用 MMR λ=0.6。

---

## 2. 目標 B：整套穿搭推薦（給一件，推薦能搭的）

### 2.1 方法（`engine02/complete_look.py`）

先選品類，再選單品（type-then-item），做法參考 Amazon P-Companion（Hao et al., CIKM 2020, doi 10.1145/3340531.3412732）。

1. **選品類**：`rank_categories` 對每個不屬於錨點品類的服飾大類 c，算它和各錨點品類的平均 NPMI，由高到低排序，取前 `n_categories` 個。和錨點同品類的算「替代品」，一律排除。
2. **在每個品類內排序單品**：

   | 方法 | 分數 |
   |---|---|
   | `random` | 隨機（對照組） |
   | `similarity` | 和錨點的平均圖片 cosine |
   | `ot` | OutfitTransformer 相容性頭，P(相容 \| 錨點＋候選) |
   | `ot_sim` | z(ot) + w·z(similarity) |
   | `ot_cir` | OutfitTransformer 互補檢索頭（`complementary_clip_best.pth`）：−‖embed_query(錨點) − embed_item(候選)‖₂，和 repo 自己的 `3_test_complementary.py` 相同 |

   - 每件商品都附 `contributions`，加總等於 score。
   - `recommend()` 對每個品類先用圖片相似度挑出 50 件，再用選定的方法重排。
3. **`FastOutfitTransformer`**：每件商品的 CLIP item embedding 只算一次（`precompute_clip_embedding` + `use_precomputed_embedding=True`）。
   - 實測和原本逐張讀圖的路徑（`compat_ot.py` 的做法）差異為 **0.0**（16 個候選的最大絕對差）。
   - 兩個 checkpoint 的 item encoder 權重完全相同，所以共用 embedding。
   - 4090 上：每題 100 個候選約 10 ms（原本每個候選約 100 ms）；VRAM 峰值 **2.43 GB**（兩個頭一起載入）；1.4 萬件商品預先計算 embedding 花 536 秒。

### 2.2 實驗設定

- **資料**：`data/catalog/polyvore_big`，25k 件，5,804 組真實 Polyvore 穿搭。
- **題目**：有 ≥3 件服飾（top/bottom/outerwear/dress/shoes/bag）的穿搭共 2,872 組。隨機抽 650 組，每組隨機藏起 1 件服飾，其餘服飾當錨點。前 150 題當 dev（只用來選混合權重 w），後 500 題當 test。
- **候選**：藏起的那件＋99 件同大類、來自其他穿搭的隨機商品。
- **指標**：Recall@1/5/10、MRR；平手時取期望名次。
- **選品類**：前 2 名是否包含藏起商品的大類。
  - NPMI 和熱門度都**排除全部 650 組題目穿搭**後重新計算，避免洩漏。
  - 另外 6.9% 的題目，藏起商品的品類和某個錨點相同（例如兩件上衣），依設計必然答錯，也計入分母。
- **標準答案與限制**：
  - 「使用者實際穿搭中的那件」是唯一正解，但其他 99 件裡可能也有能搭的，所以數字是下限。
  - 隨機負例比真實的競品容易分辨。
  - **訓練／測試可能重疊**：OutfitTransformer 是在 Polyvore Outfits（Vasileva et al. 2018）上訓練的。這份資料是 Maryland Polyvore（Han et al. 2017），同一個網站，圖片和穿搭可能重疊，**OT 的兩個頭都可能被高估**。圖片相似度（Marqo）沒有這個問題。

### 2.3 結果（test 500 題，95% bootstrap CI）

| 方法 | MRR | R@1 | R@5 | R@10 |
|---|---|---|---|---|
| random | 0.057 [0.046, 0.069] | 1.4% | 5.2% | 11.8% |
| similarity（Marqo 圖片） | 0.185 [0.160, 0.211] | 9.6% | 24.2% | 34.6% |
| ot（相容性頭） | 0.216 [0.190, 0.242] | 10.6% | 31.6% | 46.6% |
| ot_sim（w=1，dev 選出） | 0.201 [0.175, 0.227] | 10.0% | 27.2% | 43.0% |
| **ot_cir（互補檢索頭）** | **0.277 [0.247, 0.307]** | **15.4%** | **41.0%** | **53.0%** |

配對檢定（差值 [95% CI]，p）：

| 比較 | MRR | R@1 | R@5 | R@10 |
|---|---|---|---|---|
| ot vs similarity | +0.031 [0.001, 0.060]，p=0.040 | +1.0 pp，p=0.63 | +7.4 pp，p=0.003 | +12.0 pp，p<0.001 |
| ot_cir vs ot | +0.061 [0.037, 0.086]，p<0.001 | +4.8 pp，p=0.003 | +9.4 pp，p<0.001 | +6.4 pp，p=0.004 |
| ot_cir vs similarity | +0.092 [0.060, 0.124]，p<0.001 | +5.8 pp，p=0.002 | +16.8 pp，p<0.001 | +18.4 pp，p<0.001 |
| ot_sim vs ot | −0.015 [−0.040, 0.010]，p=0.25 | −0.6 pp，p=0.80 | −4.4 pp，p=0.045 | −3.6 pp，p=0.10 |

- 混合權重掃描（test 上的 MRR）：w=0.25 0.210、0.5 0.206、1 0.201、2 0.201，**全部低於單用 OT**。
- **選品類**（650 題）：

  | 方法 | 前 2 名命中率 |
  |---|---|
  | NPMI | 80.0% [76.9, 83.1] |
  | 熱門度 | 78.6% [75.5, 81.7] |
  | 隨機 | 56.0% |

  - NPMI 的前 1 名命中率是 55.7%。NPMI 相對熱門度 p=0.45。
  - 排除「藏起的品類已經在錨點裡」的題目後，NPMI 85.9%、熱門度 84.5%。
  - 依藏起的品類分：鞋 93%、外套 82%、包 79%、下身 76%、上衣 71%、洋裝 66%。

### 2.4 解讀

1. **商品層級相容性確實有用**：100 選 1 時，相容性頭的 R@10 比圖片相似度高 12 個百分點（p<0.001），和先前 FITB 4 選 1 的 54.5% vs 48%（當時不顯著）方向一致，而且這次題數多、候選多，差異變顯著。
2. **互補檢索頭（`ot_cir`）比相容性頭更好**：它就是為「給穿搭、找缺的那件」訓練的。先前 FITB 只測了相容性頭，**建議 pipeline 的錨點相容項改用它**。要注意 `ot_cir` 輸出的是距離，應該在候選池內做 z-score 後再加權。
3. **加入相似度會變差**：「和錨點長得像」不等於「能搭」，例如黑褲配黑上衣不一定是好穿搭。
4. **選品類時 NPMI 沒有比熱門度好**：Polyvore 穿搭裡鞋和包幾乎每套都有，熱門度本身就很強。NPMI 的價值在於排除明顯不合理的組合（例如洋裝配下身），但這個測驗量不到這一點。
5. **OT 的數字可能偏高**（訓練資料可能重疊），簡報上要註明。圖片相似度 0.185 的 MRR 是沒有洩漏疑慮的下限。

---

## 3. 整合掛鉤（交給 coordinator）

### 3.1 多樣化（不改 pipeline 也能用）

```python
from engine02.diversify import DiversityConfig, run_diversified
resp = run_diversified(engine, req, arm="full", cfg=DiversityConfig("dpp", 0.9, depth=20))
# resp.items[i].promoted_by_diversity / relevance_rank / max_similarity_to_higher / new_aspects
# resp.diversification = {method, param, depth, aspects, promoted[], displaced[{item_id, relevance_rank, most_similar_shown, cosine}]}
```

如果要併進 `config.py`／`pipeline.py`，建議的做法：
1. `ArmConfig` 新增 `diversify: str = "none"`、`diversify_param: float = 1.0`、`diversify_depth: int = 20`。新增 arm：`full_dpp = replace(FULL, name="full_dpp", diversify="dpp", diversify_param=0.9)`，保留 `full_mmr`，另加 `full_xquad`（λ=0.3）。**預設 `full` 建議改成 dpp 0.9**，或先以 `full_dpp` 的形式上 demo。
2. `Engine02.run` 中 `if arm.use_mmr` 那段（`pipeline.py` 約第 193–197 行）換成 `diversify.select(...)`；理由判定改用 §1.1 的規則：沒被提前的卡，用相關度第 k+1 名當門檻算 `cutoff_explanations`；被提前的卡加一條多樣化理由。最簡單的方式是直接呼叫 `diversify_response`。
3. `contracts.py` 的 `RankedItem` 新增 `relevance_rank: int | None`、`promoted_by_diversity: bool = False`；`Engine02Response` 新增 `diversification: dict | None`。`DiversifiedRankedItem`／`DiversifiedResponse` 已經是這個形狀的 subclass，JSON 相容。
4. 前端：`promoted_by_diversity=True` 的卡片，第一條理由顯示「為了多樣性而納入」，不要把後面的優點講成「因為這些才推薦」。

### 3.2 `POST /complete-look`（提議規格）

Request：
```json
{
  "anchor_item_ids": ["180419624_2"],
  "n_categories": 2,
  "categories": null,
  "k": 5,
  "method": "ot_cir",
  "prefilter": 50,
  "filters": {"gender": ["Women"]},
  "exclude_item_ids": []
}
```

Response：
```json
{
  "anchors": [{"item_id": "...", "category": "top"}],
  "slates": [
    {"category": "bottom", "category_score": 0.21,
     "items": [{"item_id": "...", "score": -0.83, "rank": 1,
                "contributions": {"complementary:outfit-transformer": -0.83}}]}
  ],
  "method": "ot_cir",
  "cooccurrence_source": "data/catalog/polyvore/category_cooccurrence.json"
}
```

實作方式：
```python
ot = FastOutfitTransformer(catalog, heads=("compatibility", "complementary"), cache_file=cache_dir / "ot_item_emb.npz")
ctl = CompleteTheLook(catalog, engine.image_emb, cooc, ot=ot)
ctl.recommend(anchor_ids, n_categories, k, method, prefilter, exclude_ids, filters, categories)
```

- **啟動時**先對整個商品庫跑 `ot.ensure_embeddings(range(len(catalog)))` 再 `save_cache()`。25k 件約 15 分鐘，只需要做一次。
- **沒有 GPU 時**退回 `method="similarity"`。

同一個 `FastOutfitTransformer` 也符合 pipeline 的 `compat_model.score(anchors, cands)` 介面（相容性頭），可以直接取代 `OutfitTransformerCompat`，每題 100 個候選從約 10 秒降到約 10 ms。如果要改用互補檢索頭，需要新增 `score = ot.complementary(...)` 的 adapter，並設 `normalize=True`，讓它用 z-score。

## 4. 重現方式

```bash
# nycu，工作目錄 /tmp/neil/agents/slate/repo（資料透過 symlink）
python scripts/eval_slate.py --catalog data/catalog/kagl      --cache-dir <index_kagl>      --n-queries 200 --out out/t9_kagl
python scripts/eval_slate.py --catalog data/catalog/kagl_full --cache-dir <index_kagl_full> --n-queries 200 --out out/t9_kagl_full
python scripts/eval_complete_look.py --catalog data/catalog/polyvore_big --emb <img_marqo-fashionSigLIP.npy> --n-dev 150 --n-test 500 --batch 48 --out out/complete_look
```

所有 seed 固定為 0。本機測試：`.venv/Scripts/python.exe -m pytest -q tests/test_slate.py`。
