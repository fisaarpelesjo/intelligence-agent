"""Shared fixtures for the ADR 0010 composed entry point — 003 Phase A0.

Test package only. Nothing here decides anything: these stand in for the pieces
the entry point *calls* so its composition can be observed. The
fixture-containment scan covers `src/`, so none of this is reachable from
production.

`resolve_policy` is deliberately not injectable through `run_until_evaluation`
— production resolves from governed content and there is no runtime override.
The repository currently holds **no approved policy**, so step 9 is unreachable
end to end, which is `002`'s third lock and is correct. `governed_policy` patches
the resolver for the tests that need to observe step 9 at all; the patch lives in
the test process and adds no switch to `src/`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest
from semantic_catalog.contracts.metric import MetricVersion
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.loader.projection import MetricView

from analytics_query.contracts._base import build
from analytics_query.contracts.audit import AnalyticsAuditEvent
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.result import ResultColumn
from analytics_query.execution.adapter import ResultColumnSchema, ResultSchema
from analytics_query.execution.midflight import CatalogSnapshot

from .adapter.fake import FakeWarehouseAdapter
from .catalog.bundle import bundle
from .catalog.decisions import decision

__all__ = [
    "COLUMNS",
    "DENIED_UPSTREAM",
    "DIMENSION_COLUMNS",
    "FIXTURE_METRIC",
    "FIXTURE_POLICY",
    "FIXTURE_SOURCE",
    "SCHEMA",
    "CollectingAuditSink",
    "FailingAuditSink",
    "StubEvaluator",
    "columns_for",
    "governed_policy",
    "metric_version",
    "snapshot_of",
    "working_adapter",
]

#: Gates 1-6 ran and one of 1, 2, 4, 5 or 6 denied. Distinct from a gate-3
#: denial: authorization passed, so the refusal is passed through verbatim.
DENIED_UPSTREAM = decision(
    outcome=Outcome.DENY, reason_code=ReasonCode.METRIC_NOT_AVAILABLE_FOR_SOURCE
)

FIXTURE_POLICY = build(
    QueryPolicy,
    version="fixture-p-1",
    effective_from=date(2026, 1, 1),
    approval=PolicyApproval(
        approver_role="data_platform", evidence_ref="fixture", approved_on=date(2026, 1, 1)
    ),
    maximum_bytes_billed=1_000_000,
    maximum_rows=1_000,
    execution_timeout_seconds=30,
    maximum_range_days=366,
    minimum_aggregation_threshold=5,
)

#: A real metric from `001`'s fixture catalog, so compilation is genuine rather
#: than stubbed. `app_sessions` sums over `semantic.fixture_daily` and allows
#: `country` and `app_version` as breakdowns.
FIXTURE_METRIC = "app_sessions"
FIXTURE_SOURCE = "app_a"
DIMENSION_COLUMNS = {"country": "country", "app_version": "app_version"}


def metric_version() -> MetricVersion:
    """The published `app_sessions` version, resolved from the fixture bundle.

    Narrowed rather than cast: `public` holds a `MetricView` for a published
    metric and a `PendingStub` for a pending one, and only the former carries a
    definition. Asserting the narrowing keeps a catalog change from silently
    handing the tests a stub.
    """
    view = bundle().public[FIXTURE_METRIC]
    assert isinstance(view, MetricView), (
        f"{FIXTURE_METRIC} must be published in the fixture catalog"
    )
    return view.metric.versions[0]


SCHEMA = ResultSchema(columns=(ResultColumnSchema(FIXTURE_METRIC, "INT64", "sessions"),))
COLUMNS = (ResultColumn(identifier=FIXTURE_METRIC, unit="sessions", is_metric=True),)


def working_adapter(**overrides: object) -> FakeWarehouseAdapter:
    """An adapter whose schema matches the governed columns, so step 9 completes.

    The default `FakeWarehouseAdapter` returns an empty schema, which is a
    shape mismatch by construction — useful for refusal tests, useless for
    observing the composed happy path.
    """
    payload: dict[str, object] = {"schema": SCHEMA, "rows": ((123,),)}
    payload.update(overrides)
    return FakeWarehouseAdapter(**payload)  # type: ignore[arg-type]


def columns_for() -> tuple[ResultColumn, ...]:
    """The governed result columns, as the catalog would supply them."""
    return COLUMNS


def snapshot_of(
    release_id: str, *, versions: tuple[str, ...] = ("installs@1",)
) -> Callable[[], CatalogSnapshot]:
    """A catalog sampler returning the same snapshot every time.

    The entry point samples before and after execution; returning a constant is
    the *unchanged* case. A test that wants a mid-flight change supplies a
    sampler whose second answer differs.
    """

    def _sample() -> CatalogSnapshot:
        return CatalogSnapshot(release_id=release_id, metric_version_ids=versions)

    return _sample


def changing_snapshot(
    first: CatalogSnapshot, second: CatalogSnapshot
) -> Callable[[], CatalogSnapshot]:
    """A sampler that answers ``first`` once and ``second`` thereafter."""
    answers = iter((first,))

    def _sample() -> CatalogSnapshot:
        return next(answers, second)

    return _sample


class StubEvaluator:
    """A fixed verdict plus call counters. Decides nothing."""

    def __init__(self, verdict: Any, *, full_verdict: Any = None) -> None:
        self._verdict = verdict
        self._full = full_verdict
        self.calls = 0
        self.snapshots: list[Any] = []

    def __call__(self, request: Any, bundle: Any, **kwargs: Any) -> Any:
        self.calls += 1
        snapshot = kwargs.get("snapshot")
        self.snapshots.append(snapshot)
        if snapshot is not None and self._full is not None:
            return self._full
        return self._verdict


class CollectingAuditSink:
    """Records every event it accepts, in order."""

    def __init__(self) -> None:
        self.events: list[AnalyticsAuditEvent] = []

    def accept(self, event: AnalyticsAuditEvent) -> None:
        self.events.append(event)

    def stages(self) -> list[str]:
        return [str(event.stage) for event in self.events]


class FailingAuditSink(CollectingAuditSink):
    """Accepts every stage but one, so fail-closed release can be observed."""

    def __init__(self, fail_on: str) -> None:
        super().__init__()
        self._fail_on = fail_on

    def accept(self, event: AnalyticsAuditEvent) -> None:
        if str(event.stage) == self._fail_on:
            raise RuntimeError(f"sink rejected {self._fail_on}")
        super().accept(event)


@contextmanager
def governed_policy(
    monkeypatch: pytest.MonkeyPatch, policy: QueryPolicy = FIXTURE_POLICY
) -> Iterator[QueryPolicy]:
    """Make a fixture policy resolvable for the duration of a test.

    Patches the resolver the pipeline imported. Production still reads governed
    content, which holds no approved instance — this only lets a test observe the
    steps that lie beyond the policy lock.
    """

    def _resolved(_on: date, **_kwargs: object) -> QueryPolicy:
        return policy

    monkeypatch.setattr("analytics_query.pipeline.resolve_policy", _resolved)
    yield policy


def utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)
