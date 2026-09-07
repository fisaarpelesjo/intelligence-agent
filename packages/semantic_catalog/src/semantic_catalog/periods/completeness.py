"""Period completeness and partial comparison — T065 (FR-025, FR-026).

One refusal and one permission, and the pair is the whole point.

**Refused: incomplete against complete.** Today-so-far against all of yesterday
shows a decline that is entirely an artefact of the day not being over. It is the
most plausible-looking wrong chart the catalog can produce, and nothing in the
output would hint at the cause.

**Permitted: equivalent partials sharing a cutoff.** Today up to 12:00 against
yesterday up to 12:00 is a fair comparison, and it is returned **labelled
partial with the cutoff named** — the label is not decoration, it is what stops
the number being read as a full-day figure later.

A cutoff is required for the permission, never inferred. Guessing one would
manufacture the equivalence the rule exists to verify.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import StrEnum

from ..contracts.reason_codes import ReasonCode
from .canonical import CanonicalPeriod

__all__ = ["ComparisonShape", "ComparisonVerdict", "compare_periods"]


class ComparisonShape(StrEnum):
    """What kind of comparison two periods form."""

    BOTH_COMPLETE = "both_complete"
    EQUIVALENT_PARTIAL = "equivalent_partial"
    PARTIAL_VS_COMPLETE = "partial_vs_complete"
    MISMATCHED_CUTOFF = "mismatched_cutoff"
    OUTSIDE_COVERAGE = "outside_coverage"


@dataclass(frozen=True, slots=True)
class ComparisonVerdict:
    """The shape, its governed reason code, and the cutoff when one applies."""

    shape: ComparisonShape
    reason_code: ReasonCode | None
    cutoff: time | None
    detail: str

    @property
    def permitted(self) -> bool:
        return self.shape in (
            ComparisonShape.BOTH_COMPLETE,
            ComparisonShape.EQUIVALENT_PARTIAL,
        )


def compare_periods(
    subject: CanonicalPeriod,
    baseline: CanonicalPeriod,
) -> ComparisonVerdict:
    """Classify a comparison between two canonical periods.

    ``None`` as a reason code means nothing needs saying: two complete periods
    compare without caveat.
    """
    if (
        subject.completeness is subject.completeness.OUTSIDE_COVERAGE
        or baseline.completeness is baseline.completeness.OUTSIDE_COVERAGE
    ):
        return ComparisonVerdict(
            shape=ComparisonShape.OUTSIDE_COVERAGE,
            reason_code=ReasonCode.RANGE_OUTSIDE_COVERAGE,
            cutoff=None,
            detail="one side of the comparison lies entirely in the future",
        )

    if subject.is_complete and baseline.is_complete:
        return ComparisonVerdict(
            shape=ComparisonShape.BOTH_COMPLETE,
            reason_code=None,
            cutoff=None,
            detail="both periods are finished",
        )

    if subject.is_partial != baseline.is_partial:
        forming = subject if subject.is_partial else baseline
        return ComparisonVerdict(
            shape=ComparisonShape.PARTIAL_VS_COMPLETE,
            reason_code=ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON,
            cutoff=None,
            detail=(
                f"the period ending {forming.requested_end} is still forming while the other "
                "is finished; the difference would read as a decline"
            ),
        )

    # Both partial from here.
    if subject.partial_cutoff is None or baseline.partial_cutoff is None:
        return ComparisonVerdict(
            shape=ComparisonShape.MISMATCHED_CUTOFF,
            reason_code=ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON,
            cutoff=None,
            detail=(
                "both periods are partial but no shared cutoff was declared; a cutoff is "
                "never inferred, because guessing one manufactures the equivalence"
            ),
        )
    if subject.partial_cutoff != baseline.partial_cutoff:
        return ComparisonVerdict(
            shape=ComparisonShape.MISMATCHED_CUTOFF,
            reason_code=ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON,
            cutoff=None,
            detail=(
                f"cutoffs differ ({subject.partial_cutoff} vs {baseline.partial_cutoff}); "
                "unequal partials are not equivalent"
            ),
        )

    return ComparisonVerdict(
        shape=ComparisonShape.EQUIVALENT_PARTIAL,
        reason_code=ReasonCode.EQUIVALENT_PARTIAL_COMPARISON,
        cutoff=subject.partial_cutoff,
        detail=f"both periods cut at {subject.partial_cutoff.isoformat()}",
    )
