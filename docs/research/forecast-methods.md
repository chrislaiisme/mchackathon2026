# 趨勢預測方法調查：我們該跑什麼，以及有什麼證據說它有效

> 調查日期 **2026-09-19**｜本檔只新增，不動 `docs/research/` 以外任何東西。
> 標記：**V** = 本輪親自取得一手來源（原文／官方評分檔／API 回應）｜**C** = 沿用本倉庫既有文件已核實的結論｜**U** = 我無法核實。
> 前提文件（讀過，不重覆）：`docs/research/forecast-evaluation.md`（Visuelle／GTM／H&M 資料判決）、
> `docs/research/live-trend-sources.md`（今天真的抓得到什麼）、`docs/research/social-trend-signals.md`（HERMES／Heuritech）、
> `docs/engine02-design.md` §3.15（趨勢詞進排序，28 組全變差）、§3.26（KOL 訊號否決）。
> **本輪與前述文件最大的不同：我沒有只讀論文，我把資料抓下來跑了一次真的 backtest。** §7 是本檔唯一的新實驗證據，
> 而它推翻了一個我們本來要寫進簡報的句子。

---

## 0. 一頁結論

1. **「贏不贏得了 seasonal naive」這個問題，在我們的資料上問錯了。** 我抓了 20 個時尚詞的英文維基百科逐日瀏覽數
   （2015-07-01→2026-09-15，每詞 4,095 天 → 584 個完整 ISO 週），跑 23 個 rolling origin × h=1..13 的 backtest：
   **seasonal naive 是七個方法裡最差的一個**（平均 MASE **1.086**），而最笨的 naive（`ŷ=y_t`）就把它打掉 **27.9%**
   （p=0.0037，20 個詞裡贏 15 個）。原因在 §7.2：這些序列的 `acf(1)` 中位數約 0.87，`acf(52)` 只有約 0.47——
   **注意力序列是「水準持續 + 新聞尖峰」，不是「每年同一週」**。零售的季節性直覺在這裡不成立。
2. **所以必過基線不是 seasonal naive，是 naive 與「季節指數 × SES」。** 後者（`seas-ses`）平均 MASE **0.706**，
   贏 seasonal naive **35.0%**、20 個詞贏 19 個、p<1e-5；而且 h≥5 之後它同時贏 naive。**這才是要被打敗的那個數字。**
3. **M4 與 M5 的結論不是「簡單就是好」，是「簡單且被正確評估的東西很難贏」。** M4 官方評分檔（V）：
   52 個參賽法裡只有 **17 個**贏過 Comb 基線、只有 **29 個**贏過 Naive2；四個純機器學習參賽法 OWA 分別是
   0.915／1.151／1.481／1.595，**沒有一個贏過 Theta（0.897）**，兩個甚至輸給 Naive2。M5 官方評分檔（V）：
   冠軍 WRMSSE **0.5204** vs 最佳簡單基線 ES_bu **0.6710**（−22.4%）——**但在最底層 L12（單品×門市）
   冠軍只有 0.884 vs ES_bu 0.915，差距剩 3.3%**。聚合層級的贏面遠大於明細層級。
4. **時間序列基礎模型可以用，而且對 20 條週序列是「秒級」的。** Chronos-Bolt／Chronos-2 是唯一
   程式與權重**全部 Apache-2.0** 的一家（V）；TimesFM **3.0 權重改成非商業授權**（V，本輪新發現）；
   Moirai **權重 cc-by-nc-4.0**（V，確認既有記載）；TimeGPT **沒有開放權重、定價頁 404**（V）；
   Lag-Llama **在 GIFT-Eval 上輸給 seasonal naive**（MASE 1.2276 vs 1.000），不要用。
