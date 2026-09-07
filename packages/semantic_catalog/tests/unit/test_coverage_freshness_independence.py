"""Coverage and freshness are independent — T078 (FR-070, FR-071; Scenario 19).

Two gates that look like one and are not. Being on time says **when** the load
ran; covering the period says **which days exist**; completeness says **how much
of the load arrived**. Any of the three can pass while another fails, and the
whole point of separating them is that neither can satisfy the other.

Each test states the trap it closes:

* a **partial** source inside its tolerance still denies (FR-070, SC-033) —
  punctuality is not completeness, and a half-loaded source produces a number
  that looks entirely ordinary;
* a source whose **coverage ends early** denies even with a clean recent load
  (FR-071, SC-034) — being on time does not manufacture the missing days;
* an **unknown** state denies with no tolerance applied at all, because there is
  nothing to compare a tolerance against.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import CompletenessStatus, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    DateRange,
)
from semantic_catalog.validation.pipeline import evaluate, gate_order

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CATALOG = FIXTURES / "decision_matrix" / "catalog"
FRESHNESS = FIXTURES / "freshness"
ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        CATALOG,
        current_commit="fixture0",
        on=ON,
        source_commits={"app_a": "fixture0", "store_a": "fixture0"},
    )


def _decide(bundle: Bundle, fixture: str | None, metric: str, source: str) -> CatalogDecision:
    return evaluate(
        CatalogValidationRequest(
            metrics=(metric,),
            sources=(source,),
            date_range=WINDOW,
            requester_access=("standard",),
        ),
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=load_snapshot(FRESHNESS / fixture) if fixture else None,
    )


# --- the gates are separate -------------------------------------------------


def test_coverage_and_freshness_are_distinct_gates() -> None:
    order = gate_order()
    assert "coverage" in order and "freshness" in order
    assert order.index("coverage") < order.index("freshness")


# --- partial denies inside tolerance (FR-070, SC-033) -----------------------


def test_the_partial_fixture_really_is_inside_tolerance(bundle: Bundle) -> None:
    """Guards the test below: if the fixture were stale it would prove nothing."""
    snapshot = load_snapshot(FRESHNESS / "partial_within_tolerance.yaml")
    record = snapshot.record_for("store_a")
    assert record is not None
    assert record.status is CompletenessStatus.PARTIAL
    assert (
        record.within_tolerance(bundle.internal.sources["store_a"], now=snapshot.observed_at)
        is True
    )


def test_a_partial_source_denies_even_within_tolerance(bundle: Bundle) -> None:
    decision = _decide(bundle, "partial_within_tolerance.yaml", "store_downloads", "store_a")
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.SOURCE_STATE_PARTIAL
    assert decision.subject.id == "store_a"


def test_partial_is_never_promoted_to_complete_by_punctuality(bundle: Bundle) -> None:
    """SC-033 as a property: zero partial sources treated as complete."""
    for fixture in ("partial.yaml", "partial_within_tolerance.yaml"):
        snapshot = load_snapshot(FRESHNESS / fixture)
        for record in snapshot.records:
            if record.status is CompletenessStatus.PARTIAL:
                source = bundle.internal.sources.get(record.source)
                assert source is not None
                metric = "app_sessions" if record.source == "app_a" else "store_downloads"
                decision = _decide(bundle, fixture, metric, record.source)
                assert decision.outcome is Outcome.DENY, fixture
                assert decision.reason_code is ReasonCode.SOURCE_STATE_PARTIAL, fixture


# --- coverage shortfall denies inside tolerance (FR-071, SC-034) ------------


def test_the_short_coverage_fixture_really_is_punctual_and_complete(
    bundle: Bundle,
) -> None:
    snapshot = load_snapshot(FRESHNESS / "long_tolerance_short_coverage.yaml")
    record = snapshot.record_for("store_a")
    assert record is not None
    assert record.status is CompletenessStatus.COMPLETE
    assert (
        record.within_tolerance(bundle.internal.sources["store_a"], now=snapshot.observed_at)
        is True
    )


def test_coverage_ending_before_the_period_denies_despite_a_clean_load(
    bundle: Bundle,
) -> None:
    decision = _decide(bundle, "long_tolerance_short_coverage.yaml", "store_downloads", "store_a")
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD
    assert decision.subject.id == "store_a"


def test_being_on_time_never_substitutes_for_the_missing_days(bundle: Bundle) -> None:
    """The two gates report different codes for the same source, same snapshot."""
    short = _decide(bundle, "long_tolerance_short_coverage.yaml", "store_downloads", "store_a")
    stale = _decide(bundle, "website_beyond_tolerance.yaml", "store_downloads", "store_a")
    assert short.reason_code is ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD
    assert stale.reason_code is ReasonCode.SOURCE_BEYOND_TOLERANCE
    assert short.reason_code is not stale.reason_code


# --- unknown denies with no tolerance applied -------------------------------


def test_an_unknown_state_denies(bundle: Bundle) -> None:
    decision = _decide(bundle, "unknown.yaml", "app_sessions", "app_a")
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.SOURCE_STATE_UNKNOWN


def test_an_unknown_state_has_no_tolerance_to_apply(bundle: Bundle) -> None:
    """There is nothing to compare against, so 'within tolerance' is undefined."""
    snapshot = load_snapshot(FRESHNESS / "unknown.yaml")
    record = snapshot.record_for("app_a")
    assert record is not None
    assert record.last_successful_update is None
    assert record.lag(now=snapshot.observed_at) is None
    assert (
        record.within_tolerance(bundle.internal.sources["app_a"], now=snapshot.observed_at) is None
    )


def test_a_missing_snapshot_denies_as_unknown(bundle: Bundle) -> None:
    decision = _decide(bundle, None, "app_sessions", "app_a")
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.SOURCE_STATE_UNKNOWN


def test_a_failed_state_denies(bundle: Bundle) -> None:
    decision = _decide(bundle, "failed.yaml", "app_sessions", "app_a")
    assert decision.reason_code is ReasonCode.SOURCE_STATE_FAILED


# --- the healthy path proves none of this is vacuous ------------------------


def test_a_healthy_source_covering_the_period_allows(bundle: Bundle) -> None:
    decision = _decide(bundle, "complete.yaml", "app_sessions", "app_a")
    assert decision.outcome is Outcome.ALLOW
    assert decision.reason_code is ReasonCode.REQUEST_ALLOWED


def test_lagging_within_tolerance_answers_with_the_lag_stated(bundle: Bundle) -> None:
    decision = _decide(bundle, "lagging_within_tolerance.yaml", "app_sessions", "app_a")
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE
    assert decision.message_pt_br
