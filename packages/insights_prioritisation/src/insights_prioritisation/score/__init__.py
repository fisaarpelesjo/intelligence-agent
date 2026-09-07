"""How an ordering is built, and what refuses to build one.

Every module here works over **declared** components. `D-A` was answered by the owner on
2026-08-27 — **magnitude and reach**, compared term by term with magnitude first, each
multiplied by a confidence factor that is `completeness_ratio` and refuses when it was
never measured.

Nothing here chooses a component, and both readers still answer `None` today: no mean
per metric travels the governed seams and `005` produces no investigation. Every finding
is therefore not prioritisable, with each component naming its own absence.
"""

from __future__ import annotations

from .components import (
    DECLARED_COMPONENTS,
    ComponentReader,
    MagnitudeZScore,
    MetricStatistics,
    ReachOfInvestigation,
    read_component,
    read_components,
)
from .compose import absent_components, may_compose
from .confidence import CONFIDENCE_FACTOR_NAME, confidence_of, weigh
from .rank import DECLARED_ORDER, rank_findings, rank_key

__all__ = [
    "CONFIDENCE_FACTOR_NAME",
    "DECLARED_COMPONENTS",
    "DECLARED_ORDER",
    "ComponentReader",
    "MagnitudeZScore",
    "MetricStatistics",
    "ReachOfInvestigation",
    "absent_components",
    "confidence_of",
    "may_compose",
    "rank_findings",
    "rank_key",
    "read_component",
    "read_components",
    "weigh",
]
