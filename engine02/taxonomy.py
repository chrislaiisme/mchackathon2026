"""Category taxonomy for ENGINE 02: normalisation, hierarchy, relaxation ladder, catalog filter values.

Resources (built by scripts/build_taxonomy_v1.py, rationale in docs/research/taxonomy.md):
  engine02/resources/taxonomy_v1.json          L1 garment slot -> L2 garment type (+ collections)
  engine02/resources/taxonomy_map_kagl.json    KAGL articleType (our `subcategory`) -> node
  engine02/resources/taxonomy_map_polyvore.json Polyvore site category (our `subcategory`) -> node

Design anchors (all opened and checked, see the report for V/U marks):
  * node ids / GPT cross-reference: Google Product Taxonomy 2021-09-21 (taxonomy-with-ids.en-US.txt);
  * garment-type granularity and attribute names: Fashionpedia ontology (Jia et al., ECCV 2020,
    arXiv:2004.12276: 27 main apparel categories, 294 attributes);
  * knit/woven prior per node: WCO HS 2022 chapter 61 (knitted or crocheted) vs 62 (not knitted);
  * Chinese synonyms: Shopee TW category tree and Yahoo 購物中心 category menu (2026-09-17);
  * hierarchical relaxation instead of "category never relaxed": query relaxation by generalising a
    constraint to its parent in a hierarchy (cf. the null-query rewriting already cited in constraints.py).

Matching is deliberately rule-based (exact, then longest non-overlapping substring) — no ML.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

RES = Path(__file__).parent / "resources"
DEFAULT_TAXONOMY = RES / "taxonomy_v1.json"

# catalog name -> source vocabularies present in its `subcategory` column
CATALOG_SOURCES = {
    "kagl": ("kagl",), "kagl_full": ("kagl",), "kagl_labeled": ("kagl",),
    "polyvore": ("polyvore",), "polyvore_big": ("polyvore",),
    "kagl_polyvore": ("kagl", "polyvore"),
}
MAPPED_STATUSES = ("mapped", "mapped_l1", "collection")


def _norm(text: str) -> str:
    """NFKC (full-width -> half-width), lower-case, collapse whitespace."""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    return re.sub(r"\s+", " ", t).strip()


def _source_key(source_value) -> str | None:
    if source_value is None or (isinstance(source_value, float) and np.isnan(source_value)):
        return None
    s = str(source_value).lower()
    if "kagl" in s or "fashion-product" in s:
        return "kagl"
    if "polyvore" in s:
        return "polyvore"
    return None


@dataclass
class _Syn:
    term: str  # normalised
    nodes: tuple[str, ...]
    exact_only: bool
    ascii: bool
    pattern: re.Pattern | None = None


@dataclass
class Taxonomy:
    path: Path = DEFAULT_TAXONOMY
    nodes: dict[str, dict] = field(default_factory=dict)
    collections: dict[str, dict] = field(default_factory=dict)
    maps: dict[str, dict[str, dict]] = field(default_factory=dict)  # source -> value -> entry

    def __post_init__(self):
        data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        self.version = data["version"]
        self.attribute_defs = data.get("attribute_defs", {})
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.collections = {c["id"]: c for c in data.get("collections", [])}
        for src in ("kagl", "polyvore"):
            f = Path(self.path).parent / f"taxonomy_map_{src}.json"
            self.maps[src] = json.loads(f.read_text(encoding="utf-8"))["entries"] if f.exists() else {}
        self._children: dict[str, list[str]] = {}
        for n in self.nodes.values():
            if n["parent"]:
                self._children.setdefault(n["parent"], []).append(n["id"])
        self._build_synonyms()

    # ------------------------------------------------------------------ hierarchy
    def is_node(self, nid: str) -> bool:
        return nid in self.nodes

    def is_collection(self, nid: str) -> bool:
        return nid in self.collections

    def label(self, nid: str | None, lang: str = "zh") -> str:
        if nid is None:
            return "（不限）" if lang == "zh" else "(any)"
        d = self.nodes.get(nid) or self.collections.get(nid)
        return d[f"label_{lang}"] if d else nid

    def ancestors(self, nid: str) -> list[str]:
        """Parents from nearest to root (excluding `nid`). Collections have no ancestors."""
        out, cur = [], self.nodes.get(nid, {}).get("parent")
        while cur:
            out.append(cur)
            cur = self.nodes[cur]["parent"]
        return out

    def children(self, nid: str) -> list[str]:
        return list(self._children.get(nid, []))

    def descendants(self, nid: str) -> list[str]:
        out, stack = [], list(self._children.get(nid, []))
        while stack:
            c = stack.pop(0)
            out.append(c)
            stack.extend(self._children.get(c, []))
        return out

    def relax_ladder(self, nid: str) -> list[str | None]:
        """[nid, parent, ..., L1, None]. A collection is an intersection facet: [coll, None]."""
        if nid in self.collections:
            return [nid, None]
        if nid not in self.nodes:
            raise KeyError(nid)
        return [nid, *self.ancestors(nid), None]

    def l1(self, nid: str) -> str | None:
        if nid not in self.nodes:
            return None
        return nid.split(".")[0]

    def legacy_coarse(self, nid: str | None) -> str | None:
        """Coarse category used by the current pipeline (Kansei applicability, co-occurrence)."""
        n = self.nodes.get(nid) if nid else None
        return n["legacy_coarse"] if n else None

    # ------------------------------------------------------------------ source maps
    def sources_for(self, catalog: str | None) -> tuple[str, ...]:
        return CATALOG_SOURCES.get(catalog or "", ("kagl", "polyvore"))

    def node_of_value(self, value: str, source: str) -> str | None:
        e = self.maps.get(source, {}).get(value)
        return e["node"] if e and e["status"] in MAPPED_STATUSES else None

    def catalog_pairs(self, nid: str, catalog: str | None = None) -> set[tuple[str, str]]:
        """(source, subcategory value) pairs whose items belong to `nid` (node incl. descendants,
        or collection incl. member nodes and collection-only source values)."""
        if nid in self.collections:
            c = self.collections[nid]
            targets = set(c.get("members", [])) | {nid}
            for m in c.get("members", []):
                targets |= set(self.descendants(m))
            extra = c.get("extra_source_values", {})
        elif nid in self.nodes:
            targets = {nid, *self.descendants(nid)}
            extra = {}
        else:
            raise KeyError(nid)
        out = set()
        for src in self.sources_for(catalog):
            for value, e in self.maps.get(src, {}).items():
                if e["status"] in MAPPED_STATUSES and e["node"] in targets:
                    out.add((src, value))
            for value in extra.get(src, []):
                if value in self.maps.get(src, {}):
                    out.add((src, value))
        return out

    def catalog_values(self, nid: str, catalog: str | None = None) -> list[str]:
        """Source `subcategory` values to filter on for node/collection `nid` in `catalog`."""
        return sorted({v for _, v in self.catalog_pairs(nid, catalog)})

    def category_mask(self, items: pd.DataFrame, ids: list[str], catalog: str | None = None) -> np.ndarray:
        """Boolean mask: (union over garment nodes) AND (each collection). Uses the `source` column
        when present so that values shared by both vocabularies ('Camisoles', 'Tights') resolve per source."""
        garment = [i for i in ids if i in self.nodes]
        colls = [i for i in ids if i in self.collections]
        if "subcategory" not in items.columns:
            return np.zeros(len(items), dtype=bool)
        # code-table lookups instead of a Python loop over the catalog on every request
        from .attrindex import AttrIndex

        idx = AttrIndex.get(items)
        default = self.sources_for(catalog)
        scodes, slookup = idx.source_codes(_source_key, "taxonomy",
                                           default=default[0] if len(default) == 1 else None)

        def mask_for(pairs: set[tuple[str, str]]) -> np.ndarray:
            return idx.pair_mask(pairs, "subcategory", scodes, slookup)

        mask = np.ones(len(items), dtype=bool)
        if garment:
            pairs = set().union(*(self.catalog_pairs(g, catalog) for g in garment))
            mask &= mask_for(pairs)
        for c in colls:
            mask &= mask_for(self.catalog_pairs(c, catalog))
        return mask

    def item_node_ids(self, items: pd.DataFrame, catalog: str | None = None) -> list[str | None]:
        """Per-item taxonomy node (None for non-apparel/unmapped) — e.g. for a taxonomy-based Kansei mask."""
        default = self.sources_for(catalog)
        out = []
        has_src = "source" in items.columns
        for i, sub in enumerate(items["subcategory"].to_numpy()):
            src = _source_key(items["source"].iat[i]) if has_src else None
            cands = [src] if src else list(default)
            node = next((n for n in (self.node_of_value(sub, s) for s in cands) if n), None)
            out.append(node)
        return out

    # ------------------------------------------------------------------ normalisation
    def _build_synonyms(self) -> None:
        index: dict[tuple[str, bool], set[str]] = {}

        def add(term: str, nid: str):
            exact = term.startswith("=")
            t = _norm(term[1:] if exact else term)
            if t:
                index.setdefault((t, exact), set()).add(nid)

        for nid, d in [*self.nodes.items(), *self.collections.items()]:
            add(d["label_zh"], nid)
            add(d["label_en"], nid)
            add(nid, nid)
            for s in d.get("synonyms_zh", []) + d.get("synonyms_en", []):
                add(s, nid)
        # source vocabulary (what ENGINE 01 may copy from GET /vocabulary), unless the value is ambiguous
        per_value: dict[str, set[str]] = {}
        for src, entries in self.maps.items():
            for value, e in entries.items():
                if e["status"] in MAPPED_STATUSES:
                    per_value.setdefault(value, set()).add(e["node"])
        for value, targets in per_value.items():
            if len(targets) == 1:
                add(value, next(iter(targets)))
        self._syn: list[_Syn] = []
        for (t, exact), nodes in index.items():
            is_ascii = all(ord(ch) < 128 for ch in t)
            pat = re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])") if is_ascii else None
            self._syn.append(_Syn(t, tuple(sorted(nodes)), exact, is_ascii, pat))
        self._exact = {}
        for s in self._syn:
            self._exact.setdefault(s.term, set()).update(s.nodes)
        self._contains = sorted([s for s in self._syn if not s.exact_only], key=lambda s: -len(s.term))

    def normalize_category(self, text: str) -> list[str]:
        """Map free text (Traditional Chinese or English, or a node id / catalog value) to node ids.

        1. exact match of the whole string against labels, synonyms, ids and catalog values;
        2. otherwise all synonym occurrences, longest first, keeping only non-overlapping spans
           (「西裝外套」 wins over 「外套」; 「運動短褲」 -> 短褲 + coll.activewear).
        Returns ids in order of appearance (ties by id); [] if nothing matches.
        """
        if not text or not str(text).strip():
            return []
        t = _norm(text)
        if t in self._exact:
            return sorted(self._exact[t])
        taken = np.zeros(len(t), dtype=bool)
        hits: list[tuple[int, str]] = []
        for s in self._contains:
            if s.ascii:
                spans = [(m.start(), m.end()) for m in s.pattern.finditer(t)]
            else:
                spans, start = [], t.find(s.term)
                while start >= 0:
                    spans.append((start, start + len(s.term)))
                    start = t.find(s.term, start + 1)
            for a, b in spans:
                if taken[a:b].any():
                    continue
                taken[a:b] = True
                hits.extend((a, n) for n in s.nodes)
        out: list[str] = []
        for _, n in sorted(hits):
            if n not in out:
                out.append(n)
        return out

    # ------------------------------------------------------------------ vocabularies for other engines
    def closed_vocabulary(self, max_synonyms: int = 6, include_non_apparel: bool = False) -> dict:
        """Compact closed vocabulary for ENGINE 01 (GPT): ids with zh label + a few zh synonyms."""
        def entry(d):
            syn = [s.lstrip("=") for s in d.get("synonyms_zh", []) if s.lstrip("=") != d["label_zh"]]
            return {"zh": d["label_zh"], "syn": syn[:max_synonyms]}

        cats = {}
        for nid, d in self.nodes.items():
            if d["level"] != 1 or (not d.get("apparel", True) and not include_non_apparel):
                continue
            cats[nid] = {**entry(d), "children": {c: entry(self.nodes[c]) for c in self.children(nid)}}
        return {
            "version": self.version,
            "category": cats,
            "collections": {cid: entry(c) for cid, c in self.collections.items()},
            "rules": [
                "category.values 只能填上面的 id（例如 outerwear.blazers）；不確定細類時填 L1（例如 outerwear）。",
                "「運動/機能/瑜珈」這類跨部位需求另填 collection id（coll.activewear），與部位 id 一起放在 category.values。",
                "使用者只說「衣服」「穿搭」而沒有部位時，category 保持 unmentioned。",
            ],
        }

    def vocabulary_payload(self, items: pd.DataFrame | None = None, catalog: str | None = None) -> dict:
        """Proposed `taxonomy` block for GET /vocabulary: node ids with labels, parent and item counts."""
        counts: dict[str, int] = {}
        if items is not None:
            for n in self.item_node_ids(items, catalog):
                for a in ([n, *self.ancestors(n)] if n else []):
                    counts[a] = counts.get(a, 0) + 1
        nodes = [
            {"id": nid, "parent": d["parent"], "level": d["level"], "label_zh": d["label_zh"], "label_en": d["label_en"],
             "apparel": d.get("apparel", True), **({"n_items": counts.get(nid, 0)} if items is not None else {})}
            for nid, d in self.nodes.items()
        ]
        colls = [{"id": cid, "label_zh": c["label_zh"], "label_en": c["label_en"]} for cid, c in self.collections.items()]
        return {"version": self.version, "nodes": nodes, "collections": colls}

    def retrieval_terms(self, nid: str, catalog: str | None = None, max_values: int = 4) -> str:
        """English text for BM25/dense query building when category.values carries node ids."""
        d = self.nodes.get(nid) or self.collections.get(nid)
        vals = self.catalog_values(nid, catalog)[:max_values] if d else []
        return " ".join([d["label_en"] if d else nid, *vals])


@lru_cache(maxsize=4)
def load_taxonomy(path: str | None = None) -> Taxonomy:
    return Taxonomy(Path(path) if path else DEFAULT_TAXONOMY)


# module-level convenience API ----------------------------------------------------------------
def normalize_category(text: str) -> list[str]:
    return load_taxonomy().normalize_category(text)


def ancestors(nid: str) -> list[str]:
    return load_taxonomy().ancestors(nid)


def relax_ladder(nid: str) -> list[str | None]:
    return load_taxonomy().relax_ladder(nid)


def catalog_values(nid: str, catalog: str | None = None) -> list[str]:
    return load_taxonomy().catalog_values(nid, catalog)


# ---------------------------------------------------------------------------------------------
# integration hook: hierarchical category relaxation around constraints.filter_with_relaxation
# ---------------------------------------------------------------------------------------------
def resolve_category_values(values: list[str], tax: Taxonomy | None = None) -> list[str]:
    """Slot values (ids, zh/en words, catalog values, legacy coarse names) -> node/collection ids."""
    tax = tax or load_taxonomy()
    coarse_to_l1: dict[str, list[str]] = {}
    for nid, d in tax.nodes.items():
        if d["level"] == 1 and d.get("apparel", True):
            coarse_to_l1.setdefault(d["legacy_coarse"], []).append(nid)
    out: list[str] = []
    for v in values:
        key = _norm(v)
        ids = coarse_to_l1.get(key) if key in coarse_to_l1 and key not in ("other",) else tax.normalize_category(v)
        for i in ids or []:
            if i not in out:
                out.append(i)
    return out


def legacy_constraints(c, ids: list[str], tax: Taxonomy):
    """For catalogs the taxonomy maps do not cover: keep the original values and add the legacy
    coarse names of the resolved nodes (e.g. 「外套」→ outerwear) for exact matching."""
    c2 = c.model_copy(deep=True)
    vals = list(c.category.values)
    for i in ids:
        if i in tax.nodes:
            lc = tax.legacy_coarse(i)
            if lc and lc not in vals:
                vals.append(lc)
    c2.category.values = vals
    return c2


def _generalise(ids: list[str], tax: Taxonomy) -> list[str]:
    out = []
    for i in ids:
        g = tax.nodes[i]["parent"] if i in tax.nodes and tax.nodes[i]["parent"] else i
        if g not in out:
            out.append(g)
    # drop nodes already covered by an ancestor in the list
    return [i for i in out if not any(a in out for a in tax.ancestors(i))]


def filter_with_category_relaxation(
    items: pd.DataFrame,
    c,
    min_results: int,
    excluded_positions: list[int] | None = None,
    catalog: str | None = None,
    tax: Taxonomy | None = None,
    allow_drop_category: bool = False,
    base=None,  # the non-category filter (default constraints.filter_with_relaxation)
):
    """Drop-in replacement for constraints.filter_with_relaxation with a hierarchical category ladder.

    Rungs: (garment ids, collections) -> (parents, collections) -> ... -> (L1s, no collections)
    [-> no category, only if allow_drop_category]. Every rung except the last runs the non-category
    ladder *without* the destructive steps (color:drop, budget:drop), so a too-specific category
    ("blazer") backs off to its parent ("outerwear") before the user's explicit colour is dropped.
    Unresolvable category values fall back to the legacy exact-match behaviour unchanged.
    """
    from .constraints import DEFAULT_LADDER
    from .constraints import filter_with_relaxation as _default_filter

    filter_with_relaxation = base or _default_filter
    tax = tax or load_taxonomy()
    slot = c.category
    if not (slot.is_hard() and slot.values):
        return filter_with_relaxation(items, c, min_results, excluded_positions)
    ids = resolve_category_values(slot.values, tax)
    if not ids:
        return filter_with_relaxation(items, c, min_results, excluded_positions)

    garment = [i for i in ids if i in tax.nodes]
    colls = [i for i in ids if i in tax.collections]
    # catalog not covered by the taxonomy maps (e.g. a new sponsor catalog): legacy exact match
    roots = [tax.l1(i) or i for i in garment] or colls
    if not tax.category_mask(items, roots, catalog).any():
        return filter_with_relaxation(items, legacy_constraints(c, ids, tax), min_results, excluded_positions)
    rungs: list[tuple[list[str], list[str]]] = [(garment, colls)]
    cur = garment
    while cur and any(tax.nodes[i]["parent"] for i in cur):
        cur = _generalise(cur, tax)
        rungs.append((cur, colls))
    if colls:
        rungs.append((cur, []))
    if allow_drop_category:
        rungs.append(([], []))

    c_no_cat = c.model_copy(deep=True)
    c_no_cat.category.values = []
    c_no_cat.category.hard = False
    soft = tuple(s for s in DEFAULT_LADDER if s not in (("color", "drop"), ("budget", "drop")))
    base_excl = set(excluded_positions or [])
    first_label = "+".join(garment + colls)
    fr = None
    for r, (g, cl) in enumerate(rungs):
        last = r == len(rungs) - 1
        cat_mask = tax.category_mask(items, g + cl, catalog) if (g or cl) else np.ones(len(items), dtype=bool)
        excl = sorted(base_excl | set(np.flatnonzero(~cat_mask).tolist()))
        fr = filter_with_relaxation(items, c_no_cat, min_results, excl, DEFAULT_LADDER if last else soft)
        label = "+".join(g + cl) if (g or cl) else "none"
        fr.applied = {"category": g + cl, **fr.applied}
        if r > 0:
            from_zh = "、".join(tax.label(i) for i in garment + colls)
            to_zh = "、".join(tax.label(i) for i in g + cl) or "不限類別"
            fr.relaxed = [f"category:{first_label}→{label}（{from_zh}→{to_zh}）", *fr.relaxed]
        if int(fr.mask.sum()) >= min_results:
            break
    return fr
