from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InsightCandidate:
    identifier: str
    magnitude: float
    confidence: float | None
    reach: float | None


@dataclass(frozen=True)
class PrioritizedInsight:
    candidate: InsightCandidate
    rank: int
    impact_score: float
    reach_score: float


@dataclass(frozen=True)
class NotPrioritisableInsight:
    candidate: InsightCandidate
    reason_code: str


@dataclass(frozen=True)
class PrioritizationOutcome:
    prioritized: tuple[PrioritizedInsight, ...]
    not_prioritisable: tuple[NotPrioritisableInsight, ...]
