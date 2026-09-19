"""ENGINE 02 on *external* public benchmarks, scored with the metric each benchmark publishes.

Everything here is additive: no shipped module is modified. Helper metrics live in
`engine02/external.py` (which documents the exact protocol each number reproduces).

Sub-commands
------------
    build-catalog   stream a Marqo benchmark HF dataset into the unified catalog schema
    marqo-t2i      Marqo fashion benchmark, task "text-to-image": Recall@1 / Recall@10 / MRR@10
                   for several encoders (pure dense = exactly the published protocol) and for
                   ENGINE 02 arms (dense / hybrid_rrf / full_zclip3)
    marqo-attr     Marqo benchmark attribute tasks ("<attr>-to-product"): P@1 / P@10 / MRR
    polyvore-compat  canonical Polyvore FITB (4 candidates) accuracy + outfit-compatibility AUC
    esci           Amazon ESCI / KDD Cup 2022 Task 1 apparel slice: nDCG@10 with E/S/C/I gains

Typical run on cfda4 (inside tmux, from the synced repo root):

    P=/tmp2/mzjiang/Research_Project/.venv/bin/python
    export HF_HOME=/tmp2/mzjiang/Research_Project/.runtime/cache/hf TOKENIZERS_PARALLELISM=false
    $P scripts/eval_external.py build-catalog --source Marqo/deepfashion-inshop \
        --out /tmp2/mzjiang/Research_Project/agents/bench/catalog/dfinshop
    $P scripts/eval_external.py marqo-t2i --dataset KAGL --catalog data/catalog/kagl_full \
        --encoders marqo-fashionSigLIP,fashion-clip,laion-CLIP-ViT-B-16 --arms dense,hybrid_rrf,full_zclip3
    $P scripts/eval_external.py polyvore-compat --catalog data/catalog/polyvore_big --n-fitb 2000 --n-compat 2000
    $P scripts/eval_external.py esci --esci-dir .../esci --model BAAI/bge-small-en-v1.5
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine02 import external as ext  # noqa: E402
from engine02.catalog import Catalog  # noqa: E402
from engine02.eval.metrics import bootstrap_ci, paired_permutation_test  # noqa: E402

# Marqo benchmark dataset name → (HF dataset, folder name in marqo-FashionCLIP/data)
MARQO_DATASETS = {
    "KAGL": "Marqo/KAGL",
    "Polyvore": "Marqo/polyvore",
    "DeepFashion-InShop": "Marqo/deepfashion-inshop",
    "DeepFashion-Multimodal": "Marqo/deepfashion-multimodal",
    "Fashion200k": "Marqo/fashion200k",
    "Atlas": "Marqo/atlas",
}
# text→image corpora that are NOT part of the Marqo suite, so they have **no published ground truth
# and no published baseline numbers**. `build-gt` creates a Marqo-format ground-truth file for them,
# which makes the harness reusable but the results only internally comparable (see the report).
EXTRA_SOURCES = {
    # H&M product photos + captions (third-party repackaging of the Kaggle competition images;
    # columns are literally `text` + `image`, so no schema mapping is needed). Licence: unstated.
    "HM-Caption": "tomytjandra/h-and-m-fashion-caption",
}
ALL_SOURCES = {**MARQO_DATASETS, **EXTRA_SOURCES}


def jdump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[written] {path}")


def summarise(per_query: dict[str, list[float]], seed: int = 0) -> dict[str, dict]:
    out = {}
    for name, vals in per_query.items():
        a = np.asarray(vals, dtype=np.float64)
        lo, hi = bootstrap_ci(a, seed=seed)
        out[name] = {"mean": round(float(a.mean()), 5), "ci95": [round(lo, 5), round(hi, 5)], "n": int(len(a))}
    return out


# =====================================================================================
# build-catalog
# =====================================================================================
def cmd_build_catalog(args) -> None:
    """Stream a Marqo benchmark dataset into `items.parquet` + `images/` (unified schema).

    Deliberately mirrors scripts/prepare_catalog.py (same image handling, same columns) but covers
    the DeepFashion / Fashion200k / Atlas schemas that the shipped script does not know about.
    `item_id` is kept **verbatim** from the dataset's `item_ID` column, because that is the key the
    Marqo ground-truth files use.
    """
    from datasets import Image as HFImage, load_dataset

    sys.path.insert(0, str(ROOT / "scripts"))
    from prepare_catalog import ATTRS, save_image  # read-only reuse

    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    text_col = args.text_col
    keep = ["image", "item_ID", text_col] + [c for c in args.extra_cols.split(",") if c]
    ds = load_dataset(args.source, split=args.split, streaming=True)
    cols = [c for c in keep if c in ds.column_names]
    ds = ds.select_columns(cols).cast_column("image", HFImage(decode=False))
    has_id = "item_ID" in cols

    t0, records, failed, seen = time.time(), [], 0, set()
    for row in ds:
        if args.limit and len(records) >= args.limit:
            break
        raw = row.pop("image")
        # corpora without an id column (e.g. HM-Caption) get a stable positional id
        iid = str(row["item_ID"]) if has_id else f"{args.id_prefix}{len(records) + failed:07d}"
        if iid in seen:
            continue
        rel = f"images/{re.sub(r'[^A-Za-z0-9._-]', '_', iid)}.jpg"
        try:
            save_image(raw, out / rel)
        except Exception as e:
            failed += 1
            print(f"  skip {iid}: {e}", file=sys.stderr)
            continue
        seen.add(iid)
        rec = dict(
            item_id=iid, title=str(row.get(text_col) or ""), description=None,
            category=None, subcategory=None, color=None, season=None, occasion=None, gender=None,
            price=None, currency=None, outfit_ids=None, image_path=rel, source=args.source,
        )
        for c in cols:
            if c in ("image", "item_ID", text_col) or c not in row:
                continue
            v = row.get(c)
            rec[f"src_{c}"] = None if v is None else str(v)
        rec["attr_source"] = json.dumps({a: "null" for a in ATTRS})
        records.append(rec)
        if len(records) % 2000 == 0:
            print(f"  {len(records)} items  {time.time() - t0:.0f}s", flush=True)

    df = pd.DataFrame.from_records(records)
    df["price"] = df["price"].astype("float64")
    df.to_parquet(out / "items.parquet", index=False)
    stats = {"source": args.source, "n_items": len(df), "failed_images": failed,
             "seconds": round(time.time() - t0, 1), "text_col": text_col,
             "extra_cols": [c for c in cols if c.startswith("src_") or c not in ("image", "item_ID", text_col)]}
    jdump(stats, out / "stats.json")


def cmd_build_gt(args) -> None:
    """Write a Marqo-format `ground_truth_text-image.json` for a corpus the benchmark does not cover.

    Construction (mirrors what the Marqo files look like): sample `n` distinct non-empty `title`
    strings uniformly without replacement, and mark **every** item whose title is exactly that
    string as relevant with gain 1 — the same "identical caption ⇒ also relevant" convention that
    gives the official KAGL file up to 20 relevant items per query.

    The resulting numbers are *not* comparable to any published figure, because the query sample is
    ours. They are only comparable across systems evaluated on this same file (fixed `--seed`).
    """
    import random

    cat = Catalog.load(args.catalog)
    titles = cat.items["title"].astype(str).str.strip()
    ids = cat.items["item_id"].astype(str)
    by_text: dict[str, list[str]] = {}
    for t, i in zip(titles, ids):
        if t:
            by_text.setdefault(t, []).append(i)
    keys = sorted(by_text)
    random.Random(args.seed).shuffle(keys)
    gt = {k: {i: 1 for i in by_text[k]} for k in keys[: args.n]}
    out = Path(args.bench_dir) / "data" / args.dataset / "gt_query_doc" / "ground_truth_text-image.json"
    jdump(gt, out)
    n_rel = [len(v) for v in gt.values()]
    print(json.dumps({"dataset": args.dataset, "corpus": len(cat), "distinct_titles": len(keys),
                      "n_queries": len(gt), "seed": args.seed,
                      "rel_per_query": {"min": min(n_rel), "mean": round(sum(n_rel) / len(n_rel), 3),
                                        "max": max(n_rel)}}, indent=2))


# =====================================================================================
# shared: encoders and image embeddings
# =====================================================================================
def _marqo_compat_encoder_class():
    """`TorchEncoder` with the exact text tokenisation the Marqo benchmark uses.

    `engine02/models.py:_txt` calls the HF processor with ``padding=True, truncation=True`` and no
    ``max_length``. `patrickjohncyh/fashion-clip`'s processor does not carry CLIP's 77-token
    position limit, so any caption longer than that raises
    ``ValueError: Sequence length must be less than max_position_embeddings`` — which is exactly
    what DeepFashion-InShop's product descriptions (up to 179 tokens) do.

    marqo-FashionCLIP/models/hf_models.py tokenises with
    ``padding="max_length", max_length=77`` (64 for SigLIP), ``truncation=True``. Overriding
    ``_txt`` here reproduces that *and* keeps the shipped module untouched — the same two keyword
    arguments belong in `engine02/models.py` (see the report's integration-hook list).
    """
    from engine02.models import TorchEncoder, _pooled

    class MarqoCompatEncoder(TorchEncoder):
        def _txt(self, texts: list[str]):
            if self.backend == "hf_clip":
                n = 64 if "siglip" in self.repo.lower() else 77
                inp = self.proc(text=texts, padding="max_length", max_length=n, truncation=True,
                                return_tensors="pt").to(self.device)
                return _pooled(self.model.get_text_features(input_ids=inp["input_ids"],
                                                            attention_mask=inp["attention_mask"]))
            return super()._txt(texts)

    return MarqoCompatEncoder


def get_encoder(name: str, device: str):
    if name == "hash":
        from engine02.encoders import HashEncoder

        return HashEncoder(dim=64)
    return _marqo_compat_encoder_class()(name, device=device, batch_size=256)


def image_embeddings(cat: Catalog, enc, cache_dir: Path) -> np.ndarray:
    from engine02.encoders import cached_image_embeddings

    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = enc.name.replace("/", "__")
    f = cache_dir / f"img_{safe}.npy"
    shared = cat.root / "index" / f"img_{safe}.npy"
    if not f.exists() and shared.exists():
        emb = np.load(shared)
        if emb.shape[0] == len(cat):  # reuse the shared cache read-only (never write to it)
            np.save(f, emb)
            print(f"  reused shared embedding cache {shared}")
    t = time.time()
    emb = cached_image_embeddings(enc, cat.image_paths(), f, batch=256)
    print(f"  embeddings {enc.name}: {emb.shape} ({time.time() - t:.0f}s)")
    return emb


def encode_queries(enc, queries: list[str], batch: int = 256) -> np.ndarray:
    out = [enc.encode_text(queries[i : i + batch]) for i in range(0, len(queries), batch)]
    return np.concatenate(out).astype(np.float64)


# =====================================================================================
# marqo-t2i
# =====================================================================================
def _gt_path(bench_dir: Path, dataset: str, query_col: str, doc_col: str) -> Path:
    return bench_dir / "data" / dataset / "gt_query_doc" / f"ground_truth_{query_col}-{doc_col}.json"


def _dense_run(qemb: np.ndarray, iemb: np.ndarray, ids: list[str], k: int, chunk: int = 128) -> list[list[str]]:
    ranked = []
    for i in range(0, len(qemb), chunk):
        sim = qemb[i : i + chunk] @ iemb.T
        for row in sim:
            ranked.append(ext.rank_ids(row, ids, k))
    return ranked


def _arm_run(engine, queries: list[str], arm: str, k: int, n_candidates: int) -> tuple[list[list[str]], float]:
    from engine02.contracts import Engine02Options, Engine02Request

    ranked, t0 = [], time.time()
    for i, q in enumerate(queries):
        req = Engine02Request(
            session_id=f"bench-{i}", retrieval_text=q,
            options=Engine02Options(top_k=k, n_candidates=n_candidates, arm=arm,
                                    explain_with_llm=False, counterfactual_check=False),
        )
        resp = engine.run(req, arm)
        ranked.append([it.item_id for it in resp.items])
        if (i + 1) % 250 == 0:
            print(f"    {arm} {i + 1}/{len(queries)}  {time.time() - t0:.0f}s", flush=True)
    return ranked, (time.time() - t0) / max(1, len(queries)) * 1000


def cmd_marqo_t2i(args) -> None:
    bench = Path(args.bench_dir)
    gt = ext.load_marqo_ground_truth(_gt_path(bench, args.dataset, "text", "image"))
    cat = Catalog.load(ROOT / args.catalog if not Path(args.catalog).is_absolute() else args.catalog)
    ids = cat.items["item_id"].astype(str).tolist()
    id_set = set(ids)

    # coverage: how much of the official ground truth our corpus actually contains
    cov = {q: [d for d in rel if d in id_set] for q, rel in gt.items()}
    n_full = sum(1 for q in gt if len(cov[q]) == len(gt[q]))
    queries = [q for q in gt if cov[q]] if args.require_gold else list(gt)
    if args.limit_queries:
        queries = queries[: args.limit_queries]
    coverage = {
        "n_gt_queries": len(gt), "n_queries_evaluated": len(queries),
        "n_queries_with_all_gold_in_corpus": n_full,
        "gold_items_in_corpus": round(sum(len(cov[q]) for q in gt) / max(1, sum(len(gt[q]) for q in gt)), 4),
        "corpus_size": len(cat), "require_gold": bool(args.require_gold),
    }
    print(json.dumps(coverage, indent=2))

    results: dict[str, dict] = {"dataset": args.dataset, "catalog": str(args.catalog), "coverage": coverage,
                                "protocol": "marqo-FashionCLIP eval.py text-to-image: top-10 run, "
                                            "Recall@k with |rel| denominator, MRR@10",
                                "encoders": {}, "arms": {}}
    per_query: dict[str, dict[str, np.ndarray]] = {}

    cache_dir = Path(args.cache_dir)
    for name in [e for e in args.encoders.split(",") if e]:
        print(f"== encoder {name}")
        enc = get_encoder(name, args.device)
        iemb = image_embeddings(cat, enc, cache_dir / Path(args.catalog).name)
        qemb = encode_queries(enc, queries)
        ranked = _dense_run(qemb, iemb.astype(np.float64), ids, ext.MARQO_TOPK)
        m = [ext.marqo_t2i_metrics(r, gt[q]) for r, q in zip(ranked, queries)]
        pq = {key: np.array([x[key] for x in m]) for key in m[0]}
        per_query[f"encoder:{name}"] = pq
        results["encoders"][name] = summarise({k: v.tolist() for k, v in pq.items()})
        del enc, iemb, qemb
        import gc

        gc.collect()

    if args.arms:
        from engine02.pipeline import Engine02

        enc = get_encoder(args.arm_encoder, args.device)
        engine = Engine02(cat, enc, cache_dir=cache_dir / Path(args.catalog).name)
        for arm in [a for a in args.arms.split(",") if a]:
            print(f"== arm {arm}")
            ranked, ms = _arm_run(engine, queries, arm, ext.MARQO_TOPK, args.n_candidates)
            m = [ext.marqo_t2i_metrics(r, gt[q]) for r, q in zip(ranked, queries)]
            pq = {key: np.array([x[key] for x in m]) for key in m[0]}
            per_query[f"arm:{arm}"] = pq
            results["arms"][arm] = summarise({k: v.tolist() for k, v in pq.items()})
            results["arms"][arm]["ms_per_query"] = round(ms, 1)
            results["arms"][arm]["encoder"] = args.arm_encoder

    results["paired_tests"] = _paired_table(per_query, ("recall@1", "recall@10", "mrr"))
    jdump(results, Path(args.out))


def _paired_table(per_query: dict[str, dict[str, np.ndarray]], metrics: tuple[str, ...]) -> list[dict]:
    """Paired permutation tests (10,000 sign flips) between every pair of systems, per metric."""
    names = list(per_query)
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            for mt in metrics:
                if mt not in per_query[a] or mt not in per_query[b]:
                    continue
                x, y = per_query[a][mt], per_query[b][mt]
                if len(x) != len(y):
                    continue
                d = x - y
                lo, hi = bootstrap_ci(d)
                rows.append({"a": a, "b": b, "metric": mt, "delta": round(float(d.mean()), 5),
                             "delta_ci95": [round(lo, 5), round(hi, 5)],
                             "p_perm": round(paired_permutation_test(x, y), 5)})
    return rows


# =====================================================================================
# marqo-attr
# =====================================================================================
def cmd_marqo_attr(args) -> None:
    """Attribute tasks. Marqo's protocol fuses doc embeddings 0.9*image + 0.1*text; ENGINE 02 fuses
    ranked lists (RRF) instead, so the two are the same *task and metric* but different mechanisms.
    """
    bench = Path(args.bench_dir)
    cat = Catalog.load(ROOT / args.catalog if not Path(args.catalog).is_absolute() else args.catalog)
    ids = cat.items["item_id"].astype(str).tolist()
    cache_dir = Path(args.cache_dir) / Path(args.catalog).name
    out: dict = {"dataset": args.dataset, "catalog": args.catalog,
                 "protocol": "marqo-FashionCLIP '<attr>-to-product': top-10 run, P@1/P@10/MRR@10; "
                             "Marqo docs = 0.9*image + 0.1*text embedding, ours as stated per row",
                 "tasks": {}}
    enc = get_encoder(args.encoder, args.device)
    iemb = image_embeddings(cat, enc, cache_dir).astype(np.float64)
    temb = None
    from engine02.pipeline import Engine02

    engine = Engine02(cat, enc, cache_dir=cache_dir)

    for qcol in [c for c in args.query_cols.split(",") if c]:
        gt = ext.load_marqo_ground_truth(_gt_path(bench, args.dataset, qcol, "image+text"))
        queries = list(gt)
        if args.limit_queries:
            queries = queries[: args.limit_queries]
        qemb = encode_queries(enc, queries)
        per_query: dict[str, dict[str, np.ndarray]] = {}

        # (a) Marqo's own document representation: 0.9*image + 0.1*text, renormalised
        if temb is None:
            texts = cat.items["title"].astype(str).tolist()
            temb = encode_queries(enc, texts, batch=512)
        mix = 0.9 * iemb + 0.1 * temb
        mix = mix / np.clip(np.linalg.norm(mix, axis=1, keepdims=True), 1e-12, None)
        for label, docs in (("marqo_doc_0.9img+0.1txt", mix), ("image_only", iemb)):
            ranked = _dense_run(qemb, docs, ids, ext.MARQO_TOPK)
            m = [ext.marqo_attr_metrics(r, gt[q]) for r, q in zip(ranked, queries)]
            per_query[f"dense:{label}"] = {k: np.array([x[k] for x in m]) for k in m[0]}

        # (b) ENGINE 02 arms
        for arm in [a for a in args.arms.split(",") if a]:
            ranked, ms = _arm_run(engine, queries, arm, ext.MARQO_TOPK, args.n_candidates)
            m = [ext.marqo_attr_metrics(r, gt[q]) for r, q in zip(ranked, queries)]
            per_query[f"arm:{arm}"] = {k: np.array([x[k] for x in m]) for k in m[0]}

        out["tasks"][qcol] = {
            "n_queries": len(queries),
            "systems": {k: summarise({m: v.tolist() for m, v in pq.items()}) for k, pq in per_query.items()},
            "paired_tests": _paired_table(per_query, ("p@1", "p@10", "mrr")),
        }
        print(json.dumps({qcol: out["tasks"][qcol]["systems"]}, indent=2))
    jdump(out, Path(args.out))


# =====================================================================================
# polyvore-compat  (FITB + compatibility AUC)
# =====================================================================================
class _OutfitScorer:
    """Score a *whole* outfit with the OutfitTransformer compatibility head.

    `engine02/complete_look.py:FastOutfitTransformer` only exposes anchors→candidates scoring; the
    compatibility task needs P(compatible | whole set), which is the head's native input. Written
    here (not in the shipped module) so nothing existing changes — see the report for the hook.
    """

    def __init__(self, ot):
        self.ot = ot

    def score(self, outfits: list[list[int]], batch: int = 32) -> np.ndarray:
        ot = self.ot
        flat = sorted({p for o in outfits for p in o})
        ot.ensure_embeddings(flat, "compatibility")
        m = ot.models["compatibility"]
        out = []
        with ot.torch.inference_mode():
            for i in range(0, len(outfits), batch):
                qs = [ot.CQuery(outfit=[ot._item(p, "compatibility") for p in o]) for o in outfits[i : i + batch]]
                out.append(m.predict_score(qs, use_precomputed_embedding=True).float().cpu().numpy().reshape(-1))
        return np.concatenate(out) if out else np.zeros(0)


def cmd_polyvore_compat(args) -> None:
    from engine02.compat import CategoryCooccurrence

    cat = Catalog.load(ROOT / args.catalog if not Path(args.catalog).is_absolute() else args.catalog)
    items = cat.items
    cache_dir = Path(args.cache_dir) / Path(args.catalog).name
    enc = get_encoder(args.encoder, args.device)
    emb = image_embeddings(cat, enc, cache_dir).astype(np.float64)
    cooc = CategoryCooccurrence.load(ROOT / args.cooccurrence) if args.cooccurrence else None

    ot = scorer = None
    if not args.no_ot:
        from engine02.complete_look import FastOutfitTransformer

        heads = tuple(h for h in args.ot_heads.split(",") if h)
        ot = FastOutfitTransformer(cat, device=args.device, heads=heads,
                                   cache_file=cache_dir / "ot_clip_emb.npz")
        scorer = _OutfitScorer(ot)

    res: dict = {"catalog": args.catalog, "encoder": args.encoder, "n_items": len(cat),
                 "fitb": {}, "compat_auc": {}}

    # ---------------- FITB (canonical: 4 candidates, chance 25%) ----------------
    for neg_mode in [m for m in args.neg_modes.split(",") if m]:
        qs = ext.fitb_questions(items, args.n_fitb, seed=args.seed, n_cands=args.n_cands, neg_mode=neg_mode)
        print(f"== FITB neg={neg_mode}: {len(qs)} questions")
        hits: dict[str, list[float]] = {}
        rng = np.random.default_rng(args.seed)
        t_ot = 0.0
        for q in qs:
            sc = {"random": rng.random(len(q.candidates)),
                  "embedding_similarity": (emb[q.candidates] @ emb[q.anchors].T).mean(axis=1)}
            if cooc is not None:
                from engine02.compat import compat_scores

                v = compat_scores([items.at[p, "category"] for p in q.candidates],
                                  [items.at[a, "category"] for a in q.anchors], cooc)
                if v is not None:
                    sc["category_npmi"] = np.asarray(v)
            if ot is not None:
                t = time.time()
                if "compatibility" in ot.models:
                    sc["outfit_transformer"] = ot.compatibility(q.anchors, q.candidates)
                if "complementary" in ot.models:
                    tc = items.at[q.candidates[q.gold], "subcategory"] or items.at[q.candidates[q.gold], "category"]
                    sc["ot_complementary"] = ot.complementary(q.anchors, q.candidates, str(tc or ""))
                t_ot += time.time() - t
            for name, s in sc.items():
                hits.setdefault(name, []).append(ext.fitb_hit(s, q.gold))
        block = {"n_questions": len(qs), "n_candidates": args.n_cands, "chance": 1.0 / args.n_cands,
                 "neg_mode": neg_mode, "ot_ms_per_candidate": round(t_ot / max(1, args.n_cands * len(qs)) * 1000, 2),
                 "accuracy": summarise(hits),
                 "paired_tests": _paired_table({k: {"acc": np.array(v)} for k, v in hits.items()}, ("acc",))}
        res["fitb"][neg_mode] = block
        print(json.dumps(block["accuracy"], indent=2))

    # ---------------- compatibility AUC ----------------
    for neg_mode in [m for m in args.neg_modes.split(",") if m]:
        pairs = ext.compat_pairs(items, args.n_compat, seed=args.seed, neg_mode=neg_mode)
        print(f"== compatibility AUC neg={neg_mode}: {len(pairs)} outfit pairs")
        outfits = [p.positive for p in pairs] + [p.negative for p in pairs]
        labels = np.array([1] * len(pairs) + [0] * len(pairs))
        scores: dict[str, np.ndarray] = {
            "embedding_pairwise_similarity": np.array([ext.mean_pairwise_similarity(emb, o) for o in outfits]),
        }
        if cooc is not None:
            scores["category_npmi"] = np.array(
                [ext.mean_pairwise_npmi(cooc, [items.at[p, "category"] for p in o]) for o in outfits])
        if scorer is not None and "compatibility" in ot.models:
            t = time.time()
            scores["outfit_transformer"] = scorer.score(outfits)
            print(f"   OT scored {len(outfits)} outfits in {time.time() - t:.0f}s")
        block = {"n_outfits": len(outfits), "n_positive": int(labels.sum()), "neg_mode": neg_mode,
                 "negative_construction": "every item replaced by a random item "
                                          + ("of the same coarse category" if neg_mode == "same_category"
                                             else "from the apparel pool"),
                 "auc": {}}
        for name, s in scores.items():
            lo, hi = ext.bootstrap_auc_ci(s, labels, n_boot=args.n_boot, seed=args.seed)
            block["auc"][name] = {"auc": round(ext.auroc(s, labels), 5), "ci95": [round(lo, 5), round(hi, 5)]}
        names = list(scores)
        block["paired_tests"] = [
            {"a": a, "b": b, **{k: round(v, 5) for k, v in
                                ext.paired_auc_delta_test(scores[a], scores[b], labels,
                                                          n_boot=args.n_boot, seed=args.seed).items()}}
            for i, a in enumerate(names) for b in names[i + 1 :]
        ]
        res["compat_auc"][neg_mode] = block
        print(json.dumps(block["auc"], indent=2))

    if ot is not None:
        ot.save_cache()
    jdump(res, Path(args.out))


# =====================================================================================
# esci
# =====================================================================================
def cmd_esci(args) -> None:
    """Amazon ESCI Task 1 (query-product ranking), apparel slice, nDCG@10 with E/S/C/I gains.

    Text only (ESCI has no images), so the "dense" leg is a *text* encoder over the product text
    and the fusion/rerank machinery is ENGINE 02's (`engine02.fusion`, `engine02.rerank`) applied to
    the judged candidate set of each query — i.e. re-ranking, exactly like KDD Cup 2022 Task 1.
    """
    from engine02.fusion import rrf, zscore
    from engine02.rerank import Term, additive_score
    from engine02.sparse import BM25Index

    d = Path(args.esci_dir)
    ex = pd.read_parquet(d / "shopping_queries_dataset_examples.parquet")
    pr = pd.read_parquet(d / "shopping_queries_dataset_products.parquet")
    ex = ex[(ex["small_version"] == 1) & (ex["split"] == args.split) & (ex["product_locale"] == args.locale)]
    print(f"ESCI task-1 {args.split}/{args.locale}: {len(ex)} judgements, {ex['query_id'].nunique()} queries")
    if args.apparel_only:
        mask = ex["query"].map(ext.is_apparel_query)
        ex = ex[mask]
        print(f"  apparel slice (query-token heuristic): {len(ex)} judgements, {ex['query_id'].nunique()} queries")
    pr = pr[pr["product_locale"] == args.locale].set_index("product_id")

    def ptext(pid: str) -> str:
        if pid not in pr.index:
            return ""
        r = pr.loc[pid]
        parts = [r.get("product_title"), r.get("product_brand"), r.get("product_color"),
                 r.get("product_bullet_point")]
        s = " ".join(str(p) for p in parts if isinstance(p, str))
        return s[: args.max_chars]

    groups = []
    for qid, g in ex.groupby("query_id"):
        g = g.drop_duplicates("product_id")
        pids = g["product_id"].astype(str).tolist()
        grades = {p: ext.ESCI_GAINS[l] for p, l in zip(pids, g["esci_label"])}
        texts = [ptext(p) for p in pids]
        if len(pids) < args.min_candidates or not any(texts):
            continue
        groups.append((str(g["query"].iloc[0]), pids, grades, texts))
        if args.limit_queries and len(groups) >= args.limit_queries:
            break
    print(f"  evaluating {len(groups)} queries, "
          f"mean {np.mean([len(p) for _, p, _, _ in groups]):.1f} candidates/query")

    # dense text embeddings
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model, device=None if args.device == "auto" else args.device)
    all_texts = [t for _, _, _, ts in groups for t in ts]
    qs = [q for q, _, _, _ in groups]
    t0 = time.time()
    demb = model.encode(all_texts, batch_size=args.batch_size, normalize_embeddings=True,
                        show_progress_bar=True, convert_to_numpy=True)
    qemb = model.encode(qs, batch_size=args.batch_size, normalize_embeddings=True, convert_to_numpy=True)
    print(f"  encoded {len(all_texts)} products + {len(qs)} queries in {time.time() - t0:.0f}s")

    systems = ("bm25", "dense", "hybrid_rrf", "hybrid_convex", "full_additive", "full_additive_zclip3")
    per_query: dict[str, dict[str, np.ndarray]] = {s: {} for s in systems}
    vals: dict[str, list[float]] = {s: [] for s in systems}
    off = 0
    for (q, pids, grades, texts), qv in zip(groups, qemb):
        de = demb[off : off + len(pids)]
        off += len(pids)
        dense = de @ qv
        bm = BM25Index(texts).scores(q)
        runs = {
            "bm25": bm,
            "dense": dense,
            "hybrid_rrf": rrf([dense, bm], k=60, depth=200),
            "hybrid_convex": 0.5 * _minmax(dense) + 0.5 * _minmax(bm),
        }
        # ENGINE 02's additive reranker with its serving weights (w_dense=1.0, w_bm25=0.5),
        # pool-level z-scores, optionally clipped at ±3 (arm full_zclip3)
        for label, clip in (("full_additive", None), ("full_additive_zclip3", 3.0)):
            terms = [Term("dense", "dense", dense, 1.0, clip=clip), Term("bm25", "bm25", bm, 0.5, clip=clip)]
            runs[label] = additive_score(terms).scores
        for s, sc in runs.items():
            order = np.argsort(-np.asarray(sc), kind="stable")
            ranked = [pids[i] for i in order[: args.k]]
            vals[s].append(ext.ndcg_linear(ranked, grades, args.k))
    for s in systems:
        per_query[s] = {f"ndcg@{args.k}": np.array(vals[s])}

    res = {
        "dataset": "amazon-science/esci-data (Shopping Queries Dataset, KDD Cup 2022 Task 1)",
        "split": args.split, "locale": args.locale, "apparel_only": bool(args.apparel_only),
        "apparel_heuristic": "whole-word match of the query against engine02.external.APPAREL_QUERY_TOKENS",
        "n_queries": len(groups), "k": args.k,
        "metric": "nDCG@k, linear gains E=1.0/S=0.1/C=0.01/I=0.0, rank discount 1/log2(r+1) "
                  "(sklearn.metrics.ndcg_score form, as in the ESCI baseline)",
        "dense_model": args.model, "task": "re-rank the judged candidate set (no images available)",
        "systems": {s: summarise({m: v.tolist() for m, v in per_query[s].items()}) for s in systems},
        "paired_tests": _paired_table(per_query, (f"ndcg@{args.k}",)),
    }
    print(json.dumps(res["systems"], indent=2))
    jdump(res, Path(args.out))


def _minmax(x: np.ndarray) -> np.ndarray:
    from engine02.fusion import minmax

    return minmax(x)


# =====================================================================================
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    base_cache = "/tmp2/mzjiang/Research_Project/agents/bench/index"
    base_bench = "/tmp2/mzjiang/Research_Project/agents/bench/marqo_bench"
    base_out = "/tmp2/mzjiang/Research_Project/agents/bench/out"

    p = sub.add_parser("build-catalog")
    p.add_argument("--source", required=True, choices=sorted(ALL_SOURCES.values()))
    p.add_argument("--out", required=True)
    p.add_argument("--split", default="data", help="HF split name ('data' for Marqo repos, else 'train')")
    p.add_argument("--text-col", default="text")
    p.add_argument("--extra-cols", default="category1,category2,category3,color")
    p.add_argument("--id-prefix", default="row", help="id prefix when the source has no item_ID column")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_build_catalog)

    p = sub.add_parser("build-gt")
    p.add_argument("--catalog", required=True)
    p.add_argument("--dataset", required=True, help="folder name under <bench-dir>/data/")
    p.add_argument("--bench-dir", default=base_bench)
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_build_gt)

    p = sub.add_parser("marqo-t2i")
    p.add_argument("--dataset", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--bench-dir", default=base_bench)
    p.add_argument("--cache-dir", default=base_cache)
    p.add_argument("--encoders", default="marqo-fashionSigLIP")
    p.add_argument("--arms", default="")
    p.add_argument("--arm-encoder", default="marqo-fashionSigLIP")
    p.add_argument("--n-candidates", type=int, default=50)
    p.add_argument("--limit-queries", type=int, default=0)
    p.add_argument("--require-gold", action="store_true",
                   help="drop queries whose gold items are absent from this corpus (needed for subsets)")
    p.add_argument("--device", default="auto")
    p.add_argument("--out", default=f"{base_out}/marqo_t2i.json")
    p.set_defaults(func=cmd_marqo_t2i)

    p = sub.add_parser("marqo-attr")
    p.add_argument("--dataset", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--query-cols", default="category2,baseColour,usage")
    p.add_argument("--bench-dir", default=base_bench)
    p.add_argument("--cache-dir", default=base_cache)
    p.add_argument("--encoder", default="marqo-fashionSigLIP")
    p.add_argument("--arms", default="hybrid_rrf,full_zclip3")
    p.add_argument("--n-candidates", type=int, default=50)
    p.add_argument("--limit-queries", type=int, default=0)
    p.add_argument("--device", default="auto")
    p.add_argument("--out", default=f"{base_out}/marqo_attr.json")
    p.set_defaults(func=cmd_marqo_attr)

    p = sub.add_parser("polyvore-compat")
    p.add_argument("--catalog", default="data/catalog/polyvore_big")
    p.add_argument("--cooccurrence", default="data/catalog/polyvore_big/category_cooccurrence.json")
    p.add_argument("--cache-dir", default=base_cache)
    p.add_argument("--encoder", default="marqo-fashionSigLIP")
    p.add_argument("--ot-heads", default="compatibility,complementary")
    p.add_argument("--no-ot", action="store_true")
    p.add_argument("--neg-modes", default="same_category,random")
    p.add_argument("--n-fitb", type=int, default=2000)
    p.add_argument("--n-compat", type=int, default=2000)
    p.add_argument("--n-cands", type=int, default=4)
    p.add_argument("--n-boot", type=int, default=2000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="auto")
    p.add_argument("--out", default=f"{base_out}/polyvore_compat.json")
    p.set_defaults(func=cmd_polyvore_compat)

    p = sub.add_parser("esci")
    p.add_argument("--esci-dir", required=True)
    p.add_argument("--split", default="test")
    p.add_argument("--locale", default="us")
    p.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--min-candidates", type=int, default=5)
    p.add_argument("--max-chars", type=int, default=512)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--limit-queries", type=int, default=0)
    p.add_argument("--apparel-only", action="store_true", default=True)
    p.add_argument("--all-queries", dest="apparel_only", action="store_false")
    p.add_argument("--device", default="auto")
    p.add_argument("--out", default=f"{base_out}/esci.json")
    p.set_defaults(func=cmd_esci)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
