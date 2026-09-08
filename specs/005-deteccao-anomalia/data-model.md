# Data Model: Deteccao de anomalia

## AnomalyRule

| Campo | Tipo | Notas |
|---|---|---|
| `metric_id` | texto | |
| `dimension_id` | texto ou nulo | |
| `dimension_value` | texto ou nulo | |
| `window_days` | inteiro | Deve ser >= 1; `0` ou negativo -> `janela_invalida` |
| `threshold_pct` | numero | Limiar de desvio percentual absoluto |

## Direction

Enum: `increase`, `decrease`.

## CandidateFinding

| Campo | Tipo |
|---|---|
| `metric_id` | texto |
| `observed_date` | data |
| `observed_value` | numero |
| `baseline_value` | numero |
| `deviation_pct` | numero |
| `direction` | `Direction` |
| `window_days` | inteiro |
| `threshold_pct` | numero |

## DetectionOutcome

| Campo | Tipo | Notas |
|---|---|---|
| `triggered` | booleano | |
| `finding` | `CandidateFinding` ou nulo | Preenchido somente quando `triggered=True` |
| `reason_code` | texto ou nulo | Preenchido quando `triggered=False` por indisponibilidade/config invalida; `None` quando simplesmente dentro do limiar |

## Motivos nomeados (`reason_code`)

- `observado_indisponivel` — dia observado sem autorizacao/execucao bem-sucedida.
- `baseline_incompleta` — pelo menos um dos `window_days` dias da baseline indisponivel.
- `baseline_zero` — media da baseline calculada como exatamente zero.
- `janela_invalida` — `window_days < 1`.
