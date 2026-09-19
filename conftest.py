"""Repo-wide pytest settings."""

import pytest


@pytest.fixture(autouse=True)
def _no_auto_context(monkeypatch):
    """ENGINE 02 fills in today's date, the current hour and the default city's weather by itself
    (engine02/context/auto.py). Tests that are not about that must not depend on the day they run;
    tests/test_auto_context.py switches it back on."""
    monkeypatch.setenv("ENGINE02_AUTO_CONTEXT", "0")
