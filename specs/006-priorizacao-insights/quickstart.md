# Quickstart: priorizacao_insights

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

Rodar os testes deste pacote: `uv run pytest packages/priorizacao_insights`.
