# 社群／KOL 訊號能不能餵進 ENGINE 02：查核與修正

> 調查日期：**2026-09-18**｜分支 `engine02-research`｜**本檔只新增，不改任何既有檔案**
> 標記：**V** = 我親自打開一手來源核對過｜**U** = 只有二手摘要／頁面抓不到，引用要保守｜**INF** = 我的推論，不是文獻結論
> 本輪工具限制（必須誠實寫進簡報）：本 session 的 **WebSearch 配額在本任務開始前就已用盡（200/200）**。因此：
> - **學術端（§2、§6）**：改用 **OpenAlex API（curl）** 逐篇取回 DOI／venue／年份／作者／**摘要原文**核對 → 標 V 的都是我逐字讀過摘要。實驗表格內的 baseline 細節無法核，一律標「僅摘要」。
> - **平台條款與資料集（§3）**：WebFetch 官方文件，多個網域（X 開發者條款 HTTP 402、Reddit 全站 403、Pinterest／HuggingFace JS 渲染）抓不到 → 逐條標「**無法核實**」，不猜。
> - **產業端（§1）**：公開紀錄最薄的一段，見該節開頭的說明。
> **行號注意**：本文件引用的行號是 2026-09-18 我讀碼時的狀態。撰寫期間 coordinator／其他 agent 正在並行修改 `engine02/config.py`、`engine02/contracts.py`、`engine02/explain.py`、`engine02/pipeline.py` 與 `tests/test_engine02.py`（我已確認那些改動與本主題無關：在 `git diff` 中 grep `trend_prior` 與 `element_trends` 皆為空）。**整合前請用函式名而不是行號定位**：`FeedbackState.design_weight_delta`、`_terms` 裡的 `per_unit["feedback_adjust"]`、`panels._need_labels`。
> 對照文件：`docs/engine02-design.md` §3.15（趨勢關鍵字 28 組負結果）／§3.16（概念圖對照組設計）、`docs/research/engine02-completeness.md` §2.1（為什麼不碰 Pinterest）、`docs/research/industry-fashion-brands.md`（聚陽客戶結構）。

---

## 總表：訊號來源 → 誰在用 → 粒度 → 我們能不能合法取得 → 值不值得做

「合法取得」＝ **2026-09-18 當下、無付費合約、無機構資格**的情況。細節：平台條款 §3.1、資料集 §3.2、廠商 §1。

| 訊號來源 | 誰在用（出處） | 粒度 | 我們能不能合法取得 | 值不值得做 |
|---|---|---|---|---|
| **Instagram 實穿照（視覺屬性偵測）** | **Heuritech**（官網 V；HERMES arXiv:2202.03224 V）、WGSN（自揭「100,000+ social media posts monthly … proprietary Instagram mapping」V）、學界 KERN/FIT（ICMR 2020 V） | Heuritech 宣稱單張圖 **2,000+ 屬性**；KERN 是 fine-grained element | **不行**。Graph API 要 Business/Creator＋強制 App Review，且「**30 unique hashtags / 7 days**」、Meta Platform Terms §3.d 要求不需要時即刪除（V） | ❌ **資格問題，不是技術問題** |
| **Influencer weak signal 當預測特徵** | **Heuritech 自己的 HERMES**（V，raw README） | 週頻趨勢序列 | 序列可下載（**repo 無授權宣告**），**但沒有圖** | ⚠️ **答案已知：−4.3% MASE @10,000 條，−1.1% @100 條** → 對我們的 11 條軸**機制性不可行** |
| **Pinterest Trends 關鍵字** | 我們自己（`trends.py::from_live_fetch`） | 關鍵字 | **只能即時、不能存**（開發者規範逐字禁止，V） | ⚠️ 只能當展示標籤，**已做** |
| **X/Twitter 貼文** | Rudna et al. 2026（V，但數字不可信，§6） | 關鍵字 | **實質不行**（用量計價、無學術層、條款頁 402 無法核實） | ❌ |
| **TikTok 貼文** | Target「mob wife」豹紋案（U，二手、無數字） | 主題／單一屬性 | **資格不符**（Research API 限學術機構） | ❌ |
| **電商上架／價格／庫存** | **EDITED**（V：「90,000 brands, 5b+ SKUs, tracked every day」） | SKU／價格／品項結構 | 自己爬＝另一個專案 | ⚠️ **注意：EDITED 的漂亮數字量的是定價最佳化，不是預測準確度** |
| **媒體／KOL 聲量折算金額** | **Launchmetrics MIV**（V） | 品牌／活動，**回顧型** | 付費 | ❌ **類別錯誤**：MIV 量媒體價值，不是需求 |
| **Google Trends（搜尋量）** | **GTM-Transformer / VISUELLE**（V）、Choi & Varian（V） | 關鍵字（商品 tag） | ✅（VISUELLE 2.0 已附現成序列；官方 API alpha 狀態無法核實） | 🟡 **唯一在真實銷售上量過淨貢獻的外生訊號：1.5% WAPE** |
| **帶日期的真實銷售＋商品圖** | **VISUELLE 2.0**（Nuna Lie，V） | 商品層級日銷（門市層級） | ✅ 免費但**要填表**、**官方頁無授權宣告** → 不可散布 | 🟡 資料最好，但不能當可重現主線 |
| **帶日期的社群策展穿搭＋商品圖** | **我們自己已經有**（`Marqo/polyvore`）；上游 `xthan/polyvore-dataset` 有 `date`/`likes`/`views`/`set_id`（V） | 商品層級，可投影到我們的 **11 條軸** | ✅ **Apache-2.0、直接抓、圖已在 repo、與商品庫同域** | ✅ **最值得**：唯一能同時做預測端與推薦端 falsification 的資料（§5） |
| **顧客回饋文字** | **Fast Retailing/UNIQLO**（官方頁 V：年收 3,900 萬則，每週回饋商品部） | 顧客語意 | 我們沒有這種資料 | 🟡 **對 OEM 最相關的方向，但不是本題** |
| **自己的 POS ＋反應速度（不做預測）** | **Zara**（「within a week」撤款；一週上架 vs 業界六個月，U）、**Shein**（約 3 天、100 件試單，U） | — | 不適用 | ⚠️ **反面論證：最成功的快時尚用「反應」取代「預測」** |
| **我們商品庫自己推導的關鍵字** | 我們自己（`trends.py::curated_lift`） | 關鍵字 | ✅ | ❌ **已量測：進排序 28 組全變差**（§3.15）；只能當標籤 |
| **Flickr CC 授權照片** | StreetStyle／GeoStyle 系做法 | 街拍屬性 | ✅ **唯一可合法儲存影像的平台**（`license` 參數挑 CC；需 attribution） | 🟡 合法但要自建 StreetStyle 級管線 → 非黑客松尺度 |
| **Amazon 評論時間序列** | **Fashion Forward**（ICCV 2017，8 萬件／6 年，V） | 商品／無監督 style cluster | ✅ 直接抓（**授權未載明**；**只有圖片 URL**） | 🟡 是「購買」不是「社群」 |

---

## 0. 三個問題的直接回答

### (1) 要素層級（element-level）的假設活下來了嗎？→ **機制活、原始訊號死、但有一個沒想到的替代訊號救回來了**

- **活（機制）**：趨勢當成 **β_d 的加性偏移**，是唯一塞得進我們加性模型而不破壞「貢獻＝解釋」的做法，而且**不必動 `pipeline.py`**：`engine02/contracts.py::FeedbackState.design_weight_delta`（`dict[element, float]`）已存在，`engine02/pipeline.py::_terms` 已在讀；項內歸因也已有現成慣例（`Term.need_shares_per_unit` 裡的 `"feedback_adjust"` 假 key）。
- **死（原本設想的社群圖訊號）**：四個獨立理由，§4.2 詳述——①**粒度錯層**（我們只有 **11 條正規軸**，且是感性印象軸不是時尚新奇軸）；②**域偏移吃掉訊號**（社群圖是實穿照、商品庫是白底商品照，§3.16 已量到 FashionCLIP 系偏好白底）；③**單位不可辨識**（社群語料 SD ↔ 商品庫 z 分之間沒有資料能定出換算係數）；④**最致命的那個——序列數不夠**（見下）。再加上 §3 的結論：**Instagram／TikTok／X 的原始圖根本合法拿不到**。

- **④ 為什麼「11 條軸」本身就是死刑：Heuritech 自己的論文把這件事量出來了。** Heuritech（本題最該對標的廠商）的 **HERMES**（David, Bellot, Le Corff, arXiv:2202.03224；Bellot 隸屬 Heuritech）公開了 **10,000 條週頻時尚趨勢序列，每條附一個「external weak signal representing behaviours of influencers」**——這就是**本題假設的產業實作版本**。他們自己 README 的 MASE 表（**V**，我逐字讀了 raw README 與 GitHub API）：

  | 序列數 | TBATS baseline | HERMES＋influencer weak signal | 相對改善 |
  |---|---|---|---|
  | **10,000** | 0.745 | **0.7132**（std 0.0032） | **−4.3%** |
  | **1,000** | 0.734 | 0.7151（std 0.0035） | **−2.6%** |
  | **100** | 0.745 | 0.7368（std 0.0043） | **−1.1%**（約 2σ） |

  兩個結論，都對我們致命：
  1. **產業龍頭用 KOL 訊號，在自己的資料上、對 TBATS，只換到 4.3% MASE。** 這是全文獻唯一一個「影響者訊號 × MASE」的數字。
  2. **效果隨序列數單調崩塌**（4.3% → 2.6% → 1.1%）。原因在摘要裡寫得很清楚：他們的做法是「per-time-series parametric models … **and a global recurrent neural network** to include sporadic external signals」——影響者訊號是**稀疏而微弱的**，必須靠**跨數千條序列的全域模型**才學得出怎麼用它。**我們只有 11 條序列。在 11 條序列上沒有東西可以 pool。** 這不只是樣本量問題，是機制上的不可行。
