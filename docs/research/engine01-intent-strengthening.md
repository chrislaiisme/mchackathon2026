# 怎麼讓 ENGINE 01 的意圖抽取「可量測地」變好

**這份文件的定位**：不是重寫 ENGINE 01，是回答一個問題——在（a）輸出目前是繁體中文自由文字、
（b）ENGINE 02 的商品庫講封閉英文詞彙、（c）**slot-filling 準確率目前是 0 個數字**的前提下，
文獻上哪些做法真的有量測過的效果，哪些只是聽起來好。

**讀之前先讀**：[`engine01-output-reality.md`](engine01-output-reality.md)（ENGINE 01 實際吐什麼的稽核）。
本文所有「現況」敘述都以 `git show origin/engine01-intent:<path>` 唯讀取得，**未改動任何程式碼**。

**一句話結論**：ENGINE 01 最大的問題不是抽得不準，是**沒有人知道它準不準**——而它自己的準確率測試
有一個不花任何額度就能修的致命洞（只算 gold 有的欄位、完全不罰多填）。
把「封閉詞彙 enum 寫進已經在用的 `--output-schema`」是唯一一個文獻數字夠強、
成本夠低、且會真的減少 ENGINE 02 adapter 工作量的改動；其餘（澄清問題、否定上移、英文 caption）
在 30 秒一段的 demo 節奏下多半是 MEASURE FIRST 或 REJECT。

---

## 0. 現況基準（從程式碼讀到的事實，不是推測）

| 事實 | 出處 |
| --- | --- |
| 抽取走 `codex exec --output-schema`，schema 由 Pydantic `IntentExtraction` 產生，`_to_strict_schema()` 補 `additionalProperties:false`＋全欄位 `required` | `llm_client.py:49-84` |
| **`Intent` 的 13 個欄位沒有任何 `Literal`／`Enum`**，全是 `Optional[str]` / `list[str]` | `shared/schemas.py:75-95` |
| system prompt 5 條規則，**沒有一條提到詞彙表、語言或正規化** | `prompts.py:8-18` |
| 每次呼叫 8–17 秒、吃 14,000–20,000 token 的團隊共用額度 | `llm_client.py:8-11` |
| 準確率測試：`for field_name, expected_value in case["expected_intent"].items()` — **只走 gold 有的欄位** | `tests/test_accuracy.py:44` |
| 比對是字面全等（list 走 set 相等） | `tests/test_accuracy.py:28-31` |
| 10 句測試集，gold 共 **37 個 slot**，跑一次＝10 次 LLM 呼叫 | `tests/test_cases.json` |
| ENGINE 02 的封閉詞彙規模：taxonomy 101 節點＋2 collections、colour 12 族／46 個 KAGL 值、occasion 4–6、season 4、gender 5 ⇒ **合計約 160 個值** | `engine02/resources/taxonomy_v1.json`、`engine02/attribute_fill.py:48-72` |

---

## 1. 約束解碼 / schema 導向抽取

**(a) 機制**。三個層級，強度遞增：①prompt 叫它輸出 JSON（FRI）；②JSON mode（保證是合法 JSON，
不保證符合 schema）；③**grammar-constrained decoding**——在每個解碼步把不合文法的 token 的 logit 設成 −∞，
所以「輸出一定是 `Formal|Casual|Sports|Ethnic` 其中之一」是**數學保證**，不是請求。
ENGINE 01 已經站在 ③ 的入口：`--output-schema` 走的就是 OpenAI Structured Outputs，
而 Structured Outputs 的 strict schema **支援 `enum`**（已於 OpenAI 官方 Structured Outputs 指南核實）。
換句話說，把 `Optional[str]` 改成 `Literal["Formal","Casual",...]`，enum 就會自動進到那份 schema 檔。

**(b) 最強數字**。
- **封閉詞彙的情況，約束解碼是大勝**：Geng et al., *Grammar-Constrained Decoding for Structured NLP
  Tasks without Finetuning*, **EMNLP 2023**, pp.10932–10952（<https://aclanthology.org/2023.emnlp-main.674/>）。
  LLaMA-33B、4-shot 的 **entity disambiguation**（把自由文字對到一個封閉實體集，
  **和我們把「上班」對到 `Formal` 是同一類問題**）：無約束 **54.1%** → input-independent grammar **68.2%**
  → **input-dependent grammar 80.3%**。closed IE 的 triplet F1 **17.5 → 36.0**（超過 fine-tuned GenIE T5-base 的 34.8）。
  constituency parsing 的輸出合法率 **64.2% → 100%**。
