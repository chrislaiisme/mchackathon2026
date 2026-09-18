# 新穎度不是雜訊，側寫不是問卷：ENGINE 02 的兩個加法項提案

> 作者：research sub-agent（`novelty-and-profile`），2026-09-18，分支 `engine02-research`。
> **本文沒有動任何程式**，只寫在 `docs/research/`。所有提案都必須能寫成 `score = Σ w_t · x_t` 的一項，並在卡片上顯示成一句話。
> 已讀：`docs/engine02-design.md`（§3 全部標題、§3.12、§3.23–§3.25 細讀）、`docs/engine02-pipeline.md`、
> `docs/research/{recsys-slate,recsys-preference,implicit-negative-feedback}.md`（避免重複既有結論）。

---

## 0. 一頁結論

| 問題 | 提案 | 為什麼不是「隨機化＋講故事」 | 殺掉它的條件 |
|---|---|---|---|
| A 新穎度 | **兩趟式校準項**（two-pass calibration，Steck RecSys 2018 的 KL 校準，改寫成可加總的每商品項）：第一趟排序 → 量出前 k 的屬性分布 q₀ → 第二趟加上 `w_cal·(p(g_i) − q₀(g_i))` | 它有**明確的目標分布 p**（來自側寫＋本輪需求機率），不是把清單打散。隨機化會讓 KL 變大而不是變小 | 與「隨機目標分布」對照組相比沒有顯著贏；或 NDCG@5 的 95% CI 不含 0 且為負 |
| A 新穎度（**不進分數**） | **意外度面板**：相對於「只用側寫」的期望集合算 unexpectedness，和跨輪的 catalog coverage 一起放在面板 | 沿用 §3.15 趨勢關鍵字的先例：量了、沒有效果就不進排序，只當展示標籤 | 不需要殺——它本來就不影響排序 |
| B 事前側寫 | **上台前 3 題成對圖片二選一**（上限 5 題），輸出只當 Bayes 偏好學習的**先驗平均 β₀**，不是硬權重；題目由既有 Laplace 後驗的變異數縮減挑選 | 3 題 ≤ 3 bits，數學上不可能決定 11 個設計軸——所以它只能當先驗，這正好是 κ=1 縮減已經在做的事 | 3 題 vs **隨機 3 題**在第 1 輪效用上沒有顯著差距（＝答案內容沒用，只是先驗被縮了） |
| 兩者的接點 | 側寫提供校準項的**目標分布 p**；本輪需求 p(n) 提供另一半 | 這就是「多來源組合」：打字的需求 ∩ 事前側寫，而且兩者都看得到自己在分數裡貢獻多少 | — |

**一句話**：新穎度要有**參考點**才不是雜訊；我們現在缺的參考點，正好就是事前側寫能提供的那一個。

---

## 1. 這篇和既有文件的分工

已經有結論、本文不重複的：

- **slate 內多樣化**：`recsys-slate.md`（MMR／DPP／xQuAD 都實作了，DPP θ=0.9 為預設，近似重複 2.45%→0.35%，NDCG −0.005 n.s.）。
- **跨輪重播**：`implicit-negative-feedback.md` ＋ 設計文件 §3.23／§3.25（新鮮度項 w=0.5，最後一輪新穎度 0.007→0.237，最佳卡片效用 +0.18，p=0.008；硬上限量了但不開）。
- **從點選學偏好**：`recsys-preference.md`（Bayes 成對 logistic ＋ κ=1 縮減）。

本文只補**兩個現在完全沒有的東西**：(A) 一個有參考點、可加總、可解釋的新穎度／校準項；(B) 第一輪**之前**就存在的使用者側寫。

---

## 2. A 問題：怎麼量新穎度，才不會只是把清單打散

### 2.1 五個詞，五個不同的參考點——這才是文獻真正的爭議

文獻不是對「新穎度好不好」有歧見，而是對**「相對於什麼」**有歧見。把參考點攤開來，爭議就消失了：

| 概念 | 參考點 | 典型公式 | 出處 |
|---|---|---|---|
| Novelty（新穎度） | **全體使用者**（流行度） | 平均自資訊 −log p(i)，越高代表越多人沒看過 | Auralist, WSDM 2012；Castells et al. 章節 |
| Unexpectedness（意外度） | **一個基準推薦器的輸出**（expected set） | `REC \ PM`，PM 是 primitive prediction model | Ge et al., RecSys 2010；Adamopoulos & Tuzhilin, TIST 2014 |
| Unserendipity | **這位使用者的歷史** | 推薦與歷史的平均 cosine，**越低越好** | Auralist, WSDM 2012 式(6) |
| Diversity（多樣性） | **清單內部** | ILD＝1 − 兩兩相似度平均；DPP 的行列式體積 | Vargas & Castells, RecSys 2011 |
| Coverage（覆蓋率） | **整個商品庫** | catalog coverage（被推薦過的商品比例）／prediction coverage | Ge et al., RecSys 2010 |
| Serendipity | **相關 ∩ 意外**（兩者的交集） | 相關且不在 expected set 裡的比例 | Kaminskas & Bridge, TiiS 2017（綜述） |

