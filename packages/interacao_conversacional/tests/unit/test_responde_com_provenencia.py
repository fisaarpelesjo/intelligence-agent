from datetime import date

from catalogo_semantico import Catalogo
from execucao_query.fake_data_source import FakeDataSource
from interacao_conversacional import QuestionIntent, responder
from interacao_conversacional.llm_provider_stub import LLMProviderStub


def test_pergunta_valida_retorna_resposta_com_provenencia(catalogo: Catalogo) -> None:
    intent = QuestionIntent(
        metric_id="signups",
        dimension_id="country",
        dimension_value="BR",
        period_expression="mes_passado",
    )

    resultado = responder(
        intent,
        catalogo,
        data_source=FakeDataSource(),
        llm_provider=LLMProviderStub(),
        reference_today=date(2026, 8, 15),
        max_bytes=10_000_000,
        max_rows=1_000,
    )

    assert resultado.success is True
    assert resultado.resolved_period is not None
    assert resultado.resolved_period.start == date(2026, 7, 1)
    assert resultado.resolved_period.end == date(2026, 7, 31)
    assert len(resultado.sentences) >= 1
