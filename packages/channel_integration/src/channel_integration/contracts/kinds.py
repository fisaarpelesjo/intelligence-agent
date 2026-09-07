"""Message kinds — T007 (FR-014, FR-108; SC-005, SC-063).

**Exactly one member is processable.** Everything else refuses with
``CHANNEL_MESSAGE_KIND_UNSUPPORTED``, naming the kind.

The enum being closed is half the mechanism; the other half is an **absence** —
no contract in this feature has a field capable of carrying a caption, filename,
alt text, transcript, OCR output or provider-generated description
(`contracts/envelope.py`). A validator that stripped derived text could be
forgotten in a refactor; a contract with nowhere to put it cannot be.

That absence is what keeps model-generated or provider-generated content from
entering the system **as the user's words** (`FR-108`). A caption is not the
question, and describing an image is not receiving one.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["TEXTUAL_KINDS", "MessageKind", "is_textual"]


class MessageKind(StrEnum):
    """The one accepted kind, and the twelve refused ones. Closed."""

    #: The only accepted kind.
    TEXT = "TEXT"

    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    STICKER = "STICKER"
    DOCUMENT = "DOCUMENT"
    LOCATION = "LOCATION"
    CONTACT = "CONTACT"
    REACTION = "REACTION"
    EDIT = "EDIT"
    DELETION = "DELETION"
    BUTTON = "BUTTON"
    #: A provider's own system message — a delivery receipt, a membership change, a
    #: webhook retry notice. Refused on kind rather than attributed to whoever the
    #: conversation belongs to.
    SYSTEM = "SYSTEM"


#: Exactly one. Declared as a set so the rule reads the same way the tests assert
#: it, and so widening it would be a visible edit rather than a new branch.
TEXTUAL_KINDS: frozenset[MessageKind] = frozenset({MessageKind.TEXT})


def is_textual(kind: MessageKind) -> bool:
    """Is this kind a textual question this feature may process?

    A predicate rather than ``kind is MessageKind.TEXT`` at each call site, so the
    single rule has a single home.
    """
    return kind in TEXTUAL_KINDS
