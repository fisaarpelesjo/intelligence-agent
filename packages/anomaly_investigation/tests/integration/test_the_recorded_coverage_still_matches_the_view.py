"""The recorded coverage still matches the view — `F-4`, and it rotted in six hours.

**`semantic.metric_availability` FREEZES a window that SLIDES.** The row records the
`MIN` and `MAX` of `event_date` at the instant it was written; the view's window moves
thirteen months ending yesterday, and the source is rebuilt daily. So the row is correct
when written and wrong the next morning.

**This file used to say the rebuild runs at 04:00 UTC. Measured on 2026-09-07, it does
not** -- `tbl_summary` was last written at `06:00:44Z`, and `metric_availability` at
`07:00:18Z` the day before. Neither hour is ours: both live in the scheduled queries of
another repository, and a number copied here goes stale without anything failing. So no
hour is written down any more. **The instants are read from the tables themselves**, and
the table that carries the rebuild is derived from the view's own definition rather than
named by hand -- if the view is ever pointed somewhere else, this node follows it.

**And nothing measured that**, which is the whole finding. `l3_reconciliation` compares
a metric's `available_from` against the **TABLE's** `min_date` — never against the view.
Table and catalog agree with each other, and after one rebuild **both are wrong about
the world**. The gate cannot bite: it is comparing two copies of the same stale number.

Measured on 2026-08-27, less than six hours after the row was written:

===============================  ==============  ==============
source                           covered_from    covered_to
===============================  ==============  ==============
``metric_availability`` (row)    2025-07-26      2026-08-25
the view, for `New trials`       2025-07-27      2026-08-26
===============================  ==============  ==============

One day, in the direction that matters: the row claims coverage for a day the view no
longer has.

## This node compares the two directly, and that is the point

It asks the warehouse both questions and compares the answers. It does not read a
report, and it does not assert that somebody once compared them — the difference is the
one this repository keeps paying for.

## Absence skips, loudly, and never passes for lack of looking

With no credential the node **skips naming what was not measured**, exactly as `T023`
does. A node that quietly passed when it could not reach the warehouse would report
*"table and view agree"* on the strength of having asked neither.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

#: `tests/integration/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]

PROJECT = "example-project-id"
VIEW = "example-project-id.semantic.subscription_daily_metrics"
AVAILABILITY = "example-project-id.semantic.metric_availability"

#: The pair this feature declared. The KPI is how the view names what the metric means.
METRIC = "new_trials"
SOURCE = "subscription_daily"
KPI = "New trials"


class _ReadRow(Protocol):
    """The one thing this file does to a result row: read its columns as a mapping."""

    def items(self) -> Iterable[tuple[str, object]]: ...


def _rows(sql: str) -> Iterator[dict[str, object]]:
    """Run one read against the real warehouse, or skip naming what was not measured."""
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
        yield from (dict(row.items()) for row in rows)
    except RefreshError as expired:  # pragma: no cover - an expired application default
        pytest.skip(
            "the BigQuery credential is absent or expired; since OD-62 the remedy is "
            "GOOGLE_APPLICATION_CREDENTIALS pointing at the read-only service account "
            f"(docs/credencial-bigquery-service-account.md): {expired}"
        )


def _recorded() -> tuple[date, date]:
    """What the table says. Skips when the pair is absent rather than inventing one."""
    rows = list(
        _rows(
            "SELECT covered_from, covered_to FROM `"
            + AVAILABILITY
            + f"` WHERE metric_id = '{METRIC}' AND source_id = '{SOURCE}'"
        )
    )
    if not rows:  # pragma: no cover - the declaration was withdrawn
        pytest.skip(f"no row for ({METRIC}, {SOURCE}); there is no recorded window to compare")
    row = rows[0]
    return row["covered_from"], row["covered_to"]  # type: ignore[return-value]


def _observed() -> tuple[date, date]:
    """What the view holds, right now."""
    rows = list(
        _rows(
            "SELECT MIN(event_date) AS covered_from, MAX(event_date) AS covered_to FROM `"
            + VIEW
            + f"` WHERE kpi_name = '{KPI}'"
        )
    )
    assert rows, "the view returned no rows for the bound KPI"
    row = rows[0]
    assert row["covered_from"] is not None, "the view measured no window for the bound KPI"
    return row["covered_from"], row["covered_to"]  # type: ignore[return-value]


def test_the_recorded_window_is_the_window_the_view_has() -> None:
    """**The comparison nothing was making, made against both sources.**

    A difference here does not mean somebody was careless. It means the source slid and
    the recording did not follow, which is what a frozen row over a sliding window does
    every single day.

    ## What this node used to say, and why it stopped saying it — 2026-09-07

    It used to demand equality outright, and end with *"the fix is to re-measure the row —
    never to widen this node"*. **The first half of that sentence contradicted the record**:
    `0493f89` writes down that the owner REFUSED to re-measure, for the right reason — a
    re-measured row is green until the next rebuild, which is a snapshot of a thing that
    moves. And the row lives in BigQuery, so re-measuring is a WRITE into another
    repository's warehouse, which is not a fix available from here.

    Meanwhile the demand was false for **one hour every day**. Measured: the source is
    rebuilt first and the availability row follows about an hour later, so between the two
    the row is exactly one cycle behind and nothing is wrong. A push at `05:37Z` passed and
    the next at `06:08Z` failed, same tree.

    **The second half of that sentence still holds and this is not a widening.** The node
    now asks a sharper question, not a weaker one: it compares the two windows AND the two
    instants, and a row is forgiven only while it has not yet had its turn to follow. Two
    cycles behind is red. One cycle behind after the row was already rewritten is red --
    it had its chance and did not take it. Only the gap between the two writes is
    tolerated, and that gap is read, never assumed.
    """
    recorded_from, recorded_to = _recorded()
    observed_from, observed_to = _observed()
    row_written = _last_written(AVAILABILITY)
    source_rebuilt = _last_written(_the_table_the_view_reads())
    assert row_is_allowed_to_lag(
        recorded=(recorded_from, recorded_to),
        observed=(observed_from, observed_to),
        row_written=row_written,
        source_rebuilt=source_rebuilt,
    ), (
        f"metric_availability records {recorded_from}..{recorded_to} and the view holds "
        f"{observed_from}..{observed_to}. The row was written at {row_written:%Y-%m-%d %H:%M:%S}Z "
        f"and the source was rebuilt at {source_rebuilt:%Y-%m-%d %H:%M:%S}Z, so this is not the "
        "window between the two writes: the catalog is asserting coverage the warehouse no "
        "longer has"
    )


#: The grain of ``event_date``, which is what "one cycle" means here. This is NOT a schedule:
#: no hour of the day is written down anywhere in this file, on purpose.
ONE_CYCLE = timedelta(days=1)


def row_is_allowed_to_lag(
    *,
    recorded: tuple[date, date],
    observed: tuple[date, date],
    row_written: datetime,
    source_rebuilt: datetime,
    cycle: timedelta = ONE_CYCLE,
) -> bool:
    """May the recorded window differ from the view's, given WHEN each one was written?

    **A pure function, so both directions can be driven without a warehouse** — the same
    shape `declaration_over_claims` uses, and for the same reason: a rule that can only be
    exercised against live BigQuery is a rule nobody can prove bites.

    Two situations produce the identical pair of windows and are opposite in meaning:

    * the source was rebuilt and the row has **not yet been rewritten** — `row_written`
      precedes `source_rebuilt`. The row is one cycle behind because it is waiting its turn.
      Nothing is wrong and nothing is over-claimed on purpose;
    * the row **was** rewritten after the rebuild and is still behind. It had its
      opportunity and did not follow, and now the catalog really is announcing a day the
      warehouse dropped.

    Anything further behind than one cycle is red in both cases: an hour of lag explains one
    cycle and explains no more than one.

    ## "Waiting its turn" has an expiry, and the first version of this did not — `S-63`

    Written first as `row_written < source_rebuilt`, and that comparison is **as true for an
    interval of one hour as for one of a year**. A row written a year before the rebuild is
    not waiting its turn: it is abandoned, and the sentence above stops describing it long
    before then.

    **The case is reachable and this repository has the precedent.** Let the availability row
    die before its own run on a day the source already rebuilt: the view holds through `D-1`,
    the row through `D-2`, and `row_written` is yesterday's. Green. If the source keeps
    rebuilding, tomorrow it is two cycles behind and this fires — correct. **But if BOTH stop,
    it stays green forever, over-claiming a day** — two frozen copies agreeing with each
    other, which is the `F-4` this entire file exists to name. These rows have been stopped
    before: `docs/pedido-ao-business-intelligence-linhas-de-observacao.md` records it.

    So the two writes must belong to the **same cycle**. Measured on 2026-09-07, the real
    interval is `22h59m25s` — an hour of room — and it only exceeds a cycle when the two
    schedules drift more than a full cycle apart, which is exactly when the story of waiting
    one's turn can no longer be told. **Still no hour of the day is written down**: the bound
    is the `cycle` already declared as the grain of `event_date`.
    """
    if recorded == observed:
        return True
    recorded_from, recorded_to = recorded
    observed_from, observed_to = observed
    exactly_one_behind = (
        observed_from - recorded_from == cycle and observed_to - recorded_to == cycle
    )
    if not exactly_one_behind:
        return False
    if not row_written < source_rebuilt:
        return False
    return source_rebuilt - row_written < cycle


def _last_written(fully_qualified: str) -> datetime:
    """When BigQuery last wrote this table, read from the dataset's own metadata.

    Skips naming what was not measured rather than guessing an instant. **A missing instant
    must never read as agreement**: that is the defect this whole file exists to name, and
    it would be a poor joke to reintroduce it in the clause that measures time.
    """
    project, dataset, table = fully_qualified.split(".")
    rows = list(
        _rows(
            "SELECT TIMESTAMP_MILLIS(last_modified_time) AS written FROM "
            f"`{project}.{dataset}.__TABLES__` WHERE table_id = '{table}'"
        )
    )
    if not rows:
        pytest.skip(
            f"{fully_qualified} has no row in __TABLES__; its write instant was not measured"
        )
    written = rows[0]["written"]
    if written is None:  # pragma: no cover - a table with no recorded write
        pytest.skip(f"{fully_qualified} reports no last_modified_time; nothing was measured")
    return cast("datetime", written)


def _the_table_the_view_reads() -> str:
    """The table whose rebuild moves the view, derived from the view's own definition.

    Naming it here by hand would put a second copy of somebody else's decision in this
    file, which is the defect three separate nodes closed this week. So it is read: the
    view's body is fetched and the tables it references are extracted. **Exactly one, or
    this node skips** — with two sources there is no single rebuild instant to compare
    against, and picking one would be a guess wearing a measurement's clothes.
    """
    _, dataset, view = VIEW.split(".")
    rows = list(
        _rows(
            "SELECT view_definition FROM "
            f"`{PROJECT}.{dataset}.INFORMATION_SCHEMA.VIEWS` WHERE table_name = '{view}'"
        )
    )
    if not rows:
        pytest.skip(f"{VIEW} has no definition in INFORMATION_SCHEMA.VIEWS; nothing was measured")
    body = cast("str", rows[0]["view_definition"] or "")
    referenced = sorted(set(re.findall(r"`([\w\-]+\.[\w]+\.[\w]+)`", body)))
    if len(referenced) != 1:
        pytest.skip(
            f"{VIEW} reads {len(referenced)} tables ({referenced}); there is no single rebuild "
            "instant to compare against, so nothing was measured"
        )
    return referenced[0]


def _retained_edge() -> date:
    """The oldest day the SOURCE still retains, across every KPI in the view.

    **The window is a retention edge that moves, and this is how that is observed rather
    than assumed.** The view carries no date filter of its own; the thirteen-month window
    is a property of the table it reads, rebuilt daily. So the edge is read the only way it
    can be read here without writing a number down: the oldest day the view holds **at
    all**. A KPI whose own oldest day IS that edge is bounded by retention. A KPI whose
    oldest day comes LATER is bounded by itself — it genuinely has no earlier data.
    """
    rows = list(_rows("SELECT MIN(event_date) AS edge FROM `" + VIEW + "`"))
    assert rows, "the view returned no rows at all"
    edge = rows[0]["edge"]
    assert edge is not None, "the view holds no day at all; there is no retention edge to read"
    return cast("date", edge)


def declaration_over_claims(
    *, declared_from: date, observed_from: date, retained_edge: date
) -> bool:
    """Does ``declared_from`` claim a day the SOURCE does not have for this KPI?

    **This is the whole re-derivation, and it is a pure function so both directions can be
    driven without a warehouse.** Two situations look identical to a comparison of dates and
    are opposite in meaning:

    * ``observed_from == retained_edge`` — the KPI reaches as far back as the source keeps
      anything. A declaration before it is **the window having slid past a date somebody
      wrote**, not a claim about days the source never had. The next rebuild moves the edge
      again, and would move it again the day after any rewritten date.
    * ``observed_from > retained_edge`` — the source still holds older days and this KPI has
      none of them. Now a declaration before ``observed_from`` **is** claiming days the
      warehouse does not have for it, and no rebuild tomorrow changes that.

    So the sliding case is not a violation and the real one is, and **no date written in this
    file decides which is which** — `OD-22-A`.
    """
    if observed_from <= retained_edge:
        return False
    return declared_from < observed_from


def _observed_first_day_by_kpi() -> dict[str, date]:
    """The first day the view holds, **per KPI**, in one read."""
    rows = _rows(
        "SELECT kpi_name, MIN(event_date) AS first_day FROM `" + VIEW + "` GROUP BY kpi_name"
    )
    observed: dict[str, date] = {}
    for row in rows:
        first_day = row["first_day"]
        if first_day is None:  # pragma: no cover - a KPI with no day at all
            continue
        observed[cast("str", row["kpi_name"])] = cast("date", first_day)
    return observed


def partition_by_what_bounds_them(
    observed: dict[str, date], retained_edge: date
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split KPIs into the two situations the predicate distinguishes.

    Returns ``(bounded_by_retention, bounded_by_their_own_history)``. The first group
    short-circuits `declaration_over_claims` before it compares anything; **only the second
    reaches the comparison at all.**
    """
    retention = tuple(sorted(name for name, day in observed.items() if day <= retained_edge))
    own = tuple(sorted(name for name, day in observed.items() if day > retained_edge))
    return retention, own


