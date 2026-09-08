# Data Model: Relatorio periodico

## KpiDefinition

| Campo | Tipo | Obrigatorio |
|---|---|---|
| `metric_id` | texto | sim |
| `dimension_id` | texto ou nulo | nao |
| `dimension_value` | texto ou nulo | nao |

## KpiResult

| Campo | Tipo | Notas |
|---|---|---|
| `metric_id` | texto | |
| `available` | booleano | |
| `value`, `unit`, `source_view` | numero/texto/texto ou nulos | Preenchidos somente quando `available=True` |
| `reason_code` | texto ou nulo | Preenchido somente quando `available=False` |

## DailyReport

| Campo | Tipo |
|---|---|
| `report_date` | data |
| `kpi_results` | lista de `KpiResult` |

## AlertDirection

Enum: `above`, `below`.

## AlertRule

| Campo | Tipo |
|---|---|
| `metric_id` | texto |
| `threshold` | numero |
| `direction` | `AlertDirection` |

## AlertResult

| Campo | Tipo | Notas |
|---|---|---|
| `metric_id` | texto | |
| `evaluated` | booleano | `False` quando a metrica estava indisponivel |
| `triggered` | booleano | Sempre `False` quando `evaluated=False` |
| `value` | numero ou nulo | Preenchido quando `evaluated=True` |
| `reason_code` | texto ou nulo | Preenchido quando `evaluated=False` |

## AlertBundle

| Campo | Tipo |
|---|---|
| `evaluation_date` | data |
| `alert_results` | lista de `AlertResult` |

`DailyReport` e `AlertBundle` nao compartilham nenhum nome de campo (FR-005, SC-004) — por isso o campo de data de `AlertBundle` se chama `evaluation_date`, nao `report_date`, apesar de conceitualmente representarem o mesmo dia.