5. **搜尋／注意力資料做 nowcasting 的效果量是「個位數到 20%」，而且會反向。** Choi & Varian（2012）自己的表裡，
   汽車銷售 MAE 改善 10.6%、消費者信心 9.3%，**但失業初領件數的一步預測 MAE 從 3.37% 變差到 3.68%**（V，原文）。
   Google Flu Trends 則是反例的教科書：**連續 108 週裡有 100 週高估**，而「GFT + 落後兩週的 CDC」MAE 0.232
   比 GFT 單獨的 0.486 好一倍（V，Lazer et al. 2014 原文）。**教訓是：注意力訊號要當「加在基線上的補充項」，
   永遠不能取代基線。**
6. **§3.15 的否決不動搖，但它不是這件事的判決。** §3.15 量的是「趨勢詞進 BM25 式分數項」，標準答案是商品屬性
   metadata。本檔講的是另一件事：**一條有自己標準答案（下一週的實際瀏覽數）的時間序列預測**。這兩件事可以同時為真。
   誠實的用途只有兩個：**後台觀察欄位**與**展示標籤**；**不可以進排序，也不可以自動轉成權重**（§6）。

**一句話**：不要做「預測下一季會流行什麼」。做「**我們把注意力序列的可預測性量出來了，而且量出來的第一個結果就推翻了
我們自己的預設基線**」——故事是 backtest，不是模型。

---

## 1. 一直在贏的那些基線：M4 與 M5 到底結論了什麼

### 1.1 M4（Makridakis, Spiliotis & Assimakopoulos, *IJF* 36(1), 2020, doi:10.1016/j.ijforecast.2019.04.014）

100,000 條序列、61 個方法、首次把預測區間納入評分。
**我沒有引用論文轉述，我下載了官方評分檔** `Evaluation and Ranks.xlsx`
（<https://github.com/Mcompetitions/M4-methods>，V）並自己重算。全體序列（Total）成績：

| 方法 | sMAPE | MASE | **OWA** |
|---|---|---|---|
| Smyl（ES-RNN，Uber，Hybrid）**冠軍** | 11.374 | 1.536 | **0.821** |
| Montero-Manso 等（FFORMA）**亞軍** | 11.720 | 1.551 | 0.838 |
| **Theta**（基線） | **12.309** | **1.697** | **0.897** |
| Comb（SES+Holt+Damped 平均，基線） | 12.555 | 1.663 | 0.898 |
| Damped | 12.661 | 1.683 | 0.907 |
| SES | 13.087 | 1.885 | 0.975 |
| **Naive2**（去季節後的 naive，OWA 的分母） | **13.564** | **1.912** | **1.000** |
| Naive | 14.208 | 2.044 | 1.058 |
| **sNaive** | **14.657** | **2.057** | **1.078** |
| RNN（官方基線） | 21.152 | 2.685 | 1.482 |
| MLP（官方基線） | 21.654 | 3.225 | 1.642 |

**Theta vs naive 的公布數字（本檔被指定要給的那一個）**：
Theta 的 **sMAPE 12.309 vs Naive2 13.564（−9.3%）**、**MASE 1.697 vs 1.912（−11.2%）**、**OWA 0.897 vs 1.000（−10.3%）**；
對 **seasonal naive**（sNaive，OWA 1.078）則是 **−16.8%**。
Theta 是 M3 的冠軍方法（Assimakopoulos & Nikolopoulos, *IJF* 2000, doi:10.1016/S0169-2070(00)00066-2），
Hyndman & Billah（*IJF* 19(2), 2003, doi:10.1016/S0169-2070(01)00143-1）證明標準 Theta ≡ **帶 drift 的 SES**，
drift 等於 OLS 斜率的一半——**它是兩行程式，卻打敗了 M4 裡 35/52 的參賽法**。

**M4 真正的結論（我從評分檔重算，V）**：
- 52 個參賽方法裡，**只有 17 個**贏過 Comb 基線；**只有 29 個**（56%）贏過 Naive2。
- **四個「純機器學習」參賽法的 OWA 是 0.915／1.151／1.481／1.595**——最好的那個仍然輸給 Theta 與 Comb，
  兩個輸給 Naive2。官方的 RNN／MLP 基線更是 1.482／1.642。
