"""Offline VLM tagging of design elements → c(i,d) with confidences (method inventory A6).

One generate() call per item: the model answers Q questions with one letter each, and
we read the next-token distribution at every answer step (output_scores) to get
P(option) instead of a hard label. Bipolar elements become P(pos) − P(neg); the
"not applicable" option becomes the applicability mask.

GPU (RTX 4090):  python scripts/vlm_tag_attributes.py --model Qwen/Qwen3-VL-8B-Instruct --limit 0
CPU smoke test:  python scripts/vlm_tag_attributes.py --model Qwen/Qwen3-VL-2B-Instruct --limit 3
Loading follows the Qwen3-VL README (AutoModelForImageTextToText + qwen_vl_utils).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# question id → (question, options); option letters are A, B, C...; last option = not applicable
QUESTIONS: list[tuple[str, str, list[str]]] = [
    ("shoulder", "Shoulder construction of the garment?", ["structured or padded", "soft or dropped", "not applicable"]),
    ("surface", "Fabric surface?", ["matte", "glossy or shiny", "not applicable"]),
    ("logo", "Is there a large visible logo or brand lettering?", ["yes", "no", "not applicable"]),
    ("pattern", "Pattern?", ["plain or solid", "bold pattern or graphic print", "not applicable"]),
    ("fit", "Fit or silhouette?", ["slim or tailored", "loose or oversized", "not applicable"]),
    ("formality", "Formality?", ["formal or business", "casual", "not applicable"]),
    ("collar", "Collar?", ["crisp structured collar", "no collar or soft collar", "not applicable"]),
    ("knit", "Is the fabric a knit?", ["knit", "woven or other", "not applicable"]),
    ("tone", "Overall color lightness?", ["dark", "light", "not applicable"]),
    ("saturation", "Color saturation?", ["vivid or bright", "muted or neutral", "not applicable"]),
]

# design element → (question id, sign): c = sign · (P(A) − P(B))
ELEMENT_MAP = {
    "structured_shoulders": ("shoulder", +1), "matte_fabric": ("surface", +1), "glossy_fabric": ("surface", -1),
    "visible_logo": ("logo", +1), "minimal_design": ("pattern", +1), "bold_pattern": ("pattern", -1),
    "tailored_fit": ("fit", +1), "relaxed_fit": ("fit", -1), "formal_style": ("formality", +1),
    "casual_style": ("formality", -1), "crisp_collar": ("collar", +1), "soft_knit": ("knit", +1),
    "dark_tone": ("tone", +1), "bright_color": ("saturation", +1),
}
LETTERS = "ABC"


def build_prompt() -> str:
    lines = ["Look at the product image and answer each question with a single letter.", ""]
    for i, (_, q, opts) in enumerate(QUESTIONS, 1):
        lines.append(f"Q{i}. {q} " + " ".join(f"{LETTERS[j]}) {o}" for j, o in enumerate(opts)))
    example = ", ".join(LETTERS[i % 3] for i in range(len(QUESTIONS)))
    lines += ["", f"Reply with exactly {len(QUESTIONS)} letters separated by commas and nothing else, e.g. {example}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct")
    ap.add_argument("--limit", type=int, default=0, help="0 = all items")
    ap.add_argument("--out", default=None)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--checkpoint-every", type=int, default=50, help="batches between partial writes")
    args = ap.parse_args()

    import torch
    from qwen_vl_utils import process_vision_info
    from transformers import AutoModelForImageTextToText, AutoProcessor

    cat_dir = ROOT / args.catalog
    items = pd.read_parquet(cat_dir / "items.parquet")
    if args.limit:
        items = items.head(args.limit)
    device_map = "auto" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    t0 = time.perf_counter()
    model = AutoModelForImageTextToText.from_pretrained(args.model, dtype=dtype, device_map=device_map).eval()
    processor = AutoProcessor.from_pretrained(args.model)
    load_s = time.perf_counter() - t0

    tok = processor.tokenizer
    # BPE merges runs like "BBB" into one token, so answers are comma-separated and each
    # answer step must be a single-letter token, either "A" or " A" (after ", ").
    variants = {}
    for prefix in ("", " "):
        ids = [tok.encode(prefix + L, add_special_tokens=False) for L in LETTERS]
        assert all(len(x) == 1 for x in ids), f"letters are not single tokens with prefix {prefix!r}: {ids}"
        variants[prefix] = [x[0] for x in ids]
    id_to_variant = {i: pre for pre, ids in variants.items() for i in ids}
    prompt = build_prompt()

    out = Path(args.out) if args.out else cat_dir / f"vlm_attributes_{args.model.split('/')[-1]}.parquet"
    partial = out.with_suffix(".partial.parquet")
    rows = pd.read_parquet(partial).to_dict("records") if partial.exists() else []
    done = {r["item_id"] for r in rows}
    todo = items[~items["item_id"].astype(str).isin(done)]
    print(json.dumps({"resume_from": len(rows), "todo": len(todo)}), flush=True)
    processor.tokenizer.padding_side = "left"  # required for batched generation (Qwen3-VL README)
    t_items = []

    def parse(scores, b, seq):
        answer = tok.decode(seq, skip_special_tokens=True).strip()
        steps = [(k, id_to_variant[tid]) for k, tid in enumerate(seq.tolist()) if tid in id_to_variant]
        valid = len(steps) == len(QUESTIONS)
        row = {"raw_answer": answer, "valid": valid}
        for qi, (qid, _, _) in enumerate(QUESTIONS):
            if valid:
                k, pre = steps[qi]
                probs = torch.softmax(scores[k][b, variants[pre]].float(), dim=-1).cpu().numpy()
            else:  # malformed answer: never guess an alignment
                probs = np.full(3, np.nan)
            for j, L in enumerate(LETTERS):
                row[f"{qid}_{L}"] = float(probs[j])
        for el, (qid, sign) in ELEMENT_MAP.items():
            pa, pb, pna = row[f"{qid}_A"], row[f"{qid}_B"], row[f"{qid}_C"]
            row[f"c_{el}"] = sign * (pa - pb)
            row[f"na_{el}"] = pna
        return row

    recs = list(todo.itertuples(index=False))
    for bi in range(0, len(recs), args.batch_size):
        batch = recs[bi : bi + args.batch_size]
        convs = [[{"role": "user", "content": [
            {"type": "image", "image": f"file:///{(cat_dir / r.image_path).resolve().as_posix()}"},
            {"type": "text", "text": prompt}]}] for r in batch]
        inputs = processor.apply_chat_template(convs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                               return_tensors="pt", padding=True).to(model.device)
        t = time.perf_counter()
        with torch.inference_mode():
            gen = model.generate(**inputs, max_new_tokens=4 * len(QUESTIONS), do_sample=False,
                                 output_scores=True, return_dict_in_generate=True)
        dt = time.perf_counter() - t
        t_items.append(dt / len(batch))
        L0 = inputs["input_ids"].shape[1]
        for b, r in enumerate(batch):
            row = parse(gen.scores, b, gen.sequences[b, L0:])
            row["item_id"] = str(r.item_id)
            rows.append(row)
        print(json.dumps({"done": len(rows), "batch_s": round(dt, 2), "s_per_item": round(dt / len(batch), 3),
                          "last": rows[-1]["raw_answer"]}), flush=True)
        if (bi // args.batch_size + 1) % args.checkpoint_every == 0:
            pd.DataFrame(rows).to_parquet(partial, index=False)

    pd.DataFrame(rows).to_parquet(out, index=False)
    partial.unlink(missing_ok=True)
    meta = {"model": args.model, "n_items": len(rows), "valid_rate": float(np.mean([r["valid"] for r in rows])) if rows else None, "load_s": round(load_s, 1),
            "sec_per_item_mean": round(float(np.mean(t_items)), 2) if t_items else None,
            "device": str(model.device), "questions": QUESTIONS, "element_map": ELEMENT_MAP}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta)[:500])


if __name__ == "__main__":
    main()
