"""No raw external identifier survives — T066 (`D-31`; FR-077; SC-037).

A phone number, a member id, a chat id, a handle, a display name and an email address are the six
things a channel integration handles constantly and must never store. Every record this feature
produces carries a **keyed, stable, non-reversible reference** instead.

Three properties, and the third is the one usually got wrong:

* **stable** — the same identity yields the same reference, so a journey across the six audit stages
  is joinable. A per-process salt would break this and is rejected in `identity.pseudonymise` for
  exactly that reason;
* **non-reversible** — keyed, so it cannot be brute-forced over the phone-number space. An unkeyed
  hash of a phone number is a directory with extra steps, and is rejected for the same reason;
* **domain-separated** — an audit actor reference and a conversation reference derived from the same
  identity are **different** references. Without separation, an operator holding one record could
  join it against another surface that was never meant to be linkable.

The scan below is over the **serialised** record rather than the object, because that is what
reaches a sink: a raw identifier hiding in an allowed string field would satisfy every field-set
assertion and still be in the file.

While `D-31` is undeclared the production port derives nothing and refuses, which `T068` asserts.
Here the fixture key is used, so the *shape* of a compliant reference is provable before the
material exists.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from channel_integration.audit.emit import AUDIT_ACTOR_LABEL, build_event
from channel_integration.contracts._base import MessageKey
from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.identity import ExternalIdentity
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.identity.scope import (
    CONVERSATION_LABEL,
    CORRELATION_LABEL,
    derive_conversation_ref,
    derive_correlation_id,
)
from channel_integration.inbound.convert import convert

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    bounds_for,
    descriptor_for,
    signed_request,
    wire_payload,
)
from ..fixtures.identity import (
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
    fixture_pseudonymiser,
)

pytestmark = pytest.mark.security

#: Synthetic identifiers shaped like the six real kinds. Obviously fake, so this file is not itself
#: a place personal data lives — the thing the rule exists to prevent.
_RAW_IDENTIFIERS = {
    "phone number": "+5511999990000",
    "member id": "U01FIXTUREMEMBER",
    "chat id": "-1001234567890",
    "handle": "@fixture.handle",
    "display name": "Fixture Da Silva",
    "email address": "fixture.person@example.invalid",
}


def _event_json(external: ExternalIdentity) -> str:
    pseudonymiser = fixture_pseudonymiser()
    event = build_event(
        stage=ChannelStage.IDENTIFIED,
        channel=ChannelId.SLACK,
        tenant=FIXTURE_TENANT,
        principal_ref=FIXTURE_PRINCIPAL,
        correlation_id=derive_correlation_id(
            pseudonymiser, FIXTURE_TENANT, ChannelId.SLACK, FIXTURE_PRINCIPAL, "provider-message-1"
        ),
        message_key=MessageKey("fixture-message-key-1"),
        code=ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED,
        pseudonymiser=pseudonymiser,
        external=external,
    )
    return event.model_dump_json()


@pytest.mark.parametrize("kind", sorted(_RAW_IDENTIFIERS))
def test_no_raw_identifier_appears_in_a_serialised_audit_event(kind: str) -> None:
    """`SC-037`, over the serialised record — the shape that actually reaches a sink."""
    raw = _RAW_IDENTIFIERS[kind]
    serialised = _event_json(ExternalIdentity(raw))
    assert raw not in serialised, f"the {kind} survived into the record"
    # Also absent in the forms an encoder might produce.
    assert raw.replace("+", "") not in serialised
    assert raw.lower() not in serialised.lower()


def test_the_reference_is_present_and_is_a_reference() -> None:
    """Without this, "no raw identifier" would be satisfied by recording nothing at all."""
    document = json.loads(_event_json(ExternalIdentity(_RAW_IDENTIFIERS["phone number"])))
    reference = document["external_identity_ref"]
    assert reference is not None
    assert len(reference["value"]) == 64, "a SHA-256 hex reference is expected"
    assert reference["key_version"] == "fixture-key-1", "a rotation must be legible in the record"


def test_the_reference_is_stable_across_derivations() -> None:
    """`FR-084` depends on it: an unstable reference makes a journey unjoinable."""
    external = ExternalIdentity(_RAW_IDENTIFIERS["member id"])
    first = json.loads(_event_json(external))["external_identity_ref"]["value"]
    second = json.loads(_event_json(external))["external_identity_ref"]["value"]
    assert first == second


def test_two_identities_do_not_collide() -> None:
    values = {
        json.loads(_event_json(ExternalIdentity(raw)))["external_identity_ref"]["value"]
        for raw in _RAW_IDENTIFIERS.values()
    }
    assert len(values) == len(_RAW_IDENTIFIERS)


def test_the_three_domains_are_separated() -> None:
    """An audit actor, a conversation and a correlation from one identity are three references."""
    pseudonymiser = fixture_pseudonymiser()
    identity = _RAW_IDENTIFIERS["chat id"]
    actor = pseudonymiser.derive(AUDIT_ACTOR_LABEL, identity)
    conversation = pseudonymiser.derive(CONVERSATION_LABEL, identity)
    correlation = pseudonymiser.derive(CORRELATION_LABEL, identity)
    assert len({actor, conversation, correlation}) == 3
    assert {AUDIT_ACTOR_LABEL, CONVERSATION_LABEL, CORRELATION_LABEL} == {
        "audit-actor",
        "conversation",
        "correlation",
    }


def test_a_derivation_is_unambiguous_across_part_boundaries() -> None:
    """``("a|b", "c")`` and ``("a", "b|c")`` must not merge two identities into one reference."""
    pseudonymiser = fixture_pseudonymiser()
    assert pseudonymiser.derive("label", "a|b", "c") != pseudonymiser.derive("label", "a", "b|c")


def test_an_unkeyed_hash_of_the_identity_is_not_what_gets_recorded() -> None:
    """The rejected substitute, asserted as rejected rather than described as rejected."""
    raw = _RAW_IDENTIFIERS["phone number"]
    serialised = _event_json(ExternalIdentity(raw))
    for digest in (
        hashlib.sha256(raw.encode()).hexdigest(),
        hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest(),
        hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest(),
    ):
        assert digest not in serialised, (
            "an unkeyed digest is brute-forceable over the number space"
        )


def _convert_fixture(provider_message_id: str) -> ChannelEnvelope:
    """Drive one successful conversion under a raw member id, returning the envelope."""
    outcome = convert(
        signed_request(ChannelId.SLACK, payload=wire_payload(message_id=provider_message_id)),
        descriptor=descriptor_for(ChannelId.SLACK),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(ChannelId.SLACK),
        kind=MessageKind.TEXT,
        external=ExternalIdentity(_RAW_IDENTIFIERS["member id"]),
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)
    return outcome


def test_the_envelope_carries_no_external_identity_at_all() -> None:
    """The strongest form available: the identity is not on the envelope in any form.

    A member id is one of the six identifiers `FR-077` names, and the envelope has no field for it
    — pseudonymous or otherwise. What travels is the resolved `principal_ref`.
    """
    envelope = _convert_fixture("provider-message-1")
    dumped = envelope.model_dump_json()
    assert _RAW_IDENTIFIERS["member id"] not in dumped
    assert "external" not in set(ChannelEnvelope.model_fields)
    assert str(envelope.principal_ref) == str(FIXTURE_PRINCIPAL)


def test_the_scope_references_are_derived_not_the_providers_own() -> None:
    """The provider's conversation reference never travels raw; the derived one does.

    Stated precisely, because `message_id` **is** the provider's id and is meant to be: it is the
    idempotency key (`FR-065`) and it identifies a message, not a person. The identifiers `FR-077`
    governs are the ones that identify a *person*, and the conversation and correlation references
    are derived so that a chat id is not carried as one.
    """
    provider_message_id = "provider-message-1"
    envelope = _convert_fixture(provider_message_id)
    assert str(envelope.message_id) == provider_message_id, (
        "the idempotency key is the provider's message id, deliberately"
    )

    pseudonymiser = fixture_pseudonymiser()
    assert str(envelope.conversation_id) == str(
        derive_conversation_ref(
            pseudonymiser, FIXTURE_TENANT, ChannelId.SLACK, FIXTURE_PRINCIPAL, provider_message_id
        )
    )
    assert str(envelope.correlation_id) == str(
        derive_correlation_id(
            pseudonymiser, FIXTURE_TENANT, ChannelId.SLACK, FIXTURE_PRINCIPAL, provider_message_id
        )
    )
    assert len(str(envelope.conversation_id)) == 64
    assert str(envelope.conversation_id) != str(envelope.correlation_id)
