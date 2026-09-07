"""The reader consumes a decision the real `001` evaluator produced — ADR 0016.

`test_comparable_window_transport` proves the reader handles the shape. This file
proves it handles the **thing** — a ``CatalogDecision`` returned by `001`'s
production ``evaluate()`` composition, run against `001`'s own fixture catalog,
carrying the window gate 7 computed on the way through.

The distinction is the one both ADR 0016 defects hid. A shape test passes against
a hand-built decision whether or not the production path ever attaches a window;
only running the evaluator shows whether one arrives.

This assertion lives here rather than in `001` because `001` depends on nothing
downstream — reaching into `analytics_query` from the catalog would invert the
dependency the architecture rests on. `002` depends on `001` already, so this is
the side of the seam that can hold the test.

Nothing here changes `002`'s execution path. The reader is not on it: converting a
window costs nothing, reads no adapter and touches no ledger.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome
from semantic_catalog.freshness.external import FreshnessSnapshot, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    Comparison,
    DateRange,
)
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.contracts.comparable_window import ComparableWindow, window_from_decision

pytestmark = pytest.mark.integration

#: `001`'s own fixture catalog. Its fixtures rather than a copy: a copy would
#: drift, and the point of this file is that the *real* evaluator's output works.
CATALOG_TESTS = Path(__file__).resolve().parents[3] / "semantic_catalog" / "tests"
CATALOG = CATALOG_TESTS / "fixtures" / "decision_matrix" / "catalog"
FRESHNESS = CATALOG_TESTS / "fixtures" / "freshness"

COMMIT = "fixture0"
ON = date(2026, 8, 11)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
JUNE = DateRange(start=date(2026, 6, 1), end=date(2026, 6, 30))


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(CATALOG, current_commit=COMMIT, on=ON)


@pytest.fixture(scope="module")
def snapshot() -> FreshnessSnapshot:
    return load_snapshot(FRESHNESS / "complete.yaml")


def _evaluate(
    bundle: Bundle, snapshot: FreshnessSnapshot | None, request: CatalogValidationRequest
) -> CatalogDecision:
    return evaluate(
        request,
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
    )


def _cross_source(comparison: Comparison | None = None) -> CatalogValidationRequest:
    return CatalogValidationRequest(
        metrics=("cross_source_metric",),
        sources=("app_a", "store_a"),
        date_range=JULY,
        comparison=comparison,
        requester_access=("standard",),
    )


# --- the reader accepts the real thing ---------------------------------------------


def test_the_reader_converts_a_real_permitted_decision(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """The call that refused before ADR 0016, now succeeding on the real path."""
    decision = _evaluate(bundle, snapshot, _cross_source())
    assert decision.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}

    window = window_from_decision(decision)
    assert isinstance(window, ComparableWindow)


def test_every_part_survives_the_conversion(bundle: Bundle, snapshot: FreshnessSnapshot) -> None:
    """Field by field against what `001` stated. Nothing defaulted, nothing derived."""
    decision = _evaluate(bundle, snapshot, _cross_source())
    stated = decision.comparable_window
    window = window_from_decision(decision)

    assert stated is not None
    assert window is not None
    assert (window.start, window.end) == (stated.start, stated.end)
    assert window.sources == stated.sources
    assert window.reason == stated.chosen_because


def test_the_governed_reason_is_not_rewritten(bundle: Bundle, snapshot: FreshnessSnapshot) -> None:
    """`001`'s wording reaches `002`'s type byte for byte."""
    decision = _evaluate(bundle, snapshot, _cross_source())
    stated = decision.comparable_window
    window = window_from_decision(decision)

    assert stated is not None
    assert window is not None
    assert len(window.reason) == len(stated.chosen_because)
    assert window.reason == stated.chosen_because


def test_a_real_period_comparison_converts_too(bundle: Bundle, snapshot: FreshnessSnapshot) -> None:
    """The shape `003`'s two-execution route actually submits."""
    decision = _evaluate(
        bundle,
        snapshot,
        _cross_source(Comparison(kind="period_over_period", baseline_range=JUNE)),
    )
    assert window_from_decision(decision) is not None


# --- and still reports none where `001` states none ---------------------------------


def test_a_real_single_source_decision_reports_no_window(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """`FR-023`: full coverage, no narrowing, nothing to qualify."""
    request = CatalogValidationRequest(
        metrics=("app_sessions",),
        sources=("app_a",),
        date_range=JULY,
        requester_access=("standard",),
    )
    decision = _evaluate(bundle, snapshot, request)

    assert decision.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}
    assert window_from_decision(decision) is None


def test_a_real_denial_reports_no_window(bundle: Bundle, snapshot: FreshnessSnapshot) -> None:
    """A refusal ships nothing a consumer could execute against."""
    request = CatalogValidationRequest(
        metrics=("store_downloads", "app_sessions"),
        sources=("app_a", "store_a"),
        date_range=JULY,
        requester_access=("standard",),
    )
    decision = _evaluate(bundle, snapshot, request)

    assert decision.outcome is Outcome.DENY
    assert window_from_decision(decision) is None


def test_a_real_decision_with_no_snapshot_reports_no_window(bundle: Bundle) -> None:
    """Unobserved coverage is unknown, not unbounded."""
    assert window_from_decision(_evaluate(bundle, None, _cross_source())) is None


# --- the conversion is deterministic -------------------------------------------------


def test_converting_the_same_real_decision_twice_agrees(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    decision = _evaluate(bundle, snapshot, _cross_source())
    first = window_from_decision(decision)
    second = window_from_decision(decision)

    assert first is not None
    assert second is not None
    assert first.model_dump_json() == second.model_dump_json()
