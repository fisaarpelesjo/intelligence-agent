from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from .modelos import ResolvedPeriod


def _start_of_week(reference: date) -> date:
    return reference - timedelta(days=reference.weekday())


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _quarter_bounds(year: int, quarter_index: int) -> tuple[date, date]:
    start_month = quarter_index * 3 + 1
    end_month = start_month + 2
    return date(year, start_month, 1), date(year, end_month, monthrange(year, end_month)[1])


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    zero_based = (month - 1) + delta
    return year + zero_based // 12, zero_based % 12 + 1


def _resolve(expression: str, reference_today: date) -> tuple[date, date] | None:
    if expression == "hoje":
        return reference_today, reference_today
    if expression == "ontem":
        ontem = reference_today - timedelta(days=1)
        return ontem, ontem
    if expression == "esta_semana":
        start = _start_of_week(reference_today)
        return start, start + timedelta(days=6)
    if expression == "semana_passada":
        start = _start_of_week(reference_today) - timedelta(days=7)
        return start, start + timedelta(days=6)
    if expression == "este_mes":
        return _month_bounds(reference_today.year, reference_today.month)
    if expression == "mes_passado":
        year, month = _shift_month(reference_today.year, reference_today.month, -1)
        return _month_bounds(year, month)
    if expression == "este_trimestre":
        return _quarter_bounds(reference_today.year, (reference_today.month - 1) // 3)
    if expression == "trimestre_passado":
        current_index = (reference_today.month - 1) // 3
        year, month = _shift_month(reference_today.year, current_index * 3 + 1, -3)
        return _quarter_bounds(year, (month - 1) // 3)
    if expression == "este_ano":
        return date(reference_today.year, 1, 1), date(reference_today.year, 12, 31)
    if expression == "ano_passado":
        return date(reference_today.year - 1, 1, 1), date(reference_today.year - 1, 12, 31)
    return None


def resolve_period(expression: str, reference_today: date) -> ResolvedPeriod | None:
    bounds = _resolve(expression, reference_today)
    if bounds is None:
        return None
    start, end = bounds
    return ResolvedPeriod(start=start, end=end, is_partial=end >= reference_today)
