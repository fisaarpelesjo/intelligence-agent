"""The authorization-context fingerprint — T089 (FR-056; SC-006).

**Carried alongside the interpretation identity, never folded into it.**

This mirrors `002`'s security amendment rather than repeating its original
mistake. `002` keyed its execution ledger on ``QueryIdentity`` alone, and
identity-only keying let a caller in a different authorization scope attach to an
execution acquired by another — inheriting its status, cost, job, audit-recovery
path and result. The fix was to **split the key** rather than pollute identity:
``ExecutionKey = (QueryIdentity, AuthorizationContextFingerprint)``.

The same split applies here for the same reason:

| | |
|---|---|
| **Identity** | principal-independent, so audit can observe the same question asked by two people |
| **Fingerprint** | binds the authorized identity, so an intent or a clarification
  contract issued to one principal is refused when presented by another |

Folding the fingerprint into the identity would destroy the first property;
dropping it would destroy the second.

## The five bound fields

``principal_ref``, principal type, authorization scope, the **canonically sorted**
granted tag set, and the governed authorization-policy pin.

**``principal_ref`` is part of who was authorized**, not a display field. An
earlier draft of this module excluded it, on the reasoning that fingerprinting
the principal would break retry equality. That reasoning was wrong in a way worth
recording: the same ``principal_ref`` hashes to the same value every time, so a
genuine repeat by the same principal still produces a byte-identical fingerprint
and single-flight still works. What the exclusion actually bought was a
**collision** — two *distinct* principals holding identical grants shared one
fingerprint, so a contract bound to one would have validated when presented by
the other. Since this value binds resolved intent and stateless clarification
contracts to an authorized identity, that collision is the whole failure mode the
binding exists to prevent.

Corrected as a security fix before the Phase 8 commit.

## What the output is, and is not

A **deterministic 64-character digest** and nothing else. It is an
identity-binding value, **not an authentication token and not an authorization
decision** — holding it grants nothing, and comparing two of them answers only
"was this the same authorized identity".

The digest exposes no raw field: no principal reference, no tag, no scope, no
policy pin. The canonical preimage is built, hashed and dropped — it is never
returned, logged or persisted, because a preimage carrying an identity reference
beside a grant set is exactly the payload the digest exists to avoid handling.

No randomness, no clock, no mutable state and no undeclared secret. This is a
plain digest over declared inputs, so two processes agree without sharing
anything.
"""

from __future__ import annotations

import hashlib
import json

from ..authorization.context_preflight import AuthorizedContext

__all__ = [
    "FINGERPRINT_INPUTS",
    "derive_authorization_fingerprint",
    "fingerprints_match",
]

#: What the fingerprint is derived from, in canonical order. Named so a reviewer
#: can see the whole input set without reading the serialisation, and so a field
#: added to ``PrincipalContext`` cannot silently join or leave it.
FINGERPRINT_INPUTS: tuple[str, ...] = (
    "principal_ref",
    "principal_type",
    "authorization_scope",
    "granted_access_tags",
    "authorization_policy_pin",
)


def derive_authorization_fingerprint(authorized: AuthorizedContext) -> str:
    """A stable, non-reversible fingerprint of the resolved authorization identity.

    Takes an ``AuthorizedContext``, so a fingerprint cannot be derived from a
    context the preflight never resolved — an unresolved scope or pin would
    otherwise file a request into the wrong isolation class silently, which is
    worse than refusing.

    The tag set is **sorted** before hashing: it is a set, and two requests
    carrying the same grants in different orders hold the same authorization.
    Everything else is carried verbatim, because scope, pin and principal
    reference are compared byte-for-byte upstream and a normalisation here would
    make this fingerprint coarser than the decision it describes.

    The preimage is local to this call and is never returned or recorded.
    """
    context = authorized.context
    payload = {
        "principal_ref": context.principal_ref,
        "principal_type": str(context.principal_type),
        "authorization_scope": context.authorization_scope,
        "granted_access_tags": sorted(context.granted_access_tags),
        "authorization_policy_pin": context.authorization_policy_pin,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprints_match(left: str, right: str) -> bool:
    """Whether two fingerprints describe the same authorized identity.

    A named function rather than an inline ``==`` so the comparison has one place
    to live, and so a caller cannot accidentally compare a fingerprint against a
    principal reference and have it typecheck.
    """
    return left == right
