# Social4Fashion 單篇查核：它會不會改變我們「不做社群趨勢預測」的決定？

> 查核日期：**2026-09-18**｜**本檔只新增，不改任何既有檔案**
> 標記沿用 `docs/research/social-trend-signals.md`：**V** = 我親自打開一手來源逐字核對｜**U** = 只有二手／抓不到，引用要保守｜**INF** = 我的推論，不是文獻結論
> **全文取得狀態：已取得 PDF 全文並逐頁讀完 11 頁**（`E:\Downloads\1-s2.0-S0957417424008844-main.pdf`，使用者提供）。因此本檔的表格數字全部標 **V**，不是摘要推測。
> 對照文件：`docs/research/social-trend-signals.md`（§2 學術線、§3 合法性、§6 KOL 假設、§5 證偽計畫）、`docs/research/forecast-evaluation.md`（§3.2 Visuelle 判決、§79–82 WAPE 表）。

---

## 一句話結論

**這篇論文沒有做預測。** 標題寫 forecasting，內容是 Instagram 手袋影像的 **extraction + dashboard** 管線；論文自己在 §6 把 trend prediction 列為 future work。所以它**不可能**與 HERMES 的 −4.3% MASE 衝突——它沒有量過任何一個預測數字，也沒有任何 forecasting baseline。**判決：(a)，不改變我們的決定。**

---

## 1. 出處與可取得性

### 1.1 書目（全部 V）

| 欄位 | 值 | 來源 |
|---|---|---|
| 標題 | Social4Fashion: An intelligent expert system for forecasting fashion trends from social media contents | PDF 首頁 / Crossref |
| 作者 | Emanuele Balloni ᵃ, Rocco Pietrini ᵃ, Matteo Fabiani ᵃ, Emanuele Frontoni ᵇ, Adriano Mancini ᵃ, Marina Paolanti ᵇ | PDF 首頁 |
| 單位 | ᵃ **Università Politecnica delle Marche, VRAI – Vision Robotics and Artificial Intelligence Lab, DII**, 60131 Ancona；ᵇ **University of Macerata, Dept. of Political Sciences, Communication and International Relations**, 62100 Macerata | PDF 首頁 |
| 期刊 | *Expert Systems With Applications*, **vol. 252**, article **124018**, 11 頁 | PDF 頁眉 |
| 日期 | Received 2023-04-07；Revised 2023-11-13；**Accepted 2024-04-16**；Available online 2024-04-21；印刷期 2024-10 | PDF 首頁 / Crossref |
| DOI / PII | `10.1016/j.eswa.2024.124018` / `S0957417424008844` | V |
| 其他 ID | Scopus `2-s2.0-85192446652`；WoS `WOS:001239731800001`；DBLP `journals/eswa/BalloniPFFMP24` | UNIMC OAI-PMH 記錄 |
| 引用數 | **Crossref 9｜OpenAlex 10｜Semantic Scholar 9（influential 1）**，2026-09-18 查 | V |

### 1.2 「Green OA」是假陽性——這點值得記下來

Unpaywall 與 OpenAlex 都把這篇標成 `oa_status: green`、`any_repository_has_fulltext: true`，但兩邊列出的唯一 URL 都是 ScienceDirect（對自動抓取回 403 / CAPTCHA）。追到底層來源後：

- Unpaywall 的 `repository_institution` 是 **Marche Polytechnic University**；OpenAIRE 解析出的實際 repository 記錄是 **UNIMC 的 U-PAD，handle `11393/340070`**，而 bitstream 連結是 `u-pad.unimc.it/request-item?...`（**request-a-copy**）。
- 我用 U-PAD 的 **OAI-PMH** 端點（`verb=GetRecord&identifier=oai:u-pad.unimc.it:11393/340070`）取回完整 Dublin Core 記錄，`dc:rights` 逐字是：
  **`info:eu-repo/semantics/restrictedAccess`**，另一條 `license uri:iris.PRI00`。（**V**）

→ **機構典藏的檔案是限制存取的，不是開放的。** 「green OA」來自典藏系統有一筆記錄，不是來自有一份可讀的檔案。**沒有任何合法的免費全文可讀**；本次全文來自使用者自行提供的 PDF。這件事對我們的意義是流程性的：**以後不要相信 Unpaywall 的 `oa_status` 欄位，要看 `oa_locations[].version` 與 repository 的 `dc:rights`。**

