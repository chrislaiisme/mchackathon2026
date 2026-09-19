# Local Whisper transcription

完整的繁體中文安裝、前端串接與疑難排解說明請見
[`docs/whisper-guide.md`](../../docs/whisper-guide.md)。

This service runs `faster-whisper` locally with these defaults:

- model: `small`
- device: `cpu`
- compute type: `int8`
- language: automatic detection

## Start

From the repository root in PowerShell:

```powershell
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.whisper_transcription.main:app --host 127.0.0.1 --port 9000
```

The first transcription downloads the `small` model and therefore takes longer.

Check the active configuration:

```powershell
Invoke-RestMethod http://127.0.0.1:9000/health
```

Test a recording:

```powershell
curl.exe -F "audio=@sample.webm" http://127.0.0.1:9000/transcribe
```

Optional environment overrides:

```env
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=
WHISPER_API_URL=http://127.0.0.1:9000/transcribe
```

The Python service reads the repository-root `.env`. Next.js reads
`WHISPER_API_URL` from `frontend/.env.local`; the default URL already works
when both services run on the same computer.
