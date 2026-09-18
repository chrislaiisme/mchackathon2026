# ENGINE01 — 需求理解

負責人：這條線的擁有者（見根目錄 `CLAUDE.md` 的「負責人對照」）。程式碼：[`backend/engine01_intent/`](../backend/engine01_intent/)。

## 目標

把一句話（文字，可選配一張參考圖）轉成結構化、可解釋的意圖——這是其他每個引擎都要吃的輸入。依簡報的說法，門檻是「抽得準＋接得住模糊」，不是照抄使用者的字面。

## 登入（必須登入才能用）

用 Google OAuth，且是硬性要求——沒登入不能打 `/intent`。走「前端 Google 按鈕拿 ID token，後端驗證」這條最簡路線，不用完整 server-side OAuth redirect：

1. 前端用 Google Identity Services 的 Sign-In 按鈕，登入成功拿到一個已簽章的 `credential`（JWT）。
2. 前端 POST 給 `POST /auth/google`（見 [`backend/engine01_intent/main.py`](../backend/engine01_intent/main.py)）。
3. 後端用官方 `google-auth` 套件（`google.oauth2.id_token.verify_oauth2_token`）驗證簽章／audience（`GOOGLE_CLIENT_ID`）／有效期，拿到 `sub`（Google 帳號 ID，當主鍵）、`email`、`name`、`picture`。
4. 用 `sub` 去 `backend/shared/user_store.py` 找或建立使用者的 JSON 檔案（`data/users/<sub>.json`）。
5. 後端自己簽一個 7 天效期的 session token（`backend/shared/auth.py` 的 `create_session_token`，HMAC 簽章，簽章 key 是 `.env` 的 `SESSION_SECRET`，不用另外裝 JWT 套件），連同 `profile` 一起回傳。
6. 前端把 token 存起來，之後每個 API 呼叫都帶 `Authorization: Bearer <token>`。
7. `get_current_user()`（`backend/shared/auth.py`）是掛在 `/intent`、`/profile` 上的 FastAPI dependency，驗證 token、解出使用者；沒有合法 token 一律 401。

不需要 client secret、不需要 server-side redirect callback，因為全程只驗證前端拿到的 ID token。Google Cloud Console 那邊要建什麼、怎麼建，見根目錄 [CLAUDE.md](../CLAUDE.md) 的「Google OAuth Client ID」。

**已用真實 Google 帳號完整測過一輪**（不是只測 bypass）：一個放在本機暫存資料夾（不在 repo 裡）的測試頁，載入 Google Identity Services 的官方按鈕，登入成功後把 `credential` 丟給 `POST /auth/google`，正確拿回 `session_token`＋`profile`，後續 `/intent` 呼叫帶著 `Authorization: Bearer` header 也正常運作。這個測試頁目前還沒決定要不要正式收進 repo（見下面「目前進度與待辦事項」）。

**開發方便用**：`.env` 裡 `DEV_BYPASS_AUTH=true` 時，`get_current_user()` 直接回傳一個固定的本機測試使用者，不用每次真的跑 Google 登入流程也能測 `/intent`／`/profile`。預設關閉，**demo 現場絕對不能開著**。

## 登入後的偏好調查（可略過）

登入後可以做一次身家調查：`age_range`（區間，例如 `18-24`／`25-34`／`35-44`／`45+`）、`style_preferences`（複選，例如日系／韓系／美式／歐美／街頭／簡約／正式／其他）。走 `GET /profile`、`PUT /profile`（partial update，見 `UserProfile`／`ProfileUpdate`，[interface-contract.md](interface-contract.md)）。

完全不擋主流程——登入完就能直接開始對話，填不填、什麼時候填都不影響能不能用 `/intent`。畫面上可以放一個小小的「略過」按鈕（例如卡片右下角），按下去直接呼叫 `PUT /profile` 帶空的 `age_range`／`style_preferences`、標記 `onboarding_completed: true`，不用真的填完表單——這是前端負責人的實作細節，後端這邊只要保證空值也能正常存就好。

這份偏好資料目前只是存起來，還沒接進 ENGINE01 的抽取 prompt（那是要跟 ENGINE02/03 討論怎麼用個人化訊號的加分項，這次先把資料落地，介接邏輯留到後面）。

