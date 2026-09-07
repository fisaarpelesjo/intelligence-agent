"""Step 4 — message kind — T038 (FR-014, FR-108; SC-005, SC-063).

One rule: **`TEXT`, or refuse naming the kind.**

The kind is classified by the adapter, because recognising a WhatsApp sticker from a WhatsApp
payload is provider knowledge and provider knowledge lives in adapters (`FR-008`). What lives
here is the **decision**, so every channel refuses the same way and no adapter gets to decide
that its media is close enough to a question.

`FR-108` is enforced by an **absence**, not by this module: no contract in this feature has a
field for a caption, filename, alt text, transcript, OCR output or provider description, so
nothing derived from media can reach the interaction boundary even if an adapter wanted it to.
:data:`DERIVED_TEXT_FIELD_NAMES` names those fields so a test can assert the absence rather
than trusting it — a validator that stripped them could be forgotten in a refactor; a contract
with nowhere to put them cannot be.
"""

from __future__ import annotations

from ..contracts._base import ChannelViolation
from ..contracts.kinds import MessageKind, is_textual
from ..contracts.reason_codes import ChannelReasonCode

__all__ = ["DERIVED_TEXT_FIELD_NAMES", "require_textual"]

#: Field names through which model-generated or provider-generated text could enter as the
#: user's words. None of them exists on any contract in this feature, and `T017` asserts it.
DERIVED_TEXT_FIELD_NAMES = frozenset(
    {
        "caption",
        "filename",
        "file_name",
        "alt_text",
        "alt",
        "transcript",
        "transcription",
        "ocr",
        "ocr_text",
        "description",
        "summary",
        "auto_caption",
        "generated_text",
    }
)


def require_textual(kind: MessageKind) -> None:
    """Accept ``TEXT``; refuse anything else, naming the kind.

    The kind **is** named to the sender, deliberately, and it is the one detail this feature
    discloses at the inbound boundary. It discloses nothing about governance — a sender who
    posted a voice note already knows they posted a voice note — and it is the difference
    between a usable refusal and a silent drop.
    """
    if is_textual(kind):
        return
    raise ChannelViolation(
        ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED,
        f"{kind.value} is not a textual question",
    )
