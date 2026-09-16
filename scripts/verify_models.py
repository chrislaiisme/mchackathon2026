"""ENGINE 02 model verification harness.

Proves each candidate model loads and runs on this machine, and measures it:
status, licence, download/load time, peak RSS, params, embedding dim,
per-item latency (batch 8) and a task-specific sanity metric.

Usage
-----
    python scripts/verify_models.py --models all --device auto
    python scripts/verify_models.py --models marqo-fashionSigLIP,bge-reranker-v2-m3 --device cuda

Every model runs in its own subprocess (``--worker``) so that
  * only ONE model is in memory at a time (the process exits afterwards), and
  * peak RSS is measured per model, not polluted by earlier models.

Results are merged into ``--out`` (default reports/model_verification_<device>.json),
so partial reruns update only the requested entries.

Test data: first 48 rows of ``Marqo/polyvore`` (streamed once, cached to
data/verify_sample/ so reruns are offline).
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import random
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "verify_sample"
OT_DIR = ROOT / "third_party" / "outfit-transformer"
N_SAMPLE = 48
BATCH = 8

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# --------------------------------------------------------------------------------------
# Model registry.  licence / notes are copied from the HF model cards (2026-09-16).
# --------------------------------------------------------------------------------------
REGISTRY: dict[str, dict] = {
    # ---- embeddings ----
    "fashion-clip": dict(
        kind="embedding", repo="patrickjohncyh/fashion-clip", backend="hf_clip",
        licence="MIT", ignore=["onnx/*", "*.bin", "*.h5", "*.msgpack"]),
    "marqo-fashionCLIP": dict(
        kind="embedding", repo="Marqo/marqo-fashionCLIP", backend="open_clip",
        fallback="hf_remote", licence="Apache-2.0",
        ignore=["onnx/*", "*.bin"]),
    "marqo-fashionSigLIP": dict(
        kind="embedding", repo="Marqo/marqo-fashionSigLIP", backend="open_clip",
        fallback="hf_remote", licence="Apache-2.0",
        ignore=["onnx/*", "*.bin"]),
    "zooclaw-fashionsiglip2": dict(
        kind="embedding", repo="srpone/zooclaw-fashionsiglip2", backend="hf_siglip",
        licence="Apache-2.0",
        notes="card: AutoModel/AutoProcessor (SiglipModel arch, 384px, fine-tuned from siglip2-base-patch16-384)"),
    "siglip2-base-patch16-224": dict(
        kind="embedding", repo="google/siglip2-base-patch16-224", backend="hf_siglip",
        licence="Apache-2.0"),
    "clip-vit-base-patch32": dict(
        kind="embedding", repo="openai/clip-vit-base-patch32", backend="hf_clip",
        licence="MIT (openai/CLIP repo; HF card has no licence tag, card says deployed use out of scope)",
        ignore=["*.h5", "*.msgpack"]),
    "laion-CLIP-ViT-B-16": dict(
        kind="embedding", repo="laion/CLIP-ViT-B-16-laion2B-s34B-b88K", backend="open_clip",
        licence="MIT (card: any deployed use out of scope)", ignore=["*.bin"]),
    # ---- rerankers ----
    "Qwen3-VL-Reranker-2B": dict(
        kind="reranker", repo="Qwen/Qwen3-VL-Reranker-2B", modality="image",
        licence="Apache-2.0", dtype="bfloat16", fallback_dtype="float32",
        prompt="Retrieve images or text relevant to the user's query."),
    "bge-reranker-v2-m3": dict(
        kind="reranker", repo="BAAI/bge-reranker-v2-m3", modality="text",
        licence="Apache-2.0", ignore=["assets/*"]),
    "Qwen3-Reranker-0.6B": dict(
        kind="reranker", repo="Qwen/Qwen3-Reranker-0.6B", modality="text",
        licence="Apache-2.0", dtype="bfloat16", fallback_dtype="float32"),
    "jina-reranker-m0": dict(
        kind="reranker", repo="jinaai/jina-reranker-m0", modality="image",
        licence="CC BY-NC 4.0 (NON-COMMERCIAL - flag)", trust_remote_code=True,
        dtype="bfloat16", fallback="hf_compute_score"),
    # ---- GPU only ----
    "Qwen3-VL-Reranker-8B": dict(
        kind="reranker", repo="Qwen/Qwen3-VL-Reranker-8B", modality="image",
        licence="Apache-2.0", dtype="bfloat16", gpu_only=True,
        prompt="Retrieve images or text relevant to the user's query."),
    # ---- local LLM ----
    "Qwen3-1.7B": dict(kind="llm", repo="Qwen/Qwen3-1.7B", licence="Apache-2.0",
                       fallback_model="Qwen2.5-1.5B-Instruct"),
    "Qwen2.5-1.5B-Instruct": dict(kind="llm", repo="Qwen/Qwen2.5-1.5B-Instruct",
                                  licence="Apache-2.0", only_explicit=True),
    # ---- compatibility ----
    "outfit-transformer": dict(kind="compat", repo="github.com/owj0421/outfit-transformer",
                               licence="MIT (code); checkpoint licence not stated"),
}



def has_spec(name: str) -> bool:
    return name in REGISTRY or (name.endswith("-fp32") and name[:-5] in REGISTRY)


def get_spec(name: str) -> dict:
    """``<name>-fp32`` is an explicit float32 variant of any registry entry (CPU bf16 comparison)."""
    if name in REGISTRY:
        return REGISTRY[name]
    spec = dict(REGISTRY[name[:-5]])
    spec.update(dtype="float32", fallback_dtype=None, fallback_model=None)
    return spec


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def pick_device(arg: str) -> str:
    import torch
    if arg == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return arg


class PeakRSS:
    """Samples process RSS in a thread; also uses Windows peak working set when present."""

    def __init__(self, interval: float = 0.05):
        import psutil
        self.proc = psutil.Process()
        self.interval = interval
        self.peak = self.proc.memory_info().rss
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                self.peak = max(self.peak, self.proc.memory_info().rss)
            except Exception:
                pass
            time.sleep(self.interval)

    def start(self):
        self._t.start()
        return self

    def rss_mb(self) -> float:
        return round(self.proc.memory_info().rss / 2**20, 1)

    def peak_mb(self) -> float:
        mi = self.proc.memory_info()
        peak = max(self.peak, mi.rss, getattr(mi, "peak_wset", 0))
        return round(peak / 2**20, 1)

    def stop(self):
        self._stop.set()


def snapshot(repo: str, ignore: list[str] | None = None) -> tuple[str, float]:
    """Download (or reuse cache). Returns (local_path, seconds)."""
    from huggingface_hub import snapshot_download
    t0 = time.perf_counter()
    err = None
    for attempt in range(4):  # the Hub drops unauthenticated connections now and then
        try:
            path = snapshot_download(repo, ignore_patterns=ignore)
            return path, round(time.perf_counter() - t0, 2)
        except Exception as e:
            err = e
            time.sleep(5 * (attempt + 1))
    try:
        path = snapshot_download(repo, ignore_patterns=ignore, local_files_only=True)
    except Exception as e:
        raise RuntimeError(f"download failed: {err!r}; offline cache: {e!r}") from e
    return path, round(time.perf_counter() - t0, 2)


def n_params(module) -> int:
    return int(sum(p.numel() for p in module.parameters()))


def sync(device: str):
    if device == "cuda":
        import torch
        torch.cuda.synchronize()


# --------------------------------------------------------------------------------------
# sample data
# --------------------------------------------------------------------------------------
def prepare_sample() -> list[dict]:
    meta_path = SAMPLE_DIR / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))["rows"]
    from datasets import load_dataset
    img_dir = SAMPLE_DIR / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    last_err = None
    for attempt in range(3):
        try:
            ds = load_dataset("Marqo/polyvore", split="data", streaming=True)
            rows = []
            for i, r in enumerate(ds):
                if i >= N_SAMPLE:
                    break
                fname = f"{i:02d}_{r['item_ID']}.jpg"
                r["image"].convert("RGB").save(img_dir / fname, quality=95)
                rows.append(dict(idx=i, item_ID=r["item_ID"], category=r["category"],
                                 text=r["text"], image=f"images/{fname}"))
            break
        except Exception as e:  # network hiccups
            last_err = e
            time.sleep(3)
    else:
        raise RuntimeError(f"could not stream Marqo/polyvore: {last_err}")
    meta = dict(source="Marqo/polyvore (split=data, streaming, first 48 rows)",
                columns=["image", "category", "text", "item_ID"], rows=rows)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def load_images(rows):
    from PIL import Image
    return [Image.open(SAMPLE_DIR / r["image"]).convert("RGB") for r in rows]


def rerank_queries(rows) -> list[tuple[int, str]]:
    """8 text queries built from paired titles.  The first token (usually the brand)
    is dropped so the query is not a verbatim copy of the caption."""
    idxs = list(range(0, N_SAMPLE, N_SAMPLE // 8))[:8]
    out = []
    for i in idxs:
        words = rows[i]["text"].split()
        q = " ".join(words[1:]) if len(words) > 2 else rows[i]["text"]
        out.append((i, q))
    return out


def doc_caption(r) -> str:
    return f"{r['text']} ({r['category']})"


# --------------------------------------------------------------------------------------
# embedding backends
# --------------------------------------------------------------------------------------
def _pooled(x):
    import torch
    if isinstance(x, torch.Tensor):
        return x
    # transformers v5: get_*_features returns BaseModelOutputWithPooling
    return x.pooler_output


class HFClip:
    def __init__(self, path, device):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.torch = torch
        self.model = AutoModel.from_pretrained(path).to(device).eval()
        self.proc = AutoProcessor.from_pretrained(path)
        self.device = device

    def enc_img(self, imgs):
        inp = self.proc(images=imgs, return_tensors="pt").to(self.device)
        return _pooled(self.model.get_image_features(pixel_values=inp["pixel_values"]))

    def enc_txt(self, txts):
        inp = self.proc(text=txts, padding=True, truncation=True, return_tensors="pt").to(self.device)
        return _pooled(self.model.get_text_features(input_ids=inp["input_ids"],
                                                    attention_mask=inp["attention_mask"]))


class HFSiglip(HFClip):
    # SigLIP was trained with padding="max_length" (64 tokens); cards use the same.
    def enc_img(self, imgs):
        inp = self.proc(images=imgs, return_tensors="pt").to(self.device)
        return _pooled(self.model.get_image_features(**inp))

    def enc_txt(self, txts):
        inp = self.proc(text=txts, padding="max_length", max_length=64, truncation=True,
                        return_tensors="pt").to(self.device)
        return _pooled(self.model.get_text_features(**inp))


class OpenClip:
    def __init__(self, repo, device):
        import open_clip
        import torch
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(f"hf-hub:{repo}")
        self.model = self.model.to(device).eval()
        self.tok = open_clip.get_tokenizer(f"hf-hub:{repo}")
        self.device = device

    def enc_img(self, imgs):
        x = self.torch.stack([self.preprocess(i) for i in imgs]).to(self.device)
        return self.model.encode_image(x)

    def enc_txt(self, txts):
        return self.model.encode_text(self.tok(txts).to(self.device))


class HFRemote:
    """Marqo card 'Hugging Face' path: AutoModel(trust_remote_code=True)."""

    def __init__(self, repo, device):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.torch = torch
        self.model = AutoModel.from_pretrained(repo, trust_remote_code=True).to(device).eval()
        self.proc = AutoProcessor.from_pretrained(repo, trust_remote_code=True)
        self.device = device

    def enc_img(self, imgs):
        p = self.proc(images=imgs, return_tensors="pt")
        return self.model.get_image_features(p["pixel_values"].to(self.device), normalize=True)

    def enc_txt(self, txts):
        p = self.proc(text=txts, padding="max_length", return_tensors="pt")
        return self.model.get_text_features(p["input_ids"].to(self.device), normalize=True)


def build_embedder(backend, spec, path, device):
    if backend == "hf_clip":
        return HFClip(path, device)
    if backend == "hf_siglip":
        return HFSiglip(path, device)
    if backend == "open_clip":
        return OpenClip(spec["repo"], device)
    if backend == "hf_remote":
        return HFRemote(spec["repo"], device)
    raise ValueError(backend)


def run_embedding(name, spec, device, rec, mon):
    import torch
    import torch.nn.functional as F
    rows = prepare_sample()
    imgs = load_images(rows)
    txts = [r["text"] for r in rows]
    path, rec["download_s"] = snapshot(spec["repo"], spec.get("ignore"))

    backend = spec["backend"]
    rec["rss_before_load_mb"] = mon.rss_mb()
    t0 = time.perf_counter()
    try:
        emb = build_embedder(backend, spec, path, device)
    except Exception as e:
        if not spec.get("fallback"):
            raise
        rec["first_error"] = f"{backend}: {type(e).__name__}: {e}"[:800]
        rec["fix_attempted"] = f"fallback backend {spec['fallback']} (documented on card)"
        gc.collect()
        backend = spec["fallback"]
        t0 = time.perf_counter()
        emb = build_embedder(backend, spec, path, device)
    rec["backend"] = backend
    rec["load_s"] = round(time.perf_counter() - t0, 2)
    rec["rss_after_load_mb"] = mon.rss_mb()
    rec["params"] = n_params(emb.model)

    def encode_all(fn, items):
        out = []
        with torch.inference_mode():
            fn(items[:BATCH])  # warm-up, not timed
            sync(device)
            t = time.perf_counter()
            for s in range(0, len(items), BATCH):
                out.append(fn(items[s:s + BATCH]).float())
            sync(device)
            dt = time.perf_counter() - t
        return F.normalize(torch.cat(out), dim=-1).cpu(), dt / len(items) * 1000

    I, rec["img_ms_per_item"] = encode_all(emb.enc_img, imgs)
    T, rec["txt_ms_per_item"] = encode_all(emb.enc_txt, txts)
    rec["img_ms_per_item"] = round(rec["img_ms_per_item"], 2)
    rec["txt_ms_per_item"] = round(rec["txt_ms_per_item"], 2)
    rec["embedding_dim"] = int(I.shape[1])

    sim = T @ I.T  # text -> image
    ranks = (sim > sim.diag().unsqueeze(1)).sum(1) + 1  # 1-based rank of true image
    rec["sanity"] = {
        "task": "text->image retrieval over 48 Polyvore pairs",
        "R@1": round(float((ranks <= 1).float().mean()), 4),
        "R@5": round(float((ranks <= 5).float().mean()), 4),
        "MRR": round(float((1.0 / ranks.float()).mean()), 4),
        "random_R@1": round(1 / N_SAMPLE, 4), "random_R@5": round(5 / N_SAMPLE, 4),
    }
    dress = [i for i, r in enumerate(rows) if "dress" in r["category"].lower()]
    other = [i for i in range(len(rows)) if i not in dress]
    with torch.inference_mode():
        P = F.normalize(emb.enc_txt(["a dress", "not a dress"]).float(), dim=-1).cpu()
    s = P @ I.T  # [2, 48]
    neg = {"n_dress_images": len(dress),
           "dress_categories": sorted({rows[i]["category"] for i in dress})}
    if dress:
        neg["dress_imgs_mean_cos_a_dress"] = round(float(s[0, dress].mean()), 4)
        neg["dress_imgs_mean_cos_not_a_dress"] = round(float(s[1, dress].mean()), 4)
        neg["dress_imgs_frac_not_ge_pos"] = round(float((s[1, dress] >= s[0, dress]).float().mean()), 4)
    if other:
        neg["nondress_imgs_mean_cos_a_dress"] = round(float(s[0, other].mean()), 4)
        neg["nondress_imgs_mean_cos_not_a_dress"] = round(float(s[1, other].mean()), 4)
    rec["negation_probe"] = neg
    del emb
    gc.collect()


# --------------------------------------------------------------------------------------
# rerankers
# --------------------------------------------------------------------------------------
def _dtype(name):
    import torch
    return {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[name]


class CEReranker:
    def __init__(self, spec, path, device, dtype):
        from sentence_transformers import CrossEncoder
        kw = {}
        if dtype:
            kw["model_kwargs"] = {"dtype": _dtype(dtype)}
        self.model = CrossEncoder(path, device=device,
                                  trust_remote_code=spec.get("trust_remote_code", False), **kw)
        self.prompt = spec.get("prompt")

    def score(self, pairs):
        kw = {"prompt": self.prompt} if self.prompt else {}
        return [float(x) for x in self.model.predict(pairs, batch_size=BATCH,
                                                     show_progress_bar=False, **kw)]


class JinaComputeScore:
    """jina-reranker-m0 card 'transformers' path: AutoModel + model.compute_score."""

    def __init__(self, spec, path, device, dtype):
        from transformers import AutoModel
        self.model = AutoModel.from_pretrained(path, dtype="auto", trust_remote_code=True)
        self.model.to(device).eval()

    def score(self, pairs):
        import torch
        with torch.inference_mode():
            return [float(x) for x in self.model.compute_score(
                [list(p) for p in pairs], max_length=2048, doc_type="image")]


def run_reranker(name, spec, device, rec, mon, budget_s):
    if spec.get("gpu_only") and device != "cuda":
        rec.update(status="gpu_only_untested")
        return
    import numpy as np
    rows = prepare_sample()
    path, rec["download_s"] = snapshot(spec["repo"], spec.get("ignore"))
    dtype = spec.get("dtype")
    rec["rss_before_load_mb"] = mon.rss_mb()
    t0 = time.perf_counter()
    try:
        rr = CEReranker(spec, path, device, dtype)
    except Exception as e:
        rec["first_error"] = f"CrossEncoder(dtype={dtype}): {type(e).__name__}: {e}"[:800]
        gc.collect()
        if spec.get("fallback") == "hf_compute_score":
            rec["fix_attempted"] = "card transformers path: AutoModel(trust_remote_code)+compute_score"
            t0 = time.perf_counter()
            rr = JinaComputeScore(spec, path, device, dtype)
        elif spec.get("fallback_dtype"):
            rec["fix_attempted"] = f"reload with dtype={spec['fallback_dtype']}"
            dtype = spec["fallback_dtype"]
            t0 = time.perf_counter()
            rr = CEReranker(spec, path, device, dtype)
        else:
            raise
    rec["load_s"] = round(time.perf_counter() - t0, 2)
    rec["dtype"] = dtype or "model default"
    rec["rss_after_load_mb"] = mon.rss_mb()
    rec["params"] = n_params(rr.model)

    if spec["modality"] == "image":
        docs = [str((SAMPLE_DIR / r["image"]).resolve()).replace("\\", "/") for r in rows]
    else:
        docs = [doc_caption(r) for r in rows]
    queries = rerank_queries(rows)

    # warm-up + speed probe on 8 pairs, dtype retry on runtime failure
    probe = [(queries[0][1], d) for d in docs[:BATCH]]
    try:
        rr.score(probe[:2])
    except Exception as e:
        if not spec.get("fallback_dtype") or "fix_attempted" in rec:
            raise
        rec["first_error"] = f"predict(dtype={dtype}): {type(e).__name__}: {e}"[:800]
        rec["fix_attempted"] = f"reload with dtype={spec['fallback_dtype']}"
        del rr
        gc.collect()
        dtype = spec["fallback_dtype"]
        t0 = time.perf_counter()
        rr = CEReranker(spec, path, device, dtype)
        rec["load_s"] = round(time.perf_counter() - t0, 2)
        rec["dtype"] = dtype
        rr.score(probe[:2])
    sync(device)
    t = time.perf_counter()
    rr.score(probe)
    sync(device)
    probe_ms = (time.perf_counter() - t) / len(probe) * 1000
    projected = probe_ms * len(queries) * len(docs) / 1000
    rec["probe_ms_per_pair"] = round(probe_ms, 1)
    rec["projected_full_s"] = round(projected, 1)

    rng = random.Random(0)
    reduced = projected > budget_s
    all_scores, n_pairs, t_total, rr_list, rr_pess = [], 0, 0.0, [], []
    for qi, q in queries:
        if reduced:
            others = [j for j in range(len(docs)) if j != qi]
            cand = sorted([qi] + rng.sample(others, BATCH - 1))
        else:
            cand = list(range(len(docs)))
        pairs = [(q, docs[j]) for j in cand]
        sync(device)
        t = time.perf_counter()
        sc = rr.score(pairs)
        sync(device)
        t_total += time.perf_counter() - t
        n_pairs += len(pairs)
        sc = np.array(sc)
        true = sc[cand.index(qi)]
        others_sc = np.delete(sc, cand.index(qi))
        rank = int((others_sc > true).sum()) + 1
        rank_ties = int((others_sc >= true).sum()) + 1  # ties counted against the true item
        rr_list.append(1.0 / rank)
        rr_pess.append(1.0 / rank_ties)
        all_scores.append(dict(query=q, true_item=rows[qi]["item_ID"], rank=rank, rank_pessimistic=rank_ties,
                               n_docs=len(cand), true_score=round(float(true), 4),
                               max_other=round(float(np.delete(sc, cand.index(qi)).max()), 4)))
    n_docs = BATCH if reduced else len(docs)
    rec["pair_ms"] = round(t_total / n_pairs * 1000, 1)
    rec["sanity"] = {
        "task": f"rerank {'images' if spec['modality'] == 'image' else 'captions'} for 8 title-derived queries",
        "docs_per_query": n_docs,
        "reduced_to_8_docs_due_to_budget": reduced,
        "MRR": round(float(np.mean(rr_list)), 4),
        "MRR_ties_pessimistic": round(float(np.mean(rr_pess)), 4),
        "R@1": round(float(np.mean([1.0 if x == 1.0 else 0.0 for x in rr_list])), 4),
        "random_MRR": round(float(np.mean([1 / k for k in range(1, n_docs + 1)])), 4),
        "per_query": all_scores,
    }
    del rr
    gc.collect()


def card_only_record(name, spec, rec):
    """Metadata for GPU-only models without loading weights."""
    from huggingface_hub import HfApi
    info = HfApi().model_info(spec["repo"], files_metadata=True)
    weights = sum((s.size or 0) for s in info.siblings if s.rfilename.endswith(".safetensors"))
    rec.update(
        weights_gb=round(weights / 1e9, 2),
        card_params="8B (card)", card_context="32k", card_layers=36,
        est_vram_bf16_gb=round(weights / 1e9 * 1.15, 1),
        note="Not loaded on CPU by design (16 GB RAM). Rerun with --device cuda on the RTX 4090.",
    )


# --------------------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------------------
RATIONALE = {
    "query": "想找夏天約會穿的洋裝，不要太正式",
    "item": {"title": "tibi knit long sleeve dress", "category": "Day Dresses"},
    "matched_attributes": ["類別：洋裝", "風格：針織、簡約休閒"],
    "caveats": ["長袖，盛夏可能偏熱"],
    "scores": {"dense": 0.31, "bm25": 7.2, "compatibility": 0.82},
}


def run_llm(name, spec, device, rec, mon):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    path, rec["download_s"] = snapshot(spec["repo"])
    rec["rss_before_load_mb"] = mon.rss_mb()
    dtype = _dtype(spec.get("dtype", "bfloat16"))
    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForCausalLM.from_pretrained(path, dtype=dtype).to(device).eval()
    rec["load_s"] = round(time.perf_counter() - t0, 2)
    rec["rss_after_load_mb"] = mon.rss_mb()
    rec["dtype"] = spec.get("dtype", "bfloat16")
    rec["params"] = n_params(model)

    messages = [
        {"role": "system", "content": "你是時尚電商的推薦說明助理。只根據使用者提供的 JSON 改寫，"
                                      "不得加入 JSON 以外的資訊。輸出必須是繁體中文、一句話、60 字以內，不要列點。"},
        {"role": "user", "content": "請把以下推薦理由改寫成給顧客看的一句話：\n"
                                    + json.dumps(RATIONALE, ensure_ascii=False)},
    ]
    kw = {"enable_thinking": False} if "Qwen3" in spec["repo"] else {}
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **kw)
    inputs = tok([text], return_tensors="pt").to(device)
    gen = dict(max_new_tokens=96, do_sample=True, temperature=0.7, top_p=0.8, top_k=20)
    torch.manual_seed(0)
    with torch.inference_mode():
        model.generate(**inputs, max_new_tokens=4, do_sample=False)  # warm-up
        # prefill latency
        sync(device)
        t = time.perf_counter()
        model(**inputs)
        sync(device)
        prefill = time.perf_counter() - t
        torch.manual_seed(0)
        t = time.perf_counter()
        out = model.generate(**inputs, **gen)
        sync(device)
        dt = time.perf_counter() - t
    new = out[0][inputs["input_ids"].shape[1]:]
    n_new = int(new.shape[0])
    rec.update(
        prompt_tokens=int(inputs["input_ids"].shape[1]),
        new_tokens=n_new,
        prefill_s=round(prefill, 2),
        generate_s=round(dt, 2),
        tokens_per_s=round(n_new / dt, 2),
        decode_tokens_per_s=round(max(n_new - 1, 1) / max(dt - prefill, 1e-6), 2),
        sampling="card non-thinking defaults: T=0.7 top_p=0.8 top_k=20, seed 0",
        output=tok.decode(new, skip_special_tokens=True).strip(),
    )
    rec["sanity"] = {"task": "zh-TW one-sentence paraphrase of fixed JSON rationale",
                     "output": rec["output"]}
    del model
    gc.collect()


# --------------------------------------------------------------------------------------
# outfit-transformer compatibility
# --------------------------------------------------------------------------------------
def run_compat(name, spec, device, rec, mon):
    import types

    import torch
    if not (OT_DIR / "src").exists():
        raise RuntimeError(f"clone missing: git clone https://github.com/owj0421/outfit-transformer {OT_DIR}")
    ckpts = sorted((OT_DIR / "checkpoints").rglob("*.pt*"))
    rec["checkpoints_found"] = [str(p.relative_to(OT_DIR)) for p in ckpts]
    cp = [p for p in ckpts if "compat" in str(p).lower() or "cp" in p.parent.name.lower()]
    if not cp:
        raise RuntimeError("no compatibility checkpoint under third_party/outfit-transformer/checkpoints "
                           "(README: gdown 1mzNqGBmd8UjVJjKwVa5GdGYHKutZKSSi -O checkpoints.zip)")
    ckpt = cp[0]
    rec["checkpoint"] = str(ckpt.relative_to(OT_DIR))
    sys.path.insert(0, str(OT_DIR))
    try:
        import cv2  # noqa: F401  (imported but unused by src/models/outfit_transformer.py)
    except ImportError:
        sys.modules["cv2"] = types.ModuleType("cv2")
        rec["shim"] = "cv2 stubbed (imported but unused in model code)"
    from src.data.datatypes import FashionCompatibilityQuery, FashionItem
    from src.models.outfit_clip_transformer import OutfitCLIPTransformer, OutfitCLIPTransformerConfig

    rows = prepare_sample()
    imgs = load_images(rows)
    rec["rss_before_load_mb"] = mon.rss_mb()
    t0 = time.perf_counter()
    # Re-implementation of src/models/load.py:load_model(model_type='clip') -- the original calls
    # model.to(rank) with rank=0, which means cuda:0 and fails on CPU-only machines.
    state = torch.load(ckpt, map_location=device, weights_only=False)
    cfg = state.get("config", {})
    model = OutfitCLIPTransformer(OutfitCLIPTransformerConfig(**cfg))
    sd = {k.replace("module.", ""): v for k, v in state["model"].items()}
    missing, unexpected = model.load_state_dict(sd, strict=False)
    model.to(device).eval()
    rec["load_s"] = round(time.perf_counter() - t0, 2)
    rec["rss_after_load_mb"] = mon.rss_mb()
    rec["missing_keys"] = len(missing)
    rec["unexpected_keys"] = len(unexpected)
    rec["config"] = {k: v for k, v in cfg.items()} if isinstance(cfg, dict) else str(cfg)
    rec["params"] = n_params(model)

    def item(i):
        r = rows[i]
        return FashionItem(item_id=i, image=imgs[i], category=r["category"], description=r["text"])

    outfits: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        outfits.setdefault(r["item_ID"].rsplit("_", 1)[0], []).append(i)
    real = [v for v in outfits.values() if len(v) >= 2]
    rng = random.Random(0)
    keys = list(outfits)
    mixed = []
    for s in real:  # same size, each item from a different outfit
        pool = rng.sample(keys, len(s))
        mixed.append([rng.choice(outfits[k]) for k in pool])
    sets = [("real_outfit", s) for s in real] + [("random_mix", s) for s in mixed]
    results = []
    with torch.inference_mode():
        model.predict_score([FashionCompatibilityQuery(outfit=[item(i) for i in real[0]])])  # warm-up
        for kind, s in sets:
            q = FashionCompatibilityQuery(outfit=[item(i) for i in s])
            sync(device)
            t = time.perf_counter()
            score = float(model.predict_score([q]).squeeze())
            sync(device)
            results.append(dict(kind=kind, items=[f"{rows[i]['item_ID']} | {rows[i]['category']}" for i in s],
                                score=round(score, 4),
                                ms=round((time.perf_counter() - t) * 1000, 1)))
    pos = [r["score"] for r in results if r["kind"] == "real_outfit"]
    negs = [r["score"] for r in results if r["kind"] == "random_mix"]
    auc = sum((p > n) + 0.5 * (p == n) for p in pos for n in negs) / (len(pos) * len(negs))
    rec["sanity"] = {
        "task": "compatibility score (sigmoid): every real outfit in the 48-row sample vs same-size random mixes",
        "n_real": len(pos), "n_random_mix": len(negs), "AUC_real_vs_mix": round(auc, 4),
        "sets": results,
        "mean_real": round(sum(r["score"] for r in results if r["kind"] == "real_outfit") / len(real), 4),
        "mean_random_mix": round(sum(r["score"] for r in results if r["kind"] == "random_mix") / len(mixed), 4),
    }
    rec["ms_per_set"] = round(sum(r["ms"] for r in results) / len(results), 1)
    del model
    gc.collect()


# --------------------------------------------------------------------------------------
# worker / driver
# --------------------------------------------------------------------------------------
def worker(name: str, device: str, out: Path, budget_s: float):
    import torch
    spec = get_spec(name)
    rec = dict(name=name, repo=spec["repo"], kind=spec["kind"], licence=spec["licence"],
               device=device, status="failed")
    if spec.get("notes"):
        rec["notes"] = spec["notes"]
    mon = PeakRSS().start()
    t_all = time.perf_counter()
    try:
        if device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        if spec.get("gpu_only") and device != "cuda":
            card_only_record(name, spec, rec)
            rec["status"] = "gpu_only_untested"
        else:
            if spec["kind"] == "embedding":
                run_embedding(name, spec, device, rec, mon)
            elif spec["kind"] == "reranker":
                run_reranker(name, spec, device, rec, mon, budget_s)
            elif spec["kind"] == "llm":
                run_llm(name, spec, device, rec, mon)
            elif spec["kind"] == "compat":
                run_compat(name, spec, device, rec, mon)
            if rec["status"] == "failed":
                rec["status"] = "ok"
                san = rec.get("sanity") or {}
                # a model that loads but scores at/below chance is broken (e.g. weights silently not loaded)
                if ("random_MRR" in san and san["MRR"] <= san["random_MRR"]) or                         ("random_R@5" in san and san["R@5"] <= san["random_R@5"]):
                    rec["status"] = "failed_sanity"
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"[:1500]
        rec["traceback"] = traceback.format_exc()[-3000:]
    finally:
        mon.stop()
        rec["peak_rss_mb"] = mon.peak_mb()
        if device == "cuda":
            rec["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
        rec["wall_s"] = round(time.perf_counter() - t_all, 1)
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")


def env_info(device):
    import psutil
    import torch
    import transformers
    info = dict(date=time.strftime("%Y-%m-%d %H:%M:%S"), device=device, python=platform.python_version(),
                torch=torch.__version__, transformers=transformers.__version__,
                cpu=platform.processor(), cpu_threads=psutil.cpu_count(),
                ram_gb=round(psutil.virtual_memory().total / 2**30, 1), torch_threads=torch.get_num_threads())
    for mod in ("open_clip", "sentence_transformers"):
        try:
            info[mod] = __import__(mod).__version__
        except Exception:
            pass
    if device == "cuda":
        info["gpu"] = torch.cuda.get_device_name(0)
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="all", help="all | comma-separated names: " + ",".join(REGISTRY))
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--out", default=None, help="default reports/model_verification_<device>.json")
    ap.add_argument("--rerank-budget-s", type=float, default=None,
                    help="if 8 queries x 48 docs is projected slower than this, use 8 docs/query "
                         "(default 900 on cpu, unlimited on cuda)")
    ap.add_argument("--timeout-s", type=float, default=5400, help="per-model subprocess timeout")
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--worker-out", help=argparse.SUPPRESS)
    args = ap.parse_args()

    device = pick_device(args.device)
    budget = args.rerank_budget_s if args.rerank_budget_s is not None else (900 if device == "cpu" else 1e12)
    if args.worker:
        worker(args.worker, device, Path(args.worker_out), budget)
        return

    if args.models == "all":
        names = [n for n, s in REGISTRY.items() if not s.get("only_explicit")]
    else:
        names = [n.strip() for n in args.models.split(",") if n.strip()]
        bad = [n for n in names if not has_spec(n)]
        if bad:
            ap.error(f"unknown models {bad}; choose from {list(REGISTRY)}")

    out = Path(args.out) if args.out else ROOT / "reports" / f"model_verification_{device}.json"
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"models": {}}

    rows = prepare_sample()  # stream once before any model runs
    report["env"] = env_info(device)
    report["sample"] = dict(source="Marqo/polyvore first 48 rows", cache=str(SAMPLE_DIR), n=len(rows),
                            rerank_queries=[dict(item=rows[i]["item_ID"], query=q) for i, q in rerank_queries(rows)])

    queue = list(names)
    while queue:
        name = queue.pop(0)
        tmp = out.parent / f".worker_{name}.json"
        tmp.unlink(missing_ok=True)
        print(f"[{time.strftime('%H:%M:%S')}] {name} ...", flush=True)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", name, "--worker-out", str(tmp),
               "--device", device, "--rerank-budget-s", str(budget)]
        try:
            proc = subprocess.run(cmd, timeout=args.timeout_s, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            if tmp.exists():
                rec = json.loads(tmp.read_text(encoding="utf-8"))
            else:
                rec = dict(name=name, repo=get_spec(name)["repo"], status="failed",
                           error=f"worker exited {proc.returncode} without result",
                           stderr_tail=proc.stderr[-2000:])
        except subprocess.TimeoutExpired:
            rec = dict(name=name, repo=get_spec(name)["repo"], status="failed",
                       error=f"timeout after {args.timeout_s}s")
        tmp.unlink(missing_ok=True)
        report["models"][name] = rec
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        brief = {k: rec.get(k) for k in ("status", "load_s", "peak_rss_mb", "error")}
        s = rec.get("sanity") or {}
        brief.update({k: s[k] for k in ("R@1", "R@5", "MRR", "mean_real", "mean_random_mix") if k in s})
        print("   ", json.dumps(brief, ensure_ascii=False)[:600], flush=True)
        fb = get_spec(name).get("fallback_model")
        if rec.get("status") != "ok" and fb and fb not in names:
            print(f"    {name} failed -> trying fallback {fb}", flush=True)
            queue.insert(0, fb)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
