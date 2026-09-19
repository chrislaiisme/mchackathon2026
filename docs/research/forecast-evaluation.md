# ENGINE 02｜「精準預測」這件事能不能宣稱？可得資料下的誠實評估設計

> 角色：本文件是**懷疑論者的報告**。任務是判斷 ENGINE 02 能不能做出**站得住腳的預測宣稱**，以及要怎麼用
> **我們真的拿得到的資料**誠實地驗證它。結論寫在最前面，理由與可實作規格寫在後面。
> 範圍限制：只新增本檔，不改任何既有檔案；建議一律寫成 `檔案:函式`，由 coordinator 整合。
> 核實標記：`[已核]` = 本次實際打開原文／API 取得；`[未核]` = 依領域常識或二手來源，標出來讓你自己決定要不要引用。

---

## 0. 一頁結論

1. **今天不能宣稱「精準預測」。** 我們沒有任何帶時間軸的銷售資料，`element_gap` 的需求側是本服務自己收到的查詢
   （`engine02/api.py::_record_demand`，deque `maxlen=500`、**沒有時間戳**、重啟即清空）。任何用這份 log 評估的
   「預測」都是在預測自己的輸入分布（§4 的循環性陷阱）。
2. **Visuelle 的判決：技術上可用、策略上不要放在關鍵路徑。** 資料要填 Google 表單才給下載連結（
   `https://forms.gle/cVGQAmxhHf7eRJ937`）[已核]，卡片上**沒有任何授權條款**，上游是 Nuna Lie 一家義大利快時尚
   公司的內部資料 → 只能離線評測、不可出貨。更關鍵的是：就算今天拿到，它支撐的任務（單品新品銷售預測）
   目前最好的公開結果是 **WAPE 54.2%**（Visuelle 1.0，GTM-Transformer）而 Attribute-kNN 基線是 **59.8%**；
   在 Visuelle 2.0 的 item-shop 層級，最佳模型 **WAPE 85.65%**、Naive 118.18%[已核]。
   也就是說，**一天之內能做到的最好情況，是重現一個「誤差等於銷量本身」的數字**，而且只贏最簡單的 kNN 約 5 個百分點。
3. **真正有時間軸、而且不用帳號就下載得到的是 H&M**：HuggingFace 鏡像 `einrafh/hnm-fashion-recommendations-data`
   非 gated，transactions **31,788,324 筆**、`t_dat` 自 **2018-09-20 至 2020-09-22**（105 週），articles **105,542 筆**
   帶 `graphical_appearance_name`（30 類）、`perceived_colour_value_name`（Dark/Bright/Light…）、`colour_group_name`（50 類）、
   `garment_group_name`（21 類）[全部已核]。這足以建出**真實的「要素×品類」週需求序列**，而且其中 6 個標籤能直接對上
   我們 15 個感性設計要素中的 6 個。授權未標示（上游是 Kaggle 競賽規則）→ **離線評測可以，不可出貨**。
4. **我們今天能宣稱的最強句子是 §5 的 S2**：「我們量化**被問到但目錄給不出來**的設計要素缺口，而且它是可否證的
   （T14：遮掉表現該要素的商品，它在缺口榜的 MRR 0.381→0.509，p<1e-4；遮掉同樣件數的隨機商品完全不動，p=1.00）」。
   這句話**不含任何預測成分**，而且已經有數據。S1（「我們預測下一季會流行什麼」）**建議明確拒絕**。
5. **贊助商自己已經排除了趨勢預測。** `docs/research/engine02-completeness.md` §2.1 記錄：「主辦方已有內部趨勢平台，
   且明確排除趨勢預測系統」。做預測宣稱不只是證據不足，而是**在對方的主場跟對方的既有系統比**，而且離題。

---

## 總表：預測目標 → 需要的資料 → 公開資料有嗎 → 標準評估 → 我們能不能做

| # | 預測目標 | 需要的資料 | 公開資料有嗎 | 該領域標準評估 | 我們能不能做 |
|---|---|---|---|---|---|
| A | **要素人氣時間序列**（某要素在需求中的週／月佔比） | 帶日期的成交（或評論）逐筆資料 ＋ 商品的要素標籤 | **有**。H&M 鏡像（標籤有、圖只有 19% 子集）；Amazon Reviews（評論日期當銷售代理，Fashion Forward 的做法）；Visuelle（tags，需表單） | 佔比的 MAE／MAPE（Fashion Forward）＋ 要素排名的 **overlap@k**；基線必須含 persistence 與 seasonal naive | **能**，H&M 路線一天內做得完（§6）。但**只能做到「要素佔比可被預測到什麼程度」，不能宣稱是我們的模型在預測** |
| B | **品類×顏色需求**（週銷量／佔比） | 同 A，且要有品類與顏色欄位 | **有**。H&M 完全具備（`product_type_name` 131／`colour_group_name` 50） | MASE／RMSSE vs seasonal naive（M5 家族指標） | **能**，而且是最容易做對的一格。但 h=26 週時 seasonal naive 就是業界現行做法，**很可能贏不了** |
| C | **新品成功機率／新品銷量** | 每件商品的上市日 ＋ 上市後前 N 週銷量 ＋ 商品圖 | **部分**。Visuelle 1.0／2.0 是唯一為此設計的（需表單、無授權）；H&M 可用「首次出現週」當上市日代理，但只有 19% 有圖 | WAPE／MAE／Tracking Signal／ERP（Visuelle 官方協定，5080 train／497 test、h=6 週） | **不建議**。SOTA WAPE 54–86%，一天內只能重現而非超越；且必過基線是 Attribute-kNN，不是 naive |
| D | **尺碼曲線**（各尺碼的需求分布） | 尺碼層級成交 ＋ **退貨**資料 | **沒有**。H&M articles 沒有尺碼欄位、沒有退貨；文獻（Myntra RecSys 2019、Amazon SDM 2020）用的都是內部退貨資料 | 尺碼分類的 accuracy／F1、退貨率下降 | **不能。建議明確拒絕宣稱** |
| E | **售罄率 sell-through** | 銷售 ＋ **庫存**（＋補貨、折扣） | **只有 Visuelle 2.0**（含 inventory／restock／discount 序列），需表單 | WAPE，或「是否會滯銷」的二分類 AUROC | **不能**（除非表單過了；而且庫存政策是 Nuna Lie 的，不是聚陽的） |
| F | **缺口本身會不會實現**（缺口高的要素明年真的賣得好嗎） | 我們的缺口榜 ＋ 同期同市場的真實銷售 | **完全沒有**。沒有任何公開資料同時有「我們的查詢分布」和「對應市場的銷售」 | 無標準（要自己定：缺口排名 vs 次期銷售成長的 Spearman ρ） | **不能，且這是最該拒絕的一格**。這正是 §3.22 已經寫明「不能宣稱」的那件事 |

---

## §1 這裡的「預測」到底可以是什麼？六個候選目標的解剖

預測宣稱之所以危險，是因為「預測」這個詞會被聽成「預測銷售」。所以先把候選目標拆開，每一個都問三件事：
**目標變數是什麼、標準答案從哪來、誰在文獻上做過**。

### A. 要素人氣時間序列（element popularity over time）
- **目標變數**：`share_d(w) = Σ_{i: 商品 i 表現要素 d} units(i, w) / Σ_i units(i, w)`，即要素 d 在第 w 週需求中的佔比。
- **為什麼是佔比而不是絕對量**：佔比把總量波動（促銷、季節、疫情）除掉，且直接對應製造商的問題
  「這一季我該把產能分給哪些要素」。副作用：佔比有加總為 1 的約束，多個要素的預測誤差不獨立（§2 統計部分要處理）。
