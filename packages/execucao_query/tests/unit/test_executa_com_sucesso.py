from datetime import date

from catalogo_semantico import AccessDecision
from execucao_query import Operator, QueryFilter, QueryRequest, executar
from execucao_query.fake_data_source import FakeDataSource


def test_execucao_com_filtro_retorna_resultado(decisao_permitida: AccessDecision) -> None:
    request = QueryRequest(
        decision=decisao_permitida,
        filter=QueryFilter(dimension_id="country", operator=Operator.EQ, values=("BR",)),
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    fonte = FakeDataSource()

    resultado = executar(request, fonte, max_bytes=10_000, max_rows=100)

    assert resultado.success is True
    assert resultado.result is not None
    assert resultado.result.unit == "count"
    assert fonte.execute_calls == 1


def test_execucao_sem_filtro_retorna_resultado_agregado(decisao_permitida: AccessDecision) -> None:
    request = QueryRequest(
        decision=decisao_permitida,
        filter=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    fonte = FakeDataSource()

    resultado = executar(request, fonte, max_bytes=10_000, max_rows=100)

    assert resultado.success is True
    assert fonte.execute_calls == 1
