import json

import numpy as np
import pandas as pd
import pytest

from engine02 import attribute_fill as AF
from engine02.catalog import Catalog
from engine02.constraints import filter_with_relaxation
from engine02.contracts import HardConstraints, Slot, SlotState
from engine02.encoders import HashEncoder


def _items():
    rows = [
        ("k1", "top", "Navy Blue", "Men", "Casual", "Summer", "dataset"),
        ("k2", "top", "Black", "Women", "Formal", "Winter", "dataset"),
        ("p1", "outerwear", None, None, None, None, "null"),
        ("p2", "outerwear", None, None, None, None, "null"),
        ("p3", "dress", None, None, None, None, "null"),
    ]
    return pd.DataFrame([dict(item_id=i, title=i, category=c, subcategory=None, color=col, gender=g, occasion=o,
                              season=s, price=None, image_path=f"images/{i}.jpg",
                              attr_source=json.dumps({a: src for a in ("color", "season", "occasion", "gender")}))
                         for i, c, col, g, o, s, src in rows])


def test_color_family_mapping_covers_kagl_vocabulary():
    assert AF.color_family("Navy Blue") == "blue" and AF.color_family("off white") == "white"
    assert AF.color_family("Multi") is None and AF.color_family(None) is None and AF.color_family("blue") == "blue"
    assert len(AF.FAMILY) == 12
    assert all(AF.color_family(AF.FAMILY_CANONICAL[f]) == f for f in AF.FAMILY)


def test_zero_shot_with_hash_encoder_prefers_matching_prompt():
    enc = HashEncoder(dim=256)
    zs = AF.ZeroShotPredictor(enc, "family", temperature=0.05)
    img = enc.encode_text(["a photo of a red top"])  # 'image' embedding that shares the red prompt's words
    p = zs.predict_proba(img, nouns=["top"])
    assert p.shape == (1, 12) and np.isclose(p.sum(), 1)
    assert AF.FAMILY[p.argmax()] == "red"


def test_calibration_metrics():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 2000)
    logits = np.eye(3)[y] * 2.0 + rng.normal(0, 1.0, (2000, 3))
    t = AF.fit_temperature(logits, y)
    assert AF.ece(AF.softmax(logits, t), y) <= AF.ece(AF.softmax(logits, 0.1), y)
    perfect = np.eye(3)[y]
    assert AF.ece(perfect, y) == pytest.approx(0.0)
    assert AF.macro_f1(y, y, 3) == pytest.approx(1.0)
    cov, acc = AF.coverage_at(AF.softmax(logits, t), y, 0.0)
    assert cov == 1.0 and 0 < acc < 1
    thr = AF.threshold_for_precision(AF.softmax(logits, t), y, 0.9)
    cov9, acc9 = AF.coverage_at(AF.softmax(logits, t), y, thr)
    assert acc9 >= 0.9 and cov9 < 1


def test_restrict_and_decide_abstain():
    p = np.array([[0.5, 0.3, 0.2], [0.1, 0.1, 0.8]])
    r = AF.restrict(p, ["Men", "Women", "Unisex"], ["Men", "Women"])
    assert np.allclose(r.sum(axis=1), 1) and r[1, 0] == pytest.approx(0.5)
    vals, conf = AF.decide(p, ["a", "b", "c"], threshold=0.6)
    assert vals == [None, "c"] and conf[1] == pytest.approx(0.8)


def test_vlm_prompt_and_option_probs():
    prompt = AF.build_mc_prompt()
    assert "Q5." in prompt and "M) multicolor" in prompt
    letter_ids = {"": list(range(100, 116)), " ": list(range(200, 216))}
    steps, variants = [], []
    for qi, (_, _, opts) in enumerate(AF.VLM_QUESTIONS):
        z = np.zeros(300)
        z[200 + len(opts) - 1] = 5.0  # pick the last option, with a " X" token
        steps.append(z)
        variants.append({"prefix": " "})
    out = AF.option_probs(steps, variants, letter_ids)
    assert out["family"].shape == (13,) and out["family"].argmax() == 12
    assert AF.option_probs(steps[:-1], variants, letter_ids) is None


