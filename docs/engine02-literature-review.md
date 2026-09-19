# ENGINE 02｜可解釋推薦：文獻對照與方案修正

> **⚠️ 先讀這段（撰寫者註明）**
>
> 《黑客松重點整理.md》裡「ENGINE 02｜檢索與排序」的方案（FashionCLIP dense＋BM25 sparse、手調權重 reranker、Polyvore 穿搭相容性、GPT 寫推薦理由、生成概念圖併入 dense 分數），**是由還沒做過相關研究的組員憑直覺寫出來的提案**，不是根據文獻或業界實證決定的架構。
>
> 本文件是對那份提案的**事後文獻檢核**：逐一確認學術界（SIGIR / KDD / CVPR / ACL / RecSys…）與業界（Amazon、Alibaba/Taobao、Pinterest、LinkedIn、Walmart、Instacart、Marqo…）是否已經做過同樣的事、做的結果如何、我們的提案哪裡天真或有誤，並給出兩天黑客松內做得到的修正版本。
>
> - 檢核日期：2026-09-16，由 6 條平行文獻搜尋線完成（嵌入模型、hybrid search、穿搭相容性、reranking／評估、可解釋性、互動式檢索）。
> - 標記：**V** = 已實際開啟論文／repo／模型卡頁面核對；**U** = 只在搜尋結果（ACM / dblp / arXiv 列表）看到標題、venue、年份，細節未逐字核對。數字請以原文為準，引用前建議再點一次連結。
> - 本文件**不是**最終架構決議，是給 ENGINE 02 負責人與全組討論 PRD 用的依據。

---

## 0. 一頁結論（TL;DR）

| 原提案 | 文獻有沒有人做過 | 判定 | 修正建議 |
|---|---|---|---|
| FashionCLIP 當 dense encoder | 有，且已被超越（Marqo 在含 Polyvore 的 6 個資料集 benchmark） | ⚠️ 過時 | 換 **Marqo-FashionSigLIP**（Apache-2.0，open_clip 一行載入）；FashionCLIP 留作消融對照 |
| Polyvore Outfits（mvasil）當商品庫 | 學術資料集 | ❌ 風險高 | HF 上是 **gated、僅限學術／非營利、需機構信箱**，作者聲明不擁有圖片版權；且**沒有**價格／顏色／季節／尺寸／場合欄位。改用 `Marqo/polyvore`（Apache-2.0）或 Han et al. 2017 版（有 price） |
| BM25＋dense「分數合併排序」 | 標準做法（Weaviate / Elastic 預設、Bruch et al. TOIS 2023） | ⚠️ 描述不足 | 分數尺度不同不能直接加：**RRF 當無調參 baseline**，另做 **per-query 正規化後的 convex combination**，α 只在 dev query 上調 |
| 顏色／價格等條件當 sparse「分數」 | Taobao MGDSPR（KDD 2021）、Vespa 都是**先過濾** | ❌ 錯誤 | 硬約束 = **filter**，軟偏好才進排序；空結果時照固定順序**放寬約束並在解釋中說明** |
| 手調權重合併 = reranker | 文獻裡這叫 score fusion，不叫 reranker | ⚠️ 名實不符 | 改稱 score fusion；真的要 rerank 用 **Qwen3-VL-Reranker-2B**（Apache-2.0、本地、圖文）或 MLLM 逐屬性驗證 top-20 |
| Polyvore 式相容性分數固定加權 | 有（OutfitTransformer、TATTOO、Loom） | ❌ 單品查詢無定義 | 所有相容性任務都需要 **anchor**（已有單品／部分穿搭）。「我想要件外套」沒有 anchor → 不啟用；有 anchor 才加相容性項 |
| GPT 根據屬性寫推薦理由 → 「所以可解釋」 | 有（LLMXRec、XRec），且文獻已指出問題 | ❌ 論證錯誤 | 有依據 ≠ 忠實（factuality ≠ faithfulness）。改為**分數分解（score decomposition）當解釋本體**，LLM 只負責改寫、程式驗證不得新增事實 |
| 生成概念圖 embedding 併入 dense 分數 | 有（BMVC 2025、VisRet、IP-CIR CVPR 2025） | ⚠️ 可能變差 | 天真 0.5/0.5 融合**比純文字還差**（62.7→61.0 mAP）；Fashion IQ 上只 +0.6 R@10。降為**可關閉的消融分支、權重 ≤0.2**，或只用於展示 |
| 回饋 → GPT 調權重 → 重跑 | 找不到支持「調手動權重」的文獻 | ⚠️ | 業界／學界做法是**改寫目標描述**（CIReVL / OSrCIR）＋**累積意圖狀態**＋**Rocchio 向量更新**（與 ENGINE 03 介面相關） |
| 「符合度 62%→89%」 | — | ❌ 循環論證 | 用同一組屬性排序再用同一組屬性打分＝只證明 filter 有效。改報「約束滿足率@5」，品質另用獨立 judge |
| 30–50 句自製 query 算 NDCG@5 | Bing / UMBRELA / Walmart 都用 LLM judge | ⚠️ 需防呆 | pooling＋人工抽驗 κ＋paired permutation test；judge 不可與排序／寫理由的模型同源 |

**一句話：** 提案的每個元件幾乎都有人做過，所以「新穎性」不在元件本身；我們能拿分的地方是把評審點名的難點——**「在約束下維持推薦品質，而不是隨便解釋」**——用「硬約束過濾＋可放寬＋分數分解解釋＋忠實度檢查」做成看得見、驗證得了的東西。

