from datetime import date

from catalogo_semantico import Catalogo
from execucao_query import CostEstimate, QueryResult
from execucao_query.fake_data_source import FakeDataSource
from interacao_conversacional import QuestionIntent, responder
from interacao_conversacional.llm_provider_stub import LLMProviderStub

REFERENCE_TODAY = date(2026, 8, 15)


def test_comparacao_entre_periodo_completo_e_parcial_e_recusada(catalogo: Catalogo) -> None:
    intent = QuestionIntent(
        metric_id="active_users",
        period_expression="este_mes",
        baseline_period_expression="mes_passado",
    )

    resultado = responder(
        intent,
        catalogo,
        data_source=FakeDataSource(),
        llm_provider=LLMProviderStub(),
        reference_today=REFERENCE_TODAY,
        max_bytes=10_000_000,
        max_rows=1_000,
    )

    assert resultado.success is False
    assert resultado.reason_code == "not_comparable_window"


def test_comparacao_entre_dois_periodos_parciais_e_permitida(catalogo: Catalogo) -> None:
    intent = QuestionIntent(
        metric_id="active_users",
        period_expression="este_mes",
        baseline_period_expression="este_trimestre",
    )

    resultado = responder(
        intent,
        catalogo,
        data_source=FakeDataSource(),
        llm_provider=LLMProviderStub(),
        reference_today=REFERENCE_TODAY,
        max_bytes=10_000_000,
        max_rows=1_000,
    )

    assert resultado.success is True
    comparacoes = [s for s in resultado.sentences if s.claim_class == "CALCULATED_COMPARISON"]
    assert len(comparacoes) == 1


def test_comparacao_com_baseline_zero_e_recusada(catalogo: Catalogo) -> None:
    intent = QuestionIntent(
        metric_id="active_users",
        period_expression="este_mes",
        baseline_period_expression="este_trimestre",
    )
    fonte = FakeDataSource(
        estimate=CostEstimate(estimated_bytes=1, estimated_rows=1),
        result=QueryResult(value=0.0, unit="count", source_view="mau", rows_returned=1),
    )

    resultado = responder(
        intent,
        catalogo,
        data_source=fonte,
        llm_provider=LLMProviderStub(),
        reference_today=REFERENCE_TODAY,
        max_bytes=10_000_000,
        max_rows=1_000,
    )

    assert resultado.success is False
    assert resultado.reason_code == "zero_baseline"
