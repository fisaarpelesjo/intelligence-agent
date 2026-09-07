"""Routing totality — T096 (FR-064; SC-049).

    Every shape maps to one route or to deny-by-default.
    Evidence: an unmapped shape denies rather than defaulting. — `tasks.md` T096

**Totality is the claim, and it is checked by exhaustion, not by example.** The
suite enumerates the full cross product of the shapes the predicate can be handed
— every subset of the differing-field set, including the empty one and one
containing a field the request contract does not carry, against no baseline, an
overlapping baseline, a touching baseline and a disjoint one — and asserts that
each lands in exactly one of two places: a ``ComparisonRoute`` member, or a
``COMPARISON_NOT_ROUTABLE`` refusal. Nothing returns ``None``, nothing raises
something else, nothing falls through.

**Deny-by-default is the half that matters.** A routing predicate that returned
the cheap route for a shape it did not recognise would be free, silent and
wrong — the caller would be billed one execution for a comparison that needed a
governed verdict, and would be told nothing. So the unroutable cases assert the
*refusal*, not merely "not two-execution".

**The derivation is asserted, not trusted.** `T095`'s whole argument is that the
supported-field set comes from ``AnalyticsQuery`` rather than from a table
somebody maintains. A test that hard-coded the six field names would recreate
exactly the drift the derivation exists to prevent, so the assertion is against
``AnalyticsQuery.model_fields`` itself.
"""

from __future__ import annotations

from datetime import date
from itertools import combinations

import pytest
from analytics_query.contracts.request import AnalyticsQuery

from analytics_interaction.comparison.routing import (
    SINGLE_REQUEST_FIELDS,
    ComparisonShape,
    classify_route,
    ranges_are_disjoint,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.comparison import ComparisonRoute
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

pytestmark = pytest.mark.unit

JULY = (date(2026, 7, 1), date(2026, 7, 31))
JUNE = (date(2026, 6, 1), date(2026, 6, 30))
#: Ends the day July starts. Not disjoint: both ranges contain 1 July.
TOUCHING = (date(2026, 6, 1), date(2026, 7, 1))
#: Overlaps the middle of July.
OVERLAPPING = (date(2026, 7, 15), date(2026, 8, 15))

#: Names the request contract does not carry. Each is a real thing somebody might
#: want to compare across and `002` cannot express — which is the point.
UNSUPPORTED_FIELDS = ("comparison", "order_by", "limit", "sql", "aggregate")


def _shape(
    fields: tuple[str, ...] = (), baseline: tuple[date, date] | None = None
) -> ComparisonShape:
    return ComparisonShape(
        differing_fields=frozenset(fields), primary_range=JULY, baseline_range=baseline
    )


def _route_or_refusal(shape: ComparisonShape) -> ComparisonRoute | InterpretationReasonCode:
    """Where the shape landed. Exactly one of the two, never neither."""
    try:
        return classify_route(shape)
    except ContractViolation as refusal:
        return refusal.code


# --- the derivation -------------------------------------------------------------


def test_the_supported_fields_are_derived_from_the_request_contract() -> None:
    """Not a list. `T095`'s central claim, asserted against the contract itself."""
    assert set(SINGLE_REQUEST_FIELDS) == set(AnalyticsQuery.model_fields) - {"date_range"}


def test_the_date_range_is_the_one_field_a_single_request_cannot_vary() -> None:
    """Why the second route exists at all — one range per request, by contract."""
    assert "date_range" in AnalyticsQuery.model_fields
    assert "date_range" not in SINGLE_REQUEST_FIELDS


def test_the_request_contract_carries_no_comparison_field() -> None:
    """`BD-1` removed it deliberately, and the routing rests on that.

    If ``comparison`` ever reappeared on ``AnalyticsQuery``, the derivation would
    silently start routing two-period comparisons through one request — so the
    absence is asserted rather than assumed.
    """
    assert "comparison" not in AnalyticsQuery.model_fields


def test_there_is_no_third_route() -> None:
    """No ``UNROUTABLE`` member. Absence of a route is a refusal, not a state."""
    assert {route.value for route in ComparisonRoute} == {"single_request", "two_execution"}


# --- totality over the full cross product --------------------------------------


def _every_field_subset() -> list[tuple[str, ...]]:
    """Every subset of the supported fields, smallest first, including empty."""
    supported = tuple(sorted(SINGLE_REQUEST_FIELDS))
    return [
        subset for size in range(len(supported) + 1) for subset in combinations(supported, size)
    ]


@pytest.mark.parametrize("fields", _every_field_subset())
@pytest.mark.parametrize("baseline", [None, JUNE, TOUCHING, OVERLAPPING])
def test_every_shape_lands_in_exactly_one_place(
    fields: tuple[str, ...], baseline: tuple[date, date] | None
) -> None:
    """The cross product. No shape returns ``None`` and none escapes uncaught."""
    landing = _route_or_refusal(_shape(fields, baseline))
    assert landing in set(ComparisonRoute) | {InterpretationReasonCode.COMPARISON_NOT_ROUTABLE}


@pytest.mark.parametrize("fields", _every_field_subset())
def test_no_second_range_is_always_the_single_request_route(fields: tuple[str, ...]) -> None:
    """Whatever the sides differ in, one ``AnalyticsQuery`` expresses it.

    Including the empty set: two sides differing in nothing is a degenerate
    comparison, but it is expressible in one request, and inventing a refusal for
    it here would be this feature deciding a question the catalog owns.
    """
    assert classify_route(_shape(fields)) is ComparisonRoute.SINGLE_REQUEST


@pytest.mark.parametrize("fields", _every_field_subset())
def test_two_disjoint_ranges_are_always_the_two_execution_route(fields: tuple[str, ...]) -> None:
    assert classify_route(_shape(fields, JUNE)) is ComparisonRoute.TWO_EXECUTION


# --- deny by default ------------------------------------------------------------


@pytest.mark.parametrize("field", UNSUPPORTED_FIELDS)
@pytest.mark.parametrize("baseline", [None, JUNE, OVERLAPPING])
def test_a_field_the_contract_does_not_carry_refuses(
    field: str, baseline: tuple[date, date] | None
) -> None:
    """Unroutable on **both** routes. The cheap one is not a fallback."""
    with pytest.raises(ContractViolation) as refusal:
        classify_route(_shape((field,), baseline))
    assert refusal.value.code is InterpretationReasonCode.COMPARISON_NOT_ROUTABLE


def test_an_unsupported_field_refuses_even_beside_supported_ones() -> None:
    """The supported majority does not carry the unsupported member through."""
    with pytest.raises(ContractViolation) as refusal:
        classify_route(_shape(("sources", "filters", "limit")))
    assert refusal.value.code is InterpretationReasonCode.COMPARISON_NOT_ROUTABLE


@pytest.mark.parametrize("baseline", [OVERLAPPING, TOUCHING, JULY])
def test_overlapping_periods_refuse(baseline: tuple[date, date]) -> None:
    """Two ranges sharing a day are not two disjoint periods.

    ``TOUCHING`` is the case worth having: it ends the day July begins, so a
    strict ``<`` on the wrong side would call it disjoint and the comparison
    would count 1 July on both sides.
    """
    with pytest.raises(ContractViolation) as refusal:
        classify_route(_shape(("sources",), baseline))
    assert refusal.value.code is InterpretationReasonCode.COMPARISON_NOT_ROUTABLE


# --- the disjointness predicate itself ------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "disjoint"),
    [
        (JUNE, JULY, True),
        (JULY, JUNE, True),
        (TOUCHING, JULY, False),
        (JULY, TOUCHING, False),
        (JULY, OVERLAPPING, False),
        (JULY, JULY, False),
        ((date(2026, 7, 1), date(2026, 7, 1)), (date(2026, 7, 2), date(2026, 7, 2)), True),
    ],
)
def test_disjointness_is_inclusive_on_both_ends(
    left: tuple[date, date], right: tuple[date, date], disjoint: bool
) -> None:
    """Symmetric, and closed at both ends — a single shared day is an overlap."""
    assert ranges_are_disjoint(left, right) is disjoint
    assert ranges_are_disjoint(right, left) is disjoint