---

## 1. 嵌入模型：FashionCLIP 與其後繼者

### 1.1 文獻

| 論文 / 模型 | 單位 | Venue / 年 | 連結 | 重點 | |
|---|---|---|---|---|---|
| Contrastive language and vision learning of general fashion concepts（FashionCLIP） | Farfetch / Coveo / Bocconi | Sci. Reports 2022 | arxiv.org/abs/2204.03972 | CLIP 在約 80 萬 Farfetch 白底商品圖上微調；text→image HITS@5 0.61（CLIP 0.22）；有 typographic attack 弱點 | V |
| fashion-clip 模型卡（FashionCLIP 2.0） | patrickjohncyh | HF | huggingface.co/patrickjohncyh/fashion-clip | MIT；自述偏向**置中白底圖**、較長 query 表現較好 | V |
| Marqo-FashionCLIP / **Marqo-FashionSigLIP** | Marqo | 2024，Apache-2.0 | huggingface.co/Marqo/marqo-fashionSigLIP | GCL 在約 100 萬商品（含顏色、材質等 7 欄位）微調；6 資料集 text→image 平均 R@1 0.121 vs FashionCLIP2.0 0.077（+57%） | V |
| Generalized Contrastive Learning for Multi-Modal Retrieval and Ranking | Marqo | WWW'25 Companion | arxiv.org/abs/2404.08535 | 商品文件 = 標題與圖片 embedding **加權平均**；多欄位勝過純圖 | V |
| ZooClaw-FashionSigLIP2 | ZooClaw | arXiv 2606.27708（2026） | huggingface.co/srpone/zooclaw-fashionsiglip2 | SigLIP2 微調，作者自報小幅勝過 Marqo-FashionSigLIP | V（數字為自報） |
| SigLIP 2 | Google | arXiv 2502.14786（2025） | arxiv.org/abs/2502.14786 | 通用多語 encoder，文字上限 64 token | V |
| LookBench | Gensmo.ai 等 | arXiv 2601.14706（2026） | arxiv.org/abs/2601.14706 | 即時時尚檢索 benchmark，多數模型 R@1 < 60% | V |
| When and why VLMs behave like bags-of-words（ARO） | Stanford 等 | ICLR 2023 | arxiv.org/abs/2210.01936 | CLIP 類模型屬性—物件綁定差、忽略語序 | V |
| Vision-Language Models Do Not Understand Negation（NegBench） | MIT / OpenAI / Oxford | CVPR 2025 | arxiv.org/abs/2501.09425 | 否定句檢索接近隨機 | V |
| Long-CLIP | — | ECCV 2024 | arxiv.org/abs/2403.15378 | CLIP 77 token 上限，**有效長度 < 20 token** | V |
| Mind the Gap（modality gap） | Stanford | NeurIPS 2022 | arxiv.org/abs/2203.02053 | 圖／文 embedding 分處不同錐區，原始 cosine 不可直接比 | V |

**Polyvore 上的直接證據**（Marqo LEADERBOARD.md，V）：Polyvore text→image R@1：FashionCLIP2.0 0.186、LAION ViT-B-16 0.198、Marqo-FashionCLIP 0.212、SigLIP-webli 0.268、**Marqo-FashionSigLIP 0.271**（R@10 0.585）。注意這是 `Marqo/polyvore`（Han 2017 版、94k items），不是 mvasil 版。

### 1.2 圖文 embedding 融合

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| GCL（同上） | Marqo | 2025 | 2404.08535 | 固定權重平均標題與圖片 embedding；零樣本 NDCG@10 0.199 vs 純圖 0.089 | V（部分） |
| Beyond Text: Text–Image Fusion for Scalable Two-Tower Retrieval | Target | arXiv 2603.04836（2026） | arxiv.org/abs/2603.04836 | 學習式融合 0.841 vs 純文字 0.802，簡單 MLP 已 0.827 → 加圖一定有幫助，學習式融合需訓練 | V |

### 1.3 修正建議
1. Encoder 換 **Marqo-FashionSigLIP**；FashionCLIP 與（可選）ZooClaw 當消融組。
2. **不要把 JSON 或關鍵字清單丟進 text encoder**：把意圖轉成一句短 caption（例：「a red casual summer dress」）。
3. **否定（「不要印花」「不要太正式」）一律變 filter 或改寫成正向詞**，不進 CLIP 文字。
4. 多品項（「紅上衣配黑裙」）**拆成每品項一次查詢**，避免屬性錯綁。
5. 商品索引用**正規化後的圖文 embedding 加權平均**（起點 0.5/0.5），權重本身列為消融變因。

---

## 2. Hybrid search、硬約束、LLM 查詢理解

