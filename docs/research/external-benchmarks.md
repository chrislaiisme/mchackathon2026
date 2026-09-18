# 外部公開基準測試：ENGINE 02 在業界／學界實際使用的資料集與指標上的表現

> 負責 agent：`bench`。日期 2026-09-18。伺服器 cfda4（Tesla V100-32GB ×3）。
> 新增檔案：`engine02/external.py`（各基準的**原始**指標定義）、`scripts/eval_external.py`（重現腳本）、
> `tests/test_bench.py`（21 項 HashEncoder 邏輯測試，本機與伺服器都通過）。
> 原始結果 JSON：`reports/agents/bench/`（不進 git），對應關係：
> `t2i_kagl.json`→§2.1、`t2i_kagl_bm25.json`→§2.1(c) 的 bm25／convex 列、`t2i_dfinshop.json`→§2.1b、
> `polyvore_compat.json`→§2.2、`esci_apparel.json`／`esci_all.json`→§2.3、`t2i_hm.json`→§2.4、
> `t2i_polyvore25k.json`→§2.4b、`attr_kagl.json`→§2.5。
> 每個 JSON 都含 `coverage`（語料是否涵蓋官方 GT）、每個系統的 mean＋bootstrap CI＋n，以及完整的配對檢定表。
> 伺服器工作目錄 `/tmp2/mzjiang/Research_Project/agents/bench/`（`marqo_bench/` 是 benchmark 的官方 GT 與 eval 原始碼）。
>
> **本文件的核心目的**：在此之前，`docs/engine02-design.md` 的所有數字都是用**我們自己**的商品庫、
> 自己合成的查詢、以及「資料集屬性當標準答案」的代理指標算出來的。這份文件改用
> **別人發布的資料集 + 別人發布的指標定義 + 別人發布的對照數字**，回答一個不同的問題：
> 「ENGINE 02 的元件放到公開排行榜上是什麼水準？」
>
> **最重要的警語先講**：可比性分三級，全文每個表格都標示。
> - **A 級（可直接比對）**：同一份**完整**語料、同一組官方查詢、同一個指標實作，且我們驗證過
>   官方 GT 的 gold 商品 100% 都在語料裡。本文屬於這級的是：
>   **Marqo KAGL text→image（§2.1）**、**Marqo DeepFashion-InShop text→image（§2.1b）**、
>   以及 **Marqo KAGL 屬性→商品的 dense 列（§2.5）**。
> - **B 級（同任務同指標，語料／切分不同）**：數量級可比，名次不可比。
> - **C 級（只在本文件內部可比）**：標準答案或負例是我們自己生成的，**不可**與論文數字並列。

---

## 0. 一頁結論

| # | 結論 | 證據 | 可比性 |
|---|---|---|---|
| 1 | **ENGINE 02 的 dense 檢索層＝公開排行榜上的開源 SOTA，而且我們在兩個完整語料上重現了排行榜。** KAGL 44,434 件：Marqo-FashionSigLIP R@1 **0.178**（公布 0.179）／R@10 **0.502**（0.489）／MRR **0.295**（0.293）。DeepFashion-InShop 52,591 件：**0.049**（0.050）／**0.247**（0.248）／**0.330**（0.330）。**兩個語料 × 三個模型 × 三個指標＝18 格公布數字，18 格全部落在我們的 95% CI 內**，其中 3 格完全相同。gold 覆蓋率都是 1.000。 | §2.1(a)、§2.1b | **A** |
| 2 | **`dense` arm 與純 encoder 逐條查詢完全相同**（Δ=0.0000，p=1.0）→ 我們的協定沒有暗改，數字可信。 | §2.1(c) | **A** |
| 3 | **Marqo-FashionSigLIP 在四個語料（KAGL 44k／DF-InShop 52k／H&M 20k／Polyvore 25k）上都顯著最好**（**八個檢定全部 p≤0.0004**）→ 維持預設，證據充分。**但修正設計文件 §3.3d 的一句話**：「時尚模型都勝過通用 CLIP」**不成立** —— fashion-clip 在四個語料上**沒有一次**勝過通用 laion-CLIP-ViT-B-16（KAGL 上顯著落後 −0.022，p=0.0065；另三個打平）。 | §2.4c | **A/C** |
| 3b | **`full_zclip3` 的 Recall@10 在四個語料上一致低於 `hybrid_rrf`**（KAGL −0.042、DF-InShop **−0.159**、H&M −0.024、Polyvore −0.026；全部 p≤0.0001），機制是 z 截斷在字面全命中時讓榜首同分。可重現的模式，已知邊界情況（**不改預設**，44k 內部實驗看不到）。 | §2.0、§2.1b、§2.4c | — |
| 4 | **「用商品描述當查詢」的 text→image 協定有嚴重字面洩漏**：光 BM25 就有 MRR@10 **0.969**（KAGL）／**0.996**（H&M）／**1.000**（DeepFashion-InShop，600/600 條查詢第 1 名就命中）。該類排行榜衡量的其實只是**影像編碼器**（協定禁止文件端用文字）。連帶地，**我們設計文件 §3.1 T1「用詞相同」欄的 0.82–0.87 是上界，不是實際水準**。 | §2.1(c)、§2.1b、§2.4 | — |
| 4b | **在真實零售目錄（H&M 20,491 件）上，Marqo-FashionSigLIP 的優勢更大**（R@1 +0.132 vs fashion-clip，p=0.0001）；而 **fashion-clip 與通用 laion 打平**（p=0.42）。 | §2.4 | **C** |
| 5 | **字面完全重疊時，把 dense 融進來會變差**：bm25 0.859 > convex 0.823 > RRF 0.517。RRF 用名次等權融合，會被平庸的一路稀釋。 | §2.1(c) | — |
| 6 | **真人標註下（ESCI，服飾切片 1,038 條＋完整 us/test 8,956 條），ENGINE 02 的可加總 rerank 是三種融合方式中最好的**：勝過 RRF（+0.005／+0.008）與凸組合（+0.009／+0.006），**四個檢定 p≤0.011**。**可解釋性在這裡不用付出排序代價。** | §2.3 | **B** |
| 7 | **「加 BM25 有沒有勝過純 dense」在兩個切片上結論相反**：服飾切片 −0.003（p=0.33）vs 完整集 **+0.003（p=0.0001）**。效果量一樣，差別只是檢定力。正確結論是「**小但穩定的 +0.003**」，不是任一單一切片的敘述 —— 又一次驗證「單切片會反號，一定要跨切片複核」。 | §2.3 | **B** |
| 8 | **穿搭：品類 NPMI 在同品類負例下準確率精確等於 0.250、AUC 精確等於 0.500**（零變異，依定義必然）。**OutfitTransformer 互補頭是最好的**：FITB 0.660（相容性頭 0.627，p=0.0017）；相容性 AUC 0.877 [0.867, 0.887]。 | §2.2 | **C** |
| 9 | **新增了 ENGINE 02 從未有過的相容性 AUC**，並把 FITB 從 n=200 擴到 n=2,000、兩種負例規則。 | §2.2、§3 | **C** |
| 10 | **對 ENGINE 01 的需求升級**：`retrieval_text_normalized` 這個布林旗標不夠，應改成回傳**詞彙覆蓋率連續值**，讓 ENGINE 02 依覆蓋率選融合策略（全命中→偏 BM25／convex；部分→dense 為主；不命中→純 dense）。 | §2.1(c)、§2.3、§5 | — |

---

## 1. 公開資料集盤點（Part 1）

盤點方式：不依賴 WebSearch。用 `curl` 打 HF `api/datasets`、`datasets-server.huggingface.co/{size,info,first-rows}`、
GitHub `api/repos` 與 `raw.githubusercontent.com`、arXiv API、OpenAlex API，並用 `curl -I` 確認匿名下載是否回 200。

標記：**V** = 本次工作實際抓到一個證明可匿名下載的 HTTP 200；**U** = 只有 README／論文聲稱，未實測；
**X** = 實測被擋（401/403/gated）。

> **盤點的執行方式與其可信度**：§1 的 URL 驗證由一個受委派的 helper agent 執行（約 46 次工具呼叫）。
> 我本人重新核對了**所有會進入 §2 實驗的項目**（Marqo 套件的列數／schema／GT 檔、ESCI 的下載路徑與
> 官方 baseline、Marqo 排行榜逐列數值），並在其中**抓到一處抄錯**（DeepFashion-InShop 的
> FashionCLIP2.0／laion 欄位被誤植為 Atlas 的數值，已修正，見 §1.3 註）。
> helper 的第一版也把「Myntra Kaggle 公開資料集需要帳號」判斷錯了，重新驗證後更正為可匿名下載。
> 沒有進入 §2 的項目（Fashionpedia、ModCloth／RTR、FEIDEGGER、H&M transactions 鏡像等）
> **我沒有二次核對**，請以 V/U 標記為準。

### 1.1 一覽表

