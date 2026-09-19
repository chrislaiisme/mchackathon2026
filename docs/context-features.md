# Context, personal options and services (intuition v0)

Creative layer on top of ENGINE 02. **Nothing here is measured yet** -- every signal says
`evidence: "intuition v0 (not yet measured)"` (or "entertainment" for the lucky colour), and a card
shows exactly how much each situation added.

## In the ranking: `Engine02Request.context`

```json
{"context": {"city": "新竹", "lat": 24.8, "lon": 120.97, "event_date": "2026-09-20",
             "commute": "scooter", "mood": "energetic", "personal_color": "autumn",
             "lucky": {"birth_year": 1998, "zodiac": "leo", "apply": false}, "surprise": true}}
```

| field | module | what it does (examples) |
|---|---|---|
| lat/lon/event_date | `context/weather.py` (Open-Meteo, free) | feels-like temp -> warmth level; rain -> water-repellent outerwear; UV -> light colours; big day/night swing -> 洋蔥式 layering |
| commute | `context/commute.py` | 機車族 + rain -> water-repellent, no long skirts; MRT -> 冷氣房 layering |
| event_date | `context/festival.py` + `resources/tw_festivals.json` | 中秋烤肉 -> dark casual; 春節 -> red/gold; 尾牙 -> formal + shine; 萬聖節 -> bold. Lunar dates checked against the Hong Kong Observatory tables |
| mood | `context/personal.py` | energetic -> saturated colours; low -> soft knit; adventurous -> avant-garde |
| personal_color | `context/personal.py`, quiz in `context/quiz.py` | 四季色彩 palettes |
| lucky | `context/lucky.py` | 今日幸運色（僅供娛樂）; display-only unless `apply: true` |
| surprise | `diversify.py` | 驚喜款: last card replaced by the boldest candidate that still fits every condition (needs a `boldness` column) |

Each ranking signal is one additive term `context:<source>` (un-normalised, |weight| <= 0.5),
so the card reads e.g. 「明天新竹體感 30°C → 短袖、透氣輕薄最實在（+0.35）」 and
`Σ contributions == score` still holds. At most two context reasons are shown per card; all of
them stay in `contributions`. No context -> no terms -> ranking identical to before.

`ENGINE02_DEMO=1` never goes to the network on `/rank`: pre-fetch with `POST /context/forecast`
and the cached forecast is used.

## Endpoints

| endpoint | what |
|---|---|
| `POST /context/signals` | all signals for a situation, incl. display-only ones |
| `POST /context/forecast` | pre-fetch (network) so the offline demo can use it |
| `GET/POST /context/quiz` | 5-question personal-colour quiz |
| `POST /context/demand` | 情境需求雷達 for the manufacturer: next N days of weather + festivals -> demand shifts, catalog supply gaps, production lead-time calendar |
| `POST /services/capsule` | 旅行打包膠囊衣櫥: destination forecast -> N items -> most mix-and-match outfits |
| `POST /services/dress-code` | 服裝規定解碼器 (incl. 喝喜酒 etiquette: 白色留給新娘) |
| `POST /services/rent-or-buy` | 租還是買; cost-per-wear from the listed price, or from the estimate labelled 「估計價約 N 元（非實際標價）」 |
| `POST /services/itinerary` | 行程表: `{origin:{city}, events:[{date, city, time, occasion}]}` -> per-stop weather or 5-year climate normal, a ready-to-send `/rank` context and top items per stop, one capsule for the whole trip, packing notes |
| `GET /inspiration?group=runway\|street\|cosplay` | 381 inspiration photos from Wikimedia Commons (`data/inspiration/`, shipped), each with licence and author (attribution is required); posters, crowds, talks, close-ups and swimwear/lingerie screened out by `engine02.inspiration.screen` |
| `POST /inspiration/{id}/recommend` | "我想要這種感覺": ranks purchasable items with the photo folded in at weight 0.2 |

## Travel (context fields `origin_city`, `event_time`, `transport`)

Send city names only -- `{"city": "札幌", "origin_city": "台北", "event_date": "2026-11-03", "event_time": "19:00"}`:
coordinates are geocoded (Open-Meteo; a zh->en alias table because it does not find "札幌"),
then distance and transport (flight / HSR / car ...), the origin-vs-destination temperature gap,
and -- beyond the ~16-day forecast -- a 5-year historical normal for those dates, labelled
「歷史平均，非預報」. `event_time` uses the hourly value at that hour. Live example:

- 台北 → 札幌 約 2,696 km・飛行約 4.1 小時
- 長途飛行約 4 小時：舒服、不易皺 → 軟針織、寬鬆版型
- 台北 23°C → 札幌 8°C：落差 15°C，洋蔥式穿搭＋一件可脫的外套（往年平均）

## The ENGINE 01 path carries context too

`POST /intent/rank` and both `POST /retrieve` services accept `"context": {...}` next to `"intent"`.
Malformed context is a 422 naming the field. A context term that is not what put a card on the
slate is kept in `reason_contributions` but not cited in the reason sentence (the minimal
sufficient-set rule), so a black jacket is never "recommended because it is 30°C".

## Next

Measure before promoting any of these from "intuition" to a default: the H&M catalog
(`scripts/prepare_catalog_hm.py`) has material words in 99.5% of descriptions, which is what the
weather term needs to be validated (docs/research/context-weather-recsys.md explains why KAGL could not).
