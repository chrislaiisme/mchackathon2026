# 製造商後台：需求分析、需求預測、版型與布料

> 調查日期 **2026-09-19**。**V** = 本次實際開啟該頁面／論文／PDF 並讀到所引文字；**U** = 只有摘要、404、付費牆或無法渲染。本文件**不改程式**，只寫在 `docs/research/`。
> 本輪 WebSearch 額度中途耗盡（200/200）→ **一手文件覆蓋率高、二手新聞與廠商官網覆蓋率低**，受影響處逐條標示。
> **前提（不重複，只延伸）**：`engine02-design.md` §3.22（缺口盤，可否證）、§3.15（趨勢關鍵字 28 組全敗）、§3.26（KOL 訊號／HERMES）、§3.34（外部訊號走側車）；`research/forecast-evaluation.md`（S1/S2/S3）、`social-trend-signals.md`、`industry-fashion-brands.md`。

---

## 0. 一頁結論

1. **製造商不做需求預測。它在別人擁有的預測底下，做一連串不可逆的承諾——最貴的那一個是布料承諾，而它發生在訂單存在之前。** 證據來自聚陽自己：**布料佔銷貨成本 58%**（副料 16%、人工 16%、製費 10%），毛利率 25%（2026-09 法說簡報 p.12，V）。布料數量抓錯 10%，約等於那張單四分之一的毛利。
2. **但聚陽的布料是「接單後才買」，而且不簽量**：「因本公司採**接單式生產**，原料之採購必須**接單後**才能依客戶要求之材質樣式進行採購，因此**並未與任何供應商簽訂大量之供貨契約**」（FY2025 年報 p.137，V）。所以真正的變數不是「要不要押布」，而是**訂單何時來、來多少、用料算得準不準**。
3. **聚陽已經自己在做需求預測，而且寫在年報裡**：「將其導入**『需求預測』**、產品開發、生產排程與品質管理」（FY2025 年報 p.7，V）；內部已有「**YY(用碼量)分析系統**」「用料系統」「風險預測平台」「PMS 用料分析系統」「**即時布料品質預測**」（p.130–131，V）。**在黑客松端出「AI 預測需求」，是在對方主場做對方已經有的東西**——`forecast-evaluation.md` 反方意見第 1 點，現在有了對方的白紙黑字。
4. **「版型／布料層級的需求預測」是一個乾淨的兩分法：企業規劃廠商完全不碰，趨勢廠商在賣、但沒有一家有同儕審查證據。** 規劃側六家（Blue Yonder／o9／RELEX／Nextail／Syrup／EDITED）把版型與布料當成「**人已經決定好的輸入**」，粒度停在 style/colour/size/store；**Heuritech 是全場最強的宣稱**——專門的製造商頁面、API 交付、「**2 years forecast**」的 fabrics 與 shapes 屬性序列，而且逐字寫著「so you can **pre-commit fabric, trims and hardware**」。**七家 Priority A 廠商同儕審查證據 = 0；First Insight 宣稱版型＋布料＋無歷史新品預測，而它自己 1,800 個 URL 的 sitemap 裡有 0 個命中 accuracy／validation**（§1.4）。
   ⚠️ **連帶的競爭警訊**：「賣趨勢情報給製造商」已經是紅海——Heuritech 有定價的製造商產品，EDITED 在 **2026-03** 推出 Manufacturer Intelligence package。**我們的差異化不能是客群。**
   而學術側**仍然是空的**：跨 OpenAlex／S2／arXiv 找不到任何一篇在預測版型或布料規格的需求，連顏色趨勢預測都幾乎只是業界刊物（§3.2）。**廠商在賣一個學術上零文獻支撐的東西——這件事本身就是簡報上的一張投影片。**
5. **學術界對「款式層級事前預測」是明確否定的**：Caro & Martínez-de-Albéniz（Springer 2015）逐字：「it is widely accepted that it is **impossible to forecast fashion at the item level a priori**… the only feasible approach is to **start selling the product and use early sales data**」（V）。製造商沒有早期銷售資料，也永遠不會比品牌更懂品牌的貨。
6. **所以：§3.22 的方向對，但要換層級與詞彙。** 不要走「預測下一季」（S1，已兩度否決）；要走**「把消費者講的話翻成布料與版型的規格語言，並誠實標示分母」**（S2/S3），加上兩個製造商側接點：**布料層級的向上聚合**（多款共用一塊布，聚合比拆款容易）與**用碼量／buy-to-cut 的產業詞彙**（QJE 2023 認證）。
7. **一個什麼都不預測、只誠實摘要需求的儀表板，是有效的答案——在這個案子裡還是唯一有證據支撐的答案。** 本輪沒有任何發現能推翻 §3.15／§3.26；改變的是「該做什麼」，不是「能不能預測」（§5）。
8. ⚠️ **我們今天對「布料」只有霧面／亮面／柔軟針織三軸，對「版型」只有肩線挺／寬鬆／合身／挺版領子四軸**，其中 `structured_shoulders` 與 `soft_knit` 在 §3.3b 的 420 件盲標中是 **0 正例**（`kansei_v1_literature.json`，15 軸，V）。**不能說我們在做「布料分析」——我們做的是「布料外觀感知」，離纖維成分、克重、織法、手感還有一整個學門的距離。這件事必須主動講。**

---

## 1. 誰真的在賣這個？廠商盤點

> §3.26 與 `social-trend-signals.md` §1 已盤過 Heuritech／WGSN／EDITED／Stylumia／Trendalytics。本節只補未盤過的七家、定價，以及最關鍵的一題：**有沒有人宣稱預測到「版型」或「布料」？**

### 1.1 答案是乾淨的兩分法：**規劃廠商不碰版型與布料，趨勢廠商才碰**

| 廠商 | 預測什麼 | 粒度（逐字） | 版型 | 布料 |
|---|---|---|---|---|
| **Blue Yonder** | 服飾的商品／品項／配貨／履約 | 「by **style, colour, size, store and channel**」 | ❌ | ❌ |
| **o9 Solutions** | 需求規劃、MFP、品項、配貨、size & pack | 「**millions of SKU-location combinations**」；size curve「aggregated at **style, class, store, or store cluster**」 | ❌ | ⚠️ **fabric 有出現，但是「何時承諾」不是「預測哪塊布」**：「Postpone commitment decisions to **procure fabric, lock color, size, and destination**」 |
| **RELEX** | 服飾**製造商**的產能、物料、生產預測 | 「**broad category levels**」「full product hierarchy」 | ❌ | ❌（尺碼粒度外包給夥伴 Sizeo） |
| **Nextail**／**Syrup**（⚠️ **2025-09-09 已被 Anaplan 併購**，`syrup.tech` 301 導向 anaplan.com） | 季中配貨、補貨、需求感測 | 「**SKU/PoS/day**」「**dynamic size curves**」／「**style, size, location** level」 | ❌（只有尺碼） | ❌ |
| **Woven Insights** | 評論爬取的回顧分析＋一個 demand forecasting 模組 | 預測頁只列 **brands, categories, colours and features**；定價 **US$85/月** | ⚠️ 只在**回顧**分析 | ⚠️ 同左 |
| **First Insight** | 新品成功率、定價、買量、配貨 | 「**SKU-level Value Scores**」（1–10）；**輸入是消費者測試問卷，不需銷售歷史** | ✅ | ✅ |
| **Heuritech** | 屬性採用率的前瞻預測 | 「weekly data points on each of our product attributes（prints, colors, **fabrics, shapes**）with… **2 years forecast**」，API 交付 | ✅ | ✅ **全場最強的宣稱** |
| **WGSN** | 趨勢投射 | 「We pinpoint **specific silhouettes, prints and materials**」 | ✅ | ✅ |
| **Trendalytics** | 搜尋量驅動的趨勢 | 「real search demand for specific **colors, silhouettes, fabrics**」 | ✅ | ⚠️ 屬性層屬於「觀察在市商品」的情報，**預測引擎是 Google 搜尋量** |
| **Stylumia** | 需求預測 | 「**silhouette, fabric weight**, occasion, price tier」 | ⚠️ | ⚠️ **只出現在部落格散文；四個產品頁零宣稱** |
| **EDITED** | 競品上架與定價情報 | Color Analysis／Pattern Analysis（花色 vs 素面） | ❌ | ❌ **9 個產品頁掃描 fabric/material/textile/silhouette/fit/cut 零命中** |

🔴 **這推翻了本文件初稿的假設。** 六家規劃廠商把版型與布料當成「**人已經決定好的輸入**」，不是預測目標；一問「哪塊布會賣」，整個企業規劃堆疊就沒有東西了。**但趨勢廠商那一側確實在賣這個。**

### 1.2 ⚠️ 競爭警訊：「賣趨勢情報給製造商」已經是紅海

- **Heuritech 有一個專門給製造商的頁面**（`heuritech.com/industries/manufacturer/`，V）：「Our **attribute-level forecasts** help you calibrate order volumes for each brand and market you supply.」以及**正中本案要害的一句**：「Sourcing decisions are locked months before final orders. Heuritech surfaces the material trends that will actually convert, so you can **pre-commit fabric, trims and hardware** with less risk of dead stock.」
- **EDITED 在 2026-03-26 推出「AI-powered Manufacturer Intelligence package」**（V）：「**Manufacturers** — What could you sell if you knew exactly what your buyers want?… **Giving you the same market data your buyers use**… Highlighting retailer assortment gaps to win new business.」客戶引言來自 **Shinsung Tongsang**。
- Trendalytics 與 Stylumia 也都把 manufacturer／exporter 列為明示客群（V）。**唯一的例外是 WGSN**——它的客群只有 Designers／Marketing／Buyers／Strategy，**零 manufacturer/supplier/ODM 命中**（V）。

→ **我們的差異化不能是「賣給製造商」這個客群，那已經被佔了。** 只能是**版型／布料的深度**，或是**沒有 POS 歷史時的新品情況**。

### 1.3 💡 本節最有用的一句引言，來自 RELEX 自己

