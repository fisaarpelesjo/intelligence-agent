"""A catalog change during execution releases nothing — 003:T009.

`002`'s `FR-029`: when the catalog release or a contributing metric definition
changes between validation and execution, the execution is abandoned rather than
completed against a definition the decision never validated. The check lives in
step 9, not inside `run_until_evaluation`, so the composition is what has to
invoke it — this phase makes that explicit.

The property is stated twice on purpose, because the weaker half is easy to
satisfy accidentally:

* the request **refuses**, and
* it refuses **at the mid-flight check specifically** — after the shape check has
  already agreed, so the refusal cannot be a shape mismatch wearing a different
  name — and releases no result and persists no analytical value.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType

from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.execute import ExecutedAnswer, execute_analytics_query
from analytics_query.execution.ledger import AuthorizationContext
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.execution.midflight import CatalogSnapshot

from ..fixtures.catalog.bundle import snapshot
from ..fixtures.catalog.decisions import ALLOWED
from ..fixtures.entry_point import (
    DIMENSION_COLUMNS,
    CollectingAuditSink,
    StubEvaluator,
    changing_snapshot,
    columns_for,
    governed_policy,
    metric_version,
    snapshot_of,
    working_adapter,
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

BEFORE = CatalogSnapshot(release_id="r-1", metric_version_ids=("installs@1",))
CHANGED_RELEASE = CatalogSnapshot(release_id="r-2", metric_version_ids=("installs@1",))
CHANGED_VERSION = CatalogSnapshot(release_id="r-1", metric_version_ids=("installs@2",))


def _run(
    sample_catalog: Callable[[], CatalogSnapshot], sink: CollectingAuditSink | None = None
) -> ExecutedAnswer:
    return execute_analytics_query(
        build(AnalyticsQuery, metrics=("installs",), sources=("google_play",), date_range=JULY),
        evaluate=StubEvaluator(ALLOWED),  # type: ignore[arg-type]
        catalog_bundle=object(),  # type: ignore[arg-type]
        ledger=InMemoryExecutionLedger(),
        observations=FixtureObservationReader(),
        adapter=working_adapter(),
        sink=sink or CollectingAuditSink(),
        context=CONTEXT,
        correlation_id="c-1",
        principal_ref="p-1",
        on=ON,
        catalog_release_id="r-1",
        required_sources=frozenset({"google_play"}),
        columns=columns_for(),
        sample_catalog=sample_catalog,
        metric_version_ids=("installs@1",),
        freshness_snapshot=snapshot(),
        metric_version=metric_version(),
        dimension_columns=DIMENSION_COLUMNS,
    )


def test_the_composition_samples_the_catalog_around_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Twice, not once. A single sample cannot detect a change."""
    samples: list[int] = []

    def counting() -> CatalogSnapshot:
        samples.append(1)
        return BEFORE

    with governed_policy(monkeypatch), contextlib.suppress(Exception):
        _run(counting)  # reaching the sampling is the point
    assert len(samples) == 2, f"expected a before and an after sample, got {len(samples)}"


@pytest.mark.parametrize(
    ("after", "what"),
    [(CHANGED_RELEASE, "release"), (CHANGED_VERSION, "metric version")],
)
def test_a_catalog_change_during_execution_refuses(
    monkeypatch: pytest.MonkeyPatch, after: CatalogSnapshot, what: str
) -> None:
    with governed_policy(monkeypatch), pytest.raises(Exception) as caught:
        _run(changing_snapshot(BEFORE, after))

    message = str(caught.value).lower()
    assert "catalog" in message or "changed" in message, (
        f"a changed {what} must refuse at the mid-flight check, got: {caught.value}"
    )


def test_a_changed_catalog_releases_no_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever the warehouse returned is discarded, not partially returned."""
    with governed_policy(monkeypatch):
        outcome: object
        try:
            outcome = _run(changing_snapshot(BEFORE, CHANGED_RELEASE))
        except Exception as refusal:
            outcome = refusal
    assert not isinstance(outcome, ExecutedAnswer), "a result was released after a catalog change"


def test_a_changed_catalog_emits_no_completion_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """No completion event means no claim that the execution stands.

    The result is withheld *and* unrecorded as complete, which is what stops a
    reader from later concluding the figure was governed.
    """
    sink = CollectingAuditSink()
    with governed_policy(monkeypatch), contextlib.suppress(Exception):
        _run(changing_snapshot(BEFORE, CHANGED_RELEASE), sink)  # the refusal is the point
    assert "EXECUTION_COMPLETE" not in sink.stages()


def test_a_changed_catalog_persists_no_analytical_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing the warehouse returned reaches any durable surface."""
    sink = CollectingAuditSink()
    with governed_policy(monkeypatch), contextlib.suppress(Exception):
        _run(changing_snapshot(BEFORE, CHANGED_VERSION), sink)  # the refusal is the point
    for event in sink.events:
        serialised = event.model_dump_json()
        assert '"row_count":' not in serialised or '"row_count":null' in serialised
        assert '"actual_bytes":' not in serialised or '"actual_bytes":null' in serialised


def test_an_unchanged_catalog_does_not_refuse_at_the_mid_flight_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must not fire on the ordinary case.

    Without this the suite could pass with a mid-flight check that always
    refused, which would be a broken feature rather than a safe one.
    """
    with governed_policy(monkeypatch):
        answer = _run(snapshot_of("r-1"))
    assert answer.result is not None, "an unchanged catalog must produce a result"
