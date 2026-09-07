"""Completion-evidence tests for T062, T063, T066, T067, T068, T070, T071.

T062: the library opens no warehouse connection itself.
T063: every branch of gates 7 to 9 has a fixture.
T066: a named-but-unused source reports ``required: false``.
T067: ``COVERAGE_ENDS_BEFORE_PERIOD`` and ``RANGE_OUTSIDE_COVERAGE`` reachable.
T068: all five states reachable; ``partial`` denies **even within tolerance**.
T070: a decision carrying ``answerable_subset`` is still ``DENY``.
T071: ``PERIOD_RESTATED`` attaches to every touched period.
"""

from __future__ import annotations

import inspect
import io
import tokenize
from datetime import date, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.contracts.source import Source
from semantic_catalog.freshness import external
from semantic_catalog.freshness.external import (
    CompletenessStatus,
    FreshnessRecord,
    FreshnessSnapshot,
    load_snapshot,
)
from semantic_catalog.freshness.limitations import limitations_for
from semantic_catalog.freshness.required import required_sources, requirement_map
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.loader.load import load_catalog
from semantic_catalog.periods.canonical import canonical_period
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    DateRange,
)
from semantic_catalog.validation.gates.coverage import comparable_window
from semantic_catalog.validation.pipeline import evaluate

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
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


def _decide(bundle: Bundle, fixture: str | None, **kwargs: object) -> CatalogDecision:
    request = CatalogValidationRequest(
        date_range=WINDOW,
        requester_access=("standard",),
        **kwargs,  # type: ignore[arg-type]
    )
    return evaluate(
        request,
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=load_snapshot(FRESHNESS / fixture) if fixture else None,
    )


# --- T062 the adapter holds nothing -----------------------------------------


def _executable_source(module: ModuleType) -> str:
    """Module source with every comment and string literal removed.

    Prose about what the module refuses to do is not the module doing it, so a
    naive substring scan over the file would flag its own docstring.
    """
    tokens = tokenize.generate_tokens(io.StringIO(inspect.getsource(module)).readline)
    return " ".join(
        tok.string for tok in tokens if tok.type not in (tokenize.COMMENT, tokenize.STRING)
    )


def test_the_library_opens_no_warehouse_connection() -> None:
    """No client, no credential, no DDL. The caller reads; this module models."""
    code = _executable_source(external).lower()
    for forbidden in (
        "bigquery",
        "google.cloud",
        "credentials",
        "connect(",
        "create table",
        "insert into",
        "merge into",
        "delete from",
    ):
        assert forbidden not in code, forbidden


def test_a_fixture_can_never_claim_production_readiness() -> None:
    """`is_fixture` is forced true on load, whatever the file says."""
    for path in sorted(FRESHNESS.glob("*.yaml")):
        assert load_snapshot(path).is_fixture, path.name


def test_lag_and_tolerance_are_derived_at_read_time(bundle: Bundle) -> None:
    """Tolerance is authored in Git; lag is observed. The comparison is the gate."""
    record = load_snapshot(FRESHNESS / "beyond_tolerance.yaml").record_for("app_a")
    assert record is not None
    source = bundle.internal.sources["app_a"]
    now = datetime(2026, 8, 11, 6, tzinfo=record.observed_at.tzinfo)
    assert record.lag(now=now) == timedelta(days=4, hours=1)
    assert record.within_tolerance(source, now=now) is False


def test_an_unobservable_lag_is_none_not_false(bundle: Bundle) -> None:
    """Three-valued on purpose: unknown must not collapse into a pass."""
    record = FreshnessRecord(
        source="app_a", status=CompletenessStatus.UNKNOWN, observed_at=datetime(2026, 8, 11)
    )
    assert record.lag(now=datetime(2026, 8, 11)) is None
    assert (
        record.within_tolerance(bundle.internal.sources["app_a"], now=datetime(2026, 8, 11)) is None
    )


def test_a_failed_state_must_explain_itself() -> None:
    with pytest.raises(ValueError, match="no last_error"):
        FreshnessRecord(
            source="app_a", status=CompletenessStatus.FAILED, observed_at=datetime(2026, 8, 11)
        )