已試過且失敗的路線（全部 403 / Cloudflare challenge / CAPTCHA）：ScienceDirect（curl、WebFetch、Playwright headless、Playwright headful 皆 403，headful 直接跳 CAPTCHA——**我沒有嘗試通過 CAPTCHA**）、`iris.univpm.it`、`u-pad.unimc.it` 網頁介面、`vrai.dii.univpm.it`、ResearchGate、Wiley、CORE（429）、BASE。**成功的只有 OAI-PMH 與 Crossref / OpenAlex / OpenAIRE / Semantic Scholar 這類 API。** arXiv 全庫搜 `Social4Fashion` **零結果**，無 preprint。

### 1.3 引用它的 9 篇：有沒有人接著做預測？**沒有。**（V，Semantic Scholar `citations`，逐篇讀摘要）

| 引用文獻 | 年 / venue | 有沒有把 S4F 的預測步驟做出來？ |
|---|---|---|
| **Made-In**（Balloni, Pietrini, Sasso, Frontoni, Paolanti） | 2025, *CVIU*, 10.1016/j.cviu.2025.104454 | **沒有。這是同一團隊的直系後繼作，仍然沒有預測。** 摘要逐字：三個模組是 3D configurator、collection grid、以及「a social media trend detector based on deep learning pipelines for **image classification, object detection and color clustering**」——和 S4F 同一套管線；驗證方式是「A **user study** with domain experts confirms the platform's usability and relevance for trend forecasting」。**還是 usability study，不是預測評估。** |
| Rudna, Rudniy & Park | 2026, *Journal of Forecasting*, 10.1002/for.70204 | 有做預測，但**不是**用 S4F 的管線（用 Amazon Sales Rank × Twitter 貼文數 × Google Trends）。**這正是 `social-trend-signals.md` §6 已經逐條駁掉的那一篇**（「mean RMSE 3.47 versus **91,034 for the univariate baseline**」）。它只是把 S4F 當相關工作引用。 |
| VogFashion | 2026, *SoftwareX* | 生成式設計系統，無預測 |
| DesignBridge | 2026, IUI, arXiv:2601.14639 | 共創介面，無預測 |
| From Pixels to Posts | 2025, arXiv:2511.19149 | 時尚 captioning / hashtag 生成（YOLO + CLIP-FAISS + LLM），無預測 |
| Differential Evolution attribute weighting | 2026, *AI* (MDPI) | 與時尚無關 |
| Circular knit fabric cues | 2026, *J. Eng. Fibers and Fabrics* | 感知研究，無預測 |
| Color trend + blockchain | 2025, ICHORA | **qualitative case study**（Burberry / LVMH），無數字 |
| Vintage revival | 2024, *Interdisciplinary Cultural and Humanities Review* | 人文論述，無數字 |

**兩個結論：**
1. **沒有任何一篇複現、也沒有任何一篇質疑** S4F 的 0.97 accuracy / 0.777 mAP。這兩個數字在文獻上是**未被獨立檢驗**的。
2. **兩年、9 次引用，沒有人把那個「預測」步驟做出來——連原團隊自己的後繼作都沒有。** 這件事本身是證據，見 §4.4。

---

## 2. 它實際上做了什麼

### 2.1 管線（V，§3.1–§3.5、Fig. 1）

```
Instagram 爬取（Instaloader，每天跑 2 次，依領域專家給的手袋型號 hashtag）
  → 圖存 AWS S3；文字（caption / hashtags / 使用者資訊 / geolocation）存 MongoDB
  → VGG-16 二元分類：fashion / not fashion（過濾掉非時尚圖）
  → YOLOv5s 偵測 + 分類：手袋 bounding box + 10 類手袋型別
  → 裁切 bbox → K-means（Elkan 變體）分 3 群取主色
       （論文明講：第 1 群是背景，第 2、3 群才是包的主色）
  → 寫回 JSON → backend API → **PowerBI dashboard**
```

**輸出端就是 dashboard，沒有模型輸出未來值。** Fig. 8 的儀表板元件逐條是：手袋類型 filter、**時間 filter**、hashtag 地理分佈地圖、主色網格、相關 hashtag 詞雲、3 個 KPI（分析貼文數／按讚數／留言數）。§5 的標題逐字是「**Social4Fashion data visualization**」。

