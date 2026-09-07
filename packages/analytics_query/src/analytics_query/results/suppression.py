"""Minimum-aggregation suppression — T078 (FR-041; SC-028).

A cell whose contributing group size falls below the governed threshold is
**withheld with an explicit reason**. Never an absent row, never an empty
result, never a zero.

Each of those three alternatives is a lie of a different shape. An absent row
says the combination does not exist. An empty result says nothing matched. A
zero says the measured quantity was zero. All three are readable as facts about
the data, and all three are wrong — the truth is "this figure exists and you may
not see it", which is what ``RESULT_CELL_SUPPRESSED`` says.

**The threshold is never invented.** It comes from the governed ``QueryPolicy``
as external evidence supplied by the data owner (`D-16`). There is no default
here, and no fallback: a policy without one is unresolvable, so suppression
cannot run against a floor nobody approved.

**Values are never perturbed.** No rounding, no noise, no banding. A perturbed
figure is still a returned figure, and a caller cannot tell how far from the
truth it is — so this feature withholds instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.reason_codes import AnalyticsReasonCode
from ..contracts.result import ResultCell

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy

__all__ = ["suppress_cell", "suppress_row", "would_suppress"]


def would_suppress(group_size: int, policy: QueryPolicy) -> bool:
    """Whether a cell backed by ``group_size`` contributors must be withheld.

    Strictly below the threshold. A group exactly at the floor is releasable —
    the threshold is the smallest publishable size, not the smallest suppressed
    one, and being off by one here changes who is identifiable.
    """
    return group_size < policy.minimum_aggregation_threshold


def suppress_cell(cell: ResultCell, group_size: int, policy: QueryPolicy) -> ResultCell:
    """Return the cell, or a suppressed cell carrying its reason.

    The suppressed cell holds **no value at all** — not a rounded one, not a
    zero, not a placeholder. Its only content is the statement that it was
    withheld and why.
    """
    if not would_suppress(group_size, policy):
        return cell
    return ResultCell(
        value=None,
        suppressed=True,
        suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
    )


def suppress_row(
    row: tuple[ResultCell, ...],
    group_sizes: tuple[int, ...],
    policy: QueryPolicy,
) -> tuple[ResultCell, ...]:
    """Apply the threshold cell by cell across one row.

    ``group_sizes`` must align with ``row`` positionally. A mismatch raises
    rather than suppressing defensively or releasing optimistically: not knowing
    which figure a group size describes means not knowing what is safe to show.
    """
    if len(row) != len(group_sizes):
        raise ValueError(
            "group sizes do not align with the row; the contributing count for each "
            "cell must be known before any cell can be released"
        )
    return tuple(
        suppress_cell(cell, size, policy) for cell, size in zip(row, group_sizes, strict=True)
    )
