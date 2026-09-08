# Contrato: funcao de priorizacao

## `priorizar(candidates: list[InsightCandidate]) -> PrioritizationOutcome`

Pura, sincrona, sem I/O.

Para cada `candidate` em `candidates`, na ordem dada:

1. Se `candidate.confidence is None` -> `NotPrioritisableInsight(candidate, reason_code="confidence_unknown")`.
2. Senao, se `candidate.reach is None` -> `NotPrioritisableInsight(candidate, reason_code="reach_unknown")`.
3. Senao -> calcular `impact_score = candidate.magnitude * candidate.confidence` e `reach_score = candidate.reach * candidate.confidence`; incluir como candidato a priorizar.

Ordenar os candidatos priorizaveis de forma descendente por `(impact_score, reach_score)` (tupla, comparada termo a termo pela semantica nativa de tupla do Python). Atribuir `rank` 1-based na ordem final.

Retornar `PrioritizationOutcome(prioritized=[...], not_prioritisable=[...])`. `len(prioritized) + len(not_prioritisable) == len(candidates)` sempre.
