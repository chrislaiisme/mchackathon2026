"""Label-noise audit, attribute filling and ENGINE 02 impact (agent `classify`).

Stages (run in order on nycu; all outputs under --out):

  prep      splits for KAGL attribute eval (group-aware on colour/gender-stripped titles, stratified by
            subcategory; test ≥2,400 / dev ~1,000 / train rest) + Qwen item lists (stratified category sample)
  embed     image embeddings: copies shared caches, computes missing ones (fashion-clip on polyvore_big)
  zeroshot  CLIP prompt-ensemble logits (Marqo-FashionSigLIP, fashion-clip): category for all items of
            kagl_full + polyvore_big; gender / colour family / exact colour / occasion / season for scope items
  vlm       Qwen3-VL-8B multiple choice (5 questions, option probabilities) for an item list
  linear    logistic-regression probes on frozen embeddings (trained on KAGL train split)
  eval      attribute metrics on KAGL test (acc, macro-F1, ECE, coverage at dev thresholds, paired tests)
  audit     category agreement / confusion + stratified disagreement sample + contact sheets
  sheet     contact sheets for an id list (visual labelling by the agent)
  transfer  metrics on the agent's visual Polyvore labels
  fill      filled COPY of data/catalog/kagl_polyvore with provenance
  t2        T2-style constraint queries (outerwear, dress) before vs after filling

  python scripts/eval_classify.py prep --out /tmp/neil/agents/classify/out
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine02 import attribute_fill as AF  # noqa: E402
from engine02.eval.metrics import bootstrap_ci, paired_permutation_test  # noqa: E402

SCOPE = ("top", "bottom", "outerwear", "dress", "shoes", "bag")  # categories kept in kagl_polyvore
SHARED = Path("/tmp/neil/mchackathon2026/data/catalog")
ENCODERS = ("marqo-fashionSigLIP", "fashion-clip")
SEED = 0


def load(cat: str) -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data/catalog" / cat / "items.parquet")
    df["item_id"] = df["item_id"].astype(str)
    return df


def ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------------------------------------
def stage_prep(a):
    out = ensure(Path(a.out))
    k = load("kagl_full")
    rng = np.random.default_rng(SEED)
    colour_words = {w for c in k["color"].dropna().unique() for w in str(c).lower().split()}
    stop = colour_words | {"men", "women", "mens", "womens", "men's", "women's", "boys", "girls", "kids", "unisex"}
    key = k["title"].fillna("").str.lower().map(lambda t: " ".join(w for w in re.findall(r"[a-z]+", t) if w not in stop))
    k["group"] = key.where(key.str.len() > 0, k["item_id"])
    scope = k[k["category"].isin(SCOPE)].copy()
    share = scope["subcategory"].value_counts(normalize=True)
    size = scope["subcategory"].value_counts()
    need = {}
    for split, n_total in (("test", a.n_test), ("dev", a.n_dev)):
        need[split] = {s: int(min(max(8, round(n_total * share[s])), 0.3 * size[s])) for s in share.index}
    groups = scope.groupby("group")["subcategory"].agg(lambda s: s.value_counts().clip(upper=3).to_dict())
    order = rng.permutation(len(groups))
    assign = {}
    for gi in order:
        g, subs = groups.index[gi], groups.iloc[gi]
        for split in ("test", "dev"):
            if all(need[split][s] > 0 for s in subs):
                assign[g] = split
                for s, n_s in subs.items():
                    need[split][s] -= n_s
                break
        else:
            assign[g] = "train"
    # groups can be large (same product line): cap test/dev items per group to keep the set diverse
    scope["split"] = scope["group"].map(assign)
    for split in ("test", "dev"):
        m = scope["split"] == split
        rank = scope[m].groupby("group").cumcount()
        scope.loc[rank[rank >= 3].index, "split"] = "holdout_unused"  # never used for training either
    scope[["item_id", "category", "subcategory", "group", "split"]].to_parquet(out / "kagl_splits.parquet", index=False)
    # Qwen lists: KAGL test+dev + stratified category sample over all 9 categories; Polyvore: all items
    shuf = k.sample(frac=1, random_state=SEED)
    strat = shuf[shuf.groupby("category").cumcount() < a.cap_per_category]
    ids = set(strat["item_id"]) | set(scope.loc[scope["split"].isin(["test", "dev"]), "item_id"])
    k[k["item_id"].isin(ids)][["item_id"]].to_csv(out / "vlm_ids_kagl_full.csv", index=False)
    strat[["item_id", "category"]].to_csv(out / "category_sample_kagl_full.csv", index=False)
    print(json.dumps({"split": scope["split"].value_counts().to_dict(), "vlm_kagl": len(ids),
                      "strat": strat["category"].value_counts().to_dict()}))


# ------------------------------------------------------------------------------------------------
def stage_embed(a):
    from engine02.encoders import cached_image_embeddings
    from engine02.models import TorchEncoder

    emb_dir = ensure(Path(a.out) / "emb")
    for cat in ("kagl_full", "polyvore_big", "kagl_polyvore"):
        items = load(cat)
        for enc in ENCODERS:
            dst = emb_dir / f"{cat}__{enc}.npy"
            src = SHARED / cat / "index" / f"img_{enc}.npy"
            if dst.exists():
                continue
            if src.exists() and np.load(src, mmap_mode="r").shape[0] == len(items):
                shutil.copy(src, dst)
                print("copied", dst, flush=True)
                continue
            if cat == "kagl_polyvore":
                continue  # derived from the two sources below
            e = TorchEncoder(enc, device="cuda", batch_size=64)
            paths = [ROOT / "data/catalog" / cat / p for p in items["image_path"]]
            cached_image_embeddings(e, paths, dst, batch=256)
            print("computed", dst, flush=True)


def emb(a, cat: str, enc: str) -> np.ndarray:
    return np.load(Path(a.out) / "emb" / f"{cat}__{enc}.npy")


# ------------------------------------------------------------------------------------------------
def exact_colors(k: pd.DataFrame) -> list[str]:
    vc = k[k["category"].isin(SCOPE)]["color"].value_counts()
    return [c for c, n in vc.items() if n >= 20 and c != "Multi"]


def stage_zeroshot(a):
    from engine02.models import TorchEncoder

    zdir = ensure(Path(a.out) / "zeroshot")
    k = load("kagl_full")
    ex = exact_colors(k)
    for enc_name in ENCODERS:
        enc = TorchEncoder(enc_name, device="cuda", batch_size=64)
        for cat in ("kagl_full", "polyvore_big"):
            items = load(cat)
            E = emb(a, cat, enc_name)
            zs = AF.ZeroShotPredictor(enc, "category", pool="max")
            np.save(zdir / f"{cat}__{enc_name}__category.npy", zs.logits(E))
            nouns = items["category"].map(AF.NOUN).fillna("product").to_numpy()
            for attr in ("gender", "family", "occasion", "season"):
                zs = AF.ZeroShotPredictor(enc, attr)
                np.save(zdir / f"{cat}__{enc_name}__{attr}.npy", zs.logits(E, nouns))
            # exact KAGL colour names as their own labels
            AF.PHRASES["exact"] = {c: [c.lower()] for c in ex}
            zs = AF.ZeroShotPredictor(enc, "exact", labels=tuple(ex))
            np.save(zdir / f"{cat}__{enc_name}__exact.npy", zs.logits(E, nouns))
            print("zeroshot", enc_name, cat, flush=True)
    (zdir / "exact_labels.json").write_text(json.dumps(ex))


# ------------------------------------------------------------------------------------------------
def stage_vlm(a):
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    out = ensure(Path(a.out) / "vlm")
    items = load(a.catalog)
    ids = set(pd.read_csv(a.ids, dtype=str)["item_id"]) if a.ids else set(items["item_id"])
    todo_all = items[items["item_id"].isin(ids)]
    dst = out / f"{a.catalog}.parquet"
    partial = dst.with_suffix(".partial.parquet")
    rows = pd.read_parquet(partial).to_dict("records") if partial.exists() else []
    done = {r["item_id"] for r in rows}
    todo = todo_all[~todo_all["item_id"].isin(done)]
    dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16  # V100 → fp16
    model = AutoModelForImageTextToText.from_pretrained(a.model, dtype=dtype, device_map="cuda").eval()
    proc = AutoProcessor.from_pretrained(a.model)
    proc.tokenizer.padding_side = "left"
    tok = proc.tokenizer
    letters = AF.LETTERS[: max(len(q[2]) for q in AF.VLM_QUESTIONS)]
    variants = {}
    for pre in ("", " "):
        idl = [tok.encode(pre + L, add_special_tokens=False) for L in letters]
        assert all(len(x) == 1 for x in idl), idl
        variants[pre] = [x[0] for x in idl]
    all_ids = variants[""] + variants[" "]
    id_to_pre = {t: pre for pre, v in variants.items() for t in v}
    local = {"": list(range(len(letters))), " ": list(range(len(letters), 2 * len(letters)))}
    prompt = AF.build_mc_prompt()
    cat_dir = ROOT / "data/catalog" / a.catalog
    recs = list(todo.itertuples(index=False))
    print(json.dumps({"todo": len(recs), "resume": len(rows)}), flush=True)
    t0 = time.perf_counter()
    for bi in range(0, len(recs), a.batch_size):
        batch = recs[bi: bi + a.batch_size]
        convs = [[{"role": "user", "content": [{"type": "image", "image": str((cat_dir / r.image_path).resolve())},
                                               {"type": "text", "text": prompt}]}] for r in batch]
        inputs = proc.apply_chat_template(convs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                          return_tensors="pt", padding=True).to(model.device)
        with torch.inference_mode():
            gen = model.generate(**inputs, max_new_tokens=4 * len(AF.VLM_QUESTIONS), do_sample=False,
                                 output_scores=True, return_dict_in_generate=True)
        L0 = inputs["input_ids"].shape[1]
        sc = torch.stack(gen.scores, dim=1)[:, :, all_ids].float().cpu().numpy()  # (b, steps, 2*letters)
        for b, r in enumerate(batch):
            seq = gen.sequences[b, L0:].tolist()
            steps = [(kk, id_to_pre[t]) for kk, t in enumerate(seq) if t in id_to_pre]
            row = {"item_id": str(r.item_id), "raw": tok.decode(seq, skip_special_tokens=True).strip()}
            probs = AF.option_probs([sc[b, kk] for kk, _ in steps], [{"prefix": p} for _, p in steps], local)
            row["valid"] = probs is not None
            for qid, _, opts in AF.VLM_QUESTIONS:
                for j, (lab, _) in enumerate(opts):
                    row[f"{qid}:{lab}"] = float(probs[qid][j]) if probs is not None else np.nan
            rows.append(row)
        nb = bi // a.batch_size + 1
        if nb % 20 == 0:
            el = time.perf_counter() - t0
            print(json.dumps({"done": len(rows), "s_per_item": round(el / (bi + len(batch)), 3), "last": rows[-1]["raw"]}),
                  flush=True)
        if nb % 100 == 0:
            pd.DataFrame(rows).to_parquet(partial, index=False)
    pd.DataFrame(rows).to_parquet(dst, index=False)
    partial.unlink(missing_ok=True)
    meta = {"model": a.model, "n": len(rows), "valid_rate": float(np.mean([r["valid"] for r in rows])),
            "sec_per_item": (time.perf_counter() - t0) / max(1, len(recs)), "prompt": prompt}
    dst.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta)[:400])


def vlm_probs(a, cat: str, qid: str, item_ids) -> np.ndarray:
    df = pd.read_parquet(Path(a.out) / "vlm" / f"{cat}.parquet").set_index("item_id")
    labels = [lab for q, _, opts in AF.VLM_QUESTIONS if q == qid for lab, _ in opts]
    return df.reindex(list(item_ids))[[f"{qid}:{lab}" for lab in labels]].to_numpy(dtype=float)


# ------------------------------------------------------------------------------------------------
TASKS = {  # task → (label list, ground-truth function on a KAGL row frame)
    "gender5": (AF.GENDER, lambda d: d["gender"]),
    "gender2": (("Men", "Women"), lambda d: d["gender"]),
    "family": (AF.FAMILY, lambda d: d["color"].map(AF.color_family)),
    "occasion": (AF.OCCASION, lambda d: d["occasion"]),
    "season": (AF.SEASON, lambda d: d["season"]),
}


def truth(d: pd.DataFrame, task: str, labels) -> np.ndarray:
    y = TASKS[task][1](d) if task in TASKS else d["color"]
    return np.array([list(labels).index(v) if v in labels else -1 for v in y])


def method_logits(a, method: str, cat: str, task: str, pos: np.ndarray, ids) -> np.ndarray | None:
    """log-probability-like scores for (method, task) at catalog positions ``pos``."""
    attr = {"gender5": "gender", "gender2": "gender", "exact": "exact"}.get(task, task)
    if method.startswith("zs_"):
        enc = {"zs_marqo": "marqo-fashionSigLIP", "zs_fclip": "fashion-clip"}[method]
        z = np.load(Path(a.out) / "zeroshot" / f"{cat}__{enc}__{attr}.npy")[pos] * 100.0
        if task == "gender2":
            z = z[:, :2]
        return z
    if method.startswith("lr_"):
        f = Path(a.out) / "linear" / f"{cat}__{method}__{task}.npy"
        if not f.exists():
            return None
        p = np.load(f)[pos]
        return np.log(np.clip(p, 1e-9, None))
    if method == "qwen":
        if task == "exact":
            return None
        p = vlm_probs(a, cat, attr, ids)
        if task == "gender2":
            p = AF.restrict(p, AF.GENDER, ("Men", "Women"))
        elif task == "family":
            p = AF.restrict(p, list(AF.FAMILY) + ["multi"], AF.FAMILY)
        return np.log(np.clip(p, 1e-9, None))
    raise ValueError(method)


def stage_linear(a):
    ldir = ensure(Path(a.out) / "linear")
    k = load("kagl_full")
    sp = pd.read_parquet(Path(a.out) / "kagl_splits.parquet").set_index("item_id")
    k["split"] = k["item_id"].map(sp["split"])
    ex = json.loads((Path(a.out) / "zeroshot" / "exact_labels.json").read_text())
    report = {}
    for enc, m in (("marqo-fashionSigLIP", "lr_marqo"), ("fashion-clip", "lr_fclip")):
        E = emb(a, "kagl_full", enc)
        targets = {"polyvore_big": emb(a, "polyvore_big", enc), "kagl_full": E}
        for task in list(TASKS) + ["exact"]:
            labels = tuple(ex) if task == "exact" else TASKS[task][0]
            y = truth(k, task, labels)
            tr = np.flatnonzero((k["split"] == "train").to_numpy() & (y >= 0))
            dv = np.flatnonzero((k["split"] == "dev").to_numpy() & (y >= 0))
            best = None
            for C in (0.3, 1.0, 3.0, 10.0):
                lp = AF.LinearProbePredictor(labels=labels, C=C).fit(E[tr], [labels[i] for i in y[tr]])
                p = lp.predict_proba(E[dv])
                nll = -np.mean(np.log(np.clip(p[np.arange(len(dv)), y[dv]], 1e-9, None)))
                if best is None or nll < best[0]:
                    best = (nll, C, lp)
            report[f"{m}:{task}"] = {"C": best[1], "dev_nll": best[0], "n_train": len(tr)}
            for cat, X in targets.items():
                np.save(ldir / f"{cat}__{m}__{task}.npy", best[2].predict_proba(X).astype(np.float32))
            print(m, task, report[f"{m}:{task}"], flush=True)
    (ldir / "linear_report.json").write_text(json.dumps(report, indent=1))


# ------------------------------------------------------------------------------------------------
def boot_ci(x, n=2000):
    return bootstrap_ci(np.asarray(x, dtype=float), n_boot=n)


def stage_eval(a):
    out = Path(a.out)
    k = load("kagl_full")
    sp = pd.read_parquet(out / "kagl_splits.parquet").set_index("item_id")
    k["split"] = k["item_id"].map(sp["split"])
    ex = json.loads((out / "zeroshot" / "exact_labels.json").read_text())
    vlm_ids = set(pd.read_parquet(out / "vlm" / "kagl_full.parquet")["item_id"]) if (out / "vlm" / "kagl_full.parquet").exists() else set()
    rows, per_item, curves = [], {}, []
    for task in list(TASKS) + ["exact"]:
        labels = tuple(ex) if task == "exact" else TASKS[task][0]
        y = truth(k, task, labels)
        te = np.flatnonzero((k["split"] == "test").to_numpy() & (y >= 0))
        dv = np.flatnonzero((k["split"] == "dev").to_numpy() & (y >= 0))
        for method in ("zs_marqo", "zs_fclip", "lr_marqo", "lr_fclip", "qwen"):
            if method == "qwen" and not vlm_ids:
                continue
            zt = method_logits(a, method, "kagl_full", task, te, k["item_id"].iloc[te])
            if zt is None:
                continue
            zd = method_logits(a, method, "kagl_full", task, dv, k["item_id"].iloc[dv])
            okt, okd = ~np.isnan(zt).any(1), ~np.isnan(zd).any(1)
            T = AF.fit_temperature(zd[okd], y[dv][okd])
            pt_raw, pt, pd_ = AF.softmax(zt, 1.0), AF.softmax(zt, T), AF.softmax(zd, T)  # raw: CLIP scale 100 / model probs
            yt = y[te]
            pred = np.where(okt, pt.argmax(1), -1)
            corr = (pred == yt).astype(float)
            per_item[(task, method)] = pd.Series(corr, index=k["item_id"].iloc[te].to_numpy())
            lo, hi = boot_ci(corr)
            row = dict(task=task, method=method, n_test=len(te), valid=float(okt.mean()), acc=corr.mean(),
                       acc_lo=lo, acc_hi=hi, macro_f1=AF.macro_f1(yt, pred, len(labels)),
                       ece_raw=AF.ece(pt_raw[okt], yt[okt]), ece_cal=AF.ece(pt[okt], yt[okt]), T=T,
                       majority=float(np.mean(yt == np.bincount(y[np.flatnonzero((k['split'] == 'train').to_numpy() & (y >= 0))]).argmax())))
            for target in (0.8, 0.9, 0.95):
                thr = AF.threshold_for_precision(pd_[okd], y[dv][okd], target)
                if thr is None:
                    row[f"thr{target}"], row[f"cov{target}"], row[f"selacc{target}"] = None, 0.0, np.nan
                    continue
                cov, sacc = AF.coverage_at(pt[okt], yt[okt], thr)
                row[f"thr{target}"], row[f"cov{target}"], row[f"selacc{target}"] = thr, cov, sacc
            conf = pt[okt].max(1)
            for q in np.linspace(0, 1, 21):
                keep = conf >= np.quantile(conf, q) if q > 0 else np.ones_like(conf, bool)
                curves.append(dict(task=task, method=method, coverage=float(keep.mean()),
                                   sel_acc=float((pt[okt].argmax(1)[keep] == yt[okt][keep]).mean())))
            rows.append(row)
            print(json.dumps({kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in row.items()}), flush=True)
    res = pd.DataFrame(rows)
    # paired permutation tests on per-item correctness vs lr_marqo (same test items)
    pvals = []
    for (task, method), s in per_item.items():
        base = per_item.get((task, "lr_marqo"))
        if base is None or method == "lr_marqo":
            continue
        common = s.index.intersection(base.index)
        pvals.append(dict(task=task, method=method, vs="lr_marqo", diff=float(s[common].mean() - base[common].mean()),
                          p=paired_permutation_test(s[common].to_numpy(), base[common].to_numpy())))
    res.to_csv(out / "attr_metrics.csv", index=False)
    pd.DataFrame(pvals).to_csv(out / "attr_paired_tests.csv", index=False)
    pd.DataFrame(curves).to_csv(out / "attr_risk_coverage.csv", index=False)
    print(pd.DataFrame(pvals).to_string())


# ------------------------------------------------------------------------------------------------
def stage_audit(a):
    out = Path(a.out)
    ensure(out / "audit")
    rng = np.random.default_rng(SEED)
    summary, sample_rows = {}, []
    for cat in ("kagl_full", "polyvore_big"):
        items = load(cat)
        meta = items["category"].fillna("other").to_numpy()
        for enc, m in (("marqo-fashionSigLIP", "zs_marqo"), ("fashion-clip", "zs_fclip")):
            z = np.load(out / "zeroshot" / f"{cat}__{enc}__category.npy")
            pred = np.array(AF.COARSE)[z.argmax(1)]
            agree = (pred == meta).astype(float)
            lo, hi = boot_ci(agree)
            summary[f"{cat}:{m}"] = dict(n=len(agree), agreement=agree.mean(), lo=lo, hi=hi)
            pd.crosstab(pd.Series(meta, name="metadata"), pd.Series(pred, name=m)).to_csv(out / "audit" / f"confusion_{cat}_{m}.csv")
            items[f"pred_{m}"] = pred
        vf = out / "vlm" / f"{cat}.parquet"
        if not vf.exists():
            continue
        v = pd.read_parquet(vf).set_index("item_id")
        sub = items[items["item_id"].isin(v.index)].copy()
        P = v.reindex(sub["item_id"])[[f"category:{c}" for c in AF.COARSE]].to_numpy(float)
        ok = ~np.isnan(P).any(1)
        sub = sub[ok]
        P = P[ok]
        sub["pred_qwen"] = np.array(AF.COARSE)[P.argmax(1)]
        sub["conf_qwen"] = P.max(1)
        if cat == "kagl_full":  # stratified sample → population weights
            strat = pd.read_csv(out / "category_sample_kagl_full.csv", dtype=str)
            sub = sub[sub["item_id"].isin(set(strat["item_id"]))]
            pop = items["category"].value_counts()
            w = sub["category"].map(pop / sub["category"].value_counts())
        else:
            w = pd.Series(1.0, index=sub.index)
        agree = (sub["pred_qwen"] == sub["category"]).to_numpy(float)
        ww = w.to_numpy(float)
        boots = []
        for _ in range(2000):
            idx = np.concatenate([rng.choice(np.flatnonzero(sub["category"].to_numpy() == c), size=int((sub["category"] == c).sum()))
                                  for c in sub["category"].unique()])
            boots.append(np.average(agree[idx], weights=ww[idx]))
        summary[f"{cat}:qwen"] = dict(n=len(sub), agreement=float(np.average(agree, weights=ww)),
                                      lo=float(np.quantile(boots, 0.025)), hi=float(np.quantile(boots, 0.975)),
                                      weighted=cat == "kagl_full")
        both = sub["pred_qwen"] == sub["pred_zs_marqo"]
        summary[f"{cat}:qwen_and_marqo_agree_with_each_other_but_not_metadata"] = float(
            np.average(((sub["pred_qwen"] != sub["category"]) & both).to_numpy(float), weights=ww))
        pd.crosstab(sub["category"].rename("metadata"), sub["pred_qwen"].rename("qwen")).to_csv(out / "audit" / f"confusion_{cat}_qwen.csv")
        per_cat = sub.assign(agree=agree).groupby("category")["agree"].mean().to_dict()
        summary[f"{cat}:qwen_per_category_agreement"] = per_cat
        dis = sub[sub["pred_qwen"] != sub["category"]]
        # stratified by metadata category: round-robin over categories, random within
        groups = {c: g.sample(frac=1, random_state=SEED) for c, g in dis.groupby("category")}
        picked, i = [], 0
        while len(picked) < a.n_disagree and any(len(g) > i for g in groups.values()):
            for c in sorted(groups):
                if len(groups[c]) > i and len(picked) < a.n_disagree:
                    picked.append(groups[c].iloc[i])
            i += 1
        for r in picked:
            sample_rows.append(dict(catalog=cat, item_id=r["item_id"], title=r["title"], subcategory=r["subcategory"],
                                    metadata=r["category"], qwen=r["pred_qwen"], qwen_conf=round(r["conf_qwen"], 3),
                                    marqo=r["pred_zs_marqo"], image_path=f"{cat}/{r['image_path']}"))
    s = pd.DataFrame(sample_rows)
    s.insert(0, "n", range(1, len(s) + 1))
    s.to_csv(out / "audit" / "disagreement_sample.csv", index=False)
    (out / "audit" / "category_agreement.json").write_text(json.dumps(summary, indent=1, default=float))
    make_sheets(s, out / "audit" / "sheets", "dis")
    print(json.dumps(summary, indent=1, default=float))


def make_sheets(df: pd.DataFrame, dst: Path, prefix: str, per: int = 12, tile: int = 256, cols: int = 4):
    from PIL import Image, ImageDraw

    ensure(dst)
    for si in range(0, len(df), per):
        chunk = df.iloc[si: si + per]
        rows_n = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tile, rows_n * (tile + 22)), "white")
        d = ImageDraw.Draw(sheet)
        for j, r in enumerate(chunk.itertuples(index=False)):
            im = Image.open(ROOT / "data/catalog" / r.image_path).convert("RGB")
            im.thumbnail((tile - 8, tile - 8))
            x, y = (j % cols) * tile, (j // cols) * (tile + 22)
            sheet.paste(im, (x + 4, y + 22))
            d.rectangle([x, y, x + tile - 1, y + tile + 21], outline=(180, 180, 180))
            d.text((x + 6, y + 4), f"#{r.n}", fill=(220, 0, 0))
        sheet.save(dst / f"{prefix}_{si // per + 1:02d}.jpg", quality=88)


def stage_sheet(a):
    df = pd.read_csv(a.ids, dtype=str)
    if "n" not in df:
        df.insert(0, "n", range(1, len(df) + 1))
    make_sheets(df, Path(a.out) / a.sheet_dir, a.prefix)


# ------------------------------------------------------------------------------------------------
def stage_transfer_sample(a):
    """~102 Polyvore items of the merged catalog (17 per category) for the agent's visual labels."""
    out = ensure(Path(a.out) / "transfer")
    m = load("kagl_polyvore")
    p = m[m["source"] == "Marqo/polyvore"]
    shuf = p.sample(frac=1, random_state=SEED + 1)
    s = shuf[shuf.groupby("category").cumcount() < 17].sort_values("category")
    s = s[["item_id", "category", "subcategory", "title", "image_path"]].reset_index(drop=True)
    s["image_path"] = "kagl_polyvore/" + s["image_path"]
    s.insert(0, "n", range(1, len(s) + 1))
    s.to_csv(out / "polyvore_sample.csv", index=False)
    make_sheets(s, out / "sheets", "pv")


