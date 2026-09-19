"""Item-level outfit compatibility with OutfitTransformer (owj0421 re-implementation, MIT code).

Category co-occurrence (compat.py) gives every item of the same category the same score, so it
cannot tell which top goes with the user's black jeans. This scorer rates the actual set
(anchor items + candidate) with the pretrained CLIP-based OutfitTransformer compatibility head.

Setup (third_party/ is gitignored):
  git clone https://github.com/owj0421/outfit-transformer third_party/outfit-transformer
  cd third_party/outfit-transformer && gdown 1mzNqGBmd8UjVJjKwVa5GdGYHKutZKSSi -O checkpoints.zip \
      && unzip checkpoints.zip -d checkpoints
Loading mirrors scripts/verify_models.py (the repo's load.py hard-codes cuda:0).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np

from .catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]
OT_DIR = ROOT / "third_party" / "outfit-transformer"


class OutfitTransformerCompat:
    name = "outfit-transformer"

    def __init__(self, catalog: Catalog, device: str = "auto", ot_dir: Path = OT_DIR, batch_size: int = 16):
        import torch
        from PIL import Image

        from .models import pick_device

        self.torch, self.Image = torch, Image
        self.catalog = catalog
        self.device = pick_device(device)
        self.batch_size = batch_size
        ckpts = [p for p in sorted((ot_dir / "checkpoints").rglob("*.pt*")) if "compat" in p.name.lower()]
        if not ckpts:
            raise FileNotFoundError(f"no compatibility checkpoint under {ot_dir}/checkpoints")
        sys.path.insert(0, str(ot_dir))
        try:
            import cv2  # noqa: F401
        except ImportError:
            sys.modules["cv2"] = types.ModuleType("cv2")  # imported but unused by the model code
        from src.data.datatypes import FashionCompatibilityQuery, FashionItem
        from src.models.outfit_clip_transformer import OutfitCLIPTransformer, OutfitCLIPTransformerConfig

        self.Query, self.Item = FashionCompatibilityQuery, FashionItem
        state = torch.load(ckpts[0], map_location=self.device, weights_only=False)
        model = OutfitCLIPTransformer(OutfitCLIPTransformerConfig(**state.get("config", {})))
        model.load_state_dict({k.replace("module.", ""): v for k, v in state["model"].items()}, strict=False)
        self.model = model.to(self.device).eval()
        self._cache: dict[int, object] = {}

    def _item(self, pos: int):
        if pos not in self._cache:
            row = self.catalog.items.iloc[pos]
            img = self.Image.open(self.catalog.image_paths()[pos]).convert("RGB")
            cat = row.get("subcategory") or row.get("category") or ""
            self._cache[pos] = self.Item(item_id=pos, image=img, category=str(cat), description=str(row["title"]))
        return self._cache[pos]

    def score(self, anchor_positions: list[int], cand_positions: list[int]) -> np.ndarray:
        anchors = [self._item(p) for p in anchor_positions]
        out = []
        with self.torch.inference_mode():
            for i in range(0, len(cand_positions), self.batch_size):
                qs = [self.Query(outfit=anchors + [self._item(p)]) for p in cand_positions[i : i + self.batch_size]]
                out.append(np.asarray(self.model.predict_score(qs).float().cpu()).reshape(-1))
        return np.concatenate(out) if out else np.zeros(0)
