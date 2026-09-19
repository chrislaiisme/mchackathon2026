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


def frontend_attribute_catalog() -> dict:
    return {
        "rating_scale": {"1": -1.0, "2": -0.5, "3": 0.0, "4": 0.5, "5": 1.0},
        "attributes": [attribute.model_dump() for attribute in ATTRIBUTE_DEFINITIONS],
    }
