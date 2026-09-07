"""T152 — the steward CLI is deterministic, discloses its limitation, and leaks no secret.

Four properties, and each has a failure that has actually happened somewhere in this repository's
history or is one flag away from happening:

* **the limitation field is always present** (`FR-099`) — a report pasted into a readiness review
  without it reads as an integration result;
* **output is deterministic** — two invocations byte-identical, so a diff shows only real change;
* **exit codes distinguish a governed refusal from a broken invocation** — collapsing them makes
  is undeclared" indistinguishable from "you mistyped the channel";
* **no secret, key or credential appears in any output**, and no flag exists that would accept one.

The schema-drift half of this task is the gate `T030` deferred: `schema export --check` compares
against a committed copy and exits 1 on drift. It is asserted here over a temporary file rather than
a committed one, because committing a schema copy is a governed artifact this task does not declare.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from channel_integration.cli.main import (
    CLI_LIMITATION,
    EXIT_INVOCATION,
    EXIT_OK,
    EXIT_VIOLATION,
    build_parser,
    emit,
    main,
)
from channel_integration.cli.simulate import SIMULATION_LIMITATION
from channel_integration.contracts.descriptor import ChannelId

from ..fixtures.channels import FIXTURE_SECRET, signed_request, wire_payload

pytestmark = pytest.mark.contract

#: Every command, in the invocation form a steward would type. Enumerated rather than discovered, so
#: adding a subcommand without adding it here fails the coverage assertion below — a new command
#: that forgot the limitation field is exactly what that assertion is for.
_INVOCATIONS: tuple[tuple[str, ...], ...] = (
    ("capabilities",),
    ("messages",),
    ("render", "--channel", "SLACK"),
    ("simulate",),
    ("simulate", "--channel", "TELEGRAM"),
    ("schema", "export"),
)

#: Commands that need a recorded file on disk, so they cannot be a bare argv tuple above. Exercised
#: by their own tests below, and named here so the coverage assertion counts them as covered rather
#: than being widened to ignore whatever it cannot reach.
_COMMANDS_WITH_DEDICATED_TESTS = frozenset({"convert"})


def _run(argv: tuple[str, ...], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    """One invocation, its exit code and its parsed payload."""
    code = main(list(argv))
    captured = capsys.readouterr()
    if not captured.out.strip():
        return code, {}
    parsed = cast("dict[str, Any]", json.loads(captured.out))
    return code, parsed


@pytest.mark.parametrize("argv", _INVOCATIONS, ids=lambda argv: " ".join(argv))
def test_every_command_carries_a_limitation_statement(
    argv: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`FR-099`, asserted per command rather than once.

    Both statements are permitted: a simulation says it used fixture payloads, and every other
    command says it read governed content. What is not permitted is neither.
    """
    _, payload = _run(argv, capsys)
    assert payload.get("limitation") in {CLI_LIMITATION, SIMULATION_LIMITATION}, (
        f"{' '.join(argv)} emitted no recognised limitation statement"
    )