- **代價是真的，但只發生在推理任務**：Tam et al., *Let Me Speak Freely?*, **EMNLP 2024 Industry Track**,
  pp.1218–1236（<https://aclanthology.org/2024.emnlp-industry.91/>）。gpt-4o-mini 的 GSM8K：
  NL **94.57** vs JSON-mode **86.95**；Shuffle Obj 82.85 → 76.43。加上嚴格 schema 更糟：
  GSM8K 上 claude-3-haiku **86.99 → 23.44**、LLaMA-3-8B **64.67 → 48.90**、gpt-3.5-turbo **74.70 → 49.25**（Table 1）。
- **但同一篇論文在分類任務上得到相反結論**，而我們就是分類任務：原文 §5.2 寫
  「In classification task JSON-mode performs much better than text due to the restriction on answer space」，
  DDXPlus 上 Gemini 1.5 Flash 開 JSON-mode 有顯著提升（Fig. 3）。
- **崩盤的原因可被規避**：作者查出 **100% 的 gpt-3.5-turbo JSON-mode 回應把 `answer` key 排在 `reason` key 前面**，
  等於強迫零樣本直答、拿掉了 CoT（§4.1）。所以「欄位順序」是可控變因，不是不可抗力。
  另外解析錯誤**不是**主因：LLaMA-3-8B 在 Last Letter/JSON 的解析錯誤率只有 0.148%，效能差距卻有 38.15%（§5.3）。
- **延遲不是理由**：Dong et al., *XGrammar*, **MLSys 2025**（<https://arxiv.org/abs/2411.15100>）宣稱
  grammar 引擎相對既有方案 **最多 100×** 加速、端到端「near-zero overhead」。
  ENGINE 01 的 8–17 秒瓶頸在 `codex exec` 子行程與模型本身，不在文法檢查。
- 反方證據要照講：.txt 團隊用**同一組 prompt** 重跑三題，結構化反而較好
  （GSM8K 0.77→0.78、Last Letter 0.73→0.77、Shuffle Obj 0.41→0.44），指控原論文兩組 prompt 不一致
  （<https://blog.dottxt.ai/say-what-you-mean.html>，**廠商部落格、非同行評審**）。

**(c) ENGINE 01 的代價**。改 `schemas.py` 的型別標註 ＋ 把 `GET /vocabulary` 的 `closed_vocabulary`
（約 160 個值）塞進 prompt 或 schema description。prompt token 會變長（估 +1.5–3K token/次，
相對現行 14–20K 是 +10~20%），延遲影響應可忽略。**風險是 Table 1 那種崩盤**——
緩解方式：在 `IntentExtraction` 最前面加一個短的 `evidence: str`（先寫理由再填槽），
且**中文原話保留**在 `*_raw` 欄位，enum 欄位另開。

**(d) 對 ENGINE 02 adapter**：**減少工作**。`ZH_OCCASION` / `ZH_SEASON` / 色詞比對三張表會從「必要」
降級成「安全網」，`unresolved` 與 `input_warnings` 會變成罕見事件而不是常態。

**(e) 判定：SHIP**（限 category / color / occasion / season / gender 五個欄位；其餘維持自由文字）。

**(f) 決定性實驗**：同一組 40 句、同一個模型、**兩組 prompt 文字相同只差 schema**，
比較 (i) 現狀自由文字 →adapter 對映，(ii) enum schema 直出。指標＝**對映後的 per-slot F1**（§2）。
配對 bootstrap；三次重複取平均與全距。這個實驗同時會驗證有沒有發生 Table 1 的崩盤。

---

## 2. Slot filling 到底該怎麼量

