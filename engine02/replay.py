"""Offline replay for the demo (PRD §8「斷網重播模式」, listed as 必做 and not implemented anywhere).

ENGINE 02 itself already survives losing the network — the encoder weights and the image
embeddings are on disk, and `engine02.explain` falls back to the template sentence whenever the
LLM call raises. What it cannot do offline is reproduce a *previous* run byte for byte, which is
what a demo fallback needs: the same five cards, the same reasons, the same LLM-written sentence,
for the same request, with the network unplugged.

This module is that record/replay layer. It wraps any `request → response` callable
(`Engine02.run`, `Engine02Service.rank`) without touching it:

    store = ReplayStore("artifacts/replay/demo", mode="record")   # rehearsal, network up
    ranked = store.wrap(service.rank)
    ...
    store = ReplayStore("artifacts/replay/demo", mode="replay")   # on stage, network down
    ranked = store.wrap(service.rank)                             # identical output, no model call

Design notes
------------
* The key is a SHA-256 of the canonical JSON of the request, **excluding fields that must not
  change the answer**: `contract_version` and `session_id` (a rehearsal and the live demo have
  different session ids but the same question). `round`, constraints, needs and the whole feedback
  ledger are all part of the key, so round 2 never replays round 1's answer.
* `mode="auto"` replays a hit and records a miss — the safest setting for a live demo: anything
  rehearsed is served from disk, anything new is computed and added.
* `mode="replay"` with `strict=True` raises on a miss instead of silently computing something
  different (and slower) on stage. `strict=False` falls back to the live call.
* Records are plain JSON (`{"request": ..., "response": ..., "response_type": ..., "recorded_at": ...}`),
  so they can be inspected, diffed and committed if a frozen demo script is wanted.
* Nothing here is in the ranking path: with `mode="off"` `wrap` returns the original callable.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel

from .contracts import Engine02Request, Engine02Response

MODES = ("off", "record", "replay", "auto")
# fields whose value must not change the cached answer
VOLATILE = ("contract_version", "session_id")


def _response_models() -> dict[str, type[BaseModel]]:
    models: dict[str, type[BaseModel]] = {"Engine02Response": Engine02Response}
    try:  # optional: the service/diversification subclasses carry extra fields
        from .diversify import DiversifiedResponse

        models["DiversifiedResponse"] = DiversifiedResponse
    except Exception:  # pragma: no cover
        pass
    try:
        from .service import ServiceResponse

        models["ServiceResponse"] = ServiceResponse
    except Exception:  # pragma: no cover
        pass
    return models


def request_key(req: Engine02Request, arm: str | None = None) -> str:
    """Stable SHA-256 over the request content that actually determines the answer."""
    data: dict[str, Any] = json.loads(req.model_dump_json())
    for f in VOLATILE:
        data.pop(f, None)
    payload = {"arm": arm, "request": data}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


class ReplayMiss(KeyError):
    """Raised in strict replay mode when a request was never recorded."""


class ReplayStore:
    def __init__(self, path: str | Path, mode: Literal["off", "record", "replay", "auto"] = "off",
                 strict: bool = True):
        if mode not in MODES:
            raise ValueError(f"unknown replay mode {mode!r}; expected one of {MODES}")
        self.path = Path(path)
        self.mode = mode
        self.strict = strict
        self.stats = {"hit": 0, "miss": 0, "recorded": 0}
        if mode in ("record", "auto"):
            self.path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def _file(self, key: str) -> Path:
        return self.path / f"{key}.json"

    def has(self, req: Engine02Request, arm: str | None = None) -> bool:
        return self._file(request_key(req, arm)).exists()

    def load(self, req: Engine02Request, arm: str | None = None) -> BaseModel:
        f = self._file(request_key(req, arm))
        if not f.exists():
            raise ReplayMiss(f"no recorded response for this request (arm={arm!r}) in {self.path}")
        raw = json.loads(f.read_text(encoding="utf-8"))
        models = _response_models()
        model = models.get(raw.get("response_type", "Engine02Response"), Engine02Response)
        resp = model.model_validate(raw["response"])
        # keep the caller's session id: replaying a rehearsal must not rewrite the live session
        if hasattr(resp, "session_id"):
            resp.session_id = req.session_id
        return resp

    def save(self, req: Engine02Request, resp: BaseModel, arm: str | None = None) -> Path:
        self.path.mkdir(parents=True, exist_ok=True)
        f = self._file(request_key(req, arm))
        f.write_text(json.dumps({
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "arm": arm,
            "response_type": type(resp).__name__,
            "request": json.loads(req.model_dump_json()),
            "response": json.loads(resp.model_dump_json()),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stats["recorded"] += 1
        return f

    # ------------------------------------------------------------------
    def wrap(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Return a drop-in replacement for ``fn(req, arm=None)``."""
        if self.mode == "off":
            return fn

        def call(req: Engine02Request, arm: str | None = None, **kw):
            if self.mode in ("replay", "auto") and self.has(req, arm):
                self.stats["hit"] += 1
                return self.load(req, arm)
            self.stats["miss"] += 1
            if self.mode == "replay" and self.strict:
                raise ReplayMiss(
                    f"strict replay: this request was not rehearsed (key {request_key(req, arm)[:12]}…). "
                    f"Record it first, or construct ReplayStore(..., strict=False)."
                )
            resp = fn(req, arm, **kw) if arm is not None else fn(req, **kw)
            if self.mode in ("record", "auto"):
                self.save(req, resp, arm)
            return resp

        call.__name__ = f"replay_{getattr(fn, '__name__', 'call')}"
        call.__doc__ = (fn.__doc__ or "") + f"\n\n[replay: mode={self.mode}, store={self.path}]"
        return call

    # ------------------------------------------------------------------
    def manifest(self) -> dict:
        """What has been rehearsed — print this before going on stage."""
        rows = []
        for f in sorted(self.path.glob("*.json")):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # pragma: no cover
                continue
            req = raw.get("request", {})
            rows.append({"key": f.stem[:12], "arm": raw.get("arm"), "round": req.get("round"),
                         "utterances": req.get("utterances", []),
                         "n_items": len(raw.get("response", {}).get("items", [])),
                         "recorded_at": raw.get("recorded_at")})
        return {"path": str(self.path), "mode": self.mode, "n_records": len(rows),
                "stats": dict(self.stats), "records": rows}