| 資料集 | 出處（venue/年） | 授權 | 規模 | 可做什麼任務（該領域慣用指標） | 免帳號可達？ |
|---|---|---|---|---|---|
| **Marqo/KAGL** | Kaggle `paramaggarwal/fashion-product-images`（Myntra 商品照，無論文）；Marqo 重新封裝 | **MIT**（卡片標示；上游 Kaggle metadata 也是 MIT） | 44,434 列（= 完整資料集），12.67 GB | text→image 檢索（Recall@1/@10、MRR@10）＋6 個屬性→商品任務（P@1/P@10/MRR） | **V**（`gated:false`，parquet shard HTTP 200） |
| **Marqo/polyvore** | Maryland Polyvore（Han et al., ACM MM 2017, doi 10.1145/3123266.3123394）重新封裝 | **apache-2.0**（卡片自述不擁有資料） | 94,096 列，2.51 GB | text→image、category→product | **V** |
| **Marqo/fashion200k** | Fashion200k（Han et al., ICCV 2017, doi 10.1109/iccv.2017.163） | **apache-2.0**（上游自 Lyst.com 爬取，實際授權**不明**） | 201,624 列，3.47 GB | text→image、3 層 category→product | **V** |
| **Marqo/atlas** | Atlas（商品目錄） | **MIT** | 78,370 列，2.70 GB | text→image、sub-category→product | **V** |
| **Marqo/deepfashion-inshop** | DeepFashion In-shop（Liu et al., CVPR 2016, doi 10.1109/cvpr.2016.124） | **卡片無授權標籤 → 不明**；上游 DeepFashion 明文 **僅限研究、非商業**，需簽表單 | 52,591 列，**216 MB** | text→image、category2/3→product、color→product | **V**（但授權是本盤點中最弱的一組） |
| **Marqo/deepfashion-multimodal** | DeepFashion-MultiModal | 同上，**不明** | 42,537 列，153 MB | text→image、category2→product | **V** |
| **Marqo/iMaterialist** | iMaterialist Fashion | **不明** | 721,065 列，**71.5 GB** | 屬性→image（無 `text` 欄） | **V**（但今晚容量不允許） |
| **Amazon ESCI / Shopping Queries** | Reddy et al., arXiv:2206.06588；**KDD Cup 2022** | **Apache-2.0**（GitHub SPDX＋LICENSE 內文都確認）→ **本盤點授權最乾淨的一份** | Task 1 精簡版：48,300 查詢／1,118,011 筆人工評分（test 14,496 查詢／336,373 筆）；Task 2/3：130,652 查詢／2,621,288 筆 | Task 1 排序（**nDCG，gain E=1.0／S=0.1／C=0.01／I=0.0**）、Task 2 四分類、Task 3 替代品辨識（micro-F1） | **V**，但 parquet 在 GitHub 是 **git-LFS pointer**，`raw.githubusercontent.com` 只會給你 130 bytes。要用 `media.githubusercontent.com/media/...`（實測 200，examples 51,286,808 B／products 1,108,857,465 B） |
| **Polyvore Outfits（官方）** | Vasileva et al., **ECCV 2018**, arXiv:1803.09196 | **CC-BY-4.0**（HF `mvasil/polyvore-outfits`，DOI 10.57967/hf/10344），但限「學術與非營利」 | ~6 GB，含 `compatibility_*.txt`、`fill_in_blank_*.json`、disjoint／nondisjoint 兩種切分 | **FITB 準確率**、**相容性 AUC**（官方切分） | **X — gated**（匿名 HEAD 回 `401 GatedRepo`，`gated:"auto"` 所以申請即通過，但不是匿名） |
| **Polyvore Outfits（第三方重封裝）** | 同上，`owj0421/polyvore-outfits` ＋ `owj0421/polyvore`（圖片，251,008 列） | `other` → **不明** | FITB nondisjoint 53,306／5,000／10,000；compatibility 106,612／10,000／20,000 | 同上，**含官方負例清單** | **V**（`nondisjoint_fill_in_the_blank/test.json` 4,131,134 B, 200） |
| **Maryland Polyvore（Han 2017 原始）** | Han et al., **ACM MM 2017** | repo `xthan/polyvore-dataset` **Apache-2.0** | 21,889 套穿搭（17,316/1,497/3,076） | FITB、相容性 AUC（最早的協定） | **U／已壞**：只有 Google Drive，README 自述 polyvore.com 被 SSense 併購、圖片 URL 全失效 |
| **Fashion IQ** | Wu et al., **CVPR 2021**（arXiv 2019） | **CDLA**（README 明文，非 OSI 授權） | dress／shirt／toptee × train/val/test，相對描述成對 | 組合式檢索，慣用 **Recall@10 與 Recall@50**（三類平均） | **字幕與切分 V**（`raw.githubusercontent` 200）；**官方圖片 U／大量失效**（`ecx.images-amazon.com` 舊連結，repo 自帶 `broken_links/`）。可用替代：`mteb/mbeir_fashioniq_task7`（V，corpus 74,381／query 6,003／qrels 6,014，TREC 格式；授權**未標示**） |
| **H&M Personalized Fashion Recs** | Kaggle **競賽** 2022（無論文） | **僅競賽規則**（非商業、限競賽用途） | 31,788,324 筆交易／105,542 商品／1,371,980 顧客（經鏡像驗證，與官方數字一致） | 下一次購買推薦，慣用 **MAP@12** | **需帳號**（**因為它是競賽**：`api/v1/competitions/...` 匿名回 401）。**MAP@12 這件事我沒驗證成功**（Kaggle 頁面是 JS 渲染），標 **U**。非官方 HF 鏡像存在但**不等於取得授權** |
| **`tomytjandra/h-and-m-fashion-caption`** | 上述 H&M 商品照的第三方重封裝 | 卡片**未標授權 → 不明** | 20,491 列，~6.3 GB，欄位就是 `text` ＋ `image` | text→image 檢索（可直接套進 Marqo 式 harness，**零 schema 對應成本**） | **V**（`gated:false`）。**注意**：其他 H&M 鏡像是 transactions／articles，那是給 MAP@12 推薦用的，跟這份檢索語料不是同一件事 |
| **Myntra `paramaggarwal/fashion-product-images-dataset`（KAGL 真正的上游）** | Kaggle **公開資料集**（非競賽） | **MIT**（Kaggle API metadata） | 下載 bundle 1.30 GB（第一筆是 `fashion-dataset/.../images.csv`）；Kaggle metadata 另稱 totalBytes 15.7 GB — 兩者不符，推測是「主要壓縮版 vs 高解析變體」，**標 U** | text→image、屬性→商品（與 Marqo/KAGL 同一份 metadata） | **V — 可匿名下載**：`curl -L -o x.zip "https://www.kaggle.com/api/v1/datasets/download/paramaggarwal/fashion-product-images-dataset"` 回 200 / `application/zip` / 1.30 GB，無需驗證 |
| **DeepFashion** | Liu et al., **CVPR 2016**（1,938 引用） | **僅研究用途**，CUHK 表單 | ~80 萬張、50 類、1,000 屬性 | In-shop 檢索（Top-k 準確率）、屬性預測 | 原始 **U**（Google Drive／表單）；**V** 只透過 Marqo 鏡像 |
| **DeepFashion2** | Ge et al., **CVPR 2019**（352 引用） | **僅研究用途**，表單＋加密壓縮檔 | 491k 圖／801k 商品／873k 配對 | 偵測、分割、consumer-to-shop 檢索 | **U — 實質需表單**，找不到匿名路徑 |
| **Fashionpedia** | Jia et al., **ECCV 2020**, doi 10.1007/978-3-030-58452-8_19 | **CC-BY-4.0** | HF 鏡像 train 45,623／val 1,158，3.48 GB | 細粒度屬性＋實例分割（mAP）→ 可當**解釋層的屬性標準答案** | **V ×2**（官方 S3 `s3.amazonaws.com/ifashionist-dataset/...` 200；`detection-datasets/fashionpedia` 不 gated） |
| **Fashion200k（原始）** | Han et al., **ICCV 2017** | repo Apache-2.0，資料本身**不明** | >30 萬圖片 URL，濾後 ~20 萬 | 屬性改寫檢索（Recall@1/10/50） | 原始 **U**（Google Drive）；**V** 透過 `Marqo/fashion200k` |
| **Rent-the-Runway／ModCloth** | Misra, Wan, McAuley, **RecSys 2018**, doi 10.1145/3240323.3240398 | McAuley lab 條款：研究用途、須引用 | ModCloth ~83k／RTR ~192k 合身評語（**U**，未清點） | 尺碼／合身三分類（AUC、macro-F1）→ 對**解釋層**有用 | **V**：舊的 `cseweb.ucsd.edu` 路徑已 404，現址 `mcauleylab.ucsd.edu/public_datasets/data/{modcloth,renttherunway}/...json.gz` 回 200。無 HF 鏡像 |
| **Zalando FEIDEGGER** | Lefakis, Akbik, Vollgraf, **LREC 2018** | **MIT** | 單檔 7,776,633 B，~8.7k 洋裝 × 5 條德文描述 | 德文 text→image 檢索 | **V**（`FEIDEGGER_release_1.2.json` 200；常被引用的 1.1 已 404）。**只有德文**，對我們價值有限 |
| **Alibaba iFashion / POG** | Chen et al., **KDD 2019**, doi 10.1145/3292500.3330652（215 引用） | **無 LICENSE → 不明** | 論文稱 101 萬套穿搭／58.3 萬商品／357 萬使用者（**U**） | 個人化穿搭生成（Hit-rate／AUC／FITB） | **U — 視為已死**：repo `wenyuer/POG` 只有一個 README 指向 Google Drive；HF 搜 `ifashion` 零結果；圖片是阿里 CDN 連結 |
| **Farfetch／ASOS 爬取、RecSys/fashionXrecsys 挑戰賽** | 工作坊系列 | **僅競賽規則**（若還拿得到） | — | 依年份不同 | **U**：Farfetch（fashionXrecsys 2021）只透過報名發放，未公開鏡像。Myntra 的公開版本見上一列 |
| **`ashraq/fashion-product-images-small`** | 同 KAGL 上游，60×80 縮圖 | 卡片**未標授權** | 44,072 列，**271 MB** | text→image 煙霧測試 | **V** — 本盤點**最便宜**的真實語料 |

### 1.2 今晚（無帳號）真正能用的

1. **`Marqo/KAGL`** — 我們的 `data/catalog/kagl_full` 就是它的完整 44,434 列（見 §2.1 的覆蓋率驗證：官方 2,000 條查詢的 gold 商品**100% 都在我們語料裡**）。→ **可直接比對 Marqo 排行榜**。
2. **`Marqo/deepfashion-inshop`** — 216 MB，可在幾分鐘內建成完整語料。→ 第二個可比對的資料集。
3. **`amazon-science/esci-data`** — Apache-2.0，真人四級評分，唯一支援「nDCG + E/S/C/I gain」的資料集。
4. **`Marqo/polyvore`（我們只取了 25,000 列子集 → 只有 C 級可比性）**、`owj0421/polyvore-outfits`（官方 FITB／compatibility 清單，匿名可取）。
5. Fashionpedia、ModCloth／RTR、FEIDEGGER：可取，但**這次沒跑**（原因見 §4）。

6. **`tomytjandra/h-and-m-fashion-caption`（20,491 列）與 Myntra 官方 Kaggle bundle（1.30 GB，MIT）** — 見 §2.4。

**不能用**：Polyvore Outfits 官方 repo（gated）、H&M 官方競賽資料（需帳號＋接受競賽規則，且 MAP@12 未驗證）、
DeepFashion2、iFashion/POG（已死）、Farfetch/ASOS。

> **Kaggle 的一般規則（重要，不要過度推論）**：Kaggle **公開資料集**可以匿名下載 ——
> `curl -L "https://www.kaggle.com/api/v1/datasets/download/<owner>/<slug>"`（實測 Myntra 回 200）。
> Kaggle **競賽資料**不行（`api/v1/competitions/...` 匿名回 401）。
> **H&M 之所以要帳號，是因為它是競賽，不是因為「Kaggle 都要帳號」。**

