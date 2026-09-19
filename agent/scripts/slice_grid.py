"""把六宮格切成六張單品卡片。

切法不信任「等分」。生圖模型排版會飄，硬照 1/3、2/3 切遲早切到衣服；所以改成
**先偵測真正的 gutter 在哪裡**：gutter 是純白色的帶狀區域，整欄（整列）的亮度高、
變異小，而格子裡是灰底加深色衣服，變異大。沿 x、y 做投影就能把它們找出來。

2026-09-19 的實測（evals/choice_images/）：偵測到的三條切線分別落在 0.333、0.666、
0.498，跟理論值誤差 ≤0.2%，六格 auto-trim 之後尺寸全等（414×581）。那一次等分硬切
其實也會過，但偵測是零成本的保險，而且它會順便告訴我們「這張圖的版面跟要求的不一樣」
——那種圖不該拿去用，該重生。

用法：
  python agent/scripts/slice_grid.py --manifest data/generated/<sid>/r1/manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grid_common import ROOT  # noqa: E402

# gutter 的共通判準：整條「平」（逐行標準差很小），因為 gutter 是純色帶，格子裡是衣服。
FLAT_STD = 6.0
# 亮極性（舊版面：中灰底 ＋ 純白 gutter）用的亮度門檻。
WHITE_MEAN = 245.0
# 暗極性（現行版面：白底 ＋ 中灰 gutter）用的判準：整條都沒有白點。
# 衣服那一欄一定含得到白底，gutter 不會——單看平均亮度會被深色衣服騙走。
NO_WHITE_MAX = 200.0
# 切線位置容許的偏差。超過就代表模型沒照版面畫，這張圖不要硬切。
POSITION_TOLERANCE = 0.06


def _runs(mask: np.ndarray) -> list[tuple[int, int, int]]:
    """連續 True 的帶：(起, 迄, 寬)。"""
    bands, start = [], None
    for i, flag in enumerate(mask):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            bands.append((start, i - 1, i - start))
            start = None
    if start is not None:
        bands.append((start, len(mask) - 1, len(mask) - start))
    return bands


def _bands_bright(mean, std, mx) -> list[tuple[int, int, int]]:
    """亮極性：亮且平。舊版面（中灰底 ＋ 純白 gutter）。"""
    return _runs((mean > WHITE_MEAN) & (std < FLAT_STD))


def _bands_dark(mean, std, mx) -> list[tuple[int, int, int]]:
    """暗極性：整條沒有白點且平。現行版面（白底 ＋ 中灰 gutter）。"""
    return _runs((mx < NO_WHITE_MAX) & (std < FLAT_STD))


# 兩種版面都要切得動，而且不必事先知道是哪一種：兩個極性都跑，取切線數量對、
# 位置誤差小的那一組。猜錯的極性通常連數量都湊不齊，分不出來時比總誤差。
POLARITIES = (("dark", _bands_dark), ("bright", _bands_bright))


def _cuts(bands: list[tuple[int, int, int]], size: int, n_cells: int) -> list[int]:
    """從白帶裡挑出 n_cells-1 條內部切線的座標（取白帶中點）。

    邊框的白邊要排除（圖的最外圈常常也是白的），所以只看 5%~95% 之間的帶；
    剩下的取最寬的幾條——真正的 gutter 一定比雜訊寬。
    """
    inner = [b for b in bands if b[0] > size * 0.05 and b[1] < size * 0.95]
    inner.sort(key=lambda b: -b[2])
    chosen = sorted(inner[: n_cells - 1])
    return [(s + e) // 2 for s, e, _ in chosen]


def _check_positions(cuts: list[int], size: int, n_cells: int) -> list[dict[str, Any]]:
    """切線該落在等分點附近。偏太多就是模型沒照版面畫。"""
    report = []
    for i, cut in enumerate(cuts, start=1):
        got, want = cut / size, i / n_cells
        report.append({"index": i, "at": round(got, 4), "expected": round(want, 4),
                       "off": round(abs(got - want), 4), "ok": abs(got - want) <= POSITION_TOLERANCE})
    return report


def _trim(arr: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    """把一格外圍殘留的 gutter 與留白修掉，只留有內容的範圍。

    切線取的是 gutter 中點，所以每格邊緣一定帶著半條 gutter；不修掉的話六張卡片的
    留白會不一致，前端並排時看起來就歪。

    判準是「不是白的**而且有變化**」兩個條件同時成立。只用第一個不夠：現行版面的
    gutter 是中灰色，它同樣不是白的，只看亮度會把那半條灰邊留在卡片上（舊版面的
    gutter 是純白，剛好被亮度那一關擋掉，所以這個洞一直沒浮現）。gutter 是純色、
    逐行標準差接近 0，衣服那幾行則是白底加深色布料、變化很大，用 FLAT_STD 分得開。
    """
    sub = arr[y0:y1, x0:x1]
    cols = np.where((sub.mean(axis=0) < WHITE_MEAN) & (sub.std(axis=0) >= FLAT_STD))[0]
    rows = np.where((sub.mean(axis=1) < WHITE_MEAN) & (sub.std(axis=1) >= FLAT_STD))[0]
    if len(cols) == 0 or len(rows) == 0:      # 整格都是白的：模型漏畫了這格
        return x0, y0, x1, y1
    return x0 + int(cols[0]), y0 + int(rows[0]), x0 + int(cols[-1]) + 1, y0 + int(rows[-1]) + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--grid", help="預設讀 manifest 裡的 grid_image")
    ap.add_argument("--force", action="store_true", help="版面對不上也照切（除錯用）")
    args = ap.parse_args()

    mpath = Path(args.manifest)
    man = json.loads(mpath.read_text(encoding="utf-8"))
    # manifest 有兩種形狀：舊的 generate_grid.py 寫 grid_image/cols/rows（相對 ROOT），
    # skill 寫 image_path 與巢狀的 grid.cols/grid.rows。兩種都收，免得多一層轉檔。
    grid_field = man.get("grid_image") or man.get("image_path")
    if args.grid:
        grid_path = Path(args.grid)
    else:
        grid_path = Path(grid_field)
        if not grid_path.is_absolute():
            grid_path = ROOT / grid_path
    grid = man.get("grid") if isinstance(man.get("grid"), dict) else man
    cols, rows = grid["cols"], grid["rows"]

    grey = np.asarray(Image.open(grid_path).convert("L"), dtype=np.float32)
    H, W = grey.shape

    best = None
    for name, finder in POLARITIES:
        vc = _cuts(finder(grey.mean(axis=0), grey.std(axis=0), grey.max(axis=0)), W, cols)
        hc = _cuts(finder(grey.mean(axis=1), grey.std(axis=1), grey.max(axis=1)), H, rows)
        vr, hr = _check_positions(vc, W, cols), _check_positions(hc, H, rows)
        complete = len(vc) == cols - 1 and len(hc) == rows - 1
        err = sum(r["off"] for r in vr + hr) if (vr or hr) else 9e9
        score = (complete, all(r["ok"] for r in vr + hr) if (vr or hr) else False, -err)
        if best is None or score > best[0]:
            best = (score, name, vc, hc, vr, hr)
    _, polarity, vcuts, hcuts, vreport, hreport = best
    detected_ok = (len(vcuts) == cols - 1 and len(hcuts) == rows - 1
                   and all(r["ok"] for r in vreport + hreport))
    if not detected_ok and not args.force:
        man["slicing"] = {"ok": False, "method": "detected", "polarity": polarity, "canvas": [W, H],
                          "columns": vreport, "rows": hreport,
                          "reason": f"偵測到 {len(vcuts)+1} 欄 × {len(hcuts)+1} 列，"
                                    f"要求的是 {cols} 欄 × {rows} 列"}
        mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(f"版面跟要求的對不上（{man['slicing']['reason']}），這張不要用，重生一張。"
                         f"\n細節已寫進 {mpath}")

    xs = [0] + vcuts + [W]
    ys = [0] + hcuts + [H]
    src = Image.open(grid_path).convert("RGB")
    out_dir = grid_path.parent / "cells"
    out_dir.mkdir(exist_ok=True)

    sizes = []
    for cell in man["cells"]:
        idx = cell["index"] - 1           # manifest 是 1 起算，row-major
        r, c = divmod(idx, cols)
        bbox = _trim(grey, xs[c], ys[r], xs[c + 1], ys[r + 1])
        path = out_dir / f"cell_{cell['index']}.png"
        src.crop(bbox).save(path)
        cell["bbox"] = list(bbox)
        cell["image"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))

    # 六格尺寸應該幾乎一樣。差太多代表某格的衣服被切到，或模型某格畫得特別大。
    widths = [w for w, _ in sizes]
    heights = [h for _, h in sizes]
    spread = max(max(widths) / min(widths), max(heights) / min(heights)) - 1
    man["slicing"] = {"ok": True, "method": "detected" if detected_ok else "forced", "polarity": polarity,
                      "canvas": [W, H], "columns": vreport, "rows": hreport,
                      "cell_sizes": sizes, "size_spread": round(spread, 4),
                      "size_spread_ok": spread <= 0.05}
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"canvas": [W, H], "cells": len(man["cells"]), "out": str(out_dir),
                      "size_spread": round(spread, 4)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
