from __future__ import annotations

from .modelos import DataSource, ExecutionOutcome, ExecutionReasonCode, Operator, QueryRequest


def _denied(reason: ExecutionReasonCode) -> ExecutionOutcome:
    return ExecutionOutcome(success=False, reason_code=reason)


def _filter_is_valid(request: QueryRequest) -> ExecutionReasonCode | None:
    query_filter = request.filter
    if query_filter is None:
        return None
    if not isinstance(query_filter.operator, Operator) or not query_filter.values:
        return ExecutionReasonCode.OPERATOR_NOT_ALLOWED
    resolved = request.decision.resolved_metric_version
    if resolved is None or query_filter.dimension_id not in resolved.allowed_dimensions:
        return ExecutionReasonCode.DIMENSION_NOT_ALLOWED
    return None


def executar(
    request: QueryRequest,
    data_source: DataSource,
    max_bytes: int,
    max_rows: int,
) -> ExecutionOutcome:
    if not request.decision.allowed:
        return _denied(ExecutionReasonCode.NOT_AUTHORIZED)

    filter_error = _filter_is_valid(request)
    if filter_error is not None:
        return _denied(filter_error)

    try:
        estimate = data_source.dry_run(request)
    except Exception:
        return _denied(ExecutionReasonCode.DATA_SOURCE_UNAVAILABLE)

    if estimate.estimated_bytes > max_bytes:
        return _denied(ExecutionReasonCode.COST_CEILING_EXCEEDED)
    if estimate.estimated_rows > max_rows:
        return _denied(ExecutionReasonCode.ROW_CEILING_EXCEEDED)

    try:
        result = data_source.execute(request)
    except Exception:
        return _denied(ExecutionReasonCode.DATA_SOURCE_UNAVAILABLE)

    return ExecutionOutcome(success=True, result=result)
