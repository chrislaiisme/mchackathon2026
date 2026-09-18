"""Image/text encoders behind one protocol, with an on-disk embedding cache.

Real model loaders live in `load_encoder`; they follow the usage verified in
reports/model_verification.md. `HashEncoder` is a deterministic stand-in for tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

import numpy as np


class Encoder(Protocol):
    name: str
    dim: int

    def encode_text(self, texts: list[str]) -> np.ndarray: ...  # (n, dim), L2-normalised

    def encode_images(self, paths: list[Path]) -> np.ndarray: ...  # (n, dim), L2-normalised


def l2n(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return x / np.clip(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12, None)


class HashEncoder:
    """Bag-of-words hashing encoder: texts and 'images' (via a sidecar caption) share a space.

    Only for unit tests — lets the pipeline run without downloading models.
    """

    def __init__(self, dim: int = 64, captions: dict[str, str] | None = None):
        self.name = f"hash-{dim}"
        self.dim = dim
        self.captions = captions or {}

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) % 2 else -1.0
        return v

    def encode_text(self, texts: list[str]) -> np.ndarray:
        return l2n(np.stack([self._vec(t) for t in texts])) if texts else np.zeros((0, self.dim), np.float32)

    def encode_images(self, paths: list[Path]) -> np.ndarray:
        return self.encode_text([self.captions.get(Path(p).name, Path(p).stem) for p in paths])


def cached_image_embeddings(encoder: Encoder, paths: list[Path], cache_file: Path, batch: int = 64) -> np.ndarray:
    cache_file = Path(cache_file)
    if cache_file.exists():
        emb = np.load(cache_file)
        if emb.shape[0] == len(paths):
            return emb
    chunks = [encoder.encode_images(paths[i : i + batch]) for i in range(0, len(paths), batch)]
    emb = np.concatenate(chunks) if chunks else np.zeros((0, encoder.dim), np.float32)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache_file, emb)
    return emb
