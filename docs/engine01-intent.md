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

**已用真實 Google 帳號完整測過一輪**（不是只測 bypass）：[`scripts/engine01-test-page/`](../scripts/engine01-test-page/) 這個非正式測試頁，載入 Google Identity Services 的官方按鈕，登入成功後把 `credential` 丟給 `POST /auth/google`，正確拿回 `session_token`＋`profile`，後續 `/intent` 呼叫帶著 `Authorization: Bearer` header 也正常運作。也能在同一個 session 裡點澄清問題的選項卡片，正確累加進同一組意圖。

**開發方便用**：`.env` 裡 `DEV_BYPASS_AUTH=true` 時，`get_current_user()` 直接回傳一個固定的本機測試使用者，不用每次真的跑 Google 登入流程也能測 `/intent`／`/profile`。預設關閉，**demo 現場絕對不能開著**。

## 登入後的偏好調查（必填，2026-09-19 起不能再略過）

登入後要做一次身家調查：`age_range`（區間，例如 `18-24`／`25-34`／`35-44`／`45+`）、`style_preferences`（複選，例如日系／韓系／美式／歐美／街頭／簡約／正式／其他）、`gender`／`contexts`（2026-09-19 新增，對齊實際蓋出來的前端 onboarding 畫面多出的兩題）。走 `GET /profile`、`PUT /profile`（partial update，見 `UserProfile`／`ProfileUpdate`，[interface-contract.md](interface-contract.md)）。**這條路徑 2026-09-19 起前端已經真的接上**（不再是 localStorage mock），見 [frontend.md](frontend.md)。

**2026-09-19 修正：這份調查改成註冊時必填，不能再略過**（原本設計是可以跳過、之後才補——這條規則已經取消）。前端 `onboarding-experience.tsx` 拿掉了原本的「Skip」按鈕，三步都要選完才能繼續。後端 `PUT /profile` 也加了對應驗證：套用完這次更新後，如果 `onboarding_completed` 會變成 `true`，但 `age_range`／`gender`／`style_preferences`／`contexts` 任一個是空的，會回 400——防止有人繞過前端直接打 API 把 onboarding 標記完成卻沒填資料。

這份偏好資料還沒接進 ENGINE01 的抽取 prompt，但**2026-09-19 起 `gender`／`style_preferences` 已經接進 `POST /recommend` 送給 ENGINE02 的 payload**（見「兩分區推薦」一節）：`gender` 一律送出、`style_keywords` 這輪是空的時候退回 `style_preferences` 當備援；`age_range`／`contexts` 目前沒有對應的 ENGINE02 掛勾，還沒接。

## 輸入

- 使用者的一句話，文字或語音。
  - **語音輸入用瀏覽器原生的 Web Speech API（`SpeechRecognition`），不用 Whisper API。** 完全在前端把語音轉成文字，不用後端、不用 API key、免費——跟團隊「不想花錢」的方向一致，也比另外接一個 Whisper 依賴單純。`/intent` 端點完全不用管輸入是打字還是講話轉出來的，反正打進來的都是同一個 `message` 欄位。這是前端負責人的工作範圍，不動 `backend/engine01_intent/`。
- 選填的參考圖（`IntentRequest.reference_image_url`）。**2026-09-19 起已實作完整的 fallback 邏輯**：使用者這輪有上傳（`POST /uploads/image` 拿到的網址）就用使用者的；沒上傳就呼叫 `backend/pinterest/client.py` 去比對團隊策展的 Pinterest 板子，比對到就用；兩者都沒有就不帶參考圖繼續跑，不擋主流程。解析出來的參考圖只存在 ENGINE01 內部的 session 狀態（`session_store.SessionState.reference_image_url`），刻意不透過 `IntentResponse` 回傳給前端——細節跟版權規則見 [pinterest-and-generation.md](pinterest-and-generation.md)。
- 這個 session 目前累積的 `Intent`（來自 `session_store.py`）——每次呼叫都是「併入」，不是每次從零抽取。

## 輸出