def merged_to_source(merged_ids) -> tuple[list[str], list[str]]:
    cats, ids = [], []
    for i in merged_ids:
        c, raw = i.split(":", 1)
        cats.append(c)
        ids.append(raw)
    return cats, ids


def predict_polyvore(a, method: str, task: str, raw_ids) -> np.ndarray | None:
    pv = load("polyvore_big")
    pos_map = {i: p for p, i in enumerate(pv["item_id"])}
    pos = np.array([pos_map[i] for i in raw_ids])
    z = method_logits(a, method, "polyvore_big", task, pos, raw_ids)
    if z is None:
        return None
    return z


def stage_transfer(a):
    out = Path(a.out)
    lab = pd.read_csv(out / "transfer" / "polyvore_labels_agent.csv", dtype=str)
    samp = pd.read_csv(out / "transfer" / "polyvore_sample.csv", dtype=str)
    lab = samp.merge(lab, on="n", suffixes=("", "_lab"))
    met = pd.read_csv(out / "attr_metrics.csv")
    _, raw = merged_to_source(lab["item_id"])
    rows = []
    for task, col in (("gender2", "gender"), ("family", "family"), ("occasion", "occasion")):
        labels = TASKS[task][0]
        y = np.array([labels.index(v) if v in labels else -1 for v in lab[col]])
        keep = y >= 0
        for method in ("zs_marqo", "zs_fclip", "lr_marqo", "lr_fclip", "qwen"):
            z = predict_polyvore(a, method, task, list(np.array(raw)))
            if z is None:
                continue
            mm = met[(met.task == task) & (met.method == method)]
            T = float(mm["T"].iloc[0]) if len(mm) else 1.0
            p = AF.softmax(z, T)
            ok = keep & ~np.isnan(z).any(1)
            corr = (p.argmax(1)[ok] == y[ok]).astype(float)
            lo, hi = boot_ci(corr)
            r = dict(task=task, method=method, n=int(ok.sum()), acc=corr.mean(), lo=lo, hi=hi,
                     macro_f1=AF.macro_f1(y[ok], p.argmax(1)[ok], len(labels)), ece=AF.ece(p[ok], y[ok]))
            thr = mm["thr0.9"].iloc[0] if len(mm) and pd.notna(mm["thr0.9"].iloc[0]) else None
            if thr is not None:
                r["cov@thr0.9"], r["selacc@thr0.9"] = AF.coverage_at(p[ok], y[ok], float(thr))
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(out / "transfer" / "transfer_metrics.csv", index=False)
    print(res.to_string())


