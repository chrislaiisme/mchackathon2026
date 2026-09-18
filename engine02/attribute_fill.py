"""Attribute filling for catalog items that lack colour / gender / occasion / season metadata.

Motivation: the merged catalog (KAGL + Polyvore) has ~12.8k Polyvore items with null colour,
gender, occasion and season, so ENGINE 02 hard filters either exclude them (gender is never
relaxed) or admit them unverified (colour/occasion ``allow_unknown``). This module predicts
those attributes from the product image, abstains below a confidence threshold (the value stays
null) and records provenance so explanations can say "顏色為模型判讀".

Predictors (all return an (n, n_labels) probability matrix over a fixed label list):

* ``ZeroShotPredictor`` — CLIP-style zero-shot classification with prompt ensembles
  (Radford et al., "Learning Transferable Visual Models From Natural Language Supervision",
  ICML 2021, arXiv:2103.00020, §3.1.4 prompt engineering/ensembling). Text embeddings of all
  templates of a label are averaged and re-normalised; probabilities are softmax(image·text / T).
* ``LinearProbePredictor`` — multinomial logistic regression on frozen image embeddings
  (the "linear probe" protocol of the same paper, §3.2), trained on KAGL metadata.
* VLM multiple choice — ``build_mc_prompt`` / ``option_probs`` implement the letter-answer
  protocol of ``scripts/vlm_tag_attributes.py`` (answer letters comma-separated, each answer
  step one single-letter token; P(option) = softmax over the option letters' logits at that
  step), cf. Robinson & Wingate, "Leveraging Large Language Models for Multiple Choice Question
  Answering", ICLR 2023, arXiv:2210.12353 (multiple-choice symbol binding).

Calibration: temperature scaling (Guo et al., "On Calibration of Modern Neural Networks",
ICML 2017, arXiv:1706.04599) fitted on a dev split; ECE with equal-width confidence bins.
Abstention: selective classification with a confidence threshold (Geifman & El-Yaniv,
"Selective Classification for Deep Neural Networks", NeurIPS 2017, arXiv:1705.08500).

Provenance rule (see docs/research/classify.md): metadata values are never overwritten;
a filled value sets ``attr_source[attr] = "predicted:<model>"`` and ``<attr>_confidence``.
``provenance_filter`` is a drop-in replacement for ``constraints.filter_with_relaxation``
that matches predicted colours at colour-family level.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from .encoders import l2n

# ---------------------------------------------------------------------------------------------
# label spaces (KAGL vocabulary is the ground truth)
# ---------------------------------------------------------------------------------------------
COARSE = ("top", "bottom", "outerwear", "dress", "shoes", "bag", "accessory", "jewelry", "other")
GENDER = ("Men", "Women", "Unisex", "Boys", "Girls")
GENDER_FILL = ("Men", "Women", "Unisex")  # labels we write into the catalog
OCCASION = ("Casual", "Formal", "Sports", "Ethnic")
SEASON = ("Summer", "Fall", "Winter", "Spring")

# 12 colour families; KAGL baseColour → family. "Multi" has no family (excluded from family eval).
COLOR_FAMILIES: dict[str, tuple[str, ...]] = {
    "black": ("Black",),
    "white": ("White", "Off White", "Cream"),
    "grey": ("Grey", "Charcoal", "Grey Melange", "Steel", "Silver", "Metallic"),
    "blue": ("Blue", "Navy Blue", "Turquoise Blue", "Teal"),
    "red": ("Red", "Maroon", "Burgundy", "Rust"),
    "pink": ("Pink", "Magenta", "Rose", "Peach", "Mauve"),
    "purple": ("Purple", "Lavender"),
    "green": ("Green", "Olive", "Sea Green", "Lime Green", "Fluorescent Green"),
    "yellow": ("Yellow", "Mustard", "Gold"),
    "orange": ("Orange",),
    "brown": ("Brown", "Coffee Brown", "Mushroom Brown", "Tan", "Taupe", "Bronze", "Copper"),
    "beige": ("Beige", "Skin", "Nude", "Khaki"),
}
FAMILY = tuple(COLOR_FAMILIES)
COLOR_TO_FAMILY = {c.lower(): fam for fam, cols in COLOR_FAMILIES.items() for c in cols}
# value written into the catalog `color` column for a predicted family (KAGL vocabulary)
FAMILY_CANONICAL = {f: COLOR_FAMILIES[f][0] for f in FAMILY}


def color_family(color) -> str | None:
    if color is None or (isinstance(color, float) and np.isnan(color)):
        return None
    c = str(color).strip().lower()
    if c in COLOR_TO_FAMILY:
        return COLOR_TO_FAMILY[c]
    return c if c in COLOR_FAMILIES else None


# natural-language phrases used by zero-shot prompts and the VLM options
PHRASES: dict[str, dict[str, list[str]]] = {
    "gender": {"Men": ["men's", "male"], "Women": ["women's", "female"], "Unisex": ["unisex"],
               "Boys": ["boys'", "kids boys"], "Girls": ["girls'", "kids girls"]},
    "occasion": {"Casual": ["casual", "everyday casual"], "Formal": ["formal", "office formal"],
                 "Sports": ["sports", "athletic sportswear"], "Ethnic": ["ethnic Indian", "traditional Indian ethnic"]},
    "season": {"Summer": ["summer"], "Fall": ["fall", "autumn"], "Winter": ["winter", "warm winter"],
               "Spring": ["spring"]},
    "family": {"black": ["black"], "white": ["white", "off-white cream"], "grey": ["grey", "charcoal grey", "silver"],
               "blue": ["blue", "navy blue"], "red": ["red", "maroon"], "pink": ["pink", "peach"],
               "purple": ["purple", "lavender"], "green": ["green", "olive green"],
               "yellow": ["yellow", "mustard"], "orange": ["orange"], "brown": ["brown", "tan"],
               "beige": ["beige", "khaki"]},
    "category": {"top": ["top", "t-shirt", "shirt", "sweater", "blouse", "kurta"],
                 "bottom": ["trousers", "jeans", "shorts", "skirt", "leggings"],
                 "outerwear": ["jacket", "coat", "blazer", "waistcoat vest"],
                 "dress": ["dress", "jumpsuit", "gown"],
                 "shoes": ["shoes", "sneakers", "sandals", "heels", "boots"],
                 "bag": ["handbag", "backpack", "clutch bag", "tote bag"],
                 "accessory": ["watch", "sunglasses", "belt", "wallet", "socks", "cap hat", "scarf", "tie"],
                 "jewelry": ["earrings", "necklace", "ring", "bracelet", "pendant"],
                 "other": ["lipstick", "perfume bottle", "nail polish", "underwear briefs", "bra", "saree",
                           "nightwear", "home decor", "makeup"]},
}
NOUN = {"top": "top", "bottom": "bottom", "outerwear": "jacket", "dress": "dress", "shoes": "shoes",
        "bag": "bag", "accessory": "accessory", "jewelry": "jewelry", "other": "product"}


def label_space(attr: str) -> tuple[str, ...]:
    return {"category": COARSE, "gender": GENDER, "occasion": OCCASION, "season": SEASON, "family": FAMILY}[attr]


def prompts_for(attr: str, label: str, noun: str = "garment") -> list[str]:
    """Prompt ensemble for one label. ``noun`` is the item's coarse-category noun (known for every item)."""
    words = PHRASES[attr][label]
    if attr == "category":
        return [t.format(w=w) for w in words for t in ("a photo of a {w}", "a product photo of a {w}", "{w}")]
    if attr == "season":
        return [t.format(w=w, n=noun) for w in words
                for t in ("a photo of a {w} {n}", "a {n} to wear in {w}", "{w} clothing")]
    return [t.format(w=w, n=noun) for w in words for t in ("a photo of a {w} {n}", "a product photo of a {w} {n}", "{w} {n}")]


