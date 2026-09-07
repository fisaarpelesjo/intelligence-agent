"""Authorization before cost — T065 (FR-014; SC-009).

`FR-014` says an authorization failure is terminal with **no cost incurred**.
That is only meaningful if it is observed rather than asserted, so this test
reads counters:

* the fake adapter's call counter is 0 — no dry run, no execution, no bytes;
* the in-memory ledger is empty — no entry was acquired, so nothing was
  attributed or reserved;
* the response carries no policy limit — the principal learns nothing about the
  governed policy by being refused by it.

The third is the one that is easy to lose. Resolving the policy before checking
authorisation would still cost nothing at the warehouse, and would still look
correct — while telling an unauthorized caller the maximum row count.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType

from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.execution.ledger import AuthorizationContext, ExecutionKey
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.pipeline import PipelineRefusal, run_until_evaluation

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.decisions import ALLOWED, DENIED_ACCESS
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

ON = date(2026, 8, 12)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
SOURCES = frozenset({"google_play"})

CONTEXT = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="authpol-1",
)


def _request() -> AnalyticsQuery:
    return build(AnalyticsQuery, metrics=("installs",), sources=("google_play",), date_range=JULY)


class _Evaluator:
    """A stub verdict plus a call counter. Decides nothing."""

    def __init__(self, decision: object) -> None:
        self.decision = decision
        self.calls = 0
        self.snapshots: list[object] = []

    def __call__(self, request: object, bundle: object, **kwargs: object) -> object:
        self.calls += 1
        self.snapshots.append(kwargs.get("snapshot"))
        return self.decision


def _run(evaluator: _Evaluator, adapter: FakeWarehouseAdapter, ledger: InMemoryExecutionLedger):
    return run_until_evaluation(
        _request(),
        evaluate=evaluator,  # type: ignore[arg-type]
        catalog_bundle=object(),  # type: ignore[arg-type]
        ledger=ledger,
        observations=FixtureObservationReader(),
        context=CONTEXT,
        correlation_id="c-1",
        principal_ref="p-1",
        on=ON,
        catalog_release_id="r-1",
        required_sources=SOURCES,
    )


# --- the refusal costs nothing ----------------------------------------------


def test_an_unauthorized_principal_reaches_no_warehouse_call() -> None:
    adapter, ledger = FakeWarehouseAdapter(), InMemoryExecutionLedger()
    with pytest.raises(PipelineRefusal) as caught:
        _run(_Evaluator(DENIED_ACCESS), adapter, ledger)

    assert caught.value.stage == "authorization"
    assert adapter.total_calls == 0
    assert adapter.dry_run_calls == 0
    assert adapter.execute_calls == 0


def test_an_unauthorized_principal_acquires_no_ledger_entry() -> None:
    """No entry means no attribution, no reservation, nothing to reconcile."""
    ledger = InMemoryExecutionLedger()
    with pytest.raises(PipelineRefusal):
        _run(_Evaluator(DENIED_ACCESS), FakeWarehouseAdapter(), ledger)

    # Probing any key finds nothing: acquisition never happened.
    assert ledger.get(ExecutionKey("a" * 64, "b" * 64)) is None
    assert (
        ledger.attach(ExecutionKey("a" * 64, "b" * 64), correlation_id="c-2", principal_ref="p-2")
        is None
    )


def test_the_refusal_discloses_no_policy_limit() -> None:
    """A principal refused by the policy learns nothing about the policy."""
    with pytest.raises(PipelineRefusal) as caught:
        _run(_Evaluator(DENIED_ACCESS), FakeWarehouseAdapter(), InMemoryExecutionLedger())

    text = str(caught.value).lower()
    for leak in ("bytes", "rows", "timeout", "threshold", "maximum", "limit", "days"):
        assert leak not in text


def test_the_refusal_reads_no_observations() -> None:
    """Reading the governed tables is a billed read; it must not happen."""
    reader = FixtureObservationReader(fail_with=AssertionError("observations must not be read"))
    with pytest.raises(PipelineRefusal):
        run_until_evaluation(
            _request(),
            evaluate=_Evaluator(DENIED_ACCESS),  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=reader,
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=SOURCES,
        )


# --- the preflight is the only pre-authorization evaluation -----------------


def test_the_preflight_passes_no_snapshot() -> None:
    """Gate 7 short-circuits before anything needs observations."""
    evaluator = _Evaluator(DENIED_ACCESS)
    with pytest.raises(PipelineRefusal):
        _run(evaluator, FakeWarehouseAdapter(), InMemoryExecutionLedger())

    assert evaluator.calls == 1
    assert evaluator.snapshots == [None]


def test_an_authorized_request_proceeds_past_authorization() -> None:
    """The refusal that follows is the policy's, not the principal's.

    Today `query-policy.yaml` holds no approved instance, so an authorized
    request still refuses — at `policy`, one stage later. That difference is
    exactly what shows the ordering is real.
    """
    evaluator = _Evaluator(ALLOWED)
    with pytest.raises(PipelineRefusal) as caught:
        _run(evaluator, FakeWarehouseAdapter(), InMemoryExecutionLedger())

    assert caught.value.stage == "policy"
    assert evaluator.calls == 1


def test_an_authorized_request_still_reaches_no_warehouse_before_policy() -> None:
    adapter = FakeWarehouseAdapter()
    with pytest.raises(PipelineRefusal):
        _run(_Evaluator(ALLOWED), adapter, InMemoryExecutionLedger())
    assert adapter.total_calls == 0