**對我們的直接後果**：

1. **隨機化只能推高 Diversity 和 Coverage**，那兩個的參考點裡完全沒有使用者。它會讓 Unserendipity 下降（看起來變好），但同時讓 Novelty 幾乎不動、讓 Serendipity 因為交集裡的「相關」那一半崩掉。所以**只要同時報這五個，隨機化立刻現形**——這就是我們該做的事：不要挑一個指標，五個一起報。
2. Serendipity 是**交集**，所以它天生無法靠單一權重最佳化；Kaminskas & Bridge 在綜述裡把它處理成「相關 ∩ 新穎 ∩ 意外」，代表任何宣稱「我們提升了 serendipity」的說法，都必須同時出示相關度沒掉。

### 2.2 Auralist 的數字：同一份實驗，兩個準確度指標給出相反的結論

Auralist（Zhang et al., WSDM 2012）是這一整條線最誠實的一篇，因為它把翻車的部分也印出來了。它的 Table 2（Last.fm）：

| 設定 | Rank（越低越好） | Top-20 Recall | Intra-List Similarity | Novelty | Unserendipity（越低越好） |
|---|---|---|---|---|---|
| Basic Auralist | 0.019 | 0.157 | 14.4 | 11.8 | 0.060 |
| Implicit SVD（SOTA 對照） | 0.039 | 0.174 | 14.7 | 10.9 | 0.046 |
| Community-aware (λ=0.05) | 0.023 | 0.030 | 3.4 | 17.2 | 0.047 |
| Bubble-aware (λ=0.2) | 0.021 | 0.029 | 3.4 | 14.2 | 0.035 |
| **Full Auralist** | 0.025 | **0.008** | 1.54 | **17.3** | **0.039** |

Full Auralist 的 Recall@20 從 0.174 掉到 0.008（掉了 95%），但 Rank 指標卻**比 SOTA 還好**（0.025 vs 0.039）。
作者自己的解釋是 recall 被污染了：「recall indicates that similar, already known items are being placed in the Top-20 list, displacing the recommendation of novel items」。

**這對我們是最重要的一課**：選哪個準確度指標，決定了新穎度看起來是免費的還是災難性的。
我們的 NDCG@5 標準答案來自**資料集屬性**（子類＋顏色＋性別＋場合），不是使用者歷史，所以它**不會**有 Auralist 的 recall 那種污染——被推上來的新穎商品只要屬性對，NDCG 就照給分。這是我們的評估設計比 Auralist 乾淨的地方，簡報上可以講，但也要講清楚代價：我們的 NDCG 因此**對「這個人會不會喜歡」完全不敏感**，它只量「符不符合這句話」。

再看 Auralist 的真人研究（21 位受試者，各自給 6 個 2008 年前的 seed 藝人）：**12 人偏好 Full Auralist、7 人偏好基準、2 人中立**。
也就是說，在一個**成功**的 serendipity 論文裡，仍有三分之一的人寧願要準確的那一版。
→ 所以新穎度應該是**一個可調權重的加法項**，不是一個全域決定。我們的架構剛好就是這樣。

### 2.3 Castells et al. 的統一框架：為什麼 ILD 會被隨機化騙

Castells, Hurley & Vargas 的章節（Recommender Systems Handbook，2015 第 2 版／2022 第 3 版）與 Vargas & Castells（RecSys 2011）把所有這些指標寫成同一個形狀：

```
metric = Σ_k  discount(k) · p(relevant | i_k) · novelty_model(i_k | 參考點)
```

三個元件：**瀏覽模型**（排名折扣）、**相關性**、**新穎度模型**。文獻中大多數指標都是把其中一兩個設成常數的特例。

對我們的兩個具體後果：

- **ILD@5 把 relevance 設成常數 1**。一份 5 張隨機卡的 ILD 會很高，但 relevance 項應該把它扣光——所以只報 ILD 等於自願被騙。修法：報 **relevance-aware 版本**（把 z(dense) 或屬性相符度乘進去），並且**用排名折扣**（我們已經有 §3.23 的眼動注視機率 ε=(1.00, 0.85, 0.71, 0.47, 0.37)，正好就是一個有依據的 discount(k)，直接重用，不要另外發明冪次律）。
- 我們的 `recsys-slate.md` 已經誠實寫了自我參照警語（ILD 用的是 DPP 最佳化時的同一個 embedding 空間）。統一框架給出的解法很直接：**新穎度模型要換一把尺**——用 metadata 屬性（顏色／場合／季節／L2 品類）算，不要用 CLIP embedding 算。

