"""The three conditions of ADR 0035, each checkable and each on its own — T702 to T705.

`FR-062` of `004` says the system MUST originate no message on its own initiative.
**That requirement is not amended.** ADR 0035 supersedes it for one case, and the case
is three conditions that must all hold:

1. the finding is **prioritisable** — `006` placed it;
2. the channel is **already enabled** — this feature enables nothing;
3. the recipient **has accepted** — the DECLARED list, derived from the report's own
   key (OD-105, 2026-09-03: the same three the daily report reaches; the 2026-08-30
   wrong-key defect died here the same way it died in `008`).

## Why they are checked in this order, and why the order is not cosmetic

**The cheapest and most informative refusal comes first.** A finding that was not
placed is the answer to *should anything be said at all*, and asking about channels or
recipients before that would report a configuration problem when the truth is there
was nothing to report.

## Why each returns its own code

A caller that sees one code must know which condition stopped it. Three conditions
behind one refusal is a message that says *not today* without saying why, and every
one of the three is fixed by a different person doing a different thing.

## The channel condition READS THE RECORD, and that is `T703`

It used to be a parameter, and a parameter is **the caller telling this function what it
wants to hear**. The readiness record is the world. So `channel_is_enabled` asks
`004`'s own reader, which derives enablement from the records and cannot be overridden by
a file, a flag or an environment variable.

**A record that cannot be read REFUSES.** `004` raises rather than answering when a record
is missing -- *"a missing record is not permission"* -- and this module turns that into the
same refusal as *declared and not ready*, deliberately. The code claims one thing: **this
feature has no evidence the channel is enabled.** Absent evidence and negative evidence are
different facts, and neither is permission; the refusal's own message says which occurred,
so nothing is lost to a reader while the code stays honest about what it asserts.

**Not measuring is never passing**, and that is the whole reason the exception is caught
rather than allowed to escape: an unhandled `ReadinessMalformed` would reach a caller as a
crash, and a crash is not a governed refusal.

## What this module does NOT do

**It does not enable anything.** ADR 0035's second condition is that the channel is
*already* enabled; making it so is a different act with a different authorization, and
nothing here writes a readiness record.

**It does not send.** It answers whether sending is permitted. The send is `T714` and
is unreachable today, which the nodes state rather than skip.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from channel_integration.compliance.readiness import ReadinessMalformed, may_send_to
from channel_integration.contracts.descriptor import ChannelId

from ..contracts.reason_codes import DistributionReasonCode
from .recipient import NoAcceptedRecipient, recipients_from

__all__ = ["DISTRIBUTED_CHANNEL", "Permission", "channel_is_enabled", "may_distribute"]

#: The one channel this feature may originate on. His decision of 2026-08-27 covers his
#: own chat on Telegram and nothing else, so a second channel is not a configuration
#: value here -- it is a decision that does not exist.
DISTRIBUTED_CHANNEL = ChannelId.TELEGRAM


@dataclass(frozen=True, slots=True)
class Permission:
    """Whether a message may be originated, and — when not — exactly which condition said no.

    `refused_for` is `None` only when every condition held. The two fields cannot
    disagree: a permission that was granted while naming a refusal, or refused while
    naming none, is refused at construction.
    """

    permitted: bool
    refused_for: DistributionReasonCode | None
    #: A lista declarada, inteira. Era um ``recipient`` singular até OD-105 (2026-09-03)
    #: — o mesmo S-24 que a `008` já pagou: o singular é o que recusou o primeiro envio
    #: real a três. Vazia quando recusado.
    recipients: tuple[str, ...]

    def __post_init__(self) -> None:
        """**A refusal that cannot say what stopped it is the silence this stack refuses.**"""
        if self.permitted and self.refused_for is not None:
            raise ValueError(f"permitted and refused at once: {self.refused_for}")
        if not self.permitted and self.refused_for is None:
            raise ValueError(
                "a refusal must name the condition that failed; an unexplained no is the "
                "silence this feature exists to avoid"
            )
        if self.permitted and not self.recipients:
            raise ValueError("permitted with nobody to send to, which cannot be acted on")


def channel_is_enabled(channel: ChannelId = DISTRIBUTED_CHANNEL) -> bool:
    """Whether `channel` is enabled, **read from the readiness records**.

    `004` owns this question and answers it from the records alone. This function adds one
    thing: a record that cannot be read comes back as **not enabled** rather than as an
    exception escaping into a caller that asked a yes-or-no question.

    **It takes no override.** A parameter saying "treat it as enabled" is exactly what
    `T703` removed, and re-adding one under another name would restore the defect with a
    different spelling.
    """
    try:
        return may_send_to(channel)
    except ReadinessMalformed:
        return False


def may_distribute(
    *,
    finding_is_prioritisable: bool,
    environment: Mapping[str, str],
) -> Permission:
    """Answer the three conditions, in the order the module docstring gives.

    `finding_is_prioritisable` stays a parameter because `006` owns it: a function here
    that decided whether a finding was placed would be this feature answering a question
    that is not its own. **The channel is not a parameter**, because the readiness record
    already answers it and a caller passing `True` would be authorising itself.
    """
    if not finding_is_prioritisable:
        return Permission(
            permitted=False,
            refused_for=DistributionReasonCode.DISTRIBUTION_FINDING_NOT_PRIORITISABLE,
            recipients=(),
        )
    if not channel_is_enabled():
        return Permission(
            permitted=False,
            refused_for=DistributionReasonCode.DISTRIBUTION_CHANNEL_NOT_ENABLED,
            recipients=(),
        )
    try:
        recipients = recipients_from(environment)
    except NoAcceptedRecipient as refused:
        return Permission(permitted=False, refused_for=refused.code, recipients=())
    return Permission(permitted=True, refused_for=None, recipients=recipients)
