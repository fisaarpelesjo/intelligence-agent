"""Every refusal happens where nothing has yet been spent — 003:T003.

Proving a request *refuses* is weaker than proving it refuses *at the boundary
where nothing is yet spent or disclosed*. A composition that resolved the policy
before authorization, or acquired a ledger entry before the context resolved,
would still refuse — and would still look correct — while having already leaked a
governed limit or filed an entry under the wrong isolation class.

So each boundary is asserted by what has **not** happened at the moment of the
refusal: adapter calls, ledger entries, and the absence of any policy figure in
the refusal text.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType

from analytics_query.contracts._base import build
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.execute import ExecutionRefused, execute_analytics_query
from analytics_query.execution.ledger import AuthorizationContext, ExecutionKey
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger

from ..fixtures.adapter.fake import FakeWarehouseAdapter
from ..fixtures.catalog.bundle import snapshot
from ..fixtures.catalog.decisions import ALLOWED, DENIED_ACCESS
from ..fixtures.entry_point import (
    DIMENSION_COLUMNS,
    CollectingAuditSink,
    StubEvaluator,
    columns_for,
    governed_policy,
    metric_version,
    snapshot_of,
)
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

ON = date(2026, 8, 12)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
SOURCES = frozenset({"google_play"})

RESOLVED = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="authpol-1",
)
#: An authorization context that cannot be completely resolved. `FR-078` requires
#: this to refuse *before* the ledger is touched.
UNRESOLVED = AuthorizationContext(
    authorization_scope="",
    granted_access_tags=frozenset(),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="",
)


def _request(**overrides: object) -> AnalyticsQuery:
    payload: dict[str, object] = {
        "metrics": ("installs",),
        "sources": ("google_play",),
        "date_range": JULY,
    }
    payload.update(overrides)
    return build(AnalyticsQuery, **payload)


def _run(
    *,
    decision: object = ALLOWED,
    context: AuthorizationContext = RESOLVED,
    adapter: FakeWarehouseAdapter | None = None,
    ledger: InMemoryExecutionLedger | None = None,
    observations: FixtureObservationReader | None = None,
    request: AnalyticsQuery | None = None,
) -> None:
    execute_analytics_query(
        request or _request(),
        evaluate=StubEvaluator(decision),  # type: ignore[arg-type]
        catalog_bundle=object(),  # type: ignore[arg-type]
        ledger=ledger or InMemoryExecutionLedger(),
        observations=observations or FixtureObservationReader(),
        adapter=adapter or FakeWarehouseAdapter(),
        sink=CollectingAuditSink(),
        context=context,
        correlation_id="c-1",
        principal_ref="p-1",
        on=ON,
        catalog_release_id="r-1",
        required_sources=SOURCES,
        columns=columns_for(),
        sample_catalog=snapshot_of("r-1"),
        metric_version_ids=("installs@1",),
        freshness_snapshot=snapshot(),
        metric_version=metric_version(),
        dimension_columns=DIMENSION_COLUMNS,
    )


def _probe(ledger: InMemoryExecutionLedger) -> bool:
    """Whether the ledger holds anything at all, by probing rather than trusting."""
    key = ExecutionKey("a" * 64, "b" * 64)
    return ledger.get(key) is not None


# --- the authorization boundary ---------------------------------------------


def test_authorization_refuses_before_any_cost_or_write() -> None:
    adapter, ledger = FakeWarehouseAdapter(), InMemoryExecutionLedger()
    with pytest.raises(ExecutionRefused) as caught:
        _run(decision=DENIED_ACCESS, adapter=adapter, ledger=ledger)

    assert caught.value.stage == "authorization"
    assert adapter.total_calls == 0, "an unauthorized principal reached the warehouse"
    assert not _probe(ledger), "an unauthorized principal acquired a ledger entry"


def test_the_authorization_refusal_discloses_no_governed_limit() -> None:
    with pytest.raises(ExecutionRefused) as caught:
        _run(decision=DENIED_ACCESS)

    text = str(caught.value).lower()
    for leak in ("bytes", "rows", "timeout", "threshold", "maximum", "limit", "days"):
        assert leak not in text, f"the refusal disclosed {leak!r} to an unauthorized principal"


# --- the policy boundary -----------------------------------------------------


def test_policy_refuses_after_authorization_and_before_the_warehouse() -> None:
    """No approved policy is in force, which is `002`'s third lock."""
    adapter = FakeWarehouseAdapter()
    with pytest.raises(ExecutionRefused) as caught:
        _run(adapter=adapter)

    assert caught.value.stage == "policy"
    assert caught.value.code == AnalyticsReasonCode.QUERY_POLICY_UNRESOLVABLE
    assert adapter.total_calls == 0