### 2.4 Calibration（Steck, RecSys 2018）：比粗暴多樣化更有原則的那一招

Steck 的主張用一句話講完：*「使用者看了 70 部愛情片、30 部動作片，推薦清單就該大約是 70/30」*。
它不是把清單推開，而是讓清單的**屬性分布 Q 貼近目標分布 P**。

形式（依 da Silva & Jannach 2025 綜述整理，該綜述系統性回顧了 2018 年後所有 build on Steck 的工作）：

- 校準度量用 KL 散度：`CL_KL(P_u, Q_u) = Σ_g p(g|u) · log( p(g|u) / q(g|u) )`。綜述指出 Steck 選 KL 的三個理由：P=Q 時為 0、對小差異敏感、偏好比較均勻的分布。
- 目標式：`L*_u = argmax_{|L|=N} (1−λ)·REL(L_u) − λ·CL(P_u, Q(L_u))`。
- 求解用 **Surrogate Submodular Greedy**，有 **(1−1/e)** 的最佳性保證，實務上只在 top-100 候選內做。

**為什麼它比 MMR／DPP 更適合我們**：

1. 它是**個人化的多樣化**。綜述明確指出 calibration 與傳統多樣化的差別就在這裡：MMR/DPP 對所有人都推開同樣的距離，calibration 推向**這個人的比例**。我們的整個賣點是「懂你」，DPP 說不出這句話。
2. 它**天然會產生一句可核對的理由**：「你的側寫是 60% 休閒 / 40% 正式，這排目前只有 20% 正式，所以第 4 張補了一件正式的」。這是分數分解，不是事後生成。
3. **它需要一個 P，而我們現在沒有 P**——這正是 B 問題存在的理由。

**相關的重要對照**：Kaya & Bridge（RecSys 2019）直接比較了 calibrated 與 intent-aware 推薦。我們已經實作了 xQuAD over needs（intent-aware 的代表，`diversify.py`，但不是預設，因為它直接最佳化自己定義的 α-NDCG）。所以 **calibration 是我們唯一還沒試過、而且文獻上被拿來和 xQuAD 正面比較過的那一支**。

**警訊（綜述自己列的）**：(a) 若使用者是單一興趣，校準反而會**降低**多樣性；(b) 舊偏好可能已經不該算；(c) 校準研究 **88% 只做離線評估，只有 8% 做使用者研究，1 篇做線上實驗**——所以「calibration 提升使用者滿意度」在文獻上其實**證據很薄**，我們不能照抄這句話當簡報結論。

### 2.5 沒有真人時，怎麼「show」而不是「assert」

每一項都要能對上一組（離線指標 × 對照 arm × 統計檢定）。下表是我建議的驗收表，**全部沿用既有基礎設施**（60 句查詢、query 層級配對置換 10,000 次、bootstrap 95% CI）。

| 要證明的事 | 離線指標（用哪把尺） | 對照 arm | 檢定 |
|---|---|---|---|
| 校準真的有效 | `MissCal_KL@5`：**用 metadata 屬性**（顏色／場合／季節／L2 品類）算 KL(P‖Q)，**不用 CLIP embedding** | `full_zclip3`（現行預設，w_cal=0） | 配對置換 10k，單一主要指標 |
| 不是「加了任何分布都會動」 | 同上 | **隨機目標分布對照**：把 P 換成同熵的隨機分布 P̃ | 同上；**這一格不顯著就整個提案作廢** |
| 沒有犧牲相關度 | NDCG@5（屬性標準答案）、硬條件滿足率 | `full_zclip3` | 配對置換 ＋ bootstrap CI；**非劣性**判準：CI 下界 > −0.01 |
| 沒有和 DPP 重複發明 | 近似重複率（cosine>0.95）、ILD@5 | `full_zclip3_nodpp` ＋ `full_zclip3_cal_nodpp` | 2×2 交互作用；若 cal 的效果在關掉 DPP 時才出現，代表它只是換句話說的 DPP |
| 意外度不是雜訊 | Unserendipity（相對側寫期望集合）、catalog coverage（跨 60 句查詢的聯集） | 隨機重排前 20 名（**同樣的 slate 大小**） | 隨機化應該在 ILD 上贏、在 NDCG 上大輸——**印出來給評審看這個對照**，它是「我們不是在隨機化」最直接的證據 |
| 解釋仍然忠實 | contributions 加總＝總分；被校準推上來的卡第一條理由是校準句 | — | 既有的 300/300 式全量檢查 |

