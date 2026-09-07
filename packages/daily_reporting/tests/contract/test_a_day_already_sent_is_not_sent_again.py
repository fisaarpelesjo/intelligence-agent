"""`T908` — `FR-908`, `SC-903`, and the node bites in **both** directions.

The Windows Task Scheduler can start a task more than once for one scheduled day: the machine is
asleep at the hour and the task runs on wake, a missed run is caught up later, or he starts it
himself to watch it work. **That is a property of the trigger `OD-21-B` chose**, not a hypothetical.

The direction a tautological node would miss is the second one. Stopping a day that already went is
easy to assert; **not stopping a day that only got refused** is where the defect lives, because a
day nobody could send yet is a day still owed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from daily_reporting.run.journal import Outcome, already_sent, line_for

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

pytestmark = pytest.mark.contract

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
INSTANT = datetime(2026, 8, 31, 7, 0, 12, tzinfo=UTC)
CLOSED_DAY = date(2026, 8, 30)


def _write(journal: Path, outcome: Outcome, *, day: date = CLOSED_DAY) -> None:
    """The package composes the line and the caller appends it — `T828`, and this helper is the
    caller for the purposes of these nodes."""
    line = line_for(instant=INSTANT, closed_day=day, outcome=outcome, zone=SAO_PAULO)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(line)


def test_a_day_already_sent_stops_the_second_run(tmp_path: Path) -> None:
    """`SC-903`, the easy direction."""
    journal = tmp_path / "j.jsonl"
    _write(journal, Outcome.SENT)
    assert already_sent(journal, CLOSED_DAY)


def test_a_day_only_refused_does_not_stop_anything(tmp_path: Path) -> None:
    """**The direction that matters.**

    A refusal means the warehouse had not rebuilt. Treating it as delivery is how the report
    silently stops arriving on exactly the days the run was early — which is the failure spec `009`
    was written around.
    """
    journal = tmp_path / "j.jsonl"
    _write(journal, Outcome.REFUSED)
    assert not already_sent(journal, CLOSED_DAY), "a refused day read as delivered"

    #: The same for a failure: a run that broke delivered nothing.
    failed = tmp_path / "f.jsonl"
    _write(failed, Outcome.FAILED)
    assert not already_sent(failed, CLOSED_DAY)


def test_no_journal_at_all_does_not_stop_anything(tmp_path: Path) -> None:
    """The first run this machine ever makes has nothing to read, and must still run."""
    assert not already_sent(tmp_path / "never-written.jsonl", CLOSED_DAY)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert not already_sent(empty, CLOSED_DAY)


def test_another_days_delivery_does_not_stop_this_one(tmp_path: Path) -> None:
    """The journal is one file for every day, so the day is part of the question."""
    journal = tmp_path / "j.jsonl"
    _write(journal, Outcome.SENT, day=date(2026, 8, 29))
    assert already_sent(journal, date(2026, 8, 29))
    assert not already_sent(journal, CLOSED_DAY), "yesterday's delivery stopped today's"


def test_a_day_refused_and_then_sent_is_a_day_that_went(tmp_path: Path) -> None:
    """Both lines exist and the later one is the answer — the catch-up run that worked."""
    journal = tmp_path / "j.jsonl"
    _write(journal, Outcome.REFUSED)
    _write(journal, Outcome.SENT)
    assert already_sent(journal, CLOSED_DAY)


def test_a_torn_line_is_not_read_as_a_delivery(tmp_path: Path) -> None:
    """A process killed mid-append leaves half a line. **Half a line is not a delivery.**"""
    journal = tmp_path / "j.jsonl"
    _write(journal, Outcome.REFUSED)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write('{"closed_day": "2026-08-30", "outc')
    assert not already_sent(journal, CLOSED_DAY)
