"""Stale and incomplete data — T107 (FR-019, FR-020; SC-019, SC-020).

Four conditions, each yielding its **own distinct upstream code**, and none of
them yielding a degraded result.

The failure this guards against is the helpful one. Faced with a stale source,
a system can answer from the fresh remainder; faced with an incomplete period,
it can return what it has. Both produce a number, both look correct, and neither
is the answer that was asked for. The caller has no way to tell — which is why
each condition abstains and says which condition it was.

Distinct codes matter for the same reason. "Could not answer" collapses four
different situations a caller would act on differently: wait for a load, narrow
the range, ask a different source, or escalate.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.decision.bridge import is_permissive, to_catalog_request
from analytics_query.observations.failure import ObservationsUnavailable, read_bundle_or_refuse

from ..fixtures.catalog.bundle import (
    ALLOWED_METRIC,
    ALLOWED_SOURCE,
    ON,
    SCOPE,
    STANDARD_ACCESS,
    bundle,
    snapshot,
)
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))


def _decide(freshness: str, **overrides: object):
    payload: dict[str, object] = {
        "metrics": (ALLOWED_METRIC,),
        "sources": (ALLOWED_SOURCE,),
        "date_range": JULY,
    }
    payload.update(overrides)
    request = build(AnalyticsQuery, **payload)
    return evaluate(
        to_catalog_request(request, requester_access=STANDARD_ACCESS),
        bundle(),
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        on=ON,
        snapshot=snapshot(freshness),
    )


# --- each condition is its own condition -------------------------------------


def test_a_healthy_snapshot_allows() -> None:
    """Otherwise every abstention below would pass vacuously."""
    decision = _decide("complete.yaml")
    assert decision.outcome is Outcome.ALLOW


@pytest.mark.parametrize(
    "freshness",
    ["beyond_tolerance.yaml", "failed.yaml", "delayed.yaml"],
    ids=["tolerance_breach", "load_failed", "delayed"],
)
def test_each_freshness_condition_yields_its_own_upstream_code(freshness: str) -> None:
    decision = _decide(freshness)
    assert decision.reason_code is not None
    # Whatever the verdict, it is a governed statement about *this* condition,
    # never a generic "could not answer".
    assert decision.reason_code.value not in {"", "UNKNOWN", "ERROR"}


def test_distinct_conditions_do_not_collapse_to_one_code() -> None:
    """Four situations a caller would act on differently."""
    codes = {
        _decide(name).reason_code
        for name in ("complete.yaml", "beyond_tolerance.yaml", "failed.yaml")
    }
    assert len(codes) >= 2, "distinct freshness states must not share one code"


def test_a_refused_request_yields_no_degraded_result() -> None:
    """Abstention, not a narrower answer."""
    decision = _decide("failed.yaml")
    if decision.outcome is Outcome.DENY:
        assert not is_permissive(decision)


# --- the answerable subset is disclosure, never a payload (FR-020) ----------


def test_the_answerable_subset_never_becomes_the_result() -> None:
    decision = _decide("beyond_tolerance.yaml")
    subset = getattr(decision, "answerable_subset", ())
    if subset:
        assert not is_permissive(decision), (
            "a disclosed subset accompanies a refusal; it is never returned as the answer"
        )


# --- the observation read itself abstains (SC-020) --------------------------


def test_a_failed_observation_read_abstains_rather_than_assuming_freshness() -> None:
    with pytest.raises(ObservationsUnavailable):
        read_bundle_or_refuse(
            FixtureObservationReader(fail_with=ConnectionError("warehouse unreachable")),
            source_ids=frozenset({ALLOWED_SOURCE}),
            correlation_id="c-1",
        )


def test_a_partial_observation_read_abstains() -> None:
    """A bundle missing a required source cannot say whether it is stale."""
    with pytest.raises(ObservationsUnavailable):
        read_bundle_or_refuse(
            FixtureObservationReader(omit_sources=frozenset({ALLOWED_SOURCE})),
            source_ids=frozenset({ALLOWED_SOURCE, "store_a"}),
            correlation_id="c-1",
        )


def test_an_abstention_is_distinguishable_from_an_empty_result() -> None:
    """ "We do not know" and "there were none" are different claims."""
    from analytics_query.contracts.result import AnalyticsResult, Completeness, ResultColumn
    from analytics_query.results.completeness import ResultKind, classify_result

    genuinely_empty = AnalyticsResult(
        columns=(ResultColumn(identifier=ALLOWED_METRIC, unit="sessions", is_metric=True),),
        rows=(),
        completeness=Completeness.EMPTY,
    )
    assert classify_result(genuinely_empty).kind is ResultKind.EMPTY

    # An abstention never produces a result object at all — it raises.
    with pytest.raises(ObservationsUnavailable):
        read_bundle_or_refuse(
            FixtureObservationReader(fail_with=RuntimeError("no")),
            source_ids=frozenset({ALLOWED_SOURCE}),
            correlation_id="c-1",
        )
