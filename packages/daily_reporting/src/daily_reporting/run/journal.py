"""Every run recorded, and the record is what stops a day going twice — `FR-906` to `FR-908`.

## Why a run has to write anything down

`008` prints its refusals to a console. **Nobody is watching a console at three in the morning**,
and from his phone a daily refusal and a working report look identical: nothing arrives that he was
not already expecting to see. A refusal that only a console hears is a system failing silently
while behaving correctly.

## Why the same record also answers `FR-908`

The Windows Task Scheduler can start a task **more than once for one scheduled day** — the machine
is asleep at the hour and the task runs on wake, a missed run is caught up later, or he starts it
himself to watch it work. That is a property of the trigger `OD-21-B` chose, not a hypothetical.

**One record answers both questions**: what happened, and whether this closed day already went. A
record the same run also *reads* is the cheapest kind to keep honest — if it stops being written
correctly, `FR-908` stops working and a node notices.

## The four outcomes are four, and never three

`SENT`, `ALREADY_SENT`, `REFUSED` and `FAILED` are distinct **because they mean different things to
whoever reads the trigger's history**:

- a **refusal** is the system working — the warehouse had not rebuilt yet, and `008` built that
  refusal on purpose;
- a **failure** is the system broken — the credential expired, the network went, the catalog would
  not load.

Collapsing them loses exactly the distinction that tells him whether to do something. Both still
exit non-zero, so neither is ever recorded by the scheduler as a success that did nothing
(`FR-907`) — the outcome says *which*, the exit code says *not fine*.

## Why this module composes the line and does not write it — `T828`

`008`'s security suite walks this package's syntax tree and refuses `open`, `write_text`,
`write_bytes` and the yaml dumps, so that **"this feature declares no production readiness" is a
property somebody can check by reading the source** rather than a sentence somebody wrote. `d_34`
is `UNDECLARED` and stays that way.

That guard is right and this requirement fits inside it. **Every decision lives here** — what the
line says, which outcome a day ended on, whether it already went, what the process should exit
with — and the caller in the harness does the one thing that is not a decision: it appends the
string to a file. Cycle 408's lesson is that the decision must live where a node can drive it, and
none of the decisions moved.

## One line per day AND PER RECIPIENT — `FR-1005`, 2026-08-31

`OD-7` was amended: the report goes to **the declared recipients**, and there are three. The
question *already sent?* asked about a closed day alone **stops having a good answer** the moment
the second of three fails:

- read as *sent*, and the next run repeats the report for the two who already got it;
- read as *not sent*, and it repeats for them too — or the day is marked and **the person who never
  received it never will.**

**The second failure is silent**, which is what makes it the dangerous one. So the line carries the
recipient and the question is asked about the **pair**.

`recipient` is optional in the reading, and that is deliberate: the lines written before this change
carry none, and treating an old line as *nobody received it* would resend the day he already got.

## Both stamps, always

Each line carries the instant in UTC **and** the same instant in the local zone. This is the point
where `FR-905` is easiest to get wrong and hardest to notice afterwards: a run journal whose
instants are naive cannot be ordered against a rebuild that is scheduled in UTC, and the loop has
already produced clock fields that were three hours — and once ninety-five minutes — from the truth.
A naive datetime is **refused**, not assumed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date
    from pathlib import Path
    from zoneinfo import ZoneInfo

__all__ = ["Outcome", "already_sent", "exit_code", "line_for", "outcome_for"]


class Outcome(StrEnum):
    """What a run turned out to be. **Four, and a refusal is not a failure.**"""

    SENT = "sent"
    ALREADY_SENT = "already_sent"
    REFUSED = "refused"
    FAILED = "failed"


#: **Only `SENT` proves delivery.** Nothing else, and the reason cost a real run.
#:
#: ## `ALREADY_SENT` was in this set until 2026-08-31, and it is a CONCLUSION
#:
#: A run writes `ALREADY_SENT` when it read the journal and decided not to send. That is a derived
#: conclusion about the journal, **not evidence that anything arrived** — and counting it as
#: delivery is how one wrong reading became permanent.
#:
#: Measured in production that day: the run printed *"3 declarados, 0 pendentes"*, sent **nothing**,
#: and wrote three `ALREADY_SENT` lines — one each. **The two recipients who had never received
#: anything acquired their own line saying they had.** A conclusion had become the evidence for
#: itself, and the next run would have read it as settled for ever.
#:
#: `ALREADY_SENT` remains a valid outcome and still exits zero: a run that correctly did nothing is
#: not a failure. It simply proves no arrival. **And that is what makes the damage heal by itself**:
#: whoever holds a `SENT` line is not sent to again, and whoever holds only `ALREADY_SENT` is still
#: owed the report.
#:
#: `REFUSED` was never in here, for the same family of reason: a day refused for want of a rebuild
#: is a day still owed.
_DELIVERED = frozenset({Outcome.SENT})


#: The outcomes that are **not a failure**, which is a DIFFERENT question from whether anything
#: arrived. `_DELIVERED` answered both until 2026-08-31, and that is one key over two questions --
#: the same shape as the recipient key of 2026-08-30, arriving inside this module.
#:
#: `ALREADY_SENT` belongs here and **not** in `_DELIVERED`: a run that correctly did nothing is not
#: a failure, and it is also not proof that anything was received.
_NOT_A_FAILURE = frozenset({Outcome.SENT, Outcome.ALREADY_SENT})


def exit_code(outcome: Outcome) -> int:
    """`FR-907` — non-zero for anything that did not put the report in front of him.

    The scheduler's history is the only place some of these are ever read, and there a zero means
    *fine*. A refusal is not fine; it is correct, which is a different word.

    **Read from `_NOT_A_FAILURE`, never from `_DELIVERED`.** Whether an outcome is a failure and
    whether it proves arrival are two questions, and one set answering both is what let a
    conclusion become its own evidence.
    """
    return 0 if outcome in _NOT_A_FAILURE else 1


def line_for(
    *,
    instant: datetime,
    closed_day: date,
    outcome: Outcome,
    zone: ZoneInfo,
    recipient: str = "",
    reason: str = "",
    message_id: int | None = None,
) -> str:
    """One journal line, with **both** stamps — `FR-906`, `FR-905`.

    Returns the text; **appending it is the caller's job** (`T828`, above). ``instant`` must carry
    a zone: assuming a naive datetime is UTC is how an instant three hours off gets written into a
    record nobody re-reads until it matters.
    """
    if instant.tzinfo is None:
        message = "instant carries no zone; refusing to assume one"
        raise ValueError(message)

    utc = instant.astimezone(UTC)
    line = {
        "instant": utc.isoformat(),
        "local": utc.astimezone(zone).isoformat(),
        "closed_day": closed_day.isoformat(),
        "recipient": recipient,
        "outcome": str(outcome),
        "reason": reason,
        "message_id": message_id,
    }
    return json.dumps(line, ensure_ascii=False) + "\n"


def _lines_of(path: Path) -> list[dict[str, Any]]:
    """Every readable line of the journal, in order. A torn line is skipped and not an answer."""
    if not path.exists():
        return []
    found: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            line: object = json.loads(raw)
        except json.JSONDecodeError:  # pragma: no cover - a torn line is not an answer
            continue
        if isinstance(line, dict):
            found.append(cast("dict[str, Any]", line))
    return found


def outcome_for(path: Path, closed_day: date, recipient: str | None = None) -> Outcome | None:
    """The **latest** outcome for that closed day — for ``recipient`` when one is given.

    Latest and not first: a day refused at `04:00` and sent at `09:00` is a day that went, and a
    journal read the other way round would send it twice.

    With ``recipient``, only that pair's lines answer — and a line naming **no** recipient answers
    only the question asked without one. See `_DELIVERED` and the loop below: both halves of the
    2026-08-31 defect are recorded there, and both cost a run that reached nobody.
    """
    wanted = closed_day.isoformat()
    found: Outcome | None = None
    for line in _lines_of(path):
        if line.get("closed_day") != wanted:
            continue
        #: **A line naming no recipient answers ONLY the question asked without one.**
        #:
        #: It said "it answers for whoever asks", and that was true while there was one recipient.
        #: With three it became the defect that sent the report to nobody: the legacy `sent` line of
        #: 06:09Z answered YES for all three, so the run found zero pending. A sentence that was
        #: correct turned false without anybody editing it — the declaration around it changed.
        #:
        #: What the line actually proves is that **somebody** received the day. Deciding it was any
        #: particular person would be filling a gap by inference, which is what `D-28` forbids.
        written = line.get("recipient") or ""
        if recipient is not None and written != recipient:
            continue
        try:
            found = Outcome(line.get("outcome"))
        except ValueError:  # pragma: no cover - an outcome nobody defined is not an answer
            continue
    return found


def anything_was_delivered(path: Path, closed_day: date) -> bool:
    """Did **any** delivery of ``closed_day`` ever happen? — and this one is MONOTONIC.

    ## Why this is not `outcome_for(path, day)`

    For a **pair**, the latest line wins: a person refused at 08:00 and sent at 12:00 is a person
    who received it, and their state evolves. For the day **as a whole** the question is different
    — *was this ever delivered to anybody* — and the answer, once true, cannot become false.

    Measured against the real journal on 2026-08-31: `outcome_for(path, day)` answered
    **`already_sent`**, because three `already_sent` lines were written after the real `sent` of
    06:10:10Z and *latest wins* let them bury it. So the reading claimed **nothing was ever
    delivered** while a message had demonstrably arrived. **Latest-wins destroys evidence when the
    question is monotonic**, which is one more shape of one function answering two questions.
    """
    for line in _lines_of(path):
        if line.get("closed_day") != closed_day.isoformat():
            continue
        try:
            if Outcome(line.get("outcome")) is Outcome.SENT:
                return True
        except ValueError:  # pragma: no cover - an outcome nobody defined is not an answer
            continue
    return False


def already_sent(path: Path, closed_day: date, recipient: str | None = None) -> bool:
    """`FR-908`, `FR-1006` — has this closed day already reached ``recipient``?

    **A refusal does not count**, and that is the whole direction of this function that a
    tautological node would miss: a day nobody could send yet is a day still to send. With three
    recipients the same sentence holds **per person**: whoever did not receive it receives it on the
    next run, or idempotency has become a block for exactly the person a failure touched.
    """
    return outcome_for(path, closed_day, recipient) in _DELIVERED
