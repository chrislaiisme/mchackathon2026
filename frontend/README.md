# IntentWeave Frontend

Next.js frontend for the IntentWeave demo. It contains the Dressing Room, Create You, Virtual You, and Try On UI.

## Prerequisites

- Node.js 20+
- npm
- The Virtual You FastAPI service running on `127.0.0.1:8081` for Create You and real Try On

## Setup

Install dependencies from this directory:

```bash
npm install
```

Create or update `frontend/.env.local`:

```bash
PERSON_EXTRACTION_SERVICE_URL=http://127.0.0.1:8081/extract
VIRTUAL_TRY_ON_SERVICE_URL=http://127.0.0.1:8081/try-on
```

Restart the Next.js dev server after changing `.env.local`.

## Run

Start the frontend:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

## Virtual You Backend

The frontend talks to the local FastAPI service through these Next.js routes:

- `POST /api/virtual-you/extract`
- `POST /api/virtual-you/try-on`

Start the backend from the repo root:

```bash
VIRTUAL_TRY_ON_PROVIDER=codex \
CODEX_BIN=/Users/chiwenhsu/.local/bin/codex \
CODEX_TRY_ON_TIMEOUT=180 \
.venv/bin/python -m uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
```

Check the backend:

```bash
curl http://127.0.0.1:8081/healthz
```

Expected for real Try On:

```json
{
  "ok": true,
  "try_on_provider": "codex"
}
```

## Demo Flow

1. Upload a full-body photo in Create You.
2. The frontend sends it to `/api/virtual-you/extract`.
3. Next.js forwards it to FastAPI `/extract`.
4. FastAPI removes the background and returns a transparent person PNG.
5. The frontend stores the original and extracted person image in browser IndexedDB.
6. Click Try On on a garment.
7. The frontend sends the current Virtual You image and garment image to `/api/virtual-you/try-on`.
8. Next.js forwards the request to FastAPI `/try-on`.
9. FastAPI runs Codex image generation, removes the generated background, and returns a PNG.
10. The Virtual You display swaps to the generated try-on image.

## Important Environment Notes

- `PERSON_EXTRACTION_SERVICE_URL` is read by the Next.js extraction route.
- `VIRTUAL_TRY_ON_SERVICE_URL` is read by the Next.js try-on route.
- `VIRTUAL_TRY_ON_PROVIDER=codex` must be set on the FastAPI process, not only in `frontend/.env.local`.
- If `VIRTUAL_TRY_ON_SERVICE_URL` is missing, the frontend route uses the mock fallback and returns the original person image.
- If FastAPI is not started with `VIRTUAL_TRY_ON_PROVIDER=codex`, `/try-on` will not use Codex.

## Troubleshooting

If Try On returns the original person image:

- Confirm `frontend/.env.local` has `VIRTUAL_TRY_ON_SERVICE_URL=http://127.0.0.1:8081/try-on`.
- Restart `npm run dev`.
- Confirm `curl http://127.0.0.1:8081/healthz` shows `"try_on_provider": "codex"`.
- Watch the FastAPI terminal for `Codex try-on subprocess args=...`.

If Create You fails with `No module named 'onnxruntime'`:

- Start FastAPI with the project virtualenv:

```bash
.venv/bin/python -m uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
```

If Try On fails quickly:

- Check the FastAPI terminal logs.
- The backend logs the Codex subprocess args, exit code, and stderr/stdout tail.
- Do not log or paste full image base64 payloads.

## Scripts

```bash
npm run dev
npm run build
npm run start
npm run lint
```
