# Whisper 本機語音輸入使用指南

本專案使用 `faster-whisper` 在本機執行語音轉文字，不需要 OpenAI API key。
目前預設配置適合 CPU 電腦：

| 設定 | 預設值 | 用途 |
| --- | --- | --- |
| `WHISPER_MODEL` | `small` | 模型大小 |
| `WHISPER_DEVICE` | `cpu` | 使用 CPU 推論 |
| `WHISPER_COMPUTE_TYPE` | `int8` | 降低 CPU 與記憶體負擔 |
| `WHISPER_LANGUAGE` | 空白 | 自動偵測語言 |
| `WHISPER_API_URL` | `http://127.0.0.1:9000/transcribe` | 前端呼叫的 Whisper API |

## 1. 第一次安裝

在 repository 根目錄開啟 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

如果 PowerShell 阻擋虛擬環境啟用，可以不啟用，後續直接使用
`.\.venv\Scripts\python.exe`。

## 2. 啟動 Whisper API

在 repository 根目錄執行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.whisper_transcription.main:app --host 127.0.0.1 --port 9000
```

看到 `Uvicorn running on http://127.0.0.1:9000` 表示服務已啟動。第一次轉錄時會下載
Whisper `small` 模型，所需時間取決於網路速度；後續會使用本機快取。

另開一個 PowerShell 視窗檢查服務：

```powershell
Invoke-RestMethod http://127.0.0.1:9000/health
```

預期結果：

```json
{
  "status": "ok",
  "model": "small",
  "device": "cpu",
  "compute_type": "int8",
  "language": "auto"
}
```

## 3. 啟動前端

保持 Whisper 視窗執行，再開一個 PowerShell 視窗：

```powershell
cd frontend
npm install
npm run dev
```

開啟 <http://localhost:3000/stylist>，按麥克風、允許瀏覽器使用麥克風，說話後停止錄音。

資料路徑：

```text
瀏覽器錄音
  -> POST /api/transcribe（Next.js）
  -> POST http://127.0.0.1:9000/transcribe（FastAPI）
  -> faster-whisper small / CPU / int8
  -> { "text": "辨識結果" }
  -> 回填前端輸入欄位
```

## 4. 直接呼叫 API

可以用既有的音訊檔測試，不經過前端：

```powershell
curl.exe -F "audio=@sample.webm" http://127.0.0.1:9000/transcribe
```

成功回應：

```json
{
  "text": "今天想找一套適合面試的穿搭",
  "language": "zh",
  "language_probability": 0.9987
}
```

支援前端上傳的格式包括 WebM、WAV、MP3、MP4、M4A、OGG 與 FLAC。預設檔案上限為
25 MiB；空白音訊、超過上限或沒有辨識出文字時，API 會回傳相應的 HTTP 錯誤。

## 5. 調整設定

後端會讀取 repository 根目錄的 `.env`。先從範例建立本機設定：

```powershell
Copy-Item .env.example .env
```

例如固定辨識繁體中文並調整檔案上限：

```env
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=zh
WHISPER_MAX_AUDIO_BYTES=26214400
```

如果 Whisper 部署在不同位置，在 `frontend/.env.local` 設定：

```env
WHISPER_API_URL=http://127.0.0.1:9000/transcribe
```

修改環境變數後，需要重新啟動對應服務。

## 常見問題

### 前端顯示 Whisper 無法連線

確認 Whisper 視窗仍在執行，再呼叫健康檢查：

```powershell
Invoke-RestMethod http://127.0.0.1:9000/health
```

### 第一次辨識很慢

第一次使用需要下載並載入 `small` 模型。下載完成後，模型會保留在 Hugging Face 的本機快取。

### CPU 辨識速度太慢

先維持 `int8`。如果展示電腦效能不足，可暫時改成 `base`；速度較快，但辨識準確度通常較低：

```env
WHISPER_MODEL=base
```

### 麥克風無法使用

確認瀏覽器已允許 `localhost` 使用麥克風。一般瀏覽器只允許在 `localhost` 或 HTTPS 頁面取得麥克風權限。

### 停止服務

分別切換到 Next.js 與 Whisper 的 PowerShell 視窗，按 `Ctrl+C`。
