"""Measure the LLM paraphrase hallucination rate **without an API key** (paste-in workflow).

The reason text shown on a card is a template by default; `explain_with_llm` lets an LLM rewrite it,
and `engine02.explain.verify_paraphrase` rejects any rewrite that cites a number or a design-element
label the facts do not contain. What we never had is the number judges will ask for: *how often does
a real LLM get rejected?* Teammates who only have a ChatGPT-style chat agent (no API key) can still
produce it:

  1. export the prompts (one card = one prompt, exactly the JSON the pipeline would send):

       python scripts/eval_llm_paraphrase.py export --catalog data/catalog/kagl --encoder hash \
           --n-queries 20 --out reports/llm_paraphrase

     writes  prompts.jsonl   (machine-readable: id, facts, template reason, prompt)
             paste_me.txt    (what the teammate pastes into the chat agent, in batches of 10)

  2. the teammate pastes each batch, then saves the agent's reply verbatim into one text file
     (`id | 句子` per line — the batch instructions say exactly that).

  3. score it here; nothing is sent anywhere, and the rejection reasons are broken down:

       python scripts/eval_llm_paraphrase.py score --prompts reports/llm_paraphrase/prompts.jsonl \
           --responses <the teammate's file> --out reports/llm_paraphrase

Reported: share accepted, share rejected for an invented number vs an invented label, length stats,
and every rejected line with the offending token, so the failure mode can be quoted on a slide
instead of being summarised as "the LLM sometimes hallucinates".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.contracts import Engine02Options, Engine02Request, NeedProbability  # noqa: E402
from engine02.explain import PARAPHRASE_PROMPT, template_reasons, verify_paraphrase  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402

SEED = 20260918
BATCH_HEADER = """以下是 {n} 張推薦卡片的「事實 JSON」。請**逐張**改寫成一句自然、不超過 60 字的繁體中文推薦理由。

規則（很重要）：
- 只能用該張 JSON 裡出現的屬性、需求、數字；**不得**加入 JSON 沒有的顏色、材質、場合、品牌或數字。
- 不確定的就不要寫，寧可短。
- 每行輸出格式固定為：`<id> | <句子>`，不要加任何其他說明或標題。

