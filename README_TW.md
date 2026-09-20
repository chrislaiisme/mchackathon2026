# Consumer Intent Agent（一句話讀懂消費者）

> 這是 [README.md](README.md) 的中文版。根目錄的 README.md 依競賽交付項目要求維持英文，這份是給團隊內部看的中文對照版，內容異動時兩邊都要同步更新。

**勢在必得**團隊為 **2026 梅竹黑客松 x 聚陽實業（Makalot Industrial）** 打造的 prototype，題目是「一句話讀懂消費者」。

Consumer Intent Agent 把消費者的一句話服飾需求，轉成結構化、可解釋的意圖，用 hybrid search ＋ reranker 檢索出符合的商品，同時生成一張原創概念圖跟檢索結果並排呈現，再依使用者回饋讓兩者跨輪次一起變準——而且這個「變準」要秀出量化、可驗證的分數，不是嘴上說有進步。

## 系統概觀

整套系統是兩個引擎加一個生成模組，後面接 FastAPI 後端、前端用 React：

- **ENGINE 01 — 需求理解**：一句話 → 結構化 JSON 意圖（品項、顏色、場合、預算、風格關鍵字），用 GPT structured output 實作。模糊或推斷出來的欄位會標成系統推斷（絕不悄悄用猜的當成使用者原話），意圖不夠明確時會出澄清選擇題。
- **ENGINE 02 — 檢索與排序**（已實作，`engine02/` ＋ `backend/engine02_retrieval/`）：在 KAGL 服飾商品庫上做 hybrid search（dense embedding ＋ 自己寫的 BM25），用一個逐項加總的分數重新排序——每一項的貢獻都會回傳、加起來剛好等於總分，這個分數分解本身就是解釋，不是另外生成的。完整設計與實驗見 [docs/engine02-design.md](docs/engine02-design.md)，怎麼跑見 [docs/engine02-pipeline.md](docs/engine02-pipeline.md)。
- **ENGINE 03 — 偏好回饋迴圈**（**已實作並前後端接通**，`backend/engine03_feedback/`）：純規則式（不吃 LLM）地把分項打分、收藏／不喜歡、整套喜歡轉成結構化的權重調整，觸發下一輪。ENGINE01 的 `POST /feedback` 透過 `engine03_client.py` 呼叫它，依 `source: "catalog"`（資料庫商品）或 `source: "generated"`（Design for Me 生成的概念圖，沒有商品 id、改用設計屬性）分流。前端統一從 `preferenceService` 自動送出這輪的收藏／不喜歡／打分／整套喜歡，使用者不用另外按「送出回饋」。細節見 [docs/engine03-feedback.md](docs/engine03-feedback.md)、[docs/status.md](docs/status.md)。
- **生成模組**：用 OpenAI Responses API 的 `image_generation` tool，每輪產一張原創概念圖跟檢索結果並排；這張圖會轉成向量併回 ENGINE 02 的 dense 分數，讓檢索和生成互相加強。
- **Pinterest 趨勢訊號**：團隊自己策展的 Pinterest 板子（Trial API access）餵進 ENGINE 02 的排序權重。

兩條迴圈共用同一套 ENGINE 01–03 程式碼：**live 流程**（真人使用者／評審在瀏覽器上互動）和一條**離線驗證迴圈**（開發階段用的模擬 LLM 使用者，帶著隱藏目標圖片人設，只用來產生量化準確度數字，不會出現在正式 demo 畫面）。詳見 [docs/system-architecture.svg](docs/system-architecture.svg) 和 [docs/validation-flow.svg](docs/validation-flow.svg)。

完整背景、評分標準、設計理由：[docs/hackathon-brief.md](docs/hackathon-brief.md)。給 AI coding agent 看的專案規格：[CLAUDE.md](CLAUDE.md)。

## Repo 結構

