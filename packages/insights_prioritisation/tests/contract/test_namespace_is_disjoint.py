"""This feature's reason codes collide with nobody — T018.

**A set intersection over the five existing enums, not a prefix check.** That
distinction is the whole node: a prefix convention that only checks itself passes
while colliding, because it never looks at what it is supposed to be disjoint from.
`005` wrote that sentence after an earlier draft of its own task list said *"disjoint
from the two that exist"* — which would have checked half the universe.

And the exhaustiveness of the outcome map is asserted here rather than intended, so
a code added without an outcome **fails** instead of defaulting to something.
"""

from __future__ import annotations

from enum import StrEnum

import pytest
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from anomaly_investigation.contracts import AnomalyReasonCode
from channel_integration.contracts.reason_codes import ChannelReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from insights_prioritisation.contracts import (
    PRIORITY_REASON_CODE_OUTCOME,
    Outcome,
    PriorityReasonCode,
    priority_outcome_for,
)

pytestmark = pytest.mark.contract

#: The five namespaces that existed before this one, by the enum itself rather than
#: by a remembered count. A number written here would age; an enum cannot.
UPSTREAM_ENUMS: dict[str, type[StrEnum]] = {
    "001 ReasonCode": ReasonCode,
    "002 AnalyticsReasonCode": AnalyticsReasonCode,
    "003 InterpretationReasonCode": InterpretationReasonCode,
    "004 ChannelReasonCode": ChannelReasonCode,
    "005 AnomalyReasonCode": AnomalyReasonCode,
}


def _members(enum: type[StrEnum]) -> set[str]:
    """Names **and** values, because a collision in either is a collision.

    Two enums whose members differ in name but share a value produce two codes that
    serialise identically, and a governed output carries the value.
    """
    return {m.name for m in enum} | {str(m.value) for m in enum}


def test_the_five_upstream_namespaces_are_reachable_and_non_empty() -> None:
    """**Read this before believing the disjointness below.**

    An intersection against an empty set is empty, so an import that silently
    resolved to nothing would make this file assert disjointness from nobody.
    """
    for label, enum in UPSTREAM_ENUMS.items():
        assert len(list(enum)) > 0, f"{label} resolved to an empty enum"
    assert len(UPSTREAM_ENUMS) == 5, "five namespaces existed before this one"


def test_this_namespace_is_non_empty() -> None:
    """The other half of the same precaution."""
    assert len(list(PriorityReasonCode)) > 0


@pytest.mark.parametrize("label", sorted(UPSTREAM_ENUMS))
def test_no_member_collides_with_an_upstream_namespace(label: str) -> None:
    """Per-namespace so a failure names which one it collided with."""
    collisions = _members(PriorityReasonCode) & _members(UPSTREAM_ENUMS[label])
    assert not collisions, f"collides with {label}: {sorted(collisions)}"


def test_the_outcome_map_is_exhaustive_over_the_enum() -> None:
    """A code added without an outcome fails here rather than defaulting.

    Both directions: a member with no entry, and an entry for no member.
    """
    assert set(PRIORITY_REASON_CODE_OUTCOME) == set(PriorityReasonCode)


def test_every_code_resolves_to_a_declared_outcome() -> None:
    """`priority_outcome_for` raises rather than defaulting, and this walks the
    whole enum so the raise has no unvisited member to hide behind."""
    for code in PriorityReasonCode:
        assert isinstance(priority_outcome_for(code), Outcome)


def test_every_code_is_deny_and_the_absence_of_a_caveat_is_deliberate() -> None:
    """**All four DENY, and that is stated rather than accidental.**

    `005` has one `ALLOW_WITH_CAVEAT` because *"nothing was declared to look at"* is
    a caveat and not a refusal. This feature has met no case of that shape, and
    inventing one to fill the column would be dead vocabulary — the `001` rule.
    """
    outcomes = {PRIORITY_REASON_CODE_OUTCOME[c] for c in PriorityReasonCode}
    assert outcomes == {Outcome.DENY}


def test_the_prefix_is_a_convention_and_the_intersection_is_the_control() -> None:
    """The prefix is checked **after** the intersection, and only as tidiness.

    Stated in this order on purpose: if this test were the only one, a code that
    dropped the prefix would fail while a code that collided would pass.
    """
    assert all(c.name.startswith("PRIORITY_") for c in PriorityReasonCode)
    assert all(str(c.value).startswith("priority_") for c in PriorityReasonCode)
