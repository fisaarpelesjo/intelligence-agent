"""Delivery outcomes and destinations — T011 (FR-054, FR-055; SC-024, SC-025).

**Six outcomes, total.** Every delivery attempt terminates in exactly one of them.
There is no absent, implicit or pending-forever state: silent abandonment,
unbounded retry and fire-and-forget do not exist (`FR-054`).

``INDETERMINATE`` is the one that matters most. A send that times out *after* the
provider may have accepted it is genuinely unknown. Reporting it as failed invites a
resend that double-delivers a governed answer; reporting it as delivered claims
something unverified. The third state is the honest one, and it is what makes "no
double delivery" assertable rather than hoped for (ADR 0021).

Making delivery atomic with its own record would need the transactional outbox —
which belongs to the feature that **originates** messages, and this one never does
(spec `C-2`, ADR 0019).

``ChannelDestination`` carries no provider artifact into the governed core
(`FR-008`): a conversation reference and a channel, resolved by the adapter into
whatever the provider's protocol requires. The adapter is Phase C (T084 — T087).
"""

from __future__ import annotations

from enum import StrEnum

from ._base import ChannelModel, ConversationRef, TenantId
from .descriptor import ChannelId
from .reason_codes import ChannelReasonCode

__all__ = ["ChannelDestination", "DeliveryOutcome", "outcome_reason_code"]


class DeliveryOutcome(StrEnum):
    """The terminal status of one delivery attempt. Closed and total."""

    DELIVERED = "DELIVERED"
    #: Nothing was sent: rendering could not carry the payload intact, or the
    #: preservation gate tripped.
    WITHHELD = "WITHHELD"
    RATE_LIMITED = "RATE_LIMITED"
    ATTEMPTS_EXHAUSTED = "ATTEMPTS_EXHAUSTED"
    #: Timed out after the provider may have accepted. Never resent, never reported
    #: as delivered.
    INDETERMINATE = "INDETERMINATE"
    #: A recognised redelivery within the governed window and the same process. No
    #: submission occurred and no second response was delivered.
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"


_OUTCOME_CODES: dict[DeliveryOutcome, ChannelReasonCode] = {
    DeliveryOutcome.DELIVERED: ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED,
    DeliveryOutcome.WITHHELD: ChannelReasonCode.CHANNEL_OUTBOUND_WITHHELD,
    DeliveryOutcome.RATE_LIMITED: ChannelReasonCode.CHANNEL_RATE_LIMIT_EXCEEDED,
    DeliveryOutcome.ATTEMPTS_EXHAUSTED: ChannelReasonCode.CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED,
    DeliveryOutcome.INDETERMINATE: ChannelReasonCode.CHANNEL_DELIVERY_INDETERMINATE,
    DeliveryOutcome.DUPLICATE_SUPPRESSED: ChannelReasonCode.CHANNEL_MESSAGE_DUPLICATE,
}


def outcome_reason_code(outcome: DeliveryOutcome) -> ChannelReasonCode:
    """The governed code that reports ``outcome``.

    Total by construction and asserted by T015: an outcome with no code would be a
    delivery state nothing could audit, which is the failure the six-outcome rule
    exists to prevent.

    ``DELIVERED`` maps to the plain delivered code. A payload that carried upstream
    caveats, or that required a disclosed structural degradation, is reported with
    ``CHANNEL_RESPONSE_DELIVERED_WITH_CAVEAT`` by the delivery path in Phase C —
    that distinction depends on the payload, not on the outcome, so it is not
    derivable here.
    """
    try:
        return _OUTCOME_CODES[outcome]
    except KeyError as exc:  # pragma: no cover - guarded by the contract test
        raise ValueError(f"delivery outcome {outcome!r} has no governed reason code") from exc


class ChannelDestination(ChannelModel):
    """Where a response goes, in governed terms only.

    Derived from the **inbound envelope** and nothing else: never from shared mutable
    state, never from a previous message, never from the response content
    (`FR-029`).
    """

    channel: ChannelId
    tenant: TenantId
    conversation_id: ConversationRef

    # The provider-side address is deliberately **absent**. An adapter resolves the
    # conversation reference into whatever the provider's protocol needs, inside the
    # adapter, where provider artifacts are allowed to exist (`FR-008`, `FR-071`).
    # A field for it here would be a provider artifact in a governed contract, and
    # `extra="forbid"` means one cannot be added by a caller either.