def exercise_report(
    bounded_by_retention: tuple[str, ...], bounded_by_their_own_history: tuple[str, ...]
) -> str:
    """One sentence naming **what the predicate was actually exercised against.**

    `S-6`. The comparison lives behind a short circuit, so a catalog where every KPI sits on
    the retention edge makes the node answer *not a violation* for every one of them without
    comparing a single date. That is the correct answer and it is also **no measurement**,
    and the difference has to be readable rather than inferred from a green run.
    """
    total = len(bounded_by_retention) + len(bounded_by_their_own_history)
    if not bounded_by_their_own_history:
        return (
            f"the coverage predicate saw {total} KPIs and compared NO date: all {total} sit on "
            "the retention edge, so the comparison short-circuited for every one of them. "
            "This node asserted nothing about any KPI's declaration today; what guards the "
            "comparison itself is test_the_re_derived_predicate_bites_in_both_directions"
        )
    return (
        f"the coverage predicate saw {total} KPIs and compared "
        f"{len(bounded_by_their_own_history)} of them: "
        f"{', '.join(bounded_by_their_own_history)} start after the retention edge, so their "
        "declarations were really checked; the remaining "
        f"{len(bounded_by_retention)} sit on the edge and short-circuited"
    )


def test_it_reports_how_many_kpis_the_predicate_was_exercised_against() -> None:
    """`S-6`. **The count is emitted on a green run, so a zero is read rather than inferred.**

    The reviewer measured it on 2026-08-30: **zero of twenty** KPIs in the view begin after
    the retention edge — all twenty start on 2025-07-30, which IS the edge. So the node below
    answers *no violation* twenty times without comparing one date, and a reader seeing it
    green would conclude the coverage of twenty KPIs had been checked. It had not.

    **This is not a logic defect and the fix is not to the logic.** The short circuit is
    correct: a declaration older than a window bounded by retention is a date the window slid
    past, not an over-claim. What was wrong was the silence — the same family as `S-2`, and as
    a gate reading green because its nodes were skipping.

    The number is warned rather than asserted **on purpose**. Asserting *"N KPIs are bounded
    by their own history"* would make this node go red the day the warehouse changes shape,
    which is the node-measuring-the-world defect this very file warns about two docstrings up.
    """
    import warnings

    observed = _observed_first_day_by_kpi()
    assert observed, "the view names no KPI at all; there is nothing to be exercised against"

    retained_edge = _retained_edge()
    retention, own = partition_by_what_bounds_them(observed, retained_edge)
    assert len(retention) + len(own) == len(observed), "a KPI fell out of both groups"

    #: The declared pair must be among what was swept, or this node and the one below are
    #: measuring different worlds.
    assert KPI in observed, f"{KPI!r} is not in the view; the declared pair reaches nothing"

    warnings.warn(exercise_report(retention, own), stacklevel=1)


