# Fashion crawler (`engine02/crawl/`)

Collects fashion posts, articles and product pages into one record format, from public pages a site
allows automated clients to fetch, from Instagram through the official API or your own export, and
from Wikimedia Commons through its API. It stops at every refusal and says why.

## Run it

```bash
# 0. environment (once) -- the crawler itself needs only the standard library
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"

# sources from a config file
python -m engine02.crawl --config scripts/crawl_sources.example.toml
python -m engine02.crawl --config scripts/crawl_sources.example.toml --source <name> --max-pages 10

# one-off URLs: stays on their host(s), follows links matching --follow
python -m engine02.crawl --url https://shop.example/collections/new --follow "/products/" --max-pages 20

# Instagram from your own data export, no network
python -m engine02.crawl --instagram-export path/to/instagram-export/

# tests (local HTTP server, no internet)
python -m pytest -q tests/test_crawl.py
```

On Traditional-Chinese Windows set `PYTHONUTF8=1` first (the console is cp950).

## Output

Each run writes `data/crawl/<run id>/` (git-ignored):

| file | content |
|---|---|
| `records.json` | one object per record; missing fields are `null`, `image_urls` a list |
| `records.csv` | the same, UTF-8 with BOM (opens in Excel); missing fields empty, image URLs joined with ` \| ` |
| `errors.jsonl` | every skipped URL and every stop, with kind, detail and HTTP status |
| `report.json` | per source: `status` (completed / stopped / not_run), `stop_reason`, pages fetched, cache hits, records, duplicates, robots-disallowed count |

Record fields: `source, url, title, text, brand, price, currency, image_urls, published_at, account,
page_type, fetched_at, field_origin`. `field_origin` says where each value came from, e.g.
`price <- jsonld:Offer.price` or `jsonld:AggregateOffer.lowPrice` (a lowest price, not a list price).

**Brand and price are taken only from structured data the page declares** -- schema.org JSON-LD,
microdata, or OpenGraph `product:*` tags. A price written in prose ("now only NT$990") is never read.
If a page does not declare it, the field stays empty.

## What makes it stop -- and what does not

| situation | classification | what the crawler does |
|---|---|---|
| robots.txt disallows a URL | **prohibited** (by the site) | that URL is never requested; the crawl continues on allowed paths |
| robots.txt disallows every start URL | **prohibited** | source `stopped: robots_disallowed_all_seeds`, 0 page requests |
| robots.txt returns 5xx / is unreachable, or 401/403 | **treated as prohibited** (RFC 9309: unreachable = disallow all) | `stopped: robots_unreachable` / `robots_refused_401_403` |
| HTTP 401 / 403 / 407 / 451 | **access refused** | `stopped: access_denied` |
| redirected to a login page, or a password gate with no content | **login required** | `stopped: login_required` |
| Cloudflare / PerimeterX / DataDome / Incapsula challenge, CAPTCHA gate page | **bot challenge** | `stopped: captcha` -- no solving, no retry |
| 429 | rate limit | waits for `Retry-After` (up to 60 s), at most 2 retries, then `stopped: rate_limited` |
| a reCAPTCHA widget in a footer form on a normal product page | **not** a block | page is used normally (only a gate page with no content counts) |
| 5xx, timeout, network error | transient | retried twice with back-off, logged, crawl continues; 5 in a row stops it |
| 404 / 410 | missing page | logged, crawl continues |
| content rendered only by JavaScript | **technical limit** | the HTML has no structured data, so fields stay empty; not a refusal |
| no brand / price / image declared | **technical limit** (the page does not provide it) | field left empty |

Things the crawler deliberately does **not** do: log in, solve CAPTCHAs, rotate IPs or proxies,
spoof a browser User-Agent, or retry past a refusal. Its User-Agent identifies it:
`IntentWeaveFashionCrawler/0.1 (+https://github.com/chrislaiisme/mchackathon2026; non-commercial research; honours robots.txt)`.

Politeness: one request at a time per host, at least `delay_s` apart (default 2 s; a robots.txt
`Crawl-delay` raises it), responses cached on disk for `cache_ttl_hours` (default 24) and
revalidated with `If-None-Match` / `If-Modified-Since` when stale.

De-duplication: URLs are normalised (fragment and tracking parameters such as `utm_*`, `fbclid`,
`gclid`, `igshid` removed, query sorted) and the canonical URL is preferred; the same content under
two URLs is caught by a title/text/first-image fingerprint.

