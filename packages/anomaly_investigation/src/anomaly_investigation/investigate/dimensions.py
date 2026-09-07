"""Which segment carried the movement — T024 (`FR-011`).

**Association only.** Every output says *this segment moved by this much and
accounts for this share*. None says the segment **caused** anything, and the
warning travels on every one.

**Reporting the absence of declared dimensions is the requirement**, not a
courtesy. An investigation that found no declared dimension has **zero** segment
contributions and still has to report — which is why `Investigation` is an entity
and not a set. A set with no members reports nothing.

**The five declared dimensions come from the baseline**, `enrichment.dimensions`:
`platform`, `product`, `store`, `country`, `version`. This module does not choose
them and does not invent one when the list is empty.
"""

from __future__ import annotations

from decimal import Decimal

from ..contracts import (
    REQUIRED_CAUSALITY_WARNING,
    AnomalyReasonCode,
    ClaimType,
    Investigation,
    ReconciliationVerdict,
    SegmentContribution,
)
from .reconcile import reconcile

__all__ = ["InvestigationOutcome", "investigate"]


class InvestigationOutcome:
    """The investigation, plus the code an absence is reported under.

    The code travels beside the entity rather than inside it: a reason code is a
    **refusal or a caveat** in this feature's vocabulary, and the investigation
    itself is neither — it emitted.
    """

    __slots__ = ("investigation", "reason_code")

    def __init__(self, investigation: Investigation, reason_code: AnomalyReasonCode | None) -> None:
        self.investigation = investigation
        self.reason_code = reason_code


def investigate(
    rule_id: str,
    *,
    declared_dimensions: tuple[str, ...],
    contributions: tuple[SegmentContribution, ...],
    total_movement: Decimal,
    tolerance: Decimal | None,
    claim_type: ClaimType = ClaimType.CORRELATION,
) -> InvestigationOutcome:
    """Build one candidate's dimension breakdown.

    **The empty case is a result, not an error.** With no declared dimension the
    investigation still emits, carrying `ANOMALY_NO_DIMENSION_DECLARED` — the one
    `ALLOW_WITH_CAVEAT` of this namespace, because nothing was refused: we looked
    and there was nothing declared to look at.

    **Contributions without declared dimensions are refused by the contract**, so
    this never has to decide what that would mean.
    """
    # **Checked before anything else, because a total that is not a number makes
    # every verdict below meaningless.** `NOT_ATTEMPTED` has four origins and a
    # reader could distinguish three of them: no tolerance (the caller knows it
    # did not ask), no contributions (visible on the entity), a suppressed segment
    # (carries a code). The fourth -- segments present, tolerance declared, nothing
    # suppressed -- was **invisible**: no verdict and nothing saying the number
    # handed in was not a number.
    #
    # The word already exists and it is the sibling's: `assess_threshold` refuses a
    # non-finite `observed` with `ANOMALY_FIGURE_UNAVAILABLE`. Same quantity, same
    # refusal, no new vocabulary.
    if not total_movement.is_finite():
        refused = Investigation(
            rule_id=rule_id,
            dimensions_declared=declared_dimensions,
            reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
            claim_type=claim_type,
            causality_warning=REQUIRED_CAUSALITY_WARNING,
        )
        return InvestigationOutcome(refused, AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE)

    if not declared_dimensions:
        empty = Investigation(
            rule_id=rule_id,
            claim_type=claim_type,
            reconciliation=reconcile((), total=total_movement, tolerance=tolerance).verdict,
            causality_warning=REQUIRED_CAUSALITY_WARNING,
        )
        return InvestigationOutcome(empty, AnomalyReasonCode.ANOMALY_NO_DIMENSION_DECLARED)

    outcome = reconcile(contributions, total=total_movement, tolerance=tolerance)
    investigation = Investigation(
        rule_id=rule_id,
        dimensions_declared=declared_dimensions,
        contributions=contributions,
        reconciliation=outcome.verdict,
        residual=outcome.residual,
        claim_type=claim_type,
        causality_warning=REQUIRED_CAUSALITY_WARNING,
    )

    reason: AnomalyReasonCode | None = None
    if any(segment.suppressed for segment in investigation.contributions):
        # Reported per segment and never coerced to zero. This is the code with no
        # FR behind it, anchored in measurement of `002`'s ResultCell.
        reason = AnomalyReasonCode.ANOMALY_SEGMENT_VALUE_SUPPRESSED
    elif outcome.verdict is ReconciliationVerdict.DID_NOT_RECONCILE:
        reason = AnomalyReasonCode.ANOMALY_CONTRIBUTIONS_DID_NOT_RECONCILE

    return InvestigationOutcome(investigation, reason)
