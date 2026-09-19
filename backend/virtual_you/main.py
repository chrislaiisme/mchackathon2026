"""Virtual You extraction and try-on service.

Run locally:
    uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
"""

from __future__ import annotations

import base64
import asyncio
import logging
import os
from functools import lru_cache

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from backend.virtual_you.codex_tryon import (
    SUPPORTED_CATEGORIES,
    CodexTryOnError,
    generate_try_on as generate_codex_try_on,
)

app = FastAPI(title="Virtual You - Person Extraction and Try-On")
logger = logging.getLogger(__name__)

DEFAULT_EXTRACTION_MODEL = "birefnet-portrait"


@lru_cache(maxsize=4)
def _rembg_session(model_name: str):
    try:
        from rembg import new_session
    except ImportError as exc:
        raise RuntimeError("rembg is not installed. Install backend requirements first.") from exc

    return new_session(model_name)


async def _read_upload(upload: UploadFile, *, label: str) -> bytes:
    data = await upload.read()

    if not data:
        raise HTTPException(status_code=400, detail=f"{label} is empty")

    return data


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "extraction_model": os.environ.get("PERSON_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL),
        "try_on_provider": os.environ.get("VIRTUAL_TRY_ON_PROVIDER", "auto"),
        "try_on_worker": bool(os.environ.get("VIRTUAL_TRY_ON_WORKER_URL")),
    }


@app.post("/extract")
async def extract_person(image: UploadFile = File(...)):
    image_bytes = await _read_upload(image, label="image")
    model_name = os.environ.get("PERSON_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL)

    try:
        from rembg import remove

        output = remove(
            image_bytes,
            session=_rembg_session(model_name),
            force_return_bytes=True,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"person extraction failed: {exc}") from exc

    return Response(content=output, media_type="image/png")


@app.post("/try-on")
async def generate_try_on(
    personImage: UploadFile = File(...),
    garmentImage: UploadFile = File(...),
    category: str = Form("upper_body"),
):
    if category not in SUPPORTED_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"unsupported category: {category}")

    person_bytes = await _read_upload(personImage, label="personImage")
    garment_bytes = await _read_upload(garmentImage, label="garmentImage")
    provider = os.environ.get("VIRTUAL_TRY_ON_PROVIDER", "").strip().lower()
    worker_url = os.environ.get("VIRTUAL_TRY_ON_WORKER_URL")

    logger.info(
        "Try-on request received provider=%s category=%s person_bytes=%s garment_bytes=%s",
        provider,
        category,
        len(person_bytes),
        len(garment_bytes),
    )

    if provider == "codex":
        try:
            output = await generate_codex_try_on(person_bytes, garment_bytes, category)
            from rembg import remove

            output = remove(
                output,
                session=_rembg_session(os.environ.get("PERSON_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL)),
                force_return_bytes=True,
            )
        except CodexTryOnError as exc:
            logger.warning("Codex try-on failed code=%s message=%s", exc.code, exc.message)
            raise HTTPException(status_code=exc.status_code, detail={"error": exc.code, "message": exc.message}) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"try-on background removal failed: {exc}") from exc

        return Response(content=output, media_type="image/png")

    if provider not in {"", "mock", "worker", "remote"}:
        raise HTTPException(status_code=503, detail=f"unsupported try-on provider: {provider}")

    if not worker_url or provider == "mock":
        return {
            "imageBase64": base64.b64encode(person_bytes).decode("ascii"),
            "provider": "mock",
        }

    try:
        response = await asyncio.to_thread(
            requests.post,
            worker_url,
            files={
                "personImage": (
                    "person.png",
                    person_bytes,
                    personImage.content_type or "image/png",
                ),
                "garmentImage": (
                    "garment.png",
                    garment_bytes,
                    garmentImage.content_type or "image/png",
                ),
            },
            data={"category": category},
            timeout=float(os.environ.get("VIRTUAL_TRY_ON_TIMEOUT_SECONDS", "180")),
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"try-on worker request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=response.text[:1200])

    content_type = response.headers.get("content-type", "")

    if "application/json" in content_type:
        return response.json()

    return Response(content=response.content, media_type=content_type or "image/png")