- **文獻先例**：Fashion Forward（Al-Halah, Stiefelhagen & Grauman, ICCV 2017）[已核] 就是這一格。他們在 Amazon
  三個品類（Dresses 19,582 件／Tops&Tees 26,848／Shirts 31,594，2008–2013）上，把商品打成 1,000 維視覺屬性、
  再 NMF 出 30 個 style，以**月**為解析度建 style 佔比序列，2008–2011 訓練／2012 驗證／2013 測試。
- **標準評估**：他們用 MAE 與 MAPE（佔比遠離 0，所以 MAPE 在這裡還算安全），並在 §4.5 對**個別要素**報
  「預測的要素人氣排名與真實排名的交集率」：Top-10 **90%**、Top-25 **84%**、Top-50 **88%**[已核]。
  這個 **overlap@k 指標是本專案最該借用的東西**——它的輸出形狀跟 `element_gap` 的榜完全一樣。
- **但必須注意這篇的致命缺口**（§2 會再講）：§4.5 的 90% **沒有報 persistence 基線的 overlap@k**。
  一個緩慢移動的屬性排名，「照抄上個月」本來就有很高的交集率。所以那個 90% 單獨看等於沒有資訊量。

### B. 品類×顏色需求（category × colour demand）
- **目標變數**：`units(category, colour, w)`，或其佔比。這是 `engine02/panels.py::category_color_gap` 的時間序列版。
- **標準評估**：零售需求預測的主流，M5 家族指標（RMSSE／WRMSSE）。M5（Makridakis, Spiliotis &
  Assimakopoulos, IJF 2022）預測 Walmart 的 **42,840 條**階層銷售序列、底層要交 **30,490 個**點預測[已核，來自摘要]。
- **可行性**：H&M 直接給。這是六格裡**唯一可以在一天內從頭到尾做完、而且每個環節都有外部標準答案**的一格。
- **陷阱**：在 2–6 個月的前置期（h=8–26 週）上，reviewer 要求的基線「去年同週」**就是採購現在的做法**，
  而我們只有兩年資料（105 週），seasonal naive 幾乎是不可超越的強基線。詳見 §2 與 §6。

### C. 新品成功機率 / 新品銷量（new-style success）
- **目標變數**：新款上市後前 6–12 週的銷量（迴歸），或「是否進入銷量前 10%」（分類）。
- **這是時尚預測文獻的主戰場**，也是整份文件裡最該勸退的一格，因為數字很難看：

| 資料集／任務 | 最簡單基線 | 最佳公開結果 | 差距 |
|---|---|---|---|
| Visuelle 1.0，h=6 週，商品層級（5080 train／497 test） | Attribute-kNN **WAPE 59.8**（X-Att-RNN 59.5） | GTM-Transformer **54.2** | **−5.6 WAPE 點** |
| Visuelle 2.0，SO-fore 2-10，**item-shop** 層級（測試＝最新 10% item-shop 對） | Naive **118.18**、SES 111.27、kNN 91.13 | CrossAttnRNN+image **85.65** | 贏 Naive 32 點，但**只贏 kNN 5.5 點** |
| Visuelle 2.0，SO-fore 2-1（h=1 週） | Naive 101.92、SES 97.85、kNN 91.11 | CrossAttnRNN+image **86.71** | 同上 |
| Visuelle 2.0，**純需求預測**（只有圖、沒有任何過去觀測） | — | CrossAttnRNN w/ image **89.02** | 比有兩週觀測的版本差 |

（以上數字全部 [已核]，來自 arXiv:2109.09824 Table 1 與 arXiv:2204.06972 Table 1／Table 2。）
- **怎麼讀這張表**：WAPE 85% 的意思是「平均絕對誤差約等於銷量的 85%」。這是這個任務的**真實難度**，
  不是某篇論文做得爛。任何上台說「我們精準預測新品銷售」的人，都在跟這張表對賭。
- **文獻**：Ekambaram et al.（KDD 2020，Myntra）是 kNN 與 X-Att-RNN 基線的出處；Kunz et al.（Zalando, arXiv:2305.14406）
  的重點是**固定庫存假設迫使你把價格–需求關係模進模型**[已核，來自摘要]——我們連價格都沒有（H&M 的 price 是正規化值，
  見 `docs/research/catalog-options.md`）。

### D. 尺碼曲線（size curve）
- **需要**：尺碼層級的成交**與退貨**。文獻（Sheikh et al., RecSys 2019, doi:10.1145/3298689.3347006；
  Meta-Learning for Size and Fit, SDM 2020, doi:10.1137/1.9781611976236.7）用的全是平台內部退貨資料。
- **公開資料**：沒有。H&M articles 沒有尺碼欄位；KAGL／Polyvore／ESCI 都沒有。
- **判決**：**不能做，也不要在簡報上出現**。這一格對製造商最有價值，也最誘人亂講。

### E. 售罄率 / 折扣時機（sell-through）
- **需要**：庫存序列。只有 Visuelle 2.0 有（inventory、restocking、discount，per item-shop）[已核，該論文 Fig. 7]。
- **判決**：綁在 Visuelle 表單上，且即使拿到，庫存政策屬於 Nuna Lie，外推到聚陽客戶零意義。

### F. 缺口會不會實現（gap → realised demand）
- 這是 `docs/engine02-design.md` §3.22 已經自己寫明「**這個驗證不能宣稱什麼**：它沒有證明缺口能預測真實銷售」的那一格。
- **沒有任何公開資料能驗證它**，因為驗證需要「我們的查詢分布」與「同一市場的實際銷售」同時存在。
- **判決**：永久拒絕。這一格是整個專案最容易被評審一句話問死的地方，也是我們已經自己堵好的地方——**不要自己拆掉**。

---

## §2 基線就是全部：每個目標的必過基線、指標與「多少算贏」

### 2.1 reviewer 一定會要的基線（照 Hyndman FPP3 §5.2 的標準組）

| 目標 | 必過基線（缺一個就會被問死） | 為什麼 |
|---|---|---|
| A 要素佔比、B 品類×顏色 | ① **naive / persistence**：`ŷ = y_{t}`；② **seasonal naive**：`ŷ = y_{t+h−52}`（「去年同週」）；③ **MA(4)／MA(13)**；④ **drift**；⑤ **SES／ETS(A,N,N)** | 這是 FPP3 的四個 benchmark（MEAN／NAIVE／SNAIVE／RW+drift）加上 Fashion Forward 的贏家。**Fashion Forward 的最佳模型就是指數平滑**，ARIMA 與神經網路都沒有比它好[已核] |
| C 新品（無過去觀測） | **naive 不存在**（沒有過去）。必過基線是 ① **Attribute-kNN**（k=11，色＋品類＋材質相似商品的加權平均）；② **Image-kNN**；③ 同品類上一季平均 | Visuelle 1.0／2.0 兩篇都用這組，而且 **kNN 是強基線**：在 Visuelle 2.0 上 kNN 91.13 已經把 Naive 118.18 打掉 27 點[已核] |
| 排名型輸出（缺口榜、要素榜） | **persistence 的 overlap@k**（照抄上期前 k 名） | Fashion Forward §4.5 的 90% 交集率沒報這一項，**我們要報**。這是我們能比原論文更誠實的地方 |

**一句話版本**：贏 naive 沒有意義（naive 在 Visuelle 2.0 上 WAPE 118%，任何東西都贏它）。
**只有贏過「最強的那個簡單基線」才算贏**，而最強的簡單基線通常是 seasonal naive 或 attribute-kNN。

### 2.2 指標：為什麼是 MASE／RMSSE，不是 sMAPE

- **MAPE 在零售會壞掉**：`y_t = 0` 時未定義（賣 0 件在單品層級極常見），而且對高估與低估不對稱。
- **sMAPE 不要用**：FPP3 §5.8 明文引 Hyndman & Koehler (2006)「recommend that the sMAPE not be used」，
  理由是分母含預測值會讓計算不穩定，而且 sMAPE **可以是負的**，根本不是「絕對百分比誤差」[已核，原文引述]。
