"""Governed comparison — T039 (FR-064, FR-065; SC-036).

**``GovernedComparison`` has no partial state.** Construction takes exactly two
sides; a one-sided value is not representable, so "return the side that worked"
is not a mistake somebody can make — it is a thing the type system will not
express (`FR-067`).

That matters more than it first reads. A difference computed across a hole is a
number nobody can interpret, and presenting one side of a refused comparison
would be exactly the confidently-wrong figure `001`'s `BO-4` exists to prevent.
The deliberate asymmetry with the single-metric case is stated in
`contracts/comparison-contract.md` §5.2: a lone answer carrying suppressed cells
is a permitted ``ALLOW_WITH_CAVEAT`` in `002`, while the same suppression inside
a comparison refuses the whole thing.

**Routing is structural, not configured.** The predicate is derived from
``AnalyticsQuery``'s own field set, so it cannot drift out of agreement with the
contract it derives from. A governed routing table was considered and rejected
for exactly that reason: a table can disagree with ``extra="forbid"``, and the
disagreement would be silent. Deriving the route is Phase 9 (`T095`+); this
module declares the closed set of routes it may produce.

**Exact decimal, no float anywhere.** ``DerivedFigure.value`` is a ``Decimal``. A
float difference is not reproducible in its last digits across platforms, and
`SC-005` requires identical output for identical input.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from analytics_query.contracts.comparable_window import ComparableWindow
from analytics_query.contracts.request import AnalyticsQuery
from analytics_query.contracts.result import AnalyticsResult
from analytics_query.contracts.result_provenance import ResultProvenance
from pydantic import Field, model_validator
from semantic_catalog.validation.decision import CatalogDecision

from ._base import InteractionModel
from .answer import CaveatSet
from .intent import ResolvedIntent, ResolvedPeriod

__all__ = [
    "ComparisonIntent",
    "ComparisonRoute",
    "DerivedFigure",
    "GovernedComparison",
    "SideResult",
]


class ComparisonRoute(StrEnum):
    """The two governed routes. Anything else denies by default.

    ``SINGLE_REQUEST`` — the sides differ only in elements ``AnalyticsQuery``
    already carries and share one date range. This is `002`'s existing path and
    this feature adds nothing to it. **Cross-source comparisons take this
    route**: `002`'s ``sources`` field takes a list and the catalog already
    evaluates their comparability in that one evaluation, so re-routing them
    through two executions would duplicate machinery `002` owns and double the
    bill (`FR-064`, `SC-049`).

    ``TWO_EXECUTION`` — the sides require two disjoint date ranges. One catalog
    verdict over the comparison *as presented*, then one governed request per
    side.

    There is deliberately no third member for "unroutable". Absence of a route is
    never permission, so it is a refusal (``COMPARISON_NOT_ROUTABLE``) rather
    than a state a comparison can be in.
    """

    SINGLE_REQUEST = "single_request"
    TWO_EXECUTION = "two_execution"


# The closed set of enumerated material-mismatch conditions (`FR-068`) is
# **T108's**, alongside the refusal matrix that evaluates them. Declaring the
# enum here without its matrix would put half of one task in another phase.


class ComparisonIntent(InteractionModel):
    """What comparison the question asked for, and how it will be served.

    ``kind`` names a `D-18` formula. The formula set ships empty, so every
    comparison refuses today — designed, not missing.

    ``route`` is **derived, never declared by the caller**. It appears on the
    resolved intent rather than the intake for that reason: a caller who could
    choose the route could choose the cheaper one for a comparison that needs the
    governed verdict.
    """

    kind: str = Field(min_length=1)
    route: ComparisonRoute
    baseline_period: ResolvedPeriod | None = None

    @model_validator(mode="after")
    def _a_baseline_belongs_to_the_two_execution_route(self) -> ComparisonIntent:
        """A second period is what makes the route two-execution in the first place.

        A single-request comparison carrying a baseline period would be claiming
        two date ranges on a route defined by sharing one — the routing predicate
        and the intent would be describing different comparisons.
        """
        if self.route is ComparisonRoute.TWO_EXECUTION and self.baseline_period is None:
            raise ValueError("the two-execution route requires a baseline period")
        if self.route is ComparisonRoute.SINGLE_REQUEST and self.baseline_period is not None:
            raise ValueError("a single-request comparison shares one date range")
        return self


class SideResult(InteractionModel):
    """One executed side: what was asked, what came back, and where it came from.

    Every field is an inherited `002` type carried whole. ``result`` values are
    **untouched** and ``provenance`` is **never merged** with the other side's —
    both are `FR-072` and `FR-033`, and both are preserved by carrying rather
    than by a rule forbidding alteration.
    """

    request: AnalyticsQuery
    result: AnalyticsResult
    provenance: ResultProvenance


class DerivedFigure(InteractionModel):
    """The computed difference. Exact decimal, marked derived.

    ``unit`` comes from the formula's `D-18` unit rule; this feature never
    converts between units, and two sides with differing declared units are a
    material mismatch that refuses.

    ``basis`` is the verdict's chosen-because, carried rather than recomputed.
    """

    value: Decimal
    unit: str = Field(min_length=1)
    derived_from: tuple[str, str]
    basis: str = Field(min_length=1)


class GovernedComparison(InteractionModel):
    """A comparison that passed every gate. **Two sides or nothing.**

    ``verdict`` covers the comparison **as presented** — for the two-execution
    route, one evaluation submitted to `001` with both sides, the kind and the
    baseline range expressed, *before* anything executes. Two independent
    single-side evaluations never constitute a comparison verdict (`FR-065`).

    ``window`` is taken from the verdict and **never recomputed, widened,
    narrowed, shifted or substituted** (`FR-066`). It is a field rather than a
    method for that reason: there is no recomputation path to disable because
    there is no computation.
    """

    verdict: CatalogDecision
    window: ComparableWindow
    formula: str = Field(min_length=1)
    sides: tuple[SideResult, SideResult]
    difference: DerivedFigure
    caveats: CaveatSet

    @model_validator(mode="after")
    def _the_difference_names_both_sides(self) -> GovernedComparison:
        """Two operands, both recorded, so the figure is traceable to its sides."""
        if len(set(self.difference.derived_from)) != 2:
            raise ValueError("a derived difference must name two distinct factual claims")
        return self


# ``ResolvedIntent.comparison`` forward-references ``ComparisonIntent``, which
# needs ``ResolvedPeriod`` from `intent.py`. The cycle is real in the data model,
# so it is closed here — the first point at which both halves exist.
# `contracts/__init__.py` imports this module, so no import order can observe a
# half-built ``ResolvedIntent``.
ResolvedIntent.model_rebuild()
