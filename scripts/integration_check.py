"""Can an LLM-driven ENGINE 01/03 actually drive this API? (run before the demo)

ENGINE 01 and ENGINE 03 are agents, not code we control, and on the day they will send whatever
JSON their prompt produced. This checks the things that decide whether the integration works:

  * the documented examples in docs/contract/ still validate against the shipped schemas
  * the shorthand an LLM naturally writes is accepted ("category": "top", "needs": {"id": 0.6})
  * a request with almost nothing in it still returns cards
  * the mistakes an LLM makes return an actionable 4xx, not a 500 and not a silent wrong answer
  * nothing on the serving path needs an API key or the network (ENGINE02_DEMO=1)
  * the response carries what ENGINE 03 needs to compute the next round

  python scripts/integration_check.py --catalog data/catalog/kagl --encoder hash
  python scripts/integration_check.py --catalog data/catalog/kagl_polyvore_filled \
      --encoder marqo-fashionSigLIP --device cuda --ot     # the real demo configuration

Exit code is non-zero if any check fails, so it can gate the demo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONTRACT = ROOT / "docs" / "contract"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--ot", action="store_true")
    ap.add_argument("--out", default="reports/server/integration")
    a = ap.parse_args()

    os.environ.update(ENGINE02_CATALOG=a.catalog, ENGINE02_ENCODER=a.encoder, ENGINE02_DEVICE=a.device,
                      ENGINE02_ARM=a.arm, ENGINE02_LLM="none", ENGINE02_DEMO="1",
                      ENGINE02_OT="1" if a.ot else "0")

    from fastapi.testclient import TestClient

    import engine02.api as api

    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + msg)
        if not ok:
            failures.append(msg)

    with TestClient(api.app) as c:
        health = c.get("/health").json()
        print(f"catalog={health['catalog']} n={health['n_items']} encoder={health['encoder']} "
              f"demo_mode={health.get('demo_mode')} warm_ms={health.get('warm_ms')}")
        check(health.get("demo_mode") is True,
              "demo mode is on, so no card ever waits on a network call for its wording")

        # ---- 1. the examples we published still work
        for name in ("example_round1_request.json", "example_round2_request.json"):
            f = CONTRACT / name
            if not f.exists():
                check(False, f"{name} is missing from docs/contract")
                continue
            r = c.post("/rank", json=json.loads(f.read_text(encoding="utf-8")))
            check(r.status_code == 200, f"the published {name} is accepted (got {r.status_code})")

        # ---- 2. the shorthand an LLM writes
        shorthand = {"session_id": "agent", "retrieval_text": "navy blue shirt for an interview",
                     "constraints": {"category": "top", "color": ["Navy Blue"]},
                     "needs": {"trustworthy": 0.6, "avoid_tryhard": 0.4}}
        r = c.post("/rank", json=shorthand)
        check(r.status_code == 200, f'"category": "top" and "needs": {{...}} are accepted (got {r.status_code})')
        if r.status_code == 200:
            body = r.json()
            check(len(body["items"]) > 0, "the shorthand request returns cards")
            applied = body["constraint_report"]["applied"]
            # the value is normalised through the taxonomy ("top" → the node id "tops"), so check
            # that it became a stated hard constraint, not that the string survived verbatim
            check(bool(applied.get("category")) and applied.get("color") == ["Navy Blue"],
                  f"the shorthand became a real hard constraint (applied={applied})")

        # ---- 3. the smallest thing anyone would send
        r = c.post("/rank", json={"session_id": "min", "retrieval_text": "something for a wedding"})
        check(r.status_code == 200 and r.json()["items"], "a request with only free text still returns cards")

        # ---- 4. the mistakes: each must be a clear 4xx, never a 500 and never a silent wrong answer
        bad = {
            "unknown arm": ({"session_id": "x", "retrieval_text": "shirt", "options": {"arm": "nope"}}, 400),
            "wrong type for top_k": ({"session_id": "x", "retrieval_text": "s", "options": {"top_k": "five"}}, 422),
            "state not in the enum": ({"session_id": "x", "retrieval_text": "s",
                                       "constraints": {"category": {"state": "maybe", "values": ["top"]}}}, 422),
            "needs prob out of range": ({"session_id": "x", "retrieval_text": "s",
                                         "needs": [{"need_id": "trustworthy", "prob": 5}]}, 422),
        }
        for label, (payload, want) in bad.items():
            r = c.post("/rank", json=payload)
            check(r.status_code == want, f"{label} → {want} (got {r.status_code})")
            if r.status_code >= 400 and r.status_code != want:
                print(f"        body: {r.text[:160]}")

        # an unknown field must NOT be a hard error — an agent will add one sooner or later
        r = c.post("/rank", json={"session_id": "x", "retrieval_text": "shirt", "mood": "confident"})
        check(r.status_code == 200, f"an unknown extra field is ignored rather than rejected (got {r.status_code})")

        # a value we cannot match must degrade visibly, not silently
        r = c.post("/rank", json={"session_id": "x", "retrieval_text": "shirt",
                                  "constraints": {"category": "spacesuit"}})
        check(r.status_code == 200, "an unknown category value does not crash the request")
        if r.status_code == 200:
            rep = r.json()["constraint_report"]
            check(bool(rep["relaxed"]) or r.json()["items"] == [] or rep["n_after_filter"] < rep["n_catalog"],
                  "an unmatchable category is either relaxed (and said so) or returns nothing")

        # ---- 5. what ENGINE 03 needs back
        r = c.post("/rank", json=shorthand)
        body = r.json()
        item = body["items"][0]
        for field in ("item_id", "score", "contributions", "reasons"):
            check(field in item, f"每張卡片都有 {field}")
        check(abs(sum(cb["contribution"] for cb in item["contributions"]) - item["score"]) < 1e-6,
              "contributions still sum to the score (the whole explainability claim)")
        check("metrics" in body and "match_policy" in body["metrics"],
              "the rule-based metrics come back, with the comparator that produced them")
        check("input_warnings" in body["constraint_report"],
              "input problems are reported back to ENGINE 01 instead of being swallowed")

        # ---- 6. the second round: feedback must change something
        first = c.post("/rank", json=shorthand).json()
        shown = [it["item_id"] for it in first["items"]]
        round2 = {**shorthand, "round": 1,
                  "constraints": {**shorthand["constraints"], "excluded_values": {"color": ["Navy Blue"]}},
                  "feedback": {"choice_history": [{"shown_item_ids": shown, "chosen_item_id": shown[0]}],
                               "chosen_item_ids": [shown[0]],
                               "design_adjust_steps": {"formal_style": -1}}}
        r2 = c.post("/rank", json=round2)
        check(r2.status_code == 200, f"a round-2 request with feedback is accepted (got {r2.status_code})")
        if r2.status_code == 200:
            b2 = r2.json()
            check(b2["metrics"]["excluded_value_hits"] == 0, "the exclusion is honoured in round 2")
            check([it["item_id"] for it in b2["items"]] != shown, "round 2 is not a replay of round 1")

        out = ROOT / a.out
        out.mkdir(parents=True, exist_ok=True)
        (out / "integration_report.json").write_text(json.dumps(
            {"catalog": health["catalog"], "encoder": health["encoder"], "demo_mode": health.get("demo_mode"),
             "failures": failures}, indent=1), encoding="utf-8")

    print(f"\n{'FAILED: ' + str(len(failures)) + ' check(s)' if failures else 'PASS: an agent can drive this API'}")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
