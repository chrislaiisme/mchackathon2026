"""Run the ENGINE 02 demo scenarios end-to-end (two rounds each) and write a readable report.

  python scripts/demo_run.py --catalog data/catalog/kagl_polyvore --encoder marqo-fashionSigLIP --device auto
  python scripts/demo_run.py --encoder hash        # model-free dry run

Each scenario is what ENGINE 01 / 03 would send; round 2 applies the scripted feedback.
Output: reports/demo/<catalog>_<encoder>.json and .md (item ids, reasons, rule metrics, what changed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine02.catalog import Catalog  # noqa: E402
from engine02.compat import CategoryCooccurrence  # noqa: E402
from engine02.contracts import Engine02Request  # noqa: E402
from engine02.encoders import HashEncoder  # noqa: E402
from engine02.composed import ComposedEngine02  # noqa: E402
from engine02.service import Engine02Service  # noqa: E402

SCENARIOS = [
    {
        "name": "A 機能運動（聚陽主力品類）",
        "utterance": "下班直接去健身房，想穿得有運動感但不要太顯眼、也不想看起來廉價",
        "round1": {
            "retrieval_text": "men sports tshirts for workout",
            "constraints": {"category": {"state": "value", "values": ["top"]},
                            "gender": {"state": "value", "values": ["Men"]},
                            "occasion": {"state": "inferred", "values": ["Sports"]}},
            "needs": [{"need_id": "sporty", "prob": 0.45}, {"need_id": "avoid_tryhard", "prob": 0.35},
                      {"need_id": "avoid_cheap", "prob": 0.20}],
        },
        "feedback_utterance": "太亮了，不要紅色的；第 2 件的感覺比較對，但想要深藍色",
        "round2": {"excluded_values": {"color": ["Red"]}, "design_adjust_steps": {"bright_color": -1},
                   "choose_rank": 2, "critique_rank": 2, "critique": {"attribute": "color", "to_value": "Navy Blue"}},
    },
    {
        "name": "B 面試（不要太正式但要可靠）",
        "utterance": "下週面試，不想太正式但要看起來可靠",
        "round1": {
            "retrieval_text": "men smart casual shirts",  # ENGINE 01: 「不想太正式但要可靠」→ smart casual
            "constraints": {"category": {"state": "value", "values": ["top"]},
                            "gender": {"state": "value", "values": ["Men"]}},
            "needs": [{"need_id": "trustworthy", "prob": 0.5}, {"need_id": "avoid_tryhard", "prob": 0.3},
                      {"need_id": "approachable", "prob": 0.2}],
        },
        "feedback_utterance": "太像上班族了，不要黑色；第 3 件不錯但要休閒一點",
        "round2": {"excluded_values": {"color": ["Black"]}, "design_adjust_steps": {"formal_style": -1},
                   "reject_rank": 1, "choose_rank": 3, "critique_rank": 3,
                   "critique": {"attribute": "occasion", "direction": "more_casual"}},
    },
    {
        # The judge says the one thing that has no attribute in it. Nothing is excluded, nothing is
        # chosen, no critique — so a system that only reads explicit feedback has nothing to act on
        # and replays the same slate. This is the scenario the fatigue term exists for (§3.23).
        "name": "C 沒有具體回饋：「這幾件都不喜歡，再給我看別的」",
        "utterance": "想找一件約會可以穿的上衣，不要太隆重",
        "round1": {
            "retrieval_text": "women casual date top",
            "constraints": {"category": {"state": "value", "values": ["top"]},
                            "gender": {"state": "value", "values": ["Women"]}},
            "needs": [{"need_id": "approachable", "prob": 0.4}, {"need_id": "avoid_tryhard", "prob": 0.35},
                      {"need_id": "polished", "prob": 0.25}],
        },
        "feedback_utterance": "這幾件都不喜歡，再給我看別的",
        # "none of these" is an explicit signal, so it maps to both hard exclusion (never show
        # these five again) and the rejection penalty (push away items that look like them).
        # The fatigue term (§3.23) covers the weaker case: the user says nothing about the slate.
        "round2": {"reject_all": True},
    },
]


def build_request(sc: dict, rnd: int, prev_items: list | None) -> Engine02Request:
    r1 = sc["round1"]
    body = {"session_id": sc["name"], "round": rnd, "utterances": [sc["utterance"]], **r1}
    if rnd == 2:
        fb = sc["round2"]
        body["utterances"].append(sc["feedback_utterance"])
        body["constraints"] = {**r1["constraints"], "excluded_values": fb.get("excluded_values", {})}
        feedback = {"design_adjust_steps": fb.get("design_adjust_steps", {})}
        if prev_items and fb.get("choose_rank") and len(prev_items) >= fb["choose_rank"]:
            feedback["chosen_item_ids"] = [prev_items[fb["choose_rank"] - 1].item_id]
        if prev_items and fb.get("reject_rank") and len(prev_items) >= fb["reject_rank"]:
            feedback["rejected_item_ids"] = [prev_items[fb["reject_rank"] - 1].item_id]
        if prev_items and fb.get("reject_all"):
            ids = [it.item_id for it in prev_items]
            feedback["rejected_item_ids"] = ids      # similarity penalty
            feedback["excluded_item_ids"] = ids      # and never show these again
        if prev_items:
            feedback["choice_history"] = [{
                "shown_item_ids": [it.item_id for it in prev_items],
                "chosen_item_id": feedback.get("chosen_item_ids", [None])[0],
                "rejected_item_ids": feedback.get("rejected_item_ids", []),
            }]
        if prev_items and fb.get("critique") and len(prev_items) >= fb["critique_rank"]:
            feedback["reference_item_id"] = prev_items[fb["critique_rank"] - 1].item_id
            feedback["critique"] = fb["critique"]
        body["feedback"] = feedback
    return Engine02Request(**body)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--cooccurrence", default="data/catalog/polyvore/category_cooccurrence.json")
    args = ap.parse_args()

    cat = Catalog.load(ROOT / args.catalog)
    if args.encoder == "hash":
        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    cooc = ROOT / args.cooccurrence
    engine = ComposedEngine02(cat, enc, cooccurrence=CategoryCooccurrence.load(cooc) if cooc.exists() else None)
    svc = Engine02Service(engine)

    out_dir = ROOT / "reports" / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{cat.name}_{enc.name}_{args.arm}"
    dump, md = [], [f"# ENGINE 02 demo run — catalog `{cat.name}`, encoder `{enc.name}`, arm `{args.arm}`\n"]
    for sc in SCENARIOS:
        r1 = svc.rank(build_request(sc, 1, None), args.arm)
        r2 = svc.rank(build_request(sc, 2, r1.items), args.arm)
        dump.append({"scenario": sc["name"], "round1": r1.model_dump(mode="json"), "round2": r2.model_dump(mode="json")})
        md.append(f"## {sc['name']}\n\n使用者：「{sc['utterance']}」→ 回饋：「{sc['feedback_utterance']}」\n")
        for label, resp in (("第 1 輪", r1), ("第 2 輪", r2)):
            m = resp.metrics
            md.append(f"### {label}（過濾後 {resp.constraint_report.n_after_filter} 件；放寬：{resp.constraint_report.relaxed or '無'}；"
                      f"硬條件滿足 {m.hard_constraint_satisfaction:.0%}；違反回饋 {m.feedback_violations} 件）\n")
            if resp.composed:
                md.append(f"批評組合：{resp.composed}\n")
            if resp.learned_preferences:
                md.append(f"從點選學到的 Δβ：{resp.learned_preferences['design_weight_delta']}\n")
            div = resp.diversification or {}
            md.append(f"多樣化：{div.get('method')} {div.get('param')}，提前 {len(div.get('promoted', []))} 件\n")
            md.append("| # | 商品 | 顏色 | 分數 | 理由（卡片上顯示） |\n|---|---|---|---|---|")
            for it in resp.items:
                md.append(f"| {it.rank} | {it.item_id} {it.title} | {it.color} | {it.score:.2f} | {it.explanation} |")
            md.append("")
        before = {i.item_id for i in r1.items}
        after = {i.item_id for i in r2.items}
        md.append(f"第 2 輪保留 {len(before & after)} 件、換掉 {len(before - after)} 件。\n")
    (out_dir / f"{stem}.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / f"{stem}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {out_dir / stem}.md")


if __name__ == "__main__":
    main()
