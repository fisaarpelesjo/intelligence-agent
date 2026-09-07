from datetime import date

from catalogo_semantico import AccessDecision
from execucao_query import ExecutionReasonCode, Operator, QueryFilter, QueryRequest, executar
from execucao_query.fake_data_source import FakeDataSource


def test_operador_fora_da_allowlist_e_recusado_sem_tocar_a_fonte(
    decisao_permitida: AccessDecision,
) -> None:
    request = QueryRequest(
        decision=decisao_permitida,
        filter=QueryFilter(dimension_id="country", operator="regex", values=("BR",)),  # type: ignore[arg-type]
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    fonte = FakeDataSource()

    resultado = executar(request, fonte, max_bytes=10_000, max_rows=100)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.OPERATOR_NOT_ALLOWED
    assert fonte.dry_run_calls == 0
    assert fonte.execute_calls == 0


def test_decisao_negada_e_recusada_sem_tocar_a_fonte(decisao_negada: AccessDecision) -> None:
    request = QueryRequest(
        decision=decisao_negada,
        filter=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    fonte = FakeDataSource()

    resultado = executar(request, fonte, max_bytes=10_000, max_rows=100)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.NOT_AUTHORIZED
    assert fonte.dry_run_calls == 0
    assert fonte.execute_calls == 0


def test_lista_de_valores_vazia_e_recusada(decisao_permitida: AccessDecision) -> None:
    request = QueryRequest(
        decision=decisao_permitida,
        filter=QueryFilter(dimension_id="country", operator=Operator.IN, values=()),
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    fonte = FakeDataSource()

    resultado = executar(request, fonte, max_bytes=10_000, max_rows=100)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.OPERATOR_NOT_ALLOWED


def test_dimensao_fora_da_allowlist_da_versao_e_recusada(
    decisao_permitida: AccessDecision,
) -> None:
    request = QueryRequest(
        decision=decisao_permitida,
        filter=QueryFilter(dimension_id="payment_method", operator=Operator.EQ, values=("x",)),
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    fonte = FakeDataSource()

    resultado = executar(request, fonte, max_bytes=10_000, max_rows=100)

    assert resultado.success is False
    assert resultado.reason_code == ExecutionReasonCode.DIMENSION_NOT_ALLOWED
    assert fonte.dry_run_calls == 0
