"""Snapshot and count do not share a scale — T015 (`FR-005`, `FR-010`, `SC-002`, `SC-004`).

**The second and third of the structural requirements, proved here.**

`004` measured the three aggregation classes as not interchangeable. `005` measured
the consequence: `MAU`, `Paid subscribers`, `MRR` and `LTV` are **snapshots** whose
own pipeline documentation warns they inflate about **thirty-fold** if summed across
days. Putting a snapshot movement and a count movement on one scale does not compare
them — it invents a common unit, and whichever finding wins wins for that reason.

**And ties are shape here, not a flag.** An ordering is a tuple of rank groups, so a
group of more than one *is* the reported tie, and there is nowhere to record an order
within it. This file proves the structure cannot express a silently-broken tie rather
than asserting that nobody would break one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from anomaly_investigation.contracts import AggregationClass
from pydantic import ValidationError

from insights_prioritisation.contracts import (
    ComponentAbsence,
    Normalisation,
    NotPrioritisable,
    Ordering,
    PrioritisedFinding,
    PriorityComponent,
    PriorityContractViolation,
    PriorityReasonCode,
)

pytestmark = pytest.mark.unit

INSTANT = datetime(2026, 8, 26, 13, 24, tzinfo=UTC)


def _placed(finding_id: str, value: str = "0.5") -> PrioritisedFinding:
    return PrioritisedFinding(
        finding_id=finding_id,
        components=(
            PriorityComponent(
                name="magnitude", read_from="candidate_finding", value=Decimal(value)
            ),
        ),
        reading_instant=INSTANT,
    )


def _unplaced(finding_id: str) -> NotPrioritisable:
    return NotPrioritisable(
        finding_id=finding_id,
        components=(
            PriorityComponent(
                name="reach",
                read_from="investigation",
                absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
            ),
        ),
        reading_instant=INSTANT,
    )


# --------------------------------------------------------------------------- #
# What an ordering must declare about its members
# --------------------------------------------------------------------------- #


def test_an_ordering_that_declares_neither_class_nor_normalisation_is_refused() -> None:
    """**Nothing would state what these findings have in common.**

    `FR-005` says one ordering per class *absent a declared normalisation*, and a
    class that is never declared makes that requirement uncheckable.
    """
    with pytest.raises((ValidationError, PriorityContractViolation)):
        Ordering(positions=((_placed("a"),),))


def test_an_ordering_that_declares_both_is_refused() -> None:
    """A single class and a cross-class normalisation contradict each other, and
    keeping both lets a reader pick the one that suits them."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        Ordering(
            aggregation_class=AggregationClass.COUNT,
            normalisation=Normalisation(
                basis="movement_share",
                covers=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
            ),
            positions=((_placed("a"),),),
        )


def test_one_class_declared_is_the_ordinary_case() -> None:
    """The refusals above would be vacuous over a type nothing satisfies."""
    ordering = Ordering(aggregation_class=AggregationClass.COUNT, positions=((_placed("a"),),))
    assert ordering.aggregation_class is AggregationClass.COUNT
    assert not ordering.is_empty


def test_a_declared_normalisation_is_the_other_legal_case() -> None:
    """`FR-005` **permits** crossing classes. What it forbids is doing it silently,
    and this is the loud way."""
    ordering = Ordering(
        normalisation=Normalisation(
            basis="movement_share", covers=(AggregationClass.COUNT, AggregationClass.SNAPSHOT)
        ),
        positions=((_placed("a"),), (_placed("b"),)),
    )
    assert ordering.normalisation is not None
    assert ordering.normalisation.basis == "movement_share"


def test_a_normalisation_covering_one_class_is_refused() -> None:
    """**A vacuously-satisfied condition, closed.** `F115`'s shape: without this, a
    caller declares a normalisation covering only `COUNT` and uses its mere presence
    to justify mixing in a `SNAPSHOT` the declaration never mentioned."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        Normalisation(basis="movement_share", covers=(AggregationClass.COUNT,))


def test_a_normalisation_names_the_classes_it_relates() -> None:
    """The refusal above would be vacuous if no `covers` value were legal."""
    n = Normalisation(
        basis="movement_share", covers=(AggregationClass.COUNT, AggregationClass.SNAPSHOT)
    )
    assert set(n.covers) == {AggregationClass.COUNT, AggregationClass.SNAPSHOT}


# --------------------------------------------------------------------------- #
# Ties are a shape, and the shape has no room for a hidden order
# --------------------------------------------------------------------------- #


def test_a_tie_is_a_rank_group_and_is_reported_as_one() -> None:
    """``(a,), (b, c), (d,)`` reads as: `a` first, `b` and `c` **tied**, `d` fourth.

    The tie is not a flag beside a flat list — it is the shape of the list.
    """
    ordering = Ordering(
        aggregation_class=AggregationClass.COUNT,
        positions=((_placed("a"),), (_placed("b"), _placed("c")), (_placed("d"),)),
    )
    assert ordering.ties == (("b", "c"),)


def test_an_ordering_with_no_tie_reports_no_tie() -> None:
    """Non-vacuity for the assertion above: `ties` is derived, so it must be empty
    when nothing tied. A property that always returned something would make the
    test above pass over any input."""
    ordering = Ordering(
        aggregation_class=AggregationClass.COUNT,
        positions=((_placed("a"),), (_placed("b"),)),
    )
    assert ordering.ties == ()


def test_an_empty_rank_group_is_refused() -> None:
    """A rank nobody occupies shifts every rank below it for no reason."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        Ordering(aggregation_class=AggregationClass.COUNT, positions=((_placed("a"),), ()))


