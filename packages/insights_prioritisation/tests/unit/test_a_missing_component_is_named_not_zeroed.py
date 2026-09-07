"""A missing component is named, never zeroed — T010 (`FR-004`, `SC-003`).

**This is the first of the three things `spec.md` § 2 requires to be structure
rather than comment, and this file is the proof that it is.**

The defect has a measured shape in this repository: `Not renewed (qty)` runs 95 to 137
per day for 396 days and then **disappears** on the newest day, and a rule that read
the absence as a value reported **minus 100 per cent** — a fall — instead of *incomplete day*.
Zero in place of an absence does not say *"I do not know"*; it says *"this is the
least important thing here"*.

**Written against the component protocol and not against a fixed list of
components**, so it holds whichever components `D-A` chooses. That matters: `D-A` is
open, and a test that named the components would have to be rewritten when the owner
answers — and a test rewritten under pressure is a test weakened under pressure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from insights_prioritisation.contracts import (
    ComponentAbsence,
    NotPrioritisable,
    PriorityComponent,
    PriorityContractViolation,
    PriorityReasonCode,
)

pytestmark = pytest.mark.unit

INSTANT = datetime(2026, 8, 26, 13, 24, tzinfo=UTC)


def _available(name: str = "magnitude", value: str = "0.34") -> PriorityComponent:
    return PriorityComponent(name=name, read_from="candidate_finding", value=Decimal(value))


def _absent(name: str = "reach") -> PriorityComponent:
    return PriorityComponent(
        name=name,
        read_from="investigation",
        absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
    )


# --------------------------------------------------------------------------- #
# The four states, and only two are legal
# --------------------------------------------------------------------------- #


def test_a_component_with_neither_value_nor_absence_is_refused() -> None:
    """**The zero-default hole, closed at construction.**

    Without this refusal a caller builds a component with neither, and the default
    appears one layer down where no contract is watching — most often as zero.
    """
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PriorityComponent(name="reach", read_from="investigation")


def test_a_component_with_both_is_refused() -> None:
    """Which is it? A component that carries a number *and* a reason for having no
    number lets a reader pick whichever supports their conclusion."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PriorityComponent(
            name="reach",
            read_from="investigation",
            value=Decimal("1"),
            absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
        )


def test_a_component_with_a_value_is_available() -> None:
    """The refusals above would be vacuous over a type nothing satisfies."""
    component = _available()
    assert component.is_available
    assert component.value == Decimal("0.34")


def test_a_component_with_a_named_absence_is_constructible_and_not_available() -> None:
    """The other legal state. **An absence is a first-class outcome**, not an error
    the caller has to encode as a sentinel."""
    component = _absent()
    assert not component.is_available
    assert component.absence is not None
    assert component.absence.reason is PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE


# --------------------------------------------------------------------------- #
# Zero is a measurement. That distinction is the whole point.
# --------------------------------------------------------------------------- #


def test_zero_is_a_legal_value_and_is_not_an_absence() -> None:
    """**The defect was never the number; it was the substitution.**

    A component measured at zero is a measurement, and refusing it would be this
    feature inventing a rule about the data's content. What the contract refuses is
    zero standing in for *"not obtained"* — and the two are now different states
    that cannot be confused, because an absence requires a reason and zero does not
    accept one.
    """
    zero = PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("0"))
    assert zero.is_available
    assert zero.value == Decimal("0")
    assert zero.absence is None


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_component_value_is_refused(bad: str) -> None:
    """A non-finite value looks like a measurement and behaves like an absence:
    every comparison against it is false, so the finding would sort somewhere
    nobody can explain. `005` closed this twice, on a threshold and on a figure."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal(bad))


# --------------------------------------------------------------------------- #
# The absence names itself with a code that describes an absence
# --------------------------------------------------------------------------- #


def test_the_absence_reason_is_a_governed_code_and_not_a_sentence() -> None:
    """Free text here would be prose this feature composed about its own failure,
    and it would be uncountable. A code can be counted, compared and refused."""
    with pytest.raises(ValidationError):
        ComponentAbsence(reason="could not get it")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "wrong",
    [
        PriorityReasonCode.PRIORITY_CLASSES_NOT_COMPARABLE,
        PriorityReasonCode.PRIORITY_RUN_DID_NOT_COMPLETE,
    ],
)
def test_a_code_that_describes_something_else_is_refused_here(
    wrong: PriorityReasonCode,
) -> None:
    """**The `005` lesson: a code with no requirement beside it gets used for
    something that was never its job.**

    Two of the four codes describe a run or an ordering failing. Letting either
    stand in for a missing component would make the vocabulary unreadable —
    *"classes not comparable"* on a component says nothing true.
    """
    with pytest.raises((ValidationError, PriorityContractViolation)):
        ComponentAbsence(reason=wrong)


def test_both_absence_codes_are_accepted() -> None:
    """The refusal above would be vacuous if the permitted set were empty."""
    for code in (
        PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE,
        PriorityReasonCode.PRIORITY_DIRECTION_NOT_DECLARED,
    ):
        assert ComponentAbsence(reason=code).reason is code


# --------------------------------------------------------------------------- #
# And the absence cannot hide inside a placed finding
# --------------------------------------------------------------------------- #


def test_a_not_prioritisable_finding_names_every_missing_component() -> None:
    """`SC-003`: the missing component is named, and **no default appears anywhere
    in that finding's components**."""
    unplaced = NotPrioritisable(
        finding_id="trials_drop",
        components=(_available(), _absent()),
        reading_instant=INSTANT,
    )
    assert unplaced.missing == ("reach",)
    values = [c.value for c in unplaced.components if not c.is_available]
    assert values == [None], "an absent component must carry no number at all"


def test_a_finding_with_everything_available_cannot_be_filed_as_not_prioritisable() -> None:
    """**The mirror refusal, and it is what keeps the two types honest.**

    If a fully-available finding could be filed here, *placed* versus *not
    placeable* would be a caller's opinion rather than a property of the data.
    """
    with pytest.raises((ValidationError, PriorityContractViolation)):
        NotPrioritisable(
            finding_id="trials_drop",
            components=(_available(), _available(name="reach")),
            reading_instant=INSTANT,
        )


def test_a_not_prioritisable_finding_with_no_components_is_refused() -> None:
    """Naming nothing is not naming the missing component."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        NotPrioritisable(finding_id="trials_drop", components=(), reading_instant=INSTANT)
