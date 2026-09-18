# ENGINE01 — 需求理解

負責人：這條線的擁有者（見根目錄 `CLAUDE.md` 的「負責人對照」）。程式碼：[`backend/engine01_intent/`](../backend/engine01_intent/)。

## 目標

把一句話（文字，可選配一張參考圖）轉成結構化、可解釋的意圖——這是其他每個引擎都要吃的輸入。依簡報的說法，門檻是「抽得準＋接得住模糊」，不是照抄使用者的字面。

## 輸入

- 使用者的一句話，文字或語音（語音需要先過一道語音轉文字，例如 Whisper API——非必要，沒時間就退回純文字）。
- 選填的參考圖。沒附圖時，系統可以退而求其次，從團隊策展的 Pinterest 板子拉一張相近的圖當輔助情境（由 `backend/pinterest/` 負責，不是這個模組的事）。
- 這個 session 目前累積的 `Intent`（來自 `session_store.py`）——每次呼叫都是「併入」，不是每次從零抽取。

## 輸出

- 更新後的 `Intent`（見 [interface-contract.md](interface-contract.md)）——模型改動或推斷出來的每個欄位，都用 `inferred_fields` 標出哪些是 GPT 自己填的，不是使用者原話。這個切分正是「可解釋」要求的具體機制：意圖面板裡沒有任何欄位會被包裝成使用者自己講的，除非真的是。
- `clarifying_questions`——只要意圖還太模糊、搜不出好結果，就出 1–3 題選擇題（每題都附自由輸入的備援選項）。每一輪都用同一套格式，不只是第一輪。

## 情境推斷

使用者沒提到的欄位（天氣、季節、情境暗示的場合等）由 GPT 自己合理推斷，明確標進 `inferred_fields`，前端要用視覺上明顯不同的樣式呈現，跟使用者親口說的欄位分開。這直接回應簡報裡「AI 像黑盒子」的抱怨——任何一個推斷欄位都要能追溯到「系統是這樣猜的，理由是這樣」，不能悄悄混進使用者自己的陳述裡。

## 實作

- FastAPI service，`POST /intent`（見 [`backend/engine01_intent/main.py`](../backend/engine01_intent/main.py)）。
- 結構化輸出用 `codex exec --output-schema`（shell 出去呼叫 OpenAI 的 Codex CLI 子行程），吃開發者自己的 ChatGPT Plus/Pro 訂閱額度，不用另外付費的 `OPENAI_API_KEY`——這是實際測過之後的刻意成本決策，跟一開始的計畫不一樣。測出來的延遲／額度代價（每次呼叫約 8–17 秒、約消耗團隊共用 Codex 額度 14–20K token）以及萬一要換回去該怎麼做，見根目錄 [CLAUDE.md](../CLAUDE.md) 的「ENGINE01 執行方式：codex exec」。丟給 Codex 的 JSON schema 是直接從 `IntentExtraction` 這個 Pydantic model（`intent` ＋ `clarifying_questions`）產生的，再經過後製處理來符合 OpenAI strict mode 的要求（每一層都要有 `additionalProperties: false`、所有欄位都列進 required）——因為 Pydantic 預設不會自動加這些，細節見 `llm_client.py` 裡的 `_to_strict_schema()`。
- 多輪對話狀態：一個單純的記憶體內 `dict[session_id, SessionState]`（見 `session_store.py`），存目前累積的 `Intent`。每次呼叫都把現有意圖加上新句子一起丟給模型，請它回傳完整的更新後意圖——比另外導入一套對話狀態框架簡單，適合兩天的開發時程。

## 離線驗證（這個引擎自己的量化數字）

`backend/engine01_intent/tests/`——一組人工標註的測試句，附上期望的結構化意圖，用「期望欄位填對的比例」打分（`test_accuracy.py`）。目前隨附 10 句起始集，正式在簡報／README 引用準確率數字前，要擴充到 30–50 句，見 [validation-plan.md](validation-plan.md)。

## 依賴

- `codex` CLI 要先裝好，並且用 `codex login` 登入過一次——這個模組不需要 `OPENAI_API_KEY`。見根目錄 `CLAUDE.md` 的「ENGINE01 執行方式：codex exec」。
- `backend/shared/schemas.py`——這個模組產出跟消費的 `Intent`、`ClarifyingQuestion`、`IntentRequest`、`IntentResponse` 都定義在這裡。
