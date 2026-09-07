"""`T906`, `T907` — every run written down, with both stamps, and four outcomes that stay four."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

import pytest

from daily_reporting.run.journal import Outcome, exit_code, line_for, outcome_for

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

pytestmark = pytest.mark.contract

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
INSTANT = datetime(2026, 8, 31, 7, 0, 12, tzinfo=UTC)
CLOSED_DAY = date(2026, 8, 30)


def _append(path: Path, **kwargs: object) -> None:
    """The package composes; the caller writes. `T828` forbids this package holding the `open`,
    and none of the DECISIONS moved — only the four lines that put a string on a disk."""
    line = line_for(**kwargs)  # type: ignore[arg-type]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _lines(path: Path) -> list[dict[str, Any]]:
    return [
        cast("dict[str, Any]", json.loads(raw))
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]


def test_both_stamps_are_written_and_both_carry_an_offset(tmp_path: Path) -> None:
    """`SC-906`, `FR-905`.

    A journal whose instants are naive cannot be ordered against a rebuild that is scheduled in
    UTC, and this loop has already produced clock fields three hours — and once ninety-five
    minutes — away from the truth.
    """
    journal = tmp_path / "runs" / "daily-report.jsonl"
    _append(
        journal,
        instant=INSTANT,
        closed_day=CLOSED_DAY,
        outcome=Outcome.SENT,
        zone=SAO_PAULO,
        message_id=41,
    )

    (line,) = _lines(journal)
    written_utc = datetime.fromisoformat(line["instant"])
    written_local = datetime.fromisoformat(line["local"])

    assert written_utc.utcoffset() is not None, "the UTC stamp is naive"
    assert written_local.utcoffset() is not None, "the local stamp is naive"
    #: The SAME instant, said twice — not two readings of a clock.
    assert written_utc == written_local == INSTANT
    #: And they are genuinely different clocks: 07:00Z is 04:00 in São Paulo.
    assert written_local.strftime("%H:%M") == "04:00"
    assert written_utc.strftime("%H:%M") == "07:00"

    assert line["closed_day"] == "2026-08-30"
    assert line["message_id"] == 41


def test_an_instant_without_a_zone_is_refused(tmp_path: Path) -> None:
    """Assuming naive means UTC is how an instant three hours off reaches a record nobody
    re-reads until it matters."""
    with pytest.raises(ValueError, match="carries no zone"):
        _append(
            tmp_path / "j.jsonl",
            instant=datetime(2026, 8, 31, 7, 0, 12),
            closed_day=CLOSED_DAY,
            outcome=Outcome.SENT,
            zone=SAO_PAULO,
        )


def test_the_four_outcomes_are_four(tmp_path: Path) -> None:
    """`FR-906` — and the pair that must never merge is refused against failed.

    A **refusal** is the system working: the warehouse had not rebuilt and `008` refuses on
    purpose. A **failure** is the system broken. Collapsing them loses the one distinction that
    tells him whether to do anything.
    """
    assert len({str(outcome) for outcome in Outcome}) == 4

    journal = tmp_path / "j.jsonl"
    for index, outcome in enumerate(Outcome):
        _append(
            journal,
            instant=INSTANT,
            closed_day=date(2026, 8, 20 + index),
            outcome=outcome,
            zone=SAO_PAULO,
            reason=str(outcome),
        )

    written = [line["outcome"] for line in _lines(journal)]
    assert written == [str(outcome) for outcome in Outcome]
    assert len(set(written)) == 4, "two outcomes were written as the same word"
    assert str(Outcome.REFUSED) != str(Outcome.FAILED)


def test_a_refusal_never_reads_as_a_success(tmp_path: Path) -> None:
    """`FR-907` — the outcome says WHICH, and the exit code says NOT FINE.

    The scheduler's history is the only place some of these are ever read, and there a zero means
    *fine*. A refusal is not fine; it is **correct**, which is a different word.
    """
    assert exit_code(Outcome.SENT) == 0
    assert exit_code(Outcome.ALREADY_SENT) == 0
    assert exit_code(Outcome.REFUSED) != 0
    assert exit_code(Outcome.FAILED) != 0

    journal = tmp_path / "j.jsonl"
    _append(
        journal,
        instant=INSTANT,
        closed_day=CLOSED_DAY,
        outcome=Outcome.REFUSED,
        zone=SAO_PAULO,
        reason="a view ainda nao carregou 2026-08-30",
    )
    (line,) = _lines(journal)
    assert line["outcome"] == "refused"
    assert line["reason"], "a refusal was recorded with no reason"
    assert line["message_id"] is None


def test_the_latest_line_for_a_day_is_the_one_that_answers(tmp_path: Path) -> None:
    """A day refused at 04:00 and sent at 09:00 is a day that **went**.

    Read the other way round, the journal would send it twice.
    """
    journal = tmp_path / "j.jsonl"
    _append(
        journal,
        instant=INSTANT,
        closed_day=CLOSED_DAY,
        outcome=Outcome.REFUSED,
        zone=SAO_PAULO,
    )
    _append(
        journal,
        instant=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
        closed_day=CLOSED_DAY,
        outcome=Outcome.SENT,
        zone=SAO_PAULO,
    )

    assert outcome_for(journal, CLOSED_DAY) is Outcome.SENT
    #: And another day's lines do not answer for this one.
    assert outcome_for(journal, date(2026, 8, 29)) is None
