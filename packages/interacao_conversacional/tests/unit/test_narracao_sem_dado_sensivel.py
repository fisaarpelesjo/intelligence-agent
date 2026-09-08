import dataclasses
from datetime import date

from catalogo_semantico import Catalogo
from execucao_query.fake_data_source import FakeDataSource
from interacao_conversacional import (
    ClaimClass,
    ClaimSentence,
    NarrationPayload,
    QuestionIntent,
    responder,
)


class SpyLLMProvider:
    def __init__(self) -> None:
        self.received_payload: NarrationPayload | None = None

    def narrar(self, payload: NarrationPayload) -> list[ClaimSentence]:
        self.received_payload = payload
        return [ClaimSentence(text="ok", claim_class=ClaimClass.FACTUAL_RESULT)]


def test_toda_sentenca_tem_claim_class_valida(catalogo: Catalogo) -> None:
    from interacao_conversacional.llm_provider_stub import LLMProviderStub

    intent = QuestionIntent(
        metric_id="signups", dimension_id="country", period_expression="mes_passado"
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
    for sentenca in resultado.sentences:
        assert sentenca.claim_class in set(ClaimClass)


def test_payload_de_narracao_nao_contem_campo_de_identidade_ou_texto_livre(
    catalogo: Catalogo,
) -> None:
    spy = SpyLLMProvider()
    intent = QuestionIntent(
        metric_id="signups", dimension_id="country", period_expression="mes_passado"
    )

    responder(
        intent,
        catalogo,
        data_source=FakeDataSource(),
        llm_provider=spy,
        reference_today=date(2026, 8, 15),
        max_bytes=10_000_000,
        max_rows=1_000,
    )

    assert spy.received_payload is not None
    campos = {f.name for f in dataclasses.fields(spy.received_payload)}
    assert campos == {"metric_id", "value", "unit", "source_view", "period_label", "comparison"}
