"""Real model wrappers. Loading code mirrors what scripts/verify_models.py verified on
CPU (reports/model_verification.md); `device="auto"` picks CUDA when available.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .catalog import Catalog
from .encoders import l2n

EMBEDDERS = {
    # name: (repo, backend)
    "fashion-clip": ("patrickjohncyh/fashion-clip", "hf_clip"),
    "marqo-fashionCLIP": ("Marqo/marqo-fashionCLIP", "open_clip"),
    "marqo-fashionSigLIP": ("Marqo/marqo-fashionSigLIP", "open_clip"),
    "zooclaw-fashionsiglip2": ("srpone/zooclaw-fashionsiglip2", "hf_siglip"),
    "siglip2-base-patch16-224": ("google/siglip2-base-patch16-224", "hf_siglip"),
    "clip-vit-base-patch32": ("openai/clip-vit-base-patch32", "hf_clip"),
    "laion-CLIP-ViT-B-16": ("laion/CLIP-ViT-B-16-laion2B-s34B-b88K", "open_clip"),
}

RERANKERS = {
    # name: (repo, modality, dtype, prompt)
    "bge-reranker-v2-m3": ("BAAI/bge-reranker-v2-m3", "text", None, None),
    "Qwen3-Reranker-0.6B": ("Qwen/Qwen3-Reranker-0.6B", "text", "bfloat16", None),
    "Qwen3-VL-Reranker-2B": ("Qwen/Qwen3-VL-Reranker-2B", "image", "bfloat16",
                             "Retrieve images or text relevant to the user's query."),
    "Qwen3-VL-Reranker-8B": ("Qwen/Qwen3-VL-Reranker-8B", "image", "bfloat16",
                             "Retrieve images or text relevant to the user's query."),
}


def pick_device(device: str = "auto") -> str:
    import torch

    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device


def _pooled(x):
    import torch

    return x if isinstance(x, torch.Tensor) else x.pooler_output


class TorchEncoder:
    def __init__(self, name: str, device: str = "auto", batch_size: int = 32):
        import torch

        repo, backend = EMBEDDERS[name]
        self.name, self.repo, self.backend = name, repo, backend
        self.device = pick_device(device)
        self.batch_size = batch_size
        self.torch = torch
        if backend == "open_clip":
            import open_clip

            self.model, _, self.preprocess = open_clip.create_model_and_transforms(f"hf-hub:{repo}")
            self.tok = open_clip.get_tokenizer(f"hf-hub:{repo}")
        else:
            from transformers import AutoModel, AutoProcessor

            self.model = AutoModel.from_pretrained(repo)
            self.proc = AutoProcessor.from_pretrained(repo)
        self.model = self.model.to(self.device).eval()
        self.dim = int(self.encode_text(["probe"]).shape[1])

    def _txt(self, texts: list[str]):
        if self.backend == "open_clip":
            return self.model.encode_text(self.tok(texts).to(self.device))
        if self.backend == "hf_siglip":
            # SigLIP/SigLIP2 were trained on lowercased text with max_length padding (64)
            texts = [t.lower() for t in texts]
            inp = self.proc(text=texts, padding="max_length", max_length=64, truncation=True, return_tensors="pt")
            return _pooled(self.model.get_text_features(**inp.to(self.device)))
        # CLIP has 77 learned text positions, but some model cards ship a tokenizer whose
        # model_max_length is larger (512), so truncation=True alone lets a long query through and
        # the forward pass dies on the position embedding. Pin the real limit.
        limit = min(77, getattr(self.model.config, "text_config", self.model.config).max_position_embeddings or 77)
        inp = self.proc(text=texts, padding="max_length", max_length=limit, truncation=True,
                        return_tensors="pt").to(self.device)
        return _pooled(self.model.get_text_features(input_ids=inp["input_ids"], attention_mask=inp["attention_mask"]))

    def _img(self, images):
        if self.backend == "open_clip":
            x = self.torch.stack([self.preprocess(i) for i in images]).to(self.device)
            return self.model.encode_image(x)
        inp = self.proc(images=images, return_tensors="pt").to(self.device)
        if self.backend == "hf_siglip":
            return _pooled(self.model.get_image_features(**inp))
        return _pooled(self.model.get_image_features(pixel_values=inp["pixel_values"]))

    def encode_text(self, texts: list[str]) -> np.ndarray:
        out = []
        with self.torch.inference_mode():
            for i in range(0, len(texts), self.batch_size):
                out.append(self._txt(texts[i : i + self.batch_size]).float().cpu().numpy())
        return l2n(np.concatenate(out)) if out else np.zeros((0, getattr(self, "dim", 0)), np.float32)

    def encode_images(self, paths: list[Path]) -> np.ndarray:
        from PIL import Image

        out = []
        with self.torch.inference_mode():
            for i in range(0, len(paths), self.batch_size):
                imgs = [Image.open(p).convert("RGB") for p in paths[i : i + self.batch_size]]
                out.append(self._img(imgs).float().cpu().numpy())
        return l2n(np.concatenate(out)) if out else np.zeros((0, self.dim), np.float32)


class CrossEncoderReranker:
    """sentence-transformers CrossEncoder; image rerankers take absolute image paths as docs."""

    def __init__(self, name: str, catalog: Catalog, device: str = "auto", batch_size: int = 8):
        import torch
        from sentence_transformers import CrossEncoder

        repo, self.modality, dtype, self.prompt = RERANKERS[name]
        self.name = name
        self.catalog = catalog
        kw = {"model_kwargs": {"dtype": getattr(torch, dtype)}} if dtype else {}
        self.model = CrossEncoder(repo, device=pick_device(device), **kw)
        self.batch_size = batch_size
        self._texts = catalog.texts()
        self._paths = [str(p.resolve()).replace("\\", "/") for p in catalog.image_paths()]

    def score(self, query: str, item_positions: list[int]) -> np.ndarray:
        docs = self._paths if self.modality == "image" else self._texts
        pairs = [(query, docs[p]) for p in item_positions]
        kw = {"prompt": self.prompt} if self.prompt else {}
        return np.asarray(self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False, **kw),
                          dtype=np.float64)
