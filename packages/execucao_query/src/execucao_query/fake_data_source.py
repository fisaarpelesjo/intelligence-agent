from __future__ import annotations

from .modelos import CostEstimate, QueryRequest, QueryResult


class FakeDataSource:
    """Implementacao em memoria de `DataSource`, para testes e uso local.

    Nao le nem escreve nada real; retorna valores configurados no construtor.
    """

    def __init__(
        self,
        estimate: CostEstimate | None = None,
        result: QueryResult | None = None,
        fail_dry_run: bool = False,
        fail_execute: bool = False,
    ) -> None:
        self._estimate = estimate or CostEstimate(estimated_bytes=1_000, estimated_rows=10)
        self._result = result or QueryResult(
            value=42.0, unit="count", source_view="fake_view", rows_returned=1
        )
        self._fail_dry_run = fail_dry_run
        self._fail_execute = fail_execute
        self.dry_run_calls = 0
        self.execute_calls = 0

    def dry_run(self, request: QueryRequest) -> CostEstimate:
        self.dry_run_calls += 1
        if self._fail_dry_run:
            raise RuntimeError("dry_run indisponivel (falha simulada)")
        return self._estimate

    def execute(self, request: QueryRequest) -> QueryResult:
        self.execute_calls += 1
        if self._fail_execute:
            raise RuntimeError("execute indisponivel (falha simulada)")
        return self._result
