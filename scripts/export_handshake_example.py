"""Export the ENGINE 03 ↔ ENGINE 02 handshake contract: schema, ledger and a JSON round trip.

  python scripts/export_handshake_example.py         # hash encoder: fast, no model download

Writes into docs/contract/:
  engine03_feedback.schema.json        the closed operation set (PRD M8) as a JSON Schema —
                                       paste it into ENGINE 03's structured-output `json_schema`
  example_engine03_handshake.json      round 1 request → cards → ENGINE 03 ops → ledger →
                                       round 2 request, all real output of engine02.handshake
  example_view_round2.json             the PRD §7 panels (engine02.panels.build_view) for round 2,
                                       including the round-1-vs-round-2 diff

Uses the same hash encoder as scripts/export_contract.py, so the item ids match the existing
round-1/round-2 examples and the files can be diffed against each other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine02.catalog import Catalog  # noqa: E402
from engine02.compat import CategoryCooccurrence  # noqa: E402
from engine02.contracts import CONTRACT_VERSION, Engine02Request  # noqa: E402
from engine02.encoders import HashEncoder  # noqa: E402
from engine02.handshake import (  # noqa: E402
    AdjustOp,
    ChoiceOp,
    ExcludeOp,
    FeedbackRound,
    FeelingOp,
    apply_round,
    handshake_example,
    need_likelihood,
    round_trip,
)
from engine02.panels import build_view, view_labels  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402

OUT = ROOT / "docs" / "contract"

ROUND1 = {
    "session_id": "demo-interview",
    "round": 1,
    "utterances": ["下週面試，不想太正式但要看起來可靠"],
    "retrieval_text": "men shirts for formal",
    "constraints": {
        "category": {"state": "value", "values": ["top"]},
        "gender": {"state": "value", "values": ["Men"]},
        "occasion": {"state": "inferred", "values": ["Formal"]},
        "season": {"state": "unmentioned", "values": []},
    },
    "needs": [
        {"need_id": "trustworthy", "label": "被信任", "prob": 0.55},
        {"need_id": "avoid_tryhard", "label": "怕顯得太用力", "prob": 0.30},
        {"need_id": "approachable", "label": "親切好相處", "prob": 0.15},
    ],
    "options": {"top_k": 5, "explain_with_llm": False},
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / "data/catalog/kagl")
    cooc = ROOT / "data/catalog/polyvore/category_cooccurrence.json"
    enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    engine = Engine02(cat, enc, cooccurrence=CategoryCooccurrence.load(cooc) if cooc.exists() else None)

    req1 = Engine02Request(**ROUND1)
    resp1 = engine.run(req1, "full")
    shown = [it.item_id for it in resp1.items]

    # 「太像上班族，不要黑色」＋點選第 3 件 — exactly the PRD §5 example, as M8 operations.
    # feeling carries log L(e|n) (PRD formula ④); ENGINE 02 never invents p(n).
    fb = FeedbackRound(
        session_id=req1.session_id, round=1, utterance="太像上班族，不要黑色",
        ops=[
            ExcludeOp(attribute="color", value="Black", quote="不要黑色"),
            FeelingOp(quote="太像上班族",
                      need_log_likelihood={"avoid_tryhard": 0.8, "trustworthy": -0.2}, lam=1.0),
            AdjustOp(element="formal_style", step=-1, quote="太像上班族"),
            ChoiceOp(shown_item_ids=shown, chosen_item_id=shown[2] if len(shown) > 2 else shown[0],
                     rejected_item_ids=shown[:1]),
        ],
    )
    doc = handshake_example(req1, resp1, fb, kansei=engine.kansei)
    req2 = round_trip(apply_round(req1, resp1, fb, kansei=engine.kansei).request)
    resp2 = engine.run(req2, "full")
    doc["round_2_response_items"] = [
        {"rank": it.rank, "item_id": it.item_id, "title": it.title, "score": round(it.score, 4),
         "reasons": it.reasons} for it in resp2.items
    ]
    doc["round_2_metrics"] = resp2.metrics.model_dump()
    # the choice likelihood ENGINE 03 needs, computed from the returned design_scores only
    if len(resp1.items) >= 2:
        n0 = req1.needs[0].need_id
        doc["choice_likelihood_example"] = {
            "formula": "σ(α·(S(A|n) − S(B|n))), S(i|n) = Σ_d K[n,d]·c(i,d) from RankedItem.design_scores",
            "need_id": n0, "A": resp1.items[0].item_id, "B": resp1.items[1].item_id,
            "P_A_over_B": round(need_likelihood(resp1.items[0], resp1.items[1], engine.kansei, n0), 4),
        }
    doc["notes"] = [
        "round_2_request 是 engine02.handshake.apply_round 的真實輸出，並經過一次 JSON round trip。",
        "exclude 進 constraints.excluded_values（永不放寬）；critique 的目標值進 required_values。",
        "adjust 只傳步數；權重換算 = KanseiTable.step_size（0.25），上限 ±3 步。",
        "choice 只累積 choice_history；Δβ 由 Engine02Service 擬合（T7），ENGINE 03 不要自己算權重。",
        "reference_item_id / critique 只在當輪有效，下一輪由 apply_round 清掉。",
        "ledger 就是畫面上的『帳本』：每條證據記下改了什麼、從多少變成多少。",
    ]

    (OUT / "engine03_feedback.schema.json").write_text(
        json.dumps(FeedbackRound.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
    for d in (doc["round_1_request"], doc["round_2_request"]):
        d.pop("query_embedding", None)
    (OUT / "example_engine03_handshake.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    view = build_view(req2, resp2, req1, resp1, **view_labels(engine))
    (OUT / "example_view_round2.json").write_text(
        view.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps({"contract_version": CONTRACT_VERSION, "out": str(OUT),
                      "ops": [o.op for o in fb.ops], "ledger_rows": len(doc["ledger"]),
                      "round2_items": [i["item_id"] for i in doc["round_2_response_items"]],
                      "turnover": view.round_diff.turnover if view.round_diff else None},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
