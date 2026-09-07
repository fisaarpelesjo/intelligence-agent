"""A counted, access-filtered discovery surface — Phase 6 fixtures.

TEST-ONLY. Reaches no catalog, no warehouse and no model, and is **never**
evidence for any external record. In particular it is not `D-11`: a corpus this
file authored, scored against a resolver this file also shaped, would measure
nothing.

Two things it must model faithfully, because the tests depend on them:

**Access filtering happens before the shape is decided.** `001`'s ``CatalogApi``
filters candidates by access and *then* decides whether the outcome is resolved,
ambiguous or not-governed. So an ambiguity the caller may not see never surfaces
as an ambiguity, and a metric they may not see is ``NotGoverned`` — identical to
one that does not exist. A fixture that filtered afterwards would let a test pass
that the real surface would fail.

**Every read is counted.** The zero-call assertions need a surface that would
have registered a call, not one that could not be called.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from semantic_catalog.search.outcomes import Ambiguous, NotGoverned, Resolved
from semantic_catalog.search.resolve import Candidate, MatchKind

__all__ = [
    "FIXTURE_DIMENSION_VALUES",
    "FIXTURE_SOURCE_IDS",
    "FixtureCatalog",
    "FixtureTerm",
]

#: The six governed sources `001` declares. Transcribed for the role tests;
#: never used as a resolution source of truth.
FIXTURE_SOURCE_IDS: frozenset[str] = frozenset(
    {
        "google_play",
        "apple_app_store",
        "galaxy_store",
        "android_app",
        "ios_app",
        "website",
    }
)

#: ``google_play`` is deliberately in both sets — it is the real collision the
#: role disambiguation exists for.
FIXTURE_DIMENSION_VALUES: frozenset[str] = frozenset({"google_play", "apple_app_store", "android"})


@dataclass(frozen=True, slots=True)
class FixtureTerm:
    """One authored term: what it matches, how, and who may see it."""

    surface: str
    metric_id: str
    kind: MatchKind
    score: float
    #: Authorization scopes permitted to see this metric. Empty means nobody.
    visible_to: frozenset[str]

    def candidate(self) -> Candidate:
        return Candidate(
            metric_id=self.metric_id,
            kind=self.kind,
            score=self.score,
            matched_term=self.surface,
        )


@dataclass
class FixtureCatalog:
    """Stands in for `001`'s ``CatalogApi``, with the same filtering order.

    ``calls`` records every ``resolve`` — a surface that cannot be observed
    cannot support a counted zero-call assertion.
    """

    terms: tuple[FixtureTerm, ...] = ()
    calls: list[str] = field(default_factory=list[str])

    def resolve(self, query: str, *, access: object) -> Resolved | Ambiguous | NotGoverned:
        """`001`'s three-way outcome, access-filtered **before** the shape.

        ``access`` is `001`'s ``AccessContext``; only its authorization scope is
        consulted here, which is enough to model the filtering the tests need.
        """
        self.calls.append(query)
        scope = getattr(access, "authorization_scope", "")

        matched = [term for term in self.terms if term.surface == query]
        visible = [term for term in matched if scope in term.visible_to]

        if not visible:
            return NotGoverned(query=query)

        candidates = tuple(sorted((term.candidate() for term in visible), key=lambda c: c.sort_key))
        if len(candidates) == 1:
            return Resolved(query=query, candidate=candidates[0])
        return Ambiguous(query=query, candidates=candidates)
