from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Direction(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"


@dataclass(frozen=True)
class AnomalyRule:
    metric_id: str
    window_days: int
    threshold_pct: float
    dimension_id: str | None = None
    dimension_value: str | None = None


@dataclass(frozen=True)
class CandidateFinding:
    metric_id: str
    observed_date: date
    observed_value: float
    baseline_value: float
    deviation_pct: float
    direction: Direction
    window_days: int
    threshold_pct: float


@dataclass(frozen=True)
class DetectionOutcome:
    triggered: bool
    finding: CandidateFinding | None = None
    reason_code: str | None = None
