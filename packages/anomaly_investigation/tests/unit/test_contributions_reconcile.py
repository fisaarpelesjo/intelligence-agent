"""Segment contributions reconcile against the total — T026 (`SC-005`).

**A set that does not reconcile is a failure, not a rounding note.** If the parts
do not add up to the movement, either a segment is missing or a figure is wrong,
and both are reasons to distrust the breakdown rather than to publish it with a
shrug.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from anomaly_investigation.contracts import (
    AnomalyReasonCode,
    ClaimType,
    ReconciliationVerdict,
    SegmentContribution,
    SourceValue,
)
from anomaly_investigation.investigate import investigate, reconcile

pytestmark = pytest.mark.unit

DIMENSIONS = ("game",)


def _segment(
    contribution: str, *, label: str = "Fortnite", suppressed: bool = False
) -> SegmentContribution:
    return SegmentContribution(
        dimension="game",
        segment_label=SourceValue(text=label, origin="game"),
        value=None if suppressed else Decimal("10"),
        suppressed=suppressed,
        contribution=Decimal(contribution),
        claim_type=ClaimType.CORRELATION,
    )


# --------------------------------------------------------------------------- #
# The verdict itself
# --------------------------------------------------------------------------- #


def test_parts_that_add_up_reconcile() -> None:
    outcome = reconcile(
        (_segment("6"), _segment("4", label="Valorant")),
        total=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.verdict is ReconciliationVerdict.RECONCILED
    assert outcome.residual == Decimal("0")


def test_parts_that_do_not_add_up_fail_rather_than_round() -> None:
    outcome = reconcile(
        (_segment("6"), _segment("1", label="Valorant")),
        total=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.verdict is ReconciliationVerdict.DID_NOT_RECONCILE
    assert outcome.residual == Decimal("3")


def test_the_tolerance_is_the_callers_and_absorbs_only_what_it_declares() -> None:
    """Two runs over the same numbers, differing only in the declared tolerance.

    The point is that the module decides nothing here: **how close is close
    enough is the rule's declaration**, exactly as the freshness bar is.
    """
    parts = (_segment("6"), _segment("3.995", label="Valorant"))
    tight = reconcile(parts, total=Decimal("10"), tolerance=Decimal("0.001"))
    loose = reconcile(parts, total=Decimal("10"), tolerance=Decimal("0.01"))

    assert tight.verdict is ReconciliationVerdict.DID_NOT_RECONCILE
    assert loose.verdict is ReconciliationVerdict.RECONCILED


def test_no_declared_tolerance_is_a_question_nobody_asked() -> None:
    """`NOT_ATTEMPTED`, never a default — and never `RECONCILED` by omission."""
    outcome = reconcile((_segment("6"),), total=Decimal("10"), tolerance=None)
    assert outcome.verdict is ReconciliationVerdict.NOT_ATTEMPTED
    assert outcome.residual is None


# --------------------------------------------------------------------------- #
# The two cases where reconciling would be a lie
# --------------------------------------------------------------------------- #


def test_a_suppressed_segment_makes_reconciliation_impossible() -> None:
    """**Not merely harder — impossible.**

    A suppressed contribution is unknown, so a residual computed without it is an
    accusation against the segments that *are* visible: it would report a gap the
    visible parts did not cause.
    """
    outcome = reconcile(
        (_segment("6"), _segment("0", label="Valorant", suppressed=True)),
        total=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.verdict is ReconciliationVerdict.NOT_ATTEMPTED
    assert outcome.residual is None


def test_zero_contributions_is_not_reconciled() -> None:
    """An empty sum equals the total only when the total is zero.

    Calling that agreement is the vacuous pass this feature keeps refusing.
    """
    outcome = reconcile((), total=Decimal("0"), tolerance=Decimal("0.01"))
    assert outcome.verdict is ReconciliationVerdict.NOT_ATTEMPTED


# --------------------------------------------------------------------------- #
# The verdict reaching the investigation, with its reason code
# --------------------------------------------------------------------------- #


def test_a_failed_reconciliation_names_its_code() -> None:
    outcome = investigate(
        "trials_drop",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("1"),),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.reconciliation is ReconciliationVerdict.DID_NOT_RECONCILE
    assert outcome.reason_code is AnomalyReasonCode.ANOMALY_CONTRIBUTIONS_DID_NOT_RECONCILE
    assert outcome.investigation.residual == Decimal("9")


def test_a_suppressed_segment_names_the_suppression_and_not_the_mismatch() -> None:
    """The two codes are not interchangeable: one says *the parts disagree*, the
    other says *we could not compare them*. Reporting the first would blame the
    data for something the suppression caused."""
    outcome = investigate(
        "trials_drop",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("0", suppressed=True),),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.reason_code is AnomalyReasonCode.ANOMALY_SEGMENT_VALUE_SUPPRESSED
    assert outcome.investigation.reconciliation is ReconciliationVerdict.NOT_ATTEMPTED


def test_a_reconciled_investigation_carries_no_reason_code() -> None:
    outcome = investigate(
        "trials_drop",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("6"), _segment("4", label="Valorant")),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.reconciliation is ReconciliationVerdict.RECONCILED
    assert outcome.reason_code is None


def test_every_investigation_carries_the_warning_byte_equal() -> None:
    """The contract already enforces it; this proves the module supplies it rather
    than leaving a caller to remember."""
    outcome = investigate(
        "trials_drop",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("10"),),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert "não comprovam causalidade" in outcome.investigation.causality_warning


# --------------------------------------------------------------------------- #
# A total that is not a number, and the four origins of NOT_ATTEMPTED
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("total", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_total_is_named_rather_than_swallowed(total: str) -> None:
    """**A non-finite movement is not a movement**, and the sibling module already
    says so about the same quantity with the same word.

    Before this, such a total produced `NOT_ATTEMPTED` with **no code at all** —
    segments present, tolerance declared, nothing suppressed, and nothing saying
    the number handed in was not a number.
    """
    outcome = investigate(
        "trials_drop",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("6"),),
        total_movement=Decimal(total),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.reconciliation is ReconciliationVerdict.NOT_ATTEMPTED
    assert outcome.reason_code is AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE
    assert outcome.investigation.residual is None


def test_the_four_origins_of_not_attempted_stay_distinguishable() -> None:
    """**The claim this whole feature rests on, applied to its own vocabulary.**

    Four different situations produce the same verdict, and a reader must be able
    to tell them apart — otherwise `NOT_ATTEMPTED` means *something happened* and
    nothing more.
    """
    no_tolerance = investigate(
        "r",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("6"),),
        total_movement=Decimal("10"),
        tolerance=None,
    )
    no_segments = investigate(
        "r",
        declared_dimensions=DIMENSIONS,
        contributions=(),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    suppressed = investigate(
        "r",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("0", suppressed=True),),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    not_a_number = investigate(
        "r",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("6"),),
        total_movement=Decimal("NaN"),
        tolerance=Decimal("0.01"),
    )

    for outcome in (no_tolerance, no_segments, suppressed, not_a_number):
        assert outcome.investigation.reconciliation is ReconciliationVerdict.NOT_ATTEMPTED

    # The caller knows it did not ask, so no code is owed.
    assert no_tolerance.reason_code is None
    # Visible on the entity itself.
    assert no_segments.reason_code is None
    assert no_segments.investigation.contributions == ()
    # Each of the other two carries its own word, and they are different words.
    assert suppressed.reason_code is AnomalyReasonCode.ANOMALY_SEGMENT_VALUE_SUPPRESSED
    assert not_a_number.reason_code is AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE
    assert suppressed.reason_code is not not_a_number.reason_code


def test_a_finite_total_still_reconciles_normally() -> None:
    """The refusal above would be worthless over a function that refused every
    total."""
    outcome = investigate(
        "trials_drop",
        declared_dimensions=DIMENSIONS,
        contributions=(_segment("10"),),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.reconciliation is ReconciliationVerdict.RECONCILED
    assert outcome.reason_code is None
