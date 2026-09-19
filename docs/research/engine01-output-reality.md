# ENGINE 01 實際輸出的樣子（給寫 adapter 的人）

**目的**：不是抄 schema 說「可能」會出什麼，而是把程式碼與測試資料真正會產出的東西寫下來，讓 ENGINE 02 的 adapter 在台上不會被意外炸掉。

**取材方式**：全部以 `git show origin/engine01-intent:<path>` 唯讀讀取，未改動任何程式碼、未切換分支。ENGINE 02 這側的行為則是在本分支 `engine02-research` 上實際跑程式碼驗證（見 §8 的實驗紀錄）。

**一句話結論**：ENGINE 01 的輸出**全部是中文自由文字**，沒有任何正規化、沒有封閉詞彙表、沒有 gender、沒有幣別，而且 `budget_*` 對我們的公開商品庫完全無效（price 欄 100% 是空的）。category 與 color 我們已經吃得下中文，**occasion / season 完全吃不下**，而 occasion/season 正好是 10 句測試句裡出現最密集的兩個欄位。

---

## 1. `Intent` 每個欄位的真實值域

定義：`backend/shared/schemas.py:75-95`（分支 `origin/engine01-intent`）。

| 欄位 | 型別 | 實際語言／值域 | 是否封閉詞彙 |
|---|---|---|---|
| `item_type` | `Optional[str]` (L80) | 中文自由文字，「襯衫」「外套」「牛仔外套」 | 否 |
| `colors` | `list[str]` (L81) | 中文自由文字，「黑色」「深灰色」 | 否 |
| `occasion` | `Optional[str]` (L82) | 中文自由文字，「正式場合」「上班」「登山」 | 否 |
| `budget_min` / `budget_max` | `Optional[float]` (L83-84) | 純數字，無單位無幣別 | — |
| `style_keywords` | `list[str]` (L85) | 中文自由文字，「簡約」「透氣」「防水」「大地色系」 | 否 |
| `material` | `Optional[str]` (L86) | 中文自由文字，「棉」「毛料」 | 否 |
| `season` | `Optional[str]` (L87) | 中文自由文字，「夏天」「秋冬」 | 否 |
| `fit` | `Optional[str]` (L88) | 中文自由文字，「修身」 | 否 |
| `pattern` | `Optional[str]` (L89) | 中文自由文字，「素面」 | 否 |
| `collar` | `Optional[str]` (L90) | 中文自由文字，「圓領」「V領」 | 否 |
| `inferred_fields` | `list[str]` (L91) | 英文欄位名稱字串（見 §3） | 半封閉 |
| `notes` | `Optional[str]` (L95) | 中文自由文字 | 否 |

**沒有任何 `Literal` / `Enum` / `Field(pattern=...)`**。schemas.py 唯一存在的封閉清單是 `STYLE_PREFERENCE_OPTIONS`／`AGE_RANGE_OPTIONS`（L19-20），那是 `UserProfile` 的偏好調查用的，**跟 `Intent` 無關**，而且註解自己就寫了「後端目前不強制檢查一定要是這幾個值」（L17）。

### prompt 對值域說了什麼（＝幾乎沒說）

`backend/engine01_intent/prompts.py:8-18`，整段 system prompt 只有 5 條規則，**沒有一條提到詞彙表、語言、大小寫或正規化**：

```
prompts.py:13  1. 只更新使用者這句話明確提到、或可以合理從情境（天氣、季節、節慶等）推斷的欄位；
               沒提到、也推斷不出來的欄位保持原值或留空，不要亂猜。
prompts.py:14  2. 任何你自己推斷（而非使用者原話）填入的欄位，欄位名稱要加進 inferred_fields；
prompts.py:15  3. 如果目前的意圖太模糊、關鍵欄位（品項、場合等）還缺，生成 1-3 題選擇題…
prompts.py:16  4. 不要覆蓋使用者之前已經明確講過、這輪也沒有矛盾說法的欄位。
prompts.py:17  5. 只輸出結構化資料，不要輸出額外的說明文字。
```

而且 prompts.py:5-6 的註解明講了語言取向：

> 「prompt 本身刻意用中文寫，因為使用者輸入本來就是中文，這樣模型比較不會在中英文之間切換造成理解落差。」

→ **設計上就是要它回中文。** 不要期待哪天它自己會吐 `"Shirts"`。

### 「襯衫 / shirt / Shirts」到底是哪個？→ **「襯衫」**

