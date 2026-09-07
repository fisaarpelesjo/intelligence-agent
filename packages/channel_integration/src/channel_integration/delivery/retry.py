"""Bounded retry — T078 (ADR 0021; FR-056, FR-057; SC-026).

A retry **re-sends the same payload**. It never re-invokes the interaction port.

That distinction is the entire module. Re-asking would run the whole governed pipeline again —
authorization, catalog resolution, execution, model-free interpretation — for a message the sender
sent once, and could return a *different* answer if anything upstream moved. The reader would then
have received two different answers to one question, with no way to know which was current.
`T097` counts the port invocations and asserts they stay at one.

**Bounds come from `D-26`.** Attempt count and backoff are governed values, so while that record is
undeclared the bounds are unconstructible and no retry is attempted at all — the transport policy is
resolved before any attempt (`T101` proves nothing is hardcoded).

**`INDETERMINATE` is never retried.** The provider may already hold the message. This is the one
place the third state pays for itself, and it is enforced by :func:`delivery.outcome.may_retry`
rather than re-decided here.

**No clock.** Backoff is *reported* as the governed number of seconds the caller should wait; this
module does not sleep, does not read a clock and does not schedule. A sleeping request path would be
a resident process, which this feature does not own (`D-30`).
"""

from __future__ import annotations

from ..contracts.delivery import DeliveryOutcome
from ..contracts.envelope import ChannelEnvelope
from ..contracts.presentation import RenderedPresentation
from ..governance.bounds import TransportBounds
from .attempt import AttemptResult, deliver_once
from .outcome import may_retry
from .ports import DeliveryPort

__all__ = ["RetryPlan", "deliver_with_retry"]


class RetryPlan:
    """What happened across a bounded sequence of attempts.

    Carries the attempt list rather than only the last outcome: "it failed" and "it failed four
    times, each rate-limited" are different operational facts.
    """

    __slots__ = ("attempts", "backoff_seconds", "outcome")

    def __init__(
        self,
        outcome: DeliveryOutcome,
        attempts: tuple[AttemptResult, ...],
        backoff_seconds: int,
    ) -> None:
        self.outcome = outcome
        self.attempts = attempts
        #: The governed wait the caller should honour before a further attempt, from `D-26`. This
        #: module reports it; it never waits.
        self.backoff_seconds = backoff_seconds

    @property
    def total_sends(self) -> int:
        """Every send across every attempt. What `FR-111` and `T104` count."""
        return sum(attempt.sends for attempt in self.attempts)

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        return (
            f"RetryPlan(outcome={self.outcome.value}, attempts={len(self.attempts)}, "
            f"sends={self.total_sends})"
        )


def deliver_with_retry(
    port: DeliveryPort,
    presentation: RenderedPresentation,
    envelope: ChannelEnvelope,
    bounds: TransportBounds,
) -> RetryPlan:
    """Attempt delivery up to the governed bound, re-sending the **same** presentation.

    The presentation is passed unchanged to every attempt, which is what makes "re-sends the
    payload" a property of the code rather than a discipline: no path here could produce a different
    one, because nothing here can construct a presentation at all.
    """
    attempts: list[AttemptResult] = []
    # `retry_attempts` is the number of *retries* the policy permits, so the first attempt is always
    # made and the bound applies to the ones after it.
    permitted = max(0, bounds.retry_attempts)
    for _ in range(permitted + 1):
        attempt = deliver_once(port, presentation, envelope)
        attempts.append(attempt)
        if not may_retry(attempt.outcome):
            return RetryPlan(attempt.outcome, tuple(attempts), bounds.retry_backoff_seconds)

    exhausted = attempts[-1].outcome
    if exhausted is not DeliveryOutcome.RATE_LIMITED:
        exhausted = DeliveryOutcome.ATTEMPTS_EXHAUSTED
    return RetryPlan(exhausted, tuple(attempts), bounds.retry_backoff_seconds)