- **救回來（本次最重要的發現）**：我們**已經有**一份帶日期、Apache-2.0、圖片已在 repo 裡的社群策展資料——**Maryland Polyvore**。上游 `xthan/polyvore-dataset` 的 `train/valid/test_no_dup.json` 每個 outfit 帶 **`date`、`set_id`、`likes`、`views`** 欄位，README 明寫「These outfits are crawled around 02/19/2017, so you can estimate the exact upload date of an outfit by looking at the "date" field」與「The name of a fashion item is **SetID_ItemIndex**」（**V**，我親自讀了 README）。而我們的 `item_id` **就是這個格式**（已驗：`100002074_1`，`outfit_ids=[100002074]`，`scripts/prepare_catalog.py::polyvore_set_id` 正是在拆它）。
  → **意思是：只靠一個 Apache-2.0 的 JSON 做 set_id join，我們手上的 Polyvore 商品就全部長出時間軸，一張圖都不用重新下載。** 而且因為打分的圖片與商品庫同域（同一批零售商品圖），**§4.2 的第②個反對理由（域偏移）在這份資料上直接消失**。

### (2) 唯一最好的、合法可得的資料來源

**`xthan/polyvore-dataset` 的 outfit metadata（Apache-2.0）＋我們已有的 Polyvore 商品圖。** 這是唯一同時滿足全部五個條件的來源：**有時間軸／有圖（已在 repo 裡）／授權明確（Apache-2.0）／不用帳號不用合約不用填表／和商品庫同域**。它還附帶 `likes`／`views`，所以能當帶日期的互動 ground truth，是唯一能同時做**預測端**與（弱版）**推薦端** falsification 的資料。

其他兩個更有名的選項都**輸在授權**，所以不能當主線：

- **HERMES 資料集**（`github.com/etidav/HERMES`）：資訊價值最高——10,000 條週頻趨勢序列＋influencer weak signal，`data/f1_main.csv` 54 MB 等六個 CSV **直接 curl 就能下載、不用帳號不用表單**（**V**，GitHub API 實測）。但 **GitHub API 回報 `license: None`，repo 沒有宣告任何授權** → 可以讀、可以分析，**不能再散布、不能進 git**，法律上曖昧。它沒有圖，所以**無法驗證我們的要素機制**，只能驗「KOL 訊號值多少」（而 §0(1) 已經引用它自己的答案：4.3%）。
- **VISUELLE 2.0**（Nuna Lie，5,355 件、2017–2019 六季、HD 商品圖＋**門市層級日銷**＋商品 tag 的 Google Trends＋天氣＋約 66.7 萬顧客匿名購買，**V**）：文獻上唯一有「真實銷售 × 外生訊號」的公開資料，**但要填表索取、官方頁無明確授權** → 不可散布、不可進 git。

### (3) 在評審面前唯一我敢辯的宣稱

> 「趨勢關鍵字進排序我們**量過，28 組設定全部變差**（−0.16～−0.38 NDCG@5，p≈1e-4，§3.15）。所以我們**沒有**把趨勢做成預測器，而是把它降級成**設計要素上的加性偏移**，並且做了三件事：偏移上限硬綁在 **0.25 ＝使用者一格回饋**（所以「使用者一句話永遠壓得過趨勢」是**代數事實**）、卡片把「這條軸有多少來自你的需求、多少來自族群偏移」**分開歸因**、附上語料 provenance。
>
> 我們**不做**要素層級的趨勢預測，理由不是我們做不到，而是**這個產業的龍頭已經把答案公布了**：Heuritech 自己的 HERMES 論文用 **10,000 條**趨勢序列＋influencer 訊號，對 TBATS 只換到 **4.3% MASE**，而且同一份 README 顯示效果在 1,000 條掉到 2.6%、**100 條掉到 1.1%**——因為那個訊號要靠跨數千條序列的全域模型才學得出來。**我們只有 11 條軸。**」

這段話的每個數字都是一手核過的（`github.com/etidav/HERMES` raw README，2026-09-18），而且它把「我們沒做」講成一個**有證據的工程決定**而不是一個缺口。

**不要**宣稱「KOL 領先、我們抓得到」——§6 的證據不支持，而且最強的正面證據（Rudna et al. 2026）一看數字就不可信（§6）。

---

## 1. 產業：是不是業界做法、到底怎麼做

> **工具限制（必讀）**：WebSearch 在本任務開始前即已用盡，且所有替代搜尋引擎（Google／Bing／DuckDuckGo／Ecosia／Mojeek／Marginalia）都回 CAPTCHA。本節是靠**直接 WebFetch 公司官網／arXiv／GitHub API** 完成的。**這代表產業媒體（BoF、Vogue Business，兩者皆付費牆／403）的批判性報導完全沒查到——那是工具失敗，不是「不存在」。** 標記：**V** = 開頁／讀原文核過；**U** = 行銷頁層級（沒有方法、沒有對照組）；**未核** = 本輪查不到。

### 1.1 Heuritech：唯一有真實方法證據的一家，而那個證據對我們是壞消息

**方法（V，公司官網 2026-09-18）**：訊號是**社群影像**——「Instagram: millions of images from tens of thousands of public accounts」，另加小紅書。粒度宣稱「detect more than **2,000** details/attributes in a single image」（6 種服裝類型＋6 種鞋類，拆成 shape／fit／hood type／color／fabric／print／pattern），並把消費者分成 **Trendsetters / Early Adopters / Mainstream** 三個面板——**這正是本題「KOL 領先」假設的產品化版本**。horizon 宣稱「up to 24 months」（依其公司沿革頁是 2024 年才延長的）。官網不同頁的規模數字互相矛盾（一頁「around 120 million posts」、首頁「3M+ daily social media images」）→ 行銷文案的變異，不是稽核過的數字。

**行銷宣稱（U，全部沒有方法與對照組）**：「up to 90% accuracy」；案例數字 Chalhoub「60% sell-through」、Wolverine「100% sell-through in 10 days」、某裙款「+9% in sales」。客戶：Prada、Dior、Adidas、Louis Vuitton、Moncler、New Balance、Chalhoub、Paco Rabanne 等。**「LVMH 在用」是採購事實，不是方法有效的證據。**

**真實證據（V，逐字核過 arXiv 摘要、GitHub raw README 與 GitHub API）**：

- **HERMES**：David, Bellot（PDF 表頭確認 **Heuritech, 6 Rue de Braque, 75003 Paris**）, Le Corff，**arXiv:2202.03224**（2022 投、2023-09 v3）。**OpenAlex 顯示只有 arXiv 版、2 次引用、沒有 venue → 不是同儕審查發表。** 摘要逐字：「By tracking thousands of fashion trends on social media with state-of-the-art computer vision approaches… We first provide publicly an appealing fashion dataset gathering **10000 weekly fashion time series**. As influence dynamics are the key of emerging trend detection, we associate with each time series **an external weak signal representing behaviours of influencers**… combines per-time-series parametric models with seasonal components and **a global recurrent neural network** to include sporadic external signals… state-of-the-art results on the proposed fashion dataset, on the weekly time series of the **M4 competition**」。
- **README 的 MASE 表（本文件最重要的數字，見 §0(1)）**：10,000 條 TBATS 0.745 → HERMES-WS **0.7132（−4.3%）**；1,000 條 0.734 → 0.7151（−2.6%）；**100 條 0.745 → 0.7368（−1.1%，std 0.0043）**。
- Heuritech 共同創辦人 Charles Ollion 掛名的 CV 論文確實存在（`arXiv:1709.09426` ICCV 2017 WS 弱標註屬性檢索；`arXiv:1812.02611` OMNIA Faster R-CNN「merging Modanet with COCO increases the final performance from 45.5% to 57.4% in mAP」；`arXiv:2010.02849` CoRe, CVPR 2022 WS 顏色回歸）→ 證明**屬性偵測**這一半有學術底子，但那些論文用的是 DeepFashion／ModaNet／COCO，**不是趨勢預測產品的準確度證據**。

**所以 Heuritech 這一家的正確結論**：①方法是**社群影像 → 數千條細粒度屬性週序列 → 全域 RNN 吃 influencer weak signal**；②**自己公布的**效果是 **4.3% MASE @10,000 條序列**，且在 100 條上掉到 1.1%；③「90% accuracy／24 months」是行銷數字，**沒有方法也沒有對照組**；④沒有任何第三方把他們的預測拿去對 naive baseline benchmark 過（**未核**，且很可能是工具限制而非不存在）。

### 1.2 其他廠商

| 廠商 | 訊號 | 粒度 | horizon | lift 證據 | 可信度 |
|---|---|---|---|---|---|
| **WGSN / TrendCurve** | **揭露最完整的一家**（V，官網 AI-data 頁）：「2,800 third-party global data sources」「**100,000+ social media posts monthly** tracked via proprietary Instagram mapping」「300+ million SKUs daily from 10,000+ brands」「30+ million consumer clickstream」「**5+ million catwalk images spanning 28 years**」 | 主題／顏色／品類 | 網站標 2025–2032（多年策略尺度） | **零**。「high accuracy」沒有方法。**而且自承是 "analyst-in-the-loop"＋「250+ experts」** → 不是純 AI 系統 | **V**（資料源揭露）／**U**（準確度） |
| **Stylumia** | 「350K+ brands」市場資料＋自有 True Demand™ | 地區／客群／品類 | **「rising demand caught 3 to 6 months early」**（本調查中唯一給出月數的廠商） | 行銷數字：「up to 2x more winners in every buy」；客戶 Fossil Group | **U**。「Intelligent Demand Index」這個產品名**本輪無法核實** |
| **EDITED** | **確認：電商上架資料，不是社群影像**（V，about-us）：「the world's largest aggregation of global retail data」「**90,000 brands, 5b+ SKUs, tracked every day**」 | SKU／價格／品項結構 | 未揭露（定位是即時競品情報） | **本調查中數字最具體的一家**，但量的是**定價與品項最佳化**不是預測準確度：Hollister「$500k+ incremental revenue」、PVH「sales +27%, units +31%」、PUMA「additional $200K」、Harrods「4% improvement on RPV」、MANGO「ecommerce revenue +50%」 | **V**（訊號來源）／**U**（數字）。**⚠️ 這些數字極易被誤引成「趨勢預測有效」——它們不是** |
| **Launchmetrics（MIV）** | 媒體與 KOL 聲量**折算金額**（V）：「assigns a **monetary value** to media mentions」，用 AVE／rate card＋5,000+ FLB 出版物庫＋互動因子，歸因到五種 Voice（名人／influencer／媒體／夥伴／自有） | 品牌／活動 | **N/A——完全是回顧型量測，不是預測** | 沒有任何對 MIV 方法本身的獨立驗證 | **V**。**⚠️ 類別錯誤警告：MIV 量的是 earned media 曝光價值，不是消費者需求。** 當需求訊號用在方法上是錯的 |
| **Trendalytics** | 社群聲量／TikTok「post and viewing velocity」；**未揭露是否真的做影像 CV** | 趨勢方向／商品層級 | 只有定性說法 | **零**（無案例數字、無論文、無專利） | **U**。本調查中公開紀錄最薄的一家 |

