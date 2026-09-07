"""Input order must not break a tie — T014's proof (`FR-010`).

**Input order carries no meaning here.** `005` hands over candidates in whatever order
its rules ran, which depends on a dict, a file listing and the day. Letting that decide
which of two equal findings a person looks at first invents a priority out of an
implementation detail — and invents it *invisibly*, because the output then looks
exactly like a real ordering.

So the assertion is not "ties exist". It is that **the same findings in a different
order produce the same grouping**, which is the only form of the claim that a
reordering can falsify.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError

from insights_prioritisation.contracts import PrioritisedFinding, PriorityComponent
from insights_prioritisation.order.ties import group_ties, tie_key

pytestmark = pytest.mark.unit

INSTANT = datetime(2026, 8, 26, 13, 24, tzinfo=UTC)


def _finding(identifier: str, **components: str) -> PrioritisedFinding:
    return PrioritisedFinding(
        finding_id=identifier,
        components=tuple(
            PriorityComponent(name=name, read_from="candidate_finding", value=Decimal(value))
            for name, value in components.items()
        ),
        reading_instant=INSTANT,
    )


def test_equal_on_every_component_is_one_reported_tie() -> None:
    groups = group_ties(
        [
            _finding("a", magnitude="0.5", reach="0.2"),
            _finding("b", magnitude="0.5", reach="0.2"),
            _finding("c", magnitude="0.9", reach="0.2"),
        ]
    )
    assert [[f.finding_id for f in g] for g in groups] == [["a", "b"], ["c"]]


def test_the_same_findings_in_a_different_order_group_the_same_way() -> None:
    """**The claim `FR-010` actually makes, and the only form a reordering can falsify.**"""
    findings = [
        _finding("a", magnitude="0.5"),
        _finding("b", magnitude="0.9"),
        _finding("c", magnitude="0.5"),
    ]
    forward = {frozenset(f.finding_id for f in g) for g in group_ties(findings)}
    backward = {frozenset(f.finding_id for f in g) for g in group_ties(list(reversed(findings)))}
    assert forward == backward, "the grouping depends on input order, which carries no meaning"


def test_one_differing_component_is_not_a_tie() -> None:
    """Equal on every component. Not on most of them."""
    groups = group_ties(
        [
            _finding("a", magnitude="0.5", reach="0.2"),
            _finding("b", magnitude="0.5", reach="0.3"),
        ]
    )
    assert [len(g) for g in groups] == [1, 1]


def test_component_order_does_not_decide_whether_two_findings_tie() -> None:
    """A component list built in a different order is the same set of measurements."""
    first = _finding("a", magnitude="0.5", reach="0.2")
    second = _finding("b", reach="0.2", magnitude="0.5")
    assert tie_key(first) == tie_key(second)
    assert len(group_ties([first, second])) == 1


def test_different_precision_is_not_the_same_measurement() -> None:
    """**`Decimal("0.5") == Decimal("0.50")` is True, and reporting that as a tie is wrong.**

    Two components measured to different precision are not the same measurement, and a
    tie is a claim about the findings rather than about the arithmetic that compared
    them. The key uses the exact decimal string for that reason.
    """
    groups = group_ties([_finding("a", magnitude="0.5"), _finding("b", magnitude="0.50")])
    assert [len(g) for g in groups] == [1, 1], (
        "0.5 and 0.50 were reported as a tie; they compare equal but were not measured "
        "to the same precision"
    )


def test_the_vacuous_tie_is_refused_one_level_up_and_the_guard_stays_here() -> None:
    """**Ungrounded is not tied**, and the difference is `F115`.

    With no declared component every pair is trivially equal on every component -- a
    condition satisfied because there was nothing to satisfy it -- which would make
    EVERYTHING one enormous tie.

    **That answer is unreachable, and the measurement is where it is refused: not here.**
    `PrioritisedFinding` will not be built with no components at all, so an ungrounded
    candidate never arrives as one; it travels as `NotPrioritisable`, which `group_ties`
    does not take. The refusal lives in `contracts/prioritised.py`, one file away.

    So the guard in `tie_key` is defence against that refusal being loosened elsewhere,
    and both halves are asserted: the contract refuses the construction, and the guard
    answers `None` rather than an empty key that would tie every ungrounded finding to
    every other.
    """
    with pytest.raises(ValidationError):
        PrioritisedFinding(finding_id="a", components=(), reading_instant=INSTANT)

    # The stand-ins are cast to the contract's type ON PURPOSE, and the cast is the honest
    # form of what this node does: it reaches PAST the contract to hand the guard something
    # the contract would have refused, which is the only way to measure a guard that exists
    # for the day somebody loosens the contract. A `SimpleNamespace` passed silently would
    # have made the reader believe the guard sees a real finding.
    ungrounded = cast(
        "list[PrioritisedFinding]",
        [
            SimpleNamespace(finding_id="a", components=()),
            SimpleNamespace(finding_id="b", components=()),
        ],
    )
    assert tie_key(ungrounded[0]) is None, (
        "a finding with no components answered a key; every such finding would then be "
        "tied with every other, on a condition nothing satisfied"
    )
    assert [len(g) for g in group_ties(ungrounded)] == [1, 1], (
        "two ungrounded findings were reported as tied with each other"
    )


def test_grouping_reports_ties_and_does_not_reorder() -> None:
    """It reports ties; it does not rank.

    Ranking needs the composition rule, which is `D-A` and is the owner's. A function
    that both grouped and sorted would be taking that decision quietly — so the groups
    come back in the order their first member appeared.
    """
    findings = [
        _finding("first", magnitude="0.1"),
        _finding("second", magnitude="0.9"),
        _finding("third", magnitude="0.1"),
    ]
    groups = group_ties(findings)
    assert [g[0].finding_id for g in groups] == ["first", "second"], (
        "the groups were reordered; this function reports ties and must not rank"
    )
