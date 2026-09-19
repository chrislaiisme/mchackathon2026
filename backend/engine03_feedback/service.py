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
)


STAR_TO_WEIGHT: dict[int, float] = {
    1: -1.0,
    2: -0.5,
    3: 0.0,
    4: 0.5,
    5: 1.0,
}


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
                action_sign = 1.0 if feedback.favorited else -1.0
                for field, value in feedback.design_attributes.items():
                    mapped = {
                        axis: coefficient * action_sign
                        for axis, coefficient in generated_attribute_axes(field, value).items()
                    }
                    for engine02_axis, weight in mapped.items():
                        weights_by_attribute[engine02_axis].append(weight)
                    generated_evidence.append(GeneratedAttributeEvidence(
                        round=feedback_round.round,
                        item_id=feedback.item_id,
                        action=action,
                        field=field,
                        value=value,
                        mapped_axes=mapped,
                    ))
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
        choice_history.append(ChoiceRecord(
            shown_item_ids=feedback_round.shown_item_ids,
            # ENGINE 02's ChoiceRecord supports one primary choice per round.
            # All favorites are still preserved in chosen_item_ids for Rocchio.
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
    )
