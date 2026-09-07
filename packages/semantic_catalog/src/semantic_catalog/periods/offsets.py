"""Per-source offset and materiality — T064 (FR-020, FR-027).

A source's reporting zone is **preserved, never normalised**. The catalog cuts
answers in ``America/Sao_Paulo``; a store that closes its day in
``America/Los_Angeles`` still closes it there, and the consequence is that one
canonical day draws on **two** of that store's reporting days.

That is a real limitation on the number, not a rounding detail, so it is
surfaced as ``TIMEZONE_OFFSET_MATERIAL`` rather than absorbed. Absorbing it would
mean the catalog quietly decided which of the store's two days to attribute the
canonical day to — a decision nobody made and nobody could see.

**Materiality is a non-zero offset**, computed per date through the IANA
database. Not a threshold: any offset at all shifts the day boundary, so any
offset at all changes which events land in the canonical day. A zone that merely
*shares* the canonical offset today may diverge on a DST transition, which is
exactly why the offset is recomputed per date instead of read once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from ..contracts.source import Source
from .canonical import CANONICAL_TIMEZONE, canonical_zone, local_midnight

__all__ = ["SourceOffset", "material_offsets", "offset_for", "offsets_for"]


@dataclass(frozen=True, slots=True)
class SourceOffset:
    """How far a source's reporting day sits from the canonical day."""

    source: str
    reporting_timezone: str
    offset: timedelta
    material: bool
    on: date

    @property
    def hours(self) -> float:
        return self.offset.total_seconds() / 3600.0

    def describe(self) -> str:
        """Human-facing summary. Identifiers and a duration, never a value."""
        return (
            f"{self.source} reporta em {self.reporting_timezone}, "
            f"{self.hours:+.0f}h em relação a {CANONICAL_TIMEZONE}"
        )


def offset_for(source: Source, *, on: date) -> SourceOffset:
    """The offset between ``source``'s reporting day and the canonical day.

    Computed from the two zones' UTC offsets **on that date**, so a transition in
    either zone is reflected rather than assumed away.
    """
    canonical = canonical_zone()
    reporting = ZoneInfo(source.reporting_timezone)

    canonical_start = local_midnight(on, canonical)
    reporting_start = local_midnight(on, reporting)
    offset = reporting_start.utcoffset() or timedelta()
    canonical_offset = canonical_start.utcoffset() or timedelta()
    delta = offset - canonical_offset

    return SourceOffset(
        source=source.id,
        reporting_timezone=source.reporting_timezone,
        offset=delta,
        material=delta != timedelta(),
        on=on,
    )


def offsets_for(
    sources: dict[str, Source], names: tuple[str, ...], *, on: date
) -> tuple[SourceOffset, ...]:
    """Offsets for the named sources, sorted for a stable answer."""
    return tuple(offset_for(sources[name], on=on) for name in sorted(names) if name in sources)


def material_offsets(offsets: tuple[SourceOffset, ...]) -> tuple[SourceOffset, ...]:
    """Only those that shift the canonical day. These become limitations."""
    return tuple(o for o in offsets if o.material)
