"""The earliest hour the daily run may start — `FR-903`, `FR-904`, `FR-905`.

## Why the hour is derived and not written

The view the report reads is rebuilt by the neighbouring project, and **a run before that rebuild
finishes finds the closed day absent and refuses**. That refusal is correct; `008` built it on
purpose. But a trigger registered an hour too early turns a correct refusal into a report that
never arrives — every day, in silence, looking exactly like a quiet day.

The upstream hour has already moved once: measured from `business-intelligence`'s own changelog,
`tbl_summary` went from `04:00` to `06:00` UTC on 2026-06-08, because it depends on
`tbl_clients_overview` at `05:00` and was otherwise reading the previous day's clients. **That move
had nothing to do with this repository and nothing here would have noticed it.** A number copied
into a scheduler by hand cannot; a rule over a measurement can.

## The rule

> The earliest admissible trigger is **the first whole hour strictly after** the measured completion
> of the rebuild.

The rounding is what buys the margin, without anybody choosing a margin. Measured 2026-08-31 from
`example_dataset.__TABLES__`, `SELECT` only: the last completion was `2026-08-30T06:00:54Z`, so the rule
answers `07:00Z` — **fifty-nine minutes of slack that nobody picked**. If the rebuild ever finishes
at `07:10Z` the same rule answers `08:00Z`, and a registration standing at `07:00Z` is shown stale
by a node rather than by somebody remembering.

## Both zones, always

The Windows Task Scheduler registers in the machine's **local** time; the rebuild is measured in
**UTC**. Measured 2026-08-31 with `zoneinfo`, `America/Sao_Paulo` holds a single offset across all
of 2026 — `UTC-3`, no daylight change — so `07:00Z` is `04:00` local **this year**. That is a fact
with a date on it, not an arithmetic rule, and this module converts rather than subtracts three.

**This is the most repeated error in this loop**: clock fields stamped without reading a clock, a
view whose window slides on São Paulo while its rebuild is scheduled in UTC. Every value here
carries its zone because the ones that did not are the ones that went wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from zoneinfo import ZoneInfo

__all__ = ["AdmissibleStart", "earliest_admissible"]


class AdmissibleStart(NamedTuple):
    """The same instant, said twice, because the two readers are different.

    ``utc`` is what the comparison against the rebuild is made in; ``local`` is what goes into the
    scheduler. **Neither is derivable from the other without a zone**, which is why both are
    carried rather than one being recomputed at each use.
    """

    utc: datetime
    local: datetime

    @property
    def local_clock(self) -> str:
        """``HH:MM`` as the scheduler wants it — and it is the LOCAL one, by name."""
        return self.local.strftime("%H:%M")


def earliest_admissible(rebuild_finished: datetime, *, zone: ZoneInfo) -> AdmissibleStart:
    """The first whole hour **strictly after** ``rebuild_finished``.

    ``rebuild_finished`` must carry a zone. A naive datetime is refused rather than assumed to be
    UTC: assuming it is exactly how an instant three hours off gets written into a scheduler.

    Strictly after, and the word does work. A rebuild that finishes at `06:00:00.000` **on** the
    hour still yields `07:00`, because a run starting in the same second as the last write reads a
    table mid-replace. The margin this rule produces is never zero.
    """
    if rebuild_finished.tzinfo is None:
        message = "rebuild_finished carries no zone; refusing to assume one"
        raise ValueError(message)

    instant = rebuild_finished.astimezone(UTC)
    whole_hour = instant.replace(minute=0, second=0, microsecond=0)
    #: ``<=`` and not ``<``: landing exactly on the hour must still advance.
    while whole_hour <= instant:
        whole_hour += timedelta(hours=1)

    return AdmissibleStart(utc=whole_hour, local=whole_hour.astimezone(zone))
