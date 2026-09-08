from datetime import date

from catalogo_semantico import Catalogo
from execucao_query import CostEstimate, QueryResult
from execucao_query.fake_data_source import FakeDataSource
from relatorio_periodico import AlertDirection, AlertRule, avaliar_alertas

REFERENCE_TODAY = date(2026, 8, 15)


def _fonte(value: float) -> FakeDataSource:
    return FakeDataSource(
        estimate=CostEstimate(estimated_bytes=1, estimated_rows=1),
        result=QueryResult(value=value, unit="count", source_view="signups_v2", rows_returned=1),
    )


def test_alerta_dispara_quando_valor_ultrapassa_limiar_acima(catalogo: Catalogo) -> None:
    rules = [AlertRule(metric_id="signups", threshold=100, direction=AlertDirection.ABOVE)]

    bundle = avaliar_alertas(
        rules, catalogo, _fonte(150), REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert bundle.evaluation_date == date(2026, 8, 14)
    assert bundle.alert_results[0].evaluated is True
    assert bundle.alert_results[0].triggered is True


def test_alerta_nao_dispara_quando_valor_nao_ultrapassa_limiar(catalogo: Catalogo) -> None:
    rules = [AlertRule(metric_id="signups", threshold=100, direction=AlertDirection.ABOVE)]

    bundle = avaliar_alertas(
        rules, catalogo, _fonte(50), REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert bundle.alert_results[0].triggered is False


def test_alerta_com_metrica_indisponivel_nao_avalia_e_nao_lanca_excecao(
    catalogo: Catalogo,
) -> None:
    rules = [
        AlertRule(metric_id="metrica_que_nao_existe", threshold=100, direction=AlertDirection.ABOVE)
    ]

    bundle = avaliar_alertas(
        rules, catalogo, FakeDataSource(), REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert bundle.alert_results[0].evaluated is False
    assert bundle.alert_results[0].triggered is False
    assert bundle.alert_results[0].reason_code == "unknown_metric"
