"""ENGINE 02 fills in the situation itself when the caller does not send one.

ENGINE 01 sends an intent, not a situation, so without this the weather, festival and time-of-day
features never reach a real shopper. When a request's `context` is missing or partial:

  * event_date  -> today in Taiwan (UTC+8, no daylight saving)
  * event_time  -> the current hour, only when the date is today (a trip in November is not "now")
                   and only between 06:00 and 22:00: someone shopping at 1 a.m. is dressing for
                   the day, not for 1 a.m., so overnight only the day's weather is used
  * city        -> ENGINE02_DEFAULT_CITY with ENGINE02_DEFAULT_LAT / ENGINE02_DEFAULT_LON
                   (default 新竹市, 24.8138, 120.9675 -- the team is in Hsinchu), only when neither a
                   city nor coordinates were given

Whatever the caller sent always wins; only empty fields are filled, and every filled field is
reported back in `context_used.auto_filled`, so a card that says 「新竹市 28°C」 can show that the city
was assumed. The weather itself is fetched by engine02/context/weather.py (cached per day);
ENGINE02_DEMO=1 still never goes to the network -- pre-fetch with POST /context/forecast.

ENGINE02_AUTO_CONTEXT=0 turns this off (then no context means no context terms, as before).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from ..contracts import ContextInput

TAIWAN = timezone(timedelta(hours=8), "Asia/Taipei")
DAY_START, DAY_END = 6, 22


def enabled() -> bool:
    return os.environ.get("ENGINE02_AUTO_CONTEXT", "1").strip().lower() not in ("0", "false", "no", "off")


def default_place() -> dict:
    """The city assumed when the caller names none (the team demos in Hsinchu)."""
    return {"city": os.environ.get("ENGINE02_DEFAULT_CITY", "新竹市").strip() or "新竹市",
            "lat": float(os.environ.get("ENGINE02_DEFAULT_LAT", "24.8138")),
            "lon": float(os.environ.get("ENGINE02_DEFAULT_LON", "120.9675"))}


def auto_context(ctx: ContextInput | None, now: datetime | None = None) -> tuple[ContextInput | None, dict]:
    """(context with the empty fields filled, {field: value it was filled with})."""
    if not enabled():
        return ctx, {}
    now = (now or datetime.now(TAIWAN)).astimezone(TAIWAN)
    base = ctx or ContextInput()
    filled: dict = {}
    today = now.date().isoformat()
    if not base.event_date:
        filled["event_date"] = today
    if not base.event_time and (base.event_date or today) == today and DAY_START <= now.hour <= DAY_END:
        filled["event_time"] = f"{now.hour:02d}:00"
    if not base.city and (base.lat is None or base.lon is None):
        filled.update(default_place())
    if not filled:
        return base, {}
    return base.model_copy(update=filled), filled