`backend/engine01_intent/tests/test_cases.json` 是唯一的人工標註真相來源，10 句全中文標註：

```json
test_cases.json:12-19   "item_type": "襯衫", "colors": ["白色"], "occasion": "上班", "season": "夏天",
                        "style_keywords": ["透氣"]
test_cases.json:23-26   "item_type": "牛仔外套", "budget_max": 2000
test_cases.json:30-34   "item_type": "連帽外套", "occasion": "休閒", "pattern": "素面"
test_cases.json:38-43   "item_type": "洋裝", "colors": ["粉色"], "occasion": "約會", "fit": "修身"
test_cases.json:47-51   "item_type": "外套", "style_keywords": ["防水"], "occasion": "登山"
test_cases.json:55-60   "item_type": "T恤", "colors": ["白色","米色"], "material": "棉", "collar": "圓領"
test_cases.json:64-70   "item_type": "大衣", "colors": ["黑色","深灰色"], "material": "毛料",
                        "occasion": "上班", "season": "秋冬"
test_cases.json:74-78   "item_type": "牛仔外套", "occasion": "休閒",
                        "style_keywords": ["短版","大地色系"]
test_cases.json:82-87   "item_type": "針織衫", "colors": ["深藍色"], "collar": "V領",
                        "style_keywords": ["簡約"]
```

`docs/interface-contract.md:36-52` 的官方範例也一樣（`"item_type": "外套"`、`"material": "秋冬材質"`）。

而且比對邏輯是**字面完全相等**：`tests/test_accuracy.py:28-31`

```python
actual_value = getattr(actual, field_name)
if isinstance(expected_value, list):
    return set(actual_value or []) == set(expected_value)
return actual_value == expected_value
```

也就是說「這個引擎算自己抽對了」的標準，就是吐出跟上面一模一樣的中文字串。任何把它英文化的行為，在他們自己的測試裡會被判錯。**這個習慣不會改。**

各欄位觀察到的粒度：

- `item_type`：品項層級不固定。有時 L1（「外套」），有時 L2（「牛仔外套」「連帽外套」「針織衫」）。
- `colors`：帶「色」字的完整詞，且**會出現修飾色**（「深灰色」「深藍色」），不是基本色名。
- `occasion`：**混合了場合與活動**——「正式場合」「上班」「約會」是場合，「登山」其實是活動，「休閒」是風格。
- `season`：口語季節，且**會出現跨季**（「秋冬」），不是單一季。
- `material`：材質名詞（「棉」「毛料」）；contract 範例甚至出現過「秋冬材質」這種非材質的值。
- `fit`/`pattern`/`collar`：形容詞（「修身」「素面」「圓領」「V領」）。
- `style_keywords`：**垃圾桶欄位**，什麼都往裡塞——風格（「簡約」）、機能（「透氣」「防水」）、版型（「短版」）、甚至顏色（「大地色系」，test_cases.json:77）。

---

## 2. Null 與空值

**保證：13 個 key 每次都會在。** `llm_client.py:49-71` 的 `_to_strict_schema()` 把每個 object 節點都補上 `required = list(properties.keys())`。我在 scratchpad 重跑了同一段程式（用 engine01 分支的 schemas.py），產出的 Intent 節點 `required` 確實是全部 13 個欄位，缺值以 `anyOf:[{string},{null}]` 表達。

因此 adapter 可以安全假設 key 一定存在，值為 `null` 或 `[]`：

```json
{"item_type":null,"colors":[],"occasion":null,"budget_min":null,"budget_max":null,
 "style_keywords":[],"material":null,"season":null,"fit":null,"pattern":null,
 "collar":null,"inferred_fields":[],"notes":null}
```

（這是 `Intent()` 的實際 `model_dump_json()` 輸出，也是第一輪送進 prompt 的「目前累積意圖」，`llm_client.py:91`。）

**哪些欄位常態是空的**：以 10 句測試句的標註來看，`budget_min` 0/10、`budget_max` 1/10、`notes` 0/10、`material` 2/10、`fit` 1/10、`pattern` 1/10、`collar` 2/10、`season` 2/10。常有值的只有 `item_type` 10/10、`occasion` 6/10、`colors` 5/10、`style_keywords` 5/10。

**使用者講得含糊時會怎樣**：prompt 規則 1（prompts.py:13）明寫「沒提到、也推斷不出來的欄位保持原值或留空，**不要亂猜**」，規則 3 要求改成出澄清問題。`docs/interface-contract.md:54` 也說「一句模糊的話，就只會產出大部分是 null 的意圖，再搭配澄清問題」。

