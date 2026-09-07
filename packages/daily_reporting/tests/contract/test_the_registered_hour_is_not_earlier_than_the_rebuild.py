"""`T904`, `SC-901` — the registered hour is never earlier than the rebuild it waits for.

## What the first version of this node got wrong, all three of them

It was written in this file, parsing the document here, and it asked three questions that were the
wrong questions. The reviewing agent drove them and found:

- **`S-17`** — it asserted the hour **equals** the floor. `09:00`, which is after the floor and
  perfectly safe, lit it. **A guard that fires when the owner exercises his own choice is a guard
  somebody silences**, and the document's own line says any hour from the floor onward serves.
- **`S-18`** — it read the field and never the `schtasks` command. Moving `/ST` to `03:00` while
  leaving the field at `04:00` left **199 passed, all green**. The field is the label; the command
  is the act, and the command is what he copies.
- **`S-19`** — `registrado_no_agendador` flipped from `NAO` to `SIM` with nothing registered and
  stayed green, because the node checked only that the value was readable.

The predicates now live in `daily_reporting.schedule.record`, so each one is driven **against
synthetic input in every direction** rather than against today's file agreeing with itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from daily_reporting.schedule.derive import AdmissibleStart, earliest_admissible
from daily_reporting.schedule.record import (
    MISSING,
    command_block,
    hour_is_admissible,
    missing_registration_fields,
    parse_fields,
    registered_clock_in_command,
    with_command_hour,
)

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
RECORD = REPO / "docs" / "registro-do-agendamento-diario.md"


def _text() -> str:
    assert RECORD.is_file(), f"{RECORD} is missing; regenerate it with write_schedule_record.py"
    return RECORD.read_text(encoding="utf-8")


def _record() -> dict[str, str]:
    fields = parse_fields(_text())
    assert fields, "the record carries no measured block; this node would forbid nothing"
    return fields


def _floor() -> tuple[datetime, AdmissibleStart]:
    fields = _record()
    finished = datetime.fromisoformat(fields["reconstrucao_medida_utc"])
    zone = ZoneInfo(fields["fuso_do_agendador"])
    return finished, earliest_admissible(finished, zone=zone)


def test_the_record_carries_every_field_this_node_needs() -> None:
    """A record missing a field would make the assertions below vacuously true."""
    fields = _record()
    for name in (
        "reconstrucao_medida_utc",
        "reconstrucao_medida_local",
        "piso_derivado_utc",
        "piso_derivado_local",
        "piso_local",
        "hora_do_gatilho",
        "fuso_do_agendador",
        "registrado_no_agendador",
        "nome_da_tarefa_registrada",
        "instante_do_registro",
    ):
        assert name in fields, f"the record does not carry {name}"
    #: Every instant in it carries a zone — `FR-905`, asserted where it is written down.
    for name in ("reconstrucao_medida_utc", "reconstrucao_medida_local", "piso_derivado_local"):
        assert datetime.fromisoformat(fields[name]).utcoffset() is not None, name


def test_the_derived_floor_in_the_record_is_the_floor_the_package_derives() -> None:
    """The **floor** is a derivation and must match exactly — this is not his choice.

    Only `hora_do_gatilho` is his to raise. The floor is what the rule answers, and a document
    claiming a different floor is claiming a different measurement.
    """
    finished, floor = _floor()
    fields = _record()
    assert datetime.fromisoformat(fields["piso_derivado_utc"]) == floor.utc
    assert datetime.fromisoformat(fields["piso_derivado_local"]) == floor.local
    assert fields["piso_local"] == floor.local_clock
    assert floor.utc > finished


def test_the_predicate_is_not_earlier_and_not_equal() -> None:
    """**`S-17`, driven in three directions.**

    The floor is the earliest hour that is safe, so every hour from it onward is safe. The day he
    picks `08:00` nothing here may go red.
    """
    _, floor = _floor()
    at_the_floor = floor.local_clock

    #: Before the floor: the run meets the view without the closed day and refuses, every day.
    earlier = (floor.local - timedelta(hours=1)).strftime("%H:%M")
    assert not hour_is_admissible(earlier, floor_clock=at_the_floor), earlier

    #: The floor itself passes.
    assert hour_is_admissible(at_the_floor, floor_clock=at_the_floor)

    #: And so does every hour after it — HIS choice, and it must cost nothing.
    for later in ("08:00", "09:00", "13:30", "23:59"):
        assert hour_is_admissible(later, floor_clock=at_the_floor), later


def test_the_command_carries_the_hour_and_not_only_the_field() -> None:
    """**`S-18`** — the `/ST` of the command is the act, and it is checked as the act.

    Moving the command while leaving the field alone was green before this node existed.
    """
    text = _text()
    assert "Register-ScheduledTask" in text, "the record does not carry the command"

    in_command = registered_clock_in_command(command_block(text))
    assert in_command is not None, "the command carries no hour"

    fields = _record()
    _, floor = _floor()

    #: The command and the field must say the SAME hour. They diverged in silence before.
    assert in_command == fields["hora_do_gatilho"], (
        f"the field says {fields['hora_do_gatilho']} and the command says {in_command}"
    )
    #: And the command's own hour is not earlier than the floor.
    assert hour_is_admissible(in_command, floor_clock=floor.local_clock), in_command


def test_a_command_before_the_floor_is_refused_whatever_the_field_says() -> None:
    """The mutation that used to pass, driven here so it cannot pass again."""
    _, floor = _floor()
    earlier = (floor.local - timedelta(hours=1)).strftime("%H:%M")

    #: **Tamper from the hour the command ACTUALLY carries**, not from the floor. Assuming those
    #: two are the same is the very thing `S-17` is about: the day he raises the trigger they part
    #: company, and a test built on the floor would break on his choice rather than on a defect.
    current = registered_clock_in_command(command_block(_text()))
    assert current is not None, "the command carries no hour"
    tampered = with_command_hour(_text(), earlier)
    assert tampered != _text(), "the command's hour was not found; the mutation proves nothing"

    in_command = registered_clock_in_command(command_block(tampered))
    assert in_command is not None and in_command == earlier
    #: **Both halves catch it**: it disagrees with the field, and it is earlier than the floor.
    assert in_command != parse_fields(tampered)["hora_do_gatilho"]
    assert not hour_is_admissible(in_command, floor_clock=floor.local_clock)


def _with_trigger_at(clock: str) -> str:
    """The record as it would read with the trigger at ``clock``, field and command together.

    **Both substitutions start from the hour the document ACTUALLY carries**, never from the floor.
    Assuming those two coincide is what made the previous version of this node pass for exactly one
    hour: with the document at `06:00` the replacement found nothing, and the node then compared the
    real hour against a constant written in the test.
    """
    text = _text()
    current_field = parse_fields(text)["hora_do_gatilho"]
    current_command = registered_clock_in_command(command_block(text))

    assert current_command is not None
    changed = with_command_hour(
        text.replace(f"- `hora_do_gatilho`: {current_field}", f"- `hora_do_gatilho`: {clock}"),
        clock,
    )
    assert parse_fields(changed)["hora_do_gatilho"] == clock, "the field was not moved"
    assert registered_clock_in_command(command_block(changed)) == clock, "the command was not moved"
    return changed


def _hours_after(floor_clock: str, *, count: int) -> list[str]:
    """``count`` distinct hours strictly after the floor, **derived from it**.

    One hour would not distinguish deriving from guessing right, which is why there are several and
    why none of them is written down.
    """
    hour, minute = (int(part) for part in floor_clock.split(":"))
    found = [f"{(hour + step) % 24:02d}:{minute:02d}" for step in range(1, count + 1)]
    assert len(set(found)) == count, found
    return found


def test_every_hour_from_the_floor_onward_is_his_and_costs_nothing() -> None:
    """**`S-17`, and it survived one cycle in a narrower form.**

    The first version fixed `08:00` as a constant and substituted it for the FLOOR's hour. Driven
    with `06:00` and `09:00` it went red — so **the node that exists to prove his choice breaks
    nothing broke on every choice except one.** It did not die in the 418 fix; it got narrower:
    from "any hour but the floor" to "any hour but 08:00".

    The hours here are **derived from the floor** and there are several, because one would not
    distinguish deriving from happening to guess right.
    """
    _, floor = _floor()

    #: The floor itself, and then several hours above it. None of these is a written constant.
    for clock in [floor.local_clock, *_hours_after(floor.local_clock, count=5)]:
        chosen = _with_trigger_at(clock)
        fields = parse_fields(chosen)

        #: The floor is untouched — it is not his to move.
        assert fields["piso_local"] == floor.local_clock, clock
        #: His hour is in both places, and they agree.
        assert (
            registered_clock_in_command(command_block(chosen)) == fields["hora_do_gatilho"] == clock
        )
        #: And nothing objects.
        assert hour_is_admissible(fields["hora_do_gatilho"], floor_clock=fields["piso_local"]), (
            clock
        )
        assert missing_registration_fields(fields) == [], clock


def test_the_three_hours_the_reviewer_measured_all_pass() -> None:
    """His measurement, kept as a node so the regression cannot come back quietly.

    `06:00`, `08:00` and `09:00` lit the previous version; only `08:00` passed. All three are after
    the derived floor of `04:00` and all three are safe.
    """
    _, floor = _floor()
    for clock in ("06:00", "08:00", "09:00"):
        assert hour_is_admissible(clock, floor_clock=floor.local_clock), clock
        fields = parse_fields(_with_trigger_at(clock))
        assert registered_clock_in_command(command_block(_with_trigger_at(clock))) == clock
        assert hour_is_admissible(fields["hora_do_gatilho"], floor_clock=fields["piso_local"]), (
            clock
        )


def test_an_hour_before_the_floor_is_still_refused_in_both_places() -> None:
    """The other side of the same predicate, so widening it did not open it."""
    _, floor = _floor()
    hour, minute = (int(part) for part in floor.local_clock.split(":"))
    earlier = f"{(hour - 1) % 24:02d}:{minute:02d}"

    fields = parse_fields(_with_trigger_at(earlier))
    assert fields["piso_local"] == floor.local_clock
    assert not hour_is_admissible(fields["hora_do_gatilho"], floor_clock=fields["piso_local"])


def test_the_registration_claim_is_coherent_in_both_directions() -> None:
    """`S-19` + `S-25` — the node asserts COHERENCE, never today's state.

    ## What this replaced, and why it went red on the right day for the wrong reason

    Until 2026-08-31 this asserted `registrado_no_agendador == "NAO"` with the comment *"Today:
    nothing is registered"*. True on the day it was written, false the instant the owner's chosen
    registration ACTUALLY HAPPENED (task `Ready`, `StartWhenAvailable=True`, next run 09-01 08:00,
    measured in Windows). Same family as *"Os vinte indicadores"*: a label true by accident of the
    calendar. **A node must assert what cannot legitimately change, not what happened to be true.**

    What cannot change: `SIM` costs the after-the-fact fields, `NAO` forbids them, and an instant,
    when present, carries its zones. The REAL document of today must pass whichever state it is in.
    """
    fields = _record()

    #: The real document, whichever state it is in, is coherent.
    assert fields["registrado_no_agendador"] in {"NAO", "SIM"}
    assert missing_registration_fields(fields) == [], (
        "the real record claims SIM without the fields that only exist after registering"
    )
    if fields["registrado_no_agendador"] == "NAO":
        for name in ("nome_da_tarefa_registrada", "instante_do_registro"):
            assert fields[name] == MISSING, f"{name} carries a value while claiming NAO"
    else:
        #: A recorded instant carries both zones — `FR-905` at the one field written by hand.
        assert "-03:00" in fields["instante_do_registro"], fields["instante_do_registro"]
        assert "UTC" in fields["instante_do_registro"], fields["instante_do_registro"]

    #: **Direction one**: `SIM` with nothing behind it is refused — the `S-19` mutation.
    claimed = {
        **fields,
        "registrado_no_agendador": "SIM",
        "nome_da_tarefa_registrada": MISSING,
        "instante_do_registro": MISSING,
    }
    assert len(missing_registration_fields(claimed)) == 2

    #: Half a claim is still a claim.
    half = {**claimed, "nome_da_tarefa_registrada": "Relatorio diario"}
    assert missing_registration_fields(half) == ["instante_do_registro"]

    #: **Direction two**: an honest `SIM` is accepted — the day of the registration, and every day
    #: after it, this must not block.
    honest = {
        **claimed,
        "nome_da_tarefa_registrada": "Relatorio diario",
        "instante_do_registro": "2026-08-31T14:03:24-03:00 (UTC 2026-08-31T17:03:24+00:00)",
    }
    assert missing_registration_fields(honest) == []


def test_the_record_says_the_hour_is_a_floor_and_who_registers() -> None:
    """The two sentences a person reads first, asserted so they cannot quietly leave.

    The second changed with `S-25`: *"NÃO registrou nada"* was STATE — true until the owner's
    registration happened — and became *"não registra por conta própria"*, which is the RULE and
    survives the act. A sentence that expires with the calendar does not belong in a node.

    (And this node itself was silently deleted by the splice that fixed `S-25`, caught because the
    prose mutation stayed green: a guard that vanishes fails nothing, which is the invisible-skip
    lesson wearing yet another coat.)
    """
    text = _text()
    assert "PISO DE SEGURANÇA" in text
    assert "não registra por conta própria" in text


def test_the_command_carries_what_the_document_claims_it_does() -> None:
    """`OD-56` — **a late run must go out as soon as the machine comes back**, and the command has
    to be able to do that.

    ## The gap this closes, found by driving

    Removing `-StartWhenAvailable` from the generated command left **202 passed**. The document
    would then have described `OD-56`'s behaviour beside a command that does not have it — a label
    asserting more than the thing it labels, which is the family this whole feature hunted. The
    owner named the risk in the decision itself, and the node was missing.

    Measured 2026-08-31 on this machine: `schtasks /Create /?` never mentions `StartWhenAvailable`,
    while `New-ScheduledTaskSettingsSet` carries it as a real parameter and building the object
    returned `StartWhenAvailable=True` **without registering anything**. That is why the form
    changed, and this node is what keeps it changed.
    """
    text = _text()
    #: **The COMMAND, not the document.** Asserting over the whole page let the prose answer for
    #: the command: with `-StartWhenAvailable` deleted from the command, a table row explaining the
    #: flag kept this green. The label answering for the act, for the fourth time.
    command = command_block(text)
    assert command, "the record carries no fenced command; nothing here would be checked"

    #: The registration itself, and the four pieces the cmdlet form needs.
    for piece in (
        "New-ScheduledTaskAction",
        "New-ScheduledTaskTrigger",
        "New-ScheduledTaskSettingsSet",
        "Register-ScheduledTask",
    ):
        assert piece in command, f"the command lost {piece}"

    #: **The setting `OD-56` is about.** Without it the run missed while the machine was off never
    #: happens at all, and the document would be claiming otherwise.
    assert "-StartWhenAvailable" in command, (
        "the command does not carry -StartWhenAvailable, so a missed run would never be made up "
        "and the document claims it would"
    )

    #: And the reason stays on the page — in the PROSE this time, which is where it belongs — so
    #: nobody puts `schtasks` back without reading why it went.
    assert "schtasks" in text, "the record does not say which form was rejected and why"