**(a) 機制**。文獻兩套標準指標：**Joint Goal Accuracy (JGA)**——整輪所有 slot 全對才算對；
**slot F1**——逐 slot 的 P/R/F1（`JointBERT`, Chen et al. 2019, <https://arxiv.org/abs/1902.10909>：
ATIS slot F1 96.1 / intent acc 97.5 / **句級全對只有 88.2**；SNIPS 97.0 / 98.6 / **92.8**）。
兩個一起報才看得出「差在哪一個 slot」。

**(b) 最強數字——為什麼「中文字串全等」是壞指標**。
- **標註雜訊會整個吃掉你的數字**：MultiWOZ 2.2（Zang et al., NLP4ConvAI@ACL 2020,
  <https://arxiv.org/abs/2007.12720>）修正了 **17.3% 的 utterance** 標註，並引入
  **categorical vs non-categorical slot、canonical value 與 span 標註**，明講是為了取代各家自己寫的
  string-matching heuristic。MultiWOZ 2.4（Ye et al., **SIGDIAL 2022**,
  <https://aclanthology.org/2022.sigdial-1.34/>）再修 **65% 對話中的 41% 輪次**，
  結果**同一個模型的 JGA 直接跳**：STAR 56.36 → **73.62**（+17.26）、SUMBT 49.01 → 61.86、TRADE 45.60 → 55.05。
  **也就是說：字面全等量到的東西，有 17 個百分點是標註者而不是模型。**
- **JGA 還會把上游錯誤重複計價**：Dey et al., *Towards Fair Evaluation of DST by Flexible Incorporation of
  Turn-level Performances*（arXiv 2204.03375, 2022）指出 belief state 是累積的，一錯全錯，
  提出 Flexible Goal Accuracy 給「局部正確」部分分數。ENGINE 01 是多輪累積意圖，**同一個陷阱**。
- **LLM 零樣本 DST 的參考水位**：Heck et al., ACL 2023（<https://arxiv.org/abs/2306.01386>），
  ChatGPT 在 MultiWOZ 2.1 零樣本 **JGA 56.44%**（IC-DST 56.96、D3ST 46.70）。
  **不要預期 ENGINE 01 會有 90%**；56% 上下才是這類系統的現實錨點。

**ENGINE 01 現在這個測試到底錯在哪（四條，都在程式碼裡）**：
1. **完全不罰多填**。`test_accuracy.py:44` 只迭代 `case["expected_intent"]`。
   模型在「登山用的防水外套，**顏色不重要**」那句自己補一個 `colors:["黑色"]`，**分數一分不扣**——
   而那正是會讓 ENGINE 02 候選池塌掉的錯誤。這是 recall-only，沒有 precision。
2. **字面全等**。`深灰色` vs `深灰`、`秋冬` vs `秋、冬` 都算全錯，但對下游是同一件事；
   反過來 `外套` vs `牛仔外套` 都算對或都算錯，取決於標註者當天的心情（gold 裡 L1/L2 混用）。
3. **gold 本身不一致**。case 4「深色系」在 gold 裡沒有 `colors`，
   case 9 的「大地色系」卻被標進 `style_keywords`；case 4 的「圖案不要太花」被標成 `pattern:"素面"`，
   等於**要求模型把否定改寫成肯定**，而這條規則 prompt 裡沒寫。
4. **跑一次就當答案**。沒有重複、沒有變異數。單輪結果會反號（見 `MEMORY.md` 的既有教訓）。

**(c) 該換成什麼——一個便宜、具體、10 句就能開跑的評測**：

