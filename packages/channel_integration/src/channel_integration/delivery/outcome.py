"""The six delivery outcomes, and what each permits — T080 (ADR 0021; FR-054; SC-024).

The enum itself is Phase A (`contracts/delivery.py`). What lives here is the **behaviour** attached
to each outcome: whether it may be retried, whether it may be reported as delivered, and which
governed code reports it.

``INDETERMINATE`` is the one that matters. A send that timed out **after** the provider may have
accepted it is genuinely unknown. Reporting it as failed invites a resend that double-delivers a
governed answer; reporting it as delivered claims something unverified. So it is neither: it is
never resent and never reported as delivered, and that pair of prohibitions is what makes "no
double delivery" assertable rather than hoped for.

``DUPLICATE_SUPPRESSED`` is likewise terminal. A recognised redelivery inside the governed window
produced no submission and no second response, and re-sending "just in case" would defeat the
suppression that detected it.

The caveat distinction is here rather than in the enum because it depends on the **payload**, not on
the outcome: a delivered response whose payload carried caveats, or which required a disclosed
structural degradation, is reported with ``CHANNEL_RESPONSE_DELIVERED_WITH_CAVEAT``.
"""

from __future__ import annotations

from ..contracts.delivery import DeliveryOutcome, outcome_reason_code
from ..contracts.presentation import RenderedPresentation
from ..contracts.reason_codes import ChannelReasonCode

__all__ = [
    "MAY_BE_REPORTED_DELIVERED",
    "RETRYABLE",
    "TERMINAL",
    "delivered_code_for",
    "may_retry",
    "reason_code_for",
]

#: Outcomes a bounded retry may follow. Deliberately small: two.
RETRYABLE: frozenset[DeliveryOutcome] = frozenset(
    {DeliveryOutcome.RATE_LIMITED, DeliveryOutcome.ATTEMPTS_EXHAUSTED}
)

#: Outcomes that end the attempt with no further send, whatever the caller would prefer.
TERMINAL: frozenset[DeliveryOutcome] = frozenset(
    {
        DeliveryOutcome.DELIVERED,
        DeliveryOutcome.WITHHELD,
        DeliveryOutcome.INDETERMINATE,
        DeliveryOutcome.DUPLICATE_SUPPRESSED,
    }
)

#: The single outcome that may be reported to anyone as "the answer arrived".
MAY_BE_REPORTED_DELIVERED: frozenset[DeliveryOutcome] = frozenset({DeliveryOutcome.DELIVERED})


def may_retry(outcome: DeliveryOutcome) -> bool:
    """May a bounded retry follow ``outcome``?

    ``INDETERMINATE`` returns ``False`` and that is the whole point of the third state: the provider
    may already hold the message, so a retry could deliver a governed answer twice.
    """
    return outcome in RETRYABLE


def reason_code_for(outcome: DeliveryOutcome) -> ChannelReasonCode:
    """The governed code that reports ``outcome``. Total, by the Phase A contract."""
    return outcome_reason_code(outcome)


def delivered_code_for(presentation: RenderedPresentation) -> ChannelReasonCode:
    """Which delivered code a successful send reports, decided by the payload.

    A response that carried caveats, or that required a disclosed structural degradation, is
    reported with the caveated code — so "delivered" never quietly covers "delivered, with things
    the reader must know".
    """
    carried_caveats = presentation.caveat_count > 0
    was_degraded = bool(presentation.degradations)
    if carried_caveats or was_degraded:
        return ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED_WITH_CAVEAT
    return ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED
