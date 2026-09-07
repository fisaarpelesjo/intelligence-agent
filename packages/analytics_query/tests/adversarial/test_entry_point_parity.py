"""Adversarial parity: the composition refuses what `002` refuses — 003:T004.

The entry point must not become a softer door into the same house. Every
adversarial shape `002` already rejects is driven through the composed path and
must produce the same governed refusal, with nothing executed and nothing
disclosed.

Most of these never reach the composition at all: a predicate-shaped identifier
or a null filter value dies in the request contract, before any of this code
runs. That is the point — the entry point adds no field, no coercion and no
second parse, so the contract's rejections remain the composition's rejections.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.date_filter import assert_no_date_filters
from analytics_query.contracts.operators import GovernedOperator
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange, GovernedFilter
from analytics_query.execute import ExecutionRefused, execute_analytics_query
from analytics_query.execution.ledger import AuthorizationContext
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.bundle import snapshot
from ..fixtures.catalog.decisions import ALLOWED, DENIED_ACCESS
from ..fixtures.entry_point import (
    DENIED_UPSTREAM,
    DIMENSION_COLUMNS,
    CollectingAuditSink,
    StubEvaluator,
    columns_for,
    metric_version,
    snapshot_of,
)
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.adversarial

ON = date(2026, 8, 12)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
CONTEXT = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="authpol-1",
)


def _run(request: AnalyticsQuery, *, decision: object = ALLOWED) -> FakeWarehouseAdapter:
    adapter = FakeWarehouseAdapter()
    with pytest.raises(ExecutionRefused):
        execute_analytics_query(
            request,
            evaluate=StubEvaluator(decision),  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            adapter=adapter,
            sink=CollectingAuditSink(),
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=frozenset({"google_play"}),
            columns=columns_for(),
            sample_catalog=snapshot_of("r-1"),
            metric_version_ids=("installs@1",),
            freshness_snapshot=snapshot(),
            metric_version=metric_version(),
            dimension_columns=DIMENSION_COLUMNS,
        )
    return adapter


# --- shapes the request contract refuses, unchanged by the composition -------

#: Each is a real `002` adversarial case. The contract must reject every one
#: before the composition can see it.
MALFORMED = [
    pytest.param({"metrics": ("installs; DROP TABLE x",)}, id="identifier-carrying-a-statement"),
    pytest.param({"metrics": ("installs--",)}, id="identifier-carrying-a-comment"),
    pytest.param({"metrics": ("Installs",)}, id="non-canonical-identifier"),
    pytest.param({"metrics": ("installs", "installs")}, id="duplicate-metric"),
    pytest.param({"metrics": ()}, id="no-metric"),
]


@pytest.mark.parametrize("overrides", MALFORMED)
def test_a_malformed_request_never_reaches_the_composition(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "metrics": ("installs",),
        "sources": ("google_play",),
        "date_range": JULY,
    }
    payload.update(overrides)
    with pytest.raises((ContractViolation, ValueError, TypeError)):
        build(AnalyticsQuery, **payload)


def test_a_reversed_range_is_refused_and_never_reordered() -> None:
    """Constructed inside the test: the contract refuses it at construction."""
    with pytest.raises((ContractViolation, ValueError)):
        DateRange(start=date(2026, 7, 31), end=date(2026, 7, 1))


def test_a_filter_naming_the_date_dimension_is_refused_before_compilation() -> None:
    """`date_range` is the sole temporal bound; the composition adds no second.

    `002` refuses this at its own date-filter guard rather than at construction,
    and the composition neither relaxes nor duplicates that guard.
    """
    query = build(
        AnalyticsQuery,
        metrics=("installs",),
        sources=("google_play",),
        date_range=JULY,
        filters=(
            GovernedFilter(dimension="date", operator=GovernedOperator.EQ, values=("2026-07-01",)),
        ),
    )
    refusal = assert_no_date_filters(query)
    assert refusal.refused
    assert refusal.code is AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE


def test_an_empty_filter_value_set_is_refused_by_the_contract() -> None:
    with pytest.raises((ContractViolation, ValueError)):
        build(
            AnalyticsQuery,
            metrics=("installs",),
            sources=("google_play",),
            date_range=JULY,
            filters=(GovernedFilter(dimension="country", operator=GovernedOperator.IN, values=()),),
        )


def test_the_entry_point_exposes_no_field_a_caller_could_widen_the_request_with() -> None:
    """An LLM-facing caller cannot smuggle query text alongside governed fields."""
    for smuggled in ("sql", "query", "query_text", "raw", "predicate", "order_by", "limit"):
        with pytest.raises((ContractViolation, ValueError, TypeError)):
            build(
                AnalyticsQuery,
                metrics=("installs",),
                sources=("google_play",),
                date_range=JULY,
                **{smuggled: "SELECT 1"},
            )


# --- refusals that do reach the composition ----------------------------------


def test_an_unauthorized_principal_bills_nothing_through_the_entry_point() -> None:
    adapter = _run(_valid(), decision=DENIED_ACCESS)
    assert adapter.total_calls == 0


def test_an_upstream_denial_bills_nothing_through_the_entry_point() -> None:
    adapter = _run(_valid(), decision=DENIED_UPSTREAM)
    assert adapter.total_calls == 0


def test_no_governed_limit_is_disclosed_on_any_refusal_the_composition_raises() -> None:
    """A refusal is not a channel for the policy."""
    for decision in (DENIED_ACCESS, DENIED_UPSTREAM, ALLOWED):
        adapter = FakeWarehouseAdapter()
        with pytest.raises(ExecutionRefused) as caught:
            execute_analytics_query(
                _valid(),
                evaluate=StubEvaluator(decision),  # type: ignore[arg-type]
                catalog_bundle=object(),  # type: ignore[arg-type]
                ledger=InMemoryExecutionLedger(),
                observations=FixtureObservationReader(),
                adapter=adapter,
                sink=CollectingAuditSink(),
                context=CONTEXT,
                correlation_id="c-1",
                principal_ref="p-1",
                on=ON,
                catalog_release_id="r-1",
                required_sources=frozenset({"google_play"}),
                columns=columns_for(),
                sample_catalog=snapshot_of("r-1"),
                metric_version_ids=("installs@1",),
                freshness_snapshot=snapshot(),
                metric_version=metric_version(),
                dimension_columns=DIMENSION_COLUMNS,
            )
        text = str(caught.value).lower()
        assert not any(
            leak in text for leak in ("1000000", "1_000_000", "bytes billed", "row ceiling")
        )


def test_every_refusal_carries_exactly_one_governed_code() -> None:
    """One code per refusal, from whichever namespace legitimately owns it."""
    for decision in (DENIED_ACCESS, DENIED_UPSTREAM, ALLOWED):
        try:
            _run(_valid(), decision=decision)
        except ExecutionRefused as refusal:  # pragma: no cover - _run already asserts
            pytest.fail(f"unexpected escape: {refusal}")
        # `_run` asserts the refusal itself; here we re-drive one to read its code.
    for decision, expected in (
        (DENIED_ACCESS, "authorization"),
        (DENIED_UPSTREAM, "upstream"),
        (ALLOWED, "policy"),
    ):
        with pytest.raises(ExecutionRefused) as caught:
            execute_analytics_query(
                _valid(),
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
                required_sources=frozenset({"google_play"}),
                columns=columns_for(),
                sample_catalog=snapshot_of("r-1"),
                metric_version_ids=("installs@1",),
                freshness_snapshot=snapshot(),
                metric_version=metric_version(),
                dimension_columns=DIMENSION_COLUMNS,
            )
        assert caught.value.stage == expected
        assert caught.value.code is not None


def _valid() -> AnalyticsQuery:
    return build(AnalyticsQuery, metrics=("installs",), sources=("google_play",), date_range=JULY)