### 1.3 Marqo 官方公布的對照數字（我實際打開的兩個來源互相一致）

來源：`raw.githubusercontent.com/marqo-ai/marqo-FashionCLIP/main/{README.md,LEADERBOARD.md}`（排行榜日期 2024-08-09）
與 `huggingface.co/Marqo/marqo-fashionSigLIP/raw/main/README.md`。

text→image，**逐資料集** Recall@1／Recall@10／MRR：

| 資料集 | Marqo-FashionSigLIP | FashionCLIP2.0 (`patrickjohncyh/fashion-clip`) | ViT-B-16-laion2b_s34b_b88k（通用 CLIP） |
|---|---|---|---|
| KAGL | 0.179 / 0.489 / 0.293 | 0.122 / 0.404 / 0.217 | 0.155 / 0.435 / 0.259 |
| Polyvore（全 94k） | 0.271 / 0.585 / 0.367 | 0.186 / 0.452 / 0.261 | 0.198 / 0.472 / 0.277 |
| **DeepFashion-InShop** | **0.050 / 0.248 / 0.330** | **0.039 / 0.175 / 0.259** | **0.039 / 0.185 / 0.267** |
| DeepFashion-Multimodal | 0.007 / 0.031 / 0.015 | 0.003 / 0.026 / 0.008 | 0.005 / 0.019 / 0.008 |
| Fashion200k | 0.111 / 0.378 / 0.187 | 0.057 / 0.221 / 0.103 | 0.062 / 0.230 / 0.108 |
| Atlas | 0.109 / 0.313 / 0.244 | 0.055 / 0.214 / 0.140 | 0.068 / 0.222 / 0.160 |
| **6 個資料集平均** | **0.121 / 0.340 / 0.239** | 0.077 / 0.249 / 0.165 | 0.088 / 0.261 / 0.180 |

（以上每一格我都回到 `LEADERBOARD.md` 原文逐列核對過。排行榜的欄位順序是
AvgRecall／Recall@1／Recall@10／MRR，很容易抄錯欄；本表只取後三欄。
DeepFashion-InShop 是唯一 **MRR 遠高於 Recall@10** 的資料集，因為它平均每條查詢有 6.7 個
相關商品（同一件商品的多個視角），Recall 的分母被撐大而 MRR 不受影響。）

**兩個對我們有直接意義的觀察**：
- Marqo 的 `Ks=[1,10]`，**整套 benchmark 沒有任何 nDCG**。要 nDCG@10＋分級相關性，只能靠 ESCI。這兩件事不要混講。
- Marqo 屬性任務的文件向量是 **0.9·image + 0.1·text 的固定凸組合**（`doc_weights`）。這是「可加總融合」在業界的一個可引用先例，但它是**固定權重的向量混合**，我們是**排序清單融合（RRF）＋可加總 rerank**，機制不同。
- 模型卡宣稱有「Marqo Fashion SigLIP **2**，MRR 與 recall 再 +78%」，但 **HF `Marqo` org 下並不存在**（枚舉過全部模型），需要聯絡業務。**我們可重現的上限就是 v1。**

---

## 2. ENGINE 02 在外部基準上的結果（Part 2）

### 2.0 先說清楚「測到的是什麼、測不到的是什麼」

**A. Marqo text→image 這個任務只測得到 ENGINE 02 的檢索與融合層。**
該任務的查詢是一句商品描述，**沒有**需求機率 p(n)、沒有錨點商品、沒有回饋、沒有趨勢關鍵字。
因此 `full_zclip3` 的可加總 rerank 在這裡只剩下 `w_dense·z(dense) + w_bm25·z(bm25)`（clip ±3）：
設計要素項 β_d 全為 0（`pipeline._terms` 會直接略過）、相容性項不啟用、懲罰項不啟用。
**所以本節不能用來證明 kansei／設計要素／穿搭相容性有效**，那些只有內部代理指標（設計文件 §3.3、§3.5c）。

實測驗證（KAGL 44k，查詢 `ADIDAS Women's Who Was That Yellow T-shirt`，列出第 1 名卡片的所有項）：

| arm | 實際生效的項（名稱, 權重, 貢獻） | 過濾後商品池 |
|---|---|---|
| `dense` | `dense` 1.0 → 0.1671 | 44,434（無硬條件） |
| `hybrid_rrf` | `dense` 1.0 → 0.0164；`bm25` 1.0 → 0.0164 | 44,434 |
| `full_zclip3` | `dense` 1.0 → **3.0**；`bm25` 0.5 → **1.5** | 44,434 |

設計要素、相容性、趨勢、懲罰四組項**一個都沒有出現**，證實上面的推論。
另外注意 `full_zclip3` 的兩項都**剛好頂到 ±3 的截斷上限**：查詢字面命中時 z 值遠超 3，
截斷後所有「完全命中」的商品分數相同 → **z-clip 會在榜首造出平手**。
這是 `full_zclip3` 在這個 benchmark 上可能不如 `hybrid_rrf` 的機制性原因（見 §2.1）。

**B. Marqo 協定的文件端只有圖片，而我們的 BM25 索引包含商品標題；而這個任務的查詢字串
就是商品標題本身。**
也就是說，`hybrid_rrf` 與 `full_zclip3` 在這個 benchmark 上是在做一件**比 Marqo 的題目簡單得多**的事
（字面完全重疊）。這個數字**不可以**和 Marqo 排行榜並列宣稱「我們贏了」。
它的正確讀法是：
1. 驗證 `dense` arm 確實等於 Marqo 的協定（實測完全相同，見 §2.1），
2. 量化「查詢用詞與商品庫一致時，混合檢索能拿到多少」的**上界**，這正是設計文件 §3.1 T1
   「用詞相同 vs 換句話說」那條結論在外部資料上的重演。

**B2. 本節完全沒有用到「模型補值」的屬性 —— 因此沒有自我一致（self-agreement）的風險。**
所有外部評測用的語料是 `kagl_full`（KAGL 原始 44,434 件，屬性全部來自資料集）、
`polyvore_big`、以及本次新建的 `dfinshop` 與 `hm_caption`（後兩者的屬性欄位全是 null）。
**沒有任何一項用 `kagl_polyvore_filled`。**
§2.5 的屬性→商品任務用的是 **Marqo 官方 GT 檔**，其標籤來自 KAGL 資料集原本的
`category2` / `baseColour` / `usage` 欄位，不是我們 `attribute_fill.py` 補的值。
（這一點值得特別寫出來：classify 分支踩過「用 Qwen3-VL 補了 `occasion`，再用 `occasion` 去評 Qwen3-VL」
的坑，去掉補值列之後結論會反號。本文件的設計從一開始就避開了這個問題，
因為外部基準的標準答案**必須**來自資料集本身才有意義。）

**C. 唯一的協定偏差（KAGL／DeepFashion-InShop 都有）**：我們的商品庫圖片是
`scripts/prepare_catalog.py` 產生的 **最長邊 384 px、JPEG q90**（每張約 4–10 KB），
Marqo 用的是原始 parquet 影像（KAGL 平均約 285 KB／張）。模型輸入都會被 resize 到 224，
但先壓到 384 再放大到 224 仍會損失細節，**這個偏差預期讓我們的數字略低，不會略高**。
其餘皆相同：同一份 44,434 件語料、同一份官方 2,000 條查詢 GT 檔、同一個指標實作
（Recall@k 分母 = |rel|、run 截斷在 top-10、MRR@10）、同一個 tokenizer
（marqo-fashionSigLIP 走 `open_clip`，與 Marqo 的 `models/open_clip_model.py` 相同；
fashion-clip 走 HF `AutoProcessor`，Marqo 用 `padding="max_length", max_length=77`，
我們用 `padding=True`，CLIP 在 EOT 位置取池化所以結果應相同）。

---

### 2.1 Marqo text→image：KAGL 44,434 件（**A 級：可直接比對排行榜**）

- **語料**：`data/catalog/kagl_full`，44,434 件 = `Marqo/KAGL` 的**完整**資料集。
- **查詢**：Marqo 官方 `data/KAGL/gt_query_doc/ground_truth_text-image.json`，2,000 條，平均每條 1.39 個相關商品（最多 20）。
- **覆蓋率驗證**：2,000 條查詢中，**2,000 條的 gold 商品全部都在我們的語料裡**（`gold_items_in_corpus = 1.000`）。
  這是「可直接比對」的前提，腳本每次都會重算並寫進結果 JSON。
- **指標**：Recall@1／Recall@10（分母 = 該查詢的全部相關商品數）／MRR@10，run 截斷在 top-10 —— 與 `eval.py` 完全一致。
- 統計：2,000 條查詢層級的 bootstrap 95% CI（10,000 次）與配對置換檢定（10,000 次符號翻轉）。

#### (a) 純 dense（＝ Marqo 的協定本身）vs Marqo 公布數字

| 模型 | 我們 Recall@1 [95% CI] | Marqo 公布 | 我們 Recall@10 [95% CI] | Marqo 公布 | 我們 MRR@10 [95% CI] | Marqo 公布 |
|---|---|---|---|---|---|---|
| **Marqo-FashionSigLIP**（我們的預設） | **0.178** [0.162, 0.195] | **0.179** | **0.502** [0.481, 0.523] | **0.489** | **0.295** [0.279, 0.313] | **0.293** |
| fashion-clip（＝排行榜的 FashionCLIP2.0） | 0.127 [0.113, 0.141] | 0.122 | 0.398 [0.378, 0.420] | 0.404 | 0.221 [0.206, 0.237] | 0.217 |
| laion-CLIP-ViT-B-16（通用 CLIP） | 0.149 [0.134, 0.165] | 0.155 | 0.432 [0.411, 0.453] | 0.435 | 0.250 [0.234, 0.266] | 0.259 |

> **九格公布數字全部落在我們的 95% CI 之內。**
> 這代表兩件事：(1) 我們的 encoder 串接方式沒有錯（tokenizer、lowercase、L2 正規化、相似度計算都對），
> (2) §2.0-C 說的「圖片壓成 384 px」在這個資料集上**沒有造成可測量的損失**。
> 這是本文件唯一一個可以說「ENGINE 02 的 dense 檢索層＝公開排行榜上的 SOTA 開源時尚模型」的地方。