### 2.1 分數融合

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| Reciprocal Rank Fusion outperforms Condorcet… | Waterloo / Google | SIGIR 2009 | dl.acm.org/doi/10.1145/1571941.1572114 | 只用名次 1/(k+rank)，不需分數尺度 | U |
| An Analysis of Fusion Functions for Hybrid Retrieval | Pinecone（Bruch et al.） | TOIS 2023 | arxiv.org/abs/2210.11934 | **convex combination ≥ RRF**，RRF 對參數敏感；CC 少量樣本即可調 α | V |
| Relevance score normalization for metasearch | Dartmouth | CIKM 2001 | dl.acm.org/doi/10.1145/502585.502657 | 正規化方式強烈影響融合品質 | U |
| Sparse embeddings for e-commerce, pt.1 | Qdrant | blog 2026 | qdrant.tech/articles/sparse-embeddings-ecommerce-part-1/ | ESCI nDCG@10：BM25 0.305 / SPLADE 0.326 / 微調 SPLADE 0.389；dense 會漏精確規格 | V |
| Elastic linear retriever、Weaviate hybrid search | Elastic / Weaviate | blog | elastic.co/search-labs/blog/linear-retriever-hybrid-search；weaviate.io/blog/hybrid-search-explained | 兩種分數分布不同，必須正規化；Weaviate 預設 min-max 後加權 | U |

> 兩條搜尋線結論有出入（一條推 RRF、一條引 Bruch 推 CC），整合後建議：**RRF(k=60) 當不用調參的 baseline，min-max/z-score 正規化後的 CC 當主力，α 只在獨立 dev query 調，兩者都報。**

### 2.2 硬約束 vs 軟偏好

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| Embedding-based Product Retrieval in Taobao Search（MGDSPR） | Alibaba | KDD 2021 | arxiv.org/abs/2106.09297 | ANN 結果再過 boolean filter（品牌、顏色、風格、族群），濾掉約 30% | V |
| Embedding-based Retrieval in Facebook Search | Meta | KDD 2020 | arxiv.org/abs/2006.11632 | ANN 運算子內嵌在 boolean term index | V |
| Query Time Constrained ANN Search | Vespa | blog 2022 | blog.vespa.ai/constrained-approximate-nearest-neighbor-search/ | 後過濾可能讓排序階段拿到 0 筆；依通過率選先濾或後濾 | V |
| ACORN / Filtered-DiskANN | Stanford / Microsoft | SIGMOD 2024 / WWW 2023 | arxiv.org/abs/2403.04871 | 過濾感知 ANN；**我們的規模用不到**，只當 future work | U |
| Rewriting null e-commerce queries | eBay | WWW 2012 | dl.acm.org/doi/10.1145/2187980.2187989 | 零結果時改寫／放寬查詢 | U |
| Semantic Product Search | Amazon | KDD 2019 | arxiv.org/abs/1907.00937 | dense 用來補關鍵字的同義詞／拼字缺口，與精確比對並存 | V |
| Enhancing Relevance of EBR at Walmart | Walmart | CIKM 2024 | arxiv.org/abs/2408.04884 | 純 embedding 會偏離 relevance | V |

### 2.3 LLM 查詢理解 → 結構化屬性（與 ENGINE 01 的介面）

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| Building the Intent Engine | Instacart | blog 2025-11 | company.instacart.com/tech-innovation/ | LLM 標註品項／屬性，**輸出對商品 taxonomy 驗證** | V |
| QUEACO | Amazon | CIKM 2021 | arxiv.org/abs/2108.08468 | 屬性表面詞 → 目錄標準值（navy → blue）是獨立一步 | U |
| Implicit Query Parsing at Amazon | Amazon | SIGIR 2023 | dl.acm.org/doi/10.1145/3539618.3591858 | 明說屬性 vs 隱含屬性（wedding → formal）分開處理 | U |
| ShoppingComp | 學術 | arXiv 2511.22978 | arxiv.org/abs/2511.22978 | 多約束購物任務前沿 LLM 僅 ~16–18%；**約束檢查別交給 LLM，用程式做** | V |

### 2.4 Polyvore Outfits 實際欄位（重要）
- HF `mvasil/polyvore-outfits` 為 gated，資料檢視回 401（V）。官方 loader 只讀 `semantic_category`、`title`、`url_name`（V）；mirror `owj0421/polyvore` 欄位為 `item_id, image, url_name, title, description, category`（V）。
- **沒有任何來源證實有 price / color / season / size / occasion。** 價格只在 Han et al. 2017 版（xthan/polyvore-dataset）有（V）。
- 影響：預算與尺寸無法真過濾；顏色要從 title/description regex＋影像 zero-shot 抽並附信心值；場合／季節只能是推論出的**軟訊號**；BM25 實際上只是在搜短標題。

### 2.5 修正建議
1. **先 filter 再排序**：品類、預算、使用者明說的顏色 → pandas mask；存活者用 dense 排序；場合／風格／ENGINE 03 偏好只重排。10–25 萬筆規模用 NumPy / FAISS `IndexFlatIP` 暴力搜即精確且夠快，不需 filtered-ANN。
2. **空結果放寬策略**：固定優先序（例：顏色 → 預算 +20% → 品類永不放寬），並在解釋文字明說「放寬了哪一條」。這直接回應企業簡報的「在約束下維持品質」。
3. **ENGINE 01 輸出要對目錄詞彙表正規化**，不認得的值標記而非直接丟進 BM25（需與 ENGINE 01 負責人對介面）。
4. **資料欄位誠實揭露**：哪些欄位是資料集真值、哪些是推論／合成，README 與簡報都寫清楚。

---

## 3. 穿搭相容性（Polyvore 系）

### 3.1 文獻

