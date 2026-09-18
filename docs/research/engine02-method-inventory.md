# ENGINE 02 方法盤點（檢索＋排序＋解釋）— 已驗證清單、消融 arm 與 M3–M7 批判

> 調查日期：2026-09-16。範圍：只收**有可跑開源實作**或「幾十行就能自寫、且有論文依據」的方法，重點放在前一輪研究**沒涵蓋**的新東西。
> 驗證標記：**V** = 本次實際打開 arXiv abstract / arXiv API / GitHub API（license 欄位）/ HF API（cardData.license）/ PyPI JSON / Context7 文件確認過；**U** = 只來自搜尋摘要或二手描述、沒從一手頁面確認，或是我的工程估算。
> 「2 天工時」一律是 **U（估算）**。CPU = 開發筆電；4090 = 之後才有。
> 前一輪已知的東西（Marqo-FashionSigLIP、Qwen3-VL-Reranker-2B、bge-reranker-v2-m3、jina-reranker-m0、Bruch TOIS 2023、Taobao MGDSPR、OutfitTransformer owj0421、TATTOO、CIReVL/OSrCIR、Rocchio-for-CLIP、MMR/DPP、CountER、CrystalCandle、BMVC 2025 generated-image fusion）只在需要時引用，不重查。

---

## 0. TL;DR（給趕時間的人）

1. **M4 最大風險**：CLIP 系模型對「細粒度屬性」本來就弱（OVAD、ARO bag-of-words），而且 WaffleCLIP 顯示「LLM 描述子」的增益可以被**隨機字串描述子**追平。→ M4 必須加一個 **random-descriptor 對照 arm**，否則無法宣稱 c(i,d) 真的在量設計元素。
2. **更可靠的 c(i,d)**：(a) CLIP-IQA 式**反義詞成對提示**（matte ↔ glossy）取兩極 softmax，天然是 Kansei 語意差異量表的形狀；(b) 4090 上用 **Qwen3-VL（Apache-2.0）離線結構化標註**＋token 機率當信心值。2026 的 zero-shot VLM 屬性標註研究顯示 VLM 大幅勝過 Fashion-CLIP embedding＋線性分類器，但「此屬性是否適用」（applicability）是瓶頸 → M4 需要 **applicability mask**。
3. **M5/M6 工具**：`bm25s`（MIT，有 `weight_mask` 可做前置過濾）＋ numpy 暴力內積就夠（型錄 < 10 萬件時不需要向量 DB）；融合用 **`ranx`**（MIT，RRF/CombSUM/CombMNZ/wsum＋`optimize_fusion` 從少量標註學權重）。
4. **M6 權重不要手調**：用 pairwise logistic（choice 回饋 = chosen ≻ not chosen）學**非負、可加**權重；想要形狀函數當解釋可上 **EBM（InterpretML，MIT，支援 `monotone_constraints`）**。
5. **M7 的「拿掉就掉出 top-5」準則太嚴且不穩**：對可加模型可以用**精確的對比邊際分解**（why A over 第 6 名）取代反覆 rerank，再加 sufficiency 指標（ERASER / LENS 的 PN/PS 概念）。
6. 優先 arm 清單見 §10；M3–M7 批判與修法見 §11。

---

## 1. Zero-shot 概念／屬性打分（M4）

### 1.1 Concept-bottleneck 與描述子系列

