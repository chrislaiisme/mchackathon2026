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
   （p=0.0037，20 個詞裡贏 15 個）。原因在 §7.2：這些序列的 `acf(1)` 中位數 0.88，`acf(52)` 只有約 0.47——
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
   永遠不能取代基線。** 而 Google Trends **同一個查詢重抓 6 次，各次相關只有 0.79–0.94**
   （Cebrián & Domenech, *Applied Economics Letters* 2023，V）——**這就是我們用 Wikimedia（CC0、確定性）的理由**（§3.5）。
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
| Naive ／ **sNaive** | 1.7520 ／ **0.8470** | 1.2534 ／ **1.1764** |
| SES ／ MA | 0.9691 ／ 0.9560 | 0.9320 ／ 0.9381 |
| **Croston ／ SBA ／ TSB ／ ADIDA ／ iMAPA**（間斷型專用） | 0.9566 ／ 0.9572 ／ 0.9614 ／ 0.9546 ／ 0.9595 | **0.9261 ／ 0.9192 ／ 0.9277 ／ 0.9223 ／ 0.9253** |
| ARIMA_bu ／ ARIMAX | 0.9075 ／ 0.6906 | 0.9170 ／ 0.9115 |
| **ES_bu（最強簡單基線）** ／ ESX | **0.6710** ／ 0.6791 | **0.9147** ／ 0.9170 |
| MLP ／ RF ／ gRF（官方 ML 基線） | 0.9768 ／ 1.0095 ／ 1.0651 | 0.9434 ／ 0.9395 ／ 0.9318 |
| **冠軍 YJ_STU** ／ 第 50 名 | **0.5204** ／ 0.5760 | 0.8842 ／ 0.8900 |

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

**我們這一題用不到 Croston**：週聚合的維基瀏覽數**沒有任何一個 0**（20 個詞的全期最小週值是 `Loafer` 的 **45**，V）。
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
| TFT ／ PatchTST（**都在該資料集上訓練過**） | 0.639 ／ 0.684 | — ／ 0.810 |
| Moirai-1.0-R Base／Large | 0.696 ／ 0.720 | 0.907 ／ 0.876 |
| SCUM（統計組合）／ AutoARIMA ／ AutoTheta ／ AutoETS | 0.728 ／ 0.761 ／ 0.793 ／ 0.838 | — ／ 0.908 ／ 0.875 ／ 0.953 |
| **Seasonal Naive** ／ Lag-Llama | **1.000** ／ 1.097 | **1.000** ／ 1.291 |

→ **零樣本比 seasonal naive 好 35%（WQL）／18%（MASE），且與「在該資料集上訓練過的」TFT/PatchTST 打平。**
這是本領域目前最強的一個「不看你的資料也能贏基線」的公開證據。

**GIFT-Eval**（<https://huggingface.co/spaces/Salesforce/GIFT-Eval>，97 個 config，同樣以 seasonal naive 正規化；
數字由 sub-agent 下載該 leaderboard 的原始 `all_results.csv` 並以其 `src/utils.py` 的幾何平均法重算，V）：

| 模型 | 正規化 MASE | 正規化 CRPS |
|---|---|---|
| TimesFM-3（**最強的純基礎模型**，榜上第 15，前 14 名是 agent／ensemble／LoRA 提交） | **0.6668** | 0.4557 |
| chronos-2 | 0.6978 | 0.4854 |
| TimesFM-2.5 | 0.7050 | 0.4903 |
| Moirai2 ／ chronos_bolt_base ／ chronos_bolt_small | 0.7281 ／ 0.8076 ／ 0.8221 | 0.5164 ／ 0.5743 ／ 0.5767 |
| Moirai large ／ base ／ small | 0.8749 ／ 0.9010 ／ 0.9461 | 0.5989 ／ 0.6095 ／ 0.6504 |
| **seasonal_naive** | **1.0000** | **1.0000** |
| **auto_arima ／ auto_theta ／ auto_ets** | **1.0736 ／ 1.0900 ／ 1.2117** | 0.9117 ／ 1.2437 ／ **7.4890** |
| timesfm 1.0 200m ／ **Lag-Llama** | 1.0771 ／ **1.2276** | 0.6804 ／ 0.8804 |

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
  **從 2011-08-21 到 2013-09-01，108 週裡有 100 週報得太高**。原文強調這些誤差**不是隨機的**——
  上一週的誤差可以預測這一週的誤差、且方向與大小隨季節變化，**表示 GFT 漏掉了傳統統計方法本來就能萃取的資訊**。
