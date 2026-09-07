# Data Model: Execucao de query governada

## Operator

Enum: `eq`, `ne`, `in`, `not_in`. Qualquer outro valor (incluindo `pattern`, `regex`, `is_null`) e invalido por construcao — nao existe no enum, entao nem chega a ser representavel.

## QueryFilter

| Campo | Tipo | Obrigatorio | Notas |
|---|---|---|---|
| `dimension_id` | texto | sim | Deve estar em `allowed_dimensions` da versao de metrica resolvida (FR-003) |
| `operator` | `Operator` | sim | |
| `values` | lista de texto, nao vazia | sim | `eq`/`ne` esperam exatamente 1 valor; `in`/`not_in` aceitam 1+; lista vazia e invalida (recusada) |

## QueryRequest

| Campo | Tipo | Notas |
|---|---|---|
| `decision` | `AccessDecision` (de `catalogo_semantico`) | Deve ter `allowed=True` e `resolved_metric_version` preenchido |
| `filter` | `QueryFilter` ou `None` | |
| `period_start`, `period_end` | data | |

## CostEstimate

| Campo | Tipo |
|---|---|
| `estimated_bytes` | inteiro |
| `estimated_rows` | inteiro |

## QueryResult

| Campo | Tipo |
|---|---|
| `value` | numero |
| `unit` | texto (copiado da versao de metrica resolvida) |
| `source_view` | texto (copiado da versao de metrica resolvida) |
| `rows_returned` | inteiro |

## ExecutionOutcome

| Campo | Tipo | Notas |
|---|---|---|
| `success` | booleano | |
| `reason_code` | `ExecutionReasonCode` ou nulo | Preenchido somente quando `success=False` |
| `result` | `QueryResult` ou nulo | Preenchido somente quando `success=True` |

## ExecutionReasonCode

- `not_authorized` — decisao recebida nao era "permitido".
- `operator_not_allowed` — operador fora da allowlist, ou lista de valores vazia em `in`/`not_in`.
- `dimension_not_allowed` — dimensao do filtro fora de `allowed_dimensions`.
- `cost_ceiling_exceeded` — `dry_run.estimated_bytes` acima do teto configurado.
- `row_ceiling_exceeded` — `dry_run.estimated_rows` acima do teto configurado.
- `data_source_unavailable` — `DataSource.dry_run` ou `DataSource.execute` levantou uma excecao.

## DataSource (Protocol — porta)

| Metodo | Assinatura | Notas |
|---|---|---|
| `dry_run` | `(request: QueryRequest) -> CostEstimate` | Nunca modifica estado |
| `execute` | `(request: QueryRequest) -> QueryResult` | Somente leitura; sem metodo de escrita em toda a interface (FR-008) |
