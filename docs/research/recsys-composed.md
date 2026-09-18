# T8｜針對已推薦商品的批評回饋：組合式檢索（「這件但換成深藍色／更正式」）

> 作者：sub-agent `composed`，2026-09-17，分支 `engine02-research`。
> 程式：`engine02/composed.py`、`tests/test_composed.py`（5 項全過，HashEncoder）、`scripts/eval_composed.py`、`scripts/eval_composed_posthoc.py`。
> 原始結果：本機 `reports/agents/composed/<catalog>_<encoder>/`（不進 git），nycu `/tmp/neil/agents/composed/out/`。

## 1. 一句話結論

評審說「這件但換成 X」時，**不要只加硬條件**（現行做法），改用 **`image_plus_text_filter` 經 pipeline 的 BM25 RRF**：
在「新屬性值」硬過濾內，以「改寫後的標題」文字向量＋BM25 做 RRF，參考圖權重 α=0（依 NDCG 選）或 α=0.3–0.5（依「最像原商品」選）。
44k 上 NDCG@10 0.347 → **0.610**（p<0.001），Hit@10 0.535 → 0.848，其他屬性保留率 0.535 → 0.825，延遲 68 → 87 ms。

## 2. 方法（全部 training-free、不需 LLM）

| 方法 | 做法 | 文獻 |
|---|---|---|
| `critique_filter` | 把 color／occasion 設成硬條件，文字查詢維持原本的 base query（`{gender} {subcategory}`），跑 pipeline `full` arm | 現行系統；批評式推薦（Wu et al. RecSys 2019） |
| `text_rewrite` | CIReVL（Karthik et al. ICLR 2024）的第 2 步，但不用 LLM：參考商品的「caption」＝catalog 標題，把舊值換成新值（occasion 則加前綴 formal／casual／sports）；純文字→圖片檢索。`text_rewrite_meta`＝用 metadata 模板 `{gender} {color} {subcategory} for {occasion}` | arXiv:2310.09291 |
| `image_plus_text` | q = norm(α·img(r) + (1−α)·txt(目標描述))；CLIP4Cir 的 element-wise sum 基線（Baldrati et al., ACM TOMM 2023, arXiv:2308.11485）。另測 target text 只用修改詞（`_mod`） | 同左 |
| `vector_arithmetic` | q = img(r) + λ·(txt("navy blue shirts") − txt("black shirts"))；潛在空間線性批評（Luo et al. WWW 2020）與 TIRG 殘差修改（Vo et al. CVPR 2019）的 embedding 版 | arXiv:1812.07119 |
| `ref_plus_filter` | 新值硬過濾內，以參考圖向量排序 | 1＋3 混合 |
| `image_plus_text_filter` | 新值硬過濾內，用 `image_plus_text` 的向量 | — |
| 選項 6（`+bm25_rrf`） | `ComposedEngine02.run_composed(req, cq, "hybrid_rrf")`：dense 用組合向量，BM25 用改寫文字，RRF 融合 | — |

LLM 介面：`LLMRewriter(llm: Callable[[str], str])` 使用 CIReVL 提示；輸出沒提到新值、或仍含舊值、或 LLM 例外時，退回 `TemplateRewriter`（`last_source` 標示 llm／template）。有 key 時直接替換 `Composer(..., rewriter=LLMRewriter(llm))`，其餘不變。**LLM 版沒有實測。**

## 3. 實驗設定

- **Catalog**：`kagl`（5k）、`kagl_full`（44k）；**encoder**：Marqo-FashionSigLIP、fashion-clip；nycu 4090。
- **Triplet**（全來自 metadata，seed 0）：服飾類參考商品 r。
  - color：換成**不同色系**的顏色（8 個色系），且這個 gender＋subcategory＋occasion＋新色至少存在 1 件
  - occasion：Casual→Formal／Sports、Formal→Casual、Sports→Casual，顏色不變
  - 每種 600 個，dev／test 各 300
- **標準答案 T**：同 gender＋subcategory＋另一屬性（color triplet 看 occasion，occasion triplet 看 color）＋新值，排除 r 本身。
  - graded NDCG：3＝T 且同季節，2＝T，1＝只有 gender＋subcategory＋新值
  - |T| 中位數：5k 為 3；44k 為 9–10
- **困難版**（「其他都不變」）：T 中和 r 圖片最相似的 top-N（N=50／5／1）。相似度用**另一個 encoder** 算，避免獎勵方法自己的向量空間。報告 `hard1_ndcg10`（單一最像目標，類似 Fashion IQ）。
- **指標**：
  - Hit@5／10（CIR 文獻的 Recall@K）、集合 Recall@10、NDCG@10
  - `preservation5`：前 5 名保留 r 另一屬性的比例
  - `change5`：前 5 名具新值的比例
  - `vis_sim5`：前 5 名和 r 的圖片相似度（另一 encoder）
- **α／λ**：α 網格 {0,…,0.3,0.5,0.7,1}（靠近 0 取得較密，因為圖－圖 cosine 遠大於文－圖）；λ 網格 {0,…,64}。在 dev 以 NDCG@10 選一組、以 hard1_ndcg10 另選一組，test 只報告選定值。
- **統計**：test 300×2 個 triplet 做配對置換檢定（10,000 次）；bootstrap 95% CI。

## 4. 結果（test，n=600，兩種變體合併；[95% CI]；p 為相對 `critique_filter`）

### 4.1 44k（kagl_full）Marqo-FashionSigLIP