- **陷阱一：Big data hubris（大數據傲慢）**——把大數據當成傳統資料的**替代品**而不是**補充品**。
  GFT 是「從 **5,000 萬**個搜尋詞裡挑出最能配適 **1,152** 個資料點的 50 個」；原文指出在這種比例下
  「找到結構上不相關卻恰好吻合的搜尋詞，機率非常高」，而他們真的挑到了**高中籃球**相關詞。**教科書級的過度配適。**
- **陷阱二：Algorithm dynamics（演算法動態）**——Google 的搜尋演算法本身一直在變（原文：光 2011 年
  6、7 月官方部落格就公告了 **86 項**變更）。2011 年 6 月起 Google 對症狀查詢**推薦相關搜尋**，
  **內生地**拉高了 GFT 的輸入。原文稱之為 **blue team dynamics**（服務提供者為商業目的修改資料生成過程），
  並另指出 **red team** 風險（研究對象刻意操縱訊號）。
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

### 3.3 Wikipedia pageviews 真的被同儕審查過：兩個成功案例

| 研究 | venue／年 | 方法 | **最強數字** |
|---|---|---|---|
| **McIver & Brownstein**, *Wikipedia Usage Estimates Prevalence of Influenza-Like Illness in the United States in Near Real-Time* | **PLOS Comput. Biol.** 10(4):e1003581, 2014, doi:10.1371/journal.pcbi.1003581 | 對 35 個條目的**每日**瀏覽數做 Poisson 迴歸，對照 CDC ILINet，**294 週** | 與 CDC 估計的**平均絕對差 0.27%**（range 0–2.38%）、**Pearson r = 0.946**；**猜中流感高峰週的次數比 Google Flu Trends 多 17%** |
| **Mestyán, Yasseri & Kertész**, *Early Prediction of Movie Box Office Success Based on Wikipedia Activity Big Data* | **PLOS ONE** 8(8):e71226, 2013, doi:10.1371/journal.pone.0071226 | 瀏覽數＋編輯者數＋編輯次數＋戲院數的多元線性迴歸，**312 部 2010 年美國上映電影** | **上映前一個月 R² ≈ 0.77**（n=312）；上映前數日、n=24 的子集 R²=0.96 |

**這兩篇是「Wikipedia 注意力有真訊號」最硬的證據，而且都比 Google Trends 乾淨**——
維基的資料是 CC0、可存檔、可重現，沒有 §3.4 的抽樣問題。
**但兩篇的標準答案都是外部的**（CDC 通報數、票房），**我們沒有對應的外部標準答案**（§3.1 的「我們沒有 CDC」）。

### 3.4 零售與時尚：兩篇必引，以及一個對我們特別重要的警告

- **Fu & Fang, *The Value of Social Media Data in Fashion Forecasting*, *Manufacturing & Service Operations Management*（M&SOM）25(3):1136–1154, 2023, doi:10.1287/msom.2023.1193**（摘要 V，全文付費牆）。
  與**三家跨國零售商**（兩家服飾、一家鞋類）合作，把自有銷售資料 ＋ 爬取的 Twitter ＋ Google Search Volume Index
  拿去預測**款式顏色與牛仔褲版型**的需求，用來決定**首批出貨量**。
  **最強數字（原文）**：加入社群媒體特徵後，**樣本外 MAD 相對「現行做法」改善 24%–57%**，三家零售商、各市場、各預測期皆一致。
  ⚠️ **但基準是「current practice」而不是 seasonal naive 或 Theta**——這是全文獻反覆出現的同一個毛病（§4.2）。
  且它用的是**自有銷售資料**，公開訊號只是補充項——**這正是 §3.1 Lazer 說的那個結構**。
- **Silva, Hassani, Madsen & Gee, *Googling Fashion: Forecasting Fashion Consumer Behaviour Using Google Trends*,
  *Social Sciences* 8(4):111, 2019, doi:10.3390/socsci8040111**（全文 V）。
  **這篇跟我們 §7 做的是同一件事**：它預測的是 **Google Trends 序列本身**（單一詞 "Burberry"，2004-01–2019-02 月頻、
  遞迴樣本外 N=60）——**不是 Burberry 的銷售**。RRMSE（以 SSA 去噪後的 DNNAR 為基準）在 h=3 個月時
  比 ARIMA／ETS／TBATS／NNAR 分別好 **29%／33%／29%／53%**（10% 顯著），但 **h=12 時四個全部不顯著**。
  **對我們的意義有兩層**：(i) 「預測注意力序列本身」是一個**已被同儕審查接受的研究對象**，不是我們自創的遁詞；
  (ii) 它的效果**隨 h 衰減到不顯著**，與 §7.3 我們量到的方向一致。

### 3.5 失敗模式：Google Trends 的同一個查詢，重抓會得到不同的數字

