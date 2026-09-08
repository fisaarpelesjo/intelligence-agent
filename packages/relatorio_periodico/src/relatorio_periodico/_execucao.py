from __future__ import annotations

from datetime import date

from catalogo_semantico import Catalogo, decidir
from execucao_query import DataSource, Operator, QueryFilter, QueryRequest, QueryResult, executar


def executar_metrica(
    catalogo: Catalogo,
    data_source: DataSource,
    metric_id: str,
    dimension_id: str | None,
    dimension_value: str | None,
    day: date,
    max_bytes: int,
    max_rows: int,
) -> QueryResult | str:
    decision = decidir(catalogo, metric_id, dimension_id, day, day, audit_sink=[])
    if not decision.allowed:
        return decision.reason_code.value if decision.reason_code else "unknown_metric"

    query_filter = None
    if dimension_id is not None:
        query_filter = QueryFilter(
            dimension_id=dimension_id, operator=Operator.EQ, values=(dimension_value or "",)
        )
    request = QueryRequest(decision=decision, filter=query_filter, period_start=day, period_end=day)
    outcome = executar(request, data_source, max_bytes, max_rows)
    if not outcome.success or outcome.result is None:
        return outcome.reason_code.value if outcome.reason_code else "data_source_unavailable"
    return outcome.result
