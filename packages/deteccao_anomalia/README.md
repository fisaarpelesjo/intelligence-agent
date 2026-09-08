# deteccao_anomalia

Produz um candidate finding quando o valor observado de uma metrica se desvia da baseline de media movel alem de um limiar configuravel — sem afirmar causa, sem se auto-originar. Regra registrada em `docs/decisions/0006-regra-de-baseline-media-movel.md` (status `Proposed`). Ve `specs/005-deteccao-anomalia/spec.md` para a especificacao completa.

## Uso

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

## Garantias

- Baseline nunca e calculada com dado parcial — qualquer dia indisponivel na janela recusa o calculo inteiro.
- Baseline zero nunca produz um desvio percentual infinito.
- Nenhum modulo de scheduling/timer/thread e importado (verificado por teste de AST) — a decisao de quando rodar e sempre externa.

## Testes

```bash
uv run pytest packages/deteccao_anomalia
```
