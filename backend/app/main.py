from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_feedback, routes_meta, routes_query
from app.config import settings
from app.core.data_loader import load_dataset
from app.core.feedback_store import ensure_log_exists

app = FastAPI(title="Intelligent Analytics Query Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    load_dataset()
    ensure_log_exists()


app.include_router(routes_query.router, prefix="/api")
app.include_router(routes_feedback.router, prefix="/api")
app.include_router(routes_meta.router, prefix="/api")