# --------------------------------------------------------------------------- #
# A finding lands in exactly one place
# --------------------------------------------------------------------------- #


def test_a_finding_both_ordered_and_not_prioritisable_is_refused() -> None:
    """`SC-002` literally. A reader could not tell what the feature concluded."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        Ordering(
            aggregation_class=AggregationClass.COUNT,
            positions=((_placed("a"),),),
            not_prioritisable=(_unplaced("a"),),
        )


def test_a_finding_ordered_twice_is_refused() -> None:
    """Two positions for one finding is two conclusions published together."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        Ordering(
            aggregation_class=AggregationClass.COUNT,
            positions=((_placed("a"),), (_placed("a"),)),
        )


def test_ordered_and_unplaced_findings_coexist_when_they_are_different_findings() -> None:
    """The refusals above would be vacuous if the two collections could not both be
    populated. `FR-004`'s ordinary case: some placed, some named as unplaceable."""
    ordering = Ordering(
        aggregation_class=AggregationClass.COUNT,
        positions=((_placed("a"),),),
        not_prioritisable=(_unplaced("b"),),
    )
    assert [f.finding_id for group in ordering.positions for f in group] == ["a"]
    assert [f.finding_id for f in ordering.not_prioritisable] == ["b"]
    assert ordering.not_prioritisable[0].missing == ("reach",)


# --------------------------------------------------------------------------- #
# A placed finding states its grounds
# --------------------------------------------------------------------------- #


def test_a_placed_finding_with_no_components_is_refused() -> None:
    """`FR-002`: an ordering whose grounds are not in the output must not be
    produced. A position with no components is exactly that."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisedFinding(finding_id="a", components=(), reading_instant=INSTANT)


def test_a_placed_finding_carrying_an_absent_component_is_refused() -> None:
    """**This is where zero would have crept back in.** A placed finding resting on
    an ingredient nobody obtained needs a number for the arithmetic, and the default
    appears one layer down."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisedFinding(
            finding_id="a",
            components=(
                PriorityComponent(
                    name="magnitude", read_from="candidate_finding", value=Decimal("1")
                ),
                PriorityComponent(
                    name="reach",
                    read_from="investigation",
                    absence=ComponentAbsence(
                        reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE
                    ),
                ),
            ),
            reading_instant=INSTANT,
        )


def test_a_repeated_component_name_is_refused() -> None:
    """A component counted twice weights itself twice without saying so."""
    with pytest.raises((ValidationError, PriorityContractViolation)):
        PrioritisedFinding(
            finding_id="a",
            components=(
                PriorityComponent(
                    name="magnitude", read_from="candidate_finding", value=Decimal("1")
                ),
                PriorityComponent(name="magnitude", read_from="investigation", value=Decimal("2")),
            ),
            reading_instant=INSTANT,
        )


# --------------------------------------------------------------------------- #
# The caveat travels, and the instant travels
# --------------------------------------------------------------------------- #


def test_an_inherited_caveat_travels_with_the_position_that_carries_it() -> None:
    """**The third structural requirement.**

    The per-game attribution of the only real table is declaredly an approximation —
    the builder's own words. A caveat on the *run* would say "something here is
    approximate"; a caveat on the *position* says which one is.
    """
    caveat = (
        "Atribuição por jogo é aproximada: a assinatura inteira vai para o top_game do usuário."
    )
    placed = PrioritisedFinding(
        finding_id="mrr_drop",
        components=(
            PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("1")),
        ),
        reading_instant=INSTANT,
        caveats=(caveat,),
    )
    assert placed.caveats == (caveat,), "the caveat must arrive byte-identical"


@pytest.mark.parametrize("cls", [PrioritisedFinding, NotPrioritisable])
def test_a_naive_reading_instant_is_refused(cls: type) -> None:
    """`FR-012` requires a difference in instants to be **visible**, and two naive
    datetimes cannot be compared across zones. Refused on both types, because the
    requirement is about every reported figure and not only the placed ones."""
    naive = datetime(2026, 8, 26, 13, 24)
    component = (
        PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("1"))
        if cls is PrioritisedFinding
        else PriorityComponent(
            name="reach",
            read_from="investigation",
            absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
        )
    )
    with pytest.raises((ValidationError, PriorityContractViolation)):
        cls(finding_id="a", components=(component,), reading_instant=naive)