- 前兩名都是**混合／組合**：冠軍是統計結構＋RNN 的 hybrid，亞軍是用 ML 去**加權組合統計方法**。
  M4 的教訓不是「ML 沒用」，是 **「ML 用在組合權重上有用，直接拿來當預測器則輸給 Theta」**。
- 區間評估（MSIS，越低越好；ACD＝覆蓋率絕對偏差）：Naive 24.055／0.0860、ARIMA 18.681／0.0920、
  **ETS 15.679／0.0373**、冠軍 12.230／**0.0022**。**大部分方法的區間是壞的，這一格比點預測更容易做出貢獻。**

### 1.2 M5（*IJF* 38(4), 2022, doi:10.1016/j.ijforecast.2021.11.013；組織篇 doi:10.1016/j.ijforecast.2021.07.007）

42,840 條 Walmart 階層序列（12 個聚合層級，底層 L12 = 30,490 條單品×門市）、h=28 天、
近 6,000 名參賽者／近 100,000 次提交（<https://www.unic.ac.cy/iff/research/forecasting/m5-competition/>，V）。
同樣地，我下載了官方 `Scores and Ranks.xlsx`（<https://github.com/Mcompetitions/M5-methods>，V）：

| 基線 | WRMSSE（12 層平均） | **L12（單品×門市）** |
|---|---|---|
| Naive | 1.7520 | 1.2534 |
| **sNaive** | **0.8470** | **1.1764** |
| SES | 0.9691 | 0.9320 |
| MA | 0.9560 | 0.9381 |
| **CRO（Croston）** | 0.9566 | **0.9261** |
| SBA（Syntetos–Boylan） | 0.9572 | **0.9192** |
| TSB | 0.9614 | 0.9277 |
| ADIDA | 0.9546 | 0.9223 |
| iMAPA | 0.9595 | 0.9253 |
| ARIMA_bu | 0.9075 | 0.9170 |
| **ES_bu（最強簡單基線）** | **0.6710** | **0.9147** |
| ESX（ES + 外生變數） | 0.6791 | 0.9170 |
| ARIMAX | 0.6906 | 0.9115 |
| MLP／RF／gRF（官方 ML 基線） | 0.9768／1.0095／1.0651 | 0.9434／0.9395／0.9318 |
| **冠軍 YJ_STU** | **0.5204** | 0.8842 |
| 第 50 名 Random_prediction | 0.5760 | 0.8900 |

**M5 的三個結論，都必須一起講，否則會誤導**：
1. **M5 是 ML 真的贏了的那一屆**：冠軍 0.5204 比最強簡單基線 ES_bu 0.6710 好 **22.4%**，比 sNaive 好 **38.6%**，
   而且**前 50 名全部**都比 ES_bu 好。這跟 M4 相反。
2. **但官方的現成 ML 基線（MLP 0.977／RF 1.010／gRF 1.065）全部輸給 ES_bu（0.671），也全部輸給 sNaive（0.847）。**
   贏的是**重度特徵工程的 LightGBM + 外生變數（價格、促銷、節慶）**，不是「把資料丟進 ML」。
3. **最重要的一條：贏面幾乎全在聚合層級。** 到了 L12 單品×門市，冠軍 0.8842 vs ES_bu 0.9147 只差 **3.3%**，
   前 50 名裡最好的 L12 是 0.8750，也只贏 ES_bu **4.3%**。
   **這個 4.3% 恰好等於 Heuritech 的 HERMES 用 10,000 條序列＋influencer 訊號換到的 4.3% MASE（§3.26，C）。**
   兩個完全獨立的來源給了同一個量級——**明細層級的可預測性上限大約就是個位數百分比**。

### 1.3 標準基線組（reviewer 會要的那一套）

| 情境 | 必跑基線 | 出處 |
|---|---|---|
| 一般（連續、非間斷） | naive、**seasonal naive**、drift、MEAN、MA(k)、**SES/ETS**、**Theta**、AutoARIMA | Hyndman & Athanasopoulos, *FPP3* §5.2；M4 官方基線組（V） |
| **間斷型需求**（大量 0，單品層級） | **Croston**（Croston, *JORS* 1972, doi:10.1057/jors.1972.50）、**SBA**（Syntetos & Boylan, *IJF* 21(2) 2005, doi:10.1016/j.ijforecast.2004.10.001）、TSB、ADIDA、iMAPA | M5 官方基線組（V，數字見上表） |
| 新品（無歷史） | Attribute-kNN／Image-kNN | Ekambaram et al., KDD 2020（C） |

