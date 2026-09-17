"""Composed retrieval for critiques on a shown item: "this one, but more casual / in navy blue".

The judge (or user) points at a reference item r and states a change. Five training-free,
LLM-free ways to turn (r, critique, base query) into a retrieval query:

1. ``critique_filter``   current ENGINE 02 behaviour: add/replace a hard constraint
                         (color=Navy Blue) and keep the base text query.
2. ``text_rewrite``      CIReVL-style (Karthik et al., "Vision-by-Language for Training-Free
                         Compositional Image Retrieval", ICLR 2024) without the LLM: the
                         reference "caption" is its catalog title / metadata, the attribute is
                         replaced by a template, and retrieval is text→image only.
3. ``image_plus_text``   CLIP4Cir element-wise sum baseline on bare CLIP features (Baldrati et al.,
                         "Composed Image Retrieval using Contrastive Learning and Task-oriented
                         CLIP-based Features", ACM TOMM 2023, arXiv:2308.11485), weighted:
                         q = norm(α·img(r) + (1−α)·txt(target phrase)).
4. ``vector_arithmetic`` q = img(r) + λ·(txt(to) − txt(from)); an attribute direction in the joint
                         space, the embedding-space analogue of latent linear critiquing
                         (Luo et al., WWW 2020) and TIRG's residual modification (Vo et al., CVPR 2019).
5. ``ref_plus_filter``   q = img(r) inside a hard filter on the changed attribute (hybrid of 1 and 3).
   ``image_plus_text_filter`` = 3 inside the same filter.

Option 6 (dense composed vector + BM25 over the rewritten text, fused by RRF inside the normal
pipeline) is :class:`ComposedEngine02.run_composed` with a fusion arm such as ``hybrid_rrf``.

LLM hook: every text method gets its target description from a :class:`Rewriter`.
:class:`TemplateRewriter` is the default; :class:`LLMRewriter` wraps any ``Callable[[str], str]``
with the CIReVL prompt and falls back to the template when the output drops the new value
or keeps the old one (same fact-check policy as ``engine02.explain``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol

import numpy as np

from .constraints import filter_with_relaxation
from .contracts import Engine02Request, Engine02Response, HardConstraints, Slot, SlotState
from .encoders import l2n
from .pipeline import Engine02

Method = Literal[
    "critique_filter", "text_rewrite", "image_plus_text", "vector_arithmetic", "ref_plus_filter",
    "image_plus_text_filter",
]
METHODS: tuple[str, ...] = (
    "critique_filter", "text_rewrite", "image_plus_text", "vector_arithmetic", "ref_plus_filter",
    "image_plus_text_filter",
)
FILTER_METHODS = {"critique_filter", "ref_plus_filter", "image_plus_text_filter"}

# direction words → (attribute, catalog value). KAGL `occasion` vocabulary.
DIRECTIONS: dict[str, tuple[str, str]] = {
    "more_formal": ("occasion", "Formal"),
    "more_casual": ("occasion", "Casual"),
    "sportier": ("occasion", "Sports"),
}
OCCASION_WORD = {"Formal": "formal", "Casual": "casual", "Sports": "sports", "Ethnic": "ethnic",
                 "Smart Casual": "smart casual", "Travel": "travel"}

# Colour families for "change to a different colour" (KAGL baseColour vocabulary).
COLOR_FAMILY: dict[str, str] = {}
for fam, cols in {
    "black_grey": ["Black", "Grey", "Charcoal", "Grey Melange", "Steel"],
    "white_cream": ["White", "Off White", "Cream", "Beige", "Skin"],
    "blue": ["Blue", "Navy Blue", "Teal", "Turquoise Blue"],
    "red": ["Red", "Maroon", "Burgundy", "Rust"],
    "pink_purple": ["Pink", "Peach", "Rose", "Magenta", "Purple", "Lavender", "Mauve"],
    "green": ["Green", "Olive", "Sea Green", "Lime Green", "Fluorescent Green"],
    "yellow_orange": ["Yellow", "Mustard", "Orange", "Gold"],
    "brown": ["Brown", "Tan", "Khaki", "Coffee Brown", "Taupe", "Bronze", "Copper"],
}.items():
    for c in cols:
        COLOR_FAMILY[c] = fam


@dataclass
class Critique:
    """Structured critique on a reference item (proposed contract: ``FeedbackState.critique``)."""

    attribute: str  # catalog column: "color" | "occasion" | ...
    to_value: str | None = None  # catalog vocabulary, e.g. "Navy Blue"
    from_value: str | None = None  # defaults to the reference item's value
    direction: str | None = None  # e.g. "more_casual"; resolves to_value when it is None

    def resolved(self, ref_row) -> "Critique":
        attr, to = self.attribute, self.to_value
        if to is None and self.direction in DIRECTIONS:
            attr, to = DIRECTIONS[self.direction]
        frm = self.from_value
        if frm is None and attr in ref_row.index:
            v = ref_row[attr]
            frm = None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
        return Critique(attribute=attr, to_value=to, from_value=frm, direction=self.direction)


@dataclass
class ComposedQuery:
    method: str
    retrieval_text: str  # text for BM25 / text encoder (base query for critique_filter)
    query_embedding: np.ndarray | None  # None → pipeline encodes retrieval_text as usual
    constraint_updates: dict[str, list[str]] = field(default_factory=dict)  # hard slots to set
    exclude_item_ids: list[str] = field(default_factory=list)  # the reference itself
    target_text: str = ""  # rewritten target description (for display / logging)
    params: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rewriters (template now, LLM later)
# ---------------------------------------------------------------------------


class Rewriter(Protocol):
    def rewrite(self, ref_row, critique: Critique, base_query: str) -> str: ...


def _replace_ci(text: str, old: str, new: str) -> tuple[str, bool]:
    pat = re.compile(rf"\b{re.escape(old)}\b", re.IGNORECASE)
    out, n = pat.subn(new, text)
    return out, n > 0


def _s(v) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)


class TemplateRewriter:
    """CIReVL step 2 without an LLM.

    source="title": catalog title with the old value replaced (keeps pattern / fit words such as
                    "Printed", "Check", "Slim Fit"); if the old value is absent, the new one is prefixed.
    source="meta":  "{gender} {color} {subcategory} for {occasion}" rebuilt from metadata (T1 wording).
    """

    def __init__(self, source: Literal["title", "meta"] = "title"):
        self.source = source

    def rewrite(self, ref_row, critique: Critique, base_query: str = "") -> str:
        c = critique.resolved(ref_row)
        if self.source == "meta":
            vals = {a: _s(ref_row.get(a)) for a in ("gender", "color", "subcategory", "occasion")}
            vals[c.attribute] = _s(c.to_value)
            occ = OCCASION_WORD.get(vals["occasion"], vals["occasion"].lower())
            head = " ".join(v for v in (vals["gender"], vals["color"], vals["subcategory"]) if v)
            return f"{head} for {occ}" if occ else head
        title = _s(ref_row.get("title")) or _s(ref_row.get("subcategory"))
        if c.attribute == "occasion":
            word = OCCASION_WORD.get(_s(c.to_value), _s(c.to_value).lower())
            if c.from_value:
                old = OCCASION_WORD.get(c.from_value, c.from_value.lower())
                title, _ = _replace_ci(title, old, word)
            return f"{word} {title}".strip()
        if c.from_value:
            out, hit = _replace_ci(title, c.from_value, _s(c.to_value))
            if hit:
                return out
        return f"{_s(c.to_value)} {title}".strip()


CIREVL_PROMPT = (
    "You edit product descriptions for image search.\n"
    "Reference item: {caption}\n"
    "Requested change: set {attribute} to '{to_value}' (was '{from_value}').\n"
    "Write ONE short English description of the target item: keep everything else about the reference "
    "item, apply the change, no negations, no brand names. Output only the description."
)


class LLMRewriter:
    """CIReVL (ICLR 2024) step 2 with a real LLM. ``llm`` is any prompt → text callable
    (same signature as ``Engine02(llm=...)``). Falls back to ``fallback`` when the output is empty,
    does not mention the new value, or still mentions the old value."""

    def __init__(self, llm: Callable[[str], str], fallback: Rewriter | None = None):
        self.llm = llm
        self.fallback = fallback or TemplateRewriter("title")
        self.last_source = "template"

    def rewrite(self, ref_row, critique: Critique, base_query: str = "") -> str:
        c = critique.resolved(ref_row)
        prompt = CIREVL_PROMPT.format(caption=_s(ref_row.get("title")), attribute=c.attribute,
                                      to_value=_s(c.to_value), from_value=_s(c.from_value))
        try:
            out = (self.llm(prompt) or "").strip().splitlines()[0].strip()
        except Exception:  # noqa: BLE001 — any LLM failure → template
            out = ""
        to_word = _s(c.to_value).lower()
        if c.attribute == "occasion":
            to_word = OCCASION_WORD.get(_s(c.to_value), to_word)
        ok = bool(out) and to_word in out.lower()
        if ok and c.from_value and c.from_value.lower() != to_word:
            ok = not re.search(rf"\b{re.escape(c.from_value.lower())}\b", out.lower())
        if ok:
            self.last_source = "llm"
            return out
        self.last_source = "template"
        return self.fallback.rewrite(ref_row, critique, base_query)


# ---------------------------------------------------------------------------
# Query composition
# ---------------------------------------------------------------------------


def direction_phrases(ref_row, c: Critique) -> tuple[str, str]:
    """(to phrase, from phrase) for vector arithmetic, e.g. ("navy blue shirts", "black shirts")."""
    sub = _s(ref_row.get("subcategory")).lower()
    if c.attribute == "occasion":
        to = OCCASION_WORD.get(_s(c.to_value), _s(c.to_value).lower())
        frm = OCCASION_WORD.get(_s(c.from_value), _s(c.from_value).lower())
    else:
        to, frm = _s(c.to_value).lower(), _s(c.from_value).lower()
    return f"{to} {sub}".strip(), f"{frm} {sub}".strip()


def modifier_phrase(c: Critique) -> str:
    if c.attribute == "occasion":
        return OCCASION_WORD.get(_s(c.to_value), _s(c.to_value).lower())
    return _s(c.to_value).lower()


class Composer:
    """Builds a :class:`ComposedQuery` for one of :data:`METHODS`.

    ``encode_text`` must return L2-normalised rows (Encoder protocol); ``image_emb`` is
    ``Engine02.image_emb``. Text encodings are memoised, so sweeping α/λ costs no extra encoder calls.
    """

    def __init__(self, catalog, image_emb: np.ndarray, encode_text: Callable[[list[str]], np.ndarray],
                 rewriter: Rewriter | None = None):
        self.catalog = catalog
        self.image_emb = image_emb
        self._encode = encode_text
        self.rewriter = rewriter or TemplateRewriter("title")
        self._memo: dict[str, np.ndarray] = {}

    def txt(self, texts: list[str]) -> np.ndarray:
        todo = [t for t in dict.fromkeys(texts) if t not in self._memo]
        if todo:
            for t, v in zip(todo, self._encode(todo)):
                self._memo[t] = np.asarray(v, dtype=np.float64)
        return np.stack([self._memo[t] for t in texts])

    def compose(self, ref_pos: int, critique: Critique, base_query: str, method: str, alpha: float = 0.5,
                lam: float = 1.0, text_source: Literal["rewrite", "modifier"] = "rewrite") -> ComposedQuery:
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r}; choose from {METHODS}")
        row = self.catalog.items.iloc[ref_pos]
        c = critique.resolved(row)
        ref_id = str(row["item_id"])
        target = self.rewriter.rewrite(row, c, base_query)
        updates = {c.attribute: [_s(c.to_value)]} if method in FILTER_METHODS and c.to_value else {}
        img = np.asarray(self.image_emb[ref_pos], dtype=np.float64)
        emb: np.ndarray | None
        text = target
        params: dict[str, float] = {}
        if method == "critique_filter":
            emb, text = None, base_query
        elif method == "text_rewrite":
            emb = self.txt([target])[0]
        elif method == "ref_plus_filter":
            emb = img
        elif method in ("image_plus_text", "image_plus_text_filter"):
            phrase = target if text_source == "rewrite" else modifier_phrase(c)
            emb = alpha * img + (1 - alpha) * self.txt([phrase])[0]
            params["alpha"] = alpha
        else:  # vector_arithmetic
            to_p, from_p = direction_phrases(row, c)
            t = self.txt([to_p, from_p])
            emb = img + lam * (t[0] - t[1])
            params["lambda"] = lam
        if emb is not None:
            emb = l2n(emb).astype(np.float64)
        return ComposedQuery(method=method, retrieval_text=text, query_embedding=emb, constraint_updates=updates,
                             exclude_item_ids=[ref_id], target_text=target, params=params)


def apply_to_request(req: Engine02Request, cq: ComposedQuery) -> Engine02Request:
    """Return a copy of ``req`` with the composed constraints, text and exclusion applied."""
    new = req.model_copy(deep=True)
    new.retrieval_text = cq.retrieval_text
    for attr, vals in cq.constraint_updates.items():
        if attr in HardConstraints.model_fields and attr not in ("budget", "excluded_values"):
            setattr(new.constraints, attr, Slot(state=SlotState.VALUE, values=list(vals)))
    new.feedback.excluded_item_ids = list(dict.fromkeys(new.feedback.excluded_item_ids + cq.exclude_item_ids))
    return new


def rank_dense(engine_like, constraints: HardConstraints, cq: ComposedQuery, k: int = 10,
               min_results: int | None = None) -> list[int]:
    """Fast path used by the evaluation: hard filter (with the pipeline's relaxation ladder) then
    exact dense ranking by ``cq.query_embedding``. Identical to arm ``dense`` of the pipeline."""
    items = engine_like.catalog.items
    c = constraints.model_copy(deep=True)
    for attr, vals in cq.constraint_updates.items():
        setattr(c, attr, Slot(state=SlotState.VALUE, values=list(vals)))
    excl = engine_like.catalog.positions(cq.exclude_item_ids)
    fr = filter_with_relaxation(items, c, min_results or k, excl)
    pool = np.flatnonzero(fr.mask)
    q = cq.query_embedding
    if q is None:
        raise ValueError("rank_dense needs a query embedding; run critique_filter through the pipeline")
    s = engine_like.image_emb[pool] @ q
    return [int(p) for p in pool[np.argsort(-s, kind="stable")[:k]]]


class ComposedEngine02(Engine02):
    """Engine02 whose query vector can be replaced by a composed one for a single call.

    Integration hook (no change to pipeline.py): ``query_embedding`` is overridden; everything else
    (filter, BM25 on ``retrieval_text``, RRF, additive rerank, reasons) is the normal pipeline.
    Not thread-safe (one override per call).
    """

    _override: np.ndarray | None = None

    def query_embedding(self, req, arm, text):  # type: ignore[override]
        if self._override is not None:
            return self._override
        return super().query_embedding(req, arm, text)

    def composer(self, rewriter: Rewriter | None = None) -> Composer:
        return Composer(self.catalog, self.image_emb, self.encoder.encode_text, rewriter)

    def run_composed(self, req: Engine02Request, cq: ComposedQuery, arm=None) -> Engine02Response:
        self._override = cq.query_embedding
        try:
            return self.run(apply_to_request(req, cq), arm)
        finally:
            self._override = None
