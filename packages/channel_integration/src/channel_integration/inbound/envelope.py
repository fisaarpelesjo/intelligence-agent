"""Step 5 — envelope construction — T039 (FR-003 — FR-008; SC-006, SC-007).

The canonical wire shape, and the exact set of fields a payload may declare.

**Unknown field refuses because the field does not exist**, not because a validator rejected it
(`FR-002`). `ChannelEnvelope` is closed to extras, so `access_tags`, `verified`, `max_rows`,
`detected_language`, `fixture` and every other name in the forbidden set arrive as
``extra_forbidden`` and become ``CHANNEL_ENVELOPE_FIELD_UNKNOWN``. This module adds the
symmetric check on the **wire** payload, so an undeclared key is refused before construction
rather than being quietly dropped on the way in.

**No field is defaulted, inferred or read from a clock** (`FR-003`, `FR-006`). An absent
reference date refuses; it is never today. An absent as-of pin means current-definition
resolution upstream and is never filled from the reference date (`FR-005`).

**The tenant and principal come from the resolved binding, not from the payload.** The payload
*declares* a tenant, which `identity.tenant` compares against the binding; what reaches the
envelope is the verified value. The principal reference never appears on the wire at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import Field

from ..contracts._base import (
    ChannelModel,
    ChannelViolation,
    ConversationRef,
    CorrelationId,
    MessageKey,
    PrincipalRef,
    TenantId,
    build,
)
from ..contracts.descriptor import ChannelId
from ..contracts.envelope import ChannelEnvelope
from ..contracts.reason_codes import ChannelReasonCode

__all__ = [
    "WIRE_FIELDS",
    "WIRE_OPTIONAL_FIELDS",
    "ValidatedWire",
    "assemble_envelope",
    "require_declared_fields_only",
    "validate_wire_shape",
    "wire_field",
]

#: Exactly what a payload may declare. A key outside this set refuses.
#:
#: Note what is **absent**: no principal, no access tag, no verified flag, no governed limit, no
#: freshness observation, no detected language, no fixture selector, and no caption, filename,
#: transcript, OCR output or description (`FR-004`, `FR-108`).
WIRE_FIELDS = frozenset(
    {
        "tenant",
        "language",
        "reference_date",
        "as_of",
        "conversation_id",
        "correlation_id",
        "message_id",
        "text",
    }
)

#: The only fields a payload may omit. Everything else in `WIRE_FIELDS` is required.
WIRE_OPTIONAL_FIELDS = frozenset({"as_of", "conversation_id", "correlation_id"})


def wire_field(payload: Mapping[str, Any], name: str) -> Any:
    """One declared field, refusing when a required one is absent."""
    if name in payload:
        return payload[name]
    if name in WIRE_OPTIONAL_FIELDS:
        return None
    raise ChannelViolation(
        ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE,
        f"the payload declares no {name}",
    )


def require_declared_fields_only(payload: Mapping[str, Any]) -> None:
    """Refuse a payload carrying a key the canonical shape does not declare."""
    unknown = sorted(set(payload) - WIRE_FIELDS)
    if unknown:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN,
            f"the payload declares undeclared fields: {', '.join(unknown)}",
        )


def _as_date(value: Any, field: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE,
                f"{field} is not an ISO-8601 date",
            ) from exc
    raise ChannelViolation(ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE, f"{field} is not a date")


class ValidatedWire(ChannelModel):
    """What a sender declared, validated, before identity is resolved.

    **This is step 5, and it runs before step 7.** The shape of a payload is the sender's own
    business and is checked on its own; identity resolution is a cost surface and must not be
    reached by a payload whose shape is already wrong. Splitting the two is what makes "an
    undeclared field costs nothing" measurable — `T052` counts registry reads and requires zero
    for exactly this case.
    """

    tenant_declared: str = Field(min_length=1)
    language: str = Field(min_length=1)
    reference_date: date
    as_of: date | None = None
    message_id: str = Field(min_length=1)
    text: str
    conversation_presented: str | None = None
    correlation_presented: str | None = None


def validate_wire_shape(payload: Mapping[str, Any]) -> ValidatedWire:
    """Step 5 — the payload's own shape, validated with nothing resolved yet."""
    require_declared_fields_only(payload)
    as_of_raw = wire_field(payload, "as_of")
    conversation = wire_field(payload, "conversation_id")
    correlation = wire_field(payload, "correlation_id")
    return build(
        ValidatedWire,
        ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE,
        tenant_declared=str(wire_field(payload, "tenant")),
        language=wire_field(payload, "language"),
        reference_date=_as_date(wire_field(payload, "reference_date"), "reference_date"),
        as_of=None if as_of_raw is None else _as_date(as_of_raw, "as_of"),
        message_id=str(wire_field(payload, "message_id")),
        text=str(wire_field(payload, "text")),
        conversation_presented=None if conversation is None else str(conversation),
        correlation_presented=None if correlation is None else str(correlation),
    )


def assemble_envelope(
    payload: Mapping[str, Any],
    channel: ChannelId,
    tenant: TenantId,
    principal_ref: PrincipalRef,
    conversation_id: ConversationRef,
    correlation_id: CorrelationId,
    text: str,
) -> ChannelEnvelope:
    """Construct the canonical envelope, or refuse.

    ``tenant``, ``principal_ref``, ``conversation_id``, ``correlation_id`` and ``text`` are the
    **resolved** values — verified tenant, resolved principal, scope-derived references and
    normalised question. The payload supplies only what a sender is entitled to declare: the
    language, the two dates and the provider's message id.
    """
    require_declared_fields_only(payload)

    as_of_raw = wire_field(payload, "as_of")
    return build(
        ChannelEnvelope,
        ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE,
        channel=channel,
        tenant=tenant,
        principal_ref=principal_ref,
        language=wire_field(payload, "language"),
        reference_date=_as_date(wire_field(payload, "reference_date"), "reference_date"),
        as_of=None if as_of_raw is None else _as_date(as_of_raw, "as_of"),
        correlation_id=correlation_id,
        conversation_id=conversation_id,
        message_id=MessageKey(str(wire_field(payload, "message_id"))),
        text=text,
    )
