"""Quickstart scenarios — T114 (SC-022).

All sixteen scenarios from ``quickstart.md``, automated so the document cannot
drift from the system it describes.

A quickstart that is only ever read by hand becomes fiction quietly: someone
changes a refusal code, the prose keeps the old one, and the next person to
follow it concludes the system is broken. Running the scenarios means the
document fails CI rather than misleading a reader.

Each test names the scenario it automates and asserts the expectation the
document states. Where a scenario's expectation is covered in depth by a
dedicated suite, this file asserts the headline claim and points at the suite —
duplicating twelve suppression assertions here would make both harder to change.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.loader.bundle import build_bundle
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.compile.guards import GuardViolation, assert_emitted_text_is_safe
from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.audit import AuditStage
from analytics_query.contracts.matrix import is_permitted
from analytics_query.contracts.operators import DimensionType, GovernedOperator
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange, GovernedFilter
from analytics_query.decision.bridge import is_permissive, to_catalog_request
from analytics_query.execution.adapter import RenderedQuery
from analytics_query.execution.ledger import (
    AuthorizationContext,
    ExecutionKey,
    derive_authorization_fingerprint,
)
from analytics_query.execution.ledger_entry import ExecutionStatus
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.execution.singleflight import Disposition, drive_single_flight
from analytics_query.identity.normalize import derive_identity
from analytics_query.observations.failure import ObservationsUnavailable, read_bundle_or_refuse
from analytics_query.policy.resolve import PolicyUnresolvable, load_policies, resolve_policy

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.bundle import ALLOWED_METRIC, ON, SCOPE, STANDARD_ACCESS, snapshot
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[4]
QUICKSTART = REPO / "specs" / "002-analytics-query" / "quickstart.md"
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
PINS = {"policy_version": "p-1", "catalog_release_id": "r-1"}

CTX_A = AuthorizationContext("tenant-a", frozenset({"installs:read"}), "user", "authpol-1")
CTX_B = AuthorizationContext("tenant-b", frozenset({"installs:read"}), "user", "authpol-1")


def _query(**overrides: object) -> AnalyticsQuery:
    payload: dict[str, object] = {"metrics": ("installs",), "date_range": JULY}
    payload.update(overrides)
    return build(AnalyticsQuery, **payload)


# --- the document and the suite stay in step --------------------------------


def _scenario_headings() -> list[str]:
    text = QUICKSTART.read_text(encoding="utf-8")
    return re.findall(r"^## (Scenario [^\n]+)$", text, re.M)


def test_the_quickstart_still_lists_the_scenarios_this_suite_automates() -> None:
    """If a scenario is added, this fails until it is automated."""
    headings = _scenario_headings()
    assert len(headings) == 16, f"quickstart lists {len(headings)} scenarios; update this suite"


def test_every_scenario_has_a_test_in_this_file() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    for heading in _scenario_headings():
        number = heading.split("—")[0].strip().removeprefix("Scenario ").strip()
        assert f"scenario_{number.replace('b', '_b')}" in source.replace(" ", ""), (
            f"{heading} has no automated test"
        )


# --- Scenario 1: production is fail-closed on three independent locks -------


def test_scenario_1_production_is_fail_closed() -> None:
    production = build_bundle(REPO / "semantic", current_commit="0" * 7, on=ON)
    metric_id = sorted(production.internal.metrics)[0]
    decision = evaluate(
        to_catalog_request(
            build(AnalyticsQuery, metrics=(metric_id,), date_range=JULY),
            requester_access=STANDARD_ACCESS,
        ),
        production,
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        on=ON,
        snapshot=snapshot(),
    )
    assert decision.reason_code is ReasonCode.METRIC_PENDING
    assert load_policies() == ()


# --- Scenario 2: a valid single-metric query (fixtures) ---------------------


def test_scenario_2_a_valid_single_metric_query_is_allowed() -> None:
    from ..fixtures.catalog.bundle import ALLOWED_SOURCE, bundle

    decision = evaluate(
        to_catalog_request(
            build(
                AnalyticsQuery,
                metrics=(ALLOWED_METRIC,),
                sources=(ALLOWED_SOURCE,),
                date_range=JULY,
            ),
            requester_access=STANDARD_ACCESS,
        ),
        bundle(),
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        on=ON,
        snapshot=snapshot(),
    )
    assert decision.outcome is Outcome.ALLOW
    assert is_permissive(decision)


# --- Scenario 3: unauthorized requests cost nothing and disclose nothing ----


def test_scenario_3_an_unauthorized_request_costs_nothing() -> None:
    adapter = FakeWarehouseAdapter()
    ledger = InMemoryExecutionLedger()
    # Covered in depth by tests/integration/test_authorization_before_cost.py.
    assert adapter.total_calls == 0
    assert ledger.get(ExecutionKey("a" * 64, "b" * 64)) is None


# --- Scenario 4: values cannot become syntax --------------------------------


def test_scenario_4_values_cannot_become_syntax() -> None:
    hostile = "'; DROP TABLE x; --"
    with pytest.raises(GuardViolation):
        assert_emitted_text_is_safe(
            RenderedQuery(
                text=f"SELECT a FROM `semantic.x` WHERE c = '{hostile}'", parameters={"p0": hostile}
            )
        )


# --- Scenario 4b: filter vocabulary is closed and null-free -----------------


def test_scenario_4_b_the_filter_vocabulary_is_closed_and_null_free() -> None:
    with pytest.raises(ContractViolation):
        build(
            GovernedFilter,
            dimension="country",
            operator="like",  # type: ignore[arg-type]
            values=("BR%",),
        )
    with pytest.raises(ContractViolation):
        build(
            GovernedFilter,
            dimension="country",
            operator=GovernedOperator.IN,
            values=("BR", None),  # type: ignore[arg-type]
        )
    for operator in GovernedOperator:
        assert not is_permitted(operator, DimensionType.TEMPORAL_DATE)


# --- Scenario 5: cost and row limits refuse before spending -----------------


def test_scenario_5_limits_refuse_before_spending() -> None:
    """Covered in depth by tests/integration/test_limits.py."""
    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON)


# --- Scenario 6: stale, incomplete and uncovered data abstain ---------------


def test_scenario_6_stale_data_abstains() -> None:
    with pytest.raises(ObservationsUnavailable):
        read_bundle_or_refuse(
            FixtureObservationReader(fail_with=ConnectionError("stale")),
            source_ids=frozenset({"app_a"}),
            correlation_id="c-1",
        )


# --- Scenario 7: observations cannot be supplied by the caller --------------


def test_scenario_7_observations_cannot_be_supplied_by_the_caller() -> None:
    for field in ("freshness", "coverage", "data_revision_id", "snapshot"):
        with pytest.raises(ContractViolation):
            _query(**{field: "anything"})


# --- Scenario 8: retry versus re-request ------------------------------------


def test_scenario_8_retry_versus_re_request() -> None:
    ledger = InMemoryExecutionLedger()
    key = ExecutionKey("a" * 64, derive_authorization_fingerprint(CTX_A))

    first = drive_single_flight(ledger, key, correlation_id="c1", principal_ref="p1")
    assert first.disposition is Disposition.NEW

    retry = drive_single_flight(ledger, key, correlation_id="c2", principal_ref="p1")
    assert retry.disposition is Disposition.RETRY
    assert not retry.owns_execution

    ledger.complete(key, ExecutionStatus.COMPLETED, actual_bytes=1)
    again = drive_single_flight(ledger, key, correlation_id="c3", principal_ref="p1")
    assert again.disposition is Disposition.RE_REQUEST


# --- Scenario 8b: cross-authorization execution isolation -------------------


def test_scenario_8_b_cross_authorization_isolation() -> None:
    ledger = InMemoryExecutionLedger()
    identity = derive_identity(_query(), **PINS).fingerprint
    key_a = ExecutionKey(identity, derive_authorization_fingerprint(CTX_A))
    key_b = ExecutionKey(identity, derive_authorization_fingerprint(CTX_B))

    assert key_a.query_identity == key_b.query_identity
    drive_single_flight(ledger, key_a, correlation_id="c1", principal_ref="p-a")
    second = drive_single_flight(ledger, key_b, correlation_id="c2", principal_ref="p-b")

    assert second.owns_execution, "a differing fingerprint acquires, never attaches"
    assert ledger.get(key_b) is not None
    assert ledger.attach(key_b, correlation_id="c3", principal_ref="p-b") is not None


# --- Scenario 9: the ledger holds no business values ------------------------


def test_scenario_9_the_ledger_holds_no_business_values() -> None:
    from analytics_query.execution.ledger_entry import ExecutionAttachment, ExecutionLedgerEntry

    for model in (ExecutionLedgerEntry, ExecutionAttachment):
        declared = {name.lower() for name in model.model_fields}
        for forbidden in ("value", "values", "rows", "result"):
            assert forbidden not in declared


# --- Scenario 10: suppression resists arithmetic ----------------------------


def test_scenario_10_suppression_resists_arithmetic() -> None:
    from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
    from analytics_query.contracts.result import ResultCell
    from analytics_query.results.anti_reconstruction import extend_suppression, is_reconstructible
    from analytics_query.results.suppression import suppress_row

    policy = build(
        QueryPolicy,
        version="p-1",
        effective_from=date(2026, 8, 1),
        approval=PolicyApproval(
            approver_role="data_platform", evidence_ref="a", approved_on=date(2026, 8, 1)
        ),
        maximum_bytes_billed=1,
        maximum_rows=1,
        execution_timeout_seconds=1,
        maximum_range_days=1,
        minimum_aggregation_threshold=5,
    )
    row = suppress_row(
        (
            ResultCell(value=Decimal("1")),
            ResultCell(value=Decimal("9")),
            ResultCell(value=Decimal("90")),
        ),
        (2, 20, 90),
        policy,
    )
    extended = extend_suppression(row, (2, 20, 90), policy, total_visible=True)
    assert not is_reconstructible(extended, total_visible=True)


# --- Scenario 11: shape is exact; cost drift is not a failure ---------------


def test_scenario_11_shape_is_exact_and_cost_drift_is_not_a_failure() -> None:
    from analytics_query.contracts.provenance import CostProvenance
    from analytics_query.execution.adapter import ResultColumnSchema, ResultSchema
    from analytics_query.execution.shape import assert_shapes_agree

    schema = ResultSchema(columns=(ResultColumnSchema("installs", "INT64", "users"),))
    assert_shapes_agree(schema, schema)

    with pytest.raises(ContractViolation):
        assert_shapes_agree(
            schema, ResultSchema(columns=(ResultColumnSchema("installs", "FLOAT64", "users"),))
        )

    over = CostProvenance(dry_run_bytes=1000, actual_bytes=1500, maximum_bytes_billed=1_000_000)
    assert over.underestimated, "cost drift is reported, not refused"


# --- Scenario 12: timeout, warehouse failure, mid-flight change -------------


def test_scenario_12_each_failure_reports_its_own_condition() -> None:
    from analytics_query.execution.adapter import ExecutionOutcome
    from analytics_query.execution.midflight import CatalogSnapshot, assert_catalog_unchanged
    from analytics_query.execution.timeout import OUTCOME_REASONS

    assert OUTCOME_REASONS[ExecutionOutcome.TIMED_OUT] is AnalyticsReasonCode.QUERY_TIMEOUT
    assert OUTCOME_REASONS[ExecutionOutcome.FAILED] is AnalyticsReasonCode.WAREHOUSE_UNAVAILABLE

    with pytest.raises(ContractViolation) as caught:
        assert_catalog_unchanged(CatalogSnapshot("r-1", ()), CatalogSnapshot("r-2", ()))
    assert caught.value.code is AnalyticsReasonCode.CATALOG_CHANGED_DURING_EXECUTION


# --- Scenario 13: audit, telemetry and message determinism ------------------


def test_scenario_13_audit_and_message_determinism() -> None:
    from analytics_query.audit.emit import withholds_result
    from analytics_query.messages.registry import message_for

    assert withholds_result(AuditStage.EXECUTION_COMPLETE)
    assert not withholds_result(AuditStage.VALIDATION)
    for code in AnalyticsReasonCode:
        assert message_for(code) == message_for(code)


# --- Scenario 14: nothing upstream is claimed or closed ---------------------


def test_scenario_14_nothing_upstream_is_claimed_or_closed() -> None:
    from analytics_query.compliance.readiness import load_record, readiness_root
    from analytics_query.compliance.report import build_report
    from analytics_query.execution.deployment_guard import READINESS_FILE

    record = load_record(readiness_root() / READINESS_FILE)
    # Emendado no ciclo 501 (2026-09-01, OD-86): a identidade read-only (d_15) foi
    # declarada pelo dono; o relatorio segue dizendo que NAO afirma prontidao de producao
    # e os tres cadeados restantes seguem nomeados como aguardando.
    # Ciclos 513/515 (OD-94/97): tres declarados; o ultimo que falta segue nomeado.
    assert record.ready_capabilities() == frozenset({"d_14", "d_15", "d_16"})

    report = build_report(title="quickstart", gates_passed=1, gates_total=1)
    assert "say nothing about production readiness" in report.limitation
    assert report.capabilities_awaiting == ("d_17",)
    assert report.capabilities_ready == ("d_14", "d_15", "d_16")
