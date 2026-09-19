# `/visual-search` 要變成「精準的照片→商品庫」還缺什麼

> 調查日期：2026-09-18｜分支 `engine02-research`｜**本檔只新增，不改任何既有檔案**
> 標記：**V** = 一手來源已核對（PDF 或官方頁）｜**U** = 只看到摘要／二手，引用要保守｜**INF** = 我的推論，不是文獻結論｜**CODE** = 我直接讀了本 repo 的程式碼，附行號可即刻複核
> 本輪限制（必須寫在簡報上）：三個子代理的 **WebSearch 配額開工即耗盡（200/200）**，產業端全部改用定點 WebFetch，因此「沒找到」一律要讀成「我載得到的那幾頁上沒有」。Street2Shop（ICCV 2015）與 Myntra（MIPR 2021）的表格是**逐頁讀 PDF**（V）；Pinterest／Alibaba／eBay 的數字來自 ar5iv HTML 的摘要式抽取，**進簡報前要對排版 PDF 複核一次**。
> 對照文件：`docs/engine02-design.md` §3.3／§3.3b／§3.3c／§3.16／§3.19／§3.21、`docs/research/external-benchmarks.md` §2.1b、`docs/research/industry-fashion-brands.md` (b3/b4/b9/b10)、`docs/research/industry-recsys-practice.md` 建議 #3、`docs/research/social-trend-signals.md` §4.2、`reports/model_verification.md`。

---

## 0. 三個直接回答

### (1) 最重要的缺口：**沒有文字時，查詢向量有 80% 是「clothing」這個字**

不是域偏移，不是多件衣服，是一條四行的接線錯誤。**CODE**：

- `engine02/api.py:376` — `VisualSearchRequest.retrieval_text: str = ""`，純上傳照片時就是空字串。
- `engine02/pipeline.py:47-62` `build_retrieval_text()` — `retrieval_text` 空、constraints 也空時，走到 `for v in c.category.values or ["clothing"]`，**回傳字串 `"clothing"`**。
- `engine02/pipeline.py:210-212` `query_embedding()` — `q = (1 − 0.2)·l2n(embed("clothing")) + 0.2·l2n(photo)`。
- `engine02/config.py:81` — 服務預設 arm `full_zclip3` 的 `concept_image_weight = 0.2`。

也就是說：**評審拖一張照片進來，我們拿「0.8 × 一個通用英文單字 + 0.2 × 那張照片」去檢索**，而且 `w_bm25 = 0.5`（`config.py`）還讓 BM25 對著 `"clothing"` 這個詞算一輪分數（對每件商品幾乎等值，z 之後是純雜訊）。

那個 0.2 **不是為這個情境量的**。§3.16 量的是「使用者講不出話的**文字**查詢 + 一張生成概念圖」，文字端仍載有真實訊號（純文字 NDCG@5 0.078，低但不是零）；那時候 0.8 的文字權重是合理的。純照片上傳時文字端載的是**零訊號**，0.8 的權重就從「合理」變成「主動加雜訊」。

文獻上這個形狀的錯誤有直接證據（**V**，`docs/engine02-literature-review.md` §6.3 已收錄）：BMVC 2025《Category-level Text-to-Image Retrieval Improved》（arXiv 2509.00177）量到 **純文字 62.7 mAP、純生成圖 41.4、天真 0.5/0.5 融合 61.0（比純文字差）、訓練過的聚合器 67.9**。結論是固定權重的凸融合很脆，最佳權重取決於**哪一邊載有訊號**；當一邊是零訊號時，給它權重必然是負貢獻。而所有已部署的以圖搜商品系統——eBay（KDD 2017）、Alibaba Pailitao（KDD 2018）、Pinterest Shop The Look（KDD 2020）、Myntra ShopLook（MIPR 2021）——**檢索端都是純圖→圖 + 品類硬約束，沒有任何文字項**（V/U 逐條見 §2）。

⚠️ **一個會被自己人誤引的反證，先講清楚**：`docs/research/recsys-composed.md:63` 量到 `image_plus_text` 在 dev 上選到的 **α 一律是 0（純文字）**。那是**另一個任務**——「這件但換成紅色」要**離開**參考圖，參考圖只會把結果拉回原色；以圖搜圖要**貼近**參考圖。不要拿 α=0 當「照片權重應該低」的證據。

**修法（`檔案:函式`）**：`engine02/api.py::visual_search` 在 `body.retrieval_text` 為空時，走「照片主導」路徑——把照片向量當**查詢向量本體**（w=1.0）而不是一個 0.2 的加項，並把 BM25 關掉（既有機制：`retrieval_text_normalized=False` → 本輪只走 dense，`pipeline.py:244`、設計文件 §1.1）。完整實作與驗證見 §7 建議 #1。

### (2) DeepFashion-InShop 的實驗設計：把 T16 的 8 個問題修掉

`scripts/eval_visual_domain.py`（T16，今天 commit `ef9cd9a`，**還沒跑過**）的骨架是對的，兩個量測 × 各自對照組的設計也對。但**照現在的寫法跑出來的數字會系統性低估域偏移**，而且沒有統計。完整的 8 項修正（含 `檔案:函式`、指標、對照組、統計、檢定力、預期效果量）在 **§4.3**，最關鍵的三項：

- **C1 參考分布必須只用 flat**。現在 `element_profile(enc, emb, ...)` 傳的 `emb` 是**全部 52,591 張（on-model + flat 混在一起）**。上線時的參考分布是純白底商品庫。混合參考會把平均值放在兩個域中間，**讓 Δz 縮水**——實驗會告訴你「域偏移比實際小」。改傳 `emb[all_flat_pos]`。
- **C2 要量「有號偏誤」，不只 |Δz|**。「街拍照會不會因為比較暗就被判成霧面」問的是**系統性有號偏移**，`|Δz|` 把偏誤和雜訊混在一起，答不了。每個要素要報 `b_d = mean_g(z_model − z_flat)` + bootstrap CI + 對 flat-vs-flat2 對照組的配對檢定。
- **C4 折疊反義極：11 條軸不是 15 條**。`matte/glossy`、`minimal/bold`、`relaxed/tailored`、`formal/casual` 四對在 antonym 模式下 **z 精確互為負號**（推導見 §4.2），現在的 pooled mean 會把這四條軸算兩次，Holm 校正也該是 11 個檢定而不是 15 個。`KanseiTable.folded`（`kansei.py:60-71`）已經算好這張對照表。

### (3) 設計要素側寫撐不撐得住跨域？**目前的答案是「不知道，而且從回傳值看不出來」——這本身就是缺口**

`engine02/concepts.py::element_profile`（`:89-131`）**沒有信心值、沒有棄權、沒有適用性遮罩、沒有域檢查**，15 條軸永遠全部回傳（**CODE**，手提包也會拿到 `crisp_collar` 的 z 分）。但有三個**已經量過的**理由預期它撐不住：

1. **有一條軸在域內就已經不可信**。§3.3c：亮面材質的 CLIP 反義詞 AUROC **0.71，CI 0.52–0.89——信賴區間含 0.5（隨機）**。在白底商品照上就接近隨機的軸，跨域不可能變好。
2. **§3.16 的 caveat 本身**（`engine02-design.md:385`）：「商品庫是白底商品照、真實生成圖是模特兒照，FashionCLIP 系模型偏好白底」。⚠️ **精確度修正**：白底偏好的一手來源是 **`patrickjohncyh/fashion-clip` 的模型卡**（`engine02-literature-review.md:42`，V），**不是**我們實際部署的 `Marqo/marqo-fashionSigLIP` 的卡。所以現在這句是**外推**，T16 正是把外推變成量測的那個實驗。
3. **`dark_tone` / `bright_color` 兩條軸 `applies_to` 是空的（套用所有品類）**，而且是最直接暴露在打光與背景下的兩條。街拍照偏暗 → `dark_tone` 的 z 會被拉高，而**這和「這件衣服真的比較深色」在數學上不可分**。`docs/research/social-trend-signals.md:102` 已經對社群照做過同一個論證並得出「量到的是拍攝域，不是流行」。

**我的判定（INF，待 T16 證實或推翻）**：側寫的**幾何／結構類軸**（`crisp_collar` 0.97、`visible_logo` 0.96、`bold_pattern` 0.90，§3.3b）大概撐得住——這和 DeepFashion CVPR 2016 Table 2 的排序一致（shape/part 群 > texture/fabric 群，V，見 §5.2）。**材質光澤、色調、鮮豔度三類撐不住**。所以**不要把原始的 15 列側寫當 spec 放上台**：只放 11 條正規軸中、|z| 過校準門檻的前 3 條，附一句拍攝域註記，其餘明講「看不出來」。這比「confidently wrong」對製造商有價值得多（§5.4）。

---

## 1. 總表：缺口 → 業界怎麼做 → 我們的最小可行版本 → 用什麼資料驗證 → 預期成本