**它會不會發明值**：**會，而且是刻意的**，但只在「可從情境合理推斷」時（prompts.py:13 的「天氣、季節、節慶等」），且必須標進 `inferred_fields`。`docs/engine01-intent.md:47-49` 稱之為「情境推斷」。所以「發明」與「捏造」的界線就是 `inferred_fields` 有沒有列到——這點對我們是好消息，見 §3。

**沒有任何程式碼會驗證它有沒有乖乖照做。** 唯一的把關是 JSON schema（型別層級），`inferred_fields` 裡的字串沒有被檢查是不是合法欄位名。

---

## 3. `inferred_fields`：語意跟我們的 `SlotState.INFERRED` 對得上

- 定義與註解：`schemas.py:91-94`
  > 「Names of the fields above that GPT filled in by contextual inference (weather, season, etc.) rather than the user stating them.」
- 內容是**上面那些欄位的名稱字串**，例如 `["season"]`（`docs/interface-contract.md:49`）。
- 填入條件：prompts.py:14 規則 2 ——「任何你自己推斷（而非使用者原話）填入的欄位，欄位名稱要加進 inferred_fields；使用者親口說的欄位不要出現在 inferred_fields。」
- 前端已經在用：`scripts/engine01-test-page/index.html:150,155-156` 把 `inferred_fields` 轉成 Set，命中的列加黃底＋「系統推斷」標籤。

**語意確認：對得上。** 我們 `engine02/contracts.py:29-42` 的四態：

```python
SlotState.VALUE      = "value"      # 有值（使用者明說）
SlotState.INFERRED   = "inferred"   # 系統推論
...
def is_hard(self) -> bool:          # contracts.py:63-66
    if self.hard is not None: return self.hard
    return self.state == SlotState.VALUE
```

→ `inferred` 的 slot `is_hard()` 回 False，`constraints.build_mask()`（`engine02/constraints.py:77`）就會跳過它，變成純軟訊號。**這正是 ENGINE 01 對 `inferred_fields` 的意圖**，兩邊不需要協調，adapter 直接照 `inferred_fields` 決定 `state` 即可。

**但有三個坑**：

1. **`inferred_fields` 是每輪由模型整包重寫的**，程式端沒有任何合併或保存邏輯（`main.py:98` 直接 `state.intent = extraction.intent`）。第 1 輪推斷出的 `season` 很可能在第 2 輪的 `inferred_fields` 裡消失，於是同一個值從軟訊號突然變成硬過濾。
2. **沒有 `dont_care` 對應物。** 測試句「登山用的防水外套，**顏色不重要**」（test_cases.json:47-51）的期望標註是 `colors` 根本不出現——也就是「不在意」跟「沒提到」在 `Intent` 裡**長得一模一樣**（都是 `[]`）。我們的 `SlotState.DONT_CARE` 永遠不會被 ENGINE 01 觸發。
3. 欄位名稱是 ENGINE 01 的名稱（`item_type`/`colors`/…），不是我們的 slot 名稱（`category`/`color`/…），adapter 要自己對照。

---

## 4. Session 與 round

- **`session_id` 產生**：`session_store.py:36` ——`key_session_id = session_id or str(uuid.uuid4())`。前端第一次不帶就開新的；**帶了但查不到也不會噴錯，一樣當新的開**（`session_store.py:35` 註解明講「例如伺服器剛重啟過」）。
- **key 是 `(user_id, session_id)`**（`session_store.py:30`），`user_id` 來自驗證過的 token，不是前端傳的（`docs/interface-contract.md:30`）。
- **`round` 起始 0**（`session_store.py:24`），在 `main.py:99` 的 `state.round += 1` 遞增，**在 LLM 呼叫成功之後**。所以第一次成功回應的 `round` 是 **1**；LLM 拋例外時 round 不會增加，intent 也不會被寫回（`main.py:96-100`）。
- **輪與輪之間存了什麼**：只有 `SessionState(session_id, intent, round)`（`session_store.py:18-24`）。**原始句子沒存、clarifying_questions 沒存、參考圖沒存。**
- **第 2 輪送什麼**：**送完整的意圖快照，不是 delta。** `main.py:102-107` 回傳 `intent=state.intent`，而 `state.intent` 在 L98 被模型回傳的整包意圖整個取代。合併是在模型內部做的：`llm_client.py:89-93` 把「目前累積的結構化意圖（JSON）」＋「使用者這一輪新說的話」串成一個 prompt 字串（`codex exec` 是單次呼叫，沒有 messages 陣列，見 L87-88 註解）。
- 記憶體字典，**重啟即全清**（`session_store.py:5-7, 28-29`）。沒有資料庫。

