"""Frontend-facing labels for ENGINE 02's default Kansei design axes."""

from __future__ import annotations

from pydantic import BaseModel


class AttributeDefinition(BaseModel):
    id: str
    label_zh: str
    prompt_zh: str
    effect_zh: str
    maps_to: dict[str, float]


def _attribute(id_: str, label: str, effect: str, maps_to: dict[str, float]) -> AttributeDefinition:
    return AttributeDefinition(
        id=id_,
        label_zh=label,
        prompt_zh=f"你喜歡這件商品的「{label}」嗎？",
        effect_zh=effect,
        maps_to=maps_to,
    )


# The frontend sees only these three directions. ENGINE 03 expands each rating
# into ENGINE 02's 15 default Kansei axes. Antonym pairs use ±0.5 on each pole:
# ENGINE 02 folds one pole into the other with a sign flip, producing a net ±1
# instead of accidentally double-counting the same bipolar axis.
ATTRIBUTE_DEFINITIONS: tuple[AttributeDefinition, ...] = (
    _attribute(
        "visual_impact",
        "醒目亮眼感",
        "星等越高，下一輪越偏向明亮、光澤、醒目圖案與明顯 Logo；越低則偏向深色、霧面與極簡。",
        {
            "dark_tone": -0.5,
            "bright_color": 0.5,
            "matte_fabric": -0.5,
            "glossy_fabric": 0.5,
            "visible_logo": 1.0,
            "minimal_design": -0.5,
            "bold_pattern": 0.5,
        },
    ),
    _attribute(
        "polished_formality",
        "俐落正式感",
        "星等越高，下一輪越偏向挺拔肩線、合身剪裁、正式風格與俐落領型。",
        {
            "structured_shoulders": 1.0,
            "relaxed_fit": -0.5,
            "tailored_fit": 0.5,
            "formal_style": 0.5,
            "casual_style": -0.5,
            "crisp_collar": 1.0,
        },
    ),
    _attribute(
        "soft_energy",
        "柔軟動感",
        "星等越高，下一輪越偏向柔軟針織與運動機能風。",
        {
            "soft_knit": 1.0,
            "athletic_style": 1.0,
        },
    ),
)

ATTRIBUTE_IDS = frozenset(attribute.id for attribute in ATTRIBUTE_DEFINITIONS)
ATTRIBUTE_MAP = {attribute.id: dict(attribute.maps_to) for attribute in ATTRIBUTE_DEFINITIONS}
ENGINE02_AXIS_IDS = frozenset(axis for mapping in ATTRIBUTE_MAP.values() for axis in mapping)


def _opposite_pair(positive: str, negative: str) -> dict[str, float]:
    """Represent one bipolar preference without double-counting after E2 folds antonyms."""
    return {positive: 0.5, negative: -0.5}


def generated_attribute_axes(field: str, value: str) -> dict[str, float]:
    """Map explicit generated-cell metadata to existing ENGINE 02 axes.

    Unknown or ambiguous values return an empty mapping and are reported as evidence instead of
    being guessed.
    """
    key = field.strip().lower().replace("-", "_")
    text = value.strip().lower().replace("-", " ").replace("_", " ")

    if key == "fit":
        if text in {"loose", "oversized", "relaxed", "baggy"}:
            return _opposite_pair("relaxed_fit", "tailored_fit")
        if text in {"tight", "slim", "fitted", "tailored"}:
            return _opposite_pair("tailored_fit", "relaxed_fit")
        return {}

    if key == "pattern":
        if text in {"solid", "plain", "unpatterned", "minimal"}:
            return _opposite_pair("minimal_design", "bold_pattern")
        if text:
            return _opposite_pair("bold_pattern", "minimal_design")

    if key == "material":
        if any(token in text for token in ("knit", "cotton", "wool", "cashmere")):
            return {"soft_knit": 1.0}
        if any(token in text for token in ("satin", "silk", "glossy")):
            return _opposite_pair("glossy_fabric", "matte_fabric")
        if "matte" in text:
            return _opposite_pair("matte_fabric", "glossy_fabric")
        return {}

    if key in {"colors", "color"}:
        if any(token in text for token in (
            "black", "navy", "charcoal", "dark", "maroon", "burgundy", "brown", "coffee",
        )):
            return _opposite_pair("dark_tone", "bright_color")
        if any(token in text for token in (
            "white", "light", "bright", "yellow", "orange", "gold", "silver", "lime",
            "turquoise", "pink", "magenta", "rose", "peach",
        )):
            return _opposite_pair("bright_color", "dark_tone")
        return {}

    if key in {"collar", "neckline"}:
        if text in {"shirt collar", "polo collar", "collared", "stand collar"}:
            return {"crisp_collar": 1.0}
        if text in {"crew", "v neck", "scoop", "boat", "square", "hood", "halter"}:
            return {"crisp_collar": -1.0}
        return {}

    if key in {"style", "style_keywords"}:
        if any(token in text for token in ("formal", "business", "professional")):
            return _opposite_pair("formal_style", "casual_style")
        if any(token in text for token in ("casual", "relaxed")):
            return _opposite_pair("casual_style", "formal_style")
        if any(token in text for token in ("sporty", "athletic", "active")):
            return {"athletic_style": 1.0}

    return {}


def frontend_attribute_catalog() -> dict:
    return {
        "rating_scale": {"1": -1.0, "2": -0.5, "3": 0.0, "4": 0.5, "5": 1.0},
        "attributes": [attribute.model_dump() for attribute in ATTRIBUTE_DEFINITIONS],
    }