| # | 缺口 | 業界怎麼做（出處） | 我們的最小可行版本 | 用什麼資料驗證 | 預期成本 |
|---|---|---|---|---|---|
| **1** | **純照片上傳時 80% 查詢是「clothing」** | eBay KDD 2017、Alibaba KDD 2018、Pinterest KDD 2020、Myntra MIPR 2021 檢索端**都是純圖→圖 + 品類硬約束，零文字項**；BMVC 2025 量到天真固定權重融合**比單一訊號差**（61.0 vs 62.7） | `api.py::visual_search`：`retrieval_text` 為空 → 照片向量當查詢本體（w=1.0）＋關掉 BM25（用既有的 `retrieval_text_normalized=False`） | `eval_visual_domain.py` 加一條 pipeline 級的 w sweep {0, 0.2, 0.5, 0.8, 1.0}，on-model→flat，配對置換檢定 | **30 分鐘**實作；驗證與 T16 同一次跑 |
| **2** | **側寫的 z 和卡片的 c(i,d) 不是同一把尺**（`profile_note` 這句話是假的） | —（這是我們自己的 bug） | `concepts.py::element_profile` 加 `distribution_normalize` 參數，`api.py:414` 傳 `ARMS[arm].concept_dn` | 一致性回歸測試：同一張商品庫圖的 `element_profile` z 必須等於 `design_scores` 那一列（現在不等） | **15 分鐘**＋一個測試 |
| **3** | **側寫 15 列裡有 4 對是精確鏡像**（同一件事講兩次，而且反號） | ZOTO Fashion Intelligence System 把印象語做成單一嵌入空間（ESWA 2022, V），沒有雙極重複 | `element_profile` 依 `table.folded` 濾掉被折疊的極；UI 只顯示 11 條正規軸 | 單元測試：`antonym` 模式下 `z(glossy) == -z(matte)`（先證實鏡像，再證實濾掉） | **10 分鐘** |
| **4** | **側寫沒有信心值／棄權／適用性遮罩** | Geifman & El-Yaniv NeurIPS 2017 選擇性分類（top-5 ImageNet 2% 錯誤率 @ 60% coverage, V）；Fashionpedia ECCV 2020 的**專家標註員**對 Opening Type 有 **32.69% 答「不確定」**（V） | 重用 `attribute_fill.py::coverage_at` / `threshold_for_precision`（**已實作、已引用文獻**）定每條軸的 \|z\| 門檻；套 `concepts.py::applicability_mask` | T16 的 risk–coverage 曲線（見 §4.3 C6）；`data/labels/` 的 420／397 件目視標註可算域內門檻 | **1 小時**（門檻要 T16 的輸出） |
| **5** | **域偏移完全沒量過** | Street2Shop ICCV 2015：同一批查詢，**全圖 5.9–23.6% vs 最佳方法 9.6–54.6% top-20**（V, PDF）；同域 In-Shop R@1 **88.0%**（CVPR 2019）vs 跨域 DeepFashion2 consumer→shop **top-1 19.2%**（**約 4.5 倍差距**） | 跑 T16（修完 8 項），加 4 個修正 arm（catalog-mean / query-domain-mean centering / per-element affine / VLM 第二意見） | `Marqo/deepfashion-inshop` **on-model(`_1_front`/`_2_side`/`_3_back`) → flat(`_6_flat`)**，同一件衣服；兩個對照組 | **216 MB 下載＋15–20 分鐘重建**（`external-benchmarks.md:661`）＋跑一次 |
| **6** | **一張照片多件衣服 → 整張嵌入把它們混在一起** | Pinterest STL KDD 2020：偵測 mAP 0.285→0.444 帶動 **Similar P@5 +38.6%**，**每品類獨立索引讓 top-5 的「差」結果 −17.1%**（U, ar5iv）；Myntra MIPR 2021 Mask R-CNN 20 類、**平均 mAP 78%**、**A/B CTR +25%**（V, PDF）；**Alibaba KDD 2018 的關鍵發現：弱監督（無框標註）IoU@0.7 只 70.2% vs 全監督 95.1，但 Recall@1 46.5 vs 46.7——檢索不需要準框**（U） | **兩層**：(a) 前端 cropperjs（MIT）讓使用者自己框——**Pinterest Flashlight 就是先出這個**；(b) `yainage90/fashion-object-detection`（**MIT**，conditional-DETR-R50，ModaNet+Fashionpedia，**7 類正好對上我們的槽位**，mAP 0.754）→ 每個 crop 一條**獨立**排序，品類硬約束 | 手工框 50 張多件衣服照當偵測驗收；檢索端用 Polyvore（3,000 件在本機）的真實穿搭圖當 query，看回來的商品是否來自同一套 | (a) **2 小時**；(b) **4–6 小時**＋每個 crop 多一次 encoder forward（CPU 125 ms/張，`model_verification.md`） |
| **7** | **非服裝照／域外查詢沒有守門** | MCM (NeurIPS 2022)：CLIP-B/16 ImageNet ID 平均 **AUROC 90.77 / FPR95 42.74**，但**最難的 OOD 集是 Texture（FPR95 57.77）**——正好是布料特寫（V）；KNN-OOD (ICML 2022) 用到訓練集的 k-NN 距離當分數，**比 SSD+ 降 FPR@95TPR 24.77%**（V） | `api.py::_encode_upload` 之後加 `concepts.py::domain_gate(vec)`：負向 prompt 集（狗／UI 截圖／白板／食物／風景／布料特寫）做 MCM softmax ＋ 到商品庫的 k-NN 距離；落在非服裝類就回 `warnings`，不回側寫 | 正例：`data/catalog/kagl/images` 5,000 張；負例：手蒐 100 張非服裝照。門檻取域內分數的**第 5 百分位**（= 95% TPR），n≥500 | **2 小時**；**k-NN 那一半幾乎免費**（`engine.image_emb @ q` 已經在算） |
| **8** | **有人臉的照片沒有任何處置（隱私）** | GDPR Recital 51 逐字：「photographs should **not systematically** be considered… special categories… only when processed through a specific technical means allowing the **unique identification**」（V）→ 純照片是**個資但不是生物識別資料**；Anthropic vision docs：「Claude cannot be used to name people in images and refuses to do so」＋「Image uploads are ephemeral and not stored」（V） | `api.py::_encode_upload` 內加 **YuNet**（OpenCV Zoo，**MIT**，WIDER Face hard AP 0.7503）偵測人臉 → **像素化（下採樣再上採樣，不是小 σ 高斯）** → 才送進 encoder；畫面上一句固定文案 | 目視：20 張有人的照片，確認 (a) 臉被遮 (b) 側寫的 11 軸 z 變化 < 域內噪音（臉不該影響服裝判讀）——這第二項本身就是一個好實驗 | **1.5 小時**；YuNet 內建於 OpenCV，無新依賴 |
| **9** | **`constraints` 壞 key → 500 而不是 400** | —（我們自己的 bug） | `api.py:419` 的 `HardConstraints(**body.constraints)` 包 try/except → 400 | `tests/test_api.py` 加一行 `{"constraints": {"bogus": 1}}` → 400 | **5 分鐘** |
| **10** | **側寫每次請求重算整個商品庫的參考分布** | —（效能，`/rank` 已經是 12.8 ms，§3.21） | 開機時預算 `(mean, sd, 排序後的 r_cat)` 並落地 `index/profile_ref_*.npz`，命名沿用 `design_*.npy` 的慣例（`pipeline.py:164-169`） | `scripts/bench_latency.py` 加 `/visual-search`；`scripts/check_parity.py` 證明側寫數值逐條不變 | **1 小時**；**同時把 T16 的 `n_prof=150` 上限解放到 800+**（檢定力！） |
| **11** | **上傳的照片沒有 HEIC／多幀／16-bit／非 Adobe CMYK 的處置** | Pillow 官方文件逐條（V，見 §6） | `_encode_upload`：`register_heif_opener()`（pillow-heif, **BSD-3**）、`n_frames>1 → seek(0)`、`I;16` 走 numpy 重新縮放、CMYK 無 `adobe` key 時標警告 | `tests/test_api.py::test_visual_search_normalises_real_world_uploads` 直接加 case（**這個測試已經存在**） | **1 小時** |
| **12** | **製造商要的是 spec，不是「相似商品」** | Walmart **Trend-to-Product**：AI 從趨勢產 mood board **再產指導供應商生產的 tech pack**，前置期 6 個月 → 6–8 週（V，`industry-fashion-brands.md` b9）；**Design2GarmentCode, CVPR 2025**：圖／文／草圖 → LMM → 參數化打版程式（V）；techpacks.co 的人工服務就是「客戶丟圖 → 人寫 tech pack」（V） | 側寫升級成 **spec 卡**：11 軸 + 信心 + **明講看不出來的欄位**；`scripts/vlm_tag_attributes.py::QUESTIONS` 加 5 題製造相關（閉合方式／袖型／領口／口袋／針織 vs 梭織）——**同一次 forward、同一個 `na_` 棄權機制、0.09–0.39 秒/件** | 現有 `data/labels/`（420 + 397 件目視標註）；新題目要新標 40 件。**注意 §3.19 的循環性陷阱**：不能用 Qwen 自己補的欄位當標準答案 | **2 小時**（改題目 + 重跑一個子集） |

---

## 2. Q1 一張照片、好幾件衣服

### 2.1 已部署系統怎麼做（區分「上線」與「論文」）

| 公司 | 上線？ | 偵測器 | 關鍵數字 | 出處 |
|---|---|---|---|---|
| **Pinterest** Similar Looks | 2015 上線、**失敗** | part-based model | 覆蓋率太差，**只有 2.4% 的日活使用者看得到偵測到的物件** | Visual Discovery at Pinterest, arXiv 1702.04680（U, ar5iv） |
| **Pinterest** Flashlight | 2016 上線 | Faster R-CNN (ResNet-101) → 後加 SSD | **Faster R-CNN 272 ms / P 0.426 / R 0.470；SSD 59 ms / P 0.502 / R 0.371**。**先出「使用者自己框」的 UI 來繞過偵測器覆蓋率不足**，等偵測變好才換成可點的 object dots | 同上（U） |
| **Pinterest** Shop The Look | **上線，KDD 2020** | ResNeXt-101-FasterRCNN + FPN；251k 圖／**727k 框**＋**133k 弱監督單品圖**（商家品類標籤，無人工框） | 偵測 mAP **0.285 → 0.444**；Similar **P@5 +38.6%**；A/B scene closeups **+51.6%**、product CTR **+29.2%**；fashion embedding **P@1 0.323 → 0.641**；累計**人工相關性 +160%、互動 +80%** | arXiv 2006.10866（U, ar5iv；`industry-fashion-brands.md` b4 已收錄 V） |
| **Myntra** ShopLook / Buy Me That Look | **上線，IEEE MIPR 2021**（注意：不是 arXiv-only 2020 preprint） | **Mask R-CNN (ResNet-101-FPN)**，~20 服飾類，~150k 自建訓練圖。**論文明寫為什麼不用 YOLO**：偵測可以離線做，所以寧可要 mAP 不要延遲 | 平均 **mAP 78%**（上衣類到 92%）；**主動學習前→後**：裙子 **51.42 → 69.09 AP**（最大贏面）、包 69.71 → 78.37；端到端 **P@5 24.6% / R@14 41.7%**；**A/B CTR +25%、加購 +4%**；**V100 上每張全身照 400–500 ms 偵測 3–5 件** | arXiv 2008.11638（**V, 逐頁讀 PDF**） |
| **Alibaba** Pailitao | **上線 2014，2017 日活 1,700 萬** | **弱監督、零框標註**：偵測分支學一個 mask 乘在 feature map 上抑制背景；監督訊號來自**點擊 log**（PVLOG triplet：正例=被點擊、負例=同頁未點擊） | **關鍵表 3**：全監督 SSD IoU@0.7 **95.1%** / R@1 46.7%；弱監督 IoU@0.7 **70.2%** / R@1 **46.5%**、R@4 **更高**、**延遲 20 ms vs 59 ms**。品類預測 model 88.86% + search 85.51% → **融合 91.01%**；PVLOG 特徵 **+17 個百分點 Identical R@1** | arXiv 2102.04674 / KDD 2018（U, ar5iv） |
| **eBay** | **上線（ShopBot）**，KDD 2017 | **刻意不做物件偵測**。整張圖嵌入，用 ResNet-50 的 **leaf-category 分類器**當約束：「we search only among top predicted categories」，再合併 | 4,096-bit hash = 512 B/圖，**200M 圖 < 100 GB**；DNN 125 ms、排序 25–70 ms；最終分數 **0.75·外觀 + 0.25·屬性比對** | arXiv 1706.03154（U, ar5iv） |
| **Musinsa** | PoC（AWS 技術部落格 2025） | **YOLOS-Fashionpedia** 偵測 → FashionCLIP 2.0 → OpenSearch | 5,032 張測試：**P@1 72% / P@5 81% / MRR 0.76**；自承素色基本款、遮擋、角度難 | `industry-fashion-brands.md` b1（V） |
| **Google Lens / Multisearch** | 上線 | **沒有公開任何架構層級說明** | — | blog.google 2022-04-07（V，但只有產品描述） |
| **Amazon StyleSnap** | 上線（re:MARS 2019） | **沒有論文、沒有工程部落格**；三個 URL 全 404 | — | **不要引用 StyleSnap 的架構主張** |

**兩句必須寫在簡報上的話**：

1. **eBay 用整張圖沒事、Pinterest 和 Myntra 不行，差別在查詢分布**。eBay 的使用者是「拍一件東西」；Pinterest／Myntra 的是「一整套穿搭照」。**我們是後者。不要拿 eBay 當「整張圖夠用」的證據，要拿它當「答案取決於查詢分布」的證據。**（INF，但論文自己的框架支持這個讀法。）
2. **Pinterest 的翻車最值得學**：Flashlight 第一次上偵測，**互動掉 −3.8% 到 −5.3%**，加上**品類一致性過濾**之後才變成 **+4.9%**。→ **切圖只是一半，品類硬約束是另一半。** 我們如果只加 crop 不加品類約束，很可能重演這件事。

### 2.2 最小可行版本，含授權與速度

**⚠️ 五個授權陷阱，先說**（全部逐條核對過 LICENSE 檔，V）：

1. **Ultralytics（YOLOv8 / YOLO11 / 它們包的 RT-DETR、SAM、MobileSAM、FastSAM）是 AGPL-3.0**，官方授權頁明寫適用於「Deploy through a SaaS platform, API, or other private system」，要求開源**整個衍生作品**。**黑客松 demo 可以，變產品不行。**
2. **FastSAM 的 README 寫 Apache-2.0，LICENSE 檔是 AGPL-3.0**。LICENSE 檔說話。
3. **`mattmdjaga/segformer_b2_clothes` 是 NVIDIA SegFormer 授權，明文「non-commercially… research or evaluation purposes only」**——這顆模型每月 21 萬次下載，幾乎沒人讀到這條。
4. **YOLO-World 是 GPL-3.0**（沒有 AGPL 的網路條款，但仍是強 copyleft）。
5. **detectron2 model zoo 的權重是 CC BY-SA 3.0**（程式碼才是 Apache-2.0），share-alike 會傳染到 fine-tune。

**我建議的兩層做法：**

| 層 | 做什麼 | 授權 | 速度 | 公開的準確度錨點 | 工時 |
|---|---|---|---|---|---|
| **Tier 0（先做）** | 前端 **cropperjs** 讓使用者自己框，一張 crop → 一條排序 | **MIT** | 伺服器端 **0 ms** | **Pinterest Flashlight 就是先出這個**；而且 Street2Shop 的官方協定本身就是「給你一個人工框 + 品類標籤」 | **~2 h** |
| **Tier 2（再做）** | **`yainage90/fashion-object-detection`**（conditional-DETR-R50，ModaNet+Fashionpedia，**7 類：bag/bottom/dress/hat/shoes/outer/top**）→ 每個 crop 走一條獨立排序，品類硬約束用既有的 `constraints.category` | **MIT**（偵測器與配套 embedder 都是） | 未公布，**要自己量**；DETR-R50 級（41.6M 參數） | **mAP 0.754**（epoch 96/100，模型卡自報） | **~4–6 h** |
| Tier 1（授權備援） | **SCHP**（Self-Correction Human Parsing，**MIT**）人體解析 → 取 `Upper-clothes` / `Pants∪Skirt∪Dress` / `Left-shoe∪Right-shoe` / `Bag` 的 bbox | **MIT** | 未公布（ResNet-101 底，預期要 GPU） | **ATR mIoU 82.29%** / LIP 59.36% | ~4 h |
| Tier 3（demo 最好講） | **Grounding DINO** 或 **OWLv2**，prompt = `"a shirt. trousers. shoes. bag."` | **Apache-2.0** | 未公布，**0.2B 參數，CPU-only demo 大概不行**（INF） | GDINO **52.5 AP COCO zero-shot** | ~3 h，零訓練 |

