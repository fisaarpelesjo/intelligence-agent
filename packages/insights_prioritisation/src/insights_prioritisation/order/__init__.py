"""How placed findings become orderings, and what refuses to let them cross.

Nothing here ranks. Ranking needs a composed score, and how the declared components
compose is `D-A` — the owner's. These modules take findings that are **already in rank
order** and decide what may be published as one ordering and what may not.
"""

from __future__ import annotations

from .ties import group_ties, tie_key
from .within_class import one_ordering_per_class, single_normalised_ordering

__all__ = [
    "group_ties",
    "one_ordering_per_class",
    "single_normalised_ordering",
    "tie_key",
]
