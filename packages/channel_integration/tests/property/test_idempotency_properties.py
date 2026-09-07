"""T148 — inside one process and one window, a duplicate key never submits twice.

The scope is the property. `IdempotencyWindow` suppresses duplicates in **this** process, for
**this** instance, inside the **governed** window, and claims nothing beyond that. So the properties
here are written to hold exactly where the claim holds and to fail if the claim ever quietly widens:

* the first sighting of a key is never a duplicate;
* every later sighting inside the window is, and reports the **first** outcome, not a new one;
* a sighting after expiry is handled afresh — the record stopped being evidence, so suppressing
  forever would be a claim the window does not make;
* two windows never see each other, because two windows are two instances.

## What is deliberately not asserted

That duplicates are suppressed across processes. They are not, `T083` refuses a multi-instance
configuration rather than pretending otherwise, and a property test asserting cross-process
suppression would be asserting the defect this feature was careful to avoid.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from channel_integration.contracts._base import MessageKey
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.idempotency.window import IdempotencyWindow

from ..fixtures.channels import AT, bounds_for
from ..fixtures.identity import FIXTURE_PRINCIPAL, FIXTURE_TENANT

pytestmark = pytest.mark.property

#: Wrapped in `MessageKey` at generation rather than at each call site: the key type is a `NewType`,
#: and a test that passed bare strings would be exercising a signature the production caller cannot
#: use.
_MESSAGE_IDS = st.builds(
    MessageKey,
    st.text(
        alphabet=st.characters(codec="ascii", exclude_categories=("Cc", "Cs", "Zs")),
        min_size=1,
        max_size=32,
    ),
)
_OUTCOMES = st.sampled_from(tuple(DeliveryOutcome))
_CHANNELS = st.sampled_from(tuple(ChannelId))


def _remember(
    window: IdempotencyWindow,
    channel: ChannelId,
    message_id: MessageKey,
    outcome: DeliveryOutcome,
    at: datetime = AT,
) -> None:
    window.remember(
        channel,
        message_id,
        FIXTURE_TENANT,
        FIXTURE_PRINCIPAL,
        outcome,
        bounds_for(channel),
        at,
    )


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(channel=_CHANNELS, message_id=_MESSAGE_IDS, outcome=_OUTCOMES)
def test_the_first_sighting_is_never_a_duplicate(
    channel: ChannelId,
    message_id: MessageKey,
    outcome: DeliveryOutcome,
) -> None:
    """A fresh window knows nothing, and a window that knows nothing suppresses nothing."""
    window = IdempotencyWindow()
    assert window.check(channel, message_id, AT).is_duplicate is False
    _remember(window, channel, message_id, outcome)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    channel=_CHANNELS,
    message_id=_MESSAGE_IDS,
    outcome=_OUTCOMES,
    repeats=st.integers(min_value=1, max_value=5),
)
def test_every_redelivery_inside_the_window_reports_the_first_outcome(
    channel: ChannelId,
    message_id: MessageKey,
    outcome: DeliveryOutcome,
    repeats: int,
) -> None:
    """The core statement: one submission, however many times the provider redelivers.

    Reporting the **first** outcome rather than a fresh one is what makes suppression honest — a
    caller learns what happened, and nothing happened twice.
    """
    window = IdempotencyWindow()
    _remember(window, channel, message_id, outcome)
    for _ in range(repeats):
        decision = window.check(channel, message_id, AT)
        assert decision.is_duplicate is True
        assert decision.first_outcome is outcome


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(channel=_CHANNELS, message_id=_MESSAGE_IDS, outcome=_OUTCOMES)
def test_a_sighting_after_the_window_is_handled_afresh(
    channel: ChannelId,
    message_id: MessageKey,
    outcome: DeliveryOutcome,
) -> None:
    """Outside the governed window the record is no longer evidence of anything.

    The expiry is computed from the governed bounds and the passed instant, so this reads the same
    bound the implementation does rather than a number written here.
    """
    window = IdempotencyWindow()
    bounds = bounds_for(channel)
    _remember(window, channel, message_id, outcome)
    after = AT + timedelta(seconds=bounds.idempotency_window_seconds + 1)
    assert window.check(channel, message_id, after).is_duplicate is False


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(channel=_CHANNELS, message_id=_MESSAGE_IDS, outcome=_OUTCOMES)
def test_two_windows_never_see_each_other(
    channel: ChannelId,
    message_id: MessageKey,
    outcome: DeliveryOutcome,
) -> None:
    """Two windows are two instances, and the scope statement says two instances do not share.

    This is the property that would fail first if suppression ever became global state — a module
    dict, a class attribute, a cache keyed on the message id alone.
    """
    first, second = IdempotencyWindow(), IdempotencyWindow()
    _remember(first, channel, message_id, outcome)
    assert first.check(channel, message_id, AT).is_duplicate is True
    assert second.check(channel, message_id, AT).is_duplicate is False


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    left=st.tuples(_CHANNELS, _MESSAGE_IDS),
    right=st.tuples(_CHANNELS, _MESSAGE_IDS),
    outcome=_OUTCOMES,
)
def test_two_different_keys_never_suppress_each_other(
    left: tuple[ChannelId, MessageKey],
    right: tuple[ChannelId, MessageKey],
    outcome: DeliveryOutcome,
) -> None:
    """The same provider message id on two channels is two messages, not a redelivery.

    Generated pairs rather than a fixed example, because the failure mode is a key that ignores one
    of its two components — and which component gets ignored is exactly what a fixed example would
    fail to explore.
    """
    window = IdempotencyWindow()
    _remember(window, left[0], left[1], outcome)
    decision = window.check(right[0], right[1], AT)
    assert decision.is_duplicate is (left == right)