**為什麼 Tier 0 + Tier 2 而不是 SAM**：SAM / SAM2 / MobileSAM / FastSAM 都是**可提示、類別無關**的——它們給你一個 mask，**永遠不會說「這是上衣」**，你還要再接一個歸屬步驟。而 Alibaba 的表 3 已經告訴我們**不需要準確的邊界**（IoU@0.7 從 95.1 掉到 70.2，R@1 只從 46.7 掉到 46.5）。所以「更準的 mask」不是我們的瓶頸。（MobileSAM 順帶一個有用的數字：與 SAM 的 mask 一致性 mIoU **0.73 vs FastSAM 的 0.27–0.41**——FastSAM 不只授權有問題，忠實度也差得多。）

**`yainage90` 的 7 類正好對上我們的槽位**（top / bottom / dress / shoes / bag / outer / hat），這是它比 `valentinafeve/yolos-fashionpedia`（45 類，會回「袖子」「領子」「亮片」這種零件框，而且**沒公布任何指標**）好的地方。

### 2.3 crop 怎麼歸屬到槽位、多個 crop 的結果怎麼合併

**歸屬的五種機制**（按證據強度排）：

1. **偵測器自己的分類頭** — Pinterest（Google Product Taxonomy）、Myntra（~20 服飾類 → 路由到**該類專屬**的 triplet embedding 模型）、`yainage90`（直接吐 7 類）。**主流。**
2. **另一個品類分類器 + 檢索式投票融合** — Alibaba：GoogLeNet 88.86% + 200M 參考圖的 kNN 85.51% → **融合 91.01%**。
3. **完全不偵測，整張圖多標籤品類預測，在每個 top-k leaf category 裡各搜一次再合併** — eBay。
4. **姿態先驗當「閘門」** — Myntra 用 head+ankle keypoints 先確認「這是全身照」，再用 ResNet18 分 front/back/left/right/detail（逐類 P/R 都在 90 幾）**把歸屬會不可靠的視角直接丟掉**。**這個「先閘門再分槽」很便宜、很少人提。**
5. **用帶標籤的 parse map 讓歸屬免費** — SCHP/ATR 的 pixel label 本身就是槽位。

**合併：我找到的每一個已部署的多物件系統都是「每槽一條清單」，不跨物件合併。**
- Pinterest STL：object dots，**點一個 dot 看那一個物件的排序**；人工相關性評的是**每個查詢物件的 top-5**。
- Myntra：**每個偵測到的服飾類一條獨立 carousel**（男 T 恤／男短褲／鞋），bbox 顏色對應 carousel。
- eBay **有**合併，但合併的是**同一張整圖的多個預測品類**，不是多個物件。

**而且硬約束比後過濾好，Pinterest 有量化**：每品類獨立索引讓 top-5 的「差」結果 **−17.1%**、「相似」結果 **+9.9%**；再加性別限制，top-5「極相似」**+12.7%**。Alibaba 同樣是**先預測品類、只搜那個品類的索引**。

**多 crop 池化的文獻（R-MAC ICLR 2016、DIR ECCV 2016、sum-pooling ICCV 2015、GeM TPAMI 2018、MOP-CNN ECCV 2014）全部是把「同一個物件」的多個區域聚成「一個」向量**——和我們要的正好相反。**沒有任何已發表的方法是把「不同物件」的分數融成一條排序**（GAP）。要做就是我們自己發明，而可辯護的設計是 **N 槽 → N 條清單，每條在自己的品類索引裡**。（如果只是想讓同一件衣服的多尺度 crop 更穩，那才用池化，而且要用 **sum/average 不要 max**——Babenko & Lempitsky ICCV 2015 的結論。）

---

## 3. Q2 域偏移（街拍／模特兒照 → 白底商品照）

### 3.1 同域 vs 跨域：那個差距有多大

| 任務 | 資料集 | 域關係 | 指標 | 數字 | 出處 |
|---|---|---|---|---|---|
| In-shop 檢索 | DeepFashion In-Shop | **同域**，混視角 | R@1 | **80.9% → 88.0%** | Multi-Similarity Loss, **CVPR 2019**（arXiv 1904.06627, U） |
| consumer→shop，**偵測框** | DeepFashion2 | 跨域 | top-1/5/10/20 | **19.2 / 34.5 / 43.5 / 52.4%** | DeepFashion2, **CVPR 2019**（U） |
| consumer→shop，只用 keypoints | DeepFashion2 | 跨域 | top-1 | 18.2% | 同上 |
| consumer→shop，**用分割** | DeepFashion2 | 跨域 | top-1 | **13.5%** | 同上（**分割比框差**，和 Myntra 的 Fig. 8 一致） |
| street→shop，**整張圖** | Street2Shop | 跨域 | top-20 | **5.9%（鞋）– 23.6%（包）** | Kiapour et al., **ICCV 2015** Table 2（**V, PDF**） |
| street→shop，**最佳方法** | Street2Shop | 跨域 | top-20 | **9.6%（鞋）– 54.6%（裙）** | 同上（**V**） |
| **人類上限**（給 10 個「相似」的選對的） | Street2Shop | — | accuracy | **平均 54.2%**（眼鏡 33.3 … 包 81.6） | 同上 Table 3（**V**） |
| Alibaba Pailitao **上線** | 自有 ~30 億圖 | 跨域 | Identical R@1 | **46.5%** | KDD 2018（U） |

**三句要進簡報的話：**

1. **同域 top-1 約 88%，跨域 top-1 約 19%——在可比的 top-1 上差約 4.5 倍。我們的 on-model→flat 代理坐在 88% 那一端。每個代理數字都要在同一句話裡標明是上界。**
2. **連 Alibaba，在約 30 億張索引、用點擊 log 訓練的嵌入上，Identical R@1 也只有 46.5%。** 如果我們的 demo 在 In-Shop 代理上報 80%+，那個數字量的是代理不是產品。期望值要對 46.5 校準，不是對 88。
3. **一定要逐槽報，不要報一個平均**。Street2Shop 最佳方法從 **9.6%（鞋）到 54.6%（裙）**，**5.7 倍的跨品類落差，而且鞋在每個系統裡都是最難的槽**。我們的功能明確承諾鞋，一個平均值會把最差的槽藏起來。Pinterest／Alibaba／Myntra 都逐品類評估，就是這個原因。

### 3.2 什麼真的能縮小差距（以及什麼**不可能**）

| 手段 | 已發表的效果量 | 我們能不能做 | 判斷 |
|---|---|---|---|
| **用配對跨域資料做 metric learning** | **Myntra MIPR 2021**：anchor 取自 **street2shop**（真實街拍）、positive 取自自家目錄的同一件、negative 取同類他件，semi-hard mining → 端到端 P@5 24.6% vs Euclidean baseline 19.3%（V）。**Alibaba**：點擊 log 的 PVLOG triplet → **+17 個百分點 Identical R@1**（U） | ❌ **不行** | **沒有可用授權的配對消費者／商店資料**，In-Shop 是研究用途（`external-benchmarks.md:275`「離線評測可以，不可出貨」），也沒有點擊 log。Myntra 為此自建 150k 圖、Sewformer 用了 100 萬合成配對——這是規模問題不是技巧問題。**列入「不建議做」。** |
| **減少非服裝脈絡（切圖／去背）** | **Street2Shop Table 2 就是這個的量化**：全圖 vs 定位 crop 只差「描述子裡有多少非服裝脈絡」——**裙 11.6 → 45.9、眼鏡 10.1 → 42.0、帽 11.6 → 36.0，約 4 倍**（V）。這是我找到的**「背景是主因」最強的數字** | ✅ **能**（Q1 的 Tier 0/2 就是） | ✅ **和 Q1 同一件事，做一次拿兩個好處。** rembg／SAM 這種「真去背」的檢索效果量我**沒有找到任何已發表數字**（GAP），所以它排在切圖後面，而且要先量再上 |
| **域特定 prompt** | — | ⚠️ **檢索端算術上不可能** | **必須講清楚**：以圖搜圖的查詢是**圖片向量**，文字塔根本不在路徑上（`pipeline.py:210-212`），prompt 不可能影響它。**但 prompt 是側寫端的槓桿**——`element_profile` 完全靠文字 prompt（`concepts.py:106-122`）。**不要把這兩件事混在一起。** |
| **每個域減自己的平均向量（centering）** | `concepts.py:65-66` 的 `distribution_normalize` 就是這個，repo 自己引 **Zhou et al. NeurIPS 2023**；模態落差／cone effect 的文獻（Liang et al.「Mind the Gap」NeurIPS 2022）我**本輪沒能核對**（U） | ✅ **幾乎免費** | ✅ **這是我最推薦先試的修正**。而且它同時修掉缺口 #2（兩把尺）。T16 的 A1/A2 arm 就是量它 |
| **重排序** | 我們**自己**量過：`Qwen3-VL-Reranker-2B` bf16 **每 pair 9.6 ms、4.25 GB VRAM，top-50 重排約 0.5 秒，demo 可開**（`engine02-design.md:577`, V）。但同一份文件 §0 記錄：4090 上加了它，**用詞相同的查詢反而變差 0.840→0.797（p=0.001）** | ⚠️ 能，但有反面證據 | ⚠️ 那個負結果是**文字查詢**上的，圖→圖跨域是**不同用法**，不能直接推論。但也不能宣稱它會有用。**排在 w 修正與 centering 之後**。k-reciprocal 重排（Zhong et al. CVPR 2017）我本輪沒核對（U），且單一查詢下它其實是 gallery 端的查詢擴展，**未量測** |
| **查詢端擴增 / αQE / DBA** | GeM 論文（Radenović et al. TPAMI 2018, arXiv 1711.02512）含 αQE；細節我本輪沒核對（U） | ✅ 能（多 crop / flip 再 sum-pool） | ⚠️ 低優先。**注意**：跨不同衣服池化是有害的（§2.3），只有同一件衣服的多尺度才適用 |

### 3.3 on-model → flat-lay 這個代理站不站得住，該叫它什麼

**站得住——當成上界，而且名字要誠實。**

**建議的叫法：「in-shop 跨呈現方式檢索（on-model → flat-lay），作為 consumer-to-shop 的*部分*代理」。**

- ✅ **「跨視角落差」（cross-view gap）** — 對 front/side/back → `_6_flat` 這個軸精確。
- ✅ **「呈現域偏移」（presentation-domain shift）** — 最精確的單一片語：偏移在**衣服怎麼被呈現**，不在誰拍的。
- ⚠️ **「部分域代理」** — 只有在**把缺的東西一條條列出來**時才能用（下面就列）。
- ❌ **絕對不要叫「跨域」或「consumer-to-shop」**。兩張照片都是同一家零售商、同一場拍攝的專業攝影。沒有消費者攝影師、沒有消費者裝置、沒有消費者環境。**這是評審唯一一定會抓到的點。**

**這個代理**捕捉不到**的六件事（全部要寫出來）：**

1. **雜亂／有紋理的真實背景**。Street2Shop 自己把這列為主要失敗原因（「visual distraction from textured backgrounds」，V）。我們的 flat 是白幕、on-model 是攝影棚幕，**兩邊都沒有街道**。
2. **不受控的打光／白平衡**。兩張都來自同一場拍攝、同一組燈。而 colour 是 Marqo In-Shop 裡基數最高的欄位（804 個值），也是真實光線下最脆的。
3. **遮擋**（手臂、包、頭髮、別人）。Myntra 為此專門建了一個姿態分類階段，**目的是把遮擋的視角丟掉**——一個生產團隊選擇丟資料，說明遮擋有多難處理。
4. **非正面、局部裁切**。`_1_front`/`_2_side`/`_3_back` 是標準棚拍角度，不是從腰部高度拍、腿被切掉的 3/4 側身。
5. **手機壓縮與低解析度**。Myntra 逐字：「Such UGC images usually have poorer resolution and/or illumination」。
6. **一張照片裡有好幾件衣服——也就是我們整個功能的重點**。In-Shop 一張圖一件。**這個代理量不到我們的核心貢獻。這是本節最重要的一句：代理測的是我們的 *embedding*，不是我們的 *分解*。** 分解要另外驗（§1 缺口 #6 的 50 張手工框）。

