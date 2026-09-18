# ENGINE 02 現況總覽：一次看完整條 Pipeline

這份文件只回答三個問題：**一句話進來後發生什麼事**、**每一步為什麼是這樣做的**、**現場 demo 會不會卡**。
實驗細節與統計在 `docs/engine02-design.md`（§3 共 21 組實驗），方法盤點在 `docs/research/`。

---

## 0. 三十秒版本

```
ENGINE 01 的 JSON
   │  硬條件（品類/顏色/性別/場合/季節/預算）＋隱性需求機率＋一句英文 retrieval_text
   ▼
① 硬條件過濾（不進分數）───放寬階梯（順序固定、會寫進理由）
   ▼  候選池
② 混合檢索：BM25（postings）＋ dense（Marqo-FashionSigLIP）→ RRF／凸組合
   ▼  候選
③ 可加總重排：S(i) = Σ 每一項的貢獻   ← 這些貢獻「就是」解釋，不是事後生成
   │   w·z(dense) + w·z(bm25) + Σ_d β_d·c(i,d) [+ 相容性] [− 否決懲罰] [− 看過未選]
   ▼
④ 理由 = 最小充分集合（拿掉就掉出前 k 的最小組合）＋ 資料來源標註
   ▼
⑤ 多樣化（DPP）→ 前 k 張卡
   ▼
ENGINE 03 的 JSON（分數分解、需求貢獻、規則指標、輸入警告）
```

**設計上唯一不妥協的事**：卡片上每一句理由都對應分數分解裡的一項，且所有項加總**剛好等於**總分
（`tests/test_engine02.py::test_contributions_sum_to_score`）。沒有「事後解釋模型」。

---

## 1. 逐階段

| # | 階段 | 程式 | 進 / 出 | 關鍵決策與依據 |
|---|---|---|---|---|
| ① | 硬條件過濾 | `constraints.py`、`taxonomy.py`、`attrindex.py` | 全庫 → 候選池 | 硬條件**是過濾不是加分**（Taobao MGDSPR, KDD 2021；Vespa）。過濾空了就依固定階梯放寬（顏色 allow_unknown → 季節 → 場合 → 丟季節 → 丟場合 → 預算 ×1.2 → 丟顏色 → 丟預算），**品類與性別永不放寬**，放寬了一定寫進理由。品類走 12/89 節點的分類體系做 L2→L1 階層放寬 |
| ② | 混合檢索 | `sparse.py`、`fusion.py`、`models.py` | 候選池 → 候選 | 詞彙一致時 BM25 幫助大、換句話說時只會加噪，所以**詞彙正規化是 ENGINE 01 的硬需求**；`retrieval_text_normalized=false` 時本輪自動只走 dense。BM25 用 postings 計分（與 rank_bm25 逐分相同，`tests/test_sparse.py`） |
| ③ | 可加總重排 | `rerank.py`、`pipeline.py::_terms`、`kansei.py` | 候選 → 分數分解 | 每一項都是 `(原始值, 權重, 貢獻)`；設計要素項 β_d 來自感性對照表 K（32 篇文獻編碼）×需求機率，c(i,d) 用反義詞成對打分（隨機字詞對照 AUROC 0.33–0.70 證明它真的在量東西）。z 標準化用**整個候選池**的統計量並截斷 ±3，否則 BM25 的長尾會壓掉其他理由 |
| ④ | 忠實理由 | `explain.py` | 分數分解 → 中文句子 | 預設**最小充分集合**（ERASER 式）：被引用的那幾項單獨就足以讓商品留在前 k。PRD 原本的「必要性」規則有 10–20% 卡片沒有任何理由。權重為負的要素寫成「避開〇〇」（極性寫反過一次，已修並有測試）。LLM 改寫要通過程式事實檢查，過不了就退回模板 |
| ⑤ | 多樣化 | `diversify.py` | 深層清單 → 前 k | DPP 快速貪婪 MAP；被多樣化推上來的卡片會標「為了多樣性而納入」並附原本排名 |
| ⑥ | 搭配推薦 | `complete_look.py` | 錨點商品 → 每品類一排 | 先用品類 NPMI 選互補品類（P-Companion, CIKM 2020 的先品類後商品），再用 OutfitTransformer**互補頭**排商品（FITB n=2000：0.660 vs 相容性頭 0.627 vs 圖片相似度 0.521） |
| ⑦ | 回饋 | `service.py`、`preference.py`、`composed.py` | 上一輪選擇 → 下一輪權重 | Bayes 成對偏好學習（κ=1 縮減，避免一次點選就暴衝）；批評式檢索（「像這件但要深藍」）把參考商品向量與必須值合成新查詢；排除永久生效 |
| ⑧ | 面板與缺口 | `panels.py` | 回應 → 畫面資料 | 「你說的 vs 你沒說的」、需求面板、Div@k、兩輪 diff、資料來源、**設計要素需求–供給缺口**（給製造商看的那一頁） |