### 2.2 資料（V）

| | 內容 |
|---|---|
| **Instagram 影像資料集**（本文新建） | **700,000 張**，人工標註並**平衡為 350,000 fashion / 350,000 non-fashion**；蒐集期間 **2022-01 至 2023-01**；**逐月分層**切 train/val/test（論文說明理由是要涵蓋季節與天候造成的變化，避免 temporal bias）；切分比例 **70 / 10 / 20** |
| **MADAME**（偵測用，引自同團隊 Della Sciucca et al. 2022, StyleTrendGAN, ICIAP-W） | **55,087 張**手袋影像、**10 類**（Backpack / Belt / Bucket / Clutch / Mini / Cross-body / Shoulder / Tote / Pochette / Bowling）；偵測切分 **80:20**、依 instance 數分層 |
| 預測目標 | **沒有預測目標**（見 §3） |
| Horizon | **沒有 horizon** |
| 取得性 | **Data availability 逐字：「Data will be made available on request.」** 無授權宣告。我在 **Zenodo / HuggingFace datasets / GitHub 全部搜過，`Social4Fashion`、`MADAME`、`StyleTrendGAN` 皆零命中**（V）。→ **兩份資料集都拿不到，也沒有授權。** |

### 2.3 蒐集方式的合法性：**今天不合法，而且當時大概也不合法**

論文 §3.1 逐字：「The crawler uses the **Instaloader** library to connect and download posts from Instagram.」（**V**，腳註直接連 `github.com/instaloader/instaloader`）

- Instaloader 是**非官方 scraper**，不是 Graph API。
- `social-trend-signals.md` §3.1 已經核過（**V**）：Instagram Graph API 需要 Business/Creator 帳號＋強制 App Review，且有「30 unique hashtags / 7 days」的硬限制，Meta Platform Terms §3.d 要求不需要時即刪除。Meta 的 Terms of Use 另外明文禁止未經事前書面許可的自動化蒐集。
- **INF（但信心高）**：以 Instaloader 大規模下載 70 萬張貼文影像，不符合 Meta 的條款；而且就算條款問題不存在，**這 70 萬張圖的著作權屬於原發文者**，所以「on request 提供」本身也是有問題的再散布。
- → **對我們的意義**：這篇論文**沒有**推翻 `social-trend-signals.md` §3 的結論（原始社群影像我們合法拿不到），它是**又一個實例**——一個有產業金主與機構資格的團隊，取得資料的方式我們**照抄不了**。

### 2.4 金主與利益揭露（V，中性陳述）

- Acknowledgments 逐字感謝 **Tod's Spa**（義大利精品皮件品牌）與其 T-Winning team，並說「Tod's contributions in terms of providing **essential data, expertise and funding** were fundamental to the success of our endeavors.」
- → 這解釋了**為什麼整篇只做手袋**：範圍是金主的品類，不是研究上的選擇。論文 §6 自己說未來要擴到 shoes / t-shirts / pants。
- **對 coordinator 讀法的更正**：關於「Paolanti 有 patent pending」——**這個宣稱不安全**。Declaration of competing interest 印出來是一段**沒填完的樣板**，逐字是：「Marina Paolanti reports was provided by University of Macerata. Marina Paolanti reports a relationship with University of Macerata that includes:. Marina Paolanti **has patent pending to No patent. Nothing to declare.**」——`has patent pending to **No patent**` 是表單欄位留空後被機器串起來的產物，**不能讀成「有一項專利審查中」**。建議只寫「利益揭露欄位在出版時是未填完的樣板，無法據以判斷」。

---

## 3. 評估與基線（本檔重點）

### 3.1 論文報了什麼

**Table 4｜fashion / non-fashion 二元分類（test set, 50 epochs, 95% CI）**（V）

| CNN | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| ResNet 50 | 0.91 (0.87–0.94) | 0.92 (0.85–0.95) | 0.92 (0.86–0.93) | 0.92 (0.85–0.94) |
| **VGG16** | **0.97 (0.95–1.00)** | **0.94 (0.92–0.96)** | **0.94 (0.92–0.97)** | **0.94 (0.92–0.96)** |
| DenseNet 121 | 0.89 (0.83–0.94) | 0.88 (0.81–0.93) | 0.91 (0.85–0.94) | 0.89 (0.83–0.93) |
| EfficientNet | 0.93 (0.85–0.96) | 0.93 (0.85–0.95) | 0.95 (0.89–1.00) | 0.94 (0.87–0.97) |