**把背景／姿態／打光三者分開的 ablation：我沒找到（GAP）。** 最接近的兩個替代：背景／脈絡由 Street2Shop Table 2 隔離出來（約 4 倍，見 §3.2）；視角／姿態由 Myntra 的姿態分類器與 DeepFashion 自己把「300,000 cross-pose/cross-domain pairs」當成一個獨立軸來隔離。**打光：什麼都沒找到，如實報告成一個公開缺口。**

**In-Shop 官方協定**：`Marqo/deepfashion-inshop` 的 card 確認 52,591 列、`item_ID` 帶視角後綴、`category1`(2) / `category2`(16) / `category3`(8) / `color`(804) / `description`。標準 In-Shop 協定**按 item 切 train/query/gallery，兩側都有多種視角**。所以我們的 on-model→flat 限制是**標準協定的一個更難的子集，不是另一個任務**——這是好事，意味著我們的數字可以和公開的 In-Shop 數字比，而且應該**低於**它們。⚠️ **待核對**：card 確認了後綴結構與 item 層級 id，但我沒能拿到「官方 query/gallery 清單混視角」的一手陳述；印那句話之前請對 `list_eval_partition.txt` 確認（我們手上的 HF 鏡像沒有這個檔）。

### 3.4 有沒有更好、下載得到、授權可用的替代資料集

| 排名 | 資料集 | 真正裝了什麼 | 取得方式 | 大小 | 授權 | 值得嗎 |
|---|---|---|---|---|---|---|
| **1** | **我們已有的 Marqo In-Shop 代理** | 52,591 列、~6.6 視角/件 | 一行 `build-catalog` | **216 MB / 15–20 分鐘** | 研究用途，**離線評測可以不可出貨** | ✅ **零摩擦，先做這個** |
| **2** | **VITON-HD**（CVPR 2021） | **11,647 train + 2,032 test 配對**，**真正的平放單品圖 ↔ 上身照**（不只是另一個棚拍角度） | Google Drive，**自助** | 1024×768 | **CC BY-NC 4.0** | ✅ **比 In-Shop 更真的配對，而且零摩擦。限制：只有正面、只有女裝、只有上衣、非商業** |
| **3** | **Pinterest Shop-The-Look / Complete-the-Look**（`github.com/kang205/STL-Dataset`） | `{product, scene, bbox}`——**場景照 + 逐件框 → 可買商品**。**任務保真度最高，這就是我們的功能** | JSON 很小，**圖片要自己爬**（signature→`i.pinimg.com` URL） | — | ⚠️ **repo 沒有任何授權或條款宣告** | ⚠️ 任務最貼，法務風險最高。**要爬。** 連結腐壞率未驗證 |
| **4** | **DeepFashion2** | 391k/34k/67k 圖、**801k 商品、873k 商業-消費者配對** | Google Drive + **密碼申請表** | 大 | **repo 無明確授權 → 視為研究用途** | ⚠️ **最好的「可比對」代理**（有公開的 consumer→shop baseline 可對），但要等表單 |
| **5** | **Amazon Berkeley Objects (ABO)** | 147,702 商品、398,212 目錄圖，**外加 8,200+ 商品的 360° 圖（每件 72 個視角）** | 公開 S3，**完全自助無表單** | **縮圖版只 3 GB** | ✅ **CC BY 4.0，可商用** | ⚠️ **授權最乾淨**、也有多呈現方式，**但是棚拍目錄圖、以居家用品為主——服裝域不對，而且沒有街拍** |
| 6 | **DeepFashion Consumer-to-Shop** | 300k+ cross-pose/cross-domain 配對 | Google Drive/百度 + **簽署同意書 email 拿解壓密碼** | 大 | **明文「非商業研究用途」** | ❌ **好幾天的取得摩擦，黑客松跳過** |
| 7 | **DressCode**（ECCV 2022） | 107,584 圖 / 53,792 單品，上身／下身／連身 | 申請表，**要機構 email、要手寫簽名、每週人工審**，且「will not be released to private companies」 | — | 同左 | ❌ **取得摩擦本身就取消資格** |
| 8 | **Street2Shop** | 404,683 商店圖 / 20,357 街拍 / 39,479 配對 / 25 家零售商 / 11 品類 | metadata + **圖片 URL 清單** | — | 研究 | ⚠️ **引用它的數字，不要指望它的圖片**。專案頁本輪載不到（404 / TLS 錯）；2015 年的 URL 清單極可能大量失效 |
| 9 | Fashion-IQ (CVPR 2021) | 圖 + 相對自然語言回饋 | URL 清單 | — | CDLA | ❌ **任務不對**（文字條件修飾，不是 consumer→shop） |
| — | Fashion200K / FACAD / Alibaba iFashion / Atlas / 2023–25 新釋出 | — | — | — | — | **本輪完全沒查（配額耗盡）** |

**黑客松排序：現有 In-Shop 代理（零摩擦）→ VITON-HD（自助、真配對、只是 NC）→ STL-Dataset（要爬 + 授權不明）→ DeepFashion2（要等密碼）。不要為 DeepFashion C2S 或 DressCode 卡住進度。**

---

## 4. Q3 設計要素側寫可不可信（**本檔的核心**）

### 4.1 現狀：程式碼層級的四個事實

**CODE**，`engine02/concepts.py::element_profile`（`:89-131`）：

| 事實 | 行號 | 後果 |
|---|---|---|
| z 的參考分布是**每次請求重算整個商品庫** | `:124` `r_cat = raw(cat)` | 17,783 × 768 × 4 prompt × 15 要素 ≈ **8.2e8 次 float64 乘加/請求**。`/rank` 是 12.8 ms（§3.21），所以 `/visual-search` 大概慢 1–2 個數量級（**INF**，沒實測）。也是 T16 把 `n_prof` 壓到 150 的原因（`eval_visual_domain.py:132` 註解自己寫了「each profile is 15 catalog-wide matvecs」）→ **檢定力被效能問題綁住** |
| **沒有**套用適用性遮罩 | 對比 `design_scores` 的 `:84-85` | **手提包也會拿到 `crisp_collar` 的 z 分**。`applicability_mask()`（`:40-48`）已經存在，只是沒被 `element_profile` 呼叫 |
| **沒有** `distribution_normalize` 參數 | `:89-91` 簽名；`api.py:414` 也沒傳 | 服務預設 arm 的 `concept_dn = True`（`config.py:35`），`design_scores` 有做（`:65-66`），**側寫沒做** → `api.py:416` 的 `profile_note`「和卡片上的設計要素用同一把尺」**對預設 arm 是假的**。`docs/research/industry-recsys-practice.md:447-448` 提議這個功能時也寫了同一句話，所以這個錯誤在文件裡傳了兩手 |
| **沒有**信心值、CI、棄權路徑 | 整個函式 | 15 條軸永遠全部回傳、永遠有一個看起來很確定的 z |

### 4.2 一個可以用紙筆證明的問題：15 條軸其實是 11 條

antonym 模式下 `raw(x) = σ((s_pos − s_neg)/T)`。把正負極互換（這正是 `glossy_fabric` 相對 `matte_fabric` 的定義，兩者的 descriptors 逐字互為對方的 negative_descriptors，我用 `kansei_v1_literature.json` 驗過）：

```
raw'(x) = σ(−d/T) = 1 − raw(x)
⇒ mean(r'_cat) = 1 − mean(r_cat),  sd(r'_cat) = sd(r_cat)
⇒ z' = ((1−r_img) − (1−μ)) / σ = −z          ← 精確互為負號
⇒ percentile' = 1 − percentile               ← 忽略平手
```

四對鏡像：`matte_fabric ↔ glossy_fabric`、`minimal_design ↔ bold_pattern`、`relaxed_fit ↔ tailored_fit`、`formal_style ↔ casual_style`。**15 條軸 = 11 條正規軸**（`docs/research/social-trend-signals.md:16` 已經從另一個方向得到同一個結論）。

**兩個後果**：

1. **UI bug**：`element_profile` 依 `-abs(z)` 排序（`:130`），所以鏡像對**一定相鄰**。卡片上的「最突出的 3 個設計要素」會出現「霧面材質 +1.8 / 亮面材質 −1.8」——**同一件事講兩次，還反著講**。`KanseiTable.folded`（`kansei.py:60-71`）已經算好要濾掉哪一極。
2. **統計 bug**：T16 對 15 個要素做 pooled mean 會把這四條軸**各算兩次**；多重比較校正也該是 **11 個檢定**。

### 4.3 核心實驗：把 T16 修好（給 coordinator 的完整規格）

**前置**：`python scripts/eval_external.py build-catalog --source Marqo/deepfashion-inshop --out <dir>/dfinshop`（216 MB、15–20 分鐘、**本機沒有這份語料**）。`eval_visual_domain.py:59` 的預設 `--catalog agents/bench/catalog/dfinshop` 在本機不存在，要改或傳參。**授權：離線評測可以，不可出貨、不可進 git。**

**分組鍵**：`ID_RE = r"^(?P<garment>.+_id_\d+_\d+)_(?P<idx>\d+)_(?P<view>[a-z]+)$"`（`:44`，已經對了）。注意 `MEN_Denim_id_00000089_**01**` 的 `01` 是同一 id 下的**不同配色**，所以 garment 鍵包含它是對的。

#### 八項修正

| # | 修正 | 位置 | 為什麼 |
|---|---|---|---|
| **C1** | **參考分布只用 flat**：`element_profile(enc, emb[all_flat_pos], emb[pos], ...)` | `eval_visual_domain.py::prof` (`:134-136`) | 現在傳全部 52,591 張（on-model + flat 混合）。上線時參考分布是**純白底**。混合參考把平均放在兩域中間，**Δz 會縮水** → 低估域偏移。**同時報混合與 flat-only 兩組，差值本身就是一個結果** |
| **C2** | **量有號偏誤**：每要素 `b_d = mean_g(z_model − z_flat)`，配 `bootstrap_ci`，並對 flat-vs-flat2 對照組做 `paired_permutation_test` | `eval_visual_domain.py::agreement` (`:159-171`) | `mean_abs_delta_z` 把偏誤和雜訊混在一起。「街拍照偏暗所以被判霧面」是**有號**問題。**偏誤可以校正，雜訊不行**——所以這個分解決定了下一步該做什麼 |
| **C3** | **統計，而且要按 garment 叢集**：重抽樣單位是**衣服**不是列。`engine02/eval/metrics.py::bootstrap_ci` 餵「每件衣服一個值」的 1-D 陣列就是合法的 cluster bootstrap；`paired_permutation_test` 做配對比較 | 新增 | 現在三個數字都是無 CI 的點估計，而 15 × n 列**不獨立**（同一件衣服 15 條軸）。既有函式的 docstring 已引 Smucker et al. CIKM 2007 |
| **C4** | **濾掉被折疊的極**，用 `table.folded`；Holm 校正跑 **11** 個檢定 | `eval_visual_domain.py::prof` | 見 §4.2 |
| **C5** | **報使用者看得到的失敗**：top-3 集合重疊（Jaccard）＋**第 1 名要素翻轉率** | 新增 | 卡片顯示的是前 3 名。照片幾乎沒表現的軸上 \|Δz\| 大是無害的；**頭條要素翻掉才是 demo 會爆的失敗** |
| **C6** | **只用參考側開閘，並掃出 risk–coverage 曲線**：把 `both = (|a|>0.25)&(|b|>0.25)` 改成只看 `|z_flat| > τ`，掃 τ ∈ {0.25, 0.5, 0.75, 1.0, 1.5, 2.0} | `:167-169` | 現在**兩側同時開閘等於對結果做條件化**，選出了「兩邊都同意這條軸有表現」的子集，**把翻轉率系統性壓低**。改成單側之後，那條曲線**就是棄權規則本身**（Geifman & El-Yaniv NeurIPS 2017；`attribute_fill.py::coverage_at` / `threshold_for_precision` 已實作同一套邏輯） |
| **C7** | **加修正 arm，並在 garment 層級切 train/test** | 新增 | 現在只量問題、不測任何修法。見下表 |
| **C8** | **檢索側索引所有 flat（~7,959），不是只索引抽到的 n 件**；明確報 gallery 大小。另加 pipeline 級的 w sweep | `:104-131` | 800 件的 gallery 會把 R@1 灌水，而且無法和公開的 In-Shop 數字比。Street2Shop 的 gallery 是 75k–170k |

