# Quickstart: catalogo_semantico

```python
from datetime import date
from catalogo_semantico import carregar_catalogo, decidir

catalogo = carregar_catalogo("packages/catalogo_semantico/catalog")
eventos_de_auditoria = []

decisao = decidir(
    catalogo,
    metric_id="signups",
    dimension_id="country",
    period_start=date(2026, 3, 1),
    period_end=date(2026, 3, 31),
    audit_sink=eventos_de_auditoria,
)

if decisao.allowed:
    print(decisao.resolved_metric_version.label)
else:
    print(f"negado: {decisao.reason_code}")
```

Rodar os testes deste pacote: `uv run pytest packages/catalogo_semantico`.
