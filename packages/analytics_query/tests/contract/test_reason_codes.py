"""Reason-code namespace (`FR-046`, `FR-047`, `FR-048`).
Reason-code contract — T014 (FR-047, FR-048; SC-008).

Three properties, each of which fails loudly rather than degrading:

**Disjointness.** The two namespaces share no member, so a consumer can switch on
one ``code`` field without ever asking which layer produced it. A collision would
make a refusal ambiguous in exactly the place ambiguity is least affordable.

**One outcome per code.** The mapping is total and single-valued, and
``outcome_for`` raises on an unmapped member rather than guessing — a guess would
let a denial read as an allow.

**Every outcome class inhabited.** A declared outcome no code can express is a
state nothing may emit and nothing may audit.
"""

from __future__ import annotations

import pytest
from semantic_catalog.contracts.reason_codes import Outcome
from semantic_catalog.contracts.reason_codes import ReasonCode as CatalogReasonCode

from analytics_query.contracts.reason_codes import (
    REASON_CODE_OUTCOME,
    REQUEST_MALFORMATION_GROUP,
    AnalyticsReasonCode,
    codes_with_outcome,
    outcome_for,
)

pytestmark = pytest.mark.contract


def test_the_namespaces_are_disjoint() -> None:
    """The property ADR 0004 exists to guarantee."""
    ours = {code.value for code in AnalyticsReasonCode}
    theirs = {code.value for code in CatalogReasonCode}
    assert not (ours & theirs), sorted(ours & theirs)


def test_a_colliding_code_would_be_detected() -> None:
    """The disjointness test must be capable of failing.

    Asserted by construction: a code borrowed from upstream is shown to collide,
    so the check above is known to have teeth.
    """
    borrowed = CatalogReasonCode.ACCESS_DENIED.value
    ours = {code.value for code in AnalyticsReasonCode}
    assert borrowed not in ours
    assert {borrowed} & {c.value for c in CatalogReasonCode}


def test_the_namespace_declares_exactly_twenty_five_codes() -> None:
    assert len(AnalyticsReasonCode) == 25


def test_every_code_has_exactly_one_outcome() -> None:
    assert set(REASON_CODE_OUTCOME) == set(AnalyticsReasonCode)
    for code in AnalyticsReasonCode:
        assert isinstance(outcome_for(code), Outcome)


def test_the_outcome_split_matches_the_contract() -> None:
    """23 DENY, 1 ALLOW_WITH_CAVEAT, 1 ALLOW — `contracts/reason-codes.md` §3."""
    assert len(codes_with_outcome(Outcome.DENY)) == 23
    assert codes_with_outcome(Outcome.ALLOW_WITH_CAVEAT) == (
        AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
    )
    assert codes_with_outcome(Outcome.ALLOW) == (AnalyticsReasonCode.QUERY_EXECUTED,)


def test_every_outcome_class_is_inhabited() -> None:
    for outcome in Outcome:
        assert codes_with_outcome(outcome), f"{outcome.value} has no code"


def test_outcome_for_raises_on_an_unmapped_code() -> None:
    """Guessing an outcome would let a denial read as an allow."""
    with pytest.raises(ValueError):
        outcome_for("NOT_A_CODE")  # pyright: ignore[reportArgumentType]


def test_the_request_malformation_group_is_descriptive_only() -> None:
    """Group membership is not a second classification axis.

    Every member is an independent code whose outcome is DENY; no member is an
    alias for another, and the group grants no shared behaviour.
    """
    assert len(REQUEST_MALFORMATION_GROUP) == 11
    for code in REQUEST_MALFORMATION_GROUP:
        assert outcome_for(code) is Outcome.DENY
    assert len({code.value for code in REQUEST_MALFORMATION_GROUP}) == 11


def test_the_only_allow_code_is_the_executed_one() -> None:
    """A permissive answer must be unambiguous about what it permits."""
    allows = codes_with_outcome(Outcome.ALLOW)
    assert allows == (AnalyticsReasonCode.QUERY_EXECUTED,)
