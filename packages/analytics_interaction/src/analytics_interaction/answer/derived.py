"""Calculated-comparison attribution — T125 (FR-035; SC-019).

**A reader can trace a difference to the numbers behind it.**

A comparison answer carries three claims, not one: the two factual results and
the difference derived from them. The derived claim names both operands in
``derived_from`` and carries the governed ``ComparisonBasis`` — the formula, the
window, and the reason that window was chosen.

Without the two factual claims beside it, a difference is an assertion the reader
has to trust. With them, it is checkable: the operands are there, the formula is
named, and the window says which days both sides were read over.

## The basis is carried, never recomputed

``ComparisonBasis`` comes from the governed comparison — the window `001` stated
and `002` converted, and the formula `D-18` declared. `FR-066` forbids
recomputing, widening, narrowing, shifting or substituting the window, and there
is no derivation here to disable because there is no computation.

``chosen_because`` in particular is upstream governed wording. Composing one
would tell the reader a basis nobody governed, and it would look authoritative.

## Only a complete comparison produces one

:func:`comparison_claims` takes a ``GovernedComparison``, which has no partial
state: it carries exactly two sides or it does not exist. So "release the side
that worked" is not a mistake reachable from here — a half comparison is not a
value this function can be handed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import build
from ..contracts.answer import ComparisonBasis
from .claims import calculated, cell_for, factual

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts._base import LocalizedRef
    from ..contracts.answer import AnswerClaim
    from ..contracts.comparison import GovernedComparison

__all__ = [
    "basis_for",
    "comparison_claims",
]


def basis_for(comparison: GovernedComparison) -> ComparisonBasis:
    """The governed basis, assembled from what the comparison already states.

    Every field is read off the comparison: the formula it was computed under,
    the window taken from the verdict, and the window's own ``reason``. Nothing
    is derived, and nothing is worded here.
    """
    return build(
        ComparisonBasis,
        formula=comparison.formula,
        window_start=comparison.window.start,
        window_end=comparison.window.end,
        chosen_because=comparison.window.reason,
    )


def comparison_claims(
    comparison: GovernedComparison,
    *,
    subjects: tuple[str, str],
    difference_subject: str,
    factual_message: LocalizedRef,
    difference_message: LocalizedRef,
) -> tuple[AnswerClaim, AnswerClaim, AnswerClaim]:
    """Three claims: both factual results, then the difference derived from them.

    Returned in that order deliberately. The operands precede the figure derived
    from them, so a renderer that presents the tuple in order presents the
    evidence before the conclusion — and one that reorders is still traceable,
    because ``derived_from`` names the subjects rather than positions.

    ``subjects`` are the two factual claims' subjects, and the same two strings
    become the derived claim's ``derived_from``. Passing them once means the
    reference cannot drift from what it references: a ``derived_from`` naming a
    subject no claim carries would be untraceable, and here it is unconstructible.

    The **units** come from different places on purpose. Each factual claim takes
    the unit `002` declared on its own metric column; the difference takes the
    unit `D-18`'s formula declared. A ratio's unit is neither operand's, which is
    why the formula states it.
    """
    primary_side, baseline_side = comparison.sides
    primary_subject, baseline_subject = subjects

    primary_unit = next(column.unit for column in primary_side.result.columns if column.is_metric)
    baseline_unit = next(column.unit for column in baseline_side.result.columns if column.is_metric)

    return (
        factual(
            subject=primary_subject,
            cell=cell_for(primary_side.result),
            unit=primary_unit,
            message=factual_message,
        ),
        factual(
            subject=baseline_subject,
            cell=cell_for(baseline_side.result),
            unit=baseline_unit,
            message=factual_message,
        ),
        calculated(
            subject=difference_subject,
            value=comparison.difference.value,
            unit=comparison.difference.unit,
            message=difference_message,
            derived_from=(primary_subject, baseline_subject),
            basis=basis_for(comparison),
        ),
    )
