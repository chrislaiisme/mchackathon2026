"""「不要黑色」— turn a stated exclusion into an enforced one, in the same round.

CLIP-family encoders are near chance on negation (NegBench, ICML 2025), so a negated phrase left
inside `retrieval_text` does not remove anything; it often retrieves the very thing the user
rejected. ENGINE 01 is supposed to move negations into `constraints.excluded_values`, and when it
does, the exclusion is hard and never relaxed (§3.2). This module is what happens when it does not:
a deterministic pass that resolves the negated phrase against the catalog's own vocabulary and
applies it **this round**, saying exactly what it did.

Deliberate limits, because a parser that guesses is worse than no parser:
  * it only fires on a value the catalog actually has (a colour, a category, an occasion, or the
    label of a design axis) — an unresolvable negation stays a warning, as before;
  * the cue must be adjacent: within 10 characters (zh) or 3 tokens (en), with no punctuation or
    conjunction in between, so 「不要黑色，藍色可以」 excludes black and not blue;
  * inside one window only the most specific kind of value is taken, so "no black shirts" excludes
    black and NOT shirts — the user is rejecting the modifier, not the thing they asked for;
  * it never removes anything the user asked FOR, it only adds an exclusion.
"""

from __future__ import annotations

import re
import unicodedata

# cue → the negated thing must follow it closely
ZH_CUES = ("不想要", "不喜歡", "不要", "不想", "不能", "避免", "拒絕", "別")
EN_CUES = ("no", "not", "without", "avoid", "except", "exclude", "dont", "doesnt", "never")
ZH_WINDOW = 10         # characters after the cue
EN_WINDOW = 3          # tokens after the cue
BREAKERS = "，,。.;；!！?？、和跟與及"   # a boundary the negation does not cross

# "no black shirts" rejects black, not shirts: inside one window the user is rejecting the
# modifier, while the head noun is what they asked FOR.
ATTR_PRIORITY = ("color", "design_element", "occasion", "season", "subcategory", "category")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s or "")).strip().lower()


def _best_in_window(window: str, vocabulary: dict[str, dict[str, str]], substring: bool):
    for attr in ATTR_PRIORITY:
        forms = vocabulary.get(attr) or {}
        for surface in sorted(forms, key=len, reverse=True):   # 「海軍藍」 before 「藍」
            if not surface:
                continue
            hit = (surface in window) if substring else bool(
                re.search(rf"\b{re.escape(surface)}\b", window))
            if hit:
                return attr, forms[surface]
    return None


def _zh_category(window: str):
    """「不要洋裝」— the catalog's own category words are English, but the taxonomy knows the
    Chinese ones, so fall back to it rather than leaving a resolvable negation unresolved."""
    from .taxonomy import load_taxonomy, resolve_category_values

    tax = load_taxonomy()
    for n in (4, 3, 2):                       # longest Chinese phrase first
        for i in range(0, max(0, len(window) - n + 1)):
            frag = window[i: i + n].strip()
            if not frag or frag.isascii():
                continue
            ids = [v for v in resolve_category_values([frag], tax) if v in tax.nodes]
            if ids:
                return "category_id", ids[0]
    return None


def find_negated(text: str, vocabulary: dict[str, dict[str, str]]) -> list[tuple[str, str, str]]:
    """Return (attribute, canonical value, the words the user actually wrote).

    `vocabulary` maps attribute → {surface form (normalised) → canonical catalog value}; the
    surface forms may be Chinese or English. `design_element` maps to an element id, not a value.
    """
    raw = str(text or "")
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    for cue in ZH_CUES:                                  # longest cue first (不想要 before 不想)
        for m in re.finditer(re.escape(cue), raw):
            window = raw[m.end(): m.end() + ZH_WINDOW]
            cut = min((window.find(b) for b in BREAKERS if b in window), default=len(window))
            window = window[:cut]
            if not window:
                continue
            hit = _best_in_window(_norm(window), vocabulary, substring=True) or _zh_category(window)
            if hit and hit not in seen:
                seen.add(hit)
                out.append((hit[0], hit[1], cue + window))

    low = _norm(raw)
    tokens = re.findall(r"[a-z0-9']+|[^\sa-z0-9']", low)
    for i, tok in enumerate(tokens):
        if tok.replace("'", "") not in EN_CUES:
            continue
        window_tokens: list[str] = []
        for t in tokens[i + 1: i + 1 + EN_WINDOW]:
            if not re.match(r"[a-z0-9']", t):
                break
            window_tokens.append(t)
        if not window_tokens:
            continue
        window = " ".join(window_tokens)
        hit = _best_in_window(window, vocabulary, substring=False)
        if hit and hit not in seen:
            seen.add(hit)
            out.append((hit[0], hit[1], f"{tok} {window}"))
    return out


def expand_color_family(value: str, items) -> list[str]:
    """「不要藍色」 must remove Navy Blue too.

    A colour word is family-level in ordinary speech, so excluding only the canonical value leaves
    the user looking at the thing they rejected under a different name. Returns every colour value
    this catalog actually has in that family (including the value itself).
    """
    from .attribute_fill import color_family

    fam = color_family(value)
    if not fam or "color" not in getattr(items, "columns", []):
        return [value]
    out = {str(value)}
    for v in items["color"].dropna().unique():
        if color_family(v) == fam:
            out.add(str(v))
    return sorted(out)


def catalog_vocabulary(items, elements=None) -> dict[str, dict[str, str]]:
    """Surface forms the user might negate → this catalog's own value, per attribute.

    Built from the catalog itself plus the Chinese colour table, so it can never invent a value
    this catalog does not have.
    """
    from .attribute_fill import COLOR_ZH, FAMILY_CANONICAL

    vocab: dict[str, dict[str, str]] = {}
    for attr in ("color", "subcategory", "occasion", "season", "category"):
        if attr not in getattr(items, "columns", []):
            continue
        forms: dict[str, str] = {}
        for v in items[attr].dropna().unique():
            sv = str(v).strip()
            if sv:
                forms[_norm(sv)] = sv
        vocab[attr] = forms
    if "color" in vocab:
        have = {_norm(v) for v in vocab["color"].values()}
        for zh, family in COLOR_ZH.items():
            canon = FAMILY_CANONICAL.get(family)
            if canon and _norm(canon) in have:
                vocab["color"].setdefault(_norm(zh), canon)
    if elements:
        # design axes are not catalog values: they come back as a different kind of exclusion
        el: dict[str, str] = {}
        for e in elements:
            forms = {_norm(e.label), _norm(e.id), _norm(e.id.replace("_", " "))}
            # people say 「不要太正式」, not 「不要正式感」
            for suffix in ("感", "的", "風", "版型", "色彩", "材質", "圖案"):
                lab = _norm(e.label)
                if lab.endswith(suffix) and len(lab) > len(suffix) + 1:
                    forms.add(lab[: -len(suffix)])
            for f in forms:
                if f:
                    el.setdefault(f, e.id)
        vocab["design_element"] = el
    return vocab