### 1.3 自己做的零售商：訊號幾乎都不是 KOL

| 公司 | 本輪實際查到的 | 可信度 |
|---|---|---|
| **Zalando Research** | 有真實可引用的 ML 論文（Implicit Quantile Networks 機率預測、TimeGrad 擴散式多變量時間序列，皆 ICML 2021 workshop），但都是**通用需求預測方法**，**沒有一篇吃社群影像或宣稱 trend lead time** | **V**（研究頁）；fashion-social 角度的公開紀錄**很薄** |
| **Zara / Inditex** | **本節最重要的反面案例**：公開資料描述 Zara 的優勢**不是預測**而是**反應**——「If a design does not sell well **within a week**, it is withdrawn from shops, further orders are canceled」；「Zara needs just one week to develop a new product and get it to stores, compared to the **six-month industry average**」（另有 4–5 週 design-to-store、改款最快約 2 週的說法） | **U**（Wikipedia 引供應鏈案例文獻）。**論證上很有用：全球最成功的快時尚用「反應速度」取代「趨勢預測」，這本身就是對「必須做趨勢預測 AI」這個前提的反證** |
| **Shein** | 「as quickly as **three days** after the identification of a trend」，約 100 件小批試單再放大（競品約 500 件） | **U**（Wikipedia）。**brief 裡提到的 "LATR" 模型名本輪完全查不到** → **無法核實／可能不是公開名稱** |
| **Fast Retailing / UNIQLO** | **顧客回饋**（不是 KOL）：官方稱年收 3,900 萬則、FY2024 於 26 國近 110 萬則，每週回饋給商品部 | **V**（官方頁，已在 `docs/research/industry-fashion-brands.md`） |
| **Target** | 「AI 偵測 TikTok『mob wife』豹紋趨勢後與供應商快速放大豹紋商品」 | **U**（Retail Dive 二手摘要，2024）。**單一屬性、數週尺度、無數字** |
| **Myntra** | 有真實論文，但都是**推薦／檢索**（`arXiv:2008.11638` Buy Me That Look、`1806.11371`、`2309.14046`），**沒有趨勢預測** | **V** |
| **Amazon** | **修正 brief 的一個錯誤**：「Fashion++」（`arXiv:1904.09261`, ICCV 2019）是 **Facebook AI Research／UT Austin**（Hsiao, Katsman, Wu, Parikh, Grauman），**不是 Amazon**，不要引成 Amazon 的論文。StyleSnap 是真實產品，但是**視覺搜尋**，找不到任何把它描述成預測系統的論文或頁面 | **V**（arXiv）；StyleSnap 的預測用途**未核到** |
| **H&M／Pinterest Predicts／Google** | 本輪都因為沒有搜尋而抓不到正確頁面（猜的 URL 全 404） | **未核**（工具失敗，不是「沒有」） |

### 1.4 這一節該帶走的四件事

1. **業界確實在做，而且最該對標的那一家（Heuritech）方法就是我們設想的那條路**（社群影像 → 細粒度屬性序列 → 吃 influencer 訊號）。所以這個產品想法**不是天真的**，這點要對提案人講清楚。
2. **但他們自己公布的效果只有 4.3% MASE，而且需要 10,000 條序列。** 這是全文獻唯一的 MASE 數字，也是我們最該引用的數字——它同時證明「這件事有人做」與「這件事對我們的規模不可行」。
3. **其他人的訊號多半不是 KOL**：EDITED 是電商上架、UNIQLO 是**顧客回饋**、Zara/Shein 是**自己的 POS＋反應速度**、WGSN 自承 **analyst-in-the-loop**。唯一明確的 KOL→採購案例（Target 豹紋）是二手報導、無數字、單一屬性、數週尺度。**Launchmetrics 的 MIV 量的是媒體價值，當需求訊號用是類別錯誤。**
4. **對聚陽（OEM）而言這些全發生在客戶那一側。** 前五大客戶 Gap Inc.／Target／Fast Retailing／Dick's／Kohl's 合計 88%（`docs/research/industry-fashion-brands.md`，已核 2026 法說簡報）；「豹紋要不要下單」是**品牌 merchandiser** 的決定，聚陽拿到 tech pack。詳見 §4.4。

---

## 2. 學術線：誰做了什麼、對照什麼 baseline、什麼 horizon

**本節全部 V**（OpenAlex `works/doi:<doi>`，逐字讀摘要原文）。凡是我沒讀到實驗表格的，標「僅摘要」，**不替它補 baseline**。

| 論文 | venue / 年 / DOI | 資料 | 粒度 | horizon | 報告的數字 | 對照的 baseline |
|---|---|---|---|---|---|---|
| **StreetStyle**（Matzen, Bala, Snavely） | arXiv 2017｜10.48550/arxiv.1706.01869 | 數百萬張全球人像照、跨數年 | 服裝屬性分類器＋style cluster | **無預測** | 首見的全球／城市級時空分析 | **沒做預測，所以沒有 baseline** |
| **GeoStyle**（Mall, Matzen, Hariharan, Snavely） | **ICCV 2019**｜10.1109/iccv.2019.00050 | 大規模街拍 | 屬性曲線＋自動發現 style＋時空事件 | 「long-term」（**摘要沒給月數**） | 長期趨勢預測比 **prior art 準 >20%** | **是比 prior art，不是比 persistence／seasonal naive**；摘要無絕對誤差 |
| **Fashion Forward**（Al-Halah, Stiefelhagen, Grauman） | **ICCV 2017**｜10.1109/iccv.2017.50（arXiv:1705.06394） | Amazon 三資料集，**8 萬件商品、6 年** | 無監督發現的 style | 摘要未給 | 「benefits greatly from visual analysis, **much more than textual or meta-data cues**」 | 只有「視覺 vs 文字／metadata」的**相對**比較；**摘要未點名 persistence／seasonal naive**；僅摘要 |
| **From Paris to Berlin**（Al-Halah & Grauman） | **CVPR 2020**｜10.1109/cvpr42600.2020.01015 | 城市級街拍 | 城市間風格影響力 | — | — | — |
| **KERN**（Ma, Ding, Yang, Liao et al.） | **ICMR 2020**｜10.1145/3372278.3390677（arXiv:2005.03297） | 自建 **FIT**：Instagram 的**細粒度時尚要素時間序列＋使用者分群** | **fine-grained fashion element**（最貼近我們的想法） | 摘要未給 | **摘要完全沒有數字**，只寫「effectively capture the complicated patterns … making preferable fashion trend forecast」 | 摘要未點名 baseline |
| **Well Googled is Half Done / GTM-Transformer**（Skenderi, Joppi, Denitto, Cristani） | **Journal of Forecasting 2024**｜10.1002/for.3104（arXiv:2109.09824, 2021） | **VISUELLE**：Nunalie 真實快時尚，**5,577 件新商品、2016–2019**，含圖／metadata／銷售／Google Trends | 商品層級新品銷售 | 新品（無歷史） | 「the addition of exogenous knowledge boosts the forecasting accuracy by **1.5% in terms of WAPE**」 | 摘要明寫比「state-of-the-art alternatives and **several baselines**」，且在 WAPE 與絕對誤差上皆最準。**1.5% 是外生訊號的淨貢獻** |
| **POP**（Joppi, Skenderi, Cristani） | ECCV 2022 workshop / LNCS｜10.1007/978-3-031-19839-7_3（arXiv:2207.11001） | webly cross-modal query expansion | 新品潛在表現 | 新品 | OpenAlex 無摘要 | **內容未核** |
| **MuQAR**（Papadopoulos, Koutlis, Papadopoulos et al.） | **IJMIR 2022**｜10.1007/s13735-022-00262-5 | Mallzee-P、**SHIFT15m**、Amazon H&K；並在 VISUELLE 上比較 | 新品**屬性**時間序列當流行度 proxy（target + exogenous 屬性序列） | 新品 | VISUELLE 上超越當時 SOTA **4.65% WAPE / 4.8% MAE** | **同樣是比 SOTA，不是比 seasonal naive** |
| **FashionKE**（Ma, Yang, Liao, Cao et al.） | ACM MM 2019｜arXiv:1908.08985 | 社群貼文 | 場合／人／穿什麼的知識抽取 | 無預測 | — | — |
| **Computational Technologies for Fashion Recommendation: A Survey**（Ding, Lai, Mok） | **ACM CSUR 2023**｜10.1145/3627100 | 綜述 | — | — | 自承要討論「the current limitations and **gaps between academic research and the real needs of the fashion industry**」 | — |
| Fashion Meets Computer Vision（Cheng et al.） | ACM CSUR 2021｜10.1145/3447239 | 綜述 | — | — | — | — |
| A Review of Modern Fashion Recommender Systems（Deldjoo, Nazary, Ramisa, McAuley） | ACM CSUR 2023｜10.1145/3624733 | 綜述 | — | — | — | — |

