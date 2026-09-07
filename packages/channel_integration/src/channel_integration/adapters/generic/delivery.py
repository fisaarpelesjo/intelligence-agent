"""GenericWebhookDeliveryAdapter — T087 (`D-25` undeclared; FR-053, FR-061, FR-071; SC-033).

Implements `delivery.ports.DeliveryPort` and nothing else.

**Unconstructible today.** `D-25` is undeclared, so a client registry, per-client endpoints and a
signature scheme do not exist, and none is created here. :func:`build_generic_delivery` refuses
instead of returning a half-configured adapter — a client that existed but could not send would
turn a governed lock into a runtime surprise.

The generic path is the widest and therefore the most locked: an unreviewed client entry would be
an arbitrary outbound endpoint reachable from a governed answer. `D-25` requires security sign-off
for exactly that reason, and no client is trusted until it exists.

Three prohibitions this adapter is written to satisfy, and which `T103` and `T096` check from
outside: it raises no provider exception, returns no provider object, and forwards no provider
error text (`FR-061`). Material is resolved **here**, through the injected resolver, at the moment
of use, and is never returned to the core (`FR-071`)."""

from __future__ import annotations

from ...compliance.readiness import may_send_to
from ...contracts._base import ChannelViolation
from ...contracts.delivery import ChannelDestination, DeliveryOutcome
from ...contracts.descriptor import ChannelId, CredentialRecord
from ...contracts.presentation import RenderedPresentation
from ...contracts.reason_codes import ChannelReasonCode
from ...delivery.ports import FragmentReceipt
from ...secrets.ref import SecretRef
from ...secrets.resolver import SecretResolver

__all__ = [
    "CHANNEL",
    "CREDENTIAL_RECORD",
    "GenericWebhookDeliveryAdapter",
    "build_generic_delivery",
]

CHANNEL = ChannelId.GENERIC_WEBHOOK
CREDENTIAL_RECORD = CredentialRecord.D_25_GENERIC


class GenericWebhookDeliveryAdapter:
    """Sends a rendered presentation to generic webhook. Holds a reference, never material."""

    __slots__ = ("_ref", "_resolver")

    def __init__(self, ref: SecretRef, resolver: SecretResolver) -> None:
        if ref.channel is not CHANNEL or ref.credential_record is not CREDENTIAL_RECORD:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
                f"the reference does not name {CHANNEL.value} credential material",
            )
        self._ref = ref
        self._resolver = resolver

    def send(
        self,
        presentation: RenderedPresentation,
        destination: ChannelDestination,
    ) -> tuple[DeliveryOutcome, tuple[FragmentReceipt, ...]]:
        """Send every fragment in order, or report why nothing was sent.

        With `D-25` undeclared the resolver yields no material, so this reports ``WITHHELD`` with no
        receipts: zero sends, which is what `FR-111`'s count requires of a channel that cannot send.
        """
        if presentation.channel is not CHANNEL:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
                "the presentation was rendered for another channel",
            )
        if destination.channel is not CHANNEL:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
                "the destination names another channel",
            )
        material = self._resolver.material_for(self._ref)
        if material is None:
            # No credential material exists. Nothing is sent and nothing is invented.
            return DeliveryOutcome.WITHHELD, ()
        # Reached only once `D-25` is declared and material resolves. The provider call itself
        # belongs to the transport surface `D-30` owns, so there is deliberately no client here to
        # call: an adapter that constructed one would be creating the very endpoint `D-25` governs.
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
            "no governed transport surface is declared for this channel (D-30)",
        )


def build_generic_delivery(
    ref: SecretRef, resolver: SecretResolver
) -> GenericWebhookDeliveryAdapter:
    """The only constructor, and it refuses while `D-25` is undeclared.

    Gated on the **readiness record**, not on a flag: ``may_send_to`` derives permission from
    the record's declared evidence, so no configuration, environment variable or argument can
    enable this channel while `D-25` is open (`FR-097`).
    """
    if not may_send_to(CHANNEL):
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
            f"{CHANNEL.value} is gated by {CREDENTIAL_RECORD.value}, which declares no evidence",
        )
    if resolver.material_for(ref) is None:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_CREDENTIAL_UNAVAILABLE,
            f"no credential material resolves for {CHANNEL.value}",
        )
    return GenericWebhookDeliveryAdapter(ref, resolver)