| 方法 | NDCG@10 | Hit@10 | hard1 NDCG@10 | 保留率@5 | 新值@5 |
|---|---|---|---|---|---|
| critique_filter（現行） | 0.347 [0.32,0.37] | 0.535 | 0.106 | 0.535 | 0.686 |
| text_rewrite | 0.225（p<0.001，更差） | 0.583 | 0.140 | 0.813 | 0.274 |
| text_rewrite_meta | 0.367（p=0.22） | 0.763 | 0.148 | 0.885 | 0.446 |
| text_rewrite+bm25_rrf | 0.298 | 0.618 | 0.195 | 0.855 | 0.314 |
| ref_plus_filter | 0.497 | 0.735 | **0.446** | 0.635 | **0.786** |
| **image_plus_text_filter+bm25_rrf α=0** | **0.610 [0.59,0.64]** p<0.001 | **0.848** | 0.360 | 0.825 | 0.737 |
| image_plus_text_filter+bm25_rrf α=0.5 | 0.539 p<0.001 | 0.787 | 0.393 | 0.791 | 0.712 |

- fashion-clip（44k）幾乎相同：critique_filter 0.348 → hybrid α=0 **0.609**（p<0.001），Hit@10 0.557 → 0.853。
- 5k 結論同方向：Marqo 0.273 → 0.591，fashion-clip 0.284 → 0.590，p 都 <0.001。
- `vector_arithmetic` 在 dev 需要 λ≈16–64，文字方向才壓得過圖片。test NDCG 0.40–0.45，保留率掉到 0.55–0.64（圖片被推離原樣），**不建議**。
- `image_plus_text`（不加過濾）在 dev 選到的 α 一律是 0，也就是參考圖在沒有過濾時只會拉回原色／原場合。

### 4.2 為什麼現行做法差：放寬階梯把批評吃掉了

- `critique_filter` 走 pipeline 時，gender＋subcategory＋新值不足 `min_results=5` 件，放寬階梯就會把剛加上的條件拿掉：
  - 44k：color 46%、occasion 21% 被放寬
  - 5k：70%／35%
- 只看**沒被放寬**的 400 個 triplet（44k Marqo），現行做法還是輸：
  - NDCG@10：0.488 vs hybrid 0.727（p<0.001）
  - Hit@10：0.735 vs 0.975
  - 保留率：0.455 vs 0.787
- 原因是 base query 完全沒用到參考商品。occasion triplet 的前 5 名中，只有 17–19% 還保留原顏色。

### 4.3 「保持其他不變」的取捨

- 在沒被放寬的子集，α=0.5 的 hard1 NDCG 為 0.471，高於 α=0 的 0.351（p<0.001），NDCG 只從 0.727 降到 0.704。
- 全體合併：
  - Marqo 44k：α=0.5 使 hard1 NDCG 0.360 → 0.393（p=0.006），NDCG 0.610 → 0.539（p<0.001）
  - 5k：hard1 差異不顯著（p=0.46–0.76）
- `ref_plus_filter` 的 hard1 最高（0.446），但保留率 0.635、NDCG 0.497。

### 4.4 延遲（44k，4090 文字編碼＋伺服器 CPU，中位數／查詢）

| 路徑 | ms |
|---|---|
| critique_filter（pipeline full） | 68 |
| text_rewrite／image_plus_text（快速路徑：編碼＋過濾＋點積） | 35 |
| image_plus_text_filter（快速路徑） | 65 |
| **image_plus_text_filter+bm25_rrf（pipeline）** | **87** |

5k 上對應數字是 29 ms vs 18 ms。

## 5. 誠實的限制

1. **標準答案是 metadata 代理**。標題中常有同款不同色（KAGL 同系列標題幾乎相同），所以 title 改寫＋BM25 會吃到「同系列」訊號。這在實際 catalog 裡是合理的，但換到標題不規則的商品庫會高估。
2. **困難版**的相似度用另一個 encoder，兩個時尚 CLIP 仍可能共享偏差。
3. **occasion 不在 catalog 文字欄位**，BM25 幫不上 occasion 的批評，只能靠硬過濾。
4. **triplet 是規則產生的**（評審真實語句需要 ENGINE 01 轉成結構化批評），不是真人回饋。LLM 改寫沒有實測。
5. α 在 NDCG 與「最像原圖」兩個目標之間有取捨，要看 demo 重視哪一個。

## 6. 建議預設與整合 hook（給 coordinator）

- **Demo 預設**：`image_plus_text_filter` + `hybrid_rrf`，α=0.3（兩個目標之間的折衷；有顯著差異的是 α=0 與 α=0.5 兩端）。
- **放寬規則**：批評產生的條件**不要**進放寬階梯；只有 pool 為 0 時才放寬，並在理由中說明。

**Contract（提議，`contracts.FeedbackState`）**：
```python
class Critique(BaseModel):
    attribute: Literal["color", "occasion", "category", "season"]
    to_value: str | None = None            # 商品庫詞彙，如 "Navy Blue"
    from_value: str | None = None          # 省略時取參考商品的值
    direction: Literal["more_formal", "more_casual", "sportier"] | None = None
FeedbackState.reference_item_id: str | None = None
FeedbackState.critique: Critique | None = None
```

**Pipeline hook**（目前以 subclass 實作，不改 pipeline.py）：
- 當 `reference_item_id` 與 `critique` 都有值時，`Engine02.run` 開頭呼叫 `Composer.compose(ref_pos, critique, base_text, "image_plus_text_filter", alpha=0.3)`，再做三件事：
  1. `retrieval_text ← cq.retrieval_text`
  2. `query_embedding()` 回傳 `cq.query_embedding`，取代 Rocchio 的文字向量
  3. `cq.constraint_updates` 寫進 constraints，並標記為「批評」，不在 ladder 中放寬（`min_results` 對這些 slot 設 1）；排除參考商品。
- 等價的現成呼叫：`ComposedEngine02(...).run_composed(req, cq, "hybrid_rrf")`。