**Table 5｜手袋偵測（test set, 95% CI）**（V，逐類節錄 + 合計）

| Class | Precision | Recall | mAP@.5 |
|---|---|---|---|
| Backpack | 0.702 (0.651–0.733) | 0.714 (0.647–0.740) | 0.714 (0.670–0.751) |
| Clutch bags | 0.912 (0.877–0.945) | 0.813 (0.787–0.871) | 0.827 (0.78–0.867) |
| Bowling bag | 0.946 (0.913–0.972) | 0.848 (0.812–0.885) | 0.855 (0.824–0.904) |
| **Total** | **0.832 (0.807–0.873)** | **0.754 (0.711–0.789)** | **0.777 (0.732–0.825)** |

CI 方法（V，§4.2）：**200 輪 bootstrap，固定模型、只對 test set 做 replacement 重抽**，取 2.5/97.5 百分位；論文自己說明這樣做是為了避免重訓（引 Efron & Tibshirani 1994、Steinbach et al. 2022）。

### 3.2 基線狀況：**分類有 3 個，偵測 0 個，主色 0 個，預測 0 個**

| 子任務 | 有沒有基線 | 是什麼 |
|---|---|---|
| fashion / non-fashion 分類 | **有，3 個** | ResNet50 / DenseNet121 / EfficientNet（同任務的其他 backbone） |
| 手袋偵測 + 分類 | **沒有** | 只有 YOLOv5s 自己的逐類數字，**沒有跟任何其他 detector 比** |
| 主色 K-means | **沒有** | §4.4 逐字「**Qualitative** results for dominant color detection are shown in Fig. 7」——**純定性，沒有任何量化指標** |
| **趨勢預測** | **不適用——因為沒有預測** | 沒有 persistence、沒有 seasonal naive、沒有 ARIMA、沒有 MASE／WAPE／sMAPE |

**50 篇參考文獻裡沒有任何一篇時間序列預測方法論**（V，我逐條掃過 Crossref 的 reference list）：沒有 Hyndman、沒有 ARIMA/ETS/TBATS/Prophet、沒有 N-BEATS/DeepAR、沒有 M-competition、沒有 MASE。方法論引用全部是 CV 與分群：VGG（Simonyan & Zisserman 2014）、YOLOv5（Jocher 2020）、COCO（Lin 2014）、PASCAL VOC（Everingham 2010）、偵測指標工具箱（Padilla 2021）、K-means（Lloyd 1982 / Jain & Dubes 1988 / Elkan 2003）、bootstrap（Efron 1994）、Grad-CAM（Selvaraju 2017）。**唯一沾到預測方法的是 Yu, Hui, Choi 2012（GRA–ELM 色彩趨勢預測），而那是在 related work 裡被引述，不是被當基線比較。**

### 3.3 論文自己承認沒有做預測（V，§6 逐字）

> 「We **foresee a future direction** for the Social4Fashion framework that embraces a more inclusive approach to **trend prediction**.」

§2 結尾也寫「This represent a novel completely modular pipeline that **paves the road for future development** in this field with analysis **on current data**」。

→ **標題與內容的落差是這篇論文最重要的事實。** 「forecasting」在標題與 abstract 裡出現，但系統交付的是「讓專家在 dashboard 上自己看」。

### 3.4 兩處論文內部數字不一致（V，我核出來的）

1. **偵測合計數字，正文與 Table 5 不符。** §4.3 正文逐字：「a total average Precision of **0.842**, Recall of **0.741** and mAP@.5 of **0.787**」；Table 5 的 Total 列是 **0.832 / 0.754 / 0.777**。三個數字**全部對不上**。Abstract 用的是 0.77（與 Table 5 一致）。
2. **MADAME 的 instance 總數對不上。** §3.3 正文說「55.087 handbag models … a total of **91 380** instances」；Table 1 的 images 欄加總**剛好 55,087**（✓），但 instances 欄加總是 **95,190**（✗）。

