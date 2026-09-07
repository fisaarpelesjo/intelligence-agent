"""As-of resolution and range segmentation — T085 (FR-034, FR-035).

A number published for a closed period must not change because somebody
redefined the metric afterwards. That is the whole of FR-034, and it reduces to
one rule: **a period is answered by the definition that was in effect during it**,
not by the definition in effect today.

Which means a range crossing a definition change has no single answer. This
module returns **one segment per overlapping version**, each naming the version
that governs it, ordered and never blended. Blending is the failure mode worth
naming precisely: averaging June under version 1 with July under version 2
produces a number that is not wrong in any specific place and is not right
anywhere — nobody can reproduce it, and nobody can tell it happened.

Deterministic by construction:

* segments are ordered by ``(start, version)``, so two runs over the same catalog
  produce byte-identical output and therefore the same ``decision_id`` (SC-021);
* clipping is inclusive on both ends, in **canonical-zone dates** — every date
  here is already canonical (``DateRange`` guarantees it), so no zone arithmetic
  happens in this module and none should;
* an unresolvable day is reported as an **uncovered span**, never silently
  attached to the nearest version.

**Pure functions only.** Nothing here reads a catalog from disk, resolves a
policy, or decides an outcome. The gate that turns a multi-segment result into
``SPANS_DEFINITION_CHANGE`` lives in the pipeline; keeping the arithmetic
separate is what makes it testable against hand-built version lists that the
``Metric`` contract itself would refuse to construct.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations

from ..contracts.metric import Metric, MetricVersion

__all__ = [
    "DaySpan",
    "OverlappingVersionsError",
    "VersionSegment",
    "covers",
    "resolve_as_of",
    "resolve_version",
    "segment",
    "segment_versions",
    "spans_definition_change",
    "uncovered_spans",
]

_ONE_DAY = timedelta(days=1)


class OverlappingVersionsError(ValueError):
    """Two version blocks claim the same day.

    The ``Metric`` contract already refuses this at load time, so a loaded
    catalog cannot reach here. The check stays because these functions accept a
    bare version sequence too, and an overlap would make as-of resolution
    ambiguous — which is exactly the ambiguity a historical answer must not have.
    """


@dataclass(frozen=True, slots=True)
class VersionSegment:
    """One contiguous span of a request answered by exactly one version."""

    metric_id: str
    version: int
    start: date
    end: date

    @property
    def metric_version_id(self) -> str:
        """``{metric}@{n}`` — the identifier a decision cites as evidence."""
        return f"{self.metric_id}@{self.version}"

    @property
    def days(self) -> int:
        """Inclusive day count. Counts dates, so DST cannot distort it."""
        return (self.end - self.start).days + 1


@dataclass(frozen=True, slots=True)
class DaySpan:
    """A stretch of requested days no version covers."""

    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def covers(version: MetricVersion, day: date) -> bool:
    """Whether ``version`` was in effect on ``day``.

    ``effective_to is None`` means current, not unbounded-in-the-past: the lower
    bound is still checked.
    """
    if day < version.effective_from:
        return False
    return version.effective_to is None or day <= version.effective_to


def _assert_no_overlap(metric_id: str, versions: Sequence[MetricVersion]) -> None:
    for left, right in combinations(versions, 2):
        left_end = left.effective_to or date.max
        right_end = right.effective_to or date.max
        if left.effective_from <= right_end and right.effective_from <= left_end:
            raise OverlappingVersionsError(
                f"metric {metric_id!r} versions {left.version} and {right.version} both claim "
                "days in the same range; as-of resolution would be ambiguous (FR-034)"
            )


def resolve_version(
    metric_id: str, versions: Sequence[MetricVersion], on: date
) -> MetricVersion | None:
    """The version in effect on ``on``, or ``None`` if the metric had none yet.

    ``None`` is a real answer — a date before the first ``effective_from`` has no
    governed definition, and inventing one by falling back to version 1 would
    answer a period the catalog never claimed to describe.
    """
    _assert_no_overlap(metric_id, versions)
    return next((v for v in versions if covers(v, on)), None)


def resolve_as_of(metric: Metric, on: date) -> MetricVersion | None:
    """The version of ``metric`` in effect on ``on`` (FR-034)."""
    return resolve_version(metric.name, metric.versions, on)


def segment_versions(
    metric_id: str, versions: Sequence[MetricVersion], start: date, end: date
) -> tuple[VersionSegment, ...]:
    """One segment per version overlapping ``[start, end]``, clipped and ordered.

    Never one blended span: a range crossing a change comes back as two
    segments naming two versions, and it is the caller's job to present them
    separately (FR-035).
    """
    if end < start:
        raise ValueError(f"range ends {end} before it starts {start}")
    _assert_no_overlap(metric_id, versions)

    segments: list[VersionSegment] = []
    for version in versions:
        lower = max(version.effective_from, start)
        upper = min(version.effective_to or end, end)
        if lower > upper:
            continue
        segments.append(
            VersionSegment(metric_id=metric_id, version=version.version, start=lower, end=upper)
        )
    return tuple(sorted(segments, key=lambda s: (s.start, s.version)))


def segment(metric: Metric, start: date, end: date) -> tuple[VersionSegment, ...]:
    """One segment per version of ``metric`` overlapping the range (FR-035)."""
    return segment_versions(metric.name, metric.versions, start, end)


def uncovered_spans(
    segments: Sequence[VersionSegment], start: date, end: date
) -> tuple[DaySpan, ...]:
    """Requested days no version covers.

    A gap between version blocks is legal in the file format and illegitimate in
    an answer: those days have no governed definition. Reporting them is how the
    caller avoids attaching them to whichever neighbouring version happens to be
    adjacent.
    """
    gaps: list[DaySpan] = []
    cursor = start
    for item in sorted(segments, key=lambda s: (s.start, s.version)):
        if item.start > cursor:
            gaps.append(DaySpan(start=cursor, end=item.start - _ONE_DAY))
        cursor = max(cursor, item.end + _ONE_DAY)
    if cursor <= end:
        gaps.append(DaySpan(start=cursor, end=end))
    return tuple(gaps)


def spans_definition_change(segments: Sequence[VersionSegment]) -> bool:
    """Whether the range was answered by more than one definition."""
    return len({s.version for s in segments}) > 1