# --- cross-source stays on the cheap route --------------------------------------


@pytest.mark.parametrize("field", ["sources", "filters", "dimensions", "metrics", "as_of"])
def test_the_comparisons_002_already_expresses_do_not_cost_two_executions(field: str) -> None:
    """`FR-064`, `SC-049`: cross-source, cross-store, cross-platform, by value.

    Every one of these differs in a field ``AnalyticsQuery`` carries and shares
    one period, so `002` evaluates the comparability in its single evaluation.
    Routing them through two executions would duplicate machinery `002` owns and
    double the bill.
    """
    assert classify_route(_shape((field,))) is ComparisonRoute.SINGLE_REQUEST


def test_a_cross_platform_comparison_over_one_period_is_one_request() -> None:
    """The concrete case from the spec: two stores, same July, one request."""
    shape = _shape(("sources", "filters"))
    assert classify_route(shape) is ComparisonRoute.SINGLE_REQUEST
    assert shape.baseline_range is None


# --- determinism -----------------------------------------------------------------


@pytest.mark.parametrize("baseline", [None, JUNE, OVERLAPPING])
def test_the_same_shape_always_routes_the_same_way(baseline: tuple[date, date] | None) -> None:
    """No clock, no policy, no preference — `SC-005`."""
    shape = _shape(("sources",), baseline)
    assert _route_or_refusal(shape) == _route_or_refusal(shape)


def test_the_field_order_never_changes_the_route() -> None:
    """``differing_fields`` is a set, and the routing must treat it as one."""
    forward = _shape(("sources", "filters", "dimensions"))
    reversed_ = _shape(("dimensions", "filters", "sources"))
    assert classify_route(forward) is classify_route(reversed_)