**我們這一題用不到 Croston**：週聚合的維基瀏覽數沒有 0（§7 實測最小值遠離 0）。
**間斷性是「聚合層級」的性質，不是「時尚」的性質**（`forecast-evaluation.md` §2.2，C）——
只有真的做到單品×尺碼層級才需要 Croston 家族。**但要在簡報上說明我們知道這條線在哪裡。**

**全部可用 `statsforecast` 跑**（PyPI 2.1.1，Apache-2.0，`requires_python>=3.10`，V）：
`Naive`／`SeasonalNaive`／`WindowAverage`／`RandomWalkWithDrift`／`AutoETS`／`AutoTheta`／`AutoARIMA`／
`CrostonClassic`／`CrostonSBA`／`TSB`／`ADIDA`／`IMAPA`；指標在 `utilsforecast` 0.2.16（Apache-2.0，V）的
`losses.mase` / `losses.rmsse`。

---

## 2. 時間序列基礎模型（2024–2026）

`backoffice-demand-prediction.md` §4.4 已經列過授權（C）。本輪逐一用 HuggingFace API 的 `license` 欄位與
PyPI JSON API 重新核，**發現一個既有文件沒有的新陷阱**。

| 模型 | 論文／年 | 尺寸 | 程式授權 | **權重授權** | pip |
|---|---|---|---|---|---|
| **Chronos / Chronos-Bolt / Chronos-2** | arXiv:2403.07815（TMLR 2024）；Chronos-2 arXiv:2510.15821 | Bolt 9M/21M/48M/205M；Chronos-2 120M；T5 8M–709M | Apache-2.0 | **Apache-2.0（全部 12 個 checkpoint）** ⭐ | `pip install chronos-forecasting`（2.3.2） |
| **TimesFM** | arXiv:2310.10688，**ICML 2024** | 1.0 200M／2.0 500M／2.5 231M／**3.0 331M** | Apache-2.0 | ≤2.5 **Apache-2.0**；**3.0 = `timesfm-non-commercial-license-v1.0`** ⚠️ | `pip install timesfm[torch]`（3.0.2） |
| **Moirai / uni2ts** | arXiv:2402.02592，**ICML 2024 Oral**；MoE arXiv:2410.10469 | small 13.8M／base 91M／large 311M／MoE 935M／2.0-small 11.4M | Apache-2.0 | **全部 `cc-by-nc-4.0`** ⚠️ | `pip install uni2ts`（2.0.0） |
| **TimeGPT** | arXiv:2310.03589（無 venue，技術報告） | — | SDK Apache-2.0 | **沒有開放權重**（HF 上 Nixtla 有 0 個模型）⚠️ | `pip install nixtla`（0.8.0，純 HTTP client） |
| **Lag-Llama** | arXiv:2310.08278（preprint，無 venue） | **2.45M**（只有一個尺寸） | Apache-2.0 | Apache-2.0 | **不在 PyPI**，只能 git clone |

（以上尺寸為 HF safetensors 實際參數量，授權為 HF API `license` 欄位，版本為 PyPI JSON API，全部 V。）

### 2.1 零樣本的實際數字

**Chronos 論文 Benchmark II（27 個訓練時沒看過的資料集，以 seasonal naive 正規化後取幾何平均，seasonal naive = 1.000）**，
arXiv:2403.07815 Table 9/10（V）：

| 模型 | 相對 WQL | 相對 MASE |
|---|---|---|
| **Chronos-T5 Large** | **0.645** | **0.823** |
| TFT（**在該資料集上訓練過**） | 0.639 | — |
| PatchTST（在該資料集上訓練過） | 0.684 | 0.810 |
| Moirai-1.0-R Base／Large | 0.696／0.720 | 0.907／0.876 |
| SCUM（統計組合） | 0.728 | — |
| AutoARIMA／AutoTheta／AutoETS | 0.761／0.793／0.838 | 0.908／0.875／0.953 |
| **Seasonal Naive** | **1.000** | **1.000** |
| Lag-Llama | 1.097 | 1.291 |

→ **零樣本比 seasonal naive 好 35%（WQL）／18%（MASE），且與「在該資料集上訓練過的」TFT/PatchTST 打平。**
這是本領域目前最強的一個「不看你的資料也能贏基線」的公開證據。

**GIFT-Eval**（<https://huggingface.co/spaces/Salesforce/GIFT-Eval>，97 個 config，同樣以 seasonal naive 正規化；
數字由 sub-agent 下載該 leaderboard 的原始 `all_results.csv` 並以其 `src/utils.py` 的幾何平均法重算，V）：

| 模型 | 正規化 MASE | 正規化 CRPS |
|---|---|---|
| TimesFM-3（**最強的純基礎模型**，榜上第 15，前 14 名是 agent／ensemble／LoRA 提交） | **0.6668** | 0.4557 |
| chronos-2 | 0.6978 | 0.4854 |
| TimesFM-2.5 | 0.7050 | 0.4903 |
| Moirai2 | 0.7281 | 0.5164 |
| chronos_bolt_base／small | 0.8076／0.8221 | 0.5743／0.5767 |
| Moirai large／base／small | 0.8749／0.9010／0.9461 | 0.5989／0.6095／0.6504 |
| **seasonal_naive** | **1.0000** | **1.0000** |
| **auto_arima／auto_theta／auto_ets** | **1.0736／1.0900／1.2117** | 0.9117／1.2437／**7.4890** |
| timesfm（1.0 200m） | 1.0771 | 0.6804 |
| **Lag-Llama** | **1.2276** | 0.8804 |

**這張表有兩件事必須講出來**：
1. **在 GIFT-Eval 上，AutoARIMA、AutoTheta、AutoETS 全部輸給 seasonal naive**（1.07／1.09／1.21 vs 1.000），
   AutoETS 的 CRPS 7.489 是全榜最後一名（少數序列的機率配適爆掉）。**「統計方法一定比較穩」是錯的**——
   統計方法在某些序列上會災難性失敗，而 seasonal naive 不會。這一點跟 §7 我自己量到的方向剛好相反
   （我的資料上 seasonal naive 最差），**說明「哪個簡單基線最強」完全取決於資料，必須量，不能假設**。
2. **TimesFM 版本差異巨大**：1.0（1.0771，輸給 seasonal naive）→ 2.0（0.7581）→ 2.5（0.7050）→ 3.0（0.6668）。
   **不可以泛稱「TimesFM」**。

### 2.2 我們今天真的跑得動哪一個？

工作量：**20 條單變量週序列 × 584 點（實際比題目說的 5 年更長）、h=8–13**。這是 ~11,700 個點，
**一次 batched forward pass 就跑完**。結論：**推論時間完全不是選擇依據，下載權重與 import 才是大頭**。

| 模型 | 單 GPU | 純 CPU | 判定 |
|---|---|---|---|
| **Chronos-Bolt-small/base** | <1 s | **數百 ms ～ 2 s** | ⭐ **首選**：Apache-2.0、單次前向、卡片明示支援 CPU |
| **Chronos-2（120M）** | <1 s（官方：單張 A10G >300 序列/秒，V） | ~1–3 s | ⭐ Chronos 家族最準，仍 Apache-2.0 |
| TimesFM 2.5（231M） | ~1 s | ~2–5 s | 可，Apache-2.0；3.0 更準但**非商業授權** |
| Moirai-2.0-R-small（11M） | ~1–3 s | ~1–3 s | 技術上可，**權重 NC** |
| Chronos-T5-large（709M） | ~1–5 s | **可能數分鐘** | ❌ 自迴歸取樣 × 709M 在 CPU 上是唯一會慢的組合 |
| TimeGPT | — | — | ❌ 現場要網路＋API key＋資料外送，定價頁 404 |
| Lag-Llama | <1 s | 1–5 s | ❌ 輸給 seasonal naive；且 `requirements.txt` 釘死 `gluonts<=0.14.4`（現行 0.17.0），會打依賴戰 |