```
步驟 0（零額度）：把 extract_intent 的原始輸出落地成 JSONL
        {case_id, message, run_idx, raw_json, latency_s, ts}
        → 之後改指標、改正規化、改對映表，全部離線重算，不再打模型。
步驟 1：測試集擴到 ~40 句 = 現有 10 句 + 30 句，其中刻意包含
        · 6 句「不在意 X」（測 dont_care ≠ unmentioned）
        · 6 句否定（「不要黑色」「不要太正式」）
        · 6 句極模糊（「想找件衣服」，gold = 全 null + 應出澄清題）
        · 6 句多輪（第 2 句只補一個欄位，測「前一輪值有沒有被弄丟」）
        · 6 句跨季／修飾色／L1-L2 邊界（「秋冬」「深藍色」「外套 vs 牛仔外套」）
步驟 2：每句標三層 gold：stated / inferred-acceptable / must-not-fill
步驟 3：正規化後再比對——把模型輸出與 gold 都先過 GET /vocabulary 的對映，
        比「Formal == Formal」而不是「上班 == 上班」。這是 MultiWOZ 2.2 的 canonical value 做法。
步驟 4：四個數字一起報
        · per-slot P / R / F1（分母＝13 個欄位，不是 gold 的欄位）
        · JGA（整句 13 個 slot 全對率）——預期會很低，這是正常的
        · hallucination rate = gold 標 must-not-fill 卻被填的比例
        · clarify precision = 該問時有問 / 不該問時沒問
步驟 5：每句跑 3 次，報 mean 與全距；比較兩個版本一律用配對檢定（同一批句子、McNemar 或配對 bootstrap）
```

**成本**：40 句 × 3 次 ≈ 120 次呼叫 ≈ **24–34 分鐘、約 1.7–2.4M 共用 token**。這是真的很貴，
所以步驟 0 的「生成與評分分離」不是可有可無——**它讓後續每一次指標迭代變成 0 成本**。

**(d) 對 adapter**：不增不減，但它第一次讓 §8.1–8.6 那些坑**有數字**，可以排優先序。
**(e) 判定：SHIP**（第 1 條「分母改成 13 欄」不花任何額度，今天就能改）。
**(f) 決定性實驗**：本節即是實驗本身。

---

## 3. 什麼時候該問，而不是猜

**(a) 機制**。澄清問題是「用一次來回換取不確定性下降」。文獻的決策規則有兩派：
**不確定性門檻**（模型自評 ambiguous 的機率 > τ 才問）與 **期望資訊增益 EIG**
（挑那個把候選解集切成兩半的問題）。

**(b) 最強數字**。
- **好問題非常值錢，壞問題會扣分**：Aliannejadi et al., **SIGIR 2019**（<https://arxiv.org/abs/1907.06554>）。
  Qulac 上 oracle 的 BestQuestion：MRR 0.2820→**0.5677**、P@1 0.1933→**0.4986（+158%）**、
  nDCG@1 0.1460→0.3988（+173%）。**但 WorstQuestion 掉到基線以下**：MRR 0.2479（基線 0.2715）、
  P@1 0.1451（基線 0.1842）。**「問」本身不是好事，問對才是。**
- **真實流量的規模感**：Zamani et al., **SIGIR 2020**（<https://arxiv.org/abs/2006.00166>），
  Bing 的 7,460 萬次澄清面板曝光／550 萬查詢。查詢**越長、意圖越分散**，互動率越高；
  **ambiguous 查詢反而互動低**（因為主流意圖已經在前幾筆結果裡了）；
  題型措辭影響巨大（"what are you trying to do?" 比通用模板高約 **5 倍**互動）；
  有澄清的 session **不滿意度低 16.6%**。
- **選擇性地問**：Kuhn, Gal & Farquhar, *CLAM*（arXiv 2212.07769, 2022/2023，**arXiv preprint，未查到正式場次**）——
  只在偵測為模糊時才問，在 Ambiguous TriviaQA 上 adjusted accuracy **約 +20 個百分點**；
  關鍵是他們的指標**對「不該問卻問了」加 0.8 的罰分**，這正是 demo 現場該用的口徑。
- **怎麼挑題**：Kobalczyk et al., *Active Task Disambiguation with LLMs*（arXiv 2502.04485, 2025）。
  用 EIG 挑問題（選能把候選解切最均的那題）：HumanEval 問 4 題後 75.9% → **85.0%**（+9.1pt）、
  APPS 64.8% → **75.5%**（+10.7pt），相對「直接叫 LLM 問問題」的 zero-shot baseline。

**(c) ENGINE 01 的代價 —— 30 秒一段的算術**。`docs/engine02-pipeline.md` §9 是三段各約 30 秒的腳本。
ENGINE 01 一次呼叫 8–17 秒。**多問一題＝多一輪 `/intent`＝再 8–17 秒**，
而使用者還要花 3–5 秒讀題目、點選項。也就是**一次澄清就吃掉 40%–70% 的一個段落**。
現行 prompt 規則 3 授權模型出 **1–3 題**，程式端**零門檻、零後處理**（`main.py:89-107`），
最壞情況是第一輪就丟三題到使用者臉上。

