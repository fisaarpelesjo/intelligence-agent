from datetime import date

from catalogo_semantico import Catalogo
from execucao_query.fake_data_source import FakeDataSource
from interacao_conversacional import QuestionIntent, responder
from interacao_conversacional.llm_provider_stub import LLMProviderStub
from interacao_conversacional.vocabulario_periodo import resolve_period


def test_metrica_desconhecida_e_repassada_como_abstencao(catalogo: Catalogo) -> None:
    intent = QuestionIntent(metric_id="metrica_que_nao_existe", period_expression="hoje")

    resultado = responder(
        intent,
        catalogo,
        data_source=FakeDataSource(),
        llm_provider=LLMProviderStub(),
        reference_today=date(2026, 8, 15),
        max_bytes=10_000_000,
        max_rows=1_000,
    )

    assert resultado.success is False
    assert resultado.reason_code == "unknown_metric"


def test_expressao_de_periodo_desconhecida_pede_clarificacao(catalogo: Catalogo) -> None:
    intent = QuestionIntent(metric_id="signups", period_expression="mes_que_vem")

    resultado = responder(
        intent,
        catalogo,
        data_source=FakeDataSource(),
        llm_provider=LLMProviderStub(),
        reference_today=date(2026, 8, 15),
        max_bytes=10_000_000,
        max_rows=1_000,
    )

    assert resultado.success is False
    assert resultado.reason_code == "clarification_needed"


def test_expressao_desconhecida_diretamente_no_resolvedor_retorna_none() -> None:
    assert resolve_period("mes_que_vem", date(2026, 8, 15)) is None


def test_todas_as_expressoes_do_vocabulario_resolvem() -> None:
    expressoes = [
        "hoje",
        "ontem",
        "esta_semana",
        "semana_passada",
        "este_mes",
        "mes_passado",
        "este_trimestre",
        "trimestre_passado",
        "este_ano",
        "ano_passado",
    ]
    for expressao in expressoes:
        assert resolve_period(expressao, date(2026, 8, 15)) is not None
