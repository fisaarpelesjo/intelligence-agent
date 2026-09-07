"""Step 1 — the structural parse — T031 (FR-013, FR-016; SC-003).

**Runs before verification, and decides nothing about content.** Its only job is to refuse
what cannot safely be parsed at all: a wrong content type, a mismatched declared length, a
body past the structural ceiling, a nesting depth past it, a field count past it.

**The ceiling here is structural, not governed.** `D-26`'s
``maximum_inbound_bytes`` is a governed number and naming it in a refusal would disclose a
governed limit to an unauthenticated stranger — which this feature may never do, at any step
(`contracts/inbound-conversion.md` §3). So this module carries its own contract ceiling,
refuses **without naming a number**, and leaves the governed bound to
`inbound.verify`, which applies it after the sender is authentic.

The two ceilings are deliberately different in kind: the structural one exists so a parser
cannot be used as a denial-of-service primitive, and it is chosen here rather than approved
elsewhere precisely because it protects the parser rather than expressing a policy.

Every byte of the payload stays **untrusted data** (`FR-016`): nothing parsed here becomes
configuration, an envelope field, an identifier of another message or a selector of a code
path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from ..contracts._base import ChannelViolation
from ..contracts.raw import RawChannelRequest
from ..contracts.reason_codes import ChannelReasonCode

__all__ = [
    "STRUCTURAL_MAX_BYTES",
    "STRUCTURAL_MAX_DEPTH",
    "STRUCTURAL_MAX_FIELDS",
    "parse_structure",
]

#: Contract ceilings. **Not** governed limits, and never named in a refusal.
#:
#: Sized so that no legitimate textual question approaches them: a question is a sentence,
#: and a sentence is not 64 KiB deep in nested objects. A payload that exceeds one of these
#: is not a large question — it is something else.
STRUCTURAL_MAX_BYTES = 64 * 1024
STRUCTURAL_MAX_DEPTH = 8
STRUCTURAL_MAX_FIELDS = 128

#: The content types a channel webhook may present. Read from the header **names** this
#: feature consumes; header values never reach a log, a trace or a refusal (`FR-070`).
_PERMITTED_CONTENT_TYPES = frozenset({"application/json", "application/json; charset=utf-8"})


def _header(raw: RawChannelRequest, name: str) -> str | None:
    lowered = name.lower()
    for key, value in raw.headers:
        if key.lower() == lowered:
            return value
    return None


def _depth_and_fields(node: object, depth: int = 1) -> tuple[int, int]:
    """Maximum nesting depth and total field count of a parsed document.

    Computed rather than assumed, and computed **before** any field is read, so a deeply
    nested payload is refused by the structure check instead of exhausting the recursion
    limit inside a validator.
    """
    if isinstance(node, Mapping):
        mapping = cast("Mapping[str, object]", node)
        fields = len(mapping)
        deepest = depth
        for value in mapping.values():
            child_depth, child_fields = _depth_and_fields(value, depth + 1)
            deepest = max(deepest, child_depth)
            fields += child_fields
        return deepest, fields
    if isinstance(node, Sequence) and not isinstance(node, str | bytes):
        items = cast("Sequence[object]", node)
        fields = 0
        deepest = depth
        for value in items:
            child_depth, child_fields = _depth_and_fields(value, depth + 1)
            deepest = max(deepest, child_depth)
            fields += child_fields
        return deepest, fields
    return depth, 0


def parse_structure(raw: RawChannelRequest) -> Mapping[str, Any]:
    """Parse ``raw`` structurally, or refuse.

    Returns the parsed mapping so later steps can read declared fields. **Verification does
    not use this result**: it runs over ``raw.body`` bytes, because a signature over a
    re-serialised parse is a signature over something the sender did not sign
    (`contracts/inbound-conversion.md` §2).
    """
    content_type = _header(raw, "content-type")
    if content_type is not None and content_type.strip().lower() not in _PERMITTED_CONTENT_TYPES:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
            "the declared content type is not a permitted JSON media type",
        )

    declared_length = _header(raw, "content-length")
    if declared_length is not None:
        try:
            expected = int(declared_length)
        except ValueError as exc:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
                "the declared content length is not an integer",
            ) from exc
        if expected != len(raw.body):
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
                "the declared content length does not match the received body",
            )

    if not raw.body:
        raise ChannelViolation(ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED, "the body is empty")
    if len(raw.body) > STRUCTURAL_MAX_BYTES:
        # Names no number: the sender is unauthenticated at every step of this feature.
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT,
            "the body exceeds the structural ceiling",
        )

    try:
        document = json.loads(raw.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
            "the body is not readable as UTF-8 JSON",
        ) from exc

    if not isinstance(document, Mapping):
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED, "the body is not a JSON object"
        )

    depth, fields = _depth_and_fields(cast("Mapping[str, object]", document))
    if depth > STRUCTURAL_MAX_DEPTH or fields > STRUCTURAL_MAX_FIELDS:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT,
            "the body exceeds the structural ceiling on nesting or field count",
        )
    return cast("Mapping[str, Any]", document)
