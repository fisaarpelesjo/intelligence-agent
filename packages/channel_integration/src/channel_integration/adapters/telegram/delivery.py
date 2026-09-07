"""TelegramDeliveryAdapter — T086 (`D-24` undeclared; FR-053, FR-061, FR-071; SC-033).

Implements `delivery.ports.DeliveryPort` and nothing else.

**Unconstructible today.** `D-24` is undeclared, so a Telegram bot identity, its token and a
webhook verification secret do not exist, and none is created here.
:func:`build_telegram_delivery` refuses instead of returning a half-configured adapter — a client
that existed but could not send would turn a governed lock into a runtime surprise.

Telegram addresses a conversation by chat id. Recorded here rather than smoothed over: this
channel's inbound scheme also binds no body, a weakness `inbound/schemes/telegram.py` states, and
`D-24` must be provisioned knowing both facts.

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

__all__ = ["CHANNEL", "CREDENTIAL_RECORD", "TelegramDeliveryAdapter", "build_telegram_delivery"]

CHANNEL = ChannelId.TELEGRAM
CREDENTIAL_RECORD = CredentialRecord.D_24_TELEGRAM


class TelegramDeliveryAdapter:
    """Sends a rendered presentation to telegram. Holds a reference, never material."""

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

        With `D-24` undeclared the resolver yields no material, so this reports ``WITHHELD`` with no
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
        # Reached only once `D-24` is declared and material resolves. The provider call itself
        # belongs to the transport surface `D-30` owns, so there is deliberately no client here to
        # call: an adapter that constructed one would be creating the very endpoint `D-24` governs.
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
            "no governed transport surface is declared for this channel (D-30)",
        )


def build_telegram_delivery(ref: SecretRef, resolver: SecretResolver) -> TelegramDeliveryAdapter:
    """The only constructor, and it refuses while `D-24` is undeclared.

    Gated on the **readiness record**, not on a flag: ``may_send_to`` derives permission from
    the record's declared evidence, so no configuration, environment variable or argument can
    enable this channel while `D-24` is open (`FR-097`).
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
    return TelegramDeliveryAdapter(ref, resolver)
