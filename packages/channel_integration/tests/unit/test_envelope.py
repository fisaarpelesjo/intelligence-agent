"""Wire shape and envelope assembly — T061 (FR-003 to FR-008; SC-006 to SC-008).

Every required field required, the two dates independent, an undeclared key refused because it
does not exist, and no field through which authority could arrive.
"""

from __future__ import annotations

from datetime import date

import pytest

from channel_integration.contracts._base import (
    ChannelViolation,
    ConversationRef,
    CorrelationId,
)
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.inbound.envelope import (
    WIRE_FIELDS,
    WIRE_OPTIONAL_FIELDS,
    assemble_envelope,
    wire_field,
)

from ..fixtures.channels import wire_payload
from ..fixtures.identity import FIXTURE_PRINCIPAL, FIXTURE_TENANT

pytestmark = pytest.mark.unit

_CONVERSATION = ConversationRef("fixture-conversation-ref")
_CORRELATION = CorrelationId("fixture-correlation-id")


def _assemble(payload: dict[str, object]):
    return assemble_envelope(
        payload,
        channel=ChannelId.SLACK,
        tenant=FIXTURE_TENANT,
        principal_ref=FIXTURE_PRINCIPAL,
        conversation_id=_CONVERSATION,
        correlation_id=_CORRELATION,
        text=str(payload["text"]),
    )


def test_a_declared_payload_assembles() -> None:
    envelope = _assemble(wire_payload())
    assert envelope.tenant == FIXTURE_TENANT
    assert envelope.principal_ref == FIXTURE_PRINCIPAL
    assert envelope.language == "pt-BR"
    assert envelope.reference_date == date(2026, 8, 17)
    assert envelope.as_of is None


#: The fields `assemble_envelope` itself reads from the payload. `tenant` and `text` are read
#: earlier, by `convert`, through `wire_field` — they reach assembly already resolved, so their
#: absence refuses one step before this function. Both paths are asserted, separately, because
#: conflating them would let one of the two stop being checked.
_ASSEMBLED_FROM_PAYLOAD = ("language", "reference_date", "message_id")


@pytest.mark.parametrize("field", _ASSEMBLED_FROM_PAYLOAD)
def test_every_field_assembly_reads_is_required(field: str) -> None:
    payload = wire_payload()
    del payload[field]
    with pytest.raises(ChannelViolation) as caught:
        _assemble(payload)
    assert caught.value.code is ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE


@pytest.mark.parametrize("field", ["tenant", "text"])
def test_the_fields_read_before_assembly_are_required_too(field: str) -> None:
    """`wire_field` is the accessor `convert` uses, and it refuses the same way."""
    payload = wire_payload()
    del payload[field]
    with pytest.raises(ChannelViolation) as caught:
        wire_field(payload, field)
    assert caught.value.code is ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE


def test_the_required_wire_fields_are_covered_between_the_two_paths() -> None:
    """No required field escapes both checks."""
    required = WIRE_FIELDS - WIRE_OPTIONAL_FIELDS
    assert required == set(_ASSEMBLED_FROM_PAYLOAD) | {"tenant", "text"}


@pytest.mark.parametrize(
    "undeclared",
    ["access_tags", "verified", "principal", "max_rows", "detected_language", "fixture", "caption"],
)
def test_an_undeclared_wire_field_refuses(undeclared: str) -> None:
    """Refused because the shape does not declare it, not because a rule named it."""
    payload = wire_payload(**{undeclared: "anything"})
    with pytest.raises(ChannelViolation) as caught:
        _assemble(payload)
    assert caught.value.code is ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN


def test_the_as_of_pin_is_optional_and_never_filled_from_the_reference_date() -> None:
    without = _assemble(wire_payload())
    assert without.as_of is None

    with_pin = _assemble(wire_payload(as_of="2026-07-01"))
    assert with_pin.as_of == date(2026, 7, 1)
    assert with_pin.reference_date == date(2026, 8, 17), "the pin does not move the reference date"


def test_a_malformed_date_refuses_rather_than_being_coerced() -> None:
    with pytest.raises(ChannelViolation) as caught:
        _assemble(wire_payload(reference_date="17/08/2026"))
    assert caught.value.code is ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE


def test_the_wire_shape_carries_no_principal_and_no_authority() -> None:
    """The principal is resolved, never declared; nothing on the wire grants anything."""
    assert "principal_ref" not in WIRE_FIELDS
    for forbidden in ("access_tags", "role", "scope", "verified", "policy_version", "freshness"):
        assert forbidden not in WIRE_FIELDS


def test_only_three_fields_may_be_omitted() -> None:
    assert {"as_of", "conversation_id", "correlation_id"} == WIRE_OPTIONAL_FIELDS
