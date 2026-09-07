"""Replay tolerance — T059 (FR-011, FR-015; SC-003).

The window is evaluated against the **passed instant**, never a clock, and only for schemes that
sign a timestamp. Where a scheme signs none, the window is not evaluated and that limit is
asserted here as a fact rather than left implicit.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.inbound.verify import VerificationFailure, verify_authenticity

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    bounds_for,
    descriptor_for,
    signed_request,
)

pytestmark = pytest.mark.unit

_TIMESTAMPED = [ChannelId.SLACK, ChannelId.GENERIC_WEBHOOK]
_UNTIMESTAMPED = [ChannelId.WHATSAPP, ChannelId.TELEGRAM]


@pytest.mark.parametrize("channel", _TIMESTAMPED)
def test_inside_the_tolerance_verifies(channel: ChannelId) -> None:
    raw = signed_request(channel, at=AT)
    verify_authenticity(
        raw,
        descriptor_for(channel),
        FIXTURE_MATERIAL,
        bounds_for(channel),
        AT + timedelta(seconds=60),
    )


@pytest.mark.parametrize("channel", _TIMESTAMPED)
def test_outside_the_tolerance_refuses(channel: ChannelId) -> None:
    raw = signed_request(channel, at=AT)
    bounds = bounds_for(channel)
    late = AT + timedelta(seconds=bounds.replay_tolerance_seconds + 1)
    with pytest.raises(VerificationFailure) as caught:
        verify_authenticity(raw, descriptor_for(channel), FIXTURE_MATERIAL, bounds, late)
    assert caught.value.code is ChannelReasonCode.CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE


@pytest.mark.parametrize("channel", _TIMESTAMPED)
def test_a_timestamp_in_the_future_beyond_tolerance_also_refuses(channel: ChannelId) -> None:
    """The window is symmetric: skew is absolute, so a future timestamp is not fresh."""
    raw = signed_request(channel, at=AT)
    bounds = bounds_for(channel)
    early = AT - timedelta(seconds=bounds.replay_tolerance_seconds + 1)
    with pytest.raises(VerificationFailure) as caught:
        verify_authenticity(raw, descriptor_for(channel), FIXTURE_MATERIAL, bounds, early)
    assert caught.value.code is ChannelReasonCode.CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE


@pytest.mark.parametrize("channel", _TIMESTAMPED)
def test_an_absent_signed_timestamp_refuses_where_the_scheme_provides_one(
    channel: ChannelId,
) -> None:
    raw = signed_request(channel, at=AT)
    without = raw.model_copy(
        update={
            "headers": tuple(
                (name, value) for name, value in raw.headers if "timestamp" not in name.lower()
            )
        }
    )
    with pytest.raises(VerificationFailure) as caught:
        verify_authenticity(
            without, descriptor_for(channel), FIXTURE_MATERIAL, bounds_for(channel), AT
        )
    # The basestring cannot be rebuilt without the timestamp, so this surfaces as an invalid
    # signature rather than as a tolerance failure — the earlier and stricter of the two.
    assert caught.value.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID


@pytest.mark.parametrize("channel", _UNTIMESTAMPED)
def test_a_scheme_without_a_signed_timestamp_has_no_window_evaluated(channel: ChannelId) -> None:
    """Stated, not simulated. Inventing a timestamp would make any replay look fresh."""
    raw = signed_request(channel, at=AT)
    far_future = AT + timedelta(days=365)
    verify_authenticity(
        raw, descriptor_for(channel), FIXTURE_MATERIAL, bounds_for(channel), far_future
    )


@pytest.mark.parametrize("channel", list(ChannelId))
def test_absent_material_refuses_before_any_scheme_runs(channel: ChannelId) -> None:
    """`FR-015`: verification that cannot run refuses. The shipped state for every channel."""
    raw = signed_request(channel)
    with pytest.raises(VerificationFailure) as caught:
        verify_authenticity(raw, descriptor_for(channel), None, bounds_for(channel), AT)
    assert caught.value.code is ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE
