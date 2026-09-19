"""The shared shapes every context module produces and the pipeline consumes. Keep this file stable:
parallel modules (weather, festival, personal options, services, demand) are written against it.

Catalog columns a preference may refer to (agreed names; a catalog without a column simply gives
that preference no effect -- never an error):

  color            str    catalog colour vocabulary (engine02/attribute_fill.py COLOR_FAMILIES)
  category         str    top | bottom | dress | outerwear | shoes | bag | ...
  warmth           int    0 = very light (tank, sandals) .. 3 = very warm (puffer, wool coat)
  water_repellent  bool   the item's own text says water-repellent / waterproof
  boldness         int    0 basic .. 3 avant-garde   (scripts/vlm_fill_catalog.py)
  style            str    minimalist | streetwear | classic | sporty | bohemian | romantic |
                          edgy | vintage | preppy | avant_garde
  occasion         str    Casual | Formal | Smart Casual | Sports | Travel | Ethnic
  season           str    Spring | Summer | Fall | Winter
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_SIGNAL_WEIGHT = 0.5          # one context signal can never outweigh what the user said


@dataclass
class AttributePref:
    """A soft preference over one catalog column.

    Exactly one of `values` (categorical: the item scores `weight` if its value is in the list)
    or `target` (numeric: the item scores `weight * (1 - |value - target| / scale)`) is set.
    `weight` may be negative (e.g. rain -> suede shoes -0.2). |weight| <= MAX_SIGNAL_WEIGHT.
    """
    column: str
    weight: float
    reason: str                              # shown on the card when this preference contributes
    values: list | None = None
    target: float | None = None
    scale: float = 3.0                       # numeric distance at which the preference reaches 0

    def __post_init__(self):
        if (self.values is None) == (self.target is None):
            raise ValueError("AttributePref needs exactly one of `values` or `target`")
        if abs(self.weight) > MAX_SIGNAL_WEIGHT:
            raise ValueError(f"|weight| {self.weight} exceeds MAX_SIGNAL_WEIGHT {MAX_SIGNAL_WEIGHT}")


@dataclass
class ContextSignal:
    source: str                              # weather | festival | commute | personal_color | mood | lucky_color | ...
    label: str                               # one line for the card, e.g. "明天新竹 16°C、降雨 70%"
    prefs: list[AttributePref] = field(default_factory=list)
    design_steps: dict[str, float] = field(default_factory=dict)   # kansei element id -> steps
    affects_ranking: bool = True             # False = shown to the user, not scored
    opt_in: bool = False                     # True = only exists because the user switched it on
    evidence: str = "opt-in, not measured"   # what justifies letting it rank
    detail: dict = field(default_factory=dict)   # raw inputs (forecast numbers, festival name ...)


@dataclass
class DailyForecast:
    """One day of weather at one place. Produced by context/weather.py; services take it as input
    (dependency injection) so they never need the network themselves."""
    date: str                                # ISO yyyy-mm-dd
    place: str
    lat: float
    lon: float
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    apparent_max_c: float | None = None
    apparent_min_c: float | None = None
    precip_prob_pct: float | None = None
    precip_mm: float | None = None
    wind_max_kmh: float | None = None
    uv_index_max: float | None = None
    source: str = "open-meteo"
    fetched_at: str | None = None
