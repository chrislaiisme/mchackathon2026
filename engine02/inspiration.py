"""Inspiration library: runway / street / cosplay photos from Wikimedia Commons, kept APART from the
product catalog.

Why a separate store and not extra catalog rows: the catalog's design scores are z-scored over the
catalog (engine02.pipeline.design_matrix), so adding full-body photos of people on a catwalk would
shift every product's z and change every card's explanation. Here a photo is only ever a *query*:
its embedding goes to /rank as `feedback.concept_image_embedding` (weight 0.2 on the serving arm,
§3.16), exactly the path /visual-search uses for an uploaded photo.

Layout (written by scripts/build_inspiration.py):

    <dir>/items.parquet                  insp_id, group, title, image_path, image_url, page_url,
                                         license, license_url, author
    <dir>/images/<insp_id>.jpg           384 px thumbnails
    <dir>/index/img_<encoder>.npy        (n, dim) L2-normalised, row order = items.parquet
    <dir>/index/meta_<encoder>.json      {"encoder_name", "dim", "n", "insp_ids"}

The embedding must come from the SAME encoder the service indexed the catalog with; a different
encoder with the same dimension would still be a different space, so the guard checks the encoder
name as well as the dimension.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

GROUPS = {
    "runway": {"label": "伸展台", "photo": "伸展台照片", "categories": ["Catwalks (fashion)"]},
    "street": {"label": "街頭穿搭", "photo": "街拍照片", "categories": ["Street fashion"]},
    "cosplay": {"label": "角色扮演", "photo": "Cosplay 照片", "categories": ["Cosplayers"]},
}
COLUMNS = ["insp_id", "group", "title", "image_path", "image_url", "page_url", "license", "license_url",
           "author"]


class InspirationError(RuntimeError):
    """The inspiration store is missing, stale or was built with another encoder."""


def encoder_key(name: str) -> str:
    """File-name-safe form of an encoder argument ("marqo-fashionSigLIP", "hash", "org/model")."""
    return name.replace("/", "__").replace("\\", "__")


@dataclass
class Inspiration:
    root: Path
    items: pd.DataFrame
    encoder: str                           # the --encoder / ENGINE02_ENCODER key the index was built for
    _emb: np.ndarray | None = field(default=None, repr=False)
    _meta: dict | None = field(default=None, repr=False)
    _pos: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.items = self.items.reset_index(drop=True)
        missing = [c for c in COLUMNS if c not in self.items.columns]
        if missing:
            raise InspirationError(f"{self.root / 'items.parquet'} lacks columns {missing}")
        self._pos = {str(i): p for p, i in enumerate(self.items["insp_id"].astype(str))}

    # ---- paths --------------------------------------------------------------------------------
    @property
    def emb_file(self) -> Path:
        return self.root / "index" / f"img_{encoder_key(self.encoder)}.npy"

    @property
    def meta_file(self) -> Path:
        return self.root / "index" / f"meta_{encoder_key(self.encoder)}.json"

    def __len__(self) -> int:
        return len(self.items)

    # ---- rows ---------------------------------------------------------------------------------
    def pos(self, insp_id: str) -> int | None:
        return self._pos.get(str(insp_id))

    def row(self, insp_id: str) -> dict | None:
        p = self.pos(insp_id)
        if p is None:
            return None
        return {k: (None if (isinstance(v, float) and v != v) else v)
                for k, v in self.items.iloc[p][COLUMNS].to_dict().items()}

    def image_file(self, insp_id: str) -> Path | None:
        r = self.row(insp_id)
        return None if r is None else self.root / str(r["image_path"])

    def counts(self) -> dict[str, int]:
        return {str(k): int(v) for k, v in self.items["group"].value_counts().sort_index().items()}

    def list_items(self, group: str | None = None, limit: int = 30, offset: int = 0) -> list[dict]:
        if group is not None and group not in GROUPS:
            raise ValueError(f"unknown group {group!r}; one of {sorted(GROUPS)}")
        df = self.items if group is None else self.items[self.items["group"] == group]
        df = df.iloc[max(0, offset): max(0, offset) + max(0, limit)]
        return [self.row(i) for i in df["insp_id"].astype(str)]

    # ---- embeddings (lazy) --------------------------------------------------------------------
    def meta(self) -> dict:
        if self._meta is None:
            if not self.meta_file.exists():
                raise InspirationError(
                    f"no inspiration index for encoder {self.encoder!r} at {self.meta_file}; run "
                    f"scripts/build_inspiration.py --encoder {self.encoder} --out {self.root}")
            self._meta = json.loads(self.meta_file.read_text(encoding="utf-8"))
        return self._meta

    def embeddings(self) -> np.ndarray:
        if self._emb is None:
            meta = self.meta()
            if not self.emb_file.exists():
                raise InspirationError(f"missing {self.emb_file}; rebuild with scripts/build_inspiration.py")
            emb = np.load(self.emb_file)
            if emb.ndim != 2 or emb.shape[0] != len(self.items):
                raise InspirationError(f"{self.emb_file} has shape {emb.shape} but items.parquet has "
                                       f"{len(self.items)} rows; rebuild the index")
            if list(meta.get("insp_ids") or []) != self.items["insp_id"].astype(str).tolist():
                raise InspirationError("index row order does not match items.parquet; rebuild the index")
            self._emb = emb.astype(np.float32, copy=False)
        return self._emb

    @property
    def dim(self) -> int:
        return int(self.embeddings().shape[1])

    def check_compatible(self, expected_dim: int, encoder_name: str | None = None) -> None:
        """Raise unless this index lives in the catalog encoder's space."""
        got = self.dim
        if got != int(expected_dim):
            raise InspirationError(
                f"inspiration embeddings have {got} dims but the catalog encoder "
                f"{encoder_name or '?'} has {expected_dim}; rebuild with the service's encoder "
                f"(scripts/build_inspiration.py --encoder <ENGINE02_ENCODER>)")
        built = self.meta().get("encoder_name")
        if encoder_name and built and built != encoder_name:
            raise InspirationError(
                f"inspiration index was built with encoder {built!r} but the service runs "
                f"{encoder_name!r}; same dimension, different space — rebuild the index")

    def embedding(self, insp_id: str, expected_dim: int | None = None,
                  encoder_name: str | None = None) -> np.ndarray:
        p = self.pos(insp_id)
        if p is None:
            raise KeyError(insp_id)
        if expected_dim is not None:
            self.check_compatible(expected_dim, encoder_name)
        return self.embeddings()[p]