# ------------------------------------------------------------------------------------------------
FILL_PLAN = {  # attr → (task, method, dev-precision target)
    "color": ("family", "qwen", 0.9),
    "gender": ("gender_fill", "qwen", 0.9),
    "occasion": ("occasion", "qwen", 0.9),
    "season": ("season", "qwen", 0.9),
}


def stage_fill(a):
    out = Path(a.out)
    plan = json.loads(a.plan) if a.plan else FILL_PLAN
    met = pd.read_csv(out / "attr_metrics.csv")
    m = load("kagl_polyvore")
    pv_mask = (m["source"] == "Marqo/polyvore").to_numpy()
    _, raw = merged_to_source(m.loc[pv_mask, "item_id"])
    preds, used = {}, {}
    for attr, (task, method, target) in plan.items():
        if method == "none":
            continue
        eval_task = "gender5" if task == "gender_fill" else task
        mm = met[(met.task == eval_task) & (met.method == method)].iloc[0]
        T, thr = float(mm["T"]), mm[f"thr{target}"]
        if pd.isna(thr):
            used[attr] = dict(method=method, skipped="no threshold reaches target on dev")
            continue
        z = predict_polyvore(a, method, "gender5" if task == "gender_fill" else task, raw)
        p = AF.softmax(z, T)
        labels = list(TASKS[eval_task][0])
        if task == "gender_fill":  # write only Men / Women / Unisex
            p = AF.restrict(p, AF.GENDER, AF.GENDER_FILL)
            labels = list(AF.GENDER_FILL)
        vals, conf = AF.decide(np.nan_to_num(p, nan=0.0), labels, float(thr))
        if attr == "color":
            vals = [AF.FAMILY_CANONICAL[v] if v else None for v in vals]
        model_name = {"qwen": "Qwen3-VL-8B-Instruct", "lr_marqo": "logreg-marqo-fashionSigLIP",
                      "zs_marqo": "zeroshot-marqo-fashionSigLIP"}.get(method, method)
        preds[attr] = pd.DataFrame(dict(item_id=m.loc[pv_mask, "item_id"].to_numpy(), value=vals, confidence=conf,
                                        model=model_name))
        used[attr] = dict(method=method, T=T, threshold=float(thr), dev_target=target,
                          filled_share=float(np.mean([v is not None for v in vals])))
    filled = AF.fill_attributes(m, preds, {k: v["threshold"] for k, v in used.items() if "threshold" in v})
    dst = ensure(Path(a.filled))
    filled.to_parquet(dst / "items.parquet", index=False)
    for f in ("images", "category_cooccurrence.json"):
        link = dst / f
        if not link.exists():
            link.symlink_to(SHARED / "kagl_polyvore" / f)
    (dst / "fill_meta.json").write_text(json.dumps(used, indent=1))
    rep = {}
    for attr in AF.FILL_ATTRS:
        for src_name, frame in (("before", m), ("after", filled)):
            pvf = frame[pv_mask]
            rep[f"{attr}:{src_name}:polyvore_nonnull"] = float(pvf[attr].notna().mean())
            for c in ("outerwear", "dress"):
                rep[f"{attr}:{src_name}:polyvore_{c}_nonnull"] = float(pvf.loc[pvf["category"] == c, attr].notna().mean())
    (out / "fill_report.json").write_text(json.dumps({"plan": used, "coverage": rep}, indent=1))
    print(json.dumps({"plan": used, "coverage": rep}, indent=1))


