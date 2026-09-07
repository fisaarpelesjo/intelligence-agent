"""Caveat passthrough — T069 (FR-017; SC-016).

Every upstream caveat reaches the caller **unmodified**. Not summarised, not
merged, not downgraded, not reworded, and never dropped because it seemed
redundant.

The reason is narrower than "be faithful". A caveat is the catalog's statement
that the number is true only under a stated qualification — a segment boundary, a
partial period, a coverage limit. A caller who receives the figure without the
qualification receives a *different claim* from the one the catalog made, and has
no way to know it. Summarising three caveats into "some limitations apply" is
exactly that failure with a friendly face.

So this module copies. It has no filtering, ranking, deduplication or truncation,
and the round-trip test asserts the tuple that comes out is the tuple that went
in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.validation.decision import CatalogDecision, Limitation

__all__ = ["carry_limitations", "has_caveats", "merge_limitations"]


def carry_limitations(decision: CatalogDecision) -> tuple[Limitation, ...]:
    """The decision's limitations, byte-for-byte.

    Returns the same objects rather than reconstructed copies: a rebuild is a
    place where a field can be dropped, and there is nothing to gain from one.
    """
    return tuple(decision.limitations)


def has_caveats(decision: CatalogDecision) -> bool:
    """Whether the decision carries any qualification at all."""
    return bool(decision.limitations)


def merge_limitations(
    upstream: tuple[Limitation, ...],
    execution_layer: tuple[Limitation, ...],
) -> tuple[Limitation, ...]:
    """Append this feature's own limitations after the upstream ones.

    **Append, never interleave or replace.** Upstream limitations keep their
    order and their position at the front, so a reader can always tell which
    qualifications came from the catalog and which from execution. Nothing is
    de-duplicated across the two groups: an execution-layer caveat that happens
    to resemble an upstream one is still a separate statement about a separate
    thing, and collapsing them would drop one of them.
    """
    return (*upstream, *execution_layer)
