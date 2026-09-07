"""Gate 9 (period) — T069 (FR-025, FR-026, FR-027, FR-071).

Runs **after** freshness, and the order is deliberate: a stale source is refused
before the system reasons about whether its period is complete. Reasoning about
the shape of a period nobody can answer from is wasted, and worse, it invites a
refusal that names the period when the real problem was the source.

Three things happen here.

**Period shape.** A range entirely in the future is refused. A range containing
today is partial, which is not itself an error — it becomes one only in
comparison.

**Comparison rules** (T065). Incomplete against complete is refused, because the
difference reads as a decline that is really just the day not being over.
Equivalent partials sharing a declared cutoff are permitted and **labelled**,
with the cutoff named.

**Time-zone materiality** (T064). Where a required source's reporting day is
offset from the canonical day, that offset is surfaced as
``TIMEZONE_OFFSET_MATERIAL`` — a caveat, not a refusal. The number is real; it
just draws on two of the source's reporting days, and a reader who does not know
that will over-read a one-day movement.
"""

from __future__ import annotations

from ...contracts.reason_codes import ReasonCode
from ...periods.canonical import PeriodCompleteness, canonical_period
from ...periods.completeness import ComparisonShape, compare_periods
from ...periods.offsets import material_offsets, offsets_for
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, caveat, deny

__all__ = ["gate_9_period"]


def gate_9_period(context: GateContext) -> GateVerdict | None:
    """Resolve the period, police the comparison, surface material offsets."""
    request = context.request
    period = canonical_period(
        request.date_range.start,
        request.date_range.end,
        on=context.on,
        cutoff=context.partial_cutoff,
    )

    if period.completeness is PeriodCompleteness.OUTSIDE_COVERAGE:
        return deny(
            ReasonCode.RANGE_OUTSIDE_COVERAGE,
            SubjectKind.PERIOD,
            f"{period.requested_start}..{period.requested_end}",
            "the requested period starts after the evaluation date; nothing has happened yet",
        )

    if request.comparison is not None:
        baseline = canonical_period(
            request.comparison.baseline_range.start,
            request.comparison.baseline_range.end,
            on=context.on,
            cutoff=context.partial_cutoff,
        )
        verdict = compare_periods(period, baseline)
        if not verdict.permitted:
            assert verdict.reason_code is not None
            return deny(
                verdict.reason_code,
                SubjectKind.PERIOD,
                f"{period.requested_start}..{period.requested_end}",
                verdict.detail,
            )
        if verdict.shape is ComparisonShape.EQUIVALENT_PARTIAL:
            assert verdict.reason_code is not None and verdict.cutoff is not None
            return caveat(
                verdict.reason_code,
                SubjectKind.PERIOD,
                f"{period.requested_start}..{period.requested_end}",
                f"equivalent partial comparison cut at {verdict.cutoff.isoformat()}",
            )

    if period.is_partial and request.comparison is None:
        return caveat(
            ReasonCode.PERIOD_INCOMPLETE,
            SubjectKind.PERIOD,
            f"{period.requested_start}..{period.requested_end}",
            "the requested period includes today, which is still forming",
        )

    offsets = material_offsets(
        offsets_for(
            dict(context.bundle.internal.sources),
            context.required_source_ids,
            on=period.requested_start,
        )
    )
    if offsets:
        first = offsets[0]
        return caveat(
            ReasonCode.TIMEZONE_OFFSET_MATERIAL,
            SubjectKind.SOURCE,
            first.source,
            first.describe(),
        )

    return None