**(d) 對 adapter**：目前是**中性**——ENGINE 01 沒有 blocking 語意（`IntentResponse` 沒有 `ready_to_rank`），
要不要等是 ENGINE 02 自己決定，adapter 照樣排序。若 ENGINE 01 加上門檻，adapter 不用改。

**(e) 判定：MEASURE FIRST，但門檻本身直接 SHIP**。具體門檻（可寫進 prompt，零成本）：
**只有在 `item_type` 仍為 null 時才出題，且一輪最多 1 題**。
理由是三層疊起來的：①`category` 是 ENGINE 02 放寬階梯裡**永不放寬**的 slot（`constraints.py:30`），
它 null 就是真的沒東西可排；②Zamani 的資料說 ambiguous 情況互動率反而低；
③CLAM 的罰分口徑說多問的代價是實的。

**(f) 決定性實驗**：拿步驟 1 的 6 句極模糊 + 6 句清楚句，量 clarify precision／recall
與「每題平均多花幾秒」。若清楚句的誤問率 > 20%，門檻就是淨賺。

---

## 4. 否定與排除：該在上游還是下游？

**(a) 機制**。三種表示法：①留在自由文字（「不要黑色」原封不動進 `retrieval_text`）；
②上游解析成結構化 `excluded_values`；③下游解析（我們現在的 `engine02/negation.py`）。

**(b) 最強數字**。
- **①絕對不行**：NegBench（Alhamoud et al., <https://arxiv.org/abs/2501.09425>，2025）——
  CLIP 系在否定 MCQ 上**接近隨機**（4 選 1 的隨機線 25%，CLIP 在 COCO MCQ-Neg 只有 39%）；
  CLIP-laion400m 在否定 COCO 查詢上 recall@5 掉 7.7%。針對性合成資料微調後
  否定 recall@5 48.0→57.8、MCQ 39.2→47.3，全量資料下 MCQ **28.6→56.2（+27.6pt）**——
  **代表這是可修的能力缺陷，而不是我們的 encoder 特別爛。**
- **②未必比較安全**：Truong et al., *Language models are not naysayers*（arXiv 2306.08189, 2023）——
  LLM 對否定同樣不可靠，SNLI-neg 上 GPT-neo-6B **31.6%（低於隨機）**，
  且**越大越差**（inverse scaling）；只有 instruction tuning 明顯改善（InstructGPT 67.3%）。
- **③我們自己的數字（已上線，`docs/engine02-design.md` §3.35）**：只警告 vs 實際排除，
  violation@5 **0.214 → 0.000**（CI −0.241~−0.186，**p=0.00005**），NDCG@5 0.6802 → **0.7256（+0.045, p=0.0007）**，
  空結果率 0.000（29 句符合條件的小樣本）。**遵守排除沒有代價，反而更準。**

**(c)(d) 上移到 ENGINE 01 值不值**。`negation.py` 的六條規則裡，有四條**本質上需要商品庫**才成立
（「只對商品庫真的有的值觸發」「顏色以色系展開」「取修飾語不取主詞」「只加排除不動正向需求」）。
ENGINE 01 看不到商品庫，只能吐「不要 黑色」這個字面，**還是得由 adapter 對到 `Black` 並展開色系**。
所以上移只能拿走「抓到否定片語」這一步，拿不走對映那一步——
**是把工作切兩半、多一個介面，不是把工作移走**。而 Truong et al. 說明，LLM 做這件事不會比正則可靠。

**(e) 判定：REJECT「把否定解析搬到上游」；SHIP「ENGINE 01 的 `retrieval_text` 不得含否定詞」**。
也就是採用 `docs/engine02-design.md` §4.1 第 2 點的一半：ENGINE 01 產生的檢索句把否定詞**刪掉**
（不要試著解析），否定原話留在 `notes` 讓下游重新解析。這是零風險的單向要求。

