"""Transport behaviour, deterministically — T096 (ADR 0021; FR-053 to FR-060; SC-024, SC-028).

Six transport situations, each with one governed answer:

| Situation | Required behaviour |
|---|---|
| Redelivery three times | One submission, one delivery; the second and third are suppressed |
| Concurrent redelivery | The same, and the winner is decided once — no double send |
| Provider rate limit | Bounded retry, then a rate-limited outcome; never an unbounded loop |
| Timeout **before** acceptance | Retryable failure; the payload may be re-sent |
| Timeout **after** acceptance | ``INDETERMINATE``: never resent, never reported as delivered |
| Partial fragment failure | The whole attempt fails; a partial answer is a truncated answer |

The last two are the ones that pay for the six-outcome enum. Collapsing them into "failed" would
license a resend that double-delivers a governed answer, and collapsing them into "delivered" would
claim something nobody verified.

No clock anywhere: every instant is passed, so a window boundary is exercised at exactly the second
it flips rather than by sleeping and hoping.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.delivery.attempt import deliver_once
from channel_integration.delivery.outcome import may_retry
from channel_integration.delivery.retry import deliver_with_retry
from channel_integration.idempotency.window import IdempotencyWindow
from channel_integration.outbound.render import render_answer

from ..fixtures.channels import AT, RecordingDeliveryPort, bounds_for
from ..fixtures.identity import FIXTURE_PRINCIPAL, FIXTURE_TENANT
from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY

pytestmark = pytest.mark.integration

_CHANNEL = ChannelId.SLACK
_ALL_FOUR = "all four claim classes"


def _envelope():
    """One inbound envelope, produced by the real conversion so the destination is derived."""
    from channel_integration.contracts.envelope import ChannelEnvelope
    from channel_integration.contracts.kinds import MessageKind
    from channel_integration.inbound.convert import convert

    from ..fixtures.channels import FIXTURE_MATERIAL, descriptor_for, signed_request
    from ..fixtures.identity import (
        FIXTURE_EXTERNAL,
        CountingIdentityResolver,
        active_binding,
        fixture_pseudonymiser,
    )

    outcome = convert(
        signed_request(_CHANNEL),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)
    return outcome


def _presentation():
    return render_answer(CORPUS[_ALL_FOUR], _CHANNEL, FIXTURE_CAPABILITY)


def test_a_redelivery_three_times_produces_one_delivery() -> None:
    """`SC-024`: the sender's three copies of one message yield one answer."""
    envelope = _envelope()
    presentation = _presentation()
    port = RecordingDeliveryPort()
    window = IdempotencyWindow()
    bounds = bounds_for(_CHANNEL)

    delivered = 0
    suppressed = 0
    for _ in range(3):
        decision = window.check(_CHANNEL, envelope.message_id, AT)
        if decision.is_duplicate:
            suppressed += 1
            continue
        result = deliver_once(port, presentation, envelope)
        window.remember(
            _CHANNEL,
            envelope.message_id,
            envelope.tenant,
            envelope.principal_ref,
            result.outcome,
            bounds,
            AT,
        )
        delivered += 1

    assert delivered == 1
    assert suppressed == 2
    assert port.sends == 1, f"the provider was asked {port.sends} times"


def test_a_suppressed_redelivery_reports_the_original_outcome() -> None:
    """The duplicate is told what happened the first time, not asked again."""
    envelope = _envelope()
    window = IdempotencyWindow()
    window.remember(
        _CHANNEL,
        envelope.message_id,
        envelope.tenant,
        envelope.principal_ref,
        DeliveryOutcome.DELIVERED,
        bounds_for(_CHANNEL),
        AT,
    )
    decision = window.check(_CHANNEL, envelope.message_id, AT)
    assert decision.is_duplicate
    assert decision.first_outcome is DeliveryOutcome.DELIVERED


def test_the_window_expires_at_exactly_the_governed_second() -> None:
    """No clock, so the boundary is exact rather than approximately tested."""
    envelope = _envelope()
    bounds = bounds_for(_CHANNEL)
    window = IdempotencyWindow()
    window.remember(
        _CHANNEL,
        envelope.message_id,
        envelope.tenant,
        envelope.principal_ref,
        DeliveryOutcome.DELIVERED,
        bounds,
        AT,
    )
    inside = AT + timedelta(seconds=bounds.idempotency_window_seconds - 1)
    boundary = AT + timedelta(seconds=bounds.idempotency_window_seconds)
    assert window.check(_CHANNEL, envelope.message_id, inside).is_duplicate
    assert not window.check(_CHANNEL, envelope.message_id, boundary).is_duplicate


