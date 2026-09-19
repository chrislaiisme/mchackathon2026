# Catalog: crawled shop products, filled in by a vision model (166 items)

Built by `scripts/crawl_to_catalog.py` from `data/crawl_dataset/records.json` (the 2026-09-19 crawl),
then every image read by **Qwen/Qwen3-VL-8B-Instruct** (`scripts/vlm_fill_catalog.py`) and merged
by `scripts/apply_vlm_fill.py`.

Sources (items before the vision model): `pchome24h` (29), `taiwanize` (29), `ssense` (27),
`cheesebeign` (26), `iroo` (19), `plainme` (15), `jksshop` (12), `whiterock` (12), `lativ` (3),
`uijshop` (3), `mercci22` (1), `pazzo` (1), `pinkoi` (1). 178 items from 1,911 records
(dropped: 1,669 not product pages, 64 not apparel -- caps, socks, incense, books ...; examples in
stats.json). The vision model then dropped 12 more: 11 "multipack" (mostly one item photographed
in several colours, e.g. "... 4colors" -- a conservative cut) and 1 size chart.

## Where each value comes from

| column | source |
|---|---|
| title, description, brand, price, currency, sku, availability | the page's structured data (JSON-LD / OpenGraph), verbatim |
| colour, gender | structured data when stated (raw value in `color_raw` / `gender_raw`); otherwise colour from the model, gender stays empty |
| category | the page's structured category, else explicit title keyword rules (`attr_source.category = "title_rule"`); the model agreed on 97.2% |
| season, occasion, fit, boldness (0-3), style | the model (`attr_source` = `vlm:Qwen3-VL-8B-Instruct`) -- **never use as evaluation ground truth** |

Price is on every item (TWD, as the shop states it), so the price filter and rent-or-buy work here,
unlike the H&M catalog.

## Files

| file | in git | how to rebuild |
|---|---|---|
| `items.parquet`, `stats.json`, `vlm_fill_report.json`, `vlm_fill_*.meta.json` | yes | needs the crawl (pages change) and a GPU |
| `index/img_marqo-fashionSigLIP.npy` | yes | 166 x 768; recomputed automatically if missing |
| `images/` | no | `python scripts/fetch_catalog_images.py --catalog data/catalog/crawl_tw` |

```bash
python scripts/fetch_catalog_images.py --catalog data/catalog/crawl_tw
ENGINE02_CATALOG=data/catalog/crawl_tw ENGINE02_ENCODER=marqo-fashionSigLIP \
  python -m uvicorn engine02.api:app --port 8002
```

**Licence**: third-party shop content (titles, descriptions, prices, images belong to the shops /
makers). **Non-commercial research demo only.** Images are not redistributed: `image_url` points
at the shop.
