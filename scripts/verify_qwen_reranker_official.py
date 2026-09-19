"""Qwen3-VL-Reranker (2B / 8B) through the official repo class, on the 48-row verify sample.

The sentence-transformers CrossEncoder path failed for 8B (LogitScore true_token_id), so
this follows the qwen3-vl-embedding README: Qwen3VLReranker(...).process(inputs).
Also compares document modality: image only vs image + title.

  git clone https://github.com/QwenLM/Qwen3-VL-Embedding third_party/qwen3-vl-embedding
  python scripts/verify_qwen_reranker_official.py --models Qwen/Qwen3-VL-Reranker-2B,Qwen/Qwen3-VL-Reranker-8B
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "verify_sample"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="Qwen/Qwen3-VL-Reranker-2B,Qwen/Qwen3-VL-Reranker-8B")
    ap.add_argument("--repo", default=str(ROOT / "third_party" / "qwen3-vl-embedding"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "qwen_reranker_official_cuda.json"))
    args = ap.parse_args()

    import numpy as np
    import torch

    sys.path.insert(0, args.repo)
    from src.models.qwen3_vl_reranker import Qwen3VLReranker

    rows = json.loads((SAMPLE / "meta.json").read_text(encoding="utf-8"))["rows"]
    idxs = list(range(0, len(rows), len(rows) // 8))[:8]
    queries = [(i, " ".join(rows[i]["text"].split()[1:]) or rows[i]["text"]) for i in idxs]
    img = [str((SAMPLE / r["image"]).resolve()) for r in rows]
    doc_sets = {
        "image": [{"image": p} for p in img],
        "image+title": [{"image": p, "text": r["text"]} for p, r in zip(img, rows)],
    }
    results = {}
    for name in args.models.split(","):
        rec = {"model": name}
        try:
            torch.cuda.reset_peak_memory_stats()
            t0 = time.perf_counter()
            model = Qwen3VLReranker(model_name_or_path=name, torch_dtype=torch.bfloat16)
            rec["load_s"] = round(time.perf_counter() - t0, 2)
            for mode, docs in doc_sets.items():
                rr, t_total = [], 0.0
                for qi, q in queries:
                    torch.cuda.synchronize()
                    t = time.perf_counter()
                    scores = model.process({"instruction": "Retrieve images or text relevant to the user's query.",
                                            "query": {"text": q}, "documents": docs})
                    torch.cuda.synchronize()
                    t_total += time.perf_counter() - t
                    s = np.asarray(scores, dtype=float)
                    rr.append(1.0 / (int((s > s[qi]).sum()) + 1))
                rec[mode] = {"MRR": round(float(np.mean(rr)), 4),
                             "R@1": round(float(np.mean([x == 1.0 for x in rr])), 4),
                             "ms_per_pair": round(t_total / (len(queries) * len(docs)) * 1000, 2),
                             "random_MRR": round(float(np.mean([1 / k for k in range(1, len(docs) + 1)])), 4)}
            rec["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
            rec["status"] = "ok"
            del model
            torch.cuda.empty_cache()
        except Exception as e:  # record and continue with the next model
            rec["status"] = "failed"
            rec["error"] = f"{type(e).__name__}: {e}"[:800]
        results[name] = rec
        print(json.dumps(rec), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
