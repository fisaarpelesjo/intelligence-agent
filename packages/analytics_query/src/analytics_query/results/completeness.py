"""Empty versus withheld — T092 (FR-040; SC-028).

Two states that look identical on a screen and mean opposite things:

* **Empty** — the query ran, the data was read, and nothing matched. The honest
  answer is "none".
* **Withheld** — figures exist and are not being shown, because a governed rule
  says so.

Rendering both as an empty table is the failure this module exists to prevent.
A reader seeing no rows concludes there were none, acts on "zero installs in
Brazil last month", and is wrong in a way nothing in the response would reveal.

So the two carry **different responses**: an empty result is a result, with
``Completeness.EMPTY`` and no reason code; a withheld one is a refusal or a
caveated result carrying ``RESULT_CELL_SUPPRESSED`` or
``RESULT_FULLY_SUPPRESSED``. A caller can always tell which they received, and
the distinction survives serialisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ..contracts.reason_codes import AnalyticsReasonCode
from ..contracts.result import Completeness

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.result import AnalyticsResult

__all__ = ["ResultDisposition", "ResultKind", "classify_result"]


class ResultKind(StrEnum):
    """What the caller is actually holding."""

    #: Rows were returned and every cell is visible.
    POPULATED = "populated"
    #: The query ran and nothing matched. A genuine "none".
    EMPTY = "empty"
    #: Rows exist but at least one cell is withheld by a governed rule.
    PARTIALLY_WITHHELD = "partially_withheld"
    #: Every cell is withheld. Not an empty result.
    FULLY_WITHHELD = "fully_withheld"


@dataclass(frozen=True, slots=True)
class ResultDisposition:
    """The kind, and the governed code that explains it where one applies."""

    kind: ResultKind
    reason_code: AnalyticsReasonCode | None = None

    @property
    def is_genuinely_empty(self) -> bool:
        """True only for a real absence of data.

        Deliberately narrow: a fully withheld result is *not* empty, and this
        property is what downstream code should branch on rather than on a row
        count.
        """
        return self.kind is ResultKind.EMPTY


def classify_result(result: AnalyticsResult) -> ResultDisposition:
    """Distinguish a genuine absence from a governed withholding.

    Reads the cells rather than the row count. A row count alone cannot tell the
    two apart — a fully suppressed row still has a row — which is precisely how
    the two states get confused.
    """
    if result.completeness is Completeness.EMPTY or not result.rows:
        return ResultDisposition(kind=ResultKind.EMPTY)

    cells = list(result.all_cells())
    suppressed = [cell for cell in cells if cell.suppressed]

    if not suppressed:
        return ResultDisposition(kind=ResultKind.POPULATED)

    if len(suppressed) == len(cells):
        return ResultDisposition(
            kind=ResultKind.FULLY_WITHHELD,
            reason_code=AnalyticsReasonCode.RESULT_FULLY_SUPPRESSED,
        )

    return ResultDisposition(
        kind=ResultKind.PARTIALLY_WITHHELD,
        reason_code=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
    )
