"""Complete-the-look: given anchor item(s), recommend items of *other* categories that go with them.

Two stages, type-then-item, following Amazon P-Companion (Hao et al., CIKM 2020,
doi 10.1145/3340531.3412732: first predict complementary product *types*, then pick items within
each type):

1. **Category selection** — rank coarse categories c ∉ categories(anchors) by the mean normalised
   PMI of outfit co-occurrence NPMI(c, category(a)) over anchors (``compat.CategoryCooccurrence``).
   Category-level NPMI is useless for ranking items inside a category (FITB 25% = chance,
   docs/engine02-design.md §3.5c) but that is exactly the question it answers here.
2. **Item ranking inside each category**, one of
   - ``random``      — control;
   - ``similarity``  — mean image-embedding cosine to the anchors (a *similarity*, not compatibility, baseline);
   - ``ot``          — OutfitTransformer compatibility P(compatible | anchors + candidate)
                       (Sarkar et al., "OutfitTransformer", WACV 2023; owj0421 CLIP re-implementation);
   - ``ot_sim``      — z(ot) + w·z(similarity), z over the candidate set;
   - ``ot_cir``      — OutfitTransformer complementary-item-retrieval head: −‖embed_query(anchors) − embed_item(c)‖₂.
   Every result carries ``contributions`` whose values sum exactly to ``score``.

``FastOutfitTransformer`` precomputes the CLIP item embeddings once per item
(``precompute_clip_embedding`` + ``use_precomputed_embedding=True``, as the repo's own test scripts do),
so scoring 100 candidates is one small transformer batch instead of 100 image encodings.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from .catalog import Catalog
from .compat import CategoryCooccurrence
from .fusion import zscore

APPAREL = ("top", "bottom", "outerwear", "dress", "shoes", "bag")
METHODS = ("random", "similarity", "ot", "ot_sim", "ot_cir")
ROOT = Path(__file__).resolve().parents[1]
OT_DIR = ROOT / "third_party" / "outfit-transformer"


# ---------------------------------------------------------------------------
# category statistics
# ---------------------------------------------------------------------------
def outfits_of(items) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for pos, ids in enumerate(items["outfit_ids"]):
        for o in (ids if ids is not None else []):
            out.setdefault(str(o), []).append(pos)
    return out


def cooccurrence_from_outfits(items, exclude_outfits: Iterable[str] = ()) -> CategoryCooccurrence:
    """Pair counts counts[a][b] (a ≤ b) over outfits, same definition as the shipped
    category_cooccurrence.json, but with held-out outfits removed (no test leakage)."""
    skip = set(map(str, exclude_outfits))
    counts: dict[str, dict[str, float]] = {}
    cats = items["category"].tolist()
    for oid, members in outfits_of(items).items():
        if oid in skip:
            continue
        cs = [cats[p] for p in members if cats[p]]
        for x in range(len(cs)):
            for y in range(x + 1, len(cs)):
                a, b = sorted((cs[x], cs[y]))
                counts.setdefault(a, {})[b] = counts.get(a, {}).get(b, 0.0) + 1.0
    return CategoryCooccurrence(counts)


def rank_categories(anchor_categories: list[str], cooc: CategoryCooccurrence,
                    allowed: Iterable[str] = APPAREL) -> list[tuple[str, float]]:
    """Complementary categories sorted by mean NPMI to the anchors; anchor categories excluded
    (same category = substitute, not complement)."""
    own = {c for c in anchor_categories if c}
    scored = []
    for c in allowed:
        if c in own:
            continue
        vals = [cooc.npmi(c, a) for a in anchor_categories if a]
        scored.append((c, float(np.mean(vals)) if vals else 0.0))
    return sorted(scored, key=lambda kv: -kv[1])


# ---------------------------------------------------------------------------
# OutfitTransformer with precomputed item embeddings
# ---------------------------------------------------------------------------
class FastOutfitTransformer:
    """Loads the compatibility and/or complementary checkpoints of owj0421/outfit-transformer.

    Loading mirrors engine02/compat_ot.py; item CLIP embeddings are cached in memory and optionally on disk.
    """

    name = "outfit-transformer"

    _HEAD_PATTERNS = {"compatibility": "compatib", "complementary": "complementary"}

    @classmethod
    def checkpoints(cls, ot_dir: Path = OT_DIR) -> dict[str, list[Path]]:
        """Which heads have a checkpoint on this machine — lets callers ask for only what is there."""
        files = sorted((Path(ot_dir) / "checkpoints").rglob("*.pt*"))
        found = {h: [p for p in files if pat in p.name.lower()] for h, pat in cls._HEAD_PATTERNS.items()}
        return {h: v for h, v in found.items() if v}

    def __init__(self, catalog: Catalog, device: str = "auto", ot_dir: Path = OT_DIR,
                 heads: tuple[str, ...] = ("compatibility",), batch_size: int = 64, cache_file: Path | None = None):
        import torch
        from PIL import Image

        from .models import pick_device

        self.torch, self.Image = torch, Image
        self.catalog = catalog
        self._paths = catalog.image_paths()
        self.device = pick_device(device)
        self.batch_size = batch_size
        sys.path.insert(0, str(ot_dir))
        try:
            import cv2  # noqa: F401
        except ImportError:
            sys.modules["cv2"] = types.ModuleType("cv2")
        from src.data.datatypes import FashionCompatibilityQuery, FashionComplementaryQuery, FashionItem
        from src.models.outfit_clip_transformer import OutfitCLIPTransformer, OutfitCLIPTransformerConfig

        self.CQuery, self.RQuery, self.Item = FashionCompatibilityQuery, FashionComplementaryQuery, FashionItem
        self.models = {}
        for h in heads:
            ck = self.checkpoints(ot_dir).get(h, [])
            if not ck:
                raise FileNotFoundError(f"no {h} checkpoint under {ot_dir}/checkpoints")
            state = torch.load(ck[0], map_location=self.device, weights_only=False)
            m = OutfitCLIPTransformer(OutfitCLIPTransformerConfig(**state.get("config", {})))
            m.load_state_dict({k.replace("module.", ""): v for k, v in state["model"].items()}, strict=False)
            self.models[h] = m.to(self.device).eval()
        # the frozen CLIP item encoder is normally identical in both checkpoints → share embeddings
        self.enc_head = {h: h for h in self.models}
        if len(self.models) == 2:
            a, b = (m.item_enc.state_dict() for m in self.models.values())
            if a.keys() == b.keys() and all(torch.equal(a[x].cpu(), b[x].cpu()) for x in a):
                first = next(iter(self.models))
                self.enc_head = {h: first for h in self.models}
        self.shared_item_encoder = len(set(self.enc_head.values())) == 1
        self.heads = tuple(self.models)
        self.cache_file = Path(cache_file) if cache_file else None
        self._emb: dict[str, dict[int, np.ndarray]] = {h: {} for h in set(self.enc_head.values())}
        if self.cache_file and self.cache_file.exists():
            d = np.load(self.cache_file)
            for h in self._emb:
                if f"pos_{h}" in d:
                    self._emb[h] = {int(p): e for p, e in zip(d[f"pos_{h}"], d[f"emb_{h}"])}

    def _raw_item(self, pos: int):
        row = self.catalog.items.iloc[pos]
        img = self.Image.open(self._paths[pos]).convert("RGB")
        cat = row.get("subcategory") or row.get("category") or ""
        return self.Item(item_id=pos, image=img, category=str(cat), description=str(row["title"]))

    def ensure_embeddings(self, positions: Iterable[int], head: str | None = None) -> None:
        for h in ([self.enc_head[head]] if head else sorted(self._emb)):
            store = self._emb[h]
            todo = sorted({int(p) for p in positions} - set(store))
            with self.torch.inference_mode():
                for i in range(0, len(todo), self.batch_size):
                    chunk = todo[i : i + self.batch_size]
                    embs = self.models[h].precompute_clip_embedding([self._raw_item(p) for p in chunk])
                    for p, e in zip(chunk, embs):
                        store[p] = np.asarray(e, dtype=np.float32)

    def save_cache(self) -> None:
        if self.cache_file:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            arrs = {}
            for h, store in self._emb.items():
                if store:
                    pos = np.array(sorted(store), dtype=np.int64)
                    arrs[f"pos_{h}"] = pos
                    arrs[f"emb_{h}"] = np.stack([store[int(p)] for p in pos])
            np.savez(self.cache_file, **arrs)

    def _item(self, pos: int, head: str):
        return self.Item(item_id=int(pos), embedding=self._emb[self.enc_head[head]][int(pos)])

    def compatibility(self, anchors: list[int], cands: list[int]) -> np.ndarray:
        m = self.models["compatibility"]
        self.ensure_embeddings(list(anchors) + list(cands), "compatibility")
        a = [self._item(p, "compatibility") for p in anchors]
        out = []
        with self.torch.inference_mode():
            for i in range(0, len(cands), self.batch_size):
                qs = [self.CQuery(outfit=a + [self._item(p, "compatibility")]) for p in cands[i : i + self.batch_size]]
                out.append(m.predict_score(qs, use_precomputed_embedding=True).float().cpu().numpy().reshape(-1))
        return np.concatenate(out) if out else np.zeros(0)

    def complementary(self, anchors: list[int], cands: list[int], target_category: str = "") -> np.ndarray:
        m = self.models["complementary"]
        self.ensure_embeddings(list(anchors) + list(cands), "complementary")
        with self.torch.inference_mode():
            q = m.embed_query([self.RQuery(outfit=[self._item(p, "complementary") for p in anchors],
                                           category=target_category)], use_precomputed_embedding=True)
            out = []
            for i in range(0, len(cands), self.batch_size):
                e = m.embed_item([self._item(p, "complementary") for p in cands[i : i + self.batch_size]],
                                 use_precomputed_embedding=True)
                out.append((-self.torch.norm(e - q, dim=-1)).float().cpu().numpy())
        return np.concatenate(out) if out else np.zeros(0)

    # engine02.pipeline compat_model protocol
    def score(self, anchor_positions: list[int], cand_positions: list[int]) -> np.ndarray:
        return self.compatibility(list(anchor_positions), list(cand_positions))


# ---------------------------------------------------------------------------
@dataclass
class ScoredItem:
    position: int
    item_id: str
    score: float
    contributions: dict[str, float]  # sums to score


@dataclass
class CategorySlate:
    category: str
    category_score: float  # mean NPMI to the anchors
    items: list[ScoredItem] = field(default_factory=list)


class CompleteTheLook:
    def __init__(self, catalog: Catalog, image_emb: np.ndarray, cooc: CategoryCooccurrence,
                 ot: FastOutfitTransformer | None = None, sim_weight: float = 0.5, seed: int = 0):
        self.catalog = catalog
        self.emb = np.asarray(image_emb, dtype=np.float64)
        self.cooc = cooc
        self.ot = ot
        self.sim_weight = sim_weight
        self.rng = np.random.default_rng(seed)

    def target_categories(self, anchors: list[int], top_n: int = 2, allowed: Iterable[str] = APPAREL):
        cats = [self.catalog.attr(a, "category") for a in anchors]
        return rank_categories(cats, self.cooc, allowed)[:top_n]

    def score_items(self, anchors: list[int], cands: list[int], method: str,
                    target_category: str = "") -> tuple[np.ndarray, list[dict[str, float]]]:
        cands = [int(c) for c in cands]
        if method == "random":
            s = self.rng.random(len(cands))
            return s, [{"random": float(v)} for v in s]
        sim = (self.emb[cands] @ self.emb[anchors].T).mean(axis=1)
        if method == "similarity":
            return sim, [{"similarity": float(v)} for v in sim]
        if self.ot is None:
            raise RuntimeError(f"method {method!r} needs an OutfitTransformer")
        if method == "ot_cir":
            s = self.ot.complementary(anchors, cands, target_category)
            return s, [{"complementary:outfit-transformer": float(v)} for v in s]
        ot = self.ot.compatibility(anchors, cands)
        if method == "ot":
            return ot, [{"compat:outfit-transformer": float(v)} for v in ot]
        if method == "ot_sim":
            a, b = zscore(ot), self.sim_weight * zscore(sim)
            return a + b, [{"compat:outfit-transformer": float(x), "similarity": float(y)} for x, y in zip(a, b)]
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")

    def recommend(self, anchor_ids: list[str], n_categories: int = 2, k: int = 5, method: str = "ot_sim",
                  prefilter: int = 50, exclude_ids: Iterable[str] = (), filters: dict[str, list[str]] | None = None,
                  categories: list[str] | None = None) -> list[CategorySlate]:
        """Per complementary category: prefilter `prefilter` items by similarity to the anchors
        (cheap), then rank them with `method`. `filters` = hard attribute filters, e.g. {"gender": ["Women"]}."""
        items = self.catalog.items
        anchors = self.catalog.positions(anchor_ids)
        if not anchors:
            return []
        skip = set(anchors) | set(self.catalog.positions(list(exclude_ids)))
        if categories:
            cats = [(c, float(np.mean([self.cooc.npmi(c, self.catalog.attr(a, "category")) for a in anchors])))
                    for c in categories]
        else:
            cats = self.target_categories(anchors, n_categories)
        mask = np.ones(len(items), dtype=bool)
        for col, vals in (filters or {}).items():
            if col in items.columns and vals:
                mask &= items[col].isin(vals).to_numpy()
        out = []
        for c, cscore in cats:
            pool = np.flatnonzero(mask & (items["category"] == c).to_numpy())
            pool = np.array([p for p in pool if p not in skip], dtype=int)
            if len(pool) == 0:
                out.append(CategorySlate(c, cscore))
                continue
            sim = (self.emb[pool] @ self.emb[anchors].T).mean(axis=1)
            pool = pool[np.argsort(-sim, kind="stable")[:prefilter]]
            s, contribs = self.score_items(anchors, list(pool), method, c)
            order = np.argsort(-s, kind="stable")[:k]
            out.append(CategorySlate(c, cscore, [
                ScoredItem(int(pool[i]), str(items.at[int(pool[i]), "item_id"]), float(s[i]), contribs[i])
                for i in order
            ]))
        return out
