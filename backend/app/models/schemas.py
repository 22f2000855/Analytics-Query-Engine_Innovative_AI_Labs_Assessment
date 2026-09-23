from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str


class GenerationOutput(BaseModel):
    """Structured contract Gemini must fill in for every generation/repair call."""

    understood: str = Field(description="Plain-language restatement of what the user is asking for")
    sql: str = Field(description="A single Snowflake SQL SELECT statement that answers the question")
    reasoning: str = Field(description="Which tables, joins, aggregations, or window functions were used and why")
    assumptions: list[str] = Field(default_factory=list, description="Any assumptions made to resolve ambiguity")
    confidence: float = Field(ge=0.0, le=1.0, description="Model's own confidence in the SQL, 0-1")


class ConfidenceBreakdown(BaseModel):
    llm_confidence: float
    repair_count: int
    repair_penalty: float
    empty_result_penalty_applied: bool
    unresolved_entities: int
    unresolved_entity_penalty_applied: bool
    final_score: float


class ExecutionMeta(BaseModel):
    success: bool
    row_count: int
    truncated: bool
    duration_ms: float
    error: Optional[str] = None


class QueryMeta(BaseModel):
    model: str
    understood: str
    assumptions: list[str] = Field(default_factory=list)
    repair_count: int
    used_self_repair: bool
    execution: ExecutionMeta
    confidence_breakdown: ConfidenceBreakdown


class QueryResponse(BaseModel):
    query: str
    generated_logic: str
    result: Any
    confidence_score: float
    explanation: str
    meta: QueryMeta


class FeedbackRequest(BaseModel):
    query: str
    generated_sql: str
    rating: Literal["up", "down"]
    corrected_sql: Optional[str] = ""
    notes: Optional[str] = ""


class FeedbackResponse(BaseModel):
    status: Literal["ok"] = "ok"
    stored_rows: int
