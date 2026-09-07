from __future__ import annotations

from collections.abc import MutableSequence
from datetime import date

from .auditoria import emitir_evento
from .modelos import AccessDecision, AuditEvent, Catalogo, MetricDefinitionVersion, ReasonCode


def _resolve_version(
    versions: tuple[MetricDefinitionVersion, ...], period_start: date, period_end: date
) -> AccessDecision | MetricDefinitionVersion:
    covering = [v for v in versions if v.covers(period_start, period_end)]
    if len(covering) == 1:
        return covering[0]
    overlapping = [v for v in versions if v.overlaps(period_start, period_end)]
    if not overlapping:
        return AccessDecision(allowed=False, reason_code=ReasonCode.NO_METRIC_VERSION_FOR_PERIOD)
    return AccessDecision(allowed=False, reason_code=ReasonCode.PERIOD_SPANS_VERSION_BOUNDARY)


def decidir(
    catalogo: Catalogo,
    metric_id: str,
    dimension_id: str | None,
    period_start: date,
    period_end: date,
    audit_sink: MutableSequence[AuditEvent],
) -> AccessDecision:
    metric = catalogo.metrics.get(metric_id)
    if metric is None:
        decisao = AccessDecision(allowed=False, reason_code=ReasonCode.UNKNOWN_METRIC)
        audit_sink.append(emitir_evento(decisao, metric_id, dimension_id, period_start, period_end))
        return decisao

    resolved = _resolve_version(metric.versions, period_start, period_end)
    if isinstance(resolved, AccessDecision):
        audit_sink.append(
            emitir_evento(resolved, metric_id, dimension_id, period_start, period_end)
        )
        return resolved

    if dimension_id is not None and dimension_id not in resolved.allowed_dimensions:
        decisao = AccessDecision(allowed=False, reason_code=ReasonCode.DIMENSION_NOT_ALLOWED)
        audit_sink.append(emitir_evento(decisao, metric_id, dimension_id, period_start, period_end))
        return decisao

    decisao = AccessDecision(allowed=True, resolved_metric_version=resolved)
    audit_sink.append(emitir_evento(decisao, metric_id, dimension_id, period_start, period_end))
    return decisao
