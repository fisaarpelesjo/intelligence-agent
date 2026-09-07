"""One ordering over a candidate `005` actually produced — T023.

**This file could not be written until 2026-08-27, and the ledger said so instead of
pretending otherwise.** `005` produced no candidate: its metric was unpublishable, then
its coverage was unobserved, then its freshness was unobserved. Writing this against a
fixture would have made it *a unit test wearing an integration test's name* — the defect
`005` refused when it kept its own `T023` asserting the refusal rather than faking the
outcome.

`005` closed `SC-001` on 2026-08-27: a `CandidateFinding` is produced end to end against
the real warehouse. So this file exists now, and it starts where that one ends.

## What is real here, and what is stood in for

**Real:** the figures, read from the view over two governed windows; the movement,
derived through the `002` and `003` seams; the window, from `001`'s own decision; the
freshness record, carrying a load time measured from the job history.

**Stood in for:** `002`'s nine-step pipeline, exactly as in `005:T023` and for the same
reason — `FR-008` forbids assembling the ledger, adapter and audit sink this feature does
not own.

## The outcome today is a REFUSAL, and it is the honest one

The candidate arrives and **cannot be placed**, because both declared components are
unobtainable:

* `magnitude` is a z-score, and a mean per metric is a FIGURE — by `005`'s `FR-003` it
  must arrive through the `002` and `003` seams, and nothing carries one yet;
* `reach` is read from an investigation, and `005` produced none for this candidate.

So the run **completes** with the finding reported as **not prioritisable**, each
component naming its own absence. That is `FR-009` working: *"nothing could be ordered"*
and *"the prioritiser broke"* must never look the same, and this asserts the first.

**The day either component becomes obtainable, this file goes red** — the assertions
below name the absence rather than tolerate it, so the arrival of a real component is a
failure that has to be re-derived rather than a silent change of behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

import pytest
from analytics_interaction.comparison.direction import Direction
from analytics_interaction.contracts.comparison import DerivedFigure
from analytics_query.contracts.comparable_window import ComparableWindow
from anomaly_investigation.contracts import AggregationClass
from anomaly_investigation.contracts.candidate import (
    REQUIRED_CAUSALITY_WARNING,
    CandidateFinding,
    ClaimType,
)
from semantic_catalog.freshness.external import CompletenessStatus, FreshnessRecord

from insights_prioritisation.contracts import (
    NotPrioritisable,
    PrioritisationRun,
    PriorityReasonCode,
    RunOutcome,
)
from insights_prioritisation.order import one_ordering_per_class
from insights_prioritisation.score import read_components

pytestmark = pytest.mark.integration

#: `tests/integration/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]

PROJECT = "example-project-id"
VIEW = "example-project-id.semantic.subscription_daily_metrics"
FRESHNESS = "example-project-id.semantic.source_freshness"
KPI = "New trials"
RULE_ID = "r-new-trials-percentage-change"

PRIMARY = (date(2026, 8, 11), date(2026, 8, 20))
BASELINE = (date(2026, 8, 1), date(2026, 8, 10))


class _ReadRow(Protocol):
    """The one thing this file does to a result row: read its columns as a mapping."""

    def items(self) -> Iterable[tuple[str, object]]: ...


def _query(sql: str) -> list[dict[str, object]]:
    """One read against the real warehouse, or a loud skip naming what was not measured."""
    try:
        from google.cloud import bigquery
    except ImportError:  # pragma: no cover - environment without the client
        pytest.skip("google-cloud-bigquery is not installed; nothing was measured")
    try:
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
    except ImportError:  # pragma: no cover - environment without the auth library
        pytest.skip("google-auth is not installed; nothing was measured")
    # The credential is probed by building the client this function uses. A separate probe can
    # succeed while the real client fails, which turns a failure into a skip.
    try:
        client = bigquery.Client(project=PROJECT)
    except DefaultCredentialsError:  # pragma: no cover - fresh clone, no credential
        pytest.skip("no Google credential is configured; nothing was measured")
    try:
        # The row arrives untyped -- the client ships no type information -- so the one thing
        # this file does with it is declared rather than inferred: it produces its items.
        rows = cast("list[_ReadRow]", list(client.query(sql).result()))
        return [dict(row.items()) for row in rows]
    except RefreshError as expired:  # pragma: no cover - an expired application default
        pytest.skip(
            "the BigQuery credential is absent or expired; since OD-62 the remedy is "
            "GOOGLE_APPLICATION_CREDENTIALS pointing at the read-only service account "
            f"(docs/credencial-bigquery-service-account.md): {expired}"
        )


def _sum_over(start: date, end: date) -> Decimal:
    rows = _query(
        "SELECT SUM(CAST(value AS NUMERIC)) AS total FROM `"
        + VIEW
        + f"` WHERE kpi_name = '{KPI}' AND event_date BETWEEN '{start}' AND '{end}'"
    )
    total = rows[0]["total"]
    assert total is not None, "the window returned no rows; the bound KPI was not measured"
    return Decimal(total)  # type: ignore[arg-type]


def _candidate() -> CandidateFinding:
    """A candidate over real figures, in the shape `005` emits.

    The movement is computed here as `005`'s own integration node computes it — from two
    sums read live — and carried into `DerivedFigure` with the basis stated. Nothing is
    invented: the direction is read off the sign of the measured movement, and the
    freshness record is the row `005` wrote from the job history.
    """
    primary = _sum_over(*PRIMARY)
    baseline = _sum_over(*BASELINE)
    assert baseline != 0, "the baseline measured zero; a percentage change has no meaning"
    movement = (primary - baseline) / baseline * Decimal(100)

    rows = _query("SELECT * FROM `" + FRESHNESS + "` WHERE source_id = 'subscription_daily'")
    if not rows:  # pragma: no cover - the observation was withdrawn
        pytest.skip("no freshness row for subscription_daily; 005 could not produce a candidate")
    row = rows[0]
    observed_at = datetime.now(tz=UTC)

    window = ComparableWindow(
        start=PRIMARY[0],
        end=PRIMARY[1],
        reason="the governed window this candidate was measured over",
        sources=("subscription_daily",),
    )
    return CandidateFinding(
        rule_id=RULE_ID,
        figure=DerivedFigure(
            value=movement,
            unit="%",
            derived_from=("new_trials", "new_trials"),
            basis="the governed window this rule was evaluated over",
        ),
        baseline_value=baseline,
        direction=(
            Direction.DECREASE
            if movement < 0
            else Direction.INCREASE
            if movement > 0
            else Direction.STABLE
        ),
        primary_window=window,
        baseline_window=ComparableWindow(
            start=BASELINE[0],
            end=BASELINE[1],
            reason="the governed baseline window this candidate was compared against",
            sources=("subscription_daily",),
        ),
        freshness=FreshnessRecord(
            source=row["source_id"],  # type: ignore[arg-type]
            status=CompletenessStatus(row["status"]),
            observed_at=observed_at,
            ingestion_started_at=row["ingestion_started_at"],  # type: ignore[arg-type]
            ingestion_finished_at=row["ingestion_finished_at"],  # type: ignore[arg-type]
            last_successful_update=row["last_loaded_at"],  # type: ignore[arg-type]
        ),
        claim_type=ClaimType.TEMPORAL_ASSOCIATION,
        causality_warning=REQUIRED_CAUSALITY_WARNING,
    )


def test_a_real_candidate_reaches_this_feature() -> None:
    """The premise, measured. Without it every assertion below is about nothing."""
    candidate = _candidate()
    assert candidate.rule_id == RULE_ID
    assert candidate.figure.value is not None
    assert candidate.freshness.last_successful_update is not None, (
        "the candidate carries no measured load time, so its freshness is a claim nobody observed"
    )


def test_both_declared_components_are_absent_and_each_names_itself() -> None:
    """**The outcome today, and the absences are named rather than tolerated.**

    `magnitude` needs a mean per metric, which is a FIGURE and must arrive through the
    governed seams; `reach` needs an investigation, and `005` produced none. Neither is
    guessed, and neither is zeroed.
    """
    components = read_components(_candidate())
    assert [component.name for component in components] == ["magnitude", "reach"]
    for component in components:
        assert component.value is None, (
            f"{component.name} produced a value: a component became obtainable, which is "
            "the good outcome and means this file must be re-derived to assert the ordering"
        )
        assert component.absence is not None
        assert component.absence.reason is PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE


def test_the_run_completes_with_the_candidate_reported_not_prioritisable() -> None:
    """**`FR-009`, end to end over a real candidate.**

    *"Nothing could be ordered"* and *"the prioritiser broke"* must never look the same.
    The run **completes**, the ordering is empty, and the finding is carried as not
    prioritisable with both absences visible — which is a result a reader can act on.
    """
    candidate = _candidate()
    unplaced = NotPrioritisable(
        finding_id=RULE_ID.replace("-", "_"),
        components=read_components(candidate),
        reading_instant=datetime.now(tz=UTC),
        caveats=(candidate.causality_warning,),
    )

    orderings = one_ordering_per_class(
        {AggregationClass.COUNT: []},
        not_prioritisable=[unplaced],
    )
    run = PrioritisationRun(
        outcome=RunOutcome.COMPLETED,
        orderings=orderings,
        read_at=datetime.now(tz=UTC),
    )

    assert run.outcome is RunOutcome.COMPLETED
    assert run.reason_code is None, "a completed run carries no reason code"
    assert run.produced_nothing, (
        "the ordering is not empty, so this node is measuring something else"
    )

    carried = [f.finding_id for o in run.orderings for f in o.not_prioritisable]
    assert carried == [RULE_ID.replace("-", "_")], (
        "the candidate was dropped instead of being reported as not prioritisable"
    )
    reported = [
        component.absence.reason
        for ordering in run.orderings
        for finding in ordering.not_prioritisable
        for component in finding.components
        if component.absence
    ]
    assert len(reported) == 2, f"both absences must be visible in the output: {reported}"


def test_the_caveat_from_the_candidate_travels_into_the_output() -> None:
    """`FR-011` over a real candidate: the causality warning is `005`'s, not ours.

    It is compared byte for byte against the constant `005` requires on every candidate,
    so this feature can neither paraphrase it nor drop it on the way through.
    """
    candidate = _candidate()
    unplaced = NotPrioritisable(
        finding_id=RULE_ID.replace("-", "_"),
        components=read_components(candidate),
        reading_instant=datetime.now(tz=UTC),
        caveats=(candidate.causality_warning,),
    )
    orderings = one_ordering_per_class({AggregationClass.COUNT: []}, not_prioritisable=[unplaced])
    carried = [c for o in orderings for f in o.not_prioritisable for c in f.caveats]
    assert carried == [REQUIRED_CAUSALITY_WARNING]
