import json

from fastapi import APIRouter

from app.config import settings
from app.core.data_loader import get_loaded_dataset, tables_exist

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok" if tables_exist() else "dataset_not_loaded",
        "model": settings.gemini_model,
        "gemini_api_key_configured": bool(settings.gemini_api_key),
    }


@router.get("/schema")
def schema():
    with open(settings.data_dictionary_json, "r", encoding="utf-8") as f:
        dictionary = json.load(f)
    dataset = get_loaded_dataset()
    return {
        "data_dictionary": dictionary,
        "schema_description": dataset.schema_description,
        "reference_date": dataset.reference_date.isoformat(),
    }


@router.get("/examples")
def examples():
    with open(settings.nl_queries_json, "r", encoding="utf-8") as f:
        return json.load(f)
