"""Acceptance check: every endpoint ENGINE 03 will call, against a real catalog and encoder.

  python scripts/api_check.py --catalog data/catalog/kagl_polyvore_filled \
      --encoder marqo-fashionSigLIP --device cuda --ot --trends --out reports/server

Runs the FastAPI app in-process (no uvicorn, no port), so it works the same on a laptop with the
hash encoder and on the GPU box. Every response is written to --out for the record, and anything
that is supposed to be true is asserted here rather than eyeballed:
  /health          reports which OutfitTransformer heads loaded
  /view            panels come from the same contributions as the ranking
  /rank            negation left in retrieval_text comes back in constraint_report.input_warnings
  /complete-look   ranks with the complementary head when its checkpoint is present
  /needs/supply, /concept-image/nearest, /trends (display only: used_in_ranking must be false)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--ot", action="store_true", help="load the OutfitTransformer for /complete-look (GPU)")
    ap.add_argument("--trends", action="store_true", help="load trend keywords for display badges")
    ap.add_argument("--out", default="reports/server/api_check")
    a = ap.parse_args()

    os.environ.update(ENGINE02_CATALOG=a.catalog, ENGINE02_ENCODER=a.encoder,
                      ENGINE02_DEVICE=a.device, ENGINE02_ARM=a.arm, ENGINE02_LLM="none")
    os.environ["ENGINE02_OT"] = "1" if a.ot else "0"
    if a.trends:
        os.environ["ENGINE02_TRENDS"] = "1"

    from fastapi.testclient import TestClient

    from engine02.api import app

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    save = lambda name, obj: (out / f"{name}.json").write_text(  # noqa: E731
        json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with TestClient(app) as c:
        h = c.get("/health").json()
        save("health", h)
        print(f"health: {h['catalog']} n={h['n_items']} encoder={h['encoder']} "
              f"complete_look={h.get('complete_look')}")
        if a.ot:
            check(h["complete_look"].get("method") == "ot_cir",
                  f"/complete-look uses the complementary head (got {h['complete_look'].get('method')})")

        vocab = c.get("/vocabulary").json()
        cats = [v for v in vocab.get("category", []) if v]
        item = c.get("/items/" + c.post("/rank", json={"session_id": "s", "retrieval_text": "blue shirt",
                                                       "options": {"top_k": 1, "explain_with_llm": False}}
                                        ).json()["items"][0]["item_id"]).json()
        check(bool(item.get("design_scores")), "/items returns per-element design scores")

        body = {"session_id": "check", "retrieval_text": "women navy blue casual dress",
                "constraints": {"category": {"state": "value", "values": [cats[0] if cats else "top"]}},
                "needs": [{"need_id": next(iter(c.get("/kansei").json()["needs"])), "prob": 0.6}],
                "options": {"top_k": 5, "explain_with_llm": False}}
        v = c.post("/view", json={"request": body})
        check(v.status_code == 200, f"/view answers 200 (got {v.status_code}: {v.text[:200]})")
        if v.status_code == 200:
            data = v.json()
            save("view", data)
            resp, view = data["response"], data["view"]
            check(all(abs(sum(x["contribution"] for x in it["contributions"]) - it["score"]) < 1e-6
                      for it in resp["items"]), "contributions still sum to the score")
            check(view["diversity"]["k"] == len(resp["items"]), "Div@k counts the shown slate")
            check(view["round_diff"] is None, "no round diff without a previous round")
            m = resp["metrics"]
            check(m["feedback_violations"] == m["excluded_value_hits"] + m["rejected_item_hits"],
                  "feedback_violations is auditable from its two parts")
            check(m["hard_constraint_satisfaction"] is None or m["hard_constraint_satisfaction"] > 0.0,
                  f"satisfaction judged with the filter's comparator "
                  f"({m['hard_constraint_satisfaction']}, policy={m.get('match_policy')})")
            v2 = c.post("/view", json={"request": {**body, "round": 1}, "prev_request": body,
                                       "prev_response": resp})
            check(v2.status_code == 200 and v2.json()["view"]["round_diff"] is not None,
                  "a second round produces the diff panel")

        neg = c.post("/rank", json={"session_id": "neg", "retrieval_text": "shirts without stripes",
                                    "options": {"top_k": 3, "explain_with_llm": False}}).json()
        save("rank_negation", neg)
        check(bool(neg["constraint_report"]["input_warnings"]), "negation in retrieval_text is reported back")

        sup = c.get("/needs/supply", params={"arm": a.arm, "threshold": 0.5}).json()
        save("needs_supply", sup)
        check(all(0.0 <= x <= 1.0 for x in sup["supply"].values()), "Sup(n) is a share in [0, 1]")

        # stand in for a generated concept image with an item's own embedding (in-process, same app)
        from engine02.api import engine as _engine

        emb = _engine().image_emb
        ci = c.post("/concept-image/nearest", json={"embedding": [float(x) for x in emb[0]], "k": 3})
        check(ci.status_code == 200, f"/concept-image/nearest answers (got {ci.status_code})")
        if ci.status_code == 200:
            save("concept_image_nearest", ci.json())
            check(abs(ci.json()["items"][0]["cosine"] - 1.0) < 1e-3,
                  "the nearest item to an item's own embedding is itself")
        check(c.post("/concept-image/nearest", json={"embedding": [0.0], "k": 3}).status_code == 400,
              "a wrong embedding size is a 400, not a silent broadcast")

        gap = c.get("/gap/elements", params={"arm": a.arm, "threshold": 0.5}).json()
        save("gap_elements", gap)
        check(gap["n_sessions"] > 0, "the gap panel counts the requests this run made")
        check(all(0.0 <= e["supply"] <= 1.0 for e in gap["elements"]), "supply is a share in [0, 1]")
        check(all(e["direction"] in ("wanted", "avoided") for e in gap["elements"]),
              "wanted and avoided demand are kept apart, not averaged to zero")
        cells = c.get("/gap/cells").json()
        save("gap_cells", cells)
        check("需求側" in cells["note"], "the gap panels state their denominator")

        tr = c.get("/trends").json()
        save("trends", tr)
        check(tr["loaded"] is bool(a.trends), "trend loading follows ENGINE02_TRENDS")
        if a.trends:
            check(tr["used_in_ranking"] is False, "trends never enter the score")

        anchor = c.post("/rank", json={"session_id": "s", "retrieval_text": "jeans",
                                       "options": {"top_k": 1, "explain_with_llm": False}}
                        ).json()["items"][0]["item_id"]
        look = c.post("/complete-look", json={"anchor_item_ids": [anchor], "n_categories": 2, "k": 5})
        if look.status_code == 503:
            print("  skip  /complete-look: this catalog has no category co-occurrence")
        else:
            check(look.status_code == 200, f"/complete-look answers 200 (got {look.status_code}: {look.text[:200]})")
            if look.status_code == 200:
                save("complete_look", look.json())
                sl = look.json()["slates"]
                check(bool(sl) and all(s["items"] for s in sl), "every returned slate has items")
                print(f"  method={look.json()['method']} slates=" +
                      str([(s["category"], len(s["items"])) for s in sl]))
        check(c.post("/complete-look", json={"anchor_item_ids": ["nope"]}).status_code in (400, 503),
              "an unknown anchor id is a 400, not an empty slate list")

    print(f"\n{'FAILED: ' + '; '.join(failures) if failures else 'PASS: every endpoint behaved'}"
          f"\nresponses written to {out}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
