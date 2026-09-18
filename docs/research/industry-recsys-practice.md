# 業界推薦／搜尋實作對照：ENGINE 02 的缺口分析

> 調查日期：2026-09-18｜分支 `engine02-research`｜本檔是**唯一新增檔案**，沒有修改任何既有檔案或程式。
> 全部建議都以 `檔案:函式` ＋「加什麼／改什麼」的形式寫，**沒有實作**。
>
> **本輪的方法限制（先講清楚）**
> - 本 session 的 WebSearch 配額在開工時就已用盡（200/200），所以本輪的一手來源管道是
>   **arXiv API（`export.arxiv.org/api/query`）＋ 對特定 URL 的 WebFetch**。
> - 因此「本輪沒找到 X 公司的論文」**只代表 arXiv 全文欄位掃描沒命中**，不代表不存在。凡屬這種情況一律寫成
>   「本輪未找到一手來源」而不是「該公司沒有做」。
> - 標記：**V** = 已實際讀到 arXiv 摘要／論文頁／該公司頁面；**U** = 只有二手或摘要層級；
>   **推論** = 我從既有資料推出來的，不是任何來源寫的。
> - 既有文件已經涵蓋的部分**不重做**：`docs/research/industry-fashion-brands.md`（聚陽客戶盤點、
>   dense 嵌入／混合檢索／屬性抽取／搭配相容／對話式助理／解釋／critiquing／生成圖／需求回饋／Kansei 十張證據表）、
>   `engine02-method-inventory.md`、`recsys-{preference,composed,slate,ltr}.md`、`external-benchmarks.md`、
>   `engine02-completeness.md`、`engine02-design.md` §0/§2。本檔只補**那些文件沒碰的題目**：
>   尺碼合身與退貨、session／序列式推薦、新品冷啟動、商業規則與商品企劃約束、價格折扣、
>   疲勞控制、以圖搜圖、趨勢預測管線、多目標排序、真人造型師在環、以及**製造端（OEM）的上游訊號**。

---

## 能力總表

