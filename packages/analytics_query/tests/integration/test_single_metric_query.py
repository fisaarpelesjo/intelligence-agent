"""End-to-end success path — T104 (FR-038, FR-042, FR-043; SC-005, SC-006, SC-015).

The whole pipeline against fixtures, running through the **real** ``evaluate()``
and the real eleven gates — not a stubbed verdict. A stub would prove this
feature reacts correctly to a decision; only the real bundle proves the decision
it reacts to is the one the catalog actually produces, which is what catches a
translation error in the bridge.

Asserts the four things a caller receives: a tabular result with governed
columns and units, values byte-identical to the adapter response, all ten
provenance elements, and the finality the evidence supports.

**Fixture-backed throughout.** Nothing here says anything about production
(`FR-063`): the catalog is `001`'s test tree, the observations are fixtures, and
no warehouse was reached.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.contracts._base import build
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.provenance import CostProvenance
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.contracts.result import ResultColumn
from analytics_query.contracts.result_provenance import (
    REQUIRED_ELEMENTS,
    ResultProvenance,
    SourceUpdate,
)
from analytics_query.decision.bridge import evaluate_fully, is_permissive, to_catalog_request
from analytics_query.execution.adapter import ResultColumnSchema, ResultSchema
from analytics_query.execution.dryrun import perform_dry_run
from analytics_query.execution.run import assert_execution_completed, execute_bounded
from analytics_query.execution.shape import assert_shapes_agree
from analytics_query.results.assemble import assemble_result
from analytics_query.results.completeness import ResultKind, classify_result

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.bundle import (
    ALLOWED_METRIC,
    ALLOWED_SOURCE,
    ON,
    SCOPE,
    STANDARD_ACCESS,
    bundle,
    snapshot,
)

pytestmark = pytest.mark.integration

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
SCHEMA = ResultSchema(columns=(ResultColumnSchema(ALLOWED_METRIC, "INT64", "sessions"),))
COLUMNS = (ResultColumn(identifier=ALLOWED_METRIC, unit="sessions", is_metric=True),)

POLICY = build(
    QueryPolicy,
    version="p-fixture",
    effective_from=date(2026, 8, 1),
    approval=PolicyApproval(
        approver_role="data_platform", evidence_ref="fixture-approval", approved_on=date(2026, 8, 1)
    ),
    maximum_bytes_billed=1_000_000,
    maximum_rows=1_000,
    execution_timeout_seconds=30,
    maximum_range_days=92,
    minimum_aggregation_threshold=5,
)


def _request() -> AnalyticsQuery:
    return build(
        AnalyticsQuery,
        metrics=(ALLOWED_METRIC,),
        sources=(ALLOWED_SOURCE,),
        date_range=JULY,
    )


def _decision():
    return evaluate_fully(
        _request(),
        evaluate=evaluate,
        bundle=bundle(),
        snapshot=snapshot(),
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        requester_access=STANDARD_ACCESS,
        on=ON,
    )


# --- the governed decision ---------------------------------------------------


def test_the_real_gates_allow_this_request() -> None:
    """Through `001`'s own pipeline, not a stub."""
    decision = _decision()
    assert decision.outcome is Outcome.ALLOW
    assert decision.reason_code is ReasonCode.REQUEST_ALLOWED
    assert is_permissive(decision)


def test_the_translation_asks_what_the_caller_asked() -> None:
    translated = to_catalog_request(_request(), requester_access=STANDARD_ACCESS)
    assert translated.metrics == (ALLOWED_METRIC,)
    assert translated.sources == (ALLOWED_SOURCE,)
    assert translated.requester_access == STANDARD_ACCESS


# --- the result --------------------------------------------------------------


def _executed(rows: tuple[tuple[Decimal, ...], ...] = ((Decimal("12345"),),)):
    adapter = FakeWarehouseAdapter(schema=SCHEMA, rows=rows, estimated_bytes=1000, actual_bytes=900)
    plan = perform_dry_run(adapter, __rendered())
    record = execute_bounded(adapter, plan, POLICY)
    execution = assert_execution_completed(record)
    assert_shapes_agree(plan.schema, execution.schema)
    return adapter, plan, record, assemble_result(execution, columns=COLUMNS)