# ------------------------------------------------------------------------------------------------
def stage_t2(a):
    from engine02 import pipeline
    from engine02.catalog import Catalog
    from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, Slot, SlotState
    from engine02.models import TorchEncoder

    out = ensure(Path(a.out) / "t2")
    enc = TorchEncoder("marqo-fashionSigLIP", device="cuda")
    cats = {"before": Catalog.load(SHARED / "kagl_polyvore"), "after": Catalog.load(Path(a.filled))}
    cache = ensure(Path(a.out).parent / "index_kagl_polyvore")
    for f in (SHARED / "kagl_polyvore" / "index").glob("*.npy"):
        if not (cache / f.name).exists():
            shutil.copy(f, cache / f.name)
    engines = {k: pipeline.Engine02(c, enc, cache_dir=cache) for k, c in cats.items()}
    pipeline.filter_with_relaxation = AF.provenance_filter("family")
    queries = []
    for c, genders, fams in (("outerwear", ("Men", "Women"), ("black", "blue", "grey", "brown", "green", "red", "beige", "white")),
                             ("dress", ("Women",), ("black", "blue", "red", "pink", "white", "green", "yellow", "purple", "beige", "grey"))):
        for g in genders:
            for f in fams:
                queries.append((c, g, f))
    rows, shown = [], []
    for arm, eng in engines.items():
        items = eng.catalog.items
        for qi, (c, g, f) in enumerate(queries):
            hc = HardConstraints(category=Slot(state=SlotState.VALUE, values=[c]),
                                 color=Slot(state=SlotState.VALUE, values=[AF.FAMILY_CANONICAL[f]]),
                                 gender=Slot(state=SlotState.VALUE, values=[g]))
            noun = {"outerwear": "jacket", "dress": "dress"}[c]
            req = Engine02Request(session_id=f"q{qi}", retrieval_text=f"{g} {f} {noun}", constraints=hc,
                                  options=Engine02Options(top_k=5, explain_with_llm=False, counterfactual_check=False))
            resp = eng.run(req, "full")
            n_pv = 0
            for it in resp.items:
                p = eng.catalog.pos(it.item_id)
                r = items.iloc[p]
                is_pv = r["source"] == "Marqo/polyvore"
                n_pv += is_pv
                shown.append(dict(arm=arm, qid=qi, category=c, gender=g, family=f, rank=it.rank, item_id=it.item_id,
                                  source="polyvore" if is_pv else "kagl", meta_color=r["color"], meta_gender=r["gender"],
                                  item_category=r["category"], attr_source=r["attr_source"],
                                  image_path="kagl_polyvore/" + r["image_path"]))
            rows.append(dict(arm=arm, qid=qi, category=c, gender=g, family=f, n_after_filter=resp.constraint_report.n_after_filter,
                             relaxed=";".join(resp.constraint_report.relaxed), n_shown=len(resp.items), n_polyvore=n_pv))
    q = pd.DataFrame(rows)
    s = pd.DataFrame(shown)
    q.to_csv(out / "queries.csv", index=False)
    s.to_csv(out / "shown.csv", index=False)
    pv = s[s["source"] == "polyvore"].drop_duplicates("item_id")[["item_id", "image_path"]].reset_index(drop=True)
    pv.insert(0, "n", range(1, len(pv) + 1))
    pv.to_csv(out / "shown_polyvore_to_label.csv", index=False)
    make_sheets(pv, out / "sheets", "t2")
    print(q.groupby("arm")[["n_after_filter", "n_polyvore"]].mean(), (q["relaxed"] != "").groupby(q["arm"]).mean())


