"""`001`'s three-way outcome, carried through — T073 (FR-007, FR-008; SC-001).

`001` deliberately built a **closed union** with three shapes, and the
distinction between them is the requirement:

| Outcome | Meaning | What the user should do next |
|---|---|---|
| ``Resolved`` | Exactly one governed metric matched | Ask the question |
| ``Ambiguous`` | Several matched, all authorised | Choose between them |
| ``NotGoverned`` | Nothing matched, **or nothing the caller may see** | Something else entirely |

And within a resolution, `001` separates ``MetricView`` from ``PendingStub``:
published and pending are different answers with different next steps. One sends
the user to build their own number; the other sends them to the metric's owner.

**This module carries all of that through unchanged.** It re-derives nothing,
collapses nothing and adds no fourth shape. The first consumer to flatten the
union treats "pending" as "missing", which is the failure `001`'s `R-8` records —
and a feature whose whole job is interpretation is exactly where that flattening
would be most tempting and most damaging.

**A pending metric's draft definition is never exposed** (`FR-008`). `001`'s
``PendingStub`` is the projection that withholds it, and it is carried as-is:
this module reads the stub's *presence*, never its contents.

**Unauthorised and non-existent are the same answer.** `001`'s ``CatalogApi``
filters by access *before* deciding the shape, so an ambiguity the caller may not
see never surfaces as an ambiguity, and a metric they may not see returns
``NotGoverned`` identical to one that does not exist. That symmetry is `FR-050`'s
and it is `001`'s to provide — this module must not add anything that could
distinguish them, which is why it exposes no count, no timing and no separate
"filtered" state.
"""

from __future__ import annotations

from enum import StrEnum

from semantic_catalog.loader.projection import MetricView, PendingStub
from semantic_catalog.search.outcomes import Ambiguous, NotGoverned, Resolved

__all__ = [
    "LifecycleStanding",
    "SlotOutcome",
    "TermOutcome",
    "classify",
    "standing_of",
]

#: `001`'s union, named here so callers depend on the alias rather than
#: re-importing the three shapes and risking a fourth being added locally.
SlotOutcome = Resolved | Ambiguous | NotGoverned


class TermOutcome(StrEnum):
    """The shape of a slot outcome, as a value a contract can carry.

    A parallel vocabulary rather than a replacement: the union is still the
    thing that travels, and this is what an audit event or a clarification
    records about it. Deriving it from the union means the two cannot disagree.
    """

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_GOVERNED = "not_governed"


class LifecycleStanding(StrEnum):
    """Published or pending. **Not** a third resolution shape.

    Kept separate from ``TermOutcome`` because they answer different questions:
    one is *did the term resolve*, the other is *what standing does what it
    resolved to have*. Folding them into one five-valued enum would make
    "pending" look like a failure to resolve, which is the collapse `FR-008`
    forbids.
    """

    PUBLISHED = "published"
    PENDING = "pending"


def classify(outcome: SlotOutcome) -> TermOutcome:
    """Which of `001`'s three shapes this is.

    Exhaustive by construction over a closed union — there is no ``else`` branch
    and no default, so a fourth shape upstream would fail here rather than being
    silently classified as one of the three.
    """
    if isinstance(outcome, Resolved):
        return TermOutcome.RESOLVED
    if isinstance(outcome, Ambiguous):
        return TermOutcome.AMBIGUOUS
    return TermOutcome.NOT_GOVERNED


def standing_of(projection: MetricView | PendingStub) -> LifecycleStanding:
    """Whether a resolved metric is published or pending.

    Reads the projection's **type**, never its contents. A pending metric's
    draft definition stays inside `001`'s stub, and nothing here opens it.
    """
    return (
        LifecycleStanding.PENDING
        if isinstance(projection, PendingStub)
        else LifecycleStanding.PUBLISHED
    )