#### (b) 三個 encoder 之間的配對檢定（n=2,000）

| A | B | Recall@1 差 [95% CI] | p | Recall@10 差 | p | MRR 差 | p |
|---|---|---|---|---|---|---|---|
| Marqo-FashionSigLIP | fashion-clip | **+0.051** [+0.035, +0.068] | 0.0001 | +0.104 [+0.084, +0.123] | 0.0001 | +0.074 [+0.060, +0.089] | 0.0001 |
| Marqo-FashionSigLIP | laion-CLIP-ViT-B-16 | **+0.029** [+0.013, +0.045] | 0.0004 | +0.070 [+0.051, +0.090] | 0.0001 | +0.046 [+0.032, +0.060] | 0.0001 |
| laion-CLIP-ViT-B-16 | fashion-clip | **+0.022** [+0.006, +0.038] | **0.0065** | +0.033 [+0.015, +0.051] | 0.0003 | +0.029 [+0.015, +0.043] | 0.0002 |

> **⚠️ 這裡修正了設計文件 §3.3d 的一句話。**
> `docs/engine02-design.md` §0 寫「時尚／SigLIP 系列**彼此無顯著差異**，但**都顯著勝過通用 CLIP**」。
> 在外部基準上這句話只對了一半：
> - 「Marqo-FashionSigLIP 最好」成立（勝過另外兩個，p≤0.0004）。
> - 但「時尚模型都勝過通用 CLIP」**不成立**：通用的 **laion-CLIP-ViT-B-16 顯著勝過時尚專用的
>   fashion-clip**（Recall@1 +0.022，p=0.0065），而且 Marqo 自己公布的數字也是這個方向（0.155 vs 0.122）。
> - 原本的結論之所以成立，是因為 §3.3d 拿來當「通用 CLIP」的是 **OpenAI CLIP ViT-B/32**（NDCG@5 0.334），
>   那是一個比 LAION ViT-B/16 弱很多的基線。**正確的說法是「選 Marqo-FashionSigLIP」，
>   而不是「時尚專用模型一定比通用模型好」。**

#### (c) ENGINE 02 各 arm（**C 級：字面洩漏，不可與排行榜並列**）

查詢字串**就是商品標題本身**，而我們的 BM25 索引包含標題 —— Marqo 的協定禁止文件端用文字，我們沒有這個限制。

| arm | Recall@1 [95% CI] | Recall@10 [95% CI] | MRR@10 [95% CI] | ms/查詢（V100，含 BM25） |
|---|---|---|---|---|
| `dense` | 0.178 [0.162, 0.195] | 0.502 [0.481, 0.523] | 0.295 [0.279, 0.313] | 224 |
| `hybrid_rrf` | 0.517 [0.496, 0.537] | **0.894** [0.881, 0.906] | **0.690** [0.673, 0.706] | 237 |
| `full_zclip3`（服務預設） | 0.515 [0.494, 0.535] | 0.852 [0.838, 0.867] | 0.679 [0.662, 0.696] | 222 |
| `hybrid_convex` | 0.823 [0.806, 0.840] | 0.992 [0.988, 0.996] | 0.945 [0.936, 0.953] | 220 |
| **`bm25`（只有關鍵字）** | **0.859** [0.843, 0.874] | **0.995** [0.992, 0.998] | **0.969** [0.962, 0.975] | 218 |

**三個結論：**

1. **`dense` arm 與純 encoder 的結果逐條查詢完全相同**（Δ = 0.0000，p = 1.0000，三個指標皆然）。
   這是協定正確性的機械式證明：ENGINE 02 的 dense 路徑**就是** Marqo 發布的那個協定，沒有暗改。
2. **這個 benchmark 的查詢有嚴重的字面洩漏**：光是 BM25 就有 Recall@1 = 0.859、MRR@10 = 0.969。
   任何把商品標題建索引的系統都能「解掉」它。**所以 Marqo 的排行榜衡量的其實只是影像編碼器的品質**
   （因為它的協定規定文件端只能用圖片），不是一個端到端商品搜尋系統的品質。
   反過來說，**我們設計文件 §3.1 T1「用詞相同」那一欄（混合檢索 0.82–0.87）同樣吃到這個效應，
   那個數字是上界，不是實際使用者會遇到的水準。**
3. **字面完全重疊時，把 dense 融進來反而會變差**：`bm25` 0.859 ≫ `hybrid_convex` 0.823 ≫ `hybrid_rrf` 0.517。
   RRF 用**名次**融合，會把一份接近完美的 BM25 排序和一份平庸的 dense 排序等權稀釋掉；
   convex 用**分數**融合，受害較小。這和設計文件 §3.1「用詞不一致時 BM25 只會帶進雜訊」是同一枚硬幣的兩面：
   **兩個訊號的品質差距越大，等權融合的代價越高。**
   對產品的意涵：ENGINE 01 回傳的 `retrieval_text_normalized` 這個旗標應該不只切換「開/關 BM25」，
   **還值得切換融合方式**（完全命中 → 偏 convex／純 BM25；完全不命中 → 純 dense）。
4. `hybrid_rrf` 與 `full_zclip3` 的 Recall@1 沒有顯著差異（+0.0016，p=0.127），
   但 `hybrid_rrf` 的 Recall@10（+0.042，p<0.0001）與 MRR（+0.011，p<0.0001）顯著較好。
   原因就是 §2.0 實測到的：**z-clip 把 dense 與 bm25 都壓到 +3 上限，所有「完全命中」的商品分數變得一樣，
   在榜首造出大量平手**。這個代價只在「查詢與標題完全一致」的極端情況出現，
   44k 內部實驗（§3.10：−0.006，p=0.65）看不到，因此**不建議因為這個數字就改掉服務預設**，
   但應該記錄成 `full_zclip3` 的已知邊界情況。

---

### 2.1b Marqo text→image：DeepFashion-InShop 52,591 件（**第二個 A 級語料**）

- **語料**：`Marqo/deepfashion-inshop` 完整 52,591 列，我們用 `scripts/eval_external.py build-catalog` 建成
  統一 schema（216 MB 下載、0 張失敗）。官方 2,000 條查詢的 gold **覆蓋率同樣 = 1.000**。
- 這份資料的查詢是**商品描述全文**（平均長很多），而且每條查詢平均有 **6.7 個**相關商品
  （同一件商品的多個視角），所以 Recall 的分母被撐大 → 絕對值天生就低，而 MRR 相對高。
- **⚠️ 授權**：HF 卡片未標授權，上游 DeepFashion 是**僅限研究、非商業**。→ **離線評測可以，不可出貨。**

| 模型 | 我們 Recall@1 [95% CI] | Marqo 公布 | 我們 Recall@10 [95% CI] | 公布 | 我們 MRR@10 [95% CI] | 公布 |
|---|---|---|---|---|---|---|
| **Marqo-FashionSigLIP** | **0.049** [0.045, 0.054] | **0.050** | **0.247** [0.233, 0.259] | **0.248** | **0.330** [0.312, 0.347] | **0.330** |
| laion-CLIP-ViT-B-16 | 0.038 [0.034, 0.042] | 0.039 | 0.185 [0.173, 0.196] | 0.185 | 0.265 [0.248, 0.282] | 0.267 |
| fashion-clip | 0.039 [0.035, 0.043] | 0.039 | 0.172 [0.161, 0.184] | 0.175 | 0.261 [0.244, 0.278] | 0.259 |

配對檢定：Marqo-FashionSigLIP > fashion-clip R@1 +0.011（p=0.0001）、MRR +0.069（p=0.0001）；
> laion R@1 +0.011（p=0.0001）、MRR +0.065（p=0.0001）；
**fashion-clip vs laion R@1 +0.001（p=0.66）、MRR −0.004（p=0.65）→ 又一次打平。**

> **第二次、也是更乾淨的一次重現**：九格公布數字全部落在 CI 內，其中 MRR 0.330／0.330、
> R@1 0.039／0.039、R@10 0.185／0.185 是**完全相同**。
> 兩個 A 級語料合計 **18 格公布數字、18 格都命中**，足以支撐「我們的 encoder 串接沒有問題」這個主張。

#### ENGINE 02 各 arm（**C 級**，600 條查詢子樣本）

這份資料的 BM25 每查詢要約 1 秒（52,591 篇長文 × ~50 個查詢詞），跑滿 2,000×4 需約 2 小時，
為了不佔用共用機器改用 **600 條查詢的子樣本**（`--limit-queries 600`，存 `t2i_dfinshop_arms.json`）。
**上面 encoder 那張表用的是完整 2,000 條官方查詢，未受此影響。**

| arm | Recall@1 [95% CI] | Recall@10 [95% CI] | MRR@10 [95% CI] | ms/查詢 |
|---|---|---|---|---|
| `hybrid_rrf` | 0.163 [0.154, 0.172] | **0.784** [0.764, 0.804] | 0.865 [0.842, 0.887] | 1015 |
| `full_zclip3` | 0.150 [0.141, 0.159] | 0.625 [0.599, 0.652] | 0.795 [0.766, 0.823] | 1003 |
| **`bm25`** | **0.206** [0.200, 0.213] | **0.952** [0.941, 0.963] | **1.000** [1.000, 1.000] | 984 |

- **BM25 的 MRR@10 = 1.000（600/600 條查詢的第 1 名就是相關商品）** —— 字面洩漏的最極端形式。
  Recall@1 只有 0.206 是因為分母是平均 6.7 個相關商品（同商品的多視角），不是因為排得差。
- **`hybrid_rrf` > `full_zclip3` 在三個指標上都顯著**（R@1 +0.013、R@10 **+0.159**、MRR +0.070，
  全部 p=0.0001）→ **第四個語料、也是差距最大的一次**，z 截斷造成榜首平手的機制再次確認。

---

### 2.2 Polyvore 穿搭相容性：FITB 準確率（4 候選）＋ 相容性 AUC（**C 級**）

- **語料**：`data/catalog/polyvore_big`，Maryland Polyvore（Han et al., ACM MM 2017）的 **25,000 件子集**。
- **模型**：`engine02/complete_look.py:FastOutfitTransformer`（owj0421 對 OutfitTransformer 的 CLIP 版重實作），
  兩顆頭都載入：`compatibility`（P(相容 | 整套)）與 `complementary`（互補檢索頭，−‖embed_query(其餘) − embed_item(候選)‖₂）。
