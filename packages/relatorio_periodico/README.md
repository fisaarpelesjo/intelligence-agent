# relatorio_periodico

Relatorio diario de KPIs e avaliacao independente de alerta por limiar. Ve `specs/004-relatorio-periodico/spec.md` para a especificacao completa.

## Uso

```python
from datetime import date
from catalogo_semantico import carregar_catalogo
from execucao_query.fake_data_source import FakeDataSource
from relatorio_periodico import (
    AlertDirection,
    AlertRule,
    KpiDefinition,
    avaliar_alertas,
    gerar_relatorio_diario,
)

catalogo = carregar_catalogo("packages/catalogo_semantico/catalog")
fonte = FakeDataSource()
hoje = date(2026, 8, 15)

relatorio = gerar_relatorio_diario(
    kpis=[KpiDefinition(metric_id="signups"), KpiDefinition(metric_id="active_users")],
    catalogo=catalogo,
    data_source=fonte,
    reference_today=hoje,
    max_bytes=10_000_000,
    max_rows=1_000,
)

alertas = avaliar_alertas(
    rules=[AlertRule(metric_id="signups", threshold=1000, direction=AlertDirection.BELOW)],
    catalogo=catalogo,
    data_source=fonte,
    reference_today=hoje,
    max_bytes=10_000_000,
    max_rows=1_000,
)

for kpi in relatorio.kpi_results:
    print(kpi.metric_id, kpi.value if kpi.available else kpi.reason_code)

for alerta in alertas.alert_results:
    print(alerta.metric_id, "disparou" if alerta.triggered else "ok")
```

## Garantias

- Relatorio sempre reporta o dia anterior (ultimo dia completo).
- Um KPI/regra indisponivel nunca aborta o relatorio/bundle inteiro nem lanca excecao.
- `DailyReport` e `AlertBundle` sao tipos independentes, sem campo em comum.

## Testes

```bash
uv run pytest packages/relatorio_periodico
```