## 輸入

- 使用者的一句話，文字或語音。
  - **語音輸入用瀏覽器原生的 Web Speech API（`SpeechRecognition`），不用 Whisper API。** 完全在前端把語音轉成文字，不用後端、不用 API key、免費——跟團隊「不想花錢」的方向一致，也比另外接一個 Whisper 依賴單純。`/intent` 端點完全不用管輸入是打字還是講話轉出來的，反正打進來的都是同一個 `message` 欄位。這是前端負責人的工作範圍，不動 `backend/engine01_intent/`。
- 選填的參考圖（`IntentRequest.reference_image_url`）。沒附圖時，理論上可以退而求其次去團隊策展的 Pinterest 板子拉一張相近的圖當輔助情境，但那條線（`backend/pinterest/`，品諭負責board策展，目前進度未知）還沒做出查詢介面，這次先不等它——沒收到 `reference_image_url` 就直接不用參考圖繼續跑，等 Pinterest 那邊有介面了再接。
- 這個 session 目前累積的 `Intent`（來自 `session_store.py`）——每次呼叫都是「併入」，不是每次從零抽取。

## 輸出

- 更新後的 `Intent`（見 [interface-contract.md](interface-contract.md)）——模型改動或推斷出來的每個欄位，都用 `inferred_fields` 標出哪些是 GPT 自己填的，不是使用者原話。這個切分正是「可解釋」要求的具體機制：意圖面板裡沒有任何欄位會被包裝成使用者自己講的，除非真的是。
- `clarifying_questions`——只要意圖還太模糊、搜不出好結果，就出 1–3 題選擇題（每題都附自由輸入的備援選項）。每一輪都用同一套格式，不只是第一輪。

## 情境推斷

使用者沒提到的欄位（天氣、季節、情境暗示的場合等）由 GPT 自己合理推斷，明確標進 `inferred_fields`，前端要用視覺上明顯不同的樣式呈現，跟使用者親口說的欄位分開。這直接回應簡報裡「AI 像黑盒子」的抱怨——任何一個推斷欄位都要能追溯到「系統是這樣猜的，理由是這樣」，不能悄悄混進使用者自己的陳述裡。

## 使用者怎麼跟 AI 對話（不需要 Hermes Agent）

現有的 FastAPI `POST /intent` ＋ `session_store.py`（使用者發一句話、後端存狀態、回傳更新後意圖）本身就是完整的對話迴圈了，前端只要重複呼叫這個端點就是在「跟 AI 對話」。Hermes Agent 在這個專案裡的角色已經定案——只是 ENGINE01 呼叫模型的後端機制（`codex exec`），不是使用者面對的對話框架，不需要再疊一層 Hermes Agent 上去當 webapp 的對話引擎。

## 實作

- FastAPI service，`POST /intent`、`POST /auth/google`、`GET /profile`、`PUT /profile`（見 [`backend/engine01_intent/main.py`](../backend/engine01_intent/main.py)）。
- 結構化輸出用 `codex exec --output-schema`（shell 出去呼叫 OpenAI 的 Codex CLI 子行程），吃開發者自己的 ChatGPT Plus/Pro 訂閱額度，不用另外付費的 `OPENAI_API_KEY`——這是實際測過之後的刻意成本決策，跟一開始的計畫不一樣。測出來的延遲／額度代價（每次呼叫約 8–17 秒、約消耗團隊共用 Codex 額度 14–20K token）以及萬一要換回去該怎麼做，見根目錄 [CLAUDE.md](../CLAUDE.md) 的「ENGINE01 執行方式：codex exec」。丟給 Codex 的 JSON schema 是直接從 `IntentExtraction` 這個 Pydantic model（`intent` ＋ `clarifying_questions`）產生的，再經過後製處理來符合 OpenAI strict mode 的要求（每一層都要有 `additionalProperties: false`、所有欄位都列進 required）——因為 Pydantic 預設不會自動加這些，細節見 `llm_client.py` 裡的 `_to_strict_schema()`。
- 多輪對話狀態：一個記憶體內的 `dict[(user_id, session_id), SessionState]`（見 `session_store.py`），存目前累積的 `Intent`。因為必須登入，key 用 `(user_id, session_id)`，`user_id` 從 `get_current_user()` 拿，`session_id` 沿用「沒給就開新的」的邏輯——一個登入使用者理論上可以同時開好幾個對話串。每次呼叫都把現有意圖加上新句子一起丟給模型，請它回傳完整的更新後意圖——比另外導入一套對話狀態框架簡單，適合兩天的開發時程。
- 身分／偏好：`backend/shared/user_store.py`，per-user 的 JSON 檔案（`data/users/<sub>.json`，已被 `.gitignore` 排除），不用資料庫——跟原始規劃文件「存儲：JSON 優先、真的需要再用資料庫」的方向一致，對話中的 session 狀態則維持存在記憶體裡就好（demo 中途重啟本來就是個問題，落不落地存都一樣，沒必要為此加資料庫）。

