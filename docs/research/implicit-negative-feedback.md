# 「看過但沒選」要怎麼估？隱性負回饋、曝光偏差與疲勞項的原理化

> 作者：sub-agent `implicit-negative-feedback`，2026-09-18。
> 讀過的程式：`engine02/pipeline.py::_terms`、`engine02/config.py`、`engine02/preference.py`、
> `engine02/service.py::_learn_preferences`、`engine02/contracts.py`、`engine02/explain.py::template_reasons`、
> `engine02/rerank.py::Term`、`engine02/handshake.py`、`engine02/diversify.py`、`scripts/eval_fatigue.py`、
> `reports/server/fatigue/`、`reports/ablation/fatigue_kagl_hash-256.json`、`docs/engine02-design.md` §3.23、
> `docs/research/industry-recsys-practice.md` §2.6／建議 #2、`docs/research/recsys-slate.md`、`docs/research/recsys-preference.md`。
> **沒有修改任何既有檔案。** 本文新增的量測都是丟棄式 probe（`Engine02` 子類，跑在 scratchpad），
> 要進 repo 的話請照 §7 的 `檔案:函式` 清單重寫。
>
> ⚠️ **引用驗證狀態**：本次 session 的 WebSearch 配額在開工前就已用盡（200/200），
> DBLP／ACM DL 的網頁介面又擋自動抓取。所有驗證都是用 WebFetch 直接抓 arXiv／OpenAlex／
> 作者自架 PDF 再用 PDF reader 讀全文完成的。下面每一條引用都標了驗證等級：
> **[V]** = 本次直接讀到原始論文／PDF／arXiv／OpenAlex 條目確認，數字是引用或近似轉述；
> **[T]** = 只有訓練知識，標題／會議／年份高信心但**本次沒有重新驗證**；
> **[?]** = 有衝突或找不到，**上台前必須自己查**。
> 把 [T] 當「大概對，引用前請自己核一次」，[?] 當「先不要寫在簡報上」。

---

## 0. 一頁結論

### 0.1 方法對照表

| 方法 | 它實際估計的是什麼 | 需要什麼資料 | 我們現在有嗎 | 建議 |
|---|---|---|---|---|
| **現行：flat −w·count** | 什麼都沒估。是一個手設的「每次被忽略扣 0.15 分」規則 | 只要 `shown_item_ids` | ✅ 有 | ⚠️ 留著機制、**換掉參數化與說法**（§7 建議 1–3） |
| **IPS / clipped IPS**（Joachims, Swaminathan & Schnabel, WSDM 2017, arXiv:1608.04468 [V]） | 無偏的 relevance／ranking loss，把曝光機率除掉 | **記錄下來的 propensity**（當時每個位置被排到的機率），或隨機化流量 | ❌ 沒有。我們是決定性排序，propensity 恆等於 1 或 0 | ❌ 不可行。論文自己記載小樣本失效：在最小的 1,700 次點擊上，**有偏的 naive 估計反而贏過無偏的 IPS**（變異數太大）[V] |
| **SNIPS**（Swaminathan & Joachims NeurIPS 2015 [T]） | 同上，但自我正規化以降變異數 | 同上 | ❌ | ❌ 不可行 |
| **Doubly Robust**（Dudík, Langford & Li, ICML 2011 [V] 存在性；Jiang & Li ICML 2016 [T]） | 同上，propensity + 一個 reward model 互補 | 同上 ＋ 一個 outcome model | ❌ propensity 這半永遠缺 | ❌ 不可行 |
| **PBM（位置基礎點擊模型）** | P(C=1) = α_uq · γ_r，把點擊拆成 **attractiveness（只看 item）× examination γ_r（只看 rank）**（Craswell, Zoeter, Taylor & Ramsey, WSDM 2008；公式經 Chuklin/Markov/de Rijke 2015 專書確認 [V]） | 同一個 item 出現在**不同位置**的大量 impression | ❌ 資料量差 2–3 個數量級 | ✅ **借它的結構，不估它的參數**——這是我們的主建議 |
| **Cascade / DBN / UBM**（Craswell 2008；Chapelle & Zhang WWW 2009；Dupret & Piwowarski SIGIR 2008；公式經 2015 專書確認 [V]） | 逐位置瀏覽、滿意後離開的序列模型（DBN 還把 perceived 與 actual relevance 分開） | 同上，且需要點擊位置序列 | ❌ | ❌ 但「排名 1 幾乎必定被檢視」這個先驗來自這一系 |
| **regression-EM**（Wang, Golbandi, Bendersky, Metzler & Najork, WSDM 2018 [V]） | 從單一排序器的 log 反推 γ_rank，**不需隨機化** | 為個人搜尋的稀疏點擊設計，但仍是生產規模 | ❌ | ❌ 不可行。**而且在 Agarwal et al. WSDM 2019 的正面對比中，它在 877,689 次 Google Drive 查詢上仍「substantially off」** [V] |
| **intervention harvesting / AllPairs**（Agarwal, Zaitsev, Wang, Li, Najork & Joachims, WSDM 2019, arXiv:1812.05161 [V]） | 從「多個排序器意外造成的位置交換」估 γ_rank，不需主動隨機化 | 多排序器長期共存的 log。實測規模：arXiv 搜尋 **53,000 查詢／25,600 點擊**；Google Drive **877,689 查詢／2 週**。合成資料的下限約 **20,000 查詢/排序器** | ❌ 我們只有一個 serving arm | ❌ 不可行。這是**最省資料**的方法，仍差我們 2–3 個數量級 |
| **RandPair / FairPairs / RandTopN 隨機化**（Radlinski & Joachims, AAAI 2006 [V]；Joachims WSDM 2017 的 swap(1,k) [V]） | 直接實驗估 γ_rank | 主動互換卡片位置並犧牲線上品質。FairPairs 實測：arXiv 搜尋 **44,399 查詢／48,976 點擊／約 3 個月**，而且只有最前面幾組 rank-pair 在 95% CI 下分得開 [V] | ⚠️ 技術上做得到（我們控制排序），但 demo 只有 2–4 輪 | ❌ 不要在 demo 做。列為「有真人 log 之後的第一步」 |
| **固定先驗 examination curve** ε(rank) | 不估，直接假設。把「被忽略」的證據強度依位置打折 | 只要 `shown_item_ids` **的顯示順序** | ✅ 有（`ChoiceRecord.shown_item_ids` 是排序過的） | ✅ **採用**，並用 Joachims et al. SIGIR 2005 的 eye-tracking 曲線當預設值（§2.3、§3.2、§7 建議 2） |
| **eye-tracking 直接量** | 使用者實際注視每個位置的比例 | 幾十位受試者＋眼動儀（Joachims et al. SIGIR 2005 只用了 **29 位**可用受試者 [V]） | ❌ 沒做 | ⚠️ **唯一小樣本可行的方法**。我們借它**已發表的數字**當先驗，自己做則列為 future work |
| **多型回饋分流：click / unclick / dislike**（Xie, Ling, Wang, Wang, Xia & Lin, *Deep Feedback Network*, IJCAI 2020，騰訊 [V]） | 把三種回饋當**三個不同的訊號通道**分開建模，而不是把 unclick 當 dislike | 生產規模的 impression log | ❌ 模型跑不了 | ✅ **設計上的背書**：它證實我們把「排除／否決／被動忽略」分成三層是業界做法（§4.7） |
| **頻次上限 frequency capping** | 不估效用，是**業務規則**：同一件在一個 session 內最多有效曝光 N 次 | 曝光計數 | ✅ 有 | ✅ **採用，且它是頭部唯一可靠的機制**（§5、§7 建議 1） |
| **ExpoMF 曝光潛變數**（Liang et al. WWW 2016 [V]） | 把「沒被看到」和「看到但不喜歡」分開的潛變數模型 | 大量 user×item 互動 | ❌ 一個 session 沒有 | ❌ 但它的**論點**就是我們的論點（§4） |
| **Recommendations as Treatments**（Schnabel et al. ICML 2016 [V]） | 用 propensity 去偏的評分預測／評估 | propensity 或 MNAR 模型 | ❌ | ❌ 不可行 |
| **離散選擇 likelihood（已經在跑）** | 品味方向 Δβ。「選了 i」對展示集合 K 個選項而言，**其餘 K−1 件已經在 softmax 分母裡** | `shown_item_ids` ＋ `chosen_item_id` | ✅ **已經在服務路徑上跑**（`service.py::_learn_preferences`） | ✅ 這是品味訊號的**唯一**正確位置（§4） |

### 0.2 六句話結論

1. **能估的都估不了。** IPS／SNIPS／DR 全部需要 logged propensity，我們的排序是決定性的，propensity 不存在。
   最有力的一個數字：Agarwal et al. WSDM 2019 在一個**和我們幾乎同構的版面**（Google Drive 的
   autocomplete overlay，**一次最多 5 筆**）上估位置偏差，用了 **877,689 次查詢／兩週**，
   而且其中 75.26% 的查詢對估計毫無貢獻，regression-EM 在這個規模上**仍然「substantially off」** [V]。
   我們有 **240 個 ranking event**。誠實答案就是 **§2 的「沒有任何一個可行，只能用先驗」**。
2. **但先驗不必是我們捏的。** eye-tracking 是本文查到的方法裡**唯一小樣本可行**的一條
   （Joachims et al. SIGIR 2005 只用了 29 位可用受試者），而它剛好發表了**前 5 個名次的注視比例**：
   正規化後 **ε = (1.00, 0.85, 0.71, 0.47, 0.37)** [V]。這就是建議的 examination 先驗——
   **借一條已發表的真人量測，而不是估一條我們估不出來的**。
3. **疲勞項**不是品味訊號，是 **session 內的位置加權頻次上限**。品味訊號已經被 `service.py::_learn_preferences` 的 Bradley–Terry likelihood 吃掉了（§4）。
4. **現行 −0.15 在頭尾兩端都做錯了事。** 實測 5k 池：排名 1 到排名 6 的分數差中位數 **0.496**，排名 5 到排名 6 是 **0.000**。−0.15 推不動頭部、卻輕易洗掉尾部——也就是說，它保留了使用者**確定看過並跳過**的那一張，換掉使用者**可能根本沒看到**的那一張。
5. 實測第 1 輪排名 k 的商品到第 3 輪還在畫面上的機率（5k、w=0.15）：**r1=0.90、r2=0.85、r3=0.75、r4=0.62、r5=0.55**——單調遞減，方向完全相反。
6. **加法分數項不是保證頭部換掉的正確工具**：要把排名 1 的持續率壓到 0.28 需要 w≈3.0（今天的 20 倍），那會讓「你還沒看過它」這一行壓過「它符合你要的條件」，卡片就開始說謊。**頭部要用硬上限，尾部才用分數項。**

