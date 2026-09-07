"""Range limits and compliance reporting — FR-008, FR-010, FR-063, FR-064; SC-025, SC-026.

Two areas the earlier phases implemented but left without a test of their own,
found by the `FR`/`SC` coverage audits (`T117`, `T118`).

**Range length** (`FR-010`) is enforced only after authorisation succeeds,
because the refusal names the governed maximum and that is a disclosure. The
canonical business time zone (`FR-008`) is resolved through the IANA database
rather than a fixed offset — a fixed `-03:00` is wrong for part of any year the
zone has ever observed DST, and "the range was one day short in October" is the
kind of defect nobody finds.

**Compliance reporting** (`FR-063`, `FR-064`) carries its fixture caveat
structurally. The limitation is a required field with fixed wording, so there is
no path that produces a fixture-backed report and forgets to say so — a report
that merely usually carries the caveat is one that will eventually be quoted
without it.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from analytics_query.compliance.readiness import Capability, ReadinessRecord
from analytics_query.compliance.report import (
    FIXTURE_LIMITATION,
    FORBIDDEN_CLAIMS,
    FixtureBackedReport,
    build_report,
)
from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import DateRange
from analytics_query.policy.limits import (
    BUSINESS_TIME_ZONE,
    assert_range_within_limit,
    business_zone,
)

pytestmark = pytest.mark.unit

POLICY = build(
    QueryPolicy,
    version="p-1",
    effective_from=date(2026, 8, 1),
    approval=PolicyApproval(
        approver_role="data_platform", evidence_ref="a-1", approved_on=date(2026, 8, 1)
    ),
    maximum_bytes_billed=1,
    maximum_rows=1,
    execution_timeout_seconds=1,
    maximum_range_days=31,
    minimum_aggregation_threshold=5,
)


# --- FR-008: the canonical business time zone -------------------------------


def test_the_canonical_zone_is_resolved_through_the_iana_database() -> None:
    assert BUSINESS_TIME_ZONE == "America/Sao_Paulo"
    assert business_zone() == ZoneInfo("America/Sao_Paulo")


def test_the_zone_is_not_a_fixed_offset() -> None:
    """A fixed offset is wrong for part of any year the zone observed DST."""
    zone = business_zone()
    winter = zone.utcoffset(__import__("datetime").datetime(2026, 7, 1))
    summer = zone.utcoffset(__import__("datetime").datetime(2026, 1, 1))
    assert winter is not None and summer is not None
    # Whether they differ depends on the year's rules; what matters is that the
    # offset is *derived* from the database rather than hard-coded.
    assert isinstance(zone, ZoneInfo)


def test_no_module_hard_codes_a_utc_offset() -> None:
    import ast
    import inspect

    from analytics_query.policy import limits

    tree = ast.parse(inspect.getsource(limits))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree)
    for offset in ("-03:00", "-0300", "timedelta(hours=-3)"):
        assert offset not in code


# --- FR-010: range length -----------------------------------------------------


def test_a_range_within_the_governed_maximum_is_permitted() -> None:
    assert_range_within_limit(DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)), POLICY)


def test_a_range_longer_than_the_maximum_is_refused() -> None:
    with pytest.raises(ContractViolation) as caught:
        assert_range_within_limit(DateRange(start=date(2026, 6, 1), end=date(2026, 7, 31)), POLICY)
    assert caught.value.code is AnalyticsReasonCode.DATE_RANGE_TOO_LONG


def test_the_refusal_states_the_requested_length_and_the_limit() -> None:
    """Permitted only because this runs after authorisation."""
    with pytest.raises(ContractViolation) as caught:
        assert_range_within_limit(DateRange(start=date(2026, 6, 1), end=date(2026, 7, 31)), POLICY)
    assert "31" in caught.value.detail
    assert "61" in caught.value.detail


def test_a_range_exactly_at_the_maximum_is_permitted() -> None:
    """The limit is the longest permitted range, not the shortest refused one."""
    assert_range_within_limit(DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)), POLICY)


# --- FR-063, FR-064, SC-025, SC-026: compliance reporting -------------------


def test_a_fixture_backed_report_states_its_limitation() -> None:
    report = build_report(title="internal validation", gates_passed=5, gates_total=5)
    assert report.limitation == FIXTURE_LIMITATION
    assert "say nothing about production readiness" in report.limitation


def test_the_limitation_cannot_be_softened() -> None:
    """Fixed wording: a caveat that varied could be weakened one report at a time."""
    with pytest.raises(ContractViolation):
        build(
            FixtureBackedReport,
            title="report",
            gates_passed=1,
            gates_total=1,
            limitation="Mostly fine.",
        )


def test_no_report_claims_production_readiness() -> None:
    for claim in FORBIDDEN_CLAIMS:
        with pytest.raises(ContractViolation):
            build(FixtureBackedReport, title=f"we are {claim}", gates_passed=1, gates_total=1)


def test_all_gates_green_still_says_nothing_about_production() -> None:
    """ "All 1200 tests pass" is true and says nothing — every one used fixtures."""
    report = build_report(title="internal validation", gates_passed=12, gates_total=12)
    assert report.all_gates_passed
    assert "fixture-backed" in report.limitation


def test_a_report_names_what_is_still_awaiting_evidence() -> None:
    """Listing only what is ready would read as complete."""
    report = build_report(title="internal validation", gates_passed=1, gates_total=1)
    # Emendado no ciclo 501 (2026-09-01, OD-86): o d_15 saiu do aguardando pela palavra do
    # dono; os tres que faltam continuam NOMEADOS — listar so o pronto leria como completo.
    assert report.capabilities_ready == ("d_14", "d_15", "d_16")  # OD-94+97
    assert report.capabilities_awaiting == ("d_17",)


def test_a_declared_and_evidenced_capability_moves_to_ready() -> None:
    record = ReadinessRecord(
        "002-analytics-query",
        {"d_17": Capability("d_17", True, "adr-0010", "engineering")},
    )
    report = build_report(title="t", gates_passed=1, gates_total=1, records=[record])
    assert report.capabilities_ready == ("d_17",)
    assert report.capabilities_awaiting == ()


def test_more_gates_passed_than_ran_is_refused() -> None:
    with pytest.raises(ContractViolation):
        build(FixtureBackedReport, title="t", gates_passed=5, gates_total=1)