（CPU 秒數除 Chronos 官方數字外為 sub-agent 的估計，標 **U**；GPU/CPU 可跑性與授權皆 V。）

**答案：Chronos-Bolt-base（或 Chronos-2）。** 唯一程式與權重都 Apache-2.0、CPU 上秒級、一行 pip、
`requires_python>=3.10` 與我們一致。**這是今天就能跑的那一個。**

---

## 3. 用搜尋／注意力資料做 nowcasting：效果量與失敗模式

### 3.1 Google Flu Trends 的失敗（Lazer, Kennedy, King & Vespignani, *Science* 343(6176):1203–1205, 2014-03-14, doi:10.1126/science.1248506）

**全文已核（V，<https://gking.harvard.edu/files/gking/files/0314policyforumff.pdf>）。到底發生什麼事，逐條照原文：**

- **錯多大**：2013 年 2 月，GFT 預測的流感樣疾病就診比例是 CDC 的**兩倍以上**；2011–2012 流感季**高估超過 50%**；
  **從 2011-08-21 到 2013-09-01，108 週裡有 100 週報得太高**。原文寫明這些誤差**不是隨機的**：
  「上一週的誤差可以預測這一週的誤差」（時間自相關），而且誤差的方向與大小隨季節變化——
  **也就是說 GFT 漏掉了傳統統計方法本來就能萃取的資訊**。
- **陷阱一：Big data hubris（大數據傲慢）**——把大數據當成傳統資料的**替代品**而不是**補充品**。
  GFT 的做法是「從 **5,000 萬**個搜尋詞裡挑出最能配適 **1,152** 個資料點的 50 個」。
  原文：在這種比例下「找到結構上不相關卻恰好吻合的搜尋詞，機率非常高」——
  他們真的挑到了與流感無關的**高中籃球**相關詞。**這就是過度配適的教科書案例。**
- **陷阱二：Algorithm dynamics（演算法動態）**——Google 的搜尋演算法本身一直在變（原文：光 2011 年
  6 月與 7 月官方部落格就公告了 **86 項**變更）。2011 年 6 月起 Google 開始對症狀查詢**推薦相關搜尋**
  （搜「發燒」會被建議搜診斷），這**內生地**拉高了 GFT 的輸入。原文稱之為 **blue team dynamics**：
  服務提供者為了自己的商業目的修改資料生成過程。另有 **red team** 風險：
  研究對象刻意操縱訊號（原文舉 Twitter 灌票、公司散布謠言影響股價）。
- **「修正後的做法」是什麼**（本節最該抄的一句）：**把 GFT 與落後的 CDC 資料結合，並動態重新校準 GFT**。
  原文圖說的實測 MAE（樣本外）：**GFT 單獨 0.486、落後 CDC 單獨 0.311、GFT + CDC 合併 0.232**，
  「所有差異在 P<0.05 下統計顯著」。
  **也就是說：純注意力訊號比「三週前的官方數字」還差；注意力訊號的價值只在它被加到官方基線之上時才出現。**
- 原文還有一句我們該引用的：即使在 2009 年更新後，一份 2010 年的研究顯示 GFT 的準確度
  「並沒有比一個用已經可得的（通常落後兩週的）CDC 資料做的相當簡單的投影好多少」。

**對我們的直接翻譯**：Wikipedia 瀏覽數之於服飾需求 = GFT 之於流感。
**我們沒有 CDC**——我們沒有任何「官方的、落後的服飾需求數字」可以拿來校準。
所以照 Lazer 的結論，我們連「合併」那一步都做不到，**只剩下「GFT 單獨」那一欄，而那一欄是最差的那一欄**。
這是拒絕把趨勢訊號轉成需求宣稱最硬的一個引用。