這是拒絕把 Google Trends 放進關鍵路徑最技術性、也最無可辯駁的理由。
**Cebrián & Domenech, *Is Google Trends a quality data source?*, *Applied Economics Letters* 30(6), 2023,
doi:10.1080/13504851.2021.2023088**；數字經其會議版 *Simulating the inconsistencies of Google Trends data*
（CARMA 2022, doi:10.4995/CARMA2022.2022.15093，**全文 V**）逐條核實：

- 同一組奧地利城市查詢**在 6 個不同日子重抓**，各次之間的**相關係數只有 0.79–0.94**。
- Carrière-Swallow & Labbé (2013)：對 "Chevrolet" **抓 50 次**，平均標準差**超過 15%**。
- D'Amuri & Marcucci (2017, *IJF* 33(4))：對 "jobs" 抓 24 次，交叉相關**至少 0.99**。
  → **不穩定度取決於查詢的熱門程度**：冷門詞單次抓取 r 僅 **0.802**，抓 10 次平均才 0.974。
- **還有一個少被提及的坑**：平均會改變尺度。冷門詞單次抓取 SVI 範圍 18–100，
  平均 20 次後變成 27.1–81.3 → **單次抓取的值不能直接跟平均後的序列比較**。
- **時尚文獻自己就知道這件事**：GTM-Transformer 原文寫明「我們把每條 Google Trend **下載 10 次取平均**」。

補充：Tom Coupé 對 Choi & Varian 做過複製研究（*Economics* 2018, doi:10.5018/economics-ejournal.ja.2018-34），
**但其結論我與 sub-agent 都無法取得全文** → 標 **U**。

**對我們的判決**：`live-trend-sources.md` 已實測非官方 widget 端點回 **429**、`pytrends` 自 2025-04-17 唯讀封存（C）。
**加上這一節：就算抓得到，同一個查詢重抓的相關只有 0.79–0.94。**
→ **Wikimedia pageviews（CC0、確定性、可存檔）是唯一該用的來源**，這也是 §7 為什麼用它。

---

## 4. 時尚專屬的方法：誰做過、報了什麼誤差、哪些需要我們拿不到的資料

`forecast-evaluation.md` §3 與 `social-trend-signals.md` §1–2 已經逐篇核過（C）。本節只做一件新的事：
**把「它報的誤差」與「它需要的資料我們有沒有」放在同一張表上**，因為前者決定值不值得抄、後者決定抄不抄得動。

| 方法 | venue／年 | 報什麼數字 | 需要的資料 | **我們拿得到嗎** |
|---|---|---|---|---|
| **Heuritech（產品）** | 行銷頁宣稱「90% accuracy／24 months」 | **沒有方法、沒有對照組、沒有信賴區間** | 數千萬張 Instagram 影像 | ❌ **不可引用**（U）。要引就引他們自己的論文 |
| **HERMES**（David, Bellot（Heuritech）, Le Corff）｜arXiv:2202.03224 | **preprint，非同儕審查**（OpenAlex：無 venue、2 次引用） | **MASE 0.745→0.7132（−4.3%）@10,000 條序列**；1,000 條 −2.6%；**100 條 −1.1%（std 0.0043）** | 10,000 條週頻時尚趨勢序列 ＋ 每條一個 influencer 弱訊號 | ⚠️ **序列可下載（repo 無授權宣告），但沒有圖**。**且這個數字是壞消息**：訊號要靠 global RNN 跨數千條 pooling 才萃取得出（C） |
| **GTM-Transformer**（Skenderi, Joppi, Denitto, Cristani）｜arXiv:2109.09824 | ***Journal of Forecasting* 2024**，doi:10.1002/for.3104 | VISUELLE 1.0 新品 h=6 週：Attribute-kNN 59.8 → **WAPE 55.2**（帶 `**` 的那一列是 54.2，**該註腳的意思未核 → 引用請用 55.2**）。消融：拿掉 Google Trends 只差 **1.5 WAPE 點** | VISUELLE：5,577 件新品、100 家店、2016-10–2019-12、Nunalie 內部銷售＋商品圖 | ❌ **資料要填 Google 表單、卡片無授權條款**。程式 MIT（架構可重用），**資料不可出貨**（C） |
| **Visuelle 2.0 / CrossAttnRNN**（Skenderi et al.） | **CVPR-W 2022**，arXiv:2204.06972 | item-shop 層級 SO-fore 2-10：**Naive 118.18 → kNN 91.13 → 最佳 85.65 WAPE** | 同上 ＋ 庫存／補貨／折扣序列 | ❌ 同上；且**配套程式庫是 CC BY-NC-SA 4.0，GitHub 卻報成 `NOASSERTION`**（自動掃描器抓不到 NC 條款）（C） |
| **POP**（Joppi, Skenderi, Cristani） | **ECCV 2022**，arXiv:2207.11001 | **VISUELLE 上最好的公開數字：WAPE 52.39／MAE 28.62**，比 Google Trends 好 2.85%、比無外生訊號好 4.23%。**外生訊號用的是 Google 圖片搜尋，不是 Trends** | 每件新品要爬 52 週 × 25 張「時髦／不時髦」圖 | ❌ 程式庫 CC BY-NC-SA 4.0；資料同 VISUELLE。**而且推論成本是每個樣本 21,979 秒**（vs GTM 4.80 秒），黑客松尺度直接出局 |
| **2024–2026 後繼**：MDiFF／Dif4FF（擴散模型） | **ICPR 2024 / ICPR-W 2024**，arXiv:2412.06840／arXiv:2412.05566 | 同一協定（VISUELLE、h=6 週）：**MDiFF 54.7**（只用圖＋上市日，**不用 Google Trends**）、**Dif4FF 54.6**（圖＋上市日＋Trends） | 同 GTM | ❌ 同 GTM |
| **KERN**（Ma, Ding, Yang, Liao, Wong, Chua） | **ICMR 2020**，doi:10.1145/3372278.3390677，arXiv:2005.03297 | **最貼近我們想法的一篇**。FIT 半年期 **MAE 0.083／MAPE 30.02**，vs 最佳基線 Linear 0.112／43.30（−26% MAE）；GeoStyle 上 MAPE 14.24 vs 16.03 | 自建 **FIT**：爬 Instagram 約 **68 萬張圖** → **197 個要素 × 74 個使用者分群 ≈ 8,000 條**半月頻序列，2014-07–2019-06 | ❌ **論文沒有給任何公開下載連結**；Instagram 原始資料在 §3.26 已判不可得。⚠️ **基線全是古典法**（AR/VAR/ES/linear/cyclic），**沒有任何神經網路基線** |
| **Fashion Forward**（Al-Halah, Stiefelhagen, Grauman） | **ICCV 2017** | Amazon 三品類月序列：**指數平滑勝過 ARIMA 與神經網路**；vs persistence −24%（Dresses）、vs drift −8%（Tops&Tees）、vs ARIMA −4%（Shirts） | Amazon 評論日期當銷售代理 ＋ 商品視覺屬性 | 🟡 Amazon Reviews 2023 非 gated **但無授權欄位**（C）。**方法上最值得抄的是它的結論：簡單指數平滑贏了**（C） |

