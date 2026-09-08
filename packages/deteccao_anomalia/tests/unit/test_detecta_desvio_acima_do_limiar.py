from datetime import date, timedelta

from _scripted_data_source import ScriptedDataSource
from catalogo_semantico import Catalogo
from deteccao_anomalia import AnomalyRule, Direction, detectar

REFERENCE_TODAY = date(2026, 8, 15)
OBSERVED_DATE = REFERENCE_TODAY - timedelta(days=1)


def _values(observed: float, baseline: float, window_days: int) -> dict[date, float]:
    values = {OBSERVED_DATE: observed}
    for offset in range(1, window_days + 1):
        values[OBSERVED_DATE - timedelta(days=offset)] = baseline
    return values


def test_aumento_acima_do_limiar_dispara_finding_com_direcao_increase(
    catalogo: Catalogo,
) -> None:
    rule = AnomalyRule(metric_id="signups", window_days=7, threshold_pct=20)
    fonte = ScriptedDataSource(_values(observed=150, baseline=100, window_days=7))

    resultado = detectar(
        rule, catalogo, fonte, REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert resultado.triggered is True
    assert resultado.finding is not None
    assert resultado.finding.direction == Direction.INCREASE
    assert resultado.finding.deviation_pct == 50.0
    assert resultado.finding.baseline_value == 100.0


def test_queda_acima_do_limiar_dispara_finding_com_direcao_decrease(catalogo: Catalogo) -> None:
    rule = AnomalyRule(metric_id="signups", window_days=7, threshold_pct=20)
    fonte = ScriptedDataSource(_values(observed=60, baseline=100, window_days=7))

    resultado = detectar(
        rule, catalogo, fonte, REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert resultado.triggered is True
    assert resultado.finding is not None
    assert resultado.finding.direction == Direction.DECREASE
    assert resultado.finding.deviation_pct == -40.0