### 3.2 Choi & Varian, *Predicting the Present with Google Trends*（Google 技術報告 2011-12-18；*Economic Record* 88(s1):2–9, 2012, doi:10.1111/j.1475-4932.2012.00809.x）

**全文已核（V，<https://people.ischool.berkeley.edu/~hal/Papers/2011/ptp.pdf>）。**
方法刻意簡單：對 `log(y_t)` 配一個**季節性 AR 基線** `y_t = b_1 y_{t−1} + b_{12} y_{t−12} + e_t`，
再把**同期**的 Google Trends 類別指數當額外迴歸項；用 **rolling window** 做樣本外一步預測。
作者原文自陳：「我們在這裡不宣稱任何方法學上的進展」，模型是**給人當起點的基線**。

| 應用 | 基線 MAE | 加 Trends 後 MAE | 改善 |
|---|---|---|---|
| 汽車及零件零售（Motor Vehicles and Parts） | 6.34% | 5.66% | **−10.6%** |
| ↳ 只看衰退期（2007-12–2009-06） | 8.86% | 6.96% | **−21.4%** |
| **失業初領件數（一步樣本外）** | **3.37%** | **3.68%** | **⚠️ 變差** |
| ↳ 只看衰退期 | 3.98% | 3.44% | −13.6% |
| ↳ 四個轉折點附近 | — | — | −21.85%／−12.36%／−0.65%／−3.22% |
| 消費者信心（Roy Morgan, 澳洲，一步樣本外） | 3.63% | 3.29% | **−9.3%** |
| 香港旅客人次 | **只有樣本內配適**（排除日本後平均 R²=73.3%） | — | — |

**結論原文**：「包含相關 Google Trends 變數的簡單季節性 AR 模型，傾向比不含這些預測變數的模型好 **5% 到 20%**。」

**三個我們必須一起講的限制**：
1. **這是 nowcasting（預測現在），不是 forecasting（預測未來）。** 原文第一頁就寫明：
   「我們**不是**宣稱 Google Trends 能幫助 *predicting the future*。我們宣稱的是它能幫助 *predicting the present*。」
   它利用的是**官方統計有發布延遲**（汽車銷售延遲 2 週、香港旅客延遲 1 個月）。
   **我們沒有任何有發布延遲的官方服飾需求數字**——所以這個機制在我們身上不存在。
2. **效果會反向。** 失業初領件數的一步預測**加了 Trends 反而變差**（3.37%→3.68%）。
   改善只出現在**衰退期與轉折點**。**「5%–20%」是精選過的上限，不是期望值。**
3. **香港旅客那一格只有樣本內 R²**，不是樣本外預測——**不可以拿來當效果量引用**。

---

## 4. 時尚專屬的方法：誰做過、報了什麼誤差、哪些需要我們拿不到的資料

`forecast-evaluation.md` §3 與 `social-trend-signals.md` §1–2 已經逐篇核過（C）。本節只做一件新的事：
**把「它報的誤差」與「它需要的資料我們有沒有」放在同一張表上**，因為前者決定值不值得抄、後者決定抄不抄得動。