### 4.1 講白了：哪些需要我們拿不到的資料

- **GTM-Transformer／Visuelle 2.0／POP**：全部綁在 **VISUELLE** 這一份資料上，而 VISUELLE 要填表單、
  卡片沒有授權條款、上游是一家義大利快時尚公司的內部銷售。**離線評測勉強可以，出貨不行。**（C）
- **KERN／Heuritech**：綁在 **Instagram 影像**上。§3.26 已逐條核過：Graph API 需 Business/Creator 帳號＋
  強制 App Review、限「30 個 hashtag / 7 天」、Meta 平台條款要求不需要時即刪除。**是資格問題，不是技術問題。**（C）
- **HERMES**：序列本身下載得到，**但沒有圖**，而且 repo 無授權宣告。更關鍵的是它的數字**否決了我們的規模**。

### 4.2 這一節最該帶走的三件事

**(1) 在 VISUELLE 上，三年的架構工作只買到 0.6 個 WAPE 點；換一個外生訊號買到 4 個點。**
GTM-Transformer（2021/2024）**55.2** → Dif4FF（2024）**54.6** → MDiFF（2024）**54.7**；
而 POP（2022）光是把 Google **Trends** 換成 Google **圖片搜尋**就做到 **52.39**。
**這是「與其調模型，不如換資料」最乾淨的一個公開證據**，也直接支持本檔的取捨：
我們該花時間在**把基線與評估做對**（§5、§7），不是在挑模型。

**(2) 這些方法沒有一篇報過「對 seasonal naive 的 MASE」**（`social-trend-signals.md` §2.1(a)，C）——
它們比的是「上一個模型」。連最強的產業證據（Fu & Fang 的 24–57%，§3.4）比的也是「current practice」。
所以**就算我們拿得到那些資料，抄過來也回答不了「值不值得做」這個問題**。
反過來說，**我們能比它們多做的一件事，就是把基線做對、把 MASE 報出來**——這正是 §5 與 §7 在做的事。

**(3) 一個真的空白**：sub-agent 掃過 OpenAlex 的引用圖，**沒有任何同儕審查論文報告過
時間序列基礎模型（Chronos／TimesFM／Moirai）在時尚需求基準上的數字**。
最接近的是 *Zero-shot Demand Forecasting for Products with Limited Sales Periods*（**IEEE BigData 2024**,
doi:10.1109/bigdata62323.2024.10825549），摘要只說「比既有時間序列方法準，尤其是銷售期短的商品」，
**沒有數字、全文付費牆 → U**。→ **§8 第 2 名做的事，在文獻上是空白格。** 這是加分項，但也代表沒有前人的數字可以對照。

