from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class AlertDirection(StrEnum):
    ABOVE = "above"
    BELOW = "below"


@dataclass(frozen=True)
class KpiDefinition:
    metric_id: str
    dimension_id: str | None = None
    dimension_value: str | None = None


@dataclass(frozen=True)
class KpiResult:
    metric_id: str
    available: bool
    value: float | None = None
    unit: str | None = None
    source_view: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class DailyReport:
    report_date: date
    kpi_results: tuple[KpiResult, ...]


@dataclass(frozen=True)
class AlertRule:
    metric_id: str
    threshold: float
    direction: AlertDirection


@dataclass(frozen=True)
class AlertResult:
    metric_id: str
    evaluated: bool
    triggered: bool
    value: float | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class AlertBundle:
    evaluation_date: date
    alert_results: tuple[AlertResult, ...]
