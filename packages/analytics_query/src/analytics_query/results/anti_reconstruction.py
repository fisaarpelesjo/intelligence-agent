"""Anti-reconstruction — T079 (FR-041; SC-029).

Suppressing the cell below the threshold is not enough. If a row shows four of
five cells plus a total, the fifth is a subtraction away — and the caller has
the withheld figure exactly, without the system ever having shown it.

So suppression **extends**: once any cell in a group is withheld, cells are
suppressed until no withheld figure can be recovered by arithmetic over what
remains visible. Concretely, a single suppressed cell alongside a visible total
forces a second suppression, because one unknown in one equation is solvable.

The rule is *at least two unknowns, or no total*. That is the smallest condition
under which the arithmetic is underdetermined, and choosing the second victim by
smallest contributing group means the extension takes the cell whose exposure
would matter most.

When nothing meaningful survives — every cell withheld — the result reports
``RESULT_FULLY_SUPPRESSED`` rather than returning a row of blanks. A table of
empty cells still communicates the shape of the cohort, and it invites the
reader to assume the figures were zero.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.reason_codes import AnalyticsReasonCode
from ..contracts.result import ResultCell

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy

__all__ = ["FullySuppressed", "extend_suppression", "is_reconstructible"]


class FullySuppressed(Exception):  # noqa: N818 - a governed refusal, not an error
    """Nothing meaningful survived suppression."""

    def __init__(self) -> None:
        self.code = AnalyticsReasonCode.RESULT_FULLY_SUPPRESSED
        super().__init__(f"{self.code.value}: no releasable figure remains")


def is_reconstructible(row: tuple[ResultCell, ...], *, total_visible: bool) -> bool:
    """Whether a withheld figure can be derived from what is still shown.

    One unknown plus a visible total is one equation in one variable. Two or
    more unknowns leave the system underdetermined, and no visible total leaves
    nothing to subtract from.
    """
    suppressed = sum(1 for cell in row if cell.suppressed)
    if suppressed == 0:
        return False
    return total_visible and suppressed == 1


def extend_suppression(
    row: tuple[ResultCell, ...],
    group_sizes: tuple[int, ...],
    policy: QueryPolicy,
    *,
    total_visible: bool,
) -> tuple[ResultCell, ...]:
    """Widen suppression until nothing withheld is recoverable.

    ``policy`` is taken so the extension cannot run without a governed
    threshold in force, even though the widening rule itself is arithmetic
    rather than threshold-driven — a caller holding no policy has no business
    deciding what is releasable.

    Raises ``FullySuppressed`` when the widening leaves nothing visible.
    """
    _ = policy.minimum_aggregation_threshold  # a governed floor must be in force

    if len(row) != len(group_sizes):
        raise ValueError("group sizes do not align with the row")

    working = list(row)
    if not is_reconstructible(tuple(working), total_visible=total_visible):
        return _refuse_if_empty(tuple(working))

    # Take the smallest visible group next: it is the cell whose exposure would
    # identify the fewest people, and therefore the one most worth hiding.
    candidates = [
        (size, index)
        for index, (cell, size) in enumerate(zip(working, group_sizes, strict=True))
        if not cell.suppressed
    ]
    if not candidates:
        return _refuse_if_empty(tuple(working))

    _, victim = min(candidates)
    working[victim] = ResultCell(
        value=None,
        suppressed=True,
        suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
    )
    return _refuse_if_empty(tuple(working))


def _refuse_if_empty(row: tuple[ResultCell, ...]) -> tuple[ResultCell, ...]:
    """A row of blanks is not a result.

    It still communicates the cohort's shape, and it reads as "the figures were
    zero" to anyone not looking closely.
    """
    if row and all(cell.suppressed for cell in row):
        raise FullySuppressed
    return row