#### C7 的五個 arm（在 held-out 的那一半 garment 上評估）

| arm | 做什麼 | 為什麼值得試 |
|---|---|---|
| **A0** | 現況（無 centering） | 基準 |
| **A1** | `distribution_normalize=True`（減商品庫平均圖片向量，再 L2） | **同時修掉缺口 #2（兩把尺）**。`concepts.py:65-66` 已實作，repo 自引 Zhou et al. NeurIPS 2023 |
| **A2** | **減查詢域自己的平均**：on-model 查詢減 mean(on-model 校準集)，flat 減 mean(flat)。**只用 train 那一半 garment 估** | 這是最便宜的域校正。**必須切 train/test，否則是拿測試集的平均去校正測試集** |
| **A3** | **逐要素仿射再校準** `z' = (z − b_d)/s_d`，`b_d`/`s_d` 在 train 半估 | 如果 C2 顯示偏誤是**常數**，這個就能修掉；如果偏誤隨衣服變動，它不會有用——**這正是 C2 要回答的** |
| **A4** | **VLM 第二意見**：`scripts/vlm_tag_attributes.py` 對同一批 on-model 與 flat 圖跑一次，比較 `c_<el>` 的跨域一致性 | §3.3c 量到 VLM 在**亮面材質**上 AUROC 0.90 vs CLIP 0.71。如果 VLM 的跨域偏誤明顯小，`full_concept_hybrid` 的 `vlm_elements` 就有第二個獨立理由。**⚠️ 成本**：兩倍圖片數 × 0.09–0.39 秒/件，要 GPU |

#### 指標、對照組、檢定力

- **對照組（T16 已經對了，保留）**：(i) **flat vs 同一件的另一張 flat** = 量測噪音下限；(ii) **flat vs 隨機另一件衣服** = 不一致的上限。建議把 (ii) 從「`usable[(i+1) % len]` 一件」改成**平均多件隨機**，降低變異。
- **主要結果表**：每要素 × 每 arm，報 `bias [CI]`、`mean|Δz|`、`sign_flip@τ`、`top3_jaccard`、`headline_flip`，全部附對 (i) 的配對 p 值與 Holm 校正後的判定。
- **檢定力（INF，標準配對檢定的比例推算）**：held-out n ≈ 500 件衣服、Holm 最壞情況 α = 0.05/11 ≈ 0.0045（雙尾 z ≈ 2.84）、power 0.8（z ≈ 0.84）⇒ 可偵測的標準化效果量 `d = (2.84+0.84)/√500 ≈ 0.165`。也就是說：**如果每件衣服的 Δz 標準差約 1 個商品庫 SD，我們能偵測到約 0.17 SD 的域偏誤。** 修完 C1/C10（快取參考分布）之後 n 可以推到 800+，就不用在 150 件上做 11 個檢定。
- **預期效果量（INF，要被證偽）**：幾何／結構軸（`crisp_collar`、`visible_logo`、`bold_pattern`）的 |bias| 落在噪音下限的 1.5 倍以內；`dark_tone`、`matte/glossy` 的 |bias| 明顯大於下限且**有一致的符號**。理由是 §3.3b/3.3c 的域內 AUROC 排序，以及 DeepFashion CVPR 2016 Table 2 的 shape/part > texture/fabric 排序。**如果實測反過來，那是個更有意思的結果，照實寫。**

#### 怎麼讀結果（三種結局，各自的行動）

1. **偏誤小、噪音小** → 側寫跨域可用，但**仍然只放 11 條軸的前 3 條**（§4.2 的 UI bug 與 C5 的頭條翻轉率獨立於域偏移）。
2. **偏誤大但是常數**（A3 修得掉）→ 上校準表，並在畫面上標「已做拍攝域校正」。
3. **偏誤隨衣服變動**（A3 修不掉）→ **走棄權**：只顯示 |z| 過 C6 曲線選出的門檻的軸，其餘明講「這張照片看不出來」。**這是最可能的結局（INF），而且它剛好也是 §5.4 對製造商最有價值的產品形態。**

### 4.4 額外的、幾乎免費的側寫驗證（不需要 In-Shop）

**一致性回歸測試**（`docs/research/industry-recsys-practice.md:458-460` 提過，但它假設了一個現在不成立的前提）：同一張**商品庫**圖片經 `element_profile` 算出的 z，應該等於 `design_scores` 那一列。**現在對預設 arm 會不相等**（缺口 #2）。**所以這個測試的第一個版本會失敗——而那正是它的價值**：把它寫進 `tests/`，它會釘住「兩把尺」這個 bug 不再回歸。

---

## 5. Q4 製造商拿到一張照片時真正想要的東西

### 5.1 產業先例：有，而且最強的那個就在我們自己的文件裡

| 先例 | 是什麼 | 數字 | 出處 |
|---|---|---|---|
| **Walmart Trend-to-Product** | AI 彙整趨勢 → mood board → **產出指導供應商生產的 tech pack**，設計師精修 | **前置期 6 個月 → 6–8 週**（少 18 週） | `industry-fashion-brands.md` b9（V） |
| **techpacks.co**（付費服務） | 自述客戶交付物就是「rough sketches or **images** of your design… and a sample/prototype」，**由人**寫成 tech pack | — | 官網（V）。**第一手證明「照片進 → spec 出」是一個既存的商業流程，只是人工執行** |
| **Design2GarmentCode**, **CVPR 2025** | **圖片／文字／設計草圖** → LMM → **參數化打版程式** → 「size-precise sewing patterns with correct stitches」 | — | arXiv 2412.08603（V）。**簡報要引的就是這一篇** |
| **Sewformer**, SIGGRAPH Asia 2023 / ACM TOG | **單張日常照片 → 完整縫製版型**（panels + seams），兩層 Transformer | 合成訓練集 **SewFactory ~100 萬 圖／版型配對** | arXiv 2311.04218（V）。**那個 100 萬很重要：它是「配對資料要多少」的答案** |
| **GarmentCode / GarmentCodeData**, SIGGRAPH Asia 2023 / 2024 | DSL 把設計參數 + 身體尺寸編譯成合法版型幾何；115,000 合成樣本 | — | arXiv 2405.17609（V，**會議收錄本輪只確認到 preprint**） |
| **ZOZO Fashion Intelligence System** | 把「casual/formal」這種**模糊印象語**和穿搭影像放進同一嵌入空間，用 Attribute Activation Map 顯示對應區域 | **自承需要乾淨照片與專業標註，未宣布上線** | ESWA 2022（V，`industry-fashion-brands.md` b10）。**這是我們 element profile 最接近的先例——包括它的警告** |
| **Stitch Fix Hybrid Designs** | 把服裝當屬性組（"genes"），用客戶回饋當 fitness 重組，**再由設計師審核** | — | Algorithms Tour（V） |

**PLM／CAD 端：找不到任何「照片 → spec」的已出貨功能**（Centric AI Studio 是概念／視覺**生成**、Bamboo Rose 只有空話、CLO3D / Style3D 沒有 photo→pattern、Techpacker 沒有）。⚠️ 但有一半的頁面載不到，所以講成**「在我們載得到的範圍內沒有」**。附帶情報：**raspberryai.com 現在導向 GoDaddy 的域名出售頁**（2026-09），引用它當競品前先查。

**一個對贊助商有用的策略洞察**（V，三個產業來源一致）：tech pack 的**作者**是品牌側的 technical designer / product developer，**工廠的版房是消費者／執行者**。所以對成衣製造商，這個工具的定位應該是**「幫品牌交給我們一份我們真的能執行的 pack」——降低製造商的來回溝通成本**，不是幫設計師省畫圖時間。

### 5.2 哪些屬性看得出來、哪些看不出來（有硬數字）

**我們手上最重要的一張表**：DeepFashion CVPR 2016 Table 2（**V，逐頁讀 PDF**），FashionNet 完整版的屬性預測 top-3 / top-5 **recall**：

| 群 | Category | Texture | Fabric | Shape | Part | Style | All |
|---|---|---|---|---|---|---|---|
| FashionNet (full) | **82.58 / 90.17** | 37.46 / **49.52** | 39.30 / **49.84** | 39.47 / **48.59** | 44.13 / **54.02** | 66.43 / 73.16 | 45.52 / **54.61** |

**要進簡報的一句話：品類分類 top-5 約 90%，屬性只有它的一半（texture/fabric/shape 約 50% recall@5，全體 54.6%）。** 論文自己的解釋是 shape 和 part 相對好，因為「discriminative information of these attributes normally exist around clothing landmarks」。（Style 的原始 recall 最高，但那一群屬性數少，recall@k 機械性地容易——不要讀成「風格很好判」。⚠️ 也要註明：這是 2016 年、1,000 個屬性多標籤空間、recall@k 的基準，現代模型會更好，但**排序**站得住。）

**第二張同樣重要的表**：Fashionpedia（ECCV 2020，V）的 294 個屬性分 9 個超類（Nickname 153、Silhouettes 25、Neckline 25、Textile Pattern 24、**Textile finishing / Manufacturing techniques 21**、Length 15、Non-Textile Type 14、**Opening Type 10**、Waistline 7），而**論文自己報告，標註階段最難的兩類是 Opening Type（32.69% 答「不確定」）與 Waistline（30.46%）**，原因是遮擋與視角。

> **這是整份簡報最有力的一句話：連*專家人類標註員*都對三分之一的「閉合方式」從照片答不出來。而閉合方式正是製造商最需要的欄位之一。**

**材質的硬天花板**（V）：整個材質辨識文獻的粒度是「布料 vs 金屬 vs 木頭」——**MINC（CVPR 2015）23 類、patch 準確率 85.2%；FMD 只有 10 類，其中「Fabric」是*一*類**。**沒有任何纖維成分的 benchmark。而且我找不到任何從影像估 GSM／克重的論文或資料集**（搜尋不可用，不能宣稱絕對沒有，但這和物理一致：GSM 是單位面積質量，成分是分子層級，兩者都不在 RGB 像素裡，除非有參考尺規、已知光照或光譜儀）。**要講成設計約束，不是模型限制。**

**誠實的三分法**：

| 可信讀出（幾何／結構，landmark 附近） | 中等（讀，但附信心，預期約 50% recall@5） | **不要宣稱，回「unknown」並請對方補** |
|---|---|---|
| 輪廓、品類、袖型／長度、領口／領型、衣長、腰線位置、印花／圖案**類型**、顏色／配色 | 口袋有無與粗略類型、可見輔料、**針織 vs 梭織**（高解析度下看得到，但吃解析度）、裡布有無（只有翻開才行）、紋理類別、圖案**repeat 尺寸**（需要畫面內有尺規） | **纖維成分**（無此粒度的 benchmark）、**克重／GSM**（物理上不在像素裡）、**彈性／垂墜／手感**（力學性質）、**縫型／線步／SPI**（要微距拍縫線，整件照差 2 個數量級）、**閉合方式**（專家 32.69% 答不出來）、**版型鬆量**（要人體尺寸）、**精確 POM 尺寸**（無尺規） |

### 5.3 VLM vs CLIP：我們自己的證據比文獻更直接

**文獻上 CLIP 系在「屬性綁定／組合性」上結構性地弱**（V）：
- **ARO（ICLR 2023 Oral）**：Visual Genome Attribution，隨機 = 50%，**CLIP 只有 62%**（BLIP 88、X-VLM 87）。結論是對比式預訓練能拿到很強的檢索、**卻沒學到組合結構**。
- **MMVP（2024）**：人類 95.7%、GPT-4V ~88%、Gemini ~86%、**LLaVA-1.5 ~29%、隨機 25%**。九個視覺模式裡有四個正是我們的失敗模式：Presence of Specific Features（有沒有口袋）、Structural and Physical Characteristics（結構）、Viewpoint and Perspective（正面 vs 背面）、Quantity and Count（幾顆扣子）。**→ 不要假設 8B 的 VLM 繼承了前沿模型的表現。**

**但我們手上有更直接的證據，而且它比文獻更該被相信**（都是我們自己量的）：

