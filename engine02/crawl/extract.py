"""HTML -> record fields, from structured data only. Nothing is inferred from prose.

Brand and price are taken ONLY from what a page declares for machines:
  JSON-LD (schema.org Product / Offer / AggregateOffer)  >  microdata (itemprop)  >  OpenGraph
  (product:price:amount, product:brand). A price in a sentence is not read: "from NT$990 in
  selected sizes" is not a product price, and parsing it would be exactly the guessing we refuse.
Category, sku, availability, colour and gender likewise: JSON-LD Product.category / .sku /
offers.availability / .color / .audience.suggestedGender (or audience.gender) > OpenGraph product:*
tags; absent when the page does not state them.
Text: JSON-LD articleBody > JSON-LD description > og:description > <meta name=description>.
Every field records where it came from in `field_origin`, e.g. price <- "jsonld:AggregateOffer.lowPrice".
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

PRODUCT_TYPES = {"product", "productgroup", "individualproduct", "productmodel"}
ARTICLE_TYPES = {"article", "blogposting", "newsarticle", "socialmediaposting", "reportagenewsarticle"}
SKIP_IMG_SUFFIX = (".svg", ".gif", ".ico")
# No end tag ever arrives for these, so they must not move the nesting depth.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
        "source", "track", "wbr"}


class _Collector(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title_parts: list[str] = []
        self.meta: dict[str, list[str]] = {}
        self.canonical: str | None = None
        self.jsonld: list[str] = []
        self.imgs: list[str] = []
        self.links: list[str] = []
        self.micro: dict[str, str] = {}
        self._in_title = self._in_jsonld = False
        self._buf: list[str] = []
        self._micro_stack: list[tuple[str, int, list[str]]] = []   # (prop, depth, text parts)
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag not in VOID:
            self._depth += 1
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and "content" in a:
                self.meta.setdefault(key, []).append(a["content"].strip())
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split() and a.get("href"):
            self.canonical = urljoin(self.base, a["href"])
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld, self._buf = True, []
        elif tag == "img":
            if a.get("width") in ("0", "1", "2") or a.get("height") in ("0", "1", "2"):
                pass                                   # tracking pixel: none of its URLs count
            else:
                for key in ("src", "data-src", "data-original"):
                    if a.get(key):
                        self.imgs.append(urljoin(self.base, a[key].strip()))
                for key in ("srcset", "data-srcset"):
                    if a.get(key):                     # every candidate, in page order
                        for cand in a[key].split(","):
                            u = cand.strip().split(" ")[0]
                            if u:
                                self.imgs.append(urljoin(self.base, u))
        elif tag == "a" and a.get("href"):
            self.links.append(urljoin(self.base, a["href"].strip()))
        prop = a.get("itemprop", "").lower()
        if prop in ("price", "pricecurrency", "brand", "name"):
            if a.get("content"):          # <meta itemprop="price" content="..."> is the common form
                self.micro.setdefault(prop, a["content"].strip())
            elif tag not in VOID:         # otherwise the element's own text
                self._micro_stack.append((prop, self._depth, []))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            self.jsonld.append("".join(self._buf))
            self._in_jsonld = False
        while self._micro_stack and self._micro_stack[-1][1] >= self._depth:
            prop, _, parts = self._micro_stack.pop()
            text = " ".join("".join(parts).split())
            if text:
                self.micro.setdefault(prop, text)
        self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if self._in_jsonld:
            self._buf.append(data)
        for _, _, parts in self._micro_stack:
            parts.append(data)


def _nodes(obj):
    """Every dict in a JSON-LD document, flattening @graph and lists."""
    if isinstance(obj, list):
        for x in obj:
            yield from _nodes(x)
    elif isinstance(obj, dict):
        yield obj
        for k in ("@graph", "mainEntity", "itemListElement", "hasVariant"):
            if k in obj:
                yield from _nodes(obj[k])


def _types(node) -> set[str]:
    t = node.get("@type", [])
    return {str(x).lower() for x in (t if isinstance(t, list) else [t])}


def _str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("name") or v.get("@id") or v.get("url")
    if isinstance(v, list):
        v = next((_str(x) for x in v if _str(x)), None)
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _images(v, base) -> list[str]:
    out = []
    for x in (v if isinstance(v, list) else [v]):
        u = x.get("url") or x.get("contentUrl") if isinstance(x, dict) else x
        if isinstance(u, str) and u.strip():
            out.append(urljoin(base, u.strip()))
    return out


def _offer_price(offers) -> tuple[str | None, str | None, str | None]:
    """(price, currency, origin) from schema.org offers, exactly as stated."""
    for o in (offers if isinstance(offers, list) else [offers]):
        if not isinstance(o, dict):
            continue
        spec = o.get("priceSpecification")
        spec = spec[0] if isinstance(spec, list) and spec else spec
        for price, cur, origin in (
            (o.get("price"), o.get("priceCurrency"), "jsonld:Offer.price"),
            ((spec or {}).get("price") if isinstance(spec, dict) else None,
             (spec or {}).get("priceCurrency") if isinstance(spec, dict) else None,
             "jsonld:Offer.priceSpecification.price"),
            (o.get("lowPrice"), o.get("priceCurrency"), "jsonld:AggregateOffer.lowPrice"),
        ):
            if price not in (None, ""):
                return str(price).strip(), _str(cur), origin
    return None, None, None


def _offer_availability(offers) -> str | None:
    """schema.org availability as stated, shortened to its term ("https://schema.org/InStock" -> "InStock")."""
    for o in (offers if isinstance(offers, list) else [offers]):
        if isinstance(o, dict):
            v = _str(o.get("availability"))
            if v:
                return v.rstrip("/").rsplit("/", 1)[-1]
    return None


def _audience_gender(aud) -> tuple[str | None, str | None]:
    """(gender, origin) from Product.audience (PeopleAudience.suggestedGender, or audience.gender)."""
    for a in (aud if isinstance(aud, list) else [aud]):
        if isinstance(a, dict):
            for key in ("suggestedGender", "gender"):
                v = _str(a.get(key))
                if v:
                    return v.rstrip("/").rsplit("/", 1)[-1], f"jsonld:Product.audience.{key}"
    return None, None


def extract(html: str, url: str) -> dict:
    c = _Collector(url)
    try:
        c.feed(html)
        c.close()
    except Exception:                      # malformed HTML: keep what was collected
        pass
    meta = {k: v[0] for k, v in c.meta.items()}
    out: dict = {"title": None, "text": None, "brand": None, "price": None, "currency": None,
                 "published_at": None, "page_type": "page", "image_urls": [], "field_origin": {},
                 "category": None, "sku": None, "availability": None, "color": None, "gender": None}
    origin = out["field_origin"]

    def put(key, value, src):
        if value not in (None, "") and out.get(key) in (None, ""):
            out[key] = value
            origin[key] = src

    docs = []
    for raw in c.jsonld:
        try:
            docs.append(json.loads(raw.strip()))
        except (ValueError, TypeError):
            continue
    nodes = [n for d in docs for n in _nodes(d)]
    products = [n for n in nodes if _types(n) & PRODUCT_TYPES]
    # A page that describes several products (or an ItemList) is a LISTING. Taking its first product
    # produced a record whose URL was the listing page -- a card that links to the wrong place.
    # Listings are for discovering links; their products are recorded from their own pages.
    is_listing = len({(_str(p.get("name")), _str(p.get("sku"))) for p in products}) > 1 or \
        any("itemlist" in _types(n) for n in nodes)
    product = products[0] if (products and not is_listing) else None
    article = next((n for n in nodes if _types(n) & ARTICLE_TYPES), None)
    imgs: list[str] = []
    if is_listing:
        out["page_type"] = "listing"
    if product:
        out["page_type"] = "product"
        put("title", _str(product.get("name")), "jsonld:Product.name")
        put("brand", _str(product.get("brand")), "jsonld:Product.brand")
        p, cur, o = _offer_price(product.get("offers"))
        put("price", p, o)
        put("currency", cur, (o.rsplit(".", 1)[0] + ".priceCurrency") if o else None)
        put("text", _str(product.get("description")), "jsonld:Product.description")
        put("category", _str(product.get("category")), "jsonld:Product.category")
        put("sku", _str(product.get("sku")), "jsonld:Product.sku")
        put("availability", _offer_availability(product.get("offers")), "jsonld:Offer.availability")
        put("color", _str(product.get("color")), "jsonld:Product.color")
        g, g_origin = _audience_gender(product.get("audience"))
        put("gender", g, g_origin)
        imgs += _images(product.get("image"), url)
    if article:
        if not product and not is_listing:
            out["page_type"] = "post" if "socialmediaposting" in _types(article) else "article"
        put("title", _str(article.get("headline") or article.get("name")), "jsonld:Article.headline")
        put("text", _str(article.get("articleBody")), "jsonld:Article.articleBody")
        put("text", _str(article.get("description")), "jsonld:Article.description")
        put("published_at", _str(article.get("datePublished")), "jsonld:Article.datePublished")
        imgs += _images(article.get("image"), url)

    put("price", c.micro.get("price"), "microdata:price")
    put("currency", c.micro.get("pricecurrency"), "microdata:priceCurrency")
    put("brand", c.micro.get("brand"), "microdata:brand")
    put("price", meta.get("product:price:amount") or meta.get("og:price:amount"), "og:product:price:amount")
    put("currency", meta.get("product:price:currency") or meta.get("og:price:currency"),
        "og:product:price:currency")
    put("brand", meta.get("product:brand") or meta.get("og:brand"), "og:product:brand")
    # Open Graph product object (Facebook catalog tags), each only when the page states it.
    put("category", meta.get("product:category"), "og:product:category")
    put("sku", meta.get("product:retailer_item_id"), "og:product:retailer_item_id")
    avail = meta.get("product:availability") or meta.get("og:availability")
    put("availability", avail.rstrip("/").rsplit("/", 1)[-1] if avail else None, "og:product:availability")
    put("color", meta.get("product:color"), "og:product:color")
    put("gender", meta.get("product:target_gender"), "og:product:target_gender")
    if out["page_type"] == "page" and meta.get("og:type", "").lower().startswith("product"):
        out["page_type"] = "product"
    elif out["page_type"] == "page" and meta.get("og:type", "").lower() == "article":
        out["page_type"] = "article"
    put("title", meta.get("og:title"), "og:title")
    put("title", " ".join("".join(c.title_parts).split()) or None, "html:title")
    put("text", meta.get("og:description"), "og:description")
    put("text", meta.get("description"), "meta:description")
    put("published_at", meta.get("article:published_time"), "og:article:published_time")
    imgs = [u for u in (_images(c.meta.get("og:image", []), url) + imgs) if u]
    imgs += c.imgs

    seen, clean = set(), []
    for u in imgs:
        if u.startswith("data:") or urlsplit(u).path.lower().endswith(SKIP_IMG_SUFFIX) or u in seen:
            continue
        seen.add(u)
        clean.append(u)
    out["image_urls"] = clean[:60]
    if out["image_urls"]:
        origin["image_urls"] = "og:image/jsonld/img"
    out["canonical"] = c.canonical
    out["links"] = c.links
    return out
