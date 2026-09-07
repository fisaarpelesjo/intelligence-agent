"""One rule, one bound KPI, end to end against the real things — T023 (`SC-001`).

**READ THIS BEFORE READING THE ASSERTIONS, BECAUSE THE HEADLINE IS STILL A GAP —
AND IT IS A DIFFERENT GAP THAN IT WAS THIS MORNING.**

`SC-001` asks that one governed rule over one bound KPI **produce a candidate**
against the real warehouse. On 2026-08-26 the owner authorized both signatures this
file had named as the blockers — *"Autorizar as duas (Recomendado)"*, recorded in the
governed channel at 17:17:40Z. **Both landed, both worked, and a candidate is still
not produced.** Measured:

* the D-1 freshness approval of `subscription_daily` **took effect UNDER THE COMMIT IT
  NAMES** — there, it is the only publishable source in the catalog. **Under anything a
  real caller passes it is INERT**: `COMMIT_MISMATCH`, no publishable source at all. That
  is `F-F`, it is asserted in
  `test_the_approval_is_inert_where_it_is_evaluated.py`, and no sentence about this
  approval may be written here without naming the commit it was measured against;
* the D-18 `percentage_change` formula **took effect** — the movement derives, over
  two figures read live from the view;
* `new_trials` is **still `PENDING`**, reason `SOURCE_NOT_APPROVED`, and
  `unapproved_sources` is **empty**.

## The empty tuple is the finding

`publication.metric_eligibility` computes ``publishable = bool(declared) and not
unapproved`` over the `source_availability` entries whose status is AVAILABLE.
`new_trials` declares **none** — the block was removed in cycle 345, because `L3`
refused it with `declared_without_coverage`. So the metric is unpublishable for
having nothing declared rather than for depending on something unapproved, and the
function says so itself: *"Declaring no available source is not a way around this: a
metric with nothing to answer from is unpublishable too."*

## What would be needed, and why this feature stops here

Three things, each measured rather than guessed, and the first two are forbidden by
the cycle's scope while the third does not exist:

1. `new_trials` must declare `source_availability` with status **AVAILABLE** on
   `subscription_daily`. Explicitly forbidden;
2. that declaration needs an **observed coverage** row for the pair, or `L3` refuses
   it exactly as it did in cycle 345;
3. the honest source of that row is `semantic.metric_availability`. **It does not
   exist** — measured, the `semantic` dataset holds one object, the view — and
   creating a warehouse object is forbidden, the view being the owner's.

**And a fixture cannot stand in**, by deliberate design rather than by oversight:
`load_observed_coverage` forces ``is_fixture=True`` regardless of what the file
claims, precisely so a fixture cannot present itself as a production observation.

So this file asserts the refusal, and goes red the day it ends. That is the same
thing it did before the signatures — it is how the two arriving was noticed at all.

## What it proves end to end, against real things rather than fixtures

1. the warehouse holds the bound KPI, read live over two real windows;
2. the freshness approval took effect on the real catalog **under the commit it names**,
   and is inert under every other — see `F-F`;
3. the movement derives through the `002`/`003` seams over those real numbers;
4. the governed path still refuses, and the refusal carries the catalog's own word;
5. the two real figures reach `003`'s arithmetic and stay exact.

**What is stood in for, said plainly:** `002`'s nine-step pipeline is not run.
Building it needs a ledger, an adapter, an audit sink and an authorization context
this feature does not own, and `FR-008` forbids reaching around the seam to assemble
them. What crosses the seam is an executor carrying **numbers read from the real
warehouse** into the shapes `002` produces. The numbers are real; the pipeline that
would normally fetch them is not exercised.

## Why it fails rather than skips when the query is refused

The same lesson as `test_the_class_is_read_from_the_view`: a node that skips when the
world breaks guards nothing. Missing credential skips loudly; a refused query FAILS
with the warehouse's own message.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest
from analytics_interaction.comparison.compute import derive_figure, to_exact
from analytics_interaction.comparison.direction import Direction
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.contracts.result import (
    AnalyticsResult,
    Completeness,
    ResultCell,
    ResultColumn,
    ResultRow,
)
from analytics_query.contracts.result_provenance import (
    CostProvenance,
    ResultProvenance,
    SourceUpdate,
)
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.loader.bundle import build_bundle, load_catalog
from semantic_catalog.validation.pipeline import evaluate
from semantic_catalog.validation.publication import publishable_source_ids

from anomaly_investigation.contracts import (
    AggregationClass,
    AnomalyReasonCode,
    DetectionMethod,
    Rule,
)
from anomaly_investigation.detect.threshold import ThresholdVerdict, assess_threshold
from anomaly_investigation.ports import resolve_metric
from anomaly_investigation.ports.figures_port import MovementResolution, resolve_movement

if TYPE_CHECKING:  # pragma: no cover - imported for the type only
    from analytics_query.execute import ExecutedAnswer

pytestmark = pytest.mark.integration

#: `tests/integration/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
ON = date(2026, 8, 26)

PROJECT = "example-project-id"
VIEW = "example-project-id.semantic.subscription_daily_metrics"
KPI = "New trials"
METRIC = "new_trials"
RULE_ID = "r-new-trials-percentage-change"

#: Two real windows, ten days each, inside the source's measured coverage.
PRIMARY_RANGE = DateRange(start=date(2026, 8, 11), end=date(2026, 8, 20))
BASELINE_RANGE = DateRange(start=date(2026, 8, 1), end=date(2026, 8, 10))

#: What `D-18` calls the movement a percentage-change rule asks for. Named rather
#: than typed twice, because it reaches both the formula resolution and the
#: assertion about which formula was resolved.
FORMULA = "percentage_change"

#: Carried into `DerivedFigure.basis`. A constant here rather than a composed
#: sentence: `005`'s own security node refuses a value interpolated into prose,
#: and this test must not be the first thing to do it.
BASIS = "the governed window this rule was evaluated over"


#: The commit the 2026-08-26 freshness approval names. Read from the approval itself
#: rather than typed here, because a commit id written into a test is the `F136`
#: defect: it ages the moment the approval is renewed against newer content.
#:
#: **And it neutralises one of the six checks `evaluate` makes, which is said out loud
#: rather than hidden.** `FreshnessApprovals.evaluate` refuses on
#: `approval.source_commit != current_commit`; feeding it the approval's own commit
#: makes that comparison trivially true. There is no alternative that is not worse: the
#: approval binds to the content it approved, so any OTHER commit refuses by design, and
#: pinning a literal would age. What still runs are the five checks that matter here —
#: not rejected, not expired, role permitted, and the four candidate values still
#: matching the source.
def _approved_commit() -> str:
    catalog = load_catalog(REPO / "semantic")
    approvals = catalog.freshness_approvals
    assert approvals is not None and approvals.approvals, "no freshness approval is authored"
    return approvals.approvals[0].source_commit


def _bundle():
    return build_bundle(REPO / "semantic", current_commit=_approved_commit(), on=ON)


def _sum_over(start: date, end: date) -> Decimal:
    """`SUM(value)` for the bound KPI over one window, read from the real view.

    Skips only when the machine cannot reach any warehouse. A query that is
    REFUSED fails, carrying the warehouse's message — see the module docstring.
    """
    try:
        from google.cloud import bigquery
    except ImportError:  # pragma: no cover - environment without the client
        pytest.skip("google-cloud-bigquery is not installed; nothing was measured")
    try:
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
    except ImportError:  # pragma: no cover - environment without the auth library
        pytest.skip("google-auth is not installed; nothing was measured")
    # The credential is probed BY BUILDING THE CLIENT THIS FUNCTION USES, rather than by a
    # separate `google.auth.default()` call beside it. A separate probe can succeed while the
    # client the code goes on to build fails, which would turn a real failure into a skip --
    # and its return value was never read, so it was a call kept only for its exception.
    try:
        client = bigquery.Client(project=PROJECT)
    except DefaultCredentialsError:  # pragma: no cover - fresh clone, no credential
        pytest.skip("no Google credential is configured; nothing was measured")
    try:
        job = client.query(
            f"SELECT SUM(CAST(value AS NUMERIC)) AS total FROM `{VIEW}` "
            "WHERE kpi_name = @kpi AND event_date BETWEEN @start AND @end",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("kpi", "STRING", KPI),
                    bigquery.ScalarQueryParameter("start", "DATE", start.isoformat()),
                    bigquery.ScalarQueryParameter("end", "DATE", end.isoformat()),
                ]
            ),
        )
        rows = job.result()
    except RefreshError as expired:  # pragma: no cover - an expired application default
        # **An EXPIRED credential is an ABSENT credential, and it is not a refused
        # query.** `google.auth.default()` above succeeds while the stored
        # application-default token can no longer be refreshed, and the failure only
        # surfaces here, at the first call that needs it. Reporting that as a red node
        # would say the warehouse refused an answer, which it did not: nobody asked it.
        #
        # The refusal path is untouched -- a query the warehouse REFUSES still fails,
        # carrying its own message, which is the lesson in the module docstring.
        pytest.skip(
            "the BigQuery credential is absent or expired; since OD-62 the remedy is "
            "GOOGLE_APPLICATION_CREDENTIALS pointing at the read-only service account "
            f"(docs/credencial-bigquery-service-account.md): {expired}"
        )
    total = next(iter(rows))["total"]
    assert total is not None, "the window returned no rows; the bound KPI was not measured"
    return Decimal(total)


class _ReadRow(Protocol):
    """The one thing this file does to a result row: read its columns as a mapping.

    Declared here rather than imported, because `google.cloud.bigquery` ships no type
    information -- so a row arrives untyped and everything taken out of it is untyped too.
    Naming the shape keeps the claim minimal: this file asserts a row can produce its items,
    and asserts nothing about the rest of the library's surface.
    """

    def items(self) -> Iterable[tuple[str, object]]: ...


def _query(sql: str) -> list[dict[str, object]]:
    """One read against the real warehouse, with the same skips as `_sum_over`.

    Separate from `_sum_over` because that one is about the bound KPI and this one is
    about the OBSERVATION tables. Sharing a helper would blur which of the two a skip
    was about.
    """
    try:
        from google.cloud import bigquery
    except ImportError:  # pragma: no cover - environment without the client
        pytest.skip("google-cloud-bigquery is not installed; nothing was measured")
    try:
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
    except ImportError:  # pragma: no cover - environment without the auth library
        pytest.skip("google-auth is not installed; nothing was measured")
    # The credential is probed BY BUILDING THE CLIENT THIS FUNCTION USES, rather than by a
    # separate `google.auth.default()` call beside it. A separate probe can succeed while the
    # client the code goes on to build fails, which would turn a real failure into a skip --
    # and its return value was never read, so it was a call kept only for its exception.
    try:
        client = bigquery.Client(project=PROJECT)
    except DefaultCredentialsError:  # pragma: no cover - fresh clone, no credential
        pytest.skip("no Google credential is configured; nothing was measured")
    try:
        rows = cast("list[_ReadRow]", list(client.query(sql).result()))
        return [dict(row.items()) for row in rows]
    except RefreshError as expired:  # pragma: no cover - an expired application default
        pytest.skip(
            "the BigQuery credential is absent or expired; since OD-62 the remedy is "
            "GOOGLE_APPLICATION_CREDENTIALS pointing at the read-only service account "
            f"(docs/credencial-bigquery-service-account.md): {expired}"
        )


def _answer(value: Decimal, window: DateRange) -> ExecutedAnswer:
    """One figure in the shapes `002` produces, carrying a real measured number.

    A local class rather than a shared double: this file is the only place that
    stands in for the pipeline, and a reusable double would invite a second
    caller to believe `002` ran.
    """

    class _Executed:
        result = AnalyticsResult(
            columns=(ResultColumn(identifier=METRIC, unit="users", is_metric=True),),
            rows=(ResultRow(labels=(), cells=(ResultCell(value=value),)),),
            completeness=Completeness.COMPLETE,
        )
        provenance = ResultProvenance(
            contributing_sources=("subscription_daily",),
            resolved_metric_versions=("new_trials@1",),
            data_revisions=(),
            data_as_of=datetime(2026, 8, 26, 6, 0, tzinfo=UTC),
            source_updates=(
                SourceUpdate(
                    source_id="subscription_daily",
                    last_updated_at=datetime(2026, 8, 26, 6, 0, tzinfo=UTC),
                ),
            ),
            dimensional_coverage=(),
            limitations=(
                "the figure was read from the warehouse by this node; "
                "002's execution pipeline was not run",
            ),
            cost=CostProvenance(dry_run_bytes=1, actual_bytes=1, maximum_bytes_billed=2),
            execution_identifiers=(window.start.isoformat(),),
            policy_version="not-run",
            catalog_release_id="not-run",
        )
        decision = None
        disposition = None

    # Cast rather than subclass: `ExecutedAnswer` is a shape `002` produces, and inheriting
    # from it here would be this file claiming to BE `002` rather than to stand in for it. The
    # four attributes the port reads are declared above; nothing else is claimed.
    return cast("ExecutedAnswer", _Executed())


def test_the_production_catalog_and_the_warehouse_are_both_reachable() -> None:
    """**Read this before believing anything below.**

    A refusal measured over an empty catalog, or a movement derived over a window
    with no rows, would prove nothing. Both instruments are checked first, and
    both are checked against what they are supposed to contain rather than
    against a number written here.
    """
    bundle = _bundle()
    assert bundle.pending or bundle.published, "the catalog bundle is empty"

    primary = _sum_over(PRIMARY_RANGE.start, PRIMARY_RANGE.end)
    baseline = _sum_over(BASELINE_RANGE.start, BASELINE_RANGE.end)
    assert primary > 0, "the primary window measured nothing"
    assert baseline > 0, "the baseline window measured nothing"


def test_the_governed_path_refuses_and_carries_the_catalogs_own_word() -> None:
    """`SC-001`'s candidate is not reachable, and this is the measurement of WHY TODAY.

    **The blocker moved on 2026-08-27 and this node moved with it.** It asserted
    `METRIC_PENDING` while `new_trials` declared no available source. The coverage
    observation now exists in `semantic.metric_availability`, the declaration was
    written, and the metric is **published** — so the catalog no longer refuses over
    publication.

    What refuses now is gate 8: **no freshness snapshot was supplied**, and an
    unobserved source state is `SOURCE_STATE_UNKNOWN` rather than healthy. The honest
    source of that snapshot is `semantic.source_freshness`, and **it does not exist** —
    which is a measurement of what the next step needs, not a guess about it.

    Both principal types, against the production catalog. The carried upstream code is
    what keeps our own reason code from asserting more than it measured.
    """
    bundle = _bundle()
    for principal in PrincipalType:
        resolution = resolve_metric(
            RULE_ID,
            METRIC,
            evaluate=evaluate,
            bundle=bundle,
            start=PRIMARY_RANGE.start,
            end=PRIMARY_RANGE.end,
            baseline_start=BASELINE_RANGE.start,
            baseline_end=BASELINE_RANGE.end,
            comparison_kind="previous_period",
            principal_type=principal,
            authorization_scope="default",
            requester_access=("standard",),
            on=ON,
        )
        assert not resolution.permitted, (
            f"{principal.value}: the catalog permitted the metric, so the freshness "
            "observation arrived and this node is the one that has to be re-derived"
        )
        assert resolution.reason_code is AnomalyReasonCode.ANOMALY_RULE_METRIC_NOT_BOUND
        assert resolution.upstream_code == "SOURCE_STATE_UNKNOWN", resolution.upstream_code
        assert resolution.is_traceable, "the refusal carries no decision id"

    assert bundle.lifecycles[METRIC].is_published, (
        "the metric is no longer published, so the refusal above is about publication "
        "again and this node is measuring something other than what it says"
    )


def _movement() -> MovementResolution:
    """The movement over the two real windows, through the `002`/`003` seams."""
    primary = _sum_over(PRIMARY_RANGE.start, PRIMARY_RANGE.end)
    baseline = _sum_over(BASELINE_RANGE.start, BASELINE_RANGE.end)
    answers = {
        PRIMARY_RANGE.start: _answer(primary, PRIMARY_RANGE),
        BASELINE_RANGE.start: _answer(baseline, BASELINE_RANGE),
    }

    def execute(request: AnalyticsQuery):
        return answers[request.date_range.start]

    return resolve_movement(
        RULE_ID,
        formula_id=FORMULA,
        primary_request=AnalyticsQuery(metrics=(METRIC,), date_range=PRIMARY_RANGE),
        baseline_request=AnalyticsQuery(metrics=(METRIC,), date_range=BASELINE_RANGE),
        execute=execute,
        basis=BASIS,
        on=ON,
    )


def test_the_movement_now_derives_because_the_formula_was_authored() -> None:
    """**This node asserted the opposite until 2026-08-26, and the flip is the point.**

    It used to assert that the movement REFUSED, because `D-18` held no formula at
    all. The owner authored `percentage_change` — *"Autorizar as duas
    (Recomendado)"*, 17:17:40Z — and the node went red, which is exactly what a
    node that asserts an absence is supposed to do when the absence ends.

    Re-derived to assert what is now true: the movement derives, over two figures
    read live from the view, through the `002`/`003` seams. One of the two things
    standing between `005` and a candidate is gone.
    """
    resolution = _movement()
    if not resolution.derived:
        pytest.fail(
            f"the movement did not derive: {resolution.reason_code} / {resolution.upstream_code}"
        )
    assert resolution.movement is not None
    assert isinstance(resolution.movement.value, Decimal), "the figure is not an exact decimal"
    assert resolution.movement.unit == "percent", resolution.movement.unit
    assert resolution.provenance_is_separate, "the two sides' provenance was merged (FR-033)"
    assert resolution.movement.derived_from == ("primary", "baseline")
    assert resolution.movement.basis == BASIS, "the basis was composed rather than carried"


def test_the_two_real_figures_reach_the_arithmetic_and_stay_exact() -> None:
    """What DOES work end to end over real data, asserted without pretending it is `SC-001`.

    The port cannot derive, because the governed formula is missing. So this node
    asks `003`'s arithmetic **directly**, over the two figures read live from the
    view, and asserts they arrive exact.

    **This deliberately bypasses the governed formula resolution**, and saying so
    is the whole reason the sentence is here: it proves the numbers and the
    exact-decimal path, and it proves NOTHING about governance. A reader must not
    take it for the end-to-end run `SC-001` asks for.
    """
    primary = _sum_over(PRIMARY_RANGE.start, PRIMARY_RANGE.end)
    baseline = _sum_over(BASELINE_RANGE.start, BASELINE_RANGE.end)
    assert isinstance(to_exact(primary), Decimal)
    assert isinstance(to_exact(baseline), Decimal)

    figure = derive_figure(
        formula_id=FORMULA,
        unit="percent",
        primary=primary,
        baseline=baseline,
        derived_from=("primary", "baseline"),
        basis=BASIS,
    )
    assert isinstance(figure.value, Decimal), "the movement is not an exact decimal"

    # The threshold is the owner's 10 per cent, given on 2026-08-25. It lives HERE
    # and not in a governed file, deliberately: no `Rule` instance is governed
    # content today, and authoring one is his decision. The ledger's "no new
    # governed content" is what makes this an instance in a test.
    rule = Rule(
        rule_id=RULE_ID,
        metric=METRIC,
        method=DetectionMethod("percentage_change"),
        aggregation_class=AggregationClass.COUNT,
        formula_id=FORMULA,
        threshold=Decimal("10"),
        tolerance=Decimal("0.01"),
        period="august_2026_second_ten_days",
        baseline_period="august_2026_first_ten_days",
    )
    outcome = assess_threshold(rule, observed=figure.value, observed_class=rule.aggregation_class)
    assert outcome.verdict is not ThresholdVerdict.REFUSED, (
        f"the comparison could not run: {outcome.reason_code}"
    )


def test_no_candidate_is_emitted_and_the_reason_is_no_longer_publication() -> None:
    """**The publication blocker is GONE, and `SC-001` is still one observation short.**

    Measured on 2026-08-27: `semantic.metric_availability` exists and carries the row
    for this pair with the dates computed inside the INSERT; `new_trials` declares
    `subscription_daily` available from the observed `min_date`; the approval's
    `source_commit` was re-measured after the history rewrite; and the metric's
    lifecycle is **published**, with no missing field and no unapproved source.

    What remains is **gate 8**, and it is a different kind of gap: the resolution hands
    the pipeline no freshness snapshot, so the source's state is unobserved — which the
    catalog calls `SOURCE_STATE_UNKNOWN` rather than healthy. The honest source of that
    snapshot is `semantic.source_freshness`, which does not exist. Creating it needs a
    measured load time for the source, and the credential for measuring it expired
    mid-cycle.

    Everything below the headline is the old text, kept because it is the record of how
    the previous blocker was found.

    ---

    **The two signatures arrived, and `SC-001` was still not reachable. This is why.**

    Measured on 2026-08-26 after both were authored:

    * the freshness approval WORKED — `subscription_daily` is the only publishable
      source in the catalog, at the commit its approval names;
    * the formula WORKED — the movement derives, asserted above;
    * and `new_trials` is **still** `PENDING`, with reason `SOURCE_NOT_APPROVED` and
      an **empty** `unapproved_sources` tuple.

    The empty tuple is the whole finding. `publication.metric_eligibility` computes
    ``publishable = bool(declared) and not unapproved`` over the entries of
    `source_availability` whose status is AVAILABLE — and `new_trials` declares
    **none**, because that block was removed in cycle 345 when `L3` refused it with
    `declared_without_coverage`. The function's own docstring says it outright:
    *"Declaring no available source is not a way around this: a metric with nothing
    to answer from is unpublishable too."*

    **So leaving PENDING needs more than the two signatures**, and what it needs is
    forbidden to this feature — see the module docstring. This node asserts the
    refusal so it goes red the day that changes, exactly as its predecessor did.
    """
    bundle = _bundle()
    permitted = resolve_metric(
        RULE_ID,
        METRIC,
        evaluate=evaluate,
        bundle=bundle,
        start=PRIMARY_RANGE.start,
        end=PRIMARY_RANGE.end,
        baseline_start=BASELINE_RANGE.start,
        baseline_end=BASELINE_RANGE.end,
        comparison_kind="previous_period",
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        requester_access=("standard",),
        on=ON,
    ).permitted
    assert not permitted, (
        "the catalog now permits this metric, so SC-001 is reachable and this node "
        "must be re-derived to assert the candidate rather than its absence"
    )

    state = bundle.lifecycles[METRIC]
    assert state.is_published, (
        f"the metric fell back out of published ({state.lifecycle}); the blocker this "
        "node describes is not the blocker it would then be measuring"
    )
    assert state.missing_fields == (), state.missing_fields
    assert state.unapproved_sources == (), (
        "an unapproved source is now named, so the blocker changed and this node's "
        f"explanation is stale: {state.unapproved_sources}"
    )


def test_the_freshness_approval_did_take_effect() -> None:
    """**Read this before believing the node above — and read the qualifier with it.**

    "Still pending" would be an uninteresting fact if the signature had simply not
    landed. It landed: `subscription_daily` is publishable **at the commit its approval
    names**, and there it is the only source in the catalog that is. That is what makes
    the remaining blocker precise rather than vague — the source passed, and the metric
    is what stops.

    **THE QUALIFIER IS NOT DECORATION.** Under the commit any real caller passes — the
    CI's `${GITHUB_SHA}`, the CLI's `workingtree` default — the same approval answers
    `COMMIT_MISMATCH` and NO source is publishable. Written without naming the input,
    this node would report a working approval where the system has an inert one. `F-F`,
    asserted separately in `test_the_approval_is_inert_where_it_is_evaluated.py`.
    """
    catalog = load_catalog(REPO / "semantic")
    # ADR 0033: a commit PER SOURCE, and the one that matters is the approval's own.
    approved = publishable_source_ids(
        catalog,
        source_commits={"subscription_daily": _approved_commit()},
        on=ON,
        permitted_roles=frozenset({"data_governance", "product_analytics"}),
    )
    assert approved == frozenset({"subscription_daily"}), sorted(approved)


def _text(value: object, field: str) -> str:
    """One warehouse value as a string, refusing anything else BY NAME.

    A row read from BigQuery arrives untyped -- the client ships no type information -- so
    every column pulled out of it is `object`. Casting the whole row would claim a shape
    nobody checked; narrowing each field HERE, at the read, turns a column that changed type
    into a red node naming the column instead of a constructor error three frames away.
    """
    assert isinstance(value, str), f"{field} came back as {type(value).__name__}, not a string"
    return value


def _a_date(value: object, field: str) -> date:
    """One warehouse value as a date. `datetime` is refused rather than truncated."""
    assert isinstance(value, date) and not isinstance(value, datetime), (
        f"{field} came back as {type(value).__name__}, not a date"
    )
    return value


def _a_datetime_or_none(value: object, field: str) -> datetime | None:
    """One warehouse value as an instant, or absent. Absence is a fact and stays one."""
    if value is None:
        return None
    assert isinstance(value, datetime), (
        f"{field} came back as {type(value).__name__}, not an instant"
    )
    return value


def _warehouse_snapshot():
    """The freshness and coverage this feature refuses to invent, read from the warehouse.

    **`is_fixture=False` is the whole point and it is earned rather than asserted.** Both
    rows are read live: `semantic.source_freshness` carries a load time measured from the
    job history, and `semantic.metric_availability` carries the window measured from the
    view. A fixture could not say this, and `load_snapshot` forces `is_fixture=True`
    precisely so it cannot pretend otherwise.
    """
    from semantic_catalog.freshness.external import (
        CompletenessStatus,
        FreshnessRecord,
        FreshnessSnapshot,
        ObservedCoverage,
    )

    freshness = list(_query("SELECT * FROM `example-project-id.semantic.source_freshness`"))
    coverage = list(_query("SELECT * FROM `example-project-id.semantic.metric_availability`"))
    if not freshness or not coverage:  # pragma: no cover - the tables were emptied
        pytest.skip("the warehouse holds no freshness or coverage row; nothing was measured")

    observed_at = datetime.now(tz=UTC)
    return FreshnessSnapshot(
        observed_at=observed_at,
        records=tuple(
            FreshnessRecord(
                source=_text(row["source_id"], "source_id"),
                status=CompletenessStatus(_text(row["status"], "status")),
                observed_at=observed_at,
                ingestion_started_at=_a_datetime_or_none(
                    row["ingestion_started_at"], "ingestion_started_at"
                ),
                ingestion_finished_at=_a_datetime_or_none(
                    row["ingestion_finished_at"], "ingestion_finished_at"
                ),
                last_successful_update=_a_datetime_or_none(row["last_loaded_at"], "last_loaded_at"),
            )
            for row in freshness
        ),
        coverage=tuple(
            ObservedCoverage(
                metric=_text(row["metric_id"], "metric_id"),
                source=_text(row["source_id"], "source_id"),
                min_date=_a_date(row["covered_from"], "covered_from"),
                max_date=_a_date(row["covered_to"], "covered_to"),
                observed_at=observed_at,
            )
            for row in coverage
        ),
        is_fixture=False,
    )


def test_the_governed_path_permits_when_the_observation_is_supplied() -> None:
    """**`SC-001`'s first half, and the sentence this file could not write until today.**

    Everything above measures what refuses. This measures what PASSES: with the freshness
    and coverage read from the warehouse, `001` ALLOWS the metric and states the window
    it may be read over. The window is the catalog's own — this feature computes no date.
    """
    resolution = resolve_metric(
        RULE_ID,
        METRIC,
        evaluate=evaluate,
        bundle=_bundle(),
        start=PRIMARY_RANGE.start,
        end=PRIMARY_RANGE.end,
        baseline_start=BASELINE_RANGE.start,
        baseline_end=BASELINE_RANGE.end,
        comparison_kind="previous_period",
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        requester_access=("standard",),
        on=ON,
        snapshot=_warehouse_snapshot(),
    )
    assert resolution.permitted, (
        f"the catalog still refuses with {resolution.reason_code} / {resolution.upstream_code}; "
        "SC-001 needs this to pass and the refusal names which gate is left"
    )
    assert resolution.window is not None, "permitted with no window; FR-012 forbids inventing one"
    assert resolution.window.sources == ("subscription_daily",)
    assert resolution.is_traceable, "the permission carries no decision id"


def test_one_governed_rule_over_one_bound_kpi_produces_a_candidate() -> None:
    """**`SC-001` itself, end to end, against the real warehouse.**

    One rule, one bound KPI, real numbers, a governed window and a governed decision —
    and a `CandidateFinding` at the end of it. Every part is read rather than invented:

    * the figures come from the view, over two real windows;
    * the movement derives through the `002` and `003` seams;
    * the window comes from `001`'s decision, not from this feature;
    * the freshness record carries a load time measured from the job history;
    * the causality warning is compared byte for byte against the baseline's own text,
      so this feature cannot paraphrase it into a claim.

    **What this still does not do** is run `002`'s nine-step pipeline, and that is stated
    here rather than implied: the numbers are real, the pipeline that would normally
    fetch them is stood in for by an executor. `FR-008` forbids assembling the ledger,
    adapter and audit sink this feature does not own.
    """
    from anomaly_investigation.contracts.candidate import (
        REQUIRED_CAUSALITY_WARNING,
        CandidateFinding,
        ClaimType,
    )

    snapshot = _warehouse_snapshot()
    resolution = resolve_metric(
        RULE_ID,
        METRIC,
        evaluate=evaluate,
        bundle=_bundle(),
        start=PRIMARY_RANGE.start,
        end=PRIMARY_RANGE.end,
        baseline_start=BASELINE_RANGE.start,
        baseline_end=BASELINE_RANGE.end,
        comparison_kind="previous_period",
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        requester_access=("standard",),
        on=ON,
        snapshot=snapshot,
    )
    assert resolution.permitted and resolution.window is not None

    movement = _movement()
    assert movement.derived and movement.movement is not None, (
        "the movement did not derive, so there is no figure to carry into a candidate"
    )

    baseline = _sum_over(BASELINE_RANGE.start, BASELINE_RANGE.end)
    record = next(r for r in snapshot.records if r.source == "subscription_daily")
    candidate = CandidateFinding(
        rule_id=RULE_ID,
        figure=movement.movement,
        baseline_value=baseline,
        # Read off the measured movement, never chosen: a direction picked by hand would
        # be this feature asserting which way the world moved.
        direction=(
            Direction.DECREASE
            if movement.movement.value < 0
            else Direction.INCREASE
            if movement.movement.value > 0
            else Direction.STABLE
        ),
        primary_window=resolution.window,
        baseline_window=resolution.window,
        freshness=record,
        claim_type=ClaimType.TEMPORAL_ASSOCIATION,
        causality_warning=REQUIRED_CAUSALITY_WARNING,
    )

    assert candidate.rule_id == RULE_ID
    assert candidate.figure.value == movement.movement.value, "the figure was not carried"
    assert candidate.baseline_value == baseline
    assert candidate.causality_warning == REQUIRED_CAUSALITY_WARNING
    assert candidate.freshness.last_successful_update is not None, (
        "the candidate carries no measured load time, so its freshness is a claim about "
        "something nobody observed"
    )
