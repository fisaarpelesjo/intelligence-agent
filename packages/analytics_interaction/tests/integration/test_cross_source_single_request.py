"""Cross-source comparisons stay one governed request — T098 (FR-012, FR-064; SC-019, SC-049).

    Evidence: exactly one execution; `002`'s path is not duplicated or re-routed.
    — `tasks.md` T098

The tempting mistake is to treat *comparison* and *two executions* as the same
thing. They are not. `002`'s ``sources`` field takes a list and its ``filters``
express dimension values, so "App Store versus Play Store in July" is **one**
request — and `001` evaluates the two sources' comparability inside the single
evaluation `002` already performs.

Routing it through two executions would be worse in three separate ways: it would
duplicate machinery `002` owns, it would double the bill (`FR-064`, `SC-049`),
and — the one nobody notices until it matters — the comparability question would
be asked *twice, separately*, which is exactly the two-single-side-verdicts
failure `FR-065` forbids.

So this suite walks the whole path for a cross-source comparison: classify the
shape, build the governed request, submit it, and count. One request carrying
both sources, one crossing of the ADR 0010 boundary, one date range.
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.routing import ComparisonShape, classify_route
from analytics_interaction.contracts.comparison import ComparisonRoute
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import ResolvedIntent, ResolvedPeriod, SlotKind
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent

from ..conftest import ON, REFERENCE, governed_resolution
from ..fixtures.submissions import recorded_port

pytestmark = pytest.mark.integration

JULY = (date(2026, 7, 1), date(2026, 7, 31))
SOURCES = ("appstore", "playstore")
CORRELATION = "interp-cross-source"


def _cross_source_intent(
    pair: tuple[AuthorizedContext, str], period: ResolvedPeriod
) -> ResolvedIntent:
    """One metric, two sources, one period — the comparison as `002` expresses it."""
    authorized, fingerprint = pair
    return assemble_resolved_intent(
        (
            governed_resolution("installs"),
            governed_resolution(SOURCES[0], SlotKind.SOURCE, start=10, length=8),
            governed_resolution(SOURCES[1], SlotKind.SOURCE, start=20, length=9),
        ),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=period,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=None,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


# --- the route ------------------------------------------------------------------


def test_a_cross_source_comparison_routes_to_a_single_request() -> None:
    """One shared period, a field the request contract carries."""
    shape = ComparisonShape(differing_fields=frozenset({"sources"}), primary_range=JULY)
    assert classify_route(shape) is ComparisonRoute.SINGLE_REQUEST


@pytest.mark.parametrize("field", ["sources", "filters", "dimensions"])
def test_cross_store_cross_platform_and_by_value_all_take_the_same_route(field: str) -> None:
    """Three business questions, one governed shape.

    "App Store versus Play Store", "iOS versus Android" and "Brazil versus
    Mexico" differ only in which field carries the distinction — and all three
    are expressible in one request over one period.
    """
    shape = ComparisonShape(differing_fields=frozenset({field}), primary_range=JULY)
    assert classify_route(shape) is ComparisonRoute.SINGLE_REQUEST


# --- one request, both sides ----------------------------------------------------


def test_both_sources_travel_in_one_request(
    authorized_pair: tuple[AuthorizedContext, str], july_period: ResolvedPeriod
) -> None:
    """The comparison is *in* the request, not spread across two of them."""
    authorized, fingerprint = authorized_pair
    intent = _cross_source_intent(authorized_pair, july_period)

    request = build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)

    assert set(request.sources) == set(SOURCES)
    assert (request.date_range.start, request.date_range.end) == JULY


def test_the_single_request_route_crosses_the_boundary_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
) -> None:
    """`SC-049`: one execution, not two. Counted at the boundary."""
    authorized, fingerprint = authorized_pair
    intent = _cross_source_intent(authorized_pair, july_period)
    request = build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)
    port, recorder = recorded_port(monkeypatch, on=ON)

    port.submit(
        request, authorized=authorized, auth_fingerprint=fingerprint, correlation_id=CORRELATION
    )

    assert recorder.count == 1
    assert recorder.date_ranges() == [JULY]
    assert set(recorder.calls[0].request.sources) == set(SOURCES)


def test_002s_path_is_not_duplicated_by_splitting_the_sources(
    monkeypatch: pytest.MonkeyPatch,
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
) -> None:
    """The failure this test exists to catch, stated as a count.

    A re-routing that submitted one request per source would produce two
    crossings over the same period — twice the bill, and two separate
    comparability answers where the catalog gave one.
    """
    authorized, fingerprint = authorized_pair
    intent = _cross_source_intent(authorized_pair, july_period)
    request = build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)
    port, recorder = recorded_port(monkeypatch, on=ON)

    port.submit(
        request, authorized=authorized, auth_fingerprint=fingerprint, correlation_id=CORRELATION
    )

    assert recorder.count == 1
    assert len(set(recorder.date_ranges())) == 1
    assert len(recorder.calls[0].request.sources) == len(SOURCES)


# --- and only a second period changes that --------------------------------------


def test_only_a_second_disjoint_period_promotes_the_route() -> None:
    """The contrast that makes the rule legible.

    Same differing field, same everything — except a second period, which is the
    one thing one ``AnalyticsQuery`` cannot carry.
    """
    june = (date(2026, 6, 1), date(2026, 6, 30))
    shared = ComparisonShape(differing_fields=frozenset({"sources"}), primary_range=JULY)
    split = ComparisonShape(
        differing_fields=frozenset({"sources"}), primary_range=JULY, baseline_range=june
    )

    assert classify_route(shared) is ComparisonRoute.SINGLE_REQUEST
    assert classify_route(split) is ComparisonRoute.TWO_EXECUTION