```
docs/               所有專案 markdown 文件與架構圖
backend/
  shared/            跨引擎共用的 Pydantic schema（介面契約）
  engine01_intent/   需求理解（FastAPI service）
  engine02_retrieval/  ENGINE02 較舊的 HTTP 介接層。2026-09-20 盤點發現內容已經跟
                       mcp_servers/catalog/（見下面）分岔——現場真正在跑的是
                       mcp_servers/catalog/，這裡只剩兩處 import 失敗時的 fallback，
                       見 docs/repo-cleanup-audit.md。
  engine03_feedback/   偏好回饋迴圈——已實作並接通（見上面「系統概觀」）
  pinterest/           Pinterest 趨勢訊號串接
engine02/            ENGINE02 的實作套件（刻意放在 repo 根目錄，見 CLAUDE.md「Repo 結構」——
                     內部路徑解析與 40+ 支腳本都假設這個位置）
frontend/            Next.js 16 + React 19 UI（IntentWeave；原規劃是 React + Vite，
                     實際蓋出來換了技術棧）
mcp_servers/catalog/ ENGINE02 現場真正執行的進入點（`mcp_servers.catalog.main:app`，
                     把 engine02/ 的 FastAPI app 掛在 /engine02/* 底下）——
                     scripts/start-demo.ps1／dev_services.py 實際啟動的就是這份
bff/images/、agent/scripts/  「生成新單品」（Design for Me）的實際生圖管線：ENGINE01
                     直接 import bff/images/concept.py，它再呼叫
                     agent/scripts/generate_grid.py／slice_grid.py（Hermes Agent，
                     Windows 上會橋接到 WSL2）。雖然放在大多沒在用的
                     agent/bff/mcp_servers/web/contracts/evals/ 平行技術棧（見
                     CLAUDE.md）旁邊，這幾個檔案本身就是現場 demo 真的在用的程式碼。
validation/          規劃中的離線驗證迴圈——目前只有 README，還沒有程式碼
scripts/             開發輔助／資料下載腳本、ENGINE02 的評測腳本，以及跨平台服務啟動器
                     dev_services.py（見下面）
```

完整盤點「哪些是真的用不到、哪些只是文件沒跟上」見 [docs/repo-cleanup-audit.md](docs/repo-cleanup-audit.md)。

## 快速開始

需求：Python 3.11+、Node.js 18+。

ENGINE01 跑在 OpenAI 的 Codex CLI 上，吃你的 ChatGPT Plus/Pro 訂閱額度（不用 API key）——先跑一次 `codex login`。**2026-09-20 核對：現場實際在跑的 demo 完全不需要 `OPENAI_API_KEY`**——ENGINE03 是純規則式（不吃 LLM），生成模組跟虛擬試穿都改走跟 ENGINE01 一樣的 `codex exec` 機制，不是直接呼叫 OpenAI API。除非你要加一個真的會呼叫 OpenAI API 的新功能，不然這欄留空即可。

```bash
cp .env.example .env   # 哪兩個值真的重要，見下面「登入設定」
codex login             # 一次性設定，ENGINE01／生成模組／虛擬試穿都需要

# ENGINE01
pip install -r backend/requirements.txt
```

**ENGINE02 有自己獨立的環境**（repo 根目錄的 `pyproject.toml`，用 `uv` 安裝——確切指令跟為什麼不共用 `backend/requirements.txt` 見 [backend/engine02_retrieval/README.md](backend/engine02_retrieval/README.md)），跑在自己的獨立服務、另一個 port 上。**ENGINE02 完全不讀 `.env`**（沒有 `load_dotenv()`）——它的環境變數要直接寫在啟動那行指令裡（見下面「怎麼開各個服務」），只寫進 `.env` 沒有用。

每個 `backend/` 底下的模組都有自己的 `README.md`，裡面有各自的執行／測試說明。

### 登入設定（Google OAuth）——必須設定，不能跳過

`/intent` 之後的每一步都要求登入。`.env` 裡真正有影響的是這兩個值：

- `SESSION_SECRET`——自己產生一組，不要共用同一組：`python -c "import secrets; print(secrets.token_hex(32))"`。
- `GOOGLE_CLIENT_ID`——**這不是密鑰**（設計上就是會被打包進瀏覽器端 JS 的公開值），直接跟團隊要現有的值來用就好，不用自己開一個新的 Google Cloud 專案；要記得跟 `frontend/.env.local` 的 `NEXT_PUBLIC_GOOGLE_CLIENT_ID` 用同一組。
- **OAuth consent screen 目前是「Testing」狀態，只有手動加進去的 Google 帳號才能登入**（不是「Published」）——不在清單上的帳號就算 Client ID 對，也會被 Google 自己擋下來、跳出「access blocked」錯誤。**如果你（或評審）要用一個之前沒用過的 Google 帳號登入，要先請團隊到 Google Cloud Console → APIs & Services → OAuth consent screen → Test users 把那個信箱加進去**（見 [CLAUDE.md](CLAUDE.md)「Google OAuth Client ID」）。不管是本機測試還是透過下面的 Cloudflare Tunnel 遠端連線，這條都一樣適用。
- 不想處理 Google 登入、只想先測後端邏輯：設 `DEV_BYPASS_AUTH=true`，所有請求都會當成同一個固定的本機測試使用者。**正式 demo 絕對不能開著這個。**

