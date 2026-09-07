"""Execution, results, provenance and recovery — T088-T097, T100.

Covers FR-023, FR-029, FR-031, FR-032, FR-037, FR-038, FR-039, FR-040, FR-041,
FR-042, FR-043, FR-044, FR-045, FR-054, FR-055, FR-056, FR-072, FR-078 and
SC-002, SC-005, SC-006, SC-007, SC-011, SC-018, SC-020, SC-028. Phase 9's test
tasks (T098, T099) cover the audit denylist and fail-closed emission; everything
else in the phase states its evidence here rather than leaving it a claim
nobody checks.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from analytics_query.audit.recovery import (
    STAGE_ORDER,
    RecoveryPlan,
    plan_recovery,
    stages_outstanding,
)
from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.audit import AuditStage
from analytics_query.contracts.comparable_window import ComparableWindow
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.provenance import CostProvenance
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result import (
    AnalyticsResult,
    Completeness,
    ResultCell,
    ResultColumn,
    ResultRow,
)
from analytics_query.contracts.result_provenance import (
    REQUIRED_ELEMENTS,
    ResultProvenance,
    SourceUpdate,
)
from analytics_query.execution.adapter import (
    ExecutionOutcome,
    ExecutionResult,
    RenderedQuery,
    ResultColumnSchema,
    ResultSchema,
)
from analytics_query.execution.dryrun import perform_dry_run
from analytics_query.execution.failures import FailureClass, classify_failure, refuse_for_failure
from analytics_query.execution.ledger import (
    AuthorizationContext,
    ExecutionKey,
    derive_authorization_fingerprint,
)
from analytics_query.execution.ledger_entry import ExecutionStatus
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.execution.midflight import CatalogSnapshot, assert_catalog_unchanged
from analytics_query.execution.run import assert_execution_completed, execute_bounded
from analytics_query.results.assemble import assemble_result, to_cell
from analytics_query.results.completeness import ResultKind, classify_result
from analytics_query.results.model_surface import to_model_payload

from ..fixtures.adapter.fake import FakeWarehouseAdapter

pytestmark = pytest.mark.unit

QUERY = RenderedQuery(text="SELECT SUM(installs) AS installs FROM `semantic.m`", parameters={})
SCHEMA = ResultSchema(columns=(ResultColumnSchema("installs", "INT64", "users"),))
COLUMNS = (ResultColumn(identifier="installs", unit="users", is_metric=True),)

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


# --- T088: bounded execution -------------------------------------------------


def test_a_completed_execution_yields_its_rows() -> None:
    adapter = FakeWarehouseAdapter(schema=SCHEMA, rows=((Decimal("42"),),))
    record = execute_bounded(adapter, perform_dry_run(adapter, QUERY), POLICY)
    assert record.completed
    assert assert_execution_completed(record).rows == ((Decimal("42"),),)


@pytest.mark.parametrize(
    "outcome",
    [ExecutionOutcome.TIMED_OUT, ExecutionOutcome.CANCELLED_OVER_LIMIT, ExecutionOutcome.FAILED],
    ids=lambda o: o.value,
)
def test_a_failed_execution_returns_nothing_partial(outcome: ExecutionOutcome) -> None:
    """No field survives in which partial output could hide."""
    adapter = FakeWarehouseAdapter(schema=SCHEMA, rows=((Decimal("42"),),), outcome=outcome)
    record = execute_bounded(adapter, perform_dry_run(adapter, QUERY), POLICY)

    assert record.result is None
    assert not record.completed
    with pytest.raises(ContractViolation):
        assert_execution_completed(record)


def test_the_cost_of_a_failed_execution_is_still_recorded() -> None:
    """The money was spent whether or not an answer came back."""
    adapter = FakeWarehouseAdapter(
        schema=SCHEMA, actual_bytes=5_000, outcome=ExecutionOutcome.FAILED
    )
    record = execute_bounded(adapter, perform_dry_run(adapter, QUERY), POLICY)
    assert record.actual_bytes == 5_000


def test_the_governed_limits_reach_the_job() -> None:
    adapter = FakeWarehouseAdapter(schema=SCHEMA)
    execute_bounded(adapter, perform_dry_run(adapter, QUERY), POLICY)
    assert adapter.last_limits is not None
    assert adapter.last_limits.maximum_bytes_billed == 1_000_000
    assert adapter.last_limits.timeout_seconds == 30


# --- T089: mid-flight catalog change ----------------------------------------


def test_an_unchanged_catalog_passes() -> None:
    before = CatalogSnapshot("r-1", ("installs@3",))
    assert_catalog_unchanged(before, CatalogSnapshot("r-1", ("installs@3",)))


def test_reordered_versions_are_not_a_change() -> None:
    assert_catalog_unchanged(
        CatalogSnapshot("r-1", ("a@1", "b@2")), CatalogSnapshot("r-1", ("b@2", "a@1"))
    )


@pytest.mark.parametrize(
    "after",
    [CatalogSnapshot("r-2", ("installs@3",)), CatalogSnapshot("r-1", ("installs@4",))],
    ids=["release", "version"],
)
def test_a_moved_catalog_discards_the_output(after: CatalogSnapshot) -> None:
    with pytest.raises(ContractViolation) as caught:
        assert_catalog_unchanged(CatalogSnapshot("r-1", ("installs@3",)), after)
    assert caught.value.code is AnalyticsReasonCode.CATALOG_CHANGED_DURING_EXECUTION


def test_the_change_refusal_names_no_metric_or_version() -> None:
    with pytest.raises(ContractViolation) as caught:
        assert_catalog_unchanged(
            CatalogSnapshot("r-1", ("installs@3",)), CatalogSnapshot("r-2", ("installs@4",))
        )
    detail = caught.value.detail.lower()
    for leak in ("installs", "r-1", "r-2", "@3", "@4"):
        assert leak not in detail


# --- T090: warehouse failures ------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ConnectionError("connection refused"), FailureClass.UNREACHABLE),
        (TimeoutError("network timeout"), FailureClass.UNREACHABLE),
        (PermissionError("403 Forbidden"), FailureClass.CREDENTIAL_REJECTED),
        (RuntimeError("credential rejected"), FailureClass.CREDENTIAL_REJECTED),
        (ValueError("malformed response"), FailureClass.ERRORED),
    ],
)
def test_each_failure_class_is_recognised(exc: Exception, expected: FailureClass) -> None:
    assert classify_failure(exc) is expected


def test_a_permission_failure_mentioning_a_connection_is_not_a_network_blip() -> None:
    """Misreading it would send an operator chasing the wrong thing."""
    assert classify_failure(RuntimeError("connection denied: permission")) is (
        FailureClass.CREDENTIAL_REJECTED
    )


@pytest.mark.parametrize("failure", list(FailureClass), ids=lambda f: f.value)
def test_every_failure_refuses_without_disclosing_the_deployment(failure: FailureClass) -> None:
    violation = refuse_for_failure(failure)
    assert violation.code is AnalyticsReasonCode.WAREHOUSE_UNAVAILABLE
    text = violation.detail.lower()
    for leak in ("credential", "permission", "host", "project", "dataset", failure.value):
        assert leak not in text


def test_no_fallback_value_appears_in_the_failure_module() -> None:
    import ast
    import inspect

    from analytics_query.execution import failures

    tree = ast.parse(inspect.getsource(failures))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in ("last_known", "default_value", "return 0", "stale"):
        assert marker not in code


# --- T091: result assembly ---------------------------------------------------


def test_values_are_copied_exactly() -> None:
    execution = ExecutionResult(
        schema=SCHEMA,
        rows=((Decimal("42.500"),),),
        actual_bytes=1,
        job_ref="j",
        outcome=ExecutionOutcome.COMPLETED,
    )
    result = assemble_result(execution, columns=COLUMNS)
    assert result.rows[0].cells[0].value == Decimal("42.500")
    assert str(result.rows[0].cells[0].value) == "42.500", "trailing precision is preserved"


def test_an_inexact_float_is_refused_rather_than_converted() -> None:
    """Converting would preserve the error while making it look exact."""
    with pytest.raises(ContractViolation) as caught:
        to_cell(0.1 + 0.2)
    assert caught.value.code is AnalyticsReasonCode.RESULT_SHAPE_MISMATCH


def test_a_boolean_is_not_a_metric_value() -> None:
    with pytest.raises(ContractViolation):
        to_cell(True)


def test_a_null_becomes_an_empty_cell_not_a_zero() -> None:
    assert to_cell(None).value is None


def test_a_column_count_mismatch_refuses() -> None:
    execution = ExecutionResult(
        schema=ResultSchema(
            columns=(ResultColumnSchema("a", "INT64", None), ResultColumnSchema("b", "INT64", None))
        ),
        rows=(),
        actual_bytes=1,
        job_ref="j",
        outcome=ExecutionOutcome.COMPLETED,
    )
    with pytest.raises(ContractViolation):
        assemble_result(execution, columns=COLUMNS)


def test_no_arithmetic_appears_in_the_assembler() -> None:
    import ast
    import inspect

    from analytics_query.results import assemble

    tree = ast.parse(inspect.getsource(assemble))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in ("round(", "* 100", "/ ", "sum(", "mean", "interpolat", "imput"):
        assert marker not in code, f"the assembler computes: {marker!r}"


# --- T092: empty versus withheld ---------------------------------------------


def _result(
    *cells: ResultCell, completeness: Completeness = Completeness.COMPLETE
) -> AnalyticsResult:
    """One single-metric-column row per cell."""
    return AnalyticsResult(
        columns=COLUMNS,
        rows=tuple(ResultRow(cells=(cell,)) for cell in cells),
        completeness=completeness,
    )


def test_a_zero_row_result_is_genuinely_empty() -> None:
    empty = AnalyticsResult(columns=COLUMNS, rows=(), completeness=Completeness.EMPTY)
    disposition = classify_result(empty)
    assert disposition.kind is ResultKind.EMPTY
    assert disposition.is_genuinely_empty
    assert disposition.reason_code is None


def test_a_fully_withheld_result_is_not_empty() -> None:
    """The distinction the whole module exists for."""
    withheld = _result(
        ResultCell(
            value=None,
            suppressed=True,
            suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
        )
    )
    disposition = classify_result(withheld)
    assert disposition.kind is ResultKind.FULLY_WITHHELD
    assert not disposition.is_genuinely_empty
    assert disposition.reason_code is AnalyticsReasonCode.RESULT_FULLY_SUPPRESSED


def test_a_partially_withheld_result_carries_its_reason() -> None:
    disposition = classify_result(
        _result(
            ResultCell(value=Decimal("1")),
            ResultCell(
                value=None,
                suppressed=True,
                suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
            ),
        )
    )
    assert disposition.kind is ResultKind.PARTIALLY_WITHHELD
    assert disposition.reason_code is AnalyticsReasonCode.RESULT_CELL_SUPPRESSED


def test_a_populated_result_carries_no_reason() -> None:
    disposition = classify_result(_result(ResultCell(value=Decimal("1"))))
    assert disposition.kind is ResultKind.POPULATED
    assert disposition.reason_code is None


# --- T094: provenance --------------------------------------------------------


def _provenance(**overrides: object) -> ResultProvenance:
    payload: dict[str, object] = {
        "contributing_sources": ("google_play",),
        "resolved_metric_versions": ("installs@3",),
        "data_revisions": ("rev-1",),
        "data_as_of": datetime(2026, 8, 12, tzinfo=UTC),
        "source_updates": (
            SourceUpdate(
                source_id="google_play", last_updated_at=datetime(2026, 8, 12, tzinfo=UTC)
            ),
        ),
        "dimensional_coverage": ("country",),
        "limitations": (),
        "cost": CostProvenance(
            dry_run_bytes=1000, actual_bytes=999, maximum_bytes_billed=1_000_000
        ),
        "execution_identifiers": ("job-1",),
        "policy_version": "p-1",
        "catalog_release_id": "r-1",
    }
    payload.update(overrides)
    return build(ResultProvenance, **payload)


def test_a_complete_provenance_block_constructs() -> None:
    assert _provenance().is_complete()


def test_all_ten_elements_are_named() -> None:
    assert len(REQUIRED_ELEMENTS) == 10
    declared = set(ResultProvenance.model_fields)
    for element in REQUIRED_ELEMENTS:
        assert element in declared


@pytest.mark.parametrize(
    "omitted", ["contributing_sources", "resolved_metric_versions", "execution_identifiers"]
)
def test_an_empty_required_element_fails_construction(omitted: str) -> None:
    with pytest.raises(ContractViolation):
        _provenance(**{omitted: ()})


def test_a_contributing_source_without_an_update_time_is_incomplete() -> None:
    """Its freshness cannot be checked, so the figure cannot be judged."""
    with pytest.raises(ContractViolation):
        _provenance(contributing_sources=("google_play", "ios_app"))


def test_the_policy_version_is_recorded_for_attribution() -> None:
    """`FR-072`: a behaviour change is attributable to the policy, not the catalog."""
    assert _provenance().policy_version == "p-1"


def test_byte_variance_is_reported_and_never_withholds() -> None:
    cost = CostProvenance(dry_run_bytes=1000, actual_bytes=1500, maximum_bytes_billed=1_000_000)
    assert cost.underestimated
    assert cost.variance_bytes == 500
    assert _provenance(cost=cost).is_complete()


def test_billed_bytes_above_the_ceiling_are_a_defect() -> None:
    """The warehouse cancels an overrun; a result reporting one should not exist."""
    with pytest.raises(ContractViolation):
        build(
            CostProvenance, dry_run_bytes=1, actual_bytes=2_000_000, maximum_bytes_billed=1_000_000
        )


# --- T095: comparable window -------------------------------------------------


def test_a_comparable_window_states_its_reason_and_sources() -> None:
    window = ComparableWindow(
        start=date(2026, 7, 1),
        end=date(2026, 7, 20),
        reason="ios_app coverage ends 2026-07-20",
        sources=("google_play", "ios_app"),
    )
    assert window.reason
    assert len(window.sources) == 2


def test_a_reversed_window_is_refused() -> None:
    with pytest.raises(ContractViolation) as caught:
        build(
            ComparableWindow,
            start=date(2026, 7, 20),
            end=date(2026, 7, 1),
            reason="r",
            sources=("a",),
        )
    assert caught.value.code is AnalyticsReasonCode.DATE_RANGE_INVALID


def test_a_window_without_a_reason_is_refused() -> None:
    """Stating the window without the reason looks like a choice, not a constraint."""
    with pytest.raises(ContractViolation):
        build(
            ComparableWindow,
            start=date(2026, 7, 1),
            end=date(2026, 7, 2),
            reason="",
            sources=("a",),
        )


def test_no_module_derives_a_comparable_window() -> None:
    import ast
    import inspect

    from analytics_query.contracts import comparable_window

    tree = ast.parse(inspect.getsource(comparable_window))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in ("min(", "max(", "intersect", "overlap"):
        assert marker not in code, f"the window is recomputed: {marker!r}"


# --- T097: audit recovery ----------------------------------------------------

CTX_A = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type="user",
    authorization_policy_pin="authpol-1",
)
CTX_B = AuthorizationContext(
    authorization_scope="tenant-b",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type="user",
    authorization_policy_pin="authpol-1",
)


def _key(context: AuthorizationContext) -> ExecutionKey:
    return ExecutionKey("a" * 64, derive_authorization_fingerprint(context))


def test_recovery_emits_only_what_the_sink_never_accepted() -> None:
    outstanding = stages_outstanding((AuditStage.VALIDATION, AuditStage.EXECUTION_START))
    assert outstanding == (AuditStage.EXECUTION_COMPLETE,)


def test_recovery_never_fabricates_a_refusal_for_a_request_that_executed() -> None:
    """A request that reached EXECUTION_START was not refused."""
    assert AuditStage.REFUSAL not in stages_outstanding((AuditStage.EXECUTION_START,))


def test_a_request_that_never_executed_may_still_owe_a_refusal_event() -> None:
    assert AuditStage.REFUSAL in stages_outstanding((AuditStage.VALIDATION,))


def test_a_complete_trail_needs_no_recovery() -> None:
    plan = RecoveryPlan(outstanding=stages_outstanding(STAGE_ORDER))
    assert plan.is_complete
    assert not plan.re_execute


def test_only_an_unknown_entry_is_recoverable() -> None:
    ledger, key = InMemoryExecutionLedger(), _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p1")
    assert plan_recovery(ledger, key) is None, "a running entry belongs to someone else"

    ledger.complete(key, ExecutionStatus.UNKNOWN)
    plan = plan_recovery(ledger, key)
    assert plan is not None
    assert not plan.re_execute, "recovery recovers the audit, never the query"


def test_a_completed_entry_is_not_recoverable() -> None:
    ledger, key = InMemoryExecutionLedger(), _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p1")
    ledger.complete(key, ExecutionStatus.COMPLETED, actual_bytes=1)
    assert plan_recovery(ledger, key) is None


def test_a_differing_fingerprint_cannot_resume_the_audit_path() -> None:
    """It never sees the entry at all — `get` requires the full key."""
    ledger = InMemoryExecutionLedger()
    ledger.acquire(_key(CTX_A), correlation_id="c1", principal_ref="p-a")
    ledger.complete(_key(CTX_A), ExecutionStatus.UNKNOWN)

    assert plan_recovery(ledger, _key(CTX_A)) is not None
    assert plan_recovery(ledger, _key(CTX_B)) is None


# --- T100: the model-facing boundary -----------------------------------------


def test_no_language_model_client_exists_anywhere_in_the_package() -> None:
    """`FR-039` enforced by absence, which is the only form that survives a refactor."""
    from pathlib import Path

    import analytics_query

    src = Path(analytics_query.__file__).parent
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for client in ("openai", "anthropic", "import llm", "chatcompletion", "genai", "vertexai"):
            assert client not in text, f"{path.relative_to(src)} imports a model client"


def test_a_payload_carries_aggregated_evidence_and_units() -> None:
    payload = to_model_payload(_result(ResultCell(value=Decimal("42"))), POLICY)
    assert payload["columns"] == [{"identifier": "installs", "unit": "users", "is_metric": True}]
    assert payload["rows"] == [["42"]]


def test_a_payload_carries_no_forbidden_key() -> None:
    payload = to_model_payload(_result(ResultCell(value=Decimal("1"))), POLICY)
    for forbidden in ("sql", "query_text", "credential", "principal_ref", "raw_rows"):
        assert forbidden not in payload


def test_a_suppressed_cell_crosses_as_an_explicit_marker_not_a_blank() -> None:
    """A model reading a blank will narrate it as absence."""
    payload = to_model_payload(
        _result(
            ResultCell(value=Decimal("1")),
            ResultCell(
                value=None,
                suppressed=True,
                suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
            ),
        ),
        POLICY,
    )
    rows = payload["rows"]
    assert isinstance(rows, list)
    assert rows[1][0] == {"suppressed": True, "reason": "RESULT_CELL_SUPPRESSED"}


def test_a_fully_withheld_result_yields_no_payload() -> None:
    withheld = _result(
        ResultCell(
            value=None,
            suppressed=True,
            suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
        )
    )
    with pytest.raises(ContractViolation) as caught:
        to_model_payload(withheld, POLICY)
    assert caught.value.code is AnalyticsReasonCode.RESULT_FULLY_SUPPRESSED


def test_an_oversized_payload_refuses_rather_than_trimming() -> None:
    """Trimming would reintroduce the substitution `FR-024` refuses, one step later."""
    narrow = build(
        QueryPolicy,
        version="p-2",
        effective_from=date(2026, 8, 1),
        approval=PolicyApproval(
            approver_role="data_platform", evidence_ref="a-1", approved_on=date(2026, 8, 1)
        ),
        maximum_bytes_billed=1,
        maximum_rows=1,
        execution_timeout_seconds=1,
        maximum_range_days=1,
        minimum_aggregation_threshold=5,
    )
    wide = _result(ResultCell(value=Decimal("1")), ResultCell(value=Decimal("2")))
    with pytest.raises(ContractViolation) as caught:
        to_model_payload(wide, narrow)
    assert caught.value.code is AnalyticsReasonCode.QUERY_ROW_LIMIT_EXCEEDED
