# Contrato: funcao de execucao

## `executar(request, data_source, max_bytes, max_rows) -> ExecutionOutcome`

**Entradas**:
- `request`: `QueryRequest`.
- `data_source`: implementacao de `DataSource` (real ou falsa).
- `max_bytes`, `max_rows`: tetos configurados (inteiros).

**Saida**: `ExecutionOutcome`.

**Ordem das checagens** (curto-circuito — a primeira que falhar produz a recusa, sem checar as seguintes nem chamar `data_source`):

1. `request.decision.allowed` deve ser `True` -> senao `not_authorized`.
2. Se `request.filter` existir:
   a. `request.filter.operator` deve ser um `Operator` valido e `request.filter.values` nao vazia -> senao `operator_not_allowed`.
   b. `request.filter.dimension_id` deve estar em `request.decision.resolved_metric_version.allowed_dimensions` -> senao `dimension_not_allowed`.
3. Chamar `data_source.dry_run(request)`. Se levantar excecao -> `data_source_unavailable`.
4. Se `estimated_bytes > max_bytes` -> `cost_ceiling_exceeded`.
5. Se `estimated_rows > max_rows` -> `row_ceiling_exceeded`.
6. Chamar `data_source.execute(request)`. Se levantar excecao -> `data_source_unavailable`. Senao, retornar `ExecutionOutcome(success=True, result=...)`.

`data_source.execute` e chamado no maximo uma vez, e somente se todas as checagens 1-5 passarem.