| 論文 | 單位 | Venue | 連結 | 數字（ND = nondisjoint, D = disjoint） | 可用 checkpoint？ | |
|---|---|---|---|---|---|---|
| Learning Fashion Compatibility with Bi-LSTMs | Maryland | ACM MM 2017 | github.com/xthan/polyvore | FITB 73.5%（Maryland 版，不可比） | TF 0.10，兩天內不可用 | V |
| Type-Aware Embeddings（建立 Polyvore Outfits） | UIUC | ECCV 2018 | github.com/mvasil/fashion-compatibility | AUC 0.86 / FITB 55.3 | 有（ND only，BSD-3） | V |
| SCE-Net | BU | ICCV 2019 | arxiv.org/abs/1908.08589 | ND AUC 0.91 / FITB 59.07 | 未查 | V |
| CSA-Net（Fashion Outfit Complementary Item Retrieval） | Amazon | CVPR 2020 | arxiv.org/abs/1912.08967 | ND FITB 63.73、R@10 8.27 | 僅非官方 | U |
| OutfitTransformer | Amazon 作者群 | WACV 2023 | arxiv.org/abs/2204.04812 | ND AUC 0.93 / FITB 67.10 / **R@10 9.58**；D FITB 59.48 | 無官方 | V |
| owj0421/outfit-transformer（重實作） | 社群 | — | github.com/owj0421/outfit-transformer | 自報 AUC 0.95 / FITB 69.24 | **MIT、有權重、FAISS demo** | V |
| TATTOO | CMU / HUST | arXiv 2509.23242（2025） | arxiv.org/abs/2509.23242 | **免訓練**：GPT-4o 為每件商品寫結構化 profile（顏色、風格、場合、季節、材質）；D FITB 65.74 勝過 OutfitTransformer | 未找到 code | V |
| Loom | 個人 | arXiv 2605.09830（2026） | github.com/anushreeberlia/loom | FashionCLIP 每槽位 ANN＋手寫多目標評分——**與本組原提案幾乎相同** | 有 | V |
| DiFashion | USTC / NUS | SIGIR 2024 | arxiv.org/abs/2402.17279 | 擴散模型**生成**穿搭圖，非檢索 | 有 | V |

### 3.2 資料集問題
- mvasil 卡片：作者「不擁有底層圖片或 metadata 版權」、**限學術／非營利**（V）。對企業出題的 demo 有風險。
- Nondisjoint split 有 item 重疊洩漏，應用 **disjoint**（V）。
- 隨機負例常是錯品類，模型只要會認品類就能拿高分，應用**同品類 hard negatives**（U）。
- fashion-compatibility-benchmark：frozen CLIP/SigLIP/FashionCLIP＋logistic regression，**檢索排名對相容性的預測力差**（V）。
- 每題只有一個正解，合理替代品算錯 → 當檢索評估不準（TATTOO，V）。

### 3.3 業界

| 系統 | 單位 | Venue | 實際訊號 | |
|---|---|---|---|---|
| Complete the Look | Pinterest | **CVPR 2019**（原筆記寫 2020 有誤） | 場景照＋商品圖的相容性 | U |
| Shop The Look | Pinterest | KDD 2020 | 物件偵測＋**視覺相似**（是相似品，不是相容） | U |
| P-Companion | Amazon | CIKM 2020 | **只用共同購買**，刻意剔除 co-view（那是「相似」訊號）；先預測互補**品類**再挑商品 | V |
| POG | Alibaba iFashion | KDD 2019 | 專家穿搭 101 萬組＋2.8 億點擊 | V |
| Outfit Generation and Recommendation | Zalando | fashionXrecsys 2020 | 造型師穿搭、圖像 embedding、**結構化屬性**（品牌、季節、顏色、材質、花紋） | V |

業界共同點：**品類／類型約束優先**、人工策展穿搭或購買行為、結構化屬性；純像素不是主訊號。

### 3.4 修正建議
1. **相容性只在有 anchor 時啟用**（「搭我的黑色牛仔褲」、衣櫃、要求整套）；單品查詢不加這項。寫成 `if anchor: add compat term`，不是固定權重。
2. **FashionCLIP cosine 量的是「相似」不是「相容」**，拿來當相容性會推薦近似重複品；兩者分開，並先做互補品類約束（P-Companion 的 type-then-item）。
3. **不要自己訓練相容性模型**。兩個可行路線：(a) 直接用 owj0421 OutfitTransformer（MIT、有權重）；(b) TATTOO 式免訓練——ENGINE 01 已經在用的 LLM 順便產生商品屬性 profile，用規則＋embedding 算相容性。路線 (b) 的屬性欄位可以**同時當解釋依據**，也呼應簡報的「規則化的文字解釋」。
4. 若要報相容性數字：disjoint split＋同品類 hard negative 自建小 FITB 集。

---

## 4. Reranking、分數校準與無標註評估

### 4.1 真正的 reranker

| 模型 / 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| RankGPT（Is ChatGPT Good at Search?） | 山東大學 / Baidu | EMNLP 2023 | arxiv.org/abs/2304.09542 | LLM zero-shot listwise rerank | V |
| RankZephyr | Waterloo | arXiv 2312.02724 | arxiv.org/abs/2312.02724 | 開源 7B listwise | U |
| **Qwen3-VL-Reranker-2B / 8B** | Alibaba Qwen | arXiv 2601.04720（2026） | huggingface.co/Qwen/Qwen3-VL-Reranker-2B | 多模態 cross-encoder，query 對圖／文／圖文文件；**Apache-2.0**，sentence-transformers `CrossEncoder` 可載 | V |
| jina-reranker-m0 | Jina AI | 2025 | huggingface.co/jinaai/jina-reranker-m0 | 可用但 **CC BY-NC 4.0**，企業 demo 避免 | V |
| bge-reranker-v2-m3 | BAAI | HF | huggingface.co/BAAI/bge-reranker-v2-m3 | 輕量中英文字 cross-encoder 備案 | U |
| LambdaMART | Microsoft Research | MSR-TR-2010-82 | — | 需要標註，無 log 不可行 | U |
| LEAPS（Taobao AI Search） | Taobao | arXiv 2601.05513（2026） | arxiv.org/abs/2601.05513 | Query Expander 擴召回 → **Relevance Verifier** 過濾；2025-08 上線 | V |
| FIRE-CIR | Inria / ENS | arXiv 2604.09114（2026） | arxiv.org/abs/2604.09114 | 對候選逐屬性問視覺問題來 rerank | V |

