from __future__ import annotations

from app.core.sql_executor import ExecutionResult
from app.models.schemas import ConfidenceBreakdown, GenerationOutput


def build_explanation(
    generation: GenerationOutput,
    execution: ExecutionResult,
    repair_count: int,
    repair_reason: str | None,
    confidence: ConfidenceBreakdown,
) -> str:
    understood = generation.understood
    if generation.assumptions:
        understood = understood.rstrip(".") + ". " + " ".join(generation.assumptions)
    parts = [f"Understood: {understood}"]

    reasoning = generation.reasoning
    if repair_count > 0 and repair_reason:
        reasoning = (
            reasoning.rstrip(".") + f". The first attempt failed ({repair_reason}); "
            f"it was automatically corrected and re-run ({repair_count} repair attempt(s))."
        )
    if not execution.success:
        reasoning = reasoning.rstrip(".") + f". The query did not run successfully: {execution.error}"
    parts.append(f"How generated: {reasoning}")

    if confidence.unresolved_entity_penalty_applied:
        parts.append(
            "Confidence was reduced because the query filters on a value that "
            "doesn't appear in the loaded dataset."
        )
    if confidence.empty_result_penalty_applied:
        parts.append("Confidence was reduced slightly because the query returned zero rows.")

    return "\n".join(parts)