- 更新後的 `Intent`（見 [interface-contract.md](interface-contract.md)）——模型改動或推斷出來的每個欄位，都用 `inferred_fields` 標出哪些是 GPT 自己填的，不是使用者原話。這個切分正是「可解釋」要求的具體機制：意圖面板裡沒有任何欄位會被包裝成使用者自己講的，除非真的是。
- `clarifying_questions`——只要核心欄位還缺，就出選擇題（每題都附自由輸入的備援選項）。每一輪都用同一套格式，不只是第一輪。**2026-09-19 新增決定性把關**：核心欄位是 `item_type`（`outfit_requested=true` 時不算缺）／`colors`／`occasion`／`material`／`season`／`style_keywords`，`backend/engine01_intent/gating.py` 會過濾 LLM 吐出的問題，只保留核心欄位、同一欄位不重複問、整個 session 累計不超過 5 題；`budget_min`／`budget_max`／`fit`／`pattern`／`collar` 不主動問。

## 情境推斷

使用者沒提到的欄位（天氣、季節、情境暗示的場合等）由 GPT 自己合理推斷，明確標進 `inferred_fields`，前端要用視覺上明顯不同的樣式呈現，跟使用者親口說的欄位分開。這直接回應簡報裡「AI 像黑盒子」的抱怨——任何一個推斷欄位都要能追溯到「系統是這樣猜的，理由是這樣」，不能悄悄混進使用者自己的陳述裡。

## 使用者怎麼跟 AI 對話

現有的 FastAPI `POST /intent` ＋ `session_store.py`（使用者發一句話、後端存狀態、回傳更新後意圖）本身就是完整的對話迴圈了，前端只要重複呼叫這個端點就是在「跟 AI 對話」。

**2026-09-19 更新，這段先前的結論已經被團隊決議取代**：先前這裡寫「不需要 Hermes Agent，`codex exec` 已經是刻意的成本決策」，但團隊在 2026-09-18 正式決議整個專案要以 Hermes Agent 應用的形式建置與交付（見根目錄 `docs/migration-to-hermes-app.md`，PRD 第 7 章）。`backend/engine01_intent/` 這裡的程式碼結構（含這份文件描述的 `POST /intent`／`codex exec` 呼叫方式）已經被複製一份到 `bff/`（Hermes app 的 runtime 層），且遷移計畫第 2 階段（`bff/` 內嵌 Hermes Agent、取代這裡的 `llm_client.py` 自己接 `codex exec`）標記「待做」——代表 `codex exec` 這個機制**遲早會被拿掉換成內嵌的 Hermes Agent**，不是永久架構。`backend/` 這邊的程式碼目前繼續維持原狀開發（遷移文件明講「分支作者照常開發，不需要 rebase」），只是要知道這不是終局狀態。正式 demo 會從 `integration/hermes-app` 分支跑，不是從 `main` 或這條分支直接跑。

## 兩分區推薦（`POST /recommend`，2026-09-19 新增）

補上 ENGINE01 之前完全沒有程式碼呼叫 ENGINE02 的缺口，同時把商品／生成圖組成固定「上衣／下身」兩分區（每區最多 6 件）展示邏輯。詳細規格見 [interface-contract.md](interface-contract.md) 第 6 節；實作分散在 `backend/engine01_intent/` 的 `zones.py`（兩分區對照）、`engine02_client.py`（呼叫 ENGINE02 的 `POST /intent/rank`／`POST /visual-search`）、`query_text.py`（組 `visual_search` 要的查詢文字）、`recommend.py`（orchestration）。前端預期在核心欄位問完（`clarifying_questions` 變空）之後才呼叫這支，後端不強制擋。

## 實作

