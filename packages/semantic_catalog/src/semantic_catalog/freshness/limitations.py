"""Outage and restatement limitations — T071 (FR-028).

Two authored facts about a source, surfaced as limitations on any period they
touch.

**An outage** is a window in which the source produced no usable data. A number
covering it is not wrong so much as thin, and the reader cannot tell without
being told.

**A restatement is not a definition change**, and conflating the two is the
error this module exists to prevent. A restatement means the *figures* moved
under an unchanged definition — the store republished last month. A definition
change means the metric's *meaning* moved. As-of resolution (FR-034) applies to
definition changes only; a restatement produces a new data revision and updates
the figures for the periods it touches. Treating a restatement as a definition
change would fork the metric's history for a correction; treating a definition
change as a restatement would silently rewrite what past answers meant.

``PERIOD_RESTATED`` attaches to **every** touched period, not only the most
recent one. A reader comparing two quarters needs to know that one of them moved
after it was first published.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from ..contracts.reason_codes import ReasonCode
from ..contracts.source import Source
from ..periods.canonical import CanonicalPeriod

__all__ = ["SourceLimitation", "limitations_for", "restatement_limitations"]


@dataclass(frozen=True, slots=True)
class SourceLimitation:
    """One authored fact that qualifies an answer for this period."""

    code: ReasonCode
    source: str
    applies_from: date
    applies_to: date
    reason_pt_br: str

    def describe(self) -> str:
        return f"{self.source} {self.applies_from}..{self.applies_to}: {self.reason_pt_br}"


def _overlaps(period: CanonicalPeriod, start: date, end: date) -> bool:
    return start <= period.requested_end and end >= period.requested_start


def restatement_limitations(source: Source, period: CanonicalPeriod) -> Iterable[SourceLimitation]:
    """``PERIOD_RESTATED`` for every restatement touching the period."""
    for restatement in source.restatements:
        if _overlaps(period, restatement.affects_from, restatement.affects_to):
            yield SourceLimitation(
                code=ReasonCode.PERIOD_RESTATED,
                source=source.id,
                applies_from=restatement.affects_from,
                applies_to=restatement.affects_to,
                reason_pt_br=restatement.reason,
            )


def _outage_limitations(source: Source, period: CanonicalPeriod) -> Iterable[SourceLimitation]:
    """Outages overlapping the period.

    Reported under ``SOURCE_STATE_PARTIAL``: a window with no usable data is a
    completeness fact about the answer, which is what that code names. It is
    attached here as a limitation, and whether it *denies* is Gate 8's call —
    an authored outage and an observed partial load are different evidence.
    """
    for outage in source.outages:
        if _overlaps(period, outage.from_date, outage.to_date):
            yield SourceLimitation(
                code=ReasonCode.SOURCE_STATE_PARTIAL,
                source=source.id,
                applies_from=outage.from_date,
                applies_to=outage.to_date,
                reason_pt_br=outage.reason,
            )


def limitations_for(
    sources: Mapping[str, Source],
    source_ids: tuple[str, ...],
    period: CanonicalPeriod,
) -> tuple[SourceLimitation, ...]:
    """Every outage and restatement limitation for the named sources.

    Sorted for a stable answer: the same request must produce the same
    limitations in the same order, or two identical decisions would differ.
    """
    collected: list[SourceLimitation] = []
    for source_id in sorted(set(source_ids)):
        source = sources.get(source_id)
        if source is None:
            continue
        collected.extend(_outage_limitations(source, period))
        collected.extend(restatement_limitations(source, period))
    return tuple(
        sorted(collected, key=lambda limitation: (limitation.source, limitation.applies_from))
    )
