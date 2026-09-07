"""Crossing, and refusing the wrong aggregation class — T019 (`FR-001`, `FR-010`).

**No arithmetic over warehouse values happens here** (`FR-003`). The movement
arrives already derived, through `003`'s comparison surface; this module compares
a derived figure against the rule's own threshold and says whether it crossed.

**A rule applied to the wrong aggregation class is refused, and the refusal names
the class the rule was written for** (`SC-006`). `004` measured the three classes
as not interchangeable, and averaging across them is the failure this refusal
exists to make unreachable.

**The comparison is over a magnitude, and the boundary is inclusive:**
``abs(observed) >= threshold``. Two consequences are stated here rather than left
for a reader to discover.

**A rule written for a fall also fires on a rise of the same size.** That is the
only honest reading of the contract as it stands, because `Rule` **declares no
direction at all** — and if the business wants one, that is a **field of the
rule**, never a trick played with the sign of the threshold.

**And exactly at the threshold crosses.** A rule saying *"alert at 10%"* is read
by an operator as *"10% alerts"*, and a boundary nobody states is a boundary
somebody changes by accident.

**Degenerate thresholds are refused at construction, not compensated for here.**
`Rule` requires ``threshold > 0`` and finite. An earlier version of this module
carried a branch that reported a negative threshold as `NEVER_FIRABLE` — **the
opposite of the truth**, since ``abs(x) >= -5`` holds for every ``x`` and such a
rule fires on everything. One patology hides and the other floods, and the run
published the wrong one as fact. The branch is gone; the condition is impossible.

**No code path produces `NEVER_FIRABLE` or `ANOMALY_RULE_THRESHOLD_UNCROSSABLE`
today, and that is declared rather than left quiet.** See § *Dead vocabulary*
below.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from ..contracts import AggregationClass, AnomalyModel, AnomalyReasonCode, GovernedName, Rule

__all__ = ["ThresholdOutcome", "ThresholdVerdict", "assess_threshold"]


class ThresholdVerdict(StrEnum):
    """What happened to one rule, and the three are deliberately not two.

    `CROSSED` and `DID_NOT_CROSS` are both results of a comparison that *ran*.
    `REFUSED` is a comparison that could not run at all — and collapsing it into
    `DID_NOT_CROSS` would turn *"we could not evaluate"* into *"nothing moved"*,
    which is the distinction `SC-002` exists to protect.
    """

    CROSSED = "crossed"
    DID_NOT_CROSS = "did_not_cross"
    REFUSED = "refused"
    NEVER_FIRABLE = "never_firable"


class ThresholdOutcome(AnomalyModel):
    """One rule's evaluation against one derived movement."""

    rule_id: GovernedName
    verdict: ThresholdVerdict
    observed: Decimal | None = Field(
        default=None, description="The derived movement, as `003` returned it. Never computed here."
    )
    threshold: Decimal | None = None
    reason_code: AnomalyReasonCode | None = None
    written_for: AggregationClass | None = Field(
        default=None,
        description=(
            "Named on a class mismatch, because SC-006 requires the refusal to say which "
            "class the rule was written for rather than only that it was wrong."
        ),
    )

    @model_validator(mode="after")
    def _the_outcome_defends_itself(self) -> ThresholdOutcome:
        """A refusal names its reason; a comparison that ran carries its numbers.

        The same shape the freshness verdict was corrected into: prose saying
        *"present when..."* enforces nothing, and the contract that cannot be
        built wrong is the one that does not need a reviewer to notice.
        """
        refused = self.verdict in (ThresholdVerdict.REFUSED, ThresholdVerdict.NEVER_FIRABLE)
        if refused and self.reason_code is None:
            raise ValueError("a refused threshold outcome must name its reason")
        if not refused and self.reason_code is not None:
            raise ValueError("a threshold outcome that ran carries no refusal reason")
        ran = self.verdict in (ThresholdVerdict.CROSSED, ThresholdVerdict.DID_NOT_CROSS)
        if ran and (self.observed is None or self.threshold is None):
            raise ValueError("a comparison that ran reports both numbers")
        if (
            self.reason_code is AnomalyReasonCode.ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH
            and self.written_for is None
        ):
            raise ValueError("a class mismatch names the class the rule was written for")
        return self


def assess_threshold(
    rule: Rule,
    *,
    observed: Decimal,
    observed_class: AggregationClass,
) -> ThresholdOutcome:
    """Compare a derived movement against a rule's threshold.

    ``observed`` is what `003` derived. **This function does not divide, subtract
    or convert** — it compares, which is the whole of the baseline's
    `business_rules` level and the reason this feature needs no new dependency.
    """
    if observed_class is not rule.aggregation_class:
        return ThresholdOutcome(
            rule_id=rule.rule_id,
            verdict=ThresholdVerdict.REFUSED,
            reason_code=AnomalyReasonCode.ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH,
            written_for=rule.aggregation_class,
        )

    if not observed.is_finite():
        # A non-finite movement is not a movement. Comparing it would produce a
        # verdict from a value no warehouse could have measured.
        return ThresholdOutcome(
            rule_id=rule.rule_id,
            verdict=ThresholdVerdict.REFUSED,
            reason_code=AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE,
        )

    crossed = abs(observed) >= rule.threshold
    return ThresholdOutcome(
        rule_id=rule.rule_id,
        verdict=ThresholdVerdict.CROSSED if crossed else ThresholdVerdict.DID_NOT_CROSS,
        observed=observed,
        threshold=rule.threshold,
    )


# --------------------------------------------------------------------------- #
# Dead vocabulary, declared rather than left quiet
# --------------------------------------------------------------------------- #
#
# `ThresholdVerdict.NEVER_FIRABLE` and `ANOMALY_RULE_THRESHOLD_UNCROSSABLE` have
# **no reachable producer in this module today**, and `Run.never_firable` has no
# writer.
#
# The rule this package inherited from `001` says a declared outcome no code can
# express is dead vocabulary — **and the inverse holds equally**: vocabulary no
# code can produce asserts a capability nobody has.
#
# **Why it is kept rather than deleted.** The spec's Edge Cases describe a real
# condition — *"a rule whose threshold is never crossable... a detector that hides
# it makes the operator believe the KPI is quiet"* — and that condition does not
# arise from the threshold's sign, which was the mistaken reading. It arises from
# the **relationship between a threshold and what the metric can actually do**: a
# rule demanding a 500% move on a bounded ratio can never fire, and nothing here
# knows a metric's bounds. Learning them means asking the catalog, which is a
# port this feature has not been authorized to widen.
#
# **So the honest state is: the word exists, the condition is real, and no
# producer is reachable.** Deleting the vocabulary would erase a known gap;
# leaving it unremarked would let a reader assume something guards it. Neither is
# acceptable, so it is written down here and in the authoritative reason-code
# table, and it is a task for whoever measures a metric's bounds.
