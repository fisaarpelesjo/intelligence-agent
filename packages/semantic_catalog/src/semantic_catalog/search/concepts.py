"""Discovery that answers **which kind of governed concept** a term names — ADR 0029.

```
build_concept_index(catalog)            -> ConceptIndex
identify(query, index, bundle, access)  -> tuple[ConceptMatch, ...]
```

`resolve` answers one question: does this term name a governed **metric**? A caller needing to know
whether a term names a dimension had no surface to ask, so downstream features either guessed or
routed every question to clarification. ADR 0028 recorded the gap and ADR 0029 authorized closing it
here, where the vocabulary lives.

## Every answer is gated, and absence denies

A dimension is disclosed only when its own `access` tag authorises the asking principal. That rule
has not changed; what it now answers has.

**Corrected 2026-08-19.** This paragraph used to say that no authored dimension carried a tag and
that therefore this surface reported no dimension. Both halves were true when written and both are
now false: the owner authored `access: standard` on the six authored axes, under a corrected
registry definition naming semantic dimensions alongside product metrics, so this surface reports
each of them to a principal the registry admits.

`Dimension.access` stays optional, and the reason changed rather than disappeared: absence has to
remain a case the gate **denies**, because that is what keeps deny-by-default observable rather than
structural. An axis authored without a tag is still refused, for the same reason an absent registry
denies in :func:`~semantic_catalog.search.api.authorize`.

A refusal is **indistinguishable from a non-match**: both return nothing. Distinguishing them would
let a caller enumerate the catalog by watching which terms refuse and which are simply unknown,
which is the disclosure `get_metric` already closed for metrics.

## What this module does not do

* It does not decide what a span *means* in a sentence. It answers "does this term name a governed
  concept, and of which kind" — the caller decides what to do with that.
* It reports **no** period and **no** filter kind. No authored period vocabulary exists; ADR
  0029 says so explicitly and does not authorize inventing one. A `ConceptKind` member for a kind
  nothing can populate would be a promise the catalog cannot keep.
* It authors no tag, no default and no fallback.

## Additive, as ADR 0028 required

A new module. `resolve`, `build_index`, `SearchIndex` and `CatalogApi` are untouched: this reuses
`normalise` and `MatchKind` and adds a parallel index rather than widening theirs. A metric's
disclosure still goes through the same `authorize` call it always did.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .api import AccessContext, authorize
from .resolve import MatchKind, normalise

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..loader.bundle import Bundle
    from ..loader.load import LoadedCatalog

__all__ = [
    "ConceptIndex",
    "ConceptKind",
    "ConceptMatch",
    "build_concept_index",
    "identify",
]


class ConceptKind(StrEnum):
    """The kinds of governed concept this catalog can answer for.

    Two members, because two kinds are authored. A `PERIOD` member would name something no authored
    content populates, and a caller reading the enum would reasonably expect the surface to answer
    for it — which is how an absent vocabulary turns into a silent gap downstream.
    """

    METRIC = "metric"
    DIMENSION = "dimension"


@dataclass(frozen=True, slots=True)
class ConceptMatch:
    """One governed concept a term names, with the kind and how the term matched.

    ``concept_id`` rather than ``metric_id``: the field name has to be true for both kinds, and a
    field called ``metric_id`` holding a dimension is a lie in a field name. That naming was the
    reason the ADR 0028 survey ruled out deriving this from `Candidate` at all.
    """

    concept_id: str
    kind: ConceptKind
    match: MatchKind
    matched_term: str

    def sort_key(self) -> tuple[int, str, str]:
        """Exactness first, then kind, then identifier. Total and stable.

        `MatchKind`'s own ordering already means "lower sorts first — exactness wins ties", so it is
        reused rather than re-stated. Ties break on kind and identifier so two runs over one catalog
        produce byte-identical output.
        """
        return (int(self.match), self.kind.value, self.concept_id)


@dataclass(frozen=True, slots=True)
class ConceptIndex:
    """Normalised term to the concepts it names, with each concept's kind.

    Separate from `SearchIndex` rather than an extension of it: that index maps a term to metric ids
    and its callers rely on that, and widening its value type would change what every existing
    caller receives.
    """

    terms: Mapping[str, tuple[ConceptMatch, ...]]

    def exact(self, query: str) -> tuple[ConceptMatch, ...]:
        """Every concept whose authored term equals ``query`` after normalisation."""
        return self.terms.get(normalise(query), ())


def _metric_entries(catalog: LoadedCatalog) -> Iterable[tuple[str, ConceptMatch]]:
    for name, metric in catalog.metrics.items():
        yield name, ConceptMatch(name, ConceptKind.METRIC, MatchKind.CANONICAL_NAME, name)
        for synonym in metric.synonyms:
            yield (
                synonym.text,
                ConceptMatch(name, ConceptKind.METRIC, MatchKind.SYNONYM, synonym.text),
            )
        for version in metric.versions:
            yield (
                version.content.label,
                ConceptMatch(name, ConceptKind.METRIC, MatchKind.LABEL, version.content.label),
            )


def _dimension_entries(catalog: LoadedCatalog) -> Iterable[tuple[str, ConceptMatch]]:
    """The same searchable fields metrics are indexed from, for dimensions.

    Canonical id, synonyms and the pt-BR label. The **description** is deliberately not indexed
    here: for metrics it is, and it produces low-precision matches that only make sense when the
    answer is already known to be a metric. Adding it for dimensions would mean a sentence
    mentioning a dimension's description text starts naming that dimension.
    """
    for identifier, dimension in catalog.dimensions.items():
        yield (
            identifier,
            ConceptMatch(identifier, ConceptKind.DIMENSION, MatchKind.CANONICAL_NAME, identifier),
        )
        for synonym in dimension.synonyms:
            yield (
                synonym.text,
                ConceptMatch(identifier, ConceptKind.DIMENSION, MatchKind.SYNONYM, synonym.text),
            )
        yield (
            dimension.content.label,
            ConceptMatch(
                identifier,
                ConceptKind.DIMENSION,
                MatchKind.LABEL,
                dimension.content.label,
            ),
        )


def build_concept_index(catalog: LoadedCatalog) -> ConceptIndex:
    """Build the concept index. Pure; safe to cache per release.

    Gating happens at :func:`identify`, not here. An index that omitted denied concepts would have
    to be rebuilt per principal, and a cached one would then leak whichever principal built it
    first.
    """
    collected: dict[str, dict[tuple[str, ConceptKind], ConceptMatch]] = {}
    for raw, match in (*_metric_entries(catalog), *_dimension_entries(catalog)):
        key = normalise(raw)
        if not key:
            continue
        bucket = collected.setdefault(key, {})
        identity = (match.concept_id, match.kind)
        previous = bucket.get(identity)
        # Keep the most exact match when one concept is reachable by several routes.
        if previous is None or int(match.match) < int(previous.match):
            bucket[identity] = match
    return ConceptIndex(
        terms={
            key: tuple(sorted(bucket.values(), key=ConceptMatch.sort_key))
            for key, bucket in collected.items()
        }
    )


def _metric_is_disclosable(bundle: Bundle, concept_id: str, access: AccessContext) -> bool:
    """The same three conditions `CatalogApi` applies, in the same order.

    A projection must exist, the metric must exist, and its tag must authorise. Re-deriving this
    rather than calling `CatalogApi._visible` keeps the module additive — ADR 0028's limit — and the
    conditions are asserted equal to `get_metric`'s answer by this package's own contract test.
    """
    if bundle.public.get(concept_id) is None:
        return False
    metric = bundle.internal.metrics.get(concept_id)
    if metric is None:
        return False
    return authorize(metric.access, bundle.internal.access_tags, access) is None


def _dimension_is_disclosable(bundle: Bundle, concept_id: str, access: AccessContext) -> bool:
    """Deny unless the dimension carries a tag **and** that tag authorises.

    Absence denies (ADR 0029), and both conditions are load-bearing: an unregistered tag is refused
    by `authorize` exactly as an absent one is, so a typo in the authored YAML denies rather than
    discloses.

    **Corrected 2026-08-19.** This docstring used to describe the return value as ``False`` for
    every dimension in the shipped catalog, because no axis carried a tag. Six now do, so it returns
    ``True`` for each of them to a principal the registry admits — and the sentence describing a
    function's own return value is the worst place for a claim to go stale, which is why this
    correction was scoped in with the change that made it necessary rather than left for later.
    """
    dimension = bundle.internal.dimensions.get(concept_id)
    if dimension is None or dimension.access is None:
        return False
    return authorize(dimension.access, bundle.internal.access_tags, access) is None


def identify(
    query: str,
    index: ConceptIndex,
    *,
    bundle: Bundle,
    access: AccessContext,
) -> tuple[ConceptMatch, ...]:
    """Every governed concept ``query`` names **and** the asking principal may be told about.

    Exact matches only. There is no fuzzy pass here: `resolve` has one for metrics, where a caller
    has already decided the term should name a metric and a near miss is a useful suggestion. Asking
    "what kind of thing is this word" is a different question, and a fuzzy answer to it would report
    a concept kind the sender never wrote.

    Returns an empty tuple for a non-match **and** for a denial, which is what keeps a refusal from
    disclosing that something exists.
    """
    disclosable = {
        ConceptKind.METRIC: _metric_is_disclosable,
        ConceptKind.DIMENSION: _dimension_is_disclosable,
    }
    return tuple(
        match
        for match in index.exact(query)
        if disclosable[match.kind](bundle, match.concept_id, access)
    )
