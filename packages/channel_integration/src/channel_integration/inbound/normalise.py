"""Step 6 — declared normalisation — T040 (FR-037 — FR-039; SC-050, SC-051).

Deterministic, **declared**, and never meaning-changing. Each rule has a name and a version,
the outcome records which applied, and the rule set is the only thing that may touch the text.

**What normalisation may do**: remove provider decoration it can identify with certainty —
a leading mention, a quoted-reply block, a threading marker — normalise Unicode to NFC, and
trim surrounding whitespace.

**What it may never do** (`FR-038`): translate, correct, expand, complete, summarise,
re-punctuate for meaning, or append context. None of those operations exists in this module,
which is why the guarantee is structural rather than a rule someone remembers.

**Ambiguity refuses** (`FR-039`). Where the rule set cannot tell decoration from content, the
message is refused with ``CHANNEL_NORMALISATION_AMBIGUOUS`` rather than guessed at. Two cases
reach it: a mention that is not leading — `"quantas instalações @bot em julho?"`, where the
mention might be a filter value — and text that is **only** decoration, where removing it
would leave no question at all. A rule set that guesses is a rule set that silently edits
questions, and a silently edited question is answered correctly to nobody.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import Field

from ..contracts._base import ChannelModel, ChannelViolation
from ..contracts.reason_codes import ChannelReasonCode

__all__ = ["NORMALISATION_RULESET_VERSION", "NormalisationOutcome", "normalise_question"]

#: Bump when a rule is added, removed or changed. Carried in the outcome so a question that
#: changed shape can be explained without retaining the original text.
NORMALISATION_RULESET_VERSION = "1"

_MENTION = re.compile(r"@[A-Za-z0-9_.\-]{2,64}")
_LEADING_MENTION = re.compile(r"^\s*(?:@[A-Za-z0-9_.\-]{2,64}\s+)+")
_QUOTED_LINE = re.compile(r"^\s*>.*$", re.M)
_THREAD_MARKER = re.compile(r"^\s*(?:\[thread\]|\[re\]|Re:)\s*", re.I)


class NormalisationOutcome(ChannelModel):
    """The normalised text and the named rules that produced it."""

    text: str = Field(min_length=1)
    #: Rule names, in application order. Empty means the text arrived already canonical.
    applied: tuple[str, ...] = ()
    ruleset_version: str = Field(min_length=1)


def normalise_question(raw_text: str) -> NormalisationOutcome:
    """Normalise ``raw_text`` under the declared rule set, or refuse.

    Pure and deterministic: the same input yields a byte-identical outcome, on every run and
    in every process (`SC-050`).
    """
    if not raw_text.strip():
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE, "the question is empty or blank"
        )

    applied: list[str] = []
    text = raw_text

    canonical = unicodedata.normalize("NFC", text)
    if canonical != text:
        applied.append("unicode-nfc")
        text = canonical

    without_quotes = _QUOTED_LINE.sub("", text)
    if without_quotes != text:
        applied.append("remove-quoted-reply")
        text = without_quotes

    without_thread = _THREAD_MARKER.sub("", text)
    if without_thread != text:
        applied.append("remove-threading-marker")
        text = without_thread

    without_mention = _LEADING_MENTION.sub("", text)
    if without_mention != text:
        applied.append("remove-leading-mention")
        text = without_mention

    stripped = text.strip()
    if stripped != text:
        applied.append("trim-surrounding-whitespace")
        text = stripped

    # Ambiguity, case one: a mention that is not leading. It might be decoration, or it might
    # be a value the question filters on. The rule set cannot tell, so it refuses.
    if _MENTION.search(text):
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS,
            "a mention appears where it cannot be distinguished from content",
        )

    # Ambiguity, case two: nothing survived. Whatever was there was either all decoration or
    # not a question, and choosing between those readings is exactly what refusing avoids.
    if not text or not any(ch.isalnum() for ch in text):
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS,
            "nothing distinguishable from decoration remains",
        )

    return NormalisationOutcome(
        text=text, applied=tuple(applied), ruleset_version=NORMALISATION_RULESET_VERSION
    )
