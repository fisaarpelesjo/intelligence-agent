"""`T1003`, `T1004`, `T1006` — the declared list, and idempotency per day AND per recipient.

`OD-7` was amended on 2026-08-31 by his own words — *"agora para as pessoas que tem o bot, pode
tacar le pau"* — from **one recipient and no other** to **the declared recipients and no other**.
What moved is how many he named. What did not move is that a chat outside the declaration receives
nothing, and this file is what keeps that true while the number changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from daily_reporting.origination.conditions import (
    RECIPIENT_KEY,
    every_recipient_is_declared,
    recipients_from,
)
from daily_reporting.run.journal import (
    Outcome,
    already_sent,
    anything_was_delivered,
    line_for,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

pytestmark = pytest.mark.contract

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
INSTANT = datetime(2026, 8, 31, 11, 0, tzinfo=UTC)
CLOSED_DAY = date(2026, 8, 30)

#: Stand-ins. **No real chat id is written in a test either** — the ids are his, and the property
#: under test is about counting and matching, not about any particular number.
DELE = "1000000001"
SEGUNDO = "1000000002"
TERCEIRO = "1000000003"
ESTRANHO = "9999999999"

#: The other key, the one that answers a DIFFERENT question.
MAY_TALK_KEY = "TELEGRAM_ALLOWED_CHAT_ID"


def _append(journal: Path, recipient: str, outcome: Outcome) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(
            line_for(
                instant=INSTANT,
                closed_day=CLOSED_DAY,
                outcome=outcome,
                zone=SAO_PAULO,
                recipient=recipient,
            )
        )


# ---------------------------------------------------------------- the list is DECLARED


def test_the_send_list_is_not_inherited_from_who_may_talk_to_the_bot() -> None:
    """**`SC-1003`, and this is the 2026-08-30 defect written as a node.**

    Measured that day: the may-talk key held three ids while the condition said *the recipient is
    his chat and no other* — it answered **yes** about a fact it could not see. Measured again
    2026-08-31: the may-talk key holds three and the declared send key holds one, and the one is the
    first of the three. **That overlap is a coincidence, not a definition.**
    """
    environment = {
        MAY_TALK_KEY: f"{DELE},{SEGUNDO},{TERCEIRO}",
        RECIPIENT_KEY: DELE,
    }
    assert recipients_from(environment) == (DELE,), (
        "the send list was inherited from the may-talk key"
    )
    #: And declaring three in the SEND key gives three — the amendment works through the
    #: declaration, never through the other key.
    assert recipients_from({**environment, RECIPIENT_KEY: f"{DELE},{SEGUNDO},{TERCEIRO}"}) == (
        DELE,
        SEGUNDO,
        TERCEIRO,
    )


def test_the_declaration_is_read_in_order_without_duplicates() -> None:
    """Separators, spacing and a repeated id — none of which is a decision anybody makes twice."""
    assert recipients_from({RECIPIENT_KEY: f" {DELE} ; {SEGUNDO} , {DELE} "}) == (DELE, SEGUNDO)
    assert recipients_from({RECIPIENT_KEY: f"{TERCEIRO}\n{SEGUNDO}"}) == (TERCEIRO, SEGUNDO)


def test_an_empty_declaration_is_nothing_and_not_an_empty_success() -> None:
    """`SC-1006`, `FR-1004`. **Sending to nobody satisfies every check phrased as "each
    recipient was authorised"**, so the empty case is answered here rather than downstream."""
    for value in ("", "   ", ",", " ; , "):
        assert recipients_from({RECIPIENT_KEY: value}) == (), repr(value)
    assert recipients_from({}) == ()
    #: And the condition refuses it rather than reading it as a clean run.
    assert not every_recipient_is_declared([], {RECIPIENT_KEY: ""})

    #: **AND NO FALLBACK, which is the dangerous shape of the empty case.**
    #:
    #: Found by driving: a mutation reading `RECIPIENT_KEY or TELEGRAM_ALLOWED_CHAT_ID` left every
    #: node green, because the fallback only fires when the send key is EMPTY and none of the cases
    #: above put the other key in the environment. An undeclared send list would then have silently
    #: become **three people who were never declared for sending** — the 2026-08-30 defect with a
    #: worse blast radius, reached through the one branch nothing was watching.
    for value in ("", "   ", ",", " ; , "):
        blank_but_talkative = {
            RECIPIENT_KEY: value,
            MAY_TALK_KEY: f"{DELE},{SEGUNDO},{TERCEIRO}",
        }
        assert recipients_from(blank_but_talkative) == (), (
            f"an empty declaration fell back to the may-talk key with {value!r}"
        )
        assert not every_recipient_is_declared([DELE], blank_but_talkative)
    #: The same with the send key absent entirely, not merely blank.
    assert recipients_from({MAY_TALK_KEY: f"{DELE},{SEGUNDO},{TERCEIRO}"}) == ()


