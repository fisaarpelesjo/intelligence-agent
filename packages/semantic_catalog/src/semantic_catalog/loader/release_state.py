"""Catalog-release state and corrective releases — T091 (FR-065, FR-075).

A published release is immutable. When one turns out to be wrong, the correction
is **forward-only**: build a new release, validate it, publish it, and move the
active pointer — in that order. The bad release is marked ``withdrawn``, never
edited and never deleted, and stays resolvable forever so the decisions issued
under it can still be explained (FR-065).

Four properties this ledger enforces rather than documents:

**The pointer moves only after validation.** :meth:`ReleaseLedger.publish` takes
a :class:`~semantic_catalog.validation.release.ReleaseValidation` and refuses an
invalid one. Passing a bare boolean would let a caller assert validity it never
established, which is the failure FR-075 is about — and *resolving a merge
conflict is not validation*, which is why the validation object carries the
commit it validated.

**Identifiers are never reused.** Publishing an id the ledger has already seen
raises. Since ``catalog_release_id`` is a content hash, a repeat means either the
same content — in which case there is nothing to publish — or a caller inventing
identifiers, which would make two different releases indistinguishable in an
audit.

**Withdrawal changes what is admitted, not what is resolvable.** A withdrawn
release refuses *new* decisions (``RELEASE_WITHDRAWN``); it resolves for audit
exactly as before, and decisions already issued keep their original release
reference because nothing rewrites them.

**Rollback is a new audited activation event.** Reactivating a previously valid
release appends an event; it does not rewind the log, reuse the earlier event's
identifier, or delete what happened in between. History that can be rewritten is
not an audit trail.

The ledger is in-memory and append-only. Durable storage of release state belongs
to the operational feature (D-13); what this feature owns is the state machine
and the rules it refuses to break.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ..validation.release import ReleaseValidation

__all__ = [
    "ActivationEvent",
    "CatalogRelease",
    "EventKind",
    "ReleaseIdentifierReuseError",
    "ReleaseLedger",
    "ReleaseStateError",
    "UnknownReleaseError",
    "UnvalidatedReleaseError",
]


class ReleaseStateError(RuntimeError):
    """Base for every refusal this ledger makes."""


class ReleaseIdentifierReuseError(ReleaseStateError):
    """A release identifier was published twice. Never permitted (FR-075)."""


class UnvalidatedReleaseError(ReleaseStateError):
    """Publication or activation was attempted without a passing validation."""


class UnknownReleaseError(ReleaseStateError):
    """A release the ledger never saw. Fails closed rather than assuming active."""


class ReleaseState(StrEnum):
    """data-model §4.5. Only ``ACTIVE`` admits new decisions."""

    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


class EventKind(StrEnum):
    """What an activation event records. Every state change has one."""

    PUBLISH = "publish"
    WITHDRAW = "withdraw"
    ACTIVATE = "activate"


@dataclass(frozen=True, slots=True)
class ActivationEvent:
    """One audited state change. Append-only; never rewritten."""

    event_id: str
    kind: EventKind
    release_id: str
    occurred_at: datetime
    reason: str
    actor_role: str
    validated_commit: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogRelease:
    """data-model §4.5. Immutable; a transition produces a new value."""

    release_id: str
    state: ReleaseState
    activated_at: datetime
    activation_event_id: str
    withdrawn_at: datetime | None = None

    @property
    def admits_new_decisions(self) -> bool:
        """Only an active release may back a new decision (FR-075)."""
        return self.state is ReleaseState.ACTIVE


def _event_id(kind: EventKind, release_id: str, occurred_at: datetime, sequence: int) -> str:
    """Deterministic, unique, and derived from what happened.

    Derived rather than random so a replayed ledger reproduces the same event
    ids; the sequence number is included so two events for the same release at
    the same instant still differ.
    """
    payload = f"{sequence}:{kind.value}:{release_id}:{occurred_at.isoformat()}"
    return f"evt:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


@dataclass(slots=True)
class ReleaseLedger:
    """Every release the catalog has published, and every event that moved one."""

    _releases: dict[str, CatalogRelease] = field(default_factory=dict[str, CatalogRelease])
    _events: list[ActivationEvent] = field(default_factory=list[ActivationEvent])

    @classmethod
    def restore(
        cls,
        releases: Sequence[CatalogRelease],
        events: Sequence[ActivationEvent],
    ) -> ReleaseLedger:
        """Rehydrate a ledger that was persisted elsewhere.

        Durable storage belongs to the operational feature (D-13), so something
        outside this library holds the bytes and hands them back. Restoring is
        not publishing: the rules that gate a *new* release do not re-run here,
        because these transitions already happened and re-deciding them would
        let a rule change rewrite history.

        Refuses a duplicate identifier, because two releases that cannot be told
        apart make every decision citing one of them unauditable.
        """
        ledger = cls()
        for release in releases:
            if release.release_id in ledger._releases:
                raise ReleaseIdentifierReuseError(
                    f"release {release.release_id!r} appears twice in the restored ledger; "
                    "identifiers are never reused (FR-075)"
                )
            ledger._releases[release.release_id] = release
        ledger._events.extend(events)
        return ledger

    # -- reads ---------------------------------------------------------------

    @property
    def releases(self) -> Mapping[str, CatalogRelease]:
        return dict(self._releases)

    @property
    def events(self) -> tuple[ActivationEvent, ...]:
        return tuple(self._events)

    @property
    def active(self) -> CatalogRelease | None:
        """The release new decisions run against, or ``None`` before the first."""
        return next(
            (r for r in self._releases.values() if r.state is ReleaseState.ACTIVE),
            None,
        )

    def resolve(self, release_id: str) -> CatalogRelease | None:
        """Any release, whatever its state.

        Withdrawn and superseded releases resolve exactly like active ones. That
        is the FR-065 guarantee: an old decision stays explainable.
        """
        return self._releases.get(release_id)

    def admits_new_decisions(self, release_id: str) -> bool:
        """Fails closed on an unknown id: unknown is not permission."""
        release = self._releases.get(release_id)
        return release is not None and release.admits_new_decisions

    # -- writes --------------------------------------------------------------

    def _record(
        self,
        kind: EventKind,
        release_id: str,
        occurred_at: datetime,
        reason: str,
        actor_role: str,
        validated_commit: str | None = None,
    ) -> ActivationEvent:
        event = ActivationEvent(
            event_id=_event_id(kind, release_id, occurred_at, len(self._events)),
            kind=kind,
            release_id=release_id,
            occurred_at=occurred_at,
            reason=reason,
            actor_role=actor_role,
            validated_commit=validated_commit,
        )
        self._events.append(event)
        return event

    def _supersede_active(self, except_id: str) -> None:
        for release_id, release in self._releases.items():
            if release_id != except_id and release.state is ReleaseState.ACTIVE:
                self._releases[release_id] = CatalogRelease(
                    release_id=release.release_id,
                    state=ReleaseState.SUPERSEDED,
                    activated_at=release.activated_at,
                    activation_event_id=release.activation_event_id,
                    withdrawn_at=release.withdrawn_at,
                )

    def publish(
        self,
        release_id: str,
        validation: ReleaseValidation,
        *,
        occurred_at: datetime,
        reason: str,
        actor_role: str,
    ) -> CatalogRelease:
        """Publish a new release and move the active pointer to it.

        Both refusals matter. An identifier already in the ledger cannot be
        republished, and a validation that did not pass cannot publish anything —
        the pointer moves *after* validation succeeds, never before, and never on
        the strength of a merge that merely applied cleanly.
        """
        if release_id in self._releases:
            raise ReleaseIdentifierReuseError(
                f"release {release_id!r} is already in the ledger; identifiers are never reused, "
                "and an incorrect release is corrected by publishing a new one (FR-075)"
            )
        if not validation.valid:
            raise UnvalidatedReleaseError(
                f"release {release_id!r} cannot be published: validation of commit "
                f"{validation.commit!r} reported {len(validation.report.errors)} error(s). The "
                "active pointer moves only after validation succeeds"
            )

        event = self._record(
            EventKind.PUBLISH, release_id, occurred_at, reason, actor_role, validation.commit
        )
        self._supersede_active(release_id)
        release = CatalogRelease(
            release_id=release_id,
            state=ReleaseState.ACTIVE,
            activated_at=occurred_at,
            activation_event_id=event.event_id,
        )
        self._releases[release_id] = release
        return release

    def withdraw(
        self, release_id: str, *, occurred_at: datetime, reason: str, actor_role: str
    ) -> CatalogRelease:
        """Mark a release withdrawn. It stays resolvable; it is never edited."""
        existing = self._releases.get(release_id)
        if existing is None:
            raise UnknownReleaseError(
                f"release {release_id!r} is not in the ledger and cannot be withdrawn"
            )
        event = self._record(EventKind.WITHDRAW, release_id, occurred_at, reason, actor_role)
        withdrawn = CatalogRelease(
            release_id=existing.release_id,
            state=ReleaseState.WITHDRAWN,
            activated_at=existing.activated_at,
            activation_event_id=event.event_id,
            withdrawn_at=occurred_at,
        )
        self._releases[release_id] = withdrawn
        return withdrawn

    def activate(
        self, release_id: str, *, occurred_at: datetime, reason: str, actor_role: str
    ) -> CatalogRelease:
        """Roll back to a previously valid release through a **new** event.

        A withdrawn release is not activatable: it was withdrawn because it was
        wrong, and reactivating it would make withdrawal reversible by fiat
        rather than by publishing a corrected release.
        """
        existing = self._releases.get(release_id)
        if existing is None:
            raise UnknownReleaseError(
                f"release {release_id!r} is not in the ledger; rollback activates a previously "
                "valid immutable release, never an unknown one"
            )
        if existing.state is ReleaseState.WITHDRAWN:
            raise UnvalidatedReleaseError(
                f"release {release_id!r} is withdrawn and must not be reactivated; publish a "
                "corrective release instead (FR-075)"
            )

        event = self._record(EventKind.ACTIVATE, release_id, occurred_at, reason, actor_role)
        self._supersede_active(release_id)
        activated = CatalogRelease(
            release_id=existing.release_id,
            state=ReleaseState.ACTIVE,
            activated_at=occurred_at,
            activation_event_id=event.event_id,
            withdrawn_at=existing.withdrawn_at,
        )
        self._releases[release_id] = activated
        return activated
