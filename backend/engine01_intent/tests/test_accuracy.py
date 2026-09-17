"""Offline slot-filling accuracy check for ENGINE01.

Usage:
    python -m backend.engine01_intent.tests.test_accuracy

Loads test_cases.json (a 10-sentence starter set -- expand to 30-50
hand-labeled sentences before quoting the resulting number in the deck or
README, per docs/validation-plan.md), runs each sentence through
extract_intent starting from a blank intent, and reports the fraction of
expected slots that came out correct.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.engine01_intent.llm_client import extract_intent
from backend.shared.schemas import Intent

_CASES_PATH = Path(__file__).parent / "test_cases.json"


def _slot_matches(actual: Intent, field_name: str, expected_value: object) -> bool:
    actual_value = getattr(actual, field_name)
    if isinstance(expected_value, list):
        return set(actual_value or []) == set(expected_value)
    return actual_value == expected_value


def run() -> None:
    cases = json.loads(_CASES_PATH.read_text(encoding="utf-8"))

    total_slots = 0
    correct_slots = 0

    for case in cases:
        extraction = extract_intent(case["message"], Intent())
        for field_name, expected_value in case["expected_intent"].items():
            total_slots += 1
            if _slot_matches(extraction.intent, field_name, expected_value):
                correct_slots += 1
            else:
                actual_value = getattr(extraction.intent, field_name)
                print(
                    f'[MISS] "{case["message"]}" -> {field_name}: '
                    f"expected {expected_value!r}, got {actual_value!r}"
                )

    accuracy = correct_slots / total_slots if total_slots else 0.0
    print(f"\nSlot-filling accuracy: {correct_slots}/{total_slots} = {accuracy:.1%}")


if __name__ == "__main__":
    run()
