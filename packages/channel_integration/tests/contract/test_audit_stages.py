"""The six audit stages, closed and ordered — T016 (ADR 0019; SC-039, SC-040).

Two claims. The stage enum is **exactly** the six accepted members in the accepted
order — a seventh is a new decision, not an addition (ADR 0019 § Acceptance). And the
event contract carries **no field in which content could travel**, which is the half of
the forbidden-content rule that a field-set test can prove; the serialised scan in
Phase B proves the other half.
"""

from __future__ import annotations

from datetime import date

import pytest

from channel_integration.contracts import (
    CHANNEL_STAGE_ORDER,
    ChannelAuditEvent,
    ChannelId,
    ChannelStage,
    DetailClass,
    Outcome,
)
from channel_integration.contracts._base import (
    CorrelationId,
    MessageKey,
    PrincipalRef,
    TenantId,
)
from channel_integration.contracts.reason_codes import ChannelReasonCode

pytestmark = pytest.mark.contract


def test_there_are_exactly_six_stages_in_the_declared_order() -> None:
    assert len(ChannelStage) == 6
    assert CHANNEL_STAGE_ORDER == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
        ChannelStage.RENDERED,
        ChannelStage.DELIVERED,
    )
    assert tuple(ChannelStage) == CHANNEL_STAGE_ORDER, "declaration order is the sequence order"


def test_the_stage_order_is_a_permutation_of_the_enum() -> None:
    """No stage may be absent from the order, and none may appear twice.

    Stated separately because a tuple that happened to be the right length could still
    omit a stage and repeat another — and the last stage present in a trail is how an
    operator learns where a message stopped.
    """
    assert set(CHANNEL_STAGE_ORDER) == set(ChannelStage)
    assert len(set(CHANNEL_STAGE_ORDER)) == len(CHANNEL_STAGE_ORDER)


def _event(**overrides: object) -> ChannelAuditEvent:
    data: dict[str, object] = {
        "stage": ChannelStage.RECEIVED,
        "channel": ChannelId.SLACK,
        "tenant": TenantId("tenant-a"),
        "principal_ref": PrincipalRef("principal-ref-a"),
        "correlation_id": CorrelationId("corr-1"),
        "message_key": MessageKey("msg-1"),
        "outcome": Outcome.DENY,
        "code": ChannelReasonCode.CHANNEL_SIGNATURE_INVALID.value,
    }
    data.update(overrides)
    return ChannelAuditEvent(**data)  # type: ignore[arg-type]


def test_an_event_carries_the_required_field_set() -> None:
    event = _event()
    assert event.stage is ChannelStage.RECEIVED
    assert event.detail_class is DetailClass.NONE
    assert event.external_identity_ref is None
    assert event.policy_version is None
    assert event.capability_version is None


def test_no_content_field_exists_on_the_event() -> None:
    """The forbidden-content set, as a field-set claim (`FR-082`)."""
    forbidden = {
        "payload",
        "body",
        "text",
        "question",
        "answer",
        "value",
        "filter_value",
        "provenance",
        "caveat",
        "caveats",
        "headers",
        "header",
        "signature",
        "credential",
        "token",
        "url",
        "error",
        "detail",
        "message",
        "external_identity",
    }
    declared = set(ChannelAuditEvent.model_fields)
    assert not declared & forbidden, sorted(declared & forbidden)


def test_an_unknown_field_is_refused_because_it_does_not_exist() -> None:
    with pytest.raises(ValueError, match=r"extra_forbidden|Extra inputs"):
        _event(payload=b"raw bytes")


def test_the_event_is_frozen() -> None:
    event = _event()
    with pytest.raises(ValueError, match=r"frozen|Instance is frozen"):
        event.stage = ChannelStage.DELIVERED  # type: ignore[misc]


def test_detail_class_is_a_closed_enumeration_not_free_text() -> None:
    """Free text is where a phone number or a signature fragment eventually appears."""
    with pytest.raises(ValueError, match=r"DetailClass|valid"):
        _event(detail_class="the X-Hub-Signature header was 'abc123'")


def test_detail_class_covers_all_three_collapsed_sets() -> None:
    """Every collapse in ADR 0018 must be distinguishable to an operator.

    Otherwise the collapse would cost the operator information as well as the sender,
    and "which half of the scheme failed?" would become unanswerable from the trail.
    """
    values = {member.value for member in DetailClass}
    assert any(value.startswith("SIGNATURE_") for value in values)
    assert any(value.startswith("BINDING_") for value in values)
    assert any(value.startswith("ENVELOPE_") for value in values)


def test_a_date_is_not_accepted_where_a_reference_belongs() -> None:
    """Typed fields, so a mistaken argument order fails rather than being coerced."""
    with pytest.raises(ValueError, match=r"valid|string"):
        _event(principal_ref=date(2026, 8, 17))
