# Quickstart: deteccao_anomalia

```python
from datetime import date
from catalogo_semantico import carregar_catalogo
from execucao_query.fake_data_source import FakeDataSource
from deteccao_anomalia import AnomalyRule, detectar

catalogo = carregar_catalogo("packages/catalogo_semantico/catalog")

rule = AnomalyRule(metric_id="signups", window_days=7, threshold_pct=20)

resultado = detectar(
    rule,
    catalogo,
    data_source=FakeDataSource(),
    reference_today=date(2026, 8, 15),
    max_bytes=10_000_000,
    max_rows=1_000,
)

if resultado.triggered:
    f = resultado.finding
    print(f"{f.metric_id}: {f.direction} de {f.deviation_pct:.1f}% (baseline={f.baseline_value})")
else:
    print(f"sem finding: {resultado.reason_code}")
```

Rodar os testes deste pacote: `uv run pytest packages/deteccao_anomalia`.