def test_two_records_for_one_source_are_refused() -> None:
    with pytest.raises(ValueError, match="two freshness records"):
        FreshnessSnapshot(
            observed_at=datetime(2026, 8, 11),
            records=(
                FreshnessRecord(
                    source="app_a",
                    status=CompletenessStatus.COMPLETE,
                    observed_at=datetime(2026, 8, 11),
                ),
                FreshnessRecord(
                    source="app_a",
                    status=CompletenessStatus.COMPLETE,
                    observed_at=datetime(2026, 8, 11),
                ),
            ),
        )


# --- T063 every branch has a fixture ----------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "complete",
        "partial",
        "delayed",
        "failed",
        "unknown",
        "lagging_within_tolerance",
        "beyond_tolerance",
        "partial_within_tolerance",
        "long_tolerance_short_coverage",
        "website_beyond_tolerance",
        "android_beyond_tolerance",
        "one_source_beyond_tolerance",
        "outside_coverage",
        "no_coverage_row",
    ],
)
def test_the_named_fixture_exists_and_loads(name: str) -> None:
    assert load_snapshot(FRESHNESS / f"{name}.yaml").records is not None


def test_every_completeness_state_has_a_fixture() -> None:
    states = {
        record.status for path in FRESHNESS.glob("*.yaml") for record in load_snapshot(path).records
    }
    assert states == set(CompletenessStatus)


# --- T066 required-source reduction -----------------------------------------


def test_a_named_but_unused_source_reports_required_false(bundle: Bundle) -> None:
    """Scenario 6c. Its staleness is irrelevant to an answer it never feeds."""
    reduction = requirement_map(bundle.internal.metrics, ("store_downloads",), ("store_a", "app_a"))
    assert reduction["store_a"].required
    assert reduction["store_a"].feeds == ("store_downloads",)
    assert not reduction["app_a"].required
    assert reduction["app_a"].feeds == ()


def test_a_source_feeding_any_requested_metric_is_required(bundle: Bundle) -> None:
    reduction = requirement_map(
        bundle.internal.metrics, ("app_sessions", "store_downloads"), ("app_a", "store_a")
    )
    assert all(r.required for r in reduction.values())


def test_the_reduction_is_stable_and_sorted(bundle: Bundle) -> None:
    result = required_sources(
        bundle.internal.metrics, ("app_sessions",), ("store_a", "app_a", "store_a")
    )
    assert [r.source for r in result] == ["app_a", "store_a"]


def test_refusal_is_per_evaluation_not_a_quarantine(bundle: Bundle) -> None:
    """Scenario 6b. The same stale snapshot denies one request and not the other."""
    stale = "website_beyond_tolerance.yaml"
    needs_it = _decide(bundle, stale, metrics=("store_downloads",), sources=("store_a",))
    does_not = _decide(bundle, stale, metrics=("app_sessions",), sources=("app_a",))
    assert needs_it.outcome is Outcome.DENY
    assert needs_it.reason_code is ReasonCode.SOURCE_BEYOND_TOLERANCE
    assert does_not.outcome is Outcome.ALLOW


# --- T067 coverage ----------------------------------------------------------


def test_a_single_source_window_is_not_narrowed() -> None:
    """BD-1 / ADR 0001: single-source coverage is offered in full."""
    snapshot = load_snapshot(FRESHNESS / "complete.yaml")
    rows = (snapshot.coverage_for("app_sessions", "app_a"),)
    window = comparable_window(tuple(r for r in rows if r is not None))
    assert window is not None
    assert not window.is_cross_source
    assert window.start == date(2026, 1, 1)
    assert window.end == date(2026, 8, 10)
    assert "FR-023" in window.chosen_because


