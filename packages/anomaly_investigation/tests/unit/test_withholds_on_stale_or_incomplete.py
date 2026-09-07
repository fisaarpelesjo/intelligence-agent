"""Nothing fires on data nobody trusts — T014 (`FR-004`).

Written **before** any detector exists, which is the ordering the plan fixed: a
detector built first and guarded second is a detector that fired on bad data at
least once.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from semantic_catalog.freshness.external import (
    CompletenessStatus,
    FreshnessRecord,
    FreshnessSnapshot,
)

from anomaly_investigation.contracts import AnomalyReasonCode
from anomaly_investigation.freshness import (
    CLASS_RANK,
    EVIDENCE_CLASS,
    WITHHOLDING_PRECEDENCE,
    WITHIN_CLASS_ORDER,
    EvidenceClass,
    FreshnessVerdict,
    assess_freshness,
    evidence_class,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def _record(
    status: CompletenessStatus = CompletenessStatus.COMPLETE,
    *,
    ratio: float | None = 1.0,
    updated: datetime | None = NOW,
    source: str = "trials",
) -> FreshnessRecord:
    # `001` refuses a FAILED record with no `last_error` -- measured, not guessed:
    # *"a failure nobody can act on is not a report"*. So the fixture supplies one,
    # and the code under test carries it forward as the withholding's evidence.
    return FreshnessRecord(
        source=source,
        status=status,
        observed_at=NOW,
        completeness_ratio=ratio,
        last_successful_update=updated,
        last_error="load aborted at 04:12" if status is CompletenessStatus.FAILED else None,
    )


def _snapshot(*records: FreshnessRecord, fixture: bool = False) -> FreshnessSnapshot:
    return FreshnessSnapshot(observed_at=NOW, records=records, is_fixture=fixture)


# --------------------------------------------------------------------------- #
# The three the requirement names
# --------------------------------------------------------------------------- #


def test_fresh_and_complete_permits_firing() -> None:
    """The positive case first: the refusals below would be vacuous without it."""
    verdict = assess_freshness(_snapshot(_record()), sources=("trials",), now=NOW)
    assert verdict.permits_firing
    assert verdict.reason_code is None
    assert verdict.sources_examined == ("trials",)


def test_unknown_freshness_withholds_and_names_the_reason() -> None:
    """`UNKNOWN` is a **declared status**, not a missing record."""
    verdict = assess_freshness(
        _snapshot(_record(CompletenessStatus.UNKNOWN)), sources=("trials",), now=NOW
    )
    assert not verdict.permits_firing
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_FRESHNESS_UNKNOWN


def test_an_incomplete_period_withholds() -> None:
    """The baseline's ``block_incomplete_comparisons`` honoured, not restated."""
    verdict = assess_freshness(
        _snapshot(_record(CompletenessStatus.PARTIAL)), sources=("trials",), now=NOW
    )
    assert not verdict.permits_firing
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE


# --------------------------------------------------------------------------- #
# The distinctions that a boolean would have destroyed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (CompletenessStatus.FAILED, AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED),
        (CompletenessStatus.DELAYED, AnomalyReasonCode.ANOMALY_FRESHNESS_STALE),
    ],
)
def test_each_status_names_its_own_reason(
    status: CompletenessStatus, expected: AnomalyReasonCode
) -> None:
    verdict = assess_freshness(_snapshot(_record(status)), sources=("trials",), now=NOW)
    assert verdict.reason_code is expected


def test_a_source_the_snapshot_says_nothing_about_is_not_a_pass() -> None:
    """`record_for` returns `None`, and its own docstring calls that unknown."""
    verdict = assess_freshness(_snapshot(_record()), sources=("trials", "renewals"), now=NOW)
    assert not verdict.permits_firing
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED
    assert verdict.record is None


def test_examining_no_source_at_all_refuses_rather_than_passes() -> None:
    """**The vacuity check.**

    A verdict over an empty source list looked at nothing. Returning *may fire*
    would be a check that reports success by doing nothing — the defect this
    repository has now measured four times in other shapes.
    """
    verdict = assess_freshness(_snapshot(_record()), sources=(), now=NOW)
    assert not verdict.permits_firing
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED
    assert verdict.sources_examined == ()


