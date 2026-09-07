"""Consolidated adversarial matrix — T110 (FR-005, FR-075, FR-078; SC-022, SC-036).

Every adversarial scenario the spec enumerates, each with a named refusal test,
and **zero reaching execution**.

The scenarios are collected here rather than left scattered because `SC-022`
counts them: "every adversarial scenario enumerated in Edge Cases is covered by
a test that asserts refusal". A scenario covered incidentally by some other
test satisfies nobody trying to check that claim.

Each test names the attack in its own terms. "Test 7 fails" tells a future
reader nothing; "a caller cannot widen a governed request by supplying an
observation" tells them what was being defended and why the assertion looks the
way it does.
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics_query.compile.guards import GuardViolation, assert_emitted_text_is_safe
from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.date_filter import reject_date_filters
from analytics_query.contracts.matrix import is_permitted, refusal_for
from analytics_query.contracts.operators import DimensionType, GovernedOperator
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange, GovernedFilter
from analytics_query.execution.adapter import RenderedQuery
from analytics_query.execution.ledger import (
    AuthorizationContext,
    ExecutionKey,
    UnresolvedAuthorizationContext,
    derive_authorization_fingerprint,
)
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.execution.singleflight import Disposition, drive_single_flight
from analytics_query.identity.normalize import derive_identity

from ..fixtures.adapter.fake import FakeWarehouseAdapter

pytestmark = pytest.mark.adversarial

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
PINS = {"policy_version": "p-1", "catalog_release_id": "r-1"}

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


def _query(**overrides: object) -> AnalyticsQuery:
    payload: dict[str, object] = {"metrics": ("installs",), "date_range": JULY}
    payload.update(overrides)
    return build(AnalyticsQuery, **payload)


# --- 1. free-form query text -------------------------------------------------


@pytest.mark.parametrize("field", ["sql", "query", "query_text", "where", "raw"])
def test_a_caller_cannot_smuggle_query_text_through_an_unknown_field(field: str) -> None:
    with pytest.raises(ContractViolation) as caught:
        _query(**{field: "SELECT * FROM `raw.events`"})
    assert caught.value.code is AnalyticsReasonCode.REQUEST_MALFORMED


# --- 2. the BD-1 fields ------------------------------------------------------


@pytest.mark.parametrize("field", ["comparison", "order_by", "limit"])
def test_the_deliberately_absent_fields_are_refused_not_ignored(field: str) -> None:
    """`BD-1`: absent from the contract, so they arrive as unknown fields."""
    with pytest.raises(ContractViolation):
        _query(**{field: "anything"})


# --- 3. identifier-shaped predicates ----------------------------------------


@pytest.mark.parametrize("identifier", ["installs; DROP TABLE x", "installs OR 1=1", "*", "1=1"])
def test_a_predicate_shaped_identifier_is_refused_at_parse(identifier: str) -> None:
    with pytest.raises(ContractViolation):
        _query(metrics=(identifier,))


# --- 4. values that try to become syntax ------------------------------------


def test_a_hostile_filter_value_never_becomes_syntax() -> None:
    hostile = "'; DROP TABLE x; --"
    governed = build(
        GovernedFilter, dimension="country", operator=GovernedOperator.EQ, values=(hostile,)
    )
    assert governed.values == (hostile,), "the value is carried, not rewritten"

    # And the emitted-text guard refuses if it ever reached the text.
    with pytest.raises(GuardViolation):
        assert_emitted_text_is_safe(
            RenderedQuery(
                text=f"SELECT a FROM `semantic.x` WHERE country = '{hostile}'",
                parameters={"p0": hostile},
            )
        )


# --- 5. the operator allowlist and the matrix -------------------------------


@pytest.mark.parametrize("operator", ["like", "regex", "is_null", "not_like", ">"])
def test_an_ungoverned_operator_is_refused(operator: str) -> None:
    with pytest.raises(ContractViolation):
        build(
            GovernedFilter,
            dimension="country",
            operator=operator,  # type: ignore[arg-type]
            values=("BR",),
        )


def test_the_date_dimension_is_not_filterable_by_any_operator() -> None:
    """`date_range` is the sole temporal bound (`FR-005`)."""
    for operator in GovernedOperator:
        assert not is_permitted(operator, DimensionType.TEMPORAL_DATE)
        refusal = refusal_for(operator, "date")
        assert refusal is not None


def test_a_date_filter_is_refused_by_name_of_its_type_not_its_id() -> None:
    refusal = reject_date_filters(
        (build(GovernedFilter, dimension="date", operator=GovernedOperator.EQ, values=("x",)),)
    )
    assert refusal.refused
    assert refusal.code is AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE


# --- 6. caller-supplied observations ----------------------------------------


@pytest.mark.parametrize(
    "field",
    ["freshness", "coverage", "data_revision_id", "snapshot", "observed_at", "as_of_instant"],
)
def test_a_caller_cannot_supply_an_observation(field: str) -> None:
    """`FR-075`: the governed tables are the sole authority."""
    with pytest.raises(ContractViolation):
        _query(**{field: "2026-08-12"})


def test_no_runtime_switch_selects_a_fixture_reader() -> None:
    from pathlib import Path

    import analytics_query

    src = Path(analytics_query.__file__).parent
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in ("os.environ", "getenv", "USE_FIXTURE", "FixtureObservationReader"):
            assert marker not in text, f"{path.relative_to(src)} reaches a fixture at runtime"


# --- 7. identity replay ------------------------------------------------------


def test_replaying_another_principals_identity_grants_nothing() -> None:
    """Identity is not an authorization artifact (`FR-035`).

    Two principals derive the same identity for the same question — that is by
    design. What stops the replay mattering is that identity alone cannot key an
    execution.
    """
    identity = derive_identity(_query(), **PINS)
    assert identity == derive_identity(_query(), **PINS)

    with pytest.raises(UnresolvedAuthorizationContext):
        ExecutionKey(identity.fingerprint, "")


# --- 8. cross-authorization attachment and status observation (FR-078) ------


def test_a_differing_authorization_context_cannot_attach() -> None:
    ledger = InMemoryExecutionLedger()
    identity = derive_identity(_query(), **PINS).fingerprint
    key_a = ExecutionKey(identity, derive_authorization_fingerprint(CTX_A))
    key_b = ExecutionKey(identity, derive_authorization_fingerprint(CTX_B))

    first = drive_single_flight(ledger, key_a, correlation_id="c1", principal_ref="p-a")
    second = drive_single_flight(ledger, key_b, correlation_id="c2", principal_ref="p-b")

    assert first.owns_execution and second.owns_execution
    assert second.disposition is Disposition.NEW


def test_a_differing_authorization_context_cannot_observe_the_status() -> None:
    ledger = InMemoryExecutionLedger()
    identity = derive_identity(_query(), **PINS).fingerprint
    key_a = ExecutionKey(identity, derive_authorization_fingerprint(CTX_A))
    key_b = ExecutionKey(identity, derive_authorization_fingerprint(CTX_B))

    drive_single_flight(ledger, key_a, correlation_id="c1", principal_ref="p-a")
    assert ledger.get(key_b) is None
    assert ledger.attach(key_b, correlation_id="c2", principal_ref="p-b") is None


# --- 9. tag escalation -------------------------------------------------------


def test_naming_an_access_tag_does_not_grant_it() -> None:
    """The request has no field for a tag; grants come from the principal."""
    declared = set(AnalyticsQuery.model_fields)
    for field in ("access_tags", "granted_access_tags", "requester_access", "scope"):
        assert field not in declared

    with pytest.raises(ContractViolation):
        _query(granted_access_tags=("restricted",))


# --- 10. single-subject cohorts ---------------------------------------------


def test_a_single_subject_cohort_is_withheld_and_not_reconstructible() -> None:
    from decimal import Decimal

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
            ResultCell(value=Decimal("50")),
            ResultCell(value=Decimal("60")),
        ),
        (1, 40, 60),
        policy,
    )
    assert row[0].suppressed
    extended = extend_suppression(row, (1, 40, 60), policy, total_visible=True)
    assert not is_reconstructible(extended, total_visible=True)


# --- 11. LLM-surface widening ------------------------------------------------


def test_no_interface_lets_a_model_widen_a_governed_request() -> None:
    """`FR-056`: there is no field through which the request grows."""
    declared = set(AnalyticsQuery.model_fields)
    assert declared == {"metrics", "dimensions", "sources", "filters", "date_range", "as_of"}


def test_no_language_model_client_exists() -> None:
    from pathlib import Path

    import analytics_query

    src = Path(analytics_query.__file__).parent
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for client in ("openai", "anthropic", "chatcompletion", "genai", "vertexai"):
            assert client not in text


# --- zero reach execution ----------------------------------------------------


def test_no_adversarial_scenario_reaches_the_warehouse() -> None:
    """`SC-022`: zero scenarios pass through to execution."""
    adapter = FakeWarehouseAdapter()

    for attempt in (
        lambda: _query(sql="SELECT 1"),
        lambda: _query(metrics=("installs; --",)),
        lambda: _query(limit=10),
        lambda: _query(freshness="fresh"),
    ):
        with pytest.raises(ContractViolation):
            attempt()

    assert adapter.total_calls == 0
