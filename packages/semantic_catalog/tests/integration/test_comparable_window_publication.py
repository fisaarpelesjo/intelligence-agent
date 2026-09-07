"""The real evaluator publishes the window it computes — ADR 0016.

Every assertion here runs the **production ``evaluate()`` composition** against
the fixture catalog. Nothing is hand-built: the decisions are what the pipeline
returns, and the windows are what gate 7 computed on the way through.

That distinction is the whole point of this file. `T067`'s evidence line reads
*"every cross-source ALLOW carries ``chosen_because``"*, `FR-024` requires a
cross-source request to *"state which window was selected and why"*, and `SC-005`
measures *"zero cross-source comparisons return an unstated window"*. All three
were satisfied by nothing: the gate computed the window and the pipeline never
attached it, so a fixture-built decision could show the shape while the real path
produced none.

## What this file does not test

The window's **calculation** — `test_freshness_and_coverage` owns that, and it is
unchanged. Nor eligibility, nor any outcome: the window is published on decisions
the pipeline already reached, and no gate verdict moves because of it.

## Where `002`'s half of the seam is asserted

Not here. `001` depends on nothing downstream, so the test that `002`'s reader
accepts a decision this evaluator produced lives in `002`'s suite, against this
same fixture catalog.

## The two triggers

* the request **declares a comparison** — `SC-005`;
* the request is **cross-source** — `FR-024`.

A single-source request that compares nothing gets none: `FR-023` gives it the
source's full coverage rather than a narrowed window, so there is no choice to
explain and attaching one would qualify an answer that was never qualified.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
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
from semantic_catalog.validation.gates.context import GateContext
from semantic_catalog.validation.gates.coverage import comparable_window, observed_rows, window_for
from semantic_catalog.validation.pipeline import evaluate
from semantic_catalog.validation.policy_runtime import resolve_policy

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "decision_matrix"
CATALOG = FIXTURES / "catalog"
FRESHNESS = FIXTURES.parent / "freshness"

COMMIT = "fixture0"
ON = date(2026, 8, 11)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
JUNE = DateRange(start=date(2026, 6, 1), end=date(2026, 6, 30))

#: Declared on both `app_a` and `store_a` in the fixture catalog, so a request
#: naming it is genuinely cross-source rather than cross-source by assertion.
CROSS_SOURCE = ("cross_source_metric",)
BOTH_SOURCES = ("app_a", "store_a")


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    # ADR 0033: `FIXTURES` already points at the fixture's own directory, so `CATALOG`
    # is that catalog -- and it CARRIES an approval naming `fixture0`. This is one of the
    # few places where the comparand actually resolves and decides, so it states the
    # commit per source. `_covers` matches by prefix and fixture0 == fixture0, so the
    # behaviour is unchanged; what changes is that the exercise moves to the new comparand.
    return build_bundle(
        CATALOG,
        current_commit=COMMIT,
        on=ON,
        source_commits={"app_a": COMMIT, "store_a": COMMIT},
    )


@pytest.fixture(scope="module")
def snapshot() -> FreshnessSnapshot:
    return load_snapshot(FRESHNESS / "complete.yaml")


def _request(
    *,
    metrics: tuple[str, ...] = CROSS_SOURCE,
    sources: tuple[str, ...] = BOTH_SOURCES,
    comparison: Comparison | None = None,
    date_range: DateRange = JULY,
) -> CatalogValidationRequest:
    return CatalogValidationRequest(
        metrics=metrics,
        sources=sources,
        date_range=date_range,
        comparison=comparison,
        requester_access=("standard",),
    )


def _evaluate(
    bundle: Bundle,
    snapshot: FreshnessSnapshot | None,
    request: CatalogValidationRequest,
    *,
    scope: str = "default",
    evaluated_at: datetime | None = None,
) -> CatalogDecision:
    """The production entry point. No shortcut, no stand-in.

    ``evaluated_at`` is passed through only where a byte-comparison needs the
    stamp pinned — the pipeline reads a clock for it, and a determinism claim
    about the *window* must not be defeated by the microsecond beside it.
    """
    return evaluate(
        request,
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope=scope,
        on=ON,
        snapshot=snapshot,
        evaluated_at=evaluated_at,
    )


def _gate_window(bundle: Bundle, snapshot: FreshnessSnapshot, request: CatalogValidationRequest):
    """What gate 7 computes for this request, obtained independently.

    Built through the same ``GateContext`` the pipeline builds, so the comparison
    below is *the gate's answer* against *the decision's answer* — not the
    decision against itself.
    """
    context = GateContext(
        request=request,
        bundle=bundle,
        policy=resolve_policy(bundle.internal, on=ON).require(),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
    )
    return window_for(context)


# --- 1. a permitted comparable comparison emits the complete window ---------------


def test_a_permitted_cross_source_decision_carries_a_complete_window(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """`FR-024`, `SC-005`, `T067`'s evidence line — satisfied by the real path."""
    decision = _evaluate(bundle, snapshot, _request())

    assert decision.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}
    window = decision.comparable_window
    assert window is not None
    assert window.sources
    assert window.chosen_because
    assert window.start <= window.end


