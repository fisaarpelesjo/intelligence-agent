"""Message kinds and derived text — T057 (FR-014, FR-108; SC-005, SC-063).

Two claims. Every non-text kind refuses **naming the kind**, and nothing derived from a
non-textual message can become a question — the second enforced by an **absence**, so the test
asserts the absence rather than a stripping step.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts._base import ChannelViolation
from channel_integration.contracts.audit import ChannelAuditEvent
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import TEXTUAL_KINDS, MessageKind, is_textual
from channel_integration.contracts.presentation import RenderedPresentation
from channel_integration.contracts.raw import RawChannelRequest
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.inbound.envelope import WIRE_FIELDS
from channel_integration.inbound.kind import DERIVED_TEXT_FIELD_NAMES, require_textual

pytestmark = pytest.mark.unit

_NON_TEXT = [kind for kind in MessageKind if kind is not MessageKind.TEXT]


def test_text_is_the_only_accepted_kind() -> None:
    assert frozenset({MessageKind.TEXT}) == TEXTUAL_KINDS
    assert is_textual(MessageKind.TEXT)
    require_textual(MessageKind.TEXT)


@pytest.mark.parametrize("kind", _NON_TEXT, ids=[k.value for k in _NON_TEXT])
def test_every_other_kind_refuses_and_names_itself(kind: MessageKind) -> None:
    with pytest.raises(ChannelViolation) as caught:
        require_textual(kind)
    assert caught.value.code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED
    assert kind.value in caught.value.detail, "the refusal must name the unsupported kind"


def test_the_enum_is_closed_at_thirteen_members() -> None:
    """One accepted, twelve refused. A fourteenth would be a decision, not an addition."""
    assert len(MessageKind) == 13
    assert len(_NON_TEXT) == 12


def test_no_contract_can_carry_text_derived_from_media() -> None:
    """`FR-108`, as an absence across every contract a payload could reach."""
    for model in (RawChannelRequest, ChannelEnvelope, RenderedPresentation, ChannelAuditEvent):
        declared = set(model.model_fields)
        overlap = declared & DERIVED_TEXT_FIELD_NAMES
        assert not overlap, f"{model.__name__} can carry derived text: {sorted(overlap)}"


def test_the_wire_shape_declares_no_derived_text_field() -> None:
    """The payload a sender may declare has nowhere to put a caption or a transcript either."""
    assert not WIRE_FIELDS & DERIVED_TEXT_FIELD_NAMES


def test_the_derived_text_names_cover_the_cases_the_specification_lists() -> None:
    """The list is the mechanism, so its coverage is asserted rather than assumed."""
    for name in ("caption", "filename", "alt_text", "transcript", "ocr", "description"):
        assert name in DERIVED_TEXT_FIELD_NAMES
