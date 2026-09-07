"""Gate 11 (as-of segmentation) — T085 (FR-034, FR-035; decision-contract §4).

Last in the order, and **never denying**. It annotates an allowed decision; it
does not gate one. A range crossing a definition change is a perfectly legitimate
question — the only illegitimate thing is answering it with a single number, and
the answer to that is a caveat plus segments, not a refusal.

``SPANS_DEFINITION_CHANGE`` is ALLOW_WITH_CAVEAT, so the pipeline continues past
it and the segments travel on the decision (assembled in ``pipeline._decision``,
alongside the limitations, from the same pure functions this gate reads).

Gate 10 (retention) remains absent from ``GATES`` rather than stubbed, for the
reason gate 6 was absent before it existed: a stub that always passes is
indistinguishable from a gate that does not work.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...contracts.reason_codes import ReasonCode
from ...resolution.as_of import VersionSegment, segment, spans_definition_change
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, caveat

__all__ = ["gate_11_as_of", "request_segments"]


def request_segments(context: GateContext) -> tuple[VersionSegment, ...]:
    """Every requested metric's segments over the requested range, ordered.

    Sorted by ``(metric_id, start, version)`` so two runs of the same request
    produce identical output — the decision cites these, and a decision whose
    evidence order wobbles is a decision whose identity wobbles.
    """
    segments: list[VersionSegment] = []
    for metric_id in sorted(set(context.request.metrics)):
        metric = context.bundle.internal.metrics.get(metric_id)
        if metric is None:
            continue
        segments.extend(
            segment(metric, context.request.date_range.start, context.request.date_range.end)
        )
    return tuple(sorted(segments, key=lambda s: (s.metric_id, s.start, s.version)))


def _spans_any_change(segments: Sequence[VersionSegment]) -> str | None:
    """The first metric whose range was answered by more than one definition."""
    for metric_id in sorted({s.metric_id for s in segments}):
        if spans_definition_change([s for s in segments if s.metric_id == metric_id]):
            return metric_id
    return None


def gate_11_as_of(context: GateContext) -> GateVerdict | None:
    """Flag a range that crosses a definition change. Never denies (FR-035)."""
    segments = request_segments(context)
    metric_id = _spans_any_change(segments)
    if metric_id is None:
        return None
    versions = sorted({s.version for s in segments if s.metric_id == metric_id})
    return caveat(
        ReasonCode.SPANS_DEFINITION_CHANGE,
        SubjectKind.METRIC,
        metric_id,
        f"metric {metric_id!r} was defined differently across the requested range: versions "
        f"{versions}. The range is answered in segments, never blended into one figure",
    )
