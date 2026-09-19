"""Local speech-to-text API backed by faster-whisper.

Defaults are deliberately CPU-friendly for the demo laptop:

    WHISPER_MODEL=small
    WHISPER_DEVICE=cpu
    WHISPER_COMPUTE_TYPE=int8

Run from the repository root:

    uvicorn backend.whisper_transcription.main:app --host 127.0.0.1 --port 9000
"""

from __future__ import annotations

import os
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from faster_whisper import WhisperModel

load_dotenv()

MODEL_NAME = os.environ.get("WHISPER_MODEL", "small")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
LANGUAGE = os.environ.get("WHISPER_LANGUAGE") or None
MAX_AUDIO_BYTES = int(os.environ.get("WHISPER_MAX_AUDIO_BYTES", str(25 * 1024 * 1024)))

app = FastAPI(title="IntentWeave local Whisper transcription")


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    """Load once on first use; the first call may download the model."""
    return WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "language": LANGUAGE or "auto",
    }


@app.post("/transcribe")
def transcribe(audio: UploadFile = File(...)) -> dict[str, str | float]:
    suffix = Path(audio.filename or "recording.webm").suffix or ".webm"
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            shutil.copyfileobj(audio.file, temp_file)
            temp_path = Path(temp_file.name)

        if temp_path.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="Audio file is empty.")
        if temp_path.stat().st_size > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file exceeds the configured size limit.")

        segments, info = get_model().transcribe(
            str(temp_path),
            language=LANGUAGE,
            vad_filter=True,
            beam_size=5,
        )
        text = "".join(segment.text for segment in segments).strip()

        if not text:
            raise HTTPException(status_code=422, detail="Whisper returned an empty transcription.")

        return {
            "text": text,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 4),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Whisper transcription failed: {exc}") from exc
    finally:
        audio.file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
