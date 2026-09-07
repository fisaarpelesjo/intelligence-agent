"""Crossing classes is possible but never silent — T013's proof (`FR-005`).

`FR-005` permits two answers and forbids a third: one ordering per class, or one under
a **declared** normalisation that appears in the output. The forbidden one is a single
ordering across classes on a scale nobody declared.

**The strongest assertion here is about what cannot be SAID, not about what is
refused.** `one_ordering_per_class` has no parameter that would express a merged
ordering, and `single_normalised_ordering` has no default for its normalisation. A
refusal can be deleted by someone in a hurry; a signature that cannot express the wrong
answer cannot be.

**And this file is where the contract's fifth refusal becomes true.** `Ordering`'s
validator documents a refusal for *a member outside the declared class* and cannot
implement it — `PrioritisedFinding` carries no class, because the class belongs to the
`005` rule that produced the candidate. The construction here is what makes the claim
hold, so the construction is what is asserted.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from anomaly_investigation.contracts import AggregationClass

from insights_prioritisation.contracts import (
    Normalisation,
    PrioritisedFinding,
    PriorityComponent,
    PriorityContractViolation,
)
from insights_prioritisation.order import one_ordering_per_class, single_normalised_ordering

pytestmark = pytest.mark.unit

INSTANT = datetime(2026, 8, 26, 13, 24, tzinfo=UTC)


def _finding(identifier: str) -> PrioritisedFinding:
    return PrioritisedFinding(
        finding_id=identifier,
        components=(
            PriorityComponent(
                name="magnitude", read_from="candidate_finding", value=Decimal("0.5")
            ),
        ),
        reading_instant=INSTANT,
    )


def test_one_ordering_per_class_and_the_classes_are_never_merged() -> None:
    """Two classes in, two orderings out, each declaring the class its members share."""
    orderings = one_ordering_per_class(
        {
            AggregationClass.COUNT: [(_finding("a"),), (_finding("b"),)],
            AggregationClass.SNAPSHOT: [(_finding("c"),)],
        }
    )
    assert len(orderings) == 2
    assert {o.aggregation_class for o in orderings} == {
        AggregationClass.COUNT,
        AggregationClass.SNAPSHOT,
    }
    for ordering in orderings:
        assert ordering.normalisation is None, "a per-class ordering declares no normalisation"
    placed = [f.finding_id for o in orderings for g in o.positions for f in g]
    assert sorted(placed) == ["a", "b", "c"], "a finding was lost or duplicated across classes"


def test_the_merged_ordering_is_unsayable_rather_than_refused() -> None:
    """**The load-bearing assertion, and it is about the signature.**

    A refusal can be deleted by somebody in a hurry. A function with no parameter for
    the wrong answer cannot produce it at all, and that is the difference between a rule
    and a structure.
    """
    parameters = inspect.signature(one_ordering_per_class).parameters
    assert list(parameters) == ["ranked", "not_prioritisable"], (
        f"one_ordering_per_class takes {list(parameters)}; a parameter that could express "
        "a single ordering across classes would make FR-005's forbidden answer reachable"
    )

    normalisation = inspect.signature(single_normalised_ordering).parameters["normalisation"]
    assert normalisation.default is inspect.Parameter.empty, (
        "the normalisation has a default, so a caller can cross classes by omission -- "
        "which is exactly the silent scale FR-005 forbids"
    )


def test_the_result_order_is_stable_so_two_runs_can_be_diffed() -> None:
    """A run answering a different order for the same input cannot be diffed.

    `005` paid for this lesson on figures, where the same statement answered three to
    five values across five runs. The same rule applies to a sequence.
    """
    ranked = {
        AggregationClass.SNAPSHOT: [(_finding("c"),)],
        AggregationClass.COUNT: [(_finding("a"),)],
    }
    first = [o.aggregation_class for o in one_ordering_per_class(ranked)]
    reversed_input = dict(reversed(list(ranked.items())))
    second = [o.aggregation_class for o in one_ordering_per_class(reversed_input)]
    assert first == second, "the ordering of orderings depends on input order"


def test_a_normalisation_licenses_exactly_the_classes_it_names() -> None:
    """Covering less than is present, and covering more, are both refused.

    Less is the obvious hole: a basis over two classes quietly carrying a third. **More
    is the subtler one** — a declaration claiming three over an ordering holding two
    cannot be checked against this output, and the same declaration would then license a
    later ordering that does hold the third.
    """
    basis = Normalisation(
        basis="declared_basis",
        covers=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
    )

    ordering = single_normalised_ordering(
        [(_finding("a"), _finding("b"))],
        normalisation=basis,
        classes_present=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
    )
    assert ordering.normalisation is basis
    assert ordering.aggregation_class is None, "a normalised ordering declares no single class"

    with pytest.raises(PriorityContractViolation):
        single_normalised_ordering(
            [(_finding("a"),)],
            normalisation=basis,
            classes_present=(
                AggregationClass.COUNT,
                AggregationClass.SNAPSHOT,
                AggregationClass.RATIO,
            ),
        )

    with pytest.raises(PriorityContractViolation):
        single_normalised_ordering(
            [(_finding("a"),)],
            normalisation=basis,
            classes_present=(AggregationClass.COUNT,),
        )


def test_a_normalised_ordering_with_no_class_stated_is_refused() -> None:
    """Stating none makes the normalisation uncheckable against the output it licenses."""
    basis = Normalisation(
        basis="declared_basis",
        covers=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
    )
    with pytest.raises(PriorityContractViolation):
        single_normalised_ordering([(_finding("a"),)], normalisation=basis, classes_present=())


def test_the_not_prioritisable_are_carried_once_and_not_per_class() -> None:
    """**A choice, stated because it is one.**

    A finding that could not be placed has no class to belong to — its components are
    missing, which is why it is there. Duplicating it across every ordering would make
    `SC-002`'s "appears in both" refusal fire on a finding nobody placed twice.
    """
    from insights_prioritisation.contracts import (
        ComponentAbsence,
        NotPrioritisable,
        PriorityReasonCode,
    )

    unplaced = NotPrioritisable(
        finding_id="d",
        components=(
            PriorityComponent(
                name="reach",
                read_from="investigation",
                absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
            ),
        ),
        reading_instant=INSTANT,
    )
    orderings = one_ordering_per_class(
        {
            AggregationClass.COUNT: [(_finding("a"),)],
            AggregationClass.SNAPSHOT: [(_finding("c"),)],
        },
        not_prioritisable=[unplaced],
    )
    carried = [f.finding_id for o in orderings for f in o.not_prioritisable]
    assert carried == ["d"], f"the unplaced finding was carried {len(carried)} times"
