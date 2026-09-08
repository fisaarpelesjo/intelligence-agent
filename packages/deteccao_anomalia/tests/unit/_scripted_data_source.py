from __future__ import annotations

from datetime import date

from execucao_query import CostEstimate, QueryRequest, QueryResult


class ScriptedDataSource:
    """DataSource de teste cujo valor depende do dia pedido (dict data -> valor).

    Um dia ausente do dict faz `execute` levantar KeyError, que `execucao_query.executar`
    traduz em `data_source_unavailable` — util para simular indisponibilidade de um dia
    especifico da janela de baseline ou do dia observado.
    """

    def __init__(self, values_by_date: dict[date, float]) -> None:
        self._values = values_by_date

    def dry_run(self, request: QueryRequest) -> CostEstimate:
        return CostEstimate(estimated_bytes=1, estimated_rows=1)

    def execute(self, request: QueryRequest) -> QueryResult:
        value = self._values[request.period_start]
        return QueryResult(value=value, unit="count", source_view="signups_v2", rows_returned=1)