## 離線驗證（這個引擎自己的量化數字）

`backend/engine01_intent/tests/`——一組人工標註的測試句，附上期望的結構化意圖，用「期望欄位填對的比例」打分（`test_accuracy.py`）。目前隨附 10 句起始集，正式在簡報／README 引用準確率數字前，要擴充到 30–50 句，見 [validation-plan.md](validation-plan.md)。這組測試腳本目前是直接呼叫 `extract_intent()`，跟登入無關，不受這次加的 auth 影響。

## 依賴

- `codex` CLI 要先裝好，並且用 `codex login` 登入過一次——`/intent` 的模型呼叫不需要 `OPENAI_API_KEY`。見根目錄 `CLAUDE.md` 的「ENGINE01 執行方式：codex exec」。
- `GOOGLE_CLIENT_ID`、`SESSION_SECRET`——登入需要，見根目錄 `CLAUDE.md` 的「Google OAuth Client ID」。開發階段可以先用 `DEV_BYPASS_AUTH=true` 跳過。
- `CORS_ALLOWED_ORIGINS`——瀏覽器前端（不管是正式前端還是測試頁）要能呼叫這幾個端點，來源網址必須在這個清單裡，預設只開 `http://localhost:5173`；有其他 port 或部署網址要另外加，見 `.env.example`。
- `backend/shared/schemas.py`——這個模組產出跟消費的 `Intent`、`ClarifyingQuestion`、`IntentRequest`、`IntentResponse`、`UserProfile`、`ProfileUpdate`、`GoogleAuthRequest`、`AuthResponse` 都定義在這裡。

## 目前進度與待辦事項

**已完成**：
- `POST /intent` 核心邏輯（結構化抽取、情境推斷、澄清問題、多輪狀態）。
- Google 登入全流程（後端邏輯＋真實帳號端到端測過，非僅 bypass）、`GET`/`PUT /profile` 偏好調查。
- `.env` 自動載入、CORS 設定（原本這兩個是漏掉的，靠 VS Code 提示才抓到，見 git log）。
- 離線測試骨架，目前 10 句起始集。

**還沒做，依優先度大致排序**：
1. **測試句擴充到 30–50 句**，實際跑一次 `test_accuracy.py` 拿到真正的準確率數字，放進簡報／README。
2. **介面契約要跟 ENGINE02/03/前端的負責人對過**——`backend/shared/schemas.py` 目前是 ENGINE01 單方面先寫的 draft v1，欄位名稱／型別都可能要改。
3. **圖片上傳功能**：讓使用者能傳一張參考圖，不是只能塞網址進 `reference_image_url`。已經決定存放方式——存本機 `data/uploads/`（跟 `data/users/` 一樣，不進資料庫、已被 `.gitignore` 排除），回傳一個本機可讀的網址；還沒設計實際的上傳端點（檔案大小限制、接受的格式等）跟實作。
4. 偏好調查資料（年齡／風格）還沒接進意圖抽取的 prompt，要跟 ENGINE02/03 討論個人化訊號怎麼用。
5. 語音輸入（前端的 Web Speech API）、Pinterest 參考圖 fallback（等 `backend/pinterest/` 查詢介面）——這兩塊 ENGINE01 這邊已經留好介面，不擋自己的進度，只是還沒有別人接上。
6. 分支 `engine01-intent` 還沒讓其他組員 checkout 確認過整體架構，也還沒開 PR 併回 `main`（見根目錄 `CLAUDE.md` 的「Git 工作流程」）。