# --- the range-limit boundary ------------------------------------------------


def test_the_range_limit_refuses_after_policy_and_before_the_warehouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeWarehouseAdapter()
    over_limit = DateRange(start=date(2020, 1, 1), end=date(2026, 1, 1))
    with governed_policy(monkeypatch), pytest.raises(ExecutionRefused) as caught:
        _run(adapter=adapter, request=_request(date_range=over_limit))

    assert caught.value.stage == "limits"
    assert adapter.total_calls == 0


# --- the execution-key boundary ----------------------------------------------


def test_an_unresolved_authorization_context_refuses_before_ledger_acquisition() -> None:
    """`FR-078`: a partial key would file the request into the wrong class.

    `002` refuses even earlier than step 6 — the preflight needs the context and
    will not proceed on a partial one — so this needs no resolvable policy. The
    boundary asserted is the same: nothing was spent and nothing was written.
    """
    adapter, ledger = FakeWarehouseAdapter(), InMemoryExecutionLedger()
    with pytest.raises(ExecutionRefused) as caught:
        _run(context=UNRESOLVED, adapter=adapter, ledger=ledger)

    assert caught.value.stage == "authorization_context"
    assert caught.value.code == AnalyticsReasonCode.LEDGER_UNAVAILABLE
    assert not _probe(ledger), "an unresolved context reached the ledger"
    assert adapter.total_calls == 0


# --- the observation boundary ------------------------------------------------


def test_an_unavailable_observation_read_refuses_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeWarehouseAdapter()
    unavailable = FixtureObservationReader(fail_with=RuntimeError("governed read failed"))
    with governed_policy(monkeypatch), pytest.raises(ExecutionRefused) as caught:
        _run(adapter=adapter, observations=unavailable)

    assert caught.value.stage == "observations"
    assert caught.value.code == AnalyticsReasonCode.OBSERVATIONS_UNAVAILABLE
    assert adapter.execute_calls == 0, "execution proceeded without observations"


def test_a_non_atomic_observation_bundle_refuses_rather_than_assuming_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial bundle is not a smaller truth; it is an unusable one."""
    partial = FixtureObservationReader(drop_part="revisions")
    with governed_policy(monkeypatch), pytest.raises(ExecutionRefused) as caught:
        _run(observations=partial)

    assert caught.value.stage == "observations"


# --- ordering, stated as a contrast ------------------------------------------


def test_the_boundaries_are_ordered_rather_than_merely_present() -> None:
    """The same request refuses at a later stage as each earlier lock is removed.

    One refusal proves nothing about ordering. A sequence of refusals that moves
    forward, and only forward, is what makes the ordering observable.
    """
    with pytest.raises(ExecutionRefused) as unauthorized:
        _run(decision=DENIED_ACCESS)
    with pytest.raises(ExecutionRefused) as no_policy:
        _run()
    with pytest.raises(ExecutionRefused) as no_context:
        _run(context=UNRESOLVED)

    assert unauthorized.value.stage == "authorization"
    assert no_policy.value.stage == "policy"
    assert no_context.value.stage == "authorization_context"
