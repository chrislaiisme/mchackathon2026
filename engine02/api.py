"""HTTP API for ENGINE 02 (FastAPI).

  ENGINE02_ENCODER=marqo-fashionSigLIP uvicorn engine02.api:app --port 8002

Environment variables:
  ENGINE02_CATALOG   catalog dir with items.parquet           (default data/catalog/kagl)
  ENGINE02_ENCODER   marqo-fashionSigLIP | fashion-clip | hash (default marqo-fashionSigLIP)
  ENGINE02_DEVICE    auto | cpu | cuda                         (default auto)
  ENGINE02_RERANKER  optional cross-reranker, e.g. Qwen3-VL-Reranker-2B (GPU only in practice)
  ENGINE02_COOC      category co-occurrence json               (default data/catalog/polyvore/category_cooccurrence.json)
  ENGINE02_KANSEI    Kansei table json                         (default engine02/resources/kansei_v0.json)
  ENGINE02_LLM       auto (OpenAI if OPENAI_API_KEY) | none    (default auto)
  ENGINE02_ARM       default ablation arm when the request does not set one (default full)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .catalog import Catalog
from .compat import CategoryCooccurrence
from .config import ARMS
from .contracts import CONTRACT_VERSION, Engine02Request, Engine02Response
from .encoders import HashEncoder
from .kansei import KanseiTable
from .llm import get_llm
from .pipeline import Engine02

ROOT = Path(__file__).resolve().parents[1]
STATE: dict = {}


def _path(env: str, default: str) -> Path:
    p = Path(os.environ.get(env, default))
    return p if p.is_absolute() else ROOT / p


def build_engine() -> Engine02:
    catalog = Catalog.load(_path("ENGINE02_CATALOG", "data/catalog/kagl"))
    enc_name = os.environ.get("ENGINE02_ENCODER", "marqo-fashionSigLIP")
    device = os.environ.get("ENGINE02_DEVICE", "auto")
    if enc_name == "hash":
        encoder = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(catalog.items["image_path"], catalog.texts())})
    else:
        from .models import TorchEncoder

        encoder = TorchEncoder(enc_name, device=device)
    cooc_file = _path("ENGINE02_COOC", "data/catalog/polyvore/category_cooccurrence.json")
    reranker = None
    if os.environ.get("ENGINE02_RERANKER"):
        from .models import CrossEncoderReranker

        reranker = CrossEncoderReranker(os.environ["ENGINE02_RERANKER"], catalog, device=device)
    llm = None if os.environ.get("ENGINE02_LLM", "auto") == "none" else get_llm("auto")
    return Engine02(
        catalog,
        encoder,
        kansei=KanseiTable.load(_path("ENGINE02_KANSEI", "engine02/resources/kansei_v0.json")),
        cooccurrence=CategoryCooccurrence.load(cooc_file) if cooc_file.exists() else None,
        llm=llm,
        cross_reranker=reranker,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["engine"] = build_engine()
    yield
    STATE.clear()


app = FastAPI(title="ENGINE 02 — retrieval, ranking, faithful explanation", version=CONTRACT_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def engine() -> Engine02:
    return STATE["engine"]


@app.get("/health")
def health() -> dict:
    e = engine()
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "catalog": e.catalog.name,
        "n_items": len(e.catalog),
        "encoder": e.encoder.name,
        "reranker": getattr(e.cross_reranker, "name", None),
        "llm": e.llm is not None,
        "kansei_version": e.kansei.version,
        "init_ms": round(e.init_ms, 1),
    }


@app.get("/arms")
def arms() -> dict:
    return {name: vars(cfg) for name, cfg in ARMS.items()}


@app.get("/kansei")
def kansei() -> dict:
    """Need ids and design-element ids that ENGINE 01 / 03 must use."""
    k = engine().kansei
    return {
        "version": k.version,
        "needs": k.needs,
        "design_elements": {el.id: el.label for el in k.elements},
        "step_size": k.step_size,
        "max_steps": k.max_steps,
    }


@app.get("/vocabulary")
def vocabulary() -> dict:
    """Catalog values ENGINE 01 must normalise slot values to (hard filters are exact matches)."""
    items = engine().catalog.items
    out = {}
    for col in ("category", "subcategory", "color", "occasion", "season", "gender"):
        vc = items[col].dropna().astype(str).value_counts()
        out[col] = vc.to_dict()
    return out


@app.post("/rank", response_model=Engine02Response)
def rank(req: Engine02Request) -> Engine02Response:
    arm = req.options.arm or os.environ.get("ENGINE02_ARM", "full")
    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    if ARMS[arm].use_cross_reranker and engine().cross_reranker is None:
        raise HTTPException(400, "this arm needs ENGINE02_RERANKER to be set on the server")
    return engine().run(req, arm)


@app.get("/items/{item_id}")
def item(item_id: str) -> dict:
    e = engine()
    pos = e.catalog.pos(item_id)
    if pos is None:
        raise HTTPException(404, "unknown item")
    row = e.catalog.items.iloc[pos].to_dict()
    row["design_scores"] = {el.id: float(e.design_matrix(ARMS["full"])[pos, j]) for j, el in enumerate(e.kansei.elements)}
    return {k: (None if (isinstance(v, float) and v != v) else v) for k, v in row.items() if k != "outfit_ids"}


@app.get("/images/{item_id}")
def image(item_id: str):
    e = engine()
    pos = e.catalog.pos(item_id)
    if pos is None:
        raise HTTPException(404, "unknown item")
    return FileResponse(e.catalog.image_paths()[pos])
