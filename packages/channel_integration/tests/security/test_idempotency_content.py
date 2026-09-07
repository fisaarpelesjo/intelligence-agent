"""The idempotency record carries no content — T099 (ADR 0021; FR-066; SC-030).

A record exists to recognise a redelivery. It does **not** exist to remember what was asked or what
was answered, and the difference is enforced twice:

* **by field set** — there is no field for question text, answer content, a value, a filter value,
  provenance, a caveat or personal data. Not an optional one, not a debug one;
* **by serialised scan** — a marked corpus is driven through a real record and the serialised
  form is
  searched for every sentinel. This is what catches a value smuggled into an allowed string field,
  which no field-set assertion can see.

The second is the load-bearing one. `extra="forbid"` stops a caller adding a field; only looking at
the bytes stops someone putting a question into ``policy_version``.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts._base import MessageKey, PrincipalRef, TenantId
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.idempotency.record import ChannelIdempotencyRecord
from channel_integration.idempotency.window import IdempotencyWindow

from ..fixtures.channels import AT, bounds_for

pytestmark = pytest.mark.security

#: One sentinel per forbidden category, distinctive so a failure names the category.
_SENTINELS = {
    "the question text": "LEAKMARK-QUESTION quantas instalacoes em julho",
    "an answer value": "LEAKMARK-VALUE-1234567.89",
    "personal data": "LEAKMARK-IDENTITY-+5511999990000",
}

_FORBIDDEN_FIELDS = (
    "question",
    "text",
    "answer",
    "body",
    "value",
    "filter_value",
    "provenance",
    "caveat",
    "payload",
    "email",
    "phone",
    "handle",
    "display_name",
    "message",
)


def _envelope_carrying(sentinel: str):
    """One envelope produced by the real conversion, carrying ``sentinel`` as the question text."""
    from channel_integration.contracts.envelope import ChannelEnvelope
    from channel_integration.contracts.identity import ExternalIdentity
    from channel_integration.contracts.kinds import MessageKind
    from channel_integration.inbound.convert import convert

    from ..fixtures.channels import FIXTURE_MATERIAL, descriptor_for, signed_request, wire_payload
    from ..fixtures.identity import (
        CountingIdentityResolver,
        active_binding,
        fixture_pseudonymiser,
    )

    payload = wire_payload(text=f"quantas instalacoes {sentinel} em julho?")
    outcome = convert(
        signed_request(ChannelId.SLACK, payload=payload),
        descriptor=descriptor_for(ChannelId.SLACK),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(ChannelId.SLACK),
        kind=MessageKind.TEXT,
        external=ExternalIdentity(f"LEAKMARK-IDENTITY-{sentinel}"),
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)
    return outcome


def test_the_record_declares_no_content_field() -> None:
    """By field set. A spare string field would eventually hold a question."""
    declared = set(ChannelIdempotencyRecord.model_fields)
    for forbidden in _FORBIDDEN_FIELDS:
        assert forbidden not in declared, f"the record declares {forbidden}"
    assert declared == {
        "key",
        "tenant",
        "principal_ref",
        "outcome_class",
        "first_seen_at",
        "expires_at",
        "policy_version",
    }


def test_a_content_field_cannot_be_added_by_a_caller() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChannelIdempotencyRecord.model_validate(
            {
                "key": {"channel": ChannelId.SLACK, "message_id": "provider-message-1"},
                "tenant": "tenant-a",
                "principal_ref": "principal-ref-a",
                "outcome_class": DeliveryOutcome.DELIVERED,
                "first_seen_at": AT,
                "expires_at": AT,
                "policy_version": "fixture-policy-1",
                "question": "quantas instalacoes?",
            }
        )


@pytest.mark.parametrize("category", sorted(_SENTINELS))
def test_no_marked_value_from_the_flow_survives_into_a_serialised_record(category: str) -> None:
    """By serialised scan, driving the **real flow** rather than stuffing the record directly.

    An earlier version passed each sentinel as the ``message_id`` and then failed — correctly,
    because the message key **is** the provider's id and is meant to appear. That version was
    testing its own input, not the boundary.

    So the sentinel now enters where content genuinely could: as the sender's question text and
    their external identity, through the actual conversion. The record is built from the
    resulting envelope, and none of it may reach the record.
    """
    sentinel = _SENTINELS[category]
    envelope = _envelope_carrying(sentinel)
    window = IdempotencyWindow()
    record = window.remember(
        ChannelId.SLACK,
        envelope.message_id,
        envelope.tenant,
        envelope.principal_ref,
        DeliveryOutcome.DELIVERED,
        bounds_for(ChannelId.SLACK),
        AT,
    )
    serialised = record.model_dump_json()
    assert sentinel not in serialised, f"leaked {category}"
    for marker in ("LEAKMARK-QUESTION", "LEAKMARK-VALUE", "LEAKMARK-IDENTITY"):
        assert marker not in serialised, f"leaked {category} via {marker}"


def test_the_message_key_is_the_providers_id_and_that_is_deliberate() -> None:
    """Stated because it looks like an exception and is not.

    The key **is** the provider's message id: it identifies a message, not a person, and `FR-065`
    requires it as the idempotency key. What `FR-066` forbids is content and personal data, and a
    provider message id is neither.
    """
    window = IdempotencyWindow()
    record = window.remember(
        ChannelId.SLACK,
        MessageKey("provider-message-1"),
        TenantId("tenant-a"),
        PrincipalRef("principal-ref-a"),
        DeliveryOutcome.DELIVERED,
        bounds_for(ChannelId.SLACK),
        AT,
    )
    assert str(record.key.message_id) == "provider-message-1"
    assert "principal-ref-a" in record.model_dump_json()


def test_the_outcome_is_a_class_and_not_a_response() -> None:
    """Knowing the first delivery was withheld is necessary; carrying the withheld answer is not."""
    window = IdempotencyWindow()
    record = window.remember(
        ChannelId.SLACK,
        MessageKey("provider-message-2"),
        TenantId("tenant-a"),
        PrincipalRef("principal-ref-a"),
        DeliveryOutcome.WITHHELD,
        bounds_for(ChannelId.SLACK),
        AT,
    )
    assert record.outcome_class is DeliveryOutcome.WITHHELD
    assert len(record.model_dump_json()) < 400, "the record grew large enough to hold content"
