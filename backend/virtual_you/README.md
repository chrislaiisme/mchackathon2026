# Virtual You service

這個 service 把 Virtual You pipeline 的模型依賴從 Next.js 前端拆出來：

- `POST /extract`：輸入 `image`，回傳透明背景 PNG。預設使用 `rembg` 的 `birefnet-portrait` session。
- `POST /try-on`：輸入 `personImage`、`garmentImage`、`category`。若有設定 `VIRTUAL_TRY_ON_WORKER_URL`，會轉送到 GPU worker；若沒有設定，回傳原人物圖作為 demo-safe fallback。

## 啟動

```bash
pip install -r backend/requirements.txt
uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
```

第一次呼叫 `/extract` 時，`rembg` 會下載對應模型到本機快取。黑客松 demo 前請先用一張測試照 warm up。

## 環境變數

```bash
PERSON_EXTRACTION_MODEL=birefnet-portrait
VIRTUAL_TRY_ON_WORKER_URL=http://127.0.0.1:8082/try-on
VIRTUAL_TRY_ON_TIMEOUT_SECONDS=180
```

Next.js 端使用：

```bash
PERSON_EXTRACTION_SERVICE_URL=http://127.0.0.1:8081/extract
VIRTUAL_TRY_ON_SERVICE_URL=http://127.0.0.1:8081/try-on
```

之後如果改用 CatVTON、IDM-VTON 或 Leffa，只要讓 GPU worker 維持 `personImage + garmentImage + category -> image/png 或 { imageBase64 }` 的介面，前端不需要知道底層模型。