**(f) 決定性實驗**：在 §2 的 6 句否定句上，比較 (i) 現況（adapter 下游解析）
(ii) ENGINE 01 自己吐 `excluded:{field,values}` 再交給 adapter。指標＝ violation@5 與誤排除率
（把使用者**要的**東西排掉的比例）。後者是上移的真正風險，現在完全沒被量過。

---

## 5. 「使用者說的」vs「模型推的」

**(a) 機制**。ENGINE 01 的 `inferred_fields`（`schemas.py:91-94`）在語意上就是
資訊檢索／推薦裡 **explicit vs implicit feedback** 的切分，處理方式也一樣：
**不是丟掉推論值，是降低它的信賴權重**。Hu, Koren & Volinsky（**ICDM 2008**,
<https://doi.org/10.1109/ICDM.2008.22>）的隱式回饋模型把每個觀測配一個信賴度
`c_ui = 1 + α·r_ui`，讓弱訊號只能小幅移動解——我們 `SlotState.INFERRED`⇒`is_hard()=False`
（`contracts.py:63-66`）就是 α→0 的極端版：推論值只進檢索、永不砍候選池。

**(b) 最強數字**。
- **推論值真的不可信**：Kim et al., *CUPID*, **COLM 2025**（<https://arxiv.org/abs/2508.01674>）——
  10 個開源與商用 LLM 從多輪互動中推斷使用者的情境偏好，
  **precision < 50%、recall < 65%**，而且「分不清先前脈絡哪些跟這次請求相關」。
  **換算到我們身上：`inferred_fields` 裡的值大約每兩個就有一個是錯的。**
- **但模型自評的信心是可用的**：Tian et al., *Just Ask for Calibration*, **EMNLP 2023**
  （<https://arxiv.org/abs/2305.14975>）——RLHF 過的模型，**口頭說出的信心比 log-prob 更準**，
  ECE 相對降約 50%（ChatGPT TriviaQA 0.140→0.054、SciQ 0.256→0.065；GPT-4 TriviaQA 0.078→0.041）。
  這對我們特別重要，因為走 `codex exec` **根本拿不到 logprob**——口頭信心是唯一可得的信號。

**(c) ENGINE 01 的代價**。`inferred_fields` 已經存在、前端已經在用黃底＋「系統推斷」標示
（`scripts/engine01-test-page/index.html:150-156`），所以真正要補的只有兩件：
①把它從 `list[str]` 升級成 `list[{field, confidence: float, basis: str}]`；
②prompt 裡明確要求**跨輪保留**（現況是每輪整包重寫，第 2 輪掉字就會讓同一個值從軟訊號變硬過濾，
見稽核 §3 坑 1）。schema 變大一點點，延遲影響可忽略。

**(d) 對 adapter**：**減少工作**——`inferred_fields` 跨輪取聯集的補償邏輯就可以退成安全網。
`confidence` 還能讓 adapter 把低信心推論值直接降成純 `retrieval_text`，不進 slot。

**(e) 判定：SHIP（保留並強化區分）**。CUPID 的 <50% precision 正好是**不能把推論值當硬條件**的論證，
而不是「推論沒用」的論證——它在我們的架構裡本來就只當軟訊號。
**MEASURE FIRST：`confidence` 數值本身**（Tian et al. 的校準結論來自 RLHF 模型的問答任務，
不保證遷移到槽位抽取）。

**(f) 決定性實驗**：在 §2 的 gold 上把 `inferred` 標成第三類，量
「模型標為 inferred 的欄位，實際正確率是多少」與「模型**沒**標 inferred 卻其實是推論的比例」（漏標率）。
後者是誠實性的真正風險——一個被包裝成使用者原話的推論值，前端不會標黃底。

---

## 6. 中文直出 vs 叫 LLM 直接寫英文 caption

**(a) 機制**。兩條路：(i) ENGINE 01 吐中文 → adapter 查表對映（現況）；
(ii) ENGINE 01 額外吐一句英文 `retrieval_text` → 直接餵 CLIP 系 encoder。