---

## 2. 兩輪迴圈實際怎麼跑（現場評測就是這個流程）

1. **第一輪**：ENGINE 01 給 JSON → 上面 ①–⑤ → 五張卡，每張帶分數分解與理由。
2. **評審給回饋**（「太像上班族」「不要黑色」「第 3 件不錯但要休閒一點」）→ ENGINE 03 轉成固定操作集
   （`handshake.py`：`adjust(要素, ±1)`、`exclude(屬性, 值)`、`critique(參考商品, 要求)`、`choose/reject`）。
3. **第二輪**：
   - 排除進 `excluded_values`（**放寬階梯永不碰**），並從正向條件移除該值；
   - 點選進偏好學習 → Δβ_d（縮減後）；
   - 批評 → 合成查詢（參考商品向量 + 必須值），且**必須值不會被放寬**；
   - 負回饋分三層，**強度不同、處置也不同**：
     ①「不要這幾件」＝明確排除 → `excluded_item_ids` 硬排除，永不再出現（demo 情境 C 實測重播 0/5）；
     ②「不喜歡這種」＝明確否決 → 相似度懲罰項，推開長得像的；
     ③ 看過但沒選＝被動忽略 → 疲勞項 −0.15（服務預設，設計文件 §3.23；對照 arm `full_zclip3_nofatigue`）。
   - 回傳 `round_diff`：哪幾件留下、哪幾件換掉、哪幾條理由變了、前後三個規則指標。

**可驗證性**：三個規則指標全部用商品屬性算、不看分數——硬條件滿足率、被排除值命中數、違反回饋件數
（= 被排除值命中 + 被否決商品出現，累計所有先前輪次，兩個子項都回傳以便逐項核對）。

---

## 3. 即時性（這次新增的重點）

現場是「評審出題 → 看結果 → 給回饋 → 再出題」，所以延遲是呈現完整度的一部分。

### 3.1 實測（cfda4，V100 級 GPU，`kagl_polyvore_filled` 17,783 件，Marqo-FashionSigLIP）

| 端點 | 優化前 p50 | 現在 p50 | 現在 p95 |
|---|---|---|---|
| `POST /rank`（17,783 件） | 298 ms | **12.8 ms** | 14.1 ms |
| `POST /rank`（44,434 件全庫） | — | **15.7 ms** | 19.7 ms |
| `POST /view`（排序＋全部面板） | — | **12.5 ms** | 14.4 ms |
| `POST /complete-look`（OT 互補頭） | 554 ms | **33.3 ms** | 87.8 ms |

（以上是**服務預設 arm**、疲勞項已開啟的數字；疲勞項本身約 0.4 ms）也就是說 **/rank 快了 23 倍、/complete-look 快了 17 倍**，而且商品庫從 17.8k 換到 44k 只多 3 ms
（過濾 2.2 → 5.2 ms，其餘不變）——這代表瓶頸已經不在資料量。