- **scaled error（MASE／RMSSE）**：Hyndman & Koehler (2006) 提出，把誤差除以**訓練段一步 naive 的 MAE**：
  `q_j = e_j / [ (1/(T−m)) Σ_{t=m+1}^{T} |y_t − y_{t−m}| ]`，`MASE = mean(|q_j|)`、
  `RMSSE = sqrt(mean(q_j²))`（非季節時 m=1）[已核，FPP3 §5.8 原式]。
  好處是**無單位**、跨序列可平均，而且**有絕對意義**：`MASE < 1` ⇔ 比訓練段的一步 naive 好。
- **M5 用的是 RMSSE**，加權成 WRMSSE（權重是各序列的累積銷售金額）；Uncertainty 賽改評九個分位
  （0.005, 0.025, 0.165, 0.250, 0.500, 0.750, 0.835, 0.975, 0.995）的加權 scaled pinball loss[分位點清單已核（Uncertainty 論文摘要）；
  「WRMSSE／WSPL」這兩個名字與權重定義來自 M5 官方組織論文（doi:10.1016/j.ijforecast.2021.07.007），我只讀到摘要 → 標 **未核**]。
  **選 RMSSE 的理由**：Walmart 的日銷是**間斷型計數**（大量 0），百分比誤差無法用；平方 scaled error 讓不同尺度的
  42,840 條序列可以加總成一個排行榜分數。
- **一個容易被講錯、但很重要的區別**：**間斷性是「聚合層級」的性質，不是「時尚」的性質**。
  我們的目標是**要素／品類層級的聚合佔比**，聚合之後 0 值消失、序列平滑 → M5 那套（RMSSE、pinball）是為
  item-store 層級設計的，**套到我們的聚合序列上是過度武裝**。在聚合佔比上，`MAE(佔比) + MASE` 就夠，
  MAPE 在這裡也還能用（Fashion Forward 的 MAPE 落在 3–25%，分母遠離 0）。**要在簡報上講清楚你在哪一層做**。
- **Kolassa (2020, doi:10.1016/j.ijforecast.2019.02.017)「最佳點預測取決於你用哪個誤差指標」**：MAE 最佳的點預測是
  **中位數**、RMSE 最佳的是**平均數**；間斷序列的中位數常常就是 0，所以**在單品層級用 MAE 當主指標，會讓「永遠預測 0」
  變成贏家**[指標–最佳點預測的對應關係已核為該文主張；具體推導我未讀全文 → 結論引用標 **未核**]。
  → **規則：任何人提議在單品層級用 MAE／MAPE 當主指標，直接否決。**
- 間斷序列若真要做，另有 MAAPE（Kim & Kim, IJF 2016, doi:10.1016/j.ijforecast.2015.12.003）與
  Kolassa (2016, doi:10.1016/j.ijforecast.2015.12.004) 主張改評**整個預測分布**而非點預測。我們不要走到這一步。

### 2.3 什麼樣的效果量才有意義

用文獻的實際差距當尺規（全部 [已核]）：

| 參考點 | 相對改善 |
|---|---|
| GTM-Transformer vs Attribute-kNN（Visuelle 1.0，WAPE 59.8→54.2） | **−9.4% 相對** |
| CrossAttnRNN+image vs kNN（Visuelle 2.0 SO-fore 2-10，91.13→85.65） | **−6.0% 相對** |
| Fashion Forward vs persistence（Dresses，MAE 0.0192→0.0146） | **−24% 相對** |
| Fashion Forward vs drift（Tops&Tees，MAE 0.0158→0.0145） | **−8% 相對（幾乎打平）** |
| Fashion Forward vs ARIMA（Shirts，MAE 0.0092→0.0088） | **−4%（在信賴區間內大概不顯著）** |

**建議的門檻**：對**最強**基線的相對改善 **≥10%**，且配對檢定 p<0.01（多重比較校正後）。
理由：10% 是上表裡「真的被同行接受為貢獻」的量級下限；低於 10% 的差距在 Fashion Forward 自己的表裡就已經
跟簡單模型互有勝負。**低於 10% 就當成 null result 記錄下來，照 §3.15 趨勢關鍵字的處理方式辦**。

### 2.4 樣本數與統計：三個會被抓到的坑

1. **配對單位必須是「序列」，不是「(序列, origin)」對。** rolling origin 產生的預測窗互相重疊，
   同一條序列的相鄰 origin 高度相關。正確做法：**先在 origin 上對每條序列平均**，再對序列做配對置換檢定
   （`engine02.eval.metrics.paired_permutation_test`）與 bootstrap CI。把 (序列×origin) 當獨立樣本會把 p 值灌到假的小。
2. **n 要夠。** 我們只有 **15 個設計要素**（`engine02/resources/kansei_v1_literature.json`），其中能對上 H&M 原生標籤的
   約 **6–8 個**（§3.4）。n=8 的配對置換檢定最小可能 p 值是 `2⁻⁸ ≈ 0.0039`，勉強能過 0.01，**但沒有任何餘裕**。
   → **分析單位必須下降到「要素 × garment_group」細格**（8 × 21 ≈ 最多 168 條序列，過量濾網後大概 60–120 條），
   否則這個實驗在設計上就不可能達到統計顯著。**這一點請 coordinator 特別注意，它決定實驗做不做得出來。**
3. **多重比較與加總約束。** 一次測 30 個要素就要 Holm 或 BH 校正；而且佔比加總為 1，
   各要素誤差負相關 → bootstrap 要**對序列重抽**而不是對觀測重抽。
4. **（可選）Diebold–Mariano 檢定**是預測比較的正統做法，但 h>1 時窗重疊要用 HAC 變異數與
   Harvey–Leybourne–Newbold 小樣本校正[未核]。本專案已有配對置換的房規，**建議維持房規、不要多開一套**。

---

## §3 哪個公開資料真的有時間軸？

### 3.1 逐一判決

