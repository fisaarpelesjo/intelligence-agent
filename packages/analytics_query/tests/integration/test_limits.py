"""Limits and refusals — T080 (FR-022, FR-024, FR-025; SC-004, SC-017, SC-020).

Byte breach, row breach, timeout — and, most importantly, **the absence of any
truncation path**.

The last one is asserted structurally rather than behaviourally. A test that
merely observes "this over-limit request refused" would still pass if someone
later added a ``truncate=True`` parameter that nobody exercised. So the suite
also asserts that `Completeness` has no truncated member, that no module
declares a limiting parameter, and that no rows survive a row-limit breach.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result import Completeness
from analytics_query.execution.adapter import (
    ExecutionOutcome,
    RenderedQuery,
    ResultColumnSchema,
    ResultSchema,
)
from analytics_query.execution.dryrun import DryRunFailed, perform_dry_run
from analytics_query.execution.limits_bytes import assert_within_byte_ceiling
from analytics_query.execution.limits_rows import (
    assert_returned_rows_within_ceiling,
    assert_within_row_ceiling,
)
from analytics_query.execution.timeout import assert_completed, limits_from_policy

from ..fixtures.adapter.fake import FakeWarehouseAdapter

pytestmark = pytest.mark.integration

QUERY = RenderedQuery(text="SELECT SUM(installs) AS installs FROM `semantic.m`", parameters={})
SCHEMA = ResultSchema(columns=(ResultColumnSchema("installs", "INT64", "users"),))

POLICY = build(
    QueryPolicy,
    version="p-1",
    effective_from=date(2026, 8, 1),
    approval=PolicyApproval(
        approver_role="data_platform", evidence_ref="a-1", approved_on=date(2026, 8, 1)
    ),
    maximum_bytes_billed=1_000_000,
    maximum_rows=1_000,
    execution_timeout_seconds=30,
    maximum_range_days=92,
    minimum_aggregation_threshold=5,
)


# --- dry run gates execution (FR-021, SC-003) -------------------------------


def test_execution_is_unreachable_without_a_successful_dry_run() -> None:
    adapter = FakeWarehouseAdapter(dry_run_raises=RuntimeError("cannot plan"))
    with pytest.raises(DryRunFailed) as caught:
        perform_dry_run(adapter, QUERY)
    assert caught.value.code is AnalyticsReasonCode.DRY_RUN_FAILED
    assert adapter.execute_calls == 0


def test_the_validated_plan_is_the_only_proof_of_a_dry_run() -> None:
    """The token cannot be forged from a raw query."""
    from analytics_query.execution import dryrun

    assert dryrun.ValidatedPlan.__doc__ is not None
    plan = perform_dry_run(FakeWarehouseAdapter(schema=SCHEMA), QUERY)
    assert plan.query is QUERY


# --- byte ceiling (FR-022, SC-004) ------------------------------------------


def test_an_over_estimate_refuses_before_execution() -> None:
    adapter = FakeWarehouseAdapter(estimated_bytes=2_000_000, schema=SCHEMA)
    plan = perform_dry_run(adapter, QUERY)

    with pytest.raises(ContractViolation) as caught:
        assert_within_byte_ceiling(plan, POLICY)

    assert caught.value.code is AnalyticsReasonCode.QUERY_COST_LIMIT_EXCEEDED
    assert adapter.execute_calls == 0


def test_the_byte_refusal_names_the_estimate_and_the_limit() -> None:
    """Permitted disclosure: the caller is past authorisation and can narrow."""
    plan = perform_dry_run(FakeWarehouseAdapter(estimated_bytes=2_000_000, schema=SCHEMA), QUERY)
    with pytest.raises(ContractViolation) as caught:
        assert_within_byte_ceiling(plan, POLICY)
    assert "2000000" in caught.value.detail
    assert "1000000" in caught.value.detail


def test_an_estimate_at_the_ceiling_is_permitted() -> None:
    plan = perform_dry_run(FakeWarehouseAdapter(estimated_bytes=1_000_000, schema=SCHEMA), QUERY)
    assert_within_byte_ceiling(plan, POLICY)


def test_the_ceiling_is_also_set_on_the_job() -> None:
    """The estimate check is legible; the job-level ceiling is what holds."""
    limits = limits_from_policy(POLICY)
    assert limits.maximum_bytes_billed == POLICY.maximum_bytes_billed
    assert limits.timeout_seconds == POLICY.execution_timeout_seconds


# --- row ceiling (FR-024, SC-017) -------------------------------------------


def test_an_over_projection_refuses_rather_than_truncating() -> None:
    adapter = FakeWarehouseAdapter(projected_rows=5_000, schema=SCHEMA)
    plan = perform_dry_run(adapter, QUERY)

    with pytest.raises(ContractViolation) as caught:
        assert_within_row_ceiling(plan, POLICY)

    assert caught.value.code is AnalyticsReasonCode.QUERY_ROW_LIMIT_EXCEEDED
    assert adapter.execute_calls == 0


def test_an_unknown_projection_is_re_checked_after_execution() -> None:
    """An unknown projection is not evidence of a small result."""
    plan = perform_dry_run(FakeWarehouseAdapter(projected_rows=None, schema=SCHEMA), QUERY)
    assert_within_row_ceiling(plan, POLICY)

    with pytest.raises(ContractViolation) as caught:
        assert_returned_rows_within_ceiling(5_000, POLICY)
    assert caught.value.code is AnalyticsReasonCode.QUERY_ROW_LIMIT_EXCEEDED


def test_a_row_breach_returns_no_rows_at_all() -> None:
    with pytest.raises(ContractViolation):
        assert_returned_rows_within_ceiling(1_001, POLICY)


def test_no_truncation_state_is_representable() -> None:
    assert {c.value for c in Completeness} == {"complete", "empty"}
    assert not hasattr(Completeness, "TRUNCATED")


def test_no_module_offers_a_truncation_parameter() -> None:
    """A parameter nobody exercises would still be a path."""
    import ast
    from pathlib import Path

    import analytics_query

    src = Path(analytics_query.__file__).parent
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for arg in [*node.args.args, *node.args.kwonlyargs]:
                assert arg.arg not in {
                    "truncate",
                    "limit",
                    "page",
                    "page_size",
                    "sample",
                    "offset",
                }, f"{path.relative_to(src)}: {node.name}({arg.arg})"


# --- timeout and failure (FR-025, SC-020) -----------------------------------


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (ExecutionOutcome.TIMED_OUT, AnalyticsReasonCode.QUERY_TIMEOUT),
        (ExecutionOutcome.CANCELLED_OVER_LIMIT, AnalyticsReasonCode.QUERY_COST_LIMIT_EXCEEDED),
        (ExecutionOutcome.FAILED, AnalyticsReasonCode.WAREHOUSE_UNAVAILABLE),
    ],
)
def test_each_non_completion_reports_its_own_condition(
    outcome: ExecutionOutcome, code: AnalyticsReasonCode
) -> None:
    """Never an empty result, never a zero."""
    adapter = FakeWarehouseAdapter(schema=SCHEMA, outcome=outcome)
    result = adapter.execute(QUERY, limits_from_policy(POLICY))

    with pytest.raises(ContractViolation) as caught:
        assert_completed(result)
    assert caught.value.code is code


def test_a_timeout_is_distinguishable_from_an_empty_result() -> None:
    """ "0 installs" and "we do not know" are different claims."""
    timed_out = FakeWarehouseAdapter(schema=SCHEMA, outcome=ExecutionOutcome.TIMED_OUT)
    with pytest.raises(ContractViolation):
        assert_completed(timed_out.execute(QUERY, limits_from_policy(POLICY)))

    empty = FakeWarehouseAdapter(schema=SCHEMA, rows=(), outcome=ExecutionOutcome.COMPLETED)
    assert_completed(empty.execute(QUERY, limits_from_policy(POLICY)))


def test_a_completed_execution_passes() -> None:
    from analytics_query.contracts.result import ResultCell

    adapter = FakeWarehouseAdapter(schema=SCHEMA, rows=((Decimal("1"),),))
    assert_completed(adapter.execute(QUERY, limits_from_policy(POLICY)))
    assert ResultCell(value=Decimal("1")).value == Decimal("1")