`/rank` 的階段拆解（優化前 → 後）：過濾 **242 → 2.2 ms**、檢索 **44 → 4.2 ms**、理由 5.7 → **1.7 ms**、
重排 0.3 ms、反事實 0.1 ms。四個瓶頸都不是模型，而是「離線該做的事被放到線上做」：

1. `attr_source` 每列 `json.loads`（五次請求 71 萬次呼叫）→ 每個商品庫只解析一次；
2. 顏色色系視圖每次請求重建 17.8k 列副本 → 快取；
3. 槽位比對每次 `Series.map(_norm)`（每槽位 × 每放寬階梯）→ `attrindex.py` 整數碼＋布林查表；
4. 規則指標每張卡建一個 1 列 DataFrame → 全庫遮罩算一次再索引。

BM25 改成 postings 計分（rank_bm25 是「每個查詢詞掃全庫」）、dense 不再把 float32 升型複製、卡片欄位改位置索引。
**每一項都用 `scripts/check_parity.py` 驗證排序不變**：60 句查詢前 20 名 id 完全相同（最大分數差 1.3e-06）。

### 3.2 冷啟動與現場風險

| 風險 | 現況 |
|---|---|
| 第一題要付 CUDA context、分類體系載入、設計矩陣、驗證器 | API 啟動時自動跑一次暖機查詢（含一次 complete-look），`/health` 回報 `warm_ms`；`ENGINE02_WARMUP=0` 可關 |
| OT 每次請求重算候選圖片 embedding | `scripts/precompute_ot_cache.py` 預算全庫（17.8k 件 1.3 分鐘、73 MB），API 預設載入 |
| 現場沒網路而 LLM 改寫每張卡都在等 | 每次呼叫 timeout 2 秒、不重試；**每個請求共用 1.5 秒總預算**，第一次失敗後整輪改用模板；`ENGINE02_DEMO=1` 直接禁用 LLM 路徑（客戶端無法覆寫） |
| 商品庫換了但快取沒換 | 設計矩陣與圖片 embedding 的快取檔名綁 encoder／kansei 版本／concept_mode，不會誤用 |

### 3.3 降級階梯（每一層都已實作，不是計畫）

| 壞掉的東西 | 系統怎麼辦 | 使用者看到什麼 |
|---|---|---|
| LLM（沒有 key／斷網／超時） | 模板理由 | 一樣有理由，`explanation_source="template"` |
| OutfitTransformer checkpoint 缺失 | `/complete-look` 退回圖片相似度 | `/health` 的 `method` 會說是哪一種 |
| 過濾後沒有結果 | 固定順序放寬 | 「已放寬季節條件」寫在卡片上 |
| 商品缺屬性 | 校準後補值或標 unknown | 「顏色為模型判讀」 |
| 分類體系對不到該商品庫 | 退回舊的精確字串比對 | 無感，結果一致 |

---

