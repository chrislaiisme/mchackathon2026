"""Drive one sentence through ENGINE 01 → 02 → 03 → 02 and assert the loop actually closes.

Run from the integration worktree, with the three apps imported in-process (no ports, so this
works on a box where nothing is listening yet):

    PYTHONPATH=. SESSION_SECRET=dev ENGINE01_LLM=stub \
    ENGINE02_CATALOG=data/catalog/kagl_polyvore_filled ENGINE02_ENCODER=marqo-fashionSigLIP \
    ENGINE02_DEVICE=cuda ENGINE02_DEMO=1 python scripts/smoke_stack.py

What it checks, in the order a judge would experience it:

  1. ENGINE 01 turns a Chinese sentence into a structured Intent.
  2. ENGINE 02 turns that Intent into ranked cards whose contributions sum to the score.
  3. ENGINE 03 turns a click plus a sentence into an updated Intent and a feedback ledger.
  4. ENGINE 02's round 2 is not a replay of round 1, and what the user rejected is gone.

Anything that fails prints why and exits non-zero, so this can gate the demo.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def check(ok: bool, msg: str, detail: str = "") -> None:
    print(("  ok   " if ok else "  FAIL ") + msg + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILURES.append(msg)


def main() -> None:
    os.environ.setdefault("ENGINE01_LLM", "stub")
    os.environ.setdefault("SESSION_SECRET", "dev-only-not-a-real-secret")
    os.environ.setdefault("ENGINE02_DEMO", "1")
    os.environ.setdefault("ENGINE02_LLM", "none")

    from fastapi.testclient import TestClient

    sentence = "下週面試，想要一件白襯衫，不要太正式"
    print(f"使用者說：{sentence}\n")

    # ── ENGINE 01 ────────────────────────────────────────────────────────────────────
    from bff.engine01_intent import llm_client
    from bff.shared.schemas import Intent

    extraction = llm_client.extract_intent(sentence, Intent())
    intent = extraction.intent.model_dump(exclude_none=True)
    print("ENGINE 01 →", json.dumps(intent, ensure_ascii=False))
    check(bool(intent.get("item_type")), "ENGINE 01 抽出了品項", str(intent))
    check(bool(intent.get("colors")), "ENGINE 01 抽出了顏色", str(intent))

    # ── ENGINE 02, round 1 ───────────────────────────────────────────────────────────
    from mcp_servers.catalog.main import app as e02_app

    with TestClient(e02_app) as e02:
        h = e02.get("/health").json()
        print(f"\nENGINE 02: catalog={h['catalog']} n={h['n_items']} encoder={h['encoder']}")
        r1 = e02.post("/retrieve", json={"session_id": "smoke", "round": 1,
                                         "message": sentence, "intent": intent})
        check(r1.status_code == 200, f"ENGINE 02 接受 ENGINE 01 的意圖（{r1.status_code}）", r1.text[:160])
        if r1.status_code != 200:
            return _finish()
        b1 = r1.json()
        shown = [p["product_id"] for p in b1["products"]]
        print(f"ENGINE 02 → {len(shown)} 張卡片, match_score={b1['match_score']}")
        for p in b1["products"][:3]:
            print(f"    {p['title'][:40]:<42} {p['attributes'].get('color', '')}")
        check(len(shown) > 0, "第一輪有卡片")
        card = b1["engine02"]["items"][0]
        total = sum(c["contribution"] for c in card["contributions"])
        check(abs(total - card["score"]) < 1e-6,
              "貢獻加總等於分數（可解釋性的不變式）", f"{total} vs {card['score']}")

        # ── ENGINE 03 ────────────────────────────────────────────────────────────────
        from bff.feedback.main import app as e03_app

        # ENGINE 03 guards /feedback with the team's session auth, so mint a dev token the same
        # way their login flow does rather than turning the guard off
        try:
            from datetime import datetime, timezone

            from bff.shared import user_store
            from bff.shared.auth import create_session_token
            from bff.shared.schemas import UserProfile

            # their session guard resolves the token against a file-backed user store, so a token
            # alone is not enough: the user has to exist
            if user_store.load_user("smoke-user") is None:
                user_store.save_user(UserProfile(
                    sub="smoke-user", email="smoke@example.invalid", name="Stack smoke test",
                    created_at=datetime.now(timezone.utc).isoformat(timespec="seconds")))
            auth = {"Authorization": f"Bearer {create_session_token('smoke-user')}"}
        except Exception as exc:                      # no SESSION_SECRET → say so, do not skip
            print(f"  (無法產生 session token: {type(exc).__name__}: {exc})")
            auth = {}

        with TestClient(e03_app) as e03:
            hh = e03.get("/health").json()
            print(f"\nENGINE 03: {hh}")
            # ENGINE 03 needs BOTH sides of round 1 (what was asked and what came back) plus the
            # vocabularies it is allowed to emit. Nothing was wiring that up — this is the glue.
            kansei = e02.get("/engine02/kansei").json()
            vocab = e02.get("/engine02/vocabulary").json()
            e02_items = b1["engine02"]["items"]
            payload = {
                "current_intent": intent,
                "feedback_inputs": [
                    {"session_id": "smoke", "round": 1, "target": "recommended",
                     "attribute_scores": [{"attribute": "正式感", "score": 0.3,
                                          "comment": "太正式"}],
                     "free_text": "太像上班族了，不要黑色",
                     "selected_option_id": shown[0]}],
                "engine02_request": {"contract_version": "0.1.0", "session_id": "smoke", "round": 1,
                                     "utterances": [sentence], "constraints": {}, "needs": [],
                                     "feedback": {}},
                "engine02_response": {
                    "contract_version": "0.1.0", "session_id": "smoke", "round": 1,
                    # their RankedItemContext says "the complete payload is accepted", so hand
                    # over our whole card rather than guessing which subset they need
                    "items": [{**it, "rank": i + 1} for i, it in enumerate(e02_items)]},
                "interaction": {"chosen_item_id": shown[0]},
                "allowed_design_elements": list(kansei.get("elements", {})) or
                                           [e["id"] for e in kansei.get("elements", [])
                                            if isinstance(e, dict)],
                "allowed_attribute_values": {k: v for k, v in vocab.items()
                                             if isinstance(v, list)},
            }
            r3 = e03.post("/feedback", json=payload, headers=auth)
            print(f"ENGINE 03（文字＋評分回饋）→ {r3.status_code}")
            if r3.status_code == 503 and "OPENAI_API_KEY" in r3.text:
                # ENGINE 03 needs a key to interpret text; its click-only path does not. On a
                # machine without the key that is a missing credential, not a broken integration —
                # so prove the click-only path works and say plainly what was not exercised.
                print("      （本機沒有 OPENAI_API_KEY：文字回饋這條路徑無法在此驗證）")
                click_only = {**payload, "feedback_inputs": [],
                              "interaction": {"chosen_item_id": shown[0],
                                              "rejected_item_ids": shown[1:2]}}
                r3 = e03.post("/feedback", json=click_only, headers=auth)
                print(f"ENGINE 03（純點擊回饋）→ {r3.status_code}")
                check(r3.status_code == 200,
                      "ENGINE 03 的純點擊路徑可用（文字路徑需要 OPENAI_API_KEY）", r3.text[:300])
            else:
                check(r3.status_code == 200, f"ENGINE 03 接受回饋（{r3.status_code}）", r3.text[:300])
            b3 = r3.json() if r3.status_code == 200 else {}
            if b3:
                print("ENGINE 03 回傳欄位:", sorted(b3)[:8])
                ops = (b3.get("feedback_round") or {}).get("ops", [])
                print(f"ENGINE 03 產生 {len(ops)} 個 op:", [o.get("op") for o in ops])
                # the ops must survive into ENGINE 02, which is what POST /handshake is for
                if ops:
                    hs = e02.post("/engine02/handshake", json={
                        "prev_request": {"session_id": "smoke", "retrieval_text": sentence},
                        "prev_response": None,
                        "feedback": {"session_id": "smoke", "round": 1, "ops": ops}})
                    check(hs.status_code == 200,
                          f"ENGINE 02 套用 ENGINE 03 的 ops（/handshake {hs.status_code}）",
                          hs.text[:200])
                    if hs.status_code == 200:
                        hb = hs.json()
                        print("   套用後:", hb["next_request"]["constraints"]["excluded_values"],
                              hb["next_request"]["feedback"]["design_adjust_steps"])
                        check(not hb["rejected_ops"],
                              "ENGINE 03 的 op 全部被接受（沒有對不上的要素）", str(hb["rejected_ops"]))

        # ── ENGINE 02, round 2 ───────────────────────────────────────────────────────
        # Close the loop with what ENGINE 03 ACTUALLY returned, not with a hand-written payload:
        # that is the difference between "the three services are alive" and "the loop works".
        next_intent = b3.get("updated_intent") or intent
        e03_feedback = b3.get("engine02_feedback")
        if e03_feedback:
            print(chr(10) + "用 ENGINE 03 回傳的 engine02_feedback 跑第二輪:",
                  sorted(k for k, v in e03_feedback.items() if v))
        payload2 = {"session_id": "smoke", "round": 2, "intent": next_intent,
                    "prev_intent": intent,
                    "feedback": e03_feedback or {
                        "session_id": "smoke", "round": 1, "target": "recommended",
                        "attribute_scores": [{"attribute": "正式感", "score": 0.3}],
                        "free_text": "太像上班族了，不要黑色",
                        "selected_option_id": shown[0]}}
        check(bool(e03_feedback), "第二輪用的是 ENGINE 03 真正吐出來的回饋（不是手寫的）")
        r2 = e02.post("/retrieve", json=payload2)
        check(r2.status_code == 200, f"ENGINE 02 接受第二輪（{r2.status_code}）", r2.text[:160])
        if r2.status_code == 200:
            b2 = r2.json()
            ids2 = [p["product_id"] for p in b2["products"]]
            colors2 = [str(p["attributes"].get("color", "")).lower() for p in b2["products"]]
            print(f"\n第二輪 → {len(ids2)} 張卡片, match_score={b2['match_score']}"
                  f"（用上一輪意圖評 {b2['engine02']['match_score_detail'].get('vs_previous_intent')}）")
            check(ids2 != shown, "第二輪不是第一輪的重播")
            excluded_now = (payload2["feedback"] or {}).get("excluded_values") or                 (r2.json()["engine02"]["constraint_report"]["applied"] or {})
            if "black" in str(payload2["feedback"]).lower() or "不要黑色" in str(payload2["feedback"]):
                check("black" not in colors2, "使用者說不要的黑色不再出現", str(colors2))
            else:
                print(f"   （本輪回饋未包含顏色排除，顏色為 {colors2}）")
            check(b2["engine02"]["metrics"]["excluded_value_hits"] == 0, "排除值沒有被違反")

    _finish()


def _finish() -> None:
    print("\n" + ("FAILED: " + str(len(FAILURES)) + " 項" if FAILURES else "PASS：三個引擎串起來了"))
    for f in FAILURES:
        print("  -", f)
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