# --------------------------------------------------------------------------- #
# Completeness: unknown is neither zero nor complete
# --------------------------------------------------------------------------- #


def test_an_unmeasured_ratio_is_not_treated_as_complete() -> None:
    verdict = assess_freshness(
        _snapshot(_record(ratio=None)),
        sources=("trials",),
        now=NOW,
        minimum_completeness=Decimal("0.99"),
    )
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_COMPLETENESS_UNMEASURED


def test_an_unmeasured_ratio_is_ignored_when_no_bar_was_declared() -> None:
    """**A question nobody asked gets no answer.**

    Choosing a default bar here would be inventing a governed threshold — which
    ratio is too low is the rule's declaration, never this module's.
    """
    verdict = assess_freshness(_snapshot(_record(ratio=None)), sources=("trials",), now=NOW)
    assert verdict.permits_firing


def test_a_ratio_below_the_declared_bar_withholds() -> None:
    verdict = assess_freshness(
        _snapshot(_record(ratio=0.8)),
        sources=("trials",),
        now=NOW,
        minimum_completeness=Decimal("0.99"),
    )
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE


# --------------------------------------------------------------------------- #
# Lag: the status is what the loader believed, the clock is what happened
# --------------------------------------------------------------------------- #


def test_a_healthy_status_still_withholds_when_the_clock_disagrees() -> None:
    """`COMPLETE` and three days old is still stale."""
    stale = _record(updated=NOW - timedelta(days=3))
    verdict = assess_freshness(
        _snapshot(stale),
        sources=("trials",),
        now=NOW,
        delay_tolerance=timedelta(hours=6),
    )
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_FRESHNESS_STALE


def test_unobservable_lag_withholds_under_its_own_name() -> None:
    """The three-valued rule `within_tolerance` documents, applied to `lag`.

    `lag` returns `None` when neither a last successful update nor a source event
    time exists. Reading that as *within tolerance* is the exact mistake the
    upstream docstring warns against — **and the withholding is right**.

    **The code is not `ANOMALY_FRESHNESS_UNKNOWN`, and that was a finding against
    an earlier version of this test.** That code means the loader *declared* the
    status unknown; here the record exists and may say `COMPLETE`. The old
    assertion locked the wrong governed word in place, which is worse than a wrong
    line of code: a test that asserts it makes the mistake load-bearing.
    """
    blind = _record(updated=None)
    verdict = assess_freshness(
        _snapshot(blind),
        sources=("trials",),
        now=NOW,
        delay_tolerance=timedelta(hours=6),
    )
    assert not verdict.permits_firing
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_FRESHNESS_NOT_OBSERVABLE
    # And the record is still COMPLETE -- which is the whole reason the two words
    # cannot be one word.
    assert verdict.record is not None
    assert verdict.record.status is CompletenessStatus.COMPLETE


def test_a_declared_status_outranks_an_instrument_limit() -> None:
    """A `PARTIAL` the loader asserted may not hide behind *we could not see*.

    Both conditions are true here: the loader declared `PARTIAL`, and the lag is
    unobservable. Reporting the instrument limit would tell an operator to go look
    at the freshness table when the data itself is incomplete.
    """
    partial_and_blind = _record(CompletenessStatus.PARTIAL, updated=None)
    verdict = assess_freshness(
        _snapshot(partial_and_blind),
        sources=("trials",),
        now=NOW,
        delay_tolerance=timedelta(hours=6),
    )
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE


# --------------------------------------------------------------------------- #
# Precedence, because more than one reason can be true at once
# --------------------------------------------------------------------------- #


def test_ingestion_failure_outranks_staleness() -> None:
    """A failed load is also late. Reporting *stale* sends an operator to the clock
    instead of to the error."""
    failed_and_old = _record(CompletenessStatus.FAILED, updated=NOW - timedelta(days=9))
    verdict = assess_freshness(
        _snapshot(failed_and_old),
        sources=("trials",),
        now=NOW,
        delay_tolerance=timedelta(hours=1),
    )
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED


def test_the_worst_source_decides_for_all_of_them() -> None:
    """One bad source withholds the rule, and the reason is that source's."""
    verdict = assess_freshness(
        _snapshot(_record(), _record(CompletenessStatus.FAILED, source="renewals")),
        sources=("trials", "renewals"),
        now=NOW,
    )
    assert verdict.reason_code is AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED
    assert verdict.record is not None
    assert verdict.record.source == "renewals"


def test_every_code_declares_its_evidence_class() -> None:
    """**The classification is the thing under review**, so it is asserted by member.

    An earlier version split the ranking by index and read the classes back out of
    the tuple. A member sitting in the wrong half was then invisible: the test
    sliced by position and checked the position, which no permutation could fail —
    and one member *was* in the wrong half.
    """
    assert set(EVIDENCE_CLASS) == set(WITHIN_CLASS_ORDER)
    assert EVIDENCE_CLASS[AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED] is EvidenceClass.NO_RECORD
    assert EVIDENCE_CLASS[AnomalyReasonCode.ANOMALY_FRESHNESS_UNKNOWN] is EvidenceClass.DECLARED
    assert (
        EVIDENCE_CLASS[AnomalyReasonCode.ANOMALY_FRESHNESS_NOT_OBSERVABLE]
        is EvidenceClass.NOT_REACHED
    )


def test_no_record_is_not_a_declaration() -> None:
    """The finding that produced the third class, stated as its own assertion.

    *"No `FreshnessRecord` for this source"* means the freshness table **has no
    row** — the strongest form of *our instrument did not reach*, not an instance
    of the loader speaking. Classifying it as `DECLARED` told a caller that
    somebody asserted something, and sent an operator to ask whoever loads the
    data about a row that does not exist.
    """
    assert (
        EVIDENCE_CLASS[AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED] is not EvidenceClass.DECLARED
    )


def test_declared_evidence_outranks_an_instrument_limit_by_class() -> None:
    """Asked over the **class**, not over a slice of the tuple.

    This is the criterion itself: a `PARTIAL` somebody asserted must never be
    reported as *we could not see*. Any member misclassified fails here, which is
    exactly what the sliced version could not do.
    """
    declared = [c for c, k in EVIDENCE_CLASS.items() if k is EvidenceClass.DECLARED]
    not_reached = [c for c, k in EVIDENCE_CLASS.items() if k is EvidenceClass.NOT_REACHED]
    assert declared and not_reached

    for d in declared:
        for n in not_reached:
            assert WITHHOLDING_PRECEDENCE.index(d) < WITHHOLDING_PRECEDENCE.index(n)


def test_absence_of_a_record_outranks_every_other_class() -> None:
    """Total absence is worse than a declared `PARTIAL`: a partial row still says
    *how* partial, and a missing row says nothing at all."""
    no_record = [c for c, k in EVIDENCE_CLASS.items() if k is EvidenceClass.NO_RECORD]
    assert no_record
    for absent in no_record:
        others = [c for c in WITHHOLDING_PRECEDENCE if c not in no_record]
        assert all(
            WITHHOLDING_PRECEDENCE.index(absent) < WITHHOLDING_PRECEDENCE.index(o) for o in others
        )


def test_the_precedence_is_derived_from_the_classes_and_not_hand_written() -> None:
    """The tuple is a **consequence** of the classification, and the direction is
    the point: when the tuple came first, the classification could not be wrong,
    only the order could — and the defect was in the classification."""
    expected = tuple(
        code for rank in CLASS_RANK for code in WITHIN_CLASS_ORDER if EVIDENCE_CLASS[code] is rank
    )
    assert expected == WITHHOLDING_PRECEDENCE
    assert CLASS_RANK == (
        EvidenceClass.NO_RECORD,
        EvidenceClass.DECLARED,
        EvidenceClass.NOT_REACHED,
    )