### 2.1 讀完之後的四個結論（本文件最重要的一節）

**(a) 沒有一篇對 persistence／seasonal naive 報 MASE。** GeoStyle 比 prior art（>20%）、MuQAR 比 SOTA（4.65% WAPE）、Fashion Forward 比「視覺 vs 文字」。時尚**本來就強季節**（春夏／秋冬），「打贏上一個模型」和「打贏 seasonal naive」是兩件完全不同的事，而**後者沒有人報**。→ 我們自己做的話**一定要報 MASE**（分母＝訓練段 seasonal-naive 的 MAE，M-competition 標準），否則我們只是在重複同一個毛病。

**(b) 唯一在「真實銷售」上量到外生訊號淨貢獻的數字是 1.5% WAPE**（Skenderi et al., *J. Forecasting* 2024，V），而且那個訊號是 **Google Trends 搜尋量**——比 KOL 貼文更接近需求。**INF**：如果最接近需求的外生訊號只值 1.5% WAPE，KOL 貼文的上界不會更高。這句話可以直接當我們**不做**這件事的理由。

**(c) 最貼近我們想法的那篇（KERN）摘要裡一個數字都沒有。** 這不代表它沒做實驗，而代表**這條線的公開紀錄薄**：要用它支撐「要素層級趨勢可預測」，必須先讀到實驗表格與 baseline，本輪沒做到 → 標 **U**。

**(d) 唯一報 MASE、也唯一量過 influencer 訊號的那一篇（HERMES），恰好是 Heuritech 自己的，而它的數字否決了我們的規模。** 4.3% @10,000 條 → 2.6% @1,000 條 → **1.1% @100 條**。摘要自己說明了為什麼：influencer 訊號是 **sporadic external signal**，要靠 **a global recurrent neural network** 跨序列學。**這是「機制上需要規模」，不是「多做幾次實驗就會有」。** 我們的 11 條軸連 100 條都不到。
→ 同時也要誠實說：HERMES **只有 arXiv 版、2 次引用、沒有 venue**，所以它也不是同儕審查證據；但它是**廠商自己對自己最有利的公開數字**，因此當作**上界**使用是安全的——真實效果不會比廠商自己報的更好。

---

## 3. 今天、無付費合約、無機構資格，我們能合法用什麼

### 3.1 平台 API（存取日期皆 2026-09-18）

| 平台 | 現況 | 能不能用 |
|---|---|---|
| **X / Twitter** | 官方定價頁（docs.x.com）顯示已改成**用量計價**：「The X API uses pay-per-usage pricing. No subscriptions—pay only for what you use.」Post 讀取 $0.005／resource，**上限「capped at 3 million Post reads per monthly billing cycle」**。頁面上**找不到任何學術／研究方案**（與 2023 關閉 Academic Research 一致）。**開發者條款頁 HTTP 402 → 儲存／再散布條款無法核實** | ❌ 要錢、且條款無法核實 → **不碰** |
| **Instagram Graph API**（hashtag search） | 需要**連到 FB 粉絲頁的 Business/Creator 帳號**＋`instagram_basic`（＋`ads_management`/`business_management`/`pages_read_engagement`）＋**強制 App Review 的 "Instagram Public Content Access"**。逐字限制：「**You can query a maximum of 30 unique hashtags within a 7 day period.**」`recent_media`/`top_media` **會回 `media_url`**。Meta Platform Terms §3.d 逐字：「**You must delete all Platform Data as quickly as possible when you no longer need to retain Platform Data for legitimate business purposes under these Terms.**」（**V**） | ❌ 黑客松拿不到 App Review；且 30 hashtag/7 天＋須刪除的保留條款讓「建一份帶日期的影像資料集」不合法 |
| **TikTok Research API** | 資格限**美國／EEA／英國／加拿大／瑞士的學術機構**（EU 非營利研究組織 beta；巴西青少年安全）；博士生需**指導教授背書函**。非學術組織（若合格）只能在鎖定的 **Virtual Compute Environment** 內用，資料不出境。**黑客松團隊不在任何合格類別內**。回傳內容細節、rate limit、保留／刪除條款**無法核實** | ❌ **資格不符** |
| **Pinterest** | 開發者規範逐字：「Except for campaign analytics information … **you may not store any information accessed through any Pinterest Materials including the API.**」並要求「call the API each time you need to access information」（**V**） | ⚠️ **這正好逐字印證我們既有的設計**：`engine02/trends.py::from_live_fetch` 標 `ephemeral=True`、`save()` 丟 `PermissionError`。**建議把這段原文補進 `trends.py` docstring 的引用**（目前只寫「PRD ref [108]」） |
| **Reddit** | reddit.com／redditinc.com／support.reddithelp.com 全部 403／抓不到 → **2026 的 rate limit、商業條款、Pushshift 現狀全部無法核實** | ❓ **不要在簡報上講任何 Reddit 數字** |
| **Flickr** | ToS 可讀（**V**）：預設商業／非商業都免費（高用量或營收導向需商業 key）；限制「may not display more than 30 Flickr user photos per page」；需顯示 attribution；**`license` 搜尋參數可以只挑 CC 授權** | ✅ **唯一「圖片可以合法存下來」的平台**（挑 CC-BY）。StreetStyle 系做法的合法版本就在這裡 |
| **Google Trends** | 官方 Search Central Blog 有 **"Introducing the Google Trends API (alpha)"（2025-07）**，但貼文本體 404、**存取模式／費用／限額無法核實**。Trends 網頁 CSV 匯出的再利用條款也**無法核實** | 🟡 可用（VISUELLE 2.0 已附現成序列），但**別在簡報上宣稱官方 API 可用** |
| **Bluesky / AT Protocol** | firehose 文件頁抓不到；Bluesky ToS 只聲明無法控制第三方應用如何處理內容，**沒有明確的「可儲存」授權** | 🟡 條款上最寬鬆，但**沒有明文許可** → 不當主線 |
| **Mastodon** | 聯邦式、每個 instance 自訂條款 → **沒有單一答案**（這是協定設計，不是查核缺口） | ❌ 不可預期 |

### 3.2 公開、帶時間戳的資料集

| 資料集 | 授權 | 規模／期間 | 圖或只有 metadata | 有時間軸？ | 不用帳號能下載？ |
|---|---|---|---|---|---|
| **`xthan/polyvore-dataset`（Maryland Polyvore）** | **Apache-2.0**（**V**，README） | **21,889 個 outfit**（17,316/1,497/3,076）；**約 2017-02-19 爬取**，每 outfit 有 **`date`／`likes`／`views`／`set_id`**；item 命名 **`SetID_ItemIndex`** | metadata（JSON）；**官方圖 URL 已失效**，但 **我們 repo 裡已經有圖**（`Marqo/polyvore`，HF card 標 apache-2.0） | ✅ **有**（outfit 上傳日期） | ✅ JSON 直接抓 |
| **HERMES fashion dataset**（`github.com/etidav/HERMES`） | **⚠️ GitHub API 回報 `license: None`——repo 沒有宣告任何授權**（**V**，2026-09-18 實測） | **10,000 條週頻時尚趨勢序列**，每條附 **influencer weak signal**；`data/` 下 6 個 CSV：`f1_main.csv` 54 MB、`f1_fashion_forward.csv` 52 MB，及 1000／100 條子集；repo 162 MB，最後更新 2023-10-27 | ❌ **只有時間序列，沒有圖** → **無法驗證我們的要素機制** | ✅ **有**（週頻） | ✅ **curl 直接下載，不用帳號也不用表單** |
| **VISUELLE 2.0** | **官方頁未載明授權**（只要求引用 CVPR 2022 workshop 論文）（**V**） | 5,355 件、**2017–2019 六季**、Nuna Lie；HD 商品圖＋**門市層級日銷／庫存／價格／折扣**＋**Google Trends**＋天氣＋66.7 萬顧客匿名購買 | ✅ 圖＋銷售＋外生序列 | ✅ **最好的時間軸** | ❌ 需填表取得連結 |
| **Amazon Reviews 2023**（McAuley Lab） | **未載明**（歷來「for research purposes」）（**V** 頁面／**U** 授權） | `Clothing_Shoes_and_Jewelry`：**22.6M users／7.2M items／66.0M ratings**；時間戳「at the second or finer level」 | **只有圖片 URL**（會逐年失效） | ✅ 有（秒級） | ✅ 直接抓 `.jsonl.gz` |
| **GeoStyle** | **CC BY 4.0**（**V**） | 只釋出 Barcelona Flickr 的**屬性預測 pickle**＋預訓練模型＋程式碼 | ❌ **沒有原圖** | 頁面未載明區間 | ✅ |
| **StreetStyle-27K** | — | — | — | — | ❌ **官方站 `streetstyle.cs.cornell.edu` TLS 憑證不符、實質無法存取**（**V**，2026-09-18 實測）。這本身就是結論：基礎設施已腐朽 |
| **SHIFT15M**（ZOZO/IQON） | 需核 | arXiv 2021（Kimura, Nakamura, Saito，**V** DOI） | — | ✅ 設計目的就是分布漂移，有時間戳 | 需核 |
| **H&M Kaggle** | **未解決**（Kaggle 競賽規則頁 JS 渲染抓不到；競賽資料集常限競賽內使用） | 帶日期交易＋商品圖 | ✅ | ✅ | ❌ 需登入；**授權未確認前不要用** |
| **FIT / POP**（KERN） | **完全無法核實**（找不到權威頁） | — | — | — | ❓ |
| DeepFashion2 / Fashionpedia / FashionIQ | FashionIQ = **CDLA**；其餘未載明 | — | 圖 | ❌ **都沒有時間戳** | 多需填表 |
| **Wikimedia pageview dumps** | 開放 | **2015–2026**，時／日粒度（**V**，目錄實測） | ❌ 只有 pageview | ✅ | ✅ |

