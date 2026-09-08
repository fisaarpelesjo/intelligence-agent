# priorizacao_insights

Ordena insights por `(magnitude*confianca, alcance*confianca)`, termo a termo — nunca um score unico. Ve `specs/006-priorizacao-insights/spec.md` para a especificacao completa.

## Uso

```python
from priorizacao_insights import InsightCandidate, priorizar

candidatos = [
    InsightCandidate(identifier="signups:2026-08-14", magnitude=50, confidence=0.9, reach=1000),
    InsightCandidate(identifier="mrr:2026-08-14", magnitude=10, confidence=None, reach=500),
]

resultado = priorizar(candidatos)

for insight in resultado.prioritized:
    print(insight.rank, insight.candidate.identifier, insight.impact_score, insight.reach_score)

for insight in resultado.not_prioritisable:
    print("nao priorizavel:", insight.candidate.identifier, insight.reason_code)
```

## Garantias

- Sem dependencia de nenhum outro pacote do monorepo — biblioteca pura.
- Confianca ou alcance desconhecidos (`None`) nunca sao tratados como valor maximo por omissao.
- Nenhum score unico combinado e exposto — apenas `impact_score` e `reach_score` separados.

## Testes

```bash
uv run pytest packages/priorizacao_insights
```
