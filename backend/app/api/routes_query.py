from fastapi import APIRouter, HTTPException

from app.core.gemini_client import GeminiUnavailableError
from app.core.pipeline import run_pipeline
from app.models.schemas import QueryRequest, QueryResponse

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def post_query(request: QueryRequest) -> QueryResponse:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")
    try:
        return run_pipeline(request.query.strip())
    except GeminiUnavailableError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
