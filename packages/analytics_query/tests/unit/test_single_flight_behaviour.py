"""Deployment guard, single-flight and revision stability — T083, T084, T085.

Covers FR-034, FR-036, FR-067, FR-078 and SC-012, SC-015, SC-036. Those three
tasks state their completion evidence here; Phase 8's test tasks (T086, T087)
cover the no-cache and value-free properties instead, so without this file the
behaviour would be a claim nobody checks.
"""

from __future__ import annotations

import pytest
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_query.compliance.readiness import Capability, ReadinessRecord
from analytics_query.decision.revision_stability import Stability, compare_revisions
from analytics_query.execution.deployment_guard import (
    SHARED_LEDGER_CAPABILITY,
    ForbiddenDeployment,
    assert_deployment_is_permitted,
    shared_ledger_is_available,
)
from analytics_query.execution.ledger import (
    AuthorizationContext,
    ExecutionKey,
    derive_authorization_fingerprint,
)
from analytics_query.execution.ledger_entry import ExecutionStatus
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.execution.singleflight import Disposition, drive_single_flight

pytestmark = pytest.mark.unit

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
IDENTITY = "a" * 64


def _key(context: AuthorizationContext) -> ExecutionKey:
    return ExecutionKey(IDENTITY, derive_authorization_fingerprint(context))


def _record(*, declared: bool, evidence: str | None) -> ReadinessRecord:
    return ReadinessRecord(
        "002-analytics-query",
        {SHARED_LEDGER_CAPABILITY: Capability(SHARED_LEDGER_CAPABILITY, declared, evidence, "eng")},
    )


# --- T083: the deployment guard (FR-036; SC-012) ----------------------------


def test_a_single_process_deployment_is_permitted() -> None:
    assert_deployment_is_permitted(
        process_count=1, records=[_record(declared=False, evidence=None)]
    )


@pytest.mark.parametrize("processes", [2, 4, 16])
def test_multi_process_without_a_shared_ledger_is_forbidden(processes: int) -> None:
    """Refused at start-up, not discovered on a request."""
    with pytest.raises(ForbiddenDeployment) as caught:
        assert_deployment_is_permitted(
            process_count=processes, records=[_record(declared=False, evidence=None)]
        )
    assert "not a permitted downgrade" in str(caught.value)


def test_a_declaration_without_evidence_does_not_unlock_it() -> None:
    """`D-17` declared but unevidenced is not readiness."""
    with pytest.raises(ForbiddenDeployment):
        assert_deployment_is_permitted(
            process_count=2, records=[_record(declared=True, evidence=None)]
        )


def test_evidenced_readiness_permits_multi_process() -> None:
    assert shared_ledger_is_available([_record(declared=True, evidence="adr-0010")])
    assert_deployment_is_permitted(
        process_count=8, records=[_record(declared=True, evidence="adr-0010")]
    )


def test_a_missing_record_reads_as_unavailable() -> None:
    """Absence is a constraint, never a permission."""
    assert not shared_ledger_is_available([])


def test_the_governed_record_leaves_it_undeclared_today() -> None:
    """The fail-closed state, read from the real readiness file."""
    assert not shared_ledger_is_available()
    with pytest.raises(ForbiddenDeployment):
        assert_deployment_is_permitted(process_count=2)


def test_zero_processes_is_refused() -> None:
    with pytest.raises(ForbiddenDeployment):
        assert_deployment_is_permitted(process_count=0)


# --- T084: retry versus re-request (FR-034, FR-078; SC-012, SC-036) ---------


def test_a_first_request_is_new_and_owns_the_execution() -> None:
    ledger = InMemoryExecutionLedger()
    outcome = drive_single_flight(ledger, _key(CTX_A), correlation_id="c1", principal_ref="p1")
    assert outcome.disposition is Disposition.NEW
    assert outcome.owns_execution


def test_a_retry_against_a_running_entry_attaches_without_owning() -> None:
    """Zero additional bytes, zero additional executions."""
    ledger, key = InMemoryExecutionLedger(), _key(CTX_A)
    drive_single_flight(ledger, key, correlation_id="c1", principal_ref="p1")
    retry = drive_single_flight(ledger, key, correlation_id="c2", principal_ref="p1")

    assert retry.disposition is Disposition.RETRY
    assert not retry.owns_execution


