"""The canonical channel envelope — T008 (FR-003 — FR-008, FR-108; SC-006 — SC-008).

The **only** object that crosses from this feature to the interaction boundary.
Nine identifying fields plus the normalised question text, all required except the
as-of pin.

**Two dates, two purposes, no derivation** (`FR-005`). ``reference_date`` resolves
relative and named period expressions upstream and touches no version;
``as_of`` fixes metric-definition version resolution and touches no period. Neither
defaults from the other, in either direction, and an omitted ``as_of`` means
current-definition resolution — matching `003` exactly. A validator cannot express
"these two must never be derived from each other", so the guarantee is structural:
this contract has no code that computes either from the other, and T061 constructs
each in isolation to prove it.

**No field can carry authority** (`FR-004`, `FR-107`). There is no ``access_tags``,
``role``, ``elevate``, ``verified``, ``max_rows``, ``policy_version``,
``freshness``, ``detected_language``, ``fixture`` or ``mode``. Each is refused
because the field does not exist.

**No field can carry text derived from media** (`FR-108`). There is no ``caption``,
``filename``, ``alt_text``, ``transcript``, ``ocr`` or ``description``. A non-text
message refuses on kind, and nothing accompanying it becomes a question.

**``language`` is typed as a plain string here, deliberately.** The governed
supported set is `003`'s ``DeclaredLanguage`` and validating it in this feature
would re-implement `003`'s language gate (`FR-093`). This contract asserts only
that a declaration is *present and non-blank*; the governed check happens where the
``QuestionIntake`` is constructed, at the interaction boundary (Phase D, T118), which
is the layer that owns it. Detection, inference, scoring and channel-locale override
exist nowhere (`FR-007`).
"""

from __future__ import annotations

import unicodedata
from datetime import date

from pydantic import Field, field_validator

from ._base import (
    ChannelModel,
    ChannelViolation,
    ConversationRef,
    CorrelationId,
    MessageKey,
    PrincipalRef,
    TenantId,
)
from .descriptor import ChannelId
from .reason_codes import ChannelReasonCode

__all__ = ["ChannelEnvelope"]

#: Line breaks and tabs a sender legitimately types. Everything else in Unicode
#: categories ``Cc`` (control) and ``Cf`` (format) is refused: NUL, the bidirectional
#: marks and overrides, the zero-width joiners and the byte-order mark.
#:
#: Refused rather than stripped. Stripping edits a question, and a question that changed
#: shape silently is the failure `FR-038` exists to prevent — a bidirectional override
#: inside what looks like a filter value is exactly the difference that must not be
#: normalised away.
#:
#: Classified by category rather than enumerated, so a codepoint nobody thought of is
#: refused by default instead of passing because it was missing from a list.
_PERMITTED_CONTROL_CHARACTERS = frozenset({chr(10), chr(13), chr(9)})
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf"})


class ChannelEnvelope(ChannelModel):
    """One inbound question, expressed channel-independently."""

    channel: ChannelId
    #: Required. Compared against the resolved principal's tenant; disagreement
    #: refuses (`FR-028`). Carried explicitly even though the deployment is
    #: single-tenant (`A-6`), because a derived tenant would make the check
    #: tautological — and the check is what turns "we are single-tenant" from an
    #: assumption into an assertion.
    tenant: TenantId
    #: The resolved binding's principal, pseudonymous. Never a phone number,
    #: member id, chat id, handle, display name or email (`FR-077`).
    principal_ref: PrincipalRef
    #: Declared, never detected. See the module docstring for why this is a plain
    #: string in this layer.
    language: str = Field(min_length=1)
    #: Resolves period expressions upstream. No effect on version resolution.
    reference_date: date
    #: Fixes version resolution upstream. No effect on period resolution. Optional;
    #: absent means current-definition resolution.
    as_of: date | None = None
    correlation_id: CorrelationId
    #: Scoped to ``(tenant, channel, principal_ref)``. A mismatch refuses,
    #: disclosing nothing about the referenced conversation's existence.
    conversation_id: ConversationRef
    #: The provider's own identifier. With ``channel``, the idempotency key.
    message_id: MessageKey
    #: The normalised question. Non-empty, textual, within the structural ceiling.
    #:
    #: Deliberately **no** ``min_length``: an empty question is
    #: ``CHANNEL_TEXT_NOT_USABLE`` per `contracts/reason-codes.md` §2, and a length
    #: constraint here would pre-empt the validator and report it as an incomplete
    #: envelope instead. Emptiness is a fact about the question, not about the envelope.
    text: str

    @field_validator("language")
    @classmethod
    def _language_is_declared_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE,
                "the declared language is blank",
            )
        return value

    @field_validator("text")
    @classmethod
    def _text_is_usable(cls, value: str) -> str:
        """Empty, blank, punctuation-only or control-bearing text refuses.

        Refused rather than repaired. The alternative — stripping the offending
        codepoints — would deliver a question the sender did not ask, and a
        bidirectional override inside a filter value is exactly the sort of
        difference that must not be normalised away silently.
        """
        if not value.strip():
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE,
                "the question is empty or whitespace only",
            )
        offending = [
            ch
            for ch in value
            if unicodedata.category(ch) in _FORBIDDEN_CATEGORIES
            and ch not in _PERMITTED_CONTROL_CHARACTERS
        ]
        if offending:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE,
                "the question carries a control, bidirectional or zero-width codepoint",
            )
        if not any(ch.isalnum() for ch in value):
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE,
                "the question carries no alphanumeric content",
            )
        return value