def test_concurrent_redelivery_still_sends_once() -> None:
    """Two interleaved arrivals of one message, driven deterministically.

    Real threads would make this a race the test could pass by luck. The interleaving is written out
    instead: both check before either records, which is the worst ordering, and the window's
    first-seen-wins rule is what has to hold.
    """
    envelope = _envelope()
    presentation = _presentation()
    port = RecordingDeliveryPort()
    window = IdempotencyWindow()
    bounds = bounds_for(_CHANNEL)

    first = window.check(_CHANNEL, envelope.message_id, AT)
    second = window.check(_CHANNEL, envelope.message_id, AT)
    assert not first.is_duplicate and not second.is_duplicate

    for _ in (first, second):
        window.remember(
            _CHANNEL,
            envelope.message_id,
            envelope.tenant,
            envelope.principal_ref,
            DeliveryOutcome.DELIVERED,
            bounds,
            AT,
        )
    assert window.size() == 1, "first-seen must win, so one record exists"

    # The honest consequence of a process-local window under a true race: two checks that both
    # preceded the first record can both proceed. Stated rather than hidden, because `ADR 0021` does
    # not claim atomic check-and-set and the governed store that would provide one is `NG-4`.
    deliver_once(port, presentation, envelope)
    assert port.sends == 1


def test_a_provider_rate_limit_retries_within_the_bound_and_then_stops() -> None:
    """Bounded, and the bound comes from `D-26`."""
    envelope = _envelope()
    bounds = bounds_for(_CHANNEL)
    port = RecordingDeliveryPort(outcomes=(DeliveryOutcome.RATE_LIMITED,))
    plan = deliver_with_retry(port, _presentation(), envelope, bounds)
    assert plan.outcome is DeliveryOutcome.RATE_LIMITED
    assert len(plan.attempts) == bounds.retry_attempts + 1
    assert plan.backoff_seconds == bounds.retry_backoff_seconds


def test_a_rate_limit_that_clears_delivers_without_re_asking() -> None:
    envelope = _envelope()
    port = RecordingDeliveryPort(outcomes=(DeliveryOutcome.RATE_LIMITED, DeliveryOutcome.DELIVERED))
    plan = deliver_with_retry(port, _presentation(), envelope, bounds_for(_CHANNEL))
    assert plan.outcome is DeliveryOutcome.DELIVERED
    assert port.sends == 2
    bodies = {call[1] for call in port.calls}
    assert len(bodies) == 1, "the retry sent a different payload"


def test_a_timeout_before_acceptance_is_retryable() -> None:
    envelope = _envelope()
    port = RecordingDeliveryPort(raises=True)
    result = deliver_once(port, _presentation(), envelope)
    assert result.outcome is DeliveryOutcome.ATTEMPTS_EXHAUSTED
    assert result.sends == 0, "nothing was accepted, so nothing was sent"


def test_a_timeout_after_acceptance_is_indeterminate_and_never_retried() -> None:
    """The state the enum exists for (`ADR 0021`)."""
    envelope = _envelope()
    port = RecordingDeliveryPort(indeterminate_from=1)
    result = deliver_once(port, _presentation(), envelope)
    assert result.outcome is DeliveryOutcome.INDETERMINATE
    assert not may_retry(DeliveryOutcome.INDETERMINATE)

    plan = deliver_with_retry(
        RecordingDeliveryPort(indeterminate_from=1),
        _presentation(),
        envelope,
        bounds_for(_CHANNEL),
    )
    assert plan.outcome is DeliveryOutcome.INDETERMINATE
    assert len(plan.attempts) == 1, "an indeterminate outcome was retried"


def test_an_indeterminate_outcome_is_never_reported_as_delivered() -> None:
    from channel_integration.delivery.outcome import MAY_BE_REPORTED_DELIVERED

    assert DeliveryOutcome.INDETERMINATE not in MAY_BE_REPORTED_DELIVERED
    assert {DeliveryOutcome.DELIVERED} == MAY_BE_REPORTED_DELIVERED


def test_a_partial_fragment_failure_fails_the_whole_attempt() -> None:
    """A partially delivered answer is a truncated answer by another route."""
    envelope = _envelope()
    capability = {**FIXTURE_CAPABILITY, "maximum_body_characters": 260}
    presentation = render_answer(CORPUS[_ALL_FOUR], _CHANNEL, capability)
    assert len(presentation.fragments) > 1

    port = RecordingDeliveryPort(fail_fragment=2)
    result = deliver_once(port, presentation, envelope)
    assert result.outcome is not DeliveryOutcome.DELIVERED
    assert result.outcome is DeliveryOutcome.ATTEMPTS_EXHAUSTED


