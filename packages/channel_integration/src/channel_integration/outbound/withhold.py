"""Withholding, as a governed outcome — T075 (ADR 0022; FR-049, FR-050; SC-020, SC-065).

Two codes, and the difference between them is which side could not carry the payload:

* ``CHANNEL_RESPONSE_NOT_REPRESENTABLE`` — **rendering** could not produce a representation with
  every
  element intact. The channel's form is the limit.
* ``CHANNEL_OUTBOUND_WITHHELD`` — a representation existed and the **preservation gate** refused
  it, or
  a later step could not deliver it whole. Something diverged after rendering.

Both mean nothing was sent. Keeping them distinct is what lets an operator tell "this channel cannot
express this answer" from "this rendering changed the answer", which are different problems with
different owners.

**No truncation path exists anywhere in this package**, and that is asserted rather than promised
(`T093`, `SC-065`). The temptation this module removes is the small one: a helper that trims to fit,
called from one place, is how a governed answer becomes a partial answer. So there is no trimming
function to call — the only outcome available when something does not fit is this one.

A withheld response is **not** an error. It carries no exception, no stack and no provider text,
and it is reported to the sender through the same governed wording registry as any other refusal.
"""

from __future__ import annotations

from ..contracts._base import ChannelViolation
from ..contracts.audit import ChannelStage, DetailClass
from ..contracts.reason_codes import ChannelReasonCode
from ..contracts.refusal import ChannelRefusal, refusal_from_violation

__all__ = [
    "NotRepresentable",
    "WithheldAfterRendering",
    "withheld",
]


class NotRepresentable(ChannelViolation):
    """Rendering could not carry the payload intact. Raised, then collapsed into a refusal."""

    def __init__(self, detail: str) -> None:
        super().__init__(ChannelReasonCode.CHANNEL_RESPONSE_NOT_REPRESENTABLE, detail)


class WithheldAfterRendering(ChannelViolation):
    """A representation existed and was refused after the fact.

    Separate from :class:`NotRepresentable` because the two name different failures: the channel's
    form versus a divergence introduced between rendering and sending.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(ChannelReasonCode.CHANNEL_OUTBOUND_WITHHELD, detail)


def withheld(
    violation: ChannelViolation,
    stage: ChannelStage = ChannelStage.RENDERED,
    detail_class: DetailClass = DetailClass.NONE,
) -> ChannelRefusal:
    """The governed refusal for ``violation``, recorded at the stage it happened.

    ``RENDERED`` by default because that is where both withhold conditions are decided. A
    caller withholding at another stage passes it explicitly rather than letting a default
    silently misfile the event — the last stage in a trail is how "where did this stop?" is
    answered.
    """
    return refusal_from_violation(violation, stage, detail_class)
