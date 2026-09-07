"""The comparable window — T103 (FR-066; SC-038).

**Taken from the verdict. Never recomputed, widened, narrowed, shifted or
substituted.**

There is no recomputation path to disable, because there is no computation. This
module reads what `001` stated and hands it on. That is the entire design, and
the reason it is a module at all is that "we just read it" is only true if there
is exactly one place where the reading happens — a second call site that derived
a window from the two sides' coverage would be the failure this task names, and
it would not look like a failure in review.

**Why deriving it would be wrong even when it agrees.** Two sources rarely cover
the same days, so a comparison narrows to the overlap. A window derived here from
the sides' coverage would be plausible and would usually match — and the times it
did not, the caller would be told the wrong basis for a number computed on a
different one. The reader has no way to detect that: both the window and the
figure look fine on their own.

**Absence refuses.** `001` stating no window for a comparison that needs one is
not an invitation to supply the requested range instead. The requested range is
precisely the thing the window exists to correct, so substituting it is the
widening this task forbids, wearing a default's clothes.

**Incompleteness refuses too.** `002`'s ``window_from_decision`` requires all four
parts — start, end, the reason and the sources — and refuses a partially stated
window rather than completing it. The reason is not decoration: a window without
its *why* reads as a choice somebody made rather than a constraint the data
imposed, which is the same disclosure defect stated one level down.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from analytics_query.contracts.comparable_window import ComparableWindow, window_from_decision

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.validation.decision import CatalogDecision

__all__ = ["window_for_comparison"]


def window_for_comparison(verdict: CatalogDecision) -> ComparableWindow:
    """The window `001` stated on this verdict, or refuse the comparison.

    ``verdict`` is the **permitted** verdict — `T101` has already established
    that the catalog allowed the comparison. Reading the window off a denied
    decision would be reading the qualification of an answer nobody is getting.

    `002` owns the reading itself: ``window_from_decision`` is the public
    contract function that already knows how a stated window is shaped and
    already refuses an incompletely stated one. Re-implementing that here would
    be a second reader of the same field, free to disagree with the first.

    Its refusal is re-raised in this feature's vocabulary — the one place a code
    is translated rather than passed through, and deliberately so. `002`'s
    ``RESULT_SHAPE_MISMATCH`` describes a *result* whose shape disagreed with its
    plan; nothing has executed here and there is no result to mis-shape. Passing
    that code up would name a stage the request never reached. The governed fact
    is the one this feature's namespace states: the comparison cannot be
    qualified, so the whole comparison refuses.

    The ``except`` is on ``ValueError`` rather than on `002`'s own
    ``ContractViolation``: that class lives in ``analytics_query.contracts._base``
    and the leading underscore puts it outside the public surface ADR 0010
    allows. `002`'s refusal *is* a ``ValueError``, so catching the base type
    catches it — the breadth is the boundary again, not carelessness.
    """
    try:
        stated = window_from_decision(verdict)
    except ValueError as exc:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "the governed comparable window is incompletely stated",
        ) from exc

    if stated is None:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "the verdict states no comparable window; the requested range is not a substitute",
        )

    return stated