### 4.2 多目標、多樣性

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| MMR | CMU | SIGIR 1998 | dl.acm.org/doi/10.1145/290941.291025 | 相關性 vs 新穎性權衡，約 10 行 | U |
| Practical Diversified Recommendations on YouTube with DPPs | Google | CIKM 2018 | dl.acm.org/doi/10.1145/3269206.3272018 | 集合層級多樣性 rerank | U |
| Recommending What Video to Watch Next | Google | RecSys 2019 | dl.acm.org/doi/10.1145/3298689.3346997 | 業界確實加權合併多目標，但各分數是**學習且校準過**、權重經線上實驗調 | U |
| Learning To Rank Diversely At Airbnb | Airbnb | CIKM 2023 | arxiv.org/abs/2210.07774 | 單品相關性獨立假設不成立 | U |

### 4.3 無使用者 log 的評估

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| LLMs can accurately predict searcher preferences | Microsoft / Bing | SIGIR 2024 | arxiv.org/abs/2309.10621 | LLM relevance 標註 ≥ 第三方標註員 | V |
| UMBRELA | Waterloo＋Microsoft | arXiv 2406.06519 | arxiv.org/abs/2406.06519 | 開源 Bing prompt，0–3 分級，可直接抄 | V |
| LLMs for Relevance Judgment in Product Search | Walmart | SIGIR 2024 | arxiv.org/abs/2406.00247 | 電商場景；注意他們是**微調過**的 judge | V |
| LLMs can be Fooled into Labelling a Document as Relevant | RMIT / Microsoft（Alaofi et al.） | SIGIR-AP 2024 | arxiv.org/abs/2501.17969 | 塞 query 詞就能騙 LLM judge → GPT 寫的理由／標題可能灌水 | U |
| LLM-based relevance assessment still can't replace human | Waterloo / UNH（Clarke & Dietz） | EVIA 2025 | arxiv.org/abs/2412.17156 | **排序與評判用同源 LLM 會循環膨脹** | U |
| Shopping Queries Dataset（ESCI） | Amazon | KDD Cup 2022 | arxiv.org/abs/2206.06588 | 13 萬 query、E/S/C/I 四級人工標註 | V |
| SQID | Crossing Minds | arXiv 2405.15190 | arxiv.org/abs/2405.15190 | ESCI 加圖片 | U |
| Effect of topic set size on retrieval experiment error | NIST | SIGIR 2002 | dl.acm.org/doi/10.1145/564376.564432 | 30–50 題時小差距不可信 | U |
| Comparison of significance tests for IR evaluation | UMass / Waterloo | CIKM 2007 | dl.acm.org/doi/10.1145/1321440.1321528 | 建議 randomization / bootstrap | U |
| iEvaLM | 人大 | EMNLP 2023 | arxiv.org/abs/2305.13112 | LLM 模擬使用者評估對話推薦 | V |
| How Reliable is Your Simulator? | 北交大 | arXiv 2403.16416 | arxiv.org/abs/2403.16416 | 模擬器**洩漏目標**導致結果膨脹 | V |
| **ConvApparel** | Google | EACL 2026 | arxiv.org/abs/2602.16938 | **服飾**對話推薦資料集；所有模擬器與真人都有顯著落差 | V |

### 4.4 修正建議
1. 手調權重合併**改名 score fusion**；若時間允許，在 top-50 上加 **Qwen3-VL-Reranker-2B**，把意圖 JSON 寫進 instruction。
2. 異質分數（cosine、BM25、相容性機率）**先 per-query 正規化**，並報告權重敏感度。
3. 最後加 **MMR**，避免 top-5 是五件幾乎一樣的東西。
4. 「符合度 62%→89%」**只能當「約束滿足率」報**，不能當品質提升證據。
5. 評估流程：UMBRELA 0–3 prompt → 各消融組 top-5 取聯集 pooling → 每個 (query, item) 只判一次 → 人工抽約 100 筆算 Cohen's κ → paired permutation test＋bootstrap CI → judge 看**原始一句話與商品圖**、不看抽出的 JSON，且**用不同模型家族**，judge 輸入去掉 GPT 寫的理由。
6. 模擬使用者驗證的結果在簡報上**明確標註為模擬**，並引 ConvApparel 說明其偏樂觀。

---

## 5. 可解釋性：忠實度才是評審要的

### 5.1 核心論點
原提案說「理由是根據真實檢索到的商品屬性寫的，所以可解釋性站得住腳」。文獻把兩件事分開：
- **Factuality（事實正確）**：理由裡的屬性是不是真的。→ 原提案有做到。
- **Faithfulness（忠實）**：理由是不是**真正導致這個排名的原因**。→ 原提案**沒有**保證。

