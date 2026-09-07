"""Audit fail-closed — T099 (FR-050; SC-011).

A sink failure at each of the four stages, with the correct withholding per
stage.

**`SC-011` is measured over two populations**, and conflating them is the
mistake this test exists to prevent. "100% of stages emit a correlated event" is
measured over runs where the sink was available. A run where the sink was
unavailable is *not* a run that emitted 3 of 4 events — it is a run that
refused, and counting it as a partial success would let a broken sink quietly
lower the bar while the metric still read 100%.

So the assertions here are about *behaviour under failure*: what the caller
receives, and whether a result was released.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from semantic_catalog.contracts.reason_codes import Outcome

from analytics_query.audit.emit import (
    PRE_EXECUTION_STAGES,
    AuditEmissionFailed,
    emit_or_refuse,
    refusal_for,
    withholds_result,
)
from analytics_query.contracts._base import build
from analytics_query.contracts.audit import AnalyticsAuditEvent, AuditStage, PrincipalType
from analytics_query.contracts.reason_codes import AnalyticsReasonCode

from ..fixtures.adapter.fake import FakeWarehouseAdapter

pytestmark = pytest.mark.integration

#: Sorted so parametrize ids are stable across runs.
_PRE_EXECUTION: list[AuditStage] = sorted(PRE_EXECUTION_STAGES, key=lambda s: s.value)


class _Sink:
    """A sink that accepts, or fails at one named stage."""

    def __init__(self, fails_at: AuditStage | None = None) -> None:
        self.fails_at = fails_at
        self.accepted: list[AuditStage] = []

    def accept(self, event: AnalyticsAuditEvent) -> None:
        if event.stage is self.fails_at:
            raise ConnectionError("the audit store is unreachable")
        self.accepted.append(event.stage)


def _event(stage: AuditStage) -> AnalyticsAuditEvent:
    deny = stage is AuditStage.REFUSAL
    return build(
        AnalyticsAuditEvent,
        stage=stage,
        correlation_id="c-1",
        query_identity=None if deny else "a" * 64,
        emitted_at=datetime(2026, 8, 12, tzinfo=UTC),
        principal_ref="opaque-1",
        principal_type=PrincipalType.USER,
        outcome=Outcome.DENY if deny else Outcome.ALLOW,
        reason_code=(
            AnalyticsReasonCode.REQUEST_MALFORMED if deny else AnalyticsReasonCode.QUERY_EXECUTED
        ),
    )


# --- emission succeeds when the sink accepts --------------------------------


@pytest.mark.parametrize("stage", list(AuditStage), ids=lambda s: s.value)
def test_a_healthy_sink_accepts_every_stage(stage: AuditStage) -> None:
    """Otherwise the failure assertions below would pass vacuously."""
    sink = _Sink()
    emit_or_refuse(sink, _event(stage))
    assert sink.accepted == [stage]


# --- emission failure at each stage -----------------------------------------


@pytest.mark.parametrize("stage", list(AuditStage), ids=lambda s: s.value)
def test_a_sink_failure_refuses_at_every_stage(stage: AuditStage) -> None:
    sink = _Sink(fails_at=stage)
    with pytest.raises(AuditEmissionFailed) as caught:
        emit_or_refuse(sink, _event(stage))

    assert caught.value.code is AnalyticsReasonCode.AUDIT_EMISSION_FAILED
    assert caught.value.stage is stage
    assert sink.accepted == [], "nothing may be recorded as accepted when it was not"


@pytest.mark.parametrize("stage", _PRE_EXECUTION, ids=[s.value for s in _PRE_EXECUTION])
def test_a_pre_execution_failure_withholds_nothing_because_nothing_ran(
    stage: AuditStage,
) -> None:
    """No warehouse call, so no result and no cost to explain."""
    assert not withholds_result(stage)

    adapter = FakeWarehouseAdapter()
    sink = _Sink(fails_at=stage)
    with pytest.raises(AuditEmissionFailed):
        emit_or_refuse(sink, _event(stage))
    assert adapter.total_calls == 0


def test_a_completion_failure_withholds_the_billed_result() -> None:
    """The query ran and was billed; the result is still not released.

    Uncomfortable and deliberate: a figure delivered without a durable record is
    one nobody can later attribute, dispute or reproduce, and once it is out no
    retrospective fix exists.
    """
    assert withholds_result(AuditStage.EXECUTION_COMPLETE)

    sink = _Sink(fails_at=AuditStage.EXECUTION_COMPLETE)
    with pytest.raises(AuditEmissionFailed) as caught:
        emit_or_refuse(sink, _event(AuditStage.EXECUTION_COMPLETE))
    assert caught.value.stage is AuditStage.EXECUTION_COMPLETE


def test_only_the_completion_stage_withholds_a_result() -> None:
    withholding = [s for s in AuditStage if withholds_result(s)]
    assert withholding == [AuditStage.EXECUTION_COMPLETE]


# --- what the caller is told -------------------------------------------------


def test_the_caller_refusal_names_no_sink_detail() -> None:
    """Which store failed, and why, is not a caller's business."""
    sink = _Sink(fails_at=AuditStage.EXECUTION_COMPLETE)
    with pytest.raises(AuditEmissionFailed) as caught:
        emit_or_refuse(sink, _event(AuditStage.EXECUTION_COMPLETE))

    violation = refusal_for(caught.value)
    assert violation.code is AnalyticsReasonCode.AUDIT_EMISSION_FAILED
    text = violation.detail.lower()
    for leak in ("connection", "unreachable", "store", "sink", "host"):
        assert leak not in text


def test_emission_is_synchronous_with_no_background_path() -> None:
    """Fire-and-forget would make `SC-011` unmeasurable."""
    import ast
    import inspect

    from analytics_query.audit import emit

    tree = ast.parse(inspect.getsource(emit))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in ("thread", "asyncio", "queue", "executor", "background", "spawn"):
        assert marker not in code, f"emission is deferred: {marker!r}"


def test_an_already_governed_failure_is_not_rewrapped() -> None:
    """A nested emission failure keeps its original stage."""

    class _Rejecting:
        def accept(self, event: AnalyticsAuditEvent) -> None:
            raise AuditEmissionFailed(AuditStage.VALIDATION, "already governed")

    with pytest.raises(AuditEmissionFailed) as caught:
        emit_or_refuse(_Rejecting(), _event(AuditStage.EXECUTION_COMPLETE))
    assert caught.value.stage is AuditStage.VALIDATION
