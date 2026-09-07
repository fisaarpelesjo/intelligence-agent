"""The composed entry point decides exactly what the pipeline decides — 003:T002.

ADR 0010 adds a composition, not a behaviour. Steps 1-8 must reach the same
decision and the same governed reason code whether they are reached through
``run_until_evaluation`` directly or through ``execute_analytics_query``.

The check is a comparison, not an inspection: both paths are driven over the
same cases and their outcomes are compared. A composition that quietly reordered
a gate, swallowed a refusal or substituted a code would diverge here rather than
be caught by reading the source.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType

from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.execute import ExecutionRefused, execute_analytics_query
from analytics_query.execution.ledger import AuthorizationContext
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.pipeline import PipelineRefusal, run_until_evaluation

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.bundle import snapshot
from ..fixtures.catalog.decisions import ALLOWED, DENIED_ACCESS
from ..fixtures.entry_point import (
    DENIED_UPSTREAM,
    DIMENSION_COLUMNS,
    CollectingAuditSink,
    StubEvaluator,
    columns_for,
    governed_policy,
    metric_version,
    snapshot_of,
    working_adapter,
)
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.contract

ON = date(2026, 8, 12)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
SOURCES = frozenset({"google_play"})
CONTEXT = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="authpol-1",
)

#: Every case `002` can reach before execution. Each must decide identically on
#: both paths — the permissive one included, which stops the comparison from
#: being satisfied by "both refuse".
CASES = [
    pytest.param(DENIED_ACCESS, "authorization", id="authorization-denied"),
    pytest.param(DENIED_UPSTREAM, "upstream", id="upstream-denied"),
    pytest.param(ALLOWED, None, id="permitted"),
]


def _request() -> AnalyticsQuery:
    return build(AnalyticsQuery, metrics=("installs",), sources=("google_play",), date_range=JULY)


def _via_pipeline(decision: object) -> tuple[str, object]:
    try:
        state = run_until_evaluation(
            _request(),
            evaluate=StubEvaluator(decision),  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=SOURCES,
        )
    except PipelineRefusal as refusal:
        return refusal.stage, refusal.code
    return "evaluated", state.decision.outcome


def _via_entry_point(decision: object) -> tuple[str, object]:
    try:
        answer = execute_analytics_query(
            _request(),
            evaluate=StubEvaluator(decision),  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            adapter=FakeWarehouseAdapter(),
            sink=CollectingAuditSink(),
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=SOURCES,
            columns=columns_for(),
            sample_catalog=snapshot_of("r-1"),
            metric_version_ids=("installs@1",),
            freshness_snapshot=snapshot(),
            metric_version=metric_version(),
            dimension_columns=DIMENSION_COLUMNS,
        )
    except ExecutionRefused as refusal:
        return refusal.stage, refusal.code
    return "evaluated", answer.decision.outcome


@pytest.mark.parametrize(("decision", "expected_stage"), CASES)
def test_both_paths_reach_the_same_stage_and_code(
    decision: object, expected_stage: str | None
) -> None:
    through_pipeline = _via_pipeline(decision)
    through_entry_point = _via_entry_point(decision)
    if expected_stage is not None:
        assert through_pipeline[0] == expected_stage
    assert through_entry_point[0] == through_pipeline[0], (
        "the entry point stopped at a different stage than the pipeline"
    )
    assert through_entry_point[1] == through_pipeline[1], (
        "the entry point produced a different governed outcome than the pipeline"
    )


def test_a_refusal_keeps_the_upstream_reason_code_verbatim() -> None:
    """`002` never restates an upstream refusal, and neither may the composition."""
    stage, code = _via_entry_point(DENIED_UPSTREAM)
    assert stage == "upstream"
    assert code == DENIED_UPSTREAM.reason_code


def test_the_entry_point_delegates_steps_one_to_eight_rather_than_repeating_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One evaluation per phase, exactly as the pipeline performs it.

    A composition that re-ran the preflight, or evaluated a third time to "be
    sure", would be forming its own view of a governance verdict.

    Needs a resolvable policy to reach the second evaluation at all: the
    repository holds no approved instance, which is `002`'s third lock.
    """
    evaluator = StubEvaluator(ALLOWED)
    with governed_policy(monkeypatch):
        _reach_evaluation(evaluator)
    assert evaluator.calls == 2, "expected exactly the preflight and the full evaluation"
    assert evaluator.snapshots[0] is None, "the preflight must pass no snapshot"
    assert evaluator.snapshots[1] is not None, "the full evaluation must pass the snapshot"


def _reach_evaluation(evaluator: StubEvaluator) -> None:
    execute_analytics_query(
        _request(),
        evaluate=evaluator,  # type: ignore[arg-type]
        catalog_bundle=object(),  # type: ignore[arg-type]
        ledger=InMemoryExecutionLedger(),
        observations=FixtureObservationReader(),
        adapter=working_adapter(),
        sink=CollectingAuditSink(),
        context=CONTEXT,
        correlation_id="c-1",
        principal_ref="p-1",
        on=ON,
        catalog_release_id="r-1",
        required_sources=SOURCES,
        columns=columns_for(),
        sample_catalog=snapshot_of("r-1"),
        metric_version_ids=("installs@1",),
        freshness_snapshot=snapshot(),
        metric_version=metric_version(),
        dimension_columns=DIMENSION_COLUMNS,
    )
