"""切完之後自動檢查每一格：該變的有沒有變、不該變的有沒有被偷改。

兩層檢查，是故意分開的：

**第一層（一定會跑，零依賴）** 只看像素：背景乾不乾淨、格子是不是空的、剪影跟顏色
相對基準格差多少。它抓得到的是粗糙但致命的失敗——模型漏畫一格、白邊沒切乾淨、
六格其實長得一模一樣、說好只改顏色結果版型也跟著變。這層只用 Pillow 與 numpy，
任何一台機器都跑得起來，也就是說**它在 demo 現場一定能跑**。

**第二層（選配）** 才是語意檢查：把每格的圖跟每格的關鍵字都轉成向量，看哪一格最像
哪一段文字。它能回答第一層答不了的問題——「這格真的是格紋嗎」「第 3 格會不會其實是
第 5 格的敘述」。它需要 FashionCLIP 家族的 encoder（engine02 已經有），沒裝 torch
的機器會被明確告知跳過，不會假裝有跑。

刻意不誇大第一層能做什麼：像素檢查看不出「口袋有沒有被偷改」這種細節，那要靠第二層
或人眼。FR-010 要的「選項圖檢查通過率」兩層都要報，不要只報好看的那個。

用法：
  python agent/scripts/check_cells.py --manifest data/generated/<sid>/r1/manifest.json
  python agent/scripts/check_cells.py --manifest ... --encoder marqo-fashionSigLIP
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grid_common import ROOT  # noqa: E402

# 背景是中灰的無縫背景，衣服比它暗或比它亮都算「內容」。門檻對著 2026-09-19 的實測圖調，
# 那張的背景大約 150–160 灰階，衣服主體在 90–130 之間。
BG_TOLERANCE = 18.0      # 跟四角估出來的背景色差這麼多以內，算背景
MIN_CONTENT = 0.05       # 內容佔比低於這個 → 這格大概是空的
MAX_CONTENT = 0.92       # 高於這個 → 沒有背景，可能是滿版誤切
MAX_STRAY_WHITE = 0.02   # 格內殘留的純白比例（白邊沒修乾淨）

# 「該動的有沒有動」的門檻。這些數字是拿 2026-09-19 的實測圖量出來的，不是憑感覺定的
# （evals/choice_images/，六格牛仔褲，基準格 + 五個單變因）：
#
#   格 | 變因              | 受光面 | 中間調 | 剪影差
#   ---|-------------------|-------|-------|-------
#    2 | fit（低腰）        |   0.8 |   4.9 | 0.0620
#    3 | fit（窄直筒）      |   3.4 |   4.0 | 0.1044
#    4 | colors（ecru 米白）| 133.6 | 119.5 | 0.0839
#    5 | length（九分）     |   4.7 |   3.3 | 0.0773
#    6 | construction（鬚邊）|   0.4 |   1.9 | 0.0344
#
# 另外兩組（同樣在 evals/choice_images/）專門用來找兩個色距統計量的盲區：
#
#   資料組                     | 期望 | 受光面   | 中間調
#   ---------------------------|-----|---------|--------
#   裙子六格（同一塊米白布）      | 低   | 1.1–3.3 | 17–30    ← 中間調被陰影比例帶著跑
#   牛仔褲六水洗（藍/深藍/黑/米白/淺藍/灰）| 高 | 1.0–142 | 42–153  ← 受光面把深色全壓在一起
#
# 兩個統計量的盲區不重疊，所以不二選一：
# 1. 顏色改動的辨識度極高（133.6 對上其他格的 ≤4.9），門檻放 12 兩邊都有很大餘裕。
# 2. **鬚邊那格的剪影只差 0.0344**，比任何真正的版型改動都小。局部工藝細節（下襬做法、
#    車線、口袋）本來就不會改變整體剪影——這不是門檻要調低，是像素層看不到這種東西。
#    硬把門檻壓到 0.03 只會讓它跟雜訊分不開，所以這類屬性改成「不判定」，明講要靠
#    語意層或人眼。誠實地說「我看不出來」比給一個假的通過率有用。
COLOR_AXES = {"colors", "pattern", "material"}          # 期待顏色／紋理變、剪影不變
SHAPE_AXES = {"fit", "length", "collar", "neckline", "sleeve_length"}
DETAIL_AXES = {"construction", "hem", "stitching", "pocket"}   # 像素層不判定，只報數字
MIN_COLOR_DELTA = 12.0   # 顏色軸：跟基準的平均色距至少要這麼大
MAX_COLOR_DELTA = 12.0   # 形狀軸：色距不該超過這麼多（超過就是順手改了顏色）
MIN_SHAPE_DELTA = 0.04   # 形狀軸：剪影差異至少要這麼大
MIN_PAIR_DISTINCT = 0.02 # 概念圖：任兩格至少要有這麼多差異，否則就是生了重複的格子


def _load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def _metrics(rgb: np.ndarray) -> dict[str, Any]:
    """一格的像素層指標。全部都不需要任何模型。"""
    h, w, _ = rgb.shape
    # 背景色用四角估：商品照的四個角一定是背景，不會是衣服。
    k = max(4, min(h, w) // 20)
    corners = np.concatenate([rgb[:k, :k].reshape(-1, 3), rgb[:k, -k:].reshape(-1, 3),
                              rgb[-k:, :k].reshape(-1, 3), rgb[-k:, -k:].reshape(-1, 3)])
    bg = corners.mean(axis=0)
    dist = np.linalg.norm(rgb - bg, axis=2)
    content = dist > BG_TOLERANCE
    ratio = float(content.mean())

    out: dict[str, Any] = {
        "background_rgb": [round(float(v), 1) for v in bg],
        "content_ratio": round(ratio, 4),
        "stray_white_ratio": round(float((rgb.min(axis=2) > 245).mean()), 4),
    }
    content_px = rgb[content]
    if ratio < MIN_CONTENT or len(content_px) == 0:
        out |= {"lit_rgb": None, "mid_rgb": None, "silhouette": None}
        return out
    # 布料本色算兩個統計量，因為單一個都有盲區（實測數字見檔案開頭的表）：
    #   受光面（最亮 25%）：對剪影面積與陰影量免疫，但深色系會塌在一起
    #                      ——深藍、黑、灰的高光都是差不多的淺灰。
    #   中間調（40–70%）  ：深淺分得開，但會被陰影比例帶著跑，同色不同剪影就誤判。
    # 兩者的盲區不重疊，所以後面「該變的」取大、「不該變的」取小。
    lum = content_px.mean(axis=1)
    lit = content_px[lum >= np.percentile(lum, 75)]
    mid = content_px[(lum >= np.percentile(lum, 40)) & (lum <= np.percentile(lum, 70))]
    out["lit_rgb"] = [round(float(v), 1) for v in lit.mean(axis=0)]
    out["mid_rgb"] = [round(float(v), 1) for v in (mid if len(mid) else lit).mean(axis=0)]
    # 剪影：把內容遮罩沿 x 與 y 投影並正規化，變成跟解析度無關的形狀描述子，
    # 這樣不同尺寸的格子也能互相比較。
    prof_x = content.mean(axis=0)
    prof_y = content.mean(axis=1)
    out["silhouette"] = {
        "x": np.interp(np.linspace(0, 1, 64), np.linspace(0, 1, len(prof_x)), prof_x).round(4).tolist(),
        "y": np.interp(np.linspace(0, 1, 64), np.linspace(0, 1, len(prof_y)), prof_y).round(4).tolist(),
    }
    return out


def _color_deltas(a: dict, b: dict) -> tuple[Optional[float], Optional[float]]:
    """兩格布料本色的距離，(受光面, 中間調) 各一個。"""
    out = []
    for key in ("lit_rgb", "mid_rgb"):
        if not a.get(key) or not b.get(key):
            out.append(None)
        else:
            out.append(round(float(np.linalg.norm(np.array(a[key]) - np.array(b[key]))), 2))
    return out[0], out[1]


def _changed_signal(deltas: tuple[Optional[float], Optional[float]]) -> Optional[float]:
    """「顏色有沒有變」取兩個統計量的**較大值**：任一個看到變化就算數。"""
    vals = [d for d in deltas if d is not None]
    return max(vals) if vals else None


def _held_signal(deltas: tuple[Optional[float], Optional[float]]) -> Optional[float]:
    """「顏色有沒有被偷改」取**較小值**：兩個都同意變了才判定被改到，避免剪影劇烈
    改變時誤報（同一塊布做成迷你裙跟長裙，中間調會差 30，受光面只差 1.1）。"""
    vals = [d for d in deltas if d is not None]
    return min(vals) if vals else None


def _shape_delta(a: dict, b: dict) -> Optional[float]:
    """兩格的剪影差距（投影曲線的平均絕對差）。"""
    if not a.get("silhouette") or not b.get("silhouette"):
        return None
    dx = np.abs(np.array(a["silhouette"]["x"]) - np.array(b["silhouette"]["x"])).mean()
    dy = np.abs(np.array(a["silhouette"]["y"]) - np.array(b["silhouette"]["y"])).mean()
    return round(float((dx + dy) / 2), 4)


def _semantic_check(man: dict, cells: list[dict], encoder_name: str) -> dict[str, Any]:
    """選配的語意層：用 FashionCLIP 家族的 encoder 做「圖 ↔ 文字」指派。

    為什麼要做指派而不只是算相似度：模型不保證照我們給的順序畫。真的畫反了的話，
    第 3 格的關鍵字會貼到第 5 格的圖上，ENGINE03 就會拿錯誤的屬性去調權重——
    這種錯不會有任何視覺徵兆，只有指派檢查抓得到。
    """
    try:
        from engine02.models import TorchEncoder
    except Exception as exc:
        return {"ran": False, "reason": f"沒有可用的 encoder（{type(exc).__name__}: {exc}）。"
                                        f"這層是選配，裝了 torch 與 open_clip 之後再跑。"}
    enc = TorchEncoder(encoder_name, device="auto")
    paths = [ROOT / c["image"] for c in cells]
    texts = []
    for c in cells:
        kw = c.get("keywords") or {}
        # 文字側只用這格自己的關鍵字，順序固定，才不會因為 dict 順序不同而分數飄。
        texts.append(", ".join(str(kw[k]) for k in sorted(kw)) or "garment")
    img = enc.encode_images(paths)
    txt = enc.encode_text(texts)
    sim = img @ txt.T                      # 兩邊都已 L2 normalise
    assigned = sim.argmax(axis=1)
    return {
        "ran": True, "encoder": enc.name,
        "diagonal": [round(float(sim[i, i]), 4) for i in range(len(cells))],
        "assigned_to": [int(a) + 1 for a in assigned],
        "assignment_ok": [bool(assigned[i] == i) for i in range(len(cells))],
        "pass_rate": round(float((assigned == np.arange(len(cells))).mean()), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--encoder", help="選配的語意檢查，例如 marqo-fashionSigLIP")
    ap.add_argument("--calibrate", action="store_true", help="只印原始指標，不判定通過與否")
    args = ap.parse_args()

    mpath = Path(args.manifest)
    man = json.loads(mpath.read_text(encoding="utf-8"))
    cells = man["cells"]
    if any(not c.get("image") for c in cells):
        raise SystemExit("manifest 裡有格子還沒切圖，先跑 slice_grid.py")

    metrics = [_metrics(_load(ROOT / c["image"] if not Path(c["image"]).is_absolute()
                              else Path(c["image"]))) for c in cells]

    # 基準格：選項圖模式的第 1 格若是未改動的基準就用它，否則拿第 1 格當參照點。
    base_idx = 0
    baseline_is_real = cells[0].get("varied_attribute") is None and man.get("mode") == "variants"

    failures: list[str] = []
    for i, (cell, m) in enumerate(zip(cells, metrics)):
        check: dict[str, Any] = {
            "content_ratio": m["content_ratio"], "stray_white_ratio": m["stray_white_ratio"],
            "lit_rgb": m["lit_rgb"], "mid_rgb": m["mid_rgb"],
            "empty_cell": m["content_ratio"] < MIN_CONTENT,
            "overflow": m["content_ratio"] > MAX_CONTENT,
            "clean_edges": m["stray_white_ratio"] <= MAX_STRAY_WHITE,
        }
        if check["empty_cell"]:
            failures.append(f"第 {cell['index']} 格幾乎是空的（內容佔比 {m['content_ratio']}）")
        if not check["clean_edges"]:
            failures.append(f"第 {cell['index']} 格殘留白邊（{m['stray_white_ratio']}）")

        if i != base_idx:
            deltas = _color_deltas(metrics[base_idx], m)
            cd_changed, cd_held = _changed_signal(deltas), _held_signal(deltas)
            sd = _shape_delta(metrics[base_idx], m)
            check |= {"color_delta_lit": deltas[0], "color_delta_mid": deltas[1],
                      "color_delta_vs_base": cd_changed, "shape_delta_vs_base": sd}
            axis = (cell.get("varied_attribute") or "").split(",")[0]
            # 「該動的有沒有動」只在有基準格可比的選項圖模式下判定；概念圖每格都在變，
            # 拿第 1 格當基準沒有意義，只報數字。
            if baseline_is_real and axis and not args.calibrate:
                if axis in COLOR_AXES:
                    check["varied_as_expected"] = bool(cd_changed and cd_changed >= MIN_COLOR_DELTA)
                    if not check["varied_as_expected"]:
                        failures.append(f"第 {cell['index']} 格說要改 {axis}，但顏色幾乎沒變"
                                        f"（受光面 {deltas[0]}、中間調 {deltas[1]}）")
                elif axis in DETAIL_AXES:
                    # 局部細節：只檢查「不該變的沒變」，該變的那項交給語意層或人眼。
                    check["varied_as_expected"] = None
                    check["pixel_layer_verdict"] = "局部細節，像素層無法判定，需語意層或人工確認"
                    check["others_held"] = bool(cd_held is not None and cd_held <= MAX_COLOR_DELTA)
                    if not check["others_held"]:
                        failures.append(f"第 {cell['index']} 格只該改 {axis}，顏色卻也變了（色距 {cd_held}）")
                elif axis in SHAPE_AXES:
                    ok_shape = bool(sd and sd >= MIN_SHAPE_DELTA)
                    ok_color = bool(cd_held is not None and cd_held <= MAX_COLOR_DELTA)
                    check["varied_as_expected"] = ok_shape
                    check["others_held"] = ok_color
                    if not ok_shape:
                        failures.append(f"第 {cell['index']} 格說要改 {axis}，但剪影幾乎沒變（{sd}）")
                    if not ok_color:
                        failures.append(f"第 {cell['index']} 格只該改 {axis}，顏色卻也變了（色距 {cd_held}）")
        cell["check"] = check

    # 概念圖：六格之間不能有兩格幾乎一樣，那等於白生一格。
    if man.get("mode") == "concepts" and not args.calibrate:
        for i, j in itertools.combinations(range(len(cells)), 2):
            sd = _shape_delta(metrics[i], metrics[j]) or 0.0
            cd = _changed_signal(_color_deltas(metrics[i], metrics[j])) or 0.0
            if sd < MIN_PAIR_DISTINCT and cd < MIN_COLOR_DELTA:
                failures.append(f"第 {cells[i]['index']} 格與第 {cells[j]['index']} 格幾乎一樣"
                                f"（剪影差 {sd}、色距 {cd}）")

    report: dict[str, Any] = {
        "pixel": {"ran": True, "failures": failures,
                  "pass_rate": round(1 - len(failures) / max(len(cells), 1), 4)},
    }
    if args.encoder:
        report["semantic"] = _semantic_check(man, cells, args.encoder)
    man["checks"] = report
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"mode": man.get("mode"), "cells": len(cells), **report,
                      "per_cell": [{"index": c["index"], "varied": c.get("varied_attribute"),
                                    "color_delta": c["check"].get("color_delta_vs_base"),
                                    "shape_delta": c["check"].get("shape_delta_vs_base")}
                                   for c in cells]},
                     ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