---

## 1. Q1：什麼才是對的估計量？

### 1.1 先把問題講清楚：我們到底想估什麼

「看過但沒選」可以對應三個**完全不同**的量，混在一起就會得到手設常數：

| 想估的量 | 形式 | 需要什麼 | 可辨識嗎 |
|---|---|---|---|
| (a) **這件商品的效用比較低** | Δ 在 item 的 relevance 上 | 要先知道使用者有沒有看到它 | ❌ 與 examination 不可分辨（§2） |
| (b) **這個品味方向使用者不要** | Δβ 在設計要素軸上 | 選擇 ＋ 展示集合 | ✅ **已經在估**（`service.py`，Bradley–Terry） |
| (c) **再看到同一件的邊際價值變低** | Δ 在 (item, 曝光次數) 上 | 曝光計數 | ✅ 不需要估，是重複曝光的定義 |

**現行 `_terms` 的 fatigue 項寫的是 (c) 的形式（item-identity、計數、不 z 標準化），但 `config.py` 的註解與 `docs/engine02-design.md` §3.23 的敘事都在講 (a)（「隱性負回饋」）。** 這個落差就是「手設 −0.15」的根源：一旦說它在估 (a)，就會被問「你的估計量是什麼、變異數多少」，而答案是沒有。一旦承認它在做 (c)，它就是一個有文獻、有業界預設值的**頻次上限**，權重也就有了操作定義（§5、§7）。

### 1.2 生產環境（有線上證據）

