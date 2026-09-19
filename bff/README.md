# bff/

Runtime：內嵌 Hermes Agent 的後端服務，對應 PRD 7.1 Agent Runtime Layer。流程由程式決定，模型只負責每一步交代的那件工作。

負責線：線 4｜Runtime、回饋迴圈與打包（整體與整合）；子資料夾依下表
對應功能：FR-008、FR-009（Agent 活動紀錄）、FR-011；全系統整合

| 位置 | 內容 | 負責線 |
|---|---|---|
| `bff/`（根目錄） | 流程控制、session、各 skill 與工具的呼叫順序、前端使用的端點 | 線 4 |
| `images/` | 選項圖生成與檢查、概念圖生成、生圖額度控管 | 線 3 |
| `feedback/` | 偏好更新、符合度分數 | 線 4 |
| `activity_log/` | 每一輪使用的 skill 與工具紀錄 | 線 4 |

## 規則

- 只對本機（127.0.0.1）開放。
- 啟動時使用安裝好的 agent profile，不讀取個人的 Hermes 設定。
- 每個步驟只開放該步驟需要的工具。

## 整合前先用

回傳假資料的 skill 與工具替身。

目前狀態：尚未開始。

---

## 串接層（已實作並驗證）

`bff/main.py` 是前端唯一要打的服務，由它依序呼叫三個引擎。

| 端點 | 流程 |
|---|---|
| `POST /round` | ENGINE 01 抽意圖 → ENGINE 02 檢索排序 → 回傳這一輪結果 |
| `POST /feedback` | ENGINE 03 轉換回饋 → 帶著回饋重跑 ENGINE 02 → 回傳下一輪結果 |
| `GET /session/{id}` | 這個 session 的所有輪次 |
| `GET /health` | 一次看三個引擎在不在 |

`POST /feedback` 一次就完成「回饋 → 再出題」，前端不用自己再呼叫一次 `/round`。同一份意圖沿用，
差別只在多了一輪回饋，所以排序改變的原因是可以指著講的。

### 四個服務一起跑

先裝依賴（一次）。ENGINE 02 用 `pyproject.toml`；ENGINE 01／03 與串接層用根目錄的
`requirements.txt`（`python-dotenv`、`google-auth` 只在那裡），**兩份都要裝**：

```bash
uv pip install -e ".[data,dev]"
uv pip install -r requirements.txt
```

ENGINE 02 還要先建商品庫（`data/README.md` 步驟 1）；沒裝 torch 的話啟動時加 `ENGINE02_ENCODER=hash`。
前端第一次要先 `cd web && npm install`。

```bash
uvicorn bff.engine01_intent.main:app --port 8000     # ENGINE 01（需要 codex login）
uvicorn mcp_servers.catalog.main:app --port 8002     # ENGINE 02（需要商品庫；無 torch 加 ENGINE02_ENCODER=hash）
uvicorn bff.feedback.main:app       --port 8003      # ENGINE 03
uvicorn bff.main:app                --port 8100      # 串接層
cd web && npm run dev                                # 前端
```

埠號可用環境變數覆寫：`ENGINE01_URL`、`ENGINE02_URL`、`ENGINE03_URL`、`BFF_TIMEOUT`、
`CORS_ALLOWED_ORIGINS`（預設 `http://localhost:3000`，配合 Next.js）。

### 每一步都記帳

回傳裡的 `activity` 記錄這一輪呼叫了哪些服務、各花幾毫秒、成功與否。任何一步失敗會回 502 並
指名是哪一步斷的（例如「engine02.retrieve 失敗（http://127.0.0.1:8002/retrieve）」），
現場排查不用猜。
