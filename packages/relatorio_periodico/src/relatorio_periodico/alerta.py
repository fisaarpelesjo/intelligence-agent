from __future__ import annotations

from datetime import date, timedelta

from catalogo_semantico import Catalogo
from execucao_query import DataSource

from ._execucao import executar_metrica
from .modelos import AlertBundle, AlertDirection, AlertResult, AlertRule


def _triggers(value: float, rule: AlertRule) -> bool:
    if rule.direction == AlertDirection.ABOVE:
        return value > rule.threshold
    return value < rule.threshold


def avaliar_alertas(
    rules: list[AlertRule],
    catalogo: Catalogo,
    data_source: DataSource,
    reference_today: date,
    max_bytes: int,
    max_rows: int,
) -> AlertBundle:
    evaluation_date = reference_today - timedelta(days=1)
    results: list[AlertResult] = []
    for rule in rules:
        outcome = executar_metrica(
            catalogo, data_source, rule.metric_id, None, None, evaluation_date, max_bytes, max_rows
        )
        if isinstance(outcome, str):
            results.append(
                AlertResult(
                    metric_id=rule.metric_id, evaluated=False, triggered=False, reason_code=outcome
                )
            )
        else:
            results.append(
                AlertResult(
                    metric_id=rule.metric_id,
                    evaluated=True,
                    triggered=_triggers(outcome.value, rule),
                    value=outcome.value,
                )
            )
    return AlertBundle(evaluation_date=evaluation_date, alert_results=tuple(results))