def load(path: str | Path, encoder: str = "marqo-fashionSigLIP") -> Inspiration:
    """Items now, embeddings on first use."""
    root = Path(path)
    f = root / "items.parquet"
    if not f.exists():
        raise InspirationError(f"no inspiration library at {root}; run scripts/build_inspiration.py")
    return Inspiration(root=root, items=pd.read_parquet(f), encoder=encoder)


def write_index(root: str | Path, items: pd.DataFrame, encoder, key: str, batch: int = 32) -> np.ndarray:
    """Write items.parquet and embed every image with `encoder` into index/img_<key>.npy (+ meta)."""
    root = Path(root)
    items = items[COLUMNS].reset_index(drop=True)
    paths = [root / p for p in items["image_path"].astype(str)]
    chunks = [encoder.encode_images(paths[i: i + batch]) for i in range(0, len(paths), batch)]
    emb = np.concatenate(chunks).astype(np.float32) if chunks else np.zeros((0, encoder.dim), np.float32)
    save_index(root, items, emb, encoder.name, key)
    return emb


def save_index(root: str | Path, items: pd.DataFrame, emb: np.ndarray, encoder_name: str, key: str) -> None:
    """items.parquet + index/img_<key>.npy + index/meta_<key>.json, rows in the same order."""
    root = Path(root)
    items = items[COLUMNS].reset_index(drop=True)
    if len(items) != len(emb):
        raise ValueError(f"{len(items)} items but {len(emb)} embeddings")
    (root / "index").mkdir(parents=True, exist_ok=True)
    items.to_parquet(root / "items.parquet", index=False)
    np.save(root / "index" / f"img_{encoder_key(key)}.npy", emb.astype(np.float32))
    meta = {"encoder_name": encoder_name, "encoder_key": key, "dim": int(emb.shape[1]) if emb.ndim == 2 else 0,
            "n": int(len(items)), "insp_ids": items["insp_id"].astype(str).tolist()}
    (root / "index" / f"meta_{encoder_key(key)}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                                                   encoding="utf-8")


# ---- content screen ---------------------------------------------------------------------------
# A Commons category holds more than outfits: event posters, panel talks, audiences, shop
# interiors, face close-ups -- and some swimwear / lingerie shots. Any of those used as
# "我想要這種感覺" would steer the ranking somewhere no one asked for, so each photo is compared, in the same
# image-text space the service ranks in, with one description of what we want and several of what
# we do not. Checked by eye on the 450-photo 2026-09-19 build (contact sheets of every drop and of
# the kept photos nearest each threshold).
SCREEN_KEEP = ["a full-body photo of a person wearing a fashionable outfit",
               "a model walking on a runway in a designer outfit",
               "a cosplayer in a full costume",
               "a street style photo of a stylish person"]
SCREEN_REJECT = {
    "text": ["a poster, logo, sign or text"],
    "crowd": ["a crowd or audience seen from far away", "a group photo of many people"],
    "face": ["a close-up portrait of a face"],
    "object": ["an empty room, shop interior, machine or object with no person"],
    "display": ["clothes on a mannequin or on display in a shop"],
    "talk": ["a person giving a talk or presentation"],
    "revealing": ["a person in a bikini, swimsuit, lingerie or underwear"],
}
SCREEN_MIN_P_OUTFIT = 0.95       # softmax over the best score per label, logit scale 100
SCREEN_MAX_REVEALING = -1.0      # revealing score minus outfit score (logit units); above -> dropped


def screen(emb: np.ndarray, encoder) -> tuple[np.ndarray, list[dict]]:
    """(keep mask, per-photo {"label", "p_outfit", "revealing_margin"}) for L2-normalised image
    embeddings. Needs a real image-text encoder: with the hash test encoder everything is kept."""
    n = len(emb)
    if n == 0 or str(getattr(encoder, "name", "")).startswith("hash"):
        return np.ones(n, bool), [{"label": "outfit", "p_outfit": None, "revealing_margin": None}] * n
    labels = ["outfit"] * len(SCREEN_KEEP) + [k for k, v in SCREEN_REJECT.items() for _ in v]
    texts = SCREEN_KEEP + [t for v in SCREEN_REJECT.values() for t in v]
    sim = (emb @ encoder.encode_text(texts).T) * 100.0
    lab = np.array(labels)
    keys = ["outfit", *SCREEN_REJECT]
    best = np.stack([sim[:, lab == k].max(1) for k in keys], 1)
    p = np.exp(best - best.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    top = p.argmax(1)
    rev = best[:, keys.index("revealing")] - best[:, 0]
    keep = (top == 0) & (p[:, 0] >= SCREEN_MIN_P_OUTFIT) & (rev <= SCREEN_MAX_REVEALING)
    info = [{"label": keys[t] if t != 0 or k else ("revealing" if r > SCREEN_MAX_REVEALING else "low_confidence"),
             "p_outfit": round(float(po), 4), "revealing_margin": round(float(r), 2)}
            for t, k, po, r in zip(top, keep, p[:, 0], rev)]
    return keep, info