| 能力 | 誰在用（出處） | 我們有沒有 | demo 值不值得做 |
|---|---|---|---|
| 硬條件過濾＋放寬階梯 | Taobao TaoSR-AGRL 的 rule-aware reward shaping（[arXiv 2510.08048](https://arxiv.org/abs/2510.08048), WWW 2026 Industry, V） | ✅ 有（`constraints.py`） | 已有，繼續講 |
| 混合檢索（BM25＋dense＋RRF） | 時尚業無明確公開先例（既有文件 b2 已查證）；通用 IR 做法 | ✅ 有 | 已有 |
| 加法式 reranker，分數分解＝解釋 | **學界有、產業未見部署**：GAM-LTR（[arXiv 2005.02553](https://arxiv.org/abs/2005.02553), V）、Neural Additive Models（[arXiv 2004.13912](https://arxiv.org/abs/2004.13912), NeurIPS 2021 spotlight, V） | ✅ 有 | **這是差異化的核心，一定要講** |
| 最小充分集合／反事實理由 | 學界 15+ 篇（CountER [arXiv 2108.10539](https://arxiv.org/abs/2108.10539) CIKM 2021 等），**本輪掃描到的全部沒有產業部署** | ✅ 有，而且量過忠實度 | **要講，且要講「我們驗過」** |
| 搭配相容／complete-the-look | Alibaba POG、Pinterest CTL/STL、Amazon CVPR 2020、Zalando AFRA、Levi's（既有文件 b4） | ✅ 有（NPMI → OutfitTransformer） | 已有，最成熟的一塊 |
| 清單多樣化（DPP/MMR） | Myntra homepage contextual bandit ＋ diversity（[arXiv 2309.14046](https://arxiv.org/abs/2309.14046), RecSys'23 fashionXrecsys, V） | ✅ 有（`diversify.py`） | 已有 |
| 從回饋學偏好（同 session） | Zalando 助理 thumbs／修正、Stitch Fix Style Shuffle（既有文件 b7/b9） | ✅ 有（Bayes pairwise＋shrinkage） | 已有 |
| 組合式批評檢索 | Amazon FashionVLP（CVPR 2022，既有文件 b7） | ✅ 有（`composed.py`） | 已有 |
| 屬性補值＋來源標示 | Amazon OpenTag、Myntra progressive extraction（既有文件 b3）；PAE 明說用途是 **trend report 與 assortment planning**（[arXiv 2405.17533](https://arxiv.org/abs/2405.17533), V） | ✅ 有（`attribute_fill.py`） | 已有，但**敘事可以改成「企劃輸入」**（見 §3） |
| **曝光疲勞／隱性負回饋（看過沒點就降權）** | 業界標準的 impression discounting；最接近的公開時尚案例是 Zalando two-stage session re-ranking（[arXiv 1908.08284](https://arxiv.org/abs/1908.08284), recsysXfashion'19, V）與 Long-Term Embeddings（[arXiv 2604.08181](https://arxiv.org/abs/2604.08181), Zalando, V） | ❌ **沒有**（只有「被否決」與「永久排除」，沒有「看過但沒選」） | ✅ **值得，建議 #2** |
| **元素層級需求缺口（demand × supply）** | Amazon Product Opportunity Explorer（既有文件 b9）、Myntra style quotient（[arXiv 1806.11424](https://arxiv.org/abs/1806.11424), V）、KERN 元素層級趨勢（[arXiv 2005.03297](https://arxiv.org/abs/2005.03297), ICMR 2020, V） | ⚠️ 只有需求層級 `Sup(n)`（`panels.py::need_supply`） | ✅ **值得，建議 #1（對贊助商最重要）** |
| **以圖搜圖／上傳照片視覺檢索** | ASOS Style Match、Amazon StyleSnap、Pinterest Shop The Look（既有文件 b3/b4）、Flipkart Shopsy（[arXiv 2210.04560](https://arxiv.org/abs/2210.04560), V）、Myntra Buy Me That Look（[arXiv 2008.11638](https://arxiv.org/abs/2008.11638), V） | ⚠️ 只有 `concept_image_neighbors`（**display-only、不進排序**，且只吃 embedding 不吃檔案） | ✅ **值得，建議 #3** |
| 新品冷啟動 | Zalando Fashion DNA（[arXiv 1609.02489](https://arxiv.org/abs/1609.02489), KDD'16 workshop, V）、SizeNet（[arXiv 1905.11784](https://arxiv.org/abs/1905.11784), CVPRW 2019, V）都把 cold start 當**主要問題** | ✅ **結構上就沒有這個問題**（全 content-based，零協同項） | **要講，但要誠實**（見 §4） |
| 尺碼／合身推薦 | Zalando 一整條線：size&fit 深度學習系統（[arXiv 1907.09844](https://arxiv.org/abs/1907.09844), V）、SizeNet、SizeFlags（[arXiv 2106.03532](https://arxiv.org/abs/2106.03532), **KDD 2021**，14 國上線, V）、FitGAN（[arXiv 2206.11768](https://arxiv.org/abs/2206.11768), V）、ALiSNet（[arXiv 2304.07533](https://arxiv.org/abs/2304.07533), V）；PreSizE（[arXiv 2105.01564](https://arxiv.org/abs/2105.01564), SIGIR 2021, V） | ❌ 沒有 | ❌ **不建議**（無尺碼、無交易資料，見「不建議做」） |
| 退貨建模 | ASOS 退貨預測 GNN 資料集（[arXiv 2302.14096](https://arxiv.org/abs/2302.14096), FashionXRecSys 2022, F1 0.792, V）；Myntra elite-customer 退貨處理（[arXiv 2105.00325](https://arxiv.org/abs/2105.00325), V） | ❌ 沒有 | ❌ 不建議（無退貨標籤） |
| Session／序列式推薦（跨 session 歷史） | Zalando 1908.08284、Session-based Complementary Fashion Rec（[arXiv 1908.08327](https://arxiv.org/abs/1908.08327), RecSys'19 fashion workshop，**2,800 萬活躍客戶、線上 A/B 購買件數 +3.24%**, V）、Zalando LSTM dynamic customer model（[arXiv 1708.07347](https://arxiv.org/abs/1708.07347), V）、Zalando LTE 2026 | ⚠️ 有**同 session 內**的偏好學習，沒有跨 session | ❌ 不建議（無互動 log） |
| 價格／折扣敏感度、markdown | Zalando markdown pricing（[arXiv 2404.02996](https://arxiv.org/abs/2404.02996)，**明說已深植生產環境、數百萬商品、週利潤提升數百萬歐元**, V）、high-frequency pricing（[arXiv 2606.13741](https://arxiv.org/abs/2606.13741)，5M+ 商品、+6% 利潤, V）、Flipkart 折扣效度（[arXiv 2005.04612](https://arxiv.org/abs/2005.04612), V） | ❌ 沒有（商品庫 `price` 覆蓋率 **0.0**，見 `data/catalog/kagl/README.md`） | ❌ 不建議 |
| 多目標排序（相關性 vs GMV／毛利／永續） | Taobao SORT-Gen（[arXiv 2505.07197](https://arxiv.org/abs/2505.07197)，+8.10% GMV, V）、DCEO（[arXiv 2608.25635](https://arxiv.org/abs/2608.25635), V）、Kuaishou HarmonRank（[arXiv 2601.02955](https://arxiv.org/abs/2601.02955), V）、Hyper-local sustainable assortment planning（[arXiv 2007.13414](https://arxiv.org/abs/2007.13414)，營收 vs 環境影響的 Pareto front, V） | ❌ 沒有 | ❌ 不建議（無毛利／庫存／碳足跡欄位） |
| 庫存／機會成本進排序 | Zalando Stock Lifetime Value（[arXiv 2607.01905](https://arxiv.org/abs/2607.01905), V） | ❌ 沒有 | ❌ 不建議 |
| 趨勢預測管線 | KERN（ICMR 2020）、REAR（[arXiv 2105.03299](https://arxiv.org/abs/2105.03299), V）、GeoStyle（[arXiv 1908.11412](https://arxiv.org/abs/1908.11412), V）、Zalando Trend Spotter（既有文件 b9） | ⚠️ 量過了，**結論是不要進排序**（`engine02-design.md` §3.15） | 只做展示標籤（已決定） |
| 需求預測／商品企劃 | Zalando deep-learning forecasting（[arXiv 2305.14406](https://arxiv.org/abs/2305.14406), V）、Myntra newsvendor SKU 量（[arXiv 2007.02510](https://arxiv.org/abs/2007.02510), V）、Flipkart ARMDN（[arXiv 1803.03800](https://arxiv.org/abs/1803.03800), V） | ❌ 沒有（也不該有，這是 ERP 的事） | ❌ 不建議（見 §3 的替代做法） |
| 真人造型師在環 | Stitch Fix Algorithms Tour 明說「需要即興、社會規範知識與共感的任務屬於人類」；stylist 最後定稿並手寫穿搭建議（[algorithms-tour.stitchfix.com](https://algorithms-tour.stitchfix.com/), V） | ⚠️ 有「人可以改」的介面（`design_adjust_steps`、`excluded_values`），但沒有「造型師覆寫並留痕」的角色 | △ 低成本可做（見 §2） |
| 零售商真的上線的解釋 UI | Amazon Help Me Decide、eBay LLM-PKG 副標題、Zalando Trend Spotter 成因說明（既有文件 b6） | ✅ 有（模板句＋`contributions[]`＋`provenance`） | 已有，但**可以借用 eBay 的短標形式**（見 §2） |
| 風格／場合分類體系 | Myntra Attr2Style：低階屬性 → 風格／場合 caption，**在 Myntra 內部使用者 pilot 中**（[arXiv 2008.11662](https://arxiv.org/abs/2008.11662), IAAI 2021, V） | ✅ 有（`taxonomy.py` + `taxonomy_v1.json`） | 已有；Attr2Style 是我們 K 表方向最接近的產業案例 |
| Kansei（感性工學）用於服飾 | **本輪與既有文件都沒找到任何品牌的量產部署**；最近的是 ZOZO 印象語嵌入（研究）、Myntra Attr2Style（pilot） | ✅ 有（K 表 v1，32 篇文獻編碼） | **要講成「把學術方法產品化」，不要說是業界標準** |

---

## §1 誰做什麼（只補既有文件沒寫的部分）

既有 `industry-fashion-brands.md` 已經做完十張技術別證據表。這裡只補「該公司的**技術堆疊**在本輪 arXiv 掃描中新出現的東西」，
以及被點名但既有文件沒處理的公司。

### 1.1 公開記錄最厚的兩家：Zalando 與 Myntra

**Zalando** 是本題目裡公開技術記錄最完整的時尚公司，而且它的重心**不在我們做的地方**：

| 主題 | 論文 | 年 | 關鍵數字／狀態 | 是否 fashion-specific |
|---|---|---|---|---|
| 尺碼與合身 | size&fit 深度學習系統 [1907.09844](https://arxiv.org/abs/1907.09844)；SizeNet [1905.11784](https://arxiv.org/abs/1905.11784)（CVPRW'19）；SizeFlags [2106.03532](https://arxiv.org/abs/2106.03532)（KDD 2021）；FitGAN [2206.11768](https://arxiv.org/abs/2206.11768)；ALiSNet [2304.07533](https://arxiv.org/abs/2304.07533) | 2019–2023 | SizeFlags：貝式機率模型 ＋ 弱標註客戶資料 ＋ 專家回饋，**14 國上線、明確以「降低尺碼相關退貨」為目標** | **極度 fashion-specific**（服飾才有 S/M/L 與版型） |
| 冷啟動的內容表徵 | Fashion DNA [1609.02489](https://arxiv.org/abs/1609.02489)（KDD'16 workshop） | 2016 | 「僅憑商品資訊即可產生無偏購買機率，即使完全沒有銷售資料」 | fashion-specific（吃標籤＋商品圖） |
| 序列／session | two-stage session re-ranking [1908.08284](https://arxiv.org/abs/1908.08284)（recsysXfashion'19）；LSTM dynamic customer model [1708.07347](https://arxiv.org/abs/1708.07347)（10 萬購物者）；Long-Term Embeddings [2604.08181](https://arxiv.org/abs/2604.08181)（2026，線上 A/B 互動與財務指標雙升） | 2017–2026 | LTE 用「high-inertia contextual anchor」把長短期偏好接起來 | 半通用 |
| 價格／markdown／庫存 | markdown pricing [2404.02996](https://arxiv.org/abs/2404.02996)（**已深植生產環境，數百萬商品，週利潤 +數百萬歐元**）；high-frequency pricing [2606.13741](https://arxiv.org/abs/2606.13741)（5M+ 商品、+6% 利潤）；Stock Lifetime Value [2607.01905](https://arxiv.org/abs/2607.01905) | 2024–2026 | SLV：把「目前庫存到生命週期結束的預期利潤」聚合成一個可用來評估任何介入的指標 | fashion-specific（季節性強、固定庫存） |
| 需求預測 | Deep Learning based Forecasting: a case study from the online fashion industry [2305.14406](https://arxiv.org/abs/2305.14406) | 2023 | 明說時尚的特點是**固定庫存假設**，必須嚴格處理價格與需求的關係 | fashion-specific |

**啟示（推論）**：Zalando 公開的力氣幾乎全在「尺碼／退貨」「價格／庫存」「序列個人化」三塊，
而**不是**在「一句話 → 隱性需求 → 可解釋排序」。這對我們是好消息：我們沒踩到他們的正面。
但也要誠實承認——他們沒做我們這塊，多半是因為**他們有交易資料所以不需要**（推論）。

**Myntra** 是第二完整的，而且它的論文更貼近「商品企劃」：

- **Understanding Fashionability: What drives sales of a style?**（[1806.11424](https://arxiv.org/abs/1806.11424)，作者掛 Myntra, V）——
  推導出 **style quotient**：「代表顧客對一件時尚商品的**風格內容**的需求，與其商務因素（價格、折扣等）解耦」，
  明說用途是 **assortment planning**。**這是本次調查裡對聚陽最有價值的一篇**（見 §3）。
- **Attr2Style**（[2008.11662](https://arxiv.org/abs/2008.11662)，IAAI 2021, V）——低階屬性 → 風格／場合描述的 transfer learning，
  「A Proof Of Concept for our model is under pilot at Myntra」。這是我們 K 表（需求 → 設計要素）最接近的產業對照：
  方向一致（低階屬性 ↔ 抽象風格），但他們是**學出來的**、我們是**文獻編碼的**，而且他們只到 pilot。
- Diversify and Conquer（[2309.14046](https://arxiv.org/abs/2309.14046)，RecSys'23 fashionXrecsys, V）——首頁 widget 排序用 contextual bandit ＋ 多樣性約束。
- Buy Me That Look（[2008.11638](https://arxiv.org/abs/2008.11638), V）、Product Review Image Ranking（[2308.05390](https://arxiv.org/abs/2308.05390), V）、
  newsvendor SKU 量（[2007.02510](https://arxiv.org/abs/2007.02510), V）、倉配分派（[2007.05081](https://arxiv.org/abs/2007.05081), V）、elite customer 退貨（[2105.00325](https://arxiv.org/abs/2105.00325), V）。

### 1.2 其餘公司：公開記錄的厚度（誠實評分）

| 公司 | 本輪新增的一手發現 | 公開記錄厚度 |
|---|---|---|
| **ASOS** | 退貨預測圖資料集 [2302.14096](https://arxiv.org/abs/2302.14096)（GNN，F1 0.792，FashionXRecSys 2022 → Springer LNEE vol 981）；Product Characterisation towards Personalisation [1803.07679](https://arxiv.org/abs/1803.07679)（從非結構化資料學屬性做推薦）；CLTV embeddings [1703.02596](https://arxiv.org/abs/1703.02596)；Mannequin-to-Human 影片生成 [2510.16833](https://arxiv.org/abs/2510.16833) | **中**。有真論文，但公開的**排序／搜尋堆疊細節很薄**；Style Match 與 Styled for You 在既有文件只有 U 級來源 |
| **Farfetch** | 本輪 arXiv 掃描**沒有**新增（FashionCLIP、iFetch 已在既有文件） | **薄**。FashionCLIP 論文本身**未聲明線上部署**（既有文件已註記） |
| **Flipkart** | 視覺相似檢索 Shopsy [2210.04560](https://arxiv.org/abs/2210.04560)、ARMDN 需求預測 [1803.03800](https://arxiv.org/abs/1803.03800)、query performance prediction [1808.00239](https://arxiv.org/abs/1808.00239)、precision merchandising [2011.08575](https://arxiv.org/abs/2011.08575)、Hinglish 語音／code-mix 查詢翻譯數篇 | **中**，但多半不是 fashion-specific（語音搜尋、倉配、評論摘要） |
| **Rakuten** | 只找到 clickstream 轉換預測 [1907.00400](https://arxiv.org/abs/1907.00400)（fashion e-commerce, V） | **薄** |
| **Alibaba / Taobao** | TaoSR-AGRL [2510.08048](https://arxiv.org/abs/2510.08048)（**rule-aware reward shaping：把商業規則拆成 dense reward**，WWW 2026 Industry, V）、SORT-Gen list-level 多目標 [2505.07197](https://arxiv.org/abs/2505.07197)（+8.10% GMV）、Retrieval-GRPO [2511.13885](https://arxiv.org/abs/2511.13885) | **厚**，但重心在多目標 GMV 與生成式召回，不是可解釋性 |
| **H&M** | 本輪**沒有**找到 H&M 自己發表的推薦／搜尋論文或工程部落格。公開的只有 2022 Kaggle 競賽資料集（既有文件 U 級） | **很薄**。**簡報不要暗示 H&M 有公開堆疊** |
| **Shein** | 本輪**沒有**找到任何一手技術來源（既有文件的「小批量 100–200 件」也是 U 級、原頁 404） | **很薄**。數字不要引用 |
| **Uniqlo / Fast Retailing** | 本輪無新增。既有文件已有「每年 3,900 萬則回饋用 AI 分析後送商品部」「FY2024 26 國 110 萬則意見每週分享給相關部門」（官方頁, V） | **需求回饋閉環有官方一手來源；推薦／搜尋堆疊完全沒公開** |
| **Net-a-Porter / YOOX（YNAP）** | 本輪 cs.IR 掃描**零命中** | **很薄**。不要在簡報引用 |
| **Nordstrom** | 本輪 arXiv **零命中**；既有文件只有一則 app 改版報導（Marketing Dive, V） | **很薄** |
| **Rent the Runway** | 本輪 arXiv **零命中**。租衣業的技術題目（可重用資源的線上配置）有學術論文（[2512.06997](https://arxiv.org/abs/2512.06997)、[2010.03983](https://arxiv.org/abs/2010.03983), V）但**沒有掛 RtR** | **很薄**。只能說「租衣模式的核心是可重用庫存配置，但 RtR 自己沒公開」 |
| **Stitch Fix** | 沒有 arXiv 論文，但 Algorithms Tour（V）是本題目裡**最完整的公開閉環**：篩選→排序→人類造型師定稿→客戶逐件回饋→回饋同時改善「她」與「其他客戶」→庫存採購→以屬性當 gene 的新款開發→人類設計師審核 | **厚（部落格形式）**。是「真人在環」與「回饋→設計」的最佳引用 |
| **True Fit** | 本輪**沒有**找到一手技術發表（純商業供應商） | **很薄**。要講尺碼就引 Zalando，不要引 True Fit |

---

## §2 他們有、我們沒有的東西

每一列：**是什麼 → 證據 → 在兩輪評審 demo 內是否可行 → 最小可信版本**。

### 2.1 ❌ 尺碼／合身推薦與退貨建模

- **證據**：Zalando 五篇（見 §1.1），SizeFlags 是**貝式模型 ＋ 弱標註 ＋ 專家回饋、14 國上線**；
  ASOS 退貨 GNN F1 0.792（[2302.14096](https://arxiv.org/abs/2302.14096)）；PreSizE（SIGIR 2021，transformer 吃品牌／品類＋購買史，
  並以內容屬性處理 unseen item 的冷啟動；作者群為 eBay Research（**推論**，論文未明寫））。
- **在 demo 內？** **不可行**。
- **最小可信版本**：**沒有**。KAGL 沒有 size 欄位、沒有交易、沒有退貨標籤（見「不建議做」）。
  唯一誠實的做法是在 Q&A 準備一句：「尺碼與退貨是時尚推薦最大的產業題目（Zalando 為此發了五篇、SizeFlags 上線 14 國），
  但它需要 SKU 層級的購買與退貨紀錄；我們這輪用的是公開商品目錄，沒有這層資料，所以我們刻意不假裝有。」

### 2.2 ⚠️ Session／序列式推薦

- **證據**：Zalando 1908.08284（session attention 重排，線上 CTR 提升）、1908.08327（**2,800 萬活躍客戶、線上 A/B 購買件數 +3.24%**）、
  1708.07347（LSTM 客戶模型）、2604.08181（2026 LTE，長短期平衡）。
- **我們的位置**：我們的 Bayes pairwise 偏好學習（`preference.py`）**本質上就是一個 session 內的序列模型**，
  只是用「每輪的選擇」而不是「點擊序列」當輸入，而且是每輪重擬合而非增量。跨 session 的長期使用者向量我們沒有。
- **在 demo 內？** 跨 session **不可行**（沒有使用者歷史）；同 session 的部分**已經有了**。
- **最小可信版本**：不新增模型，改敘事——把 `preference.py` 講成「session-based 的可解釋版本：
  Zalando 用 attention 學 session 表徵，我們學的是**設計要素上的權重**，所以同一個 session 模型的輸出可以直接印在卡片上」。

### 2.3 ✅ 新品冷啟動

- **證據**：Fashion DNA（[1609.02489](https://arxiv.org/abs/1609.02489)）與 SizeNet（[1905.11784](https://arxiv.org/abs/1905.11784)）
  都把 cold start 當**首要問題**——Fashion DNA 的賣點就是「僅憑商品資訊即可產生購買機率，即使完全沒有銷售資料」。
- **我們的位置**：ENGINE 02 的所有排序項（dense、BM25、c(i,d)、compat、penalty）**都只吃商品自身的圖與文字**，
  沒有任何協同過濾或計數特徵。所以一件今天才上架、零點擊、零銷售的新款，**day 0 就能被正常排序與解釋**。
- **在 demo 內？** 已經是事實，不用實作。
- **最小可信版本**：加一個 30 秒的 demo 動作即可（把一件商品從索引裡拿掉重建 → 它照樣能排、理由照樣成立），
  但**誠實註記**：這是「我們沒有行為資料」的結果，不是我們選擇的架構優勢（見 §4.5）。

### 2.4 ❌ 商業規則與商品企劃約束（庫存、毛利、促銷、季節）

- **證據**：Taobao TaoSR-AGRL 的 **rule-aware reward shaping**「把相關性拆解成與商業規則對齊的 dense reward」；
  Zalando SLV 把庫存機會成本變成單一可比指標；Hyper-local sustainable assortment planning 給 merchandiser 一條
  「營收 vs 環境影響」的 Pareto front 讓人挑（[2007.13414](https://arxiv.org/abs/2007.13414)）。
- **在 demo 內？** **不可行**（我們沒有 price、stock、margin、carbon 任何一欄）。
- **最小可信版本（如果 coordinator 硬要做）**：**不要**捏造毛利欄位。可行的只有**介面層宣告**：
  在 `engine02/contracts.py::TermGroup` 加一個 `"business"` 群組並在 `engine02/config.py::ArmConfig` 加 `w_business: float = 0.0`，
  預設 0（＝完全 no-op，既有數字全不變），文件說明「商業規則是一個**加法項**，所以它一旦被打開，
  卡片上就會出現一行『商業規則 +0.3』，永遠藏不住」。這是誠實的架構承諾，不是假資料。
  ⚠️ 但這仍然會被問「你們沒測過」，所以我把它排在三個建議之外。

### 2.5 ❌ 價格／折扣敏感度

- **證據**：Zalando markdown pricing（生產環境、週利潤 +數百萬歐元）、high-frequency pricing（5M+ 商品、+6% 利潤）、
  Flipkart 用 SVM 量化折扣顯著性（[2005.04612](https://arxiv.org/abs/2005.04612)）。
- **在 demo 內？** 不可行。`data/catalog/kagl/README.md` 明寫 `"price": 0.0` 覆蓋率。
- **最小可信版本**：沒有。`engine02-completeness.md` §4 已把「價格全為 null」列為 P0，那是 coordinator 的資料題，不是方法題。

### 2.6 ✅ 個人化多樣性與**疲勞控制**

- **證據**：Myntra 2309.14046 把多樣性當首頁 bandit 的約束；Zalando 1908.08284 的 session 重排本身就在處理
  「原始推薦清單裡少數真正相關的商品要往上拉」。
- **我們的位置**：多樣性**有**（DPP θ=0.9，`diversify.py`，`recsys-slate.md` 量過）；
  **疲勞控制沒有**。`FeedbackState` 裡有 `rejected_item_ids`（明確否決 → penalty 項）與 `excluded_item_ids`（永久排除），
  以及 `choice_history[].shown_item_ids`（**已經記了但沒被排序用到**）。
  → 「第一輪出現過、使用者既沒選也沒否決」的商品，第二輪可以原位重播。這在一個**以兩輪為評分單位**的 demo 裡是明顯的弱點。
- **在 demo 內？** ✅ 非常可行，資料已經在 request 裡。
- **最小可信版本**：見**建議 #2**。

### 2.7 ⚠️ 以圖搜圖／上傳照片視覺檢索

- **證據**：Flipkart Shopsy 多任務視覺檢索（[2210.04560](https://arxiv.org/abs/2210.04560)）；
  Myntra Buy Me That Look 從模特兒照偵測單品再找相似（[2008.11638](https://arxiv.org/abs/2008.11638)）；
  Pinterest Shop The Look（KDD 2020，人工相關性 +160%、互動 +80%，既有文件 b4）；ASOS Style Match、Amazon StyleSnap（既有文件 b3）。
- **我們的位置**：`panels.py::concept_image_neighbors` 只做「給一個 embedding，回最近 k 件」，
  docstring 明寫 **display-only、刻意不過 reranker**；`api.py::concept_image_nearest` 只收 `list[float]`，不收圖檔。
  也就是說「使用者／客戶丟一張照片」這條路**今天走不通**。
- **在 demo 內？** ✅ 可行。`encoders.Encoder.encode_images` 已存在，圖片向量已快取。
- **最小可信版本**：見**建議 #3**。

### 2.8 ⚠️ 風格／場合分類體系

- **證據**：Myntra Attr2Style（IAAI 2021，Myntra 內部 pilot）明說顧客是「依風格資訊，或直白說，依場合（party／sports／casual wear）」買衣服。
- **我們的位置**：`taxonomy.py` ＋ `taxonomy_v1.json` 已有（`docs/research/taxonomy.md`）。**不是缺口。**
- 唯一可補的是敘事：Attr2Style 證明「場合／風格這層抽象是顧客真正的購買軸」，正好支持我們把 occasion 當硬條件、把 Kansei 當軟需求的分工。

### 2.9 ⚠️ 趨勢預測管線

- **證據**：KERN（ICMR 2020）做**細粒度時尚元素**的趨勢預測（不是關鍵字！）；REAR（[2105.03299](https://arxiv.org/abs/2105.03299)）加上元素間與客群間的關聯；
  GeoStyle（[1908.11412](https://arxiv.org/abs/1908.11412)）從街拍影像預測屬性趨勢；Zalando Trend Spotter（既有文件 b9）。
- **我們的位置**：我們量過趨勢**關鍵字**進排序，28 組設定全變差（−0.16～−0.38 NDCG@5，`engine02-design.md` §3.15），所以只當展示標籤。**這個決定是對的，不要翻案。**
- **但要注意方法差異（重要）**：KERN／REAR／GeoStyle 預測的是**元素層級的時間序列**，
  我們測的是**關鍵字進 BM25**。兩者不是同一件事；我們的負面結果**不能**用來否定元素層級趨勢。
  → 這正好接到**建議 #1**：元素層級的「需求份額」是我們真正該做的那個版本（只是做成靜態缺口盤，不做時間序列預測）。

### 2.10 ✅ Shop the look（已有）

`complete_look.py` ＋ OutfitTransformer 互補頭，`engine02-design.md` §3.14 已實測。不是缺口。

### 2.11 ❌ 多目標排序（相關性 vs 毛利 vs 永續）

見 2.4／2.5。證據厚（Taobao SORT-Gen +8.10% GMV、DCEO +0.36% GMV、Kuaishou HarmonRank +2.6% purchase），
但全部需要我們沒有的商業指標。**不建議**。

### 2.12 △ 真人造型師在環

- **證據**：Stitch Fix Algorithms Tour（V）是唯一把分工寫清楚的公開來源：機器做「篩掉客戶說要避開的屬性」與排序，
  人做「需要即興、社會規範知識、與客戶共感」的部分，最後 stylist 定稿並手寫穿搭建議。
- **我們的位置**：我們有「人可以改」的鉤子（`design_adjust_steps`、`excluded_values`、`required_values`），
  但沒有「**造型師／商品企劃人員覆寫排序，且覆寫本身留在解釋裡**」這個角色。
- **在 demo 內？** 低成本可做，但**價值中等**（評審是製造商，不是造型師）。
- **最小可信版本**：不改程式，只在 `panels.py::provenance` 的敘事裡補一句：
  我們的 `attr_source` 已經區分「資料集原值／模型補值／unknown」，加一個 `"human"` 值就能承載造型師校正，
  而且因為 reranker 是加法的，人工覆寫會以一個具名項出現在卡片上。**排在三個建議之外。**

### 2.13 ✅ 零售商真的上線的解釋 UI

- **證據**：Amazon Help Me Decide（說明「為什麼適合你」＋較便宜／較高階切換）、eBay LLM-PKG 的**5 字 rationale 當卡片副標題**（如 "Same Brand"）、
  Zalando Trend Spotter 的趨勢成因說明（全在既有文件 b6）。
- **我們的位置**：我們的解釋比他們**更強**（分數分解 ＋ 最小充分集合 ＋ 反事實 ＋ 事實檢查），但**呈現密度可能過高**。
- **最小可信版本（0 程式）**：借 eBay 的形式——卡片上先給一個**極短標籤**（≤6 字，直接取 `contributions` 裡貢獻最大的那一項的 `_element_phrase`），
  點開才展開完整分解。`panels.py::_element_phrase` 已經回傳短語 dict，前端直接用即可。這是前端工作，寫進建議給 coordinator 但不算我的三個。

---

## §3 對「服裝製造商」真正重要的是什麼

聚陽是替品牌做衣服的，不是賣衣服的。所以「消費者推薦系統」對它有價值的部分，是**能不能反推出上游的生產決策**。
既有文件 b9 已經確認三個一手案例（Fast Retailing 的回饋閉環、Stitch Fix Hybrid Designs、Walmart Trend-to-Product、Amazon Opportunity Explorer）。
這裡補**方法層面**的標準做法，以及我們能不能誠實地產出。

### 3.1 需求感測／商品企劃的標準做法，對照我們能不能做

| 標準做法 | 一手出處 | 我們能不能做 | 怎麼做（誠實版） |
|---|---|---|---|
| **把「風格需求」與「商務因素」解耦** | Myntra style quotient：「代表顧客對風格內容的需求，**與價格、折扣等商務因素解耦**」，明說用於 assortment planning（[1806.11424](https://arxiv.org/abs/1806.11424), V） | ✅ **可以，而且我們天生就是解耦的** | 我們根本沒有價格與促銷，所以 `β_d = Σ_n p(n)·K[n,d]` 這條需求訊號**本來就不含折扣污染**。這是把「沒有價格資料」這個弱點轉成方法論優勢的唯一誠實講法 |
| **元素層級（不是商品層級）的需求聚合** | KERN 做「fine-grained fashion element trends for specific user groups」（ICMR 2020, V）；REAR 加元素間關聯（V） | ✅ **可以** | `kansei.py::KanseiTable.beta` 已經給出每個查詢的 β_d；跨查詢聚合就是元素層級需求。見**建議 #1** |
| **需求高但供給不足的缺口** | Amazon Product Opportunity Explorer：找出「轉換率低於基準」的搜尋詞群＝未滿足需求（既有文件 b9, V） | ✅ **可以，這是我們最該做的一格** | 我們的版本不需要轉換率：需求＝查詢端的 β_d 聚合，供給＝目錄端 c(i,d) 的分布。見**建議 #1** |
| **從非結構化資料抽屬性，餵給趨勢報告與 assortment planning** | PAE 明說框架用途是 trend report 與 assortment planning（[2405.17533](https://arxiv.org/abs/2405.17533), V） | ✅ **已經有了，只是敘事錯位** | `attribute_fill.py` 目前被當成「讓硬條件不用放寬」的工具（§3.17：四條件查詢放寬率 92.3% → 3.8%）。對製造商應該改講成「**把客戶的雜亂商品資料整理成可企劃的屬性表，而且每格標來源**」 |
| **面料／結構的設計要素** | Walmart Trend-to-Product 生成指導供應商生產的 **tech pack**（既有文件 b9, V） | ⚠️ **半可以** | 我們的 15 個元素裡有 `matte_fabric`、`glossy_fabric`、`soft_knit`、`crisp_collar`、`structured_shoulders`、`tailored_fit`、`relaxed_fit` —— 這些是**面料手感與結構**的詞彙，不是純外觀詞彙。「元素 → 面料規格」的對應是**我的推論**，沒有來源支持，簡報要標明是提案 |
| **多目標 assortment（營收 vs 其他目標的 Pareto）** | Hyper-local sustainable assortment planning：多目標最佳化產出 Pareto front 讓 merchandiser 挑（[2007.13414](https://arxiv.org/abs/2007.13414), V） | ⚠️ 只能做**兩軸中的一軸** | 我們能給「需求缺口」軸；「毛利／碳足跡」軸沒有資料。可以把輸出設計成「缺口大小 vs 我們的供給覆蓋率」的散佈圖，形式上對齊但不假裝有商務軸 |
| **size curve（尺碼比例規劃）** | arXiv 對「size curve / size profile / pack allocation」的檢索**零命中**（V，我實際查了）——這題在營運研究與產業期刊，不在 arXiv。最接近的是 Myntra newsvendor 的 SKU 量預測（[2007.02510](https://arxiv.org/abs/2007.02510)，但摘要**沒有**提到尺碼） | ❌ **不能** | 需要尺碼層級的銷售。見「不建議做」 |
| **配色（colourway）規劃** | 同上，arXiv 零命中 | ⚠️ **能做退化版** | 我們有 `color` 欄位（覆蓋率 1.0）與 `bright_color`／`dark_tone` 兩個元素。可以做「**品類 × 顏色**的缺口格」：哪些 (top, Navy Blue) 這類格子在需求側有份量但目錄側件數少。這是建議 #1 的第二層切面 |
| **前置期（lead time）** | Walmart：6 個月 → 6–8 週（既有文件 b9, V） | ❌ **不能** | 我們沒有任何時間或生產資料。**不要碰** |
| **需求預測** | Zalando [2305.14406](https://arxiv.org/abs/2305.14406)、Flipkart ARMDN [1803.03800](https://arxiv.org/abs/1803.03800)、Myntra newsvendor（V） | ❌ **不能，也不該** | 需要歷史銷售時間序列。這是 ERP 的事；我們該提供的是**餵給預測模型的特徵**（元素層級需求份額），不是預測本身 |

### 3.2 一句話定位（建議寫進簡報）

> 我們不做需求預測，我們做**需求的結構化**。
> Myntra 證明「與價格解耦的風格需求量」對 assortment planning 有用（style quotient, 2018）；
> Amazon 用「搜尋多但轉換低」找未滿足需求（Opportunity Explorer）；
> Fast Retailing（聚陽客戶）每年把 3,900 萬則回饋用 AI 整理後送進商品部。
> 這三件事在**品牌端**都有了，在**製造端**都看不到。ENGINE 02 把一句話消費者需求拆到設計要素層級，
> 所以同一個引擎可以輸出兩種東西：給消費者的推薦卡片，和給聚陽業務／設計的「哪些設計要素的需求沒被現有供給滿足」。

---

## §4 我們真正領先或不尋常的地方（含反面）

### 4.1 ✅ 加法式 reranker，且分數分解**就是**解釋 —— 學界有、產業未見

- **學界有**：GAM-LTR（[2005.02553](https://arxiv.org/abs/2005.02553)，V；作者群多為 Google 的 TF-Ranking 團隊，
  **依作者列表推論**，論文頁未列 affiliation，comments 只寫 "10 pages"，我**不引用會議名**）。
  它的動機和我們一字不差：「在某些場景（例如法規或政策限制）**必須**有完全可理解的排序模型，
  因為事後解釋方法無法提供足夠準確的解釋」，並主張 GAM 是 intrinsically interpretable、可蒸餾成分段線性函數。
  Neural Additive Models（[2004.13912](https://arxiv.org/abs/2004.13912)，NeurIPS 2021 Spotlight, V）是同一家族。
- **產業未見**：既有文件 b6 的結論是「沒有找到任何時尚品牌公開加法式分數分解作為解釋」。
  本輪我再掃了 interpretable/additive ranking 的近期文獻，**沒有**找到任何回報真實部署的加法式排序器。
  業界上線的解釋是 **LLM 生成的自然語言**（Amazon Help Me Decide）或**短 rationale 標籤**（eBay LLM-PKG "Same Brand"）
  或 **attention 熱力圖**（Pinterest CTL、ZOZO AAM）。
- **可以說的話**：「業界的解釋是**模型之外**生成的；我們的解釋是**模型本身**。
  GAM-LTR 指出事後解釋在受規範場景不夠用——時尚業還沒有人把這條做到產品裡。」
- **反面（Q&A 會被打的點）**：加法式模型的**代價是表達力**。我們自己的 T10（`recsys-ltr.md`）就是在
  「維持可加總」的前提下學權重，這本身就是承認我們放棄了交互項。誠實答法：
  「我們用 NDCG 量過這個代價（T10），在我們的規模上學到的加法權重沒有輸給手調，
  但我們沒有和一個非加法的強 reranker 對比過——Qwen3-VL-Reranker 那次反而變差（§0），不足以當證據。」

### 4.2 ✅ 最小充分集合理由，而且**量過它成不成立** —— 這點最不尋常

- 反事實／最小充分解釋在學界很熱：CountER（[2108.10539](https://arxiv.org/abs/2108.10539)，CIKM 2021）做「最小的商品變動使推薦翻轉」，
  另外還有 GREASE、CERec、PRINCE 系列、序列式推薦的遺傳演算法版（[2508.03606](https://arxiv.org/abs/2508.03606)）等 15 篇以上（V，我掃了標題與摘要）。
  **本輪掃到的全部沒有回報真實部署**。
- 更值得講的是**評估**：我們的 T4 量到 PRD 原版「拿掉就掉出前 5」有 10–20% 的卡片完全沒有理由、
  只有 66–68% 的理由組合本身足以留在前 5；改成最小充分集合後 100% 有理由、100% 充分，隨機理由對照組只有 12–16%（`engine02-design.md` §0/§3.4）。
  **有隨機對照組的解釋忠實度量測，在產業公開資料裡我沒看到過。**
- 對照：eBay LLM-PKG 的線上 A/B **同時換了召回來源與理由文字**，所以「解釋本身有沒有效」無法歸因（既有文件 b6 已註記）。
  這是很好的 Q&A 彈藥：連 eBay 都沒把解釋的因果單獨驗出來。

### 4.3 ⚠️ Kansei 工程用於服飾 —— 不尋常，但要說成「學術方法產品化」

- 既有文件 b10 的結論已經很清楚：**沒有任何服飾品牌公開以正式 Kansei engineering（SD 法 → 設計要素權重表）用於量產企劃或線上檢索**。
- 本輪新增的最接近產業對照是 **Myntra Attr2Style**（IAAI 2021, V）：低階屬性 → 風格／場合，
  「Proof Of Concept ... under pilot at Myntra，僅開放部分內部使用者」。方向一致、成熟度更低、而且是**學出來的**不是**文獻編碼的**。
- **我們的不尋常之處其實是「可審計性」而不是「Kansei」本身**：K 表 v1 的 50 個非零格每格都有文獻代號
  （`docs/research/kansei-evidence.md`，32 篇），而且我們量過數值敏感度（§3.18）。
  一個「每格都能問『你憑什麼給 +0.5』」的權重表，比「我們用了感性工學」這句話有力得多。
- **反面**：K 表目前是**專家先驗**，沒有 PRD 承諾的人工 SD 評分與變異數 v[n,d]（`engine02-completeness.md` §4 列為 P1）。
  評審如果問「這是你們自己編的嗎」，正確答法是「是文獻編碼＋敏感度測試，人工校正還沒做，這是已知缺口」。

### 4.4 ✅ 事實檢查過的 LLM 改寫

我們預設用模板句，LLM 改寫要通過程式事實檢查才採用（`explain.py::verify_paraphrase`），而且有被退回的量測（§3.19b）。
Amazon Help Me Decide 與 eBay LLM-PKG 都是 LLM 直出，**本輪沒找到任何公開的零售端「解釋幻覺攔截率」數字**。
這一格是真的領先，而且成本很低。

### 4.5 ⚠️ 冷啟動免疫 —— 是事實，但不要說成設計功勞

Zalando 為了 cold start 專門做了 Fashion DNA（2016）與 SizeNet（2019）。我們的 pipeline 零協同項，所以新款 day 0 可排序可解釋。
**但這是因為我們沒有行為資料，不是因為我們選擇不用（推論但顯然）**。
誠實講法：「我們的架構對『新款』是免疫的，這在 OEM 場景剛好是對的性質——聚陽提給客戶的是還沒有任何銷售紀錄的新款。
但要說清楚：這同時意味著我們**用不到**行為資料，如果要接上客戶的實際銷售，架構要加一層。」

### 4.5b ⚠️ 我們**落後**的地方（誠實清單，Q&A 要準備）

| 落後項 | 對手 | 差距有多大 |
|---|---|---|
| 尺碼／退貨 | Zalando 五篇＋14 國上線 | **巨大**，而且是時尚推薦最有商業價值的單一題目 |
| 價格／markdown／庫存機會成本 | Zalando 三篇，明說已在生產環境、週利潤數百萬歐元 | **巨大** |
| 多目標 GMV 排序 | Taobao／Kuaishou 多篇線上 A/B | **巨大** |
| 跨 session 長期個人化 | Zalando LTE（2026 線上 A/B） | 大 |
| 線上 A/B 證據 | 幾乎每一家 | **我們一個都沒有**，全部是離線與模擬使用者（`engine02-completeness.md` P2 已註記模擬器是規則式） |
| 分級人工標註 | ESCI 有真人分級（我們已在上面測過，§3.20 B 級） | 我們**自己的**測試句還沒有人工分級（`engine02-completeness.md` P0） |

---

## §5 給 coordinator 的三個建議

三個都在 ~1 天內做得完（合計約 6–8 小時），都能用**手上已有的資料**驗證，都有 30 秒 demo。

---

### 🥇 建議 #1：元素層級的需求–供給缺口盤（`element_gap`）

**為什麼排第一**：這是唯一一個**只有製造商評審會在意、而且只有我們算得出來**的輸出。
`Sup(n)` 已經把一半做完了，缺的是另一半與正確的粒度。

**證據它有用**
- Amazon Product Opportunity Explorer：用「搜尋量高、轉換低」定位未滿足需求，官方稱據此推出的新品前三個月銷售潛力 2.5 倍（既有文件 b9, V）。
- Myntra style quotient：**與價格解耦的風格需求量**，明說用於 assortment planning（[1806.11424](https://arxiv.org/abs/1806.11424), V）。
- KERN / REAR：業界研究做的是**元素層級**的需求，不是商品層級（[2005.03297](https://arxiv.org/abs/2005.03297) ICMR 2020、[2105.03299](https://arxiv.org/abs/2105.03299), V）。
- PAE：屬性抽取框架的宣稱用途就是 trend report 與 assortment planning（[2405.17533](https://arxiv.org/abs/2405.17533), V）。

**最小實作（`檔案:函式`）**
1. `engine02/panels.py::element_gap(engine, requests, arm=DEFAULT_ARM, tau=0.5)` —— 新函式，仿 `need_supply` 的寫法：
   - **需求**：對一批 `Engine02Request`（或一批 `needs[]` 向量），用 `kansei.py::KanseiTable.beta` 取每個查詢的 β_d，
     取 `Demand[d] = mean_q |β_d(q)|`（用絕對值，因為 K 表有負號的抑制需求；**正負要分開回傳兩欄**，不要相加抵消）。
   - **供給**：`Supply[d] = (design_matrix(arm)[:, d] > tau).mean()`，直接重用 `Engine02.design_matrix`（已快取）。
   - **缺口**：`Gap[d] = Demand[d] * (1 - Supply[d])`，並回傳 `{element, demand, supply, gap, top_needs_driving}`；
     `top_needs_driving` 用 `kansei.py::KanseiTable.need_shares` 已有的邏輯，讓每個元素能回答「是哪個需求在拉它」。
2. `engine02/panels.py::category_color_gap(engine, requests, arm, tau)` —— 第二層切面：
   在 `(category, color)` 格上做同一件事（`catalog.py::Catalog.attr` 取欄位），輸出「需求有份量但件數少」的格子。
   這是 §3.1 裡「colourway 的退化版」。
3. `engine02/api.py` 新增 `GET /gap/elements` 與 `GET /gap/cells`，比照既有的 `needs_supply`（`api.py::needs_supply`）寫法。
4. `engine02/contracts.py` 加兩個 response model（`ElementGap`、`GapCell`），不動既有 model。
5. `scripts/eval_gap.py` —— 新腳本，只做下面的驗證。

**怎麼用現有資料驗證（可否證）**
- **主驗證：注入式留出測試（KAGL 44k）**。對每個元素 d 做一輪：把 `c(i,d) > τ` 的商品從商品庫遮掉（用 `need_supply` 已支援的 `mask` 參數同一套做法），
  重算 `element_gap`，檢查 d 是否排到缺口榜第一。指標：**被遮元素的缺口排名的 MRR**（15 個元素，隨機基線 MRR ≈ 0.24）。
- **負對照**：隨機遮掉同樣件數的商品，缺口榜**不應該**出現系統性移動。報 MRR 差與配對置換檢定 p 值（全組都這樣做，照 `recsys-*.md` 的規格）。
- **需求側的真實查詢分布**：ESCI apparel slice 的查詢（`engine02/external.py::is_apparel_query` 已有切片邏輯，
  `scripts/eval_external.py::cmd_esci` 已有讀檔器）可以當**真人寫的查詢分布**餵需求側。
  ⚠️ 但 ESCI 需要重抓 1.16 GB（`external-benchmarks.md` §4c 明寫），所以**先用手上的 685 句 KAGL 測試句 ＋ §3.18 的 60 句帶需求查詢**跑，
  ESCI 當加分項。
- **不要**聲稱缺口榜「預測了真實銷售」——我們沒有銷售資料，這條驗證做不到，簡報要明說。

**30 秒 demo**
> 「同一個引擎，換個聚合方向。」切到缺口頁：左邊是十個需求的需求強度，右邊是目錄的供給覆蓋率，中間一條缺口排序。
> 指最上面一格：「『怕看起來太用力』這個需求，在我們測的查詢裡很常出現，
> 而它要的低 logo、霧面、低對比——目錄裡同時滿足的只有 X%。這一格就是一個開發提案。」
> 然後點進 `(top, Navy Blue)` 的格子：「細到品類×顏色。」

**風險**：`Demand` 的分母是我們自己的測試句分布，不是真實市場。**必須**在畫面上標「需求側 = N 句測試查詢」，
否則評審會（合理地）認為我們在拿自己的樣本當市場。

---

### 🥈 建議 #2：曝光疲勞項（看過但沒選 → 降權），作為第八個加法項

**為什麼排第二**：成本最低（資料已經在 request 裡）、在**兩輪評分**的 demo 裡最顯眼、
而且因為是加法項，它會自動出現在解釋裡——完全符合我們的敘事。

**證據它有用**
- Zalando two-stage session re-ranking（[1908.08284](https://arxiv.org/abs/1908.08284)，recsysXfashion'19, V）的整個問題設定就是
  「用 session 資訊把原始推薦裡少數真正相關的往上拉」，並回報線上 CTR 提升。
- Session-based Complementary Fashion Recommendations（[1908.08327](https://arxiv.org/abs/1908.08327)，2,800 萬活躍客戶，
  線上 A/B **購買件數 +3.24%**, V）。
- Myntra Diversify and Conquer（[2309.14046](https://arxiv.org/abs/2309.14046), V）把「不要一直給同樣的東西」當首頁 bandit 的一級約束。
- 我們自己的證據：`FeedbackState.choice_history[].shown_item_ids` **已經存在但排序完全沒用到**，
  而 `w_penalty` 只針對 `rejected_item_ids`。「看過、沒否決、也沒選」是**隱性負回饋**，現在是空的。

**最小實作（`檔案:函式`）**
1. `engine02/config.py::ArmConfig` 加兩欄：`use_fatigue: bool = True`、`w_fatigue: float = 0.3`、`fatigue_decay: float = 0.5`。
   **同時新增一個 arm `full_zclip3_nofatigue`（`w_fatigue=0.0`）當對照組**，並保持 `DEFAULT_ARM` 不變，讓 coordinator 自己決定要不要換預設
   （沿用「不靜默改動已量測預設」的規則）。
2. `engine02/contracts.py::TermGroup` 的 Literal 加 `"fatigue"`。
3. `engine02/pipeline.py::_terms` 加一個 `Term`：
   `raw[j] = Σ_r decay^(round_now - r) · 1[item_j ∈ choice_history[r].shown_item_ids 且 ∉ chosen ∪ rejected]`，
   權重 `-w_fatigue`，並**照 `TrendClippedEngine02` 的 docstring 補 `clip=arm.z_clip`**
   （`engine02-completeness.md` 已指出 trend/penalty 漏了 z_clip，新項不要再犯同一個錯）。
4. `engine02/explain.py::template_reasons` 加一句模板：「這件上一輪出現過但你沒有選，所以往後排了」——
   **注意**：疲勞項是負貢獻，依 `reason_mode="sufficient"` 的定義它不會成為「理由」，
   所以要走 `RankedItem` 上一個獨立欄位（例如 `demotions[]`）或只在 `contributions[]` 裡顯示，不要混進 `reasons`。
5. `engine02/panels.py::round_diff` 已經在算輪間位移，加一欄 `demoted_by_fatigue` 即可。

**怎麼用現有資料驗證**
- 直接沿用 **T5／T7 的模擬使用者 harness**（`scripts/eval_preference.py`，100–200 個隱藏目標、4–5 輪、配對統計）。
  加兩個指標：
  - **novelty@5**：第 r 輪前五名中，前面所有輪都沒出現過的比例（疲勞項應該顯著提升）。
  - **hidden utility / success rate**：第 5 輪的隱藏效用（疲勞項**不應該**顯著下降——這是這個建議的主要風險）。
- 掃 `w_fatigue ∈ {0, 0.1, 0.3, 0.5, 1.0}` 與 `decay ∈ {0.3, 0.5, 0.8}`，報配對置換檢定 p 值與 95% bootstrap CI。
- 跨庫複核：KAGL 5k 與 44k 各跑一次（照 §3.5b 的做法），避免單一規模的假結論。
- **預期的失敗模式**：如果隱藏目標商品在第一輪就出現過但模擬使用者沒選（因為排名不夠前），疲勞項會把正確答案推走。
  這就是為什麼要掃 `w_fatigue` 並且**必須**同時報 novelty 與 utility 兩條線。

**30 秒 demo**
> 第一輪五張卡。使用者只說「再正式一點」，沒有否決任何一件。第二輪：
> 「注意第二輪的前五名不是第一輪的重播——這三件是新的。」
> 翻到其中一張被降位的卡：「它還在，分數分解裡多了一行『上一輪看過未選 −0.3』。
> 我們沒有偷偷把它藏起來，我們把降權的理由也寫出來。」

---

### 🥉 建議 #3：以圖搜圖 ＋ 上傳圖片的設計要素側寫

**為什麼排第三**：業界先例最強（幾乎每家都有以圖搜），實作幾乎免費（圖片向量已快取、encoder 已有 `encode_images`），
而且**加上「這張照片的設計要素側寫」之後，它就從一個通用功能變成 OEM 的功能**——
客戶丟一張競品照或 mood board，我們回「這張照片的設計要素是什麼、我們目錄裡最接近的是哪幾件」。

**證據它有用**
- Pinterest Shop The Look（KDD 2020）：物件偵測＋視覺嵌入檢索，**人工相關性累計 +160%、互動 +80%，已上線**（既有文件 b4, V）。
- Flipkart Shopsy 視覺相似檢索（[2210.04560](https://arxiv.org/abs/2210.04560)，多任務屬性分類＋triplet ranking, V）。
- Myntra Buy Me That Look（[2008.11638](https://arxiv.org/abs/2008.11638)，從模特兒照偵測單品再推相似, V）。
- ASOS Style Match（2018 全球上線, U）、Amazon StyleSnap（re:MARS 2019, V）、Target Photo Search（2026-08, V）、
  Kohl's 以圖搜商品（2026-07, V）——**後三個是聚陽客戶或其同級零售商**，這是最好的話術。
- 我們自己的證據：§3.16 的生成概念圖實驗已經證明「圖片向量融入查詢」在我們的 pipeline 上**有效**
  （NDCG@5 0.078 → 0.278，隨機概念圖對照組 −0.004，p=0.71），w=0.2 是量過的安全值。
  **以圖搜圖只是把同一條路的輸入從「生成的圖」換成「使用者上傳的圖」。**

**最小實作（`檔案:函式`）**
1. `engine02/api.py::visual_search` —— 新端點 `POST /visual-search`（`UploadFile`）：
   存暫存檔 → `engine02/encoders.py::Encoder.encode_images([path])` → 得到 L2 正規化向量。
2. 走**兩條路，都不要新模型**：
   - **檢索**：把向量塞進 `FeedbackState.concept_image_embedding`，並用 `arm=full_concept_image`（`concept_image_weight=0.2`，已存在的 arm），
     然後呼叫既有的 `Engine02.run`。**不要**新寫一條檢索路徑——重用已量測過的那條。
   - **側寫**：新函式 `engine02/concepts.py::profile_embedding(emb, arm)` —— 用**同一組反義詞 prompt**
     （`concepts.py` 已有的 antonym 打分邏輯）對這一個向量打 15 個元素的分數，回 `{element: z}`。
     這就是「這張照片的設計要素側寫」，而且和卡片上的 c(i,d) 是同一把尺。
3. `engine02/api.py::visual_search` 回 `{profile: {...}, items: [...]}`；`panels.py::build_view` 不用改。
4. ⚠️ **不要**改 `panels.py::concept_image_neighbors` 的 display-only 性質——它的 docstring 明寫那是刻意的設計
   （生成圖不能被呈現成「造成了推薦」）。上傳的**真實照片**與生成圖不同，走新端點，把界線留著。

**怎麼用現有資料驗證**
- **檢索側（KAGL 44k）**：image→image 留出測試。用 `external.py` 已有的 Marqo 協定改一個方向：
  拿 N=1,000 件商品的圖當 query（**從索引移除該件**），看同 `(subcategory, color)` 的商品是否進 top-10。
  報 R@1 / R@10 / MRR，對照組是純 BM25（應該遠低）與純 dense（上界）。腳本：`scripts/eval_visual_search.py`。
- **側寫側（已有標籤，零成本）**：我們有 §3.3b 的 **420 件盲標**與 §3.3c 的 397 件目視標註（`data/labels/`）。
  `profile_embedding` 對這些商品圖跑出的分數，AUROC 應該和既有的 c(i,d) **一模一樣**
  （因為用的是同一組 prompt 與同一個 encoder）——這是一個**一致性測試**，不是新結果，但它證明側寫的尺度是可信的。
  → 寫成 `tests/` 的一個回歸測試比寫成實驗更合適。
- **Polyvore**：用真實穿搭照當 query 圖（Polyvore 語料已建好），檢查回來的商品是否來自同一套穿搭。
  這是「客戶丟一張穿搭照」最接近的模擬。用既有的 `external.py::outfit_index`。
- **H&M caption 語料**：`tomytjandra/h-and-m-fashion-caption`（`scripts/eval_external.py` 已註冊）可以當**第三個語料**做同樣的 image→image，
  確認結論不是 KAGL 特有的。

**30 秒 demo**
> 拖一張照片進去（用一張**不在目錄裡**的服裝照，最好是機能運動服，貼近聚陽 52% 的品類）。
> 「系統先讀這張照片的設計要素：霧面 +1.2、貼身剪裁 +0.8、無明顯 logo +0.9。」
> 「然後用同一把尺去找目錄：這五件最接近，而且每張卡片上的理由**和剛剛那組要素是同一組數字**。」
> 收尾一句：「Target 和 Kohl's 今年都上線了照片搜尋。差別是他們回商品，我們回**規格**。」

---

## §6 不建議做（看起來很誘人，但缺的資料很具體）

| 想做的事 | 需要什麼資料 | 我們手上有什麼 | 結論 |
|---|---|---|---|
| **尺碼／合身推薦**（Zalando SizeFlags 那條線） | ①商品的尺碼表（S/M/L 與實際尺寸）②同一使用者的跨品牌購買尺碼史 ③退換貨原因碼 | KAGL `items.parquet` **沒有 size 欄位**；沒有任何使用者；Polyvore 是穿搭集合、無尺碼；ESCI 是 query-product 分級、無尺碼；H&M caption 子集只有圖＋caption | ❌ 三種資料全缺。**連最小版本都做不出來** |
| **退貨預測**（ASOS GNN） | 訂單層級的退貨標籤 ＋ 顧客–商品二部圖 | 全無 | ❌ |
| **價格／折扣敏感度、markdown 最佳化** | `price`、成本／毛利、促銷日曆、售出量 | `data/catalog/kagl/README.md` 明寫 `"price": 0.0` 覆蓋率；無成本、無促銷、無銷量 | ❌ 這是 `engine02-completeness.md` 的 P0 **資料**題，不要用方法去補 |
| **多目標排序（相關性 vs 毛利 vs 永續）** | 毛利率、庫存與機會成本（Zalando SLV 那種）、碳足跡／材質永續分級 | 全無 | ❌ 除了「宣告一個 w=0 的 business 項」（§2.4）之外沒有誠實版本 |
| **跨 session 序列式推薦**（Zalando LTE） | 使用者 ID ＋ 時間排序的點擊／加購／購買序列 | 只有同一 session 內的 `choice_history`（而且是模擬使用者產生的） | ❌ 想做要外部 log（H&M Kaggle 的 **transactions** 表或 Yoochoose），**我們只有 H&M 的 caption 子集，不是交易表** |
| **需求預測（時間序列）** | 至少兩季的 SKU × 週銷量 | 全無；KAGL 有 `season` 標籤但那是屬性不是時間 | ❌ 而且這是 ERP 的事，做了會被問「你們憑什麼比客戶的 ERP 準」 |
| **size curve（尺碼比例）** | 尺碼層級銷量 | 全無 | ❌ 附帶誠實註記：我查了 arXiv 的 "size curve / size profile / pack allocation"，**零命中**——這題不在 arXiv，在營運研究與產業期刊，所以我**無法**為它提供一手學術引用 |
| **趨勢關鍵字進排序** | — | 我們**已經量過了**，28 組設定全變差（−0.16～−0.38 NDCG@5，p≈1e-4，§3.15） | ❌ **已有反面證據，不要翻案**。元素層級的版本走建議 #1 |
| **虛擬試穿／生成穿搭情境照** | 人體影像（Google 虛擬試穿、Stitch Fix Vision、FitGAN 都要） | 無人體照；也沒有法遵與肖像授權路徑 | ❌ 而且離「檢索、排序、可驗證解釋」的題目太遠 |
| **真人分級標註驅動的 LTR 重訓** | 我們自己測試句的人工 0/1/2 分級（PRD §9.3 ＋ Cohen's κ） | **還沒做**（`engine02-completeness.md` P0，估 2–3 h，兩位組員） | △ **不是不建議，是不該由我建議**——這是既有文件已排 P0 的事，比我這三個建議更優先，但它是標註工作不是實作工作 |
| **造型師覆寫角色** | — | 資料夠（`attr_source` 加一個 `"human"` 值就行） | △ 可做但價值中等（評審是製造商而非零售商），排在三個建議之外（§2.12） |

---

## §7 本檔案的誠實限制

1. **本輪只有 arXiv API ＋ 定點 WebFetch**（WebSearch 配額開工即耗盡）。所以本檔對「工程部落格」的覆蓋
   遠不如既有 `industry-fashion-brands.md`——後者是在有 WebSearch 的那一輪做的。
   H&M、Shein、YNAP、Nordstrom、Rent the Runway、True Fit 的「很薄」評分，**應該理解為「arXiv 上很薄」**。
2. **affiliation 多數論文沒寫**。我只在 arXiv 摘要／comments 明確出現公司名時標公司（Zalando、Myntra、ASOS 是明確的）；
   PreSizE 歸 eBay 是**推論**，GAM-LTR 歸 Google 是**推論**，兩處都已標記。
3. **「元素 → 面料／結構規格」的對應是我的推論**，沒有來源。§3.1 已標。
4. 我**沒有**執行任何實驗、沒有跑伺服器、沒有改任何既有檔案。三個建議的所有數字預期都是待驗證的假設，
   §5 每一條都寫了會用什麼資料、什麼指標、什麼對照組去否證它。
