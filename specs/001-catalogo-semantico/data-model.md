# Data Model: Catalogo semantico

Deriva de `spec.md` (Key Entities) e `plan.md`.

## MetricDefinitionVersion

Uma versao fechada da definicao de uma metrica.

| Campo | Tipo | Obrigatorio | Notas |
|---|---|---|---|
| `effective_from` | data | sim | Inicio da janela de vigencia (inclusive) |
| `effective_until` | data ou nulo | nao | Fim da janela (exclusive); nulo = ainda vigente |
| `label` | texto | sim | Rotulo legivel |
| `source_view` | texto | sim | Nome logico da fonte (a resolver pelo pacote de execucao de query, fora de escopo aqui) |
| `grain` | enum(`day`,`week`,`month`) | sim | Granularidade temporal |
| `aggregation` | enum(`sum`,`avg`,`count`,`last`) | sim | Tipo de agregacao |
| `unit` | texto | sim | Unidade (ex.: `currency_brl`, `count`, `percentage`) |
| `allowed_dimensions` | lista de ids de `DimensionDefinition` | sim | Pode ser vazia |
| `owner` | texto | nao | Papel responsavel (nao pessoa, conforme PRD) |
| `limitations` | texto | nao | Limitacoes conhecidas, exibidas na proveniencia por pacotes futuros |

Invariante: dentro de uma mesma `MetricDefinition`, nenhuma janela de vigencia de duas versoes pode se sobrepor (FR-008).

## MetricDefinition

| Campo | Tipo | Obrigatorio | Notas |
|---|---|---|---|
| `id` | texto (identificador estavel) | sim | Unico no catalogo (FR-008) |
| `status` | enum(`active`,`deprecated`) | sim | Descontinuada continua resolvivel para o passado (FR-007) |
| `versions` | lista de `MetricDefinitionVersion`, nao vazia | sim | Ordenada por `effective_from` |

## DimensionDefinition

| Campo | Tipo | Obrigatorio | Notas |
|---|---|---|---|
| `id` | texto | sim | Unico no catalogo |
| `type` | enum(`enumerated`,`open_text`,`temporal`) | sim | |

## AccessDecision (saida, nao persistida)

| Campo | Tipo | Notas |
|---|---|---|
| `allowed` | booleano | |
| `reason_code` | texto ou nulo | Preenchido somente quando `allowed=false`; um dos motivos nomeados na spec |
| `resolved_metric_version` | `MetricDefinitionVersion` ou nulo | Preenchido somente quando `allowed=true` |

## AuditEvent (emitido, nao mutavel apos criado)

| Campo | Tipo | Notas |
|---|---|---|
| `metric_id` | texto | Tal como pedido (pode ser desconhecido) |
| `dimension_id` | texto ou nulo | |
| `period_start` / `period_end` | data | |
| `decision` | `AccessDecision` (serializada) | |
| `emitted_at` | timestamp UTC | |

## Motivos nomeados de negacao (`reason_code`)

- `unknown_metric` — metrica nao existe no catalogo.
- `dimension_not_allowed` — dimensao nao esta em `allowed_dimensions` da metrica.
- `no_metric_version_for_period` — nenhuma versao cobre o periodo pedido.
- `period_spans_version_boundary` — periodo cruza a fronteira entre duas versoes.
