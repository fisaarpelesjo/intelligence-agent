"""Canonical channel contracts — Phase A (T004 — T013).

Channel-independent by construction: no provider identifier, header, token, cursor,
SDK object or protocol artifact appears in any model here (`FR-008`). Every model is
frozen and closed to extras, which is what makes each forbidden field a structural
impossibility rather than a validation rule (`FR-002`).

Re-exported so consumers import from one place and the module layout stays free to
change without breaking them.
"""

from ._base import (
    ChannelModel,
    ChannelViolation,
    ConversationRef,
    CorrelationId,
    MessageKey,
    PrincipalRef,
    TenantId,
    build,
)
from .audit import CHANNEL_STAGE_ORDER, ChannelAuditEvent, ChannelStage, DetailClass
from .delivery import ChannelDestination, DeliveryOutcome, outcome_reason_code
from .descriptor import ChannelDescriptor, ChannelId, CredentialRecord
from .envelope import ChannelEnvelope
from .identity import (
    BindingStatus,
    ChannelIdentityBinding,
    ExternalIdentity,
    ExternalIdentityRef,
)
from .kinds import TEXTUAL_KINDS, MessageKind, is_textual
from .presentation import Degradation, PresentationFragment, RenderedPresentation
from .raw import RawChannelRequest
from .reason_codes import (
    CHANNEL_REASON_CODE_OUTCOME,
    ChannelReasonCode,
    Outcome,
    channel_codes_with_outcome,
    channel_outcome_for,
)
from .refusal import ChannelRefusal, refusal_from_violation

__all__ = [
    "CHANNEL_REASON_CODE_OUTCOME",
    "CHANNEL_STAGE_ORDER",
    "TEXTUAL_KINDS",
    "BindingStatus",
    "ChannelAuditEvent",
    "ChannelDescriptor",
    "ChannelDestination",
    "ChannelEnvelope",
    "ChannelId",
    "ChannelIdentityBinding",
    "ChannelModel",
    "ChannelReasonCode",
    "ChannelRefusal",
    "ChannelStage",
    "ChannelViolation",
    "ConversationRef",
    "CorrelationId",
    "CredentialRecord",
    "Degradation",
    "DeliveryOutcome",
    "DetailClass",
    "ExternalIdentity",
    "ExternalIdentityRef",
    "MessageKey",
    "MessageKind",
    "Outcome",
    "PresentationFragment",
    "PrincipalRef",
    "RawChannelRequest",
    "RenderedPresentation",
    "TenantId",
    "build",
    "channel_codes_with_outcome",
    "channel_outcome_for",
    "is_textual",
    "outcome_reason_code",
    "refusal_from_violation",
]
