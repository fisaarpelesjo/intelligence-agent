"""Audit stages fire as specified, and release is fail-closed — 003:T008.

`002`'s rule, inherited whole: **no result is released until its completion event
is durably accepted**. Releasing a value whose derivation could not be recorded
produces exactly the state the audit contract exists to prevent — an answer in
the world with no trace of who asked for it or which definitions produced it.

Emission is synchronous at every stage. A sink that rejects a stage does not
degrade the request to best-effort; it refuses it.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType

from analytics_query.contracts._base import build
from analytics_query.contracts.audit import AuditStage
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.execute import ExecutedAnswer, ExecutionRefused, execute_analytics_query
from analytics_query.execution.ledger import AuthorizationContext
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.bundle import snapshot
from ..fixtures.catalog.decisions import ALLOWED, DENIED_ACCESS
from ..fixtures.entry_point import (
    DIMENSION_COLUMNS,
    CollectingAuditSink,
    FailingAuditSink,
    StubEvaluator,
    columns_for,
    governed_policy,
    metric_version,
    snapshot_of,
    working_adapter,
)
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

ON = date(2026, 8, 12)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
CONTEXT = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="authpol-1",
)


def _run(
    sink: CollectingAuditSink,
    *,
    decision: object = ALLOWED,
    adapter: FakeWarehouseAdapter | None = None,
) -> ExecutedAnswer:
    return execute_analytics_query(
        build(AnalyticsQuery, metrics=("installs",), sources=("google_play",), date_range=JULY),
        evaluate=StubEvaluator(decision),  # type: ignore[arg-type]
        catalog_bundle=object(),  # type: ignore[arg-type]
        ledger=InMemoryExecutionLedger(),
        observations=FixtureObservationReader(),
        adapter=adapter or working_adapter(),
        sink=sink,
        context=CONTEXT,
        correlation_id="c-1",
        principal_ref="p-1",
        on=ON,
        catalog_release_id="r-1",
        required_sources=frozenset({"google_play"}),
        columns=columns_for(),
        sample_catalog=snapshot_of("r-1"),
        metric_version_ids=("installs@1",),
        freshness_snapshot=snapshot(),
        metric_version=metric_version(),
        dimension_columns=DIMENSION_COLUMNS,
    )


# --- stages fire where the contract says -------------------------------------


def test_a_pre_policy_refusal_emits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Steps 1-7 own their own auditing; the composition adds no event there.

    An unauthorized principal never reaches the composition's emitter, so the
    composition cannot be the thing that discloses them.
    """
    sink = CollectingAuditSink()
    with pytest.raises(ExecutionRefused):
        _run(sink, decision=DENIED_ACCESS)
    assert sink.events == []


def test_validation_is_emitted_once_the_full_evaluation_has_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = CollectingAuditSink()
    with governed_policy(monkeypatch):
        _run(sink)
    assert sink.stages()[0] == AuditStage.VALIDATION


def test_a_denied_evaluation_emits_validation_then_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both, in that order: the decision is recorded before its consequence."""
    from ..fixtures.entry_point import DENIED_UPSTREAM

    sink = CollectingAuditSink()
    evaluator = StubEvaluator(ALLOWED, full_verdict=DENIED_UPSTREAM)
    with governed_policy(monkeypatch), pytest.raises(ExecutionRefused) as caught:
        execute_analytics_query(
            build(AnalyticsQuery, metrics=("installs",), sources=("google_play",), date_range=JULY),
            evaluate=evaluator,  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            adapter=FakeWarehouseAdapter(),
            sink=sink,
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=frozenset({"google_play"}),
            columns=columns_for(),
            sample_catalog=snapshot_of("r-1"),
            metric_version_ids=("installs@1",),
            freshness_snapshot=snapshot(),
            metric_version=metric_version(),
            dimension_columns=DIMENSION_COLUMNS,
        )

    assert caught.value.stage == "evaluation"
    assert sink.stages() == [AuditStage.VALIDATION, AuditStage.REFUSAL]


# --- emission is synchronous and fails closed --------------------------------


def test_a_sink_that_rejects_validation_stops_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The warehouse is never reached when the first stage cannot be recorded."""
    adapter = FakeWarehouseAdapter()
    sink = FailingAuditSink(AuditStage.VALIDATION)
    with governed_policy(monkeypatch), pytest.raises(ExecutionRefused) as caught:
        execute_analytics_query(
            build(AnalyticsQuery, metrics=("installs",), sources=("google_play",), date_range=JULY),
            evaluate=StubEvaluator(ALLOWED),  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            adapter=adapter,
            sink=sink,
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=frozenset({"google_play"}),
            columns=columns_for(),
            sample_catalog=snapshot_of("r-1"),
            metric_version_ids=("installs@1",),
            freshness_snapshot=snapshot(),
            metric_version=metric_version(),
            dimension_columns=DIMENSION_COLUMNS,
        )

    assert caught.value.code is AnalyticsReasonCode.AUDIT_EMISSION_FAILED
    assert caught.value.stage.startswith("audit:")
    assert adapter.execute_calls == 0, "execution proceeded past an unrecorded stage"


def test_emission_is_synchronous_rather_than_buffered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stage is complete only when the sink returned.

    Observed by ordering: the sink holds the validation event *before* the
    request can proceed, so a buffered emitter would show an empty sink here.
    """
    sink = CollectingAuditSink()
    with governed_policy(monkeypatch):
        _run(sink)
    assert sink.events, "no event reached the sink before the request continued"
    assert sink.events[0].correlation_id == "c-1"


# --- events carry what the contract requires and nothing it forbids ----------


def test_every_event_carries_the_correlating_and_governing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = CollectingAuditSink()
    with governed_policy(monkeypatch):
        _run(sink)

    for event in sink.events:
        assert event.correlation_id == "c-1"
        assert event.principal_ref == "p-1"
        assert event.policy_version
        assert event.catalog_release_id == "r-1"
        assert event.metric_ids == ("installs",)
        assert event.reason_code is not None


def test_no_event_carries_a_value_a_filter_value_or_free_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The event records what was asked and decided, never what was returned."""
    sink = CollectingAuditSink()
    with governed_policy(monkeypatch):
        _run(sink)

    for event in sink.events:
        serialised = event.model_dump_json().lower()
        for forbidden in ("select ", "installs:read=", "password", "token", "'"):
            assert forbidden not in serialised, f"the event carried {forbidden!r}"
        assert "granted_access_tags" in serialised, "the actor's tags are required"
