from __future__ import annotations

from .modelos import (
    InsightCandidate,
    NotPrioritisableInsight,
    PrioritizationOutcome,
    PrioritizedInsight,
)


def priorizar(candidates: list[InsightCandidate]) -> PrioritizationOutcome:
    not_prioritisable: list[NotPrioritisableInsight] = []
    scored: list[tuple[InsightCandidate, float, float]] = []

    for candidate in candidates:
        if candidate.confidence is None:
            not_prioritisable.append(
                NotPrioritisableInsight(candidate=candidate, reason_code="confidence_unknown")
            )
            continue
        if candidate.reach is None:
            not_prioritisable.append(
                NotPrioritisableInsight(candidate=candidate, reason_code="reach_unknown")
            )
            continue
        impact_score = candidate.magnitude * candidate.confidence
        reach_score = candidate.reach * candidate.confidence
        scored.append((candidate, impact_score, reach_score))

    scored.sort(key=lambda item: (item[1], item[2]), reverse=True)

    prioritized = tuple(
        PrioritizedInsight(candidate=candidate, rank=index, impact_score=impact, reach_score=reach)
        for index, (candidate, impact, reach) in enumerate(scored, start=1)
    )

    return PrioritizationOutcome(
        prioritized=prioritized, not_prioritisable=tuple(not_prioritisable)
    )