def test_the_exercise_report_makes_a_vacuous_run_visible() -> None:
    """**Read this before believing the count** — the mutation `S-6` names, both directions.

    A report that read the same either way would be one more green thing to skim past.
    """
    everything_on_the_edge = exercise_report(("A", "B", "C"), ())
    assert "compared NO date" in everything_on_the_edge
    assert "asserted nothing about any KPI" in everything_on_the_edge

    one_off_the_edge = exercise_report(("A", "B"), ("C",))
    assert "compared 1 of them" in one_off_the_edge
    assert "C start after the retention edge" in one_off_the_edge
    assert "NO date" not in one_off_the_edge

    #: And the partition that feeds it, driven with no warehouse.
    edge = date(2025, 7, 30)
    retention, own = partition_by_what_bounds_them(
        {"on the edge": edge, "later": edge + timedelta(days=1)}, edge
    )
    assert retention == ("on the edge",)
    assert own == ("later",)


def test_the_declared_availability_does_not_precede_the_view() -> None:
    """**The half `l3_reconciliation` structurally cannot check** — RE-DERIVED under `OD-22-A`.

    That gate compares `available_from` against the TABLE. When the table is stale, the two
    agree and both are wrong. Here the declaration is compared against **the view**.

    ## What it asserted, why it went red, and why the repair was not a new date

    It asserted ``declared >= observed_from`` outright. On 2026-08-30 that was red: the
    declaration read 2025-07-27 and the view held this KPI from 2025-07-30. **Nobody was
    careless and nothing was over-claimed** — the thirteen-month window had slid three days
    past a date measured against it on 2026-08-27, and it slides again every morning.

    **The owner refused the obvious repair**, and his reason is the finding: re-measuring the
    date makes this green until the next rebuild, which is a snapshot of a thing that moves —
    the defect this repository hunts, not the fix. `OD-22-A` says derive instead of dating.

    So the property is stated against the **retention edge**, which is itself observed: a
    declaration older than a window bounded by retention is stale, and a declaration older
    than a window bounded by the KPI's own history is an over-claim. Only the second is a
    defect, and nothing written here decides which is which.

    ## What this node does NOT assert today, stated rather than left to be discovered

    **`S-6`.** Every KPI the view holds sits ON the retention edge — twenty of twenty when
    the reviewer measured it on 2026-08-30 — so the comparison **short-circuits for all of
    them** and this node answers *no violation* without comparing a date. That answer is
    correct and it is also no measurement. The node named
    `test_it_reports_how_many_kpis_the_predicate_was_exercised_against` emits the two counts
    on every run, so the day that number is zero is read rather than inferred, and
    `test_the_re_derived_predicate_bites_in_both_directions` is what holds the comparison
    itself upright meanwhile.
    """
    from semantic_catalog.contracts.metric import AvailabilityStatus
    from semantic_catalog.loader.bundle import load_catalog

    catalog = load_catalog(REPO / "semantic")
    metric = catalog.metrics[METRIC]
    declared = [
        entry
        for entry in metric.source_availability
        if entry.source == SOURCE and entry.status is AvailabilityStatus.AVAILABLE
    ]
    assert declared, f"{METRIC} no longer declares {SOURCE} available; this node measures nothing"

    observed_from, _ = _observed()
    retained_edge = _retained_edge()
    for entry in declared:
        assert entry.available_from is not None
        assert not declaration_over_claims(
            declared_from=entry.available_from,
            observed_from=observed_from,
            retained_edge=retained_edge,
        ), (
            f"{METRIC} declares availability from {entry.available_from}; the view holds this "
            f"KPI from {observed_from} while it still retains days back to {retained_edge}, so "
            "the missing days are the KPI's own and the declaration covers days the warehouse "
            "does not have for it"
        )


