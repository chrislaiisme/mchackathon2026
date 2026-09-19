"""Catalog loading. Schema produced by scripts/prepare_catalog.py:

item_id, title, description, category, subcategory, color, season, occasion, gender,
price, currency, outfit_ids, image_path, source, attr_source
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

TEXT_FIELDS = ("title", "description", "subcategory", "color")
ATTR_FIELDS = ("category", "subcategory", "color", "season", "occasion", "gender")


@dataclass
class Catalog:
    items: pd.DataFrame
    root: Path
    name: str = "catalog"
    _id_to_pos: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.items = self.items.reset_index(drop=True)
        for col in ("description", "category", "subcategory", "color", "season", "occasion", "gender", "price"):
            if col not in self.items.columns:
                self.items[col] = None
        self._id_to_pos = {str(i): p for p, i in enumerate(self.items["item_id"].astype(str))}

    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        path = Path(path)
        df = pd.read_parquet(path / "items.parquet")
        return cls(items=df, root=path, name=path.name)

    def __len__(self) -> int:
        return len(self.items)

    def pos(self, item_id: str) -> int | None:
        return self._id_to_pos.get(str(item_id))

    def positions(self, item_ids: list[str]) -> list[int]:
        return [p for p in (self.pos(i) for i in item_ids) if p is not None]

    def texts(self) -> list[str]:
        cols = [c for c in TEXT_FIELDS if c in self.items.columns]
        return (
            self.items[cols]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.strip()
            .tolist()
        )

    def image_paths(self) -> list[Path]:
        return [self.root / p for p in self.items["image_path"].astype(str)]

    def column(self, name: str) -> np.ndarray | None:
        """Positionally indexable numpy view of one column, materialised once.

        Building a card touches ~7 fields per item; `items.at[pos, name]` on an Arrow-backed frame
        costs more than the ranking maths it accompanies, and the columns never change once loaded.
        """
        cache = self.__dict__.setdefault("_col_cache", {})
        if name not in cache:
            cache[name] = self.items[name].to_numpy() if name in self.items.columns else None
        return cache[name]

    def attr(self, pos: int, name: str):
        col = self.column(name)
        v = col[pos] if col is not None else None
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            return None
        return v
