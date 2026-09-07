"""Deprecation semantics — T089 (FR-036, FR-061 to FR-064).

Deprecation **adds a boundary**. It mutates nothing, deletes nothing, and
redirects nothing. Four dated outcomes follow from where the requested period
sits relative to ``deprecated_from``:

============================  ==========================================
Period entirely before        ``DEPRECATED_METRIC`` — allowed, annotated
Period entirely on/after      ``METRIC_DEPRECATED_FOR_PERIOD`` — denied
Period crossing               ``SPANS_DEPRECATION_BOUNDARY`` — segmented
Comparison needing both       ``COMPARISON_REQUIRES_DEPRECATED_PERIOD`` — denied
============================  ==========================================

The crossing case is where the temptation lives. The available half of the range
is a perfectly good number, and returning it alone would look helpful — which is
why FR-063 refuses it when the request is a *comparison*: silently shortening a
comparison to the part that still exists changes the question without telling
anyone. Segmenting instead makes the missing half visible.

**A replacement is disclosed, never substituted** (FR-064). ``replacement_metric_id``
is guidance in a refusal — the reader is told where to look. The catalog does not
answer with the replacement's number, because a substitute silently swapped in is
indistinguishable from the metric that was asked for. Disclosure is doubly gated:
the governed policy must permit it, and the requester must be authorised for the
replacement itself. Naming a metric somebody cannot see would leak a relationship
between two metrics through a refusal that was supposed to disclose nothing.

**A continuation version reopens the metric, and only an authored one does.**
FR-062 allows a period on or after the boundary when an explicitly governed
continuation version exists — a version block whose ``effective_from`` is on or
after ``deprecated_from``. Somebody appended it deliberately; nothing here infers
one from adjacency.

Pure functions over authored content and dates. The gate that turns a verdict
into a decision lives in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from ..contracts.metric import Metric
from ..contracts.reason_codes import ReasonCode

__all__ = [
    "BoundaryRelation",
    "DeprecationSegment",
    "DeprecationVerdict",
    "boundary_relation",
    "continuation_version",
    "deprecation_segments",
    "deprecation_verdict",
    "replacement_guidance",
]

_ONE_DAY = timedelta(days=1)


class BoundaryRelation(StrEnum):
    """Where a requested period sits relative to ``deprecated_from``."""

    BEFORE = "before"
    SPANS = "spans"
    AFTER = "after"


@dataclass(frozen=True, slots=True)
class DeprecationSegment:
    """One half of a range split by the boundary.

    ``available`` is the whole point: the post-boundary segment is returned as a
    named, dated, explicitly **unavailable** span rather than dropped, so a
    reader sees what the answer does not cover.
    """

    start: date
    end: date
    available: bool


@dataclass(frozen=True, slots=True)
class DeprecationVerdict:
    """What deprecation says about one request for one metric."""

    metric_id: str
    deprecated_from: date
    relation: BoundaryRelation
    reason_code: ReasonCode
    segments: tuple[DeprecationSegment, ...]
    replacement_metric_id: str | None
    has_continuation: bool

    @property
    def is_denial(self) -> bool:
        return self.reason_code in {
            ReasonCode.METRIC_DEPRECATED_FOR_PERIOD,
            ReasonCode.COMPARISON_REQUIRES_DEPRECATED_PERIOD,
        }


def boundary_relation(deprecated_from: date, start: date, end: date) -> BoundaryRelation:
    """Classify ``[start, end]`` against the boundary. Inclusive on both ends."""
    if end < deprecated_from:
        return BoundaryRelation.BEFORE
    if start >= deprecated_from:
        return BoundaryRelation.AFTER
    return BoundaryRelation.SPANS


def continuation_version(metric: Metric) -> int | None:
    """The authored version that governs periods on or after the boundary.

    ``None`` when nobody authored one — which is the ordinary case, and the
    reason a post-boundary period is refused rather than answered.
    """
    if metric.deprecation is None:
        return None
    boundary = metric.deprecation.deprecated_from
    candidates = [v.version for v in metric.versions if v.effective_from >= boundary]
    return min(candidates) if candidates else None


def deprecation_segments(
    deprecated_from: date, start: date, end: date
) -> tuple[DeprecationSegment, ...]:
    """Split ``[start, end]`` at the boundary, ordered, never blended."""
    relation = boundary_relation(deprecated_from, start, end)
    if relation is BoundaryRelation.BEFORE:
        return (DeprecationSegment(start=start, end=end, available=True),)
    if relation is BoundaryRelation.AFTER:
        return (DeprecationSegment(start=start, end=end, available=False),)
    return (
        DeprecationSegment(start=start, end=deprecated_from - _ONE_DAY, available=True),
        DeprecationSegment(start=deprecated_from, end=end, available=False),
    )


def deprecation_verdict(
    metric: Metric,
    start: date,
    end: date,
    *,
    comparison_start: date | None = None,
    comparison_end: date | None = None,
) -> DeprecationVerdict | None:
    """The dated deprecation outcome, or ``None`` when the metric is not deprecated.

    A comparison is refused whenever **any** part of either range falls on or
    after the boundary and no continuation version exists. That is stricter than
    refusing only the crossing case, and deliberately: comparing a live period
    against one where the metric no longer has a definition is the same error
    whichever range holds the missing half.
    """
    if metric.deprecation is None:
        return None

    boundary = metric.deprecation.deprecated_from
    relation = boundary_relation(boundary, start, end)
    continuation = continuation_version(metric)
    replacement = metric.deprecation.replacement_metric_id

    def build(code: ReasonCode) -> DeprecationVerdict:
        return DeprecationVerdict(
            metric_id=metric.name,
            deprecated_from=boundary,
            relation=relation,
            reason_code=code,
            segments=deprecation_segments(boundary, start, end),
            replacement_metric_id=replacement,
            has_continuation=continuation is not None,
        )

    if continuation is not None:
        # An authored continuation governs the post-boundary days, so the only
        # thing left to say is that the metric is deprecated at all.
        return build(ReasonCode.DEPRECATED_METRIC)

    comparison_touches = (comparison_end is not None and comparison_end >= boundary) or (
        comparison_start is not None and comparison_start >= boundary
    )
    if (comparison_start is not None or comparison_end is not None) and (
        relation is not BoundaryRelation.BEFORE or comparison_touches
    ):
        return build(ReasonCode.COMPARISON_REQUIRES_DEPRECATED_PERIOD)

    if relation is BoundaryRelation.AFTER:
        return build(ReasonCode.METRIC_DEPRECATED_FOR_PERIOD)
    if relation is BoundaryRelation.SPANS:
        return build(ReasonCode.SPANS_DEPRECATION_BOUNDARY)
    return build(ReasonCode.DEPRECATED_METRIC)


def replacement_guidance(
    verdict: DeprecationVerdict,
    *,
    policy_allows: bool,
    requester_authorised: bool,
) -> str | None:
    """The replacement id, when it may be disclosed as guidance (FR-064).

    Both gates must open. ``policy_allows`` is the governed decision
    (``refusal.disclose_replacement_metric_id``); ``requester_authorised`` is
    whether this principal could have asked for the replacement directly. A
    refusal that names a metric the requester may not see would disclose a
    relationship between two metrics that authorisation was meant to hide.
    """
    if verdict.replacement_metric_id is None:
        return None
    if not (policy_allows and requester_authorised):
        return None
    return verdict.replacement_metric_id
