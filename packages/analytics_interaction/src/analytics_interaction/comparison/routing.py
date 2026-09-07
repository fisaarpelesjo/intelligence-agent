"""Comparison routing — T095 (FR-064; SC-049).

**Structural, derived from `002`'s own field set, never a table.**

```
sides differ only in elements AnalyticsQuery already carries,
and share ONE date range
    → single_request     — 002's existing path; this feature adds nothing

sides require TWO DISJOINT date ranges
    → two_execution      — catalog verdict, then one governed request per side

anything else
    → deny by default    — absence of a route is never permission
```

**Why a predicate and not a governed routing table.** A table can disagree with
``extra="forbid"``, and the disagreement would be silent: a shape the table
routed one way would be rejected by the request contract downstream, after this
layer had already told the caller their question was fine. The predicate is
derived from ``AnalyticsQuery``'s declared fields, so it **cannot drift out of
agreement with the contract it derives from** — and `T096` asserts the derivation
rather than trusting it.

**Cross-source, cross-store, cross-platform and dimension-value comparisons take
the single-request route.** `002`'s ``sources`` field takes a list, its
``filters`` express dimension values, and the catalog evaluates their
comparability in that one evaluation. Re-routing them through two executions
would duplicate machinery `002` owns and **double the bill** (`FR-064`,
`SC-049`). Comparing two groups is not by itself a reason to execute twice.

**Only two disjoint date ranges force the second route**, because that is the one
thing one ``AnalyticsQuery`` cannot express: ``date_range`` is a single range and
`BD-1` removed ``comparison`` from the request contract deliberately.

An ambiguous or unrecognised shape **denies**. It is never silently assigned the
cheaper route, and never the more expensive one either.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from analytics_query.contracts.request import AnalyticsQuery

from ..contracts._base import ContractViolation
from ..contracts.comparison import ComparisonRoute
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "SINGLE_REQUEST_FIELDS",
    "ComparisonShape",
    "classify_route",
    "ranges_are_disjoint",
]

#: The fields a single request can already vary between the two sides. Derived
#: from ``AnalyticsQuery``'s declared fields minus ``date_range``, so a field
#: added upstream joins this set automatically and one removed leaves it.
SINGLE_REQUEST_FIELDS: frozenset[str] = frozenset(AnalyticsQuery.model_fields) - {"date_range"}


@dataclass(frozen=True, slots=True)
class ComparisonShape:
    """What the question asked for, before a route is chosen.

    Deliberately not a route: the shape is the *observation* and the route is
    the *decision*, and keeping them separate is what lets `T096` assert every
    shape maps somewhere without the shape already knowing where.

    ``differing_fields`` names the request fields the two sides differ in.
    ``baseline_range`` is present only when the question named a second period.
    """

    differing_fields: frozenset[str]
    primary_range: tuple[date, date]
    baseline_range: tuple[date, date] | None = None


def ranges_are_disjoint(left: tuple[date, date], right: tuple[date, date]) -> bool:
    """Whether two closed ranges share no day.

    Inclusive on both ends, matching `001`'s canonical period. Touching ranges —
    one ending the day the other starts — **overlap**, because both contain that
    day and a comparison across them would count it twice.
    """
    return left[1] < right[0] or right[1] < left[0]


def classify_route(shape: ComparisonShape) -> ComparisonRoute:
    """The governed route, or refuse.

    Four cases, and the ordering matters:

    1. a field the request contract does not carry — **deny**. A comparison over
       something `002` cannot express is not a comparison this feature can route;
    2. no second range — **single request**. Whatever the sides differ in, one
       request expresses it;
    3. a second range that overlaps the first — **deny**. Two ranges sharing a day
       are not two disjoint periods, and executing them would double-count it;
    4. two disjoint ranges — **two execution**.

    Deterministic: the same shape always yields the same route, and nothing here
    reads a clock, a policy or a preference.
    """
    unsupported = shape.differing_fields - SINGLE_REQUEST_FIELDS
    if unsupported:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_NOT_ROUTABLE,
            "the comparison varies elements the governed request contract does not carry; "
            "the absence of a route is never permission",
        )

    if shape.baseline_range is None:
        return ComparisonRoute.SINGLE_REQUEST

    if not ranges_are_disjoint(shape.primary_range, shape.baseline_range):
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_NOT_ROUTABLE,
            "the two periods overlap; a comparison across them would count the shared days twice",
        )

    return ComparisonRoute.TWO_EXECUTION