**三個必須寫在簡報上的誠實話**：

1. 我們沒有真人，所以**所有新穎度結論都是代理指標**；Auralist 的 21 人研究說明真人裡有三分之一會偏好「不新穎」的那一版。
2. **自我參照風險**：如果用 CLIP embedding 同時當最佳化目標和評估尺，數字一定會好看。所以主要指標一律用 metadata 屬性。
3. calibration 在文獻上的**使用者端證據很薄**（88% 純離線），我們只能宣稱「離線分布更貼近目標且相關度沒掉」，不能宣稱「使用者更滿意」。

### 2.6 A 的可出貨提案：兩趟式校準（two-pass calibration）

**為什麼要兩趟**：KL 是 **set-level** 的，不能拆成每個商品的固定貢獻，所以直接把 Steck 的目標式塞進 additive scorer 會破壞「contributions 加總＝總分」這個我們唯一不妥協的性質。解法是把 slate 層級的量**固定成一個常數**：

```
第 1 趟：現行 additive scorer → 暫定前 k → 量出屬性分布 q₀(g)      （純讀取，不改分數）
第 2 趟：對每個候選 i 加一項
         x_cal(i) = p(g_i) − q₀(g_i)        ← 只看 i 所屬的那一格，是個常數
         contribution = w_cal · x_cal(i)
```

- `p(g)` = 目標分布 = **側寫分布（B 問題的產物）與本輪需求機率 p(n) 誘導的分布的凸組合**，混合係數 ρ 是一個對照參數（ρ=0 → 完全跟著本輪查詢，ρ=1 → 完全跟著側寫）。
- 完全可加總、完全確定性、**候選 50 件只多一趟 O(50)**，對 12 ms 的 `/rank` 是雜訊等級。
- 卡片文案（模板，不需要 LLM）：
  `「你的側寫裡正式感佔 40%，這排目前只有 1 件，這件補上這一格（+0.12）」`
  這句話的每個數字都能從 `contributions[]` 逐項核對，符合既有的事實檢查機制。
- 保留 `w_cal=0` 為預設值，`full_zclip3_cal` 當實驗 arm——和團隊處理趨勢關鍵字、概念圖、新鮮度項的作法一致。

**不進分數、只進面板的部分**（沿用 §3.15 趨勢關鍵字的先例）：
- `Unexpectedness@5`：相對於「只用側寫排序」的期望集合（Ge et al. 的 primitive prediction model 就是這個角色）。
- 跨輪 `catalog coverage`：4 輪下來一共碰過商品庫的百分之幾。
- 五個新穎度指標（novelty / unexpectedness / unserendipity / ILD / coverage）**同時**顯示，附上隨機重排對照組的同一組數字。

---

## 3. B 問題：第一輪之前就存在的側寫

### 3.1 文獻地圖（我們已經有的，和我們沒有的）

| 路線 | 代表作 | 它解決什麼 | 我們的狀態 |
|---|---|---|---|
| 種子商品挑選（cold-start questionnaire） | Rashid et al., IUI 2002；Rashid, Karypis & Riedl, SIGKDD Explorations 2008 | 新使用者該被問**哪些**商品；比較 6 種挑選策略（流行度、熵、流行度×熵…），結論是**策略的選擇顯著影響使用者付出的努力與預測準確度** | ❌ 沒有 |
| 自適應 bootstrapping | Golbandi, Koren & Lempel, WSDM 2011（決策樹）；CIKM 2010 | 把問卷做成**決策樹**：下一題取決於上一題的答案，而不是固定題組 | ❌ 沒有（但我們有 Laplace 後驗，可以直接做變異數縮減選題） |
| 訪談式冷啟動 | Zhou, Yang & Zha, SIGIR 2011（functional matrix factorization） | 把「訪談問題」和「latent factor」一起學 | ❌ 沒有 |
| 選擇式引導（choice-based） | Loepp, Hussein & Ziegler, CHI 2014；Graus & Willemsen, RecSys 2015 | **二選一比打分快、對冷啟動的使用者體驗更好** | ⚠️ 我們有成對選擇，但只在**第 1 輪之後** |
| 對話式推薦 | Jannach, Manzoor, Cai & Chen, ACM CSUR 2021（綜述）；Zou, Chen & Kanoulas, SIGIR 2020；Christakopoulou et al., KDD 2018（Q&R，先問**一題**再推薦） | 互動輪次中的提問策略與成本 | ⚠️ 我們是「查詢→回饋」，不是「提問→回答」 |
| Bayes 偏好學習 | Chu & Ghahramani, ICML 2005；Jeon, Milli & Dragan, NeurIPS 2020 | 從成對比較學連續權重與不確定度 | ✅ **已經有**（`preference.py`，κ=1 縮減） |