# ---------------------------------------------------------------- the condition still SEES


def test_the_condition_asserts_the_list_and_the_count() -> None:
    """`FR-1003` — both halves, and the second catches the interesting failure."""
    environment = {RECIPIENT_KEY: f"{DELE},{SEGUNDO},{TERCEIRO}"}

    #: Exactly the declared list, in any order.
    assert every_recipient_is_declared([DELE, SEGUNDO, TERCEIRO], environment)
    assert every_recipient_is_declared([TERCEIRO, DELE, SEGUNDO], environment)

    #: **Sent to nobody** — "every recipient was declared" is vacuously true, and it must still
    #: fail. This is the half a check written only as a subset test would miss.
    assert not every_recipient_is_declared([], environment)

    #: Two of three is not the list.
    assert not every_recipient_is_declared([DELE, SEGUNDO], environment)

    #: A chat nobody declared rode along.
    assert not every_recipient_is_declared([DELE, SEGUNDO, ESTRANHO], environment)

    #: And the same person twice is not three people.
    assert not every_recipient_is_declared([DELE, DELE, SEGUNDO], environment)


def test_a_chat_outside_the_declaration_is_refused() -> None:
    """`SC-1002`. The part of `OD-7` the amendment did NOT touch."""
    environment = {RECIPIENT_KEY: f"{DELE},{SEGUNDO}"}
    assert ESTRANHO not in recipients_from(environment)
    assert not every_recipient_is_declared([ESTRANHO], environment)
    assert not every_recipient_is_declared([DELE, ESTRANHO], environment)


# ---------------------------------------------------------------- idempotency per PAIR


def test_a_recipient_who_received_it_does_not_receive_it_again(tmp_path: Path) -> None:
    """`SC-1004`, the easy direction — per person now, not per day."""
    journal = tmp_path / "runs" / "daily-report.jsonl"
    _append(journal, DELE, Outcome.SENT)

    assert already_sent(journal, CLOSED_DAY, DELE)


def test_a_recipient_who_did_NOT_receive_it_receives_it_on_the_next_run(  # noqa: N802
    tmp_path: Path,
) -> None:
    """**The direction that matters, and the one that is silent when it breaks.**

    The second of three failed. If this reads as *already sent*, the report **stops arriving for
    that person for ever** and nothing says so — idempotency turned into a block for exactly the
    recipient a failure touched.
    """
    journal = tmp_path / "runs" / "daily-report.jsonl"
    _append(journal, DELE, Outcome.SENT)
    _append(journal, SEGUNDO, Outcome.FAILED)

    assert already_sent(journal, CLOSED_DAY, DELE), "the one who received it would receive again"
    assert not already_sent(journal, CLOSED_DAY, SEGUNDO), "a failed recipient read as delivered"
    #: And the third, who has no line at all, is owed the report.
    assert not already_sent(journal, CLOSED_DAY, TERCEIRO), "a recipient with no line read as sent"


def test_the_day_is_never_answered_for_everybody_at_once(tmp_path: Path) -> None:
    """The old question, asked with three recipients, is the defect this feature exists for.

    One `sent` line used to answer *the day went*. It must not answer that for a person it does not
    name.
    """
    journal = tmp_path / "runs" / "daily-report.jsonl"
    _append(journal, DELE, Outcome.SENT)

    #: Asked without a recipient, the day did go — for somebody. That reading still exists.
    assert already_sent(journal, CLOSED_DAY)
    #: Asked about the other two, it did not.
    assert not already_sent(journal, CLOSED_DAY, SEGUNDO)
    assert not already_sent(journal, CLOSED_DAY, TERCEIRO)


def test_a_legacy_line_says_the_day_went_and_names_nobody(tmp_path: Path) -> None:
    """This replaces a node that asserted the OPPOSITE, and the replacement is the correction.

    It used to say a line with no recipient *answers for whoever asks*, and that reading was true
    while there was one recipient. With three it made the real run find zero pending and send to
    nobody. What the line proves is that **somebody** received the day; deciding it was any
    particular person is inference, and `D-28` forbids that.
    """
    journal = tmp_path / "runs" / "daily-report.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(
            line_for(instant=INSTANT, closed_day=CLOSED_DAY, outcome=Outcome.SENT, zone=SAO_PAULO)
        )

    assert anything_was_delivered(journal, CLOSED_DAY), "the day went for somebody"
    assert not already_sent(journal, CLOSED_DAY, DELE)
    assert not already_sent(journal, CLOSED_DAY, SEGUNDO)