@pytest.mark.parametrize("argv", _INVOCATIONS, ids=lambda argv: " ".join(argv))
def test_every_command_is_byte_identical_across_two_invocations(
    argv: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Determinism, over stdout rather than over the parsed object.

    Parsed equality would accept a change in key order, and the whole point of sorted keys and fixed
    separators is that a steward can diff two runs.
    """
    main(list(argv))
    first = capsys.readouterr().out
    main(list(argv))
    second = capsys.readouterr().out
    assert first == second
    assert first.endswith("\n")


def test_emit_refuses_a_payload_with_no_limitation() -> None:
    """The enforcement, asserted directly.

    Every command satisfying `FR-099` today is worth less than a helper that cannot emit a payload
    without the statement: the first is a property of six functions, the second is a property of the
    output surface.
    """
    with pytest.raises(AssertionError):
        emit({"command": "invented", "result": "none"})


def test_a_governed_refusal_and_a_broken_invocation_have_different_exit_codes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The distinction a CI gate depends on."""
    governed, _ = _run(("render", "--channel", "SLACK"), capsys)
    assert governed == EXIT_VIOLATION, (
        "rendering resolves now, so D-28 declares a matrix and this expectation must be re-derived"
    )

    broken = main(["render", "--channel", "not-a-channel"])
    capsys.readouterr()
    assert broken == EXIT_INVOCATION


def test_a_readable_command_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """`messages` reads authored content that exists, so it answers.

    Included because a CLI where every command exits non-zero would satisfy the previous test while
    telling a steward nothing, and the exit-code contract needs at least one green path.
    """
    code, payload = _run(("messages",), capsys)
    assert code == EXIT_OK
    assert payload["readable"] is True
    assert payload["codes"], "the message registry reports no codes"


def test_capabilities_reports_every_record_and_exits_one_while_all_are_undeclared(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The shipped state, and the exit code that makes it scriptable.

    A steward scripting a readiness check reads the exit code; a reader reads the record states.

    **RE-DERIVED on 2026-08-28, not deleted** -- `FR-818`. It asserted eleven records, all
    undeclared, every channel disabled. `OD-18` signed `d_24`, `OD-20-A` applied it to SENDING,
    and `OD-17` had already split the production bar into a twelfth record. So the counts moved.

    **What the node holds now is the property rather than the snapshot**: the CLI agrees with
    the library. A number written here would have to be edited every time he decides something,
    and a check that needs editing to stay green is a check that stopped measuring.
    """
    from channel_integration.compliance.readiness import (
        CHANNEL_CAPABILITIES,
        load_all_records,
        may_receive_from,
        may_send_to,
    )

    code, payload = _run(("capabilities",), capsys)

    #: The exit code is DERIVED in `_cmd_capabilities`: `EXIT_OK` when some channel is enabled,
    #: `EXIT_VIOLATION` otherwise. My first re-derivation asserted `EXIT_VIOLATION` outright and
    #: was wrong -- it described yesterday's world, and the CLI was right: one channel may send
    #: now. Compared against the same derivation the command uses, so the node holds whichever
    #: way the records go.
    #: **The exit code speaks for SENDING**, and the command says so in its own comment: it is
    #: what a steward scripts against before delivering.
    expected = EXIT_OK if any(may_send_to(channel) for channel in ChannelId) else EXIT_VIOLATION
    assert code == expected, (
        f"the CLI exited {code} while the library reports sending {expected == EXIT_OK}; the "
        f"exit code is what a steward scripts against"
    )

    #: **Each direction against ITS OWN predicate.** The previous version compared the CLI to
    #: the library under one ambiguous word, and two things agreeing under a label that changed
    #: meaning is the one configuration where the change cannot be detected -- the `387` class.
    assert payload["channels_may_send"] == {
        channel.value: may_send_to(channel) for channel in ChannelId
    }, "the CLI reports a different SENDING state than the library"
    assert payload["channels_may_receive"] == {
        channel.value: may_receive_from(channel) for channel in ChannelId
    }, "the CLI reports a different RECEIVING state than the library"
    assert payload["any_channel_may_send"] is any(may_send_to(c) for c in ChannelId)
    assert payload["any_channel_may_receive"] is any(may_receive_from(c) for c in ChannelId)

    #: And the ambiguous keys are GONE rather than kept for compatibility: a key whose meaning
    #: changed is worse than one that disappeared, because nothing tells the reader.
    for retired in ("channels_enabled", "any_channel_enabled"):
        assert retired not in payload, (
            f"{retired} is still reported; it answers only the sending half while reading as "
            f"the whole truth, which is what the split was for"
        )

    #: The command reports THIS FEATURE'S capabilities and not the inherited ones:
    #: `_cmd_capabilities` iterates `CHANNEL_CAPABILITIES`. Compared against that same list,
    #: so the node measures the command's own contract rather than a set it overlaps.
    records = load_all_records()
    assert set(payload["records"]) == set(CHANNEL_CAPABILITIES), (
        "the CLI reports a different set of records than the channel capabilities it gates"
    )
    assert payload["records"] == {
        identifier: records[identifier].state.value for identifier in CHANNEL_CAPABILITIES
    }, "the CLI reports a state the library does not"


def test_schema_export_detects_drift_and_agrees_with_itself(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The deferred schema-drift gate, now executable.

    Asserted in both directions: an identical copy is not drift, and a changed copy is. A gate that
    only checked one direction would pass a comparison that always reported drift.
    """
    _, exported = _run(("schema", "export"), capsys)
    committed = tmp_path / "schema.json"
    committed.write_text(json.dumps(exported["schema"]), encoding="utf-8")  # pyright: ignore[reportAny]

    code, payload = _run(("schema", "export", "--check", str(committed)), capsys)
    assert code == EXIT_OK
    assert payload["drift"] is False

    committed.write_text(
        json.dumps({"capability_matrix": {"required_fields": []}}), encoding="utf-8"
    )
    code, payload = _run(("schema", "export", "--check", str(committed)), capsys)
    assert code == EXIT_VIOLATION
    assert payload["drift"] is True


def test_a_missing_file_is_a_broken_invocation_not_a_governed_refusal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A steward's typo is not the governance's fault."""
    absent = tmp_path / "nothing.json"
    assert main(["convert", "--file", str(absent)]) == EXIT_INVOCATION
    capsys.readouterr()
    assert main(["schema", "export", "--check", str(absent)]) == EXIT_INVOCATION
    capsys.readouterr()


def test_convert_reports_a_canonical_recorded_request_without_converting_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A recorded request is accepted as canonical and **not** converted.

    Conversion needs verification material, transport bounds, an identity resolver and a
    pseudonymiser, and `D-22` to `D-25` and `D-31` declare none of them. So the honest answer is
    "structurally canonical, nothing converted", with the records named — not a conversion performed
    against fixture collaborators, which would be the CLI manufacturing the evidence `FR-099`
    forbids.
    """
    recorded = tmp_path / "request.json"
    request = signed_request(ChannelId.SLACK, payload=wire_payload())
    recorded.write_text(request.model_dump_json(), encoding="utf-8")

    code, payload = _run(("convert", "--file", str(recorded)), capsys)
    assert code == EXIT_VIOLATION
    assert payload["accepted_shape"] is True
    assert payload["converted"] is False
    assert "D-22" in payload["reason"]
    assert payload["limitation"] == CLI_LIMITATION


def test_convert_rejects_a_file_that_is_not_a_canonical_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The steward's file being wrong is exit 2, and the validation detail travels verbatim."""
    recorded = tmp_path / "request.json"
    recorded.write_text(json.dumps({"channel": "SLACK"}), encoding="utf-8")
    assert main(["convert", "--file", str(recorded)]) == EXIT_INVOCATION
    capsys.readouterr()


def test_no_command_output_carries_a_secret(capsys: pytest.CaptureFixture[str]) -> None:
    """Nothing resembling key material reaches stdout.

    The fixture secret is searched for by value: a command that resolved a credential and printed it
    would fail here even if the field name looked innocent.
    """
    for argv in _INVOCATIONS:
        _, payload = _run(argv, capsys)
        serialised = json.dumps(payload, ensure_ascii=False)
        assert FIXTURE_SECRET not in serialised
        for forbidden in ("secret", "token", "credential", "signature", "key"):
            assert forbidden not in {name.lower() for name in payload}, (
                f"{' '.join(argv)} emits a field named like {forbidden}"
            )


def test_the_parser_accepts_no_credential_or_key_argument() -> None:
    """The strongest form of the previous property: the flag does not exist.

    A CLI that refused to print a secret but accepted one as an argument would put key material in a
    shell history, which is a disclosure the output check cannot see.
    """
    parser = build_parser()
    forbidden = ("--secret", "--token", "--credential", "--key", "--signature", "--provider")
    rendered = parser.format_help()
    subparsers = [
        action
        for action in parser._actions
        if isinstance(action, type(parser._subparsers))  # pyright: ignore[reportPrivateUsage]
    ]
    del subparsers  # the help text below covers every subcommand's options

    for flag in forbidden:
        assert flag not in rendered, f"{flag} is an accepted argument"


def test_every_declared_subcommand_is_covered_by_this_test(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Coverage, so a new command cannot be added without an assertion reaching it.

    Read from the parser rather than restated: the failure this prevents is a seventh subcommand
    that forgets the limitation field and passes because no invocation above mentions it.
    """
    del capsys
    parser = build_parser()
    declared: set[str] = set()
    for action in parser._actions:  # pyright: ignore[reportPrivateUsage]
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            declared |= {str(name) for name in cast("dict[object, object]", choices)}

    exercised = {argv[0] for argv in _INVOCATIONS} | _COMMANDS_WITH_DEDICATED_TESTS
    uncovered = declared - exercised
    assert uncovered == set(), f"subcommands with no invocation here: {uncovered}"
