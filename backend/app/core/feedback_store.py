from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings

FIELDNAMES = ["timestamp", "query", "generated_sql", "rating", "corrected_sql", "notes"]
MAX_EXAMPLES_IN_PROMPT = 5


@dataclass
class FeedbackRow:
    timestamp: str
    query: str
    generated_sql: str
    rating: str
    corrected_sql: str
    notes: str


def ensure_log_exists() -> None:
    if not settings.feedback_log_csv.exists():
        settings.feedback_log_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.feedback_log_csv, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def append_feedback(query: str, generated_sql: str, rating: str, corrected_sql: str, notes: str) -> int:
    ensure_log_exists()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "generated_sql": generated_sql,
        "rating": rating,
        "corrected_sql": corrected_sql or "",
        "notes": notes or "",
    }
    with open(settings.feedback_log_csv, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(row)
    return len(read_all_feedback())


def read_all_feedback() -> list[FeedbackRow]:
    ensure_log_exists()
    with open(settings.feedback_log_csv, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            FeedbackRow(
                timestamp=r.get("timestamp", ""),
                query=r.get("query", ""),
                generated_sql=r.get("generated_sql", ""),
                rating=r.get("rating", ""),
                corrected_sql=r.get("corrected_sql", ""),
                notes=r.get("notes", ""),
            )
            for r in reader
        ]


def _tokenize(text: str) -> set[str]:
    return {w.strip(".,?!'\"()").lower() for w in text.split() if w.strip(".,?!'\"()")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def get_correction_examples(question: str, limit: int = MAX_EXAMPLES_IN_PROMPT) -> list[FeedbackRow]:
    """Rank past thumbs-down corrections by keyword overlap with the new question
    (plus recency as a tiebreaker), and return the top few for use as few-shot
    corrective examples in the prompt."""
    rows = [r for r in read_all_feedback() if r.rating == "down" and r.corrected_sql]
    if not rows:
        return []

    q_tokens = _tokenize(question)
    scored = []
    for idx, row in enumerate(rows):
        similarity = _jaccard(q_tokens, _tokenize(row.query))
        scored.append((similarity, idx, row))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [row for _, _, row in scored[:limit]]


def format_corrections_block(examples: list[FeedbackRow]) -> str:
    if not examples:
        return ""
    lines = ["LEARN FROM PAST USER CORRECTIONS (avoid repeating these mistakes):"]
    for ex in examples:
        lines.append(f'- Question: "{ex.query}"')
        lines.append(f"  Wrong SQL: {ex.generated_sql}")
        lines.append(f"  Corrected SQL: {ex.corrected_sql}")
        if ex.notes:
            lines.append(f"  Why: {ex.notes}")
    return "\n".join(lines)