**(b) 最強數字**。
- **把中文直接餵英文 encoder 是災難**：Geigle et al., *Babel-ImageNet*, **NAACL 2024**
  （<https://arxiv.org/abs/2306.08658>）——**原始 OpenAI CLIP（純英文訓練）在高資源非英語上只有 9.23%**，
  英語是 **76.95%**；中低資源語言 3.79–5.02%。即使是多語訓練的 OpenCLIP XLMR-L H-14，
  高資源非英語仍比英語低 **24.7 個百分點**（52.23 vs 76.95）。
  我們的 encoder 是 marqo-fashionSigLIP，tokenizer 是 **32k 英文 SentencePiece**
  （`docs/research/paraphrase-robustness.md` 已核實）——**中文進去就是碎片**。
- **專門訓練的中文塔可以很好，但那要換模型**：Chinese-CLIP（Yang et al., arXiv 2211.01335, 2022）
  在 Flickr30K-CN text→image R@1 **68.0**、MUGE 59.0，遠勝 Wukong ViT-L/14 的 51.7。
  **代價是丟掉 marqo-fashionSigLIP 的時尚領域微調**，這個交換在 hackathon 尺度不划算。
- **「叫 LLM 寫英文」在 CJK 上有正面證據**：Rakuten（**NAACL 2024 Industry**,
  <https://aclanthology.org/2024.naacl-industry.39/>）——日文電商查詢端 refinement **+3.5 點**、
  下游 NER **+11.7 點**（此條已在 `paraphrase-robustness.md` 被逐字核實為 V）。

**(c) ENGINE 01 的代價**。同一次呼叫多產一個 `retrieval_text_en: str` 欄位，
幾乎不增延遲。**但 prompts.py:5-6 的註解明講 prompt 刻意用中文寫**，
加一個英文輸出欄位是否會讓模型在中英之間切換而傷到中文槽位抽取——**這是要量的，不是可以假設的**。

**(d) 對 adapter**：**減少工作**（`retrieval_text` 可以設 `retrieval_text_normalized=true`，
本輪就能吃到 hybrid 的 BM25 側；現況因為中文詞進 BM25 只是噪音，一律設 false）。
**但不會取代對映表**——硬條件的 `required_values` 還是得是商品庫的字面值，
一句英文 caption 對不出 `Navy Blue`。**英文 caption 補的是 dense 側，不是硬條件側。**

**(e) 判定：SHIP（新增 `retrieval_text_en`，與中文欄位並存）；REJECT（用英文取代中文槽位）**。
後者會直接打壞 ENGINE 01 自己的 gold（`test_cases.json` 全中文，英文化在他們的測試裡一律判錯）。

**(f) 決定性實驗**：同一批查詢，比較 dense 檢索用 (i) adapter 從槽位拼出來的英文串
(ii) ENGINE 01 直出的英文 caption (iii) 兩者串接。指標＝ NDCG@5 / Recall@20，配對 bootstrap。
**同時必跑對照**：加了英文欄位之後，中文槽位 F1（§2）有沒有變差。

---

## ENGINE 01 該改的，照順序

1. 把 `test_accuracy.py` 的分母從 `case["expected_intent"].items()` 改成**全部 13 個欄位**，
   並同時印 precision / recall / JGA / 多填率——這條**不花任何 LLM 額度**，今天就能改。
2. 在 `extract_intent()` 外面加一層，把每次呼叫的 `{句子, 原始 JSON, 延遲, 時間戳}` 落地成 JSONL，
   讓之後所有指標與對映的迭代都離線重算、零成本。
3. `Intent` 加上 `gender: Optional[str]` 欄位——現在 ENGINE 02 的 `gender` 永遠填不了值，
   而它是放寬階梯裡永不放寬的兩個 slot 之一，不篩就是男女混排。
4. 把 `category` / `color` / `occasion` / `season` / `gender` 五個欄位改成 `Literal[...]`
   （值取自 `GET /vocabulary` 的 `closed_vocabulary`，約 160 個），中文原話另存 `*_raw` 欄位。
5. 在 `IntentExtraction` 的**最前面**加一個 `evidence: str`，強制模型先寫理由再填槽
   （Tam et al. 查出的崩盤原因就是 `answer` key 排在 `reason` 前面）。