→ 對 adapter 的意義：每輪都是 full snapshot，可以無狀態地重建 `Engine02Request.constraints`；但**前一輪的值可能被模型悄悄改掉或掉字**，不要假設單調累積。而且 `utterances` 我們要自己在 ENGINE 02 這側累積，ENGINE 01 不會給我們歷史句子。

---

## 5. 澄清問題

- 出題條件：prompts.py:15 規則 3 ——「如果目前的意圖太模糊、關鍵欄位（品項、場合等）還缺，生成 1-3 題選擇題…意圖已經夠明確時，回傳空的 `clarifying_questions` 陣列。」**判斷權完全在模型**，程式端沒有任何門檻或後處理。
- 每一輪都可能出，不只第一輪：`docs/engine01-intent.md:45`、`docs/interface-contract.md:60`。
- 結構：`schemas.py:107-114`，`field`（要補哪個 Intent 欄位）＋ `question` ＋ `options: list[{id,label}]` ＋ `allow_free_text`（預設 True，L114 註解說「理論上一直是 True」）。`options[].id` 是自由字串，範例是英文 slug（`interface-contract.md:66-70`：`casual`/`work`/`date`），`label` 是中文。
- **ENGINE 01 有沒有要求 ENGINE 02 等答案？沒有。** 程式與文件都找不到任何「阻擋」語意：`main.py:89-107` 就是回應完就結束，`IntentResponse`（`schemas.py:128-132`）沒有 `blocking`/`ready_to_rank` 之類的旗標。`docs/engine01-intent.md:23` 描述的實測流程是「在同一個 session 裡點澄清問題的選項卡片，正確累加進同一組意圖」——選項被點下去就是**再打一次 `/intent`，message 帶選項文字**（`scripts/engine01-test-page/index.html:193` 的 `overrideText` 走這條）。
- → **要不要等，是我們自己的決定。** 建議：`clarifying_questions` 非空時照樣排序（我們有 relaxation ladder，不會空手），但在卡片上標示「條件還不完整」。

---

## 6. 預算：單位、幣別，以及一個必須講白的事實

- `budget_min` / `budget_max` 是 `Optional[float]`（`schemas.py:83-84`）。**schema 裡沒有 currency 欄位，prompt 也完全沒提幣別。**
- 唯一的實證：test_cases.json:22-26，「預算大概兩千元以內」→ `"budget_max": 2000`。→ 單位是**元，隱含新台幣**，數字直接是面額（不是分、不是千元）。`budget_min` 在 10 句裡從未出現過。
- `interface-contract.md:43` 的範例 `"budget_max": 3000` 同樣沒有幣別。

**必須講白：我們的公開商品庫沒有價格。** 實測 `data/catalog/kagl/items.parquet`（5000 列）：`price` 欄 **100% 為 null**，`currency` 同樣沒有可用值。

而 `engine02/constraints.py:88-98` 的預算過濾是：

```python
price = pd.to_numeric(items["price"], errors="coerce").to_numpy(copy=True)
ok = ~np.isnan(price)          # ← 全 NaN ⇒ 整個 ok 全 False
```

→ **只要 adapter 把 `budget_max` 當成硬約束填進 `BudgetSlot` 且 `state=VALUE`，候選集會瞬間歸零**，然後 relaxation ladder 才慢慢救——但 `budget:drop` 是 ladder 的**最後一步**（`constraints.py:22-30`），在它之前 `season:drop`、`occasion:drop`、`color:drop` 已經先被犧牲掉了。結果不是空手，而是**一串幾乎沒有條件的商品**。

**結論：adapter 必須無條件丟棄 `budget_min`/`budget_max`**（或最多只放進解釋文字），在 `BudgetSlot` 上保持 `state=UNMENTIONED`。

---

## 7. 程式做了、但 schema 沒說的事