---

## 5. 評估協定：我會跑的那一個（可直接實作）

### 5.1 為什麼是 MASE

Hyndman & Koehler, *Another look at measures of forecast accuracy*, **IJF 22(4):679–688, 2006**,
doi:10.1016/j.ijforecast.2006.03.001（書目 V；主張經 FPP3 §5.8 原文轉引 V）。

`q_j = e_j / [ (1/(T−m)) Σ_{t=m+1}^{T} |y_t − y_{t−m}| ]`，`MASE = mean(|q_j|)`，非季節時 `m=1`。

- **無單位** → 20 個詞的瀏覽量差三個數量級（`Sneakers` vs `Pleat`），不正規化就不能平均。
- **有絕對意義**：`MASE < 1` ⇔ 比**訓練段的一步季節性 naive** 好。
- **MAPE 不能用**（零售會出現 `y_t=0`、對高低估不對稱）；**sMAPE 明文不建議用**（FPP3 §5.8 引 Hyndman & Koehler
  原話 "recommend that the sMAPE not be used"，分母含預測值、可以是負的）（C）。
- **分母要寫清楚是哪一個 m。** §7 我用 `m=52`（週資料的年季節），所以 MASE 的分母是**訓練段的
  seasonal-naive MAE**，不是 one-step naive MAE。**這兩個差很多，論文裡最常被糊弄的就是這一格。**

### 5.2 我會跑的完整協定

1. **資料**：20 個詞 × `en.wikipedia` 逐日 `agent=user` 瀏覽數，**2015-07-01 起**（實測 2014 回 404，V），
   聚合到 ISO 週、**丟掉不滿 7 天的週**。實得 **584 週／詞**（V）。UA 要帶聯絡資訊、呼叫間隔 6.5 s（`live-trend-sources.md`，C）。
2. **切分**：**rolling origin / expanding window**（FPP3 §5.10 time series cross-validation）。
   最後 **104 週**當測試區，origin 每 **4 週**一個 → **23 個 origin**；每個 origin 預測 **h=1..13**。
   **訓練段永遠只用 origin 之前的資料**（含季節指數的估計，否則就是未來函數洩漏）。
3. **基線（全部要跑，不能只挑弱的）**：naive、seasonal naive(52)、drift、MA(13)、SES、**Theta**、
   **季節指數 × SES**，加 AutoETS／AutoARIMA。
4. **指標**：主指標 **MASE**（m=52），輔以 RMSSE。**逐詞報告，不准只報 20 詞平均**——
   平均會把「只有 3 個詞有訊號」藏起來（§7 的 `Hoodie`／`Ballet_flat` 就是反例）。
5. **區間**：報 80%／95% 的**實測覆蓋率**與 **MSIS**（M4 的區間指標）。
   **§1.1 的 M4 數字就是現成的尺規**：ETS 的 ACD 0.0373、冠軍 0.0022。
   若做機率預測，用 M5 的九個分位（0.005/0.025/0.165/0.25/0.5/0.75/0.835/0.975/0.995）算 **pinball loss**（V，M5 摘要）。
   **這一格比點預測更值得做**：§2.1 顯示 AutoETS 在 GIFT-Eval 的 CRPS 是 7.489（全榜最後），
   也就是說**點預測還行的方法，區間可以爛到無法使用**——量出來本身就是貢獻。
6. **統計**：
   - **配對單位必須是「詞」，不是「(詞, origin)」。** rolling origin 的預測窗重疊、相鄰 origin 高度相關。
     正確做法：**先在 origin 上對每個詞平均**，再對 20 個詞做配對置換檢定＋bootstrap CI
     （用現成的 `engine02.eval.metrics.paired_permutation_test`）。
   - **n=20 的功效**：配對置換的最小可能 p 值是 `2^-20 ≈ 1e-6`，總體比較功效足夠；**但逐詞宣稱必須校正**。
   - **多重比較陷阱（本節重點）**：一次測 20 個詞、α=0.05，**至少一個假陽性的機率是 `1 − 0.95^20 = 64.2%`**。
     用 **Benjamini–Hochberg FDR**（*JRSS-B* 1995, doi:10.1111/j.2517-6161.1995.tb02031.x，V）控制。
     同時比較**多個方法**時，正統做法是 **Model Confidence Set**（Hansen, Lunde & Nason, *Econometrica* 2011,
     doi:10.3982/ECTA5771，V）——回報「統計上分不出高下的方法集合」，而不是硬選一個冠軍。
     Diebold–Mariano（*JBES* 1995, doi:10.1080/07350015.1995.10524599，V）是預測比較的正統檢定，
     但 h>1 時窗重疊要用 HAC 變異數與 Harvey–Leybourne–Newbold 小樣本校正（U）。
     **建議維持本專案既有的配對置換房規，不要多開一套。**
