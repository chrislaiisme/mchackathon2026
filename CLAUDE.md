# CLAUDE.md

給 AI coding agent（Claude Code、Codex 等）在這個 repo 工作時看的專案指示。先讀這份，細節都連到 `docs/`，不在這裡重複。

## 文件語言規則

**所有 `.md` 文件一律用中文寫，包括這份檔案，以後新增的 md 文件也一樣。** 唯一例外是根目錄的 `README.md`——競賽交付項目明確要求「GitHub 原始碼＋英文 README」（見下方交付項目），所以它必須維持英文；對應的中文版放在 [README_TW.md](README_TW.md)，兩份互相連結，內容改動時兩邊都要同步更新。程式碼裡的變數名、函式名、commit message、PR 標題維持英文是正常慣例，不受這條規則影響——這條規則只管 `.md` 文件的內文語言。專有名詞、API 名稱、套件名、程式碼、檔案路徑、URL（例如 FastAPI、React、Vite、Pydantic、OpenAI、Codex、GPT、Pinterest、FashionCLIP、Polyvore、BM25、ENGINE01/02/03）維持原文，不用硬翻。

## 程式碼註解規則

**所有 `.py` 檔都要寫足夠的註解**——每個邏輯段落都要有基本註解，重要／不直覺的部分（例如為什麼選這個實作方式、跟其他模組的隱含依賴關係）要多寫一點，不要只寫 docstring 就結束。這條蓋過一般「只在必要時加註解」的預設寫法，是這個專案特別要求的。新增或編輯任何 `.py` 檔時都要記得補。註解用中文寫，跟這個專案其他地方的語言慣例一致；變數名、函式名等識別字維持英文是正常慣例，不受影響。

## 這是什麼

**Consumer Intent Agent（一句話讀懂消費者）** — 為 **2026 梅竹黑客松 x 聚陽實業（Makalot Industrial）** 打造的 prototype，團隊名 **勢在必得**。題目：*「一句話讀懂消費者」*。比賽日：**2026-09-19**。完整背景見 [docs/hackathon-brief.md](docs/hackathon-brief.md)。

交付項目：(1) 可實際運作、可互動展示的 prototype，(2) 這個 repo ＋英文 README，(3) 一支 2–3 分鐘的 demo 影片，(4) 現場問答與臨場調整。

評分標準（總分 100%）：問題理解與契合度 35%．技術方案與資料應用 35%．呈現完整度與可行性 20%．表達與應變 10%。評審明確表示前兩項比重最重——對消費者行為的洞察和技術紮實度，比展示得多完整更重要。評審現場的評測方式是一個迴圈：出題目 → 看結果 → 給回饋 → 出第二題 → 檢查系統是否真的變準。ENGINE 03 存在的目的，就是要讓這個迴圈可以被驗證，不是嘴上說說。

## 系統架構

兩條迴圈共用同一套 ENGINE 01–03 程式碼：

- **Live 流程**（真人使用者／評審，在瀏覽器上操作）：[docs/system-architecture.svg](docs/system-architecture.svg)。使用者一句話 → ENGINE 01（結構化意圖）→ ENGINE 02（檢索）和生成模組**同時並行**執行，兩者吃同一組意圖 → 結果並排呈現 → 使用者回饋 → ENGINE 03 → 下一輪。跑到使用者滿意為止，不是固定兩輪。
- **驗證流程**（只在開發階段用，不會出現在正式 demo 畫面）：[docs/validation-flow.svg](docs/validation-flow.svg)。一個帶著隱藏目標圖片人設的模擬 LLM 使用者，跑 2–4 輪對付同一套 ENGINE 01–03 程式碼；FashionCLIP 對目標圖片的 cosine similarity 就是量化的收斂指標，用來在簡報裡佐證「回饋迴圈真的有效」。

三個引擎、一個生成模組、一條趨勢訊號串接：

| 模組 | 負責 | 核心技術 | 資料夾 |
|---|---|---|---|
| ENGINE01 | 需求理解＋登入 | GPT structured output、FastAPI、Google OAuth | `backend/engine01_intent/` |
| ENGINE02 | 檢索與排序 | FashionCLIP ＋ BM25 hybrid search、reranker、Polyvore Outfits Dataset | `backend/engine02_retrieval/` |
| ENGINE03 | 回饋 → 權重／意圖更新 | GPT structured output | `backend/engine03_feedback/` |
| 生成模組 | 每輪一張概念圖＋虛擬形象試穿 | OpenAI Responses API 的 `image_generation` tool | `backend/generation/` |
| Pinterest | 趨勢訊號餵給 ENGINE02/03 | 團隊自選板子、Pinterest API v5 Trial access | `backend/pinterest/` |
| 前端 | UI | React + Vite | `frontend/` |
| 驗證 | 離線量化指標 | 模擬使用者 ＋ FashionCLIP 相似度 | `validation/` |

