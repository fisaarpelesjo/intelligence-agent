"""A reader's failure becomes a named absence and never a number — T009's proof (`FR-004`).

`T010` proves the CONTRACT refuses a component with neither a value nor an absence.
This proves the MACHINERY never builds one that way, and — the part that matters —
that it converts in one direction only.

**The measured shape of the defect:** `Not renewed (qty)` ran 95 to 137 per day for 396
days and then disappeared on the newest day, and a rule that read the absence as a value
reported **minus one hundred per cent** — a fall — instead of *incomplete day*. A zero
in place of an absence does not say "I do not know"; it says "this is the least
important thing here".

**And the registry is empty on purpose**, because `D-A` is open and is the owner's. That
is asserted too: an empty declaration must yield nothing, not an empty success.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from insights_prioritisation.contracts import PriorityReasonCode
from insights_prioritisation.score import (
    DECLARED_COMPONENTS,
    read_component,
    read_components,
)

pytestmark = pytest.mark.unit


class _Reader:
    """A reader that answers what it was told to answer. Not a component — a way to get one."""

    def __init__(self, name: str, read_from: str, answer: Decimal | None) -> None:
        self.name = name
        self.read_from = read_from
        self._answer = answer

    def __call__(self, finding: object) -> Decimal | None:
        return self._answer


class _Broken:
    """A reader with a defect in it, which is NOT the same thing as missing data."""

    name = "magnitude"
    read_from = "candidate_finding"

    def __call__(self, finding: object) -> Decimal | None:
        raise RuntimeError("the reader is broken")


def test_a_reader_that_answers_gives_a_component_carrying_its_value() -> None:
    component = read_component(_Reader("magnitude", "candidate_finding", Decimal("0.34")), None)
    assert component.value == Decimal("0.34")
    assert component.absence is None
    assert component.read_from == "candidate_finding"


def test_zero_is_a_value_and_not_an_absence() -> None:
    """**The distinction the whole feature turns on, asserted at the boundary.**

    A component that genuinely measured zero must arrive as a VALUE. If this module
    treated a falsy answer as missing, the two would collapse — and the collapse would
    run in the safe-looking direction, reporting a real zero as unknown.
    """
    component = read_component(_Reader("reach", "investigation", Decimal(0)), None)
    assert component.value == Decimal(0)
    assert component.absence is None, "a measured zero was reported as missing data"


def test_a_reader_that_cannot_answer_gives_a_named_absence_and_no_number() -> None:
    component = read_component(_Reader("reach", "investigation", None), None)
    assert component.value is None, "a failure became a number"
    assert component.absence is not None
    assert component.absence.reason is PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE


def test_a_broken_reader_is_not_reported_as_missing_data() -> None:
    """**The two need different fixes, and one code for both tells nobody which.**

    Swallowing the exception would report a defect in the reader as an absence of data.
    The absence is the honest answer for *"the investigation has no reach"*; it is a lie
    for *"the reach function raised"*.
    """
    with pytest.raises(RuntimeError):
        read_component(_Broken(), None)


def test_both_kinds_come_back_together_so_a_reader_sees_the_gap() -> None:
    """`NotPrioritisable` carries what was obtained AND what was not.

    A shorter list would say only that something is missing; the pair says which.
    """
    readers = (
        _Reader("magnitude", "candidate_finding", Decimal("0.34")),
        _Reader("reach", "investigation", None),
    )
    components = read_components(None, readers=readers)

    assert [c.name for c in components] == ["magnitude", "reach"]
    assert components[0].value == Decimal("0.34") and components[0].absence is None
    assert components[1].value is None and components[1].absence is not None


def test_the_registry_holds_exactly_the_two_components_he_chose() -> None:
    """**`D-A` was answered on 2026-08-27, and this node was re-derived against it.**

    It asserted the registry was EMPTY, and said in its own docstring that the day he
    answered it would fail and be re-derived — *"that failure is the good outcome"*. It
    failed on the day, and this is the re-derivation.

    **What is refused is asserted beside what is chosen**, because a decision recorded
    only as what it includes leaves the exclusions to memory. Direction is a filter and
    not a component; trust and recency are out; duration was offered and withdrawn
    because nothing here persists a run to read *"consecutive days"* from.
    """
    declared = [reader.name for reader in DECLARED_COMPONENTS]
    assert declared == ["magnitude", "reach"], (
        f"the registry declares {declared}; D-A chose magnitude and reach, in that order"
    )
    for refused in ("direction", "trust", "recency", "duration"):
        assert refused not in declared, (
            f"{refused!r} is a component of the ORDER, and D-A does not make it one"
        )

    obtained = read_components(None)
    assert [component.name for component in obtained] == ["magnitude", "reach"]
    assert all(component.value is None for component in obtained), (
        "a component produced a value for a finding that is not one; both readers must "
        "answer None until a mean per metric and an investigation actually arrive"
    )