### 3.3 §3 的結論

- **原始社群圖：合法拿不到。** Instagram 要 App Review＋30 hashtag/7 天＋須刪除；TikTok 資格不符；X 要錢且條款無法核；Pinterest 明文禁存。→ 「把 Instagram/TikTok 餵進 recommender」在 2026 年對我們**不是技術問題，是資格問題**。
- **唯一可以合法儲存社群來源影像的平台是 Flickr（挑 CC 授權）**，但那要自己重建 StreetStyle 等級的管線，不是黑客松尺度。
- **最好的選擇是我們已經有的那份**：Polyvore（Apache-2.0 metadata＋repo 內既有圖＋`date`/`likes`/`views`）。它是「社群策展」而不是「KOL 貼文」，這個差別必須在簡報上講清楚——但它是**唯一**我們能今天就跑完整 falsification 的資料。
- **資訊價值最高的那份（HERMES）不能當主線，因為 repo 沒有宣告授權。** 可以讀、可以引用它的 README 數字（公開發表的內容），**不要把 CSV 放進 git，也不要在它上面建我們的主線結果**。它沒有圖，本來也驗不了我們的機制。
- **一個給簡報用的對比**：WGSN 揭露自己每月追 **100,000+ 則社群貼文**、Heuritech 追**數千萬張圖並維持 10,000 條序列**，才拿到 4.3% MASE。我們手上合法可用的是 **21,889 個 Polyvore outfit、11 條軸**。**規模差距本身就是我們不做預測的理由**，而且這個理由比「我們沒時間」誠實得多。

---

## 4. 在我們的架構裡，會動的版本長什麼樣

### 4.1 先釘住既有架構的事實（讀碼核對，全部 V）

| 事實 | 位置 |
|---|---|
| `S(i)=Σ_terms`，每項 `raw/normalized/weight/contribution`，加總**嚴格等於**總分（測試強制） | `engine02/rerank.py::additive_score`、`Term` |
| `β_d = γ·(Σ_n p(n)K[n,d] + step·Δsteps_d) + learned Δβ` | `engine02/pipeline.py::_terms`、`engine02/kansei.py::KanseiTable.beta` |
| **`learned Δβ` 已是契約欄位**：`FeedbackState.design_weight_delta: dict[str,float]`，`_terms` 已在讀、已處理反義極 sign-flip | `engine02/contracts.py:130`、`engine02/pipeline.py::_terms` |
| 設計項的**項內歸因**已有慣例：`Term.need_shares_per_unit` 除 need 外放了 `"feedback_adjust"` 假 key，`need_shares` 加總＝該項貢獻 | `engine02/pipeline.py::_terms`、`engine02/contracts.py::Contribution.need_shares` |
| 卡片／面板把 `need_shares` 的 key 當 need 標籤查表 | `engine02/explain.py:36`、`engine02/panels.py::_need_labels` |
| 15 要素 → **11 條正規軸**（4 對反義極折疊：matte/glossy、minimal/bold、relaxed/tailored、formal/casual） | `engine02/kansei.py::KanseiTable.load`；`preference.py` 也自稱 "full 11×11 covariance" |
| **單張圖打分已寫好**：同 prompt、同公式，回報 z 與百分位，有 prompt cache | `engine02/concepts.py::element_profile`（`api.py:411` 已在用） |
| 偏好學習的 Kansei 先驗中心／共變異 | `engine02/preference.py::prior_mean / prior_cov` |
| **商品庫沒有任何時間欄位**（15 欄，已驗 parquet：kagl 5000×15、polyvore 3000×15） | `engine02/catalog.py` docstring |
| `item_id` 就是 Polyvore 的 `SetID_ItemIndex`，拆解函式已存在 | `scripts/prepare_catalog.py::polyvore_set_id`、`adapt_polyvore` |
| 趨勢關鍵字進排序的代價已量測、已否決 | `docs/engine02-design.md` §3.15、`scripts/eval_trends.py` |

### 4.2 原假設的「訊號」那一半為什麼不成立（四個獨立理由，第 ④ 個是決定性的）

1. **粒度錯層**。11 條軸是**感性印象軸**（可信任感／幹練感的視覺中介），不是**時尚新奇軸**。文獻上真的會動的是細粒度屬性（KERN 明寫 fine-grained element；GeoStyle 是單屬性曲線）。一個具體流行（寬版直筒）投影到 `relaxed_fit` 只是微小位移，而且**跟「這個月抓到的照片比較多街拍」不可區分**。
2. **域偏移吃掉訊號**。`element_profile` 是對**商品庫**分布做 z 的；社群語料是模特兒實穿照，而 §3.16 已量到 FashionCLIP 系偏好白底商品照。直接拿社群圖對商品庫 z-score → 量到的是**拍攝域**。改成對社群語料自己的基準 z → 域偏移被控掉，但變成對**語料組成漂移**極度敏感。
   → **例外、也就是我們的出路**：Polyvore 的 item 圖**就是零售商品圖**，和商品庫同域 → **這個反對理由在 Polyvore 資料上不成立**。這是為什麼 §0(1) 說訊號「救回來了」。
3. **單位不可辨識**。β_d 乘的是商品庫 z 分的 c(i,d)；趨勢序列的單位是語料 SD。兩者之間**沒有資料能定出換算係數**。唯一誠實做法：**不要估它**，用既有 `step_size = 0.25` 當硬上限，並在 docstring 與簡報上明說這是**設計選擇**而非估計值。
4. **序列數不夠——這是最致命、也最好引用的那個（詳見 §0(1)、§1.1、§2.1(d)）**。Heuritech 自己的 HERMES 顯示 influencer 訊號的價值是 **4.3% MASE @10,000 條序列**，而且**隨序列數單調崩塌到 1.1% @100 條**；機制上的原因寫在他們摘要裡——那個訊號 sporadic 且微弱，必須靠 **global RNN 跨數千條序列 pool** 才學得出怎麼用。**我們有 11 條。** 所以就算 ①②③ 全部解決了，要素層級的趨勢預測在我們的維度上**機制性地不可行**，而不只是「資料不夠」。
   → 這一條同時給了我們一個**正面**的推論：既然訊號的價值需要規模才萃取得出來，那麼**在 11 條軸上唯一站得住的用法就是「一個有上限的小偏移」，而不是一個預測器**。§4.3 的設計就是照這個推論做的。

### 4.3 會動的版本：不是預測器，是「有揭露、有上限」的族群偏移

**機制（`檔案:函式` 級，全部是給 coordinator 的新增建議，我沒有改任何檔案）**

| 步驟 | 位置 | 要加什麼 |
|---|---|---|
| ① outfit → 日期 | **新檔** `engine02/element_trends.py::load_polyvore_dates(json_paths) -> dict[set_id, date]` | 讀 `xthan/polyvore-dataset` 的 `*_no_dup.json`，取 `set_id` + `date`。用既有的 `prepare_catalog.polyvore_set_id(item_id)` 做 join。**`date` 欄位的實際格式必須先打開 JSON 確認**（README 說「estimate the exact upload date」，暗示可能是相對字串）→ 這是一個約 30 分鐘的前置檢查，**沒過就整條不做** |
| ② 圖 → 11 軸原始分數 | `engine02/element_trends.py::score_corpus(engine, dates)` | 直接重用 `engine.design_matrix(ARMS["full"])`（已是商品庫 z 分的 c(i,d)）**或** `concepts.py::element_profile` 的同一條 antonym 公式。**z 的 mean/SD 在切訓練／測試之前固定一次**（否則洩漏）。回傳 `DataFrame[month, element, mean_c, n_items, n_outfits]` |
| ③ 月序列 → 偏移向量 | `engine02/element_trends.py::to_beta_offset(series, cap=0.25)` | `Δβ_d = clip(κ·(y_d(T) − baseline_d), ±cap)`，`cap` 預設 = `KanseiTable.step_size`。**`κ` 是寫死的設計選擇**，docstring 必須這樣寫 |
| ④ 接進排序 | **不改 `pipeline.py` 也能跑**：填 `FeedbackState.design_weight_delta` | `_terms` 已在讀。**但**該欄位語意是「從 choice_history 學到的」，兩者混在同一個 dict 會**分不開歸因** → 建議 coordinator 新增 `FeedbackState.trend_prior_delta` 並在 `_terms` 多讀一個 dict（約 5 行） |
| ⑤ 歸因（解釋誠實性的核心） | `engine02/pipeline.py::_terms` 的 `per_unit` dict | 加 `per_unit["trend_prior"] = <趨勢那一份>`，做法與現有 `per_unit["feedback_adjust"]` **完全一致**。`need_shares` 仍加總等於該項貢獻（既有測試會驗），卡片就能寫「挺肩線 +0.31，其中 0.24 來自你想要的『幹練』、**0.07 來自族群偏移**」 |
| ⑥ 文案標籤 | `engine02/panels.py::_need_labels`、`engine02/explain.py::template_reasons`（ 合併處，目前第 36 行） | 各加一行 `"trend_prior": "族群近期偏移（你的回饋可覆蓋）"` |
| ⑦ **絕對不要動** | `engine02/kansei.py::KanseiTable.K`、`engine02/preference.py::prior_mean` | **K 不能寫入**：K[n,d] 的語意是「文獻說這個需求由這個要素服務」，趨勢是「族群分布在動」；混進同一矩陣就再也分不開，`kansei_v1_literature.json` 的可稽核性也會消失。**`prior_mean` 也不能動**：它是「對**這個使用者**的先驗」，趨勢是**族群**的事；塞進去等於告訴 Bayes 學習器「這個使用者本來就偏好流行」，會讓使用者的回饋需要更多證據才翻得動它 |

**避免與感性表雙重計數的三道防線**