- **零後處理、零正規化。** `main.py:96-100` 只做三件事：取 session state → 呼叫 LLM → 整包覆蓋並存回。沒有 trim、沒有大小寫處理、沒有詞彙表對映、沒有欄位白名單檢查、沒有 `inferred_fields` 合法性檢查。
- **零重試。** `llm_client.py:128-150` 只跑一次 `subprocess.run`，非 0 exit code 直接 `raise RuntimeError`。
- **timeout 沒被接住。** `llm_client.py:136` 設了 `timeout=_CODEX_TIMEOUT_SECONDS`（預設 90 秒，L40），但 `except` 只接 `FileNotFoundError`（L138）——`subprocess.TimeoutExpired` 會直接往上冒。
- **延遲很高。** 模組 docstring（`llm_client.py:8-11`）自承「每次呼叫約 8-17 秒、吃掉 14,000-20,000 token 的團隊共用 Codex 額度」。`README.md:35` 也再講一次。→ **ENGINE 02 的 p99 預算跟這個比起來是零頭；台上的等待感全部來自 ENGINE 01。**
- **執行方式是 shell 出去叫 `codex exec` CLI**（`llm_client.py:106-126`），不是 OpenAI SDK。機器上要先 `codex login`（`README.md:11-17`）。
- **CORS 預設只開 `http://localhost:5173`**（`main.py:41`），用 `CORS_ALLOWED_ORIGINS` 逗號分隔覆蓋。
- **`reference_image_url` 是死的。** `IntentRequest` 有這個欄位（`schemas.py:125`），但 `main.py:96` 呼叫 `extract_intent(request.message, state.intent)` **完全沒有把它傳下去**。丟進來會被靜默忽略。
- **`Intent` 沒有 gender 欄位。** 我們 `HardConstraints.gender`（`contracts.py:90`）永遠無法從 ENGINE 01 填值，而 `gender` 是 ladder 裡**永不放寬**的兩個 slot 之一（`constraints.py:30`）。KAGL 是 Men 2595 / Women 1994 / Unisex 274 → 不篩就是男女混排。

### HTTP 狀態碼與錯誤形狀（`POST /intent`）

| 狀況 | 碼 | body |
|---|---|---|
| 正常 | 200 | `IntentResponse` |
| 缺 / 格式錯的 `Authorization: Bearer` | 401 | `{"detail":"Missing bearer token"}`（`auth.py:130-131`） |
| token 壞掉或過期 | 401 | `{"detail":"Invalid or expired session token"}`（`auth.py:136-137`） |
| token 合法但使用者檔案不存在 | 401 | `{"detail":"Unknown user"}`（`auth.py:142`） |
| request body 缺 `message` | 422 | FastAPI 預設的 validation error |
| `codex` 不在 PATH | **500** | 無 JSON，`RuntimeError`（`llm_client.py:140-143`） |
| `codex exec` 非 0 退出（沒登入／額度用完） | **500** | 無 JSON，`RuntimeError`（`llm_client.py:148-150`） |
| 超過 90 秒 | **500** | 無 JSON，`TimeoutExpired` 未被接住 |
| 模型回傳不合 schema | **500** | 無 JSON，Pydantic `ValidationError`（`llm_client.py:156`） |

→ **所有 LLM 端的失敗都是裸 500，沒有結構化錯誤 body。** adapter 要用 HTTP 狀態碼判斷，不要試著 parse。另外注意：`session_store.get_or_create()` 在 `main.py:95` 就已經把 session 寫進字典（`session_store.py:40-41`），所以**失敗的第一輪會留下一個 `round=0`、空 intent 的 session**。

### 真實 POST /intent 回應範例

Request（`DEV_BYPASS_AUTH=true`，取自 `README.md:38-41` 的 curl）：

```json
{"message": "秋冬要穿去上班的毛料大衣，黑色或深灰色"}
```

Response 200（依 `IntentResponse`（`schemas.py:128-132`）＋ strict schema 的 13 個必填 key ＋ test_cases.json:62-71 的人工標註組出來；`session_id` 是 uuid4，`round` 從 1 起算）：

```json
{
  "session_id": "3f1c9b42-7a0e-4d9a-9a11-2c5f6b8e0d31",
  "round": 1,
  "intent": {
    "item_type": "大衣",
    "colors": ["黑色", "深灰色"],
    "occasion": "上班",
    "budget_min": null,
    "budget_max": null,
    "style_keywords": [],
    "material": "毛料",
    "season": "秋冬",
    "fit": null,
    "pattern": null,
    "collar": null,
    "inferred_fields": [],
    "notes": null
  },
  "clarifying_questions": []
}
```

