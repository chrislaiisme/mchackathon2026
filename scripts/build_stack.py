"""Assemble the whole system (ENGINE 01 + 02 + 03) in one working tree, on one machine.

The team's branches each hold one piece and none of them holds all three:

  team/integration/hermes-app   the Hermes app layout: agent/ skills, bff/, mcp_servers/,
                                engine01_intent, and ENGINE 02 (our package + service layer,
                                which the migration moved to mcp_servers/catalog/main.py)
  team/engine03-feedback        ENGINE 03, written against ENGINE 02's published contract but
                                still in the old backend/ layout and never migrated

This script performs the migration that is missing, in place, so the stack can actually be
started. It is idempotent and it only writes inside the target worktree.

    python scripts/build_stack.py --worktree /tmp2/mzjiang/integration/hermes

What it does, and why each step exists:

1. **ENGINE 03 → `bff/feedback/`** with its imports rewritten from `backend.shared` to
   `bff.shared`. Without this, ENGINE 03 exists on a branch nobody can run next to ENGINE 02.
2. **Fix `mcp_servers/catalog/main.py`**, whose auth import still points at `backend.shared.auth`
   after the migration renamed `backend/` to `bff/`.
3. **A stub LLM for ENGINE 01**, because its real path shells out to `codex exec` on the author's
   ChatGPT subscription and that binary does not exist on a GPU server. The stub is deliberately
   dumb — a keyword matcher over the same `Intent` schema — so the stack can be exercised end to
   end without pretending we reproduced ENGINE 01's model.
4. **A runner and a smoke test** that drive one sentence through all three engines and assert the
   loop actually closes (round 2 differs from round 1, and an exclusion is honoured).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

E03_FILES = ("__init__.py", "contracts.py", "main.py", "prompts.py", "service.py",
             "README.md", "examples/click_only_request.json",
             "tests/__init__.py", "tests/test_service.py")

STUB = '''"""A stand-in for ENGINE 01's model, for machines without the `codex` CLI.

ENGINE 01 calls `codex exec`, which rides the author's ChatGPT subscription. That binary is not on
the GPU server, so the whole stack could not be exercised there. This stub fills the same `Intent`
schema with a keyword matcher over the user's sentence.

