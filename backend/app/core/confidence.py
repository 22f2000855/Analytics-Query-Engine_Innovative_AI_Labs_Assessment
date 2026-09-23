from __future__ import annotations

from app.models.schemas import ConfidenceBreakdown

REPAIR_DECAY = 0.7
EMPTY_RESULT_MULTIPLIER = 0.85
UNRESOLVED_ENTITY_MULTIPLIER = 0.8


def compute_confidence(
    llm_confidence: float,
    repair_count: int,
    execution_success: bool,
    row_count: int,
    unresolved_entities: int = 0,
) -> ConfidenceBreakdown:
    if not execution_success:
        return ConfidenceBreakdown(
            llm_confidence=llm_confidence,
            repair_count=repair_count,
            repair_penalty=0.0,
            empty_result_penalty_applied=False,
            unresolved_entities=unresolved_entities,
            unresolved_entity_penalty_applied=False,
            final_score=0.0,
        )

    score = llm_confidence
    repair_penalty = REPAIR_DECAY**repair_count
    score *= repair_penalty

    empty_penalty_applied = row_count == 0
    if empty_penalty_applied:
        score *= EMPTY_RESULT_MULTIPLIER

    entity_penalty_applied = unresolved_entities > 0
    if entity_penalty_applied:
        score *= UNRESOLVED_ENTITY_MULTIPLIER

    final_score = round(max(0.0, min(1.0, score)), 2)

    return ConfidenceBreakdown(
        llm_confidence=llm_confidence,
        repair_count=repair_count,
        repair_penalty=repair_penalty,
        empty_result_penalty_applied=empty_penalty_applied,
        unresolved_entities=unresolved_entities,
        unresolved_entity_penalty_applied=entity_penalty_applied,
        final_score=final_score,
    )


def count_unresolved_entities(where_literals: list[str], entity_values: dict[str, set[str]]) -> int:
    """Count string literals from the SQL that don't match any known value in any
    entity-bearing column. Cheap heuristic: a literal is "unresolved" only if it
    doesn't match ANY known value across ANY tracked column (avoids false positives
    for date strings, 'NA' region code, etc. which are legitimate exact matches)."""
    all_known_values = {v for values in entity_values.values() for v in values}
    unresolved = 0
    for literal in where_literals:
        if literal in all_known_values:
            continue
        # Skip values that look like dates or numbers embedded as strings.
        if literal.count("-") == 2 or literal.replace(".", "", 1).isdigit():
            continue
        # Skip values that are substrings used for LIKE-style partial matches.
        if any(literal.lower() in v.lower() or v.lower() in literal.lower() for v in all_known_values):
            continue
        unresolved += 1
    return unresolved
