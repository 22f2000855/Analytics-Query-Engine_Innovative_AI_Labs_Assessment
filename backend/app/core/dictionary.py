from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date

from app.config import settings


@dataclass
class TimeFacts:
    today: str
    this_month: str
    last_month: str
    this_quarter_label: str
    this_quarter_start: str
    this_quarter_end: str
    last_quarter_label: str
    last_quarter_start: str
    last_quarter_end: str
    this_year: int
    last_year: int


def _quarter_bounds(year: int, quarter: int) -> tuple[str, str]:
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    start = date(year, start_month, 1)
    end = date(year, end_month, calendar.monthrange(year, end_month)[1])
    return start.isoformat(), end.isoformat()


def compute_time_facts(reference_date: date) -> TimeFacts:
    year, month = reference_date.year, reference_date.month
    quarter = (month - 1) // 3 + 1

    if month == 1:
        last_month_year, last_month_month = year - 1, 12
    else:
        last_month_year, last_month_month = year, month - 1

    if quarter == 1:
        last_q_year, last_q = year - 1, 4
    else:
        last_q_year, last_q = year, quarter - 1

    this_q_start, this_q_end = _quarter_bounds(year, quarter)
    last_q_start, last_q_end = _quarter_bounds(last_q_year, last_q)

    return TimeFacts(
        today=reference_date.isoformat(),
        this_month=f"{year:04d}-{month:02d}",
        last_month=f"{last_month_year:04d}-{last_month_month:02d}",
        this_quarter_label=f"Q{quarter} {year}",
        this_quarter_start=this_q_start,
        this_quarter_end=this_q_end,
        last_quarter_label=f"Q{last_q} {last_q_year}",
        last_quarter_start=last_q_start,
        last_quarter_end=last_q_end,
        this_year=year,
        last_year=year - 1,
    )


def load_data_dictionary() -> dict:
    with open(settings.data_dictionary_json, "r", encoding="utf-8") as f:
        return json.load(f)


def format_time_facts_block(facts: TimeFacts) -> str:
    return "\n".join(
        [
            f"- today (reference date, = latest order_date in sales_data) = {facts.today}",
            f"- this month = {facts.this_month}",
            f"- last month = {facts.last_month}",
            f"- this quarter = {facts.this_quarter_label} ({facts.this_quarter_start} to {facts.this_quarter_end})",
            f"- last quarter = {facts.last_quarter_label} ({facts.last_quarter_start} to {facts.last_quarter_end})",
            f"- this year = {facts.this_year}",
            f"- last year = {facts.last_year}",
            (
                "- IMPORTANT: this dataset only contains rows for 2024-01 through 2024-03. "
                "If a resolved period (e.g. last quarter, last year, YoY prior-year) falls "
                "outside that range, still write correct SQL against the real date values, "
                "but note this in `assumptions` and lower `confidence` — never invent numbers."
            ),
        ]
    )