### 怎麼開各個服務（2026-09-19，實測過的組合）

Windows demo 機最快的方式是用一支啟動器一次開完整服務：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1
```

它會在背景啟動 ENGINE01／02／03、Whisper、Virtual You 與前端；已被使用的 port 會沿用、不會強制關掉既有程序，log 會寫到 `data/runtime/logs/`。想先只看它預計做什麼、不真正啟動時，加上 `-WhatIf`。

啟動器回傳前會檢查下列端點：

| 服務 | Port | 用途 |
| --- | ---: | --- |
| ENGINE02 | 8002 | 商品庫排序，以及背景、事實查核過的推薦理由改寫 |
| ENGINE01 | 8000 | 登入、意圖流程、回饋，以及給瀏覽器安全使用的 ENGINE02 改寫 proxy |
| ENGINE03 | 8003 | 回饋迴圈 |
| Whisper | 9000 | 語音轉文字 |
| Virtual You | 8081 | 人像擷取與 Try On |
| Frontend | 3000 | Next.js 前端 |

`start-demo.ps1` 預設啟用 `ENGINE02_REWRITER=codex`，請先完成一次 `codex login`。推薦排序本身不會等待改寫：ENGINE01 會先顯示 ENGINE02 的模板理由，再在背景請 ENGINE02 事實查核，完成後只替換卡片文字。若離線 demo 想略過這個非必要增強，請明確執行 `powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1 -Engine02Rewriter none`。

目前預設模型 `gpt-5.6-luna` 最快支援的推理強度是 `low`。要明確選擇帳號可用的模型，請只在啟動 ENGINE02 時帶入，例如：`powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1 -Engine02CodexModel gpt-5.6-terra -Engine02CodexEffort low`。啟動器刻意不沿用 terminal 裡舊的 `ENGINE02_CODEX_MODEL`／`ENGINE02_CODEX_EFFORT`，因為模型與推理強度不相容時，背景改寫就會安全退回模板。

### 程式或設定改完後怎麼重開

啟動器的設計是沿用已經佔用的 port，所以它不會 reload 已在跑的程序。請先到原本的 terminal 停掉對應程序；或用 `Get-NetTCPConnection -State Listen -LocalPort <port>` 找到 PID，再用 `Stop-Process -Id <pid>` 停掉，然後重跑啟動器。本 repo 的程式異動後，ENGINE01、ENGINE02、Frontend 要重開；如果只改 intent／recommendation，其他服務不需要重開。

### 將一位 demo 帳號重設成第一次使用

本系統把後端 profile 存在 `data/users/<Google-sub>.json`、瀏覽器資料存於 `intentweave.*` localStorage，進行中的對話 state 則只存在 ENGINE01 記憶體。它**不會**儲存或刪除 Google 帳號本身。

1. 先停掉 ENGINE01，再依登入 email 刪除一位使用者的 app profile（腳本會拒絕模糊目標，且由 PowerShell 再次確認）：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\reset-demo-user.ps1 -Email judge@example.com
   ```

2. 在 demo 用的瀏覽器開 `http://127.0.0.1:3000`，按 F12 → Console，貼入：

   ```js
   Object.keys(localStorage).filter((key) => key.startsWith("intentweave.")).forEach((key) => localStorage.removeItem(key)); location.reload();
   ```

   或改用 F12 → Application → Storage → **Clear site data** 清掉本機前端 origin 的資料。

3. 重開 ENGINE01（或再跑 `start-demo.ps1`）後再登入；這次會視為本 app 的新註冊／重新 onboarding。若還希望 Google 顯示不同帳號的挑選畫面，請在該瀏覽器登出 Google，或用無痕視窗；不要刪除使用者真正的 Google 帳號。

下面每一項都是一個要一直開著的獨立 terminal。ENGINE02 要先開（ENGINE01 會直接打它），其餘順序不拘。

```powershell
# Terminal 1 — ENGINE02（port 8002，真實商品庫）
$env:ENGINE02_DEMO="1"; $env:ENGINE02_PUBLIC_BASE="http://localhost:8002/engine02"
.venv-engine02\Scripts\python.exe -m uvicorn mcp_servers.catalog.main:app --port 8002

# Terminal 2 — ENGINE01（port 8000）
.venv\Scripts\python.exe -m uvicorn backend.engine01_intent.main:app --port 8000

# Terminal 3 — 前端（port 3000）
cd frontend
npm run dev

# Terminal 4 — 語音輸入（選用，只有按麥克風才需要）
.venv\Scripts\python.exe -m uvicorn backend.whisper_transcription.main:app --host 127.0.0.1 --port 9000

# Terminal 5 — 虛擬試穿（選用，只有「Try On」功能需要）
$env:VIRTUAL_TRY_ON_PROVIDER="codex"
.venv\Scripts\python.exe -m uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
```