# ---------------------------------------------------------------------------------------------
# probability utilities
# ---------------------------------------------------------------------------------------------
def softmax(z: np.ndarray, t: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64) / t
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(logits: np.ndarray, y: np.ndarray, grid: Sequence[float] | None = None) -> float:
    """Temperature scaling (Guo et al. 2017): T minimising NLL on held-out labels (y = int index)."""
    grid = grid if grid is not None else np.exp(np.linspace(np.log(0.05), np.log(20.0), 121))
    best, best_t = np.inf, 1.0
    for t in grid:
        p = softmax(logits, t)
        nll = -np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None)))
        if nll < best:
            best, best_t = nll, float(t)
    return best_t


def ece(probs: np.ndarray, y: np.ndarray, n_bins: int = 15) -> float:
    """Expected calibration error of the top-label confidence (equal-width bins)."""
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == y).astype(float)
    bins = np.minimum((conf * n_bins).astype(int), n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        m = bins == b
        if m.any():
            total += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(total)


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, n_labels: int) -> float:
    f1s = []
    for c in range(n_labels):
        tp = np.sum((y_pred == c) & (y_true == c))
        fp = np.sum((y_pred == c) & (y_true != c))
        fn = np.sum((y_pred != c) & (y_true == c))
        if tp + fn == 0:  # class absent from ground truth: not counted
            continue
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f1s)) if f1s else float("nan")


