"""The one shape every source produces, URL normalisation for de-duplication, and CSV/JSON export."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that identify a click, not a page. Two URLs differing only in these are one page.
TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "igshid", "igsh", "mc_cid", "mc_eid", "_ga", "_gl",
    "ref", "ref_src", "ref_url", "spm", "scm", "yclid", "twclid", "ttclid", "si",
}


@dataclass
class Record:
    source: str
    url: str                                   # canonical URL (or permalink) -- the de-dup key
    title: str | None = None
    text: str | None = None                    # post / article text, or the page's own description
    brand: str | None = None                   # only if the page states it in structured data
    price: str | None = None                   # as the page states it; never parsed from prose
    currency: str | None = None
    image_urls: list[str] = field(default_factory=list)
    published_at: str | None = None
    account: str | None = None                 # Instagram account; not the same thing as a brand
    page_type: str | None = None               # product | article | post | page
    fetched_at: str | None = None
    field_origin: dict[str, str] = field(default_factory=dict)  # field -> jsonld | og | microdata | ...

    def fingerprint(self) -> str:
        """Content identity, to catch the same item served under two URLs."""
        basis = "\x1f".join([(self.title or "").strip().lower(), (self.text or "").strip().lower()[:500],
                             self.image_urls[0] if self.image_urls else ""])
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_url(url: str) -> str:
    """Lowercase scheme/host, drop the fragment, default ports and tracking parameters, sort the rest."""
    p = urlsplit(url.strip())
    scheme = (p.scheme or "http").lower()
    host = (p.hostname or "").lower()
    if p.port and not ((scheme == "http" and p.port == 80) or (scheme == "https" and p.port == 443)):
        host = f"{host}:{p.port}"
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    return urlunsplit((scheme, host, p.path or "/", urlencode(sorted(query)), ""))


CSV_FIELDS = ["source", "url", "title", "text", "brand", "price", "currency", "image_urls",
              "published_at", "account", "page_type", "fetched_at", "field_origin"]


def export(records: list[Record], out_dir: Path) -> dict[str, str]:
    """records.json (lists kept as lists) and records.csv (image_urls joined with " | ")."""
    out_dir.mkdir(parents=True, exist_ok=True)
    js, cs = out_dir / "records.json", out_dir / "records.csv"
    js.write_text(json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=1), encoding="utf-8")
    with cs.open("w", encoding="utf-8-sig", newline="") as fh:          # BOM: Excel opens UTF-8 correctly
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in records:
            d = r.to_dict()
            d["image_urls"] = " | ".join(d["image_urls"])
            d["field_origin"] = json.dumps(d["field_origin"], ensure_ascii=False) if d["field_origin"] else ""
            w.writerow({k: ("" if d.get(k) is None else d[k]) for k in CSV_FIELDS})
    return {"json": str(js), "csv": str(cs)}
