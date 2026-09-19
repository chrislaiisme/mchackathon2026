# Inspiration library: runway / street / cosplay (381 photos)

Photos from Wikimedia Commons categories "Catwalks (fashion)", "Street fashion" and "Cosplayers",
built by `scripts/build_inspiration.py --per-group 150` on 2026-09-19 (official API, serial, cached).
A photo here is never a product: it is a *query* ("我想要這種感覺") -- its embedding is folded into
`/rank` at weight 0.2, the same path `/visual-search` uses for an uploaded photo. It is kept out of
the catalog so the catalog's z-scored design terms do not move.

| group | kept |
|---|---|
| runway 伸展台 | 126 |
| street 街頭穿搭 | 120 |
| cosplay 角色扮演 | 135 |

## Content screen

450 photos were downloaded; 69 were dropped by `engine02.inspiration.screen`: each photo is
compared, in the Marqo-FashionSigLIP image-text space, with "a person wearing an outfit" and with
posters, crowds, talks, face close-ups, empty rooms / machines, clothes on mannequins and
swimwear / lingerie. Kept only when the outfit description wins with p >= 0.95 and swimwear /
lingerie is not close behind. Drops by reason: 40 low confidence, 6 crowd, 6 talk, 5 display,
5 revealing, 4 face, 2 object, 1 text -- every one listed with its scores in `build_report.json`.
The thresholds were set by looking at contact sheets of every drop and of the kept photos nearest
each threshold, not measured against labels.

## Attribution is required

Every row has `license`, `license_url`, `author` and `page_url` (CC BY 2.0, CC BY-SA 2.0-4.0, CC0,
public domain ...). Show them wherever a photo is shown; `GET /inspiration` returns them.

## Files (all in git)

| file | content |
|---|---|
| `items.parquet` | insp_id, group, title, image_path, image_url, page_url, license, license_url, author |
| `images/<insp_id>.jpg` | 384 px thumbnails (CC-licensed; shipped because Commons files get renamed, deleted or recategorised) |
| `index/img_marqo-fashionSigLIP.npy` + `meta_...json` | embeddings in row order, from the same encoder the service uses |
| `build_report.json` | crawl counters, licences, screen drops |

Rebuild: `python scripts/build_inspiration.py --per-group 150` (network, no key; ~15 min on CPU).
Re-screen only: `python scripts/build_inspiration.py --screen-only`.
