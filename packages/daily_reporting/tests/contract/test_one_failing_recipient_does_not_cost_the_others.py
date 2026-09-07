"""`T1007` — the loop that actually sends, driven where a node can reach it.

Three mutations of this loop stayed **green** while it lived in the harness script, because the
harness nodes stub that module out: `break` on the first failure, accepting a recipient outside the
declaration, and dropping `getChat` before each send. **The thing that sends was the thing no node
reached.** These are those three, plus the refusals.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from daily_reporting.run.fanout import send_to_each

pytestmark = pytest.mark.contract

DELE = "1000000001"
SEGUNDO = "1000000002"
TERCEIRO = "1000000003"
ESTRANHO = "9999999999"
TRES = (DELE, SEGUNDO, TERCEIRO)


def _recorder() -> tuple[list[tuple[str, str, str]], Callable[[str, str, str], None]]:
    seen: list[tuple[str, str, str]] = []

    def record(who: str, outcome: str, reason: str) -> None:
        seen.append((who, outcome, reason))

    return seen, record


def test_every_recipient_is_identified_before_being_sent_to() -> None:
    """`FR-1008`. `getChat` before **each** send, and the order is not incidental.

    Identifying after sending would tell you who you already messaged.
    """
    order: list[str] = []
    send_to_each(
        TRES,
        TRES,
        send=lambda one: order.append(f"send:{one}"),
        identify=lambda one: order.append(f"id:{one}"),
    )
    assert order == [f"{what}:{one}" for one in TRES for what in ("id", "send")], order


def test_one_failing_does_not_stop_the_others() -> None:
    """**The mutation that was green**: a `break` on the first failure.

    The third recipient's delivery is not the second recipient's to lose.
    """
    reached: list[str] = []

    def _send(one: str) -> None:
        reached.append(one)
        if one == SEGUNDO:
            message = "o Bot API recusou"
            raise RuntimeError(message)

    seen, record = _recorder()
    result = send_to_each(TRES, TRES, send=_send, identify=lambda _one: None, on_result=record)

    assert reached == list(TRES), "the loop stopped early"
    assert result.sent == (DELE, TERCEIRO)
    assert result.failed == (SEGUNDO,)
    #: **Two of three is not success.**
    assert not result.all_delivered
    assert [who for who, _outcome, _reason in seen] == list(TRES)
    assert {who: outcome for who, outcome, _r in seen}[SEGUNDO] == "failed"


def test_a_failure_to_IDENTIFY_is_that_recipients_failure(  # noqa: N802
) -> None:
    """Sending to a chat nobody could identify is what `getChat` exists to prevent."""
    sent: list[str] = []

    def _identify(one: str) -> None:
        if one == SEGUNDO:
            message = "getChat 400"
            raise RuntimeError(message)

    result = send_to_each(TRES, TRES, send=sent.append, identify=_identify)

    assert SEGUNDO not in sent, "a recipient nobody could identify was sent to anyway"
    assert result.failed == (SEGUNDO,)
    assert result.sent == (DELE, TERCEIRO)


def test_a_pending_recipient_outside_the_declaration_refuses_the_whole_pass() -> None:
    """**The second mutation that was green.** `OD-7` amended is *the declared and no other*.

    Nothing is sent — not even to the ones that were fine. A list containing a chat nobody declared
    is not a list to act on, and partially acting on it would be choosing which half to trust.
    """
    sent: list[str] = []
    result = send_to_each([DELE, ESTRANHO], TRES, send=sent.append, identify=lambda _one: None)

    assert sent == [], "something was sent despite an undeclared recipient in the list"
    assert result.sent == ()
    assert result.refused_for is not None
    assert not result.all_delivered


def test_nobody_pending_and_nobody_declared_are_both_refusals() -> None:
    """`SC-1006`. **Sending to nobody satisfies every check phrased as "each was authorised".**"""
    sent: list[str] = []

    empty_pending = send_to_each([], TRES, send=sent.append, identify=lambda _one: None)
    assert empty_pending.refused_for is not None
    assert not empty_pending.all_delivered

    empty_declared = send_to_each(TRES, [], send=sent.append, identify=lambda _one: None)
    assert empty_declared.refused_for is not None
    assert not empty_declared.all_delivered

    assert sent == []


def test_a_clean_pass_reports_everybody_and_nothing_else() -> None:
    """The direction that must not cost anything: three declared, three sent, one line each."""
    seen, record = _recorder()
    result = send_to_each(
        TRES, TRES, send=lambda _one: None, identify=lambda _one: None, on_result=record
    )

    assert result.sent == TRES
    assert result.failed == ()
    assert result.refused_for is None
    assert result.all_delivered
    assert [(who, outcome) for who, outcome, _r in seen] == [(one, "sent") for one in TRES]


def test_the_pending_subset_is_respected_and_not_widened_to_the_declaration() -> None:
    """A recipient who already received today is not in ``pending``, and must not be sent to."""
    sent: list[str] = []
    result = send_to_each([SEGUNDO], TRES, send=sent.append, identify=lambda _one: None)

    assert sent == [SEGUNDO], sent
    assert result.sent == (SEGUNDO,)
    assert result.all_delivered
