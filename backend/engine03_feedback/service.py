"""ENGINE 03 preference-feedback transformation."""

from __future__ import annotations

import json
import os
from typing import Iterable

from dotenv import load_dotenv
from openai import OpenAI

from .contracts import (
    AdjustOp,
    AnchorOp,
    ChoiceOp,
    CritiqueOp,
    Engine3Decision,
    Engine3Request,
    Engine3Response,
    ExcludeItemOp,
    ExcludeOp,
    FeedbackOp,
    FeedbackRound,
    FeelingOp,
    GenerationDecision,
    RejectedOperation,
    RequireOp,
)
from .prompts import GENERATION_SYSTEM_PROMPT, RECOMMENDATION_SYSTEM_PROMPT

load_dotenv()


def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for text, selected-option, or attribute-score feedback; "
            "click-only feedback can run without it"
        )
    return OpenAI(api_key=api_key)


def _canonical_value(value: str, allowed: list[str]) -> str | None:
    if not allowed:
        return value
    lookup = {candidate.casefold(): candidate for candidate in allowed}
    return lookup.get(value.casefold())


def _feedback_utterance(request: Engine3Request, target: str = "recommended") -> str | None:
    messages: list[str] = []
    for feedback in request.feedback_inputs:
        if feedback.target == target and feedback.free_text and feedback.free_text not in messages:
            messages.append(feedback.free_text)
    return "；".join(messages) or None


def _requires_language_model(request: Engine3Request, target: str = "recommended") -> bool:
    return any(
        feedback.target == target
        and (
        feedback.free_text
        or feedback.selected_option_id
        or feedback.attribute_scores
        )
        for feedback in request.feedback_inputs
    )


def _validate_ops(
    request: Engine3Request, ops: Iterable[FeedbackOp]
) -> tuple[list[FeedbackOp], list[RejectedOperation]]:
    valid: list[FeedbackOp] = []
    rejected: list[RejectedOperation] = []
    shown_ids = {item.item_id for item in request.engine02_response.items}
    need_ids = {need.need_id for need in request.engine02_request.needs}
    element_ids = set(request.allowed_design_elements)

    for op in ops:
        reason: str | None = None
        if isinstance(op, (ExcludeOp, RequireOp)):
            canonical = _canonical_value(
                op.value, request.allowed_attribute_values.get(op.attribute, [])
            )
            if canonical is None:
                reason = f"unknown {op.attribute} value {op.value!r}; refresh ENGINE 02 /vocabulary"
            else:
                op.value = canonical
        elif isinstance(op, AdjustOp) and element_ids and op.element not in element_ids:
            reason = f"unknown design element {op.element!r}; refresh ENGINE 02 /kansei"
        elif isinstance(op, CritiqueOp):
            if op.reference_item_id not in shown_ids:
                reason = f"reference item {op.reference_item_id!r} was not shown in this round"
            elif op.attribute is None and op.direction is None:
                reason = "critique needs attribute+to_value or direction"
            elif op.attribute and op.to_value:
                canonical = _canonical_value(
                    op.to_value, request.allowed_attribute_values.get(op.attribute, [])
                )
                if canonical is None:
                    reason = f"unknown critique value {op.to_value!r}; refresh ENGINE 02 /vocabulary"
                else:
                    op.to_value = canonical
        elif isinstance(op, FeelingOp):
            unknown = set(op.need_log_likelihood) - need_ids
            if op.needs_override is not None:
                unknown |= {need.need_id for need in op.needs_override} - need_ids
            if unknown:
                reason = f"unknown need ids: {sorted(unknown)}; refresh ENGINE 02 /kansei"
            elif not op.need_log_likelihood and op.needs_override is None:
                reason = "feeling requires need_log_likelihood or needs_override"
        elif isinstance(op, ChoiceOp):
            referenced = set(op.rejected_item_ids)
            if op.chosen_item_id:
                referenced.add(op.chosen_item_id)
            unknown = referenced - shown_ids
            if unknown:
                reason = f"choice item ids were not shown this round: {sorted(unknown)}"
        elif isinstance(op, ExcludeItemOp):
            unknown = set(op.item_ids) - shown_ids
            if unknown:
                reason = f"excluded item ids were not shown this round: {sorted(unknown)}"

        if reason:
            rejected.append(RejectedOperation(operation=op.model_dump(mode="json"), reason=reason))
        else:
            valid.append(op)
    return valid, rejected


