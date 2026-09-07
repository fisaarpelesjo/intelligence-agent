"""Counting the entry-point calls — Phase 9 test support.

`FR-031` is a **count**, not an inspection: exactly one governed execution per
side, none speculative. Proving that against a hand-written fake port would prove
something about the fake. So these tests count the calls
``GovernedExecutionPort.submit`` makes to `002`'s real entry point, by replacing
``execute_analytics_query`` in the port's own module namespace.

That placement is deliberate. Patching the name where the port *looks it up*
means the port's real code runs — its fingerprint check, its argument
construction, its single call site — and only the crossing of the boundary is
observed. A fake port would have let the port itself be wrong.

The recorder returns a sentinel rather than a constructed ``ExecutedAnswer``.
Phase 9 asserts *how many times* and *with what* the boundary was crossed;
building a full governed answer would require a result, a decision and a complete
ten-element provenance, none of which any assertion here reads, and a fixture
answer that looked real enough to assert against would be the more dangerous
object to have lying around.

TEST-ONLY. Reaches no warehouse, no adapter and no ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

import pytest
from analytics_query.contracts.request import AnalyticsQuery
from semantic_catalog.contracts.metric import MetricVersion
from semantic_catalog.freshness.external import FreshnessSnapshot
from semantic_catalog.loader.bundle import Bundle

from analytics_interaction.execution import port as port_module
from analytics_interaction.execution.port import ExecutionEnvironment, GovernedExecutionPort

__all__ = ["Submission", "SubmissionRecorder", "bound_environment", "recorded_port"]

#: A value that is present, non-``None`` and does nothing. Standing in for a
#: collaborator the recorder guarantees is never reached.
_INERT = object()

_SENTINEL = object()


@dataclass
class Submission:
    """One crossing of the ADR 0010 boundary, as it was made."""

    request: AnalyticsQuery
    correlation_id: str
    principal_ref: str


@dataclass
class SubmissionRecorder:
    """Every entry-point call, in order.

    A list rather than a counter: "one call per side" and "one call, twice" are
    different claims, and only the recorded requests distinguish them.
    """

    calls: list[Submission] = field(default_factory=list[Submission])

    def __call__(self, request: AnalyticsQuery, **kwargs: Any) -> object:
        self.calls.append(
            Submission(
                request=request,
                correlation_id=str(kwargs["correlation_id"]),
                principal_ref=str(kwargs["principal_ref"]),
            )
        )
        return _SENTINEL

    @property
    def count(self) -> int:
        return len(self.calls)

    def date_ranges(self) -> list[tuple[date, date]]:
        return [(c.request.date_range.start, c.request.date_range.end) for c in self.calls]


def recorded_port(
    monkeypatch: pytest.MonkeyPatch, *, on: date
) -> tuple[GovernedExecutionPort, SubmissionRecorder]:
    """A real port whose one boundary crossing is recorded.

    Every collaborator is a placeholder: the recorder replaces the entry point,
    so nothing downstream of it is ever consulted. Supplying working stand-ins
    would suggest the test exercises `002`'s ordering, which it does not and must
    not — that ordering is `002`'s own suite's claim, and duplicating it here
    would create a second place where it could be asserted differently.

    The three precisely-typed collaborators are cast placeholders for the same
    reason: constructing a real bundle, snapshot and metric version would tie
    every Phase 9 submission test to `001`'s fixture catalog for no assertion's
    benefit.
    """
    recorder = SubmissionRecorder()
    monkeypatch.setattr(port_module, "execute_analytics_query", recorder)
    return GovernedExecutionPort(bound_environment(on=on)), recorder


def bound_environment(*, on: date) -> ExecutionEnvironment:
    """A complete binding whose collaborators are never consulted.

    Every required name is present and non-``None``, because the environment
    refuses an incomplete binding at construction — which is itself the property
    ``test_execution_port_boundary`` asserts. The values are inert placeholders:
    once the entry point is replaced by the recorder, nothing downstream of it
    runs, and constructing a real bundle, snapshot and metric version would tie
    every submission test to `001`'s fixture catalog for no assertion's benefit.
    """
    return ExecutionEnvironment(
        evaluate=_INERT,
        ledger=_INERT,
        observations=_INERT,
        adapter=_INERT,
        sink=_INERT,
        context=_INERT,
        sample_catalog=lambda: _INERT,
        catalog_bundle=cast("Bundle", _INERT),
        on=on,
        catalog_release_id="r-1",
        required_sources=frozenset({"appstore"}),
        columns=(),
        metric_version_ids=("mv-1",),
        freshness_snapshot=cast("FreshnessSnapshot", _INERT),
        metric_version=cast("MetricVersion", _INERT),
    )
