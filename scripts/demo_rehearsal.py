"""Demo rehearsal: ask ENGINE 02 what a judge would actually type, and check the answers.

    python scripts/demo_rehearsal.py --catalog data/catalog/hm_filled --encoder marqo-fashionSigLIP
    python scripts/demo_rehearsal.py --encoder hash            # fast, no model download
    python scripts/demo_rehearsal.py --out reports/rehearsal.json

`scripts/api_check.py` proves every endpoint answers. This one asks whether the answers are the
right kind of thing: 「牛仔褲」 has to return trousers in denim, 「不要黑色」 must not return black,
a NT$800 budget must not return a NT$1,500 item, a scooter commute must produce a scooter reason.
It runs the app in-process (no port), one round per scenario, and prints PASS/FAIL per check with
the latency, so a failing demo question is found before the stage rather than on it.

Exit code 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Each scenario: what the shopper says, and what has to be true of the answer.
# `expect` matches the item's subcategory + title + description (lower-cased), `forbid` must not
# appear in the item's colour, and `min_hits` says how many of the shown cards must match.
INTENT_SCENARIOS = [
    ("牛仔褲", {"item_type": "牛仔褲"}, {"expect": ["denim", "jean"], "min_hits": 2}),
    ("百褶裙", {"item_type": "裙子"}, {"expect": ["skirt", "裙"], "min_hits": 3}),
    ("約會洋裝", {"item_type": "洋裝", "occasion": "約會"}, {"expect": ["dress", "洋裝"], "min_hits": 3}),
    ("面試襯衫，不要太正式", {"item_type": "襯衫", "occasion": "面試", "style_keywords": ["不要太正式"]},
     {"expect": ["shirt", "blouse", "襯衫"], "min_hits": 3}),
    ("冬天的外套", {"item_type": "外套", "season": "冬天"}, {"expect": ["jacket", "coat", "parka", "外套"], "min_hits": 3}),
    ("帽T", {"item_type": "帽T"}, {"expect": ["hoodie", "sweatshirt"], "min_hits": 2}),
    ("針織毛衣", {"item_type": "毛衣"}, {"expect": ["sweater", "knit", "cardigan", "jumper"], "min_hits": 3}),
    ("運動鞋", {"item_type": "運動鞋"}, {"expect": ["sneaker", "shoe", "trainer"], "min_hits": 2}),
    ("上班背的包", {"item_type": "包包", "occasion": "上班"}, {"expect": ["bag", "backpack", "tote"], "min_hits": 2}),
    ("短褲", {"item_type": "短褲"}, {"expect": ["shorts"], "min_hits": 3}),
    ("連身褲", {"item_type": "連身褲"}, {"expect": ["jumpsuit", "playsuit", "dungaree", "romper"], "min_hits": 2}),
    ("白襯衫", {"item_type": "襯衫", "colors": ["白色"]}, {"expect": ["shirt", "blouse"], "min_hits": 3}),
    ("黑色西裝外套", {"item_type": "西裝外套", "colors": ["黑色"]}, {"expect": ["blazer", "jacket", "suit"], "min_hits": 2}),
    ("男生的 T 恤", {"item_type": "T恤", "gender": "男"}, {"expect": ["t-shirt", "tee", "top"], "min_hits": 3}),
    ("不要黑色的洋裝", {"item_type": "洋裝", "colors": ["不要黑色"]}, {"expect": ["dress"], "min_hits": 2, "forbid_color": "black"}),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/hm_filled")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--out", default=None, help="write every response to this json file")
    a = ap.parse_args(argv)

    os.environ.update(ENGINE02_CATALOG=a.catalog, ENGINE02_ENCODER=a.encoder, ENGINE02_DEVICE=a.device,
                      ENGINE02_DEMO="1", ENGINE02_LLM="none", ENGINE02_WARMUP="0")
    from fastapi.testclient import TestClient

    from engine02.api import app

    results: list[dict] = []
    record: dict = {}

    def check(name: str, ok: bool, detail: str = "", ms: float | None = None) -> None:
        results.append({"check": name, "ok": bool(ok), "detail": detail, "ms": ms})
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name:<34} {detail}" + (f"  ({ms:.0f} ms)" if ms else ""))

    with TestClient(app) as c:
        h = c.get("/health").json()
        print(f"商品庫 {h['catalog']}｜{h['n_items']} 件｜編碼器 {h['encoder']}\n")

        # ---- what a judge types ---------------------------------------------------------------
        for i, (says, intent, exp) in enumerate(INTENT_SCENARIOS):
            t = time.perf_counter()
            r = c.post("/intent/rank", json={"session_id": f"demo{i}", "message": says, "intent": intent,
                                             "top_k": a.top_k})
            ms = (time.perf_counter() - t) * 1000
            if r.status_code != 200:
                check(f"「{says}」", False, f"HTTP {r.status_code}", ms)
                continue
            body = r.json()
            record[says] = body
            items = body["engine02"]["items"]
            text = [" ".join(str(it.get(k) or "") for k in ("subcategory", "title", "description")).lower()
                    for it in items]
            hits = sum(any(w in t for w in exp["expect"]) for t in text)
            ok = len(items) == a.top_k and hits >= exp["min_hits"]
            detail = f"{hits}/{len(items)} 件符合 {exp['expect'][:2]}"
            if exp.get("forbid_color"):
                bad = [it["title"] for it in items if str(it.get("color") or "").lower() == exp["forbid_color"]]
                ok = ok and not bad
                detail += f"｜黑色 {len(bad)} 件"
            ms_engine = sum(body["engine02"]["timings_ms"].values())
            check(f"「{says}」", ok, detail + f"｜符合度 {body.get('match_score', 0):.2f}"
                  + (f"｜放寬 {body['engine02']['constraint_report']['relaxed']}"
                     if body["engine02"]["constraint_report"]["relaxed"] else ""), ms_engine)

        # ---- budget, situation, surprise --------------------------------------------------------
        r = c.post("/rank", json={"session_id": "b", "retrieval_text": "dress",
                                  "constraints": {"budget": {"state": "value", "max_price": 800}},
                                  "options": {"top_k": a.top_k}}).json()
        over = [i["title"] for i in r["items"] if (i["price"] or 0) > 800]
        check("預算 800 元以內", not over and bool(r["items"]), f"超出預算 {len(over)} 件；"
              f"估計價 {sum(bool(i['price_estimated']) for i in r['items'])}/{len(r['items'])} 件")

        r = c.post("/rank", json={"session_id": "s", "retrieval_text": "jacket",
                                  "context": {"commute": "scooter", "city": "新竹市", "lat": 24.81, "lon": 120.97},
                                  "options": {"top_k": a.top_k}}).json()
        reasons = " ".join(x for i in r["items"] for x in i["reasons"])
        check("情境：機車通勤有專屬理由", "機車" in reasons, reasons[:60] + "…")
        used = r.get("context_used", {})
        check("情境：回報用了哪些訊號", bool(used.get("signals")),
              "；".join(s["label"][:26] for s in used.get("signals", [])[:2]) or str(used.get("problems")))

        r = c.post("/rank", json={"session_id": "auto", "retrieval_text": "shirt", "options": {"top_k": 3}}).json()
        af = r.get("context_used", {}).get("auto_filled", {})
        check("沒送情境時自動帶入地點/日期", bool(af.get("city") and af.get("event_date")), str(af)[:70])

        r = c.post("/rank", json={"session_id": "sp", "retrieval_text": "party outfit",
                                  "context": {"surprise": True}, "options": {"top_k": a.top_k}}).json()
        sur = r["diversification"].get("surprise", {})
        check("驚喜款", bool(sur.get("applied") or sur.get("reason_if_not_applied")),
              f"套用={sur.get('applied')}｜{(sur.get('reason_if_not_applied') or '')[:46]}")

        # ---- the feedback loop -------------------------------------------------------------------
        r1 = c.post("/rank", json={"session_id": "fb", "retrieval_text": "dress", "options": {"top_k": a.top_k}}).json()
        ids1 = [i["item_id"] for i in r1["items"]]
        fb = {"chosen_item_ids": [ids1[2]], "rejected_item_ids": [ids1[0]],
              "design_weight_delta": {"minimal_design": 0.5, "bold_pattern": -0.5}}
        r2 = c.post("/rank", json={"session_id": "fb", "round": 1, "retrieval_text": "dress",
                                   "feedback": fb, "options": {"top_k": a.top_k}}).json()
        ids2 = [i["item_id"] for i in r2["items"]]
        moved = (statistics.mean(i["design_scores"].get("minimal_design", 0) for i in r2["items"])
                 - statistics.mean(i["design_scores"].get("minimal_design", 0) for i in r1["items"]))
        check("回饋：被拒絕的不再出現", ids1[0] not in ids2, f"換了 {len(set(ids2) - set(ids1))}/{len(ids2)} 張")
        check("回饋：往要求的方向移動", moved > 0, f"素面簡約平均 {moved:+.2f}")
        check("回饋：卡片說明來源", any("回饋" in x for i in r2["items"] for x in i["reasons"]),
              next((x for i in r2["items"] for x in i["reasons"] if "回饋" in x), "—")[:50])

        # ---- the services ------------------------------------------------------------------------
        svc = [
            ("整套搭配", "/complete-look", {"anchor_item_ids": [ids1[0]], "n_categories": 3, "k": 3},
             lambda j: bool(j.get("slates"))),
            ("旅行膠囊衣櫥", "/services/capsule", {"lat": 43.06, "lon": 141.35, "city": "札幌", "days": 3,
                                            "n_items": 6, "budget": 8000}, lambda j: j.get("n_outfits", 0) > 0),
            ("行程表", "/services/itinerary", {"origin": {"city": "台北"},
                                           "events": [{"date": "2026-11-03", "city": "札幌", "occasion": "晚餐"}]},
             lambda j: bool(j.get("events") and j.get("capsule"))),
            ("服裝規定解碼", "/services/dress-code", {"text": "喝喜酒 semi-formal"}, lambda j: bool(j.get("explanation_zh") or j.get("rules"))),
            ("租還是買", "/services/rent-or-buy", {"item_id": ids1[0], "occasion": "婚禮", "times_expected": 1},
             lambda j: bool(j.get("advice"))),
            ("情境需求雷達", "/context/demand", {"lat": 24.81, "lon": 120.97, "city": "新竹市", "days": 7},
             lambda j: bool(j.get("days") or j.get("shifts") or j.get("gaps"))),
        ]
        for name, path, payload, ok_fn in svc:
            t = time.perf_counter()
            r = c.post(path, json=payload)
            ms = (time.perf_counter() - t) * 1000
            ok = r.status_code == 200 and ok_fn(r.json())
            record[name] = r.json() if r.status_code == 200 else {"status": r.status_code, "body": r.text[:300]}
            check(name, ok, f"HTTP {r.status_code}", ms)

        g = c.get("/inspiration", params={"group": "runway", "limit": 3})
        insp = g.json().get("items", []) if g.status_code == 200 else []
        check("靈感圖庫清單有授權與作者", bool(insp) and all(i.get("license") and i.get("author") for i in insp),
              f"{len(insp)} 張")
        if insp:
            rr = c.post(f"/inspiration/{insp[0]['insp_id']}/recommend", json={"session_id": "insp", "top_k": 3})
            check("「我想要這種感覺」", rr.status_code in (200, 409),
                  f"HTTP {rr.status_code}" + ("（編碼器不同，已明確拒絕）" if rr.status_code == 409 else ""))

    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"results": results, "responses": record}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    bad = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(bad)}/{len(results)} 通過" + (f"；失敗：{[r['check'] for r in bad]}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