## 4. 端點

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/rank` | 主要排序（回 `ServiceResponse`：卡片＋分數分解＋規則指標＋輸入警告） |
| POST | `/view` | 排序＋§7 全部面板（前端不要自己重算聚合值） |
| POST | `/complete-look` | 搭配推薦（品類 NPMI → OT 互補頭；分數是負距離，只在同格內可比） |
| POST | `/concept-image/nearest` | 概念圖最近商品（純展示，刻意不走 reranker） |
| POST | `/rank/plain` | 不做批評合成與多樣化的純管線（消融用） |
| GET | `/gap/elements`、`/gap/cells` | 設計要素／品類×顏色的需求–供給缺口（需求側＝本服務實際收到的查詢，回應裡會標明） |
| GET | `/needs/supply` | Sup(n)，ENGINE 03 算缺口乘積的另一半 |
| GET | `/vocabulary`、`/kansei`、`/arms` | ENGINE 01 要對齊的詞彙、需求與要素 id、消融 arm 清單 |
| GET | `/trends` | 趨勢標籤（`used_in_ranking` 永遠 false） |
| GET | `/items/{id}`、`/images/{id}`、`/health` | 商品、圖片、狀態（含載到哪些 OT 頭、暖機時間、是否 demo 模式） |

契約檔：`docs/contract/`（request／response JSON Schema＋兩輪真實範例＋ENGINE 03 操作集 schema）。

---

## 5. 模型與資料（全部可公開取得）

| 角色 | 選擇 | 授權 | 為什麼 |
|---|---|---|---|
| 圖文 encoder | **Marqo-FashionSigLIP** | Apache-2.0 | 外部四語料八個檢定全勝（p≤0.0004）；文字要轉小寫（模型卡） |
| CPU 備援 | fashion-clip | MIT | 沒 GPU 時可跑；但它在外部語料**沒有**勝過通用 LAION ViT-B/16 |
| 穿搭相容性 | owj0421/outfit-transformer（CLIP 版權重） | MIT（程式） | 互補頭最好；可能與測驗資料有圖片重疊，要講明 |
| 屬性補值 | Qwen3-VL-8B-Instruct ＋ 凍結 embedding 上的 logistic probe | Apache-2.0 | 全量 25,000 件，格式正確率 100% |
| 商品庫 | KAGL 44,434 ＋ Polyvore 服飾（合併 17,783 使用中） | 見 `docs/research/catalog-options.md` | KAGL 缺外套／洋裝／針織，用 Polyvore 補 |
| 外部評測 | Marqo fashion benchmark、Amazon ESCI、H&M caption、DeepFashion-InShop | ESCI Apache-2.0；DeepFashion／H&M 鏡像無授權標示 → **只離線評測** | 復現公布數字 18/18 落在我們 CI 內 |

---

## 6. 已經有數字的結論（節選）

| 結論 | 證據 |
|---|---|
| 可解釋性不用付排序代價 | **真人分級標註**（ESCI）：我們的可加總 rerank nDCG@10 勝過 RRF 與凸組合，四個檢定 p≤0.011 |
| 最小充分理由優於 PRD 的必要性規則 | 100% 卡片有理由、100% 充分；PRD 版 10–20% 沒理由，隨機理由只有 12–16% |
| 隱性需求維持 γ=1 | 前 5 名換掉 19–26%，NDCG@5 下降不顯著 |
| 屬性補值讓四條件查詢幾乎不必放寬 | 需要放寬的比例 92.3% → **3.8%** |
| 缺口盤真的在找缺口，不是在量目錄大小 | T14（44k，45 次試驗）：遮掉表現該要素的商品後，該要素在缺口榜的 MRR 0.381 → **0.509**（p<1e-4）；遮掉**同樣件數的隨機商品**則 0.380，與基線無異（p=1.00） |
| 趨勢關鍵字不能進排序 | 28 組設定全部變差（−0.16～−0.38 NDCG@5） |
| 概念圖融入查詢有效（w=0.2） | 模糊查詢 0.078 → 0.278，**隨機概念圖對照組無效**（−0.004, p=0.71） |
| VLM 打分沒有比 CLIP 反義詞好 | 去掉循環性標籤後 CLIP 0.982 vs VLM 0.974、顏色 0.849 vs 0.812 |
| 排序對感性表數值不敏感，但理由會變 | ±50% 擾動前 5 名仍 91% 相同；±20% 就有 51.5% 卡片換理由 |

---

## 7. 還沒完成的事（誠實清單）

| 項目 | 為什麼還沒做 | 需要誰 |
|---|---|---|
| 真人盲標與 Cohen's κ | 現有 420 筆是 **LLM 標註者**做的，所以 §3.3 的 AUROC 是模型對模型 | 組員 1–2 小時（題本已備好：`data/labels/human_tasks.csv`） |
| LLM 改寫的幻覺率 | 組員用的是 ChatGPT 介面的 agent、不是 API | 貼上式流程已備好（`reports/llm_paraphrase/paste_me.txt`，100 張卡） |
| 價格與預算條件 | 公開商品庫沒有價格 | 贊助商資料，或明確標示為合成 |
| 尺碼／合身／退貨 | 需要 SKU 層級購買與退貨紀錄，公開資料沒有 | **建議在 Q&A 主動認領**，不要假裝有 |
| 疲勞項是否該成為預設 | 剛實作，還沒跑 T5/T7 對照（novelty 應升、隱藏效用不應降） | 我，下一輪實驗 |
| 以圖搜圖（上傳照片） | 端點只收 embedding，還沒收圖檔 | 我，若時間允許 |

---

## 8. 現場啟動指令與上台前檢查清單

### 8.1 啟動（一行）

```bash
# demo 機（有 GPU）。ENGINE02_DEMO=1 = 不論前端怎麼送都不打 LLM，理由一律走模板
ENGINE02_CATALOG=data/catalog/kagl_polyvore_filled ENGINE02_ENCODER=marqo-fashionSigLIP ENGINE02_DEVICE=cuda ENGINE02_OT=1 ENGINE02_TRENDS=1 ENGINE02_DEMO=1 python -m uvicorn engine02.api:app --host 0.0.0.0 --port 8002