def test_a_declared_comparison_carries_one_too(bundle: Bundle, snapshot: FreshnessSnapshot) -> None:
    """The second trigger: the request states a baseline range."""
    request = _request(comparison=Comparison(kind="period_over_period", baseline_range=JUNE))
    decision = _evaluate(bundle, snapshot, request)

    assert decision.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}
    assert decision.comparable_window is not None


def test_the_window_survives_serialisation_off_the_real_decision(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """Transport and composition together, end to end."""
    decision = _evaluate(bundle, snapshot, _request())
    restored = CatalogDecision.model_validate_json(decision.model_dump_json())
    assert restored.comparable_window == decision.comparable_window


# --- 2. the emitted window equals the gate's result exactly ------------------------


def test_the_emitted_window_equals_the_gate_result_field_for_field(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """No recomputation, no selective copy, no enrichment, no normalisation.

    Compared against the gate's own output rather than against a literal, so a
    pipeline that rebuilt a *plausible* window would fail here even if its dates
    happened to match.
    """
    request = _request()
    emitted = _evaluate(bundle, snapshot, request).comparable_window
    computed = _gate_window(bundle, snapshot, request)

    assert emitted is not None
    assert computed is not None
    assert emitted.start == computed.start
    assert emitted.end == computed.end
    assert emitted.sources == computed.sources
    assert emitted.chosen_because == computed.chosen_because
    assert emitted == computed


def test_the_governed_reason_is_carried_byte_for_byte(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """``chosen_because`` is governed wording. Not re-cased, not trimmed."""
    request = _request()
    emitted = _evaluate(bundle, snapshot, request).comparable_window
    computed = _gate_window(bundle, snapshot, request)

    assert emitted is not None
    assert computed is not None
    assert len(emitted.chosen_because) == len(computed.chosen_because)
    assert emitted.chosen_because == computed.chosen_because


def test_the_window_is_computed_from_the_rows_the_gate_walked(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """One traversal, one pairing rule.

    A second traversal with a slightly different metric-to-source pairing would
    produce a window describing coverage nobody validated — and both would look
    like plausible windows.
    """
    request = _request()
    context = GateContext(
        request=request,
        bundle=bundle,
        policy=resolve_policy(bundle.internal, on=ON).require(),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
    )
    rows = observed_rows(context)
    assert rows
    assert {row.source for row in rows} <= set(BOTH_SOURCES)
    assert comparable_window(rows) == _evaluate(bundle, snapshot, request).comparable_window


def test_publication_is_deterministic(bundle: Bundle, snapshot: FreshnessSnapshot) -> None:
    """Same request, same catalog, byte-identical decision."""
    stamp = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    first = _evaluate(bundle, snapshot, _request(), evaluated_at=stamp)
    second = _evaluate(bundle, snapshot, _request(), evaluated_at=stamp)
    assert first.model_dump_json() == second.model_dump_json()


# --- 3. a denial emits none --------------------------------------------------------


def test_a_denied_decision_from_the_real_path_carries_no_window(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """A refusal ships no evidence a consumer could execute against.

    ``downloads`` against ``sessions`` is declared not comparable in the fixture
    catalog, so this is a real gate 6 denial rather than a constructed one.
    """
    request = _request(metrics=("store_downloads", "app_sessions"), sources=BOTH_SOURCES)
    decision = _evaluate(bundle, snapshot, request)

    assert decision.outcome is Outcome.DENY
    assert decision.comparable_window is None


def test_an_authorisation_denial_carries_no_window(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """A protected refusal discloses nothing, the window included."""
    request = CatalogValidationRequest(
        metrics=("restricted_metric",),
        sources=("app_a",),
        date_range=JULY,
        requester_access=(),
    )
    decision = _evaluate(bundle, snapshot, request)

    assert decision.outcome is Outcome.DENY
    assert decision.comparable_window is None


def test_a_denial_with_no_snapshot_carries_no_window(bundle: Bundle) -> None:
    """No observed coverage is refused, never treated as unbounded."""
    decision = _evaluate(bundle, None, _request())
    assert decision.outcome is Outcome.DENY
    assert decision.comparable_window is None


# --- 4. a non-comparison ALLOW emits none ------------------------------------------


def test_a_single_source_permitted_decision_carries_no_window(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """`FR-023`: full coverage, not a narrowed window. No choice to explain.

    Attaching one would qualify an answer that was never qualified, and a reader
    would look for a narrowing that did not happen.
    """
    request = CatalogValidationRequest(
        metrics=("app_sessions",),
        sources=("app_a",),
        date_range=JULY,
        requester_access=("standard",),
    )
    decision = _evaluate(bundle, snapshot, request)

    assert decision.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}
    assert decision.comparable_window is None


def test_a_single_source_decision_that_declares_a_comparison_does_carry_one(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """The trigger is the comparison, not the source count.

    A period-over-period question on one source still has a window its answer is
    qualified by — which is exactly what `003`'s two-execution route submits.
    """
    request = CatalogValidationRequest(
        metrics=("app_sessions",),
        sources=("app_a",),
        date_range=JULY,
        comparison=Comparison(kind="period_over_period", baseline_range=JUNE),
        requester_access=("standard",),
    )
    decision = _evaluate(bundle, snapshot, request)

    assert decision.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}
    assert decision.comparable_window is not None
    assert decision.comparable_window.is_cross_source is False


# --- 5. incomplete evidence yields no executable window ----------------------------


def test_a_request_without_a_snapshot_yields_no_window(bundle: Bundle) -> None:
    """Unobserved coverage is unknown, not unbounded. Gate 7 refuses first."""
    decision = _evaluate(bundle, None, _request())
    assert decision.comparable_window is None


def test_a_snapshot_missing_the_coverage_row_yields_no_executable_window(
    bundle: Bundle,
) -> None:
    """Silence in the availability table is not coverage.

    The decision denies and states no window, so nothing downstream can execute
    against a window that was never observed.
    """
    snapshot = load_snapshot(FRESHNESS / "no_coverage_row.yaml")
    decision = _evaluate(bundle, snapshot, _request())

    assert decision.outcome is Outcome.DENY
    assert decision.comparable_window is None


def test_coverage_outside_the_period_denies_and_states_no_window(bundle: Bundle) -> None:
    snapshot = load_snapshot(FRESHNESS / "outside_coverage.yaml")
    decision = _evaluate(bundle, snapshot, _request())

    assert decision.outcome is Outcome.DENY
    assert decision.comparable_window is None


# --- 6. `002`'s reader — asserted from `002`, which is where it may be imported ----
#
# `001` depends on nothing downstream, and reaching into `analytics_query` from
# this package would invert the dependency the whole architecture rests on. The
# claim that `002`'s reader accepts a decision this evaluator produced is
# therefore made in `002`'s own suite, against this same fixture catalog:
# `packages/analytics_query/tests/integration/test_real_decision_window.py`.


# --- nothing else moved -------------------------------------------------------------


def test_the_outcome_is_unchanged_by_publication(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """Publication is disclosure, not a gate.

    The same request evaluated for its outcome and for its window returns one
    decision; there is no branch where attaching a window changes what was
    decided.
    """
    request = _request()
    decision = _evaluate(bundle, snapshot, request)
    assert decision.reason_code is not None
    assert decision.subject.id
    assert decision.evidence_refs


def test_the_decision_id_does_not_depend_on_the_window(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """`decision_id` derives from six declared inputs, and the window is not one.

    A window that entered identity would make an answer's id depend on observed
    coverage, so the same governed question would identify differently as
    coverage grew.
    """
    request = _request()
    with_window = _evaluate(bundle, snapshot, request)
    single = CatalogValidationRequest(
        metrics=CROSS_SOURCE,
        sources=("app_a",),
        date_range=JULY,
        requester_access=("standard",),
    )
    without = _evaluate(bundle, snapshot, single)

    assert with_window.comparable_window is not None
    assert without.comparable_window is None
    assert with_window.decision_id != without.decision_id  # the sources differ, not the window