**關鍵判斷**：我們缺的**不是**偏好學習器，而是它的**先驗平均 β₀**。
目前 β₀ = γ·p(n)·K，完全由 ENGINE 01 這一句話決定。第 1 輪還沒有任何選擇資料，所以第 1 輪的排序**完全沒有個人化**。
事前側寫能加的，精確地說就是三件事：

1. **β₀**：先驗平均從「只看這句話」變成「這句話 ＋ 這個人」。這是唯一會改變分數的一項。
2. **校準目標分布 p(g)**（§2.6 的那個 P）——沒有側寫就沒有 P，calibration 也就無從談起。
3. **硬條件預填**（性別、預算區間、排除值）：不進分數，只進過濾器與 `constraint_report`，而且要照實標示「來自側寫，不是你這句話說的」。

### 3.2 幾題？——證據、以及證據到不了的地方

**能查到的證據**（Zou, Chen & Kanoulas, *Towards Question-based Recommender Systems*, SIGIR 2020；arXiv:2005.14255）：

- 離線：「the performance of Qrec reaches very good performance already, **within the first 10 questions**, while asking more than 10 questions does not add much regarding the performance」——**10 題是效益的上界**。
- 真人研究（21 位 crowd worker、33 個目標商品）：使用者平均回答 **15 題**（中位數 12）；**71.4%** 的人表示願意回答 **10–20 題**；每題回答時間**中位數 5 秒**；95.2% 認為題目容易回答。

**證據到不了的地方**：上面這些是在「使用者自己想找東西、願意投資時間」的情境量出來的。我們的情境是**評審站在台上、全場在等**。文獻給了我們兩個數字——**上界 10 題**與**單價 5 秒／題**——但沒有給「台上該問幾題」。那個數字只能由時間預算導出：

```
3 題 × 5 秒 ≈ 15 秒（建議預設）
5 題 × 5 秒 ≈ 25 秒（上限）
10 題 × 5 秒 ≈ 50 秒 ← 在一個三段各 30 秒的 demo 腳本裡，這會吃掉一整段
```

`docs/engine02-pipeline.md` §9 的現場腳本是三段各約 30 秒。**3 題 ≈ 15 秒**可以塞進開場那一段而不破壞節奏；10 題不行。

**第二個獨立論證（資訊量）**：一次二選一最多提供 1 bit。我們的設計軸有 **11 維**（`preference.py` 合併反義後）。
3 題最多 3 bits，連 11 個軸的正負號都決定不了一半。
→ 所以 3 題**在數學上只能當先驗，不能當結論**，這和 κ=1 縮減（Δβ·n/(n+1)）的設計意圖完全一致；反過來說，如果有人主張「問 3 題就能大幅改變排序」，那一定是 §3.12 已經否決過的「一次點選就暴衝」的同一個錯誤。

**題目怎麼挑**（Rashid 2002 的結論：挑選策略比題數更重要）：用我們**已經有的** Laplace 後驗，貪婪挑選能最大化 β 後驗變異數縮減的圖片對（等價於 D-optimal 設計的一步近似）。候選對從商品庫離線預算好一個小池子（例如 200 對），現場只做查表，零額外延遲。這就是 Golbandi 的 adaptive bootstrapping，長在我們既有的貝氏機器上，不需要新模型。

### 3.3 B 的可出貨提案：`GET /profile/questions` → `POST /profile`（3 題，全部離線預算）

```
上台前（或評審落座時）：
  ① GET /profile/questions?n=3      → 3 組圖片二選一（離線預算的池子，變異數縮減排序）
  ② 評審點 3 次                      → 約 15 秒
  ③ POST /profile {choices}          → Bayes 成對更新 → 得到 β_profile 與 p_profile(g)
  ④ 之後每一輪 /rank：
       β₀ ← γ·p(n)·K  +  κ₀/(κ₀+n) · β_profile        （κ₀=3，等效樣本數上限）
       校準目標 p(g)  ← ρ·p_profile(g) + (1−ρ)·p_query(g)
```

- **兩個項、兩句話**，都在 `contributions[]` 裡：
  - 設計要素項的 `need_shares` 多一格 `from_profile`：「這件的休閒感（+0.18），其中 0.07 來自你事前選的那三張圖」。
  - 校準項：「你的側寫裡正式感佔 40%…」（§2.6）。
