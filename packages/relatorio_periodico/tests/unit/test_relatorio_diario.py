from datetime import date

from catalogo_semantico import Catalogo
from execucao_query.fake_data_source import FakeDataSource
from relatorio_periodico import KpiDefinition, gerar_relatorio_diario

REFERENCE_TODAY = date(2026, 8, 15)


def test_relatorio_com_todos_os_kpis_disponiveis(catalogo: Catalogo) -> None:
    kpis = [
        KpiDefinition(metric_id="signups"),
        KpiDefinition(metric_id="active_users"),
        KpiDefinition(metric_id="monthly_recurring_revenue"),
    ]

    relatorio = gerar_relatorio_diario(
        kpis, catalogo, FakeDataSource(), REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert relatorio.report_date == date(2026, 8, 14)
    assert len(relatorio.kpi_results) == 3
    assert all(kpi.available for kpi in relatorio.kpi_results)


def test_relatorio_com_um_kpi_indisponivel_nao_falha(catalogo: Catalogo) -> None:
    kpis = [
        KpiDefinition(metric_id="signups"),
        KpiDefinition(metric_id="active_users"),
        KpiDefinition(metric_id="metrica_que_nao_existe"),
    ]

    relatorio = gerar_relatorio_diario(
        kpis, catalogo, FakeDataSource(), REFERENCE_TODAY, max_bytes=10_000_000, max_rows=1_000
    )

    assert len(relatorio.kpi_results) == 3
    disponiveis = [k for k in relatorio.kpi_results if k.available]
    indisponiveis = [k for k in relatorio.kpi_results if not k.available]
    assert len(disponiveis) == 2
    assert len(indisponiveis) == 1
    assert indisponiveis[0].reason_code == "unknown_metric"
