"""An empty ordering is a result, not an absence — T016 (`FR-009`, `SC-007`).

**The distinction: "nothing deserved attention" and "the prioritiser broke" must
never look the same.**

Both hand back an empty collection, and if the outcome is read from the collection's
length the two become one — an operator who cannot tell them apart learns nothing
from either. `005` closed the identical hole on its own runs; the shape recurs
because emptiness is the natural representation of both.

So the outcome is a **field**, and this file asserts that the field is what carries
the meaning.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from anomaly_investigation.contracts import AggregationClass
from pydantic import ValidationError

from insights_prioritisation.contracts import (
    Ordering,
    PrioritisationRun,
    PrioritisedFinding,
    PriorityComponent,
    PriorityContractViolation,
    PriorityReasonCode,
    RunOutcome,
)

pytestmark = pytest.mark.unit

INSTANT = datetime(2026, 8, 26, 13, 24, tzinfo=UTC)


def _placed(finding_id: str = "a") -> PrioritisedFinding:
    return PrioritisedFinding(
        finding_id=finding_id,
        components=(
            PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("1")),
        ),
        reading_instant=INSTANT,
    )


def _empty_ordering(cls: AggregationClass = AggregationClass.COUNT) -> Ordering:
    return Ordering(aggregation_class=cls)


# --------------------------------------------------------------------------- #
# The two outcomes, and the field that separates them
# --------------------------------------------------------------------------- #


def test_a_completed_run_with_an_empty_ordering_is_a_result() -> None:
    """*"Nothing crossed a threshold today"* is an answer an operator can act on."""
    run = PrioritisationRun(
        outcome=RunOutcome.COMPLETED, orderings=(_empty_ordering(),), read_at=INSTANT
    )
    assert run.produced_nothing
    assert run.reason_code is None
    assert run.orderings[0].is_empty


def test_a_run_that_did_not_complete_is_not_produced_nothing() -> None:
    """**The assertion that keeps the two apart.**

    A failed run holds an empty ordering too, and `produced_nothing` must refuse to
    describe it — otherwise the property becomes the very conflation this module
    exists to prevent.
    """
    run = PrioritisationRun(
        outcome=RunOutcome.DID_NOT_COMPLETE,
        reason_code=PriorityReasonCode.PRIORITY_RUN_DID_NOT_COMPLETE,
        read_at=INSTANT,
    )
    assert not run.produced_nothing
    assert run.reason_code is PriorityReasonCode.PRIORITY_RUN_DID_NOT_COMPLETE


def test_the_two_runs_are_distinguishable_by_a_field_and_not_by_a_length() -> None:
    """Both hold nothing. Only the field tells them apart, which is `SC-007`."""
    completed = PrioritisationRun(
        outcome=RunOutcome.COMPLETED, orderings=(_empty_ordering(),), read_at=INSTANT
    )
    failed = PrioritisationRun(
        outcome=RunOutcome.DID_NOT_COMPLETE,
        reason_code=PriorityReasonCode.PRIORITY_RUN_DID_NOT_COMPLETE,
        orderings=(_empty_ordering(),),
        read_at=INSTANT,
    )
    assert completed.orderings[0].is_empty and failed.orderings[0].is_empty
    assert completed.outcome is not failed.outcome


def test_a_run_with_a_placed_finding_did_not_produce_nothing() -> None:
    """Non-vacuity: `produced_nothing` must be false when something was placed, or
    the assertions above would hold over every run."""
    run = PrioritisationRun(
        outcome=RunOutcome.COMPLETED,
        orderings=(Ordering(aggregation_class=AggregationClass.COUNT, positions=((_placed(),),)),),
        read_at=INSTANT,
    )
    assert not run.produced_nothing


# --------------------------------------------------------------------------- #
# The pairings the contract refuses
# --------------------------------------------------------------------------- #


def test_a_completed_run_carrying_a_reason_code_is_refused() -> None:
    """The code would describe a failure that did not happen, and a reader would
    trust the code over the outcome."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisationRun(
            outcome=RunOutcome.COMPLETED,
            reason_code=PriorityReasonCode.PRIORITY_RUN_DID_NOT_COMPLETE,
            read_at=INSTANT,
        )


def test_a_failed_run_with_no_reason_code_is_refused() -> None:
    """An unnamed failure reports only that something went wrong."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisationRun(outcome=RunOutcome.DID_NOT_COMPLETE, read_at=INSTANT)


@pytest.mark.parametrize(
    "wrong",
    [
        PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE,
        PriorityReasonCode.PRIORITY_DIRECTION_NOT_DECLARED,
        PriorityReasonCode.PRIORITY_CLASSES_NOT_COMPARABLE,
    ],
)
def test_a_code_that_describes_a_component_or_an_ordering_is_refused_on_a_run(
    wrong: PriorityReasonCode,
) -> None:
    """**The `005` lesson again, on a different field.** Three of the four codes
    describe a component or an ordering; putting one on a run says nothing true
    about the run."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisationRun(outcome=RunOutcome.DID_NOT_COMPLETE, reason_code=wrong, read_at=INSTANT)


def test_two_orderings_claiming_the_same_class_are_refused() -> None:
    """The same findings could be ordered twice, differently, and both published."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisationRun(
            outcome=RunOutcome.COMPLETED,
            orderings=(_empty_ordering(), _empty_ordering()),
            read_at=INSTANT,
        )


def test_orderings_of_different_classes_coexist() -> None:
    """The refusal above would be vacuous if several orderings were never legal —
    and several is the **ordinary** case: `FR-005` makes one per class the default."""
    run = PrioritisationRun(
        outcome=RunOutcome.COMPLETED,
        orderings=(
            _empty_ordering(AggregationClass.COUNT),
            _empty_ordering(AggregationClass.SNAPSHOT),
            _empty_ordering(AggregationClass.RATIO),
        ),
        read_at=INSTANT,
    )
    assert len(run.orderings) == 3
    assert {o.aggregation_class for o in run.orderings} == set(AggregationClass)


def test_a_naive_read_at_is_refused() -> None:
    """As on the findings, and for the same reason: a run's conclusions have to be
    datable, because the source is rebuilt daily."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisationRun(outcome=RunOutcome.COMPLETED, read_at=datetime(2026, 8, 26, 13, 24))
