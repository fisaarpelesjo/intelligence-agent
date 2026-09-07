"""Retry versus re-request — T084 (FR-034, FR-078; SC-012, SC-036).

Two words for two different things, and conflating them costs either money or
correctness.

A **retry** is the same attempt re-driven because its outcome is unknown or the
transport failed. It attaches to the in-flight execution: no second execution,
no second bill.

A **re-request** is the same execution key asked again later. It executes
afresh and is billed on its own, because the data may have changed and there is
no cache to answer from.

The ledger's state is what distinguishes them, and the mapping is deliberately
asymmetric: `RUNNING` and `UNKNOWN` attach, every terminal state re-executes.
`UNKNOWN` attaching is the load-bearing choice — a process that died mid-flight
may already have billed, so treating it as "never ran" would silently
double-bill. Naming the uncertainty is what lets a retry resolve through the
ledger rather than by assumption.

**Attachment requires the full `ExecutionKey`.** A request whose query identity
matches but whose authorization-context fingerprint differs presents a different
key, and therefore acquires its own execution rather than attaching to one it
was never entitled to observe (`FR-078`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .ledger import Acquired, Attached
from .ledger_entry import TERMINAL_STATUSES

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .ledger import ExecutionKey, ExecutionLedger
    from .ledger_entry import ExecutionLedgerEntry

__all__ = ["Disposition", "SingleFlightOutcome", "classify_disposition", "drive_single_flight"]


class Disposition(StrEnum):
    """What the ledger's state means for this request."""

    #: Attach to an execution already in flight. Zero additional bytes.
    RETRY = "retry"
    #: A fresh attempt with its own entry, billed on its own.
    RE_REQUEST = "re_request"
    #: Nothing exists for this key yet.
    NEW = "new"


@dataclass(frozen=True, slots=True)
class SingleFlightOutcome:
    """The entry this request is bound to, and how it got there."""

    disposition: Disposition
    entry: ExecutionLedgerEntry
    #: True when this caller owns the execution and must drive it to a terminal
    #: state. False when it attached and merely awaits someone else's outcome.
    owns_execution: bool


def classify_disposition(entry: ExecutionLedgerEntry | None) -> Disposition:
    """Read the ledger state as a disposition.

    Deny-by-default in the direction that matters: an unrecognised status is
    treated as `RETRY`, because attaching wastes a wait while re-executing may
    double-bill. When unsure whether money was already spent, assume it was.
    """
    if entry is None:
        return Disposition.NEW
    if entry.status in TERMINAL_STATUSES:
        return Disposition.RE_REQUEST
    return Disposition.RETRY


def drive_single_flight(
    ledger: ExecutionLedger,
    key: ExecutionKey,
    *,
    correlation_id: str,
    principal_ref: str,
) -> SingleFlightOutcome:
    """Acquire or attach atomically, and report which happened.

    **The binding decision is ``acquire`` alone.** The prior state is read only
    to *label* what happened — `acquire` replaces a terminal entry with a fresh
    `PLANNED` one, so afterwards the two cases are indistinguishable. Reading
    first is therefore not the check-then-act race single-flight exists to avoid:
    losing that race mislabels a re-request as new, and never causes a duplicate
    execution, because the compare-and-set still decides who owns the work.
    """
    prior = ledger.get(key)
    observed = classify_disposition(prior)

    result = ledger.acquire(key, correlation_id=correlation_id, principal_ref=principal_ref)

    if isinstance(result, Attached):
        # Someone else holds this execution. Its status tells us whether we are
        # waiting on live work or on an outcome that was lost.
        return SingleFlightOutcome(
            disposition=Disposition.RETRY, entry=result.entry, owns_execution=False
        )

    assert isinstance(result, Acquired)
    # Acquired means this caller owns the work. Whether that is a first attempt
    # or a re-request after a terminal outcome is what the prior read told us,
    # and the ledger records both the same way — only the billing story differs.
    disposition = Disposition.RE_REQUEST if observed is Disposition.RE_REQUEST else Disposition.NEW
    return SingleFlightOutcome(disposition=disposition, entry=result.entry, owns_execution=True)