- **為什麼是 C 級（三個理由，缺一不可地讓它不能跟論文並列）**：
  1. `Marqo/polyvore` **不含**官方的 `fill_in_blank_test.json` 與 `compatibility_test.txt`，
     所以**題目與負例都是我們自己生成的**（`engine02/external.py:{fitb_questions,compat_pairs}`，seed=0）。
  2. 我們的語料是 25,000 件子集，不是完整的 94,096 件，負例池比論文小 → 題目**偏簡單**。
  3. OutfitTransformer 的訓練資料是 Polyvore Outfits，**與本測驗的圖片可能重疊**（設計文件 §3.5c 已標注此風險）。
- **兩種負例規則**都跑：`random`（Han et al. 2017 式，從服飾池均勻抽）與
  `same_category`（Vasileva et al. 2018 式，同粗品類內抽，較難）。

#### (a) FITB 準確率（n=2,000 題，4 候選，隨機 25%）

| 打分方式 | `same_category` 負例 | `random` 負例 |
|---|---|---|
| 隨機對照 | 0.256 [0.236, 0.275] | 0.234 [0.216, 0.253] |
| 品類共現 NPMI（原 PRD） | **0.250** [0.250, 0.250] | 0.557 [0.539, 0.574] |
| 圖片 embedding 平均相似度 | 0.521 [0.499, 0.543] | 0.395 [0.373, 0.416] |
| OutfitTransformer 相容性頭 | 0.627 [0.607, 0.649] | 0.646 [0.625, 0.667] |
| **OutfitTransformer 互補頭**（`ot_cir`） | **0.660** [0.639, 0.681] | **0.721** [0.701, 0.740] |

配對置換檢定（n=2,000，`same_category`）：
互補頭 > 相容性頭 **+0.033** [+0.013, +0.054]，**p=0.0017**；
相容性頭 > embedding 相似度 **+0.107** [+0.081, +0.133]，p=0.0001；
embedding 相似度 > NPMI **+0.271**，p=0.0001；NPMI vs 隨機 **+0.006** [−0.014, +0.025]，**p=0.579（＝隨機）**。

**解讀：**
1. **設計文件 §3.5c 的結論在 10 倍題數下完全成立，而且更強**：
   NPMI 在同品類負例下準確率**剛好 0.250，CI 寬度為 0**（同品類分數完全相同，只能全部平手）——
   「品類層級相容性對『要搭我的牛仔褲』毫無作用」現在是一個**零變異的機械事實**，不是統計推論。
   OutfitTransformer 從 §3.5c 的 54.5%（n=200）提升到 **62.7%（n=2,000，CI 寬度從 ±7 pt 縮到 ±2 pt）**。
   （兩者題目抽樣規則略有不同 —— 舊腳本要求「扣掉被藏商品後仍有 ≥3 件服飾」，
   新版要求整套 ≥3 件 —— 所以不是同一批題目，但方向與量級一致。）
2. **互補頭（`ot_cir`）顯著勝過相容性頭**，兩種負例規則都成立（+0.033／+0.074，p≤0.0017）。
   這和 `docs/research/recsys-*.md` 裡「100 選 1 的 MRR 互補頭 0.277 > 相容性頭 0.216」是**同方向的獨立佐證**，
   而且這次是在 4 候選的**標準協定**上。→ **`POST /complete-look` 應該繼續用互補頭當預設。**
3. **負例規則會整個改變排名**：`random` 負例下 NPMI 跳到 0.557（因為隨機抽到的負例通常是別的品類，
   NPMI 一眼就能排除），而 embedding 相似度反而掉到 0.395。
   **任何引用「FITB 準確率」的數字，都必須同時說明負例怎麼抽的，否則無法比較。**

#### (b) 穿搭相容性 AUC（正例 2,000 套真實穿搭 vs 2,000 套逐件替換的假穿搭）

| 打分方式 | `same_category` 負例 | `random` 負例 |
|---|---|---|
| 品類共現 NPMI | **0.500** [0.482, 0.518] | 0.845 [0.832, 0.858] |
| 圖片 embedding 兩兩平均相似度 | 0.737 [0.722, 0.752] | 0.644 [0.627, 0.662] |
| **OutfitTransformer 相容性頭** | **0.877** [0.867, 0.887] | **0.872** [0.861, 0.882] |

配對 bootstrap（2,000 次重抽，`same_category`）：
OT > embedding 相似度 **+0.140** [+0.124, +0.155]，p=0.0005；
OT > NPMI **+0.377** [+0.357, +0.397]，p=0.0005。

**解讀：**
1. **這是 ENGINE 02 第一次有相容性 AUC 的數字**（之前完全沒有，見 §3 稽核表）。
2. **OT 是唯一對負例規則穩健的打分方式**（0.877 vs 0.872，幾乎不變）。
   NPMI 在同品類負例下**精確地等於 0.500**（依定義必然如此：替換後品類組成完全沒變），
   而 embedding 相似度在兩種規則下**方向相反**（0.737 → 0.644）——
   因為隨機替換會把不同品類的商品塞進來，反而讓「整套看起來不像一組」這件事被相似度以外的訊號主導。
3. **與論文數字的關係（務必照實說）**：Vasileva et al. (ECCV 2018) 在
   **Polyvore Outfits nondisjoint 官方切分、官方負例**上報 **AUC 0.86 / FITB 55.3%**
   （其官方 repo README 另稱改良後的預訓練模型可達 **0.88 / 57.6%**，我實際開啟該 README 確認）。
   我們的 0.877 / 62.7% **看起來相近甚至更高，但這是巧合，不構成任何比較**：
   不同資料集（Maryland 25k 子集 vs Polyvore Outfits）、**不同負例（我們自己生成）**、可能的訓練資料重疊。
   簡報上只能說「**我們的穿搭頭在一個自建但協定一致的測驗上，達到與文獻同一量級的水準**」。
   Han et al. (ACM MM 2017) 的 FITB／AUC 數字**我沒有開啟論文確認，因此本文件不引用**
   （只確認了其資料集規模 21,889 套：17,316／1,497／3,076）。

---

### 2.3 Amazon ESCI / KDD Cup 2022 Task 1：**真人分級標註**下的 nDCG@10（**B 級**）

這是本文件**唯一**用真人標註（不是資料集屬性代理、不是模擬使用者）的結果，也是對 ENGINE 02
排序層最強的外部檢驗。

- **資料**：`amazon-science/esci-data`（Apache-2.0），官方 Task 1 精簡版 **`split == "test"`、`product_locale == "us"`**。
- **切片**：用查詢字串的整字比對取服飾／鞋類子集（`engine02/external.py:APPAREL_QUERY_TOKENS`，
  65 個詞）→ **1,038 條查詢**，平均每條 ~23 個已標註候選商品。
  **這是一個啟發式，不是資料集標籤** —— ESCI 的商品沒有品類欄位。
- **任務**：對每條查詢的**已標註候選集合重排**，與 KDD Cup 2022 Task 1 的題型相同。
- **指標**：nDCG@10，gain **E=1.0 / S=0.1 / C=0.01 / I=0.0**，**線性** gain、discount 1/log₂(r+1)
  （`sklearn.metrics.ndcg_score` 形式，官方 baseline 用的就是這個；
  注意 `engine02/eval/metrics.py:ndcg_at_k` 用的是指數 gain 2^g−1，對小數 gain 會算出不同的數，
  `tests/test_bench.py` 有一條測試專門釘住這個差異）。
- **沒有圖片**：ESCI 只有文字，所以 dense 那一路改用文字編碼器 **`BAAI/bge-small-en-v1.5`**
  編 `product_title + brand + color + bullet_point`（截 512 字元），BM25 用 `engine02/sparse.py` 的同一個實作。

兩個切片都跑：**服飾切片 n=1,038** 與**完整 us/test n=8,956**（後者是官方 Task 1 測試集的全部 us 查詢）。

| 系統 | 服飾切片 nDCG@10（n=1,038） | 完整 us/test nDCG@10（n=8,956） |
|---|---|---|
| `bm25`（`engine02.sparse`） | 0.717 [0.705, 0.728] | 0.690 [0.686, 0.695] |
| `dense`（bge-small-en-v1.5） | **0.765** [0.754, 0.776] | 0.724 [0.720, 0.729] |
| `hybrid_rrf`（`engine02.fusion.rrf`, k=60） | 0.757 [0.746, 0.768] | 0.719 [0.715, 0.723] |
| `hybrid_convex`（α=0.5, min-max） | 0.753 [0.742, 0.764] | 0.722 [0.718, 0.726] |
| **`full_additive`（ENGINE 02 可加總 rerank，w_dense=1.0 / w_bm25=0.5）** | 0.762 [0.751, 0.773] | **0.728** [0.723, 0.732] |
| `full_additive_zclip3`（服務預設的 z 截斷） | 0.762 [0.752, 0.773] | 0.727 [0.723, 0.732] |

配對置換檢定（10,000 次符號翻轉）：

| A | B | 服飾切片 Δ（p） | 完整 us/test Δ（p） | 判讀 |
|---|---|---|---|---|
| `dense` | `bm25` | +0.048（0.0001） | +0.034（0.0001） | dense 顯著勝過 BM25 |
| `full_additive` | `hybrid_rrf` | **+0.005（0.0109）** | **+0.008（0.0001）** | **可加總 rerank 顯著勝過 RRF** |
| `full_additive` | `hybrid_convex` | **+0.009（0.0001）** | **+0.006（0.0001）** | 也顯著勝過凸組合 |
| `full_additive` | `dense` | −0.003（**0.3337**，CI 含 0） | **+0.003（0.0001）** | ⚠️ **兩個切片結論不同，見下方第 2 點** |
| `dense` | `hybrid_rrf` | +0.008（0.0133） | +0.005（0.0001） | RRF 比純 dense 差 |
| `full_additive` | `full_additive_zclip3` | +0.0002（0.2269） | ~0（n.s.） | z 截斷無影響（候選集只有 ~23 件，z 很少超過 3） |

**解讀：**

1. **在三種融合方式之間，ENGINE 02 的「z-score 可加總 rerank」是最好的那一個**，
   兩個切片、對兩個對手都顯著（p≤0.011）。這是可加總設計第一次在**真人標註**上拿到正面證據 ——
   而它的可加總性正是解釋層的基礎，等於「**可解釋性在這裡不用付出排序代價**」。