模糊句（例如「想找件衣服」）時的形狀，依 prompts.py:15 ＋ `interface-contract.md:62-72`：

```json
{
  "session_id": "3f1c9b42-7a0e-4d9a-9a11-2c5f6b8e0d31",
  "round": 1,
  "intent": {"item_type": null, "colors": [], "occasion": null, "budget_min": null,
             "budget_max": null, "style_keywords": [], "material": null, "season": null,
             "fit": null, "pattern": null, "collar": null, "inferred_fields": [], "notes": null},
  "clarifying_questions": [
    {"field": "occasion",
     "question": "這件外套主要會在什麼場合穿？",
     "options": [{"id": "casual", "label": "日常休閒"},
                 {"id": "work", "label": "上班／正式"},
                 {"id": "date", "label": "約會／社交"}],
     "allow_free_text": true}
  ]
}
```

---

## 8. 會怎麼弄死我們（依機率排序）

以下每一條都在本分支實際跑程式碼驗證過。

### 8.1 `occasion` / `season` 的中文 100% 對不上，而且我們沒有任何對映表 —— 機率：必定發生

實測（`data/catalog/kagl/items.parquet`，字串 strip+lower 後比對）：

```
occasion '正式場合' matches: 0   '上班': 0   '休閒': 0   '約會': 0   '登山': 0
season   '夏天'    matches: 0   '秋冬': 0
```

catalog 的實際值是 `Casual 3842 / Sports 489 / Formal 422 / Ethnic 230 / Travel 6 / Smart Casual 4`、`Summer 2373 / Fall 1357 / Winter 756 / Spring 493`。

`engine02/` 底下**沒有 `OCCASION_ZH` 或 `SEASON_ZH`**（grep 無結果）。後果：mask 歸零 → ladder 的 `occasion:allow_unknown` 沒用（null 率 0.1%）→ 一路放寬到 `occasion:drop`/`season:drop`，回傳的東西場合完全不對，且 `satisfaction` 報 0。
**Adapter 必須自己補這兩張表。** 「秋冬」還要拆成兩個值（`Fall`+`Winter`）。

### 8.2 `budget_max` 讓候選集歸零後被 ladder 拖垮 —— 機率：只要使用者提錢就發生

見 §6。price 欄 100% null，`constraints.py:91` 的 `ok = ~np.isnan(price)` 全 False。`budget:drop` 在 ladder 最後一格，之前先把 color/season/occasion 全犧牲掉。
**Adapter 直接丟棄 budget，不要當硬約束。**

### 8.3 修飾色掉出我們的中文色表 —— 機率：高（10 句測試句就中 2 句）

實測 `engine02.attribute_fill.normalize_color_values`：

```
['黑色']          -> (['Black'], [('黑色','Black')])        ✓
['白色','米色']   -> (['White','Beige'], …)                 ✓
['粉色']          -> (['Pink'], …)                          ✓
['黑色','深灰色'] -> (['Black','深灰色'], …)   ← 深灰色 未轉
['深藍色']        -> (['深藍色'], [])          ← 完全未轉
```

原因：`attribute_fill.py:79-92` 的 `COLOR_ZH` 收了 `深灰`、`深藍`，**但沒收 `深灰色`、`深藍色`**。而 ENGINE 01 的習慣是**一律帶「色」字**（test_cases.json:65, 84 就是這兩個值）。
色欄 null 率 0%，所以 `color:allow_unknown` 無效，要一路走到 ladder 第 7 格 `color:drop`。
**修法（在 adapter 側，不改 engine02）**：轉換前先剝掉結尾的「色」再查表；或把 `深藍色` 直接對到 `Navy Blue`。

### 8.4 `item_type` 的品項粒度對不上 KAGL 的 `category` —— 機率：中高

好消息：`taxonomy.resolve_category_values` 吃得下中文，實測 8 個測試值全中：

```
外套→['outerwear']   襯衫→['tops.shirts']   牛仔外套→['outerwear.jackets']
連帽外套→['outerwear.jackets']   洋裝→['dresses.dresses','dresses.party_dresses']
T恤→['tops.tshirts']   大衣→['outerwear.coats']   針織衫→['tops.sweaters']
```

壞消息：KAGL 的 `category` 只有 9 個粗類，其中 **`outerwear` 只有 42 件、`dress` 只有 19 件**（total 5000）。而 `category` 是 ladder 裡**永不放寬**的兩個 slot 之一（`constraints.py:30`：「a wrong category is not a recommendation」）。
→ 只要使用者說「大衣」「洋裝」，候選池只有數十件，top-5 幾乎是把整個小池子倒出來。這不會 4xx，但台上會很難看。