"""


def _engine(a) -> Engine02:
    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    return Engine02(cat, enc, cache_dir=ROOT / a.catalog / "index")


def cmd_export(a: argparse.Namespace) -> None:
    import random

    from engine02.eval.tasks import _slot, make_queries, random_needs

    from engine02.contracts import HardConstraints

    eng = _engine(a)
    rng = random.Random(SEED)
    queries = make_queries(eng.catalog.items, n=a.n_queries)
    el_labels = {e.id: e.label for e in eng.kansei.elements}

    rows = []
    for q in queries:
        needs = random_needs(rng, eng.kansei.need_ids)
        req = Engine02Request(
            session_id=q.qid, retrieval_text=q.text(False), needs=needs,
            constraints=HardConstraints(category=_slot([q.category]), gender=_slot([q.gender])),
            options=Engine02Options(top_k=a.per_query, explain_with_llm=False))
        resp = eng.run(req, a.arm)
        for it in resp.items:
            reasons, facts = template_reasons(it.contributions, el_labels, eng.kansei.needs,
                                              resp.constraint_report.relaxed)
            if not facts:
                continue  # nothing to paraphrase; the card would stay on the template anyway
            rows.append(dict(id=f"{q.qid}-{it.item_id}", item_id=it.item_id, title=it.title,
                             template="；".join(reasons), facts=facts,
                             prompt=PARAPHRASE_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False))))

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    with (out / "prompts.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    lines = []
    for i in range(0, len(rows), a.batch):
        chunk = rows[i: i + a.batch]
        lines.append(f"=========== 第 {i // a.batch + 1} 批（共 {(len(rows) - 1) // a.batch + 1} 批）===========")
        lines.append(BATCH_HEADER.format(n=len(chunk)))
        for r in chunk:
            lines.append(f"{r['id']} | {json.dumps(r['facts'], ensure_ascii=False)}")
        lines.append("")
    (out / "paste_me.txt").write_text("\n".join(lines), encoding="utf-8")

    vocab = ROOT / a.out / "vocabulary.json"
    vocab.write_text(json.dumps(eng.vocabulary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} cards from {len(queries)} queries -> {out}/prompts.jsonl")
    print(f"give the teammate {out}/paste_me.txt ({(len(rows) - 1) // a.batch + 1} batches of {a.batch});"
          f" they paste each batch and save the replies as `<id> | <句子>` lines")


def _parse_responses(path: Path) -> dict[str, str]:
    """Accept `id | text` lines (what the batch asks for) or JSONL {"id":..., "text":...}."""
    out: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("=====") or line.startswith("#"):
            continue
        if line.startswith("{"):
            try:
                d = json.loads(line)
                if d.get("id"):
                    out[str(d["id"])] = str(d.get("text", "")).strip()
                continue
            except json.JSONDecodeError:
                pass
        if "|" in line:
            i, t = line.split("|", 1)
            i, t = i.strip(), t.strip()
            if i and t and t[0] not in "{[":  # skip the prompt lines echoed back
                out[i] = t
    return out


def cmd_score(a: argparse.Namespace) -> None:
    prompts = {}
    for line in Path(a.prompts).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            prompts[d["id"]] = d
    answers = _parse_responses(Path(a.responses))
    vocab_file = Path(a.prompts).parent / "vocabulary.json"
    vocab = json.loads(vocab_file.read_text(encoding="utf-8")) if vocab_file.exists() else []

    num_re = re.compile(r"-?\d+(?:\.\d+)?")
    rows = []
    for cid, text in answers.items():
        p = prompts.get(cid)
        if p is None:
            rows.append(dict(id=cid, status="unknown_id", text=text, offending=""))
            continue
        facts = p["facts"]
        ok = verify_paraphrase(text, facts, vocab)
        allowed_nums, allowed_labels = set(), set()
        for f in facts:
            for _, v in f.items():
                if isinstance(v, (int, float)):
                    allowed_nums |= {f"{v}", f"{abs(v):.2f}"}
                elif isinstance(v, str):
                    allowed_labels.add(v)
                elif isinstance(v, list):
                    allowed_labels.update(x for x in v if isinstance(x, str))
        bad_num = [n for n in num_re.findall(text)
                   if n not in allowed_nums and f"{float(n):.2f}" not in allowed_nums]
        bad_lab = [lab for lab in vocab if lab and lab in text and not any(lab in x for x in allowed_labels)]
        rows.append(dict(id=cid, status="accepted" if ok else "rejected", text=text,
                         offending=", ".join(bad_num + bad_lab), n_chars=len(text),
                         template=p["template"]))

    df = pd.DataFrame(rows)
    missing = sorted(set(prompts) - set(answers))
    n = len(df[df.status != "unknown_id"])
    acc = float((df.status == "accepted").sum()) / max(1, n)
    rej = df[df.status == "rejected"]
    num_rej = float(sum(bool(num_re.findall(o)) for o in rej.offending)) / max(1, len(rej)) if len(rej) else 0.0

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "paraphrase_scored.csv", index=False, encoding="utf-8-sig")
    summary = dict(n_cards=len(prompts), n_answered=n, n_missing=len(missing),
                   accepted=round(acc, 4), rejected=round(1 - acc, 4),
                   rejected_for_a_number=round(num_rej, 4),
                   median_chars=float(np.median(df.n_chars.dropna())) if n else None,
                   over_60_chars=int((df.n_chars.fillna(0) > 60).sum()))
    (out / "paraphrase_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if len(rej):
        print(f"\n{len(rej)} rejected — the fact-checker caught these (first 10):")
        for r in rej.head(10).itertuples():
            print(f"  [{r.offending}] {r.text[:70]}")
    if missing:
        print(f"\n{len(missing)} cards have no answer (first 5): {missing[:5]}")
    print("\nReminder: a rejected rewrite is not a failure of the system — the card falls back to the\n"
          "template, so the user never sees the invented fact. The number to quote is the rejection rate.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--catalog", default="data/catalog/kagl")
    e.add_argument("--encoder", default="hash")
    e.add_argument("--device", default="auto")
    e.add_argument("--arm", default="full_zclip3")
    e.add_argument("--n-queries", type=int, default=20)
    e.add_argument("--per-query", type=int, default=5)
    e.add_argument("--batch", type=int, default=10)
    e.add_argument("--out", default="reports/llm_paraphrase")
    s = sub.add_parser("score")
    s.add_argument("--prompts", default="reports/llm_paraphrase/prompts.jsonl")
    s.add_argument("--responses", required=True)
    s.add_argument("--out", default="reports/llm_paraphrase")
    a = ap.parse_args()
    (cmd_export if a.cmd == "export" else cmd_score)(a)


if __name__ == "__main__":
    main()
