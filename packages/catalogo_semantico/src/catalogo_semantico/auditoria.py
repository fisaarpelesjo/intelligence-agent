from __future__ import annotations

from datetime import date

from .modelos import AccessDecision, AuditEvent


def emitir_evento(
    decisao: AccessDecision,
    metric_id: str,
    dimension_id: str | None,
    period_start: date,
    period_end: date,
) -> AuditEvent:
    return AuditEvent(
        metric_id=metric_id,
        dimension_id=dimension_id,
        period_start=period_start,
        period_end=period_end,
        decision=decisao,
    )