| 方法 | venue／年 | 報什麼數字 | 需要的資料 | **我們拿得到嗎** |
|---|---|---|---|---|
| **Heuritech（產品）** | 行銷頁宣稱「90% accuracy／24 months」 | **沒有方法、沒有對照組、沒有信賴區間** | 數千萬張 Instagram 影像 | ❌ **不可引用**（U）。要引就引他們自己的論文 |
| **HERMES**（David, Bellot（Heuritech）, Le Corff）｜arXiv:2202.03224 | **preprint，非同儕審查**（OpenAlex：無 venue、2 次引用） | **MASE 0.745→0.7132（−4.3%）@10,000 條序列**；1,000 條 −2.6%；**100 條 −1.1%（std 0.0043）** | 10,000 條週頻時尚趨勢序列 ＋ 每條一個 influencer 弱訊號 | ⚠️ **序列可下載（repo 無授權宣告），但沒有圖**。**且這個數字是壞消息**：訊號要靠 global RNN 跨數千條 pooling 才萃取得出（C） |
| **GTM-Transformer**（Skenderi, Joppi, Denitto, Cristani）｜arXiv:2109.09824 | ***Journal of Forecasting* 2024**，doi:10.1002/for.3104 | VISUELLE 1.0 新品 h=6 週：**WAPE 59.8（Attribute-kNN）→ 54.2**（−9.4% 相對）；外生 Google Trends 訊號的**淨貢獻只有 1.5% WAPE** | VISUELLE：5,577 件新品、2016–2019、Nunalie 內部銷售＋商品圖 | ❌ **資料要填 Google 表單、卡片無授權條款**。程式 MIT（架構可重用），**資料不可出貨**（C） |
| **Visuelle 2.0 / CrossAttnRNN**（Skenderi et al.）｜CVPR-W 2022，arXiv:2204.06972 | item-shop 層級 SO-fore 2-10：**Naive 118.18 → kNN 91.13 → 最佳 85.65 WAPE** | 同上 ＋ 庫存／補貨／折扣序列 | ❌ 同上；且**配套程式庫是 CC BY-NC-SA 4.0，GitHub 卻報成 `NOASSERTION`**（自動掃描器抓不到 NC 條款）（C） |
| **POP**（Joppi, Skenderi, Cristani）｜ECCV-W 2022，arXiv:2207.11001 | webly cross-modal query expansion 的外生訊號；**具體數字本輪未核** | 需要對每件新品做網路查詢擴展 | ❌ **程式庫 CC BY-NC-SA 4.0**；資料同 VISUELLE（C）；**數字 U** |
| **KERN**（Ma, Ding, Yang, Liao et al.）｜ICMR 2020，doi:10.1145/3372278.3390677，arXiv:2005.03297 | **最貼近我們想法的一篇**（fine-grained fashion element 時間序列）。**摘要裡一個數字都沒有**（C） | 自建 **FIT**：Instagram 的細粒度要素時間序列＋使用者分群 | ❌ **FIT 找不到權威下載頁**（C）；Instagram 原始資料在 §3.26 已判不可得 |
| **Fashion Forward**（Al-Halah, Stiefelhagen, Grauman）｜ICCV 2017 | Amazon 三品類月序列：**指數平滑勝過 ARIMA 與神經網路**；vs persistence −24%（Dresses）、vs drift −8%（Tops&Tees）、vs ARIMA −4%（Shirts） | Amazon 評論日期當銷售代理 ＋ 商品視覺屬性 | 🟡 Amazon Reviews 2023 非 gated **但無授權欄位**（C）。**方法上最值得抄的是它的結論：簡單指數平滑贏了**（C） |

### 4.1 講白了：哪些需要我們拿不到的資料

- **GTM-Transformer／Visuelle 2.0／POP**：全部綁在 **VISUELLE** 這一份資料上，而 VISUELLE 要填表單、
  卡片沒有授權條款、上游是一家義大利快時尚公司的內部銷售。**離線評測勉強可以，出貨不行。**（C）
- **KERN／Heuritech**：綁在 **Instagram 影像**上。§3.26 已逐條核過：Graph API 需 Business/Creator 帳號＋
  強制 App Review、限「30 個 hashtag / 7 天」、Meta 平台條款要求不需要時即刪除。**是資格問題，不是技術問題。**（C）
- **HERMES**：序列本身下載得到，**但沒有圖**，而且 repo 無授權宣告。更關鍵的是它的數字**否決了我們的規模**。

### 4.2 這一節對我們的唯一有用結論

**這些方法沒有一篇報過「對 seasonal naive 的 MASE」**（`social-trend-signals.md` §2.1(a)，C）。
它們比的是「上一個模型」。所以**就算我們拿得到那些資料，抄過來也回答不了「值不值得做」這個問題**。
反過來說，**我們能比它們多做的一件事，就是把基線做對、把 MASE 報出來**——這正是 §5 與 §7 在做的事。