def stage_t2_score(a):
    out = Path(a.out) / "t2"
    q = pd.read_csv(out / "queries.csv")
    s = pd.read_csv(out / "shown.csv", dtype={"item_id": str})
    lab_ids = pd.read_csv(out / "shown_polyvore_to_label.csv", dtype=str)
    lab = pd.read_csv(out / "shown_polyvore_labels_agent.csv", dtype=str).merge(lab_ids, on="n")
    lab = lab.set_index("item_id")
    sat = []
    for r in s.itertuples(index=False):
        if r.source == "kagl":
            fam, gen = AF.color_family(r.meta_color), r.meta_gender
        elif r.item_id in lab.index:
            fam, gen = lab.at[r.item_id, "family"], lab.at[r.item_id, "gender"]
        else:
            sat.append(dict(color_ok=np.nan, gender_ok=np.nan, cat_ok=np.nan))
            continue
        cat_ok = r.item_category == r.category if r.source == "kagl" else (lab.at[r.item_id, "category_ok"] == "1")
        gen_ok = gen == r.gender or (r.source != "kagl" and gen == "Unisex")
        sat.append(dict(color_ok=float(fam == r.family), gender_ok=float(gen_ok), cat_ok=float(cat_ok)))
    s = pd.concat([s.reset_index(drop=True), pd.DataFrame(sat)], axis=1)
    s["all_ok"] = s[["color_ok", "gender_ok", "cat_ok"]].min(axis=1, skipna=False)
    s.to_csv(out / "shown_scored.csv", index=False)
    per_q = s.groupby(["arm", "qid"]).agg(sat=("all_ok", "mean"), color=("color_ok", "mean"),
                                          n_labeled=("all_ok", lambda x: x.notna().sum())).reset_index()
    rows = []
    for arm in ("before", "after"):
        d = per_q[per_q.arm == arm]
        lo, hi = boot_ci(d["sat"].dropna())
        qa = q[q.arm == arm]
        rows.append(dict(arm=arm, satisfaction=d["sat"].mean(), lo=lo, hi=hi, color_sat=d["color"].mean(),
                         relaxation_rate=float((qa["relaxed"].fillna("") != "").mean()),
                         color_dropped=float(qa["relaxed"].fillna("").str.contains("color:drop").mean()),
                         mean_pool=qa["n_after_filter"].mean(), polyvore_share_shown=qa["n_polyvore"].sum() / qa["n_shown"].sum()))
    b = per_q[per_q.arm == "before"].set_index("qid")["sat"]
    af = per_q[per_q.arm == "after"].set_index("qid")["sat"]
    common = b.dropna().index.intersection(af.dropna().index)
    res = pd.DataFrame(rows)
    res["p_after_vs_before"] = paired_permutation_test(af[common].to_numpy(), b[common].to_numpy())
    by_src = s.groupby(["arm", "source"])["all_ok"].agg(["mean", "count"]).reset_index()
    res.to_csv(out / "t2_summary.csv", index=False)
    by_src.to_csv(out / "t2_by_source.csv", index=False)
    print(res.to_string(), "\n", by_src.to_string())