def test_a_cross_source_window_is_the_intersection_and_says_why() -> None:
    snapshot = load_snapshot(FRESHNESS / "long_tolerance_short_coverage.yaml")
    healthy = load_snapshot(FRESHNESS / "complete.yaml")
    rows = tuple(
        row
        for row in (
            healthy.coverage_for("app_sessions", "app_a"),
            snapshot.coverage_for("store_downloads", "store_a"),
        )
        if row is not None
    )
    window = comparable_window(rows)
    assert window is not None
    assert window.is_cross_source
    assert window.end == date(2026, 7, 20)
    assert window.chosen_because


def test_coverage_ending_before_the_period_denies(bundle: Bundle) -> None:
    decision = _decide(
        bundle,
        "long_tolerance_short_coverage.yaml",
        metrics=("store_downloads",),
        sources=("store_a",),
    )
    assert decision.reason_code is ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD
    assert decision.subject.id == "store_a"


def test_coverage_outside_the_period_denies(bundle: Bundle) -> None:
    decision = _decide(
        bundle, "outside_coverage.yaml", metrics=("app_sessions",), sources=("app_a",)
    )
    assert decision.reason_code is ReasonCode.RANGE_OUTSIDE_COVERAGE


def test_silence_in_the_availability_table_is_not_coverage(bundle: Bundle) -> None:
    decision = _decide(
        bundle, "no_coverage_row.yaml", metrics=("app_sessions",), sources=("app_a",)
    )
    assert decision.reason_code is ReasonCode.RANGE_OUTSIDE_COVERAGE


# --- T068 freshness ---------------------------------------------------------


@pytest.mark.parametrize(
    "fixture, metric, source, code",
    [
        ("partial.yaml", "app_sessions", "app_a", ReasonCode.SOURCE_STATE_PARTIAL),
        ("failed.yaml", "app_sessions", "app_a", ReasonCode.SOURCE_STATE_FAILED),
        ("unknown.yaml", "app_sessions", "app_a", ReasonCode.SOURCE_STATE_UNKNOWN),
        ("beyond_tolerance.yaml", "app_sessions", "app_a", ReasonCode.SOURCE_BEYOND_TOLERANCE),
    ],
)
def test_every_unhealthy_state_denies(
    bundle: Bundle, fixture: str, metric: str, source: str, code: ReasonCode
) -> None:
    decision = _decide(bundle, fixture, metrics=(metric,), sources=(source,))
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is code
    assert decision.subject.id == source


def test_partial_denies_even_within_tolerance(bundle: Bundle) -> None:
    """FR-070 / SC-033. Punctuality is not completeness."""
    snapshot = load_snapshot(FRESHNESS / "partial_within_tolerance.yaml")
    record = snapshot.record_for("store_a")
    assert record is not None
    assert record.within_tolerance(bundle.internal.sources["store_a"], now=snapshot.observed_at), (
        "the fixture must be inside tolerance, or it proves nothing"
    )

    decision = _decide(
        bundle,
        "partial_within_tolerance.yaml",
        metrics=("store_downloads",),
        sources=("store_a",),
    )
    assert decision.reason_code is ReasonCode.SOURCE_STATE_PARTIAL


def test_lagging_within_tolerance_allows_with_a_caveat(bundle: Bundle) -> None:
    decision = _decide(
        bundle, "lagging_within_tolerance.yaml", metrics=("app_sessions",), sources=("app_a",)
    )
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE


def test_a_missing_snapshot_denies_as_unknown(bundle: Bundle) -> None:
    decision = _decide(bundle, None, metrics=("app_sessions",), sources=("app_a",))
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.SOURCE_STATE_UNKNOWN


def test_coverage_and_freshness_are_independent(bundle: Bundle) -> None:
    """FR-071 / SC-034. On time, and still missing the days."""
    snapshot = load_snapshot(FRESHNESS / "long_tolerance_short_coverage.yaml")
    record = snapshot.record_for("store_a")
    assert record is not None
    assert record.status is CompletenessStatus.COMPLETE
    assert record.within_tolerance(bundle.internal.sources["store_a"], now=snapshot.observed_at)
    decision = _decide(
        bundle,
        "long_tolerance_short_coverage.yaml",
        metrics=("store_downloads",),
        sources=("store_a",),
    )
    assert decision.reason_code is ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD


# --- T070 disclosure --------------------------------------------------------


def test_a_decision_carrying_a_subset_is_still_a_denial(bundle: Bundle) -> None:
    decision = _decide(
        bundle,
        "one_source_beyond_tolerance.yaml",
        metrics=("cross_source_metric",),
        sources=("app_a", "store_a"),
    )
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.SOURCE_BEYOND_TOLERANCE
    assert decision.answerable_subset == ("app_a",)


def test_the_subset_names_sources_and_nothing_else(bundle: Bundle) -> None:
    """Nothing in it can be mistaken for an answer."""
    decision = _decide(
        bundle,
        "one_source_beyond_tolerance.yaml",
        metrics=("cross_source_metric",),
        sources=("app_a", "store_a"),
    )
    assert all(s in bundle.internal.sources for s in decision.answerable_subset)


def test_no_subset_rides_on_an_allow(bundle: Bundle) -> None:
    decision = _decide(bundle, "complete.yaml", metrics=("app_sessions",), sources=("app_a",))
    assert decision.outcome is Outcome.ALLOW
    assert decision.answerable_subset == ()


def test_no_subset_when_every_required_source_is_healthy(bundle: Bundle) -> None:
    """A subset equal to the whole set discloses nothing and reads as a contradiction."""
    decision = _decide(
        bundle, "no_coverage_row.yaml", metrics=("app_sessions",), sources=("app_a",)
    )
    assert decision.outcome is Outcome.DENY
    assert decision.answerable_subset == ()


# --- T071 limitations -------------------------------------------------------


def _source_with_history() -> Source:
    return Source.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "source",
            "id": "store_a",
            "type": "app_store",
            "product": "fixture_app",
            "platform": "android",
            "store": "store_a",
            "reporting_timezone": "America/Los_Angeles",
            "earliest_available_date": "2026-01-01",
            "expected_refresh_interval": "P1D",
            "delay_tolerance": "P2D",
            "owner": "fixture_owner",
            "content": {"lang": "pt-BR", "label": "Loja de teste"},
            "outages": [{"from": "2026-07-05", "to": "2026-07-06", "reason": "Falha de ingestão."}],
            "restatements": [
                {
                    "restated_at": "2026-08-01",
                    "affects_from": "2026-07-01",
                    "affects_to": "2026-07-31",
                    "reason": "A loja republicou os números do mês.",
                },
                {
                    "restated_at": "2026-08-01",
                    "affects_from": "2026-05-01",
                    "affects_to": "2026-05-31",
                    "reason": "Correção anterior.",
                },
            ],
        }
    )


def test_a_restatement_attaches_to_every_touched_period() -> None:
    source = _source_with_history()
    period = canonical_period(date(2026, 7, 1), date(2026, 7, 31), on=ON)
    found = limitations_for({"store_a": source}, ("store_a",), period)
    codes = {limitation.code for limitation in found}
    assert ReasonCode.PERIOD_RESTATED in codes
    assert ReasonCode.SOURCE_STATE_PARTIAL in codes  # the outage window


def test_an_untouched_restatement_does_not_attach() -> None:
    source = _source_with_history()
    period = canonical_period(date(2026, 6, 1), date(2026, 6, 30), on=ON)
    assert limitations_for({"store_a": source}, ("store_a",), period) == ()


def test_limitations_are_stable_across_calls() -> None:
    source = _source_with_history()
    period = canonical_period(date(2026, 5, 1), date(2026, 7, 31), on=ON)
    first = limitations_for({"store_a": source}, ("store_a",), period)
    second = limitations_for({"store_a": source}, ("store_a",), period)
    assert [x.describe() for x in first] == [x.describe() for x in second]
    assert len(first) == 3


def test_the_production_catalog_declares_no_history_yet() -> None:
    """Outages and restatements are D-1 inventory nobody has supplied."""
    catalog = load_catalog(REPO / "semantic")
    for source in catalog.sources.values():
        assert source.outages == ()
        assert source.restatements == ()
