"""Authorization-context fingerprint — T062 (FR-078; SC-036).

Derived from the authorization context that the preflight call **already
resolved** — this is not a second authorization decision, and it never re-opens
one. Its only job is to turn "who is asking, under what grants" into a stable,
non-reversible value that the execution key can carry.

The inputs are exactly those that materially determine access: authorization
scope, the normalized granted access-tag set, principal type, and the governed
authorization-policy pin. Credentials, tokens, display names and raw principal
identifiers are excluded — the fingerprint lands on a metadata-only ledger, and
a hash of a secret is still a commitment to that secret.

**Context, not principal.** Two requests from the same principal under unchanged
grants produce the same fingerprint, so a genuine technical retry still attaches
and single-flight keeps working (`FR-034`). Fingerprinting the principal instead
would have broken exactly the property it exists to provide.
"""

from __future__ import annotations

from ..execution.ledger import (
    AuthorizationContext,
    AuthorizationContextFingerprint,
    ExecutionKey,
    UnresolvedAuthorizationContext,
    derive_authorization_fingerprint,
)

__all__ = [
    "AuthorizationContext",
    "AuthorizationContextFingerprint",
    "UnresolvedAuthorizationContext",
    "derive_authorization_fingerprint",
    "execution_key_for",
]


def execution_key_for(
    query_identity: str,
    context: AuthorizationContext,
) -> ExecutionKey:
    """Combine identity and fingerprint into the one key the ledger accepts.

    Raises ``UnresolvedAuthorizationContext`` when the context is incomplete, so
    an unresolved context refuses **before** ledger acquisition — a partial
    fingerprint would file the request into the wrong isolation class silently,
    which is worse than refusing.
    """
    return ExecutionKey(query_identity, derive_authorization_fingerprint(context))