def test_a_retry_against_an_unknown_entry_attaches() -> None:
    """The query may already have billed; re-executing would bill twice."""
    ledger, key = InMemoryExecutionLedger(), _key(CTX_A)
    drive_single_flight(ledger, key, correlation_id="c1", principal_ref="p1")
    ledger.complete(key, ExecutionStatus.UNKNOWN)

    retry = drive_single_flight(ledger, key, correlation_id="c2", principal_ref="p1")
    assert retry.disposition is Disposition.RETRY
    assert not retry.owns_execution


@pytest.mark.parametrize(
    "terminal",
    [
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMED_OUT,
        ExecutionStatus.CANCELLED_OVER_LIMIT,
    ],
    ids=lambda s: s.value,
)
def test_every_terminal_state_yields_a_re_request(terminal: ExecutionStatus) -> None:
    ledger, key = InMemoryExecutionLedger(), _key(CTX_A)
    drive_single_flight(ledger, key, correlation_id="c1", principal_ref="p1")
    ledger.complete(key, terminal)

    again = drive_single_flight(ledger, key, correlation_id="c2", principal_ref="p1")
    assert again.disposition is Disposition.RE_REQUEST
    assert again.owns_execution


def test_a_differing_fingerprint_never_attaches() -> None:
    """Equal identity, different authorization context: a different execution."""
    ledger = InMemoryExecutionLedger()
    first = drive_single_flight(ledger, _key(CTX_A), correlation_id="c1", principal_ref="p-a")
    second = drive_single_flight(ledger, _key(CTX_B), correlation_id="c2", principal_ref="p-b")

    assert first.owns_execution
    assert second.owns_execution, "a differing fingerprint must acquire, never attach"
    assert second.disposition is Disposition.NEW


def test_each_attachment_is_attributed_without_rewriting_the_acquirer() -> None:
    ledger, key = InMemoryExecutionLedger(), _key(CTX_A)
    drive_single_flight(ledger, key, correlation_id="c1", principal_ref="p-acquirer")
    attached = drive_single_flight(ledger, key, correlation_id="c2", principal_ref="p-attacher")

    assert attached.entry.principal_ref == "p-acquirer"
    assert [a.principal_ref for a in attached.entry.attachments] == ["p-attacher"]


# --- T085: re-request value stability (FR-067; SC-015) ----------------------


def test_unchanged_revisions_reproduce() -> None:
    verdict = compare_revisions({"google_play": "r1"}, {"google_play": "r1"})
    assert verdict.stability is Stability.REPRODUCIBLE
    assert verdict.values_are_reproducible
    assert verdict.reason_code is None


def test_a_moved_revision_reports_period_restated() -> None:
    verdict = compare_revisions({"google_play": "r1"}, {"google_play": "r2"})
    assert verdict.stability is Stability.RESTATED
    assert verdict.reason_code is ReasonCode.PERIOD_RESTATED
    assert verdict.changed_sources == ("google_play",)
    assert not verdict.values_are_reproducible


def test_changed_sources_are_sorted_for_determinism() -> None:
    verdict = compare_revisions(
        {"ios_app": "r1", "google_play": "r1"}, {"ios_app": "r2", "google_play": "r2"}
    )
    assert verdict.changed_sources == ("google_play", "ios_app")


def test_two_unknown_revisions_are_undetermined_not_unchanged() -> None:
    """Two unknowns are not evidence of sameness."""
    verdict = compare_revisions({"google_play": None}, {"google_play": None})
    assert verdict.stability is Stability.UNDETERMINED
    assert verdict.reason_code is ReasonCode.REPRODUCIBILITY_LIMITED
    assert not verdict.values_are_reproducible


def test_a_source_appearing_or_vanishing_is_undetermined() -> None:
    """The two runs did not read the same thing."""
    assert (
        compare_revisions({"google_play": "r1"}, {"google_play": "r1", "ios_app": "r1"}).stability
        is Stability.UNDETERMINED
    )
    assert (
        compare_revisions({"google_play": "r1", "ios_app": "r1"}, {"google_play": "r1"}).stability
        is Stability.UNDETERMINED
    )


def test_stability_derives_from_revisions_never_from_storage() -> None:
    """No stored figure participates in the comparison."""
    import ast
    import inspect

    from analytics_query.decision import revision_stability

    tree = ast.parse(inspect.getsource(revision_stability))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in ("cache", "stored", "previous_value", "load", "persist"):
        assert marker not in code, f"stability consults storage: {marker!r}"