7. **預先登記**：**詞表、origin、horizon、主指標，在看測試段之前寫死**。
   §3.15 的前車之鑑就是「28 組設定」——設定數愈多，事後挑一組的誘惑愈大。
8. **必做的 sanity check**：
   - **origin 間隔與 horizon 的共振**：§7.3 的 MASE 在 h=3,7,11 有規律突起，那是 origin 每 4 週一個
     讓 `h` 與 `h+4` 落在同一個季節相位造成的**協定假影，不是模型性質**。要嘛 origin 間隔取質數，要嘛在報告裡講明。
   - **COVID**：2020 落在訓練段、不在測試段（測試段 ≈ 2024-09→2026-09）。實測 2020 年均值／全期均值
     在 0.85–1.07 之間（V），**這些詞沒有 COVID 斷點**——但這句話要量了才能說。
   - **打散時間對照組**：把序列時間軸隨機打散再跑一次，任何「贏」都應該消失。沒消失就是評估有洩漏。

---

## 6. 一個趨勢預測誠實地能拿來幹嘛（§3.15 說了趨勢詞不能進排序）

§3.15 否證的是「熱門關鍵字進 BM25 式分數項」，標準答案是**商品屬性 metadata**，
所以任何與那個標準答案正交的新項都只會扣分（C，這條邊界要一起講）。
本檔的預測有**自己的標準答案**（下一週的實際瀏覽數），是另一件事。但那不代表它可以進產品。

| 用途 | 判定 | 它能支撐的宣稱 | 它**不能**支撐的宣稱 |
|---|---|---|---|
| **(a) 後台觀察面板的一欄** | ✅ **建議做，這是主用途** | 「`satin` 本週的維基注意力，比一個**季節指數×SES 模型**在 80% 區間內預期的高／低，而我們的目錄對它的覆蓋率是 y%」 | ❌「所以要多做緞面」 |
| **(b) 展示標籤** `trends.trend_badges()` | ✅ 代價 0，已在跑 | 「這個詞近期出現在公開注意力資料中」 | ❌ 任何數量宣稱 |
| **(c) 需求側輸入（自動改權重）** | ❌ **拒絕** | — | **沒有任何資料能定出「Wikipedia z 分數 → Δβ」的換算係數**（單位不可辨識，`live-trend-sources.md` §2，C）。且 Lazer 的結論是純注意力訊號連落後的官方數字都不如（§3.1） |
| **(d) 進排序** | ❌ **維持否決** | — | §3.15 的 28 組全變差（C） |

**所以正確的產品形態不是「預測」，是「意外偵測」**：
有了校準過的區間，我們能說的是「**這一週的注意力偏離了它自己的基線多少**」，
而要報的數字是**區間覆蓋率**（我們的區間可不可信），不是點預測準確度。
這句話有標準答案、可否證、而且不需要任何我們拿不到的資料。

**唯一合法的決策入口仍然是 `Engine02Request.design_weight_prior`**（§3.26，C）：
有上限（夾在一格使用者回饋 `step_size=0.25` 內）、有歸因（卡片上標示「外部趨勢／企劃偏好」）、
且**由人填，不由本模型自動灌**。

---

## 7. 我實際跑的 backtest（本檔唯一的新實驗證據）

**資料（V）**：20 個時尚詞的 `en.wikipedia` 逐日 `agent=user` 瀏覽數，2015-07-01→2026-09-15，
每詞 4,095 天 → **584 個完整 ISO 週**（週範圍 2015-W28 → 2026-W37）。
**協定**：§5.2 的協定，23 個 origin × h=1..13，MASE 分母 = 訓練段 seasonal-naive(52) MAE。

### 7.1 結果（20 詞平均）

| 方法 | 平均 MASE | 中位數 | vs seasonal naive | 20 詞中贏幾個 | 配對置換 p |
|---|---|---|---|---|---|
| **seasonal naive(52)** | **1.0861** | 0.9494 | — | — | — |
| naive | 0.7835 | 0.6548 | **−27.9%** | 15/20 | 0.0037 |
| drift | 0.7862 | 0.6499 | −27.6% | 14/20 | 0.0042 |
| MA(13) | 0.8868 | 0.7510 | −18.3% | 15/20 | 0.0250 |
| SES | 0.8364 | 0.6874 | −23.0% | 16/20 | 0.0016 |
| **Theta** | 0.8326 | 0.6823 | −23.3% | 16/20 | 0.0014 |
| **季節指數 × SES** | **0.7058** | **0.4611** | **−35.0%** | **19/20** | **<1e-5** |

