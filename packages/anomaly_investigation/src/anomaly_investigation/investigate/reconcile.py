"""Do the segments account for the movement? — T025 (`SC-005`).

**The arithmetic here is a sum and a subtraction over figures `003` already
derived.** `FR-003` forbids arithmetic over *warehouse values*; adding up
contributions that were each obtained through the governed seam is not that, and
the alternative — asking upstream to reconcile — would be asking it a question
about our own breakdown.

**The tolerance is the caller's**, for the same reason the freshness bar is: how
close is close enough is a rule's declaration. Passing none means the question was
not asked, and an unasked question gets `NOT_ATTEMPTED` rather than a default.
"""

from __future__ import annotations

from decimal import Decimal

from ..contracts import ReconciliationVerdict, SegmentContribution

__all__ = ["Reconciliation", "reconcile"]


class Reconciliation:
    """The verdict and the remainder, together.

    A plain pair rather than a model: it is an intermediate result on the way to
    the `Investigation`, and giving it a second contract would mean two shapes
    asserting the same fact.
    """

    __slots__ = ("residual", "verdict")

    def __init__(self, verdict: ReconciliationVerdict, residual: Decimal | None) -> None:
        self.verdict = verdict
        self.residual = residual


def reconcile(
    contributions: tuple[SegmentContribution, ...],
    *,
    total: Decimal,
    tolerance: Decimal | None,
) -> Reconciliation:
    """Compare the sum of contributions against the total movement.

    **A suppressed segment makes reconciliation impossible, not merely harder.**
    Its contribution is unknown, so any residual computed without it would be an
    accusation against the segments that *are* visible. This returns
    `NOT_ATTEMPTED` rather than a residual that reads as a real gap.

    **Zero contributions is also `NOT_ATTEMPTED`**, never `RECONCILED`: an empty
    sum equals the total only when the total is zero, and agreeing with nobody is
    the vacuous pass this feature keeps refusing.
    """
    if not total.is_finite():
        # **A non-finite movement is not a movement**, and the sibling module says
        # the same thing about the same quantity: comparing it would produce a
        # verdict from a value no warehouse could have measured. Reported here
        # rather than swallowed, because the caller must be able to tell this from
        # the three legitimate reasons the verdict is NOT_ATTEMPTED.
        return Reconciliation(ReconciliationVerdict.NOT_ATTEMPTED, None)

    if not contributions or tolerance is None:
        return Reconciliation(ReconciliationVerdict.NOT_ATTEMPTED, None)

    if any(segment.suppressed for segment in contributions):
        return Reconciliation(ReconciliationVerdict.NOT_ATTEMPTED, None)

    accounted = sum((segment.contribution for segment in contributions), Decimal(0))
    residual = total - accounted

    if not residual.is_finite():
        return Reconciliation(ReconciliationVerdict.NOT_ATTEMPTED, None)

    verdict = (
        ReconciliationVerdict.RECONCILED
        if abs(residual) <= tolerance
        else ReconciliationVerdict.DID_NOT_RECONCILE
    )
    return Reconciliation(verdict, residual)