| 資料集 | 授權 | 顆粒度 / 期間 | 有圖？ | 一天內能不能用？ |
|---|---|---|---|---|
| **Visuelle 1.0**（arXiv:2109.09824；J. Forecasting 2024, doi:10.1002/for.3104） | **未標示**。Nuna Lie 釋出供研究，需填 Google 表單取得連結[已核] | 5,577 件新品，2016–2019，週銷（12 週生命週期），含 tags、52 週 Google Trends | **有**（每件一張商品圖） | **有條件**：表單自動回連結則 10 分鐘可下載；GTM repo 給了完整參考實作與 5080/497 切分。**但只能離線評測，不可出貨** |
| **Visuelle 2.0**（CVPRW 2022, arXiv:2204.06972） | 同上，另一份表單[已核] | 5,355 件，6 季（疫情前），**item-shop** 層級銷售＋庫存＋補貨＋折扣＋天氣＋667K 匿名顧客購買 | **有**（HD 圖） | **有條件**，同上。任務（SO-fore 2-10／2-1）定義清楚，測試集＝**最新 10% item-shop 對** |
| **POP signals**（ECCV 2022, arXiv:2207.11001） | repo 內直接給訊號檔[已核] | 對齊 Visuelle 商品 ID 的外生「潛在表現」序列 | — | **訊號拿得到，但沒有 Visuelle 的銷售就沒用**（鑰匙有、鎖沒有） |
| **H&M Personalized Fashion Recs**（Kaggle 2022；HF 鏡像 `einrafh/hnm-fashion-recommendations-data`，非 gated[已核]） | 鏡像**未標授權**；上游是**競賽規則**（非商業、限競賽用途） | **transactions 31,788,324 筆**，`t_dat` **2018-09-20 → 2020-09-22（105 週）**；**articles 105,542**；customers 1,371,980[全部已核] | **鏡像無圖**。圖在另一份 `tomytjandra/h-and-m-fashion-caption`（20,491 筆 text+image，約 19%） | **能，而且是首選**。§6 給了完整可實作規格 |
| **M5 / Walmart**（IJF 2022） | 競賽資料，公開可得 | 42,840 條階層日銷序列，2011–2016 | 無 | **方法學參考用**。品類是食品／家用／嗜好，**沒有服飾**[未核（品類清單來自 M5 組織論文，我只讀到摘要）] |
| **Corporación Favorita**（Kaggle 2017–18；HF 有 `THULab/favorita_*` 局部鏡像[已核存在]） | 競賽規則 | 厄瓜多雜貨日銷，2013–2017 | 無 | **方法學參考用**。雜貨、無服飾、無要素 |
| **Amazon Reviews 2023**（`McAuley-Lab/Amazon-Reviews-2023`，非 gated、卡片**未標授權**[已核]） | 未標示 | 評論帶時間戳，Clothing/Shoes/Jewelry 子集，商品 metadata 含圖片 URL | 圖為外連 URL | **能，但是代理指標**。Fashion Forward 就是這樣做的（評論數當銷售代理）。缺點：評論 ≠ 銷售、抓圖＝複製零售商素材 |
| **我們現有的四份語料**（KAGL 44k／Polyvore／H&M caption／ESCI） | 見 `docs/research/external-benchmarks.md` | **全部沒有日期** | 有 | **不能做任何預測** |
| 「Fashion Dataset with sales」類 Kaggle 雜牌資料 | 多為 unknown／NC | 通常是爬蟲快照，**沒有真正的時間軸** | 外連圖 | **不要用**。這類資料是 demo 事故的主要來源 |

### 3.2 Visuelle 的完整判決（你最想要的那一個）

**技術上可用。策略上不要放在關鍵路徑。理由四點：**

1. **取得路徑有第三方依賴。** 兩個版本都只能透過 Google 表單拿下載連結（`forms.gle/cVGQAmxhHf7eRJ937`），
   HuggingFace **沒有任何鏡像**（我用 `visuelle`、`nunalie` 搜過 HF datasets API，零結果[已核]）。
   表單若是自動回連結就是 10 分鐘的事；若是人工審核就是**不可控的等待**。
   → **處置：現在就去填表（成本 2 分鐘），但把它當 30 分鐘的 spike 加一個硬性 go/no-go，主線走 H&M。**
2. **授權是最弱的一環。** 卡片與論文都沒有授權條款，它是一家公司的內部銷售資料「for research and innovation purposes」。
   跟 `docs/research/external-benchmarks.md` 對 DeepFashion 的處置一致：**離線評測可以，不可出貨**。
   給贊助商看的東西裡不能有它的數字當賣點。
3. **它支撐的任務正好是最難看的那一格。** 見 §1.C 的表。就算完整跑通，能講的話是
   「我們重現了一個 WAPE 54% 的結果，比 kNN 好 5 個百分點」。對製造商評審，這不是加分項，是**送給對手的問題**。
4. **它的要素詞彙不是我們的要素詞彙。** Visuelle 的 tags 是 Nuna Lie 的 category／colour／fabric，
   測試集只有 **497 件商品**。用它擬合出來的 β_d prior，是**一家義大利品牌 2019 年一季的先驗**，
   外推到聚陽 2026 年的訂單毫無根據——而 §3.19 已經教過我們，這種「標準答案是別人的、或是自己填的」的數字有多危險。

**如果表單通了，該跑的實驗（照官方協定，不要自己發明）：**
- 切分：5,080 train / **497 最新商品** test（Visuelle 1.0）；或最新 10% item-shop 對（Visuelle 2.0）。
- 目標：h=6 週（模型以 12 週訓練後再截短評估，這是原文的做法）。
- 基線：Attribute-kNN（k=11，cosine）／Image-kNN／Attr+Image-kNN／SES／Naive。
- 指標：WAPE（主）、MAE、Tracking Signal（|TS|>3.75 算系統性偏誤）、ERP。
- **我們唯一該加的東西**：把 `engine02` 的 `c(i,d)` 當成商品特徵餵進 kNN 的距離，看它**是否勝過原本的
  attribute 距離**。這是「我們的要素表徵有用嗎」的問題，不是「我們會預測銷售」的問題，**而且它可證偽**。
  這個框架下 null result 也有價值（就是 §3.15 的處理方式）。
- **不該做的事**：宣稱我們在 Visuelle 上「做了預測」。我們是在測一個表徵。

### 3.3 為什麼 H&M 是首選（含已核實的欄位證據）

`transactions`：`t_dat, customer_id, article_id, price, sales_channel_id`，首列 `2018-09-20`、末列 `2020-09-22`[已核]。
`articles` 的可用要素欄位與基數[已核]：

| 欄位 | 基數 | 主要值 |
|---|---|---|
| `graphical_appearance_name` | 30 | Solid 49,747／All over pattern 17,165／Melange 5,938／Stripe 4,990／Denim 4,842／Front print 3,215／Placement print 3,098／Check 2,178／Lace 1,513／Glittering-Metallic 958／Sequin 806／Dot 681 |
| `perceived_colour_value_name` | 8 | **Dark 42,706**／Dusty Light 22,152／Light 15,739／Medium Dusty 12,630／**Bright 6,471**／Medium 5,711 |
| `colour_group_name` | 50 | — |
| `perceived_colour_master_name` | 20 | — |
| `garment_group_name` | 21 | Jersey Fancy 21,445／Knitwear 7,490／Trousers 6,727／Blouses 5,838／Dresses Ladies 4,874／Shirts 2,116／Dressed 908 |
| `product_type_name` | 131 | — |
| `index_group_name` | 5 | Ladieswear 39,737／Baby-Children 34,711／Divided 15,149／Menswear 12,553／**Sport 3,392** |
| `detail_desc` | 自由文字 | 例：「Knee-length shorts in soft washed cotton with an elasticated drawstring…」 |

### 3.4 我們 15 個要素能對上幾個 H&M 標籤（決定實驗做不做得出來）

| 我們的要素 | H&M 標籤對應 | 強度 |
|---|---|---|
| `dark_tone` 低明度深色 | `perceived_colour_value_name == 'Dark'` | **強** |
| `bright_color` 鮮豔色彩 | `== 'Bright'` | **強** |
| `minimal_design` 素面簡約 | `graphical_appearance == 'Solid'` | **強** |
| `bold_pattern` 強烈圖案 | `'All over pattern' ∪ 'Front print' ∪ 'Placement print' ∪ 'Other pattern'` | **強** |
| `glossy_fabric` 亮面材質 | `'Glittering/Metallic' ∪ 'Metallic' ∪ 'Sequin' ∪ 'Hologram'` | **中**（數量少，約 2.1k） |
| `soft_knit` 柔軟針織 | `garment_group == 'Knitwear'` | **中** |
| `athletic_style` 運動機能風格 | `index_group == 'Sport'` | **中**（是商業部門，不是視覺要素） |
| `formal_style` 正式感 | `garment_group ∈ {'Dressed','Shirts'}` | **弱** |
| `visible_logo` 明顯 logo | `'Front print'`（與 bold_pattern 重疊，**不可同時計入**） | **弱** |
| `relaxed_fit`／`tailored_fit`／`crisp_collar`／`matte_fabric`／`structured_shoulders`／`casual_style` | 只能從 `detail_desc` 抓關鍵字（"loose fit"／"slim fit"／"collar"／"satin"） | **不可用**（代理的代理） |

→ **可用要素 4 強 + 3 中 = 7 條**。這就是為什麼 §2.4 說**分析單位必須是「要素 × garment_group」細格**。

