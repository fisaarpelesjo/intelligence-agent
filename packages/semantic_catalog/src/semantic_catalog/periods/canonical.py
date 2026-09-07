"""Canonical period semantics — T061 (FR-020, FR-027).

Every requested period is expressed in **one** business time zone,
``America/Sao_Paulo``, and it is resolved through the IANA database via
``zoneinfo`` — **never a fixed offset**.

That is not pedantry. The canonical zone observed daylight saving until 2019, so
a range crossing a transition contains a 23-hour day, a 25-hour day, and one
local hour that occurs twice. A hard-coded ``-03:00`` gets every one of those
wrong, and gets them wrong quietly: the arithmetic still returns a number.

Three period states, and the distinction between the last two matters:

``complete``
    The whole range lies in the past. Every day in it has finished.

``partial``
    The range includes today, which is still forming. A number for it is real
    but not final, and comparing it against a finished period manufactures a
    decline (FR-025).

``outside_coverage``
    The range starts after the evaluation date. Nothing has happened yet.

``partial_cutoff`` is what makes an equivalent-partial comparison legal: two
periods cut at the same local time are comparable, and the cutoff must be named
in the answer (FR-026).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

__all__ = [
    "CANONICAL_TIMEZONE",
    "CanonicalPeriod",
    "PeriodCompleteness",
    "canonical_period",
    "canonical_zone",
    "day_length",
    "local_midnight",
]

#: The one business time zone. Declared here, referenced everywhere else.
CANONICAL_TIMEZONE = "America/Sao_Paulo"


def canonical_zone() -> ZoneInfo:
    """The canonical zone from the IANA database.

    A function rather than a module constant so the lookup fails loudly at the
    call site if the platform has no tz database, instead of at import time in
    whatever unrelated module happened to import this one first.
    """
    return ZoneInfo(CANONICAL_TIMEZONE)


class PeriodCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    OUTSIDE_COVERAGE = "outside_coverage"


def local_midnight(day: date, zone: ZoneInfo | None = None) -> datetime:
    """Start of ``day`` in the given zone, DST-aware.

    On a spring-forward day local midnight may not exist as a wall clock time in
    some zones; ``zoneinfo`` resolves that rather than silently producing an
    instant an hour out.
    """
    return datetime.combine(day, time.min, tzinfo=zone or canonical_zone())


def day_length(day: date, zone: ZoneInfo | None = None) -> timedelta:
    """Real elapsed length of ``day``. 23 or 25 hours across a DST transition.

    The two midnights are converted to UTC before subtracting. Subtracting two
    aware datetimes that share a ``tzinfo`` gives the **wall-clock** difference,
    which is 24 hours on every day including the two each year that are not —
    the same wrong answer a fixed ``-03:00`` offset produces, arrived at by a
    different route.
    """
    tz = zone or canonical_zone()
    start = local_midnight(day, tz).astimezone(UTC)
    end = local_midnight(day + timedelta(days=1), tz).astimezone(UTC)
    return end - start


@dataclass(frozen=True, slots=True)
class CanonicalPeriod:
    """A requested range, resolved in the canonical zone (data-model §4.1)."""

    requested_start: date
    requested_end: date
    canonical_timezone: str
    completeness: PeriodCompleteness
    partial_cutoff: time | None = None

    @property
    def is_complete(self) -> bool:
        return self.completeness is PeriodCompleteness.COMPLETE

    @property
    def is_partial(self) -> bool:
        return self.completeness is PeriodCompleteness.PARTIAL

    @property
    def days(self) -> int:
        """Inclusive day count. Correct across DST because it counts dates."""
        return (self.requested_end - self.requested_start).days + 1

    def elapsed(self) -> timedelta:
        """Real elapsed time across the range, DST transitions included.

        Converted to UTC before subtracting, for the reason in :func:`day_length`.
        """
        zone = canonical_zone()
        start = local_midnight(self.requested_start, zone).astimezone(UTC)
        end = local_midnight(self.requested_end + timedelta(days=1), zone).astimezone(UTC)
        return end - start

    def contains(self, day: date) -> bool:
        return self.requested_start <= day <= self.requested_end


def canonical_period(
    start: date,
    end: date,
    *,
    on: date,
    cutoff: time | None = None,
) -> CanonicalPeriod:
    """Resolve a requested range against the evaluation date.

    ``on`` is passed in rather than read from the clock: a decision must be
    reproducible, and a period whose completeness depends on when the test ran
    is not.
    """
    if end < start:
        raise ValueError(f"period ends {end} before it starts {start}")

    if start > on:
        completeness = PeriodCompleteness.OUTSIDE_COVERAGE
    elif end >= on:
        completeness = PeriodCompleteness.PARTIAL
    else:
        completeness = PeriodCompleteness.COMPLETE

    return CanonicalPeriod(
        requested_start=start,
        requested_end=end,
        canonical_timezone=CANONICAL_TIMEZONE,
        completeness=completeness,
        partial_cutoff=cutoff if completeness is PeriodCompleteness.PARTIAL else None,
    )