評審原話「主管問怎麼跑出來的答不出來」，問的是後者。

### 5.2 文獻

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| Explainable Recommendation: A Survey and New Perspectives | Rutgers | FnTIR 2020 | arxiv.org/abs/1804.11192 | 區分 model-intrinsic vs post-hoc；原提案屬 post-hoc | V |
| A Survey of Explanations in Recommender Systems（Tintarev & Masthoff） | Aberdeen | ICDE-W 2007 | doi 10.1109/ICDEW.2007.4401070 | 7 個目標（透明、可審查、信任、有效、說服、效率、滿意）彼此會衝突；GPT 流暢句子偏「說服」 | U |
| PETER / PEPLER | HKBU / Rutgers | ACL 2021 / TOIS 2023 | arxiv.org/abs/2105.11601 | 生成的解釋學的是像評論，不是跟著評分器 | V |
| Unlocking the Potential of LLMs for Explainable Recs（LLMXRec） | — | DASFAA 2024 | arxiv.org/abs/2312.15661 | 推薦器＋LLM 寫解釋，**最接近原提案** | U |
| XRec | HKU | EMNLP Findings 2024 | arxiv.org/abs/2406.02377 | 同為 post-hoc | V |
| RecExplainer | MSRA | arXiv 2311.10947 | arxiv.org/abs/2311.10947 | 承認 LLM 本身不知道模型為何排序，需額外對齊 | V |
| Mitigating Misleadingness in LLM-Generated NL Explanations for RecSys | VUB | IUI 2025 Workshops | CEUR 3957 | 分類學明確區分「事實錯誤」與「對系統運作的不忠實描述」 | V |
| The Utility of LLMs in RecSys Explanation Evaluation | UZH | RecSys 2026 | arxiv.org/abs/2609.01627 | 人和 LLM 都無法可靠偵測非事實內容 → **事實檢查用程式** | V |
| RobustExplain | — | arXiv 2601.19120 | arxiv.org/abs/2601.19120 | 輸入有雜訊時 LLM 解釋會變 | V |
| Language Models Don't Always Say What They Think | NYU / Anthropic | NeurIPS 2023 | arxiv.org/abs/2305.04388 | CoT 解釋可能隱藏真正影響答案的偏差 | V |
| CountER | Rutgers | CIKM 2021 | doi 10.1145/3459637.3482420 | 反事實解釋：最小屬性改變使推薦翻轉 | U |
| From latent factors to language（n=326） | UMONS | IntRS@RecSys 2025 | arxiv.org/abs/2509.18980 | **可解釋模型的數值 → LLM 只負責改寫**，最接近建議做法 | V |
| CrystalCandle（原 Intellige） | LinkedIn | 工程 blog 2022；arXiv 2306.07464 | linkedin.com/blog/engineering/ | 每筆預測 SHAP/LIME → 特徵分組 → **模板填入真值**；A/B 續約 +8% | V |
| EX³ | Amazon | RecSys 2021 | amazon.science | 以關鍵屬性作為推薦集合的解釋，十億級 | V |
| Toward Explainable Fashion Recommendation | 東北大學 | arXiv 1901.04870 | arxiv.org/abs/1901.04870 | 用替換特徵觀察分數變化驗證解釋 | V |
| PAI-BPR | IIIT-Delhi | IEEE BigMM 2020 | arxiv.org/abs/2008.01780 | 屬性層級解釋穿搭相容（含哪些屬性衝突） | V |
| Explainable Outfit Recommendation（NOR） | 山東大學 / UvA | TKDE 2020 | arxiv.org/abs/1806.08977 | 穿搭匹配＋生成評論 | U |

**可審查／批評式推薦（ENGINE 02 解釋 ↔ ENGINE 03 回饋的橋）**

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| Critiquing-based recommenders: survey | EPFL / HKBU | UMUAI 2012 | doi 10.1007/s11257-011-9108-6 | 使用者對展示商品下「便宜一點」「不要那麼正式」 | U |
| Deep Language-based Critiquing | Toronto | **RecSys 2019**（非 SIGIR） | github.com/wuga214/DeepCritiquingForRecSys | 預測 keyphrase 當解釋，使用者批評 keyphrase 即更新推薦 | U |
| Latent Linear Critiquing | Toronto | **WWW 2020**（非 SIGIR） | github.com/k9luo/LatentLinearCritiquingforConvRecSys | 批評 = 使用者 embedding 的線性編輯 | U |
| Interacting with Explanations through Critiquing | EPFL | IJCAI 2021 | arxiv.org/abs/2005.11067 | 直接在解釋上增刪屬性，多輪 | V |
| Transparent and Scrutable Recs Using NL User Profiles | UCL | ACL 2024 | arxiv.org/abs/2402.05810 | LLM 寫的文字 profile 驅動推薦，編輯 profile 即改變推薦 | U |