→ 這兩處不影響本檔的結論（結論是「沒有預測」，不依賴這些數字），但**如果評審引用 0.777 或 0.787，要知道論文自己有兩個版本**。

### 3.5 實際被分析的資料量遠小於 700k（V，Fig. 8）

儀表板截圖上的 KPI：Backpack 類 **1,019 posts analyzed**（361K likes、14K comments）、Shoulder bag 類 **967 posts**（177K likes、12K comments），期間 **2021-12-17 至 2023-01-25**。

→ **70 萬張是分類器的訓練集，不是趨勢分析的樣本。** 真正進到「趨勢」視圖的是**每類約 1,000 則貼文、跨 13 個月**。**INF**：若要在這上面做月頻序列，每類每月約 75 則貼文——這個樣本量連描述統計都很脆弱，更不用說預測。這是論文沒有做預測的一個**結構性**理由，不只是時間不夠。

### 3.6 「這份評估撐不撐得住一個懷疑論的審稿人？」

**分兩段回答，而且答案不同：**

- **作為 CV 論文：撐得住，而且做得比多數同類論文謹慎。** 有 3 個 backbone 對照、有 200 輪 bootstrap CI、有 Grad-CAM 可解釋性檢查、明講類別不平衡（最大比例約 3:1）並因此**刻意不用 accuracy 而用 PASCAL VOC mAP** 評偵測、逐類報告而非只報平均。這些都是好習慣。（唯一該扣分的是偵測沒有任何 baseline，以及主色完全沒有量化。）
- **作為 forecasting 論文：完全撐不住——因為它根本不是。** 沒有預測目標、沒有 horizon、沒有 test-time 的時間切分（月分層切分是為了讓訓練集涵蓋四季，**不是** temporal holdout）、沒有任何預測基線、沒有任何預測指標。**它不是「用了弱基線」，而是「沒有基線，因為沒有被評估的預測」。**

> **這正好是使用者問題的反面。** 使用者擔心的是「比較對象是 univariate baseline 而不是 persistence / seasonal-naive，所以宣稱的 gain 是假象」——那是 **Rudna et al. 2026** 的病（`social-trend-signals.md` §6 已處理）。**Social4Fashion 沒有這個病，因為它沒有宣稱任何 gain。** 它的問題是**標題的語意膨脹**，不是評估設計的缺陷。

---

## 4. 與我們既有結論的關係

### 4.1 它沒有牴觸 HERMES，因為兩者量的不是同一件事

| | **HERMES**（Heuritech, arXiv:2202.03224） | **Social4Fashion** |
|---|---|---|
| 被預測的量 | **10,000 條週頻時尚趨勢序列**的未來值 | **無** |
| 訊號角色 | influencer weak signal 當**外生特徵** | Instagram 圖是**唯一的觀測對象**，不是特徵 |
| 評估 | **MASE vs TBATS**，跨 10,000 / 1,000 / 100 條分別報 | Accuracy / mAP，對其他 CNN backbone |
| 結果 | −4.3% / −2.6% / **−1.1%** MASE | 0.97 acc / 0.777 mAP |
| 對「11 條軸」的意涵 | **致命**：效果隨序列數單調崩塌，機制上需要跨數千條序列 pooling | **無意涵**：它沒說過任何關於序列數的事 |

→ **Social4Fashion 不能被引用來支持或反對「社群訊號值多少」，因為它從未測量過那件事。** `social-trend-signals.md` §0(1)④ 與 §2.1(d) 的論證**不受影響**。

### 4.2 逐項對照使用者指定的四組差異