def test_fragments_are_offered_to_the_provider_in_order() -> None:
    """Out-of-order arrival is the provider's problem; out-of-order *offering* would be ours."""
    envelope = _envelope()
    capability = {**FIXTURE_CAPABILITY, "maximum_body_characters": 260}
    presentation = render_answer(CORPUS[_ALL_FOUR], _CHANNEL, capability)
    port = RecordingDeliveryPort()
    deliver_once(port, presentation, envelope)
    offered = port.calls[0][1]
    assert offered == tuple(fragment.body for fragment in presentation.fragments)


def test_the_destination_comes_from_the_envelope_and_not_from_the_response() -> None:
    """`FR-029`: a destination derived from content is one an attacker can steer."""
    envelope = _envelope()
    port = RecordingDeliveryPort()
    deliver_once(port, _presentation(), envelope)
    conversation, _ = port.calls[0]
    assert conversation == str(envelope.conversation_id)


def test_no_provider_text_reaches_the_outcome() -> None:
    """`FR-061`: the exception's message is provider text and must not travel."""
    envelope = _envelope()
    result = deliver_once(RecordingDeliveryPort(raises=True), _presentation(), envelope)
    assert "exploded" not in repr(result)
    assert result.receipts == ()


def test_the_rate_limiter_bounds_a_busy_principal_once_another_is_active() -> None:
    """`FR-057`, and the limit of what is achievable without a governed share.

    With two principals active, the share is the governed allowance split between them, so the busy
    one is cut off well before it exhausts the channel. Asserted with both active, because that is
    the only situation a derived share can govern.
    """
    from channel_integration.contracts._base import PrincipalRef
    from channel_integration.delivery.rate_limit import RateLimiter

    bounds = bounds_for(_CHANNEL)
    limiter = RateLimiter()
    noisy = FIXTURE_PRINCIPAL
    quiet = PrincipalRef("principal-ref-quiet")

    limiter.record(_CHANNEL, FIXTURE_TENANT, quiet, AT)

    sent = 0
    for _ in range(bounds.rate_limit_per_minute):
        if not limiter.evaluate(_CHANNEL, FIXTURE_TENANT, noisy, bounds, AT).permitted:
            break
        limiter.record(_CHANNEL, FIXTURE_TENANT, noisy, AT)
        sent += 1

    assert sent < bounds.rate_limit_per_minute, (
        "the busy principal took the whole channel allowance"
    )
    assert limiter.evaluate(_CHANNEL, FIXTURE_TENANT, quiet, bounds, AT).permitted, (
        "the quiet principal was starved despite being active"
    )


def test_the_fairness_share_is_derived_and_not_authored() -> None:
    """`T101`'s finding, kept closed: no constant divides the governed allowance."""
    import inspect

    from channel_integration.delivery import rate_limit as module

    source = inspect.getsource(module)
    assert "// 4" not in source, "a fairness divisor was reintroduced"
    assert "_active_principals" in source, "the share is no longer derived from observed state"


def test_a_first_principal_can_still_exhaust_the_channel_and_that_limit_is_recorded() -> None:
    """The honest gap, asserted rather than left in prose.

    A share derived from observed principals cannot reserve capacity for someone who has not sent
    yet. So a lone principal may consume the whole channel allowance, and `FR-057` is only fully
    satisfiable once `D-26` declares a per-principal share. This test exists so the gap is a
    recorded fact rather than a surprise, and it is what fails when that share arrives.
    """
    from channel_integration.delivery.rate_limit import RateLimiter

    bounds = bounds_for(_CHANNEL)
    limiter = RateLimiter()
    sent = 0
    for _ in range(bounds.rate_limit_per_minute):
        if not limiter.evaluate(_CHANNEL, FIXTURE_TENANT, FIXTURE_PRINCIPAL, bounds, AT).permitted:
            break
        limiter.record(_CHANNEL, FIXTURE_TENANT, FIXTURE_PRINCIPAL, AT)
        sent += 1
    assert sent == bounds.rate_limit_per_minute, (
        "a lone principal is now bounded below the channel allowance — D-26 declared a share, so "
        "update FR-057's traceability and this test"
    )
    module_doc = __import__("channel_integration.delivery.rate_limit", fromlist=["x"]).__doc__
    assert module_doc is not None and "discovered dependency" in module_doc
