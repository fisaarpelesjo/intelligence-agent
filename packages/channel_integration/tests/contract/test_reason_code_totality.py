"""The 31 codes, their outcome map and its totality — T015 (ADR 0018; SC-060).

Three separate claims, deliberately not folded into one:

* the enum has **exactly** the 31 accepted members, by group count;
* the outcome map is **total and single-valued** — every code mapped once;
* **every outcome class is inhabited**, mirroring `001`'s rule that a declared outcome
  no code can express is a state nothing may emit or audit.

A 32nd code fails this test rather than passing silently, which is what makes ADR
0018's "a 32nd requires a new decision" enforceable instead of aspirational.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts.delivery import DeliveryOutcome, outcome_reason_code
from channel_integration.contracts.reason_codes import (
    CHANNEL_REASON_CODE_OUTCOME,
    ChannelReasonCode,
    Outcome,
    channel_codes_with_outcome,
    channel_outcome_for,
)

pytestmark = pytest.mark.contract


def test_the_namespace_has_exactly_thirty_one_codes() -> None:
    assert len(ChannelReasonCode) == 31


def test_the_group_counts_match_the_contract() -> None:
    """5 authenticity + 5 envelope + 3 identity + 8 configuration + 5 flow + 2 rendering
    + 3 permitted = 31, exactly as `contracts/reason-codes.md` §2 enumerates.

    Counted by prefix and by membership rather than by re-listing, so the assertion
    fails on an addition to any group instead of only on a change to a total.
    """
    values = {code.value for code in ChannelReasonCode}
    authenticity = {
        "CHANNEL_PAYLOAD_MALFORMED",
        "CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT",
        "CHANNEL_SIGNATURE_INVALID",
        "CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE",
        "CHANNEL_VERIFICATION_UNAVAILABLE",
    }
    envelope = {
        "CHANNEL_ENVELOPE_INCOMPLETE",
        "CHANNEL_ENVELOPE_FIELD_UNKNOWN",
        "CHANNEL_MESSAGE_KIND_UNSUPPORTED",
        "CHANNEL_TEXT_NOT_USABLE",
        "CHANNEL_NORMALISATION_AMBIGUOUS",
    }
    identity = {
        "CHANNEL_IDENTITY_UNMAPPED",
        "CHANNEL_TENANT_MISMATCH",
        "CHANNEL_SCOPE_MISMATCH",
    }
    configuration = {
        "CHANNEL_NOT_CONFIGURED",
        "CHANNEL_CREDENTIAL_UNAVAILABLE",
        "CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE",
        "CHANNEL_IDENTITY_POLICY_UNRESOLVABLE",
        "CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE",
        "CHANNEL_METADATA_POLICY_UNRESOLVABLE",
        "CHANNEL_AUDIT_UNAVAILABLE",
        "INTERACTION_BOUNDARY_UNAVAILABLE",
    }
    flow = {
        "CHANNEL_RATE_LIMIT_EXCEEDED",
        "CHANNEL_DELIVERY_FAILED",
        "CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED",
        "CHANNEL_DELIVERY_INDETERMINATE",
        "CHANNEL_MESSAGE_DUPLICATE",
    }
    rendering = {"CHANNEL_RESPONSE_NOT_REPRESENTABLE", "CHANNEL_OUTBOUND_WITHHELD"}
    permitted = {
        "CHANNEL_MESSAGE_ACCEPTED",
        "CHANNEL_RESPONSE_DELIVERED",
        "CHANNEL_RESPONSE_DELIVERED_WITH_CAVEAT",
    }
    groups = (authenticity, envelope, identity, configuration, flow, rendering, permitted)
    assert [len(group) for group in groups] == [5, 5, 3, 8, 5, 2, 3]
    union: set[str] = set()
    for group in groups:
        assert not (union & group), "a code appears in two groups"
        union |= group
    assert union == values


def test_the_outcome_map_is_total_and_single_valued() -> None:
    assert set(CHANNEL_REASON_CODE_OUTCOME) == set(ChannelReasonCode)
    for code in ChannelReasonCode:
        assert channel_outcome_for(code) is CHANNEL_REASON_CODE_OUTCOME[code]


def test_the_outcome_distribution_is_28_deny_2_allow_1_with_caveat() -> None:
    assert len(channel_codes_with_outcome(Outcome.DENY)) == 28
    assert len(channel_codes_with_outcome(Outcome.ALLOW)) == 2
    assert len(channel_codes_with_outcome(Outcome.ALLOW_WITH_CAVEAT)) == 1


@pytest.mark.parametrize("outcome", list(Outcome))
def test_every_outcome_class_is_inhabited(outcome: Outcome) -> None:
    assert channel_codes_with_outcome(outcome), f"{outcome} has no channel code"


def test_the_duplicate_outcome_denies() -> None:
    """A recognised redelivery is DENY, not a permissive outcome.

    Treating it as ALLOW would let a caller read "duplicate" as "delivered again,
    fine" — which is precisely the reading that hides a double delivery.
    """
    assert channel_outcome_for(ChannelReasonCode.CHANNEL_MESSAGE_DUPLICATE) is Outcome.DENY


def test_every_delivery_outcome_maps_to_a_governed_code() -> None:
    """A delivery state with no code would be a state nothing could audit."""
    for outcome in DeliveryOutcome:
        assert outcome_reason_code(outcome) in ChannelReasonCode
    assert len({outcome_reason_code(o) for o in DeliveryOutcome}) == len(DeliveryOutcome)