def test_the_re_derived_predicate_bites_in_both_directions() -> None:
    """**Read this before believing the node above** — the two mutations `OD-22-A` names.

    A predicate that never fires would report a clean catalog forever, and one that fires on
    the slide would be the node needing an edit every morning. Both directions are driven
    here, with no warehouse and no date written against today's window.
    """
    #: The window slid: every observed date moves together and the KPI still reaches the
    #: edge. **This must NOT fire** — it is exactly the situation that was red.
    for day in range(5):
        slid = date(2025, 7, 30) + timedelta(days=day)
        assert not declaration_over_claims(
            declared_from=date(2025, 7, 27), observed_from=slid, retained_edge=slid
        ), f"the slide alone fired the predicate at {slid}, which is the defect it replaced"

    #: The source still holds older days and this KPI has none of them. **This MUST fire.**
    assert declaration_over_claims(
        declared_from=date(2025, 7, 27),
        observed_from=date(2025, 9, 1),
        retained_edge=date(2025, 7, 30),
    ), "a declaration reaching past the KPI's own history did not fire"

    #: And the boundary, both ways: one day inside is a claim, the first observed day is not.
    assert declaration_over_claims(
        declared_from=date(2025, 8, 31),
        observed_from=date(2025, 9, 1),
        retained_edge=date(2025, 7, 30),
    )
    assert not declaration_over_claims(
        declared_from=date(2025, 9, 1),
        observed_from=date(2025, 9, 1),
        retained_edge=date(2025, 7, 30),
    )