### 5.3 修正建議（兩天內可做）
1. **分數分解就是解釋本體。** Score = Σ wᵢ·fᵢ，逐商品記錄每一項貢獻（語意相似、顏色符合、預算符合、風格標籤、相容性、偏好）。理由 = 前 2–3 個正貢獻＋任何負貢獻或被放寬的約束，畫成小長條圖。
2. **LLM 只當改寫器。** 輸入 `{feature, value, contribution, rank_vs_#2}`，指示只能用這些事實；程式檢查輸出中每個屬性／數字都在輸入裡，否則退回模板句。模板句與流暢句並列顯示。
3. **忠實度檢查（CountER 精神）。** 對每個被引用的特徵把其貢獻歸零後重排，若該商品名次**沒掉**，這個理由就不忠實。另檢查貢獻加總 = 總分、把別件商品的理由換過來應該檢查失敗。
4. **對比式理由。** 「為什麼 A 排在 B 前面」= 兩者貢獻差，直接回應「約束下的品質」。
5. **可審查迴圈接 ENGINE 03。** 被引用的屬性做成可刪除的 chip（「正式 ✕」），點擊即改意圖 JSON 並重排——這就是 critiquing，也正好對上現場評測「給回饋 → 再出題」。
6. **可報的數字**：忠實度檢查通過率、事實檢查幻覺率、同一商品多次生成理由的一致性。**不要**用 LLM 當事實檢查 judge。

---

## 6. 互動式檢索：「這件但休閒一點」

### 6.1 Composed Image Retrieval（參考圖＋修改文字）

Fashion IQ val，零訓練（zero-shot），R@10/R@50，三類平均：

| 方法 | 單位 | Venue | 連結 | R@10/R@50 | Code | |
|---|---|---|---|---|---|---|
| Fashion IQ（資料集） | IBM / UT Austin | CVPR 2021 | arxiv.org/abs/1905.12794 | — | 有 | U |
| Pic2Word | Google | CVPR 2023 | github.com/google-research/composed_image_retrieval | 24.70/43.70（ViT-L） | Apache-2.0 | V |
| SEARLE | Florence | ICCV 2023 | github.com/miccunifi/SEARLE | 25.56/46.23（ViT-L） | CC BY-NC | V |
| LinCIR | NAVER | CVPR 2024 | github.com/navervision/lincir | 26.28/46.49（L）；45.11/65.69（ViT-G） | 有 | V |
| **CIReVL** | Tübingen / Munich | ICLR 2024 | github.com/ExplainableML/Vision_by_Language | **免訓練**：BLIP-2 描述參考圖 → LLM 把描述＋修改改寫成目標描述 → CLIP 以文搜圖；28.55/48.57（L）、32.19/52.36（G） | MIT | V |
| OSrCIR | CAS / Microsoft / Adelaide | arXiv 2412.11077 | arxiv.org/abs/2412.11077 | GPT-4o 單步推理意圖；33.26/54.37（L）、37.57/57.11（G） | 待釋出 | V |
| MCoT-RE | — | arXiv 2507.12819 | arxiv.org/abs/2507.12819 | 38.70/57.74（L）（表格抽取有疑義，謹慎引用） | ? | V |

### 6.2 多輪互動檢索

| 論文 | 單位 | Venue | 連結 | 重點 | |
|---|---|---|---|---|---|
| Conversational Fashion Image Retrieval via Multiturn NL Feedback | CUHK | SIGIR 2021 | github.com/yfyuan01/MultiturnFashionRetrieval | 多輪 Fashion IQ | V |
| FashionNTM | Amazon / UC | ICCV 2023 | arxiv.org/abs/2308.10170 | 記憶網路跨輪保留約束 | U |
| Chatting Makes Perfect（ChatIR） | Hebrew U. | NeurIPS 2023 | github.com/levymsn/ChatIR | 5 輪後 78% vs 單輪 64% | U |
| PlugIR | SNU | ACL 2024 | github.com/Saehyung-Lee/PlugIR | LLM 把對話濃縮成單一 query 給任意 retriever | U |
| VOGUE | Toronto | arXiv 2510.21151（2025） | arxiv.org/abs/2510.21151 | 60 段真人時尚對話；MLLM 難推論未明說的偏好 | V |
| Rufus | Amazon | amazon.science blog 2024 | amazon.science/blog/the-technology-behind-amazons-genai-powered-shopping-assistant-rufus | 目錄＋評論＋Q&A 檢索、以顧客評分做 RL | V |

### 6.3 生成再檢索（原提案的概念圖分支）

| 論文 | Venue | 連結 | 證據 | |
|---|---|---|---|---|
| Category-level Text-to-Image Retrieval Improved | BMVC 2025 | arxiv.org/abs/2509.00177 | 純文字 62.7 mAP；純生成圖 41.4；**天真 0.5/0.5 融合 61.0（比純文字差）**；訓練過的聚合器 67.9 | V |
| Imagine and Seek（IP-CIR） | CVPR 2025 | arxiv.org/abs/2411.16752 | 免訓練生成代理圖；**Fashion IQ R@10 只 45.11→45.74** | V |
| VisRet（Visualize-then-Retrieve） | ACL 2026 | arxiv.org/abs/2505.20291 | 知識密集、非時尚 query 上 +0.125 nDCG@30 | V |
| Diffusion Augmented Retrieval | SIGIR 2025 | arxiv.org/abs/2501.15379 | 簡單 query 持平，10 輪對話後才 +7.61% Hits@10 | U |
| LookSync | Glance（InMobi） | arXiv 2511.00072 | 生成造型對應 1200 萬真實商品；業界用法是**生成圖給使用者看**，不是暗中當 query | V |

另注意**風格落差**：生成圖多為模特兒／生活照，Polyvore 是白底去背圖，FashionCLIP 模型卡自述偏好白底。

### 6.4 Rocchio 回饋（免訓練 baseline）

