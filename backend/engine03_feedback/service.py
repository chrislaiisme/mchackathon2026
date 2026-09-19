"""Deterministic ENGINE 03 transformation from UI feedback to ENGINE 02 operations."""

from __future__ import annotations

import json
from collections.abc import Iterable

from .contracts import (
    AdjustOp,
    AnchorOp,
    ChoiceOp,
    Engine3Request,
    Engine3Response,
    ExcludeItemOp,
    FeedbackOp,
    FeedbackRound,
    RejectedOperation,
)


LOW_SCORE = 0.4
HIGH_SCORE = 0.6


def _score_ops(
    request: Engine3Request,
) -> tuple[list[FeedbackOp], list[RejectedOperation]]:
    """Map 0..1 ratings to one discrete ENGINE 02 step; the neutral band is a no-op."""

    allowed = set(request.allowed_design_elements)
    ops: list[FeedbackOp] = []
    rejected: list[RejectedOperation] = []
    for rating in request.attribute_scores:
        wire = {"op": "adjust", "element": rating.element, "score": rating.score}
        if rating.element not in allowed:
            rejected.append(
                RejectedOperation(
                    operation=wire,
                    reason=(
                        f"unknown design element {rating.element!r}; "
                        "refresh ENGINE 02 /kansei"
                    ),
                )
            )
            continue
        if rating.score < LOW_SCORE:
            ops.append(AdjustOp(element=rating.element, step=-1))
        elif rating.score > HIGH_SCORE:
            ops.append(AdjustOp(element=rating.element, step=1))
    return ops, rejected


def _interaction_ops(
    request: Engine3Request,
) -> tuple[list[FeedbackOp], list[RejectedOperation]]:
    """Translate explicit buttons exactly; never infer interaction state from scores."""

    interaction = request.interaction
    shown_ids = [item.item_id for item in request.engine02_response.items]
    shown = set(shown_ids)
    ops: list[FeedbackOp] = []
    rejected: list[RejectedOperation] = []

    if interaction.chosen_item_id or interaction.rejected_item_ids:
        referenced = set(interaction.rejected_item_ids)
        if interaction.chosen_item_id:
            referenced.add(interaction.chosen_item_id)
        unknown = sorted(referenced - shown)
        operation = {
            "op": "choice",
            "shown_item_ids": shown_ids,
            "chosen_item_id": interaction.chosen_item_id,
            "rejected_item_ids": interaction.rejected_item_ids,
        }
        if unknown:
            rejected.append(
                RejectedOperation(
                    operation=operation,
                    reason=f"choice item ids were not shown this round: {unknown}",
                )
            )
        else:
            ops.append(ChoiceOp(**operation))

    if interaction.excluded_item_ids:
        unknown = sorted(set(interaction.excluded_item_ids) - shown)
        operation = {"op": "exclude_item", "item_ids": interaction.excluded_item_ids}
        if unknown:
            rejected.append(
                RejectedOperation(
                    operation=operation,
                    reason=f"excluded item ids were not shown this round: {unknown}",
                )
            )
        else:
            ops.append(ExcludeItemOp(**operation))

    if interaction.anchor_item_ids:
        # Anchors may come from the wardrobe or an earlier round, so they need not be in this slate.
        ops.append(
            AnchorOp(
                item_ids=interaction.anchor_item_ids,
                replace=interaction.replace_anchors,
            )
        )
    return ops, rejected


def _deduplicate(ops: Iterable[FeedbackOp]) -> list[FeedbackOp]:
    result: list[FeedbackOp] = []
    seen: set[str] = set()
    for op in ops:
        key = json.dumps(op.model_dump(mode="json"), sort_keys=True)
        if key not in seen:
            result.append(op)
            seen.add(key)
    return result


def process_feedback(request: Engine3Request) -> Engine3Response:
    """Return deterministic ENGINE 02 operations; no LLM or natural-language state is involved."""

    score_ops, score_rejected = _score_ops(request)
    interaction_ops, interaction_rejected = _interaction_ops(request)
    return Engine3Response(
        engine02_feedback=FeedbackRound(
            session_id=request.session_id,
            round=request.round,
            utterance=None,
            ops=_deduplicate([*score_ops, *interaction_ops]),
        ),
        rejected_ops=[*score_rejected, *interaction_rejected],
    )
