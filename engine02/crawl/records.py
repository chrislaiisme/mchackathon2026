"""The one shape every source produces, URL normalisation for de-duplication, and CSV/JSON export."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

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
    # Optional product facts, only when the page states them in structured data (never inferred).
    category: str | None = None                # Product.category / og product:category, verbatim
    sku: str | None = None
    availability: str | None = None            # schema.org term, e.g. InStock / OutOfStock
    color: str | None = None                   # verbatim, e.g. "深藍色" -- normalised downstream
    gender: str | None = None                  # verbatim, e.g. "female" / "unisex"

    def fingerprint(self) -> str:
        """Content identity, to catch the same item served under two URLs."""
        basis = "\x1f".join([(self.title or "").strip().lower(), (self.text or "").strip().lower()[:500],
                             self.image_urls[0] if self.image_urls else ""])
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)


def _ascii_path(path: str) -> str:
    """IRI -> URI for the path: percent-encode only non-ASCII characters and spaces. Existing %xx
    escapes are left alone (unquoting first would turn %2F into a real / and change the path).
    A raw 「/products/文青女孩」 link crashed the whole crawl process in urllib before this."""
    return "".join(c if (ord(c) < 128 and c != " ") else quote(c) for c in path)


def normalize_url(url: str) -> str:
    """Lowercase scheme/host, drop the fragment, default ports and tracking parameters, sort the rest,
    and make the result plain ASCII (percent-encoded path, IDNA host) so any HTTP client accepts it."""
    p = urlsplit(url.strip())
    scheme = (p.scheme or "http").lower()
    host = (p.hostname or "").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    try:
        port = p.port
    except ValueError:                        # "http://x:abc/" -- keep going without a port
        port = None
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    return urlunsplit((scheme, host, _ascii_path(p.path or "/"), urlencode(sorted(query)), ""))


CSV_FIELDS = ["source", "url", "title", "text", "brand", "price", "currency", "image_urls",
              "published_at", "account", "page_type", "fetched_at", "field_origin",
              "category", "sku", "availability", "color", "gender"]


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