def test_the_resulting_order_is_this_one() -> None:
    """Equality over the derived result, so a change to any class or to the
    within-class order is visible as a diff rather than as silence."""
    assert WITHHOLDING_PRECEDENCE == (
        AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED,
        AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED,
        AnomalyReasonCode.ANOMALY_FRESHNESS_UNKNOWN,
        AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE,
        AnomalyReasonCode.ANOMALY_FRESHNESS_STALE,
        AnomalyReasonCode.ANOMALY_FRESHNESS_NOT_OBSERVABLE,
        AnomalyReasonCode.ANOMALY_COMPLETENESS_UNMEASURED,
    )


def test_the_precedence_covers_every_code_it_ranks_exactly_once() -> None:
    """A reason the module can produce but the ranking omits would sort by
    accident, and a duplicate would make `index` silently prefer the first."""
    assert len(set(WITHHOLDING_PRECEDENCE)) == len(WITHHOLDING_PRECEDENCE)


def test_evidence_class_raises_rather_than_defaulting() -> None:
    """A default would make an unclassified code indistinguishable from a
    classified one, and the classification is the governed fact."""
    assert evidence_class(AnomalyReasonCode.ANOMALY_FRESHNESS_STALE) is EvidenceClass.DECLARED
    with pytest.raises(KeyError):
        evidence_class(AnomalyReasonCode.ANOMALY_RULE_METRIC_NOT_BOUND)


# --------------------------------------------------------------------------- #
# The fixture flag travels and does not withhold
# --------------------------------------------------------------------------- #


def test_a_fixture_snapshot_permits_firing_but_says_it_is_a_fixture() -> None:
    """`SC-001` demands the real warehouse, and this is the field that will keep
    `T023` honest — it travels rather than blocking, because a fixture is a
    legitimate way to run a unit test and an illegitimate way to prove `SC-001`."""
    verdict = assess_freshness(_snapshot(_record(), fixture=True), sources=("trials",), now=NOW)
    assert verdict.permits_firing
    assert verdict.observed_from_fixture

    real = assess_freshness(_snapshot(_record()), sources=("trials",), now=NOW)
    assert not real.observed_from_fixture


# --------------------------------------------------------------------------- #
# The verdict defends itself -- the three states a reviewer constructed by hand
# --------------------------------------------------------------------------- #


def test_a_withholding_without_a_reason_is_refused() -> None:
    """**A refusal nobody can act on is not a report.**

    The exact rule `001` enforces one layer up by refusing a ``FAILED`` record with
    no ``last_error``. That lesson reached this feature as a corrected test fixture;
    this is the same lesson applied to the contract this feature authors.
    """
    with pytest.raises(ValidationError):
        FreshnessVerdict(permits_firing=False, sources_examined=("trials",))


def test_a_permission_carrying_a_reason_is_refused() -> None:
    """A contradiction a caller could read either way, and the readings are
    *fire* and *do not fire*."""
    with pytest.raises(ValidationError):
        FreshnessVerdict(
            permits_firing=True,
            reason_code=AnomalyReasonCode.ANOMALY_FRESHNESS_STALE,
            sources_examined=("trials",),
        )


def test_a_permission_that_examined_nothing_is_refused_by_the_type() -> None:
    """`assess_freshness` already refuses this at its door.

    But **the function guarding while the type does not** means anyone assembling
    a verdict by hand gets no guard — and Phase 3 assembles by hand.
    """
    with pytest.raises(ValidationError):
        FreshnessVerdict(permits_firing=True, sources_examined=())


def test_the_two_legitimate_shapes_still_build() -> None:
    """The refusals above would be vacuous if nothing satisfied the contract."""
    permitted = FreshnessVerdict(permits_firing=True, sources_examined=("trials",))
    withheld = FreshnessVerdict(
        permits_firing=False,
        reason_code=AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE,
        sources_examined=("trials",),
    )
    assert permitted.reason_code is None
    assert withheld.reason_code is AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE


def test_a_withholding_may_examine_nothing() -> None:
    """The empty-source refusal is itself a withholding with no sources examined,
    so the type must allow exactly that shape and no other."""
    verdict = assess_freshness(_snapshot(_record()), sources=(), now=NOW)
    assert not verdict.permits_firing
    assert verdict.sources_examined == ()