### 7.2 為什麼 seasonal naive 在這裡是最差的

實測自相關（log 瀏覽數，V）：`acf(1)` 落在 **0.34–0.97**（中位數 0.88），
`acf(52)` 落在 **0.12–0.73**（中位數約 0.47）。
**注意力序列由「水準持續」主導，年季節性存在但是次要的。**
`Sneakers` 的 `acf(52)` 只有 0.116、`Cargo_pants` 0.163——**對這些詞「去年同週」幾乎沒有資訊**。
相對地 `Leather_jacket`（0.729）、`Parka`（0.709）確實有強年季節。
**這就是為什麼贏家是「同時用兩者」的季節指數 × SES，而不是只用其中一個的任一端。**

### 7.3 h 的相依性（20 詞 × 23 origin 平均）

| h | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| seasonal naive | 0.899 | 0.992 | 1.592 | 1.068 | 0.885 | 0.958 | 1.520 | 1.007 | 0.871 | 0.955 | 1.531 | 0.983 | 0.861 |
| naive | **0.403** | **0.569** | **0.913** | **0.606** | 0.608 | 0.745 | 1.084 | 0.754 | 0.750 | 0.854 | 1.200 | 0.859 | 0.840 |
| 季節指數×SES | 0.450 | 0.609 | 0.957 | 0.626 | **0.568** | **0.695** | **1.008** | **0.657** | **0.602** | **0.708** | **1.016** | **0.660** | **0.619** |

**naive 在 h≤4 最好，季節指數×SES 從 h=5 起接手，seasonal naive 在每一個 h 都最差。**
（h=3,7,11 的突起是 §5.2(8) 說的 origin 間隔假影。）

### 7.4 這個結果的邊界（不要過度推論）

- **只測了 20 個英文維基條目**，不是台灣市場、不是銷售。注意力≠需求（`live-trend-sources.md` §3.2，C）。
- **`Cardigan_(sweater)` 我刻意用了消歧義條目**；`live-trend-sources.md` 記載 `cardigan` 的最大條目是
  威爾斯地名——**同名污染是真的，只是這次被我在條目層級擋掉了**。這件事本身說明對映表必須逐列人工驗。
- **沒有跑基礎模型。** 這正是 §8 要做的下一步，而**門檻已經被這張表訂死了：0.7058**。

---

## 8. 建議實作的 2–3 個方法（排序）

### 第 1 名：`statsforecast` 基線組 —— 這就是交付物本身

- **(a)** `pip install statsforecast==2.1.1 utilsforecast==0.2.16`（皆 Apache-2.0，V）
- **(b) 執行時間**：20 序列 × 584 點 × 23 origin。**CPU 約 1–3 分鐘**（`AutoARIMA` 是唯一的大頭）。
  **GPU 無用**——這些方法沒有 GPU 路徑。§7 的整張表我用純 numpy 在本機跑完**不到 2 分鐘**。
- **(c) 要報的**：§7.1 那張表（逐詞 ＋ 平均 ＋ 中位數 ＋ 配對置換 p ＋ BH 校正後的逐詞判定）、
  §7.3 的 h 相依表、80%/95% 區間覆蓋率。
- **(d) 什麼結果代表不該出貨**：**沒有。這一格不會失敗，因為它的產出是「量測」不是「模型」。**
  真正的失敗模式是**沒跑它就去跑基礎模型**——那樣所有數字都沒有分母。

### 第 2 名：Chronos-Bolt-base 零樣本 —— 唯一值得加的模型

- **(a)** `pip install chronos-forecasting==2.3.2`（程式與權重皆 **Apache-2.0**，V）；
  模型 `amazon/chronos-bolt-base`（205M）或 `amazon/chronos-2`（120M，更準）。
- **(b) 執行時間**：20 條序列一次 batched forward pass。**單 GPU <1 秒；CPU 數百 ms ～ 3 秒**
  （官方卡片：Chronos-2 單張 A10G >300 序列/秒；Bolt 比原版 Chronos 快至多 250 倍，V。CPU 秒數為估計，U）。
  **實際耗時是下載權重的 10–60 秒。**
- **(c) 要報的**：零樣本 MASE 對上 §7.1 的七個基線，逐詞 ＋ 配對置換 ＋ BH；以及區間覆蓋率。
  可引的外部數字：Chronos Benchmark II 上對 seasonal naive 的 **−18% MASE／−35% WQL**（V）。