- **κ₀=3 的意思**：側寫最多相當於 3 次點選的證據；到了第 3 輪它自然被真實回饋稀釋掉。這讓「側寫會不會綁架後面幾輪」變成一個**有上界的、可證明的**性質，而不是一句保證。
- **可跳過**：沒有側寫時 β_profile=0、ρ=0，整條路徑是 no-op，退回今天的行為（和 `concept_image_weight=0` 同一個模式）。
- 側寫來源一律標在 `explanation_source` 與面板上：**「這一項來自你事前的 3 個選擇，不是你這句話說的」**——這句話本身就是我們可驗證解釋主張的延伸。

### 3.4 B 的實驗：哪些 arm、哪個指標、什麼時候該殺掉它

沿用 `scripts/eval_preference.py` 的模擬使用者框架（200 位、5 輪、隱藏效用、query 層級配對置換 10k、bootstrap 95% CI）。模擬側寫的方式：讓模擬使用者用**它自己的隱藏效用**回答 3 題（這就是「誠實回答」的上界）。

| Arm | 內容 | 它回答什麼問題 |
|---|---|---|
| `p0`（基準） | 現行預設，無側寫 | — |
| `p3` | 3 題，變異數縮減選題 | 主要提案 |
| `p5` / `p10` | 5 題 / 10 題 | 題數的邊際報酬（對應 Zou et al. 的 10 題上界） |
| **`p3_rand`** | 3 題，**隨機挑對** | 選題策略有沒有用（Rashid 2002 的主張） |
| **`p3_shuffled`** | 3 題，但**答案洗牌** | **最重要的對照**：如果洗牌後效果一樣，那增益來自 κ₀ 這個縮減本身，和側寫內容無關——**提案作廢** |
| `p3_noisy` | 答案有 20% 機率翻轉 | 台上按錯／評審隨便點的穩健性 |

**主要指標（要事先講定，不能事後挑）**：

1. **第 1 輪隱藏效用**——側寫的價值理論上**集中在第 1 輪**，因為第 2 輪之後真實回饋會接手。這是最誠實的主要指標。
2. 第 1 輪 NDCG@5（屬性標準答案）：檢查側寫**沒有**傷害「符不符合這句話」。側寫不該蓋過使用者剛剛打的字。
3. 第 5 輪平均效用：檢查側寫**沒有**綁架後面幾輪（預期：`p3` 與 `p0` 在第 5 輪應該**沒有顯著差異**；有顯著差異且為負，就是 κ₀ 太大）。

**預先寫死的三個殺掉條件**：

- (a) `p3` vs `p3_shuffled` 在第 1 輪效用上的 95% CI **含 0** → 側寫沒有傳遞資訊，作廢。
- (b) `p3` 的第 1 輪 NDCG@5 相對 `p0` 顯著下降 → 側寫在蓋掉使用者打的字，作廢（或把 κ₀ 調小再測一次，且必須重報）。
- (c) `p10 − p3` 的第 1 輪效用差顯著且大於 `p3 − p0` 的一半 → 3 題不夠，必須誠實說「現場題數是被時間預算綁住的妥協」，並把數字印在簡報上。

**輔助：延遲驗收**。`GET /profile/questions` 必須是純查表（池子離線算好），`POST /profile` 是 11 維的 Newton 法，應該 <5 ms。要用 `scripts/bench_latency.py` 的同一套方法量出來，否則不准上台。

---

## 4. 兩個提案為什麼合起來才是「創意」

單獨看，calibration 是 2018 年的老招、preference elicitation 是 2002 年的老招。合起來的那個結構才是新的：

```
打字的需求 p(n) ──┐
                  ├─→ 目標分布 p(g) ──→ 校準項 ──→ 卡片上一句可核對的話
事前側寫 p_prof ──┘                                「你的側寫裡正式感佔 40%，這排只有 1 件」
        │
        └────────→ 先驗平均 β₀（κ₀=3 有上界）──→ 設計要素項的 need_shares 多一格 from_profile
```

- **多來源**：兩個來源在分數裡各自佔一格，而且**分得開**（`need_shares` 已經有這個機制）。
- **新穎且有價值**：新穎度有參考點（目標分布），價值有守門（NDCG 非劣性 ＋ 硬條件滿足率）。
- **講得出口**：兩句話都是事實陳述，不是對使用者口味的指控——這和 §3.23 把「你沒選它」改寫成「你還沒看過這件」是同一個原則。

**工程量估計**（僅供排程參考，我沒有實作、沒有量過）：校準項約 1 個檔案 + 1 個 arm 旗標；側寫端點約 2 個端點 + 離線題庫腳本 + 既有 `preference.py` 的一個 `prior_mean` 參數。兩個實驗都能重用現有的 eval 腳本骨架。

---

## 5. 反對意見（先自己講，免得被評審講）