補充：
- `ENGINE02_PUBLIC_BASE` 一定要帶 `/engine02` 路徑段——`mcp_servers.catalog.main:app` 是把整包 API 掛在這個前綴底下的，沒帶這段組出來的商品圖網址會 404。
- 前端 `frontend/.env.local`（不會進 git）要對應補上：ENGINE01 用的 `NEXT_PUBLIC_API_BASE_URL`，虛擬試穿（Terminal 5）用的 `PERSON_EXTRACTION_SERVICE_URL`／`VIRTUAL_TRY_ON_SERVICE_URL`——少了這兩個時，試穿現在會明確回設定錯誤，不會再把原圖假裝成成功結果。
- 虛擬試穿服務第一次呼叫 `/extract` 會下載一個約 973MB 的去背模型（`rembg` 的 `birefnet-portrait`）；語音服務第一次呼叫 `/transcribe` 會下載 Whisper `small` 模型——這兩個都建議提早 warm up，不要等到 demo 現場才第一次觸發下載。
- ENGINE02 的商品目錄是服務啟動時讀一次、存進記憶體，不是每次請求都重讀——底層資料有更新的話要重啟 Terminal 1 才會生效；ENGINE01 不會快取 ENGINE02 的任何資料，不用跟著改。

### 跨平台一鍵啟動／關閉／重啟

上面手動開 5 個 terminal 的方式、還有 `start-demo.ps1`／`reset-demo-user.ps1`，都只能在 Windows／PowerShell 上跑。團隊不是所有人都用 Windows，所以另外準備了 **`scripts/dev_services.py`**——純 Python 標準庫寫的跨平台版本，不用額外裝套件，服務清單跟健康檢查都跟 PowerShell 版一致，另外還多了單一服務關閉／重啟的功能：

```bash
python scripts/dev_services.py start                    # 啟動全部 6 個服務
python scripts/dev_services.py start engine01 engine02   # 只啟動指定的幾個
python scripts/dev_services.py status                    # 查每個服務目前是否在跑、健康檢查過不過
python scripts/dev_services.py stop frontend              # 關掉單一服務
python scripts/dev_services.py restart engine01 --env CORS_ALLOWED_ORIGINS=https://example.com,http://localhost:3000
                                                           # 重啟並覆蓋一個環境變數
                                                           # （下面「遠端 demo」流程會用到）
```

服務名稱：`engine02`、`engine01`、`engine03`、`whisper`、`virtual-you`、`frontend`。兩支腳本並存，看習慣哪個、用哪個 OS 就用哪支。

補充：
- 已經有服務在監聽某個 port 時，`start` 會偵測到、直接跳過不重複啟動，視為重用，不會報錯。
- 每個服務的 log 會寫到 `data/runtime/logs/<服務>-<port>.stdout.log`／`.stderr.log`——啟動後如果卡住，先去那邊看實際錯誤。
- `restart` 的 `--env` 覆蓋只影響這次重啟的行程環境變數，不會寫進 `.env`、也不會留存下來，下次重啟要覆蓋的話要再帶一次。

### 讓評審用自己的電腦連上你的 demo（Cloudflare Quick Tunnel）

不想讓評審擠在你的筆電前面操作？完整步驟見 **[docs/remote-demo-tunnel.md](docs/remote-demo-tunnel.md)**——包含怎麼裝 `cloudflared`、為什麼前端跟 ENGINE01 **兩個都要** tunnel（只開前端不夠，因為 `NEXT_PUBLIC_API_BASE_URL` 這種變數是啟動時就烤進瀏覽器端 JS 的），以及最容易漏掉的一步：登入要用到 Google OAuth，必須先把 tunnel 拿到的網址加進 Google Cloud Console 的允許清單，評審才登得進去。

## 交付項目清單（依競賽簡報）

1. 可實際運作、可現場互動展示的 prototype。
2. 這個 GitHub repo ＋英文 README（可重現性）。
3. 2–3 分鐘的 demo 影片（MP4）。
4. 現場問答與臨場調整——賽後不需要繳交模型權重。

## 授權

非商業性質的黑客松 prototype，不適用於正式產品環境。
