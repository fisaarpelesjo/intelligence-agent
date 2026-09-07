"""The idempotency window — T081 (ADR 0021; FR-063 to FR-065; SC-029, SC-064).

A store of :class:`ChannelIdempotencyRecord` keyed by ``(channel, message_id)``, bounded by `D-26`'s
governed window, and **process-local by construction**.

"By construction" is a claim about what the code cannot do, and it is written to be checkable:

* the store is a plain ``dict`` on an instance, so its lifetime is the object's;
* nothing here imports a client, a socket, a broker, a cache or a database driver — `T098`'s scan
  asserts the absence;
* there is no ``replicate``, ``sync``, ``share``, ``publish`` or ``coordinate`` operation, because
  every one of those would be a distributed-deduplication claim in disguise;
* the scope is named in the docstring of every public operation, so a reader cannot pick up the
  suppression guarantee without also picking up its limit.

**The window is governed, not chosen.** ``idempotency_window_seconds`` comes from `D-26`; while that
record is undeclared the bounds object is unconstructible, so no window exists and no suppression is
claimed at all.

**The instant is passed.** Expiry is evaluated against the caller's instant, which makes the
boundary testable at exactly the second it flips (`R-5`).

**First-seen wins.** A redelivery inside the window returns ``DUPLICATE_SUPPRESSED`` and the
original outcome class. It does **not** re-submit and does not re-deliver: the whole point is that
the sender's second copy of one message produces no second answer.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..contracts._base import MessageKey, PrincipalRef, TenantId
from ..contracts.delivery import DeliveryOutcome
from ..contracts.descriptor import ChannelId
from ..governance.bounds import TransportBounds
from .record import ChannelIdempotencyRecord, IdempotencyKey, key_for

__all__ = ["IdempotencyDecision", "IdempotencyWindow"]


class IdempotencyDecision:
    """Whether this message has been seen, and what happened the first time.

    ``first_outcome`` is ``None`` for a message never seen inside the window. It is the original
    outcome class for a recognised redelivery, so a caller can report what happened without
    re-deriving or re-sending it.
    """

    __slots__ = ("first_outcome", "is_duplicate", "record")

    def __init__(
        self,
        is_duplicate: bool,
        first_outcome: DeliveryOutcome | None,
        record: ChannelIdempotencyRecord | None,
    ) -> None:
        self.is_duplicate = is_duplicate
        self.first_outcome = first_outcome
        self.record = record

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        return (
            f"IdempotencyDecision(duplicate={self.is_duplicate}, "
            f"first_outcome={self.first_outcome.value if self.first_outcome else None})"
        )


class IdempotencyWindow:
    """One process's view of which messages it has already handled.

    **Scope: this process, this instance, this governed window.** Nothing is replicated, shared,
    synchronised or coordinated, so this suppresses duplicates *here* and claims nothing about any
    other instance. Running several instances without a governed shared store is refused rather than
    silently degraded (`T083`).
    """

    __slots__ = ("_records",)

    def __init__(self) -> None:
        self._records: dict[IdempotencyKey, ChannelIdempotencyRecord] = {}

    def check(
        self,
        channel: ChannelId,
        message_id: MessageKey,
        at: datetime,
    ) -> IdempotencyDecision:
        """Has this message been handled inside the window? Decides; records nothing.

        Scope, restated because a caller reads this docstring and not the class one: **this process
        only**.
        """
        record = self._records.get(key_for(channel, message_id))
        if record is None:
            return IdempotencyDecision(False, None, None)
        if record.has_expired(at):
            # Outside the governed window the record is no longer evidence of anything, so the
            # message is handled afresh rather than suppressed forever.
            return IdempotencyDecision(False, None, None)
        return IdempotencyDecision(True, record.outcome_class, record)

    def remember(
        self,
        channel: ChannelId,
        message_id: MessageKey,
        tenant: TenantId,
        principal_ref: PrincipalRef,
        outcome: DeliveryOutcome,
        bounds: TransportBounds,
        at: datetime,
    ) -> ChannelIdempotencyRecord:
        """Record that this message was handled, with the outcome **class** and nothing else.

        Scope: **this process only**. The expiry is computed from the governed window and the passed
        instant, so no clock is read and the boundary is exact.
        """
        record = ChannelIdempotencyRecord(
            key=key_for(channel, message_id),
            tenant=tenant,
            principal_ref=principal_ref,
            outcome_class=outcome,
            first_seen_at=at,
            expires_at=at + timedelta(seconds=bounds.idempotency_window_seconds),
            policy_version=bounds.policy_version,
        )
        # First-seen wins: a redelivery must not overwrite the original record, or the outcome
        # reported for a duplicate would drift from what actually happened first.
        self._records.setdefault(record.key, record)
        return self._records[record.key]

    def size(self) -> int:
        """How many records this **process** holds. For tests and operator reporting only."""
        return len(self._records)
