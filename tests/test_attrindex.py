"""The vectorised filter must match the row-by-row implementation exactly."""

import numpy as np
import pandas as pd
import pytest

from engine02.attrindex import AttrIndex
from engine02.constraints import _norm, _slot_mask, _slot_mask_indexed

VALUES = ["Navy Blue", "navy blue", " Navy Blue ", "White", None, float("nan"), "Olive", "olive"]


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 300
    col = [VALUES[i % len(VALUES)] for i in range(n)]
    sub = [["Shirts", "Tights", "Camisoles", "Jeans", None][i % 5] for i in range(n)]
    src = [["Marqo/polyvore", "kagl-fashion-product", None][i % 3] for i in range(n)]
    return pd.DataFrame(dict(item_id=[str(i) for i in range(n)], color=col, subcategory=sub,
                             category=[["top", "bottom", None][i % 3] for i in range(n)],
                             gender=[["Men", "women", None][i % 3] for i in range(n)],
                             occasion=[None] * n, season=[None] * n, source=src,
                             title=[f"t{i}" for i in range(n)],
                             image_path=[f"images/{i}.jpg" for i in range(n)]))


@pytest.mark.parametrize("col, values", [
    ("color", ["Navy Blue"]),
    ("color", ["navy blue", "white"]),
    ("color", ["NAVY BLUE "]),            # caller-side whitespace/case
    ("color", ["nope"]),
    ("color", []),
    ("gender", ["Men", "Women"]),
    ("category", ["top"]),
])
@pytest.mark.parametrize("allow_unknown", [False, True])
def test_indexed_slot_mask_matches_row_by_row(col, values, allow_unknown):
    df = frame()
    slow = _slot_mask(df[col], values, allow_unknown)
    fast = _slot_mask_indexed(df, col, values, allow_unknown)
    assert fast is not None
    assert np.array_equal(slow, fast), (col, values, allow_unknown)


def test_indexed_slot_mask_matches_with_subcategory_fallback():
    df = frame()
    for values in (["Shirts"], ["top", "jeans"], ["Tights"]):
        slow = _slot_mask(df["category"], values, False, df["subcategory"])
        fast = _slot_mask_indexed(df, "category", values, False, "subcategory")
        assert np.array_equal(slow, fast), values


def test_pair_mask_matches_the_python_loop():
    """Per-source resolution: the same value can belong to different nodes in two vocabularies."""
    from engine02.taxonomy import _source_key

    df = frame()
    idx = AttrIndex.get(df)
    scodes, slookup = idx.source_codes(_source_key, "t", default=None)
    subs = df["subcategory"].astype(object).to_numpy()
    srcs = [(_source_key(s) or "") for s in df["source"].to_numpy()]

    for pairs in ({("polyvore", "Tights"), ("kagl", "Shirts")},
                  {("kagl", "Tights")},
                  {("polyvore", "Camisoles"), ("polyvore", "Jeans")},
                  set()):
        vals_any = {v for _, v in pairs}
        slow = np.array([((s, v) in pairs) if s else (v in vals_any) for s, v in zip(srcs, subs)], dtype=bool)
        fast = idx.pair_mask(pairs, "subcategory", scodes, slookup)
        assert np.array_equal(slow, fast), pairs


def test_index_is_cached_per_frame_not_shared_between_views():
    df = frame()
    view = df.copy()
    view["color"] = ["Blue"] * len(view)          # what provenance_filter does for colour families
    a, b = AttrIndex.get(df), AttrIndex.get(view)
    assert a is not b
    assert AttrIndex.get(df) is a                  # same frame → same index
    assert not AttrIndex.get(view).mask("color", ["Navy Blue"]).any()
    assert AttrIndex.get(df).mask("color", ["Navy Blue"]).any()


def test_krippendorff_alpha_sees_the_na_disagreements_kappa_drops():
    """The headline agreement statistic must not delete the hardest cases."""
    import importlib.util
    from pathlib import Path as _P

    spec = importlib.util.spec_from_file_location(
        "eha", _P(__file__).resolve().parents[1] / "scripts" / "eval_human_agreement.py")
    eha = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eha)

    # both raters agree on every 1/0 pair, but disagree on every applicability call
    pairs = [("1", "1")] * 10 + [("0", "0")] * 10 + [("1", "na")] * 10 + [("0", "na")] * 10
    k, n_k = eha.cohens_kappa([a for a, _ in pairs if a in "01" and _ in "01"],
                              [b for a, b in pairs if a in "01" and b in "01"])
    alpha, n_a = eha.krippendorff_alpha(pairs)
    assert n_k == 20 and n_a == 40, "kappa sees half the data, alpha sees all of it"
    assert k == pytest.approx(1.0), "on the 1/0 subset the raters agree perfectly"
    assert alpha < 0.75, f"alpha must pay for the 20 na disagreements, got {alpha}"


def test_krippendorff_alpha_is_one_for_perfect_agreement_and_zero_for_chance():
    import importlib.util
    from pathlib import Path as _P

    spec = importlib.util.spec_from_file_location(
        "eha", _P(__file__).resolve().parents[1] / "scripts" / "eval_human_agreement.py")
    eha = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eha)

    perfect = [("1", "1")] * 5 + [("0", "0")] * 5 + [("na", "na")] * 5
    assert eha.krippendorff_alpha(perfect)[0] == pytest.approx(1.0)
    # a rater who always says "1" against one who always says "0" is worse than chance
    assert eha.krippendorff_alpha([("1", "0")] * 10)[0] < 0.0
