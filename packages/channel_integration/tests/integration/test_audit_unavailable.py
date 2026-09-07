"""`D-31` fail-closed — T068 (`R-13`; FR-077, FR-083; SC-038).

The shipped state of this feature is: **no pseudonymisation key material exists**. `D-31` is
undeclared, nothing in this repository provides a key, and none is invented, generated, derived or
defaulted.

The consequence must be a governed refusal, not a degraded record. Three degradations were available
and all three are rejected, so the test asserts the rejection rather than the description:

* record the **raw** identity — that is the directory `FR-077` exists to prevent;
* record an **unkeyed hash** — brute-forceable over the phone-number space, so a directory with
  extra steps;
* record **nothing** in the reference field — a trail that cannot be joined across the six stages,
  which defeats `FR-084`.

So while `D-31` is undeclared: no reference is constructible, therefore no compliant audit event
exists, therefore the flow refuses with ``CHANNEL_AUDIT_UNAVAILABLE`` **before delivery**. Delivery
does not exist yet, which is why "before delivery" is asserted here as "before an envelope is
produced at all" — the earliest point that is provable in Phase B, and strictly stronger.

The readiness record is asserted too. If `d_31` were ever flipped to declared without material
actually existing, every assertion above would still pass while the property was gone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from channel_integration.audit.emit import build_event
from channel_integration.contracts._base import ChannelViolation, MessageKey
from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.identity.pseudonymise import (
    KeyedPseudonymiser,
    unavailable_pseudonymiser,
)
from channel_integration.identity.scope import derive_conversation_ref, derive_correlation_id
from channel_integration.inbound.convert import convert

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    bounds_for,
    descriptor_for,
    signed_request,
)
from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    active_binding,
)

pytestmark = pytest.mark.integration

_CHANNELS = list(ChannelId)

#: The governed record that makes every assertion in this file meaningful.
_READINESS_RECORD = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "readiness"
    / "multichannel-external-readiness.yaml"
)


@pytest.mark.parametrize("channel", _CHANNELS)
def test_every_channel_refuses_when_no_key_material_is_declared(channel: ChannelId) -> None:
    """`SC-038`, per channel: the production port refuses and the flow yields no envelope."""
    outcome = convert(
        signed_request(channel),
        descriptor=descriptor_for(channel),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(channel),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=channel)),
        pseudonymiser=unavailable_pseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal), "an envelope must not be produced"
    assert outcome.code is ChannelReasonCode.CHANNEL_AUDIT_UNAVAILABLE
    assert outcome.stage is ChannelStage.IDENTIFIED, (
        "the refusal must be recorded where it happened, before submission"
    )


def test_the_refusal_arrives_before_any_envelope_exists() -> None:
    """Stronger than "before delivery", and provable now: nothing downstream is constructed."""
    outcome = convert(
        signed_request(ChannelId.SLACK),
        descriptor=descriptor_for(ChannelId.SLACK),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(ChannelId.SLACK),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=unavailable_pseudonymiser(),
        at=AT,
    )
    assert not isinstance(outcome, ChannelEnvelope)


def test_no_audit_event_is_constructible_without_material() -> None:
    """The record itself refuses, so no code path can emit a non-compliant event."""
    with pytest.raises(ChannelViolation) as caught:
        build_event(
            stage=ChannelStage.IDENTIFIED,
            channel=ChannelId.SLACK,
            tenant=FIXTURE_TENANT,
            principal_ref=FIXTURE_PRINCIPAL,
            correlation_id="fixture-correlation-1",  # type: ignore[arg-type]
            message_key=MessageKey("fixture-message-key-1"),
            code=ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED,
            pseudonymiser=unavailable_pseudonymiser(),
            external=FIXTURE_EXTERNAL,
        )
    assert caught.value.code is ChannelReasonCode.CHANNEL_AUDIT_UNAVAILABLE


def test_no_scoped_reference_is_constructible_without_material() -> None:
    """Scope derivation uses the same port, so the hole is not beside the rule."""
    port = unavailable_pseudonymiser()
    for derive in (derive_conversation_ref, derive_correlation_id):
        with pytest.raises(ChannelViolation) as caught:
            derive(port, FIXTURE_TENANT, ChannelId.SLACK, FIXTURE_PRINCIPAL, "provider-message-1")
        assert caught.value.code is ChannelReasonCode.CHANNEL_AUDIT_UNAVAILABLE


def test_the_unavailable_port_declares_its_state_rather_than_a_version() -> None:
    """ "undeclared" is the honest key version. A fabricated one would look like a rotation."""
    assert unavailable_pseudonymiser().key_version == "undeclared"


def test_a_fresh_port_is_returned_each_time_so_nothing_can_be_mutated_into_answering() -> None:
    assert unavailable_pseudonymiser() is not unavailable_pseudonymiser()


def test_weak_material_is_refused_rather_than_stretched() -> None:
    """A short key is refused at construction, not padded, hashed or accepted with a warning."""
    with pytest.raises(ValueError, match="at least 32 bytes"):
        KeyedPseudonymiser(b"too-short", "some-version")
    with pytest.raises(ValueError, match="version"):
        KeyedPseudonymiser(b"x" * 32, "   ")


def test_the_readiness_record_still_declares_d_31_unavailable() -> None:
    """The assertion that keeps every other assertion here meaningful."""
    text = _READINESS_RECORD.read_text(encoding="utf-8")
    assert "d_31" in text
    section = text.split("d_31", 1)[1]
    assert "declared: false" in section
    assert "evidence_ref: null" in section