| 面向 | Social4Fashion | 我們的問題 | 一樣還是不一樣 |
|---|---|---|---|
| **attribute-level popularity vs sales** | 兩者都不是。它做的是 **attribute-level 的「當期計數」**（某月某地某類手袋出現幾次、主色分佈），**沒有把計數轉成序列再外推** | 我們要的是 11 條**感性印象軸**上的流行度偏移 | **不一樣，而且它更弱**：它連「流行度時間序列」這個物件都沒有建構出來 |
| **Instagram images vs weak signals** | **Instagram 原圖**（實穿照），靠 Instaloader 爬 | 我們合法拿不到 Instagram 原圖（§3.1 V）；能拿的是 HERMES 那種**沒有圖**的 weak signal 序列 | **不一樣，而且這是死結**：它的整個管線建立在「我有 70 萬張 Instagram 圖」之上 |
| **他們的 held-out set vs 競爭性 benchmark** | **自建、未公開、request-only 的 held-out set**；MADAME 也是自家資料集；**沒有在任何公開 benchmark 上比過** | — | **不一樣**：Visuelle / VITON / DeepFashion 這類公開 benchmark 一個都沒碰。**沒有可比性，也沒有外部檢驗** |
| **粒度** | **1 個品類（手袋）× 10 個子類 × RGB 主色** | **11 條正規化感性軸**（跨品類） | **不一樣**：它的「屬性」是 taxonomy 上的品類節點與像素統計，不是我們的感性軸。`social-trend-signals.md` §4.2① 的「粒度錯層」反對理由**原封不動成立** |

### 4.3 §5 的前提要更正：**Visuelle / GTM-Transformer 不是這個團隊做的**

brief 裡寫「This group also produced the Visuelle / Visuelle 2.0 datasets and GTM-Transformer」——**這是錯的**（V，Crossref 作者單位）：

- **GTM-Transformer / Visuelle**（`10.1002/for.3104`）：Geri Skenderi（**University of Verona**, CS）、Christian Joppi（**Humatics Srl**, Verona）、Matteo Denitto（**Humatics Srl**）、Marco Cristani（**University of Verona**）。官方頁是 `humaticslab.github.io/forecasting/visuelle`（`forecast-evaluation.md` §17 已核）。
- **Social4Fashion**：UNIVPM（Ancona）VRAI lab + University of Macerata。

**兩個團隊沒有共同作者，也沒有共同機構。** Social4Fashion 引用了 Mall et al.（GeoStyle）、Al-Halah（Fashion Forward）、Ma et al.（KERN）、Ding et al.（REAR），但**完全沒有引用 Visuelle 或 GTM-Transformer**。

→ 所以「Social4Fashion 與 Visuelle 的關係」這個問題的答案是：**沒有關係。** `forecast-evaluation.md` 對 Visuelle 的判決（SOTA WAPE 54–86%、Naive 118%、需填表、無授權）**完全不受本檔影響**，也不需要修改。

### 4.4 反過來說，這篇論文給了我們一個**正面**的論證

這是本次查核最有價值的發現，值得寫進簡報：

> 一個團隊，有**精品品牌金主**（Tod's）出錢出資料出領域專家、有**一整年**的蒐集期、有 **70 萬張人工標註影像**、有兩所大學的工程資源、發在 **JCR Q1 的 Expert Systems with Applications**——最後交付的是**一個 PowerBI 儀表板**，並把 trend prediction 寫成 future work。**兩年後、9 次引用，包括原團隊自己的後繼作（Made-In, CVIU 2025），沒有人把那一步做出來。**

**INF（但這是本檔最想主張的推論）**：這是一個**難度的自然實驗**。困難的部分不是 extraction（偵測 mAP 0.777、分類 0.97，這些他們做到了），而是 **forecast**。如果 forecast 在這個資料上是可做的，一個拿了品牌金主的團隊沒有理由把它留給 future work。

這一句話可以和既有的 HERMES 論證互補：
- **HERMES 講的是「就算做了，值多少」** → 4.3% MASE，而且要 10,000 條序列。
- **Social4Fashion 講的是「有錢有資料有資格的人，做到哪裡就停了」** → 停在 dashboard。

兩者合起來，`social-trend-signals.md` §0(3) 那段「我們沒做趨勢預測，這是工程決定不是缺口」的台詞就有**兩個**獨立支撐，而不是只靠 HERMES 一個。

### 4.5 結構上與我們**已經在做**的東西相同的那一塊

Social4Fashion 的骨架是：**detect → classify attribute → 依時間與地點聚合 → 面板**。我們 repo 裡對應的東西**已經存在**：

