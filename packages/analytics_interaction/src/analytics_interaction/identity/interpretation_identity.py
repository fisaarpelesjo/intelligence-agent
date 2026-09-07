"""The interpretation identity — T088 (FR-056, FR-098; SC-006).

```
InterpretationIdentity = H(
    canonical(ResolvedIntent), reference_date, as_of, language,
    catalog_release, policy_version, vocabulary_version )
```

**Never derived from raw question text** (`FR-056`). Two people who ask the same
thing in different words reach the same identity; one person who asks the same
words about different things does not. Hashing the text would invert both, and
would put a span of the question into whatever stored the identity.

**Principal-independent**, deliberately, so audit can observe the same question
asked by two people. Safe here precisely because this feature holds no state and
acquires nothing — identity keys no shared resource. Where the authorization
dimension is needed, `authorization_fingerprint.py` carries it **alongside**.

**Both dates are separate members** (`FR-098`). The same sentence under a
different reference date is a different interpretation rather than a collision,
and so is the same sentence under a different as-of pin. Neither is derived from
the other and neither can be: they enter the canonical form as two distinct keys,
and an omitted ``as_of`` enters as ``null`` rather than being filled or dropped.

**Normalisation is scoped exactly as `002` scopes it.** Governed identifiers and
structural formatting normalise; **filter values do not**. `002`'s `FR-033` keeps
filter values byte- and Unicode-sensitive because the warehouse compares them
that way, and an identity coarser than the request it produces would let two
semantically different questions share one (`SC-006`).

**No clock, no randomness, no process identity, no mutable state.** Every input
is an argument, and the same arguments always produce the same digest.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..contracts.intent import ResolvedIntent

__all__ = [
    "IDENTITY_MEMBERS",
    "canonical_intent",
    "derive_interpretation_identity",
]

#: The seven members, in the order the contract states them. Named so a reviewer
#: sees the whole composition without reading the serialisation — and so a field
#: added to ``ResolvedIntent`` cannot silently join or leave the identity.
IDENTITY_MEMBERS: tuple[str, ...] = (
    "intent",
    "reference_date",
    "as_of",
    "language",
    "catalog_release",
    "policy_version",
    "vocabulary_version",
)


def canonical_intent(intent: ResolvedIntent) -> dict[str, Any]:
    """The intent reduced to what identifies it, with governed sets ordered.

    ``metrics``, ``dimensions`` and ``sources`` are **sorted**: they are
    set-like, and a question naming two metrics in either order asks the same
    thing. Sorting is what makes two orderings of the same request share an
    identity rather than producing two.

    ``filters`` keep their **declared order and their exact values**. The order
    is part of the request `002` will receive, and the values are compared
    byte-sensitively downstream — normalising either would make the identity
    coarser than the request it describes.

    ``resolutions`` are deliberately absent. They record *how* the question was
    read — positions, match kinds — and two people reaching the same governed
    identifiers by different phrasings have asked the same question. Including
    them would make the identity a function of wording, which is what `FR-056`
    forbids.

    The period contributes its resolved boundaries and its governed expression,
    not the convention record: two identical ranges are the same period however
    they were named.
    """
    period = intent.period
    return {
        "metrics": sorted(intent.metrics),
        "dimensions": sorted(intent.dimensions),
        "sources": sorted(intent.sources),
        "filters": [
            {
                "dimension": governed.dimension,
                "operator": str(governed.operator),
                "values": list(governed.values),
            }
            for governed in intent.filters
        ],
        "period": None
        if period is None
        else {
            "start": period.start.isoformat(),
            "end": period.end.isoformat(),
            "expression": period.expression,
        },
        "comparison": None
        if intent.comparison is None
        else {
            "kind": intent.comparison.kind,
            "route": str(intent.comparison.route),
        },
    }


def derive_interpretation_identity(intent: ResolvedIntent) -> str:
    """The identity, as a hex digest.

    Every member comes from ``intent``, so an identity cannot be derived from
    inputs the intent did not carry — and the intent's own construction already
    refused anything ungoverned.

    ``as_of`` serialises as ``null`` when omitted. That is a *distinct* member
    value, not an absence: "no pin" and "pinned to 2026-07-01" are different
    interpretations, and dropping the key would make the first collide with a
    contract version that never had the field.
    """
    payload = {
        "intent": canonical_intent(intent),
        "reference_date": intent.reference_date.isoformat(),
        "as_of": None if intent.as_of is None else intent.as_of.isoformat(),
        "language": str(intent.language),
        "catalog_release": intent.catalog_release,
        "policy_version": intent.policy_version,
        "vocabulary_version": intent.vocabulary_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