---

## §4 我們的缺口盤是預測嗎？不是。而且要精確地說「不是」

### 4.1 它到底在算什麼（逐項拆解）

`engine02/panels.py::element_gap`：

- 需求側：`D_d = Σ_{sessions} (needs_beta + fb_beta)_d`，其中 β_d 由 `engine02/kansei.py::Kansei.beta` 從
  **本次查詢宣告的需求機率與回饋步數**算出（正負分開、不相消）。
- 供給側：`S_d = mean( c(:, d) > τ )`，目錄中表現該要素的商品比例。
- 輸出：`Gap_d = |D_d / Σ|D|| × (1 − S_d)`（想避開的要素則乘 `S_d`）。

**三個項全部在時間點 t 量測。** 這是一個**現況陳述**：
> 「在本服務收到的這 N 句查詢裡，要素 d 佔了被宣告需求的 x%，而目錄裡只有 y% 的商品表現它。」

這句話**完全正確、可稽核、而且已經被驗證是在回應正確的東西**（T14：遮掉表現該要素的商品 → MRR 0.381→0.509，
p<1e-4；遮掉同樣件數的隨機商品 → 0.380，p=1.00，`docs/engine02-design.md` §3.22）。
它**不是**預測，缺三樣東西：

1. **沒有時間索引。** `engine02/api.py::_record_demand` 把需求存進一個 `deque(maxlen=500)`，
   元素是 `(needs_probs, adjust_steps, (category, colour))`——**沒有時間戳**，而且在 process 記憶體裡、重啟即消失。
2. **沒有樣本外的未來目標。** 沒有「下一期」可以比對。
3. **沒有外部分母。** 需求側是我們自己的查詢，不是市場。

### 4.2 循環性陷阱（這一節是本文件最重要的一段）

**如果我們用「自己未來的查詢」來評估「對需求的預測」，那是自我實現的。**
需求側 = 本服務收到的查詢分布；能決定這個分布的人是**使用者、也就是現場的我們自己與少數評審**。
一個預測「下週我們的查詢會問什麼」的模型，預測的是**我們自己的輸入**，不是市場。更糟的是它可以被刻意灌票：
多打幾句同樣的查詢，「趨勢」就出現了。**這種指標在示範現場的可操縱性是 100%。**

這正是 `docs/engine02-design.md` §3.19 那個「差點寫錯的結論」的同一個病：當標準答案是自己的元件產生的，
數字就是循環的（當時是 Qwen3-VL 補的 `occasion` 欄位被拿去當 VLM 打分的標準答案）。
**規則推廣：凡是標準答案由我們自己的元件或自己的輸入產生，就不可以叫「驗證」，只能叫「一致性檢查」。**

順帶說一個**供給側也有的、但無害的循環**：`scripts/eval_gap.py` 用 `c(i,d) > τ` 決定「哪些商品表現該要素」，
而供給側也是 `c(i,d) > τ`。所以 T14 是**機制檢查**（這個指標是在回應特定要素的供給，不是回應目錄變小），
**不是外部驗證**。腳本的 docstring 已經誠實寫了這件事——保持原樣。

### 4.3 最小的誠實升級（如果非要有「時間」這個字）

不要叫預測，叫**「本場需求變化」**。實作代價約 20 分鐘：

- `engine02/api.py::_record_demand`：在 tuple 裡加一個 `time.time()`（或單調序號）。這是唯一必要的既有檔案改動。
- 新增 `engine02/panels.py::element_gap_delta(engine, sessions_with_ts, window, arm, threshold)`：
  把 log 切成最近 `window` 筆與前一段 `window` 筆，回報
  `Δshare_d = share_d(近) − share_d(遠)`，**並且同時回報兩段的 n**。
- 顯著性：share 的差用 multinomial／bootstrap 給 CI。**n < 30 就直接回傳 `insufficient_data`，不要畫箭頭。**
  沒有這道閘門，2 句查詢的變動會在畫面上長成一支趨勢箭頭，那是會被抓的。
- 文案：`「本場 N 句查詢中，要素 d 的需求佔比由 x% 變為 y%（樣本 n₁/n₂，非市場量測）」`。
  跟 `/gap/cells` 已經有的 `note: "需求側 = 本服務實際收到的查詢，不是市場量測"` 同一個口氣。

**上限要講清楚**：`maxlen=500`、in-process、重啟清空。現場實際 n 大概是 20–50。
**在這個 n 下沒有任何「趨勢」是真的。** 這個面板的價值是「讓評審看到系統在記錄需求」，不是預測。

---

## §5 上台要講的那句話：三個候選，遞減的野心

### S1（高野心｜**建議拒絕**）
> 「我們預測下一季會上升的設計要素。」

- **現有證據**：**零**。我們沒有任何帶日期的銷售資料，`element_gap` 沒有時間軸，趨勢關鍵字實驗（§3.15，T11）
  是**負面結果**：28 組設定全部讓 NDCG@5 下降 0.16–0.38（p≈1e-4），而且手動維護清單只比**隨機字詞**好一點
  （44k：−0.266 vs −0.301）。我們唯一一次碰「趨勢訊號」的經驗是它幾乎和隨機字詞無法區分。
- **敵意評審會問**：「跟去年同期比，你贏了嗎？用什麼資料驗的？樣本多少？」
- **答案**：沒有資料、沒驗過、不能回答。**所以不要講。**
- **另外**：`docs/research/engine02-completeness.md` §2.1 記錄「主辦方已有內部趨勢平台，且明確排除趨勢預測系統」。
  講 S1 等於**離題**＋**在對方主場挑戰對方的既有系統**。

### S2（**今天的證據支持這一句，建議當主標**）
> 「我們量化**被問到、但目錄給不出來**的設計要素缺口。而且這個指標是可否證的：把表現該要素的商品從目錄裡移除，
> 它在缺口榜的排名會顯著上升（MRR 0.381 → 0.509，排第一 28.9%，p<1e-4）；移除**同樣件數**的隨機商品，
> 排名完全不動（0.380，p=1.00）。需求側的分母是本服務實際收到的查詢，寫在每一份回應裡。」

- **現有證據**：T14（`scripts/eval_gap.py`，KAGL 44k、Marqo-FashionSigLIP 真 encoder、45 次試驗，
  `docs/engine02-design.md` §3.22）。外加 T3 的 `c(i,d)` AUROC（`full` 反義詞版在乾淨標籤下 0.85–0.98，
  隨機字詞對照 0.47–0.63，§3.19）與 T4 理由忠實度 100%。
- **敵意評審會問 1**：「缺口能預測銷售嗎？」
  **答**：**不能，我們也沒有這樣宣稱。** 它量的是「這個目錄被問到什麼、而目錄裡沒有什麼」。要預測銷售
  需要帶日期的成交資料，公開資料裡最好的（Visuelle）在單品層級的 SOTA 誤差是銷量的 54–86%，
  我們不會在一天內解決那個問題，也不會假裝解決了。
- **敵意評審會問 2**：「需求側是你們自己的查詢，那不就是你們說什麼就是什麼？」
  **答**：對，所以分母寫在回應裡（`n_sessions`），而且我們把它叫「本服務收到的需求」而不是「市場需求」。
  正式上線時需求側要換成聚陽自己的客戶詢價／訂單文字，或接他們的內部趨勢平台——換掉分母，公式不用改。
- **敵意評審會問 3**：「這個指標會不會只是在反映『目錄變小』？」
  **答**：那正是我們設計對照組的原因。隨機移除同樣件數，排名 p=1.00 完全不動。而且第一版實驗設計是錯的
  （只給單一要素需求時它永遠排第一），我們把它改掉並寫進文件了。

### S3（低野心｜**建議當開場的框架句**）
> 「我們把自由文字的消費者需求，轉成工廠可以動作的**要素級規格**——而且每張卡片的理由加總剛好等於它的分數。」