- **(d) 什麼結果代表不該出貨**：**MASE 沒有比 0.7058（季節指數×SES）低至少 10% 相對、
  或配對置換 p ≥ 0.01（BH 校正後）** → **不出貨這個模型，出貨這張表**。
  照 §3.15 處理 null result 的房規辦：把負結果寫進簡報，這是本專案第六個「量了才否決」的功能。
  10% 這個門檻的來源是 `forecast-evaluation.md` §2.3（C）：文獻上被同行接受為貢獻的差距下限。

### 第 3 名（選配，只在前兩名做完且還有時間時）：TimesFM 2.5 零樣本

- **(a)** `pip install timesfm[torch]==3.0.2`，模型 `google/timesfm-2.5-200m-pytorch`（**Apache-2.0**，V）。
  **不要用 3.0**：權重是 `timesfm-non-commercial-license-v1.0`，學術評測可以、出貨不行、且不得再散布（V）。
  **不要用 Moirai**：全部權重 `cc-by-nc-4.0`（V）。**不要用 Lag-Llama**：GIFT-Eval MASE 1.2276，輸給 seasonal naive（V）。
- **(b)** GPU ~1 秒／CPU ~2–5 秒（估計，U）。
- **(c)** 當作 Chronos 的第二意見；若兩個基礎模型**方向不一致**，那本身就是「這個資料上沒有穩定訊號」的證據。
- **(d)** 同第 2 名的門檻。**另外：如果它贏了但 Chronos 沒贏，不要只報贏的那個**——
  那正是 §5.2(6) 的多重比較陷阱，該用 Model Confidence Set 回報「分不出高下的集合」。

### 誠實的總結句（建議直接當簡報的那一頁）

> 「我們沒有做趨勢預測器。我們做的是**把趨勢預測這件事拿去量**。
> 量的結果第一個推翻的是我們自己的預設：**在注意力資料上，seasonal naive 不是強基線，它是最弱的那一個**
> （MASE 1.086，輸給最笨的 naive 27.9%）。要打敗的是季節指數×SES 的 **0.706**。
> 基礎模型要進產品，得先跨過這個數字 10% 且 p<0.01；跨不過我們就報表不報模型。
> 而且不論跨不跨得過，它都**不會進排序**——§3.15 量過 28 組，全部變差。」

---

## 我無法核實的部分

- **M5 的官方論文正文**：ScienceDirect 對本機回 403／captcha，`unic.ac.cy` 的 M5 頁沒有結果數字。
  §1.2 的**所有數字來自官方 `Scores and Ranks.xlsx`（V）**，但「M5 組織者在論文裡怎麼措辭他們的結論」**未核**；
  參賽隊伍的確切數目未核（官網只寫「近 6,000 名參賽者／近 100,000 次提交」）。
- **CPU 推論秒數**：除 Chronos 官方卡片的數字外，TimesFM／Moirai／Lag-Llama 皆**沒有公布的延遲數字**，
  §2.2 與 §8 的 CPU 秒數是依參數量與前向次數推估。
- **TimeGPT 的免費額度與定價**：`nixtla.io/pricing` 與 `docs.nixtla.io` 皆 404，只有「Book a free trial」。
- **GTM-Transformer 表中帶 `**` 那一列（WAPE 54.2）的註腳意思**：未查到定義 → 本檔一律引用 **55.2**。
- **Boone, Ganeshan, Hicks & Sanders, *Can Google Trends Improve Your Sales Forecast?*（*POM* 27(10), 2018,
  doi:10.1111/poms.12839）的確切改善幅度**：全文付費牆、找不到 OA 版，摘要無數字 → **不要引用任何百分比**。
- **Fu & Fang（M&SOM 2023）的 24–57%**：只核到摘要逐字，**未讀到方法與「current practice」的定義**。
- **Coupé（2018）對 Choi & Varian 的複製研究結論**：EconStor／De Gruyter 皆擋機器人，全文未取得。
- **Vosen & Schmidt（2011）、Carrière-Swallow & Labbé（2013）的確切 RMSE 改善**：付費牆，只核到摘要主張。
- **基礎模型在零售／時尚上的同儕審查數字**：IEEE BigData 2024 那篇全文付費牆，摘要無數字。
- **Chronos 的 TMLR 接受狀態**：由 repo 連向 OpenReview 推得，arXiv metadata 本身沒有 journal ref。
- **Lag-Llama 的 NeurIPS 2023 R0-FoMo workshop 版本**：arXiv abs 頁未載明。
- **Diebold–Mariano 在 h>1 的 HAC／HLN 小樣本校正細節**：沿用領域常識，未讀原文。
- **§7 的外部效度**：我只量了英文維基百科的注意力序列。**它與台灣市場的服飾需求之間沒有任何已驗證的係數**，
  這一點 `live-trend-sources.md` §3.2 已經寫過，本輪沒有任何新證據改變它。
