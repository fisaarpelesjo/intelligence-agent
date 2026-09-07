"""Isolation under concurrency — T105 (FR-026 to FR-029; SC-013, SC-014).

Two tenants, two channels, two principals, interleaved, with **crossed identifiers**: every response
returns to its own origin, and a reference belonging to one scope is refused when presented by
another.

The interleaving is written out rather than threaded. Real threads would make this a race the test
could pass by luck; an explicit interleaving makes the worst ordering the ordering under test. What
concurrency actually threatens here is **shared state**, and the property that protects against
it is that there is none: every scoped reference is *derived* from the resolved principal, tenant
and channel, so two flows cannot influence each other even when they run at the same instant.

Four crossings are driven:

* a conversation reference from tenant A presented under tenant B;
* the same principal on two channels — the references must differ;
* two principals in one tenant — the references must differ;
* a correlation id from one flow presented in another.

Each must refuse with ``CHANNEL_SCOPE_MISMATCH``, and the refusal must disclose nothing about
whether the referenced conversation exists.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts._base import PrincipalRef, TenantId
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.identity import ExternalIdentity
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.identity.scope import derive_conversation_ref, derive_correlation_id
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
    CountingIdentityResolver,
    active_binding,
    fixture_pseudonymiser,
)

pytestmark = pytest.mark.integration

_TENANT_A = TenantId("tenant-a")
_TENANT_B = TenantId("tenant-b")
_PRINCIPAL_A = PrincipalRef("principal-ref-a")
_PRINCIPAL_B = PrincipalRef("principal-ref-b")
_MESSAGE = "provider-message-1"


def _convert(
    channel: ChannelId,
    tenant: TenantId,
    principal: PrincipalRef,
    *,
    conversation_id: str | None = None,
    correlation_id: str | None = None,
    message_id: str = _MESSAGE,
) -> ChannelEnvelope | ChannelRefusal:
    """One conversion for one scope, with whatever references the caller presents."""
    overrides: dict[str, object] = {"tenant": str(tenant), "message_id": message_id}
    if conversation_id is not None:
        overrides["conversation_id"] = conversation_id
    if correlation_id is not None:
        overrides["correlation_id"] = correlation_id
    payload = wire_payload(**overrides)
    return convert(
        signed_request(channel, payload=payload),
        descriptor=descriptor_for(channel),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(channel),
        kind=MessageKind.TEXT,
        external=ExternalIdentity(f"fixture-external-{principal}"),
        resolver=CountingIdentityResolver(
            active_binding(channel=channel, tenant=tenant, principal_ref=principal)
        ),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
    )


def _expected_conversation(channel: ChannelId, tenant: TenantId, principal: PrincipalRef) -> str:
    return str(
        derive_conversation_ref(fixture_pseudonymiser(), tenant, channel, principal, _MESSAGE)
    )


def test_four_concurrent_flows_each_return_to_their_own_origin() -> None:
    """`SC-013`: two tenants by two channels by two principals, interleaved."""
    flows = [
        (ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A),
        (ChannelId.SLACK, _TENANT_B, _PRINCIPAL_B),
        (ChannelId.WHATSAPP, _TENANT_A, _PRINCIPAL_B),
        (ChannelId.WHATSAPP, _TENANT_B, _PRINCIPAL_A),
    ]
    envelopes: list[ChannelEnvelope] = []
    for channel, tenant, principal in flows:
        outcome = _convert(channel, tenant, principal)
        assert isinstance(outcome, ChannelEnvelope), (channel, tenant, principal)
        envelopes.append(outcome)

    for (channel, tenant, principal), envelope in zip(flows, envelopes, strict=True):
        assert envelope.channel is channel
        assert str(envelope.tenant) == str(tenant)
        assert str(envelope.principal_ref) == str(principal)
        assert str(envelope.conversation_id) == _expected_conversation(channel, tenant, principal)

    references = {str(envelope.conversation_id) for envelope in envelopes}
    assert len(references) == 4, "two distinct scopes produced the same conversation reference"


def test_the_same_principal_on_two_channels_gets_two_references() -> None:
    """`FR-026`: a channel is part of the scope, not a label on it."""
    slack = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A)
    whatsapp = _convert(ChannelId.WHATSAPP, _TENANT_A, _PRINCIPAL_A)
    assert isinstance(slack, ChannelEnvelope) and isinstance(whatsapp, ChannelEnvelope)
    assert str(slack.conversation_id) != str(whatsapp.conversation_id)


def test_two_principals_in_one_tenant_get_two_references() -> None:
    first = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A)
    second = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_B)
    assert isinstance(first, ChannelEnvelope) and isinstance(second, ChannelEnvelope)
    assert str(first.conversation_id) != str(second.conversation_id)


def test_a_conversation_reference_from_another_tenant_refuses() -> None:
    """`SC-014`: the crossing that matters most, because it crosses a tenant boundary."""
    stolen = _expected_conversation(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A)
    outcome = _convert(ChannelId.SLACK, _TENANT_B, _PRINCIPAL_B, conversation_id=stolen)
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH


def test_a_conversation_reference_from_another_channel_refuses() -> None:
    stolen = _expected_conversation(ChannelId.WHATSAPP, _TENANT_A, _PRINCIPAL_A)
    outcome = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A, conversation_id=stolen)
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH


def test_a_conversation_reference_from_another_principal_refuses() -> None:
    stolen = _expected_conversation(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_B)
    outcome = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A, conversation_id=stolen)
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH


def test_a_crossed_correlation_id_refuses() -> None:
    stolen = str(
        derive_correlation_id(
            fixture_pseudonymiser(), _TENANT_B, ChannelId.SLACK, _PRINCIPAL_B, _MESSAGE
        )
    )
    outcome = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A, correlation_id=stolen)
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH


def test_a_scope_refusal_discloses_nothing_about_existence() -> None:
    """A reference that never existed and one belonging to someone else refuse identically.

    Otherwise the difference between the two answers tells a caller which conversations are real.
    """
    stolen = _expected_conversation(ChannelId.SLACK, _TENANT_B, _PRINCIPAL_B)
    invented = "conversation-that-never-existed"
    first = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A, conversation_id=stolen)
    second = _convert(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A, conversation_id=invented)
    assert isinstance(first, ChannelRefusal) and isinstance(second, ChannelRefusal)
    assert first.sender_text() == second.sender_text()
    assert first.code is second.code
    assert len(first.sender_text()) == len(second.sender_text())


def test_a_declared_tenant_that_disagrees_with_the_binding_refuses() -> None:
    """Declaring is not deciding: the wire says which tenant, the binding says whether."""
    payload = wire_payload(tenant=str(_TENANT_B))
    outcome = convert(
        signed_request(ChannelId.SLACK, payload=payload),
        descriptor=descriptor_for(ChannelId.SLACK),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(ChannelId.SLACK),
        kind=MessageKind.TEXT,
        external=ExternalIdentity("fixture-external-a"),
        resolver=CountingIdentityResolver(
            active_binding(channel=ChannelId.SLACK, tenant=_TENANT_A, principal_ref=_PRINCIPAL_A)
        ),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_TENANT_MISMATCH


def test_no_shared_mutable_state_couples_two_flows() -> None:
    """What concurrency actually threatens, asserted as an absence.

    The conversion modules hold no module-level mutable container, so two flows at the same instant
    have nothing to contend over — which is why an explicit interleaving is a sufficient instrument.
    """
    from channel_integration.identity import resolve, scope
    from channel_integration.inbound import convert as convert_module

    for module in (convert_module, scope, resolve):
        members: dict[str, object] = dict(vars(module))
        state: dict[str, object] = {
            name: value
            for name, value in members.items()
            if not name.startswith("__") and isinstance(value, dict | list | set)
        }
        mutable = {
            name
            for name, value in state.items()
            if isinstance(value, list | set) or not name.isupper()
        }
        assert not mutable, f"{module.__name__} holds mutable module state: {sorted(mutable)}"