| Social4Fashion | 我們已有的 |
|---|---|
| YOLOv5 偵測 + 10 類手袋分類 | `engine02/attrindex.py`、`engine02/attribute_fill.py`、`engine02/taxonomy.py` |
| 「某類 × 某主色 × 某期間」的計數聚合 | **`engine02/panels.py::category_color_gap`**（品類 × 顏色 cell 的缺口）、`panels.py::element_gap`、`panels.py::need_supply` |
| PowerBI 的 filter / KPI / 詞雲 | `engine02/panels.py::build_view`、`Provenance`、`RoundDiff` |
| 200 輪 bootstrap CI | `engine02/eval/metrics.py::bootstrap_ci`、`paired_permutation_test` |

→ **這正是為什麼判決是 (a) 而不是 (b)。** 它唯一在結構上可借鑑的東西，**我們已經有了**，而且我們的版本跑在**合法且與商品庫同域**的資料上（Polyvore / 我們自己的商品庫），它的版本跑在我們**拿不到**的 Instagram 上。可借鑑的不是一個新元件，而是**一個確認**：我們選的那條「描述當前結構、不外推」的路，和一個拿了產業金主的團隊在同一個問題上最後停下來的位置**是同一個位置**。

---

## 5. 結論：**(a)——不改變我們的決定**

三選一，我主張 **(a) 機制仍然無法轉移到 11 條軸，而且沒有合法資料來源**。理由按強度排序：

1. **它沒有做預測，所以不可能構成反證。** 論文 §6 自己把 trend prediction 列為 future work；50 篇參考文獻裡沒有任何時間序列方法論；沒有 horizon、沒有預測目標、沒有預測基線、沒有 MASE/WAPE。**一篇沒有量過預測的論文，不能推翻一篇量過預測的論文（HERMES）。**
2. **粒度錯層原封不動。** 它的「屬性」是 1 個品類下的 10 個 taxonomy 子類加 RGB 主色；我們的是 11 條跨品類感性軸。`social-trend-signals.md` §4.2① 的反對理由不受影響。
3. **資料在法律上對我們是封閉的，兩層都封。** (i) 蒐集端：Instaloader 爬取不符合 Meta 條款（§2.3）；(ii) 取得端：論文的兩份資料集都是 **request-only、無授權宣告**，Zenodo / HF / GitHub 零鏡像。連機構典藏的論文本身都是 `restrictedAccess`（§1.2）。
4. **可重用的元件我們已經有了**（§4.5），所以不構成 (b)。
5. **沒有可以設計的實驗**，所以不構成 (c)：要複製它就要 70 萬張 Instagram 圖，那正是我們**合法拿不到**的東西；而它的分析樣本量（每類約 1,000 則貼文 / 13 個月，§3.5）即使拿得到也撐不起一個序列。**唯一能用我們合法資料做的預測端實驗，`social-trend-signals.md` §5.1（Polyvore 月頻要素序列 vs seasonal naive，報 MASE）已經寫好了，本檔不改動它，也不新增。**

### 5.1 建議怎麼在簡報上用這篇（純寫作，約 10 分鐘）

把它放進 §7 的 **R1** 那張投影片，當 HERMES 旁邊的第二個證據，**但要用對方式**：

- ✅ **可以說**：「2024 年 ESWA 上有一篇叫 *Social4Fashion: ...for **forecasting** fashion trends*，Tod's 出資、70 萬張人工標註的 Instagram 圖、一整年蒐集。它交付的是 PowerBI 儀表板，論文第 6 節把 trend prediction 寫成 future work。兩年、9 次引用，包括原團隊自己的後繼作，沒有人把那一步做出來。」
- ❌ **不要說**：「這篇論文證明社群趨勢預測沒用」——它沒有測試過，這樣講會被問倒。
- ❌ **不要**引用 0.97 / 0.777 當作對我們有利或不利的證據——那是手袋偵測的數字，與我們的問題無關。
- ⚠️ 如果評審引用**這一篇**來質疑我們，正確回答是：「那篇沒有做預測，它自己在結論說預測是 future work。真正量過這件事的是 Heuritech 自己的 HERMES：**4.3% MASE，需要 10,000 條序列；100 條時掉到 1.1%。我們有 11 條。**」

---

## 6. 我無法核實的部分（逐條）

