"""Provenance on every decision — T074 (FR-039, SC-008; Principle III).

Constitution Principle III: *every answer MUST carry its provenance* —
contributing sources, data-as-of timestamp, source update time, dimensional
coverage, and known limitations. Not "be sufficient to reconstruct with the
right side inputs": **carry**.

How each of the five is represented, exercised through the real
``evaluate_and_emit`` path rather than by constructing objects by hand:

| Requirement | Where it lives |
|---|---|
| contributing sources | ``decision.freshness[].source`` with its ``required`` flag |
| data-as-of | ``freshness_snapshot`` evidence ref, ``{source}@{observed_at}`` |
| source update time | ``decision.freshness[].last_successful_update`` |
| coverage | ``coverage_window`` evidence ref, ``{metric}:{source}:{from}:{to}`` |
| limitations | ``decision.limitations[]`` |

The identifier forms are the governed ones from research §identifier scheme, so
data-as-of and coverage are carried without inventing a contract field.

**Authorisation refusals carry none of it.** Listing a metric's contributing
sources, their states and their update times on an ACCESS_DENIED would hand the
requester the shape of a metric they may not see — the exact disclosure Gate 3
runs before Gate 4 to prevent.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.audit_event import EvidenceKind
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.provenance.audit_emit import (
    CollectingSink,
    EvaluatedDecision,
    evaluate_and_emit,
)
from semantic_catalog.provenance.evidence import provenance_for
from semantic_catalog.provenance.revision import load_revisions, resolve_revisions
from semantic_catalog.validation.decision import CatalogValidationRequest, DateRange

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CATALOG = FIXTURES / "decision_matrix" / "catalog"
FRESHNESS = FIXTURES / "freshness"
REVISIONS = FIXTURES / "revisions"

ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
PRINCIPAL = "prn_" + "p" * 24


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        CATALOG,
        current_commit="fixture0",
        on=ON,
        source_commits={"app_a": "fixture0", "store_a": "fixture0"},
    )


def _run(
    bundle: Bundle,
    *,
    metrics: tuple[str, ...] = ("app_sessions",),
    sources: tuple[str, ...] = ("app_a",),
    access: tuple[str, ...] = ("standard",),
    scope: str = "default",
    freshness: str | None = "complete.yaml",
    revisions: str | None = "app_a_stable.yaml",
    sink: CollectingSink | None = None,
) -> EvaluatedDecision:
    return evaluate_and_emit(
        CatalogValidationRequest(
            metrics=metrics, sources=sources, date_range=WINDOW, requester_access=access
        ),
        bundle,
        sink or CollectingSink(),
        principal_id=PRINCIPAL,
        principal_type=PrincipalType.USER,
        authorization_scope=scope,
        correlation_id="corr-prov",
        on=ON,
        snapshot=load_snapshot(FRESHNESS / freshness) if freshness else None,
        revisions=load_revisions(REVISIONS / revisions) if revisions else None,
    )


def _kinds(result: EvaluatedDecision) -> set[EvidenceKind]:
    return {ref.kind for ref in result.decision.evidence_refs}


# --- the five elements, on every applicable outcome -------------------------


@pytest.mark.parametrize(
    "label, kwargs, expected",
    [
        ("allow", {}, Outcome.ALLOW),
        ("caveat_deprecated", {"metrics": ("deprecated_metric",)}, Outcome.ALLOW_WITH_CAVEAT),
        (
            "caveat_lagging",
            {"freshness": "lagging_within_tolerance.yaml"},
            Outcome.ALLOW_WITH_CAVEAT,
        ),
        ("deny_stale", {"freshness": "beyond_tolerance.yaml"}, Outcome.DENY),
        ("deny_unknown", {"freshness": "unknown.yaml"}, Outcome.DENY),
    ],
)
def test_every_applicable_decision_carries_all_five(
    bundle: Bundle, label: str, kwargs: dict[str, object], expected: Outcome
) -> None:
    result = _run(bundle, **kwargs)  # type: ignore[arg-type]
    decision = result.decision
    assert decision.outcome is expected, label

    # 1 contributing sources, with the required flag that makes them meaningful
    assert decision.freshness, label
    assert all(v.source for v in decision.freshness), label
    assert any(v.required for v in decision.freshness), label

    # 2 data-as-of, inside the governed freshness_snapshot identifier
    assert EvidenceKind.FRESHNESS_SNAPSHOT in _kinds(result), label

    # 3 source update time — present whenever the source ever loaded
    for verdict in decision.freshness:
        if verdict.status != "unknown":
            assert verdict.last_successful_update is not None, f"{label}:{verdict.source}"

    # 4 coverage, inside the governed coverage_window identifier
    assert EvidenceKind.COVERAGE_WINDOW in _kinds(result), label

    # 5 limitations — the field always travels, empty when nothing qualifies
    assert decision.limitations is not None, label


def test_the_data_as_of_instant_is_recoverable_from_the_reference(bundle: Bundle) -> None:
    """The identifier form is `{source}@{observed_at}`, so the instant is in it."""
    result = _run(bundle)
    snapshot = load_snapshot(FRESHNESS / "complete.yaml")
    refs = [r for r in result.decision.evidence_refs if r.kind is EvidenceKind.FRESHNESS_SNAPSHOT]
    assert refs
    assert all(ref.id.startswith("app_a@") for ref in refs)
    assert snapshot.snapshot_id is not None
    assert all(snapshot.snapshot_id in ref.id for ref in refs)


def test_the_coverage_window_is_recoverable_from_the_reference(bundle: Bundle) -> None:
    result = _run(bundle)
    refs = [r for r in result.decision.evidence_refs if r.kind is EvidenceKind.COVERAGE_WINDOW]
    assert refs
    assert any(ref.id == "app_sessions:app_a:2026-01-01:2026-08-10" for ref in refs)


def test_the_source_update_time_is_the_observed_one(bundle: Bundle) -> None:
    result = _run(bundle)
    verdict = next(v for v in result.decision.freshness if v.source == "app_a")
    record = load_snapshot(FRESHNESS / "complete.yaml").record_for("app_a")
    assert record is not None
    assert verdict.last_successful_update == record.last_successful_update
    assert verdict.tolerance == bundle.internal.sources["app_a"].delay_tolerance


def test_a_named_but_unused_source_is_reported_as_not_required(bundle: Bundle) -> None:
    """A reader must be able to see the stale source was not the reason."""
    result = _run(
        bundle,
        metrics=("store_downloads",),
        sources=("store_a", "app_a"),
        freshness="android_beyond_tolerance.yaml",
        revisions=None,
    )
    by_source = {v.source: v for v in result.decision.freshness}
    assert by_source["store_a"].required
    assert not by_source["app_a"].required
    assert result.decision.outcome is not Outcome.DENY


# --- authorisation refusals disclose nothing --------------------------------


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"access": ()}, ReasonCode.ACCESS_DENIED),
        ({"metrics": ("restricted_metric",)}, ReasonCode.ACCESS_TAG_SCOPE_MISMATCH),
        (
            {"metrics": ("retired_metric",), "access": ("retired_tag",)},
            ReasonCode.ACCESS_TAG_DEPRECATED,
        ),
    ],
)
def test_an_authorisation_refusal_leaks_no_source_metadata(
    bundle: Bundle, kwargs: dict[str, object], code: ReasonCode
) -> None:
    result = _run(bundle, **kwargs)  # type: ignore[arg-type]
    decision = result.decision
    assert decision.reason_code is code
    assert decision.freshness == (), "a refusal must not name contributing sources"
    assert decision.data_revisions == (), "a revision id names the source it belongs to"
    assert EvidenceKind.FRESHNESS_SNAPSHOT not in _kinds(result)
    assert EvidenceKind.COVERAGE_WINDOW not in _kinds(result)
    assert EvidenceKind.DATA_REVISION not in _kinds(result)


def test_an_unknown_metric_discloses_nothing_either(bundle: Bundle) -> None:
    result = _run(bundle, metrics=("nao_existe",))
    assert result.decision.reason_code is ReasonCode.METRIC_NOT_GOVERNED
    assert result.decision.freshness == ()
    assert _kinds(result) == {EvidenceKind.CATALOG_RELEASE}


def test_the_audit_event_of_a_refusal_carries_no_source_state(bundle: Bundle) -> None:
    sink = CollectingSink()
    _run(bundle, access=(), sink=sink)
    event = sink.events[0]
    assert not [r for r in event.evidence_refs if r.kind is EvidenceKind.FRESHNESS_SNAPSHOT]
    assert not [r for r in event.evidence_refs if r.kind is EvidenceKind.DATA_REVISION]
    # source_ids echo what the requester asked for; that is not a disclosure.
    assert event.source_ids == ("app_a",)


# --- absent evidence never becomes a successful decision --------------------


def test_a_missing_snapshot_cannot_produce_a_successful_decision(bundle: Bundle) -> None:
    result = _run(bundle, freshness=None)
    assert result.decision.outcome is Outcome.DENY
    assert result.decision.reason_code is ReasonCode.SOURCE_STATE_UNKNOWN
    assert EvidenceKind.COVERAGE_WINDOW not in _kinds(result)


def test_an_unknown_source_state_reports_no_update_time_rather_than_a_guess(
    bundle: Bundle,
) -> None:
    """Nothing is inferred. Unknown stays unknown."""
    result = _run(bundle, freshness="unknown.yaml")
    verdict = next(v for v in result.decision.freshness if v.source == "app_a")
    assert verdict.status == "unknown"
    assert verdict.last_successful_update is None
    assert verdict.lag is None


# --- the assembled statement ------------------------------------------------


def test_the_provenance_statement_assembles_from_the_decision(bundle: Bundle) -> None:
    result = _run(bundle)
    snapshot = load_snapshot(FRESHNESS / "complete.yaml")
    resolution = resolve_revisions(
        ("app_a",),
        load_revisions(REVISIONS / "app_a_stable.yaml"),
        period_start=WINDOW.start,
        period_end=WINDOW.end,
    )
    statement = provenance_for(
        result.decision, ("app_a",), snapshot, resolution, metric_ids=("app_sessions",)
    )
    assert statement.is_sufficient
    assert [s.source for s in statement.sources] == ["app_a"]
    assert statement.data_as_of == snapshot.observed_at
    assert isinstance(statement.data_as_of, datetime)
    source = statement.sources[0]
    assert source.last_successful_update is not None
    assert source.coverage_start == date(2026, 1, 1)
    assert source.coverage_end == date(2026, 8, 10)
    assert source.data_revision_id == "app_a@rev3"
    assert source.is_complete_evidence
    assert "app_a" in statement.describe()


# --- nothing else regressed -------------------------------------------------


def test_provenance_does_not_disturb_decision_identity(bundle: Bundle) -> None:
    """Evidence refs are not a decision_id input; adding them changes no id."""
    first, second = _run(bundle), _run(bundle)
    assert first.decision.decision_id == second.decision.decision_id


def test_provenance_does_not_disturb_finality(bundle: Bundle) -> None:
    stable = _run(bundle)
    without = _run(bundle, revisions=None)
    assert stable.decision.is_final
    assert not without.decision.is_final
    assert without.decision.reproducibility.value == "limited"