RELEX 的服飾**製造商**頁（`relexsolutions.com/industries/cpg-manufacturing/apparel-and-footwear/`，V）逐字寫出了製造商的處境：

> 「**Apparel manufacturers receive firm orders just a few months ahead but must plan capacity, materials, and production 6 to 24 months out. Short product lifecycles keep long-term forecasts at broad category levels, forcing decisions based on incomplete signals.**」

**一家賣預測軟體的廠商，公開承認製造商的長期預測只能做到「broad category levels」。** 這句話同時支持 §2.1 的時程表、支持我們不做款式層級預測，而且是**對方陣營自己說的**。

### 1.4 證據等級：同儕審查 = 0／7

**七家 Priority A 廠商沒有任何一家有同儕審查證據。** 有方法描述的只有兩則：First Insight 的 Kohl's 案例描述了一個準對照設計（「tested vs. non-tested product **in the same sub-classes or categories**」，**但沒有 n、沒有期間、沒有統計檢定**），以及 M&S 的「**12% increase in sell-through** for products tested vs untested」。其餘（Nextail/Guess +5pp、Syrup/Faherty +30% sales、First Insight 的「80% 產品成功率改善」「10-15x ROI」）**全部沒有方法**。

**三個特別值得記的觀察**：
- ✅ **唯一有方法論衛生的是 Syrup**：它公開指名自己的評估指標是 **RMSSE**（「Compares forecast against a **naive baseline**, typically the 4 week average」）與 Weighted MAPE（V，Wayback）。**這是整個廠商圈唯一一個提到 naive 基線的**——和我們堅持報 MASE 的立場一致。但它**沒有公布任何對照這些指標的結果**。
- ❌ **Blue Yonder 服飾頁的「Actual Results」區塊實際渲染成 `Up to 0% reduction of out-of-stocks` 和 `$0M profit due to markdown avoidance`**（未觸發的動畫計數器）——**那一頁根本沒有真實的服飾數字**（V）。o9 的三個服飾案例**全部匿名且 KPI 欄位沒有任何數字**（V）。RELEX 服飾製造商頁有 7 個客戶 logo、**零個指標**（V）。
- 🔴 **First Insight 的獨立驗證：徹底的負面結果。** 跨 Crossref／OpenAlex／S2／arXiv／四個搜尋引擎／Wayback／以及它自己 1,800 個 URL 的 sitemap，**找不到任何同儕審查、預印本或獨立研究在測試它的 Value Score 準確度**。**它自己的 sitemap 有 0 個 URL 命中 accuracy／validation／proven／university／academic**（V）；12 份白皮書全是消費者意見調查。**它從未公布任何預測準確度指標**（無 MAPE、無命中率、無 AUC）；`/why-first-insight` 上唯一的數字是「98% of our customers would recommend First Insight」。分析師覆蓋是**定位而非準確度**（Gartner/Forrester 皆列為 "sample vendor"）。創辦人 Greg Petro 在 OpenAlex／S2 **沒有學術作者檔案**；他 2006 年參與的一篇未發表工作論文，**在 2010 年的同儕審查版（_J. of Research in Interactive Marketing_ 4(1):30–45, DOI 10.1108/17505931011033542）把他從作者名單移除**（V）。Forbes 上 2012–2026 的 489 篇專欄**全是 CEO 自己寫的**（Forbes contributor 不經編審），而 First Insight 自己轉載的 361 個 Forbes URL **現在全部 301 導回首頁——已經撤下**（V）。
  → **每一個流通在外的 First Insight 準確度數字，最終都指回 First Insight 自己或它 CEO 的專欄。**

### 1.5 定價：不是「全部不公開」，有三個硬數字

| 廠商 | 公開價格 | 出處 |
|---|---|---|
| 🔴 **EDITED** | **US$300,000 / 12 個月合約**，依啟用模組（Assortment／Pricing／Site Merchandising／Customer）×使用者×地區計價，「No refunds」 | **AWS Marketplace**（V） |
| 🔴 **Heuritech** | **Essential 起 12k€/年；Business 起 35k€/年**；Enterprise 需詢價 | **自家官網 `heuritech.com/pricing/`——唯一在自己網站標價的一家**（V） |
| 🔴 **WGSN**（企業版） | **£33,462.85 未稅 / £40,155.42 含稅，1 年（2026-07-31～2027-07-30）**，Coventry University → WGSN Ltd.，註記「the university has taken since 2009」 | **UK Find a Tender 公告 2026/S 000-080555**（V） |
| **Woven Insights** | **US$85/月**（Individual），10 天試用；Business 為 Custom | 官網定價頁（V） |
| First Insight／Trendalytics／Stylumia／Nextail／Blue Yonder／o9／RELEX | **完全查不到**（官網無定價頁；Vendr 條目存在但零數字或 404） | V（缺席） |

⚠️ **不要把 START by WGSN 的 US$109/12 個月當成 WGSN 的價格**——WGSN 自己的 FAQ 說兩者「serve distinct corporate tiers」（V）。
→ **意義**：①這是年約制企業銷售（12k€～US$300k/年），不是黑客松能「接一下 API」的東西；②**現在有了可引用的價格帶**，但簡報上仍不要出現「比 X 便宜」——我們沒有可比較的功能。

⚠️ **必須點破的引用陷阱**（`social-trend-signals.md` 已警告，這裡再釘一次）：**EDITED 的 PVH「sales +27%」、Hollister「$500k+ incremental revenue」量的是定價與品項結構最佳化，不是趨勢預測準確度**；Launchmetrics 的 MIV 量的是媒體曝光折算金額，**當需求訊號用是類別錯誤**。另補一個新的：**Stylumia 的部落格引用「24–57% 準確度提升」，那是 Fisher et al.（M&SOM，本文件 §3.2 的那一篇）的結果，不是 Stylumia 自己的結果**（V）。

---

## 2. 製造商那一側：做什麼決定、在什麼時程上

### 2.1 決定／時程表

| # | 製造商真正在做的決定 | 出貨前時程 | 誰拍板 | 當下有的資料 | 可逆？ | 證據 |
|---|---|---|---|---|---|---|
| 1 | **產能預留**：接下品牌的季度產能預訂、排線排月 | 6–12 個月 | 製造商（依品牌預測） | 品牌季預測（若有）、上季實績、線表 | 可，但傷關係 | Better Buying V |
| 2 | **紗／原纖維年度訂量**（有做的公司） | 6–9 個月 | 製造商或布廠 | 年度量估、分季 | 已簽約 | 儒鴻年報 V |
| 3 | **胚布／基布下訂（核心的那一注）** | 3–6 個月 | **製造商**（FOB／ODM） | 品牌預測＋自己對售罄的判斷；**此時還沒有 PO** | 幾乎不可逆 | QJE 2023 V |
| 4 | **布料平台化／材料收斂**：開發哪些布、能否跨款重用 | 12–24 個月 | 製造商↔品牌 | R&D pipeline、前代平台重用率 | 策略性、黏著 | 聚陽／儒鴻／Toray-UNIQLO V |
| 5 | **顏色／染缸釋出（postponement 的點）** | 4–10 週 | 製造商，依品牌指令 | 有早期售罄就用，否則用品牌色彩計畫 | 染下去不可逆 | postponement 文獻 V |
| 6 | **每張單的用布量（YY／用碼量、排版、buy-to-cut）** | PO 後 6–12 週 | 製造商 | Tech pack、排版、歷史耗用 | 只能當損耗回收 | QJE 2023／聚陽 YY 系統／Shein 算布系統 V |
| 7 | **排線／加班／外包** | 2–8 週 | 製造商 | 已確認 PO、線效率、SMV | 可，有成本 | QJE 2023／ILO V |
| 8 | **向品牌提補貨建議** | 季中 2–6 週 | 製造商**建議**，品牌決定 | 品牌售罄資料——**分享了才有** | — | 聚陽年報明文 V |

**承重結論**：第 3、4、6 項是 ODM 的錢所在，而**沒有一項是成衣需求預測**——它們都是**材料決定**。

### 2.2 風險歸屬：FOB／ODM 的布是製造商自己買的