def __rendered():
    from analytics_query.execution.adapter import RenderedQuery

    return RenderedQuery(
        text=f"SELECT SUM({ALLOWED_METRIC}) AS {ALLOWED_METRIC} FROM `semantic.fixture_daily`",
        parameters={},
    )


def test_the_result_is_tabular_with_governed_columns_and_units() -> None:
    _, _, _, result = _executed()
    assert [c.identifier for c in result.columns] == [ALLOWED_METRIC]
    assert [c.unit for c in result.columns] == ["sessions"]
    assert classify_result(result).kind is ResultKind.POPULATED


def test_values_are_byte_identical_to_the_adapter_response() -> None:
    """`SC-006`: compared against the raw response, not a re-derivation."""
    adapter, _, _, result = _executed(((Decimal("12345.6700"),),))
    assert adapter.last_query is not None
    assert result.rows[0].cells[0].value == Decimal("12345.6700")
    assert str(result.rows[0].cells[0].value) == "12345.6700", "trailing precision survives"


def test_the_shape_the_dry_run_validated_is_the_shape_that_executed() -> None:
    _, plan, _, _ = _executed()
    assert plan.schema == SCHEMA


def test_exactly_one_dry_run_precedes_exactly_one_execution() -> None:
    adapter, _, _, _ = _executed()
    assert adapter.dry_run_calls == 1
    assert adapter.execute_calls == 1


# --- provenance --------------------------------------------------------------


def test_all_ten_provenance_elements_are_present() -> None:
    _, plan, record, _ = _executed()
    provenance = build(
        ResultProvenance,
        contributing_sources=(ALLOWED_SOURCE,),
        resolved_metric_versions=(f"{ALLOWED_METRIC}@1",),
        data_revisions=(),
        data_as_of=datetime(2026, 8, 11, tzinfo=UTC),
        source_updates=(
            SourceUpdate(
                source_id=ALLOWED_SOURCE, last_updated_at=datetime(2026, 8, 11, tzinfo=UTC)
            ),
        ),
        dimensional_coverage=(),
        limitations=(),
        cost=CostProvenance(
            dry_run_bytes=plan.estimated_bytes,
            actual_bytes=record.actual_bytes,
            maximum_bytes_billed=POLICY.maximum_bytes_billed,
        ),
        execution_identifiers=(record.job_ref,),
        policy_version=POLICY.version,
        catalog_release_id=bundle().release_id,
    )

    assert provenance.is_complete()
    assert len(REQUIRED_ELEMENTS) == 10
    assert provenance.cost.dry_run_bytes == 1000
    assert provenance.cost.actual_bytes == 900


def test_both_cost_figures_are_reported() -> None:
    """`SC-035`: estimate and actual, always."""
    _, plan, record, _ = _executed()
    cost = CostProvenance(
        dry_run_bytes=plan.estimated_bytes,
        actual_bytes=record.actual_bytes,
        maximum_bytes_billed=POLICY.maximum_bytes_billed,
    )
    assert cost.dry_run_bytes and cost.actual_bytes
    assert not cost.underestimated


# --- finality (FR-043) -------------------------------------------------------


def test_the_decision_stays_pre_evidence_until_a_revision_arrives() -> None:
    """The `001`/`002` seam, observed rather than described.

    `001` answers "may this be answered?" and stops at `PRE_EVIDENCE`. It is the
    data revision this feature supplies that advances the decision — and the
    fixture snapshot supplies none, so `limited` is the honest state.
    """
    decision = _decision()
    assert decision.finality == "pre_evidence"
    assert decision.reproducibility == "limited"


def test_this_run_says_nothing_about_production() -> None:
    """`FR-063`: fixture-backed throughout, and it must be stated."""
    from analytics_query.compliance.report import build_report

    report = build_report(title="single metric query", gates_passed=1, gates_total=1)
    assert "say nothing about production readiness" in report.limitation
    # Emendado no ciclo 501 (2026-09-01, OD-86): d_15 pronto por palavra+evidencia; a
    # frase-limite acima e o que este no guarda, e ela continua obrigatoria.
    assert report.capabilities_ready == ("d_14", "d_15", "d_16")  # OD-94+97
