"""The execution-ledger port and the execution key — T039 (FR-066, FR-078; SC-013, SC-036).

**The key is a pair, and that is the whole point.** ``QueryIdentity`` is
deliberately principal-independent (`FR-035`), so two callers in different
authorization scopes derive the *same* identity. A ledger keyed on identity alone
would hand the second caller ``Attached`` for the first's execution, and with it
the execution's status, cost, warehouse job, audit-recovery path and result.

So every method here takes an ``ExecutionKey``. None takes a bare identity —
identity-only keying is unrepresentable through this port rather than merely
discouraged, which is the difference between a rule and a guarantee.

The fingerprint hashes the authorization **context**, not the principal. Two
requests from the same principal under unchanged grants produce the same key, so
a genuine technical retry still attaches (`FR-034`). Keying on the principal
would have broken exactly the property single-flight exists to provide.

**Metadata only.** No method accepts a value-bearing field. Enforced here by the
signatures and by the field-set and content scans over ``ExecutionLedgerEntry``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .ledger_entry import ExecutionLedgerEntry, ExecutionStatus

__all__ = [
    "Acquired",
    "Attached",
    "AuthorizationContext",
    "AuthorizationContextFingerprint",
    "ExecutionKey",
    "ExecutionLedger",
    "LedgerUnavailable",
    "UnresolvedAuthorizationContext",
    "derive_authorization_fingerprint",
]


class LedgerUnavailable(RuntimeError):  # noqa: N818 - named for its reason code, LEDGER_UNAVAILABLE
    """The port could not be reached. There is no proceed-without-a-ledger path."""


class UnresolvedAuthorizationContext(ValueError):  # noqa: N818 - a governed refusal, not an error
    """An input to the fingerprint could not be resolved, so none was computed.

    A partial fingerprint would place the request in the wrong isolation class
    silently, which is worse than refusing.
    """


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """Exactly the authorization inputs that materially determine access.

    Carries no credential, token, personal display data or raw principal
    identifier — the fingerprint derived from it is safe on a metadata-only
    ledger, and is non-reversible besides.
    """

    authorization_scope: str
    granted_access_tags: frozenset[str]
    principal_type: str
    authorization_policy_pin: str

    def is_completely_resolved(self) -> bool:
        """Whether every input is present. Anything missing means refuse."""
        return bool(
            self.authorization_scope
            and self.principal_type
            and self.authorization_policy_pin
            and all(tag for tag in self.granted_access_tags)
        )


#: A SHA-256 hex digest over the canonical authorization context.
type AuthorizationContextFingerprint = str


def derive_authorization_fingerprint(
    context: AuthorizationContext,
) -> AuthorizationContextFingerprint:
    """Hash the authorization context deterministically and non-reversibly.

    Tags are sorted and de-duplicated so grant order never splits an execution
    that should be shared. Raises rather than returning a partial fingerprint.
    """
    if not context.is_completely_resolved():
        raise UnresolvedAuthorizationContext(
            "authorization context is not completely resolved; no fingerprint is computed"
        )
    canonical = json.dumps(
        {
            "authorization_scope": context.authorization_scope,
            "granted_access_tags": sorted(context.granted_access_tags),
            "principal_type": context.principal_type,
            "authorization_policy_pin": context.authorization_policy_pin,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExecutionKey:
    """``(query identity, authorization-context fingerprint)``. Both required.

    Equality and hashing cover both halves, so a differing fingerprint is a
    different key to every dict, set and comparison in the system — the
    isolation property holds by construction rather than by remembering to check.
    """

    query_identity: str
    authorization_context_fingerprint: AuthorizationContextFingerprint

    def __post_init__(self) -> None:
        if not self.query_identity:
            raise ValueError("query_identity is required")
        if not self.authorization_context_fingerprint:
            raise UnresolvedAuthorizationContext(
                "authorization_context_fingerprint is required; an execution key is never "
                "a query identity alone"
            )


@dataclass(frozen=True, slots=True)
class Acquired:
    """This caller owns the execution and must drive it to a terminal state."""

    entry: ExecutionLedgerEntry


@dataclass(frozen=True, slots=True)
class Attached:
    """Another caller *presenting the same key* already owns the execution."""

    entry: ExecutionLedgerEntry


@runtime_checkable
class ExecutionLedger(Protocol):
    """The execution of record, keyed on the full ``ExecutionKey``.

    Concurrency scope is a property of the implementation behind this port, and
    is stated per implementation rather than assumed — see execution-contract
    §7.1. A weaker scope may duplicate an execution, which is wasteful; it must
    never merge two authorization contexts, which is a disclosure.
    """

    def acquire(
        self, key: ExecutionKey, *, correlation_id: str, principal_ref: str
    ) -> Acquired | Attached:
        """Atomic compare-and-set on the full key.

        Exactly one caller receives ``Acquired`` while an entry for that key is
        running; every other caller **presenting the same key** receives
        ``Attached``. A caller whose identity matches but whose fingerprint
        differs presents a different key and acquires its own entry.
        """
        ...

    def attach(
        self, key: ExecutionKey, *, correlation_id: str, principal_ref: str
    ) -> ExecutionLedgerEntry | None:
        """Attach to a running execution, recording the attaching principal.

        Returns ``None`` when no entry exists for this key — including when one
        exists for the same query identity under a different fingerprint.
        """
        ...

    def complete(
        self, key: ExecutionKey, status: ExecutionStatus, **metadata: object
    ) -> ExecutionLedgerEntry:
        """Terminal transition. Idempotent for the same status and key."""
        ...

    def get(self, key: ExecutionKey) -> ExecutionLedgerEntry | None:
        """Read an entry by full key. No lookup by identity alone exists."""
        ...