6. 在 prompt 裡加一條硬規則：**只有 `item_type` 為 null 時才出澄清題，且一輪最多 1 題**。
7. 新增 `dont_care: list[str]` 欄位，讓「顏色不重要」跟「沒提到顏色」在 schema 裡長得不一樣。
8. 新增 `retrieval_text_en: str`（一句英文短描述），並在 prompt 裡明令**不得含否定詞**，
   否定原話留在 `notes`。
9. 把 `inferred_fields` 升級成 `list[{field, confidence, basis}]`，並在 prompt 裡要求**跨輪保留**
   而不是每輪整包重寫。
10. 在 `llm_client.py:136` 補 `except subprocess.TimeoutExpired`，回一個有 body 的 503 而不是裸 500。
11. 測試集從 10 句擴到 ~40 句，補齊 dont_care / 否定 / 極模糊 / 多輪 / 跨季與修飾色五類。

## ENGINE 02 無論如何都要留著的安全網

即使上面 11 條全做完，`engine02/intent_adapter.py` 的這些行為**一條都不能拿掉**——
因為 demo 現場真正會出事的，是 ENGINE 01 沒照 schema 走、或根本沒回應的那一次：

- **中英對照表**（`ZH_OCCASION` / `ZH_SEASON` / `ZH_GENDER` / 色詞比對）：enum 不保證上游今天就上線，
  也不保證所有欄位都改。
- **「對不到就不變硬條件」**：任何無法解析到商品庫值的詞留在檢索文字、列入 `unresolved`，
  永不升格成硬過濾（避免候選集無聲歸零）。
- **無條件丟棄 `budget_min`/`budget_max`**：`price` 欄 100% 為 null，
  當硬條件會讓候選集瞬間歸零而 `budget:drop` 又在放寬階梯的最後一格。
- **`inferred` 一律軟性、且跨輪取聯集**：CUPID 的 <50% precision 就是理由。
- **`engine02/negation.py` 繼續在下游跑**：上游解析否定的誤排除風險沒被量過，
  而色系展開與「只對商品庫有的值觸發」本來就只有下游做得到。
- **`round` 變小 ⇒ 視為 session 重置**，清掉本地累積的回饋。
- **ENGINE 01 500／timeout ⇒ 降級成純 dense**：拿使用者原句當 `retrieval_text`、
  所有 slot 留 `UNMENTIONED`，不因為上游掛掉就整場空白。
- **所有丟棄與對映都寫進 `constraint_report.input_warnings`**：邊界的每一個決定都要看得見。

---

## 我無法核實的部分

- **ENGINE 01 真實的 slot-filling 準確率**：本文所有「它現在多準」的推斷都來自 prompt 文字與人工標註，
  **我沒有 `codex` 登入、沒有跑過 `test_accuracy.py`**，一個觀測值都沒有。
- **NegBench 的正式場次在我們自己的文件裡就不一致**：`docs/engine02-design.md:46` 寫「CVPR 2025」、
  `:830` 寫「ICML 2025」。我這次從 arXiv 頁面**沒有查到場次欄位**，只確認了 arXiv 2501.09425 與數字。
  引用前請先統一。
- **CLAM 的發表場次**：arXiv 2212.07769 頁面沒有 comments/venue 欄位，只有 v1 2022-12-15、v2 2023-02-20。
  本文一律以 preprint 引用。
- **Active Task Disambiguation 是否確為 ICLR 2025**：ar5iv 摘要頁未明載，僅有 arXiv 2502.04485。
- **OpenAI Structured Outputs 的 enum 數量上限**：官方 Structured Outputs 指南確認 strict schema
  **支援 `enum`**，但該頁未列出 enum 總數／字元數上限，我沒查到確切數字。
  我們估算只需要約 160 個值，主觀判斷遠低於任何合理上限，但**這是判斷不是查證**。
- **Hu/Koren/Volinsky (ICDM 2008) 的信賴度公式**我只引用機制、未重新核實論文內的數值。
- **「加一個英文欄位會不會傷到中文抽取」完全沒有證據**，兩個方向都只是假設，必須實測。
- **Rakuten NAACL 2024 的 +3.5／+11.7** 是沿用 `paraphrase-robustness.md` 已標為已核實（V）的結論，
  本次未重新開啟原文。
