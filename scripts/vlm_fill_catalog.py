"""Screen and label a freshly built catalog with a vision-language model, in the catalog's OWN vocabulary.

A modern source (e.g. Amazon Reviews 2023) brings modern-looking products but two problems KAGL did
not have: noise that no category rule can catch (size-chart images, 50-packs, non-garments), and
missing attributes (colour ~12%, season and occasion 0%). One pass of Qwen3-VL fixes both.

Method (same as scripts/vlm_tag_attributes.py): the model sees the image and the title and answers
every question with ONE letter; the next-token distribution at each answer step gives P(option)
instead of a hard label. Consequences that matter for "creative but sensible":

  * every option is an existing catalog value, so the model cannot invent vocabulary that the
    ranking, the Chinese intent adapter or the negation logic would not recognise;
  * each answer carries a probability, so apply_vlm_fill.py can leave a field EMPTY when the model
    is unsure rather than guess -- an empty field relaxes cleanly, a wrong one filters wrongly;
  * bold or unusual pieces are KEPT and scored for boldness (Q8) instead of being thrown away.
    What is thrown away is only what is not a wearable product at all (Q1).

    CUDA_VISIBLE_DEVICES=0 python scripts/vlm_fill_catalog.py --catalog data/catalog/amz_pool
    python scripts/vlm_fill_catalog.py --catalog data/catalog/amz_pool --limit 3 \
        --model Qwen/Qwen3-VL-2B-Instruct                      # CPU smoke test

Output: <catalog>/vlm_fill_<model>.parquet, one row per item, with p_<question>_<option> for every
option, the argmax and its probability. It never edits items.parquet; apply_vlm_fill.py does.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# (question id, question, [(option text shown to the model, value written to the catalog), ...])
# Values are the catalog's own vocabulary; see engine02/attribute_fill.py COLOR_FAMILIES and
# engine02/intent_adapter.py ZH_OCCASION / ZH_SEASON. None = "no value" (never written).
QUESTIONS: list[tuple[str, str, list[tuple[str, str | None]]]] = [
    ("product", "What does the image show?", [
        ("one wearable clothing item, pair of shoes, or bag, shown as a product", "ok"),
        ("a size chart, measurement table, text or diagram", "size_chart"),
        ("several items sold together as a pack or set", "multipack"),
        ("something that is not clothing, shoes or a bag", "not_apparel")]),
    ("category", "Which kind of item is it?", [
        ("top (shirt, t-shirt, blouse, sweater, hoodie)", "top"),
        ("bottom (pants, jeans, shorts, skirt)", "bottom"),
        ("dress, jumpsuit or romper", "dress"),
        ("outerwear (coat, jacket, blazer, vest)", "outerwear"),
        ("shoes", "shoes"),
        ("bag", "bag")]),
    ("color", "Main color of the item?", [
        ("black", "Black"), ("white", "White"), ("off-white or cream", "Off White"),
        ("grey", "Grey"), ("charcoal", "Charcoal"), ("navy blue", "Navy Blue"),
        ("blue", "Blue"), ("teal or turquoise", "Teal"), ("red", "Red"),
        ("burgundy or maroon", "Burgundy"), ("pink", "Pink"), ("purple or lavender", "Purple"),
        ("green", "Green"), ("olive", "Olive"), ("yellow", "Yellow"), ("mustard", "Mustard"),
        ("orange", "Orange"), ("brown", "Brown"), ("tan or camel", "Tan"),
        ("beige or khaki", "Beige"), ("many colors, no single main color", None)]),
    ("season", "Which season is it best suited for?", [
        ("spring", "Spring"), ("summer", "Summer"), ("fall", "Fall"), ("winter", "Winter")]),
    ("occasion", "Which occasion is it best suited for?", [
        ("everyday casual", "Casual"), ("office, business or formal event", "Formal"),
        ("smart casual, dinner or a date", "Smart Casual"), ("sports or outdoor activity", "Sports"),
        ("travel", "Travel")]),
    ("fit", "Fit or silhouette?", [
        ("slim or fitted", "slim"), ("regular", "regular"), ("loose or oversized", "loose"),
        ("not applicable (shoes or bag)", None)]),
    ("pattern", "Pattern?", [
        ("solid, no pattern", "solid"), ("stripes or checks/plaid", "stripe_check"),
        ("floral", "floral"), ("graphic, logo or print", "graphic"), ("other pattern", "other")]),
    ("boldness", "How bold is the design?", [
        ("a basic everyday staple", 0), ("has one distinctive detail", 1),
        ("a bold statement piece", 2), ("avant-garde, experimental or costume-like", 3)]),
    # Every option names VISUAL cues. The first wording offered "romantic or feminine", and the model
    # used it as a gender detector: all 20 items it chose were womenswear, slippers included.
    ("style", "Which style fits it best, judging only by the visible design?", [
        ("minimalist: plain, clean lines, no decoration", "minimalist"),
        ("streetwear: oversized cuts, bold graphics or logos, sneaker culture", "streetwear"),
        ("classic or business: tailored, timeless, neat", "classic"),
        ("sporty: athletic cut or technical fabric", "sporty"),
        ("bohemian: flowing shapes, folk or ethnic prints, fringe", "bohemian"),
        ("romantic: ruffles, lace, bows or soft florals", "romantic"),
        ("edgy, gothic or punk: leather, studs, dark or harsh details", "edgy"),
        ("vintage or retro: clearly the styling of an earlier decade", "vintage"),
        ("preppy: collegiate, polo, cable knit or tartan", "preppy"),
        ("avant-garde: unusual cuts, shapes or construction", "avant_garde")]),
]
LETTERS = "ABCDEFGHIJKLMNOPQRSTU"
assert max(len(o) for _, _, o in QUESTIONS) <= len(LETTERS)


def build_prompt(title: str) -> str:
    lines = ["Look at the product image and its title, then answer each question with a single letter.",
             f"Product title: {title[:200]}", ""]
    for i, (_, q, opts) in enumerate(QUESTIONS, 1):
        lines.append(f"Q{i}. {q} " + " ".join(f"{LETTERS[j]}) {o[0]}" for j, o in enumerate(opts)))
    # Answers are NUMBERED ("Q1: A, Q2: B") and parsed by number, not by position. A bare letter list
    # let the model skip Q1 and start at Q2 while still emitting nine letters, so every answer shifted
    # by one and nothing flagged it (pilot: a skirt's "B = bottom" read as "B = size chart").
    example = ", ".join(f"Q{i + 1}: {LETTERS[i % 3]}" for i in range(len(QUESTIONS)))
    lines += ["", "Answer every question, in order, in exactly this format and nothing else:", example]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct")
    ap.add_argument("--limit", type=int, default=0, help="0 = all items")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--checkpoint-every", type=int, default=20, help="batches between partial writes")
    a = ap.parse_args()

    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    cat_dir = Path(a.catalog) if Path(a.catalog).is_absolute() else ROOT / a.catalog
    items = pd.read_parquet(cat_dir / "items.parquet")
    if a.limit:
        items = items.head(a.limit)
    cuda = torch.cuda.is_available()
    dtype = (torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16) if cuda else torch.float32
    t0 = time.perf_counter()
    # {"": 0}, not "auto": on a shared GPU "auto" offloaded layers to the CPU although 60 GB were free.
    model = AutoModelForImageTextToText.from_pretrained(a.model, dtype=dtype, device_map={"": 0} if cuda else "cpu").eval()
    processor = AutoProcessor.from_pretrained(a.model)
    processor.tokenizer.padding_side = "left"      # required for batched generation (Qwen3-VL README)
    load_s = time.perf_counter() - t0

    tok = processor.tokenizer
    # BPE can merge "AB" into one token, so answers are comma-separated and every answer step must be
    # a single-letter token: bare ("A"), after the comma's space (" A"), or -- if the model drops the
    # space anyway -- merged with the comma (",A"), which Qwen's tokenizer does emit as one token.
    variants = {}
    for prefix in ("", " ", ",", ":"):      # ":" -- "Q1:A" merges ":A" into one token
        ids = [tok.encode(prefix + L, add_special_tokens=False) for L in LETTERS]
        if all(len(x) == 1 for x in ids):
            variants[prefix] = [x[0] for x in ids]
    assert "" in variants and " " in variants, "letters are not single tokens"
    id_to_variant = {i: pre for pre, ids in variants.items() for i in ids}

    out = cat_dir / f"vlm_fill_{a.model.split('/')[-1]}.parquet"
    partial = out.with_suffix(".partial.parquet")
    rows = pd.read_parquet(partial).to_dict("records") if partial.exists() else []
    done = {r["item_id"] for r in rows}
    todo = items[~items["item_id"].astype(str).isin(done)]
    print(json.dumps({"resume_from": len(rows), "todo": len(todo), "load_s": round(load_s, 1)}), flush=True)

    qnum_before = re.compile(r"Q(\d+)\s*:\s*$")
    qnum_glued = re.compile(r"Q(\d+)\s*$")    # the colon lives inside the letter token (":A")

    def parse(scores, b, seq) -> dict:
        ids = seq.tolist()
        answer = tok.decode(ids, skip_special_tokens=True).strip()
        # Locate each answer by the question number written just before it -- never by position.
        found: dict[int, tuple[int, str]] = {}
        for k, t in enumerate(ids):
            if t not in id_to_variant:
                continue
            before = tok.decode(ids[:k], skip_special_tokens=True)
            rx = qnum_glued if id_to_variant[t] == ":" else qnum_before
            mnum = rx.search(before)
            if mnum:
                qi = int(mnum.group(1)) - 1
                if 0 <= qi < len(QUESTIONS) and qi not in found:
                    found[qi] = (k, id_to_variant[t])
        row = {"raw_answer": answer, "valid": len(found) == len(QUESTIONS), "n_answered": len(found)}
        for qi, (qid, _, opts) in enumerate(QUESTIONS):
            n = len(opts)
            if qi in found:
                k, pre = found[qi]
                # softmax over THIS question's options only: a letter outside the range is not an answer
                probs = torch.softmax(scores[k][b, variants[pre][:n]].float(), dim=-1).cpu().numpy()
                j = int(np.argmax(probs))
            else:                                  # skipped question: leave it empty, never shift
                probs, j = np.full(n, np.nan), -1
            for jj in range(n):
                row[f"p_{qid}_{jj}"] = float(probs[jj])
            row[f"{qid}_idx"] = j
            row[f"{qid}_p"] = float(probs[j]) if j >= 0 else float("nan")
        return row

    t_items = []
    recs = list(todo.itertuples(index=False))
    for bi in range(0, len(recs), a.batch_size):
        batch = recs[bi: bi + a.batch_size]
        convs = [[{"role": "user", "content": [
            {"type": "image", "image": str((cat_dir / r.image_path).resolve())},
            {"type": "text", "text": build_prompt(str(r.title))}]}] for r in batch]
        inputs = processor.apply_chat_template(convs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                               return_tensors="pt",
                                               processor_kwargs={"padding": True}).to(model.device)
        t = time.perf_counter()
        with torch.inference_mode():
            gen = model.generate(**inputs, max_new_tokens=8 * len(QUESTIONS), do_sample=False,
                                 output_scores=True, return_dict_in_generate=True)
        dt = time.perf_counter() - t
        t_items.append(dt / len(batch))
        L0 = inputs["input_ids"].shape[1]
        for b, r in enumerate(batch):
            row = parse(gen.scores, b, gen.sequences[b, L0:])
            row["item_id"] = str(r.item_id)
            rows.append(row)
        print(json.dumps({"done": len(rows), "s_per_item": round(dt / len(batch), 3),
                          "last": rows[-1]["raw_answer"]}), flush=True)
        if (bi // a.batch_size + 1) % a.checkpoint_every == 0:
            pd.DataFrame(rows).to_parquet(partial, index=False)

    pd.DataFrame(rows).to_parquet(out, index=False)
    partial.unlink(missing_ok=True)
    meta = {"model": a.model, "n_items": len(rows),
            "valid_rate": float(np.mean([r["valid"] for r in rows])) if rows else None,
            "load_s": round(load_s, 1),
            "sec_per_item_mean": round(float(np.mean(t_items)), 3) if t_items else None,
            "questions": [(q, text, [o[0] for o in opts]) for q, text, opts in QUESTIONS],
            "values": {q: [o[1] for o in opts] for q, _, opts in QUESTIONS}}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("n_items", "valid_rate", "sec_per_item_mean")}))


if __name__ == "__main__":
    main()
