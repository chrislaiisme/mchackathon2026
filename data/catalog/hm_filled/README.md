# Catalog: H&M, filled in by a vision model (9,870 items)

`data/catalog/hm` (10,000 adult apparel/shoes/bag articles, `scripts/prepare_catalog_hm.py --n 10000
--seed 0`, from the open Hugging Face mirror `einrafh/hnm-fashion-recommendations-data`) with every
image read by **Qwen/Qwen3-VL-8B-Instruct** (`scripts/vlm_fill_catalog.py`, 1x A100-class GPU,
0.36 s/item) and merged by `scripts/apply_vlm_fill.py`.

## What is in the table and where each value comes from

| column | source |
|---|---|
| category, colour, pattern, gender | **H&M's own labels** (never overwritten by the model) |
| season, occasion | model (`attr_source` says `vlm:Qwen3-VL-8B-Instruct`); `season_p`, `occasion_p` = answer probabilities |
| fit, boldness (0-3), style | model; used for the 驚喜款 slot and the style terms |
| price | **not in the source** -- every row carries a labelled **estimate** (`price_estimated` = true, `price_basis`, `attr_source.price = "estimated:price-estimate-v1"`; engine02/price_estimate.py, written by `scripts/estimate_prices.py`). Never a price tag, never ground truth |

130 of 10,000 rows were dropped because the image is not one sellable item:
79 multipacks, 47 size charts, 4 not apparel (listed with titles in `vlm_fill_report.json`).

## How good is the model (checked against H&M's labels, not against itself)

| check | n | agreement |
|---|---|---|
| category | 10,000 | 94.0% |
| colour family | 9,234 | 80.8% (exact colour 68.9%) |
| pattern | 9,997 | 77.0% |
| season vs. the item's own description word (only items whose text names one season) | 4,713 | 78.9% |

**Season / occasion have no ground truth.** Never use them as evaluation labels.

## Files

| file | in git | how to rebuild |
|---|---|---|
| `items.parquet` | yes | needs a GPU (~1 h for 10k) -- that is why it ships |
| `vlm_fill_report.json`, `vlm_fill_Qwen3-VL-8B-Instruct.meta.json` | yes | written by the two scripts above (prompts + options in the meta) |
| `index/img_marqo-fashionSigLIP.npy` | yes | 9,870 x 768 image embeddings in row order; recomputed automatically if the row count differs (~15 min on CPU) |
| `images/` | no | `python scripts/fetch_catalog_images.py --catalog data/catalog/hm_filled` |

```bash
python scripts/fetch_catalog_images.py --catalog data/catalog/hm_filled
ENGINE02_CATALOG=data/catalog/hm_filled ENGINE02_ENCODER=marqo-fashionSigLIP \
  python -m uvicorn engine02.api:app --port 8002
```

**Licence**: H&M Kaggle competition rules -- *Non-Commercial Purposes & Academic Research*.
Product images are H&M's. Hackathon demo only.
