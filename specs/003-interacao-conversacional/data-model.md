# Data Model: Interacao conversacional

## PeriodExpression (vocabulario fechado)

`hoje`, `ontem`, `esta_semana`, `semana_passada`, `este_mes`, `mes_passado`, `este_trimestre`, `trimestre_passado`, `este_ano`, `ano_passado`. Qualquer outro texto e desconhecido -> pedido de clarificacao (FR-001).

## ResolvedPeriod

| Campo | Tipo | Notas |
|---|---|---|
| `start` | data | |
| `end` | data | |
| `is_partial` | booleano | `True` se `end` ainda nao passou em relacao a data de referencia injetada |

## QuestionIntent

| Campo | Tipo | Obrigatorio |
|---|---|---|
| `metric_id` | texto | sim |
| `dimension_id` | texto ou nulo | nao |
| `dimension_value` | texto ou nulo | nao (exigido se `dimension_id` presente) |
| `period_expression` | texto | sim |
| `baseline_period_expression` | texto ou nulo | nao (presente = pergunta de comparacao) |

## ComparisonResult

| Campo | Tipo |
|---|---|
| `current_value` | numero |
| `baseline_value` | numero |
| `percentage_change` | numero |

## ClaimClass (reutiliza o vocabulario do PRD)

`FACTUAL_RESULT`, `CALCULATED_COMPARISON`, `INTERPRETATION`, `LIMITATION`.

## ClaimSentence

| Campo | Tipo |
|---|---|
| `text` | texto |
| `claim_class` | `ClaimClass` |

## NarrationPayload (estrutura fechada, FR-007)

| Campo | Tipo | Notas |
|---|---|---|
| `metric_id` | texto | |
| `value` | numero | |
| `unit` | texto | |
| `source_view` | texto | |
| `period_label` | texto | Rotulo resolvido (ex.: "mes passado"), nunca a pergunta original |
| `comparison` | `ComparisonResult` ou nulo | |

Nenhum outro campo e permitido — em particular, nenhum campo de identidade de usuario, nenhum texto livre da pergunta original, nenhuma credencial/token.

## AnswerOutcome

| Campo | Tipo | Notas |
|---|---|---|
| `success` | booleano | |
| `reason_code` | texto ou nulo | Preenchido quando `success=False` (inclui `clarification_needed` e as recusas traduzidas de `catalogo_semantico`/`execucao_query`) |
| `sentences` | lista de `ClaimSentence` | Preenchida quando `success=True` |
| `resolved_period` | `ResolvedPeriod` ou nulo | Preenchida quando `success=True`, base da proveniencia |

## ReasonCode (uniao dos motivos possiveis)

- `clarification_needed` — expressao de periodo fora do vocabulario.
- `not_comparable_window` — comparacao entre periodo completo e parcial.
- `zero_baseline` — comparacao com baseline zero.
- Motivos herdados de `catalogo_semantico.ReasonCode` (ex.: `unknown_metric`) e de `execucao_query.ExecutionReasonCode` (ex.: `cost_ceiling_exceeded`) — repassados sem reinterpretacao.