2. **⚠️ 「加 BM25 有沒有勝過純 dense」在兩個切片上結論相反，這件事本身才是重點。**
   - 服飾切片（n=1,038）：−0.003，p=0.33 → 看起來「打平甚至略輸」。
   - 完整 us/test（n=8,956）：**+0.003，p=0.0001** → 顯著勝出。
   - 效果量幾乎一樣（±0.003），差別只在**樣本數**：服飾切片的檢定力不足。
   **正確的結論是「可加總融合比純 dense 好約 +0.003 nDCG@10，效果很小但穩定」**，
   而不是任一個單一切片的敘述。
   → 這正好重演了本專案記憶裡那條教訓：**單輪／單切片的效果會反號，結論一律要配對統計＋跨切片複核。**
     本段是這條教訓在外部資料上的又一個實例。
3. **效果量很小（+0.003）要照實說**：BM25 對真實使用者查詢的邊際貢獻**非常有限**。
   原因與設計文件 §3.1 T1 同一條：ESCI 的查詢是真實使用者打的字（"mens black dress shirt"），
   和商品標題只是**部分**重疊，不像 §2.1／§2.4 那樣逐字相同。
3. **合併起來看 §2.1 與 §2.3，我們得到一條完整的曲線**：
   查詢與標題**逐字相同** → BM25 獨大（R@1 0.859），融合反而傷害；
   查詢**部分重疊**（真實使用者）→ dense 略勝，融合打平；
   查詢**換句話說**（設計文件 T1）→ BM25 只帶雜訊，必須關掉。
   **→ 對 ENGINE 01 的需求升級**：`retrieval_text_normalized` 這個布林旗標**不夠**，
   應該回傳「查詢詞彙對商品庫的覆蓋率」這個連續值，讓 ENGINE 02 據以選融合策略（見 §5）。
4. **與官方 baseline 的關係**：`amazon-science/esci-data` 的 README（我實際開啟）公布
   Task 1 baseline **nDCG = 0.83**，用的是**在 ESCI 上微調過的** MS MARCO cross-encoder
   （`cross-encoder/ms-marco-MiniLM-L-12-v2`），對**完整公開測試集**、以 Terrier 計算。
   我們的 0.765 是 **零樣本（沒有任何 ESCI 訓練）**、**只在服飾切片**、**只到 @10**。
   → **B 級：同一份資料、同一個 gain 定義、同一個題型，但不同子集與不同訓練條件，數字不可直接相減。**
   合理的說法是：「一個完全沒看過 ESCI 的零樣本混合檢索器，在服飾查詢上達到 0.765，
   官方微調 cross-encoder 在全集是 0.83。」

---

### 2.4 H&M 商品圖文檢索（`tomytjandra/h-and-m-fashion-caption`，**C 級**）

加跑這一份的理由：本任務的框架是「時尚公司實際會用的資料」，而 **H&M 是唯一一間真實零售商的商品目錄**
（KAGL 是 Myntra、Polyvore 是 UGC 穿搭、DeepFashion 是學術爬取）。

- **語料**：20,491 件，`text` + `image` 兩欄，0 張失敗，落地 325 MB。
- **⚠️ 為什麼是 C 級**：Marqo 的 benchmark **不包含**這份資料，所以**沒有官方 GT、也沒有任何可對照的公布數字**。
  查詢是我們自己抽的（`scripts/eval_external.py build-gt --n 2000 --seed 0`：
  隨機抽 2,000 個相異 `text`，gold = 所有 `text` 完全相同的商品；實測每條查詢**恰好 1 個** gold）。
  **只能在本表內部橫向比較。**
- **⚠️ 授權**：這是 H&M Kaggle 競賽圖片的第三方重封裝，HF 卡片**未標授權**。
  → **僅供離線評測，不可出貨、不可對外展示圖片。**

| 系統 | Recall@1 [95% CI] | Recall@10 [95% CI] | MRR@10 [95% CI] | ms/查詢 |
|---|---|---|---|---|
| dense: **Marqo-FashionSigLIP** | **0.385** [0.363, 0.406] | **0.759** [0.740, 0.777] | **0.503** [0.484, 0.521] | 169 |
| dense: laion-CLIP-ViT-B-16 | 0.262 [0.242, 0.281] | 0.628 [0.608, 0.649] | 0.371 [0.353, 0.389] | |
| dense: fashion-clip | 0.253 [0.234, 0.272] | 0.628 [0.607, 0.649] | 0.363 [0.345, 0.381] | |
| `hybrid_rrf` | 0.740 [0.720, 0.759] | 0.979 [0.973, 0.985] | 0.825 [0.811, 0.839] | 173 |
| `full_zclip3` | 0.739 [0.719, 0.758] | 0.955 [0.945, 0.964] | 0.818 [0.804, 0.832] | 171 |
| **`bm25`** | **0.992** [0.988, 0.996] | **1.000** [1.000, 1.000] | **0.996** [0.994, 0.998] | 179 |

配對檢定（Recall@1，n=2,000）：
Marqo-FashionSigLIP > fashion-clip **+0.132** [+0.110, +0.154]，p=0.0001；
> laion **+0.123** [+0.101, +0.146]，p=0.0001；
**fashion-clip vs laion +0.009 [−0.028, +0.011]，p=0.42（不顯著）**。
`dense` arm 再一次與純 encoder 完全相同（Δ=0.0000，p=1.0）。

**解讀：**
1. **Marqo-FashionSigLIP 在真實零售目錄上的優勢比 KAGL 更大**（R@1 +0.13 vs KAGL 的 +0.05）。
   這是「選它當預設」最貼近業務場景的一項證據。
2. **fashion-clip 與 laion 打平（p=0.42）**。合併 §2.1(b)（KAGL 上 laion **顯著勝過** fashion-clip）看，
   結論是：**「時尚專用」本身不保證更好，重點是那一個具體的模型。**
3. **BM25 拿到 Recall@1 = 0.992、MRR = 0.996** —— 這份資料的每個 caption 都是唯一的，
   而 caption 就是查詢，所以關鍵字比對幾乎必然命中。
   **這把 §2.1 結論 4 推到極致：「用商品描述當查詢」的 text→image 協定，
   對一個會索引商品文字的真實系統而言是個已解決的問題；它只能用來評比影像編碼器。**
   我們的 demo 絕對不能拿這類數字宣稱系統效能。

---

### 2.4b Marqo text→image：Polyvore **25,000 件子集**（**C 級 —— 語料只有官方的 27%**）

- 官方 Polyvore 語料是 94,096 件，我們只有 25,000 件（`data/catalog/polyvore_big`）。
- 因此 2,000 條官方查詢中**只有 527 條**的 gold 商品在我們語料裡（`gold_items_in_corpus = 0.264`），
  腳本用 `--require-gold` 只評這 527 條。
- **語料越小，題目越簡單** → 我們的 R@1 0.395 vs Marqo 在完整 94k 上公布的 0.271。
  **這個差距不是我們比較好，純粹是語料只有 27%。** 放在這裡的唯一用途是第三次驗證 encoder 排序。

| 系統 | Recall@1 [95% CI]（n=527） | Recall@10 | MRR@10 |
|---|---|---|---|
| dense: Marqo-FashionSigLIP | **0.395** [0.353, 0.436] | 0.725 [0.685, 0.763] | 0.503 [0.467, 0.540] |
| dense: laion-CLIP-ViT-B-16 | 0.309 [0.271, 0.349] | 0.641 [0.602, 0.683] | 0.408 [0.373, 0.444] |
| dense: fashion-clip | 0.290 [0.252, 0.330] | 0.620 [0.581, 0.660] | 0.393 [0.358, 0.430] |
| `hybrid_rrf` | 0.713 [0.676, 0.751] | 0.958 [0.939, 0.975] | 0.792 [0.763, 0.821] |
| `full_zclip3` | 0.713 [0.676, 0.751] | 0.932 [0.909, 0.953] | 0.788 [0.758, 0.817] |

### 2.4c 三個語料彙整：encoder 的選擇有多穩？

| 比較（Recall@1 差，配對置換檢定） | KAGL 44k (n=2,000) | DF-InShop 52k (n=2,000) | H&M 20k (n=2,000) | Polyvore 25k (n=527) |
|---|---|---|---|---|
| **Marqo-FashionSigLIP − fashion-clip** | **+0.051**（p=0.0001） | **+0.011**（p=0.0001） | **+0.132**（p=0.0001） | **+0.104**（p=0.0001） |
| **Marqo-FashionSigLIP − laion-ViT-B-16** | **+0.029**（p=0.0004） | **+0.011**（p=0.0001） | **+0.123**（p=0.0001） | **+0.085**（p=0.0001） |
| laion-ViT-B-16 − fashion-clip | **+0.022**（p=0.0065） | −0.001（p=0.66，n.s.） | +0.009（p=0.42，n.s.） | +0.019（p=0.34，n.s.） |

**這張表是本文件對「encoder 該選誰」最完整的答案：**
- **Marqo-FashionSigLIP 在四個語料上都顯著最好**（**八個檢定全部 p≤0.0004**）→ **維持現行預設，證據充分。**
- **fashion-clip 在四個語料上沒有任何一次勝過通用的 laion-CLIP-ViT-B-16**（一次顯著落後、三次打平）。
  → 設計文件 §3.3d「時尚模型都勝過通用 CLIP」**需要修正**（見 §0 第 3 點）。
- **`full_zclip3` 的 Recall@10 在三個有跑 arm 的語料上都低於 `hybrid_rrf`**
  （KAGL −0.042、H&M −0.024、Polyvore −0.026），原因一致（z 截斷在字面全命中時造成榜首平手）。
  **這是可重現的模式，不是雜訊。**

### 2.5 Marqo「屬性→商品」任務：KAGL（**A 級（dense 列）／C 級（arm 列）**）

這組任務的查詢是**一個屬性值**（`Topwear`、`Navy Blue`、`Formal`…），不是商品標題，所以比 §2.1 更接近
ENGINE 02 實際會收到的輸入。指標是 **P@1 / P@10 / MRR@10**（Marqo 排行榜用 Precision 而非 Recall，
因為每個屬性值對應成千上萬件商品）。

**⚠️ n 非常小**：GT 每個屬性值只有一條查詢 → `category2` n=45、`baseColour` n=46、`usage` **n=8**。
Marqo 的排行榜也是這個 n。**所有 CI 都很寬，任何「差 0.05」的比較都不該當結論。**

Marqo 的文件向量是 `0.9·image + 0.1·text` 的固定凸組合；我們照做當對照組，另外列純圖片與 ENGINE 02 的 arm。