# ------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage")
    ap.add_argument("--out", default="/tmp/neil/agents/classify/out")
    ap.add_argument("--n-test", type=int, default=2600)
    ap.add_argument("--n-dev", type=int, default=1100)
    ap.add_argument("--cap-per-category", type=int, default=700)
    ap.add_argument("--catalog", default="kagl_full")
    ap.add_argument("--ids", default=None)
    ap.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--n-disagree", type=int, default=30)
    ap.add_argument("--sheet-dir", default="sheets")
    ap.add_argument("--prefix", default="s")
    ap.add_argument("--plan", default=None, help='JSON {"color": ["family", "qwen", 0.9], ...}')
    ap.add_argument("--filled", default="/tmp/neil/agents/classify/catalog_kagl_polyvore_filled")
    a = ap.parse_args()
    fn = {"prep": stage_prep, "embed": stage_embed, "zeroshot": stage_zeroshot, "vlm": stage_vlm,
          "linear": stage_linear, "eval": stage_eval, "audit": stage_audit, "sheet": stage_sheet,
          "transfer_sample": stage_transfer_sample, "transfer": stage_transfer, "fill": stage_fill,
          "t2": stage_t2, "t2_score": stage_t2_score}[a.stage]
    fn(a)


if __name__ == "__main__":
    main()
