"""從 Pinterest 圖版抽出主色盤，當成生圖的顏色軸。

這是 Pinterest 在這條線上的**實際**用途。docs/pinterest-and-generation.md 講得很清楚：
Pinterest 是趨勢訊號，原圖只在內部用，絕對不能出現在 demo 或簡報畫面上（版權）。
所以這裡不把參考圖餵給生圖模型做 image-to-image，只從它們身上取一件抽象的東西——
色盤——再用文字送進 prompt。產出的圖是全新的，跟任何一張原圖都沒有像素關係。

色盤存成 JSON 資料檔（`data/pinterest_trends/palette.json`，已被 gitignore），
不寫死在程式裡：換一個圖版就換一組趨勢色，那是資料的變動，不該改程式。

用法：
  export PINTEREST_ACCESS_TOKEN=...                 # 只用來下載，不會寫進任何檔案
  python agent/scripts/pinterest_palette.py --board <board_id> [--board <board_id>]
  python agent/scripts/pinterest_palette.py --from-disk          # 已經下載過就不用 token
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TRENDS = ROOT / "data" / "pinterest_trends"

# 服裝業講得出口的顏色名。生圖模型吃文字不吃 hex（實測 hex 常常被忽略），
# 所以抽出來的色格要對應回一個「人會講的顏色」。刻意只放中性與低彩度的名字——
# 這個圖版本身就是這個調性，硬塞飽和色名進去只會讓對應變得不準。
NAMED: dict[str, tuple[int, int, int]] = {
    "off-white": (238, 235, 228), "cream": (245, 240, 225), "sand beige": (214, 199, 175),
    "light grey": (200, 200, 200), "mid grey": (145, 145, 145), "charcoal": (70, 70, 70),
    "black": (30, 30, 30), "khaki": (176, 176, 144), "olive": (112, 112, 80),
    "warm taupe": (144, 112, 112), "mocha brown": (112, 80, 80), "navy": (45, 55, 85),
}


def fetch(board_ids: list[str], token: str) -> int:
    """把圖版上的 pin 圖下載到 data/pinterest_trends/（gitignore 過，不進版控）。"""
    TRENDS.mkdir(parents=True, exist_ok=True)
    n = 0
    for board in board_ids:
        req = urllib.request.Request(
            f"https://api.pinterest.com/v5/boards/{board}/pins?page_size=100",
            headers={"Authorization": f"Bearer {token}"})
        for pin in json.load(urllib.request.urlopen(req)).get("items", []):
            imgs = ((pin.get("media") or {}).get("images") or {})
            if not imgs:
                continue
            best = max(imgs, key=lambda k: imgs[k].get("width", 0))
            dst = TRENDS / f"{pin['id']}.jpg"
            if not dst.exists():
                urllib.request.urlretrieve(imgs[best]["url"], dst)
            n += 1
    return n


def palette(top_n: int = 6) -> list[dict]:
    """統計所有參考圖的主色，對應回顏色名。

    丟掉過亮與過暗的像素：那多半是背景、死白的牆與陰影，不是衣服的顏色。
    量化成粗色格再統計，避免同一件衣服的明暗變化被當成好幾種顏色。
    """
    counts: Counter = Counter()
    files = sorted(TRENDS.glob("*.jpg"))
    if not files:
        raise SystemExit(f"{TRENDS} 沒有圖，先用 --board 下載")
    for path in files:
        arr = np.asarray(Image.open(path).convert("RGB").resize((64, 64)), dtype=np.float32)
        arr = arr.reshape(-1, 3)
        lum = arr.mean(axis=1)
        arr = arr[(lum > 28) & (lum < 240)]
        if not len(arr):
            continue
        for px in (arr // 32 * 32 + 16).astype(int):
            counts[tuple(px)] += 1

    total = sum(counts.values())
    names = np.array(list(NAMED.values()), dtype=np.float32)
    labels = list(NAMED)
    # 一個顏色名可能被好幾個色格對到，合併起來算佔比，取佔比最高的前 top_n 個。
    merged: Counter = Counter()
    for rgb, n in counts.items():
        idx = int(np.linalg.norm(names - np.array(rgb, dtype=np.float32), axis=1).argmin())
        merged[labels[idx]] += n
    return [{"name": name, "share": round(n / total, 4)}
            for name, n in merged.most_common(top_n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", action="append", default=[], help="Pinterest board id，可給多個")
    ap.add_argument("--from-disk", action="store_true", help="不下載，直接用既有的圖")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--out", default=str(TRENDS / "palette.json"))
    args = ap.parse_args()

    if args.board and not args.from_disk:
        token = os.environ.get("PINTEREST_ACCESS_TOKEN")
        if not token:
            raise SystemExit("需要 PINTEREST_ACCESS_TOKEN（見 .env.example），或改用 --from-disk")
        print(f"下載 {fetch(args.board, token)} 張參考圖")

    colors = palette(args.top)
    out = Path(args.out)
    out.write_text(json.dumps({"source": "pinterest", "boards": args.board,
                               "n_reference_images": len(list(TRENDS.glob('*.jpg'))),
                               "colors": colors}, ensure_ascii=False, indent=2), encoding="utf-8")
    for c in colors:
        print(f"  {c['name']:12} {c['share']*100:5.1f}%")
    print(f"寫出 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