### 8.5 `style_keywords` 是垃圾桶，會把顏色混進來 —— 機率：中

test_cases.json:77 把「大地色系」標在 `style_keywords`，不是 `colors`。我們的 `HardConstraints.style_keywords`（`contracts.py:91`）幸好**不在 `SLOT_COLUMNS`**（`constraints.py:18`），所以不會硬過濾——但如果 adapter 把它拼進 `retrieval_text`，BM25 會拿到中文詞而 catalog 全是英文，只會加噪音。
→ 拼進 `retrieval_text` 時務必同時設 `retrieval_text_normalized: false`（`contracts.py:191-194` 說明：off-vocabulary 的字給 BM25 只會變噪音，T1 實測 hybrid 0.09–0.21 vs dense 0.43–0.46）。

### 8.6 `material` / `fit` / `pattern` / `collar` / `notes` 在我們這裡沒有歸宿 —— 機率：中

KAGL 的欄位只有 `item_id, title, description, category, subcategory, color, season, occasion, gender, price, currency, outfit_ids, image_path, source, attr_source`（實測）——**沒有 material / fit / pattern / collar 欄**。
`taxonomy_v1.json` 的 `attribute_defs` 有 `neckline`（圓領/V領/…）、`fit`（合身、標準、寬鬆）的中英對照，但那是 taxonomy 的屬性定義，catalog 沒有對應欄位可以篩。
→ 這四個欄位只能進 `retrieval_text` 或解釋文字。**絕對不要試著塞進 `required_values`**（`contracts.py:95-97`）——那是永不放寬的硬約束，塞進去就是直接歸零且無法救回。

### 8.7 `inferred_fields` 每輪重寫，導致 slot 硬度在輪與輪之間跳動 —— 機率：中

見 §3 坑 1。第 2 輪如果模型忘了把 `season` 重新列進 `inferred_fields`，同一個「秋冬」就從軟訊號變成硬過濾，候選池可能突然塌掉。
→ **Adapter 應該自己記住「這個 slot 曾經被標為 inferred」，取聯集而不是每輪重讀。**

### 8.8 session_id 在 ENGINE 01 重啟後靜默換人 —— 機率：中（demo 現場改 code 重啟就會中）

`session_store.py:35-42`：帶了查不到的 `session_id` 不會噴錯，直接開一個新的空 session，`round` 從 0 重數。我們這邊如果拿 `round` 對 `choice_history` 或 `design_adjust_steps` 做索引，會對到錯的輪次。
→ **Adapter 應該以「`round` 變小」作為 session 重置的偵測訊號**，並清掉我們自己的 feedback 累積。

### 8.9 ENGINE 01 裸 500 / 90 秒 timeout —— 機率：中低，但一旦發生就是全線停擺

見 §7 表格。所有 LLM 失敗都是無 body 的 500。
→ **Adapter 需要一條「ENGINE 01 掛掉」的降級路徑**：直接拿使用者原句當 `utterances` + `retrieval_text`、所有 slot 留 `UNMENTIONED`，走純 dense 檢索。我們有這個能力，不該因為 ENGINE 01 掛掉就整場空白。

### 8.10 `gender` 永遠是空的 —— 機率：必定，但後果溫和

`Intent` 沒這個欄位。gender 不篩 → 男女混排。不會 4xx，也不會空手。
→ 若要處理，只能從 `UserProfile` 或另外問一題澄清題拿。

### 8.11 真正會 4xx 的只有一種

`Engine02Request`（`contracts.py:182-220`）對 ENGINE 01 送來的東西已經很寬容：`Slot._accept_shorthand`（`contracts.py:44-60`）接受 `"top"`、`["top"]` 和完整 dict 三種寫法，`_accept_needs_mapping` 接受 dict 形式的 needs。
剩下唯一的 422 風險是 **`session_id` 缺漏**（`contracts.py:184`，唯一沒有預設值的欄位）。ENGINE 01 一定會給，除非 adapter 在 ENGINE 01 500 的降級路徑上忘了自己生一個。

---

## 給 adapter 的最小待辦清單