整個專案不用 LangChain／LlamaIndex——每個模組都直接呼叫 GPT API（chat completions structured output，或 Responses API 做圖片生成）。這是規劃文件裡的刻意決定，不是漏掉沒做。

## Repo 結構

```
index.html, privacy.html, styles.css, assets/, .nojekyll   # 既有 GitHub Pages 網站 — 不要動，理由見下面
README.md               英文，根目錄（交付項目 #2 要求）
README_TW.md            README.md 的中文版
CLAUDE.md               這份檔案
docs/                    所有 markdown 文件＋架構圖都放這裡
backend/
  shared/                跨引擎共用的 Pydantic schema — 介面契約的程式碼版本
  engine01_intent/        \
  engine02_retrieval/      | 每個引擎／模組一個資料夾，對照上面表格
  engine03_feedback/      /
  generation/
  pinterest/
  requirements.txt        整個 backend/ 共用一份依賴檔
frontend/                React + Vite
validation/              模擬使用者驗證迴圈腳本
scripts/                 開發輔助腳本（例如下載資料集）
```

**不要重新調整或刪除根目錄的 `index.html` / `privacy.html` / `styles.css` / `assets/` / `.nojekyll`。** 這些是給 Pinterest App 審核用的隱私權政策網站。GitHub Pages 實際上是從獨立的 `gh-pages` 分支發布的（`chrislaiisme.github.io/mchackathon2026/`），所以這些檔案留在 `main` 上目前只是歷史遺留——但沒跟團隊確認前不要刪，也絕對不要沒確認就 push 到 `gh-pages`。

## P0 現況 — 各模組的 GPT 存取方式

**團隊目前只有 ChatGPT Plus/Pro 訂閱，還沒有人申請 platform.openai.com 的 API key。** 這件事對 ENGINE02（推薦理由生成）、ENGINE03、生成模組（透過 Responses API 呼叫 `image_generation` tool）仍然重要，這幾個都需要 `OPENAI_API_KEY`。如果之後團隊決定要申請：去 platform.openai.com 建帳號、生一把 key、加一筆小額預付款（整場黑客松預估花費遠低於 US$2，抓 US$5–10 就很夠），並且透過線下管道分享——絕對不要寫進 commit 或明碼貼在聊天紀錄裡。把 `.env.example` 複製成 `.env`、本機填好；`.env` 已經被 gitignore。

**ENGINE01 已經不需要這個了。** 它改用 `codex exec`，細節見下面。不要假設其他引擎也一樣不需要 API key，那是各自負責人要做的決定。

## ENGINE01 執行方式：`codex exec`，不用 API key

這是實際測過兩條路之後的刻意選擇：團隊希望不要花錢，所以 ENGINE01 改成呼叫 OpenAI 的 Codex CLI（`codex exec --output-schema`），吃開發者自己的 ChatGPT Plus/Pro 訂閱額度（`codex login`，這台開發機已經登入好了），不用另外付費的 API key。每次呼叫零邊際成本，這點已經實測確認。

代價（同樣是實測出來的，不是憑空假設）：

| | `codex exec`（本專案採用） | 直接用 OpenAI API key |
|---|---|---|
| 花費 | $0 | 約 $0.001／次呼叫 |
| 延遲 | 每次約 8–17 秒 | 約 1–3 秒 |
| 每次呼叫的 token 數 | 約 14,000–20,000 | 約 1,500 |

這些 token 花費是算在團隊**共用**的 ChatGPT 方案 Codex 額度上——跟現場兩天大家用 Claude Code／Codex 輔助寫程式是同一個額度池。ENGINE01 每輪對話都要呼叫一次，累積起來不是小數目，尤其接近 demo 時段要多留意。如果之後真的變成問題（額度用完，或現場每輪等 8–17 秒太慢），修法是把 `backend/engine01_intent/llm_client.py` 裡 `extract_intent()` 的實作換回直接呼叫 OpenAI API——函式簽名和呼叫它的地方都不用動。

任何要跑 ENGINE01 的機器，前提是：裝好 `codex` CLI，並且用 `codex login` 登入過一次（完全不需要 `OPENAI_API_KEY`）。不需要另外裝 Hermes Agent——`codex exec --output-schema` 本身就有原生的 JSON schema 限制輸出功能，這正是查證當下 Hermes 自己的 one-shot 模式還沒有的東西（上游有一個開放中的 feature request）。Hermes Agent 在這個專案裡的角色就停在這裡（ENGINE01 的模型呼叫備選方案），不是使用者面對的對話框架——`POST /intent` 本身透過 session 狀態重複呼叫，已經是完整的「使用者跟 AI 對話」迴圈了，不需要再疊一層 Hermes 上去當 webapp 的對話引擎。

## Google OAuth Client ID（ENGINE01 登入用，免費，跟上面的 P0 花費問題無關）

