"""Merge scripts/vlm_fill_catalog.py output into a catalog -- without ever overwriting a human label.

Rules this script enforces (not just documents):

  * a field the dataset already has is NEVER replaced; the model only fills fields that are empty;
  * every model-filled field is recorded in `attr_source` as "vlm:<model>", so it can be excluded
    from evaluation -- a model-filled column is not ground truth;
  * items the model judged not to be a wearable single product (size chart, multipack, not
    apparel) are dropped, and every drop is listed with its reason in vlm_fill_report.json;
  * new columns the dataset never had (fit, boldness, style) are added and marked as model output.

It also reports how far the model can be trusted, on this catalog, against whatever human labels
exist: category, colour family and pattern agreement, and -- because season has no ground truth --
agreement with unambiguous season words in the item's own description ("linen", "padded" ...).

    python scripts/apply_vlm_fill.py --catalog data/catalog/hm
    python scripts/apply_vlm_fill.py --catalog data/catalog/hm --out data/catalog/hm_filled

Writes <out>/items.parquet (images are linked, not copied) and <out>/vlm_fill_report.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Conservative on purpose: a word only counts if it points one way. "knit" (spring cardigans) and
# "cotton" (all year) are deliberately absent.
WARM = re.compile(r"\b(linen|sleeveless|airy|shorts?|sandals?|swim\w*|strappy|lightweight|breathable)\b", re.I)
COLD = re.compile(r"\b(wool|padded|down|fleece|thermal|quilted|faux fur|teddy|shearling|insulat\w+|lined hood)\b", re.I)
WARM_SEASONS, COLD_SEASONS = {"Spring", "Summer"}, {"Fall", "Winter"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--fill", default=None, help="vlm_fill_*.parquet (default: the one in the catalog)")
    ap.add_argument("--out", default=None, help="output catalog dir (default: <catalog>_filled)")
    a = ap.parse_args()

    from engine02.attribute_fill import color_family

    src = Path(a.catalog) if Path(a.catalog).is_absolute() else ROOT / a.catalog
    fill_path = Path(a.fill) if a.fill else sorted(src.glob("vlm_fill_*.parquet"))[-1]
    meta = json.loads(fill_path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    vals, model = meta["values"], meta["model"].split("/")[-1]
    tag = f"vlm:{model}"
    out = Path(a.out) if a.out else src.parent / f"{src.name}_filled"
    if out.resolve() == src.resolve():
        raise SystemExit("--out must differ from --catalog: the source catalog is never edited in place")

    items = pd.read_parquet(src / "items.parquet")
    fill = pd.read_parquet(fill_path)
    m = items.merge(fill, on="item_id", how="left", validate="one_to_one")
    for q in vals:
        m[f"vlm_{q}"] = [vals[q][int(i)] if pd.notna(i) and int(i) >= 0 else None for i in m[f"{q}_idx"]]
    # availability is decided PER QUESTION: a skipped question is empty, the others still count
    answered = {q: (m[f"{q}_idx"].fillna(-1).astype(int) >= 0) for q in vals}
    labelled = answered["product"]

    report: dict = {"model": meta["model"], "catalog": str(src.name), "n_items": len(m),
                    "n_labelled": int(labelled.sum()), "n_unlabelled": int((~labelled).sum()),
                    "answered_per_question": {q: int(v.sum()) for q, v in answered.items()}}

    # ---- agreement with human labels, measured before anything is changed ----------------------
    def agree(mask, a_col, b_col, key=lambda x: x):
        sub = m[mask & m[a_col].notna() & m[b_col].notna()]
        return {"n": len(sub), "agreement": round(float((sub[a_col].map(key) == sub[b_col].map(key)).mean()), 4)
                if len(sub) else None}
    report["agreement_with_dataset"] = {
        "category": agree(labelled, "category", "vlm_category"),
        "color_exact": agree(labelled, "color", "vlm_color"),
        "color_family": agree(labelled, "color", "vlm_color", key=color_family),
    }
    if "pattern" in m:
        report["agreement_with_dataset"]["pattern"] = agree(labelled, "pattern", "vlm_pattern")

    text = (m["title"].fillna("") + " " + m["description"].fillna("")).astype(str)
    warm, cold = text.str.contains(WARM), text.str.contains(COLD)
    clear = labelled & (warm ^ cold) & m["vlm_season"].notna()
    expected = np.where(warm[clear], "warm", "cold")
    got = m.loc[clear, "vlm_season"].map(lambda s: "warm" if s in WARM_SEASONS else "cold")
    report["season_vs_description_words"] = {
        "n_items_with_one_clear_word": int(clear.sum()),
        "agreement": round(float((got.to_numpy() == expected).mean()), 4) if clear.any() else None,
        "note": "season has no ground truth; this checks only items whose own text points one way"}

    # ---- drop what is not a wearable single product -------------------------------------------
    drop = labelled & (m["vlm_product"] != "ok")
    report["dropped"] = {"n": int(drop.sum()),
                         "by_reason": m.loc[drop, "vlm_product"].value_counts().to_dict(),
                         "items": m.loc[drop, ["item_id", "title", "vlm_product"]].to_dict("records")}
    m = m[~drop].copy()
    labelled = labelled[~drop]

    # ---- fill empty fields only, and say so in attr_source --------------------------------------
    filled_counts = {}
    attr_sources = []
    for i, row in m.iterrows():
        src_map = json.loads(row["attr_source"]) if isinstance(row.get("attr_source"), str) else {}
        attr_sources.append(src_map)
    for field in ("season", "occasion", "color"):
        can = answered[field].loc[m.index] & m[field].isna() & m[f"vlm_{field}"].notna()
        m.loc[can, field] = m.loc[can, f"vlm_{field}"]
        filled_counts[field] = int(can.sum())
        for pos in np.flatnonzero(can.to_numpy()):
            attr_sources[pos][field] = tag
    m["attr_source"] = [json.dumps(s) for s in attr_sources]
    m["season_p"] = m["season_p"].where(answered["season"].loc[m.index])
    m["occasion_p"] = m["occasion_p"].where(answered["occasion"].loc[m.index])
    # columns the dataset never had: always model output
    m["fit"] = m["vlm_fit"]
    m["boldness"] = m["vlm_boldness"]
    m["style"] = m["vlm_style"]
    m["model_fields"] = json.dumps({"fit": tag, "boldness": tag, "style": tag})
    report["filled"] = filled_counts
    report["coverage_after"] = {k: round(float(m[k].notna().mean()), 4)
                                for k in ("color", "season", "occasion", "gender", "fit", "boldness", "style")}
    report["distribution"] = {k: m[k].value_counts().to_dict() for k in ("season", "occasion", "boldness", "style")}

    keep = [c for c in items.columns] + ["season_p", "occasion_p", "fit", "boldness", "style", "model_fields"]
    out.mkdir(parents=True, exist_ok=True)
    m[keep].reset_index(drop=True).to_parquet(out / "items.parquet", index=False)
    img_src, img_dst = src / "images", out / "images"
    if img_src.exists() and not img_dst.exists():
        try:
            os.symlink(img_src.resolve(), img_dst, target_is_directory=True)
        except OSError:
            shutil.copytree(img_src, img_dst)
    for f in ("README.md", "stats.json"):
        if (src / f).exists():
            shutil.copy2(src / f, out / f)
    (out / "vlm_fill_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str),
                                              encoding="utf-8")
    show = {k: report[k] for k in ("n_items", "n_labelled", "agreement_with_dataset",
                                   "season_vs_description_words", "filled", "coverage_after")}
    show["dropped"] = {k: report["dropped"][k] for k in ("n", "by_reason")}
    print(json.dumps(show, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
