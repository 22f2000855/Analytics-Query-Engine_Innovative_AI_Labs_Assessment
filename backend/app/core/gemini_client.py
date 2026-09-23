from __future__ import annotations

import json
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from app.config import settings
from app.models.schemas import GenerationOutput

_client: genai.Client | None = None

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class GeminiUnavailableError(RuntimeError):
    """Raised when Gemini can't be reached, or fails, after retries are exhausted."""


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return exc.code in RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


def _call_with_retry(fn):
    last_exc: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                break
            time.sleep(BASE_DELAY_SECONDS * (2**attempt))

    raise GeminiUnavailableError(
        "Unable to reach the Gemini API right now. Please try again in a moment."
    ) from last_exc


def _parse_response(response) -> GenerationOutput:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, GenerationOutput):
        return parsed
    try:
        data = json.loads(response.text)
        return GenerationOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise GeminiUnavailableError(
            "The AI model returned an unexpected response format. Please try rephrasing your question."
        ) from exc


def _generate(system_prompt: str, user_message: str) -> GenerationOutput:
    client = get_client()

    def do_call():
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=[user_message],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=GenerationOutput,
                temperature=0.1,
            ),
        )

    response = _call_with_retry(do_call)
    return _parse_response(response)


def generate(system_prompt: str, question: str) -> GenerationOutput:
    return _generate(system_prompt, f"Question: {question}")


def repair(system_prompt: str, repair_message: str) -> GenerationOutput:
    return _generate(system_prompt, repair_message)