1. **「校準只是 xQuAD 換皮」**——不是。xQuAD 是把清單推去覆蓋**多個**需求（intent-aware），calibration 是把清單推去符合**一個指定比例**。§2.5 的 2×2 交互作用 arm 就是設計來驗這件事的；而且 Kaya & Bridge（RecSys 2019）已經把這兩者正面比較過。
2. **「側寫只是在給模型偷看答案」**——這是模擬實驗最大的循環性風險，和 `recsys-preference.md` §5 已經自陳的問題同源。`p3_shuffled` 這個 arm 就是為此設的；另外必須加跑一次「側寫用 metadata 口味、排序用設計要素」的不共用特徵版本（團隊已有這套作法）。
3. **「現場評審不會想先答題」**——所以它必須可跳過且是 no-op，而且 3 題 ≈ 15 秒有 Zou et al. 的 5 秒／題中位數當依據。真正的風險是**台上按錯**，`p3_noisy` 就是量這個。
4. **「新穎度提升會傷害相關度」**——文獻的答案是「看你用哪個準確度指標」（§2.2 的 Auralist 表）。我們的答案必須是**非劣性檢定**，不是「p>0.05 所以沒差」。

---

## 6. 我無法核實的部分

- **我沒有打開全文、只用 Crossref 核到書目資料（venue/年份/頁碼/DOI）的**：Kaminskas & Bridge (TiiS 2017)、Ge et al. (RecSys 2010)、Steck (RecSys 2018) **原文**、Adamopoulos & Tuzhilin (TIST 2014)、Castells et al. 章節、Vargas & Castells (RecSys 2011)、Rashid et al. (IUI 2002)、Rashid et al. (SIGKDD Expl. 2008)、Golbandi et al. (WSDM 2011 / CIKM 2010)、Zhou et al. (SIGIR 2011)、Loepp et al. (CHI 2014)、Graus & Willemsen (RecSys 2015)、Jannach et al. (CSUR 2021)、Kaya & Bridge (RecSys 2019)、Chu & Ghahramani (ICML 2005)、Christakopoulou et al. (KDD 2018)、Kotkov et al. (KBS 2016 / SAC 2018)。ACM DL 對本機的抓取回 403/404。
  - 這些出處的**內容描述**（例如 §3.1 表格裡「Ge et al. 的 unexpectedness＝REC\PM」、「Rashid 比較 6 種挑選策略」）來自 Semantic Scholar 的 TLDR、da Silva & Jannach 綜述的轉述、以及我的既有知識，**不是逐字核對過的原文**。引用前若要寫進對外簡報，請至少開一次原文確認。
  - 唯二逐字核對過全文的是 **Auralist（WSDM 2012）** 與 **Zou et al.（SIGIR 2020）**，以及 **da Silva & Jannach 的 calibration 綜述（arXiv:2507.02643）**。§2.2、§2.4、§3.2 的所有引號與數字都出自這三份 PDF 的內文。
- **Steck 原文的 λ 取值與實驗數據**我沒看到；§2.4 的公式 (6)(7)、KL 的三個性質、Surrogate Submodular Greedy 的 (1−1/e) 保證，全部轉述自 da Silva & Jannach 2025 綜述對 Steck 的整理，**不是 Steck 原文**。
- **「88% 純離線、8% 使用者研究、2%（1 篇）線上實驗」**是該綜述對**校準文獻**的統計，不是對整個新穎度文獻的統計。
- **da Silva & Jannach 綜述的最終發表狀態**：PDF 頁首寫 *ACM Trans. Recomm. Syst., Vol. 1, No. 1, Article 1. Publication date: January 2025*，看起來是預排版；我只能確認 arXiv 版本（2507.02643, 2025）。是否已正式刊出於 TORS，**我沒有核實**。
- **3 題這個數字**：文獻給的是「10 題以後沒有增益」與「每題中位數 5 秒」。「3」是我從 demo 的 30 秒／段時間預算和 11 維 ≫ 3 bits 的資訊量論證推出來的**設計選擇**，**文獻沒有直接支持這個數字**。§3.4 的 `p5`/`p10` arm 就是拿來檢驗它的。
- 所有工程量、延遲估計（<5 ms、O(50) 一趟）都是**估計**，沒有實測。
- 我沒有跑任何實驗、沒有改任何程式，本文所有效果宣稱都是**待驗證的假設**。

---

## 7. 參考文獻