- **§3.3c（397 件目視標註）**：亮面材質 CLIP 0.71 → **Qwen3-VL 0.90**；logo 0.96 → 0.98；領子 0.97 → 0.98；圖案 0.90 → 0.94；**寬鬆版型 CLIP 0.86 > VLM 0.77**。
- **§3.19 的循環性修正**：第一版看起來 VLM 大勝，但那是**拿 Qwen 自己補的 `occasion` 當標準答案**。清乾淨之後**結論翻轉**——VLM 在正式感／休閒／深色／鮮豔四軸上**沒有**勝過 CLIP 反義詞，顏色類還明顯較差。
- **§3.13**：VLM 會誠實回答「不適用」：肩線 46%、領子 61%、版型 26%。

> **這兩件事合起來，就是 Q4 的答案**：我們**已經**有一個「spec + 信心 + 棄權」引擎（`scripts/vlm_tag_attributes.py`），已經在 17,783 件上跑完、答案格式正確率 99.99%、**0.09–0.39 秒/件**，而且它的 `na_<el>` 欄位就是棄權訊號。**缺的不是模型，是題目。**

**⚠️ 我沒找到任何時尚屬性上 VLM 標註 vs CLIP 零樣本的公開 head-to-head benchmark**（GAP）。這其實對我們有利：**§3.3c 就是那個 benchmark**，只是標註員也是 LLM（§3.3c 自己註明了這個偏誤方向）。`data/labels/human_tasks.csv` 的 140 題真人盲標（`engine02-design.md:104`，**還沒填**）是把它變成真證據的那一步。

### 5.4 建議的產品形態：spec 卡，不是相似商品

```
參考照片 → ┌─ 11 條設計軸 × {z, 百分位, 信心, 是否棄權}      ← element_profile + 校準門檻
           ├─ 製造相關屬性 × {值, 信心, 「看不出來」}          ← vlm_tag_attributes 加題
           ├─ 「這 7 個欄位照片看不出來，請提供」               ← 明確的洞
           └─ 目錄裡最接近的 5 件（每槽一條）                  ← 純圖→圖 + 品類約束
```

**加題的具體做法**：`scripts/vlm_tag_attributes.py::QUESTIONS`（`:28-39`）現在 10 題。加 5 題，**同一次 forward、同一個 letter-probability 讀法、同一個「not applicable」選項**，成本幾乎不變：

| 新題 | 選項 | 為什麼可信 |
|---|---|---|
| 閉合方式 | 拉鍊 / 扣子 / 套頭 / 其他 / **not applicable** | Fashionpedia 說專家 32.69% 答不出來 → **`na_` 會高，而那正是誠實的輸出** |
| 袖長 | 無袖 / 短袖 / 長袖 / not applicable | Fashionpedia Length 群；幾何類，預期可信 |
| 領口 | 圓領 / V領 / 高領 / 襯衫領 / not applicable | Fashionpedia Neckline 25 屬性；§3.3c 領子 AUROC 0.98 |
| 口袋 | 有可見口袋 / 無 / not applicable | MMVP 的「Presence of Specific Features」是弱項 → 預期信心低，**要驗** |
| 針織 vs 梭織 | 針織 / 梭織 / not applicable | **已經有這題**（`knit`），但**沒有映射到 `athletic_style` 以外任何要素**，也沒單獨呈現 |

**⚠️ 要避開 §3.19 的循環性陷阱**：新題目的標準答案**不能**是任何模型補出來的欄位。要嘛用 `data/labels/` 的人工／目視標註，要嘛新標 40 件。**這一條要寫進交給任何 sub-agent 的 brief。**

**額外情報**：`ELEMENT_MAP` 只覆蓋 15 個要素中的 **14** 個——**`athletic_style` 沒有對應題目**（我用 `vlm_attributes_*.meta.json` 驗過）。而聚陽 **52% 是機能運動服**（`industry-fashion-brands.md`）。**這是一個一題就能補的缺口。**

---

## 6. Q5 現場的健壯性

### 6.1 好消息：一半已經做了

`engine02/api.py::_encode_upload`（`:170-203`，commit `6005e29`）**已經**處理：EXIF `exif_transpose`（`:185`）、RGBA/LA/P **合成到白底**（`:186-189`）、`convert("RGB")` 收掉 CMYK（`:190`）、1600 px 上限（`:191-192`）、`MAX_IMAGE_PIXELS = 80_000_000` 防解壓縮炸彈（`:182`）、**解碼前**就擋的 12 MB 位元組上限（`:404-406` → 413）、壞 base64 → 400、臨時檔 `finally: unlink`（`:202-203`）。`tests/test_api.py:162-204` 有透明 RGBA、CMYK JPEG、2400×1800 超大、垃圾位元組、413 的回歸測試。**這一節的一半是「已經做對了，別動」。**

### 6.2 還缺的，逐項給守門與位置

| 失效模式 | 現狀 | 守門（含確切 API） | 放哪裡 |
|---|---|---|---|
| **EXIF 旋轉** | ✅ 已做 | — | — |
| **瀏覽器 vs PIL 的旋轉不一致** | ✅ 已做，但值得寫進 docstring | 現代瀏覽器預設 `image-orientation: from-image`，使用者**看到的是轉正的**，Pillow 不轉。**這是實務上最會出的 bug**，我們已經避開了。**另一個陷阱**：轉正後若把原始 `exif` bytes 再 `save(exif=...)`，會把舊的 orientation tag 塞回去——`exif_transpose` 會移除該 tag，**不要重新注入** | `_encode_upload` 註解 |
| **非 Adobe 慣例的 CMYK JPEG** | ⚠️ 會**靜默色彩反轉** | Pillow 的 `JpegImagePlugin` 對 CMYK **無條件假設 Adobe 反相慣例**（原始碼 `rawmode = "CMYK;I"  # assume adobe conventions`）。守門：`if img.mode == "CMYK" and "adobe" not in img.info:` → 加一條 warning（不要拒絕） | `_encode_upload` |
| **16-bit PNG / `I;16` / `F`** | ⚠️ `convert("RGB")` **截在 255，整張變白** | 走 numpy 重新縮放後轉 `L`：`a = np.asarray(img).astype("float32"); a = (a - a.min())/max(a.ptp(),1e-6)*255` | `_encode_upload` |
| **調色盤透明度（`P` + `tRNS`）** | ⚠️ 現在 `P` 直接進 RGBA 分支，**大致對**，但 `info["transparency"]` 沒讀 | `img.convert("RGBA" if "transparency" in img.info else "RGB")` | `_encode_upload` |
| **HEIC/HEIF（iPhone）** | ❌ 完全沒有 → `UnidentifiedImageError` → 400 | `pillow-heif`（**BSD-3-Clause**，有 Windows wheel，CPython 3.10–3.15）：`from pillow_heif import register_heif_opener; register_heif_opener(thumbnails=False)`。**⚠️ 兩個註記**：(a)「iOS Safari 上傳時會轉成 JPEG」這件事我**本輪無法核實**，**不要靠瀏覽器幫你轉**；(b) **`pi_heif` 已停止維護（1.4.0 是最後一版）**，2023 年的教學會叫你裝死掉的那個 | `api.py` 模組層註冊一次 |
| **動畫 GIF / 多幀 TIFF** | ⚠️ 現在取 PIL 預設幀（通常是 0，但沒明寫） | `if getattr(img, "n_frames", 1) > 1: img.seek(0)`。**Pillow 文件的陷阱**：「Seeking to later frames in a `P` image will change the image to `RGB`」，而且 GIF 的第 2 幀之後可能是**局部 delta**——**永遠不要抓中間幀** | `_encode_upload` |
| **SVG / 非影像位元組 / 錯 MIME** | ⚠️ 只靠 PIL 嗅探（其實**已經夠**，因為輸入是 JSON 裡的 base64，沒有 `content_type` 可騙） | 如果哪天改成 multipart：**`imghdr` 在 Python 3.13 已移除**，用 `puremagic.what()`（官方 what's-new 直接這樣寫）；`python-magic` 在 Windows 要找 libmagic DLL，**我們在 Windows 上，建議用純 Python 的 `puremagic` / `filetype`**。**SVG 不是安全的「圖片」**（是 XML，可帶 script 與 XXE）→ 直接拒。**最強的一招我們已經在做**：解碼後重新編碼成 PNG（`:193-195`），一次剝掉 EXIF、附加酬載與 polyglot 結構 | `_encode_upload` |
| **請求體上限** | ⚠️ 只有應用層的 12 MB | **部署陷阱，一定要寫進 runbook**：nginx `client_max_body_size` **預設 1m**，**會靜默擋掉一般手機照片**，而且「browsers cannot correctly display this error」。Starlette 現在有 `RequestBodyLimitMiddleware(max_body_size=...)`，會用 Content-Length 先擋、**也一定累計實收位元組**（所以擋得住低報的 header）。**base64 in JSON 有 4/3 的膨脹**，而 `await request.json()` 會把整個 body 讀進記憶體 → **每個併發請求要預算約 4 倍圖片大小的 RAM** | nginx 設定 + `api.py` middleware |
| **截圖帶 UI 邊框 / 縮圖 / 重度濾鏡** | ❌ 沒有 | **這一塊公開的科學很少，門檻是民俗，必須在自己的資料上校準（V 的只有下面這兩條）**。可用啟發式：比對常見機種解析度；無 EXIF + PNG 是強聯合訊號；算逐列色彩變異數、標出橫貫全寬且近零變異的列（狀態欄／導航欄）；長寬比 > 2.0。**低解析度**：`min(w,h) < 224` 直接拒（CLIP 輸入就是 224，更小的純粹是上採樣）；Anthropic 文件獨立佐證「very small images under 200 pixels」會出錯。**模糊**：Laplacian 變異數（Pech-Pacheco et al., ICPR 2000），**但 pyimagesearch 那個 threshold=100.0 明文說要逐資料集調，而且和解析度相關——不要照抄** | 新函式 `api.py::_upload_warnings(im)` → 回 `warnings` 不要拒 |
| **非服裝照** | ❌ 沒有 | 見 §1 缺口 #7：**MCM**（NeurIPS 2022）負向 prompt 集 + softmax，**加**到商品庫的 k-NN 距離（KNN-OOD, ICML 2022——**對我們幾乎免費，`engine.image_emb @ q` 已經在算了**）。門檻取域內分數第 5 百分位（= 95% TPR，領域慣例的 FPR95）。**⚠️ 預期最弱的一格**：MCM 論文裡最難的 OOD 集是 **Texture（FPR95 57.77）**——正好是布料特寫，而那是服裝使用者**合理**會上傳的東西。**要預留這個坑** | `concepts.py::domain_gate` |
| **`constraints` 壞 key** | ❌ **500** | `api.py:419` 的 `HardConstraints(**body.constraints)` 包 try/except → 400 | `api.py::visual_search` |

### 6.3 隱私：如果評審上傳一張有人的照片，我們該怎麼做、怎麼說

**先把法律講精確（這題大部分人會講錯）**（全部逐字核對 gdpr-info.eu，V）：

- **Art. 4(1)**：照片裡有可識別的人 → **是個資**。上傳的那一刻我們就有 GDPR 義務。
- **Art. 4(14)**：生物識別資料要求「**specific technical processing**」且「**allow or confirm the unique identification**」。
- **Recital 51 是決定性的那段**，逐字：「The processing of photographs should **not systematically** be considered to be processing of special categories of personal data as they are covered by the definition of biometric data **only when processed through a specific technical means allowing the unique identification or authentication** of a natural person.」
- ⇒ **一張普通照片不自動是生物識別資料，也不自動是 Art. 9 特種資料。** 我們的服裝屬性抽取**兩個條件都不滿足**（我們在分類衣服，不在識別人）→ **Art. 9 不適用，不需要 9(2)(a) 的明示同意（在生物識別這個理由上）。**
- ⇒ **加上人臉*偵測*之後**：偵測（有沒有臉）**不是**唯一識別，依 Recital 51 的讀法仍在 Art. 9 之外；而且**純粹為了模糊而偵測是一個資料最小化措施，對我們有利**。人臉*辨識／比對*才會踩進 Art. 9。**「偵測即模糊」是法律上最乾淨的設計。**
- **不管 Art. 9 適不適用，這些都還在**：Art. 5(1)(a) 透明、5(1)(c) **資料最小化**、5(1)(e) 儲存限制、5(1)(f) 完整性。**Art. 35 DPIA** 在「大規模處理 Art. 9(1) 特種資料」時特別需要——**一個黑客松 demo 既非大規模也非 Art. 9 → 不觸發 DPIA。被質疑時就這樣講，這是乾淨的論證。**
- **EU AI Act Art. 5 的兩條紅線**（V）：**5(e)** 禁止「untargeted scraping of facial images」建臉部辨識資料庫 → **不要從靈感照建人臉索引**；**5(g)** 禁止用生物識別資料推論種族／政治／宗教／性傾向 → **不要從穿衣服的人身上推論人口統計特徵**（這在時尚 AI 裡是個很誘人的「功能」）。

