"""Reading the schedule record, and the three things the first node got wrong — `S-17` to `S-19`.

## Why this is in the package and not in the test

The first version of `T904` parsed the document inside the test file and asked it three questions
that all turned out to be the wrong questions. Putting the predicates here means a node can drive
**each one against synthetic input in every direction**, instead of asserting that today's file
agrees with itself — which is cycle 408's lesson, arriving for the third time.

## `S-17` — the predicate is NOT EARLIER, never EQUAL

The first node asserted the registered hour **equals** the derived floor. The document itself says
*"qualquer hora depois do piso serve"*, and `FR-903` asks for an hour **after the rebuild**, not for
the floor exactly. So the node would have gone red on the day he chose to receive the report at
`08:00` — **a guard that fires when the owner exercises his own choice is a guard somebody
silences**, and then it protects nothing at all.

## `S-18` — the field is the label, the command is the ACT

The record carries the trigger's hour twice: as `hora_do_gatilho`, and inside the `schtasks`
`/ST`. The first node read only the field. Moving the command to `/ST 03:00` while leaving the field
at `04:00` left every suite green — **and the command is the thing he copies and pastes.** The label
matching while the act does not is the exact defect this whole feature has hunted, reappearing in
the guard written to catch it.

## And a field name that did not match what it held

The first attempt at the fix called the trigger's hour `hora_registrada_local` while it held the
**floor**, which is a label not matching its content — the very defect this feature spent itself
hunting, produced while fixing a guard against it. Two fields now, and the difference is who
decides: `piso_local` is **derived** and matched for equality; `hora_do_gatilho` is what the
command's `/ST` carries, and only ever checked as **not earlier**.

## `S-19` — `SIM` has to cost something

`registrado_no_agendador` went from `NAO` to `SIM` with nothing registered, and stayed green: the
node checked only that the value was readable. A field that can be flipped for free is prose
wearing the shape of data, and `T913` rests on it alone. So `SIM` now requires the fields that can
only exist **after** a registration — the task's name and the instant — and `SIM` without them is
refused.

**None of this asks the test to talk to Windows.** It asks the claim to be expensive.
"""

from __future__ import annotations

import re

__all__ = [
    "MISSING",
    "command_block",
    "hour_is_admissible",
    "missing_registration_fields",
    "parse_fields",
    "registered_clock_in_command",
    "with_command_hour",
]

#: The generator writes the machine-readable fields between these markers.
_BLOCK = re.compile(r"<!-- medido: inicio -->(.*?)<!-- medido: fim -->", re.S)
_FIELD = re.compile(r"^- `([a-z_]+)`: (.+)$", re.M)

#: The fenced block the record puts the registration command in. **Asserting over the whole
#: document lets the PROSE satisfy a check meant for the COMMAND**: removing `-StartWhenAvailable`
#: from the command left the node green, because a table row explaining the flag still mentioned it.
#: `S-18` for the fourth time, and the shape never changes: the label answering for the act.
_COMMAND_BLOCK = re.compile(r"```powershell(.*?)```", re.S)

#: What the registration command carries as the hour, **in either form the record may use**.
#:
#: `OD-56` changed the form: `schtasks /Create` does **not** expose `StartWhenAvailable`, measured
#: from its own help on 2026-08-31, so the command became `New-ScheduledTaskTrigger -At HH:MM`. A
#: pattern that only knew `/ST` would have stopped guarding **silently** at that moment — the `S-18`
#: defect returning through the door the fix left open.
_START_TIME = re.compile(r"(?:/ST\s+|-At\s+)(\d{1,2}:\d{2})")

#: A field with no value yet. Written out rather than left blank, so that "not filled" is a value
#: somebody can see and a node can refuse.
MISSING = "-"

#: The fields that cannot exist before a registration happened on his machine.
_ONLY_AFTER_REGISTERING = (
    "nome_da_tarefa_registrada",
    "instante_do_registro",
)


def parse_fields(text: str) -> dict[str, str]:
    """The measured block, as ``{field: value}``. Empty when the block is absent."""
    found = _BLOCK.search(text)
    if not found:
        return {}
    return {name: value.strip() for name, value in _FIELD.findall(found.group(1))}


def registered_clock_in_command(text: str) -> str | None:
    """The hour the registration command actually carries, or ``None`` if it carries none.

    **`S-18`.** This is the hour that runs on his machine, because this is the line he copies. A
    record whose field and whose command disagree is a record that reads correct and acts wrong.
    """
    found = _START_TIME.search(text)
    if not found:
        return None
    hour, minute = found.group(1).split(":")
    return f"{int(hour):02d}:{minute}"


def hour_is_admissible(clock: str, *, floor_clock: str) -> bool:
    """Is ``clock`` **not earlier** than the floor, both as local `HH:MM`? — `S-17`, `FR-903`.

    Not *equal*: the floor is the earliest hour that is safe, and every hour after it is safe too.
    His preference lives above the floor and moving it must not fail anything.

    Earlier is the only thing refused, and a daily trigger before the floor means the run meets the
    view without the closed day, refuses, and the report never arrives.
    """
    return _minutes(clock) >= _minutes(floor_clock)


def missing_registration_fields(fields: dict[str, str]) -> list[str]:
    """Which of the after-the-fact fields a `SIM` is claiming without carrying — `S-19`.

    Empty for `NAO`, because nothing is claimed. For `SIM`, every field that only exists after a
    registration must carry a value: `SIM` has to cost something, or it is a flag anybody can flip.
    """
    if fields.get("registrado_no_agendador") != "SIM":
        return []
    return [
        name
        for name in _ONLY_AFTER_REGISTERING
        if not fields.get(name) or fields.get(name) == MISSING
    ]


def _minutes(clock: str) -> int:
    hour, minute = (int(part) for part in clock.split(":"))
    return hour * 60 + minute


def with_command_hour(text: str, clock: str) -> str:
    """``text`` with the command's hour rewritten to ``clock``, **using the reader's own pattern**.

    ## Why a writer at all, instead of a `str.replace` at each call site

    `OD-56` changed the command from `schtasks /Create /ST HH:MM` to
    `New-ScheduledTaskTrigger -At HH:MM`, because `schtasks` does not expose
    `StartWhenAvailable`. The reader followed. **Three test helpers did not**: each had the literal
    `/ST` written inside it, so their substitutions silently found nothing and their assertions
    started comparing the real hour against an hour that was never written.

    That is the same class as `S-18` — a guard bound to the FORM of the artefact rather than to what
    it means — arriving for the third time, now inside the fix for it. So reader and writer share
    one pattern and a change of form cannot desynchronise them again.
    """
    return _START_TIME.sub(lambda match: match.group(0).replace(match.group(1), clock), text)


def command_block(text: str) -> str:
    """The registration command alone, without the prose that explains it.

    Empty when the record carries no fenced command — which a node must then refuse rather than
    read as *nothing wrong here*.
    """
    found = _COMMAND_BLOCK.search(text)
    return found.group(1) if found else ""