- **現有證據**：T1 檢索、T3 要素分數 AUROC、T4「最小充分集合」理由（100% 有理由、100% 足夠，隨機理由 12–16%）、
  §3.21 的 12 ms 延遲、`/gap/elements` 與 `/gap/cells` 兩個端點。
- **敵意評審會問**：「那不就是個檢索系統？」
  **答**：差別在輸出層級與可稽核性。檢索系統輸出商品；我們輸出**要素**（肩線挺、素面簡約、低明度深色…）
  加上供給缺口，這是 2–6 個月前置期的開發會議能直接用的東西。而且每個分數可以拆回貢獻項，加總相等（有測試守著）。

### 判決
**S3 當框架、S2 當主張、S1 明確不講。** 而且建議在簡報上**主動**放一句
「我們**不**宣稱預測銷售，理由是 ⟨Visuelle 的 SOTA 數字⟩」——主動說出自己不能做什麼，
在有製造業評審的場合是加分項，而且會把最危險的那個問題從敵意提問變成我們自己的論點。

---

## §6 如果真的拿到帶日期的語料：端到端 backtest 規格（可直接實作）

以下寫成 H&M 路線（最可能發生）。Visuelle 路線的差異寫在 §6.8。

### 6.1 資料建構
- 來源：HF `einrafh/hnm-fashion-recommendations-data`，configs `transactions`（31,788,324 列）與 `articles`（105,542 列）。
- 建議新腳本 `scripts/build_hm_timeseries.py`（**新檔**）：
  1. 只取 `index_group_name == 'Ladieswear'`（避免童裝／運動混入改變佔比的意義；要跑第二組就換這個值）。
  2. `t_dat` → ISO 週；範圍 2018-W38 … 2020-W39，共 **105 週**。
  3. 要素指示函數 `1[i ∈ d]` 用 §3.4 的**強／中**七項對應（`visible_logo` 因與 `bold_pattern` 重疊而**排除**）。
  4. 輸出 `units[d, g, w]`（d=要素、g=`garment_group_name`、w=週）與分母 `units[·, g, w]`，
     目標變數 `share[d, g, w] = units[d,g,w] / units[·,g,w]`。
  5. **最小量濾網**：只保留全期週均 `units[·, g, w] ≥ 200` 且 `units[d, g, ·]` 非零週數 ≥ 80% 的細格。
     預期剩 **60–120 條序列**（這就是統計檢定的 n）。輸出 CSV 到 `reports/`（不進 git）。
- 授權處置：**只在本機／nycu 離線評測，結果數字不得出現在對外簡報作為產品能力宣稱**，
  與 `docs/research/external-benchmarks.md` 對 DeepFashion 的處置一致。

### 6.2 切分與 rolling origin（Hyndman FPP3 §5.10 time series cross-validation）
- origin 從**第 53 週**開始（讓 seasonal naive 有 `y_{t−52}` 可用），每次前進 1 週。
- 水平 **h ∈ {4, 13, 26}**（對應約 1 個月／1 季／半年；2–6 個月前置期主要看 h=13 與 h=26）。
- 可用 origin 數：`origins(h) = 105 − 52 − h + 1` → **h=4：50 個、h=13：41 個、h=26：28 個**。
  **h > 26 不要做**，origin 數不足以支撐任何結論。
- 訓練資料只用 origin 以前（嚴格單向；不得用未來週做正規化、不得用全期算 z-score）。

### 6.3 基線（全部要跑，不能只挑弱的）
1. `naive`：`ŷ = y_{w0}`
2. `seasonal_naive`：`ŷ = y_{w0+h−52}`（**去年同週；這是採購現行做法，是最關鍵的對手**）
3. `ma4`、`ma13`：最近 4／13 週平均
4. `drift`：`y_{w0} + h·(y_{w0} − y_{w0−k})/k`
5. `ses`：Simple Exponential Smoothing（**Fashion Forward 的贏家**，α 在 origin 前的資料上選）
6. （B 目標另加）`attribute_knn`：k=11，用 `c(i,·)` 或 H&M 標籤算商品相似度，加權平均鄰居的歷史 share

候選模型必須**贏過以上全部**才算贏。只贏 `naive` 一律視為沒有結果。

### 6.4 指標
- **主**：`MASE`（分母＝origin 前訓練段的一步 naive MAE，m=1）。**同時報 m=52 的季節版**，
  但註明只有 2 年資料時季節分母不穩。
- **輔**：`RMSSE`（與 M5 同族，便於外部對照）、`MAE(share)`（絕對可讀性）。
- **排名型**：`overlap@10`——把每個 garment_group 內的要素按預測 share 排序，取前 10（或 min(10, 可用要素數)）
  與真實前 10 的交集比例。**必須同時報 persistence 的 overlap@10**（Fashion Forward §4.5 沒報，這是我們的加分點）。
- **禁用為主指標**：MAPE、sMAPE（Hyndman & Koehler 2006；FPP3 §5.8）。可以在附錄報，但不作為結論依據。

### 6.5 統計檢定
1. 每條序列先在其所有 origin 上把 MASE 平均（處理窗重疊造成的相依）。
2. 對「序列」做 `paired_permutation_test`（10,000 次）＋ `bootstrap_ci`（對序列重抽）。
   兩者都在 `engine02.eval.metrics`，維持房規。
3. 每個 (模型, 基線, h) 組合一個檢定 → 用 **Holm** 校正家族錯誤率。
4. 固定 seed，記錄在輸出 JSON 裡。

### 6.6 COVID 斷點（必做，否則結論會被推翻）
2020-03 之後是 regime break。**同時報兩版**：
(a) 全期；(b) 排除 2020-W10 之後的 origin（h=26 時剩約 10 個 origin，要註明樣本不足）。
兩版不一致時，**以 (b) 為主結論並照實說明**，不得只報好看的那一版。

### 6.7 出貨 β_d prior 的最小門檻（gate；四個條件全過才動預設）
1. **統計**：在 **h=13** 上，候選模型的 MASE 相對**最強基線**改善 **≥10%**，Holm 校正後 **p<0.01**；
   且在 h=4 與 h=26 至少一個方向一致、另一個不顯著變差。
2. **排名**：`overlap@10` 至少比 persistence 高 **5 個百分點**（配對檢定 p<0.05）。
3. **詞彙可轉移**：預測得準的要素中，**至少 5 個**能對回 `kansei_v1_literature.json` 的 `design_elements`
   （§3.4 的強／中項）。少於 5 個 → prior 無法轉移，無論 MASE 多好都**不出貨**。
4. **排序代價**：照 §3.16 概念圖的做法，先量代價再定權重。形式
   `β_d ← β_d + λ · ẑ_d`（`ẑ_d` = 預測要素需求成長的池內標準化值），λ 掃 {0.05, 0.1, 0.2, 0.5}，
   **只有在內部 NDCG@5 不顯著下降的最大 λ** 才能採用。若所有 λ 都讓 NDCG@5 顯著下降，
   **退回展示標籤**——這正是 §3.15 對趨勢關鍵字做過的處置，不要重犯同一個錯。

四條任一不過 → **記成 null result 寫進 §3**，不改任何預設。負面結果本身就是交付物。

### 6.8 Visuelle 路線的差異
- 用官方協定：5,080 train / **497 最新商品** test；h=6 週（模型以 12 週訓練）；
  指標 WAPE（主）／MAE／Tracking Signal（|TS|>3.75 為系統性偏誤）／ERP。
- **必過基線**：Attribute-kNN（**WAPE 59.8**）、Image-kNN（62.2）、Attr+Image-KNN（61.3）、GBoosting（64.1）、
  Cat-MM-RNN（63.3）、X-Att-RNN（**59.5**）。
  參考天花板：GTM-Transformer **55.2**／**54.2**（用 Fashion IQ 自動抽 tag 的版本）。
