"""Normalised query identity — T027 (FR-033; SC-014).

Two requests that ask the same thing must share one identity however they were
written, so the canonical form sorts every collection, case-folds identifiers and
serialises deterministically before hashing.

**The principal is excluded, deliberately.** Identity must never become an
authorization artifact (`FR-035`): every execution is authorized on the
requesting principal's own tags. Including the principal would also hide the fact
that the same query was asked twice, which is the thing the ledger exists to see.
The timestamp is excluded for the same reason — a per-request identity
de-duplicates nothing.

**Identity alone is not an execution key.** Precisely because it is
principal-independent, two differently-authorized callers derive the same
identity. An execution keyed on it alone would let the second attach to the
first's execution and inherit its status, cost, warehouse job, audit-recovery
path and result. The execution key is the pair
`(QueryIdentity, AuthorizationContextFingerprint)`; the second half arrives with
the ledger in Phase 8 (`FR-078`, execution-contract §7.0). Nothing in this module
acquires, attaches to or observes an execution.

**Normalization is scoped, and the scope is load-bearing.** Case and whitespace
folding applies to governed **identifiers** and to structural formatting — key
order, separators, and collection order for operators whose value list is a set.
It is never applied to filter values or to the policy/catalog pins. Filter values
are data the warehouse compares byte- and case-sensitively; folding them would
make identity coarser than the query it identifies, so single-flight would
resolve two different questions to one answer. `ß`/`ss` and `İ`/`i` are the cases
that make this concrete — `str.casefold` collapses both.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..contracts.request import AnalyticsQuery

__all__ = ["QueryIdentity", "canonical_form", "derive_identity"]


class QueryIdentity:
    """A fingerprint and the canonical form it was taken over."""

    __slots__ = ("canonical_form", "fingerprint")

    def __init__(self, fingerprint: str, canonical: str) -> None:
        self.fingerprint = fingerprint
        self.canonical_form = canonical

    def __eq__(self, other: object) -> bool:
        return isinstance(other, QueryIdentity) and other.fingerprint == self.fingerprint

    def __hash__(self) -> int:
        return hash(self.fingerprint)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"QueryIdentity({self.fingerprint[:12]}...)"


def canonical_form(
    query: AnalyticsQuery,
    *,
    policy_version: str,
    catalog_release_id: str,
) -> str:
    """Deterministic JSON over the request's semantic content.

    Sorted keys, sorted collections, case-folded identifiers, ISO dates. Two
    requests differing only in whitespace, ordering or letter case produce the
    same string — which is what makes `SC-014` testable rather than aspirational.
    """
    payload: dict[str, Any] = {
        "metrics": sorted(m.casefold() for m in query.metrics),
        "dimensions": sorted(d.casefold() for d in query.dimensions),
        "sources": sorted(s.casefold() for s in query.sources),
        "filters": sorted(
            (
                [
                    f.dimension.casefold(),
                    f.operator.value,
                    sorted(f.values),
                ]
                for f in query.filters
            ),
            key=repr,
        ),
        "date_range": [query.date_range.start.isoformat(), query.date_range.end.isoformat()],
        "as_of": query.as_of.isoformat() if query.as_of else None,
        "policy_version": policy_version,
        "catalog_release_id": catalog_release_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def derive_identity(
    query: AnalyticsQuery,
    *,
    policy_version: str,
    catalog_release_id: str,
) -> QueryIdentity:
    """SHA-256 over the canonical form. Excludes the principal and the clock."""
    canonical = canonical_form(
        query, policy_version=policy_version, catalog_release_id=catalog_release_id
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return QueryIdentity(digest, canonical)
