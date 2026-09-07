"""The refusal, over a REAL `006` outcome and never a fixture — T702.

**A fixture here would be this node agreeing with itself.** The property under test is
that *the finding `006` actually returns today refuses distribution* — and a fixture
finding is one this file chose, so asserting over it would prove that a value this file
picked produces the refusal this file expected. The warehouse is what makes the claim
about the world.

## What is real, and what stands in

**Real:** both figures, read live from the view over two governed windows; the freshness
row `005` wrote from the job history; and `006`'s own component readers, called on the
candidate those produce.

**Stood in:** `002`'s nine-step pipeline is not run. The numbers are real and the
pipeline that would normally fetch them is not exercised — the same statement `005`'s and
`006`'s integration nodes make, for the same reason: `FR-008` forbids assembling the
ledger, adapter and audit sink this feature does not own.

**And the assembly lives here because no production composer exists.** `005` may not
assemble it, `006` reads a candidate rather than building one, and the only composer in
the repository is the demonstration harness under `tools/`, which a package test must not
import. That is a real gap and it is named rather than worked around.

## Why it skips loudly rather than failing without a credential

The same rule the two features before it settled: a machine that cannot reach the
warehouse cannot answer the question, and failing there would make a fresh clone red. The
skip **names what was not measured**, so it is never mistaken for a pass.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol, cast

import pytest
from analytics_interaction.comparison.direction import Direction
from analytics_interaction.contracts.comparison import DerivedFigure
from analytics_query.contracts.comparable_window import ComparableWindow
from anomaly_investigation.contracts.candidate import (
    REQUIRED_CAUSALITY_WARNING,
    CandidateFinding,
    ClaimType,
)
from insights_prioritisation.score import read_components
from semantic_catalog.freshness.external import CompletenessStatus, FreshnessRecord

from proactive_distribution.contracts import DistributionReasonCode
from proactive_distribution.distribute import RECIPIENT_KEY, may_distribute

pytestmark = pytest.mark.integration

PROJECT = "example-project-id"
VIEW = "example-project-id.semantic.subscription_daily_metrics"
FRESHNESS = "example-project-id.semantic.source_freshness"
KPI = "New trials"
RULE_ID = "r-new-trials-percentage-change"

#: Two ten-day windows inside the source's measured coverage. Constants, because this
#: feature owns no calendar and a window derived here would be it choosing which period
#: matters.
PRIMARY = (date(2026, 8, 11), date(2026, 8, 20))
BASELINE = (date(2026, 8, 1), date(2026, 8, 10))


class _ReadRow(Protocol):
    """The one thing this file does to a result row: read its columns as a mapping."""

    def items(self) -> Iterable[tuple[str, object]]: ...


def _rows(sql: str) -> list[dict[str, object]]:
    """One read against the real warehouse, or a skip naming what was not measured."""
    try:
        from google.cloud import bigquery
    except ImportError:  # pragma: no cover - environment without the client
        pytest.skip("google-cloud-bigquery is not installed; the refusal was NOT measured")
    try:
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
    except ImportError:  # pragma: no cover - environment without the auth library
        pytest.skip("google-auth is not installed; the refusal was NOT measured")
    try:
        client = bigquery.Client(project=PROJECT)
    except DefaultCredentialsError:  # pragma: no cover - fresh clone, no credential
        pytest.skip("no Google credential is configured; the refusal was NOT measured")
    try:
        rows = cast("list[_ReadRow]", list(client.query(sql).result()))
    except RefreshError as expired:  # pragma: no cover - an expired application default
        pytest.skip(
            "the BigQuery credential is absent or expired; since OD-62 the remedy is "
            "GOOGLE_APPLICATION_CREDENTIALS pointing at the read-only service account "
            f"(docs/credencial-bigquery-service-account.md): {expired}"
        )
    return [dict(row.items()) for row in rows]


def _sum_over(start: date, end: date) -> Decimal:
    """`SUM(value)` for the bound KPI over one window, read from the real view."""
    rows = _rows(
        "SELECT SUM(CAST(value AS NUMERIC)) AS total FROM `"
        + VIEW
        + "` WHERE kpi_name = 'New trials' AND event_date BETWEEN DATE '"
        + start.isoformat()
        + "' AND DATE '"
        + end.isoformat()
        + "'"
    )
    total = rows[0]["total"] if rows else None
    if total is None:  # pragma: no cover - the window covers no row
        pytest.skip(f"the view returned no figure between {start} and {end}")
    return Decimal(str(total))


def _instant(value: object) -> datetime | None:
    """One warehouse value as an instant, refusing anything else by name."""
    if value is None:
        return None
    assert isinstance(value, datetime), f"a freshness column is {type(value).__name__}"
    return value


def _real_candidate() -> CandidateFinding:
    """A candidate over real figures, in the shape `005` emits."""
    primary = _sum_over(*PRIMARY)
    baseline = _sum_over(*BASELINE)
    assert baseline != 0, "the baseline measured zero; a percentage change has no meaning"
    movement = (primary - baseline) / baseline * Decimal(100)

    rows = _rows("SELECT * FROM `" + FRESHNESS + "` WHERE source_id = 'subscription_daily'")
    if not rows:  # pragma: no cover - the observation was withdrawn
        pytest.skip("no freshness row for subscription_daily; 005 produces no candidate")
    row = rows[0]
    observed_at = datetime.now(tz=UTC)

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
        primary_window=ComparableWindow(
            start=PRIMARY[0],
            end=PRIMARY[1],
            reason="the governed window this candidate was measured over",
            sources=("subscription_daily",),
        ),
        baseline_window=ComparableWindow(
            start=BASELINE[0],
            end=BASELINE[1],
            reason="the governed baseline window this candidate was compared against",
            sources=("subscription_daily",),
        ),
        freshness=FreshnessRecord(
            source=str(row["source_id"]),
            status=CompletenessStatus(str(row["status"])),
            observed_at=observed_at,
            ingestion_started_at=_instant(row["ingestion_started_at"]),
            ingestion_finished_at=_instant(row["ingestion_finished_at"]),
            last_successful_update=_instant(row["last_loaded_at"]),
        ),
        claim_type=ClaimType.TEMPORAL_ASSOCIATION,
        causality_warning=REQUIRED_CAUSALITY_WARNING,
    )


def test_a_real_candidate_reaches_this_feature() -> None:
    """The premise, measured. Without it every assertion below is about nothing."""
    candidate = _real_candidate()
    assert candidate.rule_id == RULE_ID
    assert candidate.figure.value != 0, "the movement measured zero; nothing moved to report"


def test_the_real_finding_is_not_prioritisable_and_distribution_refuses() -> None:
    """**`T702`, and the refusal is about the warehouse rather than about a fixture.**

    `006` is asked to read its components off the candidate the warehouse produced. Every
    one comes back with a named absence today — magnitude needs a mean per metric, which
    is a figure and must arrive through the `002`/`003` seams; reach is read from an
    investigation `005` does not yet produce.

    **The day either becomes obtainable this node goes red**, and that is its function:
    the feature learns its premise changed from a failing assertion rather than from
    somebody remembering to look.
    """
    components = read_components(_real_candidate())
    assert components, "006 returned no component at all, so nothing here was measured"

    absences = [c for c in components if c.absence is not None]
    assert len(absences) == len(components), (
        "a component became obtainable, which is the GOOD outcome and means this node must "
        f"be re-derived to assert distribution rather than its refusal: {absences}"
    )

    prioritisable = not absences
    permission = may_distribute(
        finding_is_prioritisable=prioritisable,
        environment={RECIPIENT_KEY: "an-id-this-node-never-reads"},
    )
    assert not permission.permitted
    assert permission.refused_for is DistributionReasonCode.DISTRIBUTION_FINDING_NOT_PRIORITISABLE


def test_the_refusal_names_the_warehouse_and_not_the_missing_labels() -> None:
    """**Two absences, and today the first one is what stops it.**

    His five labels exist since 2026-08-27, so *no approved way to say it* is no longer the
    blocker. What stops distribution is that nothing is worth saying — and the code says
    exactly that, which is the whole reason the two were never allowed to merge.
    """
    components = read_components(_real_candidate())
    permission = may_distribute(
        finding_is_prioritisable=not any(c.absence is not None for c in components),
        environment={RECIPIENT_KEY: "an-id-this-node-never-reads"},
    )
    assert permission.refused_for is not DistributionReasonCode.DISTRIBUTION_LABELS_NOT_APPROVED
    assert permission.refused_for is DistributionReasonCode.DISTRIBUTION_FINDING_NOT_PRIORITISABLE
