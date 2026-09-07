"""The refusal type and the frozen model base — `T801`.

A refusal here is a **governed outcome**, not a crash. It carries a
:class:`~daily_reporting.contracts.reason_codes.ReportReasonCode` so a caller learns
*which* condition stopped it, and the two products' codes never collapse into one.
"""

from __future__ import annotations

from .reason_codes import ReportReasonCode

__all__ = ["ReportRefusal"]


class ReportRefusal(ValueError):  # noqa: N818 - a governed refusal, not an error
    """Raised when this package refuses to summarise or to raise an alert.

    A distinct type so a caller can tell *"this feature refused"* from *"something
    broke"*, which are different problems with different fixes. **The code is carried
    on the exception rather than parsed out of its message**, because a message is
    prose and prose is what this feature exists not to depend on.
    """

    def __init__(self, code: ReportReasonCode, detail: str) -> None:
        self.code: ReportReasonCode = code
        self.detail: str = detail
        super().__init__(f"{code.value}: {detail}")