def restrict(probs: np.ndarray, labels: Sequence[str], keep: Sequence[str]) -> np.ndarray:
    """Marginalise onto a label subset by dropping other columns and renormalising."""
    idx = [list(labels).index(k) for k in keep]
    p = probs[:, idx]
    return p / np.clip(p.sum(axis=1, keepdims=True), 1e-12, None)


def coverage_at(probs: np.ndarray, y: np.ndarray, threshold: float) -> tuple[float, float]:
    """(coverage, selective accuracy) when abstaining below ``threshold``."""
    conf = probs.max(axis=1)
    keep = conf >= threshold
    acc = float((probs.argmax(axis=1)[keep] == y[keep]).mean()) if keep.any() else float("nan")
    return float(keep.mean()), acc


def threshold_for_precision(probs: np.ndarray, y: np.ndarray, target: float, min_n: int = 20) -> float | None:
    """Smallest confidence threshold whose selective accuracy on (dev) data reaches ``target``."""
    conf = probs.max(axis=1)
    correct = probs.argmax(axis=1) == y
    order = np.argsort(-conf)
    cum = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    ok = np.flatnonzero((cum >= target) & (np.arange(1, len(order) + 1) >= min_n))
    if not len(ok):
        return None
    return float(conf[order][ok.max()])


# ---------------------------------------------------------------------------------------------
# predictors
# ---------------------------------------------------------------------------------------------
@dataclass
class ZeroShotPredictor:
    """Prompt-ensemble zero-shot classifier over a shared image/text embedding space."""

    encoder: object  # engine02.encoders.Encoder
    attr: str
    labels: tuple[str, ...] | None = None
    temperature: float = 0.01  # CLIP logit scale 100
    pool: str = "mean"  # "mean": one averaged prompt vector per label; "max": best-matching synonym per label
    _cache: dict[str, list[np.ndarray]] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self.labels = tuple(self.labels or label_space(self.attr))

    def text_vectors(self, noun: str = "garment") -> list[np.ndarray]:
        """Per label: (n_synonyms, dim) template-averaged vectors (one row when pool == "mean")."""
        if noun not in self._cache:
            n_tpl = len(prompts_for(self.attr, self.labels[0], noun)) // len(PHRASES[self.attr][self.labels[0]])
            vecs = []
            for lab in self.labels:
                e = self.encoder.encode_text(prompts_for(self.attr, lab, noun))
                if self.pool == "max":
                    per_word = e.reshape(len(PHRASES[self.attr][lab]), n_tpl, -1).mean(axis=1)
                    vecs.append(l2n(per_word))
                else:
                    vecs.append(l2n(e.mean(axis=0, keepdims=True)))
            self._cache[noun] = vecs
        return self._cache[noun]

    def logits(self, image_emb: np.ndarray, nouns: Sequence[str] | None = None) -> np.ndarray:
        """Cosine similarities (n, n_labels); per-item noun lets prompts name the item's category."""
        image_emb = np.asarray(image_emb, dtype=np.float32)
        nouns = np.asarray(list(nouns)) if nouns is not None else np.full(len(image_emb), "garment")
        out = np.zeros((len(image_emb), len(self.labels)), np.float32)
        for n in np.unique(nouns):
            m = nouns == n
            for j, v in enumerate(self.text_vectors(str(n))):
                out[m, j] = (image_emb[m] @ v.T).max(axis=1)
        return out

    def predict_proba(self, image_emb: np.ndarray, nouns: Sequence[str] | None = None) -> np.ndarray:
        return softmax(self.logits(image_emb, nouns), self.temperature)


