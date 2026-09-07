"""One delivery attempt — T077 (ADR 0021; FR-053, FR-055, FR-111; SC-024, SC-066).

One attempt, one explicit terminal status, and **exactly the fragments of one governed outcome, and
zero otherwise**. That last clause is `FR-111` and it is the reactive rule made countable: this
feature originates nothing, so the number of sends caused by an inbound message is either the
fragment count of its one response or zero. There is no acknowledgement, no progress update, no
heartbeat, no retry notice and no "still working on it" — `T104` counts them.

**The destination comes from the inbound envelope and nowhere else** (`FR-029`). Not from shared
state, not from the previous message, not from the response content. A destination derived from
content is a destination an attacker can steer by writing the right question.

**A partial send fails the attempt.** If fragment three is refused after one and two were accepted,
the outcome is not "mostly delivered": a partially delivered answer is a truncated answer by another
route. The outcome reports failure and the receipts show exactly how far it got, so an operator sees
the truth rather than an average.

**A provider exception never escapes.** Anything the port raises — and a well-behaved port raises
nothing — is collapsed here into ``CHANNEL_DELIVERY_FAILED`` with no provider text carried
(`FR-061`).
"""

from __future__ import annotations

from ..contracts.delivery import ChannelDestination, DeliveryOutcome
from ..contracts.envelope import ChannelEnvelope
from ..contracts.presentation import RenderedPresentation
from .ports import DeliveryPort, FragmentReceipt

__all__ = ["AttemptResult", "deliver_once", "destination_for"]


class AttemptResult:
    """The terminal status of one attempt, with the per-fragment receipts behind it."""

    __slots__ = ("outcome", "receipts", "sends")

    def __init__(
        self,
        outcome: DeliveryOutcome,
        receipts: tuple[FragmentReceipt, ...],
        sends: int,
    ) -> None:
        self.outcome = outcome
        self.receipts = receipts
        #: How many sends this attempt caused. Counted rather than assumed, because `FR-111` is a
        #: statement about a number and `T104` reads it.
        self.sends = sends

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        return f"AttemptResult(outcome={self.outcome.value}, sends={self.sends})"


def destination_for(envelope: ChannelEnvelope) -> ChannelDestination:
    """The destination for a response, derived from the inbound envelope only.

    Three fields, all already verified: the channel the message arrived on, the tenant the binding
    confirmed, and the scope-derived conversation reference. The provider-side address is resolved
    inside the adapter, so no provider artifact enters the governed core (`FR-008`).
    """
    return ChannelDestination(
        channel=envelope.channel,
        tenant=envelope.tenant,
        conversation_id=envelope.conversation_id,
    )


def deliver_once(
    port: DeliveryPort,
    presentation: RenderedPresentation,
    envelope: ChannelEnvelope,
) -> AttemptResult:
    """Send ``presentation`` once, and report exactly one terminal outcome.

    Total: every path returns an :class:`AttemptResult`. A port that raises is reported as
    ``ATTEMPTS_EXHAUSTED`` for this attempt rather than propagating: a transport failure is a
    delivery outcome, and an exception crossing this boundary would become an unhandled error in
    whatever loop called it.
    """
    destination = destination_for(envelope)
    try:
        outcome, receipts = port.send(presentation, destination)
    except Exception:
        # Deliberately swallows the exception object: `FR-061` forbids carrying a provider's own
        # text anywhere, and an exception's message is provider text.
        return AttemptResult(DeliveryOutcome.ATTEMPTS_EXHAUSTED, (), 0)

    sends = len(receipts)
    expected = len(presentation.fragments)

    # **Indeterminate wins, and the order matters.** One unknown fragment makes the whole attempt
    # unknown: the provider may already hold part of the answer, so neither failure nor success is
    # honest. This is checked *first* because the partial-delivery rule below would otherwise
    # downgrade an indeterminate attempt to ATTEMPTS_EXHAUSTED — a **retryable** outcome — which is
    # precisely the path that double-delivers a governed answer. `T096` caught that ordering.
    if any(receipt.indeterminate for receipt in receipts):
        return AttemptResult(DeliveryOutcome.INDETERMINATE, receipts, sends)

    # Claiming delivery requires every fragment accepted. Anything less is partial delivery wearing
    # a success label, so the claim is downgraded rather than trusted.
    claimed_delivered = outcome is DeliveryOutcome.DELIVERED
    every_fragment_accepted = sends == expected and all(r.accepted for r in receipts)
    if claimed_delivered and not every_fragment_accepted:
        return AttemptResult(DeliveryOutcome.ATTEMPTS_EXHAUSTED, receipts, sends)

    return AttemptResult(outcome, receipts, sends)