| 任務 | 系統 | P@1 [95% CI] | Marqo 公布 P@1 | P@10 | 公布 | MRR | 公布 |
|---|---|---|---|---|---|---|---|
| **sub-category**<br>(n=45) | `0.9img+0.1txt`（＝Marqo 協定） | 0.689 [0.556, 0.822] | **0.711** | 0.684 | **0.687** | 0.745 | **0.756** |
| | 純圖片 | 0.667 [0.533, 0.800] | — | 0.664 | — | 0.748 | — |
| | `hybrid_rrf` | 0.756 [0.622, 0.867] | — | 0.678 | — | 0.813 | — |
| | `full_zclip3` | **0.800** [0.667, 0.911] | — | 0.713 | — | 0.830 | — |
| **colour**<br>(n=46) | `0.9img+0.1txt` | 0.522 [0.370, 0.652] | **0.587** | 0.509 | **0.502** | 0.618 | **0.664** |
| | 純圖片 | 0.370 [0.239, 0.522] | — | 0.407 | — | 0.489 | — |
| | `hybrid_rrf` | **0.957** [0.891, 1.000] | — | 0.852 | — | 0.975 | — |
| | `full_zclip3` | 0.935 [0.870, 1.000] | — | 0.854 | — | 0.953 | — |
| **usage**<br>(n=8) | `0.9img+0.1txt` | **0.375** | **0.375** | **0.400** | **0.400** | **0.438** | **0.438** |
| | 純圖片 | 0.250 | — | 0.325 | — | 0.281 | — |
| | `hybrid_rrf` / `full_zclip3` | 0.500 | — | 0.438 / 0.512 | — | 0.525 | — |

**解讀：**
1. **第二次重現成功**：`usage` 三個指標與 Marqo 公布數字**完全相同**（0.375 / 0.400 / 0.438），
   `sub-category` 與 `colour` 的公布值也都落在我們的 95% CI 內。
2. **Marqo 的 0.9img+0.1txt 混合確實有用**：純圖片 → 加 10% 文字，colour 的 P@1 從 0.370 → 0.522。
   這是「把文字訊號混進來」在**向量層**的作法；ENGINE 02 在**清單層**（RRF／可加總）做同一件事。
3. **顏色任務上 ENGINE 02 的 arm 大勝（0.957 vs 0.522）—— 但這又是字面洩漏**：
   KAGL 的標題本來就寫著顏色（"U.S. Polo Assn. Men **Navy Blue** Shoes"），BM25 直接命中。
   這說明的是「**有結構化屬性時就該用過濾／關鍵字，不要叫影像編碼器去猜顏色**」，
   而這正是 ENGINE 02 §2 架構「硬條件用過濾、不進分數」的既有設計。
4. `sub-category` 的差距（0.800 vs 0.689）比較小也比較誠實，因為子類名稱（`Topwear`）
   不一定逐字出現在標題裡。但 n=45、CI 重疊，**不宣稱顯著**。

---

## 3. 指標覆蓋度稽核（Part 3）

這個任務族（時尚檢索／推薦／穿搭相容性／對話式推薦／可解釋推薦）的經典論文用的指標，以及 ENGINE 02 的狀態：

| 指標 | 誰在用（代表出處） | ENGINE 02 狀態 | 位置 / 原因 |
|---|---|---|---|
| **Recall@K** | Fashion IQ（R@10/@50）、Fashion200k、Marqo benchmark（R@1/@10） | **原本有（部分）＋本次補齊並實際報出** | 原本 `engine02/eval/metrics.py:recall_at_k` 存在，但**沒有任何實驗真的報它**。本次新增 Marqo 協定的 Recall@1／@10（trec_eval 分母＝\|rel\|、run 截斷 top-10），`engine02/external.py:marqo_t2i_metrics`，在 §2.1／§2.4 三個語料上報出 |
| **nDCG@K** | 幾乎所有排序論文；ESCI／KDD Cup 2022 Task 1 | **原本有，本次補上第二種 gain** | `metrics.py:ndcg_at_k` 用指數 gain (2^g−1)。ESCI 的 gain 是小數（1.0/0.1/0.01），官方 baseline 用 `sklearn.ndcg_score` 的**線性** gain → 本次新增 `external.py:ndcg_linear`，並在測試中驗證兩者**不相等** |
| **MRR** | Marqo benchmark、P-Companion 類補配任務 | **原本有＋本次補上截斷語意** | `metrics.py:mrr` 是全排名 MRR；Marqo 只取 top-10，所以公布的其實是 **MRR@10**。`external.py` 用 run 長度截斷來對齊 |
| **MAP@K** | **H&M Kaggle（MAP@12）**、傳統 CF 文獻 | **仍缺** | 需要真實購買／點擊序列當標準答案。我們沒有互動日誌，H&M 官方資料需 Kaggle 帳號（§1.1），而且我連「官方指標是 MAP@12」都沒能從 Kaggle 頁面驗證。用模擬使用者算 MAP@12 只會量到自己的模擬器 |
| **HitRate@K** | 穿搭生成（POG, KDD 2019）、序列推薦 | **有** | `metrics.py:hit_at_k`（`scripts/eval_concept_image.py` 在用）；T5 的「成功率」本質也是 HitRate@5 |
| **FITB 準確率（4 候選）** | Han et al. ACM MM 2017、Vasileva et al. ECCV 2018、OutfitTransformer (WACV 2023) | **原本有（n=200）＋本次擴充** | 原 `scripts/eval_compat_fitb.py` 只有 200 題、單一負例規則。本次 n=2,000、**兩種負例規則**（Han 式隨機／Vasileva 式同品類）、加入互補頭、配對置換檢定 |
| **相容性 AUC** | Han 2017（0.90）、Vasileva 2018（0.86/0.88） | **本次新增** | 之前完全沒有。`external.py:compat_pairs` + `auroc` + `paired_auc_delta_test`，整套穿搭打分（而非錨點→候選）。**負例是我們生成的**（官方 `compatibility_test.txt` 不在 `Marqo/polyvore` 裡）→ **C 級可比性** |
| **ILD / α-nDCG / 近似重複率** | MMR (SIGIR 1998)、DPP (NeurIPS 2018 / YouTube CIKM 2018)、xQuAD | **有** | `engine02/diversify.py:{ild,alpha_ndcg,near_duplicate_rate}`，結果在 `docs/research/recsys-slate.md`。**自我參照警語已寫在該文件**（α-nDCG 用我們自己的 K 表，xQuAD 直接最佳化它） |
| **coverage / novelty（目錄覆蓋、冷門度）** | 多樣性文獻標配 | **仍缺** | novelty 幾乎都定義成「1 − 熱門度」或負對數流行度，需要互動頻次。我們的商品庫**沒有任何曝光／購買次數**，價格欄位也是 null。目錄覆蓋率（一組查詢共觸及多少 distinct 商品）技術上可算，但沒有查詢分布可以說它代表什麼 |
| **comprehensiveness / sufficiency（解釋忠實度）** | ERASER (ACL 2020)、CountER (CIKM 2021) | **有** | `engine02/eval/tasks.py:t4_faithfulness`，即設計文件 §3.4 的「拿掉理由就掉出前 5」＝comprehensiveness、「只留理由仍在前 5」＝sufficiency，並附隨機理由對照組 |
| **校準 ECE** | 校準文獻；推薦系統中用於機率輸出 | **部分有** | `engine02/attribute_fill.py:ece` 有實作，但**只用在屬性分類器**（`scripts/eval_classify.py`）。**排序分數與 p(n) 需求機率都沒有校準評估** → 因為兩者都沒有機率語意（加總分數不是機率），要報 ECE 必須先定義一個校準目標，目前沒有標準答案可以定 |
| **SR@t（對話式推薦第 t 輪成功率）** | EAR (WSDM 2020)、CRS 文獻 | **有** | 設計文件 §3.5 的 T5 就是 SR@1..4（`eval/tasks.py:t5_feedback`）。**但使用者是規則式模擬器**，不是真人，不能當成真實 SR |
| **Precision@K** | Marqo 的屬性→商品任務 | **本次新增** | `external.py:marqo_attr_metrics`（P@1/P@10 依 Marqo 的 k 為分母定義） |

### 3.0 本次實際新增的指標實作（都在 `engine02/external.py`，都有測試）

| 函式 | 重現的是誰的定義 | 測試（`tests/test_bench.py`） |
|---|---|---|
| `marqo_t2i_metrics` | marqo-FashionCLIP `utils/metrics.py`（BEIR/pytrec_eval）＋ 其自訂 MRR | `test_recall_denominator_is_all_relevant_docs`、`test_mrr_is_truncated_at_the_run_length` |
| `marqo_attr_metrics` | 同上，屬性任務改報 P@k | `test_precision_metric_for_attribute_tasks` |
| `rank_ids` | trec_eval 式的確定性排序（分數→id 破平手） | `test_rank_ids_is_deterministic_under_ties` |
| `ndcg_linear` | ESCI／KDD Cup 2022 Task 1 的線性 gain nDCG（`sklearn.ndcg_score` 形式） | `test_ndcg_linear_matches_hand_computation`、`test_ndcg_linear_differs_from_exponential_gain_version` |
| `fitb_questions` / `fitb_hit` | Han 2017（random 負例）／Vasileva 2018（同品類負例）的 FITB 協定 | 4 條（題目結構、負例規則、可重現性、平手拆分） |
| `compat_pairs` | 同上兩篇的相容性負例生成（逐件替換，正負例套數與尺寸分布相同） | `test_compat_pairs_are_paired_and_substituted` |
| `auroc` / `bootstrap_auc_ci` / `paired_auc_delta_test` | Mann–Whitney U（平手 0.5）＋配對 bootstrap 檢定 | 3 條 |

### 3.1 仍缺的三項與理由（總結）

1. **MAP@K**：缺真實互動日誌（H&M 需帳號；我們的商品庫無交易資料）。
2. **coverage / novelty**：缺曝光／購買頻次，novelty 的定義無法落地。
3. **排序分數與需求機率的 ECE**：缺機率語意與校準標準答案；硬要報會是自我參照。

（以上三項都不是「忘了做」，而是**沒有可信標準答案**。簡報上應如此說明，而不是留白。）

---

## 4. 沒跑的與原因

本次**實際跑了 6 個外部評測**：Marqo text→image ×4 語料（KAGL、DeepFashion-InShop、H&M、Polyvore 子集）、
Marqo 屬性→商品 ×3 任務、Polyvore FITB／相容性 AUC、ESCI nDCG@10 ×2 切片。以下是**沒跑**的：