1. **不同通道**：趨勢走 `trend_prior_delta`（加性 Δβ），感性走 `K`。代數上加在同一個 `design:<d>` 項，但**來源可分離、歸因可分離**。
2. **上限 ≤ 一格回饋**：`cap = step_size = 0.25`，而使用者一次 `adjust(d,±1)` 就是 0.25 → 「使用者一句話永遠壓得過趨勢」是**代數事實**，不是承諾。
3. **不被 γ 放大**：`_terms` 現在是 `arm.need_scale*(beta_needs+beta_fb) + learned`，趨勢偏移走 `learned` 那一側 → **不受 γ 影響**，T6 的 γ sweep 結論不會被污染。

**「這個要素最近在社群上升」這句話我們能不能辯？** 不能，除非同時說出三件事。文案建議：

> 「挺肩線（其中 +0.07 來自族群偏移）」＋可展開的 provenance：「來源：Maryland Polyvore 策展穿搭，<n> 件、<日期區間>；基準＝同語料全期平均；打分用的是**和商品庫同一組 prompt、同一個影像模型**。**這是 2010s 的 Polyvore 快照，不是 2026 年的流行證據，也不是預測。**」

`engine02/panels.py::Provenance` 已有 provenance caveat 欄位與測試 → 這是延伸既有機制。**沒有這段 provenance 就不要上這個功能**，否則我們是把「我們抓到那一小撮資料的組成」講成「社群在流行」。

**冷啟動**：語料月份不足（`n_months < 24` 或月內 `n_items` 低於門檻）→ `to_beta_offset` 回空 dict → **完全 no-op**、卡片上不出現趨勢字樣。與 §3.16「沒有概念圖時完全是 no-op」同一個設計與同一個風險控制理由。

### 4.4 2–6 個月生產前置期：這一項其實不適用於我們，必須講清楚

**聚陽是 OEM，趨勢決策不在我們這一端。** 前五大客戶 Gap Inc.／Target／Fast Retailing／Dick's／Kohl's 合計 88%（`docs/research/industry-fashion-brands.md`，已核 2026 法說簡報）。做「豹紋要不要下單」的是**品牌 merchandiser**，聚陽拿到 tech pack。所以：

- 一個領先 6 個月的訊號**改變的是品牌的行為，不是 OEM 的行為**；
- ENGINE 02 的職責是**消費者端、既有商品庫上的對話式推薦**。在這個職責裡，趨勢先驗的作用**根本不是預測**，而是一個**流行度先驗**——弱得多，但誠實得多；
- 對 OEM 真正有價值的用法是**提案側**：「我們建議這個款，因為要素 X 在<語料>上升」。那是一張投影片，不是線上排序項。（**INF**）

**文獻宣稱的 lead time 是多少？** GeoStyle 說「long-term」但摘要沒給月數；Fashion Forward 摘要也沒給；唯一有真實銷售、設定明確的 GTM-Transformer 做的是「新品第一季」，而外生訊號只值 1.5% WAPE。產業側的行動窗口是 Zara 約 4–5 週／Shein 約 3 天／傳統約 6 個月（**U**，二手）。→ **「領先 2 週沒用」這個批評在文獻上根本還沒被回答**：沒有人公開報過可信的「社群訊號領先服飾銷售 N 個月」估計。公開紀錄在這一點上是**薄的**，我們不該假裝它厚。

---

## 5. 怎麼用我們拿得到的資料把它證偽

### 5.0 先講一件必須說出來的事：§3.15 那個實驗**不能**用來評估趨勢先驗

`scripts/eval_trends.py` 的 docstring 自己就寫了：

> "NDCG@5/@10 against the attribute ground truth (T1's grades — **the trend term is *not* part of that ground truth, so any NDCG change is a cost, not a gain**)"

也就是說：在那個評估設計下，**任何**與屬性 metadata 正交的新項都只會扣分——**包含一個正確的趨勢訊號**。§3.15 的 28 組負結果是一個**有效的警告**（「你要為這個項付出多少屬性相關性」），但它**不是**「趨勢無效」的證據；如果我們拿同一套工具評估趨勢先驗，會拿到同一個負號，而它**什麼都不代表**。

→ **建議：不要重跑那個實驗，也不要在簡報上拿它的負號當「我們驗過了」。** 要驗趨勢，ground truth 必須有時間軸。（這一點也請寫進 `docs/engine02-design.md` §3.15 的邊界說明——那個結論對「關鍵字項」成立，對「任何趨勢機制」不成立。）

### 5.1 預測端 backtest（要素流行度）— **這一段在黑客松內做得到**

- **資料**：`polyvore_big`（25k Polyvore 商品，nycu 上）＋ `xthan/polyvore-dataset` 的 `*_no_dup.json` 的 `date`。圖已在手、授權 Apache-2.0、**與商品庫同域**。
- **前置閘門（沒過就停）**：打開 JSON 確認 ①`date` 的實際格式與可解析性；②join 後的**逐月覆蓋率**（每月至少幾百件才有意義）；③實際日期區間（需要 ≥5 年的月資料，見下）。
- **序列**：每條正規軸 d，`y_d(t) = mean_{item ∈ 該月 outfit} c(i,d)`。z 的 mean/SD **在切割前固定一次**。
- **必須打敗的 baseline**（整個測試的重點）：① persistence `ŷ(T+h)=y(T)`；② **seasonal naive `ŷ(T+h)=y(T+h−12)`** ← 時尚是強季節，這才是真正的對手；③ drift／線性；④ **GeoStyle 式參數曲線**（線性＋年週期正弦），只用訓練段擬合。
- **指標**：**MASE**（分母＝訓練段 seasonal-naive 的 MAE）為主，sMAPE 為輔。**逐軸報告，不准只報 11 軸平均**——平均會把「只有 1 條軸有訊號」藏起來。
- **統計**：rolling-origin，配對檢定用既有 `engine02/eval/metrics.py::paired_permutation_test` / `bootstrap_ci`，seed 固定。
- **三個對照組（照 §3.16 與 `concepts.py::random_words` 的既有慣例）**：
  1. **打散時間**：隨機重排 outfit 的月份標籤後重跑。打散後一樣好 → 我們量到的是語料組成，不是流行。
  2. **隨機描述詞**：用 `concepts.py::_random_descriptors` 造 11 條假軸跑同一管線（WaffleCLIP, ICCV 2023 的對照邏輯，`concepts.py` 已實作）。
  3. **組成固定**：每月重抽樣到固定的 outfit 數／品類組成，看序列還在不在。
- **樣本量的誠實話（INF）**：月資料 5 年 = 60 點。留 24 個月測試、h=3 rolling origin ≈ 22 個 origin × 11 軸 = 242 個配對觀測，**但高度自相關、軸之間也相關**，有效 n 更接近「每軸 ~22」。所以：**即使跑得動，「打敗 seasonal naive」的宣稱也只能逐軸講、而且會很弱。** 這是一張投影片，不是一個 demo 賣點。
- **外部對照（不用自己跑就能引用）**：HERMES 的 README 已經把「11 條 vs 10,000 條」的答案給我們了——**1.1% @100 條、std 0.0043**。我們的 11 條只會更差。所以 §5.1 的**預期結果是打不贏 seasonal naive**，而這個負結果**在 Heuritech 自己的數字下是被預測到的**，不是我們做壞了。這一點要寫進報告：一個**事前就有外部理由預期為負、事後也確實為負**的實驗，比一個沒有預期的實驗有價值得多。

### 5.2 推薦端測試（唯一真正能辯的那個）

- **有效設計只有一種**：ground truth 必須隨時間變。
  - **黑客松版（用手上的資料）**：Polyvore 的 **`likes` / `views`** 是**帶日期的互動訊號**。協定：用 ≤T 月算要素趨勢 → `to_beta_offset` → `trend_prior_delta`；在 T+1…T+3 月**新上傳的 outfit** 上評估排序（NDCG@k / recall@k，相關性＝該月被高度 like 的商品）；同一組查詢**配對**比較「有／無趨勢先驗」，`paired_permutation_test`；加上 §5.1 的三個對照組。**這個 ground truth 與屬性 metadata 正交，所以不會落入 §5.0 的陷阱。**
  - **嚴謹版（做不完）**：VISUELLE 2.0 的門市層級日銷，或 H&M Kaggle 的帶日期交易（授權未解決）。
- **樣本量（INF，配對檢定 n ∝ 1/效果²）**：§3.15 用約 60 個查詢就在 −0.16 NDCG@5 打到 p≈1e-4。正向效果合理量級 ≤ +0.02，同樣的每查詢 SD 之下需要約 `60 × (0.16/0.02)² ≈ 3,800` 個配對查詢——**約 60 倍於 §3.15 的規模**。這個數字本身就是結論：**黑客松時程內做不出統計上站得住的推薦端正向宣稱。**
- **做得到的誠實替代品**：不宣稱排序變好，只報 T6（`engine02/eval/tasks.py::t6_need_tradeoff`）的三欄結構——`ndcg5`（代價）、`alignment`（機制有沒有做它說的事）、`changed`（前 k 換掉幾件）。**但要明說 `alignment` 是循環的**（用同一組 β 算），這點 `eval_trends.py` 與 T6 的 docstring 都已自承。

---

## 6. KOL 專屬問題：「網紅領先、大眾跟隨」站得住嗎？

