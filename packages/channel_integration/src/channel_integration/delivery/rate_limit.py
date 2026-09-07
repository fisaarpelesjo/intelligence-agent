"""Rate limiting, per channel, with per-principal fairness — T079 (FR-057; SC-025).

Two limits, and the second is the one that is usually forgotten:

* **per channel**, because the provider's limit is per channel and exceeding it gets the whole
  integration throttled;
* **per principal inside a tenant**, because a channel-wide limit alone lets one busy principal
  consume the tenant's whole allowance and starve everyone else. Fairness is not politeness here: a
  starved principal receives no answer, which is indistinguishable from a broken integration.

**What the per-principal limit can and cannot do today, stated precisely.** `D-26` declares a
channel allowance and **no per-principal share**. A share is a governed value, so this module does
not author one — an earlier version divided the allowance by a hardcoded four, and `T101` correctly
reported that as a policy this feature had no authority to set.

What is left is derivable: the share is the governed allowance split across the principals
**observed active in the window**. That bounds a busy principal once a second one appears, and it
cannot reserve capacity for a principal who has not sent yet. So a first principal may still
consume the whole channel allowance before anyone else arrives, and no fairness rule expressible
without a governed share can prevent that. Recorded as a discovered dependency rather than
papered over: `FR-057`'s fairness requirement needs a per-principal share in `D-26` to be fully
satisfiable.

**Process-local by construction**, exactly like idempotency (ADR 0021). Nothing here replicates,
shares, synchronises or coordinates, so this claims a limit **for one process** and says so. Running
several instances without a governed shared store would make the effective limit a multiple of the
governed one — which is why multi-instance configuration **refuses** (`T083`).

**No clock.** The evaluation instant is a parameter, so a window boundary is testable at exactly the
second it flips (`R-5`).

The counter holds a pseudonymous principal reference and a count. No question, no answer, no value
and no personal data (`FR-066`).
"""

from __future__ import annotations

from datetime import datetime

from ..contracts._base import PrincipalRef, TenantId
from ..contracts.descriptor import ChannelId
from ..governance.bounds import TransportBounds

__all__ = ["RateLimiter", "RateVerdict"]


class RateVerdict:
    """Whether a send is permitted now, and what the limiter counted.

    Carries the counts so a refusal is explicable without re-deriving them, and so a test can assert
    the fairness split rather than only the yes/no.
    """

    __slots__ = ("channel_count", "permitted", "principal_count")

    def __init__(self, permitted: bool, channel_count: int, principal_count: int) -> None:
        self.permitted = permitted
        self.channel_count = channel_count
        self.principal_count = principal_count

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        return (
            f"RateVerdict(permitted={self.permitted}, channel={self.channel_count}, "
            f"principal={self.principal_count})"
        )


class RateLimiter:
    """A process-local, window-bounded counter over a channel and its principals.

    The window is `D-26`'s ``rate_limit_per_minute``, evaluated against the **passed** instant. One
    limiter instance is one process's view, and it is named that way in every report so nothing
    reads it as a distributed guarantee.
    """

    __slots__ = ("_channel_events", "_principal_events")

    def __init__(self) -> None:
        self._channel_events: dict[ChannelId, list[datetime]] = {}
        self._principal_events: dict[tuple[TenantId, ChannelId, PrincipalRef], list[datetime]] = {}

    @staticmethod
    def _within(events: list[datetime], at: datetime, window_seconds: int) -> list[datetime]:
        """The events still inside the window ending at ``at``.

        Filtering rather than mutating in place, so a verdict never depends on whether a previous
        caller happened to prune first.
        """
        return [event for event in events if (at - event).total_seconds() < window_seconds]

    def evaluate(
        self,
        channel: ChannelId,
        tenant: TenantId,
        principal_ref: PrincipalRef,
        bounds: TransportBounds,
        at: datetime,
    ) -> RateVerdict:
        """Would a send now be within both limits? Counts nothing; decides only.

        Split from :meth:`record` so a caller can ask before sending without the question itself
        consuming allowance — a limiter whose check is also a charge cannot be tested.
        """
        window = 60
        limit = bounds.rate_limit_per_minute

        channel_events = self._within(self._channel_events.get(channel, []), at, window)
        key = (tenant, channel, principal_ref)
        principal_events = self._within(self._principal_events.get(key, []), at, window)

        # Per-principal fairness, **derived from observed state rather than from a chosen
        # constant**. An earlier version divided the channel allowance by a hardcoded four, which
        # was a governed value this feature had no authority to author — `T101` caught it. The
        # share is now the channel's governed allowance split across the principals actually
        # active in this window, at least one, so the only number involved is one the caller can
        # see.
        active = max(1, self._active_principals(channel, at, window))
        principal_limit = max(1, limit // active)

        permitted = len(channel_events) < limit and len(principal_events) < principal_limit
        return RateVerdict(permitted, len(channel_events), len(principal_events))

    def _active_principals(self, channel: ChannelId, at: datetime, window_seconds: int) -> int:
        """How many principals have sent on ``channel`` inside the window.

        Observed, not configured. This is what lets the fairness share be arithmetic over a fact
        instead of a constant somebody picked.
        """
        return sum(
            1
            for (_, event_channel, _), events in self._principal_events.items()
            if event_channel is channel and self._within(events, at, window_seconds)
        )

    def record(
        self,
        channel: ChannelId,
        tenant: TenantId,
        principal_ref: PrincipalRef,
        at: datetime,
    ) -> None:
        """Record that a send happened at ``at``."""
        self._channel_events.setdefault(channel, []).append(at)
        self._principal_events.setdefault((tenant, channel, principal_ref), []).append(at)
