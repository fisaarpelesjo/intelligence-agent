"""The canonical refusal contract — Phase B, required by T041 (FR-001, FR-045).

`canonical-contracts.md` §1 names four canonical contracts: inbound message, outbound
response, **refusal** and delivery event. Phase A built three of them; this is the fourth,
and it arrives now because `T041`'s conversion operation is **total** — every input yields
an envelope or a refusal — and totality needs a refusal type to be expressible.

Two projections, and the split is the disclosure boundary:

* :meth:`ChannelRefusal.sender_text` — the governed pt-BR wording, and nothing else. This
  is what a channel may transmit.
* ``detail_class`` — the operator-facing classification of a **collapsed** refusal
  (ADR 0018). It travels so the audit emitter can record which member of a collapsed set
  failed, and it is **never** part of the sender projection.

A refusal is a governed **state**, not an error: it names no exception, no stack and no
trace (`FR-045`), and it carries no payload, no header, no signature and no identity.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from ..messages.registry import message_for
from ._base import ChannelModel, ChannelViolation
from .audit import ChannelStage, DetailClass
from .reason_codes import ChannelReasonCode, Outcome, channel_outcome_for

__all__ = ["ChannelRefusal", "refusal_from_violation"]


class ChannelRefusal(ChannelModel):
    """One governed refusal, at one stage, with its stored wording."""

    code: ChannelReasonCode
    #: Where the message stopped. The last stage a trail shows.
    stage: ChannelStage
    #: The stored pt-BR wording for ``code``, resolved from governed content. **Never**
    #: generated, paraphrased or translated here.
    message_pt_br: str = Field(min_length=1)
    #: Operator-facing only. Excluded from :meth:`sender_text` by construction.
    detail_class: DetailClass = DetailClass.NONE

    @field_validator("code")
    @classmethod
    def _only_a_denying_code_refuses(cls, value: ChannelReasonCode) -> ChannelReasonCode:
        """A refusal carries a DENY code.

        An ALLOW code inside a refusal would let a permitted outcome be reported as a
        refusal, or the reverse — the exact confusion the outcome map exists to prevent.
        """
        if channel_outcome_for(value) is not Outcome.DENY:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
                f"{value.value} is not a denying code and cannot express a refusal",
            )
        return value

    def sender_text(self) -> str:
        """What a channel may transmit: the governed wording, alone.

        A method rather than a field, so the sender projection cannot be widened by adding
        a field somewhere else. Everything a sender is not entitled to — the detail class,
        the stage, the internal code taxonomy — stays out by construction.
        """
        return self.message_pt_br


def refusal_from_violation(
    violation: ChannelViolation,
    stage: ChannelStage,
    detail_class: DetailClass = DetailClass.NONE,
    **arguments: str,
) -> ChannelRefusal:
    """Turn a raised :class:`ChannelViolation` into the canonical refusal.

    The wording comes from the governed registry keyed by the violation's code, so a
    refusal's text is never assembled from the violation's developer-facing ``detail``.
    That detail may name which envelope field was absent or which signature mode failed; it
    belongs in ``detail_class`` and in the audit trail, never in a response
    (`contracts/inbound-conversion.md` §6).
    """
    return ChannelRefusal(
        code=violation.code,
        stage=stage,
        message_pt_br=message_for(violation.code, **arguments),
        detail_class=detail_class,
    )
