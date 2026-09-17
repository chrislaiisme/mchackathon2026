# Interface Contract — ENGINE01 ↔ ENGINE02 ↔ ENGINE03 ↔ Frontend

**Status: draft v1, written by the ENGINE01 owner to unblock parallel development. Needs sign-off from whoever owns ENGINE02/03/frontend before it's final — flag any field you need renamed or added.**

The Python source of truth is [`backend/shared/schemas.py`](../backend/shared/schemas.py) (Pydantic models). This doc explains *why* the fields exist and gives example JSON; if the two ever disagree, the code wins.

## Why this exists

Per the planning doc's dev-split section: the 5 lines can only actually work in parallel if the JSON shape between them is agreed before coding starts, because the 2 on-site days don't leave room to renegotiate field names mid-build. This is that agreement, in its first draft form.

## 1. Structured intent (`Intent`)

Produced by ENGINE01, consumed by ENGINE02 (to build the search query) and ENGINE03 (to know what to correct).

```json
{
  "item_type": "外套",
  "colors": ["黑色"],
  "occasion": "正式場合",
  "budget_min": null,
  "budget_max": 3000,
  "style_keywords": ["簡約", "剪裁俐落"],
  "material": "秋冬材質",
  "season": "秋冬",
  "fit": null,
  "pattern": null,
  "collar": null,
  "inferred_fields": ["season"],
  "notes": null
}
```

- Every field is optional except the container itself — an empty/unclear sentence just yields a mostly-null intent plus clarifying questions.
- `inferred_fields` lists which of the above field names were filled in by GPT's contextual guess (weather, season, etc.) rather than stated by the user. Frontend must render these visibly different (e.g. "system inferred: 秋冬") — this is the concrete implementation of the "可解釋" requirement: nothing in the intent panel is unlabeled.
- `colors` / `style_keywords` are lists because a sentence can name more than one.

## 2. Clarifying question (`ClarifyingQuestion`)

Produced by ENGINE01 whenever the current `Intent` is too sparse/ambiguous to search well. Same shape is reused every round (not just round 1).

```json
{
  "field": "occasion",
  "question": "這件外套主要會在什麼場合穿？",
  "options": [
    {"id": "casual", "label": "日常休閒"},
    {"id": "work", "label": "上班／正式"},
    {"id": "date", "label": "約會／社交"}
  ],
  "allow_free_text": true
}
```

Frontend always renders a free-text box alongside the options (`allow_free_text` is expected to stay `true` in practice, but the field exists in case a question is options-only).

## 3. Feedback input (`FeedbackInput`)

Produced by the frontend (user/judge), consumed by ENGINE03. Recommended products and the generated concept image are scored **separately** — this is deliberate per the brief, so ENGINE03 can tell which branch (retrieval vs. generation) to adjust.

```json
{
  "session_id": "abc123",
  "round": 1,
  "target": "recommended",
  "attribute_scores": [
    {"attribute": "color", "score": 0.8, "comment": null},
    {"attribute": "fit", "score": 0.3, "comment": "太正式了"}
  ],
  "free_text": "整體不錯，但希望休閒一點",
  "selected_option_id": null
}
```

`target` is `"recommended"` or `"generated"` — the frontend sends one `FeedbackInput` per branch when the user rates both.

## 4. Feedback result (`FeedbackResult`)

Produced by ENGINE03, consumed by ENGINE01 (updated intent) and ENGINE02/generation (weight adjustments) to drive the next round.

```json
{
  "session_id": "abc123",
  "round": 2,
  "updated_intent": { "...": "same shape as Intent, with corrections applied" },
  "weight_adjustments": [
    {"field": "fit", "delta": -0.4, "reason": "使用者覺得太正式，降低正式風格權重"}
  ]
}
```

## 5. Retrieval result (`RetrievalResult`)

Produced by ENGINE02 + the generation module together (they run in parallel and their outputs are combined into one response for the frontend).

```json
{
  "session_id": "abc123",
  "round": 1,
  "products": [
    {
      "product_id": "polyvore_123",
      "image_url": "https://...",
      "title": "Slim wool blazer",
      "attributes": {"color": "black", "material": "wool"},
      "score": 0.91,
      "reason": "符合你要求的黑色、正式場合，剪裁俐落"
    }
  ],
  "concept_image": {
    "image_url": "https://...",
    "prompt_used": "一件簡約風格的黑色正式場合外套，剪裁俐落，秋冬材質",
    "response_id": "resp_abc"
  },
  "match_score": 0.62
}
```

- `match_score` is the "符合度分數" shown before/after feedback in the live demo (e.g. "62% → 89%") — it's the concrete, on-stage proof that the feedback loop works, so don't drop this field.
- `concept_image.response_id` is the OpenAI Responses API id, kept so the generation module can pass it as `previous_response_id` on the next round instead of starting the image from scratch.

## Open questions for the other engine owners

- Exact `attributes` keys on `ProductCard` — depends on what fields the Polyvore dataset actually exposes cleanly; ENGINE02 owner should confirm/extend.
- Whether `weight_adjustments` needs a fixed enum of `field` values or stays free-form text keyed by whatever `Intent`/ranking-signal name applies — currently free-form, tighten if ENGINE02/03 need stricter matching.
- Units/scale for `AttributeScore.score` and `RetrievalResult.match_score` — currently both 0–1 floats; confirm this works for however ENGINE03's weight math is implemented.