# 沒有 GPU 的備援機（CPU，約 1 秒/查詢，仍然完整可跑）
ENGINE02_CATALOG=data/catalog/kagl ENGINE02_ENCODER=fashion-clip ENGINE02_DEMO=1 python -m uvicorn engine02.api:app --port 8002
```

啟動會自己跑一次暖機查詢（含一次 complete-look），所以第一題不必付 CUDA context 與索引建置的成本。

### 8.2 上台前 60 秒檢查（看 `GET /health` 四個欄位）

```bash
curl -s localhost:8002/health | python -m json.tool
```

| 欄位 | 應該是什麼 | 不對的話 |
|---|---|---|
| `n_items` | 17783（合併補值庫） | 商品庫路徑錯了 |
| `complete_look.method` | `"ot_cir"` | checkpoint 沒載到 → 會退回圖片相似度（能跑，但搭配品質差） |
| `warm_ms` | 有數字（幾百 ms） | 暖機失敗 → 第一題會慢 |
| `demo_mode` | `true` | 忘了 `ENGINE02_DEMO=1` → 斷網時每張卡會等 timeout |

再跑一次完整端點驗收（15 項斷言，約 1 分鐘）：

```bash
python scripts/api_check.py --catalog data/catalog/kagl_polyvore_filled     --encoder marqo-fashionSigLIP --device cuda --ot --trends
```

### 8.3 兩件事不要在現場做

- **不要換商品庫或換 encoder**：設計矩陣與圖片 embedding 的快取綁 encoder／kansei 版本，換了就要重算（17.8k 件約 2 分鐘，44k 更久）。要換就在上台前換完並跑過 §8.2。
- **不要清 `data/catalog/*/index/`**：裡面有圖片 embedding、設計矩陣與 OutfitTransformer 的 embedding 快取（73 MB）。刪了會在評審面前重算。

---

## 9. 現場 demo 建議腳本（三段各約 30 秒）

1. **理解＋解釋**：打一句「下週面試，不想太正式但要可靠」→ 五張卡，點開任一張：「這條分數分解就是理由，
   而且加起來剛好是總分」→ 指出「你沒說但在加分的需求」那一欄。
2. **可驗證的進步**：說「太像上班族了，不要黑色，第 3 件不錯但要休閒一點」→ 第二輪並排：
   留下幾件／換掉幾件、哪幾條理由變了、三個規則指標前後對照（被排除值命中 0）。
3. **給製造商的那一頁**：切到缺口盤 →「這些需求常被問到，但目錄同時滿足的只有 X%」→
   點進 `(top, Navy Blue)` 這格 →「這一格就是一個開發提案」。收尾講延遲：`/rank` 服務端 p50 ~50 ms、
   `/complete-look` 34 ms，全部離線可跑。