- FastAPI service，`POST /intent`、`POST /recommend`、`POST /auth/google`、`GET /profile`、`PUT /profile`、`POST /uploads/image`（見 [`backend/engine01_intent/main.py`](../backend/engine01_intent/main.py)）。
- 結構化輸出用 `codex exec --output-schema`（shell 出去呼叫 OpenAI 的 Codex CLI 子行程），吃開發者自己的 ChatGPT Plus/Pro 訂閱額度，不用另外付費的 `OPENAI_API_KEY`——這是實際測過之後的刻意成本決策，跟一開始的計畫不一樣。測出來的延遲／額度代價（每次呼叫約 8–17 秒、約消耗團隊共用 Codex 額度 14–20K token）以及萬一要換回去該怎麼做，見根目錄 [CLAUDE.md](../CLAUDE.md) 的「ENGINE01 執行方式：codex exec」。丟給 Codex 的 JSON schema 是直接從 `IntentExtraction` 這個 Pydantic model（`intent` ＋ `clarifying_questions`）產生的，再經過後製處理來符合 OpenAI strict mode 的要求（每一層都要有 `additionalProperties: false`、所有欄位都列進 required）——因為 Pydantic 預設不會自動加這些，細節見 `llm_client.py` 裡的 `_to_strict_schema()`。
- 多輪對話狀態：一個記憶體內的 `dict[(user_id, session_id), SessionState]`（見 `session_store.py`），存目前累積的 `Intent`。因為必須登入，key 用 `(user_id, session_id)`，`user_id` 從 `get_current_user()` 拿，`session_id` 沿用「沒給就開新的」的邏輯——一個登入使用者理論上可以同時開好幾個對話串。每次呼叫都把現有意圖加上新句子一起丟給模型，請它回傳完整的更新後意圖——比另外導入一套對話狀態框架簡單，適合兩天的開發時程。
- 身分／偏好：`backend/shared/user_store.py`，per-user 的 JSON 檔案（`data/users/<sub>.json`，已被 `.gitignore` 排除），不用資料庫——跟原始規劃文件「存儲：JSON 優先、真的需要再用資料庫」的方向一致，對話中的 session 狀態則維持存在記憶體裡就好（demo 中途重啟本來就是個問題，落不落地存都一樣，沒必要為此加資料庫）。

## 離線驗證（這個引擎自己的量化數字）

`backend/engine01_intent/tests/`——一組人工標註的測試句，附上期望的結構化意圖，用「期望欄位填對的比例」打分（`test_accuracy.py`）。目前隨附 10 句起始集，正式在簡報／README 引用準確率數字前，要擴充到 30–50 句，見 [validation-plan.md](validation-plan.md)。這組測試腳本目前是直接呼叫 `extract_intent()`，跟登入無關，不受這次加的 auth 影響。

## 依賴

- `codex` CLI 要先裝好，並且用 `codex login` 登入過一次——`/intent` 的模型呼叫不需要 `OPENAI_API_KEY`。見根目錄 `CLAUDE.md` 的「ENGINE01 執行方式：codex exec」。
- `GOOGLE_CLIENT_ID`、`SESSION_SECRET`——登入需要，見根目錄 `CLAUDE.md` 的「Google OAuth Client ID」。開發階段可以先用 `DEV_BYPASS_AUTH=true` 跳過。
- `CORS_ALLOWED_ORIGINS`——瀏覽器前端（不管是正式前端還是測試頁）要能呼叫這幾個端點，來源網址必須在這個清單裡，預設同時開 `http://localhost:5173`（`scripts/engine01-test-page/`）跟 `http://localhost:3000`（實際前端 IntentWeave 是 Next.js，預設 port 是 3000，不是原規劃的 Vite）；有其他 port 或部署網址要另外加，見 `.env.example`。
- `PINTEREST_ACCESS_TOKEN`／`PINTEREST_BOARD_NAME`——參考圖 fallback 用（見上面「輸入」一節），沒設定時 `backend/pinterest/client.py` 會直接回傳沒有參考圖，不影響 `/intent` 主流程。`PINTEREST_BOARD_NAME` 要填 Pinterest 上的顯示名稱（例如「IntentWeave References」），不是網址 slug——2026-09-19 真實 API 驗證時踩過這個坑，見 git log。
- `ENGINE02_BASE_URL`——`POST /recommend` 呼叫 ENGINE02 用，預設 `http://localhost:8000`。本機啟動 ENGINE02：`ENGINE02_DEMO=1 ENGINE02_PUBLIC_BASE=http://localhost:8000 uvicorn mcp_servers.catalog.main:app --port 8000`（見 ENGINE02 負責人交接文件；`mcp_servers/catalog/` 是 Hermes app 遷移後的路徑，內容跟原本的 `backend/engine02_retrieval/` 目前逐位元組相同）。
- `backend/shared/schemas.py`——這個模組產出跟消費的 `Intent`、`ClarifyingQuestion`、`IntentRequest`、`IntentResponse`、`UserProfile`、`ProfileUpdate`、`GoogleAuthRequest`、`AuthResponse`、`ZoneSlate`、`ZonedRecommendationResult`、`RecommendRequest` 都定義在這裡。

## 目前進度與待辦事項

