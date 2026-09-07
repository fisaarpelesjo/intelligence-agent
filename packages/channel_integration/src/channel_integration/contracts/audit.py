"""Channel audit event and its six stages — T013 (ADR 0019; FR-081, FR-082; SC-040).

`001`'s ``requested_operation`` is a closed enum with no value for execution, so
`002` defined its own event (ADR 0005); `003` had no value for interpretation, so it
defined a third (ADR 0012). None of the three has a value for message receipt,
verification, identity resolution, rendering or delivery, so this feature defines a
fourth. Recorded as a deliberate consequence of the additive rule rather than drift
(spec `C-5`, ADR 0019).

**Six stages, closed and ordered.** A refusal emits the stage it refused at and
nothing after it, so the last stage present in a trail is where the message stopped —
which makes "where did this die?" a query rather than an investigation.

**The forbidden-content set is enforced twice.** By field set here: there is no field
for a payload, a question, an answer, a value, a filter value, provenance content, a
caveat, personal data, a credential or a signature, so a value cannot be *added*. And
by the serialised content scan in Phase B (T065): so a value cannot be *smuggled*
into an allowed field.

``detail_class`` is what lets the three deliberate code collapses (ADR 0018) stay
non-disclosing to a sender while remaining analysable by an operator. It is a
**closed enumeration of classes**, never free text: free text is where a phone number
or a signature fragment would eventually appear.

While `D-31` is undeclared, ``external_identity_ref`` is not constructible, so no
compliant event exists and the flow refuses with ``CHANNEL_AUDIT_UNAVAILABLE`` before
delivery (`FR-083`, `R-13`). The event contract is written now so that the refusal is
a governed state rather than a missing feature.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from semantic_catalog.contracts.reason_codes import Outcome

from ._base import ChannelModel, CorrelationId, MessageKey, PrincipalRef, TenantId
from .descriptor import ChannelId
from .identity import ExternalIdentityRef

__all__ = ["CHANNEL_STAGE_ORDER", "ChannelAuditEvent", "ChannelStage", "DetailClass"]


class ChannelStage(StrEnum):
    """The six channel lifecycle stages. Closed and ordered.

    A seventh stage is a **new decision**, not an addition (ADR 0019 § Acceptance).
    """

    RECEIVED = "RECEIVED"
    VERIFIED = "VERIFIED"
    IDENTIFIED = "IDENTIFIED"
    SUBMITTED = "SUBMITTED"
    RENDERED = "RENDERED"
    DELIVERED = "DELIVERED"


#: Declaration order **is** the sequence order, asserted by T016 rather than left to
#: the reader. Two orderings — one in code, one in a document — would eventually
#: disagree about which stage a message reached.
CHANNEL_STAGE_ORDER: tuple[ChannelStage, ...] = (
    ChannelStage.RECEIVED,
    ChannelStage.VERIFIED,
    ChannelStage.IDENTIFIED,
    ChannelStage.SUBMITTED,
    ChannelStage.RENDERED,
    ChannelStage.DELIVERED,
)


class DetailClass(StrEnum):
    """Operator-facing classification of a collapsed refusal. Never sender-facing.

    A closed enumeration, not free text. Each member names *which* member of a
    collapsed set failed, at the granularity an operator needs and no finer: the
    class, never the value. ``SIGNATURE_ABSENT`` tells an operator the header was
    missing; it does not carry the header.
    """

    NONE = "NONE"

    # Signature collapse (ADR 0018).
    SIGNATURE_ABSENT = "SIGNATURE_ABSENT"
    SIGNATURE_MALFORMED = "SIGNATURE_MALFORMED"
    SIGNATURE_MISMATCH = "SIGNATURE_MISMATCH"
    SIGNATURE_RETIRED_MATERIAL = "SIGNATURE_RETIRED_MATERIAL"
    SIGNATURE_WRONG_CHANNEL = "SIGNATURE_WRONG_CHANNEL"

    # Identity collapse (ADR 0018).
    BINDING_ABSENT = "BINDING_ABSENT"
    BINDING_REVOKED = "BINDING_REVOKED"
    BINDING_EXPIRED = "BINDING_EXPIRED"
    BINDING_AMBIGUOUS = "BINDING_AMBIGUOUS"

    # Envelope collapse (ADR 0018) — which field class was absent.
    ENVELOPE_TENANT_ABSENT = "ENVELOPE_TENANT_ABSENT"
    ENVELOPE_LANGUAGE_ABSENT = "ENVELOPE_LANGUAGE_ABSENT"
    ENVELOPE_REFERENCE_DATE_ABSENT = "ENVELOPE_REFERENCE_DATE_ABSENT"
    ENVELOPE_CORRELATION_ABSENT = "ENVELOPE_CORRELATION_ABSENT"
    ENVELOPE_CONVERSATION_ABSENT = "ENVELOPE_CONVERSATION_ABSENT"
    ENVELOPE_MESSAGE_ID_ABSENT = "ENVELOPE_MESSAGE_ID_ABSENT"


class ChannelAuditEvent(ChannelModel):
    """One event, at one stage, for one message.

    Every field is either an identifier, a pseudonymous reference, a governed code or
    a governing version. **Nothing here is content.**
    """

    stage: ChannelStage
    channel: ChannelId
    tenant: TenantId
    #: Pseudonymous. Never a name, handle or address.
    principal_ref: PrincipalRef
    #: Pseudonymous, under `D-31` key material. **Never** the phone number, member
    #: id, chat id, handle, display name or email (`FR-077`). Optional only because
    #: a `RECEIVED` event precedes identity resolution — not because it may be
    #: omitted once known.
    external_identity_ref: ExternalIdentityRef | None = None
    correlation_id: CorrelationId
    message_key: MessageKey
    outcome: Outcome
    #: Exactly one governed code, from any of the four namespaces. Typed as a string
    #: because the four enums are disjoint by test (T014): one field can carry any
    #: of them unambiguously, and a union would make every consumer switch on type
    #: before switching on value.
    code: str = Field(min_length=1)
    detail_class: DetailClass = DetailClass.NONE
    #: The `D-26` version in force, or ``None`` while it is undeclared.
    policy_version: str | None = None
    #: The `D-28` version in force, or ``None`` while it is undeclared.
    capability_version: str | None = None

    # Deliberately absent, and the absence is the mechanism (`FR-082`): no `payload`,
    # `body`, `text`, `question`, `answer`, `value`, `filter_value`, `provenance`,
    # `caveat`, `headers`, `signature`, `credential`, `token`, `url` or `error`. A
    # value cannot be added, and `extra="forbid"` means a caller cannot add one
    # either.
