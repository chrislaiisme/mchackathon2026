"""Give ENGINE 01 a no-codex path, patched where it is actually called.

ENGINE 01 calls `llm_client.extract_intent()` through the module, so patching the import in
main.py does nothing. The switch belongs at the top of `extract_intent` itself, which is also the
only place that knows the return type.

    python scripts/patch_e01_stub.py --worktree /tmp2/mzjiang/integration/hermes

Idempotent. Only active when ENGINE01_LLM=stub, so a machine with `codex` installed is unaffected.
"""

from __future__ import annotations

import argparse
from pathlib import Path

GUARD = '''    # No `codex` on this machine (e.g. the GPU server): ENGINE01_LLM=stub swaps in a keyword
    # matcher so the three engines can be wired and tested together. It is NOT a reproduction of
    # ENGINE 01 and no accuracy claim may be made from it. See llm_stub.py.
    if os.environ.get("ENGINE01_LLM") == "stub":
        from bff.engine01_intent.llm_stub import extract_intent_stub

        merged = extract_intent_stub(message, current_intent.model_dump() if current_intent else {})
        return IntentExtraction(intent=Intent(**merged), clarifying_questions=[])

'''


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worktree", required=True)
    a = ap.parse_args()

    p = Path(a.worktree) / "bff" / "engine01_intent" / "llm_client.py"
    s = p.read_text(encoding="utf-8")
    if "ENGINE01_LLM" in s:
        print("already patched")
        return

    anchor = ('def extract_intent(message: str, current_intent: Intent) -> IntentExtraction:\n'
              '    """Merge `message` into `current_intent` via `codex exec`, and return the\n'
              '    updated intent plus any clarifying questions."""\n')
    if anchor not in s:
        raise SystemExit("could not find extract_intent's definition; ENGINE 01 changed shape")
    s = s.replace(anchor, anchor + GUARD, 1)
    p.write_text(s, encoding="utf-8")
    print("patched bff/engine01_intent/llm_client.py")


if __name__ == "__main__":
    main()
