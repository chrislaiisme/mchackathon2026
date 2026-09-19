"""Trend-keyword signal for the additive reranker (PRD §6.6), without Pinterest data.

The PRD asks for a small trend bonus: ``w_trend · z(BM25(item text, trend keywords))``.
``Engine02.set_trends`` has always accepted the keyword list, but nothing ever fed it, so the
``trend`` term was dead code in every arm. This module supplies the keywords.

Why not Pinterest
-----------------
Pinterest's Developer Guidelines forbid **storing** information obtained from their API, using
it to train AI/ML, and creating new content from Pins; displayed Pins must link back to the
original Pin (PRD ref [108]).  A checked-in trend list scraped from Pinterest would therefore
violate the terms, and an offline evaluation that replays a stored list is exactly the
"storing" that is forbidden.  Consequences for this module:

* the default sources are **catalog-derived** or a **local hand-maintained file** — no Pinterest;
* :func:`from_live_fetch` exists for a request-time call to *any* trend API (Pinterest's
  ``GET /v5/trends/keywords/{region}/top/{trend_type}`` returns keywords, not images), but the
  object it returns refuses to be written to disk (``ephemeral=True``), so no Pinterest data can
  leak into the repo or into a cache;
* the sponsor already runs an internal trend platform and excluded trend *forecasting* from the
  brief, so the weight stays small and the term is only ever a tie-breaker.

Catalog-derived sources (both training-free, reproducible, no external service)
-------------------------------------------------------------------------------
``curated_lift``
    A term is "in style" if items whose text contains it are over-represented among items that
    human stylists actually put into outfits.  With the Polyvore outfits merged into the catalog
    (``outfit_ids`` non-empty; Vasileva et al., ECCV 2018 / Han et al., ACM MM 2017) this is a
    log-odds lift of the term's document frequency inside curated items against the whole
    catalog, with an informative-Dirichlet prior variance so rare terms are not ranked first
    (Monroe, Colaresi & Quinn, *Political Analysis* 2008, "Fightin' Words", §3.5 — the standard
    log-odds-ratio-with-prior statistic for over-representation).

``outfit_partner``
    Context-dependent: terms of the items that share an outfit with items of the anchor
    categories ("what is currently styled *with* a blazer").  This uses the outfit
    co-occurrence structure itself rather than item popularity.

Neither source is a trend *forecast*; both are "what stylists in this dataset put together".
Say so on the slide — the dataset is a 2010s Polyvore snapshot, so it is a **stand-in** for the
sponsor's live trend feed, not evidence about 2026 fashion.

Hook for the coordinator
------------------------
``attach_trends(engine, load_trends(...))`` — one line, no pipeline change; the existing
``arm.use_trend`` / ``arm.w_trend`` switches then take effect.  The term is dormant until this
is called, so every number measured so far is unaffected.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd

from .pipeline import Engine02
from .sparse import tokenize

RESOURCES = Path(__file__).parent / "resources"
DEFAULT_FILE = "trend_keywords_v0.json"

# Tokens that are pure taxonomy / boilerplate: keeping them would make the trend term a copy of
# the BM25 term (both score the same catalog words) instead of an independent signal.
GENERIC = frozenset(
    """
    women womens woman men mens man unisex kid kids boy boys girl girls
    shirt shirts tshirt tshirts top tops tee tees dress dresses pant pants trouser trousers
    jean jeans short shorts skirt skirts jacket jackets coat coats sweater sweaters shoe shoes
    boot boots sandal sandals heel heels sneaker sneakers bag bags handbag handbags watch watches
    set sets pack size fit style styles wear collection new
    """.split()
)


@dataclass(frozen=True)
class TrendTerm:
    term: str
    score: float  # source-specific strength (log-odds z for curated_lift, PMI for outfit_partner)
    df: int  # documents containing the term (support)

    def to_dict(self) -> dict:
        return {"term": self.term, "score": round(float(self.score), 4), "df": int(self.df)}


@dataclass
class TrendKeywords:
    """A trend keyword list plus the provenance the demo has to show."""

    terms: list[TrendTerm] = field(default_factory=list)
    source: str = "manual"  # curated_lift | outfit_partner | manual | live:<name>
    as_of: str = ""
    catalog: str | None = None
    notes: list[str] = field(default_factory=list)
    ephemeral: bool = False  # True → came from a live API; must never be persisted

    # ------------------------------------------------------------------
    def keywords(self, top_n: int | None = None) -> list[str]:
        t = sorted(self.terms, key=lambda x: -x.score)
        return [x.term for x in (t[:top_n] if top_n else t)]

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "as_of": self.as_of,
            "catalog": self.catalog,
            "notes": self.notes,
            "terms": [t.to_dict() for t in sorted(self.terms, key=lambda x: -x.score)],
        }

    def save(self, path: str | Path) -> Path:
        if self.ephemeral:
            raise PermissionError(
                "this trend list came from a live API (ephemeral=True) and must not be stored; "
                "Pinterest's developer guidelines forbid storing information obtained from the API"
            )
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def from_dict(cls, raw: dict) -> "TrendKeywords":
        terms = [TrendTerm(term=t["term"], score=float(t.get("score", 0.0)), df=int(t.get("df", 0)))
                 if isinstance(t, dict) else TrendTerm(term=str(t), score=0.0, df=0)
                 for t in raw.get("terms", [])]
        return cls(terms=terms, source=raw.get("source", "manual"), as_of=raw.get("as_of", ""),
                   catalog=raw.get("catalog"), notes=list(raw.get("notes", [])))


def load_trends(path: str | Path | None = None) -> TrendKeywords:
    """Load a trend list. ``None`` → the checked-in hand-maintained fallback."""
    p = Path(path) if path else RESOURCES / DEFAULT_FILE
    return TrendKeywords.from_dict(json.loads(Path(p).read_text(encoding="utf-8")))


def from_live_fetch(fetch: Callable[[], Iterable[str]], name: str = "live") -> TrendKeywords:
    """Wrap a request-time trend API call. The result is marked ephemeral and cannot be saved.

    ``fetch`` must return keyword strings only (never images or Pin content). Example for
    Pinterest: ``GET /v5/trends/keywords/{region}/top/{trend_type}`` — keywords are allowed to be
    *used* at request time; storing them is not.
    """
    words = [w.strip().lower() for w in fetch() if w and w.strip()]
    terms = [TrendTerm(term=w, score=float(len(words) - i), df=0) for i, w in enumerate(words)]
    return TrendKeywords(terms=terms, source=f"live:{name}", as_of=date.today().isoformat(),
                         notes=["即時呼叫、未存檔（Pinterest 開發者規範不得儲存 API 資訊）"], ephemeral=True)


# ---------------------------------------------------------------------------
# catalog-derived sources
# ---------------------------------------------------------------------------
def _doc_tokens(items: pd.DataFrame, fields: Sequence[str] = ("title", "description")) -> list[set[str]]:
    cols = [c for c in fields if c in items.columns]
    if not cols:
        return [set() for _ in range(len(items))]
    texts = items[cols].fillna("").astype(str).agg(" ".join, axis=1).tolist()
    out = []
    for t in texts:
        toks = {w for w in tokenize(t) if len(w) > 2 and not w.isdigit() and w not in GENERIC}
        out.append(toks)
    return out


def _in_outfit(items: pd.DataFrame) -> np.ndarray:
    if "outfit_ids" not in items.columns:
        return np.zeros(len(items), dtype=bool)
    return items["outfit_ids"].map(lambda v: bool(v is not None and len(v) > 0) if not isinstance(v, float) else False) \
        .to_numpy(dtype=bool)


def curated_lift_terms(items: pd.DataFrame, top_n: int = 40, min_df: int = 8, min_group: int = 5,
                       fields: Sequence[str] = ("title", "description")) -> list[TrendTerm]:
    """Log-odds-ratio with an informative Dirichlet prior (Monroe et al. 2008) of every token's
    document frequency inside curated outfits vs the whole catalog.

    Requires a catalog where only part of the items belong to curated outfits (``outfit_ids``),
    e.g. the merged ``kagl_polyvore``. Raises otherwise — a silent all-or-nothing split would
    produce a meaningless list.
    """
    mask = _in_outfit(items)
    n_in, n_out = int(mask.sum()), int((~mask).sum())
    if n_in < min_group or n_out < min_group:
        raise ValueError(
            f"curated_lift needs both curated and non-curated items (got {n_in} in outfits, "
            f"{n_out} not); use a merged catalog such as kagl_polyvore, or the outfit_partner source"
        )
    docs = _doc_tokens(items, fields)
    c_in: Counter[str] = Counter()
    c_all: Counter[str] = Counter()
    for i, toks in enumerate(docs):
        c_all.update(toks)
        if mask[i]:
            c_in.update(toks)
    total_in = sum(c_in.values()) or 1
    total_all = sum(c_all.values()) or 1
    a0 = 500.0  # prior strength, in pseudo-tokens, over the catalog-wide distribution
    out: list[TrendTerm] = []
    for w, f_all in c_all.items():
        if f_all < min_df:
            continue
        f_in = c_in.get(w, 0)
        f_rest = f_all - f_in
        prior = a0 * f_all / total_all
        # δ = log odds(in) − log odds(rest), both smoothed by the same prior
        y_in, y_rest = f_in + prior, f_rest + prior
        d_in, d_rest = total_in + a0 - y_in, (total_all - total_in) + a0 - y_rest
        if min(y_in, y_rest, d_in, d_rest) <= 0:
            continue
        delta = math.log(y_in / d_in) - math.log(y_rest / d_rest)
        sd = math.sqrt(1.0 / y_in + 1.0 / y_rest)
        out.append(TrendTerm(term=w, score=delta / sd, df=f_all))
    out.sort(key=lambda t: -t.score)
    return out[:top_n]


def outfit_partner_terms(items: pd.DataFrame, anchor_categories: Sequence[str], top_n: int = 20,
                         min_df: int = 3, fields: Sequence[str] = ("title", "description")) -> list[TrendTerm]:
    """Terms of the items that share a curated outfit with items of ``anchor_categories``.

    Score = PMI-style lift of a term's document frequency among outfit partners against its
    frequency among all outfit items. Answers "what is being styled with a blazer right now",
    which is the contextual version of the trend bonus.
    """
    if "outfit_ids" not in items.columns:
        raise ValueError("outfit_partner needs an `outfit_ids` column (Polyvore-style catalog)")
    cats = {c.lower() for c in anchor_categories}
    by_outfit: dict[str, list[int]] = defaultdict(list)
    for i, v in enumerate(items["outfit_ids"]):
        if v is None or isinstance(v, float):
            continue
        for o in v:
            by_outfit[str(o)].append(i)
    cat_col = items["category"].astype(str).str.lower() if "category" in items.columns else None
    partners: set[int] = set()
    for members in by_outfit.values():
        if cat_col is None:
            continue
        anchors = [m for m in members if cat_col.iat[m] in cats]
        if anchors:
            partners.update(m for m in members if m not in set(anchors))
    docs = _doc_tokens(items, fields)
    in_outfit = set(np.flatnonzero(_in_outfit(items)).tolist())
    c_p: Counter[str] = Counter()
    c_b: Counter[str] = Counter()
    for i in partners:
        c_p.update(docs[i])
    for i in in_outfit:
        c_b.update(docs[i])
    n_p, n_b = max(len(partners), 1), max(len(in_outfit), 1)
    out = []
    for w, f in c_p.items():
        if f < min_df:
            continue
        p_p, p_b = f / n_p, (c_b.get(w, 0) + 0.5) / n_b
        out.append(TrendTerm(term=w, score=math.log(p_p / p_b), df=f))
    out.sort(key=lambda t: -t.score)
    return out[:top_n]


def derive_trends(items: pd.DataFrame, source: str = "curated_lift", catalog: str | None = None,
                  top_n: int = 40, anchor_categories: Sequence[str] | None = None,
                  min_df: int = 8) -> TrendKeywords:
    if source == "curated_lift":
        terms = curated_lift_terms(items, top_n=top_n, min_df=min_df)
        notes = ["來源：人工策展穿搭（Polyvore outfit_ids）中過度出現的詞，對照整個商品庫的基準率",
                 "統計：Monroe et al. 2008 的 log-odds-ratio with informative Dirichlet prior",
                 "這不是趨勢預測，是「造型師在這份資料集裡常放進穿搭的詞」；資料集是 2010 年代快照"]
    elif source == "outfit_partner":
        terms = outfit_partner_terms(items, anchor_categories or ["outerwear"], top_n=top_n,
                                     min_df=max(1, min_df // 4))
        notes = [f"來源：與 {list(anchor_categories or ['outerwear'])} 同一套穿搭的單品用詞（PMI lift）",
                 "情境相依：換錨點品類就換一組關鍵字"]
    else:
        raise ValueError(f"unknown trend source {source!r}; expected curated_lift | outfit_partner")
    return TrendKeywords(terms=terms, source=source, as_of=date.today().isoformat(),
                         catalog=catalog, notes=notes)


# ---------------------------------------------------------------------------
def attach_trends(engine, trends: TrendKeywords | None = None, top_n: int | None = 30) -> list[str]:
    """Integration hook: feed the keyword list to an existing ``Engine02`` instance.

    Returns the keywords actually installed. ``arm.use_trend`` and ``arm.w_trend`` decide whether
    they matter; with no call to this function the trend term stays absent (the state every
    number in docs/engine02-design.md was measured in).
    """
    tk = trends if trends is not None else load_trends()
    words = tk.keywords(top_n)
    engine.set_trends(words)
    return words


CLIP_GROUPS = ("trend", "penalty")


class TrendClippedEngine02(Engine02):
    """Wrapper that applies ``arm.z_clip`` to the trend (and penalty) terms as well.

    `ArmConfig.z_clip` documents itself as "clip normalised **dense/bm25/trend/penalty** terms to
    ±z_clip", but `pipeline.Engine02._terms` only passes `clip=arm.z_clip` to the dense and BM25
    terms. The trend term is the *same* heavy-tailed pool-level BM25 distribution that motivated
    z-clipping in the first place (docs/engine02-design.md §3.10: most items score 0, a single
    keyword match reaches z≈8), so in the serving arm `full_zclip3` it is the one unclipped z in
    the sum and one matched keyword can outweigh every other reason. Measured in
    scripts/eval_trends.py (`--clip-trend`).

    The penalty term is z-scored image cosine, bounded in [−1, 1], so clipping it changes little;
    it is included here only because the config says it should be clipped.

    Equivalent change in `Engine02._terms`, for the coordinator (two lines):

        terms.append(Term("trend", "trend", tr_all[top], arm.w_trend,
                          stats=..., clip=arm.z_clip))          # ← add clip
        terms.append(Term("penalty:rejected_similarity", "penalty", sim_all[top], -arm.w_penalty,
                          stats=..., clip=arm.z_clip))          # ← add clip
    """

    def _terms(self, req, arm, pool, cand, dense_all, bm25_all, top, text):  # type: ignore[override]
        terms = super()._terms(req, arm, pool, cand, dense_all, bm25_all, top, text)
        if arm.z_clip:
            for t in terms:
                if t.group in CLIP_GROUPS and t.clip is None:
                    t.clip = arm.z_clip
        return terms


def trend_badges(engine, resp, keywords: Sequence[str] | None = None, z_cap: float = 3.0) -> dict[str, dict]:
    """Trend as a **display badge**, not a ranking term (PRD §6.6 asks the card to show「趨勢」).

    Returns ``item_id -> {matched: [...], z: float}`` for the cards in ``resp``, computed from the
    catalog text only. The score, the contributions and the order are untouched, so the badge
    cannot make the explanation unfaithful — and it costs 0 NDCG, unlike putting the term in the
    sum (scripts/eval_trends.py). Use this when the demo wants the trend chip but not the risk.
    """
    words = [w.lower() for w in (keywords if keywords is not None else engine.trend_keywords)]
    if not words:
        return {}
    wordset = set(words)
    s = engine.bm25.scores(" ".join(words))
    mu, sd = float(s.mean()), float(s.std() or 1.0)
    texts = engine.catalog.texts()
    out: dict[str, dict] = {}
    for it in resp.items:
        pos = engine.catalog.pos(it.item_id)
        if pos is None:
            continue
        matched = sorted(set(tokenize(texts[pos])) & wordset)
        z = float(np.clip((s[pos] - mu) / sd, -z_cap, z_cap))
        out[it.item_id] = {"matched": matched, "z": round(z, 3),
                           "affects_score": False,
                           "label": ("符合近期趨勢關鍵字：" + "、".join(matched)) if matched else ""}
    return out


def trend_coverage(engine, keywords: Sequence[str] | None = None) -> dict:
    """Sanity check before enabling the term: how much of the catalog the keywords even touch."""
    words = list(keywords) if keywords is not None else list(engine.trend_keywords)
    if not words:
        return {"n_keywords": 0, "in_vocab": 0, "nonzero_share": 0.0}
    s = engine.bm25.scores(" ".join(words))
    return {
        "n_keywords": len(words),
        "in_vocab": int(sum(w in engine.bm25.vocab for w in words)),
        "nonzero_share": float((s > 0).mean()),
        "max": float(s.max()) if len(s) else 0.0,
        "mean_nonzero": float(s[s > 0].mean()) if (s > 0).any() else 0.0,
    }
