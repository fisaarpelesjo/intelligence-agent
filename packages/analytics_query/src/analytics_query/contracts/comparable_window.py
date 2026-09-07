"""Comparable-window reporting — T095 (FR-044; SC-018).

Every cross-source comparison states the window it used **and why that window
was chosen**. Both come from the upstream decision, and neither is recomputed
here.

The "why" matters as much as the window. Two sources rarely cover the same
period exactly, so a comparison silently narrows to the overlap — and a reader
who sees only the figures cannot tell whether they are comparing January to
January or January to three weeks of January. Stating the window without the
reason is nearly as bad: it looks like a choice someone made rather than a
constraint the data imposed.

**Recomputation is the failure mode.** Deriving the window here from the two
sources' coverage would produce something plausible that occasionally differs
from what `001` actually validated — and the caller would be told the wrong
basis for a number that was computed on a different one.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from ._base import ContractViolation, QueryModel
from .reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.validation.decision import CatalogDecision

__all__ = ["ComparableWindow", "window_from_decision"]


class ComparableWindow(QueryModel):
    """The window a comparison actually used, and the reason for it."""

    start: date
    end: date
    #: Why this window and not the requested one. Taken from the upstream
    #: decision verbatim — never composed here.
    reason: str = Field(min_length=1)
    #: The sources the window was narrowed to accommodate.
    sources: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _the_window_is_ordered(self) -> ComparableWindow:
        if self.end < self.start:
            raise ContractViolation(
                AnalyticsReasonCode.DATE_RANGE_INVALID,
                "the comparable window ends before it starts",
            )
        return self


#: What the upstream decision may call the window's reason, newest first.
#: ``chosen_because`` is `001`'s own name for it — the one its coverage gate has
#: always used and, since ADR 0016, the one its published decision carries. The
#: other two predate that and are kept so no consumer of an older shape breaks.
#:
#: This is a widening of what can be **read**, never of what is accepted: all
#: four parts are still required below, and a window stating none of these three
#: is still refused.
REASON_ATTRIBUTES: tuple[str, ...] = ("chosen_because", "reason", "rationale")


def _stated_reason(stated: object) -> str | None:
    """The reason the upstream decision gave, under whichever name it used.

    Returns ``None`` when it gave none — which the caller turns into a refusal
    rather than into a composed sentence. Nothing here defaults, derives or
    summarises: the reason is governed wording and this feature only carries it.
    """
    for attribute in REASON_ATTRIBUTES:
        value = getattr(stated, attribute, None)
        if value:
            return str(value)
    return None


def window_from_decision(decision: CatalogDecision) -> ComparableWindow | None:
    """Read the comparable window off the upstream decision.

    Returns ``None`` when the decision states none — a single-source request has
    no comparison to qualify. ``None`` is deliberately not an empty window: an
    empty window would assert that a comparison happened over no days.

    Nothing here derives a window. If `001` stated one, it is reported as given;
    if it did not, none is reported.
    """
    stated = getattr(decision, "comparable_window", None)
    if stated is None:
        return None

    start = getattr(stated, "start", None)
    end = getattr(stated, "end", None)
    reason = _stated_reason(stated)
    sources = tuple(getattr(stated, "sources", ()) or ())

    if start is None or end is None or not reason or not sources:
        # A window the upstream decision could not fully describe is not a
        # window this feature completes on its guess.
        raise ContractViolation(
            AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
            "the upstream comparable window is incompletely stated",
        )

    return ComparableWindow(start=start, end=end, reason=str(reason), sources=sources)
