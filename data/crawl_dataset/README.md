# Crawl dataset (2026-09-19): 1,911 records from 38 sources

Everything the crawler (`engine02/crawl/`, docs/crawler.md) collected in one run of
`scripts/crawl_sources.example.toml`, merged by `scripts/merge_crawl_runs.py`. It ships because a
re-crawl gives a different set: shops change stock, feeds move on, Commons files get recategorised.

| kind | records | from |
|---|---|---|
| product pages | 242 | 13 Taiwanese / international shops (Pinkoi, lativ, iROO, PChome 24h, SSENSE, JKS, Whiterock, Cheesebeign, Taiwanize, Plain-me, U.I.J ...) |
| articles | 422 | fashion media (Vogue Runway, Vogue TW, GQ TW, Bazaar TW, Bella, ELLE TW, Hypebeast, Hypebae, Highsnobiety, JUKSY, WWD, BoF, Guardian, LTN iStyle, WEAR, The Sartorialist, CNA, PopDaily ...) |
| images | 800 | Wikimedia Commons: runway 300, street fashion 200, cosplay 300 -- every one with its licence and author |
| posts | 447 | Mastodon public hashtag timelines (#ootd #fashion #streetstyle #穿搭); sensitive / content-warning posts skipped |

1,890 records have at least one image URL. **Price (242) and brand (138) appear only where the page
declared them in structured data** -- nothing is guessed; missing = empty.

## Files

| file | content |
|---|---|
| `records.json` | one object per record (fields: docs/crawler.md "Output") |
| `records.csv` | the same, UTF-8 with BOM (opens in Excel), image URLs joined with ` \| ` |
| `sources.json` | per source: status, stop reason, pages fetched, records -- including the ones that gave 0 |
| `errors.jsonl` | every stop and skipped URL |

Images are **not** in the repo (URLs only), except the Commons thumbnails in `data/inspiration/`.

## Sources that gave nothing, and why

| source | result | kind |
|---|---|---|
| styleforum | HTTP 403 on the first pages -> `stopped: access_denied` | refused by the site; not retried |
| beams_tw, whowhatwear, yahoo_buy, udnstyle, ptt_mixmatch | pages fetched, no product/article structured data in the HTML | technical limit (content rendered by JavaScript or no schema.org markup) |
| lativ, PAZZO, Mercci22, Pinkoi | 1-3 records | same technical limit on most pages |
| Instagram | not crawled | robots.txt disallows all automated collection; supported only via the official API or your own export (docs/crawler.md) |

## Use

- As a catalog: `data/catalog/crawl_tw/` (product pages mapped to the catalog schema by
  `scripts/crawl_to_catalog.py`, then season / occasion / boldness filled by the vision model).
- As inspiration: `data/inspiration/` (Commons photos, embedded, shown with attribution).

**Licence**: third-party content -- non-commercial research / hackathon demo only. Commons images
carry their own CC licence (`field_origin.license`, `field_origin.author`): show the attribution.
Mastodon posts belong to their authors; `account` is kept so they can be credited.