| 系統 | 對「曝光未點擊」做什麼 | 估的是什麼 | 需要的資料 | 我們能不能照做 |
|---|---|---|---|---|
| **YouTube 排序網路**（Covington, Adams & Sargin, RecSys 2016 [V] 標題／會議；負例機制 [T]，線上部署） | **直接把「曝光了但沒點」當排序網路的負例**，正例用觀看時間加權 | P(click)／觀看時間 | 一般的 impression＋click log，**不需要 propensity** | ⚠️ 這是「未點擊＝硬負例」在生產環境最有名的先例。但它是**跨使用者、億級樣本**的統計平均；我們是**單一使用者、20 個 impression**，同一個做法在這裡沒有統計意義（§4.3） |
| **YouTube 多任務排序**（Zhao et al., RecSys 2019, *Recommending What Video to Watch Next* [V] 標題／會議，shallow tower 細節 [T]，線上部署） | 一個 **shallow tower** 專門吃位置與裝置特徵，訓練時把它的輸出加到主 logit、服務時把位置特徵固定成常數，於是位置偏差不進排序分數 | P(engagement \| features) 拆成無偏 relevance ＋ 位置偏差項 | 巨量 impression＋點擊＋**服務時的位置記錄**（不需隨機化） | ❌ 資料量差太遠。但「把位置當獨立、可拔掉的加性項」這個結構就是我們 §3 的形式，只是我們**設**它而不是**學**它 |
| **YouTube REINFORCE off-policy**（Chen, Beutel, Covington, Jain, Belletti & Chi, WSDM 2019, arXiv:1812.02353 [V]，線上部署） | 用 importance weighting 校正歷史策略（推廣到 top-K slate）；未點擊不當硬負例 | 校正後的策略梯度 | 需要**歷史策略的動作機率** | ❌ 沒有 propensity |
| **騰訊 Deep Feedback Network**（Xie et al., IJCAI 2020 [V]，論文自述已部署） | **click / unclick / dislike 三種回饋各走各的模組**，明確不把 unclick 當 dislike | 三通道的 engagement 分數 | 生產規模 log | ✅ **這是我們三層設計（排除／否決／被動忽略）最直接的業界背書**，而且它的核心主張就是 §4 的主張：unclick ≠ dislike |
| **Taobao ESMM**（Ma, Zhao, Huang, Wang, Hu, Zhu & Gai, SIGIR 2018, arXiv:1804.07931 [V]） | 在**全曝光空間**用 pCTR × pCTCVR 鏈式建模，避開「只在點擊樣本上訓練 CVR」的樣本選擇偏差 | 全量曝光＋點擊＋轉換 | ❌ 模型跑不了 | ⚠️ 教訓可用：**曝光空間才是正確的訓練空間**，未點擊曝光有資訊，但資訊要用模型結構表達，不是手設常數 |
| **YouTube DPP 多樣化**（Wilhelm et al., CIKM 2018 [T]，線上部署於 YouTube） | slate 內多樣化，不處理跨輪重複 | 行列式體積（slate 內相似度） | slate 內 embedding | ✅ 我們已經有（`diversify.py`，θ=0.9）——但它**管不到跨輪**（§5） |
| **Netflix Calibrated Recommendations**（Steck, RecSys 2018 [T]） | 把推薦清單的類別分布校正到使用者歷史分布，是**後處理約束**不是學到的效用項 | 分布距離 | 使用者歷史類別分布 | ⚠️ 框架可借（「約束而非效用」），但需要歷史 |
| **Zalando session 重排**（[1908.08284](https://arxiv.org/abs/1908.08284)，recsysXfashion'19 [T]，回報線上 CTR 提升） | 用 session 內互動把少數真正相關的往上拉 | session 內 re-ranking 分數 | session 互動 log | ⚠️ 已在 `industry-recsys-practice.md` 引用過；它**不是**「未點擊即負例」的證據 |
| **Zalando session 互補推薦**（[1908.08327](https://arxiv.org/abs/1908.08327)，2,800 萬活躍客戶，線上 A/B 購買 +3.24% [T]） | 同上 | 同上 | 同上 | ⚠️ 同上 |
| **Myntra Diversify and Conquer**（[2309.14046](https://arxiv.org/abs/2309.14046) [T]） | 把多樣性當首頁 bandit 的**一級約束** | bandit reward ＋ 約束 | 線上流量 | ✅ 框架支持「不要一直給同樣的東西 = 約束」 |
| **廣告頻次上限（Meta／Google）** | 直接**硬上限**：同一創意在時間窗內最多曝光 N 次 | 不估效用，是規則 | 曝光計數 | ✅ **完全照做得到**。具體預設值見 §5.3（部分 [?]） |

### 1.3 論文（沒有線上證據，或證據在論文自己的離線資料上）

| 方法 | 估的是什麼 | 需要的資料 | 對我們 |
|---|---|---|---|
| **ExpoMF**（Liang, Charlin, McInerney & Blei, WWW 2016, arXiv:1510.07025 [V]） | 引入曝光潛變數，**明確主張**把所有未消費商品當負例會混淆「沒被曝光」與「曝光了但不喜歡」 | 大量 user×item | ❌ 用不了模型，但**它的論點就是我們 §4 的論點** |
| **Recommendations as Treatments**（Schnabel, Swaminathan, Singh, Chandak & Joachims, ICML 2016, arXiv:1602.05352 [V]） | propensity 加權的去偏學習與評估 | propensity | ❌ |
| **隱性回饋信賴度加權**（Hu, Koren & Volinsky, ICDM 2008 [T]） | 把未觀察到的互動當「低信賴度的 0」而不是「確定的負例」 | 大量互動 | ⚠️ **概念直接可用**：未點擊的正確處理是**降低信賴度**，不是給負分。這是 §4 推薦的理論依據之一 |
| **BPR**（Rendle, Freudenthaler, Gantner & Schmidt-Thieme, UAI 2009, arXiv:1205.2618 [V]） | 成對排序似然 P(i ≻ j)：互動過的 ≻ 沒互動過的，**不是硬負例，只是「比較不偏好」** | 互動對 | ⚠️ 注意：BPR 用的是「未**觀察**」，不是「已展示未選」。我們的情況更強（確定展示過），所以成對似然更合理——**而那正是 `preference.py::comparison_pairs` 已經在做的事**（§4） |
| **XDM**（Lv et al., 2020, arXiv [V]，論文級） | 明確把**曝光但未點擊的序列**用 metric learning 併進序列匹配 | 大量序列 | ⚠️ 支持「未點擊曝光是有用的輔助訊號」，但方法本身需要大量資料 |
| **Spotify skip 建模 / WSDM Cup 2019**（資料集：Brost, Mehrotra & Jehan, *The Music Streaming Sessions Dataset*, WWW 2019 companion, arXiv:1901.09851 [V]，1.6 億 session） | P(skip \| track, session 上下文) | 完整連續收聽序列 | ❌ **而且結構上不類比**：skip 是使用者的**主動動作**（相當於我們的 `rejected_item_ids`），不是「看過沒選」。另外值得注意：這個資料集**刻意用均勻隨機推薦策略收集了一個子集**，就是為了能做 counterfactual 評估——這正好說明「要有 propensity 必須刻意去隨機化」（§2.2） |
| **Spotify 多樣性消費**（Hansen, Mehrotra, Hansen, Brost, Maystre & Lalmas, *Shifting Consumption towards Diverse Content on Music Streaming Platforms*, **WSDM 2021** [V]） | 多樣性與長期消費的關係 | 長期 log | ❌ ⚠️ **注意**：常被誤引成「WSDM 2020 / on Spotify」，正確的是 WSDM 2021 與上面的標題 |
| **Pinterest** | — | — | ⚠️ PinnerSage（Pal et al., KDD 2020, arXiv:2007.03634 [V]）只做多模態使用者向量，**與 skip／hide／疲勞無關**。我**找不到** Pinterest 公開發表的疲勞懲罰或 skip-as-negative 論文 **[?]**，**不要在簡報上聲稱有** |
| **使用者疲勞建模**（Alibaba／Tencent 的 SIGIR／CIKM 一系列） | P(click \| 該類目近期曝光次數) | 長期跨 session 曝光 log | ❌ **[?] 兩位研究 agent 都找不到可靠引用（OpenAlex 搜到的都是醫學 fatigue 論文）。上台前不要提。**最接近的可驗證論文是上面的騰訊 DFN（IJCAI 2020） |
| **mere exposure vs. wear-out**（Zajonc, JPSP 1968 [V]；Bornstein 1989、Montoya et al. 2017 meta-analysis [T]） | 重複曝光對好感度的倒 U 形效果（約 10–20 次後下降） | 心理學實驗 | ⚠️ **重要的反面證據**：文獻說前幾次重複曝光是**增加**好感的。所以「第 2 次看到同一件就扣分」在心理學上沒有支持，只有在「使用者已經主動給了回饋、期待畫面改變」這個**互動契約**上有支持。這強化了 §4 的結論：它是介面承諾，不是效用估計 |

**結論（Q1）**：沒有一個估計量可以用。所有無偏方法的共同前提是 logged propensity 或隨機化流量，兩者我們都沒有，而且在一個 2–4 輪的 demo 裡拿不到。
**可以誠實做的只有兩件事**：(i) 借 PBM 的**結構**（examination × relevance）但用**先驗**填 examination；(ii) 把整件事重新定義成**頻次上限**，那是一個規則，規則不需要估計量，只需要一個能講清楚的預設值。

---

## 2. Q2：位置偏差是明顯的干擾項——標準做法哪些對我們可行？

### 2.1 標準做法與它們的資料需求

我們的資料量：60 個模擬使用者 × 4 輪 ≈ **240 個 ranking event**（約 1,200 個 item-slot 觀測）。
下表的「論文／部署規模」全部是本次直接讀 PDF 或 arXiv 原文確認的數字 [V]。

| 做法 | 怎麼做 | 論文／部署實際規模 [V] | 我們（≈240 個 ranking event） |
|---|---|---|---|
| **eye-tracking 先驗** | 直接量使用者注視哪裡（Granka, Joachims & Gay, SIGIR 2004：36 人收 26 人可用、397 次查詢；Joachims, Granka, Pan, Hembrooke & Gay, SIGIR 2005：34 人收 **29 人**可用） | **幾十位受試者**、實驗室等級 | ✅ **唯一小樣本可行的一條。** 我們自己做要真人與眼動儀（future work），但**它已發表的數字可以直接當先驗用**（§2.3） |
| **FairPairs / RandPair 隨機化** | 主動互換相鄰位置，比較兩位置點擊率（Radlinski & Joachims, AAAI 2006） | arXiv 搜尋引擎線上：**44,399 查詢／13,304 個 IP／48,976 點擊／約 3 個月**，而且只有最前面幾組 rank-pair 在 95% CI 下分得開 | ❌ 差約 200 倍，而且會犧牲 demo 品質。Wang et al. WSDM 2018 明確把 RandPair／RandTopN 列為「會傷害使用者體驗」 |
| **swap(1,k) intervention** | 把排名 1 換到第 k 名，比較 CTR（Joachims et al., WSDM 2017） | 生產部署：21 天點擊 log，其中 **7 天**做 swap 實驗；訓練集 **5,437** 次點擊事件、驗證集 **1,755**；擬合出的衰減曲線底部 p_r ≈ **0.12** | ❌ 而且論文自己記載：在最小的 **1,700** 點擊規模上，**naive 估計贏過無偏的 IPS** |
| **regression-EM** | 交替估 relevance 與 γ_rank，**不需隨機化**（Wang, Golbandi, Bendersky, Metzler & Najork, WSDM 2018） | 為個人搜尋的稀疏點擊設計，仍是生產規模 | ❌ 而且在 Agarwal et al. 2019 的正面對比中，它在 **877,689 次 Google Drive 查詢**上仍「substantially off」 |
| **dual learning**（Ai, Bi, Luo, Guo & Croft, SIGIR 2018, arXiv:1804.05938） | 同時學排序器與 propensity 模型 | Yahoo LTR（≈**19,944** 查詢）、Istella、MSLR-WEB10K | ❌ |
| **intervention harvesting / AllPairs**（Agarwal, Zaitsev, Wang, Li, Najork & Joachims, WSDM 2019） | 利用「多排序器共存時同一 item 落在不同位置」的自然實驗，不需主動隨機化 | arXiv 搜尋：**53,000 查詢／25,600 點擊**（3 個排序器）；Google Drive：**877,689 查詢／2 週**。合成資料下限約 **20,000 查詢/排序器** | ❌ 我們只有一個 serving arm。而且這是**最省資料**的方法（作者自述比次佳的 local estimator 省一個數量級），仍差我們 2–3 個數量級 |
| **trust bias 修正**（Agarwal et al., WWW 2019 [T]；Vardasbi et al., CIKM 2020 仿射修正 [T]） | 把「因為排名高就信任」和「真的相關」分開 | 比 PBM 更大 | ❌ ⚠️ 這兩篇本次**沒有驗證到**，引用前請自己查 |

**順帶一個重要的 [V] 事實**：Agarwal et al. 2019 自己量到 **MSE 隨 examination 曲線變陡而急速上升**——
曲線越陡，底部名次的點擊就越少、越估不準。這對我們是雙重壞消息：樣本少、而且我們想估的正是陡不陡。

### 2.2 直說：**一個都不可行，只能用先驗**

**答案是「none, use a prior」。** 理由不是「我們懶」，而是三個結構性障礙，每一個單獨就足以否決：

1. **決定性排序 → propensity 不存在。** `pipeline.Engine02.run` 是 argsort，同一個 request 永遠給同一個順序。IPS 的分母 P(rank \| item, context) 是 0/1，除下去不是無偏，是除以零或乘以 1。
2. **同一件商品沒有位置變異。** 所有 θ_rank 估計法的可辨識性都來自「同一個 item 出現在不同位置」。實測（§0.2 第 5 點）第 1 輪排名 1 的商品到第 3 輪還在畫面上的機率是 0.90，而且通常**還在同一個位置附近**——這正是位置變異最小的情況。
3. **樣本量差 2–3 個數量級。** 240 個 ranking event，其中「同一 item 出現在 ≥2 個不同位置」的事件只有幾十個。任何 EM 都會收斂到先驗。

**最有力的一個引用**（[V]，一定要記住）：Agarwal et al. WSDM 2019 裡有一個**和我們幾乎同構**的實測場景——
**Google Drive Search 的 autocomplete overlay，一次最多只顯示 5 筆結果**。
他們在上面跑了 **877,689 次查詢／兩週**才把 examination 曲線估出來，而且：

- **75.26% 的查詢**在兩個排序器下拿到**完全相同的 top-5**，對估計毫無貢獻；
- 剩下的查詢裡，還有 74.5% 的 result-pair 落在同一個名次；
- 在這個規模上，**regression-EM 仍然「substantially off」**，naive CTR 更差。

也就是說：**「一次 5 筆」這個版面已經有人在真實世界估過位置偏差了，他們需要 88 萬次查詢。我們有 240 次。**
這是「一個都不可行」最乾淨的證據，而且不是我們推論出來的，是別人量出來的。

**要誠實地說的一句話**：「位置偏差我們沒有辦法估，所以我們沒有估。我們**借了一條已發表的 examination 曲線**當先驗，
把它寫在 config 裡當成一個可以被質疑、可以被替換的假設，而不是假裝我們學到了它。」

### 2.3 先驗該長什麼樣：把眼動儀的數字借過來

#### (a) 先修正一個我原本要寫錯的東西

文獻常用的參數化是 θ_r = (1/r)^η。**η=1（也就是 θ_r = 1/r）在 Joachims et al. WSDM 2017 與
Agarwal et al. WSDM 2019 裡都是合成實驗的預設值 [V]**，η 只有在測「模型設定錯了會怎樣」時才被掃到 [0, 2]。
**但這兩篇（以及 Ai et al. SIGIR 2018、Wang et al. WSDM 2018）都沒有報告「從真實資料估出 η≈1.0–1.5」這種數字**——
我本來想引的那個區間**查不到來源 [?]，不要用**。η=1 是**合成實驗的慣例**，不是實測值。

#### (b) 真正有數字的地方：eye-tracking（而且它剛好只有 5 個名次）

Joachims, Granka, Pan, Hembrooke & Gay, *Accurately Interpreting Clickthrough Data as Implicit Feedback*,
**SIGIR 2005**（29 位可用的眼動受試者）**Figure 1** 報告了**各名次被注視的比例** [V]：

| 名次 | 被注視的比例（Fig 1，讀圖近似） | 正規化到名次 1（＝ε） |
|---|---|---|
| 1 | ~65–70% | **1.00** |
| 2 | ~55–60%（**幾乎和名次 1 一樣**） | **0.85** |
| 3 | ~48% | **0.71** |
| 4 | ~32% | **0.47** |
| 5 | ~25% | **0.37** |
| 6 | ~18% | 0.27 |
| 7–10 | ~10–12%（換頁效應） | ~0.16 |

同一篇的 **Table 2** 有精確發表值可以佐證上緣：**點擊名次 1 之前看過名次 1 的比例 = 90.6%；
點擊名次 2 之前看過名次 2 = 90.5%；點擊名次 3 之前看過名次 1 = 73.9%、看過名次 2 = 82.6%** [V]。

⚠️ Fig 1 的數字是**讀長條圖近似**的，不是論文表格裡的精確值；要寫進簡報請標明「約」。

#### (c) 這條曲線該怎麼用，以及為什麼它對我們是保守的

| 曲線 | ε=(r1…r5) | 平均 | 性質 |
|---|---|---|---|
| flat（＝現行，也是我們模擬器的假設） | 1.00, 1.00, 1.00, 1.00, 1.00 | 1.00 | 假設 5 張一定看完 |
| **eye-tracking（建議預設）** | **1.00, 0.85, 0.71, 0.47, 0.37** | **0.68** | 已發表、真人量測、剛好覆蓋 5 個名次 |
| 冪律 η=0.5 | 1.00, 0.71, 0.58, 0.50, 0.45 | 0.65 | 和上面很接近，可當敏感度對照 |
| 冪律 η=1.0（文獻合成預設） | 1.00, 0.50, 0.33, 0.25, 0.20 | 0.46 | 對尾部最保護，但對 5 張卡幾乎確定太陡 |
| 冪律 η=1.5 | 1.00, 0.35, 0.19, 0.13, 0.09 | 0.35 | 太陡，不要用 |

注意 eye-tracking 曲線**配不上任何單一 η**：名次 1→3 幾乎持平（等效 η≈0.23–0.31），
名次 3→5 才明顯掉（等效 η≈0.54–0.62）。**真實的注意力在前幾名是平的、然後才斷崖**，
冪律抓不到這個形狀——這本身就是「不要用冪律、直接用查表」的理由。

**為什麼借一個「10 條藍色連結」的曲線對我們是安全的**：SIGIR 2005 的版面是**垂直清單、要捲動**；
我們是**一排 5 張卡、通常一個畫面就看完**，所以我們真實的 ε 應該**比它更平（更高）**。
用一條偏低的 ε 會讓尾部的懲罰**偏小**，也就是**少誤傷**使用者可能還沒看到的商品——
誤傷正是這一項唯一可能真的傷害使用者的方向。所以這個借用在風險上是往安全邊靠的。

**還有一個 [V] 的支持**：Joachims et al. WSDM 2017 §7.5（Robustness to Misspecified Propensities）
量到「設定錯但保守的偏差模型，仍然明顯勝過完全不做偏差修正」。
（⚠️ 注意方向不能直接照搬：IPS 是把 propensity 放在**分母**，我們是**乘上** ε，正負號的推論不一樣。
所以只引用「一個粗略的固定先驗勝過完全不修正」這個結論，不要引用它的方向性。）

---

## 3. Q3：per-position／per-round 先驗比 flat 懲罰好嗎？

### 3.1 為什麼 flat 一定是錯的：測到的數字

**(a) flat −0.15 推不動頭部。** 5k 池、40 句查詢、`full_zclip3_nofatigue`、HashEncoder，排名 k 到排名 6 的分數差（中位數）：

| 排名 k | s_k − s_6（中位數） | −0.15 夠不夠把它擠出前 5？ |
|---|---|---|
| 1 | **0.496** | ❌ 差 3.3 倍 |
| 2 | 0.420 | ❌ 差 2.8 倍 |
| 3 | 0.270 | ❌ 差 1.8 倍 |
| 4 | 0.092 | ✅ 夠 |
| 5 | 0.000 | ✅ 綽綽有餘 |

（s1−s6 的分位數：p25 = 0.155、中位數 0.496、p75 = **1.210**。）

**(b) 所以它只洗尾部，不洗頭部。** 直接量「第 1 輪排名 k 的商品，到第 3 輪還在畫面上」的機率（5k、40 句、模擬使用者固定選第 3 張）：

| 設定 | r1 | r2 | r3* | r4 | r5 | novelty@R3 | 懲罰總量 |
|---|---|---|---|---|---|---|---|
| **flat w=0.15（現行）** | **0.90** | 0.85 | 0.75 | 0.62 | 0.55 | 0.190 | 0.150 |
| flat w=0.50 | 0.78 | 0.72 | 0.62 | 0.57 | 0.50 | 0.255 | 0.500 |
| **ε=r⁻¹, w=0.50** | **0.72** | 0.75 | 0.47 | 0.78 | 0.70 | 0.210 | **0.228** |
| ε=r⁻¹, w=0.80 | 0.72 | 0.70 | 0.38 | 0.82 | 0.75 | 0.195 | 0.365 |
| ε=r⁻⁰·⁵, w=0.50 | 0.75 | 0.82 | 0.55 | 0.75 | 0.60 | 0.220 | 0.323 |
| ε=r⁻¹, w=1.5 | 0.62 | 0.65 | 0.15 | 0.68 | 0.68 | 0.310 | 0.685 |
| ε=r⁻¹, w=3.0 | **0.28** | 0.57 | 0.00 | 0.55 | 0.68 | 0.385 | 1.370 |

\* r3 這一欄**不可解讀**：probe 的模擬使用者永遠選第 3 張，所以第 3 名在第 1 輪被排除在懲罰之外、卻在後續輪次以其他排名被懲罰。這是 probe 的人工痕跡，不是發現。

**四個可以直接引用的結論**：

1. **examination 加權以不到一半的懲罰總量，換到比 flat 更好的頭部位移**：ε=r⁻¹／w=0.5 的平均懲罰是 0.228（flat 0.5 的 46%），r1 持續率 0.72 比 flat 0.5 的 0.78 更低。**每單位懲罰的頭部位移效率更高**，因為懲罰集中在我們最確定被看過的那一張。
2. **它故意讓尾部更黏**（r4 0.62→0.78、r5 0.55→0.70）。這是設計意圖，不是 bug：那兩張是使用者**可能根本沒看到**的。代價是 novelty@5 幾乎沒進步（0.190→0.210）。
3. **→ 所以 novelty@5 是錯的驗收指標。** 它把 5 個位置等權相加，於是「洗掉尾部」和「換掉頭部」得到同樣的分數，而 demo 的失敗是**頭部**（評審再看到同一張第一名）。**必須加 head-persistence 指標**（§7 建議 5）。
4. **分數項本質上推不動頭部。** 要把 r1 持續率壓到 0.28 需要 w≈3.0，是今天的 20 倍、懲罰總量 1.37——那已經大到會壓過「它符合你要的條件」這類真正的理由，卡片就開始說謊。**頭部需要的是硬上限，不是更大的權重。**

> §2.3(c) 建議的 eye-tracking 曲線 (1.00, 0.85, 0.71, 0.47, 0.37) 平均值 0.68，
> 在 w=0.5 時懲罰總量 **0.34**，最接近上表的 `ε=r⁻⁰·⁵, w=0.50` 那一列（0.323 / r1=0.75 / novelty 0.220）。
> 也就是說：**建議值的行為已經被上表包住了**，它比 η=1 的頭部位移略差（0.75 vs 0.72），
> 但它是唯一有真人量測支持的形狀。**兩個都要進 §7 建議 5 的敏感度掃描。**

### 3.2 建議的參數化（單一推薦）

```
fatigue_raw(i) = Σ_{r < t}  γ^(t−1−r) · κ_r · ε(rank_{i,r}) · 1[ i ∈ shown_r \ ({chosen_r} ∪ rejected_r) ]
term          = Term("fatigue:shown_not_chosen", "fatigue", fatigue_raw, −w_fatigue, normalize=False)

ε = (1.00, 0.85, 0.71, 0.47, 0.37)   ← 查表，不是冪律。來源：Joachims et al. SIGIR 2005 Fig 1
                                        （29 位眼動受試者的各名次注視比例，正規化到名次 1）
                                        名次 > 5 時外推用 0.27（Fig 1 的名次 6）
γ = fatigue_decay = 0.5              （不變）
κ_r = 1.0  若第 r 輪有 chosen_item_id
      0.5  若第 r 輪沒有（outside-option 輪，證據弱得多，見 §4.4）
w_fatigue = 0.5                      （從 0.15 改）
```

**加上一個硬上限（這一半才是頭部的保證）**：

```
effective_exposure(i) = Σ_{r<t} κ_r · ε(rank_{i,r})     # 不帶 γ 衰減：計數不該遺忘
若 effective_exposure(i) ≥ 1.0  →  把 i 從候選池移除這一輪
例外（必須有）：若移除後 pool < min_results + top_k，則不移除，只留分數項，並在
                constraint_report 揭露「符合條件的商品只剩 N 件」
```

`effective_exposure ≥ 1.0` 的語意剛好是廣告業的「一次有效曝光」：
名次 1 被忽略一次就滿額（1.00）；名次 2 要兩次（0.85+0.85 > 1）；名次 5 要三次（0.37×3 = 1.11）。
**這就是位置加權的 frequency capping**，而 frequency capping 不需要估計量，只需要一個能講清楚的門檻。

**為什麼 ε 用查表而不用 rank^(−η)**：因為真人眼動資料的形狀**不是冪律**——
名次 1→3 幾乎持平（等效 η≈0.23–0.31）、名次 3→5 才斷崖（等效 η≈0.54–0.62）（§2.3c）。
用單一 η 去配它，前三名和後兩名必然有一邊錯得很明顯。查表同時也讓這個先驗**看得見、可替換、可被質疑**，
這比塞一個指數進 config 更符合我們「假設要寫在明面上」的作風。

**為什麼 w=0.5 不是另一個手設數字**：它有上下界，兩邊都已經量過。

- 上界：`docs/engine02-design.md` §3.23 已經測過 **flat w=0.5** 在 44k／60 使用者／4 輪上是安全的（平均效用 p=0.90 沒掉、最佳卡片 +0.21 且 p=0.004、找到目標 0.900 p=0.50）。建議的 ε 加權版**平均懲罰總量只有 0.34**，嚴格小於那個已測安全的設定。
- 下界：它嚴格大於今天的 0.15（總量 0.34 vs 0.15）。
- 也就是說，**建議值被夾在「已測過的現行值」與「已測過的安全上界」之間**，中間變的只有**分布**（懲罰怎麼分配到 5 個位置），而分布那一半有真人量測支持。

### 3.3 怎麼驗證，而且不讓模擬器自己定義答案

**必須先講出來的循環性**：`scripts/eval_fatigue.py` 的模擬使用者在
`scores = [u[p]/τ + gumbel[p] for p in pos]` 這一行**對 5 個位置一視同仁**，也就是 ε ≡ 1。
**這正是本題要檢驗的假設。** 在 ε≡1 的世界裡，flat 懲罰就是**正確**的模型，任何 ε<1 都只是自己綁手。
所以：**這個模擬器結構上不可能選出 η，它只能排除 η。**

可行的驗證設計（把它寫成 regret 表，不是 argmax）：

1. **`scripts/eval_fatigue.py:main` 加 `--examine-eta-true`**（模擬器的真相）與 `--examine-eta-assumed`（排序器的假設），跑**二維格點**。模擬器的真相是：使用者只以機率 r^(−η_true) 「看到」排名 r 的卡；沒看到的卡**不能被選**，而且理想系統**不應該**懲罰它。
2. 報 **regret 表**：對每個 η_true，比較「排序器用 η_assumed」與「排序器用 η_true（oracle）」的差距。看的是**最大 regret（minimax）**，不是最好平均。
   - 要證明的命題是：**η_assumed=1.0 在 η_true=0 時損失很小，在 η_true=1.5 時比 η_assumed=0 好很多。** 也就是「假設有位置偏差」是不對稱地安全的。
   - 如果 η_assumed=1.0 在 η_true=0 時損失**不小**，那結論就該是留在 flat，並誠實寫下來。
3. **指標要換**（§3.1 結論 3）：
   - `head_repeat@1`：第 1 輪排名 1 的商品仍出現在第 t 輪的比例 —— **主指標，應該顯著下降**。
   - `head_repeat@1_pos1`：更嚴格，仍出現且**仍在第 1 位**。
   - `unseen_demoted@k`：被推走的商品中，**模擬器判定使用者其實沒看到**的比例 —— **誤傷指標，應該低**。這個指標只在有 η_true 的模擬器裡存在，是 ε 加權唯一能被證明有用的地方。
   - 維持 `utility_mean` / `utility_max` / `found_target` 當護欄。
4. **兩個規模都跑**（5k ＋ 44k），照 §3.5b 的慣例；本文的 gap profile 只量了 5k，44k 的候選分數分布更密、gap 可能更小，**w=0.5 在 44k 可能過強，採用前必須重量**。

**還是要說的一句**：即使上面全部跑完，我們證明的仍然是「在我們假設的使用者模型下，這個參數化不比 flat 差且誤傷更低」。**η 本身的值只有真人 eye-tracking 或線上隨機化能定**（§8）。

---

## 4. Q4：Bayesian 一致性——疲勞項是不是在重複計算偏好學習器？⭐

> 這是本 brief 最重要的一題，先給答案：
> **形式上沒有重複計算，但敘事上有，而敘事就是我們在賣的東西。**
> **建議：機制留著，但把它從「品味訊號」降級成純粹的多樣性／新穎度裝置，並讓程式碼在結構上無法被當成品味訊號。**

### 4.1 先確認事實：偏好學習器**真的在服務路徑上**，而且真的吃了「展示未選」

這不是假設，是讀出來的：

- `engine02/service.py::_learn_preferences`（第 65–86 行）在**每次 `rank()` 之前**跑
  `BayesLogistic(rationality=0.5, prior_sd=1.0, shrink_kappa=1.0).update(hist, F, beta0)`，
  把結果寫進 `req.feedback.design_weight_delta`。
- `engine02/preference.py::comparison_pairs`（第 145–157 行）的 docstring 一字不差：
  > *chosen ≻ every other shown item*
  ```python
  rows += [F[r.chosen] - F[j] for j in r.shown if j != r.chosen]
  ```
- `engine02/pipeline.py::_terms`（第 408–416 行）把 Δβ 加到設計要素的權重上。

**所以同一個事件（「第 1 輪展示了 5 件、使用者選了第 3 件」）今天在服務路徑上被讀了兩次**：
一次進 Bradley–Terry 的成對似然（4 個 pair，每個都說「被選的 ≻ 這一件」），
一次進 fatigue 項（4 件各得 −0.15）。

### 4.2 為什麼形式上**不是**重複計算

兩者作用在**不相交的量**上，這是關鍵：

| | Δβ（偏好學習器） | fatigue 項 |
|---|---|---|
| 作用對象 | 11 個**設計要素軸**上的權重 | **商品 identity** |
| 會不會外推 | ✅ 會。學到「不要正式感」之後，**從沒展示過**的正式商品也會降分 | ❌ 完全不會。沒展示過的商品這一項恰好是 0 |
| 對兩件都沒展示過的商品 | 可以改變它們的相對順序 | **永遠不能**改變它們的相對順序 |
| 是不是統計估計量 | ✅ 是。有先驗、有後驗、有 Laplace 共變異、有 κ=1 縮減 | ❌ 不是。是一個計數 |
| 消失條件 | 資料說使用者其實喜歡正式感 | 使用者沒再看到它 |

用一句可以上簡報的話：
> **Δβ 學的是「你要什麼樣的東西」，它會外推到你沒看過的商品；疲勞項記的是「你已經看過哪幾件」，它對你沒看過的商品恰好是 0。兩者的定義域不重疊，所以不是同一筆證據算兩次。**

而且 fatigue 項在**設計要素空間裡是不可表達的**——它不能寫成任何 Δβ·c(i,d)，因為它是 item-indicator。這跟 `preference.py::LinUCB` 的 optimism bonus 面臨的是同一個問題，那裡的 docstring 已經誠實寫了「cannot be written as a Δβ」。

### 4.3 為什麼敘事上**是**重複計算——而這才是真問題

`config.py` 第 41–46 行的註解、以及 `docs/engine02-design.md` §3.23 的第一句，都把這一項稱為
**「隱性負回饋」（implicit negative feedback）**。那是一個**品味主張**：「使用者看過沒選 ⇒ 使用者比較不喜歡它」。

這個主張有三個問題，每一個都足以在台上被打：

1. **這個品味推論已經被 likelihood 做完了，而且做得更好。** McFadden 條件 logit（1974 [V]）／Luce 選擇公理（1959 [V]）的整個要點就是：
   P(i \| C) = exp(u_i)/Σ_{j∈C} exp(u_j) —— **沒被選的 K−1 件已經在分母裡**。
   Jeon, Milli & Dragan（NeurIPS 2020, arXiv:2002.04833 [V]）把這個結構推廣成 reward-rational implicit choice，
   而 `preference.py` 的 docstring 引的就是它。**再額外扣一次分，就是同一份證據在品味方向上用了兩次**——
   而且第二次沒有先驗、沒有 shrinkage、沒有變異數，是一個常數。
2. **它不可辨識。** 「沒選」= 「沒看到」∪「看到了但不喜歡」。ExpoMF（Liang et al., WWW 2016 [V]）與
   Schnabel et al.（ICML 2016 [V]）的核心論點就是不能把這兩者混為一談。我們**無法**分開（§2.2），所以我們**不該**聲稱在估前者。
   Hu, Koren & Volinsky（ICDM 2008 [V]）的處理方式也不是給負分，而是**降低信賴度**（c_ui = 1 + α·r_ui，
   未觀察的配對是「低信賴度的 0」而不是「確定的負例」）。BPR（Rendle et al., UAI 2009 [V]）也一樣——
   未互動的商品只是「比較不偏好」，不是硬負例。
   **業界也是這樣分的**：騰訊 Deep Feedback Network（Xie et al., IJCAI 2020 [V]）
   把 **click / unclick / dislike 拆成三個獨立的回饋通道**，明確不把 unclick 當 dislike。
   這正好背書我們自己的三層（排除／否決／被動忽略）——但也正好說明**第三層不該用第二層的語彙**。
   ⚠️ 反方證據要一起講：YouTube 的 RecSys 2016 排序網路**確實**直接把「曝光未點擊」當負例 [T]。
   差別是規模與對象：那是**跨數億使用者**的統計平均，統計上站得住；
   我們是**單一使用者、一個 session、約 20 個 impression**，同一個做法在這裡只是一個常數。
3. **它在卡片上會說謊，而卡片是我們的賣點。** 「因為你沒選它，所以往後排」把一個系統無法支持的意圖歸給使用者。
   使用者可能只是還沒看完、在比較、或想回頭再看（§6）。

**另外一個直接的證據**：心理學那邊的方向其實是**反的**。mere exposure effect（Zajonc, JPSP 1968 [V]，Bornstein 1989／Montoya 2017 meta-analysis [T]）說前十幾次重複曝光是**增加**好感的，倒 U 形要到 10–20 次才下降。所以「第二次看到同一件就該扣分」在效用層面**沒有**文獻支持。它唯一站得住的依據是**互動契約**：使用者給了回饋、期待畫面改變。那是介面承諾，不是效用估計。

### 4.4 順手挖到的一個實際問題：「這一輪沒選」現在被當成最強的證據

`pipeline.py::_terms` 第 461 行：

```python
ignored = set(rec.shown_item_ids) - {rec.chosen_item_id} - set(rec.rejected_item_ids)
```

當 `chosen_item_id is None`（使用者只講了一句話、沒點任何卡；`handshake.py` 第 267–270 行的 `ChoiceOp` 允許這樣），
`ignored` = **全部 5 件**，每件都拿滿額 −0.15。

但在離散選擇理論裡，「什麼都沒選」是 **outside option** 事件，是**最弱**的證據——
它可能意味著 5 件都不好，也可能意味著使用者還在看、或者他的回饋是走 `AdjustOp` 那條路。
標準做法是把「不選」當成 choice set 裡一個額外的替代選項並給它自己的效用 [T]，而不是把 5 件全部當負例。
**現在的實作把最弱的證據當成最強的（5 件滿額），這個方向是錯的。**
→ §3.2 的 κ_r 就是最小修正；`preference.py` 那邊其實已經正確處理了（`comparison_pairs` 在 `chosen is None` 時不產生任何 pair）。

### 4.5 兩邊的論證，攤開來

**「應該只留在 likelihood 裡，疲勞項砍掉」的論證**
- 統計上乾淨：一個事件、一個似然、一個後驗，有先驗與 shrinkage。
- 不可辨識的量就不要估（ExpoMF／Schnabel 的論點）。
- 卡片不會說謊。
- **致命反駁**：`docs/engine02-design.md` §3.23 已經量到，**關掉這一項時第 4 輪的新穎度是 0.007**。
  Δβ 完全救不了畫面重播——因為 Δβ 是**設計要素方向**的更新，而在第 1 輪就已經最符合那個方向的商品，
  在更新之後**還是**最符合（往往更符合）。**likelihood 在數學上沒有任何理由讓同一件商品離開畫面。**
  這不是實作瑕疵，是 additive-over-features 模型的結構性質。

**「應該留著，而且不要動」的論證**
- 0.007 → 0.213 是測出來的，`p<1e-4`，而且最佳卡片效用**變好**了（+0.15, p=0.015）。
- 加法項讓它出現在分數分解裡，符合「解釋就是分數分解」的敘事。
- **致命反駁**：它今天**根本沒有出現在解釋裡**（§4.6），所以那個好處是名義上的；
  而它被稱作「隱性負回饋」則是實際上的雙重計算主張。

### 4.6 一個沒人注意到的事實：這一項在卡片上是隱形的

`explain.py::template_reasons` 第 36 行：

```python
cited = [c for c in contribs if c.cited and c.contribution > 0]
```

只有**正**貢獻會變成理由。而 fatigue 項的 raw ≥ 0、weight < 0、且 `normalize=False`，
所以它的 contribution **恆 ≤ 0**，**永遠不可能被引用成理由**。
`explain.py::GROUP_LABEL` 也沒有 `"fatigue"` 這個 key。

對比 `penalty:rejected_similarity`：它**有** z 標準化，所以「和被否決商品不像」的商品拿到**負 z × 負權重 = 正貢獻**，
於是 `GROUP_LABEL["penalty"] = "和你否決過的商品不同"` 這句話講得出來。fatigue 項因為刻意不 z 標準化，失去了這個能力。

`industry-recsys-practice.md` 建議 #2 的第 4、5 點（`explain.py` 模板、`RankedItem.demotions[]`、
`panels.py::round_diff` 的 `demoted_by_fatigue`）**都沒有實作**——我 grep 過，`demot` 在 `engine02/` 下 0 個命中。
所以現狀是：**這一項改變排序，但系統無法說明它改了什麼。** 這在一個以「解釋就是分數分解」為賣點的系統裡是最不該留的洞。

### 4.7 建議（Q4 的答案）

**保留機制，重寫它的身分。三件事：**

1. **改名與改敘事。** 從「隱性負回饋 / fatigue」改成 **「session 內重複曝光控制 / 新穎度」**。
   在 `config.py` 與 §3.23 明確寫：
   > 這一項**不是**品味訊號。品味訊號是 `service.py::_learn_preferences` 擬合的 Δβ，
   > 「選了 i」對展示集合的證據已經完整進了 Bradley–Terry 的成對似然。
   > 這一項只做一件事：**使用者給了回饋之後，畫面必須改變**——這是介面承諾，不是效用估計。
2. **讓它在結構上無法變成品味訊號。** 加一個不變量測試（§7 建議 4）：
   對任意兩件**都沒有被展示過**的商品，開／關這一項的相對順序必須完全相同。
   今天這個性質成立（raw=0），但它只靠 `normalize=False` 這一行維持；`industry-recsys-practice.md` 建議 #2 的第 3 點
   當時還要求加 `clip=arm.z_clip`，而一旦有人「順手補上」z 標準化，性質就會靜默破掉——
   §3.23 記錄的 +0.52 正貢獻事故就是這樣發生的。**要有測試守住它。**
3. **把它翻成正向的「新穎度」寫法，這樣它才講得出話。**
   `raw'(i) = ε_max_total − fatigue_raw(i)`、`weight = +w`（`ε_max_total` 是本輪的最大可能曝光量）。
   **排序完全等價**（同一輪內差一個常數平移，不改任何順序），但貢獻變成正的，於是：
   - 沒看過的商品：**「這件你還沒看過（+0.50）」** ← 誠實、可驗證、正面。
   - 看過沒選的商品：0，不出現在理由裡，**不會出現「因為你沒選它」這種指控**。

   注意這跟 §3.23 記錄的事故**不一樣**：當時的問題是 z 標準化讓沒看過的商品拿到 +0.52 卻**貼著「fatigue」的標籤**——
   荒謬的是標籤，不是正負號。`GROUP_LABEL["fatigue"] = "這件你還沒看過"` 把標籤修對了，
   而且因為 `reason_mode="sufficient"` 只在這一項**真的決定了排名**時才引用它，它不會變成每張卡都貼的廢話。

---

## 5. Q5：fatigue vs novelty vs diversity——正確的框架是不是「session 內頻次上限」？

### 5.1 三件不同的事，我們現在有兩件

| 裝置 | 管什麼 | 我們的實作 | 量過嗎 |
|---|---|---|---|
| **slate 內多樣化** | 同一輪的 5 張卡不要互相重複 | `diversify.py`，DPP fast greedy MAP，θ=0.9，depth=20 | ✅ `recsys-slate.md`：近似重複 44k 2.45%→0.35% |
| **跨輪新穎度** | 第 t 輪不要重播第 t−1 輪 | fatigue 項 | ✅ §3.23（但指標是 novelty@5，見 §3.1） |
| **跨 session 新穎度** | 下次開 app 不要看到上次的 | 沒有 | ❌ 不在 demo 範圍 |

**關鍵的結構事實：DPP 管不到跨輪。** 行列式 kernel 只看**當前這一個 slate** 裡的兩兩相似度。
`diversify.py::select_dpp(rel, emb, k, theta)` 的 `emb` 是候選的圖片向量，裡面沒有任何「上一輪展示過」的資訊。
我查過的 DPP 文獻（Kulesza & Taskar 2012 [V]；Chen, Zhang & Zhou NeurIPS 2018 / arXiv:1709.05135 [V]；
Wilhelm et al. CIKM 2018 YouTube 線上部署 [T]）**沒有一篇處理跨輪／時序多樣性**——
它們都是單一 slate 的重排。跨 session 的「不要重複」在業界通常是**另一個機制**（排除清單、衰減、曝光上限）疊在上面，
而不是塞進 DPP kernel。**這一點對我們有利**：它說明 fatigue 項不是「DPP 的重複發明」，而是 DPP 結構上做不到的那一半。

（我沒有找到明確把曝光歷史寫進 DPP kernel 的論文 **[?]**。技術上可行——把「已展示過」當成一個額外的相似度維度——
但沒有引用可以靠，不要在簡報上聲稱這是標準做法。）

### 5.2 正確的框架就是頻次上限

是的。把它當 frequency capping 有三個好處：

1. **規則不需要估計量。** 頻次上限是一個**業務規則**，它的正當性來自「使用者給了回饋、畫面就該變」，
   不需要 propensity、不需要 θ_rank、不需要 log。這直接解掉 Q1／Q2 的死結。
   這也是 Steck 的 Calibrated Recommendations（RecSys 2018 [T]）與 MMR（Carbonell & Goldstein, SIGIR 1998 [T]）
   的同一個模式：**後處理約束，不是學到的效用項**。Myntra 的 *Diversify and Conquer*（[2309.14046](https://arxiv.org/abs/2309.14046) [T]）
   把多樣性直接當首頁 bandit 的一級約束，也是同一個選擇。
2. **它有一個現成的、可解釋的單位**：**有效曝光次數**。而「有效曝光」本來就是位置／可見度加權的
   （廣告業的 viewable impression 概念），所以 §3.2 的 `ε(rank)` 加權不是我們發明的花招，而是這個框架的標準做法。
3. **卡片講得出來**，而且不必猜使用者的意圖：
   > 「這件你這一輪已經看過 1 次（排在第 1 位），先換別的給你。」
   對照今天講不出來的版本：「因為你沒選它，所以往後排。」

### 5.3 業界預設值 —— ⚠️ 這一段最弱，上台前必須自己查

**兩位研究 agent 都沒有**驗證到任何可靠的頻次上限預設值或學術引用 **[?]**。本次 WebSearch 配額用盡，
Buchbinder, Feldman, Ghosh & Naor *Frequency Capping in Online Advertising*（WINE 2010，期刊版在
*Mathematical Programming*）我只有訓練知識、**沒有**重新確認年份與卷期。
廣告平台（Meta／Google Display）的具體預設上限數字我**一個都沒有查證到**。

**所以建議**：**不要**在簡報上引用任何「業界標準是 N 次」的數字。改成講我們自己能守住的話：

> 「我們把它當 session 內的頻次上限。門檻是**一次位置加權的有效曝光**——
> 排在第 1 位被跳過一次就算滿額，排在第 5 位要五次。
> 這個門檻不是從別人的產品抄的，是從**我們自己量到的分數差**訂的（§3.1）：
> 排名 1 到排名 6 的分數差中位數是 0.496，所以一個分數懲罰要推得動它就得大到 0.5，
> 而那已經大到會壓過其他理由——所以頭部我們用**硬上限**，尾部才用分數項。」

這是一個**從我們自己的量測推出來的門檻**，比抄一個查不到的業界數字誠實得多，也更難被打。

---

## 6. Q6：上台會出什麼事

| # | 失敗模式 | 為什麼會發生（程式層面） | 守門措施（`檔案:函式`） | 嚴重度 |
|---|---|---|---|---|
| 1 | **評審問同一件事兩次，期待同一個答案** | 若是**新 session**（`choice_history=[]`），fatigue 項不啟動（`tests/test_engine02.py::test_fatigue_term_is_off_without_history` 已守住），第 1 輪可重現 ✅。但若在**同一個 session** 裡重問，`handshake` 會再追加一筆 `ChoiceRecord`，畫面就變了 | (a) demo 前置一個「重新開始」按鈕，明確開新 `session_id`；(b) `handshake.py::next_request` 加一條規則：**`ChoiceOp` 沒有 `chosen_item_id` 也沒有 `rejected_item_ids` 時不要追加 `ChoiceRecord`**（單純重問不該算一次曝光）；(c) 講稿先說「這是同一段對話的第 3 輪，所以畫面會變——要看一樣的我按重新開始」 | 🔴 高 |
| 2 | **使用者想比較／想回頭再看** | 沒有任何「釘住」機制。`excluded_item_ids` 是永久排除、`anchor_item_ids` 是搭配用，兩個都不是「請留著」 | (a) `contracts.py::FeedbackState` 加 `pinned_item_ids`，在 `pipeline.py::_terms` 的 fatigue 計算與硬上限裡**完全豁免**；(b) `chosen_item_id` 已經豁免了（`ignored` 減掉它），要在講稿裡明講「你點過的那件不會消失」；(c) 「上一輪第 3 件再給我看」走 `required_values`／硬指定，繞過這一項 | 🔴 高 |
| 3 | **候選池太小，懲罰擠不掉任何東西** | **量到了**：5k 池、`w=0.3`、15 使用者、3 輪 → 最後一輪 novelty **0.1733**（≈ 4.1/5 仍是舊的）（`reports/ablation/fatigue_kagl_hash-256.json`）。根因我量到了：**4 個硬條件下 5k 池的中位數只有 20 件**，p10=6、最小 5，40 句裡 23 句 ≤25 件 | (a) 硬上限**必須**有薄池 fallback（§3.2）；(b) `constraint_report` 新增 `pool_exhausted: bool` 與 `n_unseen_in_pool`，卡片誠實寫「符合條件的只剩 N 件，這幾件你都看過了」；(c) 這種情況**正確的動作是建議放寬一個條件**，不是硬換卡片。`pipeline.py` 的放寬階梯已經存在，把它接上 | 🔴 高 |
| 4 | **沒看過的商品拿到正的「疲勞」貢獻** | §3.23 記錄過的事故（+0.52）。今天靠 `normalize=False` 一行維持 | 加不變量測試（§7 建議 4）；若採用 §4.7 的正向「新穎度」寫法，就把標籤一起修對 | 🟠 中（已修，但沒測試守住） |
| 5 | **畫面閃爍（A,B → C,D → A,B）** | `fatigue_decay=0.5`：兩輪前被忽略的商品權重只剩 0.25，於是第 3 輪可以回來 | 硬上限的 `effective_exposure` **刻意不帶 γ 衰減**（§3.2）——計數不該遺忘。分數項可以衰減，上限不行。並加測試：同一件商品不得在 4 輪內出現→消失→再出現 | 🟠 中 |
| 6 | **系統改了排序但說不出為什麼** | `explain.py::template_reasons` 只引用正貢獻，fatigue 恆 ≤0 → **永遠不是理由**；`GROUP_LABEL` 沒有 `fatigue`；`RankedItem.demotions` / `RoundDiff.demoted_by_fatigue` 都沒實作 | §7 建議 3（正向新穎度寫法）＋ `panels.py::RoundDiff` 的 `dropped_items` 加上歸因欄位 | 🔴 高（這是賣點被打的地方） |
| 7 | **「你沒選它」被讀成指控** | 現行敘事就是「隱性負回饋」 | §4.7 的改名＋正向寫法；`explain.py` 明訂用語規則（`engine02-design.md` §4.3 已經有「負權重要寫成『避開〇〇』」的先例，照同一個模式辦） | 🟠 中 |
| 8 | **這一輪沒選任何卡 → 5 件全滿額扣分** | `_terms` 第 461 行，`chosen_item_id is None` 時 `ignored` = 全部 | §3.2 的 `κ_r = 0.5`（`preference.py::comparison_pairs` 那邊已經正確處理了） | 🟠 中 |
| 9 | **評審問「0.15 怎麼來的」** | 目前的答案是「掃了 5 個值，選最小的有效值」——那是調參，不是原理 | §7 建議 1–2 的完整答覆：**頭部是位置加權的頻次上限（規則，不需估計）、尾部是 examination 先驗打折（假設，明寫在 config 裡且掃過敏感度）**。加一句：「位置偏差我們估不了，所以我們沒有估」 | 🔴 高 |
| 10 | **44k 上 w=0.5 過強** | 本文的 gap profile 只量了 5k；44k 候選分數分布更密、gap 可能更小 | 採用前**必須**在 44k 重跑 §3.3 的格點。上界已知安全（§3.23 的 flat 0.5），但 ε 加權版沒測過 | 🟠 中 |

---

## 7. 給 coordinator 的建議

按「比 −0.15 更站得住」的程度排序。**每一條都只動我列出的函式。**

### 建議 1 🥇 把頭部換成位置加權的硬上限（`pipeline.py` 候選過濾 ＋ `config.py::ArmConfig`）

- **改什麼**：`engine02/config.py::ArmConfig` 加 `fatigue_cap: float | None = 1.0` 與
  `fatigue_examination: tuple[float, ...] = (1.0, 0.85, 0.71, 0.47, 0.37)`（見建議 2）。
  在 `engine02/pipeline.py` 建候選池的地方（`_terms` 之前，和 `excluded_item_ids` 同一層）算
  `effective_exposure(i) = Σ_r κ_r·ε(rank_{i,r})`（**不帶 γ 衰減**），
  `≥ fatigue_cap` 的商品移出候選池；若移除後 `pool < min_results + top_k` 就不移除，
  並在 `ConstraintReport` 記 `pool_exhausted=True`、`n_unseen_in_pool=N`。
- **為什麼比 −0.15 站得住**：它不是估計量，是**規則**，所以不需要 propensity（我們沒有）也不需要 θ_rank（我們估不了）。
  它的門檻有操作定義（**一次位置加權的有效曝光**，ε 的值來自 Joachims et al. SIGIR 2005 的真人眼動量測 [V]），
  而且**保證**評審不會再看到同一張第一名——
  分數項做不到這件事：實測要把 r1 持續率壓到 0.28 需要 w≈3.0，是今天的 20 倍，
  那會讓「你還沒看過它」壓過「它符合你的條件」，卡片就開始說謊（§3.1 表）。
- **量什麼**：`head_repeat@1`（第 1 輪排名 1 的商品在第 t 輪仍出現的比例）。
  baseline = `full_zclip3`（今天 5k 實測 **0.90**）。目標 = 0.00（硬上限的定義）。
  護欄 = `utility_mean` / `utility_max` / `found_target` 配對置換檢定不顯著下降；
  新增 `pool_exhausted` 觸發率（5k 4 條件下預期很高，要量出來）。
- **風險**：薄池（**5k、4 個硬條件下中位數只有 20 件**）會讓 fallback 頻繁觸發，上限形同不存在。
  這不是 bug 是物理限制，所以 fallback 必須**揭露**而不是靜默。另一個風險是誤刪使用者還沒看到的商品——
  由 η 控制（排名 5 要被忽略 5 次才滿額）。

### 建議 2 🥈 尾部的分數項改成 examination 加權（`pipeline.py::_terms`）

- **改什麼**：`config.py::ArmConfig` 加
  `fatigue_examination: tuple[float, ...] = (1.0, 0.85, 0.71, 0.47, 0.37)`（名次 > 5 時用 0.27）。
  `_terms` 第 454–479 行那一段，`weight_by_pos` 的累加從
  `w = arm.fatigue_decay ** (n_rounds - 1 - r)` 改成
  `w = arm.fatigue_decay ** (n_rounds-1-r) * kappa_r * eps(rank0)`，
  其中 `rank0` 是該商品在 `rec.shown_item_ids` 裡的索引、
  `eps(j) = arm.fatigue_examination[j] if j < len(...) else 0.27`、
  `kappa_r = 1.0 if rec.chosen_item_id else 0.5`。
  `config.py` 的 `w_fatigue` 0.15 → **0.5**。
  **`normalize=False` 不要動**（§3.23 的事故）。
  ⚠️ **同時要跟 ENGINE 03 確認 `shown_item_ids` 一定是顯示順序**——這整個建議建立在索引＝名次上。
  `handshake.py` 第 269 行的 fallback（`[it.item_id for it in prev_resp.items]`）本來就是排序過的，
  但 ENGINE 03 自己送的那條路沒有任何保證，要寫進 `docs/contract/` 並加驗證。
- **為什麼比 −0.15 站得住**：(a) 它借的是 PBM 的結構
  `P(click) = α_item · γ_rank`（Craswell, Zoeter, Taylor & Ramsey, WSDM 2008；
  公式經 Chuklin/Markov/de Rijke 2015 專書確認 [V]），而且**明說我們用先驗填 γ、沒有估它**；
  (b) ε 的值**不是我們捏的**，是 Joachims et al. SIGIR 2005 Fig 1 的真人眼動量測 [V]，
  而 eye-tracking 是本文查到的方法裡**唯一小樣本可行**的一條（29 位受試者）；
  (c) 它修掉一個實測到的方向性錯誤——今天的 flat 懲罰保留使用者**確定看過**的那張（r1 持續 0.90）、
  洗掉使用者**可能沒看到**的那張（r5 持續 0.55）；
  (d) w=0.5 被夾在兩個**已經量過**的設定之間：懲罰總量 0.34 嚴格小於 §3.23 測過安全的 flat 0.5，
  又嚴格大於今天的 0.15，**變的只有分布**；
  (e) κ_r 修掉 §4.4 的問題——「這一輪什麼都沒選」現在被當成最強證據（5 件滿額），
  在離散選擇理論裡它是 outside-option，是最弱的。
- **量什麼**：§3.3 的二維 regret 表（ε_true × ε_assumed，至少要含 flat／eye-tracking／η=1 三條），
  主指標 `head_repeat@1`、誤傷指標 `unseen_demoted@k`，護欄照舊。**5k 與 44k 都要跑**。
  baseline = `full_zclip3`（flat 0.15）與 `full_zclip3_nofatigue`。
- **風險**：ε 的真值我們定不了（§8）；借的是垂直清單的曲線，我們是一排卡片（往安全邊借，見 §2.3c）。
  44k 的 gap 更小，w=0.5 可能過強（失敗模式 10）。
  ε 加權會**故意**讓尾部更黏（r4 0.62→0.78、r5 0.55→0.70），所以**看 novelty@5 會覺得沒進步**——
  這正是為什麼要換指標。

### 建議 3 🥉 把它翻成正向的「新穎度」，讓它終於能上卡片（`pipeline.py::_terms` ＋ `explain.py`）

- **改什麼**：`_terms` 裡 `raw' = eps_max_total − fatigue_raw`、`weight = +arm.w_fatigue`
  （`eps_max_total` = 本輪理論最大曝光量，是個常數，**同一輪內平移不改任何順序**）。
  `explain.py::GROUP_LABEL` 加 `"fatigue": "這件你還沒看過"`。
  `panels.py::RoundDiff` 的 `dropped_items` 旁加 `dropped_reason: dict[str, str]`（值為 `"fatigue_cap"` / `"score"` / `"filtered"`）。
- **為什麼比現狀站得住**：現狀是**這一項改排序但系統說不出話**——`template_reasons` 只引用正貢獻
  （`explain.py` 第 36 行），fatigue 貢獻恆 ≤0，`GROUP_LABEL` 也沒有這個 key，
  `industry-recsys-practice.md` 建議 #2 的第 4、5 點從來沒實作（`demot` 在 `engine02/` 下 0 個命中）。
  在一個賣「解釋就是分數分解」的系統裡，這是最該補的洞。
  正向寫法同時讓卡片說**真話**（「這件你還沒看過」）而不是**指控**（「因為你沒選它」），
  而 `reason_mode="sufficient"` 會確保它只在真的決定了排名時才被引用，不會變成每張卡的廢話。
- **量什麼**：沿用 `eval_llm_paraphrase.py` 的事實檢查流程——
  「分數加總 = 總分」、「引用的理由單獨能贏過相關度第 6 名」、
  新增「被標為『你還沒看過』的卡片，確實不在任何 `choice_history[].shown_item_ids` 裡」，
  照 `recsys-slate.md` 的 300/300 格式報。
- **風險**：排序等價需要 `eps_max_total` 在**同一輪內**是常數——跨輪比較貢獻數字時它的基準會變，
  所以 `RoundDiff` 不要直接相減兩輪的 fatigue 貢獻。

### 建議 4 加不變量測試，守住「沒看過的商品這一項恰好是 0」（`tests/test_engine02.py`）

- **改什麼**：新增 `test_fatigue_never_reorders_unseen_items`：
  取兩件都不在任何 `shown_item_ids` 裡的商品，斷言開／關 fatigue 的相對順序完全相同；
  並斷言它們的 fatigue contribution 恰為 0.0。
- **為什麼**：這個性質今天只靠 `normalize=False` 一行維持，而
  `industry-recsys-practice.md` 建議 #2 的第 3 點當時還要求補 `clip=arm.z_clip`（那會蘊含 z 標準化）。
  一旦有人「順手補上」，§3.23 的 +0.52 事故就會靜默復發。
  現有的 `test_fatigue_term_penalises_only_items_shown_but_not_chosen` 測的是被展示過的那些，**沒有測沒看過的**。
- **量什麼**：測試通過／不通過。**風險**：無。這是純增益。

### 建議 5 換驗收指標（`scripts/eval_fatigue.py:main`）

- **改什麼**：加 `head_repeat@1`、`head_repeat@1_pos1`、`unseen_demoted@k`，
  加 `--examine-eta-true` / `--examine-eta-assumed` 兩個旗標跑 §3.3 的格點並報 regret 表。
  `novelty_last` 留著但**降級成次要指標**。
- **為什麼**：novelty@5 把 5 個位置等權相加，所以「洗掉尾部」和「換掉頭部」拿到同樣的分數，
  而 demo 的失敗是頭部。實測證據：ε 加權把 r1 持續率從 0.90 拉到 0.72（明顯改善），
  novelty@5 只從 0.190 動到 0.210（看起來沒改善）。**用錯指標會讓正確的改動看起來沒用。**
- **量什麼**：這條就是量測本身。**風險**：新指標可能顯示建議 1、2 其實不如預期——那是好事，及早知道。

### 建議 6 文件與敘事（`config.py` 註解、`docs/engine02-design.md` §3.23）

- **改什麼**：把「隱性負回饋 / implicit negative feedback」的說法換成
  **「session 內重複曝光控制」**，並在 §3.23 加一段明寫：
  品味訊號是 `service.py::_learn_preferences` 的 Δβ（Bradley–Terry 成對似然已經吃掉了「選了 i ⇒ 其餘 K−1 件較差」），
  這一項**不是**品味訊號，兩者定義域不重疊（一個外推到沒看過的商品，一個對沒看過的商品恰好是 0）。
  §3.23 也要補上「`found_target` 是類別層級指標」的限制（§8）。
- **為什麼**：這是失敗模式 9 的答覆，而且是零成本的。**風險**：無。

---

## 8. 誠實限制

**沒有真人 log 就定不了的事：**

1. **examination 曲線 ε(rank) 的真值。** 我建議的 (1.00, 0.85, 0.71, 0.47, 0.37) 是
   **借來的**（Joachims et al. SIGIR 2005 Fig 1，29 位眼動受試者，**垂直清單版面** [V]），
   不是我們自己量的，而且 Fig 1 的數字是**讀長條圖近似**的，不是論文表格的精確值。
   我們的版面是「一排 5 張卡、一個畫面看完」，真實曲線應該更平；我論證這個方向是安全的（§2.3c），
   但那是**風險論證**，不是估計。
   另外我必須更正一件事：文獻裡**沒有**「從真實資料估出 η≈1.0–1.5」這種數字 **[?]**——
   η=1（θ_r = 1/r）只是 Joachims 2017／Agarwal 2019 **合成實驗的預設值** [V]。
   我也**找不到**任何針對 ≤5 張卡的 grid／carousel 位置偏差量測 **[?]**
   （最接近的是 Agarwal et al. 2019 的 Google Drive 5 筆 overlay，但那是生產規模的估計，不是版面研究）。

2. **「看過沒選」到底有多少是「沒看到」。** 這是 §2.2 的不可辨識性，它不是資料量問題，
   是我們的排序是決定性的、沒有 propensity。**再多模擬使用者也不會解決它。**
   要有 propensity 只有一條路：**刻意隨機化**。這不是我的推測——
   Spotify 的 Music Streaming Sessions Dataset（arXiv:1901.09851 [V]）就是
   **刻意用均勻隨機推薦策略收集了一個子集**，專門為了能做 counterfactual 評估。

3. **重複曝光是不是真的降低效用。** 心理學文獻的方向是**反**的（mere exposure，Zajonc, JPSP 1968 [V]；
   倒 U 形要 10–20 次後才轉折，Bornstein 1989／Montoya et al. 2017 meta-analysis [T]）。
   我**沒有找到**推薦系統文獻證明「同一 session 內重複曝光同一件商品降低點擊率」**[?]**
   （業界的 banner blindness / creative fatigue 是常識，但兩位研究 agent 都拿不出可驗證的標題／會議／年份；
   OpenAlex 搜 "fatigue-aware recommendation" 只回醫學論文）。
   最接近的可驗證論文是騰訊 DFN（Xie et al., IJCAI 2020 [V]），但它做的是
   **把 click / unclick / dislike 分成三個通道**，不是「疲勞」。
   所以這一項唯一站得住的依據是**互動契約**（使用者給了回饋、畫面就該變），不是效用。這一點要照這樣講。

4. **我們的模擬器在結構上不能選出這個參數化。** `eval_fatigue.py` 的使用者對 5 個位置一視同仁（ε≡1），
   而那正是本題要檢驗的假設。在 ε≡1 的世界裡 flat 懲罰是**正確**的模型。
   模擬器能做的只有**排除**（證明某條 ε 在 ε_true≡1 下損失很大），不能**選擇**。

5. **`found_target` 這個護欄比看起來弱得多。** 我量過：`eval/tasks.py::Query.grades` 是**屬性層級**的，
   5k 庫的中位數查詢有 **6 件** grade≥3、**128 件** grade>0。
   所以「找到目標」是一個有 ~6 個可互換成員的**類別**指標——
   疲勞項推走一件 grade-3，另一件 grade-3 會補上，指標幾乎不動（§3.23 的 p=1.00 有一部分是這個原因）。
   **要真正測「有沒有把使用者要的那一件推走」，必須有單一隱藏目標商品的變體。**

6. **本文的 gap profile 與持續率只量了 5k ＋ HashEncoder。**
   44k ＋ marqo-fashionSigLIP 的候選分數分布更密，gap 可能明顯更小，w=0.5 可能過強。
   §3.1 的表**不能**直接外推到服務設定，採用前必須在 44k 重量。
   （我本機沒有 `data/catalog/kagl_full/items.parquet`，跑不了。）

7. **引用驗證不完整。** 本次 session 的 WebSearch 配額在開工前已用盡（200/200），
   DBLP／ACM DL 擋自動抓取；所有驗證都是 WebFetch 抓 arXiv／OpenAlex／作者自架 PDF 再讀全文完成的。
   標 **[V]** 的包括：Joachims/Swaminathan/Schnabel WSDM 2017（全文）、
   Agarwal et al. WSDM 2019（全文，含 Google Drive 與 arXiv 的樣本數）、
   Joachims et al. SIGIR 2005（全文，含 Fig 1／Table 2／Table 3）、Granka et al. SIGIR 2004（全文）、
   Radlinski & Joachims AAAI 2006（全文）、Chuklin/Markov/de Rijke 2015 專書 Ch.1–4（PBM／CM／UBM／DBN 公式）、
   McFadden 條件 logit 的 choice-set 條件性、Luce 1959、Bradley–Terry 1952、Plackett 1975、
   Jeon/Milli/Dragan NeurIPS 2020、Liang et al. WWW 2016（ExpoMF）、Schnabel et al. ICML 2016、
   Rendle et al. BPR、Hu/Koren/Volinsky ICDM 2008、ESMM SIGIR 2018、DIN KDD 2018、
   Xie et al. DFN IJCAI 2020、Covington et al. RecSys 2016、Zhao et al. RecSys 2019、
   Chen et al. WSDM 2019、PinnerSage KDD 2020、Steck RecSys 2018、
   Kulesza & Taskar 2012、Chen/Zhang/Zhou arXiv:1709.05135、Zajonc 1968、
   Brost et al. arXiv:1901.09851、Hansen et al. WSDM 2021。
   標 **[T]** 的是高信心訓練知識但**本次沒有重新驗證**（含 YouTube RecSys 2016 的負例取樣細節、
   RecSys 2019 shallow tower 的實作細節、SNIPS、Jiang & Li、MMR、trust bias WWW 2019、
   Vardasbi CIKM 2020、Wilhelm et al. CIKM 2018）——引用前請自己核一次。
   標 **[?]** 的**不要寫進簡報**：
   - 頻次上限的**所有**業界預設值與學術引用（§5.3；兩位 agent 都完全查不到）
   - Alibaba／Tencent 的「使用者疲勞建模」論文（查不到，OpenAlex 只回醫學論文）
   - Pinterest 的 skip／hide／疲勞論文（查不到；PinnerSage 與此無關）
   - ≤5 卡 grid／carousel 的位置偏差量測
   - 「從真實資料估出 η≈1.0–1.5」
   - 把曝光歷史寫進 DPP kernel 的論文
   - Gartrell et al. 的會議（AAAI 2017 vs arXiv 頁上的 "submitted to KDD 2016"，有衝突）
   - Liang/Charlin/Blei *Causal Inference for Recommendation* 的會議與年份
   **已更正的引用**：Spotify 多樣性那篇是
   *Shifting Consumption towards Diverse Content on **Music Streaming Platforms***, **WSDM 2021**
   （Hansen, Mehrotra, Hansen, Brost, Maystre, Lalmas）[V]，
   不是常被誤引的「on Spotify / WSDM 2020」。
   另外 DFN 是**騰訊**（IJCAI 2020），不是 Alibaba。

8. **本文所有新量測都是丟棄式 probe**，跑在 scratchpad 的 `Engine02` 子類上，**不在 git 裡、不可重現**。
   照 `sep-simulator-run-provenance` 的教訓：**這些數字只能當方向指引，不能當結論**。
   要拿它們做決定，請先照建議 5 把量測寫進 `scripts/eval_fatigue.py` 並進 git。