@dataclass
class LinearProbePredictor:
    """Multinomial logistic regression on frozen L2-normalised image embeddings."""

    labels: tuple[str, ...]
    C: float = 1.0
    max_iter: int = 2000
    model: object = None

    def fit(self, emb: np.ndarray, y: Sequence[str]) -> "LinearProbePredictor":
        from sklearn.linear_model import LogisticRegression

        yi = np.array([self.labels.index(v) for v in y])
        self.model = LogisticRegression(C=self.C, max_iter=self.max_iter).fit(emb, yi)
        return self

    def predict_proba(self, emb: np.ndarray) -> np.ndarray:
        p = self.model.predict_proba(emb)
        full = np.zeros((len(emb), len(self.labels)))
        full[:, self.model.classes_] = p  # classes never seen in training keep probability 0
        return full


# ---------------------------------------------------------------------------------------------
# VLM multiple-choice protocol (model-free parts; the torch runner is in scripts/eval_classify.py)
# ---------------------------------------------------------------------------------------------
LETTERS = "ABCDEFGHIJKLMNOP"
VLM_QUESTIONS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("category", "What kind of product is shown?", [
        ("top", "top (t-shirt, shirt, sweater, blouse, kurta)"), ("bottom", "bottom (trousers, jeans, shorts, skirt)"),
        ("outerwear", "outerwear (jacket, coat, blazer, waistcoat)"), ("dress", "dress or jumpsuit"),
        ("shoes", "shoes or sandals"), ("bag", "bag"),
        ("accessory", "accessory (watch, belt, sunglasses, wallet, socks, cap, scarf, tie)"),
        ("jewelry", "jewelry"), ("other", "other (beauty product, underwear, nightwear, saree, home item)")]),
    ("gender", "Who is it designed for?", [("Men", "men"), ("Women", "women"), ("Unisex", "unisex"),
                                          ("Boys", "boys"), ("Girls", "girls")]),
    ("family", "Main color?", [(f, PHRASES["family"][f][-1] if f in ("white", "grey") else f) for f in FAMILY]
     + [("multi", "multicolor")]),
    ("occasion", "Usage occasion?", [("Casual", "casual"), ("Formal", "formal"), ("Sports", "sports"),
                                     ("Ethnic", "ethnic or traditional")]),
    ("season", "Best season?", [("Summer", "summer"), ("Fall", "fall"), ("Winter", "winter"), ("Spring", "spring")]),
]


def build_mc_prompt(questions=VLM_QUESTIONS) -> str:
    lines = ["Look at the product image and answer each question with a single letter.", ""]
    for i, (_, q, opts) in enumerate(questions, 1):
        lines.append(f"Q{i}. {q} " + " ".join(f"{LETTERS[j]}) {text}" for j, (_, text) in enumerate(opts)))
    example = ", ".join(LETTERS[i % 2] for i in range(len(questions)))
    lines += ["", f"Reply with exactly {len(questions)} letters separated by commas and nothing else, e.g. {example}"]
    return "\n".join(lines)


