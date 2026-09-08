from __future__ import annotations

from datetime import date, timedelta

from catalogo_semantico import Catalogo
from execucao_query import DataSource

from ._execucao import executar_metrica
from .modelos import DailyReport, KpiDefinition, KpiResult


def gerar_relatorio_diario(
    kpis: list[KpiDefinition],
    catalogo: Catalogo,
    data_source: DataSource,
    reference_today: date,
    max_bytes: int,
    max_rows: int,
) -> DailyReport:
    report_date = reference_today - timedelta(days=1)
    results: list[KpiResult] = []
    for kpi in kpis:
        outcome = executar_metrica(
            catalogo,
            data_source,
            kpi.metric_id,
            kpi.dimension_id,
            kpi.dimension_value,
            report_date,
            max_bytes,
            max_rows,
        )
        if isinstance(outcome, str):
            results.append(KpiResult(metric_id=kpi.metric_id, available=False, reason_code=outcome))
        else:
            results.append(
                KpiResult(
                    metric_id=kpi.metric_id,
                    available=True,
                    value=outcome.value,
                    unit=outcome.unit,
                    source_view=outcome.source_view,
                )
            )
    return DailyReport(report_date=report_date, kpi_results=tuple(results))
