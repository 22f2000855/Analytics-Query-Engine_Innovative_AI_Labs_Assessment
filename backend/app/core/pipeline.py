from __future__ import annotations

from app.config import settings
from app.core import gemini_client
from app.core.confidence import compute_confidence, count_unresolved_entities
from app.core.data_loader import get_loaded_dataset
from app.core.dictionary import compute_time_facts, load_data_dictionary
from app.core.explanation import build_explanation
from app.core.feedback_store import get_correction_examples
from app.core.prompt_builder import build_repair_prompt, build_system_prompt
from app.core.sql_executor import ExecutionResult, execute_sql
from app.core.sql_validator import validate_sql
from app.models.schemas import ExecutionMeta, QueryMeta, QueryResponse


def run_pipeline(question: str) -> QueryResponse:
    dataset = get_loaded_dataset()
    dictionary = load_data_dictionary()
    time_facts = compute_time_facts(dataset.reference_date)
    corrections = get_correction_examples(question)
    system_prompt = build_system_prompt(dataset, dictionary, time_facts, corrections)

    generation = gemini_client.generate(system_prompt, question)

    repair_count = 0
    repair_reason: str | None = None
    execution: ExecutionResult | None = None

    while True:
        validation = validate_sql(generation.sql)
        if not validation.ok:
            failure_reason = validation.error or "SQL failed validation."
            execution = ExecutionResult(
                success=False, rows=[], row_count=0, truncated=False, duration_ms=0.0, error=failure_reason
            )
        else:
            execution = execute_sql(generation.sql)
            failure_reason = execution.error

        if execution.success or repair_count >= settings.max_repair_attempts - 1:
            break

        repair_count += 1
        repair_reason = failure_reason
        repair_prompt = build_repair_prompt(question, generation.sql, failure_reason or "unknown error")
        generation = gemini_client.repair(system_prompt, repair_prompt)

    unresolved_entities = 0
    if validation.ok and validation.where_literals:
        unresolved_entities = count_unresolved_entities(validation.where_literals, dataset.entity_values)

    confidence = compute_confidence(
        llm_confidence=generation.confidence,
        repair_count=repair_count,
        execution_success=execution.success,
        row_count=execution.row_count,
        unresolved_entities=unresolved_entities,
    )

    explanation = build_explanation(
        generation=generation,
        execution=execution,
        repair_count=repair_count,
        repair_reason=repair_reason,
        confidence=confidence,
    )

    result: object
    if execution.success:
        result = execution.rows
    else:
        result = None

    meta = QueryMeta(
        model=settings.gemini_model,
        understood=generation.understood,
        assumptions=generation.assumptions,
        repair_count=repair_count,
        used_self_repair=repair_count > 0,
        execution=_to_execution_meta(execution),
        confidence_breakdown=confidence,
    )

    return QueryResponse(
        query=question,
        generated_logic=generation.sql,
        result=result,
        confidence_score=confidence.final_score,
        explanation=explanation,
        meta=meta,
    )


def _to_execution_meta(execution: ExecutionResult) -> ExecutionMeta:
    return ExecutionMeta(
        success=execution.success,
        row_count=execution.row_count,
        truncated=execution.truncated,
        duration_ms=execution.duration_ms,
        error=execution.error,
    )