def option_probs(step_logits: Sequence[np.ndarray], step_variants: Sequence[dict[str, int]] | None,
                 letter_ids: dict[str, list[int]], questions=VLM_QUESTIONS) -> dict[str, np.ndarray] | None:
    """Per-question option probabilities from the logits at the answer steps.

    ``step_logits[q]``: vocabulary logits at the q-th answer step; ``letter_ids[prefix]``: token id of
    each letter A.. for tokenizer prefix "" or " "; ``step_variants[q]["prefix"]`` says which variant
    was generated. Returns None when the number of answer steps is wrong (never guess an alignment).
    """
    if len(step_logits) != len(questions):
        return None
    out = {}
    for qi, (qid, _, opts) in enumerate(questions):
        pre = step_variants[qi]["prefix"] if step_variants else ""
        ids = letter_ids[pre][: len(opts)]
        z = np.asarray(step_logits[qi], dtype=np.float64)[ids]
        out[qid] = softmax(z[None, :])[0]
    return out


# ---------------------------------------------------------------------------------------------
# filling a catalog with provenance
# ---------------------------------------------------------------------------------------------
FILL_ATTRS = ("color", "gender", "occasion", "season")


def _is_null(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


def decide(probs: np.ndarray, labels: Sequence[str], threshold: float) -> tuple[list[str | None], np.ndarray]:
    """Argmax label per row, or None (abstain) when max probability < threshold."""
    conf = probs.max(axis=1)
    arg = probs.argmax(axis=1)
    vals = [labels[a] if c >= threshold else None for a, c in zip(arg, conf)]
    return vals, conf


def fill_attributes(items: pd.DataFrame, predictions: dict[str, pd.DataFrame], thresholds: dict[str, float],
                    only_null: bool = True) -> pd.DataFrame:
    """Return a copy of ``items`` with predicted attributes written where metadata is null.

    ``predictions[attr]`` has columns item_id, value (catalog vocabulary), confidence, model.
    Rules: (1) metadata values are never overwritten; (2) predictions below ``thresholds[attr]``
    are not written (value stays null → the relaxation ladder's allow_unknown still applies);
    (3) ``attr_source[attr] = "predicted:<model>"`` and ``<attr>_confidence`` are set;
    (4) for colour a ``color_family`` column is added for all rows (metadata-derived or predicted).
    """
    out = items.copy()
    src = [json.loads(s) if isinstance(s, str) and s else {} for s in out.get("attr_source", [None] * len(out))]
    pos = {str(i): p for p, i in enumerate(out["item_id"].astype(str))}
    for attr, pred in predictions.items():
        col_conf = f"{attr}_confidence"
        if col_conf not in out.columns:
            out[col_conf] = np.nan
        values = out[attr].astype(object).tolist()
        conf_col = out[col_conf].to_numpy(dtype=float, copy=True)
        thr = thresholds.get(attr, 0.0)
        for r in pred.itertuples(index=False):
            p = pos.get(str(r.item_id))
            if p is None or _is_null(r.value) or r.confidence < thr:
                continue
            if only_null and not _is_null(values[p]):
                continue
            values[p] = r.value
            conf_col[p] = float(r.confidence)
            src[p][attr] = f"predicted:{r.model}"
        out[attr] = values
        out[col_conf] = conf_col
    for s in src:  # make every attribute's provenance explicit
        for a in FILL_ATTRS:
            s.setdefault(a, "null")
    out["attr_source"] = [json.dumps(s) for s in src]
    out["color_family"] = [color_family(c) for c in out["color"]]
    return out


# `attr_source` is one JSON string per row, so a naive is_predicted() parses the whole catalog on
# every call — 711k json.loads for five requests (≈0.6 s each) once the filter and the metrics both
# ask. The column never changes for a loaded catalog, so parse it once per frame.
_PRED_CACHE: dict[tuple[int, int], dict[str, np.ndarray]] = {}
_PRED_KEEPALIVE: dict[tuple[int, int], pd.DataFrame] = {}


def _predicted_map(items: pd.DataFrame) -> dict[str, np.ndarray]:
    key = (id(items), len(items))
    hit = _PRED_CACHE.get(key)
    if hit is not None:
        return hit
    out: dict[str, np.ndarray] = {}
    if "attr_source" in items.columns:
        parsed = [json.loads(s) if isinstance(s, str) and s else {} for s in items["attr_source"]]
        attrs = {a for d in parsed for a in d}
        for a in attrs:
            out[a] = np.fromiter((str(d.get(a, "")).startswith("predicted:") for d in parsed),
                                 dtype=bool, count=len(parsed))
    _PRED_CACHE[key] = out
    _PRED_KEEPALIVE[key] = items  # keep the frame alive so id() cannot be reused by another object
    return out


def is_predicted(items: pd.DataFrame, attr: str) -> np.ndarray:
    got = _predicted_map(items).get(attr)
    return got if got is not None else np.zeros(len(items), dtype=bool)


def provenance_note(items: pd.DataFrame, pos: int) -> dict[str, str]:
    """Attribute → Traditional-Chinese note for explanations, only for predicted attributes."""
    names = {"color": "顏色", "gender": "性別", "occasion": "場合", "season": "季節"}
    src = items["attr_source"].to_numpy() if "attr_source" in items.columns else None
    s = src[pos] if src is not None else None
    d = json.loads(s) if isinstance(s, str) and s else {}
    return {a: f"{names.get(a, a)}為模型判讀" for a, v in d.items() if str(v).startswith("predicted:")}


# ---------------------------------------------------------------------------------------------
# provenance-aware hard filter (drop-in for constraints.filter_with_relaxation)
# ---------------------------------------------------------------------------------------------
def provenance_filter(predicted_policy: str = "family", min_confidence: float = 0.0,
                      base: Callable | None = None) -> Callable:
    """Build a ``filter_with_relaxation`` replacement.

    predicted_policy:
      "family"  – colour constraints match at colour-family level ("Navy Blue" query matches any blue);
                  applies to every row, since users' colour words are family-level most of the time.
      "exact"   – unchanged string matching (baseline behaviour).
      "unknown" – predicted values are treated as null (only admitted by the ladder's allow_unknown).
    min_confidence: predicted values below it are treated as null at query time.
    """
    from . import constraints as C

    base = base or C.filter_with_relaxation

    # Both views depend only on the catalog, never on the request, so build each at most once per
    # frame. Before this cache a colour-constrained request rebuilt a 17.8k-row copy and re-mapped
    # every colour on every call (and the metrics asked for it a second time).
    views: dict[tuple[int, int, bool], pd.DataFrame] = {}
    keepalive: list[pd.DataFrame] = []

    def _view(items: pd.DataFrame, family: bool) -> pd.DataFrame:
        key = (id(items), len(items), family)
        hit = views.get(key)
        if hit is not None:
            return hit
        view = items
        changed = False
        for attr in FILL_ATTRS:
            conf_col = f"{attr}_confidence"
            pred = is_predicted(items, attr)
            if not pred.any():
                continue
            drop = np.zeros(len(items), dtype=bool)
            if predicted_policy == "unknown":
                drop = pred
            elif min_confidence > 0 and conf_col in items.columns:
                drop = pred & (items[conf_col].to_numpy(dtype=float) < min_confidence)
            if drop.any():
                if not changed:
                    view, changed = items.copy(), True
                view.loc[drop, attr] = None
        if family:
            if not changed:
                view, changed = items.copy(), True
            view["color"] = [color_family(v) for v in view["color"]]
        views[key] = view
        keepalive.append(items)  # hold a reference so id(items) cannot be recycled
        return view

    def _prepare(items: pd.DataFrame, c) -> tuple[pd.DataFrame, object]:
        family = predicted_policy in ("family", "unknown") and bool(c.color.values)
        view = _view(items, family)
        if family:
            fams = sorted({color_family(v) or str(v).lower() for v in c.color.values})
            c = c.model_copy(deep=True)
            c.color.values = fams
            for d in (c.excluded_values, c.required_values):
                if "color" in d:
                    d["color"] = sorted({color_family(v) or str(v).lower() for v in d["color"]})
        return view, c

    def filter_fn(items, c, min_results, excluded_positions=None, ladder=C.DEFAULT_LADDER):
        view, c2 = _prepare(items, c)
        return base(view, c2, min_results, excluded_positions, ladder)

    # the rule-based metrics must judge with the same comparator the filter used, or the card says
    # "0% of constraints satisfied" about items the filter deliberately admitted (colour family)
    filter_fn.prepare = _prepare
    filter_fn.policy = predicted_policy
    return filter_fn