- **Marqo/fashion200k（201,624 列）、Marqo/atlas（78,370 列）、Marqo/iMaterialist（71.5 GB）**：
  下載＋逐張編碼的成本超出今晚配額（`/tmp2` 只剩 ~150 GB，且須在使用完畢後清空）。
  Fashion200k／Atlas 的 GT 檔已下載在 `agents/bench/marqo_bench/data/`，只要有 GPU 時段就能照 §2.1 的同一條指令跑。
- **Fashion IQ（Recall@10/@50）**：官方圖片連結大量失效，可行路徑是 `mteb/mbeir_fashioniq_task7`（74,381 張語料）。
  但 Fashion IQ 是**組合式檢索**（參考圖＋相對描述），對應的是 ENGINE 02 的 `composed.py`（T8），
  不是本次的檢索主線；而且該鏡像**未標授權**。列為下一步第一順位。
- **H&M MAP@12**：需 Kaggle 帳號並接受競賽規則；非官方鏡像不等於授權。
- **Polyvore Outfits 官方切分（disjoint／nondisjoint）**：官方 HF repo 被 gate（401）。
  匿名替代 `owj0421/polyvore-outfits` 已驗證可取，但要另外下載 `owj0421/polyvore`（2.21 GB 圖片）才能對上圖，
  今晚沒有時間，因此 §2.3 的 FITB／AUC 用的是**我們自己從 Maryland Polyvore 25k 子集生成的題目**。
- **Fashionpedia / ModCloth / RTR / FEIDEGGER**：都可匿名取得，但對應的是屬性標註與合身預測，
  不是 ENGINE 02 目前的排序主線；留作解釋層的外部標準答案來源。
- **Myntra 官方 Kaggle bundle（1.30 GB，MIT）**：驗證了可匿名下載，但它的內容與
  `Marqo/KAGL`（我們已經在用的 44,434 件）**是同一批商品與同一份 metadata**，
  重跑不會得到新資訊；**價值在於授權**（MIT，且是上游原件），如果之後要對外展示商品圖，
  應該改用這個來源而不是 Marqo 的重封裝。

---

## 4b. 與 `docs/engine02-design.md` 現有數字的抵觸／修正（協調者請看這節）

| design.md 的說法 | 外部證據 | 建議處置 |
|---|---|---|
| §0／§3.3d：「時尚／SigLIP 系列**彼此無顯著差異**，但**都顯著勝過通用 CLIP**」 | **後半句不成立。** fashion-clip 在 KAGL／DF-InShop／H&M／Polyvore 四個外部語料上**沒有一次**勝過通用 laion-CLIP-ViT-B-16；在 KAGL 上**顯著落後**（R@1 −0.022，p=0.0065）。Marqo 官方排行榜同方向。 | **改寫成「選 Marqo-FashionSigLIP」**，並註明原結論的「通用 CLIP」是較弱的 OpenAI CLIP ViT-B/32，不是 LAION ViT-B/16。 |
| §3.1 T1「用詞相同」欄：混合檢索 0.82–0.87 ≫ dense 0.61 | **數量級被字面重疊灌水。** 同樣的查詢型態下，光 BM25 在 KAGL 就有 R@1 0.859、在 H&M 有 0.992。 | 在 T1 表下加一句：**「用詞相同」是上界情境**，真實使用者查詢（ESCI）下 BM25 相對 dense 的邊際貢獻只有 +0.003 nDCG@10。 |
| §3.10：`full_zclip3` 在 44k 上「幾乎沒有代價」（−0.006，p=0.65） | **在字面全命中的情境下有可重現的代價**：Recall@10 比 `hybrid_rrf` 低 0.042（KAGL）／0.024（H&M）／0.026（Polyvore），機制是 z 截斷讓榜首同分。 | **不改預設**（44k 內部實驗仍成立），但把這個邊界情況記入 §3.10。 |
| §3.5c：FITB「OutfitTransformer 54.5%（n=200）」、「和 embedding 相似度差距不顯著」 | **n=2,000 下差距顯著**：OT 0.627 vs embedding 0.521，**+0.107，p=0.0001**。NPMI 則精確等於 0.250（零變異）。 | 更新 §3.5c 的數字與顯著性結論（原本的「不顯著」只是 n=200 檢定力不足）。 |
| §3.7「搭配推薦：互補頭 MRR 0.277 > 相容性頭 0.216」 | **在標準 4 候選 FITB 協定上獨立複現**：互補頭 0.660 > 相容性頭 0.627（+0.033，p=0.0017）；random 負例下 0.721 vs 0.646（+0.074，p=0.0001）。 | 可直接引用為第二個證據源。 |
| （全新）相容性 AUC | **ENGINE 02 之前沒有這個指標**。OT 0.877 [0.867, 0.887]，embedding 0.737，NPMI **0.500**。 | 新增到 §3.5c。 |

---

## 4c. 重現方式與伺服器清理

`/tmp2` 使用率 98%，所以跑完後已刪掉**可一行指令重建**的大檔（ESCI parquet 1.1 GB、
fashion-clip／laion 的圖片 embedding 快取）。保留的是 `marqo_bench/`（官方 GT 與 eval 原始碼，6.8 MB）、
`out/`（結果 JSON，148 KB）、`catalog/{dfinshop,hm_caption}`（重建要 15–20 分鐘）與 marqo 的 embedding 快取。

```bash
P=/tmp2/mzjiang/Research_Project/.venv/bin/python
B=/tmp2/mzjiang/Research_Project/agents/bench
export HF_HOME=/tmp2/mzjiang/Research_Project/.runtime/cache/hf TOKENIZERS_PARALLELISM=false
cd $B/repo

# A 級：官方語料 + 官方 GT（GT 檔已在 $B/marqo_bench/data/，不需重抓）
$P scripts/eval_external.py marqo-t2i --dataset KAGL --catalog data/catalog/kagl_full \
   --encoders marqo-fashionSigLIP,fashion-clip,laion-CLIP-ViT-B-16 --arms dense,hybrid_rrf,full_zclip3
$P scripts/eval_external.py marqo-attr --dataset KAGL --catalog data/catalog/kagl_full

# 需要先重建語料（各約 15 分鐘）
$P scripts/eval_external.py build-catalog --source Marqo/deepfashion-inshop --out $B/catalog/dfinshop
$P scripts/eval_external.py build-catalog --source tomytjandra/h-and-m-fashion-caption \
   --split train --extra-cols "" --id-prefix hm --out $B/catalog/hm_caption
$P scripts/eval_external.py build-gt --catalog $B/catalog/hm_caption --dataset HM-Caption --n 2000

# 穿搭（用現有 polyvore_big 語料）
$P scripts/eval_external.py polyvore-compat --catalog data/catalog/polyvore_big --n-fitb 2000 --n-compat 2000

# ESCI（需重新下載 1.16 GB）
cd $B/esci && for f in examples products; do curl -sSL -O \
  "https://media.githubusercontent.com/media/amazon-science/esci-data/main/shopping_queries_dataset/shopping_queries_dataset_$f.parquet"; done
cd $B/repo && $P scripts/eval_external.py esci --esci-dir $B/esci            # 服飾切片
              $P scripts/eval_external.py esci --esci-dir $B/esci --all-queries
```

`build-gt` 固定 `--seed 0`，所以 H&M 的 2,000 條查詢可完全重現。
FITB／相容性題目也固定 `--seed 0`（`engine02/external.py` 用 `random.Random(seed)`）。

---

## 5. 給協調者的整合掛鉤（Integration hooks）

**本次工作沒有修改任何既有檔案**（`git status` 四個檔案全是 `??`）。以下是建議的整合點：

1. **（唯一一個需要改既有介面的）`Engine02Request.retrieval_text_normalized: bool | None`
   → 增加一個連續值欄位。**
   建議新欄位：`retrieval_text_coverage: float | None`（0–1，ENGINE 01 用 `GET /vocabulary` 算出
   「retrieval_text 的詞有多少比例出現在商品庫詞彙」）。
   ENGINE 02 端只要在 `pipeline.Engine02.run` 既有的那段分流裡多一個分支即可
   （目前已經有 `arm.bm25_adaptive` 用 `self.bm25.coverage(text)` 做同樣的事，
   所以**實作成本幾乎為零，缺的是 ENGINE 01 願意回傳這個值**）。
   證據見 §2.1(c) 與 §2.3：覆蓋率高 → 偏 convex／BM25；中 → dense 為主；低 → 純 dense。
   ⚠️ 注意 §3.7 T10 已經試過「以詞彙覆蓋率分流」並發現**在 44k 上失效**；
   本次的新證據是**外部資料上兩個極端都成立**，所以建議的是「重新評估」，不是「直接改預設」。
2. **`POST /complete-look` 繼續用 OutfitTransformer 互補頭當預設** —— §2.2(a) 在標準 4 候選協定上
   獨立佐證了它勝過相容性頭（+0.033／+0.074，p≤0.0017）。
3. **整套穿搭打分（相容性 AUC 用得到）目前沒有公開介面。**
   `complete_look.FastOutfitTransformer` 只有 `compatibility(anchors, cands)`（錨點→候選）。
   本次在 `scripts/eval_external.py:_OutfitScorer` 用它的內部物件補了「整套打分」。
   建議把它升級成 `FastOutfitTransformer.score_outfit(positions: list[int]) -> float`
   （三行，包裝 `CQuery(outfit=[...])` + `predict_score`），這樣「這套穿搭搭不搭？」
   就能變成一個真正的端點。
4. **`engine02/external.py` 的指標可以直接被其他 agent 重用**：
   `ndcg_linear`（線性 gain，ESCI／sklearn 形式，與既有 `ndcg_at_k` 並存不衝突）、
   `auroc` + `bootstrap_auc_ci` + `paired_auc_delta_test`（配對 AUC 檢定，`eval/metrics.py` 沒有）、
   `marqo_t2i_metrics` / `marqo_attr_metrics`（trec_eval 語意的 Recall@k、P@k、截斷 MRR）。
5. **`full_zclip3` 的已知邊界情況**（§2.1(c) 結論 4）：查詢與商品標題逐字相同時，
   z 截斷會讓所有完全命中的商品同分而在榜首造成平手，Recall@10 因此比 `hybrid_rrf` 低 0.042（p<0.0001）。
   **不建議因此改預設**（內部 44k 實驗看不到這個效應），但應記錄。