def test_fill_never_overwrites_metadata_and_marks_provenance():
    items = _items()
    preds = {
        "color": pd.DataFrame(dict(item_id=["k1", "p1", "p2"], value=["Red", "Blue", "Black"],
                                   confidence=[0.99, 0.9, 0.3], model="m")),
        "gender": pd.DataFrame(dict(item_id=["p1", "p3"], value=["Women", "Women"], confidence=[0.95, 0.8], model="m")),
    }
    out = AF.fill_attributes(items, preds, thresholds={"color": 0.5, "gender": 0.5})
    assert out.loc[0, "color"] == "Navy Blue"  # metadata kept
    assert out.loc[2, "color"] == "Blue" and pd.isna(out.loc[3, "color"])  # p2 abstained
    src = json.loads(out.loc[2, "attr_source"])
    assert src["color"] == "predicted:m" and src["gender"] == "predicted:m" and src["occasion"] == "null"
    assert json.loads(out.loc[0, "attr_source"])["color"] == "dataset"
    assert out.loc[2, "color_confidence"] == pytest.approx(0.9) and np.isnan(out.loc[0, "color_confidence"])
    assert list(out["color_family"])[:3] == ["blue", "black", "blue"]
    assert AF.is_predicted(out, "color").tolist() == [False, False, True, False, False]
    assert AF.provenance_note(out, 2) == {"color": "顏色為模型判讀", "gender": "性別為模型判讀"}
    assert pd.isna(items.loc[2, "color"])  # input untouched


def _hc(**kw):
    return HardConstraints(**{k: Slot(state=SlotState.VALUE, values=v) for k, v in kw.items()})


def test_provenance_filter_policies():
    items = AF.fill_attributes(_items(), {
        "color": pd.DataFrame(dict(item_id=["p1", "p2"], value=["Blue", "Blue"], confidence=[0.9, 0.6], model="m")),
        "gender": pd.DataFrame(dict(item_id=["p1", "p2", "p3"], value=["Men"] * 3, confidence=[0.9] * 3, model="m")),
    }, thresholds={"color": 0.5, "gender": 0.5})
    c = _hc(color=["Navy Blue"], gender=["Men"])
    exact = filter_with_relaxation(items, c, min_results=1)
    assert np.flatnonzero(exact.mask).tolist() == [0]  # 'Blue' != 'Navy Blue'
    fam = AF.provenance_filter("family")(items, c, 1)
    assert np.flatnonzero(fam.mask).tolist() == [0, 2, 3]
    conf = AF.provenance_filter("family", min_confidence=0.8)(items, c, 3)
    # p2 (low conf) and p3 (no colour) become unknown → admitted only via the relaxation ladder
    assert np.flatnonzero(conf.mask).tolist() == [0, 2, 3, 4] and conf.relaxed == ["color:allow_unknown"]
    unk = AF.provenance_filter("unknown")(items, c, 1)
    assert np.flatnonzero(unk.mask).tolist() == [0]  # predicted gender ignored → Polyvore unreachable
    assert items.loc[2, "color"] == "Blue"  # filter never mutates the catalog


def test_engine_accepts_filled_catalog(tmp_path, monkeypatch):
    from engine02 import pipeline
    from engine02.contracts import Engine02Options, Engine02Request

    items = AF.fill_attributes(_items(), {
        "color": pd.DataFrame(dict(item_id=["p1"], value=["Blue"], confidence=[0.9], model="m"))}, {"color": 0.5})
    cat = Catalog(items=items, root=tmp_path, name="toy")
    eng = pipeline.Engine02(cat, HashEncoder(dim=64), cache_dir=tmp_path / "idx")
    monkeypatch.setattr(pipeline, "filter_with_relaxation", AF.provenance_filter("family"))
    req = Engine02Request(session_id="s", retrieval_text="blue jacket", constraints=_hc(category=["outerwear"], color=["Navy Blue"]),
                          options=Engine02Options(top_k=1, explain_with_llm=False))
    resp = eng.run(req, "full")
    assert [it.item_id for it in resp.items] == ["p1"]