**Cajal-Grossi, Macchiavello & Noguera (2023), _Quarterly Journal of Economics_ 138(4):2391–2450**, DOI [10.1093/qje/qjad026](https://doi.org/10.1093/qje/qjad026)（開放取用 `eprints.lse.ac.uk/120547/1/qjad026.pdf`，V 逐字讀）：

> 「Unlike **cut-make-trim systems (like those in China, Mexico, and Myanmar), in which buyers provide fabric**…, Bangladeshi exporters **source fabric and inputs before cutting**…」／「Fabric and labor… jointly account for **85%–90% of the variable costs**… **Fabric utilization choices are made order by order.**」

同篇給了產業自己的布料 KPI，**這就是儀表板該說的語言**：**buy-to-cut**（買進布÷裁切布）、**cut-to-ship**（裁切布÷出貨成衣）、**buy-to-ship**（兩者相乘，「a commonly used performance indicator. Lower values represent lower levels of waste.」）。而該文把 **order lead time** 定義為「the time elapsed between the **incoming shipment of fabric** and the outgoing shipment of garments」——**產業的碼表是從布到廠開始走，不是從 PO 開始。** 另：採購策略主要由**買方固定效果**解釋（是品牌的組織能力，不是商品特性）。

### 2.3 剩布誰吃？有實測數字

**Better Buying Institute, "Better Planning and Forecasting", Deep Dive 2020 Vol.1 No.1**（2018Q4 收資料，27 家受評品牌，**由供應商回報**；Wayback `web.archive.org/web/20241209121734id_/https://betterbuying.org/download/better-planning-and-forecasting/?wpdmdl=1320`，V）：

- **剩布的處理**：**買方付錢買下 29.1%**／**買方要求供應商「先留著」等未來訂單 66.3%**。→ **這就是「fabric liability」的實務：三分之二的情況由供應商墊資，押在一張可能不會來的未來訂單上。**
- **發生頻率**：「Fluctuations in actual purchase orders versus expected orders resulted in excess materials」平均 **30.0%** 的供應商碰到（各買方 5.3%–59.3%）。
- **預測提前量**：評分要求「forecasts **180 days or more in advance of production**」且「**accurate within 10% variance**」；實際**只有約 18% 的供應商拿到 ≥180 天**（最佳 44%），**約 23% 在下單前不到 60 天才拿到**。逐字：「Last-minute forecast and order changes (**45 to 60 days prior to production**) place suppliers and workers in especially precarious situations.」機制：「Suppliers can… **book needed materials that may take time to acquire**」。
- **ILO INWORK Issue Brief No.10 (2017)**（ILO/ETI 全球調查，**N=1,454 供應商、87 國**，V）：「only **17 per cent of suppliers**… considered their orders to have **enough lead time**」；供應商把工時暴衝歸因於買方行為（尖峰 66%、訂單變動 34%），只有 **9%** 歸因於自己的預測。

⚠️ **術語警告**：「fabric liability」「committed greige」「blanket fabric booking」是**業界用語，不是學術用語**。OpenAlex 全文檢索 `"fabric liability"` 只回 **2 筆**（一篇 Aberdeen 碩論、一篇 BRAC 實習報告）（V）。概念是真的，**但不要把它引到學術來源上**。

### 2.4 Zara／Inditex 的 postponement：學術版

**Caro, F. & Martínez-de-Albéniz, V. (2015), "Fast Fashion: Business Model Overview and Research Opportunities", in _Retail Supply Chain Management_, 2nd ed., Springer**（2014 preprint，`anderson.ucla.edu/faculty_pages/felipe.caro/papers/CaroMartinez-de-Albeniz2014_BookChapterFastFashion.pdf`，V 全文）：

- postponement 定義：「postpone all risky production decisions… QR often requires **holding raw materials ready to be dyed, cut and sewed after item-level demand forecasts have improved**.」
- **6 週的下限是有條件的**：「the total design-to-market time… can be reduced to a mere **6 weeks if the appropriate fabric is used**」→ **快時尚的快不是製造成就，是「材料已經先擺好」的成就。**
- **QR 的教科書取捨，就是布料下訂決定的數學**：早期訂量 `q₁` 成本 `c₁`、快反補單 `q₂` 成本 `c₂ ≥ c₁`，最適 `q₂(D) = (D−q₁)⁺`，`q₁` 解臨界分位 **`Pr[D ≥ q₁] = c₁/c₂`**；Fisher & Raman (1996) 加上 MOQ 與快反產能上限：「QR capacity constraints imply that **inflating early orders is desirable**」。
- 結構：H&M 基本款「**70% or more**」，Zara 從 90 年代末的 <20% 成長到「**40% or more**」；兩家每週約 **120 個新品導入**。
- **最關鍵的一句**：「it is widely accepted that it is **impossible to forecast fashion at the item level a priori**… The only feasible approach is to **start selling the product and use early sales data**.」

**Caro, Gallien et al. (2010), _Interfaces_ 40(1):71–84**, DOI [10.1287/inte.1090.0472](https://doi.org/10.1287/inte.1090.0472)（V）：對照組實驗，**控制後相對銷售影響平均 +4.1%**，2007 年約 **US$233m 增收**；門市商品生命週期「**five to six weeks**」。⚠️ **這是零售商的配貨最佳化，不是製造商的決定——時尚領域量得最嚴謹的 OR 成果，但站在圍籬的另一邊，不要借用它的 ROI。**

**胚布 50%**：Aftab, Yuanjian & Kabir (2017), _IJBM_ 12(7):115, DOI [10.5539/ijbm.v12n7p115](https://doi.org/10.5539/ijbm.v12n7p115)（V，低階開放期刊，只當引用線索）轉述「**Zara stores 50% of its fabrics in a 'grey' undyed state**… (Ferdows et al., 2004)」，以及 Comditel（Inditex 100% 子公司，管全集團胚布染整，對接 200+ 布料供應商）、「其餘 260 家供應商**沒有一家超過 4%**」（Ghemawat & Nueno, HBS 703-497）。→ **引用時必須寫「Ferdows et al. (2004) 所報、經 Aftab et al. (2017) 轉述」，原始出處未核（HBR 付費牆，U）。**
❌ **「Zara 留 50–60% 的季度不預先決定」找不到任何可及的一手或同儕審查來源 → 業界傳說，不要寫進簡報。** 可用替代：生命週期 5–6 週、每週約 120 新品、基本款 <20%→≥40%（皆 V）。

### 2.5 Shein：小批量是真的，「3 天」和「個位數 %」不是

sheingroup.com 的 PDF **不是 404**，是對非瀏覽器客戶端回 13 bytes 的殘根；經 Wayback CDX 全部取回（V）。

- ✅ **「100–200 件首批」是 Shein 自己的話，出現兩次**：2023 一頁白皮書「**New designs are created in small batches of 100-200 pieces to measure demand**」；2024 永續報告「**New styles are launched in small initial batches of 100 to 200 pieces**」（皆 V）。
- ⚠️ **「未售庫存個位數 %」被 Shein 自己收回**：只出現在 2023 一頁紙；2023 年報軟化為「consistently low unsold inventory rates」、2024 年報再軟化為「keeping unsold inventory levels low」，**兩份都沒有百分比**（V）→ 標 **U**，不要引。
- ❌ **「3 天從趨勢到商品」在 Shein 所有自家文件中都不存在**（已 grep；唯一的日數是付款條件 30 天）（V）→ 新聞／部落格出處。
- 🎯 **真正重要的：Shein 蓋的是「製造商側」的算布工具。** 2024 報告 "Planning with Precision"（V）：「**Traditionally, brands place orders and suppliers must then estimate and procure the volume of fabric**… prone to human error, resulting in **excess fabric or shortages**」→「in 2024, we rolled out an **automatic fabric calculation system**… **generating the predicted volume of each type of fabric required based on order quantities**… based on **historical material use by garment type**.」**這和聚陽的「YY(用碼量)分析系統」「PMS 用料分析系統」是同一個東西——產業裡最積極的兩家各自獨立蓋了同一個系統。**
- ❌ **Shein 模式不能移植到代工廠**：①Shein **擁有需求訊號**（自家 App 行為），代工廠看到的是 PO——那是品牌的**決定**，不是市場的**訊號**；②Shein **擁有 SKU 決定權**，可以 150 件就砍款，聚陽不能砍 Gap 的款；③Shein 的供應鏈**同地群聚且有現貨布市場**，而印尼／越南／柬埔寨的布廠 MOQ 是以千碼與染缸下限計的。Shein 自己的文字也確認方向：**供應商是平台需求訊號的消費端，不是擁有者。**
- ❌ **Shein 的學術文獻沒有價值**：OpenAlex 兩組查詢（N≈768、37）無任何頂級 OM／經濟期刊分析（V）。**只能引 Shein 自己的 PDF，並註明是未經稽核的自陳。**

### 2.6 Li & Fung：brief 的前提是錯的，而更正本身最有用

- 🔴 **沒有「Three-Year Plan 2020–2022」，那個計畫被取消了**：AR2019 CEO 致詞（V）「2019 marked the end of our current Three-Year Plan (2017–2019)… **While we did not meet our financial targets**」「**we will not announce a new three-year plan**」。❌ 「Creation Centre」一詞**不存在於**其年報與官網（V）。
- **著名的 40→21 週，baseline 是自己編的**：2017-03-30 Analyst Day slide 11（`lifung.com/wp-content/uploads/2018/02/pre170330a.pdf`，V）Pre-Order 17w／Pre-Production 13w／Production+Shipping 10w = 40w，**註腳逐字**「(1) Our estimate of industry average; **not representative of Li & Fung customers.**」；且官網今日自相矛盾（首頁 40→21 週，另一頁「slashing it 60% to **16 weeks**」，皆 V）。**唯一被實際量過的是 n = 2 件衣服**（AR2019，HKUST 碩士生研究，digital sampling「reduces the overall lead time by **45%**」）。
- **結局**：2020-05-27 下市；LF Logistics 2022 以 US$3.6bn EV 賣給 Maersk；員工 17,371（2017）→ 3,568（2025）；債券票面 4.375%（2019，投資等級）→ **8.375%**（2025-07-30）。**ESG Report 2025 全文 grep：「3D」= 0、「LFX」= 0、「UNIFi3D」= 0**（V）——數位故事已從自己的揭露裡消失。
- 💡 **敘事鉤子**：HBS case 301009（**2000 年**，*Li & Fung: Internet Issues*）談的已經是同一件事——中介商用數位平台逃離毛利壓縮。2017–2019 是**同一招的第二次**，隔十七年。**「數位轉型救不了一個被去中介化的中介商」，是一個要做 back office 的隊伍必須先講的教訓。**

### 2.7 聚陽自己說了什麼（本節最重要）

來源皆為 TWSE／MOPS 一手文件（V，全文抽取）。⚠️ `www.makalot.com.tw` 是純前端 SPA，對非 JS 抓取只回公司名，**要走 MOPS**。

**(a) 布料：接單後才買，不簽量**——見 §0 第 2 點的逐字引文；另「最近二年度**向前十大供應商進貨項目為布料**」（p.107）。風險管理靠**先議價**（「**提前議定採購價格**，避免成本上漲風險」p.104）與**股權而非合約**（「為降低**面料採購成本**…**轉投資面料布廠及面料貿易商**」p.125；法說 p.4「an addition of a **fabric mill in Vietnam through JV**… upgrade its **speed to market**」）。

**(b) 成本結構與規模（法說 p.10–12，本文件的經濟錨點）**：COGS **Fabrics 58% / Accessories 16% / Labor 16% / OH 10%**；對 ASP **Material 56% / Labor 12% / OH 7% / 毛利 25%**。FY2025 出貨 **17.5 百萬打（≈2.1 億件）**、ASP **US$62.8/打（≈US$5.2/件）**；2026E 產能 18.4 百萬打。
→ **這是一門一件五美元、一年兩億件的生意。** 以「抓住下一個流行」為賣點的儀表板和這個成本結構對不上；**任何能讓 58% 那一格少浪費 1% 的東西，都直接落在毛利上。**

**(c) 需求訊號：四家同業中唯一公開宣稱與客戶共用銷售資訊的**
> 「雙方之深入互動已提升到從**前端趨勢整合及產品概念發想，到最終銷售資訊之共用**…包含**提供客戶從市場銷售資訊之回饋，庫存、當季產品研發、下季產品及少量多款之生產模式等建議**」（p.95）；「以完整**全流程的服務(從前端的銷售預測、R&D 到後端的銷售補貨)**…**關注客戶銷售資訊，隨時提醒客戶補貨或轉換產品**」（p.103）；「**與客人的資料交換透過 RPA 或是 API 介接**」（p.132）

**(d) 他們自己講的痛點**
> 「**前景能見度變低**，各大零售品牌紛紛調整採購策略，**延後並分多次下訂單**」（p.95）；「**少量多款或依照銷售狀況快速補貨的下單模式…將成為未來下單的主流**」，對策是「**藉用外部時尚數據資料庫，並搭配 AI 及爬蟲技術分析銷售回饋**…為客戶提供更加精準的市場趨勢建議」（p.105）；法說 p.6「**Reduce supply chain lead-time** — **customers require vendors to shorten lead-time.**」

**(e) 🎯 AI：本次調查中最關鍵的一句**
> 「聚陽持續強化大數據、AI 與智慧製造實務應用，將其導入**『需求預測』**、產品開發、生產排程與品質管理流程…同時強化對**『訂單波動、交期風險』**與品質異常的預警與控管能力。」——FY2025 年報 致股東報告書 p.7（V）

內部具名系統（p.130–131，V）：「**YY(用碼量)分析系統**」「**用料系統**」「驗布系統」「排程輔助系統」「**風險預測平台**」「**PMS 用料分析系統**」「3D雲端資料庫」「數位產品發展研發（DPC）」，另有「**TechPack 技術包裹辨識技術**」「**即時布料品質預測**」。FY2025 研發支出 **NT$285.57m＝營收 0.83%**。

**(f) 沒有公布前置期天數**：聚陽、申洲、Crystal、儒鴻四家年報全文掃 `lead[- ]time`／`交期`／`\d+ days`／`delivery cycle`：**零**（V）。→ **任何「布料前置期 45–60 天」式的部落格表格，背後沒有可查證的一手來源。** 廣傳的「申洲 15 天交貨」也**不在**申洲 AR2016／2019／2025 任何一份裡（V）。

### 2.8 同業對照：布料那一注的兩種公開模式

| 公司 | 布料風險怎麼處理 | 證據 |
|---|---|---|
| **聚陽** | **純接單式**，不簽量；靠**先議價**＋**轉投資布廠**（越南 JV） | FY2025 年報 p.104/125/137、法說 p.4（V） |
| **儒鴻** | **部分預測式**：與 INVISTA 簽 Lycra「協議計畫性採購，將預計採購數量**依年度訂單需求分季排定**」；明言「**預測客戶需求，平衡接單生產與計畫性生產方式**」 | FY2025 年報 p.108（V） |
| **申洲國際** | **自己擁有布廠**：年產能「**280,000 公噸布料、6 億件成衣**」；越南西寧新廠約 200 噸/日，「alleviate fabric supply constraints」 | AR2025 p.4/14（V） |
| **Crystal** | **自建布廠**（越南 2026 年底投產）；**現金循環週期 2024 的 71 天 → 2025 的 81 天**（存貨週轉 52 天） | AR2025（V） |

**三個共同點**：①四家都指認同一個痛——**品牌把下單決定往後延、往小拆**；②**沒有一家公布前置期**；③**只有聚陽公開宣稱與客戶共用最終銷售資訊，也只有聚陽把 AI 寫進「需求預測」。**

---

## 3. 論文

> 既有文件已引 GTM-Transformer、Visuelle 2.0、HERMES、Steinker POM 2017、MuQAR、POP、KERN、Fashion Forward、GeoStyle。本節只寫**新的**，並**更正既有文件的三個數字**。

### 3.0 ⚠️ 先更正我們自己文件裡的三件事

1. **「Visuelle 1.0 最佳 WAPE 54.2%」過時了**：實際最佳是 **POP（+GTM）WAPE 52.39 / MAE 28.62**（ECCV 2022，[arXiv:2207.11001](https://arxiv.org/abs/2207.11001)，V 逐字讀 Table 2），MuQAR 52.6 次之。**這不改變結論，只讓它更硬：三年半過去，SOTA 只在約 3 個 WAPE 點的帶狀區間裡 churn。**
2. **2024 年的擴散模型並沒有超越 2022 年的 SOTA**：Dif4FF（ICPR 2024，[arXiv:2412.05566](https://arxiv.org/abs/2412.05566)）54.6、MDiFF（ECCV FashionAI WS 2024，[arXiv:2412.06840](https://arxiv.org/abs/2412.06840)）54.7，兩者比的是 **GTM 的 55.2 版本**而非 52.39。⚠️ **而且這兩篇是同一份工作**（arXiv 標註 substantial text overlap，同一實驗室）——**只能引一篇，引兩篇會被看成灌水。**
3. **HERMES 這條線是死的**：Semantic Scholar 顯示它只有 **7 次引用，且沒有一篇是時尚預測論文**（V）。§3.26 把它當「廠商對自己最有利的公開數字＝上界」仍然正確，但不要暗示它是活躍研究線。

### 3.1 新品需求預測：SOTA 沒動，評估標準也沒修好

**最佳單一入口**：*NFPPF: A Survey on Evolutions, Models and Emerging Trends*（Springer Nature CS 2025，[arXiv:2501.10324](https://arxiv.org/abs/2501.10324)，V），它逐字確認了 `social-trend-signals.md` §2.1(a) 的批評：整個被調查文獻「The results are reported in terms of **MAE and WAPE**」——**全領域沒有一篇報 MASE，也沒有一篇對 seasonal naive。**

| 方法 | WAPE ↓ | MAE ↓ | venue / 年 |
|---|---|---|---|
| **POP (+GTM)** | **52.39** | **28.62** | ECCV 2022（V，讀表） |
| MuQAR | 52.6 | 28.7 | IJMIR 2022（U，轉引自 survey） |
| Dif4FF ＝ MDiFF | 54.6 / 54.7 | 30.0 / 30.1 | ICPR 2024 / ECCV WS 2024（V） |
| GTM-Transformer（FashionIQ 屬性版／標準版） | 54.2 / 55.2 | 29.6 / 30.2 | _J. Forecasting_ 2024（V） |
| **中位數預測器** | **58.3** | **31.8** | **只有 Dif4FF 有報**（V） |
| X-Att-RNN ／ **Attribute k-NN** ／ 平均值預測器 | 59.5 ／ **59.8** ／ 60.1 | 32.3 ／ 32.7 ／ 32.8 | baseline（V） |

🎯 **對製造業評審最有說服力的一句**：**最好的多模態 Transformer（52.39）只贏「查一下屬性最像的舊款」（59.8）7.4 個 WAPE 點，只贏「直接猜中位數」（58.3）5.9 點**；而 Google Trends 這個外生訊號只值 **1.5 個 WAPE 點**（既有記載）。**簡單的屬性類比已經抓到大部分訊號。**

⚠️ **沒有 VISUELLE 競賽這回事**：官方頁與 arXiv 全文（`all:visuelle` 共 11 篇）皆確認沒有 leaderboard、沒有挑戰賽（V）；NFPPF survey 自己把 VISUELLE 1.0/2.0 歸類為 **private（Nunalie 公司資料）**。
⚠️ **沒有任何 LLM 式的時尚銷售預測器存在**（V）。有用的懷疑論反證：*When Does Multimodality Lead to Better Time Series Forecasting?*（[arXiv:2506.21611](https://arxiv.org/abs/2506.21611)，V）——跨 16 個任務，多模態增益**取決於條件，且在時間序列模型本身很弱時幫助最大**。

### 3.2 屬性層級需求預測：只有四篇真的以屬性為預測目標

| 論文 | venue / 年 / DOI | 資料 | 數字 → 對照的基線 |
|---|---|---|---|
| ⭐ **The Value of Social Media Data in Fashion Forecasting** | **M&SOM 2023**, [10.1287/msom.2023.1193](https://doi.org/10.1287/msom.2023.1193) | 3 家跨國公司 POS＋Twitter＋Google SVI，**專有** | **樣本外 MAD 改善 24–57%**，對照**各零售商自己的首批出貨預測**。目標是**屬性**（顏色、牛仔褲版型）。無 naive、無 MASE（V） |
| **MuQAR** | IJMIR 2022, [10.1007/s13735-022-00262-5](https://doi.org/10.1007/s13735-022-00262-5) | Mallzee-P、SHIFT15m、VISUELLE | 目標屬性序列＋**其他所有屬性當外生**；比 GTM **+4.65% WAPE**，僅對前一個 SOTA（V） |
| ⭐⭐ **Two-Stage ML for Intermittent Fashion Sales** | _Forecasting_ 2026, [10.3390/forecast8040056](https://doi.org/10.3390/forecast8040056) | 伊拉克零售商，**64 條以屬性定義的群組序列** | **有報 WRMSSE（M5 的 naive 標準化指標）**；擊敗 Croston、SBA、單階段 ML、LSTM、TFT；rolling-origin CV（V） |
| ⭐⭐ **Greedy aggregation–decomposition** | **EJOR 2018**, [10.1016/j.ejor.2018.02.029](https://doi.org/10.1016/j.ejor.2018.02.029) | 新加坡零售商，SKU-store-day | **提出 RMASE**，尺度無關、對照零預測誤差；擊敗 Croston 家族（V） |
| New product life cycle curve with product attributes | **POM 2022**, [10.1111/poms.13892](https://doi.org/10.1111/poms.13892) | JD.com | 比京東現行生產模型**降誤差 5.35–30.76%**（指標未具名，無 naive）（V） |
| Leveraging Comparables for New Product Sales Forecasting | **POM 2018**, [10.1111/poms.12963](https://doi.org/10.1111/poms.12963) | 嬌生＋大型快時尚 | MAPE/WMAPE **改善 20–60%**，對照未具名的「廣泛使用方法」（V） |
| ⭐ **Leading-indicator augmented hierarchical forecasts** | **Omega 2025**, [10.1016/j.omega.2025.103335](https://doi.org/10.1016/j.omega.2025.103335) | **一家全球製造商**，SKU 層級 | 摘要無數字。**本次全部搜尋中唯一站得住的「製造商側 OR」錨點**（V） |
| ⚠️ Fashion Sales with Social Media Signals (3Ts) | _J. Forecasting_ 2026, [10.1002/for.70204](https://doi.org/10.1002/for.70204) | 77 條配對屬性序列 | 宣稱 VECM **RMSE 3.47 vs 91,034**——同批序列差四個數量級，幾乎確定是單位／水準假象。**只能引框架，絕不可引數字**（與 §3.26 記的 Rudna et al. 同一個毛病）（V） |
| **REAR**（KERN 的延伸） | **IEEE TMM 2021**, [10.1109/TMM.2021.3078907](https://doi.org/10.1109/TMM.2021.3078907) | 社群媒體的細粒度時尚要素 | 在 KERN 上加使用者群體關係與滑動時間注意力（V） |

**三個帶回家的結論**：
- **整個搜尋只有兩篇使用 naive 標準化指標**（EJOR 2018 的 RMASE、_Forecasting_ 2026 的 WRMSSE），**而且都在零售端，不在時尚 CV 圈。** 我們堅持報 MASE 在文獻上是少數派，但站得住。
- **M&SOM 2023 是「社群資料對屬性層級預測有價值」最強的一篇**（24–57% MAD）。⚠️ **但它的對照是零售商自己的首批出貨預測，不是 naive**，資料是三家跨國公司的專有 POS。**它不能用來支持我們做趨勢訊號——我們既沒有 POS，也沒有那個對照組。**
- ⚠️ **找不到任何一篇在預測「版型」或「布料規格」的未來需求；顏色趨勢預測甚至完全是業界刊物而非研究**（Crossref 只回 Bloomsbury／Berg 的時尚研究書章）。**空白的更可能解釋是沒有人拿得到那個標準答案。**
- **階層式預測是這一格真正成熟的方法學**：SKU→顏色→品類→屬性當階層，用 MinTrace／BottomUp 調和。**對我們的意義：往「布料」向上聚合，統計上比往「款式」向下拆解容易得多**（聚合降低變異係數），且有 Apache-2.0 的 `hierarchicalforecast` 可直接跑（§4.4）。

### 3.3 尺碼與合身：本節最該帶走的是一個「其實沒效」的數字

| 論文 | venue / 年 / DOI | 資料 | 數字 |
|---|---|---|---|
| Sembium et al., Recommending Product Sizes | **RecSys 2017**, [10.1145/3109859.3109891](https://doi.org/10.1145/3109859.3109891) | Amazon 鞋類，專有 | **AUC +17–21%**（對照未具名）。⚠️ **實際上線 A/B：Fit 交易 +0.49%** |
| Misra, Wan & McAuley, Decomposing fit semantics | **RecSys 2018**, [10.1145/3240323.3240398](https://doi.org/10.1145/3240323.3240398) | **ModCloth 82,790／RentTheRunway 192,544**（本文釋出） | **AUC 0.657 / 0.719**。**完全沒有報 accuracy** |
| Zalando **SFnet** | **RecSys 2019**, [10.1145/3298689.3347006](https://doi.org/10.1145/3298689.3347006) | ModCloth＋RTR＋Zalando 專有 | **AUC 0.689 / 0.749** |

⚠️ **更正 brief**：Sembium 的貝氏續作是 **WWW 2018**（[10.1145/3178876.3186149](https://doi.org/10.1145/3178876.3186149)），**不是 RecSys 2018**；RecSys 2018 的貝氏尺碼論文是 Zalando 的 Karessli et al.（[10.1145/3240323.3240388](https://doi.org/10.1145/3240323.3240388)，**完全沒有量化結果**）。另有 Myntra（SIGIR eCom'22, [arXiv:2208.06261](https://arxiv.org/abs/2208.06261)，macro-F1 +1.37–4.31%，只對自己的 ablation）與 Farfetch Tailor（[arXiv:2401.01978](https://arxiv.org/abs/2401.01978)，相對 SFnet +45.7%，**不給絕對值**）。

🔴 **本節最該講的數字（來自 Zalando 自己的表）**：**ModCloth 有 68.5% 的標籤就是「Fit」，而 SFnet 的 accuracy 是 0.690——深度模型贏「永遠猜 Fit」0.5 個百分點**；RTR 是 73.8% vs 0.760，**+2.2pp**。**這整條線沒有任何一篇報多數類基線。** 再加上 Amazon 實際上線只有 **+0.49%**——**誠實的讀法是：ML 尺碼／合身預測從來沒有展示過大的真實效果。**

**尺碼曲線（決定每個尺碼做幾件）——真正的白地**：
- **(a) 排版下料規劃（cut order planning）是成熟 OR，但把尺碼曲線當「給定的輸入」**，只負責省布。其中 _Fibres & Textiles in Eastern Europe_ 2020, [10.5604/01.3001.0013.5851](https://doi.org/10.5604/01.3001.0013.5851)（V）給了本文件第二個經濟錨點：**布料佔生產成本 50–60%**，與聚陽的 58% 互相印證。另見 Rose & Shier, _ITOR_ 2014, [10.1111/itor.12104](https://doi.org/10.1111/itor.12104)（V，COP 是 NP-hard；業界把 COP 與排版分開解會「erroneous estimates of the true length used」）。
- **(b) 決定尺碼配比本身：整個文獻只有兩篇。** ⭐ **Top-Dog-Index**（**Annals of OR 2015**, [10.1007/s10479-014-1746-8](https://doi.org/10.1007/s10479-014-1746-8) / [arXiv:0804.1412](https://arxiv.org/abs/0804.1412)，V）是**本次找到最切題的一篇**：論證你**無法**從銷售估出各尺碼需求（單店供給太小 ⇒ 銷售太少或未滿足需求被嚴重截斷），在真實資料上「**could not verify any of the demand distribution assumptions suggested in the literature**」；實地盲測毛收益高**約 1 個百分點**。另一篇是 Caro & Gallien, _Operations Research_ 2010, [10.1287/opre.1090.0698](https://doi.org/10.1287/opre.1090.0698)（V，把「關鍵尺碼缺貨就下架」寫進網路 MIP，試點 +3–4% 銷售）。
- → **`all:"size curve" AND all:retail` 在 arXiv 回 0 筆。沒有任何 ML／預測論文在量產前預測新款的尺碼曲線。**

🔴 **結論不變但引用升級**：`forecast-evaluation.md` 目標 D「明確拒絕宣稱尺碼曲線」應維持，理由改用 **Top-Dog-Index 那句「文獻裡的需求分布假設一個都驗不起來」**。可商用的替代只到**體型分布**（ANSUR II＋NHANES BMX，§4.1）——那**不能預測尺碼需求**，只能誠實說「這是母體的體型分布」。

### 3.4 布料與材質：古典工程學才是這一格的主體

**「布料」在製造業真正的意思，是 Kawabata（KES-F）與 FAST 的客觀量測**——手感、剛柔、懸垂、壓縮、表面摩擦，用接觸式儀器量，不是從照片推。主要文獻：Peirce, _J. Text. Inst. Trans._ 21(9) T377–T416, **1930**（早於 DOI 制度，**不存在 DOI**）；Kawabata 1980 → 引 Woodhead 2005 重印 [10.1533/9781845690984.appendix_a](https://doi.org/10.1533/9781845690984.appendix_a)；Kawabata & Niwa, **IJCST 1991**, [10.1108/eb002968](https://doi.org/10.1108/eb002968)（KES-F→製造的橋樑）；Ly, Tester et al., "**FAST – Fabric Assurance by Simple Testing**", IJCST 7(2/3) 1995, [10.1108/09556229510087146](https://doi.org/10.1108/09556229510087146)；Ciesielska-Wrobel & Van Langenhove, _TRJ_ 82(14):1457–1468, 2012。
⚠️ **這一段對我們是限制不是機會**：KES-F 要四台專用儀器加受訓操作員，**FAST 存在的理由就是 KES-F 對產業太慢**——兩者都無法規模化當資料來源。

**電腦視覺這一側只能做材質辨識與瑕疵偵測，不是布料性質預測**：**MINC**（CVPR 2015, [arXiv:1412.0623](https://arxiv.org/abs/1412.0623)，3M 樣本 23 類）patch 分類 **85.2%**、全圖分割 **73.1%**；**DTD**（CVPR 2014, [arXiv:1311.3618](https://arxiv.org/abs/1311.3618)，5,640 圖 47 類）**53.82% mAP** vs 最佳專門紋理描述子 39.67%（罕見的真基線）；**4D Light-Field**（ECCV 2016, [arXiv:1608.06985](https://arxiv.org/abs/1608.06985)）**77% vs 70%**（乾淨的 +7pp ablation）；⭐ **MuLTER / CoMMonS**（_J. Textile Institute_ 2020, [arXiv:2003.07725](https://arxiv.org/abs/2003.07725)）是唯一**公開的布料表面顯微影像基準**（纖維長度、平滑度、起毛），MINC-2500 **82.2%**——⚠️ **但在 CoMMonS 自己身上只贏第二名 0.2–3.2%，作者自承「the overall accuracy rates are not high」。**

⚠️ **瑕疵偵測：量多但不嚴謹。** 子領域已集中到 **Tianchi** 競賽資料集而非 TILDA/AITEX/ZJU-Leaper，且 2024–25 最強的幾篇（Fab-ASLKS +5% mAP@50、Fab-ME +3.5%、SPFFNet +0.8–8.1%）**全是未審查的 preprint，只贏自己的 YOLOv8s backbone，沒有一篇給絕對 mAP**。**不要引任何「+5% mAP」當成問題已解決的證據。** 唯一同儕審查並同時在 MVTec-AD＋AITEX＋TILDA 上評估的是 _TRJ_ 2023/24, [10.1177/00405175231206820](https://doi.org/10.1177/00405175231206820)（V）。

❌ **「哪塊布適合這個設計」在文獻上幾乎不存在**：唯一命中是 _TRJ_ 2017, [10.1177/0040517517729383](https://doi.org/10.1177/0040517517729383)（V），而它是 **Fuzzy AHP＋Fuzzy TOPSIS，沒有資料集、沒有指標、沒有基線**。**沒有任何學習式的「布料↔設計」配對模型存在。**

⚠️ 這正好對上我們自己的量測：§3.3b「**材質光澤不可靠**（CLIP AUROC 0.71，CI 0.52–0.89），跟 OVAD、MODA 文獻一致」，§3.3c 換 VLM 才到 0.90。**連「亮不亮」都要動用 VLM 才做得準，談克重與織法是沒有根據的。**

### 3.5 需求訊號 → 生產屬性：本次最強的一格——但橋的另一端沒接上

| 論文 | venue / 年 | 輸入 / 資料 | 最佳數字 → 基線 |
|---|---|---|---|
| **NeuralTailor** | **SIGGRAPH 2022 (TOG)**, [10.1145/3528223.3530179](https://doi.org/10.1145/3528223.3530179) | **3D 點雲**；22,000 件 / 19 類（公開） | 已見類別 **Panel L2 1.5、片數準確率 99.7%、縫合 96.3/99.4**；⚠️ **未見類別掉到 5.2 / 83.6% / 74.7–83.9** |
| **Sewformer** | **SIGGRAPH Asia 2023 (TOG)**, [10.1145/3618319](https://doi.org/10.1145/3618319) | **單張影像**；⭐ SewFactory 約 1M 影像/版型對 | **Panel L2 3.57、片數 88.7%、縫合 F1 95.7** vs 重訓的 NeuralTailor 4.41 / 83.6% / 84.5 |
| **DressCode / SewingGPT** | **SIGGRAPH 2024 (TOG)**, [10.1145/3658147](https://doi.org/10.1145/3658147) | 文字；19,683 個版型 | 自迴歸文字→服裝 |
| **ChatGarment**（VLM） | **CVPR 2025**, [arXiv:2412.17811](https://arxiv.org/abs/2412.17811) | ~40k 件 / 1M 影像 | Dress4D **CD 3.12、F 0.75、失敗率 0%** vs SewFormer 27.06/0.55/4.3% |
| **AIpparel** | [arXiv:2412.03937](https://arxiv.org/abs/2412.03937) | GCD-MM，**>120,000 件** | SewFactory **Panel L2 2.8cm、片數 93.9%**；多模態生成 **59.0%** vs SewFormer-FT 10.3% |
| **GarmentDiffusion** | **IJCAI 2025**, [arXiv:2504.21476](https://arxiv.org/abs/2504.21476) | 三個資料集含 GarmentCodeData 115,195 | SewFactory 片數 **0.883** vs SewFormer 0.859；⭐ **快 100 倍** |
| **GarmentCodeData** | **ECCV 2024**, [arXiv:2405.17609](https://arxiv.org/abs/2405.17609) | ⭐ **115,000 件量身版型**、CAESAR 體型、XPBD 懸垂 | 授權見 §4.1 的不一致警告 |

🎯 **這是本次唯一「從感知輸入產生真正生產工件」的成熟技術線，而且有真 benchmark。** 但有**兩個不能粉飾的缺口**：
1. ❌ **「tech pack 生成 LLM」作為研究文獻並不存在**（arXiv `abs:"tech pack"` 無相關結果；搜服裝規格生成只回虛擬試穿）（V）。
2. ❌ **上表每一篇走的都是「影像／文字 → 3D 圖學的縫紉版型」，服務對象是虛擬替身、試穿與遊戲。沒有一篇走「消費者需求訊號 → 可製造的規格」，也沒有一篇拿真實工廠版型或真的做出來的衣服驗證過**——指標是**對合成標準答案**的 panel L2（公分）與縫合 F1。
→ **這是我們要「蓋」的橋，不是可以「走過去」的橋。** demo 裡若要出現「版型」兩字，誠實的做法是**把 GarmentCode 的參數化版型當成一張可展示的語彙表**（「寬鬆 = 胸圍鬆份 +X cm」），**不是宣稱我們能從對話生成版型**。

### 3.6 代工廠的訂單預測：真的是空白

跨 OpenAlex（含 IJF／IJPE 的 ISSN 限定掃描）、S2 關鍵字＋引用圖、Crossref、arXiv 約 15 組查詢後：**沒有任何同儕審查的 OR／預測論文，用真實訂單資料預測「服飾／紡織代工廠收到的訂單」並對照具名基線報誤差。**
- 長鞭效應經典實證：Cachon, Randall & Schmidt, **M&SOM 2007**, [10.1287/msom.1060.0149](https://doi.org/10.1287/msom.1060.0149)（V）——美國普查資料，**批發端有放大，零售端與多數製造端沒有**；⚠️ 摘要無服飾分項，且不是預測論文。
- **最高價值的未解項**：Thomassey, **IJPE 2010**, [10.1016/j.ijpe.2010.07.018](https://doi.org/10.1016/j.ijpe.2010.07.018)——**199 次引用，IJPE 裡被引最多的服飾預測論文**，摘要透過所有管道皆取不到（U）。**值得用學校帳號調出來。**
- *Analysis of the Bullwhip Effect in the Apparel Supply Chain: Bangladesh*（SSRN 2026, [10.2139/ssrn.6726101](https://doi.org/10.2139/ssrn.6726101)）題目正中要害，**但是未審查的 preprint——這件事本身就是結論。**

**對我們的意義**：ODM 站在鏈的最末端，**它看到的訂單波動有相當部分是零售端決策被放大後的產物，不是消費者偏好的變化**。這是「**不要把 PO 當需求訊號**」的理論依據，也和 §2.2 的 QJE 結果一致（採購行為主要由**買方固定效果**解釋）。

---

## 4. 開源：資料集與程式碼，以及能不能商用

> 判準：**能不能商用**。凡 non-commercial、research-only、或沒寫授權（＝視同保留所有權利）一律不可出貨——和 §3.27 拒絕 BRIA RMBG-1.4 是同一條標準。

### 4.1 版型（silhouette / fit / pattern）

| 資料集 | 規模 | 授權 | 商用 |
|---|---|---|---|
| ⭐ **Fashionpedia** annotations＋ontology | 48,825 圖、46 物件、**294 屬性** | 「licensed under a **Creative Commons Attribution 4.0 License**」；軟體 BSD-2 | **可（需標註）** |
| Fashionpedia **影像** | train 45,623 | 「Fashionpedia **does not own the copyright of the images**」，**逐圖授權欄位** | **需逐圖過濾**（見下） |
| **3D Garments w/ Sewing Patterns** `zenodo.org/records/5267549` | **23,500+** 件、~85 GB | **CC BY 4.0**（Zenodo API 確認） | **可** |
| **GarmentCodeData v1+v2**（ETH RC `20.500.11850/690432`） | **115,000** 筆、368 GB | ⚠️ **兩來源不一致**：ETH RC Rights 欄寫 CC BY 4.0（但 DataCite `rightsList` 為空），論文（ECCV 2024）自述 **CC BY-SA 4.0**。**法務簽核前須釐清，保守當 SA（copyleft）處理** | **可（可能有 SA 義務）** |
| **GarmentCode/pygarment、Garment-Pattern-Generator、NeuralTailor** | 程式 | **MIT** | **可** |
| ⭐ **ANSUR II** `openlab.psu.edu/ansur2/` | 4,082 男＋1,986 女，**93 項量測** | 無授權聲明，但美國陸軍職務作品 → **17 U.S.C. §105，在美不受著作權保護** | **可（最佳免費體型來源）** |
| **NHANES BMX（CDC/NCHS）** | 全國抽樣、有加權 | 美國公有領域＋DUA（僅統計用途、不得重新識別）；**無 NC 條款** | **可** |
| DeepFashion-MultiModal | 44,096 圖 | 「**non-commercial research purposes only**… any portion of **derived data**」 | **不可** |
| DeepFashion／DeepFashion2 | 800K＋／491,895 | DF：non-commercial only；**DF2 完全沒有 LICENSE 檔** | **不可** |
| ModCloth／RentTheRunway | 82,790／192,544，含 fit 與身體量測 | **無授權、無條款，只要求引用 → 視同保留所有權利**；且是作者本就沒有權利的爬取 UGC，含使用者自填身體量測 | **不可** |
| CAESAR／SizeUSA／SMPL·SMPL-X／Sewformer·SewFactory·DressCode | — | 前二者「available for **purchase**」；SMPL「**non-commercial**… commercial purposes is **prohibited**」；後三者**無授權** | **全部不可** |

🎯 **Fashionpedia 的 `silhouette` 屬性有 25 類**（asymmetrical, symmetrical, peplum, circle, flare, fit and flare, trumpet, mermaid, balloon, bell, bell bottom, bootcut, peg, pencil, straight, a-line, tent, baggy, wide leg, high low, curved/tight/regular/loose fit, oversized），另有 `length`（15）、`waistline`（7）、`neckline type`（25）、`opening type`（10）。**這是 DeepFashion-MultiModal 那 12 個 shape 屬性的合法商用替代品，而且更細——我們目前只有 4 條版型軸，這裡有 25 類 silhouette。**
⚠️ **Fashionpedia 影像的逐圖授權比例很差**：train split（n=45,623）**51.2% 是 NonCommercial**（BY-NC-ND 32.4%、BY-NC-SA 10.6%、BY-NC 8.3%）；48.8% 允許商用，但**同時允許商用與改作的只有 35.5%**。→ **本體隨便用，像素要過濾，過濾完剩約三分之一。**

### 4.2 布料（fabric / material）

| 資料集 | 規模 | 授權 | 商用 |
|---|---|---|---|
| ⭐ **Fab-IL** `zenodo.org/records/19353920` | **97,575 張真實產線布料影像**、4 個工廠 domain、16 種瑕疵＋正常、13.5 GB | **CC BY 4.0** | **可**（約為 AITEX 的 400 倍，且授權乾淨） |
| **Fabric Texture Images** `zenodo.org/records/17802801`／**Flax Fiber Fabrics** `zenodo.org/records/15608199` | 747 MB／1.08 GB | **CC BY 4.0** | **可** |
| ⭐ **Fashionpedia 織品屬性** | `textile pattern` 18 類、`textile finishing/manufacturing techniques` 21 類、`non-textile material type` 10、`leather` 4 | **CC BY 4.0** | **可** |
| **MINC / Materials in Context**（CVPR 2015） | 3.0M 點、23 類（含 fabric、leather）；MINC-2500 = 57,500 patch | 「The **annotations** are licensed under a **CC BY 4.0**… The **photos have their own licenses**」；全解析度影像 non-commercial only | **標註可／影像不可** |
| **Fabrics**（Kampouris et al.） | ~2,000 件、9 類、**附廠商成分標籤** | 「provided for **research purposes ONLY (NO commercial products)**」 | **不可**（可惜——這是唯一有成分標籤的） |
| DTD／FMD／AITEX AFID／TILDA／ZJU-Leaper／DAGM 2007 | — | DTD「research purposes」；FMD 無授權聲明無逐圖清單；**AITEX、TILDA、ZJU-Leaper、DAGM 四者皆完全沒有授權聲明** | **全部不可** |
| ❌ **「MaterialWise」** | — | **找不到，不存在這個影像資料集**（同名者是 ChemFORWARD 的化學危害篩選工具） | — |

### 4.3 帶時間軸的銷售資料：**結構性缺口**

| 資料集 | 授權 | 商用 |
|---|---|---|
| **Visuelle 2.0**（5,355 商品、110 店、2016-11–2019-12，含 inventory/restock/discount） | **資料完全沒有授權聲明 → 視同保留所有權利**；仍是 Google 表單。配套 `visuelle2.0-code` 是 **CC BY-NC-SA 4.0**，⚠️ **但 GitHub 報成 SPDX `NOASSERTION`，自動掃描器不會標出 NC** | **不可** |
| **H&M**（Kaggle，31.8M 筆交易） | 「Competition Data for **non-commercial purposes only**」。⚠️ **修正既有記載**：我們引用的 HF 鏡像 `einrafh/hnm-…` **完全沒有 license 欄位**（`cardData.license = None`），README 自述「non-komersial dan riset」——**它什麼都沒授予，Kaggle 條款仍然管得到** | **不可** |
| M5／Corporación Favorita／SHIFT15m／Amazon Reviews 2023 | 前三者明文 non-commercial（SHIFT15m 是 CC BY-NC 4.0）；Amazon Reviews **無 license 欄位、無條款 → 保留所有權利** | **全部不可** |
| UCI Online Retail II（1,067,371 列，2009–2011） | **CC BY 4.0** | **可**（但是禮品雜貨，不是服飾） |
| Fashion Product Images（paramaggarwal，44k 商品） | Croissant：**MIT** | **可\***（**無銷售日期**；且是爬取的 Myntra 照片，MIT 是上傳者掛的） |
| **2023–2026 新的服飾銷售序列** | HuggingFace 全面掃過（top-30 `fashion` 標籤＋4 組查詢）：**一個都沒有** | **不存在** |

🔴 **結論**：**版型與體型已經有乾淨可商用的來源；服飾銷售時間序列沒有，而且用公開資料解不了。要做真的預測，資料只能來自製造商客戶。**
⚠️ **三個現行的「授權洗白」陷阱**（V）：`Qdrant/hm_ecommerce_products` 在 H&M 競賽資料上掛 **cc-by-4.0**；`snchakri/m5-retail-demand-forecasting-benchmarks` 在 M5 上掛 **apache-2.0**；AWS open-data registry 的 **BodyM** 寫 CC BY-**NC** 卻連到純 CC BY 的法條頁。**資料集卡上的 CC BY 徽章不代表那些影像是你的——MINC 與 Fashionpedia 都白紙黑字說自己不擁有照片。**

### 4.4 程式碼

| 套件 | 授權 | naive／seasonal-naive | MASE／RMSSE | 備註 |
|---|---|---|---|---|
| ⭐ **Darts** 0.47.0 | **Apache-2.0** | **有**（`NaiveSeasonal`/`NaiveMean`/`NaiveDrift`/`NaiveMovingAverage`） | **兩者都有** | **唯一一個套件同時給齊三樣** |
| **statsforecast** 2.1.1 ＋ **utilsforecast** 0.2.16 | Apache-2.0 | **有**（`SeasonalNaive` 等，另含 Croston/ADIDA/IMAPA/TSB） | **utilsforecast 兩者都有**（`losses.mase`、`losses.rmsse`、`msse`、`scaled_crps`） | Nixtla 堆疊的基礎 |
| ⭐ **hierarchicalforecast** 1.5.1 | Apache-2.0 | — | 經 `utilsforecast` | **屬性／布料層級聚合的正解**（BottomUp/TopDown/MinTrace/ERM） |
| **GluonTS** 0.17.0／**sktime**／**neuralforecast** 3.2.2／**Prophet** 1.4.0 | Apache-2.0／BSD-3／Apache-2.0／**MIT** | 前二有（⚠️ sktime **沒有** `strategy="seasonal_last"`，要寫 `NaiveForecaster(strategy="last", sp=N)`）；後二**無** | GluonTS 與 neuralforecast 只有 MASE；sktime 兩者都有；**Prophet 都沒有** | Prophet 的基線與指標要自己帶 |
| ⭐ **Chronos / Chronos-Bolt**、**TimesFM** | **Apache-2.0（含權重）** | — | — | zero-shot 可用 |
| ⚠️ **Moirai (uni2ts)** | 程式 Apache-2.0，**權重 `cc-by-nc-4.0`「research purposes only」** | — | — | **程式可／權重不可** |
| **humaticslab/GTM-Transformer**（MIT，架構可重用）／POP-Mining-POtential-Performance（**CC BY-NC-SA 4.0，不可**） | 見左 | — | — | — |
| ⭐ **Marqo-FashionSigLIP**（已在用） | `license: apache-2.0`；訓練涵蓋 categories/styles/colors/**materials** | — | — | **可** |
| ⚠️ fashion-clip／laion CLIP-ViT-B-32 | 皆 `license: mit`，**但卡片分別寫「was not developed for model deployment」（且 Farfetch 資料條款「Awaiting official release」）與「Any deployed use case… whether commercial or not - is currently out of scope.」** | — | — | **兩者都避開** |

---

## 5. 誠實的判決

### 5.1 有沒有任何東西改變 §3.15／§3.26 的否決？

**沒有。證據比之前更強，只是方向不同。**

| 之前的理由 | 本輪新增的證據 | 判定 |
|---|---|---|
| §3.15：趨勢關鍵字 28 組全部變差 | 無新證據可推翻 | **維持** |
| §3.26：Heuritech 自己只做到 4.3% MASE @10,000 條 | **Heuritech 現在公開賣「2 年期的 fabrics/shapes 屬性預測」給製造商，起價 12k€/年**——但它唯一公布過方法與數字的地方，仍然是那份 4.3% MASE 的 HERMES；**七家 Priority A 廠商同儕審查證據 = 0**；HERMES **只有 7 次引用且無人跟進**（這條線是死的） | **維持，且更尖銳：產品賣得比證據遠** |
| 主辦方已有內部趨勢平台，排除趨勢預測 | **聚陽 FY2025 年報白紙黑字寫 AI 已導入「需求預測」**，且已有 YY 用碼量分析系統、PMS 用料分析系統、風險預測平台、即時布料品質預測 | **從「離題」升級為「重複造輪子」** |
| Visuelle SOTA 誤差等於銷量的一半到全部 | Caro & Martínez-de-Albéniz：「**impossible to forecast fashion at the item level a priori**」；且**最強的 Transformer 只贏屬性 k-NN 7.4 個 WAPE 點** | **維持，且有了教科書級引用** |
| 資料授權都不乾淨 | 逐一核過後更糟：Visuelle 2.0 資料無授權、H&M 的 HF 鏡像**也**無授權（修正既有記載）、ModCloth/RTR 無授權、**2023 年後沒有任何新的公開服飾銷售序列** | **維持，且更嚴重** |

**唯一被改變的是「該做什麼」**：既有文件的框架是「預測 vs 不預測」。本輪顯示這個二分法放錯了地方——**製造商要的根本不是成衣需求預測，是材料決定的支援**（§2.1 第 3、4、6 項）。

### 5.2 一場 demo、約 100 段對話，能誠實宣稱什麼？

先把分母算清楚：聚陽 **FY2025 出貨 17.5 百萬打 ≈ 2.1 億件**。100 段對話 ≈ **2.1 億分之一的量級**，而且來源是現場的隊員與評審。

| | 宣稱 | 為什麼 |
|---|---|---|
| ✅ | 「這 N 段對話裡被講到最多的設計要素是 X，而目錄裡只有 y% 的商品表現它」 | §3.22 已驗證（T14：MRR 0.381→0.509，p<1e-4；隨機移除對照 p=1.00）。**每份回應都寫出 `n_sessions`** |
| ✅ | 「我們把自由文字翻成**要素級**規格，每張卡片的理由加總等於它的分數」 | T4 理由忠實度 100%，有測試守著 |
| ✅ | 「**布料是聚陽 58% 的銷貨成本**，所以需求訊號最該落地的地方是材料，不是款式」 | 聚陽法說 p.12（V）＋ _FTEE_ 2020 的 50–60% 互相印證。**這是把我們的輸出對準對方錢包的那一句** |
| ✅ | 「我們**不**做趨勢預測，理由有四個數字：Heuritech 自己的 4.3% MASE、Visuelle WAPE **52.4–86%**、**最強 Transformer 只贏屬性 k-NN 7.4 點**、我們自己 28 組全敗」 | 主動說出做不到什麼，在製造業評審面前是加分 |
| ⚠️ | 「我們看得到**版型**偏好」 | 只有 4 條軸，`structured_shoulders`／`soft_knit` 盲標 **0 正例**、`relaxed_fit` 只有 7 個正例（CI 0.71–0.98）。**要講就得講這個 n** |
| ⚠️ | 「我們看得到**布料**偏好」 | 只有霧面／亮面／柔軟針織，光澤要靠 VLM 才有 0.90（CLIP 0.71）。**這是「布料外觀」，不是布料** |
| ❌ | 「我們預測下一季流行什麼」 | 零證據；對方已有需求預測系統 |
| ❌ | 「缺口高的要素明年會賣得好」 | 沒有資料能驗證。**這是我們自己寫在 §3.22 的護欄，不要自己拆** |
| ❌ | 「我們能預測布料用量／buy-to-cut」 | 需要 tech pack、排版與歷史耗用。**聚陽自己已經有 YY 系統了** |
| ❌ | 「我們能預測尺碼曲線」 | 需要退貨資料；唯一公開資料集授權不乾淨；且 Top-Dog-Index 證明**連從銷售估各尺碼需求都做不到** |
| ❌ | 任何縮短前置期的百分比 | Li & Fung 的 40→21→16 週是反面教材：自訂 baseline、註腳自我否認、唯一量過的是 **n=2 件衣服** |

### 5.3 建議的後台定位：三層，野心遞減，證據遞增

- **第一層（主張，今天就有證據）——「需求的誠實摘要」**：「這是本服務收到的 N 段對話。被要求最多的設計要素是這些；目錄能回應的比例是這些；缺口排序這樣算（公式在頁面上），而且它是可否證的。」**沒有預測成分，分母寫在畫面上。** 這是 S2，唯一的新增是把單位換成製造商的語言。
- **第二層（框架）——「翻譯層」**：「消費者講的是『看起來可靠』『不要太用力』；工廠要的是肩線、鬆份、光澤、領型。我們做的是中間的翻譯，而且每一步都能拆回去對帳。」這是 S3。對 ODM 特別有說服力，因為 **§2.7(c) 聚陽自己說他們在做「從前端趨勢整合及產品概念發想，到最終銷售資訊之共用」**——我們補的正是「前端概念發想」那一段的結構化。
- **第三層（接口，不是功能）——「留位置，不造訊號」**：「真正的需求預測需要帶日期的銷售資料，那是貴公司與品牌客戶之間的資產。我們做的是把介面留好：`design_weight_prior` 接受外部先驗——企劃的指示，或貴公司既有平台的輸出——有上限、有歸因、使用者永遠壓得過它。」這就是 §3.26 已做的事，**現在有了更好的說法**：對方年報自己寫了有需求預測系統，所以「**我們接你的，不取代你的**」是禮貌也是事實。

### 5.4 如果一定要有一個「更往製造商走」的新東西

按證據支撐度排序，**只有第一項是本輪證據明確支持的**：

1. ✅ **把缺口盤的軸，從 15 條感性要素擴成 Fashionpedia 的 silhouette／textile 本體（CC BY 4.0；25 類 silhouette＋18 類 textile pattern＋21 類 finishing）。** 這不是預測，是**提高解析度**——它讓「版型」與「布料」第一次有真實的類別支撐，而且授權乾淨（§4.1）。成本是重新校準 `c(i,d)` 並對每條新軸重跑 §3.3 的 AUROC；**沒有 AUROC 的軸不准上盤面**（既有標準）。
2. ⚠️ **把缺口的聚合層級往上加一層「布種」**（例：霧面＋柔軟針織＋深色 → 某一類布）。統計上比往下拆款容易（§3.2），但**需要一張「要素→布種」的對照表，而那張表我們沒有**，只能由聚陽提供。**沒有那張表就不要做**，否則又是一個自己產生標準答案的循環（§4.2 的規則）。
3. ❌ **不要做**：布料用量預測、尺碼曲線、趨勢時間序列、訂單機率。理由見 §5.2。

### 5.5 結論句

> **一個什麼都不預測、但把需求摘要得誠實的儀表板，是一個有效的答案——在這個案子裡，它還是唯一有證據支撐的答案。**
>
> 理由不是我們懶：是**布料佔聚陽 58% 的成本卻在接單後才買**（他們自己的簡報與年報），是**他們的 AI 已經寫進「需求預測」**（他們自己的年報），是**款式層級的事前預測被教科書判定不可能**（Caro & Martínez-de-Albéniz），是**最強的多模態 Transformer 只贏「查屬性最像的舊款」7.4 個 WAPE 點**（§3.1），是**所有帶日期的服飾銷售資料授權都不乾淨且 2023 年後沒有新的**（§4.3），也是**我們自己量過 28 組趨勢設定全部變差**（§3.15）。
>
> 在一個滿場都是「AI 預測流行趨勢」的會場，**唯一一組說得出自己做不到什麼、而且每一句都附得出數字和出處的隊伍**，記憶點比多一個沒驗證的功能高。

---

## 我無法核實的部分

**完全無法核實（不要寫進簡報）**
- **「Zara 留 50–60% 的季度不預先決定」／「只預先設計 15–25%」**——找不到任何可及的一手或同儕審查來源。業界傳說。
- **「Shein 3 天從趨勢到商品」**、**「Shein 未售庫存個位數 %」**——前者在 Shein 自家所有 PDF 全文皆無；後者只在 2023 一頁紙出現，2023／2024 兩份永續報告都已刪去百分比。
- **「申洲 15 天交貨」**——不在 AR2016／2019／2025 任何一份裡。
- **Nike 款式／SKU 收斂百分比**——2017 Consumer Direct Offense 新聞稿 404，Wayback 無對應快照。
- **Toray–UNIQLO 第 2／3／4 期的金額或期間**——兩家公司都沒公布過（僅 2006 第一期的「5 年逾 2,000 億日圓」「73 個開發主題」是 V）。
- **任何「布料前置期 45–60 天」式的天數表**——四家上市成衣廠年報全文掃描皆無。

**一手來源未開（有轉述或 metadata，但原文未讀）**
- Ferdows, Lewis & Machuca (2004), "Rapid-Fire Fulfillment", _HBR_ 82(11)——胚布 50% 的原始出處，付費牆。
- Ghemawat & Nueno, "ZARA: Fast Fashion", HBS case 703-497——Comditel／12,000 款／260 家供應商的原始出處。
- ⭐ Thomassey, **IJPE 2010**, 10.1016/j.ijpe.2010.07.018——**199 次引用，IJPE 裡被引最多的服飾預測論文**，摘要透過所有管道皆取不到。**本次最高價值的未解項。**
- ⭐ Maile & Whitfield (2026), "Rethinking economic upgrading in apparel GVCs", _Environment and Planning A_, 10.1177/0308518x261421107——主題正是頂級成衣供應商如何透過產品創新週期的夥伴關係捕捉價值；Sage 與 CBS 皆 403。
- Caro & Gallien (2012), _Operations Research_ 60(6):1404–1422（已定位 PDF，未讀）；*Demand forecasting for fashion products: a systematic review*, **IJF 2023**, 10.1016/j.ijforecast.2023.02.005（付費牆）；Sembium 的 WWW 2018 續作（摘要取不到）。
- **MuQAR 的 52.6 WAPE 是從 NFPPF survey 的表轉引，未讀原論文表格（U）。**
- McKinsey Apparel CPO Survey／State of Fashion——從未成功開啟（逾時）。

**本輪未完成的查證（不是「不存在」）**
- **G2、SourceForge、Capterra、TrustRadius、Google Scholar 全數硬 403 擋自動化**——First Insight 的第三方評論與定價因此未讀（U）。
- First Insight 相關的 _J. of Research in Interactive Marketing_ 2010 全文付費牆：**無法排除該文內部有提到 First Insight**（雖然 Petro 不在作者名單、摘要也沒有驗證宣稱）。
- Stylumia 的「Intelligent Demand Index」「3–6 個月提前」等宣稱，本輪仍**無法核實**（與 `social-trend-signals.md` 一致）。
- WebSearch 額度中途耗盡（200/200），二手新聞（WSJ、WWD、Rest of World、Sourcing Journal）覆蓋率低。
- WGSN 的「$15,500/年」「€1250/月」等數字來自 Reddit 自述（**U**，無方法）——**只有 Coventry University 的 £33,462.85 是政府公告（V），要引就引那個。**
- Kaggle 條款引文透過渲染代理取得，法務簽核前值得人眼複查；**ETH GarmentCodeData 的授權與論文自述不一致（§4.1）必須釐清**；MINC 授權在另一次查證中該網域無法連線，值得複查一次。

**我們自己這一側的兩個弱點（不是外部核實問題，但同樣要講）**
- `element_gap` 的需求側是 `deque(maxlen=500)`、**沒有時間戳**、重啟即清空（`engine02/api.py::_record_demand`）。**任何「趨勢箭頭」在今天的程式上都沒有依據。**
- 15 條要素軸裡**版型只有 4 條、布料只有 3 條**，其中 `structured_shoulders` 與 `soft_knit` 在 420 件盲標中是 **0 正例**（KAGL 幾乎沒有西裝外套與針織衫）。**「版型與布料」這個題目，我們目前的解析度不夠——這正是 §5.4 第 1 項存在的理由。**