| 證據 | 出處 | 說的是什麼 | 對我們的意思 |
|---|---|---|---|
| **反對** influentials 假設 | Watts & Dodds, **JCR 2007**｜10.1086/518527（**V** 摘要原文） | 「large cascades of influence are driven **not by influentials but by a critical mass of easily influenced individuals**」；並說該假設「requires more careful specification and testing than it has received」 | 「KOL 領先」是**營銷界的假設，不是實證結論**。註：這篇是**模擬**，所以也不是反面定論 |
| 影響力分佈很散 | Bakshy, Hofman, Mason, Watts, **WSDM 2011**｜10.1145/1935826.1935845（**U**，子代理經 Crossref 核書目） | 約 160 萬 Twitter 使用者；多數 cascade 很小；**追蹤數是很弱的影響力預測因子**；鎖定大量普通使用者常比鎖定少數大號更有成本效益 | 「找到幾個 KOL 就能引爆」在資料上罕見 |
| 擴散結構 | Goel, Watts & Goldstein, **EC 2012**｜10.1145/2229012.2229058（**V** 摘要原文）；Goel, Anderson, Hofman, Watts, **Management Science 2016**｜10.1287/mnsc.2015.2158（**U**） | 多數 cascade 極淺；約 10 億次 Twitter 擴散事件中「structural virality typically remains **low** regardless of popularity size」→ 大型事件主要是**廣播**（一對多），不是多代人傳人 | 連「病毒式」都不是 trickle；**trickle-down 的比喻本身就不對** |
| 因果識別 | Shalizi & Thomas, **Sociological Methods & Research 2011**｜10.1177/0049124111404820（**V**，摘要／venue） | homophily 與 contagion 在觀察性社群網路研究中**generically confounded**；無模仿的簡單模型也能產生同樣的相關性特徵 | **任何「KOL 貼文領先銷售」的觀察性相關都不是因果證據。** 我們拿相關性上台會被問倒 |
| 網紅行銷實際量到什麼 | Leung, Gu & Li, **Journal of Marketing 2022**｜10.1177/00222429221102889（**V** 摘要原文） | 量的是 **engagement elasticity**（不是銷售）；「influencer originality, follower size, and sponsor salience enhance effectiveness, and **posts that announce new product launches diminish it**」；activity／follower–brand fit／positivity 皆**倒 U** | 兩件事：①連頂級行銷期刊量的也是**互動**不是**需求**；②「**宣布新品的貼文效果更差**」直接打到「KOL 貼文＝新流行前導指標」這個直覺 |
| 經典時尚擴散理論**反對** top-down | King 1963「A Rebuttal to the 'Trickle-Down' Theory」（2024 Routledge 重印，10.4324/9781003424208-13，**U**）；Blumer 1969 collective selection（**U**） | **trickle-across**：在大眾媒體／大量生產市場，時尚採納是**橫向、近乎同時**跨階層與價位發生的，不是從精英慢慢滴下來 | 時尚學界在社群媒體出現前**數十年**就大致否定了 naive top-down 模型。KOL 敘事是在**復辟一個該領域自己反駁過的理論** |
| 外生訊號在真實銷售上的價值 | Skenderi et al., **J. Forecasting 2024**｜10.1002/for.3104（**V**） | Google Trends 外生訊號 → **1.5% WAPE** | 比 KOL 貼文更接近需求的訊號，淨貢獻只有 1.5% |
| 大數據前導指標的經典翻車 | Lazer, Kennedy, King, Vespignani, **Science 2014**｜10.1126/science.1248506（**V** DOI；細節 **U**） | Google Flu Trends 連年高估（一度約 2 倍），而一個**只用上週數字的 recency heuristic 就贏了它** | 平台訊號會因平台自身行為改變而失效——**我們的語料組成漂移是同一類問題** |
| nowcasting ≠ forecasting | Choi & Varian, **Economic Record 2012**｜10.1111/j.1475-4932.2012.00809.x（**V** DOI） | 「**predicting the present**」：改善的是**當期**估計，不是未來期 | 名字就講了：搜尋量能講「現在」，不能講「未來」 |
| **最強的正面證據——但不可信** | Rudna, Rudniy & Park,「Forecasting Fashion Sales With Social Media Signals: Insights From Amazon, Twitter, and Google Trends」**Journal of Forecasting 2026**｜10.1002/for.70204（**V** 摘要原文，**cites 0**） | 77 條時尚屬性週序列（Amazon Sales Rank × Twitter 貼文數 × Google Trends），4,620 個預測；「VECM attaining a **mean RMSE of 3.47 versus 91,034 for the univariate baseline (97.7% improvement)**」 | **INF：這個數字站不住。** ①對照組是「univariate baseline」，**不是 persistence 也不是 seasonal naive**；②同一個目標上 RMSE 3.47 vs 91,034 差了**四個數量級**，那不是「訊號很強」，那是**baseline 在非定態序列上爆掉**；③目標是 **Amazon Sales Rank**（序位 proxy，不是件數或金額）；④2026 年發表、**0 引用、未被複現**。→ 我們**不要引用它當正面證據**；如果評審引用它，上面四點就是回答 |
| 揭露／贊助比例 | Evans, Phua, Lim, Jun, *J. Interactive Advertising* 2017｜10.1080/15252019.2017.1366885（**U**） | 揭露語言會影響消費者是否辨識為廣告 | 「時尚 KOL 貼文有多少比例是贊助／送禮」「FTC 揭露合規率」**本輪查不到可信數字** → **不要在簡報上放百分比** |
| **唯一的 steelman** | Aral & Walker, **Science 2012**｜10.1126/science.1215842（**U**，子代理核書目） | 約 1,200 萬 FB 使用者的**隨機化田野實驗**：真實的影響力／易感性變異確實存在 | 影響力**不是零**；而且 2007–2012 的文獻早於 TikTok Shop／直播電商的短迴路。這一塊該標「**未被研究／開放問題**」，不是「不支持」 |
| **量過 influencer 訊號到底值多少的唯一一篇** | David, Bellot（Heuritech）, Le Corff, **HERMES**, arXiv:2202.03224（**V**，逐字讀 README 與摘要） | 10,000 條時尚趨勢序列，每條附「external weak signal representing **behaviours of influencers**」；**MASE 0.745 → 0.7132（−4.3%）**，1,000 條 −2.6%、**100 條 −1.1%** | **這是「KOL 有一點用」的最佳證據，也是「用處很小且需要巨大規模」的最佳證據。** 同一份數字同時支持與否決這個題目——這正是我們該在簡報上呈現的方式 |

**失效模式（付費促銷 → 訊號可能是落後的）**：結構上的論證是——品牌的買貨決策發生在上市前數個月，之後才付錢請 KOL 推它，所以 KOL 貼文內容是**品牌過去決策的下游**；把它當「需求」餵回推薦系統，等於把**品牌自己的舊決策**當需求證據餵回去，形成自我強化迴路。Leung et al. 2022「宣布新品的貼文效果更差」與這個圖像一致，但**沒有任何研究直接量過這個 lead/lag 方向**（我與子代理都沒找到）。→ **標 INF；簡報上講成「一個我們無法排除的風險」，不要講成「文獻證實」。**

**判定：不支持（強版），開放（弱版），但「值多少」已經有答案（很少）。**

- **強版（「KOL 領先、大眾跟隨」是趨勢形成的機制）：不支持。** 學術上是被質疑的假設（Watts & Dodds）、觀察性證據**不可識別**（Shalizi & Thomas）、擴散結構是**廣播而非 trickle**（Goel et al.）、經典時尚理論本身就主張**橫向擴散**（King, Blumer）、最接近的實證量的是**互動而非需求**（Leung et al.）。
- **弱版（演算法推薦時代是否出現了真實的短迴路 KOL→購買通道）：沒有被研究**，唯一指向它的論文（Rudna et al. 2026）數字不可信。
- **但「KOL 訊號當預測特徵值多少」已經有一個一手數字**：**4.3% MASE，需要 10,000 條序列**（HERMES，Heuritech 自己的論文與資料）。這個數字讓整場爭論變得可以結案：**不必爭「KOL 有沒有領先」，因為就算有，它值 4.3%，而且那 4.3% 要靠我們沒有的規模才拿得到。**

→ **對 ENGINE 02 的直接結論：不要把「KOL 領先」當立論基礎。** 我們要做的東西可以用「族群品味的可量測偏移」來立論，那個立論不需要 KOL 假設成立。

---

## 7. 給 coordinator 的建議（已排序）

排序依據是「證據強度 ÷ 成本」，不是「聽起來多厲害」。

### R1（**最高價值，純寫作，約 30 分鐘**）— 把「為什麼不做趨勢預測」寫成一張有外部證據的投影片

- **機制**：不需要任何程式。內容就是 §0(1) 的那張表——Heuritech（本題最該對標的廠商）自己公開的 MASE **−4.3% @10,000 條 → −2.6% @1,000 條 → −1.1% @100 條**，加上他們摘要裡「sporadic external signals」需要「a **global** recurrent neural network」的機制說明，再對上「我們有 **11** 條軸」。旁邊放 WGSN 自揭的「100,000+ social media posts monthly」「5+ million catwalk images spanning 28 years」「analyst-in-the-loop＋250+ experts」當規模對照。
- **需要的資料**：無（全部是 `github.com/etidav/HERMES` 的 raw README 與 arXiv:2202.03224 摘要，皆為公開內容）。
- **證偽計畫**：不適用（這是引用，不是我們的宣稱）。唯一要小心的是**不要把 HERMES 講成同儕審查證據**——它只有 arXiv 版、2 次引用、無 venue（**V**）。正確講法：「**這是廠商自己對自己最有利的公開數字，所以拿來當上界是安全的。**」
- **誠實評估**：**投影片宣稱，而且是本次調查最有價值的單品。** 它把「我們沒做趨勢預測」從一個缺口變成一個**有外部數字支撐的工程決定**，用的還是提案人最想對標的那家公司自己的數字。**如果只能做一件事，做這件。**

### R2（建議做，demo 功能）— 趨勢降級為「有上限、有歸因、有 provenance 的 β_d 偏移」；先做**歸因骨架**，訊號可後補

