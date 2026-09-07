"""Fixture channel descriptors, material and signed requests — T050 (FR-072; SC-034).

**TEST-ONLY, and never evidence for any external record.** These descriptors are enabled and
this material verifies, which is exactly what production does not have: `D-22` to `D-25` are
undeclared, so the real path resolves no material and refuses. A fixture proves contract
behaviour and says nothing about availability or readiness.

Reachable from `tests/` only. No `src` module references this file, and no flag, environment
variable or deployment mode selects it (`FR-072`, asserted by `T070`).

The signing helpers construct requests the way each provider would: WhatsApp over the raw body,
Slack over `v0:<ts>:<body>`, Telegram with a shared token, the generic client over
`<ts>.<body>`. They sign with the **fixture** material, so a test can produce a genuinely valid
signature without any real secret existing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from channel_integration.audit.emit import AuditEmissionFailed
from channel_integration.contracts._base import ChannelViolation
from channel_integration.contracts.audit import ChannelAuditEvent, ChannelStage
from channel_integration.contracts.delivery import ChannelDestination, DeliveryOutcome
from channel_integration.contracts.descriptor import (
    ChannelDescriptor,
    ChannelId,
    CredentialRecord,
)
from channel_integration.contracts.presentation import RenderedPresentation
from channel_integration.contracts.raw import RawChannelRequest
from channel_integration.delivery.ports import DeliveryPort, FragmentReceipt
from channel_integration.governance.bounds import TransportBounds
from channel_integration.governance.capabilities import resolve_capability_matrix
from channel_integration.governance.resolve import ContentUnresolvable
from channel_integration.inbound.schemes import VerificationMaterial
from channel_integration.inbound.schemes._hmac import hexdigest
from channel_integration.inbound.schemes.generic import GenericWebhookScheme
from channel_integration.inbound.schemes.slack import SlackScheme
from channel_integration.inbound.schemes.telegram import TelegramScheme
from channel_integration.inbound.schemes.whatsapp import WhatsAppScheme
from channel_integration.secrets.ref import SecretRef
from channel_integration.secrets.resolver import SecretResolver

from .payloads import FIXTURE_CAPABILITY

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "AT",
    "FIXTURE_BOUNDS",
    "FIXTURE_CAPABILITY",
    "FIXTURE_MATERIAL",
    "FIXTURE_SECRET",
    "FixtureSecretResolver",
    "RecordingAuditSink",
    "RecordingDeliveryPort",
    "assert_the_production_resolver_still_refuses",
    "bounds_for",
    "descriptor_for",
    "fixture_capabilities",
    "secret_ref_for",
    "signed_request",
    "wire_payload",
]

#: The evaluation instant every fixture request is signed against. Fixed, because the instant is
#: a parameter and a fixed one is what makes these tests reproducible (`R-5`).
AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

#: Obviously fake, and shaped so no scanner mistakes it for a real credential.
FIXTURE_SECRET = "fixture-secret-not-a-credential"

FIXTURE_MATERIAL = VerificationMaterial(active=FIXTURE_SECRET, retired=("fixture-retired-key",))

_SCHEME_NAMES = {
    ChannelId.WHATSAPP: WhatsAppScheme.name,
    ChannelId.SLACK: SlackScheme.name,
    ChannelId.TELEGRAM: TelegramScheme.name,
    ChannelId.GENERIC_WEBHOOK: GenericWebhookScheme.name,
}

_CREDENTIAL_RECORDS = {
    ChannelId.WHATSAPP: CredentialRecord.D_22_WHATSAPP,
    ChannelId.SLACK: CredentialRecord.D_23_SLACK,
    ChannelId.TELEGRAM: CredentialRecord.D_24_TELEGRAM,
    ChannelId.GENERIC_WEBHOOK: CredentialRecord.D_25_GENERIC,
}


def descriptor_for(channel: ChannelId, enabled: bool = True) -> ChannelDescriptor:
    """A descriptor naming the scheme its channel expects.

    ``enabled`` is settable **here** because this is a fixture. In production the flag is derived
    from the readiness record and no configuration can set it (`FR-097`).
    """
    return ChannelDescriptor(
        channel=channel,
        verification_scheme=_SCHEME_NAMES[channel],
        transport_policy_ref="fixture-policy-1",
        capability_ref="fixture-capability-1",
        credential_record=_CREDENTIAL_RECORDS[channel],
        enabled=enabled,
    )


def secret_ref_for(channel: ChannelId) -> SecretRef:
    """A reference naming fixture material, with custody declared as fixture custody."""
    return SecretRef(
        name=f"fixture-{channel.value.lower()}",
        channel=channel,
        credential_record=_CREDENTIAL_RECORDS[channel],
        custody="fixture, held by the test suite",
        rotation="never; this material is not real",
    )


class FixtureSecretResolver:
    """Resolves fixture references to fixture material. Nothing real is reachable."""

    def __init__(self, material: VerificationMaterial | None = FIXTURE_MATERIAL) -> None:
        self._material = material

    def material_for(self, ref: SecretRef) -> VerificationMaterial | None:
        return self._material


#: The bounds a fixture run uses. Every value is a fixture value: `D-26` is undeclared, so
#: production cannot construct this object at all and refuses instead.
FIXTURE_BOUNDS = TransportBounds(
    channel=ChannelId.SLACK,
    replay_tolerance_seconds=300,
    maximum_inbound_bytes=32 * 1024,
    timeout_seconds=10,
    retry_attempts=2,
    retry_backoff_seconds=1,
    rate_limit_per_minute=60,
    idempotency_window_seconds=600,
    continuation_mechanism="fixture-continuation",
    policy_version="fixture-policy-1",
)


def bounds_for(channel: ChannelId) -> TransportBounds:
    """Fixture bounds for ``channel``, identical except for the channel they name."""
    return FIXTURE_BOUNDS.model_copy(update={"channel": channel})


def wire_payload(**overrides: object) -> dict[str, object]:
    """The canonical wire payload, with only declared fields.

    A test overriding a field gets exactly that field changed, so a failure names one difference
    rather than a rewritten payload.
    """
    payload: dict[str, object] = {
        "tenant": "tenant-a",
        "language": "pt-BR",
        "reference_date": "2026-08-17",
        "message_id": "provider-message-1",
        "text": "quantas instalações tivemos na Google Play em julho?",
    }
    payload.update(overrides)
    return payload


def signed_request(
    channel: ChannelId,
    payload: dict[str, object] | None = None,
    at: datetime = AT,
    material: VerificationMaterial = FIXTURE_MATERIAL,
    body: bytes | None = None,
) -> RawChannelRequest:
    """A request whose signature genuinely verifies under ``material``.

    ``body`` overrides the serialised payload, for tests that need the signature to be computed
    over one body and presented with another — the tampering case.
    """
    serialised = body if body is not None else json.dumps(payload or wire_payload()).encode()
    timestamp = str(int(at.timestamp()))

    if channel is ChannelId.WHATSAPP:
        headers = (
            ("content-type", "application/json"),
            ("x-hub-signature-256", "sha256=" + hexdigest(material.active, serialised)),
        )
    elif channel is ChannelId.SLACK:
        basestring = b":".join((b"v0", timestamp.encode(), serialised))
        headers = (
            ("content-type", "application/json"),
            ("x-slack-request-timestamp", timestamp),
            ("x-slack-signature", "v0=" + hexdigest(material.active, basestring)),
        )
    elif channel is ChannelId.TELEGRAM:
        headers = (
            ("content-type", "application/json"),
            ("x-telegram-bot-api-secret-token", material.active),
        )
    else:
        basestring = b".".join((timestamp.encode(), serialised))
        headers = (
            ("content-type", "application/json"),
            ("x-client-id", "fixture-client"),
            ("x-signature-timestamp", timestamp),
            ("x-signature-sha256", hexdigest(material.active, basestring)),
        )

    return RawChannelRequest(channel=channel, body=serialised, headers=headers, received_at=at)


#: Structural check that the fixture satisfies the port, at import time. An annotated binding
#: rather than a function, so the check runs on import and is not dead code a linter must excuse.
_RESOLVER_SATISFIES_THE_PORT: SecretResolver = FixtureSecretResolver()


# --------------------------------------------------------------------------- #
# Fixture delivery surfaces — extends T050's channel fixtures for Phase C      #
# --------------------------------------------------------------------------- #
# Added when Phase C needed a transport to drive. It lives here rather than in a new file because
# the ledger declares no fixture module for a delivery double, and inventing one would be an
# undeclared artifact — the finding-F class. A channel fixture is what this file is for.
#
# `T121` declares the fixture **interaction** double separately, in `tests/fixtures/interaction.py`,
# and that one stays out of Phase C: nothing here reaches the interaction port.


class RecordingDeliveryPort:
    """A `DeliveryPort` double that records every send and answers as instructed.

    Records rather than merely counting: `T096` needs to know *which* fragments were offered and in
    what order, and a counter cannot tell a partial send from a repeated one.

    The scripted outcomes are consumed in order, so a test states the provider's behaviour as a
    sequence — first attempt rate-limited, second accepted — rather than as a flag this double
    reinterprets.
    """

    def __init__(
        self,
        outcomes: tuple[DeliveryOutcome, ...] = (DeliveryOutcome.DELIVERED,),
        indeterminate_from: int | None = None,
        fail_fragment: int | None = None,
        raises: bool = False,
    ) -> None:
        self._outcomes = list(outcomes)
        self._indeterminate_from = indeterminate_from
        self._fail_fragment = fail_fragment
        self._raises = raises
        #: Every call, as ``(conversation_ref, tuple_of_fragment_bodies)``.
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    @property
    def sends(self) -> int:
        """How many times the provider was asked to send. What `FR-111` counts."""
        return len(self.calls)

    def send(
        self,
        presentation: RenderedPresentation,
        destination: ChannelDestination,
    ) -> tuple[DeliveryOutcome, tuple[FragmentReceipt, ...]]:
        self.calls.append(
            (str(destination.conversation_id), tuple(f.body for f in presentation.fragments))
        )
        if self._raises:
            # A provider client that throws. The core must collapse it into an outcome and carry no
            # provider text (`FR-061`).
            raise RuntimeError("provider exploded with a message nobody may record")

        outcome = self._outcomes[min(len(self.calls) - 1, len(self._outcomes) - 1)]
        receipts: list[FragmentReceipt] = []
        for fragment in presentation.fragments:
            if self._indeterminate_from is not None and fragment.index >= self._indeterminate_from:
                receipts.append(FragmentReceipt(fragment.index, accepted=False, indeterminate=True))
            elif self._fail_fragment is not None and fragment.index == self._fail_fragment:
                receipts.append(FragmentReceipt(fragment.index, accepted=False))
            else:
                receipts.append(FragmentReceipt(fragment.index, accepted=True))
        return outcome, tuple(receipts)


#: Structural check that the double satisfies the port, performed at import time.
_DOUBLE_SATISFIES_THE_PORT: DeliveryPort = RecordingDeliveryPort()


# --------------------------------------------------------------------------- #
# Fixture audit and capability surfaces — added 2026-08-19 for T122's round trip
# --------------------------------------------------------------------------- #
# Same reasoning as the delivery double above: the ledger declares no fixture module for an audit
# sink or for a capability resolver, and inventing one would be an undeclared artifact. Both are
# channel-side surfaces the composed path drives, which is what this file is for.


class RecordingAuditSink:
    """A `ChannelAuditSink` that keeps every event it accepted, in order.

    Keeps the events rather than a count because `T131` reconstructs a journey from the trail and
    `T122`'s own criterion is about **order** — a counter cannot tell `RECEIVED, VERIFIED` from
    `VERIFIED, RECEIVED`.

    ``refuse_from`` makes the sink stop accepting at a chosen point, so the withholding rule can be
    exercised without a mode: `FR-083` forbids releasing what cannot be recorded, and a sink that
    could never fail would leave that rule untested.
    """

    def __init__(self, refuse_from: int | None = None) -> None:
        self._refuse_from = refuse_from
        #: Every accepted event, in acceptance order.
        self.events: list[ChannelAuditEvent] = []

    @property
    def stages(self) -> tuple[ChannelStage, ...]:
        """The stage trail, in order. What an operator would read."""
        return tuple(event.stage for event in self.events)

    def accept(self, event: ChannelAuditEvent) -> None:
        if self._refuse_from is not None and len(self.events) >= self._refuse_from:
            raise AuditEmissionFailed("the fixture sink was told to stop accepting here")
        self.events.append(event)


def fixture_capabilities(channel: ChannelId) -> Mapping[str, Any]:
    """The fixture capability entry, for **every** channel. **TEST-ONLY.**

    Production resolves this through `governance.capabilities.resolve_capability_matrix`, which
    refuses for every channel because `D-28` is undeclared. That refusal is the shipped behaviour
    and `assert_the_production_resolver_still_refuses` below states it as an assertion rather than
    as a comment, so this fixture cannot quietly become the thing anyone believes production does.

    ``channel`` is accepted and ignored on purpose: a per-channel fixture matrix would be this file
    authoring four governed entries, and one entry that every channel shares cannot be mistaken for
    a declaration about any of them.
    """
    return FIXTURE_CAPABILITY


def assert_the_production_resolver_still_refuses(channel: ChannelId) -> None:
    """Raise unless production's capability resolution still refuses for ``channel``.

    Called by every test that injects `fixture_capabilities`, so injecting one can never be read as
    evidence that the channel is renderable. The day `D-28` is declared, this stops holding and the
    tests that lean on it say so loudly instead of silently continuing to pass.
    """
    try:
        resolve_capability_matrix(channel)
    except (ChannelViolation, ContentUnresolvable):
        # Two bases, because `ContentUnresolvable` is a `ValueError` carrying the document's own
        # code rather than a `ChannelViolation`. Catching only one of them would make this helper
        # report a refusal as a success on exactly the path it exists to check.
        return
    raise AssertionError(
        f"{channel.value} now resolves a real capability matrix, so injecting a fixture one is no "
        "longer measuring the composition against an undeclared decision — re-derive the test"
    )
