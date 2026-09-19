"""呼叫 Hermes 的 image_gen plugin 生一張圖。**這支要用 Hermes 自己的 venv 跑**。

為什麼獨立成一支、而不是寫在 generate_grid.py 裡：Hermes 的 plugin 住在它自己的
虛擬環境（`~/.hermes/hermes-agent/venv`），而 prompt 的組裝要 import 專案的 engine02
（在專案 venv 裡）。兩邊的依賴沒有交集，硬湊在同一個直譯器裡遲早出事，所以照
ENGINE01 shell out 給 `codex exec` 的同一套做法：跨行程呼叫，介面是 stdout 的 JSON。

為什麼直接打 provider、不走 `hermes -z` 對話模式：對話模式是讓模型自己決定要不要呼叫
生圖工具，它可能改寫 prompt、可能乾脆不生。選項圖的單變因禁不起這種不確定性，所以
繞過對話層，直接叫 provider。

認證走 ChatGPT/Codex 訂閱的 OAuth（`hermes auth` 設定過一次即可），不需要
OPENAI_API_KEY——這跟 ENGINE01 用 `codex login` 吃訂閱額度是同一個邏輯，見 CLAUDE.md。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Hermes 的程式碼樹。不寫死絕對路徑（agent/README.md 的規則），從 HOME 推。
HERMES_DIR = Path(os.environ.get("HERMES_AGENT_DIR") or (Path.home() / ".hermes" / "hermes-agent"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    # quality 是綁在 model id 上的（gpt-image-2-low / -medium / -high 是同一個 API 模型的
    # 三個 quality 檔位），provider 只認 OPENAI_IMAGE_MODEL 這個環境變數，不吃參數。
    ap.add_argument("--model", default=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2-low"))
    # 注意：這個值送得出去，但 gpt-image-2 走 OpenAI namespace 時**尺寸是模型自己推的**，
    # 實測要 portrait(1024x1536) 拿回 1312x1199。所以這裡只是表態，不是保證。
    ap.add_argument("--aspect", default="portrait")
    args = ap.parse_args()

    sys.path.insert(0, str(HERMES_DIR))
    os.environ["OPENAI_IMAGE_MODEL"] = args.model
    try:
        from tools.image_generation_tool import _dispatch_to_plugin_provider
    except Exception as exc:
        print(json.dumps({"success": False, "error": f"無法載入 Hermes image_gen：{exc}",
                          "hint": f"這支要用 {HERMES_DIR}/venv/bin/python 執行"}, ensure_ascii=False))
        return 1

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    t0 = time.time()
    raw = _dispatch_to_plugin_provider(prompt, args.aspect)
    seconds = round(time.time() - t0, 1)
    if raw is None:
        print(json.dumps({"success": False, "seconds": seconds,
                          "error": "image_gen.provider 沒設定，請確認 ~/.hermes/config.yaml 的 "
                                   "image_gen.provider 是 openai-codex"}, ensure_ascii=False))
        return 1
    out = json.loads(raw)
    out["seconds"] = seconds
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