Page budget: links that look like a single product/article (`prefer`, default `/product(s)/`,
`/market/n/`, `/article`, long numeric ids ...) are fetched before listing pages. Plain
breadth-first spent lativ's whole 30-page budget on category pages and found 1 product.
A page that describes several products (or an ItemList) is a **listing**: it is used for links and
never recorded, so a record's URL always points at the product it describes.

## Other sources

| type | what | key needed |
|---|---|---|
| `commons` | Wikimedia Commons categories (runway, street fashion, cosplay) with licence + author per image | no |
| `mastodon` | public hashtag timelines (`#ootd`, `#streetstyle`, `#穿搭` ...); sensitive / content-warning posts skipped | no |
| `instagram_api` / `instagram_export` | see below | yours |

## The shipped dataset

`data/crawl_dataset/` (in git) is one full run of the example config on 2026-09-19: 1,911 records
from 38 sources, with every source's status and stop reason in `sources.json` (README there).
Several runs -- e.g. source groups crawled in parallel -- are merged with

```bash
python scripts/merge_crawl_runs.py --runs data/crawl/<run1> --runs data/crawl/<run2> --out data/crawl_dataset
```

(de-duplicated by URL, newest fetch wins, then by content fingerprint).

## From crawl to catalog

```bash
python scripts/crawl_to_catalog.py --records data/crawl_dataset --out data/catalog/crawl_tw --download-images
```

Keeps product pages with an image, maps them to the catalog schema without guessing (price, brand,
colour, gender only as the page states them; category from the page, else explicit title keywords,
recorded as `title_rule`), and drops non-apparel (a Pinkoi doll bundle, a desk calendar) with the
count in stats.json. Season / occasion are left for `scripts/vlm_fill_catalog.py`.

## Instagram

Checked on 2026-09-19, not assumed:

- **technically reachable**: an anonymous `GET https://www.instagram.com/hm/` returns HTTP 200;
- **explicitly prohibited**: `instagram.com/robots.txt` ends with `User-agent: * / Disallow: /`
  and begins *"Collection of data on Instagram through automated means is prohibited unless you
  have express written permission from Instagram"*. Pointing the web crawler at it therefore ends
  in `stopped: robots_disallowed_all_seeds` with zero page requests (verified live).

So Instagram has its own module with two supported routes:

**1. Official Graph API** -- needs an Instagram professional (business/creator) account linked to
a Facebook Page, an app, and a token. Put them in `.env` (git-ignored):

```
IG_ACCESS_TOKEN=...
IG_USER_ID=...        # the IG user id of YOUR professional account
```

```toml
[[sources]]
name = "ig_brands"
type = "instagram_api"
mode = "business_discovery"          # public posts of other business/creator accounts
usernames = ["somebrand", "otherbrand"]
max_posts = 200

[[sources]]
name = "ig_tag"
type = "instagram_api"
mode = "hashtag"                     # needs the hashtag permission; recent_media = last 24 h only
hashtags = ["ootd"]
hashtag_edge = "top_media"
```

`mode = "own_media"` reads your own account. Auth, permission, rate-limit and hashtag-quota errors
stop the source with the Graph API's error code in the report; the token is scrubbed from every
logged URL and never written to disk (this module does not use the page cache).

**2. Your own export** -- Instagram app → Your activity → Download your information → JSON. Point
the crawler at the unzipped folder (`--instagram-export`, or `type = "instagram_export"` with
`path = ...`). The parser reads posts as objects with a `media` list of image `uri`s, repairs
Meta's mis-encoded non-ASCII text, and **lists any file whose structure it does not recognise**
in the report instead of guessing. A CSV with `url, caption, image_url, timestamp, account`
columns is also accepted, as is a saved Graph API JSON response.

Neither route fills `brand` or `price`: a post does not declare them. The posting account goes in
`account`.

## Config reference

```toml
[defaults]
delay_s = 3.0            # min seconds between requests to one host
max_pages = 50
cache_ttl_hours = 24

[[sources]]
name = "example_shop"
type = "web"
start_urls = ["https://shop.example/collections/new"]
allowed_domains = ["shop.example"]      # subdomains included; default = hosts of start_urls
follow = ["/products/", "/collections/new\\?page="]   # regex; empty = every allowed link
exclude = ["/cart", "/account"]
sitemaps = []                            # explicit sitemap URLs (.xml or .xml.gz, index supported)
use_robots_sitemaps = false              # also read the Sitemap: lines in robots.txt
max_depth = 2
record_page_types = ["product", "article", "post"]   # listing pages are for discovery only
```

`scripts/crawl_sources.example.toml` holds the sources that were checked against their live
robots.txt and a sample page; each stanza says what was verified and when.
