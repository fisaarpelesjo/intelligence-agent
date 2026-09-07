"""pt-BR synonym and fuzzy resolution — T044 (FR-014, FR-015, FR-057).

**This proves functional behaviour only. It does not prove SC-002.** SC-002 is a
measured criterion over at least 50 real business phrasings, and that corpus is
D-11, still open (T107). What is demonstrated here is that the governed seed
synonyms — including the informal and misspelled forms actually authored in the
catalog — resolve deterministically to the English canonical identifier. Quality
against phrasings nobody has collected yet is not claimed.

**Deterministic by construction**, because a resolver that reorders its own
results between runs cannot be governed:

* normalisation is a pure function — case-folded, accent-stripped, punctuation
  removed, whitespace collapsed;
* fuzzy matching uses a fixed ratio threshold, never a learned or tuned one;
* ties break on a stable key — score, then match kind, then identifier — so two
  equally good candidates always come back in the same order.

No language model participates. Matching is lookup and string distance over
governed content: names, pt-BR labels, descriptions, authored synonyms and
glossary terms (FR-015).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import IntEnum

from ..loader.load import LoadedCatalog

__all__ = [
    "FUZZY_THRESHOLD",
    "Candidate",
    "MatchKind",
    "SearchIndex",
    "build_index",
    "normalise",
    "resolve",
]

#: Minimum similarity for a fuzzy match. Fixed, not tuned: a threshold that
#: moves with the corpus makes yesterday's resolution unreproducible.
FUZZY_THRESHOLD = 0.82

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


class MatchKind(IntEnum):
    """How a term matched. Lower sorts first — exactness wins ties."""

    CANONICAL_NAME = 0
    SYNONYM = 1
    LABEL = 2
    GLOSSARY = 3
    DESCRIPTION = 4
    FUZZY = 5


def normalise(text: str) -> str:
    """Case-fold, strip accents, drop punctuation, collapse whitespace.

    Accent stripping is what makes ``retencao`` match ``retenção`` without an
    authored misspelling for every accented word. It is applied to both sides,
    so it never invents a match that the raw forms would not support after the
    same treatment.
    """
    decomposed = unicodedata.normalize("NFD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = _PUNCTUATION.sub(" ", stripped)
    return _WHITESPACE.sub(" ", cleaned).strip()


@dataclass(frozen=True, slots=True)
class Candidate:
    """One resolution candidate, with why it matched."""

    metric_id: str
    kind: MatchKind
    score: float
    matched_term: str

    @property
    def sort_key(self) -> tuple[float, int, str]:
        """Stable ordering: best score, then most exact kind, then identifier."""
        return (-self.score, int(self.kind), self.metric_id)


@dataclass(frozen=True, slots=True)
class SearchIndex:
    """Normalised term to metric, built once from a loaded catalog.

    ``terms`` maps a normalised term to every metric it can denote. A term
    claimed by two metrics stays ambiguous here and is resolved by nobody — that
    is FR-016's job, not this index's.
    """

    terms: Mapping[str, tuple[tuple[str, MatchKind], ...]]

    def exact(self, query: str) -> tuple[tuple[str, MatchKind], ...]:
        return self.terms.get(normalise(query), ())


def _index_entries(catalog: LoadedCatalog) -> Iterable[tuple[str, str, MatchKind]]:
    """``(term, metric_id, kind)`` for every governed searchable term."""
    for name, metric in catalog.metrics.items():
        yield name, name, MatchKind.CANONICAL_NAME
        for synonym in metric.synonyms:
            yield synonym.text, name, MatchKind.SYNONYM
        for version in metric.versions:
            yield version.content.label, name, MatchKind.LABEL
            yield version.content.description, name, MatchKind.DESCRIPTION

    # Glossary terms point at the metrics whose synonyms already claim them.
    # A glossary term that denotes no metric is a concept, not a metric, and
    # resolving it to one would be a guess.
    for term in catalog.glossary_terms.values():
        for synonym in (*term.synonyms,):
            for name, metric in catalog.metrics.items():
                if any(normalise(s.text) == normalise(synonym.text) for s in metric.synonyms):
                    yield term.content.term, name, MatchKind.GLOSSARY


def build_index(catalog: LoadedCatalog) -> SearchIndex:
    """Build the normalised term index. Pure; safe to cache per release."""
    collected: dict[str, dict[str, MatchKind]] = {}
    for raw, metric_id, kind in _index_entries(catalog):
        key = normalise(raw)
        if not key:
            continue
        bucket = collected.setdefault(key, {})
        # Keep the most exact kind when a term arrives by several routes.
        if metric_id not in bucket or kind < bucket[metric_id]:
            bucket[metric_id] = kind
    return SearchIndex(
        terms={
            key: tuple(sorted(((m, k) for m, k in bucket.items()), key=lambda p: (p[1], p[0])))
            for key, bucket in collected.items()
        }
    )


def resolve(query: str, index: SearchIndex) -> tuple[Candidate, ...]:
    """Every candidate for ``query``, best first.

    Exact matches short-circuit the fuzzy pass: if a term is authored, distance
    to some other term is irrelevant and admitting it would only add noise.
    An empty result means "no governed match", which the caller must report
    explicitly rather than paper over (FR-017).
    """
    normalised = normalise(query)
    if not normalised:
        return ()

    exact = index.exact(query)
    if exact:
        return tuple(
            sorted(
                (Candidate(m, k, 1.0, normalised) for m, k in exact),
                key=lambda c: c.sort_key,
            )
        )

    best: dict[str, Candidate] = {}
    for term, entries in index.terms.items():
        ratio = SequenceMatcher(None, normalised, term).ratio()
        if ratio < FUZZY_THRESHOLD:
            continue
        for metric_id, _kind in entries:
            current = best.get(metric_id)
            if current is None or ratio > current.score:
                best[metric_id] = Candidate(metric_id, MatchKind.FUZZY, ratio, term)

    return tuple(sorted(best.values(), key=lambda c: c.sort_key))