| 論文 | Venue | 連結 | 重點 | |
|---|---|---|---|---|
| Revisiting Relevance Feedback for CLIP-based Interactive Image Retrieval | ECCV 2024 Workshop | arxiv.org/abs/2404.16398 | frozen CLIP＋喜歡/不喜歡回饋即可與 metric learning 競爭 | V |
| A Little More Like This | WACV 2026 | arxiv.org/abs/2511.17255 | Rocchio 式更新下比較多種回饋；生成式回饋多輪會漂移 | V |

### 6.5 修正建議
1. **回饋改寫目標描述，而不是只調權重**：LLM 拿「被喜歡商品的屬性／caption＋回饋（更休閒、材質不變）」產出新目標描述再檢索（CIReVL / OSrCIR 路線）。
2. **累積意圖狀態**：材質 = locked、正式度 = casual；新一輪不得默默丟掉舊約束。畫面顯示**狀態 diff**，這就是「看得見的進步」。
3. **Rocchio**：q ← α·q + β·mean(喜歡) − γ·mean(不喜歡)，幾行程式。
4. **有參考商品時做 composed query**：融合參考商品 embedding 與改寫後文字 embedding，而非只用文字。
5. **概念圖降級**為可關閉、低權重分支或純展示。
6. 以上 1–4 大部分落在 ENGINE 02／03 的介面上，需與 ENGINE 03 負責人對齊「回饋輸出的是意圖 diff 還是權重 diff」。

---

## 7. 修正後的 ENGINE 02 建議流程（草案）

```
ENGINE 01 intent JSON
   │  (1) 正規化到目錄詞彙表；分成 hard constraints / soft preferences / negations / anchor
   ▼
Hard filter（pandas mask：品類、預算*、明說的顏色、否定條件）
   │  結果為空 → 依固定順序放寬，記錄 relaxed_constraints
   ▼
Candidate retrieval（top-100）
   ├─ dense：Marqo-FashionSigLIP，query = 一句短 caption（無否定）
   │          ＋ 有 anchor/參考商品時做 composed query
   │          ＋ 回饋輪次：Rocchio 更新
   ├─ sparse：BM25 over title/description
   └─ 融合：RRF(k=60) baseline / 正規化 CC（α 在 dev set 調）
   ▼
Score fusion（每項先正規化，逐項記錄貢獻）
   ├─ soft preferences（場合、風格、ENGINE 03 偏好）
   ├─ compatibility（僅在有 anchor 時；OutfitTransformer 或 TATTOO 式屬性規則）
   └─ [可選消融] 生成概念圖相似度，權重 ≤ 0.2
   ▼
[可選] Qwen3-VL-Reranker-2B on top-50 → MMR 多樣性 → top-5
   ▼
Explanation
   ├─ 分數分解長條圖＋被放寬的約束
   ├─ LLM 改寫 → 程式事實檢查 → 失敗退回模板
   ├─ 忠實度檢查（ablate cited feature → rank 是否下降）
   └─ 屬性 chip 可點掉 → 回饋給 ENGINE 03
```
\* 預算只有在採用含 price 的資料版本時才是真過濾，否則要在簡報中標明為合成欄位。

### 評估計畫（對應評分標準「技術方案」35%＋「回饋迴圈可驗證」）

| 層級 | 指標 | 方法 |
|---|---|---|
| 檢索品質 | NDCG@5 | 消融組：BM25 / dense(FashionCLIP) / dense(Marqo) / hybrid-RRF / hybrid-CC / +rerank / +概念圖；UMBRELA judge、pooling、人工 κ、paired permutation test |
| 約束 | Constraint-satisfaction@5、空結果率、放寬率 | 純程式判定 |
| 解釋 | 忠實度通過率、幻覺率、一致性 | ablation 重排、字串／數值比對、重複生成 |
| 回饋迴圈 | 多輪 NDCG／約束保留率 | 模擬使用者（明確標註為模擬）＋少量真人對照 |

---

## 8. 需要全組決定的事

1. **資料集**：mvasil 版 gated 且限學術；是否改 `Marqo/polyvore`（Apache-2.0）或 Han 2017 版（有 price）？價格欄位要不要合成？
2. **生成概念圖**：證據顯示併入檢索分數效益很小甚至負面，是否降級為展示用／消融分支？（會影響第五位組員的工作範圍）
3. **ENGINE 02 ↔ 03 介面**：回饋輸出「意圖 diff＋Rocchio 向量」還是「權重 diff」？
4. **ENGINE 01 ↔ 02 介面**：intent JSON 需拆出 `hard_constraints`、`soft_preferences`、`negations`、`anchor_item` 四塊，並對目錄詞彙表正規化。
5. **「符合度 62%→89%」**：改名為約束滿足率，另備真正的品質指標。

---

## 附錄：引用更正紀錄

| 原筆記／原 brief 寫法 | 查證後 |
|---|---|
| Pinterest Complete the Look 2020 | CVPR **2019** |
| Deep Language-based Critiquing（SIGIR 2019） | **RecSys 2019** |
| Latent Linear Critiquing（SIGIR 2020） | **WWW 2020** |
| 「LLMs can be fooled into labelling…」是 Clarke & Dietz | 實為 **Alaofi, Thomas, Scholer, Sanderson（SIGIR-AP 2024）**；Clarke & Dietz 是另一篇（EVIA 2025） |
| LLMXRec | 論文標題為 *Unlocking the Potential of LLMs for Explainable Recommendations*（DASFAA 2024） |
| arXiv 2603.03080 *Beyond Factual Correctness* | **已撤稿，勿引用** |
