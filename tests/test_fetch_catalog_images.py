"""scripts/fetch_catalog_images.py: one dropped transfer must not end the whole run."""

import http.client
import importlib.util
import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_catalog_images", ROOT / "scripts" / "fetch_catalog_images.py")
fci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fci)


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), (200, 10, 10)).save(buf, "JPEG")
    return buf.getvalue()


def test_incomplete_read_is_retried_not_fatal(tmp_path, monkeypatch):
    calls = []

    def urlopen(req, timeout=60):
        calls.append(req)
        if len(calls) == 1:     # 2026-09-19: IncompleteRead killed a fresh clone's run at 8,001/9,870
            raise http.client.IncompleteRead(b"x" * 10, 100)
        return _Resp(_jpeg())

    monkeypatch.setattr(fci.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fci.time, "sleep", lambda s: None)
    dst = tmp_path / "images" / "a.jpg"
    assert fci.fetch("https://img.test/a.jpg", dst) is True and dst.exists() and len(calls) == 2
    # identifies itself like the crawler, never Python's default User-Agent
    assert "IntentWeaveFashionCrawler" in calls[0].get_header("User-agent")


def test_persistent_failure_returns_false(tmp_path, monkeypatch):
    def urlopen(req, timeout=60):
        raise http.client.IncompleteRead(b"", 5)

    monkeypatch.setattr(fci.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fci.time, "sleep", lambda s: None)
    assert fci.fetch("https://img.test/b.jpg", tmp_path / "b.jpg") is False
