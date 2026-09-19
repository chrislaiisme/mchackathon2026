"""Deterministic conversion from a round of item feedback to ENGINE 02 input."""

from __future__ import annotations

from collections import defaultdict

from .attributes import ATTRIBUTE_MAP, generated_attribute_axes
from .contracts import (
    AttributeEvidence,
    ChoiceRecord,
    Engine02Feedback,
    Engine3Request,
    Engine3Response,
    GeneratedAttributeEvidence,
    OutfitEvidence,
)


STAR_TO_WEIGHT: dict[int, float] = {
    1: -1.0,
    2: -0.5,
    3: 0.0,
    4: 0.5,
    5: 1.0,
}


def _apply_generated_action(
    *,
    round_number: int,
    item_id: str,
    design_attributes: dict[str, str],
    action: str,
    weights_by_attribute: dict[str, list[float]],
    evidence: list[GeneratedAttributeEvidence],
) -> None:
    """Translate a generated favorite/dislike without leaking its id to ENGINE 02."""

    action_sign = 1.0 if action == "favorite" else -1.0
    for field, value in design_attributes.items():
        mapped = {
            axis: coefficient * action_sign
            for axis, coefficient in generated_attribute_axes(field, value).items()
        }
        for engine02_axis, weight in mapped.items():
            weights_by_attribute[engine02_axis].append(weight)
        evidence.append(GeneratedAttributeEvidence(
            round=round_number,
            item_id=item_id,
            action=action,
            field=field,
            value=value,
            mapped_axes=mapped,
        ))


def process_feedback(request: Engine3Request) -> Engine3Response:
    """Combine the previous three rounds plus the current round for ENGINE 02.

    Multiple ratings for the same attribute are averaged. This keeps the
    round-level delta on the same [-1, 1] scale regardless of how many cards
    the user rated, while ``attribute_evidence`` preserves every item-level
    signal for explanation and auditing.
    """

    rounds = [*request.previous_rounds, request]
    item_status: dict[str, str] = {}
    choice_history: list[ChoiceRecord] = []
    evidence: list[AttributeEvidence] = []
    generated_evidence: list[GeneratedAttributeEvidence] = []
    outfit_evidence: list[OutfitEvidence] = []
    weights_by_attribute: dict[str, list[float]] = defaultdict(list)

    for feedback_round in rounds:
        round_chosen: list[str] = []
        round_rejected: list[str] = []
        for feedback in feedback_round.item_feedbacks:
            if feedback.source == "catalog" and feedback.favorited:
                item_status[feedback.item_id] = "chosen"
                round_chosen.append(feedback.item_id)
            if feedback.source == "catalog" and feedback.disliked:
                item_status[feedback.item_id] = "rejected"
                round_rejected.append(feedback.item_id)
            if feedback.source == "generated" and (feedback.favorited or feedback.disliked):
                action = "favorite" if feedback.favorited else "dislike"
                _apply_generated_action(
                    round_number=feedback_round.round,
                    item_id=feedback.item_id,
                    design_attributes=feedback.design_attributes,
                    action=action,
                    weights_by_attribute=weights_by_attribute,
                    evidence=generated_evidence,
                )
            for rating in feedback.attribute_ratings:
                weight = STAR_TO_WEIGHT[rating.stars]
                for engine02_axis, coefficient in ATTRIBUTE_MAP[rating.attribute].items():
                    weights_by_attribute[engine02_axis].append(weight * coefficient)
                evidence.append(AttributeEvidence(
                    round=feedback_round.round,
                    item_id=feedback.item_id,
                    source=feedback.source,
                    attribute=rating.attribute,
                    stars=rating.stars,
                    weight=weight,
                ))
        for outfit in feedback_round.outfit_feedbacks:
            catalog_ids: list[str] = []
            generated_ids: list[str] = []
            for item in outfit.items:
                if item.source == "catalog":
                    item_status[item.item_id] = "chosen"
                    catalog_ids.append(item.item_id)
                else:
                    generated_ids.append(item.item_id)
                    _apply_generated_action(
                        round_number=feedback_round.round,
                        item_id=item.item_id,
                        design_attributes=item.design_attributes,
                        action="favorite",
                        weights_by_attribute=weights_by_attribute,
                        evidence=generated_evidence,
                    )
            outfit_evidence.append(OutfitEvidence(
                round=feedback_round.round,
                outfit_id=outfit.outfit_id,
                catalog_item_ids=catalog_ids,
                generated_item_ids=generated_ids,
            ))

        # Outfit favorites are deliberately excluded: ChoiceRecord can represent only
        # one chosen item, so inserting the pair would create false preference history.
        if round_chosen or round_rejected:
            choice_history.append(ChoiceRecord(
                shown_item_ids=feedback_round.shown_item_ids,
                chosen_item_id=round_chosen[0] if round_chosen else None,
                rejected_item_ids=round_rejected,
            ))

    chosen_item_ids = [item_id for item_id, status in item_status.items() if status == "chosen"]
    rejected_item_ids = [item_id for item_id, status in item_status.items() if status == "rejected"]

    # A neutral-only ENGINE 02 axis is omitted because sending 0 changes nothing.
    design_weight_delta = {
        attribute: sum(weights) / len(weights)
        for attribute, weights in weights_by_attribute.items()
        if abs(sum(weights)) > 1e-12
    }

    return Engine3Response(
        session_id=request.session_id,
        round=request.round,
        window_rounds=[item.round for item in rounds],
        engine02_feedback=Engine02Feedback(
            chosen_item_ids=chosen_item_ids,
            rejected_item_ids=rejected_item_ids,
            choice_history=choice_history,
            design_weight_delta=design_weight_delta,
        ),
        attribute_evidence=evidence,
        generated_attribute_evidence=generated_evidence,
        outfit_evidence=outfit_evidence,
    )
