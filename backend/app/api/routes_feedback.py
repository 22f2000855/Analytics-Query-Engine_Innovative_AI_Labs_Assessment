from fastapi import APIRouter

from app.core.feedback_store import append_feedback
from app.models.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
def post_feedback(request: FeedbackRequest) -> FeedbackResponse:
    stored_rows = append_feedback(
        query=request.query,
        generated_sql=request.generated_sql,
        rating=request.rating,
        corrected_sql=request.corrected_sql or "",
        notes=request.notes or "",
    )
    return FeedbackResponse(stored_rows=stored_rows)