**已部署產品怎麼做**：唯一核對到的一手政策是 Anthropic 自己的 vision docs（V）：「Claude **cannot be used to name people in images and refuses to do so**」、「Image uploads are **ephemeral and not stored** beyond the duration of the API request」、「Claude does not parse or receive any metadata from images」。**Google Lens / Pinterest / Bing 的人臉政策本輪都載不到，不要引用。** Clearview AI 的罰款數字我也**沒能核實，上台前要查。**

**建議的處置（要講成「我們的設計選擇」，不是可引用的準則——我沒找到任何權威的「黑客松隱私標準」）：**

1. **只在記憶體**。現在 `_encode_upload` 會**寫一個臨時 PNG 到磁碟**（`:193-195`，因為 `Encoder` 協定只吃 path）——**這是唯一需要改的隱私點**。要嘛給 `Encoder` 加一個吃 PIL 物件的路徑，要嘛至少確認 `finally: unlink` 覆蓋所有例外路徑（**現在是有的**，`:202-203`）。
2. **不落地、不記錄像素**。只記尺寸、格式、雜湊。**最常見的失誤是 debug log 印 base64。**
3. **上傳前一句固定文案**（Art. 5(1)(a)）：「您的照片只在記憶體中處理以讀取服裝設計要素，不會被儲存；我們不辨識照片中的人。」
4. **在任何顯示／快取／送外部 API 之前先偵測並模糊人臉**（Art. 5(1)(c)）。
5. **剝 EXIF**——`exif_transpose` + 重新編碼順手丟掉 **GPS 座標**，那是我們毫無用處的個資。§6.2 的「重新編碼」同時是安全與隱私控制。
6. **模糊要不可逆**。小 σ 高斯理論上可反捲積、實務上仍可辨識。用**下採樣再上採樣（像素化）**，或把核大小按人臉框縮放（σ ≈ face_width/6），不要固定 σ=5。

**人臉偵測選項**（授權 + 數字都核對過，V）：

| 選項 | 授權 | 準確度 | 延遲 |
|---|---|---|---|
| **YuNet（OpenCV Zoo）⭐ 建議** | **MIT** | **WIDER Face AP：Easy 0.8844 / Medium 0.8656 / Hard 0.7503** | repo 未公布；~5–15 ms CPU（**估計**） |
| MediaPipe BlazeFace | 程式碼 Apache 2.0；**模型 CC-BY 4.0** | — | **短距模式 2.94 ms CPU / 7.41 ms GPU（Pixel 6，官方數字）** |
| OpenCV Haar | Apache 2.0 | 弱，只有正面，誤報多 | ~10–50 ms VGA CPU（估計） |
| RetinaFace / SCRFD | 程式碼 MIT，**但 insightface 的訓練資料與模型「non-commercial research purposes only」** ⚠️ | WIDER hard AP 91.4% | 論文稱單核 CPU 可即時 |
| YOLOv8-face / YOLOv5-face | ⚠️ **AGPL-3.0** | — | — |

**建議 YuNet**：MIT 無附帶條件、數字真的好（hard 0.7503）、模型檔很小、**內建於 OpenCV 所以沒有新依賴**。
**#1 大坑**：`det.setInputSize((w, h))` **每次影像尺寸變動都要重呼叫**，否則偵測框回在錯誤的座標系。`detect()` 回一個 `[num_faces, 15]` 的 Mat（0-3 bbox、4-13 五個 landmark、**14 是分數**）。另外 opencv_zoo 的 demo 是自己包了一層 `YuNet` 類別，直接複製 demo 拿到的是 wrapper 不是原生 API。

**要額外做的一個實驗（便宜又有說服力）**：模糊人臉**前後**，同一張照片的 11 軸 z 變化應該小於域內噪音——**臉不應該影響服裝判讀**。20 張照片就能看出來，而且它同時證明「我們的隱私措施沒有損害功能」。

---

## 7. 給 coordinator 的建議（排序）

### 🥇 建議 #1：純照片上傳時，讓照片當查詢本體（w=1.0），並關掉 BM25

**為什麼排第一**：**30 分鐘的改動**，而且它修的是「精準」這個目標本身最大的單一漏洞。現在 80% 的查詢向量是 `embed("clothing")`。

**`檔案:函式` 與實作草圖**

1. `engine02/api.py::visual_search`（`:381-424`）：
   ```python
   photo_only = not body.retrieval_text.strip()
   ...
   if photo_only:
       req.retrieval_text_normalized = False   # 既有機制：本輪只走 dense（pipeline.py:244）
   ```
2. 查詢向量：**不要改 `pipeline.py`**。用既有的覆寫 hook `engine02/composed.py::ComposedEngine02.query_embedding`（`:321-324`）——它的存在理由就是「替換單次呼叫的查詢向量，其餘走正常 pipeline」。或者更小的改動：在 `engine02/config.py` 新增一個 arm
   ```python
   "visual_photo_first": replace(FULL, name="visual_photo_first", z_clip=3.0,
                                 concept_image_weight=1.0, w_bm25=0.0),
   ```
   並讓 `visual_search` 在 `photo_only` 且呼叫端沒指定 `arm` 時選它。**新增 arm 比改預設 arm 安全**：`full_zclip3` 的所有既有數字不受影響，`GET /arms` 自動列出來，消融表可以直接加一列。
3. `api.py` 回傳裡把實際用的 `arm` 與 `concept_image_weight` 誠實吐出來（**已經在做**，`:409`、`:423`）。

**確切的驗證實驗**
- **資料**：`<dir>/dfinshop`（重建，216 MB / 15–20 分鐘）。
- **任務**：只把 flat 圖進索引，用同一件衣服的 `_1_front` 當查詢，`retrieval_text=""`，**走完整 pipeline**（不是裸點積）。
- **Sweep**：`concept_image_weight ∈ {0, 0.2, 0.5, 0.8, 1.0}` × `w_bm25 ∈ {0, 0.5}`。
- **指標**：R@1 / R@10 / MRR，**gallery = 全部 flat（~7,959），要報 gallery 大小**。
- **基準**：`full_zclip3`（w=0.2, w_bm25=0.5）＝ 現在上線的東西。
- **統計**：`engine02/eval/metrics.py::paired_permutation_test` 逐衣服配對 + `bootstrap_ci`。
- **預期效果量（INF）**：w=0.2 → w=1.0 的 R@1 提升應該**大於一個數量級**，因為 w=0.2 時的查詢向量幾乎不含照片資訊。**如果沒有，那說明我的程式碼讀錯了，請以實測為準。**
- **必要的 sanity check**：`w=0` 應該退化成「用 `embed("clothing")` 檢索」＝ 幾乎隨機。如果 w=0 就已經不錯，代表 In-Shop 的 gallery 太容易，要加大 gallery。

**Demo 那一句**
> 「拖一張照片進來——我們不是拿它去*微調*一句查詢，它**就是**查詢。同一顆編碼器索引了商品庫，所以照片和商品在同一個空間裡。」

---

### 🥈 建議 #2：把 T16 修好並跑掉，加 5 個修正 arm

**為什麼排第二**：這是唯一能把 §3.16 的 caveat 從「我們猜」變成「我們量過」的實驗，而**簡報上那句 caveat 現在是我們最大的未量測風險**。骨架已經寫好了。

**`檔案:函式`**：`scripts/eval_visual_domain.py`（全部 8 項修正見 §4.3）＋ `engine02/concepts.py::element_profile` 加 `distribution_normalize` 與 `catalog_stats` 參數。

**確切的驗證實驗**：§4.3 的完整規格。摘要：
- **資料路徑**：`<dir>/dfinshop`（`items.parquet` + `images/`，`item_id` 逐字保留）。
- **分組**：`ID_RE`（`:44`），garment = `.+_id_\d+_\d+`，視角 = 尾綴。
- **主指標**：每要素**有號偏誤** `b_d = mean_g(z_model − z_flat)` [bootstrap CI]；副指標 `mean|Δz|`、`sign_flip@τ`（單側開閘）、`top3_jaccard`、`headline_flip`。
- **對照組**：flat vs 同一件的另一張 flat（噪音下限）；flat vs 多件隨機衣服平均（上限）。
- **基準 arm**：A0 = 現在的 `element_profile`（無 centering、無遮罩、15 軸）。
- **統計**：按 garment 叢集 bootstrap；對對照組 (i) 做配對置換；**Holm 校正 11 個檢定**。
- **檢定力**：held-out n ≈ 500 ⇒ 可偵測 ≈ **0.165 SD** 的偏誤（INF，比例推算）。
- **預期效果量（INF，要被證偽）**：`crisp_collar`/`visible_logo`/`bold_pattern` 的 |bias| ≤ 1.5 × 噪音下限；`dark_tone`/`matte-glossy` 的 |bias| 明顯大於下限且**符號一致**。

**Demo 那一句**
> 「這是我們自己找出來的弱點，而且我們去量了它：同一件衣服，穿在模特兒身上和平放拍，我們的 11 條設計軸有 N 條會偏移超過噪音下限——**所以這幾條我們不顯示，會告訴你『看不出來』。**」

---

### 🥉 建議 #3：側寫加上棄權、適用性遮罩、折疊反義極，並修掉「兩把尺」

**為什麼排第三**：它把 #2 的量測結果變成一個**產品行為**，而且三個零件（`applicability_mask`、`table.folded`、`threshold_for_precision`）**全部已經寫好了，只是沒被接起來**。

**`檔案:函式`**
1. `engine02/concepts.py::element_profile` — 加 `distribution_normalize: bool = False`（對齊 `design_scores:65-66`）、`categories`／`applies_to` 遮罩、依 `table.folded` 濾極、回傳多兩個欄位 `confidence` 與 `abstain`。
2. `engine02/api.py::visual_search:414` — 傳 `distribution_normalize=ARMS[arm].concept_dn`。
3. `engine02/api.py:416` — `profile_note` 改寫。**現在那句話是假的。**
4. 門檻來源：`engine02/attribute_fill.py::threshold_for_precision` / `coverage_at`（`:181-203`，**已實作且已引 Guo et al. ICML 2017 + Geifman & El-Yaniv NeurIPS 2017**）。

**確切的驗證實驗**
- **一致性回歸測試（零成本，馬上做）**：`tests/test_api.py` 加一個 case——拿一張**商品庫內**的圖，`element_profile` 的 z 必須逐條等於 `Engine02._design_scores()` 那一列。**這個測試現在會失敗**，那就是缺口 #2 的證明。修完後它釘住不再回歸。
- **門檻校準**：`data/labels/labels_part_*.csv`（420 件）與 §3.3c 的 397 件目視標註 → 逐要素的 risk–coverage 曲線 → 取 dev 上達到目標精確率 0.9 的最小門檻（**和 §3.11／§3.17 的補值用同一套方法、同一個目標值**，這樣簡報上只要講一次）。
- **跨域門檻**：用 #2 的 C6 曲線。
- **預期**（INF）：`crisp_collar`/`visible_logo`/`bold_pattern` 的 coverage 高（AUROC 0.90–0.97）；`glossy_fabric` 的 coverage 會**很低甚至 0**——**那是正確答案**，AUROC 0.71 的 CI 含 0.5。

**Demo 那一句**
> 「這張照片我們讀出 4 條設計軸，另外 7 條我們明講看不出來。**對做衣服的人來說，『我不知道你的克重，請你給』比一個編出來的數字有價值得多——編錯一次就是一批貨。**」

---

### 4️⃣ 建議 #4：多件衣服 —— 先做前端切圖，再做 MIT 授權的偵測器

**`檔案:函式`**
1. **Tier 0**：前端 cropperjs（MIT）。伺服器**零改動**——`/visual-search` 收到的就是一張 crop。
2. **Tier 2**：新檔 `engine02/detect.py::garment_crops(im) -> list[tuple[str, Image]]`，用 `yainage90/fashion-object-detection`（**MIT**，`transformers` 的 `pipeline("object-detection")` 一行），7 類對上槽位。
3. `engine02/api.py::visual_search` 加 `slots: bool = False`；為真時對每個 crop 跑一次 `_encode_upload` 之後的路徑，**每槽一條獨立排序，並把該槽的品類塞進 `constraints.category`**（Pinterest 的 −17.1% 壞結果就是這一步換來的）。
4. **不要合併成一條清單**（§2.3：沒有任何已發表方法這樣做，而且每個已部署系統都是每槽一條）。

