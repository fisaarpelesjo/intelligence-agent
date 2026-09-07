# Quickstart: execucao_query

```python
from datetime import date
from catalogo_semantico import carregar_catalogo, decidir
from execucao_query import Operator, QueryFilter, QueryRequest, executar
from execucao_query.fake_data_source import FakeDataSource

catalogo = carregar_catalogo("packages/catalogo_semantico/catalog")
eventos = []
decisao = decidir(
    catalogo, "signups", "country", date(2026, 3, 1), date(2026, 3, 31), audit_sink=eventos
)

request = QueryRequest(
    decision=decisao,
    filter=QueryFilter(dimension_id="country", operator=Operator.EQ, values=["BR"]),
    period_start=date(2026, 3, 1),
    period_end=date(2026, 3, 31),
)

resultado = executar(request, FakeDataSource(), max_bytes=10_000_000, max_rows=1_000)

if resultado.success:
    print(resultado.result.value, resultado.result.unit)
else:
    print(f"recusado: {resultado.reason_code}")
```

Rodar os testes deste pacote: `uv run pytest packages/execucao_query`.
