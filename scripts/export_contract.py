"""Write JSON Schemas and a real request/response example for teammates (ENGINE 01 / 03 / frontend).

  python scripts/export_contract.py            # uses the hash encoder: fast, no model download
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine02.catalog import Catalog  # noqa: E402
from engine02.compat import CategoryCooccurrence  # noqa: E402
from engine02.contracts import CONTRACT_VERSION, Engine02Request, Engine02Response  # noqa: E402
from engine02.encoders import HashEncoder  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402

OUT = ROOT / "docs" / "contract"

EXAMPLE_ROUND1 = {
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
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "engine02_request.schema.json").write_text(
        json.dumps(Engine02Request.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "engine02_response.schema.json").write_text(
        json.dumps(Engine02Response.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")

    cat = Catalog.load(ROOT / "data/catalog/kagl")
    cooc = ROOT / "data/catalog/polyvore/category_cooccurrence.json"
    enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    engine = Engine02(cat, enc, cooccurrence=CategoryCooccurrence.load(cooc) if cooc.exists() else None)

    req1 = Engine02Request(**EXAMPLE_ROUND1)
    resp1 = engine.run(req1, "full")
    first = resp1.items
    # round 2: ENGINE 03 turned "太像上班族，不要黑色＋點選第 3 件" into ledger updates
    req2 = Engine02Request(**{
        **EXAMPLE_ROUND1, "round": 2,
        "utterances": EXAMPLE_ROUND1["utterances"] + ["太像上班族，不要黑色"],
        "constraints": {**EXAMPLE_ROUND1["constraints"], "excluded_values": {"color": ["Black"]}},
        "feedback": {"design_adjust_steps": {"formal_style": -1},
                     "chosen_item_ids": [first[2].item_id] if len(first) > 2 else [],
                     "rejected_item_ids": [first[0].item_id] if first else []},
    })
    resp2 = engine.run(req2, "full")
    for name, obj in (("example_round1_request", req1), ("example_round1_response", resp1),
                      ("example_round2_request", req2), ("example_round2_response", resp2)):
        data = obj.model_dump(mode="json")
        if "query_embedding" in data and data["query_embedding"]:
            data["query_embedding"] = data["query_embedding"][:4] + ["...truncated"]
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"contract {CONTRACT_VERSION} written to {OUT}")


if __name__ == "__main__":
    main()
