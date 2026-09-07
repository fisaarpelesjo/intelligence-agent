"""T138 — identifiers are derived and scoped, so a crafted one cannot cross a boundary.

`conversation_id` and `correlation_id` are **derived** from the tuple `(tenant, channel,
principal_ref, provider_message_id)` through the pseudonymiser. A caller may present one — the
generic webhook path does — and presenting anything other than what its own scope derives refuses
with `CHANNEL_SCOPE_MISMATCH`.

That design is what these attacks probe. A caller who could present an arbitrary identifier would
read or join another principal's exchange; a caller whose identifier collided with another tenant's
would do the same by accident.

Four attacks:

* **crafted identifier** — a plausible-looking reference the attacker made up;
* **another scope's identifier** — the real reference derived for a different principal;
* **the same provider message id in two tenants** — must derive two different references;
* **the same message id on two channels** — same, because the channel is part of the scope.

The last two are the ones that matter most, and they are asserted as **inequality of derived
values** rather than as a refusal: nothing refuses there, because nothing is wrong — the point is
that the derivation separates them.
"""

from __future__ import annotations

import json

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
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
    FIXTURE_EXTERNAL,
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
    fixture_pseudonymiser,
)

pytestmark = pytest.mark.adversarial

_CHANNEL = ChannelId.GENERIC_WEBHOOK


def _convert(
    payload: dict[str, object],
    channel: ChannelId = _CHANNEL,
) -> ChannelEnvelope | ChannelRefusal:
    raw = signed_request(channel, body=json.dumps(payload).encode())
    return convert(
        raw,
        descriptor=descriptor_for(channel),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(channel),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=channel)),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )


def test_presenting_nothing_uses_the_derived_reference() -> None:
    """The baseline, so every refusal below is a refusal of something specific."""
    outcome = _convert(wire_payload())
    assert isinstance(outcome, ChannelEnvelope)
    expected = derive_conversation_ref(
        fixture_pseudonymiser(),
        FIXTURE_TENANT,
        _CHANNEL,
        FIXTURE_PRINCIPAL,
        str(wire_payload()["message_id"]),
    )
    assert outcome.conversation_id == expected


@pytest.mark.parametrize(
    "crafted",
    [
        "conv-1",
        "00000000-0000-0000-0000-000000000000",
        "tenant-b:principal-2:m1",
        "../../etc/passwd",
        "' OR 1=1 --",
    ],
)
def test_a_crafted_conversation_reference_is_refused(crafted: str) -> None:
    """Anything other than what this scope derives is out of scope, whatever it looks like.

    The shapes are deliberately varied — a short handle, a UUID, a scope-looking triple, a traversal
    string, an injection string — because a check that compared *format* rather than *value* would
    accept the UUID and reject the rest.
    """
    outcome = _convert(wire_payload(conversation_id=crafted))
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code in {
        ChannelReasonCode.CHANNEL_SCOPE_MISMATCH,
        ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN,
        ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
    }


def test_another_scopes_real_correlation_id_is_refused() -> None:
    """The strongest version of the attack: a genuine identifier, from the wrong scope.

    Derived for a different provider message id, so it is a value the system itself would produce —
    just not for this exchange. A check that validated shape or provenance rather than the scoped
    value would pass this.
    """
    other = derive_correlation_id(
        fixture_pseudonymiser(),
        FIXTURE_TENANT,
        _CHANNEL,
        FIXTURE_PRINCIPAL,
        "provider-message-999",
    )
    outcome = _convert(wire_payload(correlation_id=str(other)))
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH


def test_the_same_provider_message_id_derives_different_references_in_two_tenants() -> None:
    """No refusal here, and that is the point: the derivation separates them.

    The same provider message id in two tenants is two exchanges. If the derivation ignored the
    tenant, duplicate suppression in one tenant would suppress the other's message, and a
    correlation id would join two organisations' records.
    """
    pseudonymiser = fixture_pseudonymiser()
    left = derive_conversation_ref(
        pseudonymiser, FIXTURE_TENANT, _CHANNEL, FIXTURE_PRINCIPAL, "provider-message-1"
    )
    from channel_integration.contracts._base import TenantId  # local: only this test needs the type

    right = derive_conversation_ref(
        pseudonymiser, TenantId("tenant-b"), _CHANNEL, FIXTURE_PRINCIPAL, "provider-message-1"
    )
    assert left != right, (
        "the tenant is not part of the derivation, so two tenants share a reference"
    )


def test_the_same_provider_message_id_derives_different_references_on_two_channels() -> None:
    """The channel is part of the scope for the same reason the tenant is.

    Providers assign message ids independently, so a collision across channels is not hypothetical —
    it is expected, and it must not become a shared conversation.
    """
    pseudonymiser = fixture_pseudonymiser()
    references = {
        channel: derive_conversation_ref(
            pseudonymiser, FIXTURE_TENANT, channel, FIXTURE_PRINCIPAL, "provider-message-1"
        )
        for channel in ChannelId
    }
    assert len(set(references.values())) == len(references), (
        f"two channels derive the same reference: {references}"
    )


def test_the_same_provider_message_id_derives_different_references_for_two_principals() -> None:
    """And the principal, which is the boundary a user would try to cross."""
    from channel_integration.contracts._base import PrincipalRef

    pseudonymiser = fixture_pseudonymiser()
    mine = derive_conversation_ref(
        pseudonymiser, FIXTURE_TENANT, _CHANNEL, FIXTURE_PRINCIPAL, "provider-message-1"
    )
    theirs = derive_conversation_ref(
        pseudonymiser,
        FIXTURE_TENANT,
        _CHANNEL,
        PrincipalRef("principal-someone-else"),
        "provider-message-1",
    )
    assert mine != theirs


def test_a_derived_reference_carries_no_provider_identifier() -> None:
    """The reference is pseudonymous, so it may not contain what it was derived from.

    A reference that embedded the provider message id or the principal would leak both to anywhere
    the reference travels — an audit record, a log line, a correlation header.
    """
    reference = str(
        derive_conversation_ref(
            fixture_pseudonymiser(),
            FIXTURE_TENANT,
            _CHANNEL,
            FIXTURE_PRINCIPAL,
            "provider-message-1",
        )
    )
    for secret in ("provider-message-1", str(FIXTURE_PRINCIPAL)):
        assert secret not in reference, f"the derived reference embeds {secret!r}"
