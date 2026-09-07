from datetime import date

from catalogo_semantico import AccessDecision
from execucao_query import ExecutionReasonCode, QueryRequest, executar
from execucao_query.fake_data_source import FakeDataSource


def _request(decisao: AccessDecision) -> QueryRequest:
    return QueryRequest(
        decision=decisao,
        filter=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )


def test_falha_no_dry_run_vira_recusa_nomeada(decisao_permitida: AccessDecision) -> None:
    fonte = FakeDataSource(fail_dry_run=True)

    resultado = executar(_request(decisao_permitida), fonte, max_bytes=1_000, max_rows=100)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.DATA_SOURCE_UNAVAILABLE


def test_falha_no_execute_vira_recusa_nomeada(decisao_permitida: AccessDecision) -> None:
    fonte = FakeDataSource(fail_execute=True)

    resultado = executar(_request(decisao_permitida), fonte, max_bytes=1_000_000, max_rows=1_000)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.DATA_SOURCE_UNAVAILABLE