1. **那 70 萬張 Instagram 資料集與 MADAME 的實際授權條款。** 論文只寫「Data will be made available on request」，**沒有任何授權宣告**。我在 Zenodo API、HuggingFace datasets API、GitHub search API 用 `Social4Fashion` / `MADAME` / `StyleTrendGAN` 搜過，**全部零命中**；`vrai.dii.univpm.it` 回 403 所以**實驗室官網上有沒有下載連結我無法確認**。→ 我只能說「公開索引上找不到」，不能說「一定不存在」。
2. **MADAME 的原始論文內容**（Della Sciucca et al. 2022, *StyleTrendGAN*, ICIAP 2022 Workshops, LNCS, `10.1007/978-3-031-13324-4_17`）**我沒有讀到全文**。MADAME 的蒐集方式、授權、是否同樣是 Instagram 爬取——**全部未核**。我對 MADAME 的描述**只來自 Social4Fashion 的 §3.3 轉述**。
3. **MADAME instance 總數到底是 91,380 還是 95,190**（§3.4）。論文正文與 Table 1 不一致，我無法判定哪個是對的。
4. **偵測合計指標到底是 0.842/0.741/0.787 還是 0.832/0.754/0.777**（§3.4）。正文與 Table 5 不一致。Abstract 與 Table 5 一致（0.77），所以**我在本檔一律採用 Table 5 的版本**，但這是我的選擇，不是論文的裁決。
5. **Made-In (CVIU 2025) 的全文我沒讀到**（ScienceDirect 403）。我對它「仍然沒有做預測」的判斷**只根據 OpenAlex 取回的摘要全文**（該摘要明確寫 user study 而非預測評估）。→ 標 **U**：不排除正文裡有我沒看到的量化預測評估，但摘要的 highlights 五條全是系統與 usability，沒有一條提到預測準確度。
6. **VogFashion (SoftwareX 2026) 的摘要在 OpenAlex 與 Semantic Scholar 都是空的**，我只從標題與 venue 判斷它是生成式設計系統。標 **U**。
7. **Instagram 條款的法律判斷**（§2.3）是 **INF**，不是法律意見。我核到的一手事實只有：論文用 Instaloader（V）、`social-trend-signals.md` §3.1 記錄的 Graph API 資格與 30-hashtag/7-day 限制（V）。「所以違反條款」是我的推論。
8. **競爭利益聲明的真實內容。** 出版出來的那段是未填完的樣板（§2.4），我無法從中判斷 Paolanti 是否真有專利審查中。**不要在任何地方寫「有 patent pending」。**
9. **這篇論文在同儕審查中是否被要求處理「標題說 forecasting 但沒有 forecast」這件事。** Received 2023-04 → Revised 2023-11 → Accepted 2024-04，審查歷時一年，但**審稿意見不公開**，我無法得知。
10. **儀表板實際的分析樣本量是否就是 Fig. 8 的 ~1,000/類。** 那是截圖上的 KPI，**可能只是某個 filter 狀態下的計數**，不一定是系統全量。我在 §3.5 的推論標 INF。

---

## 附錄：本檔用到的取得路線（給後續查核參考）

**能用的（無 Cloudflare）：**
- `api.crossref.org/works/<doi>` — 書目 + **完整 reference list**（這次的關鍵證據）
- `api.openalex.org/works/doi:<doi>` — `locations[]`、`abstract_inverted_index`
- `api.semanticscholar.org/graph/v1/paper/DOI:<doi>/citations?fields=title,abstract,...` — 引用它的論文＋摘要
- `api.unpaywall.org/v2/<doi>?email=` — `oa_locations[].repository_institution`（**用它找出典藏機構，不要信 `oa_status`**）
- `api.openaire.eu/search/publications?doi=<doi>&format=json` — **解析出實際的 repository handle**
- **`<repo>/oai/request?verb=GetRecord&identifier=oai:<host>:<handle>&metadataPrefix=oai_dc`** — **本次最有用的一招**：IRIS/DSpace 的 OAI-PMH 端點**不在 Cloudflare 後面**，網頁介面 403 時它照樣回完整 Dublin Core，包含 `dc:description`（摘要全文）與 **`dc:rights`（真正的存取狀態）**

**不能用的：** ScienceDirect（403 → headful 跳 CAPTCHA，**不嘗試繞過**）、`iris.univpm.it` 網頁、`u-pad.unimc.it` 網頁、`vrai.dii.univpm.it`、ResearchGate、Wiley、CORE（429）、BASE。Playwright headless 與 headful persistent context 對這些站**都沒有幫助**。
