"""Inspiration library (靈感牆): offline — synthetic photos, the hash encoder, no network."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from engine02.encoders import HashEncoder
from engine02.inspiration import COLUMNS, InspirationError, load, write_index

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"

SPEC = [("runway", "runway-aaa", (20, 20, 20), "Paris show black coat", "CC BY-SA 4.0", "Jane Photog"),
        ("runway", "runway-bbb", (200, 180, 160), "Milan beige tailoring", "CC BY 2.0", "Studio X"),
        ("street", "street-ccc", (30, 60, 140), "Tokyo street denim", "CC BY-SA 3.0", "K. Tanaka"),
        ("street", "street-ddd", (150, 20, 30), "Seoul red jacket", "Public domain", "unknown"),
        ("cosplay", "cosplay-eee", (240, 200, 230), "Pink magical girl", "CC BY 4.0", "Cos Fan")]


def _script():
    spec = importlib.util.spec_from_file_location("build_inspiration", ROOT / "scripts" / "build_inspiration.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build(root: Path, dim: int = 256, key: str = "hash") -> pd.DataFrame:
    from PIL import Image

    rows = []
    for group, iid, rgb, title, lic, author in SPEC:
        p = root / "images" / f"{iid}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (96, 128), rgb).save(p, format="JPEG")
        rows.append({"insp_id": iid, "group": group, "title": title, "image_path": f"images/{iid}.jpg",
                     "image_url": f"https://upload.wikimedia.org/x/{iid}.jpg",
                     "page_url": f"https://commons.wikimedia.org/wiki/File:{iid}.jpg",
                     "license": lic, "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
                     "author": author})
    items = pd.DataFrame(rows, columns=COLUMNS)
    write_index(root, items, HashEncoder(dim=dim), key)
    return items


def test_library_lists_with_attribution_and_guards_dimension(tmp_path):
    _build(tmp_path)
    lib = load(tmp_path, encoder="hash")
    assert len(lib) == 5 and lib.counts() == {"cosplay": 1, "runway": 2, "street": 2}
    street = lib.list_items("street")
    assert [r["insp_id"] for r in street] == ["street-ccc", "street-ddd"]
    assert len(lib.list_items(limit=2)) == 2
    for r in lib.list_items():
        assert r["license"] and r["author"] and r["page_url"].startswith("https://commons.wikimedia.org/")
    with pytest.raises(ValueError):
        lib.list_items("catalog")

    v = lib.embedding("runway-aaa", expected_dim=256, encoder_name="hash-256")
    assert v.shape == (256,) and abs(float(np.linalg.norm(v)) - 1.0) < 1e-5
    with pytest.raises(InspirationError, match="256 dims.*512"):
        lib.embedding("runway-aaa", expected_dim=512, encoder_name="marqo-fashionSigLIP")
    with pytest.raises(InspirationError, match="different space"):   # same dim, other encoder
        lib.check_compatible(256, "fashion-clip")
    with pytest.raises(KeyError):
        lib.embedding("nope")
    with pytest.raises(InspirationError, match="build_inspiration"):
        load(tmp_path, encoder="marqo-fashionSigLIP").embeddings()     # no index for that encoder
    with pytest.raises(InspirationError):
        load(tmp_path / "missing")


def test_stale_index_is_refused(tmp_path):
    items = _build(tmp_path)
    items.iloc[::-1].to_parquet(tmp_path / "items.parquet", index=False)   # reorder rows only
    with pytest.raises(InspirationError, match="row order"):
        load(tmp_path, encoder="hash").embeddings()


def test_build_script_rows_and_thumbnails(tmp_path):
    from PIL import Image

    from engine02.crawl.http import FetchError

    mod = _script()

    def rec(url, lic="CC BY-SA 4.0", author="<b>A</b>"):
        return SimpleNamespace(url=url, title="Look", image_urls=[url + ".jpg"],
                               field_origin={"license": lic, "license_url": "u", "author": author})

    seen: set[str] = set()
    rows, skipped = mod.records_to_rows("runway", [rec("p1"), rec("p2", lic=""), rec("p1")], seen)
    assert [r["page_url"] for r in rows] == ["p1"]
    assert skipped == {"no_license": 1, "duplicate": 1}
    assert rows[0]["insp_id"].startswith("runway-") and rows[0]["image_path"].endswith(".jpg")
    rows2, _ = mod.records_to_rows("street", [rec("p1"), rec("p3")], seen)   # de-dup across groups
    assert [r["page_url"] for r in rows2] == ["p3"]

    buf = io.BytesIO()
    Image.new("RGBA", (800, 1200), (255, 0, 0, 0)).save(buf, format="PNG")

    class FakeFetcher:
        def get(self, url):
            if "p3" in url:
                raise FetchError(url, "HTTP 404", 404)
            return SimpleNamespace(body=buf.getvalue())

    kept, fails, stop = mod.download(rows + rows2, tmp_path, FakeFetcher())
    assert len(kept) == 1 and fails == {"fetch:404": 1} and stop is None
    with Image.open(tmp_path / kept[0]["image_path"]) as im:
        assert im.format == "JPEG" and im.mode == "RGB" and im.width == 384 and im.height == 576


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_WARMUP", "0")
    monkeypatch.setenv("ENGINE02_INSPIRATION", str(tmp_path / "insp"))
    _build(tmp_path / "insp")
    from fastapi.testclient import TestClient

    from engine02.api import app
    from engine02.inspiration_api import router

    if not any(getattr(r, "path", None) == "/inspiration" for r in app.routes):
        app.include_router(router)
    with TestClient(app) as c:
        yield c


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")
def test_inspiration_api_list_image_and_recommend(client, tmp_path, monkeypatch):
    d = client.get("/inspiration", params={"group": "runway", "limit": 30}).json()
    assert d["groups"]["runway"] == {"label": "伸展台", "count": 2}
    assert [it["group"] for it in d["items"]] == ["runway", "runway"]
    first = d["items"][0]
    for k in ("image_url", "title", "license", "author", "page_url", "attribution"):
        assert first[k], k
    assert "Jane Photog" in first["attribution"] and "CC BY-SA 4.0" in first["attribution"]
    assert client.get("/inspiration", params={"group": "catalog"}).status_code == 400
    assert len(client.get("/inspiration").json()["items"]) == 5

    img = client.get(first["image_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get("/inspiration/images/nope").status_code == 404

    body = {"retrieval_text": "men navy blue shirts for formal", "top_k": 4, "context": {"mood": "calm"}}
    r = client.post(f"/inspiration/{first['insp_id']}/recommend", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["response"]["items"]) == 4
    assert out["note"] == "以這張伸展台照片的感覺為參考（權重 0.2，文字需求仍是主角）"
    assert out["inspiration"]["author"] == "Jane Photog" and out["inspiration"]["license"] == "CC BY-SA 4.0"
    assert out["concept_image_weight"] == 0.2 and "profile" in out

    # same path as /visual-search: identical to /rank with the photo as concept_image_embedding
    from engine02.inspiration import load as load_lib

    vec = load_lib(tmp_path / "insp", "hash").embedding(first["insp_id"]).tolist()
    ref = client.post("/rank", json={"session_id": "inspiration", "retrieval_text": body["retrieval_text"],
                                     "context": body["context"],
                                     "feedback": {"concept_image_embedding": vec},
                                     "options": {"top_k": 4, "explain_with_llm": False}}).json()
    assert [it["item_id"] for it in ref["items"]] == [it["item_id"] for it in out["response"]["items"]]

    bare = client.post("/inspiration/street-ccc/recommend", json={}).json()
    assert "街拍照片" in bare["note"] and "還沒說想找什麼" in bare["note"]
    assert len(bare["response"]["items"]) == 5
    assert client.post("/inspiration/nope/recommend", json={}).status_code == 404
    assert client.post("/inspiration/street-ccc/recommend", json={"arm": "nope"}).status_code == 400


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")
def test_inspiration_api_refuses_foreign_encoder_index(client, tmp_path, monkeypatch):
    other = tmp_path / "insp64"
    _build(other, dim=64)                       # built with a 64-dim encoder, service runs 256
    monkeypatch.setenv("ENGINE02_INSPIRATION", str(other))
    assert client.get("/inspiration").status_code == 200            # browsing still works
    r = client.post("/inspiration/runway-aaa/recommend", json={"retrieval_text": "coat"})
    assert r.status_code == 409 and "64 dims" in r.json()["detail"]
    monkeypatch.setenv("ENGINE02_INSPIRATION", str(tmp_path / "nowhere"))
    assert client.get("/inspiration").status_code == 503


# ---- content screen -----------------------------------------------------------------------------
class _PromptEncoder:
    """Text i -> unit vector e_i, so an image embedding says exactly which prompt it matches."""
    name = "fake-clip"

    def __init__(self):
        from engine02.inspiration import SCREEN_KEEP, SCREEN_REJECT
        self.texts = SCREEN_KEEP + [t for v in SCREEN_REJECT.values() for t in v]
        self.dim = len(self.texts)

    def encode_text(self, texts):
        return np.stack([np.eye(self.dim, dtype=np.float32)[self.texts.index(t)] for t in texts])

    def vec(self, **w):
        v = np.zeros(self.dim, np.float32)
        for text, x in w.values():
            v[self.texts.index(text)] = x
        return v / np.linalg.norm(v)


def test_screen_keeps_outfits_and_drops_posters_and_revealing_shots():
    from engine02.inspiration import SCREEN_KEEP, SCREEN_REJECT, screen
    enc = _PromptEncoder()
    rev = SCREEN_REJECT["revealing"][0]
    emb = np.stack([
        enc.vec(a=(SCREEN_KEEP[2], 1.0)),                                   # a cosplayer: kept
        enc.vec(a=(SCREEN_REJECT["text"][0], 1.0)),                         # an event poster
        enc.vec(a=(SCREEN_KEEP[0], 0.8), b=(rev, 0.795)),                   # outfit, but swimwear close behind
        enc.vec(a=(SCREEN_KEEP[1], 0.9), b=(SCREEN_REJECT["crowd"][0], 0.87)),  # outfit wins, not confidently
    ])
    keep, info = screen(emb, enc)
    assert keep.tolist() == [True, False, False, False]
    assert [i["label"] for i in info] == ["outfit", "text", "revealing", "low_confidence"]
    assert info[0]["p_outfit"] > 0.99


def test_screen_is_a_no_op_for_the_hash_test_encoder():
    from engine02.inspiration import screen
    keep, info = screen(np.ones((3, 8), np.float32) / np.sqrt(8), HashEncoder(dim=8))
    assert keep.all() and info[0]["p_outfit"] is None
