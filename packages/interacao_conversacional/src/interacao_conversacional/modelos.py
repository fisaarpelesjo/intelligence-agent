from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol


class ClaimClass(StrEnum):
    FACTUAL_RESULT = "FACTUAL_RESULT"
    CALCULATED_COMPARISON = "CALCULATED_COMPARISON"
    INTERPRETATION = "INTERPRETATION"
    LIMITATION = "LIMITATION"


@dataclass(frozen=True)
class QuestionIntent:
    metric_id: str
    period_expression: str
    dimension_id: str | None = None
    dimension_value: str | None = None
    baseline_period_expression: str | None = None


@dataclass(frozen=True)
class ResolvedPeriod:
    start: date
    end: date
    is_partial: bool


@dataclass(frozen=True)
class ComparisonResult:
    current_value: float
    baseline_value: float
    percentage_change: float


@dataclass(frozen=True)
class ClaimSentence:
    text: str
    claim_class: ClaimClass


@dataclass(frozen=True)
class NarrationPayload:
    metric_id: str
    value: float
    unit: str
    source_view: str
    period_label: str
    comparison: ComparisonResult | None = None


@dataclass(frozen=True)
class AnswerOutcome:
    success: bool
    reason_code: str | None = None
    sentences: tuple[ClaimSentence, ...] = ()
    resolved_period: ResolvedPeriod | None = None


class LLMProvider(Protocol):
    def narrar(self, payload: NarrationPayload) -> list[ClaimSentence]: ...
