"""In-process execution ledger — T045 (FR-036, FR-078; SC-012, SC-036).

**Test and single-process local stewardship only.** Its atomicity is a lock
inside one process, so two processes each see an empty ledger and both execute.
That is stated, not assumed: full `FR-036` needs the shared atomic adapter
(`D-17`), and multi-process deployment without it is a forbidden configuration
guarded by readiness — never a silent downgrade to per-process single-flight.
A downgrade would satisfy `FR-036` in tests and violate it in production, which
is the worst combination available.

Cross-authorization isolation, by contrast, holds **here** and in every other
implementation, because it is a property of the key rather than of the locking:
the store is keyed on ``ExecutionKey``, and a differing authorization-context
fingerprint is simply a different dict key (`FR-078`).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from .ledger import Acquired, Attached, ExecutionKey
from .ledger_entry import (
    TERMINAL_STATUSES,
    ExecutionAttachment,
    ExecutionLedgerEntry,
    ExecutionStatus,
)

__all__ = ["InMemoryExecutionLedger"]

#: States in which a further caller attaches rather than starting a second
#: execution. `UNKNOWN` is included deliberately — the query may already have
#: billed, so re-executing would bill twice.
_ATTACHABLE: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.PLANNED,
        ExecutionStatus.DRY_RUN_OK,
        ExecutionStatus.RUNNING,
        ExecutionStatus.UNKNOWN,
    }
)


class InMemoryExecutionLedger:
    """A dict guarded by one lock. Correct within a process, and only there."""

    __slots__ = ("_entries", "_lock")

    def __init__(self) -> None:
        self._entries: dict[ExecutionKey, ExecutionLedgerEntry] = {}
        self._lock = threading.Lock()

    def acquire(
        self, key: ExecutionKey, *, correlation_id: str, principal_ref: str
    ) -> Acquired | Attached:
        """Atomic compare-and-set on the full key.

        The lock spans the read and the write. Checking membership and then
        inserting outside a lock is the classic way two callers both believe
        they acquired — the bug this method exists to not have.
        """
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing.status in _ATTACHABLE:
                attached = existing.with_attachment(
                    ExecutionAttachment(
                        principal_ref=principal_ref,
                        correlation_id=correlation_id,
                        attached_at=datetime.now(UTC),
                    )
                )
                self._entries[key] = attached
                return Attached(entry=attached)

            # No entry, or a terminal one: this is a new execution of record.
            # A terminal entry means the previous attempt finished, so this is a
            # re-request and is billed on its own.
            entry = ExecutionLedgerEntry(
                query_identity=key.query_identity,
                authorization_context_fingerprint=key.authorization_context_fingerprint,
                correlation_id=correlation_id,
                principal_ref=principal_ref,
                status=ExecutionStatus.PLANNED,
                started_at=datetime.now(UTC),
            )
            self._entries[key] = entry
            return Acquired(entry=entry)

    def attach(
        self, key: ExecutionKey, *, correlation_id: str, principal_ref: str
    ) -> ExecutionLedgerEntry | None:
        """Attach to a running execution for this exact key.

        Returns ``None`` when nothing is attachable — including when an entry
        exists for the same query identity under a *different* fingerprint,
        which is simply a different key and therefore invisible here.
        """
        with self._lock:
            existing = self._entries.get(key)
            if existing is None or existing.status not in _ATTACHABLE:
                return None
            attached = existing.with_attachment(
                ExecutionAttachment(
                    principal_ref=principal_ref,
                    correlation_id=correlation_id,
                    attached_at=datetime.now(UTC),
                )
            )
            self._entries[key] = attached
            return attached

    def complete(
        self, key: ExecutionKey, status: ExecutionStatus, **metadata: object
    ) -> ExecutionLedgerEntry:
        """Terminal transition. Replaying the same terminal status is a no-op."""
        with self._lock:
            existing = self._entries.get(key)
            if existing is None:
                raise KeyError("no execution of record for this key")
            if existing.status is status and status in TERMINAL_STATUSES:
                return existing
            update: dict[str, object] = {"status": status, **metadata}
            if status in TERMINAL_STATUSES and "ended_at" not in metadata:
                update["ended_at"] = datetime.now(UTC)
            completed = existing.model_copy(update=update)
            # Re-validate: model_copy bypasses validators, and the terminal
            # invariants are exactly what must not be bypassed here.
            completed = ExecutionLedgerEntry.model_validate(completed.model_dump())
            self._entries[key] = completed
            return completed

    def get(self, key: ExecutionKey) -> ExecutionLedgerEntry | None:
        """Read by full key. There is no lookup by query identity alone."""
        with self._lock:
            return self._entries.get(key)