def test_a_later_line_for_the_same_pair_wins(tmp_path: Path) -> None:
    """A recipient failed at 08:00 and got it at 12:00. **That person is done.**"""
    journal = tmp_path / "runs" / "daily-report.jsonl"
    _append(journal, SEGUNDO, Outcome.FAILED)
    _append(journal, SEGUNDO, Outcome.SENT)

    assert already_sent(journal, CLOSED_DAY, SEGUNDO)
    #: And it says nothing about anybody else.
    assert not already_sent(journal, CLOSED_DAY, TERCEIRO)


# ------------------------------------------------- os dois que faltavam, e por isso passou


def test_a_legacy_line_does_not_answer_for_an_arbitrary_recipient(tmp_path: Path) -> None:
    """**Measured in production on 2026-08-31, and the report reached nobody.**

    The real run printed *"3 declarados, 0 pendentes, todos os declarados ja receberam"* and sent
    **nothing**. The two new recipients had never received anything.

    The cause: `outcome_for` skipped a line only when it named a **different** recipient, so a line
    naming **none** answered for everybody. The comment said it "answers for whoever asks" — true
    while there was one recipient, **false the moment there were three**. A sentence that was
    correct became a defect without anybody editing it.
    """
    journal = tmp_path / "runs" / "daily-report.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(
            line_for(instant=INSTANT, closed_day=CLOSED_DAY, outcome=Outcome.SENT, zone=SAO_PAULO)
        )

    #: The day did go — for somebody. That reading is still true and still useful.
    assert already_sent(journal, CLOSED_DAY)

    #: **But it names nobody, so it proves delivery to nobody.** Three declared recipients and one
    #: legacy line cannot mean all three received it.
    for one in (DELE, SEGUNDO, TERCEIRO):
        assert not already_sent(journal, CLOSED_DAY, one), (
            f"a line naming no recipient answered YES for {one}"
        )


def test_an_already_sent_line_is_not_evidence_of_delivery(tmp_path: Path) -> None:
    """**A conclusion must never become the evidence for itself.**

    `already_sent` is what a run writes when it *read the journal and decided not to send*. It is a
    DERIVED conclusion. Counting it as delivery is how one wrong reading became permanent: the real
    run of 2026-08-31 wrote three `already_sent` lines, one per recipient, and the two who had never
    received anything acquired their own line saying they had.

    Keeping `sent` as the only proof is also what makes the damage **heal by itself**: whoever holds
    a `sent` line is not sent to again, and whoever holds only `already_sent` is still owed the
    report.
    """
    journal = tmp_path / "runs" / "daily-report.jsonl"
    _append(journal, SEGUNDO, Outcome.ALREADY_SENT)

    assert not already_sent(journal, CLOSED_DAY, SEGUNDO), (
        "an already_sent line counted as delivery, so a conclusion became its own evidence"
    )
    #: And `sent` still proves it, which is the direction that must not break.
    _append(journal, TERCEIRO, Outcome.SENT)
    assert already_sent(journal, CLOSED_DAY, TERCEIRO)


def test_a_delivery_cannot_be_buried_by_later_lines(tmp_path: Path) -> None:
    """**Measured against the real journal, and this is the second defect of 2026-08-31.**

    Three `already_sent` lines were written after the real `sent` of 06:10:10Z. Asked about the day
    as a whole, *latest wins* let them bury it, and the reading claimed **nothing was ever
    delivered** while a message had demonstrably arrived.

    For a **pair** the latest line must win — a person refused then sent is a person who received
    it. For the **day** the question is monotonic: once delivered, always delivered. One function
    answering both is the shape this repository keeps closing.
    """
    journal = tmp_path / "runs" / "daily-report.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(
            line_for(instant=INSTANT, closed_day=CLOSED_DAY, outcome=Outcome.SENT, zone=SAO_PAULO)
        )
    for one in (DELE, SEGUNDO, TERCEIRO):
        _append(journal, one, Outcome.ALREADY_SENT)

    assert anything_was_delivered(journal, CLOSED_DAY), (
        "a real delivery was buried by later already_sent lines"
    )
    #: And it says nothing about who — the three are still owed the report.
    for one in (DELE, SEGUNDO, TERCEIRO):
        assert not already_sent(journal, CLOSED_DAY, one), one

    #: A day with no `sent` line at all was never delivered, which is the other direction.
    other = tmp_path / "runs" / "outro.jsonl"
    _append(other, DELE, Outcome.REFUSED)
    assert not anything_was_delivered(other, CLOSED_DAY)