1. 丟掉 `budget_min`/`budget_max`（§6）。
2. 補 `occasion` 中→英表（含「上班/正式場合」→`Formal`、「休閒/約會」→`Casual`、「登山」→`Sports`）（§8.1）。
3. 補 `season` 中→英表，並處理「秋冬」這類跨季拆成多值（§8.1）。
4. `colors` 轉換前先剝結尾的「色」再查 `COLOR_ZH`；`深藍色`→`Navy Blue`（§8.3）。
5. `item_type` 走 `resolve_category_values`（已可用），但對 `outerwear`/`dress` 這種小池子要有預期（§8.4）。
6. `material`/`fit`/`pattern`/`collar`/`style_keywords`/`notes` 只進 `retrieval_text`，且 `retrieval_text_normalized=false`（§8.5、8.6）。
7. `inferred_fields` → `SlotState.INFERRED`，並且**跨輪取聯集**（§3、§8.7）。
8. `gender` 永遠 `UNMENTIONED`（§8.10）。
9. `round` 變小 ⇒ 視為 session 重置（§8.8）。
10. ENGINE 01 500／timeout ⇒ 降級成純 dense（§8.9）。

### 對照現有的 `engine02/intent_adapter.py`（工作目錄中未提交的版本）

寫報告時發現這個 adapter 已經存在，上面 10 點大多已經做到：`ZH_OCCASION`/`ZH_SEASON`/`ZH_GENDER` 表已建（L32-54）、budget 被明確丟棄並寫進 `input_warnings`（L229-234）、`inferred_fields` → `SlotState.INFERRED`（L154-157）、顏色用「最長中文色詞子字串」比對（L177-184）所以 `深藍色`/`深灰色` 都能過。實測確認：

```
深藍色 -> blue -> Blue      深灰色 -> grey -> Grey       ✓
```

**但有兩個還沒補的缺口**（實測）：

- **跨季被吃掉一半**：`_zh_lookup` 是「最長 key 優先的子字串比對」，`'秋冬' -> Fall`、`'春夏' -> Spring`，Winter/Summer 整個消失。ENGINE 01 的 test_cases.json:69 就是 `"season": "秋冬"`。→ `_zh_lookup` 對 season 應該回傳**多值**。
- **修飾色被降級成基本色**：`深藍色` 走 `FAMILY_CANONICAL["blue"]` → `"Blue"`，而 KAGL 有 195 件 `Navy Blue` 被排除在外。→ 修飾色應該展開成同族多值（`Blue` + `Navy Blue`），不是塌到族長。

---

## 我無法核實的部分

以下是推論或未經執行驗證，不要當成事實：

- **模型實際輸出從未被我看到。** 我沒有 `codex` 登入、也沒有跑 `test_accuracy.py`（跑一次會打 10 次 `codex exec`、約 2-3 分鐘並消耗共用額度，`README.md:93` 明講「沒事不要重複跑」）。§1 的值域、§7 的範例 payload 全部是從 **prompt 文字 ＋ 人工標註的期望值 ＋ strict schema** 推出來的，不是觀測到的模型輸出。真實輸出可能與期望標註不同（`test_accuracy.py:50-57` 那段印 `[MISS]` 的程式碼本身就承認會不同）。
- **實際 slot-filling 準確率不明。** `docs/engine01-intent.md:83` 把「實際跑一次拿到數字」列為第 1 順位待辦，代表**這個數字目前不存在**。所以「它有多常填錯欄位（例如把顏色塞進 `style_keywords`）」我只能從 test_cases.json 的標註習慣推測。
- **多輪的實際合併行為。** 「第 2 輪會不會把第 1 輪的值弄丟」我是從「模型整包重寫 ＋ 程式端零保護」推論的（prompts.py:16 規則 4 有要求不要覆蓋，但沒有程式強制）。沒有多輪的測試案例可以驗證。
- **`inferred_fields` 是否真的只放合法欄位名。** prompt 有要求，但沒有任何驗證。也可能出現 `"colors"` 以外的怪字串。
- **`clarifying_questions` 的觸發頻率與 `options[].id` 的實際命名。** `interface-contract.md:66-70` 的英文 slug 是人手寫的文件範例，不是模型輸出。
- **`Intent` 的中文用詞是否穩定。** 「正式場合」vs「正式」、「夏天」vs「夏季」這類同義變體，我只有 10 個標註樣本，涵蓋不足以斷言。中文對映表應該做成**寬鬆前綴／同義詞比對**，不要做字典完全相等。
- **`notes` 欄位從未在任何測試資料或文件範例中出現非 null 值**，我不知道模型會往裡面寫什麼。
