"""End-to-end emitter test — T081 (FR-043; SC-014).

Tests the integration (T075), not the contract.

Evidence: **one fully populated event per ALLOW and per DENY**, access refusals
included. An audit that skips refusals cannot answer "who was refused", and one
that skips allows cannot answer "what was this principal permitted to see".

Also asserts the property that separates an audit from a log: a suppressed
emission **raises**. A decision that happened beside an audit that says it did
not is worse than no audit — it is one that looks complete and lies by omission.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.audit_event import (
    CatalogDecisionAuditEvent,
    EvidenceKind,
    RequestedOperation,
)
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.provenance.audit_emit import (
    AuditEmissionError,
    CollectingSink,
    EvaluatedDecision,
    evaluate_and_emit,
)
from semantic_catalog.provenance.revision import load_revisions
from semantic_catalog.validation.decision import (
    CatalogValidationRequest,
    DateRange,
    Finality,
    Reproducibility,
)

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CATALOG = FIXTURES / "decision_matrix" / "catalog"
FRESHNESS = FIXTURES / "freshness"
REVISIONS = FIXTURES / "revisions"

ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
PRINCIPAL = "prn_" + "c" * 24


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
    sink: CollectingSink,
    *,
    metrics: tuple[str, ...] = ("app_sessions",),
    sources: tuple[str, ...] = ("app_a",),
    access: tuple[str, ...] = ("standard",),
    scope: str = "default",
    freshness: str | None = "complete.yaml",
    revisions: str | None = "app_a_stable.yaml",
    supersedes: str | None = None,
) -> EvaluatedDecision:
    return evaluate_and_emit(
        CatalogValidationRequest(
            metrics=metrics, sources=sources, date_range=WINDOW, requester_access=access
        ),
        bundle,
        sink,
        principal_id=PRINCIPAL,
        principal_type=PrincipalType.USER,
        authorization_scope=scope,
        correlation_id="corr-1",
        on=ON,
        snapshot=load_snapshot(FRESHNESS / freshness) if freshness else None,
        revisions=load_revisions(REVISIONS / revisions) if revisions else None,
        supersedes_decision_id=supersedes,
    )


# --- one event per outcome --------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, Outcome.ALLOW),
        ({"access": ()}, Outcome.DENY),
        ({"metrics": ("nao_existe",)}, Outcome.DENY),
        ({"metrics": ("deprecated_metric",)}, Outcome.ALLOW_WITH_CAVEAT),
        ({"freshness": "beyond_tolerance.yaml"}, Outcome.DENY),
        ({"metrics": ("restricted_metric",)}, Outcome.DENY),
    ],
)
def test_exactly_one_event_per_decision(
    bundle: Bundle, kwargs: dict[str, object], expected: Outcome
) -> None:
    sink = CollectingSink()
    result = _run(bundle, sink, **kwargs)  # type: ignore[arg-type]
    assert result.decision.outcome is expected
    assert sink.count == 1, "one decision, one event"
    assert sink.events[0].decision_id == result.decision.decision_id


def test_an_access_refusal_is_audited(bundle: Bundle) -> None:
    """The refusal an audit exists for. Skipping it is the classic failure."""
    sink = CollectingSink()
    result = _run(bundle, sink, access=())
    assert result.decision.reason_code is ReasonCode.ACCESS_DENIED
    assert sink.count == 1
    assert sink.events[0].outcome is Outcome.DENY
    assert sink.events[0].reason_code is ReasonCode.ACCESS_DENIED
    assert sink.events[0].principal_id == PRINCIPAL


def test_every_event_is_fully_populated(bundle: Bundle) -> None:
    sink = CollectingSink()
    _run(bundle, sink)
    event = sink.events[0]
    assert event.correlation_id
    assert event.decision_id
    assert event.principal_id and event.principal_type
    assert event.requested_operation is RequestedOperation.VALIDATE
    assert event.metric_ids == ("app_sessions",)
    assert event.source_ids == ("app_a",)
    assert event.date_range is not None
    assert event.granted_access_tags == ("standard",)
    assert event.policy_version and event.catalog_release_id
    assert event.resolved_versions == ("app_sessions@1",)
    assert event.evidence_refs


def test_ten_decisions_produce_ten_events(bundle: Bundle) -> None:
    sink = CollectingSink()
    for _ in range(10):
        _run(bundle, sink)
    assert sink.count == 10
    assert len({e.principal_id for e in sink.events}) == 1


# --- provenance on the event ------------------------------------------------


def test_the_event_carries_the_data_revision(bundle: Bundle) -> None:
    sink = CollectingSink()
    _run(bundle, sink)
    kinds = {ref.kind for ref in sink.events[0].evidence_refs}
    assert EvidenceKind.DATA_REVISION in kinds
    assert any(ref.id == "app_a@rev3" for ref in sink.events[0].evidence_refs)


def test_the_event_records_the_final_decision_id(bundle: Bundle) -> None:
    """An event citing a pre-evidence id could never be joined to the answer."""
    sink = CollectingSink()
    result = _run(bundle, sink)
    assert result.decision.finality is Finality.FINAL
    assert sink.events[0].decision_id == result.decision.decision_id


def test_a_limited_decision_is_still_audited(bundle: Bundle) -> None:
    sink = CollectingSink()
    result = _run(bundle, sink, revisions=None)
    assert result.decision.reproducibility is Reproducibility.LIMITED
    assert result.decision.finality is Finality.PRE_EVIDENCE
    assert sink.count == 1


# --- the event carries no forbidden content ---------------------------------


def test_no_event_carries_a_value_a_row_or_prompt_text(bundle: Bundle) -> None:
    sink = CollectingSink()
    for kwargs in ({}, {"access": ()}, {"metrics": ("deprecated_metric",)}):
        _run(bundle, sink, **kwargs)  # type: ignore[arg-type]
    for event in sink.events:
        serialised = str(event.model_dump(mode="json"))
        for forbidden in ("calculation_basis", "@example.com", "Bearer", "password="):
            assert forbidden not in serialised, forbidden


def test_the_event_names_only_governed_identifiers(bundle: Bundle) -> None:
    sink = CollectingSink()
    _run(bundle, sink)
    event = sink.events[0]
    assert all(m in bundle.internal.metrics for m in event.metric_ids)
    assert all(s in bundle.internal.sources for s in event.source_ids)


# --- a suppressed emission raises -------------------------------------------


def test_a_refusing_sink_raises_rather_than_passing_silently(bundle: Bundle) -> None:
    def _refuse(event: CatalogDecisionAuditEvent) -> None:
        raise RuntimeError("sink unavailable")

    with pytest.raises(AuditEmissionError, match="refused the event"):
        evaluate_and_emit(
            CatalogValidationRequest(
                metrics=("app_sessions",),
                sources=("app_a",),
                date_range=WINDOW,
                requester_access=("standard",),
            ),
            bundle,
            _refuse,
            principal_id=PRINCIPAL,
            principal_type=PrincipalType.USER,
            authorization_scope="default",
            correlation_id="corr-1",
            on=ON,
            snapshot=load_snapshot(FRESHNESS / "complete.yaml"),
            revisions=load_revisions(REVISIONS / "app_a_stable.yaml"),
        )


def test_a_contract_violation_fails_before_reaching_the_sink(bundle: Bundle) -> None:
    """Construction precedes emission, so a bad event never lands anywhere."""
    sink = CollectingSink()
    with pytest.raises(Exception):  # noqa: B017 - contract raises its own type
        evaluate_and_emit(
            CatalogValidationRequest(
                metrics=("app_sessions",),
                sources=("app_a",),
                date_range=WINDOW,
                requester_access=("standard",),
            ),
            bundle,
            sink,
            principal_id="maria.silva@example.com",
            principal_type=PrincipalType.USER,
            authorization_scope="default",
            correlation_id="corr-1",
            on=ON,
            snapshot=load_snapshot(FRESHNESS / "complete.yaml"),
        )
    assert sink.count == 0, "a rejected event must not reach the sink"