**確切的驗證實驗**
- **偵測側**：手工框 50 張多件衣服照（Polyvore 的 `metadata_full.parquet` 有 21,587 套穿搭可抽，但**要真的穿搭照不是去背單品**——這點要先確認）。報每槽的 IoU@0.5 命中率。**基準**：整張圖（= 一個覆蓋全圖的框）。
- **檢索側**：用 Polyvore 真實穿搭圖當 query（本機有 3,000 件 + 圖），看每槽回來的商品是否來自同一套穿搭。**基準**：整張圖一條清單。既有工具：`engine02/external.py::outfit_index`。
- **預期效果量**：Street2Shop 的 crop 增益是 1.9–4 倍（裙 11.6→45.9）；**但那是在有人工框與品類標籤的協定下**，我們的自動框會低於它。**保守預期 1.5–2 倍，逐槽報。**
- ⚠️ **Pinterest 的翻車要當風險登記**：只加 crop 不加品類約束，互動可能**變差**（−3.8% ~ −5.3%）。

**Demo 那一句**
> 「一張穿搭照裡有上衣、下身、鞋。我們不把它們混成一個向量——**分三次問，三條答案，每一條都只在它自己的品類裡找。**」

---

### 5️⃣ 建議 #5：側寫的參考分布開機時算好（效能 + 檢定力）

**`檔案:函式`**：`engine02/pipeline.py::Engine02.__init__` 旁邊加一個 `profile_reference(arm)`，落地 `<catalog>/index/profile_ref_<enc>_<table>_<mode>_dn{0,1}.npz`（存每要素的 `mean`、`sd` 與**排序後的 `r_cat`** 以便算百分位），命名沿用 `pipeline.py:164-169` 的 `design_*.npy` 慣例。`element_profile` 收一個可選的 `catalog_stats`，有就不重算。

**驗證**：`scripts/check_parity.py` 證明側寫數值**逐條不變**（既有慣例，§3.21 每一項優化都這樣證）；`scripts/bench_latency.py` 加 `/visual-search` 的 p50/p95。
**預期**：每請求 8.2e8 次乘加 → 約 4.6e4 次（**INF**，15 要素 × 4 prompt × 768 維）。**副作用比主作用重要：T16 的 `n_prof` 上限從 150 解放到 800+，11 個檢定才有檢定力。**

---

### 6️⃣ 建議 #6：域外查詢守門 + 人臉模糊

**`檔案:函式`**
1. `engine02/concepts.py::domain_gate(encoder, image_emb, vec, prompt_cache) -> dict` — 負向 prompt 集的 MCM softmax（`τ=1`，論文預設）＋ 到商品庫的 k-NN 距離（**`engine.image_emb @ q` 已經在算**）。
2. `engine02/api.py::_encode_upload` 之後、`element_profile` 之前呼叫；非服裝就**回 `warnings` 並跳過側寫**，不要拒絕請求（現場拒絕比誠實警告難看）。
3. `engine02/api.py::_encode_upload` 內加 YuNet 人臉像素化（見 §6.3 的完整程式）。
4. 警告的回傳通道：`engine02/contracts.py::ConstraintReport.input_warnings`（`:223`）**已經存在**，語意也對（「problems with the input」）；或在 `visual_search` 的 dict 加一個 top-level `warnings`。**建議後者**，因為域外與人臉不是 ENGINE 01 該修的輸入問題。

**驗證**
- 正例 5,000 張（`data/catalog/kagl/images`）、負例手蒐 100 張非服裝照（狗／UI 截圖／白板／食物／風景／**布料特寫**）。報 AUROC 與 FPR95；門檻取域內第 5 百分位。**n≥500 才報 quantile**（conformal 的慣例：n=1000、α=0.1 時實現覆蓋率約 0.88–0.92）。
- **人臉模糊的非劣性測試**：20 張有人照片，模糊前後 11 軸 z 的變化必須小於域內噪音。
- **預期**：MCM 論文 CLIP-B/16 平均 AUROC 90.77；**但布料特寫那一格會差**（Texture FPR95 57.77）。**要在簡報上先認了這一格。**

---

## 8. 不建議做（以及確切的阻礙）

| 想做的事 | 阻礙 | 結論 |
|---|---|---|
| **用配對跨域資料微調 encoder**（Myntra／Alibaba 那條路） | ①**沒有可用授權的配對消費者↔商店資料**：In-Shop 是研究用途、DeepFashion C2S 要簽同意書等 email、DeepFashion2 要等表單密碼、DressCode 明文不給私人公司；②**沒有點擊 log**（Alibaba 的 +17pp 完全靠 PVLOG）；③**規模**：Myntra 自建 150k 圖、Sewformer 用 100 萬合成配對 | ❌ **資料、授權、時程三個都缺。連最小版本都做不出來。** 誠實話術：「這是這個問題的正解，Myntra 和 Alibaba 都這樣做，我們缺的是配對資料與互動 log——這剛好是贊助商有、我們沒有的東西。」 |
| **Ultralytics YOLO（v8/11）、FastSAM、YOLOv8-face** | **AGPL-3.0，官方授權頁明寫適用於「Deploy through a SaaS platform, API」**，要求開源整個衍生作品。FastSAM 的 README 寫 Apache 但 LICENSE 是 AGPL | ❌ **demo 可以、產品不行。既然 `yainage90`（MIT）和 YOLOX / RT-DETR / DETR / Grounding DINO / OWLv2（Apache-2.0）都在，沒有理由踩這個。第一天就選對比事後重訓便宜。** |
| **`mattmdjaga/segformer_b2_clothes`** | 卡片寫 licence "other"，指向 **NVIDIA SegFormer 授權 §3.3：「only may be used or intended for use non-commercially」** | ❌ **用 SCHP（MIT）代替，而且 SCHP 公布的 ATR mIoU 82.29% 還比較高**（⚠️ 評測協定不同，不嚴格可比） |
| **從照片估克重／GSM、纖維成分、縫型／線步／SPI** | ①**沒有任何這個粒度的 benchmark**——整個材質辨識文獻是 10–23 類（FMD 只有一類叫 "Fabric"、MINC 23 類 85.2% patch 準確率）；②**物理上不在 RGB 像素裡**（GSM 是單位面積質量、成分是分子層級、縫線要微距）；③Fashionpedia 的**專家標註員**對閉合方式有 32.69% 答「不確定」 | ❌ **要講成設計約束不是模型限制。而且「明講看不出來」本身就是 §5.4 的產品賣點——編一個 GSM 給製造商是負價值（錯一次是一批貨）。** |
| **把多個 crop 的結果合併成一條排序** | **沒有任何已發表的方法或評測**（GAP）；而且池化文獻（R-MAC / GeM / sum-pooling / MOP-CNN）全部是「同一物件多區域 → 一個向量」，跨衣服池化**重新製造出我們要修的混合問題**；每個已部署系統（Pinterest / Myntra）都是每槽一條清單 | ❌ **要做就是我們自己發明。N 槽 → N 條清單才是可辯護的設計。** |
| **用「域特定 prompt」修檢索端的域偏移** | **算術上不可能**：以圖搜圖的查詢是圖片向量，文字塔不在路徑上（`pipeline.py:210-212`）。prompt 只影響 `element_profile`（`concepts.py:106-122`） | ❌ **檢索端不成立。但側寫端成立——不要把這兩件事混在一起講。** |
| **拿 `recsys-composed.md` 的 α=0 當「照片權重該低」的證據** | 那是**反向任務**：composed retrieval 要**離開**參考圖（「這件但換紅色」），參考圖只會把結果拉回原色；以圖搜圖要**貼近**參考圖 | ❌ **不要翻案，也不要引用。兩個任務的最佳 α 方向相反。** |
| **rembg / SAM 去背當域偏移的第一個修法** | ①**我沒找到任何已發表的「去背 → 檢索準確度變化」數字**（GAP）；②SAM 系是類別無關的，**不做歸屬**；③Alibaba 表 3 顯示檢索**不需要準邊界**（IoU@0.7 從 95.1 掉到 70.2，R@1 只掉 0.2pp）；④真正的問題可能只是 #1 的 w=0.2 bug | ⚠️ **不是「不要做」，是「不要先做」。** 排在 w 修正、centering、切圖之後，而且要先量再上 |
| **用 §3.15 的趨勢負結果去評估任何新項** | `eval_trends.py` 的 docstring 自承標準答案是屬性 metadata，**任何與它正交的新項都只會扣分** | ❌ **同一個陷阱會吃掉 `domain_gate` 與 spec 欄位的評估。要用各自的標準答案。**（這條是從 `social-trend-signals.md` §5.0 借來的，同樣適用。） |
| **把 `panels.py::concept_image_neighbors` 改成走 reranker** | 它的 docstring 明寫是**刻意**的 display-only（生成圖不能被呈現成「造成了推薦」）；`engine02-completeness.md:88` 與 `industry-recsys-practice.md:451` 都警告過 | ❌ **界線留著。上傳的真實照片走 `/visual-search`，那是另一條路。** |

---

## 9. 本檔的誠實限制

1. **三個子代理的 WebSearch 配額開工即耗盡（200/200）**，產業端全部改用定點 WebFetch。「沒找到」= 「我載得到的那幾頁上沒有」。具體的覆蓋洞：**Amazon StyleSnap 的架構（所有 URL 404）、Google Lens 的多物件機制、ModaNet 的細節、YOLO-World 的 FPS、YOLOX 的 CPU 延遲、Grounding DINO / OWLv2 / SCHP / yainage90 的實測延遲、rembg / U²-Net 的授權與延遲、Fashion200K / FACAD / Alibaba iFashion / Atlas、Street2Shop 現在的圖片可用率、Clearview 的罰款數字、Google Lens / Pinterest 的人臉政策。**
2. **兩個信心層級要分開讀**：Street2Shop（ICCV 2015）Table 2/3 與 Myntra（MIPR 2021）Table I–IV 是**逐頁讀 PDF**（V，數字可信到個位數）；**Pinterest KDD 2020 / 2017、Alibaba KDD 2018、eBay KDD 2017 的數字來自 ar5iv HTML 的摘要式抽取——方向可信，精確位數進簡報前要對排版 PDF 複核一次。**
3. **本輪沒能核對的引用**（標 U，不要當定論）：模態落差（Liang et al. NeurIPS 2022）、k-reciprocal 重排（Zhong et al. CVPR 2017）、αQE 的細節（Radenović et al. TPAMI 2018）、Multi-Similarity CVPR 2019 的完整 In-Shop 對照表（只拿到 80.9 → 88.0 這個錨點）、In-Shop 官方 query/gallery 清單是否混視角。
4. **我沒有執行任何實驗、沒有連伺服器、沒有改任何既有檔案。** 本檔所有預期效果量都標了 INF，而且每一條都寫了會用什麼資料、什麼指標、什麼對照組去**否證**它。
5. **本機沒有跑 T16 的語料**：`data/catalog/` 只有 KAGL 5,000 件與 Polyvore 3,000 件（含圖）。`kagl_full` / `polyvore_big` / `kagl_polyvore_filled` / `dfinshop` / `hm_caption` **都在伺服器的 `/tmp2/mzjiang/Research_Project/agents/bench/catalog/`**，本機的 HF 快取只有 README stub。**dfinshop 要重建：216 MB、15–20 分鐘。**
6. **`data/catalog/kagl/vlm_attributes_*.meta.json` 的 `n_items: 17783` 與 `valid_rate` 是舊的**（被 kagl_polyvore 那次的 meta 覆蓋）；它自己的 parquet 只有 3,494 列（5,000 件裡的 70%）。**要相信 parquet 不要相信 meta。**
7. **「設計要素 → 面料／結構規格」的對應是推論**，`industry-recsys-practice.md:500` 已經標過一次，本檔 §5.4 的新題目同樣是提案而非文獻結論。
8. **`element_profile` 完全沒有出現在 `docs/engine02-design.md` 裡**（`docs/engine02-pipeline.md:173` 只記了「端點只收 embedding，還沒收圖檔」，而那句現在也過期了）。**它是全新的、零實證的功能**——這就是為什麼建議 #2 和 #3 排得這麼前面。
9. **授權紅線**（不是研究限制，是出貨限制）：`Marqo/deepfashion-inshop` 的 HF 卡無授權標籤、上游 DeepFashion 明文僅限研究非商業 → **離線評測可以，不可出貨、不可進 git**（`external-benchmarks.md:275`、`engine02-pipeline.md:144` 已有同一條規則）。VITON-HD 是 CC BY-NC 4.0，同樣只能用於研究框架下的評測。
