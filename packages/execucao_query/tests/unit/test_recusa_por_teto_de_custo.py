from datetime import date

from catalogo_semantico import AccessDecision
from execucao_query import CostEstimate, ExecutionReasonCode, QueryRequest, executar
from execucao_query.fake_data_source import FakeDataSource


def _request(decisao: AccessDecision) -> QueryRequest:
    return QueryRequest(
        decision=decisao,
        filter=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )


def test_estimativa_de_bytes_acima_do_teto_e_recusada(decisao_permitida: AccessDecision) -> None:
    fonte = FakeDataSource(estimate=CostEstimate(estimated_bytes=1_000_000, estimated_rows=1))

    resultado = executar(_request(decisao_permitida), fonte, max_bytes=1_000, max_rows=100)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.COST_CEILING_EXCEEDED
    assert fonte.execute_calls == 0


def test_estimativa_de_linhas_acima_do_teto_e_recusada(decisao_permitida: AccessDecision) -> None:
    fonte = FakeDataSource(estimate=CostEstimate(estimated_bytes=1, estimated_rows=10_000))

    resultado = executar(_request(decisao_permitida), fonte, max_bytes=1_000_000, max_rows=100)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.ROW_CEILING_EXCEEDED
    assert fonte.execute_calls == 0


def test_estimativa_dentro_dos_tetos_executa_uma_vez(decisao_permitida: AccessDecision) -> None:
    fonte = FakeDataSource(estimate=CostEstimate(estimated_bytes=10, estimated_rows=1))

    resultado = executar(_request(decisao_permitida), fonte, max_bytes=1_000, max_rows=100)

    assert resultado.success is True
    assert fonte.execute_calls == 1
