# Data Model: Priorizacao de insights

## InsightCandidate

| Campo | Tipo | Notas |
|---|---|---|
| `identifier` | texto | Livre — ex.: `"signups:2026-08-14"` |
| `magnitude` | numero | Fornecido pelo chamador |
| `confidence` | numero ou nulo | `None` -> nao priorizavel |
| `reach` | numero ou nulo | `None` (com `confidence` presente) -> nao priorizavel |

## PrioritizedInsight

| Campo | Tipo |
|---|---|
| `candidate` | `InsightCandidate` |
| `rank` | inteiro (>= 1) |
| `impact_score` | numero (`magnitude * confidence`) |
| `reach_score` | numero (`reach * confidence`) |

## NotPrioritisableInsight

| Campo | Tipo | Notas |
|---|---|---|
| `candidate` | `InsightCandidate` | |
| `reason_code` | texto | `confidence_unknown` ou `reach_unknown` |

## PrioritizationOutcome

| Campo | Tipo |
|---|---|
| `prioritized` | lista de `PrioritizedInsight`, ordenada por `rank` |
| `not_prioritisable` | lista de `NotPrioritisableInsight` |

Ordenacao de `prioritized`: descendente por `(impact_score, reach_score)`, comparado como tupla (o segundo elemento so desempata quando o primeiro e igual — comportamento nativo de comparacao de tupla em Python).