It is NOT a reproduction of ENGINE 01 and must never be used to claim anything about its accuracy:
it exists so the wiring between the three engines can be tested. Set ENGINE01_LLM=stub to use it.
"""

from __future__ import annotations

import re

ITEM_WORDS = ("連帽外套", "牛仔外套", "大衣", "外套", "襯衫", "洋裝", "裙", "褲", "T恤", "上衣",
              "毛衣", "針織衫", "西裝", "鞋", "包")
COLOR_WORDS = ("深藍", "藏青", "海軍藍", "淺藍", "藍", "黑", "白", "灰", "紅", "粉", "紫", "綠",
               "黃", "橘", "棕", "咖啡", "米", "卡其", "銀", "金")
OCCASION_WORDS = ("面試", "上班", "約會", "婚禮", "宴會", "運動", "健身", "登山", "旅行", "休閒",
                  "日常", "正式")
SEASON_WORDS = ("春夏", "秋冬", "春", "夏", "秋", "冬")
STYLE_WORDS = ("簡約", "修身", "寬鬆", "素面", "印花", "圓領", "立領", "針織", "棉", "亮面",
               "霧面", "深色", "鮮豔", "正式", "休閒", "運動", "透氣", "防水", "低調")


def _find(text: str, words) -> list[str]:
    return [w for w in words if w in text]


def extract_intent_stub(message: str, current: dict | None = None) -> dict:
    """Merge `message` into the current intent. Same shape as backend Intent."""
    out = dict(current or {})
    text = str(message or "")

    item = next((w for w in ITEM_WORDS if w in text), None)
    if item:
        out["item_type"] = item
    colors = [c + "色" if not c.endswith("色") else c for c in _find(text, COLOR_WORDS)]
    if colors:
        out["colors"] = colors[:2]
    occ = next((w for w in OCCASION_WORDS if w in text), None)
    if occ:
        out["occasion"] = occ
    season = next((w for w in SEASON_WORDS if w in text), None)
    if season:
        out["season"] = season
    styles = _find(text, STYLE_WORDS)
    # keep a negation attached to the word it negates: 「不要太正式」 must not become 「正式」
    phrases = []
    for s in styles:
        m = re.search(r"(不要|不想|別|避免)(太|很)?" + re.escape(s), text)
        phrases.append(m.group(0) if m else s)
    if phrases:
        out["style_keywords"] = phrases[:3]
    budget = re.search(r"(\\d[\\d,]*)\\s*(元|塊|nt|NT)", text)
    if budget:
        out["budget_max"] = float(budget.group(1).replace(",", ""))
    out.setdefault("inferred_fields", [])
    out["notes"] = "stub extractor (no codex on this machine)"
    return out
'''


def run(cmd: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(cmd)}\n{r.stderr[:400]}")
    return r.stdout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worktree", required=True, help="the integration worktree to assemble into")
    ap.add_argument("--repo", default=None, help="repo holding the team/* branches (default: worktree)")
    ap.add_argument("--e03-branch", default="team/engine03-feedback")
    a = ap.parse_args()

    wt = Path(a.worktree)
    repo = Path(a.repo) if a.repo else wt
    if not (wt / "engine02").is_dir():
        raise SystemExit(f"{wt} does not look like the integration worktree (no engine02/)")

    # ---- 1. ENGINE 03 into the Hermes layout
    dst = wt / "bff" / "feedback"
    dst.mkdir(parents=True, exist_ok=True)
    moved = []
    for rel in E03_FILES:
        try:
            blob = run(["git", "show", f"{a.e03_branch}:backend/engine03_feedback/{rel}"], cwd=repo)
        except SystemExit:
            print(f"  (skip {rel}: not on {a.e03_branch})")
            continue
        # the migration renamed backend/ to bff/; ENGINE 03 never saw that
        blob = blob.replace("backend.shared", "bff.shared").replace("backend/shared", "bff/shared")
        blob = blob.replace("backend.engine03_feedback", "bff.feedback")
        blob = blob.replace("backend/engine03_feedback", "bff/feedback")
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(blob, encoding="utf-8")
        moved.append(rel)
    print(f"1. ENGINE 03 → bff/feedback/ ({len(moved)} files)")

    # ---- 2. ENGINE 02's service layer still imports the pre-migration path
    cat = wt / "mcp_servers" / "catalog" / "main.py"
    if cat.exists():
        s = cat.read_text(encoding="utf-8")
        fixed = s.replace("from backend.shared.auth import", "from bff.shared.auth import")
        fixed = fixed.replace("`backend/shared/auth.py`", "`bff/shared/auth.py`")
        fixed = fixed.replace("uvicorn backend.engine02_retrieval.main:app",
                              "uvicorn mcp_servers.catalog.main:app")
        if fixed != s:
            cat.write_text(fixed, encoding="utf-8")
            print("2. mcp_servers/catalog/main.py: auth import repointed to bff.shared.auth")
        else:
            print("2. mcp_servers/catalog/main.py: already correct")
    else:
        print("2. WARNING: mcp_servers/catalog/main.py missing — ENGINE 02 has no service layer here")

    # ---- 3. a stub so ENGINE 01 can run without the codex CLI
    stub = wt / "bff" / "engine01_intent" / "llm_stub.py"
    stub.write_text(STUB, encoding="utf-8")
    e01_main = wt / "bff" / "engine01_intent" / "main.py"
    if e01_main.exists():
        s = e01_main.read_text(encoding="utf-8")
        if "ENGINE01_LLM" not in s:
            # route through the stub only when explicitly asked
            s = s.replace(
                "from .llm_client import extract_intent",
                "import os\n\n"
                "if os.environ.get(\"ENGINE01_LLM\") == \"stub\":\n"
                "    # no codex on this machine; see llm_stub.py for what this is and is not\n"
                "    from .llm_stub import extract_intent_stub as _stub\n"
                "\n"
                "    def extract_intent(message, current_intent):\n"
                "        from .llm_client import IntentExtraction\n"
                "        from bff.shared.schemas import Intent\n"
                "\n"
                "        data = _stub(message, current_intent.model_dump() if current_intent else {})\n"
                "        return IntentExtraction(intent=Intent(**data), clarifying_questions=[])\n"
                "else:\n"
                "    from .llm_client import extract_intent", 1)
            e01_main.write_text(s, encoding="utf-8")
            print("3. ENGINE 01: ENGINE01_LLM=stub path added")
        else:
            print("3. ENGINE 01: stub path already present")
    else:
        print("3. WARNING: bff/engine01_intent/main.py missing")

    print("\nassembled. next: scripts/run_stack.sh, then scripts/smoke_stack.py")


if __name__ == "__main__":
    main()
