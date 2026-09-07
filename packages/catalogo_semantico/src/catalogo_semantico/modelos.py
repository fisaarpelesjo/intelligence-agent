from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum


class Aggregation(StrEnum):
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    LAST = "last"


class Grain(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class MetricStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class DimensionType(StrEnum):
    ENUMERATED = "enumerated"
    OPEN_TEXT = "open_text"
    TEMPORAL = "temporal"


class ReasonCode(StrEnum):
    UNKNOWN_METRIC = "unknown_metric"
    DIMENSION_NOT_ALLOWED = "dimension_not_allowed"
    NO_METRIC_VERSION_FOR_PERIOD = "no_metric_version_for_period"
    PERIOD_SPANS_VERSION_BOUNDARY = "period_spans_version_boundary"


@dataclass(frozen=True)
class MetricDefinitionVersion:
    effective_from: date
    label: str
    source_view: str
    grain: Grain
    aggregation: Aggregation
    unit: str
    allowed_dimensions: tuple[str, ...] = ()
    effective_until: date | None = None
    owner: str | None = None
    limitations: str | None = None

    def covers(self, period_start: date, period_end: date) -> bool:
        if period_start < self.effective_from:
            return False
        return self.effective_until is None or period_end < self.effective_until

    def overlaps(self, period_start: date, period_end: date) -> bool:
        starts_before_end = self.effective_until is None or period_start < self.effective_until
        ends_after_start = period_end >= self.effective_from
        return starts_before_end and ends_after_start


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    status: MetricStatus
    versions: tuple[MetricDefinitionVersion, ...]

    def __post_init__(self) -> None:
        if not self.versions:
            raise ValueError(f"metric '{self.id}' must declare at least one version")


@dataclass(frozen=True)
class DimensionDefinition:
    id: str
    type: DimensionType


@dataclass(frozen=True)
class Catalogo:
    metrics: dict[str, MetricDefinition]
    dimensions: dict[str, DimensionDefinition]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason_code: ReasonCode | None = None
    resolved_metric_version: MetricDefinitionVersion | None = None


@dataclass(frozen=True)
class AuditEvent:
    metric_id: str
    dimension_id: str | None
    period_start: date
    period_end: date
    decision: AccessDecision
    emitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