- **機制**：新檔 `engine02/element_trends.py`（`load_polyvore_dates` / `score_corpus` / `to_beta_offset`）；`engine02/contracts.py::FeedbackState` 新增 `trend_prior_delta: dict[str,float]`；`engine02/pipeline.py::_terms` 多讀一個 dict 並在 `per_unit` 加 `"trend_prior"` 鍵（約 5 行）；`engine02/panels.py::_need_labels` 與 `engine02/explain.py::template_reasons` 各加一行標籤。`cap = KanseiTable.step_size = 0.25`。詳細對照表見 §4.3。
- **需要的資料**：**無**。`trend_prior_delta={}` 時**完全 no-op**，所有既有數字不受影響（與 §3.16 的 no-op 設計同一個理由）。
- **證偽計畫**：三條單元測試即可交付——①空 dict 時排序與分數**逐位元相同**；②有值時 `contributions` 加總仍等於 `score`、`need_shares` 加總仍等於該項貢獻；③偏移被 clip 在 ±0.25，且一次 `adjust(d,±1)` 一定翻得動它。
- **誠實評估**：**demo 功能。** 它的價值不是「趨勢有效」，而是「我們把一個**量過是負的**東西（§3.15）改造成一個**可歸因、可被使用者覆蓋、成本為零**的機制」。這是評審會欣賞的工程判斷，而且不需要任何未經驗證的宣稱。

### R3（建議做，零成本，純文件）— 在 `docs/engine02-design.md` §3.15 補一句邊界說明

- **機制**：註明該 28 組負結果的評估 ground truth 是**屬性 metadata**，因此**任何與它正交的新項都只會扣分**（`scripts/eval_trends.py` 的 docstring 已自承這一點）。所以該結論對「**關鍵字項**」成立、對「**任何趨勢機制**」**不成立**；要驗趨勢必須用帶時間軸的 ground truth（§5.2）。
- **誠實評估**：這是**防守**。如果評審或別組拿 §3.15 說「你們自己證明趨勢沒用」，我們要能一句話說清楚那個實驗量的是什麼、不能量什麼。

### R4（建議做，零成本，純文件）— 把 Pinterest 條款原文補進既有 docstring

- **機制**：`engine02/trends.py` 模組 docstring 目前寫「PRD ref [108]」，建議補上 2026-09-18 核到的逐字原文：「Except for campaign analytics information … **you may not store any information accessed through any Pinterest Materials including the API.**」
- **誠實評估**：**demo 功能（稽核性）**。我們的 `ephemeral=True` ＋ `save()` 丟 `PermissionError` 是「把規範寫成程式」的好例子，值得有原文撐著。

### R5（時間夠才做，投影片宣稱，預期為負）— Polyvore 帶日期的要素流行度 backtest

- **機制**：§5.1 的完整協定（MASE vs persistence／seasonal naive／drift／GeoStyle 參數曲線；**逐軸報告**；三個對照組：打散時間／隨機描述詞／固定組成）。工具全部現成：`engine.design_matrix`、`concepts.py::_random_descriptors`、`eval/metrics.py::paired_permutation_test`／`bootstrap_ci`。
- **需要的資料**：`xthan/polyvore-dataset` 的 `*_no_dup.json`（Apache-2.0，直接抓）＋既有 `polyvore_big` 的圖與 embedding cache。**先跑 §5.1 的前置閘門**（`date` 實際格式是否可解析、逐月覆蓋率、實際日期區間），**閘門沒過就整條不做**。
- **證偽計畫**：它本身就是。**預期結果是打不贏 seasonal naive**，而這個負結果在 HERMES 的 −1.1% @100 條之下**是事前就該預期的**。
- **誠實評估**：**投影片宣稱，而且很可能是負向的。** 最有價值的產出是那句話：「我們**量過了**：在我們拿得到的資料上，要素層級的社群趨勢**贏不過季節性 naive**——這和 Heuritech 自己在 100 條序列上的 −1.1% 一致。所以我們把趨勢做成上限 0.25 的偏移，而不是預測器。」**做這件事的唯一理由是我們願意報告負結果**（本專案已有 §3.15 的先例）。

### R6（可選，很可能是 null）— Polyvore `likes` 的推薦端配對測試

- **機制**：§5.2 的黑客松版（用 `likes`/`views` 當帶日期的相關性，與屬性 metadata 正交，所以不會落入 §5.0 的陷阱）。
- **誠實評估**：§5.2 的樣本量推算（需要約 **3,800** 個配對查詢才能偵測 +0.02 NDCG@5，約 60× §3.15 的規模）說明我們**大概打不出顯著的正向**。只在有時間、且願意報告 null 的情況下做。

---

## 8. 不建議做／做不到（附具體阻礙）

| 項目 | 具體阻礙 |
|---|---|
| **接 Instagram Graph API 抓 hashtag 影像** | ①需 Business/Creator＋連 FB 粉絲頁；②**強制 App Review（"Instagram Public Content Access"）**，黑客松時程內拿不到；③逐字限制「a maximum of **30 unique hashtags within a 7 day period**」；④Meta Platform Terms §3.d 要求「delete all Platform Data as quickly as possible when you no longer need to retain」→ 建**帶日期的影像資料集**本身不合法 |
| **接 TikTok Research API** | 資格限美／EEA／英／加／瑞的**學術機構**（博士生需指導教授背書函）；黑客松團隊**不在任何合格類別**；非學術路徑只能在 TikTok 的 Virtual Compute Environment 內，資料不出境 |
| **接 X/Twitter API** | 已改用量計價（Post 讀取 $0.005/resource，月上限 300 萬）；**找不到任何學術／研究方案**；開發者條款頁 **HTTP 402**，儲存／再散布條款**無法核實** → 條款沒核過就不接 |
| **儲存 Pinterest 任何資料** | 開發者規範逐字禁止（見 R4）。既有 `from_live_fetch` 的 `ephemeral` 設計保留 |
| **做要素層級的趨勢預測器（＝本題的原始假設）** | **機制性不可行，不只是資料不夠**：Heuritech 自己的 HERMES 顯示 influencer 訊號要靠「a **global** recurrent neural network」跨數千條序列 pool 才萃取得出來，效果 **−4.3% @10,000 條 → −2.6% @1,000 條 → −1.1% @100 條**（**V**，raw README）。**我們只有 11 條正規軸。** 再加上域偏移與單位不可辨識（§4.2 ①②③） |
| **把 HERMES 的 CSV 放進 git，或當主線結果的基礎** | `github.com/etidav/HERMES` **GitHub API 回報 `license: None`——repo 沒有宣告任何授權**（**V**）。可以讀、可以引用它 README 的公開數字，**不能再散布**。而且它**沒有圖**，本來就驗不了我們的機制 |
| **引用 EDITED／Launchmetrics 的數字當「趨勢預測有效」** | **類別錯誤。** EDITED 的 Hollister「$500k+」、PVH「+27%」量的是**定價與品項最佳化**，訊號來源是**電商上架資料、不是社群**；Launchmetrics MIV 是把媒體曝光**折算成金額**的**回顧型**指標，不是需求 |
| **引用「Fashion++ 是 Amazon 的論文」** | 事實錯誤：`arXiv:1904.09261`（ICCV 2019）是 **Facebook AI Research／UT Austin**（Hsiao, Katsman, Wu, Parikh, Grauman） |
| **引用 Shein 的 "LATR" 模型** | 本輪完全查不到這個名稱的任何公開來源 → **無法核實，可能不是公開名稱**。Shein 唯一可引用的是「約 3 天到首批、約 100 件小批試單」（**U**，Wikipedia） |
| **引用 Heuritech 的「90% accuracy／24 months」** | 行銷頁數字，**沒有方法、沒有對照組、沒有信賴區間**（**U**）。要引 Heuritech 就引他們自己論文的 **4.3% MASE**（**V**） |
| **把趨勢做成關鍵字 BM25 項** | **已量測：28 組全部顯著變差，−0.16～−0.38 NDCG@5，p≈1e-4**（§3.15）。不要再碰 |
| **把趨勢寫進 `KanseiTable.K`** | K[n,d] 的語意是「文獻說這個需求由這個要素服務」，混入族群分布後**再也分不開**，`kansei_v1_literature.json` 的可稽核性消失，且 T6 的 γ 結論會被污染 |
| **把趨勢寫進 `preference.py::prior_mean`** | 那是「對**這個使用者**的先驗」；塞入族群趨勢等於假設「這個使用者本來就偏好流行」，會讓使用者回饋需要更多證據才翻得動 |
| **宣稱「KOL 領先、我們抓得到」** | §6：強版不被支持（Watts & Dodds、Goel et al.、Shalizi & Thomas、King/Blumer、Leung et al.），弱版未被研究，唯一正面論文（Rudna et al. 2026）數字不可信（四個數量級的 RMSE 差＝baseline 爆掉） |
| **宣稱任何「領先 N 個月」** | 文獻上沒有人公開報過可信估計（§4.4）。只能說「我們不知道」 |
| **用 StreetStyle-27K** | 官方站 `streetstyle.cs.cornell.edu` **TLS 憑證不符、實質無法存取**（2026-09-18 實測）；且釋出物理解上是註記＋Instagram URL，URL 多已失效 |
| **用 GeoStyle 的資料重跑** | CC BY 4.0 沒問題，但釋出物是 Barcelona Flickr 的**屬性預測 pickle＋模型**，**沒有原圖** → 無法用我們的 `design_scores` 打分 |
| **用 H&M Kaggle** | 競賽授權**未解決**（規則頁 JS 渲染抓不到；競賽資料集常限競賽內使用）。**授權確認前不要用** |
| **用 VISUELLE 2.0 當主線** | 要填表、**官方頁無明確授權** → 不可散布、不可進 git；資料本身很好，但只適合當「文獻對照」，不適合當我們的可重現主線 |
| **在黑客松內做出推薦端的統計顯著正向宣稱** | §5.2 的樣本量推算：需要約 **3,800 個配對查詢**（約 60× §3.15 的規模）才能偵測到合理量級的 +0.02 NDCG@5 |
| **引用 Reddit 的任何數字** | 本輪 reddit.com／redditinc.com／support.reddithelp.com **全部 403／抓不到**，2026 的 rate limit、商業條款、Pushshift 現狀**全部無法核實** |
| **引用「X% 的時尚 KOL 貼文是贊助」** | 本輪查不到可信一手數字（WebSearch 配額用盡；此類數字只在產業調查報告裡）。**不要放百分比** |
