from datetime import date, timedelta

from _scripted_data_source import ScriptedDataSource
from catalogo_semantico import Catalogo
from deteccao_anomalia import AnomalyRule, detectar

REFERENCE_TODAY = date(2026, 8, 15)
OBSERVED_DATE = REFERENCE_TODAY - timedelta(days=1)


def test_desvio_dentro_do_limiar_nao_dispara(catalogo: Catalogo) -> None:
    rule = AnomalyRule(metric_id="signups", window_days=7, threshold_pct=20)
    values = {OBSERVED_DATE: 105.0}
    for offset in range(1, 8):
        values[OBSERVED_DATE - timedelta(days=offset)] = 100.0
    fonte = ScriptedDataSource(values)

    resultado = detectar(
        rule, catalogo, fonte, REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert resultado.triggered is False
    assert resultado.finding is None
    assert resultado.reason_code is None


def test_baseline_incompleta_nao_dispara_e_nomeia_motivo(catalogo: Catalogo) -> None:
    rule = AnomalyRule(metric_id="signups", window_days=7, threshold_pct=20)
    values = {OBSERVED_DATE: 150.0}
    for offset in range(1, 7):  # falta um dos 7 dias da janela
        values[OBSERVED_DATE - timedelta(days=offset)] = 100.0
    fonte = ScriptedDataSource(values)

    resultado = detectar(
        rule, catalogo, fonte, REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert resultado.triggered is False
    assert resultado.reason_code == "baseline_incompleta"


def test_baseline_zero_nao_dispara_e_nomeia_motivo(catalogo: Catalogo) -> None:
    rule = AnomalyRule(metric_id="signups", window_days=3, threshold_pct=20)
    values = {OBSERVED_DATE: 10.0}
    for offset in range(1, 4):
        values[OBSERVED_DATE - timedelta(days=offset)] = 0.0
    fonte = ScriptedDataSource(values)

    resultado = detectar(
        rule, catalogo, fonte, REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert resultado.triggered is False
    assert resultado.reason_code == "baseline_zero"


def test_dia_observado_indisponivel_nao_calcula_baseline(catalogo: Catalogo) -> None:
    rule = AnomalyRule(metric_id="signups", window_days=3, threshold_pct=20)
    fonte = ScriptedDataSource({})  # nenhum dia disponivel, nem o observado

    resultado = detectar(
        rule, catalogo, fonte, REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert resultado.triggered is False
    assert resultado.reason_code == "observado_indisponivel"


def test_janela_invalida_e_recusada_sem_tocar_a_fonte(catalogo: Catalogo) -> None:
    rule = AnomalyRule(metric_id="signups", window_days=0, threshold_pct=20)
    fonte = ScriptedDataSource({})

    resultado = detectar(
        rule, catalogo, fonte, REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert resultado.triggered is False
    assert resultado.reason_code == "janela_invalida"