| 出處 | 場域／年份 | URL |
|---|---|---|
| Kaminskas & Bridge, *Diversity, Serendipity, Novelty, and Coverage: A Survey and Empirical Analysis of Beyond-Accuracy Objectives in Recommender Systems* | ACM TiiS 7(1), 1–42, 2017 | https://doi.org/10.1145/2926720 |
| Zhang, Ó Séaghdha, Quercia & Jambor, *Auralist: Introducing Serendipity into Music Recommendation* | WSDM 2012, 13–22 | https://doi.org/10.1145/2124295.2124300 ／ 全文 https://researchswinger.org/publications/zhang12auralist.pdf |
| Ge, Delgado-Battenfeld & Jannach, *Beyond Accuracy: Evaluating Recommender Systems by Coverage and Serendipity* | RecSys 2010, 257–260 | https://doi.org/10.1145/1864708.1864761 |
| Adamopoulos & Tuzhilin, *On Unexpectedness in Recommender Systems* | ACM TIST 5(4), 2014 | https://doi.org/10.1145/2559952 |
| Castells, Hurley & Vargas, *Novelty and Diversity in Recommender Systems* | Recommender Systems Handbook（2015 第2版 881–918；2022 第3版 603–646） | https://doi.org/10.1007/978-1-4899-7637-6_26 ／ https://doi.org/10.1007/978-1-0716-2197-4_16 |
| Vargas & Castells, *Rank and Relevance in Novelty and Diversity Metrics for Recommender Systems* | RecSys 2011, 109–116 | https://doi.org/10.1145/2043932.2043955 |
| Steck, *Calibrated Recommendations* | RecSys 2018, 154–162 | https://doi.org/10.1145/3240323.3240372 |
| da Silva & Jannach, *Calibrated Recommendations: Survey and Future Directions* | arXiv:2507.02643, 2025 | https://arxiv.org/abs/2507.02643 |
| Kaya & Bridge, *A Comparison of Calibrated and Intent-Aware Recommendations* | RecSys 2019, 151–159 | https://doi.org/10.1145/3298689.3347045 |
| Kotkov, Wang & Veijalainen, *A Survey of Serendipity in Recommender Systems* | Knowledge-Based Systems 111, 180–192, 2016 | https://doi.org/10.1016/j.knosys.2016.08.014 |
| Kotkov, Konstan, Zhao & Veijalainen, *Investigating Serendipity in Recommender Systems Based on Real User Feedback* | SAC 2018, 1341–1350 | https://doi.org/10.1145/3167132.3167276 |
| Rashid, Albert, Cosley, Lam, McNee, Konstan & Riedl, *Getting to Know You: Learning New User Preferences in Recommender Systems* | IUI 2002, 127–134 | https://doi.org/10.1145/502716.502737 |
| Rashid, Karypis & Riedl, *Learning Preferences of New Users in Recommender Systems: An Information Theoretic Approach* | SIGKDD Explorations 10(2), 90–100, 2008 | https://doi.org/10.1145/1540276.1540302 |
| Golbandi, Koren & Lempel, *Adaptive Bootstrapping of Recommender Systems Using Decision Trees* | WSDM 2011, 595–604 | https://doi.org/10.1145/1935826.1935910 |
| Golbandi, Koren & Lempel, *On Bootstrapping Recommender Systems* | CIKM 2010, 1805–1808 | https://doi.org/10.1145/1871437.1871734 |
| Zhou, Yang & Zha, *Functional Matrix Factorizations for Cold-Start Recommendation* | SIGIR 2011, 315–324 | https://doi.org/10.1145/2009916.2009961 |
| Loepp, Hussein & Ziegler, *Choice-Based Preference Elicitation for Collaborative Filtering Recommender Systems* | CHI 2014, 3085–3094 | https://doi.org/10.1145/2556288.2557069 |
| Graus & Willemsen, *Improving the User Experience During Cold Start Through Choice-Based Preference Elicitation* | RecSys 2015, 273–276 | https://doi.org/10.1145/2792838.2799681 |
| Jannach, Manzoor, Cai & Chen, *A Survey on Conversational Recommender Systems* | ACM Computing Surveys 54(5), 2021 | https://doi.org/10.1145/3453154 |
| Zou, Chen & Kanoulas, *Towards Question-Based Recommender Systems* | SIGIR 2020（arXiv:2005.14255） | https://arxiv.org/abs/2005.14255 |
| Christakopoulou, Beutel, Li, Jain & Chi, *Q&R: A Two-Stage Approach Toward Interactive Recommendation* | KDD 2018, 139–148 | https://doi.org/10.1145/3219819.3219894 |
| Chu & Ghahramani, *Preference Learning with Gaussian Processes* | ICML 2005, 137–144 | https://doi.org/10.1145/1102351.1102369 |

（既有文件已引用、本文沿用不重列：Chen, Zhang & Zhou NeurIPS 2018 DPP；Wilhelm et al. CIKM 2018；Carbonell & Goldstein SIGIR 1998；Santos et al. WWW 2010；Jeon, Milli & Dragan NeurIPS 2020；Joachims et al. SIGIR 2005。）
