# execucao_query

Executa uma leitura somente-leitura contra uma fonte de dados abstrata, sob uma decisao de autorizacao ja aprovada pelo `catalogo_semantico`. Ve `specs/002-execucao-query/spec.md` para a especificacao completa.

## Uso

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
    filter=QueryFilter(dimension_id="country", operator=Operator.EQ, values=("BR",)),
    period_start=date(2026, 3, 1),
    period_end=date(2026, 3, 31),
)

resultado = executar(request, FakeDataSource(), max_bytes=10_000_000, max_rows=1_000)

if resultado.success:
    print(resultado.result.value, resultado.result.unit)
else:
    print(f"recusado: {resultado.reason_code}")
```

## Garantias

- Decisao "negado" e recusada antes de qualquer chamada a fonte de dados.
- Operador fora da allowlist (`eq`/`ne`/`in`/`not_in`) e recusado sem compilar nada.
- `dry_run` sempre roda antes de `execute`; excedendo o teto de bytes ou linhas, `execute` nunca e chamado.
- Nenhuma excecao da fonte de dados escapa — vira recusa nomeada `data_source_unavailable`.
- `DataSource` e estruturalmente somente-leitura — sem nenhum metodo de escrita na interface.

## Testes

```bash
uv run pytest packages/execucao_query
```
