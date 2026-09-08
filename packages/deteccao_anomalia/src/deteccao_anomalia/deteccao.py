from __future__ import annotations

from datetime import date, timedelta

from catalogo_semantico import Catalogo
from execucao_query import DataSource

from ._execucao import executar_metrica
from .modelos import AnomalyRule, CandidateFinding, DetectionOutcome, Direction


def _sem_finding(reason_code: str) -> DetectionOutcome:
    return DetectionOutcome(triggered=False, reason_code=reason_code)


def detectar(
    rule: AnomalyRule,
    catalogo: Catalogo,
    data_source: DataSource,
    reference_today: date,
    max_bytes: int,
    max_rows: int,
) -> DetectionOutcome:
    if rule.window_days < 1:
        return _sem_finding("janela_invalida")

    observed_date = reference_today - timedelta(days=1)
    observed_outcome = executar_metrica(
        catalogo,
        data_source,
        rule.metric_id,
        rule.dimension_id,
        rule.dimension_value,
        observed_date,
        max_bytes,
        max_rows,
    )
    if isinstance(observed_outcome, str):
        return _sem_finding("observado_indisponivel")

    baseline_values: list[float] = []
    for offset in range(1, rule.window_days + 1):
        day = observed_date - timedelta(days=offset)
        outcome = executar_metrica(
            catalogo,
            data_source,
            rule.metric_id,
            rule.dimension_id,
            rule.dimension_value,
            day,
            max_bytes,
            max_rows,
        )
        if isinstance(outcome, str):
            return _sem_finding("baseline_incompleta")
        baseline_values.append(outcome.value)

    baseline_value = sum(baseline_values) / len(baseline_values)
    if baseline_value == 0:
        return _sem_finding("baseline_zero")

    observed_value = observed_outcome.value
    deviation_pct = (observed_value - baseline_value) / baseline_value * 100

    if abs(deviation_pct) <= rule.threshold_pct:
        return DetectionOutcome(triggered=False)

    finding = CandidateFinding(
        metric_id=rule.metric_id,
        observed_date=observed_date,
        observed_value=observed_value,
        baseline_value=baseline_value,
        deviation_pct=deviation_pct,
        direction=Direction.INCREASE if deviation_pct > 0 else Direction.DECREASE,
        window_days=rule.window_days,
        threshold_pct=rule.threshold_pct,
    )
    return DetectionOutcome(triggered=True, finding=finding)