def test_the_lag_rule_bites_in_both_directions() -> None:
    """**The forgiveness is exactly one cycle wide, and only before the row's turn.**

    Driven as a pure function, with no warehouse, so the rule can be proven to bite in the
    direction that matters — a node that only ever runs against live data green is a node
    nobody has seen refuse.
    """
    rebuilt = datetime(2026, 9, 7, 6, 0, 44, tzinfo=UTC)
    before = datetime(2026, 9, 6, 7, 0, 18, tzinfo=UTC)
    after = datetime(2026, 9, 7, 7, 0, 18, tzinfo=UTC)
    current = (date(2025, 8, 7), date(2026, 9, 6))
    one_behind = (date(2025, 8, 6), date(2026, 9, 5))
    two_behind = (date(2025, 8, 5), date(2026, 9, 4))

    #: The row equals the view: nothing to forgive, and WHEN it was written cannot matter.
    assert row_is_allowed_to_lag(
        recorded=current, observed=current, row_written=after, source_rebuilt=rebuilt
    )

    #: One cycle behind, written BEFORE the rebuild: it is waiting its turn. This is the
    #: hour that closed the push gate every single day, and it is not a defect.
    assert row_is_allowed_to_lag(
        recorded=one_behind, observed=current, row_written=before, source_rebuilt=rebuilt
    )

    #: One cycle behind, written AFTER the rebuild: it had its turn and did not follow.
    assert not row_is_allowed_to_lag(
        recorded=one_behind, observed=current, row_written=after, source_rebuilt=rebuilt
    )

    #: Two cycles behind is red however you slice the instants -- an hour of lag explains
    #: one cycle and explains no more than one. THIS is the real over-claim the node exists
    #: to catch, and the forgiveness must not reach it.
    assert not row_is_allowed_to_lag(
        recorded=two_behind, observed=current, row_written=before, source_rebuilt=rebuilt
    )
    assert not row_is_allowed_to_lag(
        recorded=two_behind, observed=current, row_written=after, source_rebuilt=rebuilt
    )

    #: Behind on ONE end only is not "one cycle behind": the pair moves together or the row
    #: is describing a window nobody wrote.
    assert not row_is_allowed_to_lag(
        recorded=(date(2025, 8, 6), date(2026, 9, 6)),
        observed=current,
        row_written=before,
        source_rebuilt=rebuilt,
    )

    #: ONE CYCLE BEHIND, WRITTEN LONG BEFORE THE REBUILD -- `S-63`. The row is not waiting
    #: its turn, it is abandoned, and two frozen copies agreeing with each other is the
    #: `F-4` this file exists to name. A month and a year, because `row_written <
    #: source_rebuilt` is equally true for both and the sentence in the docstring is true
    #: for neither.
    a_month_early = rebuilt - timedelta(days=30)
    a_year_early = rebuilt - timedelta(days=365)
    assert not row_is_allowed_to_lag(
        recorded=one_behind, observed=current, row_written=a_month_early, source_rebuilt=rebuilt
    )
    assert not row_is_allowed_to_lag(
        recorded=one_behind, observed=current, row_written=a_year_early, source_rebuilt=rebuilt
    )

    #: And the boundary of that bound, both sides of it: the real interval measured on
    #: 2026-09-07 was 22h59m25s and must pass; a full cycle apart must not. The bound is the
    #: cycle itself, so this moves with `ONE_CYCLE` and with no hour written down.
    assert row_is_allowed_to_lag(
        recorded=one_behind,
        observed=current,
        row_written=rebuilt - ONE_CYCLE + timedelta(seconds=1),
        source_rebuilt=rebuilt,
    )
    assert not row_is_allowed_to_lag(
        recorded=one_behind,
        observed=current,
        row_written=rebuilt - ONE_CYCLE,
        source_rebuilt=rebuilt,
    )

    #: And the row AHEAD of the view is never forgiven -- it announces a day the view does
    #: not have at all, which is the over-claim in its purest form.
    assert not row_is_allowed_to_lag(
        recorded=(date(2025, 8, 8), date(2026, 9, 7)),
        observed=current,
        row_written=before,
        source_rebuilt=rebuilt,
    )
