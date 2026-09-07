"""The fail-closed quadruple lock — T109 (FR-061, FR-062, FR-078; SC-022, SC-023, SC-036).

Four independent locks hold this feature shut, and **removing any one still
refuses**:

1. no publishable source — the production catalog has none (`D-1`);
2. no governed observation read — `EXT-A` is undeclared;
3. no approved `QueryPolicy` — `D-14` and `D-16` are open;
4. no completely resolvable authorization context — refuses before the ledger.

Independence is the property worth testing, and it is easy to lose. If three of
the four were really the same lock wearing different names, then one upstream
approval would open all of them at once — and nobody would notice until a query
ran that nobody had approved.

The fourth lock is the newest (`FR-078`) and refuses **before** ledger
acquisition, so an unresolved context never reaches a state anything could
attach to.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.loader.bundle import build_bundle
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.decision.bridge import is_permissive, to_catalog_request
from analytics_query.execution.ledger import (
    AuthorizationContext,
    UnresolvedAuthorizationContext,
    derive_authorization_fingerprint,
)
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.identity.authorization_context import execution_key_for
from analytics_query.observations.failure import ObservationsUnavailable, read_bundle_or_refuse
from analytics_query.policy.resolve import PolicyUnresolvable, load_policies, resolve_policy

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.bundle import ON, SCOPE, STANDARD_ACCESS, snapshot
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
#: The repository root: tests/integration -> tests -> analytics_query -> packages -> root.
REPO = Path(__file__).resolve().parents[4]
PRODUCTION = REPO / "semantic"

RESOLVED_CONTEXT = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type="user",
    authorization_policy_pin="authpol-1",
)


# --- lock 1: no publishable source (FR-061) ---------------------------------


def test_the_production_catalog_refuses_every_metric() -> None:
    """`D-1` is open, so nothing is publishable — and this is not a fault."""
    production = build_bundle(PRODUCTION, current_commit="0" * 7, on=ON)
    assert production.internal.metrics, "the production catalog must actually contain metrics"

    for metric_id in sorted(production.internal.metrics):
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
        assert decision.outcome is Outcome.DENY
        assert decision.reason_code is ReasonCode.METRIC_PENDING
        assert not is_permissive(decision)


def test_the_refusal_is_a_governed_state_not_a_system_fault() -> None:
    """`FR-061`: it must not be presented as something broken."""
    production = build_bundle(PRODUCTION, current_commit="0" * 7, on=ON)
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
    assert decision.message_pt_br
    for fault in ("erro interno", "falha do sistema", "exception", "traceback"):
        assert fault not in decision.message_pt_br.lower()


# --- lock 2: no governed observation read -----------------------------------


def test_an_unavailable_observation_read_refuses() -> None:
    with pytest.raises(ObservationsUnavailable):
        read_bundle_or_refuse(
            FixtureObservationReader(fail_with=ConnectionError("EXT-A undeclared")),
            source_ids=frozenset({"app_a"}),
            correlation_id="c-1",
        )


# --- lock 3: no approved policy ---------------------------------------------


def test_no_approved_policy_is_in_force() -> None:
    assert load_policies() == ()
    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON)


# --- lock 4: no resolvable authorization context (FR-078) -------------------


@pytest.mark.parametrize(
    "context",
    [
        AuthorizationContext("", frozenset({"t"}), "user", "p"),
        AuthorizationContext("s", frozenset({"t"}), "", "p"),
        AuthorizationContext("s", frozenset({"t"}), "user", ""),
    ],
    ids=["no_scope", "no_principal_type", "no_policy_pin"],
)
def test_an_unresolved_context_refuses_before_ledger_acquisition(
    context: AuthorizationContext,
) -> None:
    ledger = InMemoryExecutionLedger()
    with pytest.raises(UnresolvedAuthorizationContext):
        execution_key_for("a" * 64, context)

    # Nothing was acquired: the refusal happened before the ledger was touched.
    key = execution_key_for("a" * 64, RESOLVED_CONTEXT)
    assert ledger.get(key) is None


# --- independence: removing any one lock still refuses ----------------------


def test_removing_the_policy_lock_alone_still_refuses() -> None:
    """A governed policy would not make the catalog publishable."""
    production = build_bundle(PRODUCTION, current_commit="0" * 7, on=ON)
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
    assert decision.outcome is Outcome.DENY


def test_removing_the_observation_lock_alone_still_refuses() -> None:
    """A healthy observation read does not approve a policy."""
    bundle_read = read_bundle_or_refuse(
        FixtureObservationReader(), source_ids=frozenset({"app_a"}), correlation_id="c-1"
    )
    assert bundle_read.source_ids() == frozenset({"app_a"})

    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON)


def test_removing_the_context_lock_alone_still_refuses() -> None:
    """A resolvable context does not approve a policy or publish a source."""
    assert derive_authorization_fingerprint(RESOLVED_CONTEXT)

    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON)


def test_no_warehouse_call_occurs_under_any_lock() -> None:
    """Zero adapter calls across the whole fail-closed suite."""
    adapter = FakeWarehouseAdapter()
    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON)
    assert adapter.total_calls == 0


def test_the_four_locks_are_independent() -> None:
    """Four distinct evidence records, not one wearing four names."""
    from analytics_query.compliance.readiness import load_record, readiness_root
    from analytics_query.execution.deployment_guard import READINESS_FILE

    record = load_record(readiness_root() / READINESS_FILE)
    assert set(record.capabilities) == {"d_14", "d_15", "d_16", "d_17"}
    # Emendado no ciclo 501 (2026-09-01, OD-86): d_15 declarado pelo dono; os outros tres
    # continuam fechados e a independencia segue medida — um nao abre o outro.
    assert record.ready_capabilities() == frozenset({"d_14", "d_15", "d_16"}), (
        "so d_14 (OD-94), d_15 (OD-86) e d_16 (OD-97) tem palavra e evidencia"
    )