- **我們唯一該問的問題**：把 `c(i,d)` 當 kNN 的距離特徵，能不能贏過原本的 attribute 距離？
  這是「表徵有效性」問題，可證偽，而且 null 也能寫。
- **不要**試圖超越 GTM-Transformer。那不是一天的工作，而且贏 5 個 WAPE 點在台上講不出價值。

### 6.9 （選配）把圖接回來，讓 `c(i,d)` 進入真實銷售的迴路
H&M 鏡像沒有圖，但 `tomytjandra/h-and-m-fashion-caption`（20,491 筆）的 caption 是
**`graphical_appearance` + 顏色 + `detail_desc` 的正規化串接**——實測首列
`"solid black jersey top with narrow shoulder straps"` 對應 `Solid` + `Black` + detail_desc[已核]。
因此可以：正規化（小寫、去標點）後與 `articles` 的 `appearance+colour+detail_desc` 做字串 join → 取得 `article_id`
→ 接上 transactions。**閘門：match rate < 60% 就放棄這條路**，改用 H&M 原生標籤（§6.1）。
**重要**：`c(i,d)` 必須只從**圖片**算（Engine02 本來就用 image embedding），
因為 caption 文字裡就寫著 `Solid`／顏色——用文字算會是標籤洩漏。

---

## 給 coordinator 的建議

### 要建的（合計約 2 小時，全部是新檔，除了一個 20 分鐘的既有檔案 hook）
1. **[P0，20 分鐘，唯一需要改既有檔案的項目]**
   `engine02/api.py::_record_demand` 加時間戳（tuple 多一個 `time.time()`）。
   這是所有「時間」相關敘事的前提，而且不加的話連「本場需求變化」都做不到。
2. **[P0，40 分鐘，新檔]** `engine02/panels.py::element_gap_delta`（或放新模組避免動既有檔案，
   例如 `engine02/gap_delta.py::element_gap_delta`）：窗對窗的需求佔比差，**回傳兩段的 n**，
   `n < 30` 回 `insufficient_data`。外加 `GET /gap/elements/delta` 端點。
   **文案一律用「本場需求變化」，不得用「趨勢」或「預測」。**
3. **[P1，只在有人堅持要預測時做，約 2 小時，新檔]**
   `scripts/build_hm_timeseries.py` ＋ `scripts/eval_forecast.py`，照 §6.1–6.6 實作。
   這是**唯一**能在可得資料下誠實支撐任何預測語言的路徑。
4. **[P2，2 分鐘，零風險]** 現在去填 Visuelle 的表單（`forms.gle/cVGQAmxhHf7eRJ937`）。
   拿到就當 bonus，拿不到不影響任何事。**不要排進關鍵路徑。**

### 要宣稱的
- **主標：S2**（缺口可量化且可否證，T14 有數字）。
- **框架句：S3**（自由文字 → 要素級規格）。
- 主動說出：「我們不宣稱預測銷售」，並附上 Visuelle SOTA 的 WAPE 54–86% 當理由。
  **把最危險的問題變成自己的論點。**

### 要拒絕宣稱的（寫進簡報的自我限制清單）
- ❌ 「預測下一季流行的設計要素」——零證據，且贊助商已排除趨勢預測。
- ❌ 「預測銷售／售罄率」——沒有任何帶日期的銷售資料，且 SOTA 誤差等於銷量本身。
- ❌ 「預測尺碼曲線」——需要退貨資料，公開資料完全沒有。
- ❌ 「缺口高的要素明年會賣得好」——**這是最危險的一句**，沒有任何資料能驗證它，
  而 §3.22 已經自己寫明不能宣稱。不要自己拆掉自己的護欄。
- ❌ 在需求側 n < 30 的情況下畫任何趨勢箭頭。

---

## 反方意見（反對做任何預測宣稱的最強論證）

**如果只能留一段，留這一段。**

1. **贊助商自己把這件事排除了。** `docs/research/engine02-completeness.md` §2.1：
   「主辦方已有內部趨勢平台，且明確排除趨勢預測系統」。做預測宣稱不只是證據薄弱，
   是**在對方的主場、用一天的工作量、挑戰對方長期營運的系統**。輸的機率接近 1，而且離題。
2. **我們唯一一次碰趨勢訊號，結果是負的。** §3.15（T11）：28 組設定全部讓 NDCG@5 下降 0.16–0.38（p≈1e-4），
   而且手動維護的趨勢清單只比**隨機字詞**好一點點。我們對「趨勢訊號」的實測經驗是：**幾乎測不出它和隨機的差別**。
3. **這個任務在文獻上的誠實難度，講出來對我們不利。** Visuelle 2.0 item-shop 層級最佳 WAPE 85.65%、
   Naive 118.18%；Visuelle 1.0 商品層級最佳 54.2%、Attribute-kNN 59.8%。
   任何預測宣稱的誠實版本都是「我們的預測誤差約等於銷量的一半到全部」。
   **這句話一旦出現在有製造業評審的場合，會抵銷掉前面所有正確的東西。**
4. **在我們真正在意的前置期（2–6 個月）上，reviewer 的基線就是業界現行做法，而且大概無法被超越。**
   h=26 週時 `seasonal naive`＝「去年同週」＝採購現在就在做的事。在 105 週（其中最後半年是疫情）、
   沒有價格、沒有行銷日曆、沒有外生訊號的條件下，贏它的先驗機率很低。
   而**輸給「去年同週」的預測系統，在製造商眼裡不是不完美，是沒有用**。
5. **每一份帶日期的語料授權都不乾淨。** Visuelle 無授權條款、H&M 是競賽規則、Amazon Reviews 卡片未標、
   Favorita 是競賽規則。凡是建在這些資料上的能力**都不能出貨**，只能離線評測。
   一個「不能出貨的預測能力」當賣點，是一張會被法務退回的簡報。
6. **外部效度是零。** 就算全部做成了，結論是「一家義大利快時尚（或一家瑞典快時尚）在 2018–2020 的
   某個市場、某些標籤上，某個模型比 seasonal naive 好 x%」。
   把它講成「聚陽 2026 年該開發什麼」之間有一道無法用資料跨過的鴻溝。
7. **機會成本最實在。** 做這件事的時間會擠掉已經可辯護的東西（T14 的缺口盤、T15 的疲勞項、12 ms 的延遲、
   理由忠實度）。**用已經量過的東西講一個小而硬的故事，勝過用沒量過的東西講一個大而軟的故事。**

**反方的結論**：不要做預測宣稱。做 §5 的 S2，把 S1 明確地、主動地拒絕掉，
並把「我們拒絕宣稱什麼、以及為什麼」本身當成一張投影片。
在一個充滿「AI 預測流行趨勢」提案的會場，**唯一一組說得出自己做不到什麼、而且說得出數字的隊伍**，
記憶點比多一個沒驗證的功能高。

---

## 參考文獻與核實狀態

### 預測方法學
1. Hyndman, R. J. & Koehler, A. B. (2006). *Another look at measures of forecast accuracy*. **IJF** 22(4), 679–688.
   doi:10.1016/j.ijforecast.2006.03.001 — MASE 的出處；明確建議**不要用 sMAPE**。[書目已核；主張經 FPP3 §5.8 轉引已核]
2. Hyndman, R. J. & Athanasopoulos, G. *Forecasting: Principles and Practice* (3rd ed.).
   §5.8 Evaluating point forecast accuracy（scaled errors、MASE／RMSSE 原式、sMAPE 不建議使用）、
   §5.10 Time series cross-validation（rolling origin）。<https://otexts.com/fpp3/accuracy.html> [已核，原文引述]
