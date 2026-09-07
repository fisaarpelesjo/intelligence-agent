"""Steps 2 and 3 — verification and replay tolerance — T037 (ADR 0020; FR-009 — FR-012, FR-015).

**Scheme from the descriptor, never from the payload.** The registry below maps a scheme name
to its implementation; `ChannelDescriptor.verification_scheme` selects one. A payload naming
its own scheme is refused as an unknown envelope field long before this, and there is no
parameter here through which one could arrive.

**Verification runs over the received bytes.** `raw.body`, never a re-serialised parse.

**The instant is a parameter.** No clock is read on this path, so the replay window is
reproducible and testable without freezing time (`R-5`). The governed tolerance comes from
`D-26`; it is not defaulted, and while `D-26` is undeclared the caller cannot even construct
the bounds this function requires.

**Two absences refuse rather than degrade** (`FR-015`):

* no material — ``CHANNEL_VERIFICATION_UNAVAILABLE``. Every channel is in this state today,
  because `D-22` to `D-25` are undeclared;
* no scheme registered under the descriptor's name — the same code. A descriptor naming a
  scheme nobody implemented is a configuration defect, and processing the message anyway
  would be verification by omission.

**A scheme that provides no signed timestamp cannot have its replay window evaluated**, and
that limit is stated rather than simulated. Inventing a timestamp from the receiving clock
would make any replayed payload look fresh, which is worse than admitting the gap: WhatsApp
and Telegram are in this position, and it is `D-22` / `D-24` content to decide what
compensates.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..contracts._base import ChannelViolation
from ..contracts.audit import DetailClass
from ..contracts.descriptor import ChannelDescriptor, ChannelId
from ..contracts.raw import RawChannelRequest
from ..contracts.reason_codes import ChannelReasonCode
from ..governance.bounds import TransportBounds
from .schemes import VerificationMaterial, VerificationScheme
from .schemes.generic import GenericWebhookScheme
from .schemes.slack import SlackScheme
from .schemes.telegram import TelegramScheme
from .schemes.whatsapp import WhatsAppScheme

__all__ = [
    "EXPECTED_SCHEME",
    "SCHEMES",
    "VerificationFailure",
    "scheme_for",
    "verify_authenticity",
]

#: Name to implementation. Named entries rather than discovery, so a module appearing in the
#: package cannot become a verification scheme without a descriptor pointing at it.
SCHEMES: Mapping[str, VerificationScheme] = {
    scheme.name: scheme
    for scheme in (WhatsAppScheme(), SlackScheme(), TelegramScheme(), GenericWebhookScheme())
}

#: Which scheme each channel is expected to name. A descriptor pointing elsewhere is a
#: defect: it would let one channel be verified under another's rules.
#: The canonical channel-to-scheme map. **Public since 2026-08-28**: the readiness module
#: asks it whether a channel's scheme evaluates an instant, which is the inbound half of
#: the key `OD-20-A` split. It was private and read through the underscore for one commit;
#: reaching around a name that says "mine" is the boundary crossing this repository refuses
#: elsewhere, so the name changed rather than the reach.
EXPECTED_SCHEME: Mapping[ChannelId, str] = {
    ChannelId.WHATSAPP: WhatsAppScheme.name,
    ChannelId.SLACK: SlackScheme.name,
    ChannelId.TELEGRAM: TelegramScheme.name,
    ChannelId.GENERIC_WEBHOOK: GenericWebhookScheme.name,
}


class VerificationFailure(ChannelViolation):
    """A refusal that also carries the operator-facing detail class.

    The governed code is collapsed for the sender (ADR 0018); the class is what an operator
    reads in the audit trail. Carrying it on the exception is what lets the conversion
    operation put it in the event without re-deriving it — and without ever returning it.
    """

    def __init__(self, code: ChannelReasonCode, detail: str, detail_class: DetailClass) -> None:
        super().__init__(code, detail)
        self.detail_class = detail_class


def scheme_for(descriptor: ChannelDescriptor) -> VerificationScheme:
    """The scheme the descriptor names, or refuse.

    Also asserts the descriptor names the scheme its channel is expected to use: a
    cross-wired descriptor would verify a WhatsApp payload under Slack's rules, which is the
    "valid for a different channel" case the collapsed code covers.
    """
    expected = EXPECTED_SCHEME[descriptor.channel]
    if descriptor.verification_scheme != expected:
        raise VerificationFailure(
            ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE,
            f"{descriptor.channel.value} must name {expected}",
            DetailClass.SIGNATURE_WRONG_CHANNEL,
        )
    scheme = SCHEMES.get(descriptor.verification_scheme)
    if scheme is None:
        raise VerificationFailure(
            ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE,
            "the descriptor names no implemented scheme",
            DetailClass.NONE,
        )
    return scheme


def verify_authenticity(
    raw: RawChannelRequest,
    descriptor: ChannelDescriptor,
    material: VerificationMaterial | None,
    bounds: TransportBounds,
    at: datetime,
) -> None:
    """Verify ``raw``, then evaluate the replay window. Returns nothing, or refuses.

    Nothing is returned because there is nothing to say: verification either happened or the
    message is refused. A boolean return would invite a caller to ignore it.
    """
    if material is None:
        raise VerificationFailure(
            ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE,
            f"no verification material for {descriptor.channel.value}",
            DetailClass.NONE,
        )

    scheme = scheme_for(descriptor)
    outcome = scheme.verify(raw.body, raw.headers, material)
    if not outcome.ok:
        raise VerificationFailure(
            ChannelReasonCode.CHANNEL_SIGNATURE_INVALID,
            "authenticity could not be confirmed",
            outcome.detail,
        )

    if not scheme.provides_signed_timestamp:
        # No signed timestamp exists, so no window is evaluable. Stated, not simulated.
        return

    signed = scheme.signed_timestamp(raw.headers)
    if signed is None:
        raise VerificationFailure(
            ChannelReasonCode.CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE,
            "the scheme signs a timestamp and none was presented",
            DetailClass.NONE,
        )
    skew = abs(int(at.timestamp()) - signed)
    if skew > bounds.replay_tolerance_seconds:
        raise VerificationFailure(
            ChannelReasonCode.CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE,
            "the signed timestamp is outside the governed tolerance",
            DetailClass.NONE,
        )