**已完成**：
- `POST /intent` 核心邏輯（結構化抽取、情境推斷、澄清問題、多輪狀態）。
- Google 登入全流程（後端邏輯＋真實帳號端到端測過，非僅 bypass）、`GET`/`PUT /profile` 偏好調查。
- `.env` 自動載入、CORS 設定（原本這兩個是漏掉的，靠 VS Code 提示才抓到，見 git log）。
- 離線測試骨架，目前 10 句起始集。
- [`scripts/engine01-test-page/`](../scripts/engine01-test-page/)——已經正式收進 repo 的測試頁，任何人 clone 下來都能用它驗證 ENGINE01（含真實 Google 登入）。
- **圖片上傳＋Pinterest 參考圖 fallback**（2026-09-19）：`POST /uploads/image`、`backend/pinterest/client.py`，接進 `/intent` 的解析邏輯，見上面「輸入」一節。單元測試見 `backend/pinterest/tests/test_client.py`；**已對真實 Pinterest API／真實板子驗證過**，過程中修掉兩個真的 bug（板名比對、中英文關鍵字不通），見 git log。
- **前端登入／onboarding 真的接上，且改成必填**（2026-09-19）：main 上新合併的前端（IntentWeave，Next.js）原本這兩塊完全是 localStorage mock，這次改成真的呼叫 `POST /auth/google`／`PUT /profile`；onboarding 同時改成註冊時必填，拿掉了原本的 Skip 捷徑（前後端都有擋）。已用假 session（跳過真實 Google 登入）端到端驗證過；**真正點擊 Google 按鈕、用真實帳號登入這一步還沒有人做過**（見下面待辦 1）。
- **ENGINE01→ENGINE02 整合呼叫＋兩分區推薦**（2026-09-19）：`POST /recommend`，見上面「兩分區推薦」一節跟 [interface-contract.md](interface-contract.md) 第 6 節。全部用 mock 測過（37 個 pytest），也對 ENGINE01 這端做過真實 smoke test（gating／outfit_requested／404／優雅降級都驗證過）；**還沒對真的 ENGINE02（含真實商品庫）做過端到端測試**，這台開發機沒有 `data/catalog/...` 資料檔。
- **核心欄位把關**（2026-09-19）：`backend/engine01_intent/gating.py`，見上面「輸出」一節。8 個 pytest，也用真實 `codex exec` 呼叫驗證過（單品／套裝兩種情境，出來的澄清問題數量跟欄位都符合預期）。

**還沒做，依優先度大致排序**：
1. **用真實 Google 帳號完整跑一次新前端的登入流程**：需要先把 `http://localhost:3000` 加進 Google Cloud Console 的 Authorized JavaScript origins（`.env` 的 `GOOGLE_CLIENT_ID` 不用換，跟 `frontend/.env.local` 的 `NEXT_PUBLIC_GOOGLE_CLIENT_ID` 已經對齊），這步是使用者帳號層級的操作，agent 沒辦法代為完成，也不會代為輸入 Google 帳密。
2. **測試句擴充到 30–50 句**，實際跑一次 `test_accuracy.py` 拿到真正的準確率數字，放進簡報／README。
3. **介面契約要跟 ENGINE02/03/前端的負責人對過**——`backend/shared/schemas.py` 目前是 ENGINE01 單方面先寫的 draft v1，欄位名稱／型別都可能要改，2026-09-19 新增的規格草案（生圖獨立觸發、每張卡片回饋、收藏小屋、兩分區推薦的欄位命名）都還沒定案，見 [interface-contract.md](interface-contract.md) 第 6、7 節。
4. **對真的 ENGINE02（含真實商品庫）做一次 `/recommend` 端到端測試**——這台機器沒有 `data/catalog/...`，要先跟 ENGINE02 負責人要資料或跑資料準備腳本。
5. 語音輸入（前端的 Web Speech API）——這塊 ENGINE01 這邊不擋，還沒有人接上。
6. `/complete-look` ＋ `engine02/outfit_budget.py` 的預算感知套裝規劃，比現在兩分區各自代表性品項各查一次更貼近真實需求，值得換過去（見 [interface-contract.md](interface-contract.md) 第 6 節）。
7. 分支 `engine01-intent` 還沒讓其他組員 checkout 確認過整體架構，也還沒開 PR 併回 `main`（見根目錄 `CLAUDE.md` 的「Git 工作流程」）。
