"""This feature's reason codes collide with nobody — `T802`.

**A set intersection over the seven existing enums, not a prefix check.** That
distinction is the whole node: a prefix convention that only checks itself passes while
colliding, because it never looks at what it is supposed to be disjoint from. `005`
wrote that sentence after an earlier draft of its own task list said *"disjoint from the
two that exist"* — which would have checked half the universe.

**And the seven are named by their enums rather than by a count.** A number written here
would age the day an eighth namespace is added; an enum cannot.
"""

from __future__ import annotations

from enum import StrEnum

import pytest
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from anomaly_investigation.contracts import AnomalyReasonCode
from channel_integration.contracts.reason_codes import ChannelReasonCode
from insights_prioritisation.contracts import PriorityReasonCode
from proactive_distribution.contracts import DistributionReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from daily_reporting.contracts import ReportReasonCode
from daily_reporting.contracts.origination_codes import OriginationReasonCode

pytestmark = pytest.mark.contract

#: The seven namespaces that existed before this one, by the enum itself.
UPSTREAM_ENUMS: dict[str, type[StrEnum]] = {
    "001 ReasonCode": ReasonCode,
    "002 AnalyticsReasonCode": AnalyticsReasonCode,
    "003 InterpretationReasonCode": InterpretationReasonCode,
    "004 ChannelReasonCode": ChannelReasonCode,
    "005 AnomalyReasonCode": AnomalyReasonCode,
    "006 PriorityReasonCode": PriorityReasonCode,
    "007 DistributionReasonCode": DistributionReasonCode,
}


def _members(enum: type[StrEnum]) -> set[str]:
    """Names **and** values, because a collision in either is a collision.

    Two enums whose members differ in name but share a value produce two codes that
    serialise identically, and a governed output carries the value.
    """
    return {member.name for member in enum} | {str(member.value) for member in enum}


def test_the_seven_upstream_namespaces_are_reachable_and_non_empty() -> None:
    """**Read this before believing the disjointness below.**

    An intersection against an empty set is empty, so an import that silently resolved
    to nothing would make this file assert disjointness from nobody — a vacuous check,
    the `F115` shape, passing loudest exactly when it holds least.
    """
    for label, enum in UPSTREAM_ENUMS.items():
        assert list(enum), f"{label} resolved to an empty enum"


@pytest.mark.parametrize(
    "mine", [ReportReasonCode, OriginationReasonCode], ids=lambda e: e.__name__
)
def test_this_namespace_is_disjoint_from_every_one_before_it(mine: type[StrEnum]) -> None:
    """Set intersection, per namespace, naming the collision if there is one.

    **Both of this feature's enums are driven**, and the second was added on 2026-08-28: a
    node that checked only the first would have gone on passing while a new namespace
    collided with `007`'s.
    """
    for label, enum in UPSTREAM_ENUMS.items():
        collision = _members(mine) & _members(enum)
        assert not collision, f"{label} shares {sorted(collision)} with {mine.__name__}"


def test_this_features_two_namespaces_do_not_collide_with_each_other() -> None:
    """*Why a report could not be built* and *may the built thing leave* are two questions.

    They are separate enums on purpose, and a code shared between them would let a reader
    mistake an authority refusal for a construction refusal.
    """
    collision = _members(ReportReasonCode) & _members(OriginationReasonCode)
    assert not collision, f"the two namespaces share {sorted(collision)}"


def test_the_intersection_would_catch_a_collision() -> None:
    """**Proof the check bites**, over an enum this file makes rather than the real one.

    A node asserting *no collision* while there is no collision is green for two
    reasons and cannot tell them apart. This is the second reason, measured: an enum
    that deliberately reuses one of this feature's values must be caught.
    """
    borrowed = ReportReasonCode.REPORT_KPI_NOT_DERIVABLE

    class Colliding(StrEnum):
        SOMETHING_ELSE = borrowed.value

    assert _members(ReportReasonCode) & _members(Colliding), (
        "the intersection accepts an enum reusing this feature's own value"
    )


def test_every_code_says_which_product_refused() -> None:
    """The two products never merge, and neither do their reasons.

    A code belongs to the report or to the alert and never to both, because *the
    summary could not be built* and *the summary is built and says nothing more* are
    different outcomes for the person reading.
    """
    for code in ReportReasonCode:
        assert code.value.startswith(("report_", "alert_")), (
            f"{code.name} names neither product, so a reader cannot tell which refused"
        )