ENGINE01「必須登入」，需要一組 Google Cloud 的 OAuth Client ID 才能驗證登入。這是免費的帳號設定步驟，跟上面「P0 現況」那個要花錢／要有人加值的 API key 問題完全分開，不要混在一起判斷優先順序——沒有 Client ID 之前，開發用 `DEV_BYPASS_AUTH=true` 照樣能測 `/intent`／`/profile`，不擋開發，只有「demo 前」才是真正的截止線。

還沒建的話，步驟：

1. [console.cloud.google.com](https://console.cloud.google.com/) 建一個新專案。
2. 「APIs & Services」→「OAuth consent screen」：User Type 選 External，填 App name／support email／developer contact email，Scopes 維持預設（`openid`／`email`／`profile`），Test users 先把隊友的 Google 帳號都加進去，或直接 Publish App（只用基本 scope，不會觸發 Google 審查）。
3. 「APIs & Services」→「Credentials」→「Create Credentials」→「OAuth client ID」，Application type 選 Web application，「Authorized JavaScript origins」加 `http://localhost:5173`（Vite 預設 port，之後有部署網址也要加），「Authorized redirect URIs」留空（這個登入方式用不到）。
4. 拿到的 Client ID 同時填進後端 `.env` 的 `GOOGLE_CLIENT_ID`，和前端初始化 Google Identity Services 按鈕用的同一組 ID——兩邊必須一致，因為後端會檢查 token 的 audience。旁邊那組 Client secret 這個流程用不到，不用管它，更不要 commit 進 git。

## 介面契約

`backend/shared/schemas.py` 是引擎之間流動的 JSON（結構化意圖、回饋 delta、商品卡片等）的程式碼版真相來源——這樣訂出來是為了讓各條線能平行開發、不用互相等待。書面規格見 [docs/interface-contract.md](docs/interface-contract.md)。要改這裡的欄位名稱／型別之前，先知會其他引擎的負責人再 merge，因為 ENGINE02/03／前端都依賴它。

## Git 工作流程

- `main` 是共用分支；目前其他組員的既有內容是 GitHub Pages 網站，維持原樣。
- 每條線一個分支，目前提議的命名慣例（還沒經過全隊確認）：`engine01-intent`、`engine02-retrieval`、`engine03-feedback`、`frontend`、`pinterest-generation`。
- `git worktree` 是規劃文件裡提到的選用技巧（在同一台機器上把多個分支各自簽出到不同資料夾），如果想同時跑多個 agent 在不同分支上會用得到，一般單分支開發不需要。
- 推到共用遠端或開 PR 一律先跟使用者確認——這會讓其他四位組員都看得到。

## 負責人對照

- ENGINE01（需求理解）：這個工作目錄的擁有者。
- Pinterest 板子策展：品諭（依規劃文件）。
- ENGINE02、ENGINE03、前端、生成模組：文件裡還沒指定，確定後再補上。

## 環境備註

- 這個 repo 放在 OneDrive 底下（`...\OneDrive\桌面\Hackathon`）。OneDrive 的同步用戶端可能會在寫檔案途中鎖檔，或讓剛寫好的檔案延遲才能用（在建這個 repo 的過程中實際遇過：`pip install` 剛裝完，import openai SDK 的 `jiter` 依賴時噴了一次 `DLL load failed`，下一次馬上重試就正常了——典型的「檔案還沒完全同步好」症狀）。如果 `pip install`／`npm install`／`git` 操作在寫了一大堆檔案之後（例如 `frontend/node_modules`）表現得不穩定，先重試一次再當成真的 bug。如果一直發生，考慮把這個資料夾排除在 OneDrive 同步之外，而不是搬移整個 repo。
- 後端：Python 3.11+，整個 `backend/` 共用一份 `backend/requirements.txt`——不要每個引擎各自開一份 venv／requirements，兩天的黑客松時程沒有餘裕去對五套環境。
- 前端：React + Vite，不用 Next.js／SSR——UI 就是輸入框、結果卡片、意圖面板、回饋控制項，用不到一整套 app 框架的複雜度。
- 後端有設 CORS（`CORS_ALLOWED_ORIGINS`，預設 `http://localhost:5173`），任何要從瀏覽器呼叫這幾個 API 的畫面（正式前端或臨時測試頁）網址都要在這個清單裡，不然瀏覽器會直接擋掉，不會是 401，是完全連不到。

## 想找更多細節的話

- 完整競賽簡報、評分標準、設計討論歷程：[docs/hackathon-brief.md](docs/hackathon-brief.md)
- PRD 骨架：[docs/prd.md](docs/prd.md)
- 各模組規格：`docs/engine01-intent.md`、`docs/engine02-retrieval.md`、`docs/engine03-feedback.md`、`docs/frontend.md`、`docs/pinterest-and-generation.md`
- 量化驗證設計：[docs/validation-plan.md](docs/validation-plan.md)
