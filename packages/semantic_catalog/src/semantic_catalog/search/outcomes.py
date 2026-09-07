"""Search outcomes — T045 (FR-016, FR-017).

Three response shapes, and the distinction between them is the requirement:

:class:`Resolved`
    Exactly one governed metric matched.

:class:`Ambiguous`
    Several matched. All candidates are returned with what distinguishes them.
    **Never a silent single resolution** (FR-016) — picking the top scorer would
    answer a question the user did not ask, and they would have no way to know.

:class:`NotGoverned`
    Nothing matched. Said explicitly (FR-017), because "no governed metric" and
    "a metric that is pending" are different answers with different next steps:
    one sends the user to build their own number, the other sends them to the
    owner.

A near-tie is treated as ambiguity rather than resolved-with-low-confidence.
Confidence that only the resolver can see is not a thing the reader can act on.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..loader.projection import MetricView, PendingStub
from .resolve import Candidate, SearchIndex, resolve

__all__ = [
    "AMBIGUITY_MARGIN",
    "Ambiguous",
    "NotGoverned",
    "Resolved",
    "SearchHit",
    "SearchOutcome",
    "resolve_outcome",
]

#: Two candidates whose scores differ by less than this are ambiguous. A margin
#: rather than strict equality: 0.94 versus 0.93 is not a decision, it is noise.
AMBIGUITY_MARGIN = 0.05


@dataclass(frozen=True, slots=True)
class Resolved:
    """Exactly one governed metric matched."""

    query: str
    candidate: Candidate

    @property
    def metric_id(self) -> str:
        return self.candidate.metric_id


@dataclass(frozen=True, slots=True)
class Ambiguous:
    """Several matched. Every candidate is returned, never one of them."""

    query: str
    candidates: tuple[Candidate, ...]

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(c.metric_id for c in self.candidates)


@dataclass(frozen=True, slots=True)
class NotGoverned:
    """Nothing matched. An explicit non-answer, not an empty list."""

    query: str


SearchOutcome = Resolved | Ambiguous | NotGoverned


def resolve_outcome(query: str, index: SearchIndex) -> SearchOutcome:
    """Classify a query into exactly one of the three shapes."""
    candidates = resolve(query, index)
    if not candidates:
        return NotGoverned(query=query)
    if len(candidates) == 1:
        return Resolved(query=query, candidate=candidates[0])

    best = candidates[0]
    contenders = tuple(c for c in candidates if best.score - c.score < AMBIGUITY_MARGIN)
    if len(contenders) == 1:
        return Resolved(query=query, candidate=best)
    return Ambiguous(query=query, candidates=contenders)


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One search result: a published view or a pending stub, never a raw model.

    The union is the point — a published metric and a pending stub are different
    answers, and flattening them into one shape would lose the distinction the
    caller needs to act on (R-8).
    """

    metric_id: str
    projection: MetricView | PendingStub
    candidate: Candidate

    @property
    def is_pending(self) -> bool:
        return isinstance(self.projection, PendingStub)
