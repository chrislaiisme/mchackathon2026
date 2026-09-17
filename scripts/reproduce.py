"""One entry point for the whole ENGINE 02 offline evaluation chain, with fixed seeds.

  python scripts/reproduce.py --check-claims                 # which doc numbers have a script
  python scripts/reproduce.py --list                         # stages, in order, with their cost
  python scripts/reproduce.py --stage core --dry-run         # print the exact commands
  python scripts/reproduce.py --stage core --catalog data/catalog/kagl --encoder marqo-fashionSigLIP
  python scripts/reproduce.py --stage all --device cuda --out-root reports/reproduce

Why this exists: every number in `docs/engine02-design.md` came from its own script with its own
flags, spread over two machines and several sub-agents. `--check-claims` makes the coverage
explicit — for each claim in the design doc, the stage that regenerates it, or `MISSING` if none
exists. The stage list is the reproducibility statement for the judges, and the manifest it
writes (command, exit code, wall time, output files, git commit) is the evidence.

Seeds: every stage is invoked with `--seed 0` where the script accepts it, `PYTHONHASHSEED=0`,
and the catalog/encoder are pinned on the command line. Stages that need a GPU, the VLM tagging
output, or the blind visual labels are marked and skipped (with a reason) when the input is
absent, rather than failing the run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


@dataclass
class Stage:
    name: str
    desc: str
    args: list[str]  # after `python scripts/<script>`
    script: str
    groups: tuple[str, ...] = ("all",)
    needs: tuple[str, ...] = ()  # gpu | vlm_tags | visual_labels | outfits | polyvore | esci
    out: str | None = None  # relative to --out-root; "" = the script has its own default
    minutes: str = "?"
    claims: tuple[str, ...] = field(default_factory=tuple)


# `{cat}`, `{enc}`, `{dev}`, `{out}` are substituted; `{out}` is <out-root>/<stage.out>.
STAGES: list[Stage] = [
    Stage("tests", "unit tests (model-free, HashEncoder)", ["-q", "tests"], "pytest",
          groups=("all", "core", "fast"), minutes="<1",
          claims=("§0 additive guarantee", "§3.9 132/138 tests pass")),
    Stage("ablation", "T1–T6: retrieval, constraints, concepts, reasons, feedback, γ trade-off",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}", "--tasks", "t1,t2,t3,t4,t5,t6",
           "--n-queries", "100", "--n-targets", "200", "--out", "{out}"],
          "run_ablation.py", groups=("all", "core"), out="ablation_{catname}_{enc}", minutes="20–60",
          claims=("§3.1 T1", "§3.2 T2", "§3.3 T3", "§3.4 T4", "§3.5 T5", "§3.5d T6", "§3.10 z-clip")),
    Stage("visual_labels", "3.3b/3.3c: AUROC of c(i,d) vs the blind visual labels",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--out", "{out}/visual_label_auroc.csv"],
          "eval_visual_labels.py", groups=("all", "core"), needs=("visual_labels",),
          out="visual_labels_{catname}", minutes="2–5", claims=("§3.3b", "§3.3c")),
    Stage("compat_fitb", "3.5c: fill-in-the-blank compatibility (NPMI vs embedding vs OutfitTransformer)",
          ["--catalog", "data/catalog/polyvore_big", "--encoder", "{enc}", "--device", "{dev}",
           "--n", "200", "--out", "{out}/compat_fitb.json"],
          "eval_compat_fitb.py", groups=("all", "core"), needs=("polyvore",),
          out="compat_fitb", minutes="5–15", claims=("§3.5c",)),
    Stage("composed", "T8: 「這件但換成 X」 composed retrieval",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}", "--seed", "0", "--out", "{out}"],
          "eval_composed.py", groups=("all", "core"), out="composed_{catname}", minutes="10–30",
          claims=("§3.7 T8",)),
    Stage("preference", "T7: learning Δβ from clicks (Bayes vs PRD ±1 vs Thompson vs LinUCB)",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}", "--stage", "evaluate",
           "--seed", "0", "--out", "{out}"],
          "eval_preference.py", groups=("all", "core"), out="preference_{catname}", minutes="20–60",
          claims=("§3.7 T7",)),
    Stage("preference_damping", "T7b: shrinking the first click (κ=1)",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}", "--out", "{out}"],
          "eval_preference_damping.py", groups=("all",), out="preference_damping_{catname}",
          minutes="20–60", claims=("§3.12 T7b",)),
    Stage("slate", "T9: slate diversification (MMR / DPP / xQuAD)",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}", "--seed", "0", "--out", "{out}"],
          "eval_slate.py", groups=("all", "core"), out="slate_{catname}", minutes="10–20",
          claims=("§3.7 T9",)),
    Stage("complete_look", "complete-the-look: complementary category then item",
          ["--catalog", "data/catalog/polyvore_big", "--device", "{dev}", "--seed", "0",
           "--out", "{out}"],
          "eval_complete_look.py", groups=("all",), needs=("polyvore",), out="complete_look",
          minutes="10–30", claims=("§3.7 搭配推薦",)),
    Stage("ltr", "T10: learned additive weights vs hand-set weights",
          ["--stage", "evaluate", "--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}",
           "--out", "{out}"],
          "eval_ltr.py", groups=("all",), out="ltr_{catname}", minutes="20–60", claims=("§3.7 T10",)),
    Stage("trends", "T11 (new): what the trend-keyword term does to the ranking",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}", "--n-queries", "100",
           "--weights", "0,0.1,0.2,0.5", "--seed", "0", "--out", "{out}"],
          "eval_trends.py", groups=("all", "core", "audit"), out="trends_{catname}", minutes="5–15",
          claims=("§6.6 趨勢訊號（PRD）",)),
    Stage("concept_image", "T12 (new): the generated-concept-image branch at weights 0 / 0.1 / 0.2",
          ["--catalog", "{cat}", "--encoder", "{enc}", "--device", "{dev}", "--n-targets", "150",
           "--weights", "0,0.1,0.2", "--seed", "0", "--out", "{out}"],
          "eval_concept_image.py", groups=("all", "core", "audit"), out="concept_image_{catname}",
          minutes="10–20", claims=("§3.6 full_concept_image",)),
    Stage("classify", "3.11: attribute filling for the Polyvore rows (accuracy + effect on E2)",
          ["evaluate", "--catalog", "kagl_full", "--out", "{out}"],
          "eval_classify.py", groups=("all",), needs=("gpu",), out="classify", minutes="30–90",
          claims=("§3.11",)),
    Stage("vlm_tags", "3.13: Qwen3-VL-8B design-element tagging of the catalog (input to full_concept_vlm)",
          ["--catalog", "{cat}", "--model", "Qwen/Qwen3-VL-8B-Instruct"],
          "vlm_tag_attributes.py", groups=("all",), needs=("gpu",), out=None, minutes="60–240",
          claims=("§3.13",)),
    Stage("models", "model verification: every candidate encoder / reranker / VLM loads and runs",
          ["--models", "all", "--device", "{dev}"],
          "verify_models.py", groups=("all",), needs=("gpu",), out=None, minutes="30–120",
          claims=("§3.3d encoder 比較", "§4.4 GPU 實測")),
    Stage("contract", "export the request/response JSON Schemas and the two-round examples",
          [], "export_contract.py", groups=("all", "core", "fast"), out=None, minutes="<1",
          claims=("§4.3 規格檔",)),
    Stage("handshake", "export the ENGINE 03 feedback schema, the round-trip example and the §7 panels",
          [], "export_handshake_example.py", groups=("all", "core", "fast", "audit"), out=None,
          minutes="<1", claims=("§4.2 ENGINE 03 介面",)),
]

# Claims in docs/engine02-design.md and the stage that regenerates them. `None` = no script.
CLAIMS: list[tuple[str, str, str | None]] = [
    ("§0/§3.1 T1 NDCG@5 by arm and wording", "hybrid vs dense vs BM25, 5k and 44k", "ablation"),
    ("§0/§3.2 T2 relaxation rate, satisfaction", "hard filter + relaxation ladder", "ablation"),
    ("§0/§3.3 T3 c(i,d) AUROC (metadata labels)", "antonym vs descriptor vs random words", "ablation"),
    ("§0/§3.4 T4 reason coverage / sufficiency", "sufficient vs necessity vs contrastive", "ablation"),
    ("§0/§3.5 T5 feedback SR@t", "critique vs Rocchio, rule-based simulated user", "ablation"),
    ("§3.5d T6 γ trade-off", "NDCG cost vs need alignment", "ablation"),
    ("§3.10 z-clip ±3", "full vs full_zclip3", "ablation"),
    ("§3.1 latency per query", "timings_ms in the T1 CSV", "ablation"),
    ("§3.3d encoder comparison (7 models)", "dense NDCG@5 per encoder", "ablation"),  # one run per encoder
    ("§3.3b visual-label AUROC (420 items)", "logo / collar / pattern / fit / sheen", "visual_labels"),
    ("§3.3c VLM vs CLIP on the same 397 items", "Qwen3-VL-8B tag AUROC", "visual_labels"),
    ("§3.5c FITB compatibility (200 questions)", "NPMI 25% / embedding 48% / OT 54.5%", "compat_fitb"),
    ("§3.7 T7 preference learning", "Bayes vs PRD ±1 vs Thompson / LinUCB", "preference"),
    ("§3.12 T7b damping κ", "|Δβ| after one click, feedback-first reasons", "preference_damping"),
    ("§3.7 T8 composed critique", "NDCG@10 0.347 → 0.610", "composed"),
    ("§3.7 T9 diversification", "DPP θ=0.9, near-duplicate rate", "slate"),
    ("§3.7 complete-the-look MRR", "complementary head vs similarity", "complete_look"),
    ("§3.7 T10 learned weights", "5-fold CV, +0.009 vs routing", "ltr"),
    ("§3.11 attribute filling", "gender 0.935 / colour 0.838, effect on satisfaction", "classify"),
    ("§3.13 merged-catalog VLM tagging", "17,783 items, 0.39 s/item, format accuracy", "vlm_tags"),
    ("§4.4 GPU latency (reranker, VLM, LLM)", "ms/pair, VRAM", "models"),
    ("§2/§3.0 catalog build (5k / 44k / merged)", "scripts/prepare_catalog.py + merge_catalogs.py", "prepare"),
    ("§3.8 taxonomy coverage 95.3% / 85.9%", "scripts/build_taxonomy_v1.py --report", "taxonomy"),
    ("§6.6 trend keyword term (PRD, never measured)", "T11: NDCG cost, keyword coverage", "trends"),
    ("§3.6 full_concept_image (never run)", "T12: weights 0 / 0.1 / 0.2 with a stand-in image", "concept_image"),
    ("§4.2 ENGINE 03 handshake + §7 panels", "ops → next request, ledger, said-vs-unsaid, round diff", "handshake"),
    ("§3.3b the blind visual labels themselves", "sampling + LLM annotation of data/labels/*.csv", None),
    ("§0/§3.3 Kansei table v1 (32 papers, 50 non-zero cells)", "literature coding of K[n,d]", None),
    ("§0 LLM paraphrase fact-check (Qwen3-1.7B got 盛夏偏熱 backwards)", "one-off manual observation", None),
    ("§3.9 cross-hardware reproduction (cfda4 V100, fp16)", "rerun tests + ablation + vlm_tags there", "tests"),
]

EXTRA_STAGES = {  # stages that exist as scripts but take arguments too project-specific to template
    "prepare": "scripts/prepare_catalog.py / scripts/merge_catalogs.py (see engine02/README.md)",
    "taxonomy": "scripts/build_taxonomy_v1.py (writes engine02/resources/taxonomy_v1.json + a coverage report)",
}


def available(needs: tuple[str, ...], catalog: Path, device: str) -> tuple[bool, str]:
    for need in needs:
        if need == "gpu" and device == "cpu":
            return False, "needs a GPU (--device cpu)"
        if need == "visual_labels" and not list((ROOT / "data/labels").glob("labels_part_*.csv")):
            return False, "data/labels/labels_part_*.csv not present (blind labels are not in git)"
        if need == "vlm_tags" and not list(catalog.glob("vlm_attributes_*.parquet")):
            return False, "no vlm_attributes_*.parquet in the catalog (run the vlm_tags stage)"
        if need == "polyvore" and not (ROOT / "data/catalog/polyvore_big/items.parquet").exists():
            return False, "data/catalog/polyvore_big missing"
        if need == "outfits" and not (catalog / "items.parquet").exists():
            return False, "catalog missing"
    return True, ""


def build_cmd(st: Stage, catalog: str, encoder: str, device: str, out_root: Path) -> list[str]:
    catname = Path(catalog).name
    out = str(out_root / st.out.format(catname=catname, enc=encoder)) if st.out else ""
    subs = {"{cat}": catalog, "{enc}": encoder, "{dev}": device, "{out}": out}
    args = [subs.get(a, a).format(catname=catname, enc=encoder) if "{" in a else a for a in st.args]
    if st.script == "pytest":
        return [PY, "-m", "pytest", *args]
    return [PY, str(ROOT / "scripts" / st.script), *args]


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception:  # pragma: no cover
        return "unknown"


def check_claims() -> int:
    by_stage = {s.name for s in STAGES} | set(EXTRA_STAGES)
    missing = [c for c in CLAIMS if c[2] is None]
    unknown = [c for c in CLAIMS if c[2] is not None and c[2] not in by_stage]
    width = max(len(c[0]) for c in CLAIMS) + 2
    print("docs/engine02-design.md 的數字 → 產生它的 stage\n")
    for claim, what, stage in CLAIMS:
        tag = stage if stage else "MISSING"
        print(f"  {claim:<{width}} {tag:<20} {what}")
    print(f"\n{len(CLAIMS) - len(missing)}/{len(CLAIMS)} claims have a script.")
    if missing:
        print("\n沒有腳本可重現（要人工或一次性產出，簡報上必須照實說）：")
        for claim, what, _ in missing:
            print(f"  - {claim}: {what}")
    if unknown:
        print("\nBUG: claim points at an unknown stage:", [c[0] for c in unknown])
    for name, note in EXTRA_STAGES.items():
        print(f"\n[{name}] 不在自動鏈裡：{note}")
    return 1 if unknown else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="core", help="all | core | fast | audit | comma-separated stage names")
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out-root", default="reports/reproduce")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check-claims", action="store_true")
    ap.add_argument("--stop-on-error", action="store_true")
    args = ap.parse_args()

    if args.check_claims:
        return check_claims()
    if args.list:
        for st in STAGES:
            print(f"  {st.name:<20} {st.minutes:>7} min  groups={','.join(st.groups):<20} "
                  f"needs={','.join(st.needs) or '-':<16} {st.desc}")
        return 0

    want = {w.strip() for w in args.stage.split(",") if w.strip()}
    chosen = [st for st in STAGES if want & set(st.groups) or st.name in want]
    if not chosen:
        print(f"no stage matched {args.stage!r}; try --list", file=sys.stderr)
        return 2
    out_root = Path(args.out_root if Path(args.out_root).is_absolute() else ROOT / args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    catalog = ROOT / args.catalog
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(ROOT)}

    manifest = {"git_commit": git_commit(), "catalog": args.catalog, "encoder": args.encoder,
                "device": args.device, "python": sys.version.split()[0], "stages": []}
    rc_all = 0
    for st in chosen:
        cmd = build_cmd(st, args.catalog, args.encoder, args.device, out_root)
        ok, why = available(st.needs, catalog, args.device)
        rec = {"stage": st.name, "cmd": " ".join(cmd), "claims": list(st.claims)}
        if not ok:
            rec.update(status="skipped", reason=why)
            print(f"[skip] {st.name}: {why}", flush=True)
        elif args.dry_run:
            rec.update(status="dry-run")
            print(f"[dry] {' '.join(cmd)}", flush=True)
        else:
            print(f"[run ] {st.name}: {' '.join(cmd)}", flush=True)
            t0 = time.perf_counter()
            p = subprocess.run(cmd, cwd=ROOT, env=env)
            rec.update(status="ok" if p.returncode == 0 else "failed", returncode=p.returncode,
                       seconds=round(time.perf_counter() - t0, 1))
            print(f"[{rec['status']}] {st.name} in {rec['seconds']}s", flush=True)
            if p.returncode != 0:
                rc_all = 1
                if args.stop_on_error:
                    manifest["stages"].append(rec)
                    break
        manifest["stages"].append(rec)
    (out_root / "reproduce_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_root / 'reproduce_manifest.json'}", flush=True)
    return rc_all


if __name__ == "__main__":
    raise SystemExit(main())
