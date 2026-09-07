"""Composing what is present is worse than not composing — T011's proof (`FR-004`).

**A finding placed on partial grounds is not placed lower. It is placed WRONGLY**, and
nothing downstream can tell: three components out of four produce a number on a
different scale from a finding that had all four, and the two then sort against each
other as if they were comparable.

`spec.md` § 2 names it: *a missing component defaulted to zero silently ranks something
last*, and zero *"does not express ignorance — it expresses this finding is
unimportant"*.

**And the empty case refuses through the same door**, which is the part worth asserting
rather than assuming. With `D-A` open there are no declared components, so a finding has
no grounds at all — and a position resting on nothing is not a position, which `FR-002`
forbids by requiring the position to be reconstructible from its output.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from insights_prioritisation.contracts import (
    ComponentAbsence,
    PriorityComponent,
    PriorityReasonCode,
)
from insights_prioritisation.score import absent_components, may_compose

pytestmark = pytest.mark.unit


def _value(name: str, value: str = "0.34") -> PriorityComponent:
    return PriorityComponent(name=name, read_from="candidate_finding", value=Decimal(value))


def _absent(name: str) -> PriorityComponent:
    return PriorityComponent(
        name=name,
        read_from="investigation",
        absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
    )


def test_a_complete_set_may_be_composed() -> None:
    """The positive half, or the refusals below would pass with the rule deleted."""
    assert may_compose([_value("magnitude"), _value("reach", "0.9")])


def test_one_absence_refuses_the_whole_composition() -> None:
    """**Not "compose the rest". The rest is a different scale wearing the same shape.**"""
    components = [_value("magnitude"), _absent("reach"), _value("recency", "0.5")]
    assert not may_compose(components)
    assert [c.name for c in absent_components(components)] == ["reach"]


def test_a_measured_zero_does_not_refuse() -> None:
    """**The distinction the whole feature turns on, at the other boundary.**

    A component that genuinely measured zero is COMPLETE. If this refused on it, the
    feature would treat a real measurement as missing data — the same collapse as
    treating missing data as zero, running the other way.
    """
    assert may_compose([_value("magnitude", "0"), _value("reach", "0")])


def test_no_components_at_all_refuses_too() -> None:
    """A position resting on nothing is not a position.

    This is where `D-A` being open lands today: no component is declared, so no finding
    has grounds, and composing is refused for every one of them. **It is not a special
    case** — it falls out of "every declared component carries a value", because with
    none declared none carries one.
    """
    assert not may_compose([])
    assert absent_components([]) == ()


def test_the_absences_come_back_as_components_and_not_as_names() -> None:
    """`NotPrioritisable` carries what was obtained AND what was not.

    A caller building one needs the absences themselves; re-deriving them from names
    would be the second lookup that drifts from the first.
    """
    missing = absent_components([_value("magnitude"), _absent("reach")])
    assert len(missing) == 1
    assert missing[0].absence is not None
    assert missing[0].absence.reason is PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE
    assert missing[0].read_from == "investigation", "the source entity travels with the absence"