def _interaction_ops(request: Engine3Request) -> list[FeedbackOp]:
    interaction = request.interaction
    shown_ids = [item.item_id for item in request.engine02_response.items]
    ops: list[FeedbackOp] = []
    if interaction.chosen_item_id or interaction.rejected_item_ids:
        ops.append(
            ChoiceOp(
                shown_item_ids=shown_ids,
                chosen_item_id=interaction.chosen_item_id,
                rejected_item_ids=interaction.rejected_item_ids,
            )
        )
    if interaction.excluded_item_ids:
        ops.append(ExcludeItemOp(item_ids=interaction.excluded_item_ids))
    if interaction.anchor_item_ids:
        ops.append(AnchorOp(item_ids=interaction.anchor_item_ids, replace=interaction.replace_anchors))
    return ops


def _deduplicate(ops: Iterable[FeedbackOp]) -> list[FeedbackOp]:
    result: list[FeedbackOp] = []
    seen: set[str] = set()
    for op in ops:
        key = json.dumps(op.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        if key not in seen:
            result.append(op)
            seen.add(key)
    return result


def _feedback_for_target(request: Engine3Request, target: str) -> list[dict]:
    return [
        item.model_dump(mode="json")
        for item in request.feedback_inputs
        if item.target == target
    ]


def _model_decision(request: Engine3Request) -> Engine3Decision:
    context = {
        "base_intent": request.current_intent.model_dump(mode="json"),
        "feedback_intent": request.feedback_intent.model_dump(mode="json"),
        # Target separation is enforced before the model call, not trusted to prompting alone.
        "feedback_inputs": _feedback_for_target(request, "recommended"),
        "engine02_request": request.engine02_request.model_dump(mode="json"),
        "shown_items": [item.model_dump(mode="json") for item in request.engine02_response.items],
        "interaction": request.interaction.model_dump(mode="json"),
        "allowed_design_elements": request.allowed_design_elements,
        "allowed_attribute_values": request.allowed_attribute_values,
    }
    response = _client().beta.chat.completions.parse(
        model=os.environ.get("ENGINE3_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": RECOMMENDATION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        response_format=Engine3Decision,
        temperature=0.1,
    )
    decision = response.choices[0].message.parsed
    if decision is None:
        raise RuntimeError("model returned no parsed ENGINE 03 decision")
    return decision


def _generation_decision(request: Engine3Request) -> GenerationDecision:
    context = {
        "current_intent": request.current_intent.model_dump(mode="json"),
        "feedback_inputs": _feedback_for_target(request, "generated"),
    }
    response = _client().beta.chat.completions.parse(
        model=os.environ.get("ENGINE3_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        response_format=GenerationDecision,
        temperature=0.1,
    )
    decision = response.choices[0].message.parsed
    if decision is None:
        raise RuntimeError("model returned no parsed generation decision")
    return decision


def process_feedback(request: Engine3Request) -> Engine3Response:
    """Return a validated ENGINE 02 FeedbackRound and ENGINE 01 Intent."""
    if _requires_language_model(request, "recommended"):
        decision = _model_decision(request)
    else:
        decision = Engine3Decision(
            reasoning="依照使用者在介面上的明確操作更新回饋帳本。",
            ops=[],
            updated_intent=request.current_intent,
        )

    generation = (
        _generation_decision(request)
        if _requires_language_model(request, "generated")
        else None
    )

    # IDs come from explicit UI actions. Any LLM-produced ID operation is
    # discarded to prevent hallucinated products and duplicate evidence.
    language_ops = [
        op for op in decision.ops if not isinstance(op, (ChoiceOp, AnchorOp, ExcludeItemOp))
    ]
    valid_ops, rejected = _validate_ops(request, language_ops)
    ui_ops, ui_rejected = _validate_ops(request, _interaction_ops(request))

    return Engine3Response(
        reasoning=decision.reasoning,
        engine02_feedback=FeedbackRound(
            session_id=request.engine02_response.session_id,
            round=request.engine02_response.round,
            utterance=_feedback_utterance(request, "recommended"),
            ops=_deduplicate([*valid_ops, *ui_ops]),
        ),
        updated_intent=decision.updated_intent,
        generation_prompt=generation.generation_prompt if generation else None,
        generation_adjustments=generation.adjustments if generation else [],
        rejected_ops=[*rejected, *ui_rejected],
    )