| 方法 | 論文（venue/年） | Repo／License | pip? CPU? GPU? | 2 天工時 | 對 ENGINE 02 的用途 | 驗證 |
|---|---|---|---|---|---|---|
| **Classification by Description**（Menon & Vondrick） | ICLR 2023，[arXiv 2210.07183](https://arxiv.org/abs/2210.07183) | 搜尋沒找到官方 repo（`sachit-menon/classify_by_descriptions` 經 GitHub API 回 404） | 自寫約 30 行：描述子 embedding 取平均 | 0.5h | 就是 M4 現在的做法 | 論文 V／repo U |
| **WaffleCLIP** — random words / 隨機字元描述子 | ICCV 2023，[arXiv 2306.07282](https://arxiv.org/abs/2306.07282) | [ExplainableML/WaffleCLIP](https://github.com/ExplainableML/WaffleCLIP)，**MIT** | conda env；CPU 可以（只需要編碼文字＋圖片）| 1h（只取「隨機描述子」生成器當對照組）| **M4 的必要對照組**：abstract 明說隨機字元／字詞描述子的增益和 LLM 描述子相當，而且語意資訊用在「消除類名歧義的高層概念」上比較有價值 | V |
| **Comparative descriptors**（描述目標類別和最相近類別的差異） | WACV 2025，[arXiv 2411.05357](https://arxiv.org/abs/2411.05357) | abstract 頁沒有 repo 連結 | 自寫 | 1h | 很適合 M4：要 GPT 寫 "structured shoulders **vs** soft/dropped shoulders" 的對比描述子，並過濾掉和 CLIP 圖像空間不對齊的描述子 | 論文 V／code U |
| **LaBo**（Language in a Bottle） | CVPR 2023，[arXiv 2211.11158](https://arxiv.org/abs/2211.11158) | [YueYANG1996/LaBo](https://github.com/YueYANG1996/LaBo)，**GitHub 未偵測到 license** | 要訓練（submodular 選概念＋線性層）、要 GPU | 不建議 | 只借概念選擇（submodular：discriminability＋coverage）的想法來挑 d 的描述子 | V |
| **Label-free CBM** | **ICLR 2023**（任務描述寫 CVPR 有誤），[arXiv 2304.06129](https://arxiv.org/abs/2304.06129) | [Trustworthy-ML-Lab/Label-free-CBM](https://github.com/Trustworthy-ML-Lab/Label-free-CBM)，**無 license** | 要訓練（CLIP-Dissect 對齊＋稀疏線性層）| 不建議 | 借「刪掉和圖像空間不相似／過度相似的概念」的過濾步驟 | V |
| **LM4CV**（Learning Concise and Descriptive Attributes） | ICCV 2023，[arXiv 2308.03685](https://arxiv.org/abs/2308.03685) | [wangyu-ustc/LM4CV](https://github.com/wangyu-ustc/LM4CV)，**無 license** | 要訓練，torch 2.0.1 | 不建議 | 論點：少量「精選」屬性就夠 → 支持把 d 砍到 15–30 個 | V |
| **Post-hoc CBM** | 前一輪已引用 | [mertyg/post-hoc-cbm](https://github.com/mertyg/post-hoc-cbm)，**MIT** | CPU 可 | — | concept bank 的做法可以借 | V（license）|
| **SpLiCE**：把 CLIP 圖像 embedding 分解成稀疏、非負的概念詞組合 | NeurIPS 2024，[arXiv 2402.10376](https://arxiv.org/abs/2402.10376) | [AI4LIFE-GROUP/SpLiCE](https://github.com/AI4LIFE-GROUP/SpLiCE)，**Apache-2.0** | 免訓練；CPU 可跑（稀疏迴歸）| 3–4h | **c(i,d) 的替代算法**：把 d 的描述子當 concept 字典，對每件商品解一次稀疏非負分解，係數就是 c(i,d)。描述子彼此相關時比「各自算 cosine」少重複計算（例如 matte 和 minimal 共用方向）| V |
| **Discover-then-Name（DN-CBM）** | ECCV 2024（U） | [neuroexplicit-saar/discover-then-name](https://github.com/neuroexplicit-saar/discover-then-name)，**MIT** | 要訓練 SAE（在 4090 上要數十分鐘以上，U）| 不建議 | 研究延伸 | repo V／venue U |

### 1.2 提示集成、校準、標準化

| 方法 | 論文 | Repo／License | 實作 | 用途 | 驗證 |
|---|---|---|---|---|---|
| **CLIP prompt ensembling**（多個 template 平均文字 embedding） | CLIP，[arXiv 2103.00020](https://arxiv.org/abs/2103.00020) | open_clip（`open-clip-torch` 3.3.0，MIT，pure wheel）| 5 行 | M4 的每個描述子 × 多個 template 平均 | 論文身分 V；「ensembling 在 ImageNet 帶來幾個百分點」只在正文，本次沒打開正文 → U |
| **CLIP-IQA 反義詞成對提示** | AAAI 2023，[arXiv 2207.12396](https://arxiv.org/abs/2207.12396) | [IceClear/CLIP-IQA](https://github.com/IceClear/CLIP-IQA)，license = NOASSERTION（自訂條款，用前要讀）| 自寫 10 行：`softmax([s(img,"matte fabric"), s(img,"glossy fabric")]/τ)[0]` | **M4 核心改法**：abstract／搜尋摘要顯示用 "Good photo." / "Bad photo." 成對提示降低語言歧義，而且可以評估抽象的 "feel"。這和 Kansei 語意差異（SD）雙極量表同構 | V（論文）／license 細節 U |
| **Distribution Normalization（DN）**：推論時減掉測試批次的平均 embedding | NeurIPS 2023，[arXiv 2302.11084](https://arxiv.org/abs/2302.11084) | [fengyuli-dev/distribution-normalization](https://github.com/fengyuli-dev/distribution-normalization)，**無 license** | 3 行：`img -= mean_img_catalog`、`txt -= mean_txt`（依論文設定）| M4 的「跨型錄 z-score」就是 DN 的一階近似；**建議改成 embedding 層級的 DN，再加 per-d 的 z-score** | V |
| **Zero-shot 溫度校準** | ICLR 2023 workshop，[arXiv 2303.12748](https://arxiv.org/abs/2303.12748) | — | 1 個標量 τ | 反義詞 softmax 的 τ：論文結論是每個 CLIP 模型的單一 τ 可以跨資料集、跨 prompt 泛化（搜尋摘要）| 論文 V／結論 U |

### 1.3 證據：CLIP 對細粒度服飾屬性到底行不行？

| 證據 | 內容 | 驗證 |
|---|---|---|
| **OVAD**（CVPR 2023，[arXiv 2211.12914](https://arxiv.org/abs/2211.12914)，[code](https://github.com/OVAD-Benchmark/ovad-benchmark-code) CC0-1.0；資料 CC BY-NC-SA 4.0）| 專門測 VLM 的物件層級屬性理解（117 個屬性、140 萬筆標註）。搜尋摘要稱 box-given 設定下 CLIP ViT-B16 約 16.6 AP，專門方法 OvarNet 約 28.6 | 基準 V／數字 U |
| **ARO / NegCLIP**（ICLR 2023 Oral，[arXiv 2210.01936](https://arxiv.org/abs/2210.01936)，[repo](https://github.com/mertyg/vision-language-models-are-bows) MIT）| VLM 像 bag-of-words，屬性綁定（哪個屬性屬於哪個物件）很弱 → "matte **jacket** with glossy **buttons**" 這類敘述會失效 | V |
| **Zero-Shot Product Attribute Labeling with VLMs: Three-Tier**（WACV 2026 Workshop PRAW，[arXiv 2601.15711](https://arxiv.org/abs/2601.15711)）| DeepFashion-MultiModal，5,000 張圖、18 個屬性。9 個 VLM（GPT-5／Gemini 2.5 系列）zero-shot macro-F1 **64.0%**，約為「Fashion-CLIP embedding＋logistic regression」的 **3 倍**；細粒度 70.8% F1，但**「屬性是否適用」只有 34.1% NA-F1**，是瓶頸 | V（abstract）|
| **GPT-4o-mini / Gemini 2.0 Flash zero-shot**（[arXiv 2507.09950](https://arxiv.org/abs/2507.09950)）| 同一資料集：Gemini 2.0 Flash macro-F1 56.79%，GPT-4o-mini 43.28%；**GPT-4o-mini 的 neckline 只有 15.07%**。沒有 CLIP baseline | V（HTML）|
| **Fashion Florence**（2026-05，[arXiv 2605.09827](https://arxiv.org/abs/2605.09827)，模型 [anushreeberlia/fashion-florence](https://huggingface.co/anushreeberlia/fashion-florence) **MIT**）| Florence-2（0.77B）用 LoRA 在 3,688 筆 iMaterialist 上微調；material 準確率 63.0%（GPT-4o-mini 43.3%），style F1 0.753，JSON 合法率 99.8% | 模型 license V／數字 V（HTML 摘要）|
| **MODA General Attribute Suite**（2026-09，[arXiv 2609.13279](https://arxiv.org/abs/2609.13279)，[hopit-ai/Moda_ner](https://github.com/hopit-ai/Moda_ner) MIT；catalog/fullbody 權重是 CC BY-NC 4.0）| 監督模型 vs FashionCLIP 2.0：catalog track 0.8292 vs 0.6657。**Material 在 crop track 只有 0.41**。文中提到 Qwen3-VL-8B 在 crop track zero-shot 只有 0.1805（格式／標籤空間對不上的因素未知）| repo V／數字 U（HTML 摘要，沒逐表核對）|
| **Fashion compatibility benchmark**（[alifarzadjamali/fashion-compatibility-benchmark](https://github.com/alifarzadjamali/fashion-compatibility-benchmark)，README 寫 Apache-2.0）| 比較 7 種凍結表徵（CLIP L/14@336、SigLIP2、FashionCLIP 2.0、Marqo-FashionSigLIP、DINOv3…）＋PCA＋LR。「fashion 專用模型的好處不一致」| U（README 摘要）|

**結論（對 M4）**：
- 形狀類、顯著的元素（袖長、有無 logo、長度）CLIP 還算可以；**材質光澤（matte/glossy）、肩線結構、領口**這類細節，CLIP cosine 不可靠（OVAD／ARO 的證據，加上 MODA 的 material 0.41 顯示連監督模型都難）。
- **不能把 c(i,d) 當已知事實**。每個 d 要用 30–50 件人工標註檢查 AUROC，**AUROC < 0.7 的 d 從 M6 拿掉，或只當 soft prior**（U：門檻是工程建議）。

### 1.4 替代方案：VLM 離線結構化標註（4090）

| 模型 | License（HF API V）| 大小／硬體 | 用法 | 備註 |
|---|---|---|---|---|
| **Qwen3-VL-2B / 4B / 8B-Instruct** | **Apache-2.0** | 2B 在 CPU 上很慢但能跑（U）；8B 需要 4090 | 每件商品產生 JSON：`{shoulder: structured/soft/dropped/NA, surface: matte/sheen/glossy/NA, neckline: ..., logo_visible: bool}`；用 closed-vocab 約束解碼（`outlines`，[dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) Apache-2.0），取選項 token 的機率 → c(i,d)=P(yes)−P(no)，**NA 就 mask 掉** | 前面 2601.15711 的證據支持「VLM > CLIP embedding」，但它測的是 GPT/Gemini，不是 Qwen → 對 Qwen 是 U |
| Qwen2.5-VL-3B | **qwen-research（非商用）** | — | 避開 | V |
| Qwen2.5-VL-7B | Apache-2.0 | 4090 | 備選 | V |
| Florence-2-base / large | **MIT** | CPU 可 | 原生不是自由問答；要用 Fashion Florence（MIT）的微調權重才能輸出 JSON 屬性 | V |
| PaliGemma2-3b-mix | **Gemma license** | — | 條款比 Apache 麻煩，不建議 | V |
| moondream2 | Apache-2.0 | CPU 可 | CPU 備案 | V |
| Qwen3-VL-Embedding-2B | Apache-2.0（[arXiv 2601.04720](https://arxiv.org/abs/2601.04720)）| 4090 | M5 dense 的替代 embedding（和 Qwen3-VL-Reranker 同系列）| V |

**建議**：M4 做成 **hybrid**：`c(i,d) = applicability(i,d) · [α·VLM_prob + (1−α)·CLIP_antonym_softmax]`。只有 CPU 時先用 CLIP antonym；4090 到手後一晚跑完 VLM 標註（U：型錄 1–5 萬件、8B 大約每秒 2–5 張）。

---

## 2. Kansei 工程 × 深度學習／CLIP（M3）

| 項目 | 內容 | 可用性 | 驗證 |
|---|---|---|---|
| **Do VLMs Agree on the Affective Qualities of Shape?**（Bux et al.，2026-09，[arXiv 2608.25876](https://arxiv.org/abs/2608.25876)）| 用「正極 − 負極」的正規化文字 embedding 差當 Kansei 語意軸，把 3D 物件投影上去；6 個 VLM（CLIP、OpenCLIP、SigLIP2、ALIGN、FLAVA、Qwen3-VL-Embedding）。**情感軸的跨模型平均 rank 相關只有 0.36**（無關詞對 0.14，幾何控制軸 0.44），**強烈依類別而定**（0.51 vs 0.21）；**沒有和人類比對** | code「發表後釋出」（CC BY 4.0）→ 目前**不能跑**，但方法 5 行就能寫 | V（HTML）|
| **Kawaii style recognition**（Kansei＋DL，7,000 張女裝圖、每張 8 個 kawaii 評分；分類 84.45%，回歸平均誤差 0.42）| 單一情感維度的監督資料集；沒找到公開下載 | 只能當文獻依據 | U（ResearchGate 摘要）|
| **T-shirt Kansei image＋BPNN**（AUTEX Research Journal 2023，[DOI 10.1515/aut-2023-0007](https://www.degruyterbrill.com/document/doi/10.1515/aut-2023-0007/html)）| 經典流程：SD 問卷 → 參數化設計元素 → 神經網路映射 | 沒有 code | U |
| **LookBench**（2026-01，[arXiv 2601.14706](https://arxiv.org/abs/2601.14706)，CC BY 4.0）| 服飾檢索基準，abstract 提到 category–attribute taxonomy；搜尋摘要稱每個類別 10–25 個屬性，**含 style intent（elegant、street）** | 可以當 d 清單／風格詞彙的參考來源 | 基準 V／taxonomy 細節 U |
| **Aesthetics Based on Fashion Images**（Surrey）| 1,064 張圖、體型／上下身屬性、成對美感評比 | [kahlan.eps.surrey.ac.uk/featurespace/fashion](http://kahlan.eps.surrey.ac.uk/featurespace/fashion/) | U |

**公開的「情感服飾屬性」資料集很稀少**：沒找到可直接下載、同時標了 trustworthy／try-hard 這類 hidden need 的資料集。

**對 M3 的建議**：Kansei 傳統做法是用 **SD 評分 → 數量化 I 類（對設計元素做虛擬變數回歸）** 來估 K[n,d]。黑客松可行版本：團隊 3–5 人對 40 件商品做 5 個 need 的 SD 評分（約 1 小時），用 VLM 標好的 d 當自變數，跑 ridge 回歸得到 K̂_data，再和 GPT 填的 K_gpt 比較符號一致率（U：流程是我設計的）。另外可以用 2608.25876 的「兩極文字向量差」直接得到 **need 軸 zero-shot 分數** s(i,n)，當作 K 的 sanity check。

---

## 3. Query 端（ENGINE 01/03 → 02 的介面）

| 方法 | 論文 | Repo／License | CPU? | 工時 | 用途 | 驗證 |
|---|---|---|---|---|---|---|
| **HyDE** | [arXiv 2212.10496](https://arxiv.org/abs/2212.10496)（ACL 2023，U）| [texttron/hyde](https://github.com/texttron/hyde)，**無 license**；依賴 pyserini（Java）| 自寫：LLM 寫「理想商品描述」→ 編碼 → dense 查詢 | 1h | 把「怕看起來太用力」這類需求轉成可檢索的商品描述；**只當 dense 的一路**，和原 query 一起丟進 RRF | V |
| **Query2doc** | EMNLP 2023，[arXiv 2303.07678](https://arxiv.org/abs/2303.07678) | 無官方 code（U）| 自寫：`query ×5 + pseudo_doc` 串接後給 BM25 | 1h | abstract：BM25 在 MS-MARCO/TREC DL 提升 3–15%；**小 LM 幾乎沒幫助** → 要用強 LLM | V |
| **Query Rewriting for RAG（Rewrite-Retrieve-Read）** | [arXiv 2305.14283](https://arxiv.org/abs/2305.14283)（EMNLP 2023，U）| — | — | — | 概念參考 | 論文 V |
| **BEQUE**（Taobao 長尾 query 改寫）| WWW 2024 Industry，[arXiv 2311.03758](https://arxiv.org/abs/2311.03758) | 無 code | — | — | 電商 query 改寫的工業證據（改寫模型需要訓練，不直接用）| V |
| **NegBench** | CVPR 2025，[arXiv 2501.09425](https://arxiv.org/abs/2501.09425) | [m1k2zoo/negbench](https://github.com/m1k2zoo/negbench)，**MIT** | 評估 CPU 可、微調要 GPU | — | 證據：CLIP 類模型對否定**常常接近隨機**；合成否定 caption 微調後，否定查詢 recall 約 +10%（abstract）| V |
| **NegCLIP** | ICLR 2023（見 §1.3）| MIT | — | — | 同上 | V |

**否定處理結論**：**永遠不要把 "no visible logo" 丟進 CLIP 文字編碼器**。解析成 (1) M5 的硬性 exclude（metadata），或 (2) M6 的負向懲罰項 `−γ·c(i, visible_logo)`，而且查詢文字只保留正向片語。NegBench 的結果直接支持 PRD 現在「exclude constraint＋negative penalty」的設計，但要確保 dense query 字串裡**沒有**否定詞（U：工程建議）。

**多品項意圖**：「上班穿、要可信賴、配西褲的上衣」→ LLM 分解成 per-slot 子查詢 → 每個 slot 各跑一次 M5，最後組合時才用 compat。這和 xQuAD 的 sub-query 框架一致（§8）。

---

## 4. 檢索變體（M5）

| 元件 | 來源 | License／打包 | Windows / CPU | 評語 | 驗證 |
|---|---|---|---|---|---|
| **bm25s** | [arXiv 2407.03618](https://arxiv.org/abs/2407.03618)；[xhluca/bm25s](https://github.com/xhluca/bm25s) | **MIT**；PyPI 0.3.11 pure wheel | ✅ | `retrieve(..., weight_mask=np.ndarray)` 可以**直接吃硬過濾遮罩**（Context7 文件）；有 stemmer／stopwords。中文要自己切詞（jieba）再丟 token list（U）| V |
| **bge-m3 sparse（lexical_weights）** | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | **MIT**；`FlagEmbedding` 1.4.2 | CPU 可（568M，偏慢，U）| **多語**的學習式稀疏檢索，`return_sparse=True` → `compute_lexical_matching_score`。中英混雜的商品標題可以用它取代 BM25 | V |
| **SPLADE v3** | [naver/splade](https://github.com/naver/splade) | 模型 **CC BY-NC-SA 4.0** | — | 非商用 → 贊助商情境避開 | V |
| **OpenSearch neural sparse doc-v3-distill** | HF | **Apache-2.0** | CPU（inference-free query 端）| 英文限定的商用可行 SPLADE 替代品 | license V／「query 端免推論」U |
| **jina-clip-v2** | HF | **CC BY-NC 4.0** | — | 非商用，避開 | V |
| **Marqo-ecommerce-embeddings-L** | HF | **Apache-2.0** | GPU 較佳 | 電商通用 embedding，可以和 FashionSigLIP 做 dense 的 arm 比較 | license V／效能 U |
| **ColPali / ColQwen2.5** | [vidore/colqwen2.5-v0.2](https://huggingface.co/vidore/colqwen2.5-v0.2) MIT | 4090 | 為**文件頁面**設計；商品圖用多向量很浪費，**不建議** | license V／判斷 U |

### 向量儲存（Windows、要過濾）

| 選項 | License／PyPI | Windows | 過濾 | 評語 | 驗證 |
|---|---|---|---|---|---|
| **numpy / torch 暴力內積＋布林遮罩** | — | ✅ | 任意 | **型錄 ≤ 10 萬件時首選**：精確、零依賴、最好 debug；M4/M6 反正要整個矩陣 | U（規模門檻是估算）|
| **FAISS** | MIT；faiss-cpu 1.15.0 有 5 個 Windows wheel | ✅ | 只有 `IDSelector`，沒有 metadata 查詢語言 | 小型錄沒必要 | V（PyPI）|
| **LanceDB** | Apache-2.0；0.38.0 有 Windows wheel | ✅ | SQL `where` 前置過濾；內建 FTS＋**hybrid search＋`RRFReranker(k=60)`** | 想要「一個庫包辦 M5」就選它 | V（PyPI＋Context7）|
| **Qdrant local mode** | Apache-2.0；`QdrantClient(path=...)` 或 `":memory:"` | ✅（pure wheel）| payload filter | Context7 原始碼註解：**local mode 一律精確暴力搜尋**，HNSW 參數無效 → 等於 numpy，只是多了 API | V |
| **Chroma** | Apache-2.0；1.5.9 有 Windows wheel | ✅ | `where` metadata | 可行但沒有明顯優勢 | V（PyPI）|

**建議**：M5 = numpy dense＋`bm25s(weight_mask)`（或 bge-m3 sparse）＋`ranx.fuse(method="rrf")`。除非需要持久化／多人共用，否則不用 DB。

---

## 5. 融合與排序（M5→M6）

| 方法 | 來源 | License | 用途 | 驗證 |
|---|---|---|---|---|
| **ranx**：`fuse()` 支援 rrf、sum（CombSUM）、mnz（CombMNZ）、anz、min/max/med、wsum，以及 min-max／z-score 等 norm；`optimize_fusion(qrels, runs, norm, method, metric)` 會用網格搜尋學權重 | [AmenRa/ranx](https://github.com/AmenRa/ranx)；PyPI 0.3.21 | **MIT** | **M5 的 RRF vs CombMNZ vs 凸組合**一行切換；用 20–40 條 LLM-judge qrels 調 wsum 權重 | V（Context7 程式碼）|
| **Pairwise logistic（RankNet 線性版）**：在 `x_chosen − x_rejected` 上跑 `LogisticRegression(fit_intercept=False)`，係數限制非負（`scipy.optimize.nnls`，或 `positive=True` 的線性回歸變體）| 經典（Joachims 2002 RankSVM 的 logistic 版）| sklearn BSD | **M6 權重學習，而且保持可加** → 解釋依然成立；ENGINE 03 的 choice 回饋直接變訓練樣本 | U（標準做法，沒逐一查論文）|
| **Coordinate ascent**（Metzler & Croft）| RankLib（Java）| — | 直接最佳化 nDCG 的可加權重；Python 用 `ranx.optimize_fusion` 的網格搜尋就是低維替代 | U |
| **choix**（Bradley–Terry / Plackett–Luce）| [lucasmaystre/choix](https://github.com/lucasmaystre/choix) | **MIT**；pure wheel | 把 chosen ≻ not-chosen 轉成 item 或 feature 層級的效用 | V |
| **EBM（Explainable Boosting Machine）** | [interpretml/interpret](https://github.com/interpretml/interpret)；PyPI 0.7.8 | **MIT** | GAM：每個特徵一條形狀函數 f_k(x_k)，**f_k 就是解釋**；`monotone_constraints=[1,-1,0,...]` 可在建構子設定；官方 FAQ **建議事後用 isotonic 做單調化，避免相關特徵互相補償**（Context7）。排序要自己把問題轉成 pairwise 差值分類，或 pointwise 回歸 LLM-judge 分數（U）| V |
| **Neural RankGAM** | WSDM 2021，[arXiv 2005.02553](https://arxiv.org/abs/2005.02553) | TF-Ranking（Apache-2.0，**repo 已 archived**）| 直接用 ranking loss 訓練的 GAM、支援單調限制；TF 生態，2 天內**不建議** | V（repo archived 由 API 確認）|
| **Convex vs RRF** | Bruch TOIS 2023（前一輪）| — | 有少量標註時凸組合通常 ≥ RRF | 前一輪 |

**建議**：M6 **先用手調權重跑通，再用 pairwise logistic（非負）學權重**；EBM 當 P2 arm（標註太少時形狀函數會過擬合，U）。

---

## 6. 解釋（M7）

| 方法 | 論文 | Repo／License | 適用 | 驗證 |
|---|---|---|---|---|
| **可加模型的 Shapley** | — | — | 若特徵獨立、baseline = 候選平均，φ_k = w_k·(x_k − x̄_k)，**就是 z-score 貢獻本身**。M6 已經是這個形式 | U（標準推導）|
| **RankingSHAP**（listwise 歸因：解釋整個排序而不是單一分數）| SIGIR 2025，[arXiv 2403.16085](https://arxiv.org/abs/2403.16085) | [MariaHeuss/RankingShap](https://github.com/MariaHeuss/RankingShap)；**repo 沒有 LICENSE 檔**（搜尋摘要稱 GPL）| 概念重要：「為什麼是**這個順序**」vs「為什麼這件分數高」。另提出兩種**忠實度評估**範式，可以借來評 M7 | 論文 V／license U |
| **CountER** | CIKM 2021，[arXiv 2108.10539](https://arxiv.org/abs/2108.10539) | [chrisjtan/counter](https://github.com/chrisjtan/counter)，**無 license** | 最小擾動讓 item 掉出 top-K，就是 M7 的原型 | V |
| **LENS**（Necessity & Sufficiency 統一框架）| UAI 2021，[arXiv 2103.14651](https://arxiv.org/abs/2103.14651) | [limorigu/LENS](https://github.com/limorigu/LENS)，**CC0-1.0** | PN（拿掉會不會失去 top-5）＋ **PS（只留這個理由＋baseline，能不能進 top-5）**；也支援理由的**組合**（最小充分集合）| V |
| **ERASER** comprehensiveness / sufficiency | ACL 2020，[arXiv 1911.03429](https://arxiv.org/abs/1911.03429) | [jayded/eraserbenchmark](https://github.com/jayded/eraserbenchmark)，**Apache-2.0** | 改成排序版：comprehensiveness = 拿掉理由後排名下降的量；sufficiency = 只留理由時的排名。當成 **M7 的評估指標**而不是生成方法 | V |
| **對比解釋「why A not B」** | 可加模型的精確做法：`S(A)−S(B) = Σ_k w_k (x_k^A − x_k^B)` | 自寫 | 對 top-5 的每件 A，取 B = 第 6 名（或使用者上一輪選的商品），列出邊際正貢獻最大的項 | U（推導）|

---

## 7. 免訓練的搭配相容性（M6 compat）

| 方法 | 來源 | License | CPU | 用途 | 驗證 |
|---|---|---|---|---|---|
| **Polyvore（Maryland）** 類別共現統計 | [xthan/polyvore-dataset](https://github.com/xthan/polyvore-dataset) | Apache-2.0（repo；圖片版權另計，U）| ✅ | P(cat_b \| cat_a) 共現表 → compat 項（PRD 的做法）| V |
| **Polyvore Outfits（type-aware）** | [arXiv 1803.09196](https://arxiv.org/abs/1803.09196)（ECCV 2018）；[mvasil/fashion-compatibility](https://github.com/mvasil/fashion-compatibility) | **BSD-3-Clause**；HF 資料集 `mvasil/polyvore-outfits` | ✅ 統計；模型要 GPU | 有細類別，共現表更細 | repo V／venue U |
| **Loom**（anchor item → slot 限制的 FashionCLIP ANN → 6 項多目標打分：embedding 相似度、color harmony、formality、occasion、style direction、outfit 內多樣性；**從 CLIP 推斷材質厚重感**；occasion 的 vibe / anti-vibe 錨點向量）| 2026-05，[arXiv 2605.09830](https://arxiv.org/abs/2605.09830) | [anushreeberlia/loom](https://github.com/anushreeberlia/loom)，**MIT** | ✅ | **和 M6 幾乎同構的免訓練可加打分器**：620 件型錄上 outfit score 是 random 的 3.3 倍，違規率降 42%；消融顯示 direction reranking 不可或缺。**vibe/anti-vibe 錨點 ≈ Kansei need 軸**，可以直接抄 | V（abstract）／程式品質 U |
| **CLIP pairwise cosine 當 compat** | — | — | ✅ | 警告：相似 ≠ 相配（同色同款會得高分）。只適合當「風格一致性」項，不能當搭配度 | U |
| **fashion-compatibility-benchmark**（7 種凍結表徵＋LR head）| 見 §1.3 | Apache-2.0（README）| 要 CUDA 環境 | 4090 上「凍結 FashionSigLIP＋LR」是 minutes 級的輕訓練選項 | U |
| OutfitTransformer（owj0421）、TATTOO | 前一輪 | — | — | — | 前一輪 |

---

## 8. 多樣性（top-50 → 展示的 top-K）

| 方法 | 論文 | Repo／License | 工時 | 用途 | 驗證 |
|---|---|---|---|---|---|
| **MMR** | Carbonell & Goldstein SIGIR 1998 | 自寫 15 行 | 0.5h | sim 用 FashionSigLIP 圖像 cosine | U（經典，沒開頁）|
| **Fast greedy DPP MAP** | NeurIPS 2018，[arXiv 1709.05135](https://arxiv.org/abs/1709.05135) | [laming-chen/fast-map-dpp](https://github.com/laming-chen/fast-map-dpp)，**Apache-2.0**（numpy）| 1h | kernel `L = diag(q)·S·diag(q)`，q = exp(α·S(i))；支援滑動視窗 | V |
| **xQuAD**（顯式面向多樣化）| Santos et al. WWW 2010 | 沒找到維護中的 Python 套件 → 自寫 25 行 | 1h | **面向 = 設計元素群或 hidden need n**：P(aspect\|q) = p(n)，P(i\|aspect) = β_n 投影後的分數 → 同時涵蓋多個 need，而且「涵蓋了哪個 need」本身就是解釋 | 論文 U（搜尋結果列出，沒開頁）|

**建議**：xQuAD over needs 是**本題最有特色**的多樣化（和 p(n) 直接接上）；DPP 當視覺多樣性對照。

---

## 9. 回饋驅動的個人化（ENGINE 03 → 02）

| 方法 | 論文 | Repo／License | 用途 | 驗證 |
|---|---|---|---|---|
| **Rocchio for CLIP** | 前一輪 | — | query 向量更新 | 前一輪 |
| **LinUCB** | WWW 2010，[arXiv 1003.0146](https://arxiv.org/abs/1003.0146) | [fidelity/mabwiser](https://github.com/fidelity/mabwiser)，**Apache-2.0**（PyPI 2.7.4）| 候選的特徵向量 = M6 的 z-score 項；探索獎勵 | V |
| **Bayesian 可加權重（高斯先驗＋Laplace 近似的 logistic）** | 經典（Chapelle & Li 2011 TS 實證研究，U）| 自寫 30 行 numpy | **Δβ 的正規化版**：prior μ = Σ_n p(n)K[n,d]、Σ = σ²I；每個 choice (A≻B) 做一步 Laplace 更新；**Thompson sampling** 抽 β 來排序 → 自然探索＋不確定性可視化 | U |
| **Contextual dueling bandits／Feel-Good TS** | ICML 2024，[arXiv 2404.06013](https://arxiv.org/abs/2404.06013)（U）| — | 理論依據：線性效用＋成對偏好 | U |
| **choix** | 見 §5 | MIT | 離線把累積偏好擬合成 BT 分數 | V |

**建議**：PRD 的 adjust(±1) → Δβ 太粗。改成「**adjust 是 β_d 上的虛擬觀測**（高斯更新、固定步長 κ），choice 是 logistic 觀測」，兩種回饋共用同一個後驗 → 一致且可解釋（U）。

---

## 10. 消融研究 arm 清單（排好優先序）

評估設定（先做，約 3h）：**30–40 條情境 query**（帶 hidden need）×「top-50 union 用 LLM-judge 打 0–3 分，再人工抽查 20%」→ nDCG@10、Recall@50、need-coverage@5；解釋另外量 ERASER-式 comprehensiveness/sufficiency。**每個比較都跑 query 層級的配對 bootstrap / Wilcoxon，不看單次平均**。

| 優先 | Arm | 內容 | 改動模組 | CPU? | 工時（U）|
|---|---|---|---|---|---|
| **P0** | A0 | 硬過濾＋FashionSigLIP dense only | baseline | ✅ | 1h |
| **P0** | A1 | A0＋bm25s（或 bge-m3 sparse）＋`ranx` RRF(k=60) → top-50（= PRD M5）| M5 | ✅ | 2h |
| **P0** | A1b | 同 A1，但融合改成 z-norm wsum，權重用 `optimize_fusion` 在 train split 學 | M5 | ✅ | 0.5h |
| **P0** | A2 | A1＋M6 手調權重，c(i,d) = LLM 描述子平均 cosine、跨型錄 z（= PRD M4+M6）| M4/M6 | ✅ | 4h |
| **P0** | **A3** | A2 但描述子換成 **WaffleCLIP 隨機描述子**（類名／元素名保留）| M4 對照 | ✅ | 1h |
| **P0** | A4 | A2 但 c(i,d) = **反義詞成對 softmax**（CLIP-IQA 式）＋ DN 去均值＋ applicability mask | M4 | ✅ | 2h |
| **P0** | A5 | c(i,d) 內部驗證：每個 d 人工標 40 件 → AUROC(A2 vs A4 vs A6)；AUROC<0.7 的 d 剔除後重跑 | M4 gate | ✅ | 2h |
| **P1** | A6 | c(i,d) = **Qwen3-VL-8B 結構化標註機率**（outlines 約束）；或和 A4 混合 | M4 | 4090 | 4h＋一晚推論 |
| **P1** | A7 | M6 權重改成 **非負 pairwise logistic**（LLM-judge 對＋模擬 choice）| M6 | ✅ | 2h |
| **P1** | A8 | 解釋：M7 原版（zero-term＋rerank，top-5 necessity）vs **對比邊際（A vs 第 6 名）** vs **PN+PS（LENS 式）**；指標 = 有 ≥1 理由的 item 比例、comprehensiveness、sufficiency、穩定度（換一個 z-score 池的 Jaccard）| M7 | ✅ | 3h |
| **P1** | A9 | Query 端：原 query vs **LLM 結構化解析（否定 → exclude/penalty）** vs ＋HyDE 一路 | 前處理 | ✅（API LLM）| 2h |
| **P1** | A10 | 多樣化：無 vs MMR vs DPP vs **xQuAD over needs** | 後處理 | ✅ | 2h |
| **P2** | A11 | compat：Polyvore 共現 vs Loom 式 CLIP 錨點（formality/occasion）vs OutfitTransformer | M6 compat | ✅／GPU | 3h |
| **P2** | A12 | EBM（monotone）取代線性 M6 | M6 | ✅ | 3h |
| **P2** | A13 | 個人化：Rocchio vs 高斯-Laplace β 後驗＋Thompson（模擬使用者 10 輪）| 03→02 | ✅ | 3h |
| **P2** | A14 | Dense 換成 Qwen3-VL-Embedding-2B；加 Qwen3-VL-Reranker 當上限 | M5 | 4090 | 2h |

**2 天最小可行組合**：A0, A1, A1b, A2, **A3**, A4, A5, A8（CPU 全部可跑），4090 到了再補 A6。

---

## 11. M3–M7 批判與具體修法

### M3 — Kansei 表 K[n,d]（GPT 填初始值、人工修正）
**問題**
1. **LLM／VLM 的情感判斷本身不穩**：6 個 VLM 在 Kansei 軸上的跨模型 rank 相關只有 0.36，而且高度依類別而定（2608.25876，V）。GPT 填的 K 很可能「看起來合理、但符號不穩」。
2. K 和上下文無關：「structured shoulders → trustworthy」對西裝外套成立，對洋裝不一定 → **K 應該依類別而定**（至少 top/bottom/outer/dress 四組）。
3. n×d 格子太多，人工修正會流於形式。

**修法**
- GPT 用 **5 次取樣＋不同 prompt**填 K，取中位數；**變異數 v[n,d] 大的格子才給人修**。β 的先驗變異數 = v（接 §9 的 Bayesian 更新）。
- K 值限制在 {−1, −0.5, 0, 0.5, 1}，而且每格要附一句理由（M7 要用）。
- **資料校驗**：40 件 × 5 need 的 SD 評分 → ridge 回歸得到 K̂；報告 sign agreement(K_gpt, K̂)。
- need 軸的 zero-shot sanity check：`s(i,n) = cos(img, t(n+) − t(n−))`，檢查 Σ_d K[n,d]c(i,d) 和 s(i,n) 的相關。

### M4 — zero-shot 概念分數 c(i,d)
**問題**
1. **沒有對照組就無法證明描述子有語意**：WaffleCLIP 顯示隨機描述子的增益和 LLM 描述子相當（V）。
2. **CLIP 的屬性能力弱**：OVAD／ARO（V），材質類尤其難（MODA material 0.41，U）。
3. **applicability**：「肩線結構」對褲子沒有意義，但 z-score 仍會給它一個數值，而且可能很大；VLM 研究顯示 applicability 本身就是瓶頸（NA-F1 34.1%，V）。
4. 跨型錄 z-score 之後 M6 **又在候選內 z-score 一次** → 雙重標準化；候選集中所有商品都 matte 時，微小差異會被放大成 ±2σ。
5. 單極 cosine（"matte fabric"）混了「圖裡有沒有布料」、「照片風格」等干擾因子。

**修法**
- 每個 d 改成**雙極**：`c = softmax([cos(v, t_pos), cos(v, t_neg)]/τ)[0] − 0.5`，t_pos/t_neg 各用 2–3 個描述子（再乘 prompt ensemble）。τ 用 A5 的 40 件標註擬合一個標量（2303.12748 的思路）。
- **Embedding 先做 DN 去均值**（2302.11084），再計算；z-score 只做一次（**類別內、跨型錄**）。
- **applicability mask**：`a(i,d) ∈ {0,1}` 由類別規則表決定（肩線只給上衣／外套），或由 VLM 的 NA 輸出決定。
- **品質閘門**：d 的 AUROC < 0.7 就不進 M6（或權重乘 0.3）。**加上 A3 random-descriptor 對照**。
- 4090 可用時改成 VLM 機率＋CLIP 混合（§1.4）。

### M5 — 硬過濾＋dense＋BM25＋RRF(k=60) → top-50
**問題**
1. 代工商品標題常常是模板文字（款號、布料代碼），BM25 可能**噪音多於訊號**；中文沒切詞時 BM25 幾乎失效。
2. RRF 丟掉分數量級；只融合 2 路時，k=60 讓兩路名次差異被強烈壓平（名次 1 vs 10 的 RRF 差距很小）。
3. 如果先 ANN 再過濾（post-filter），會掉 recall。
4. 否定詞如果留在 dense query 裡會污染結果（NegBench，V）。

**修法**
- 用 `bm25s(weight_mask=filter_mask)` 做**前置過濾**；dense 用 numpy 全量內積＋同一個 mask（精確、不掉 recall）。
- 標題先正規化（去款號、展開布料代碼成自然語言），中文用 jieba，或者直接用 **bge-m3 sparse** 當 lexical 那一路。
- `ranx` 同時跑 RRF / CombMNZ / z-wsum（A1 vs A1b），用資料決定而不是寫死。
- query 解析時把否定移到 filter/penalty，dense 只編碼正向片語。
- top-50 夠用；但如果之後要做多樣化，**候選放大到 100** 會比較穩（U）。

### M6 — 可加 reranker（候選內 z-score）
**問題**
1. **候選內 z-score 讓解釋依賴候選池**：同一件商品換一個 query 池，「因為 matte」的貢獻就不一樣 → 解釋不穩；某一項變異接近 0 時會被放大。
2. **共線性、重複計算**：`sim`（FashionSigLIP 文字↔圖）和 `Σβ_d c(i,d)`（同一個 CLIP 空間）高度相關 → 貢獻分配任意，GPT 會把同一件事講兩次。
3. d 很多時 `Σ_d β_d c` 整體會壓過其他項（和 d 的數量成正比）。
4. 權重手調，無從驗證。
5. trend 項和 need 無關，容易變成主導因素，削弱「hidden need」的故事。

**修法**
- 標準化改成 **catalog-level robust scaling**（median/IQR，類別內），再**套固定的 clip [−3, 3]**；候選內只做平移（減候選均值），**不除候選 std**，並設 std 下限 ε。
- 概念項**先聚成 need 層級**：`need_n(i) = Σ_d K[n,d]·c(i,d)/‖K[n,·]‖₁`，M6 用 `Σ_n p(n)·need_n(i)`，並以 **need 為解釋單位**（使用者理解的是 "trustworthy"，不是 23 個元素）；元素層級只在下鑽時展示。
- 對 sim 做**殘差化**：`sim⊥ = sim − proj(sim | concept 項)`，或者就在 A7 用學到的非負權重，讓資料決定。
- 權重用 **非負 pairwise logistic**（A7）；EBM 只當 P2。
- 所有權重和 β 做 L1 正規化，同時報告每一項的平均 |貢獻| 比例（避免某一項暗中主導）。

### M7 — counterfactual necessity（zero 一項 → rerank → 掉出 top-5 才展示）
**問題**
1. **Overdetermination**：排第 1 的商品通常多項都強，拿掉任一項都不會掉出 top-5 → **最好的商品反而沒有理由可展示**；貼著第 5 名的商品則幾乎每項都「必要」。理由數量和排名呈反向關係，UX 會很怪。
2. 「zero 一項」其實是**對所有候選一起**把該項設為候選均值，也就是全域消融；其他商品同時變動，所以結果不是「這件商品本身的必要性」。
3. 只有 necessity（PN），沒有 sufficiency（PS）；也不處理「兩個理由合起來才必要」。
4. 對可加模型重跑 rerank 是多餘的：可以精確、封閉形式地計算。
5. 候選內 z-score 讓結果依賴候選池（見 M6-1）。
6. GPT 改寫可能加入沒通過檢查的內容（幻覺理由）。

**修法**
- **對比邊際版 necessity**：對 top-5 的 A，令 B = 第 6 名，`margin = S(A)−S(B)`；理由 k 必要 ⟺ `w_k(x_k^A − x_k^B) > margin`（精確，O(terms)，不用 rerank）。對第 1 名則用「A vs 第 2 名」解釋為什麼是第一。
- **最小充分集合（LENS 式 PS）**：依 `w_k(x_k^A − x̄_k)` 貪婪累加，直到 A 排名 ≤ 5 → 展示這個最小集合（≤ 3 項）。**每件 top-5 商品保證至少有 1 個理由**。
- 解釋單位 = need（M6 修法），外加 1 個具體設計元素當證據（K[n,d]·c(i,d) 最大的那個），並附上 M3 的一句理由。
- 評估（A8）：ERASER 式 comprehensiveness（移除理由後 A 名次下降）/ sufficiency，以及跨候選池的解釋 Jaccard 穩定度；RankingSHAP 的忠實度範式當參考。
- GPT 改寫限定**填模板＋禁止新增屬性**，再用字串比對確保提到的 d/n 都在通過清單中（U：工程防護）。

---

## 12. 授權速查（贊助商是商業公司 → 以商用可行為準）

| 可商用（V）| 非商用／受限（V）| 無 license 檔（只能讀、重寫，V）|
|---|---|---|
| WaffleCLIP (MIT)、Post-hoc CBM (MIT)、SpLiCE (Apache)、NegBench (MIT)、ARO/NegCLIP (MIT)、bm25s (MIT)、ranx (MIT)、interpret/EBM (MIT)、choix (MIT)、mabwiser (Apache)、fast-map-dpp (Apache)、ERASER (Apache)、LENS (CC0)、OVAD code (CC0)、Loom (MIT)、Moda_ner code (MIT)、fashion-compatibility (BSD-3)、polyvore-dataset repo (Apache)、LanceDB / Qdrant / Chroma (Apache)、FAISS (MIT)、outlines (Apache)、Qwen3-VL 2B/4B/8B (Apache)、Qwen3-VL-Embedding/Reranker-2B (Apache)、Qwen2.5-VL-7B (Apache)、Florence-2 (MIT)、fashion-florence (MIT)、moondream2 (Apache)、Marqo-FashionSigLIP (Apache)、Marqo-ecommerce-L (Apache)、FashionCLIP (MIT)、bge-m3 (MIT)、SigLIP2 (Apache)、opensearch neural sparse v3 (Apache) | jina-clip-v2 (CC BY-NC)、SPLADE v3 (CC BY-NC-SA)、Qwen2.5-VL-3B (qwen-research)、PaliGemma2 (Gemma)、OVAD 資料 (CC BY-NC-SA)、MODA catalog/fullbody 權重 (CC BY-NC)、CLIP-IQA (NOASSERTION) | LaBo、Label-free CBM、LM4CV、HyDE、CountER、DN、RankingSHAP（README 可能寫 GPL，U）|

---

## 13. 沒查到／仍不確定（誠實清單）

- Menon & Vondrick 官方 code 位置（U）。
- 沒找到**公開、可下載**的「服飾 × 情感／hidden need」標註資料集；kawaii 資料集未確認能否取得。
- CLIP 系模型在 iMaterialist／Fashionpedia **細粒度屬性 zero-shot** 的一手數字：這次沒從論文表格逐一核對（MODA 數字來自 HTML 摘要，U）。Fashionpedia repo（cvdfoundation/fashionpedia）GitHub API 顯示沒有 license 欄位。
- Qwen3-VL 在服飾屬性上的 zero-shot 表現沒有獨立的一手評測；MODA 提到 8B 在 crop track 只有 0.18，但原因（標籤空間、格式）不明 → **A6 一定要自己量**。
- xQuAD、MMR 原始論文頁面沒開（經典，U）。
