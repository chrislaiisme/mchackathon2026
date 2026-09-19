# Virtual You service

這個 service 把 Virtual You pipeline 的模型依賴從 Next.js 前端拆出來：

- `POST /extract`：輸入 `image`，回傳透明背景 PNG。預設使用 `rembg` 的 `birefnet-portrait` session。
- `POST /try-on`：輸入 `personImage`、`garmentImage`、`category`。若沒有設定 provider/worker，回傳原人物圖作為 demo-safe fallback；設定 `VIRTUAL_TRY_ON_PROVIDER=codex` 時會透過本機 `codex exec` 與 `$imagegen` 產生真實試穿圖；若設定 `VIRTUAL_TRY_ON_WORKER_URL`，仍可沿用外部 worker。

## 啟動

```bash
pip install -r backend/requirements.txt
uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
```

第一次呼叫 `/extract` 時，`rembg` 會下載對應模型到本機快取。黑客松 demo 前請先用一張測試照 warm up。

## 環境變數

```bash
PERSON_EXTRACTION_MODEL=birefnet-portrait
VIRTUAL_TRY_ON_PROVIDER=codex
CODEX_BIN=codex
CODEX_TRY_ON_TIMEOUT=180
CODEX_TRY_ON_CONCURRENCY=1
VIRTUAL_TRY_ON_WORKER_URL=http://127.0.0.1:8082/try-on
VIRTUAL_TRY_ON_TIMEOUT_SECONDS=180
```

Next.js 端使用：

```bash
PERSON_EXTRACTION_SERVICE_URL=http://127.0.0.1:8081/extract
VIRTUAL_TRY_ON_SERVICE_URL=http://127.0.0.1:8081/try-on
```

## Codex Try-On

Codex provider 使用已登入的本機 Codex CLI，不需要 `OPENAI_API_KEY`：

```bash
codex login
VIRTUAL_TRY_ON_PROVIDER=codex \
VIRTUAL_TRY_ON_SERVICE_URL=http://127.0.0.1:8081/try-on \
uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
```

`/try-on` 會建立暫存資料夾，保存 `person.png` 與 `garment.png`，再用 `codex exec --image person.png --image garment.png` 執行 `$imagegen` prompt。生成結果會轉成 PNG 回傳給既有前端。

之後如果改用外部 worker，只要讓 worker 維持 `personImage + garmentImage + category -> image/png 或 { imageBase64 }` 的介面，前端不需要知道底層模型。
