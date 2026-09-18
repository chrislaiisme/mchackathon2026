"""Per-catalog normalised column codes, so hard filtering is O(n) in C instead of in Python.

Filtering runs on every request, for every slot, and again for every step of the relaxation ladder.
Doing `col.map(_norm).isin(values)` each time means a Python call per row per slot per step — on a
17.8k-item catalog that was tens of milliseconds per request before the ladder even widened
anything, and the same normalisation was recomputed identically every time.

A catalog frame does not change once loaded, so normalise each filterable column once into integer
codes plus a `value → code` dictionary. A membership test then becomes a boolean lookup table
indexed by the codes, which numpy does in one pass.

The cache is keyed by `id(frame)` with the frame kept alive, because the filtered views built by
`attribute_fill.provenance_filter` are separate long-lived frames that deserve their own index.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# columns worth indexing: the hard-constraint slots plus the two used to resolve categories
INDEXED = ("category", "subcategory", "color", "occasion", "season", "gender", "source")


def _norm_array(values: np.ndarray) -> list[str | None]:
    out: list[str | None] = []
    for s in values:
        if s is None or s is pd.NA or (isinstance(s, float) and np.isnan(s)):
            out.append(None)
        else:
            out.append(str(s).strip().lower())
    return out


class AttrIndex:
    """Integer codes for the normalised values of one catalog frame (code 0 = missing)."""

    __slots__ = ("n", "codes", "lookup", "isna", "_pair_cache")

    def __init__(self, items: pd.DataFrame):
        self.n = len(items)
        self.codes: dict[str, np.ndarray] = {}
        self.lookup: dict[str, dict[str, int]] = {}
        self.isna: dict[str, np.ndarray] = {}
        self._pair_cache: dict[tuple, np.ndarray] = {}
        for col in INDEXED:
            if col not in items.columns:
                continue
            norm = _norm_array(items[col].to_numpy())
            vals: dict[str, int] = {}
            codes = np.zeros(self.n, dtype=np.int32)
            for i, v in enumerate(norm):
                if v is None:
                    continue
                c = vals.get(v)
                if c is None:
                    c = len(vals) + 1  # 0 stays reserved for "missing"
                    vals[v] = c
                codes[i] = c
            self.codes[col] = codes
            self.lookup[col] = vals
            self.isna[col] = codes == 0

    # ------------------------------------------------------------------
    @classmethod
    def get(cls, items: pd.DataFrame) -> "AttrIndex":
        key = (id(items), len(items))
        hit = _CACHE.get(key)
        if hit is None:
            hit = cls(items)
            _CACHE[key] = hit
            _KEEPALIVE[key] = items
        return hit

    def has(self, col: str) -> bool:
        return col in self.codes

    def _select(self, col: str, values) -> np.ndarray:
        """Boolean lookup table over the code space of `col`."""
        table = np.zeros(len(self.lookup[col]) + 1, dtype=bool)
        for v in values:
            c = self.lookup[col].get(str(v).strip().lower())
            if c is not None:
                table[c] = True
        return table

    def mask(self, col: str, values, allow_unknown: bool = False, also: str | None = None) -> np.ndarray:
        out = self._select(col, values)[self.codes[col]]
        if also and also in self.codes:
            out |= self._select(also, values)[self.codes[also]]
        if allow_unknown:
            out |= self.isna[col]
        return out

    def source_codes(self, fn, name: str, default: str | None = None) -> tuple[np.ndarray, dict[str, int]]:
        """Codes for `fn(raw source value)` — the taxonomy maps 'Marqo/polyvore' → 'polyvore'.

        Cached under `name`, since the mapping function is fixed per caller. Rows whose key is
        unknown get code 0, which the pair table treats as "no source recorded".
        """
        hit = self._pair_cache.get(("__src__", name))
        if hit is not None:
            return hit, self.lookup[f"__src__{name}"]
        raw = self.codes.get("source")
        lookup: dict[str, int] = {}
        if raw is None:
            key = default
            codes = np.zeros(self.n, dtype=np.int32)
            if key:
                lookup[key] = 1
                codes[:] = 1
        else:
            inv = {c: v for v, c in self.lookup["source"].items()}
            per_code = {0: 0}
            for c, v in inv.items():
                k = fn(v)
                if k is None:
                    per_code[c] = 0
                    continue
                if k not in lookup:
                    lookup[k] = len(lookup) + 1
                per_code[c] = lookup[k]
            table = np.zeros(max(per_code) + 1, dtype=np.int32)
            for c, mapped in per_code.items():
                table[c] = mapped
            codes = table[raw]
        self._pair_cache[("__src__", name)] = codes
        self.lookup[f"__src__{name}"] = lookup
        return codes, lookup

    def pair_mask(self, pairs: set[tuple[str, str]], value_col: str = "subcategory",
                  source_codes: np.ndarray | None = None,
                  source_lookup: dict[str, int] | None = None) -> np.ndarray:
        """Rows whose (source, value) is in `pairs`; rows with no source match on the value alone.

        This is the taxonomy's per-source resolution ('Tights' means different things in the two
        vocabularies) expressed as table lookups instead of a Python loop over the catalog.
        """
        key = (value_col, id(source_codes), frozenset(pairs))
        hit = self._pair_cache.get(key)
        if hit is not None:
            return hit
        vcodes = self.codes[value_col]
        vlook = self.lookup[value_col]
        n_v = len(vlook) + 1
        any_value = np.zeros(n_v, dtype=bool)
        for _, v in pairs:
            c = vlook.get(str(v).strip().lower())
            if c is not None:
                any_value[c] = True

        if source_codes is None or not source_lookup:
            out = any_value[vcodes]
        else:
            allowed = np.zeros((len(source_lookup) + 1, n_v), dtype=bool)
            allowed[0] = any_value  # no source recorded → match on the value alone
            for s, v in pairs:
                sc = source_lookup.get(s)
                vc = vlook.get(str(v).strip().lower())
                if sc is not None and vc is not None:
                    allowed[sc, vc] = True
            out = allowed[source_codes, vcodes]
        self._pair_cache[key] = out
        return out


_CACHE: dict[tuple[int, int], AttrIndex] = {}
_KEEPALIVE: dict[tuple[int, int], pd.DataFrame] = {}