3. Makridakis, S., Spiliotis, E. & Assimakopoulos, V. (2022). *M5 accuracy competition: Results, findings, and conclusions*.
   **IJF** 38(4). doi:10.1016/j.ijforecast.2021.11.013 — 42,840 條 Walmart 階層序列、底層 30,490 個點預測。
   [摘要已核；指標名稱 WRMSSE 與權重定義**未核**]
4. Makridakis, S. et al. (2021). *The M5 uncertainty competition: Results, findings and conclusions*. **IJF**.
   doi:10.1016/j.ijforecast.2021.10.009 — 九個分位 (0.005, 0.025, 0.165, 0.25, 0.5, 0.75, 0.835, 0.975, 0.995)。[摘要已核]
5. Makridakis, S. et al. (2022). *The M5 competition: Background, organization, and implementation*. **IJF**.
   doi:10.1016/j.ijforecast.2021.07.007 — RMSSE／WRMSSE 的正式定義出處。[**未核**，只取得 OA 連結]
6. Makridakis, S., Spiliotis, E. & Assimakopoulos, V. (2019). *The M4 Competition: 100,000 time series and 61
   forecasting methods*. **IJF** 36(1), 54–74. doi:10.1016/j.ijforecast.2019.04.014 — 摘要已核（含預測區間評估）；
   「以 sMAPE 與 MASE 的 OWA 評分」這個細節 **未核**。
7. Kolassa, S. (2020). *Why the "best" point forecast depends on the error or accuracy measure*. **IJF** 36(1), 208–211.
   doi:10.1016/j.ijforecast.2019.02.017 — MAE↔中位數、RMSE↔平均數。[書目已核；內容**未核**]
8. Kolassa, S. (2016). *Evaluating predictive count data distributions in retail sales forecasting*. **IJF** 32(3).
   doi:10.1016/j.ijforecast.2015.12.004 [書目已核]
9. Kim, S. & Kim, H. (2016). *A new metric of absolute percentage error for intermittent demand forecasts*.
   **IJF** 32(3), 669–679. doi:10.1016/j.ijforecast.2015.12.003（MAAPE）[書目已核]

### 時尚／零售預測
10. Skenderi, G., Joppi, C., Denitto, M. & Cristani, M. *Well Googled is Half Done: Multimodal Forecasting of New
    Fashion Product Sales with Image-based Google Trends*. arXiv:2109.09824；**Journal of Forecasting** (2024)
    doi:10.1002/for.3104 — VISUELLE（5,577 件、2016–2019、Nunalie）；5,080/497 切分；h=6 週；
    WAPE／MAE／TS／ERP；Table 1 全部數字。[全文經 ar5iv **已核**]
11. Skenderi, G., Joppi, C., Denitto, M., Scarpa, B. & Cristani, M. (2022). *The Multi-Modal Universe of Fast-Fashion:
    The Visuelle 2.0 Benchmark*. **CVPR Workshops** 2022, 2241–2246. arXiv:2204.06972 — 5,355 件、6 季、item-shop
    層級、SO-fore 2-10／2-1、測試＝最新 10% item-shop 對；Table 1／2 全部數字。[全文經 ar5iv **已核**]
12. Joppi, C., Skenderi, G. & Cristani, M. (2022). *POP: Mining POtential Performance of new fashion products via
    webly cross-modal query expansion*. **ECCV** 2022. arXiv:2207.11001 — POP 外生訊號，repo 內直接提供。[摘要＋repo **已核**]
13. Ekambaram, V. et al. (2020). *Attention based Multi-Modal New Product Sales Time-series Forecasting*. **KDD** 2020.
    doi:10.1145/3394486.3403362 — Attribute/Image-kNN 與 Cat-MM-RNN／X-Att-RNN 基線的出處。[書目已核，經 [10][11] 轉引]
14. Al-Halah, Z., Stiefelhagen, R. & Grauman, K. (2017). *Fashion Forward: Forecasting Visual Style in Fashion*.
    **ICCV** 2017. doi:10.1109/ICCV.2017.50；arXiv:1705.06394 — Amazon 三品類、2008–2013、月解析度；
    train 2008–11／val 2012／test 2013；基線 mean/last/drift/AR/AR+S/VAR/ARIMA/FFNN/TLNN；
    **指數平滑勝過 ARIMA 與神經網路**；Table 2 全部數字；§4.5 要素人氣排名交集率 90/84/88%。[全文經 ar5iv **已核**]
15. Kunz, M. et al. (2023, Zalando). *Deep Learning based Forecasting: a case study from the online fashion industry*.
    arXiv:2305.14406 — 固定庫存假設迫使模型必須處理價格–需求關係。[摘要**已核**]
16. Sheikh, A.-S. et al. (2019). *A deep learning system for predicting size and fit in fashion e-commerce*.
    **RecSys** 2019. doi:10.1145/3298689.3347006；*Meta-Learning for Size and Fit Recommendation in Fashion*.
    **SDM** 2020. doi:10.1137/1.9781611976236.7 — 尺碼曲線需要退貨資料。[書目已核]

### 資料集（可得性由本次 API 查詢核實）
17. **Visuelle / Visuelle 2.0** 官方頁：<https://humaticslab.github.io/forecasting/visuelle> — 下載需填表單，
    表單連結 `https://forms.gle/cVGQAmxhHf7eRJ937`（GTM／POP repo 均指向同一份）；**無授權條款**；
    HF 上**無鏡像**（`visuelle`／`nunalie` 搜尋零結果）。[**已核**]
18. **H&M Personalized Fashion Recommendations**（Kaggle 2022）；HF 鏡像 `einrafh/hnm-fashion-recommendations-data`
    （非 gated、卡片無授權）：transactions 31,788,324 列（`t_dat` 2018-09-20→2020-09-22）、articles 105,542、
    customers 1,371,980；欄位與各屬性基數見 §3.3。[**全部已核**，經 HuggingFace datasets-server]
19. `tomytjandra/h-and-m-fashion-caption`：20,491 列 `text`+`image`；caption ＝ appearance＋顏色＋detail_desc 的
    正規化串接。[**已核**]
20. **Corporación Favorita Grocery Sales Forecasting**（Kaggle 2017–18）；HF 局部鏡像 `THULab/favorita_transactions`、
    `THULab/favorita_stores` 存在。[鏡像存在**已核**；列數／期間／指標 NWRMSLE **未核**]
21. **Amazon Reviews 2023**（McAuley Lab），HF `McAuley-Lab/Amazon-Reviews-2023`，非 gated、**卡片未標授權**。
    [可得性**已核**；Clothing 子集規模**未核**]

### 專案內部依據
22. `docs/engine02-design.md` §3.22（T14 缺口盤驗證）、§3.15（T11 趨勢關鍵字的負面結果）、
    §3.19（循環性：標準答案是自己填的）、§3.16（先量代價再定權重）、§3.23（T15）。
23. `scripts/eval_gap.py`（T14 的注入／對照設計與 docstring 裡已寫明的宣稱邊界）。
24. `engine02/panels.py::element_gap`、`::category_color_gap`、`::need_supply`；
    `engine02/api.py::_record_demand`（`deque(maxlen=500)`、**無時間戳**）、`::gap_elements`、`::gap_cells`；
    `engine02/kansei.py::Kansei.beta`；`engine02/resources/kansei_v1_literature.json`（15 個 `design_elements`）。
25. `docs/research/engine02-completeness.md` §2.1（Pinterest 規範；**「主辦方已有內部趨勢平台，且明確排除趨勢預測系統」**）。
26. `docs/research/external-benchmarks.md` §1.1／§2.4（H&M 需帳號的原因、四語料授權盤點、
    「離線評測可以，不可出貨」的既有處置原則）；`docs/research/catalog-options.md`（H&M price 是正規化值）。
