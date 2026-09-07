"""The steward CLI — T150 (`FR-099`; mirrors `001`, `002` and `003`).

Six read-only subcommands for whoever operates this feature. **None of them contacts a provider,
opens a socket, reads a credential, or declares readiness.** They report what the governed content
and the readiness records say, and today most of them report that a governed document resolves to
nothing.

```
convert            replay a recorded request file through the production `convert` render
render a recorded payload file for one channel simulate           both of the above, per channel,
over one recorded file capabilities       which channels may send, which may receive, and
which records gate them
messages           every governed pt-BR message this feature authored schema export      the
generated governed-content schemas, or --check for drift
```

## Exit codes, mirroring the three features before it

| Code | Meaning |
|---|---|
| ``0`` | the command answered |
| ``1`` | a **governed** outcome — nothing resolves, a payload is withheld, or drift was found |
| ``2`` | a broken invocation — unknown command, bad argument, missing file |

A governed refusal and a broken invocation are different things, and a caller scripting this needs
to tell them apart. Collapsing both into ``1`` would make "`D-28` is undeclared" indistinguishable
from "you mistyped the channel", and a CI gate would read the second as the first.

**Refusing is a normal outcome here.** While `D-26` through `D-28` are open, ``render`` withholds
for every channel. That is the shipped state, not a malfunction, and the output says which record
applies rather than printing an empty object — which a reader would take for "nothing is
restricted".

**This paragraph used to end with "and ``capabilities`` reports every channel disabled", and that
sentence outlived the world it described.** It was written on 2026-08-18, before `OD-18` signed
`d_24` and `OD-20-A` split the key, and it went on asserting here — two lines above a docstring
this same cycle corrected — the opposite of what the command answers. **No sentence in this module
states which channels are open.** ``capabilities`` reports ``channels_may_send`` and
``channels_may_receive``, read from the records at the instant it runs; the field ``enabled`` it
named does not exist in the output any more, for the reason `_cmd_capabilities` records in its own
comment. A reader who wants the answer runs the command, and a count written here would be a
second copy of it that nothing keeps true.

## Every output carries the limitation (`FR-099`)

Each payload carries a ``limitation`` field, and :func:`emit` **refuses to write a payload without
one**. That is enforced in code rather than left to each command's diligence, because `FR-099` is
about what a pasted report looks like to somebody who did not run it, and the command that forgets
the field is the one whose output ends up in a readiness review.

## What the CLI never does

No interactive prompt, no shell execution, no dynamic import, no environment override of readiness
or governed content, no provider argument, no credential argument, no key argument, no network. A
value cannot enter through a path that is not a parameter, and there is no flag that makes any of
this succeed against something other than the real governed files.

Output is deterministic JSON — sorted keys, fixed separators — so two identical invocations are
byte-identical and a diff between two runs shows only what actually changed. No instant is read from
a clock: every command that needs one takes ``--at`` with no default, for the reason `003`'s CLI
records — a defaulted instant makes one invocation answer differently on two days with nothing in
the output to explain why.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..compliance.readiness import (
    CHANNEL_CAPABILITIES,
    IDEMPOTENCY_SCOPE_STATEMENT,
    capability_state,
    may_receive_from,
    may_send_to,
)
from ..contracts.descriptor import ChannelId
from ..contracts.raw import RawChannelRequest
from ..governance.capabilities import resolve_capability_matrix
from ..governance.resolve import ContentUnresolvable
from ..messages.registry import MessageRegistryMalformed, load_registry
from .simulate import SIMULATION_LIMITATION

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = [
    "CLI_LIMITATION",
    "EXIT_INVOCATION",
    "EXIT_OK",
    "EXIT_VIOLATION",
    "build_parser",
    "emit",
    "main",
]

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_INVOCATION = 2

#: The limitation sentence every non-simulation report carries. Distinct from
#: :data:`~channel_integration.cli.simulate.SIMULATION_LIMITATION` because the two say different
#: true things: a simulation used fixture payloads, while ``capabilities`` and ``messages`` read
#: the real governed files and still prove nothing about a provider.
CLI_LIMITATION = (
    "Esta saída é uma leitura de conteúdo governado e registros de prontidão. "
    "Ela não é evidência de integração real, de comportamento em produção "
    "nem de prontidão de canal."
)


class MissingLimitationError(AssertionError):
    """Raised when a command tries to emit a payload with no limitation field.

    An exception rather than a silent insertion: inserting the field here would let a command author
    forget it and never find out, and the point of `FR-099` is that the report itself carries the
    statement.
    """


def emit(payload: dict[str, Any]) -> None:
    """Deterministic JSON on stdout, with the limitation field enforced.

    Sorted keys and fixed separators, so two identical invocations are byte-identical.
    ``ensure_ascii=False`` because the governed content is pt-BR and escaping every accent would
    make the output unreadable for the person it is written for.
    """
    limitation = payload.get("limitation")
    if not isinstance(limitation, str) or not limitation.strip():
        raise MissingLimitationError(
            "every CLI payload must carry a non-empty `limitation` field (FR-099)"
        )
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    sys.stdout.write("\n")


def _read_json(path: Path) -> Any:
    """One recorded file, or a broken invocation.

    A missing or malformed file is exit 2, not exit 1: the steward's command was wrong, and
    reporting that as a governed refusal would be this CLI blaming the governance for a typo.
    """
    return json.loads(path.read_text(encoding="utf-8"))


# --- convert ------------------------------------------------------------------------------------


def _cmd_convert(args: argparse.Namespace) -> int:
    """Replay a recorded request through the production `convert`.

    The recorded file must carry the canonical request fields. Nothing is inferred: an absent field
    is a broken invocation rather than a default, because a default here would make the CLI convert
    a request the steward did not record.
    """
    path: Path = args.file
    if not path.is_file():
        sys.stderr.write(f"{path} does not exist\n")
        return EXIT_INVOCATION
    try:
        document = _read_json(path)
    except (OSError, json.JSONDecodeError) as broken:
        sys.stderr.write(f"{path} is not readable JSON: {broken}\n")
        return EXIT_INVOCATION

    if not isinstance(document, dict):
        sys.stderr.write(f"{path} does not carry a recorded request object\n")
        return EXIT_INVOCATION

    try:
        RawChannelRequest.model_validate(document)
    except ValueError as invalid:
        # A recorded file that is not a canonical request is the steward's file being wrong, so this
        # is exit 2 and the validation message travels verbatim rather than being summarised.
        sys.stderr.write(f"{path} is not a canonical RawChannelRequest: {invalid}\n")
        return EXIT_INVOCATION

    emit(
        {
            "command": "convert",
            "file": str(path),
            "accepted_shape": True,
            "converted": False,
            "reason": (
                "conversion needs verification material, transport bounds, a resolver and "
                "a pseudonymiser, and D-22 to D-25 and D-31 declare none. The recorded request is "
                "structurally canonical and nothing was converted."
            ),
            "limitation": CLI_LIMITATION,
        }
    )
    return EXIT_VIOLATION


# --- render -------------------------------------------------------------------------------------


def _cmd_render(args: argparse.Namespace) -> int:
    """Report what rendering for one channel would do, through the production resolution.

    While `D-28` declares no capability matrix this reports withheld for every channel, and names
    the governed code. That is the answer a steward needs: the channel cannot be rendered for, and
    the reason is a missing declaration rather than a payload defect.
    """
    channel: ChannelId = args.channel
    try:
        matrix = resolve_capability_matrix(channel)
    except ContentUnresolvable as refusal:
        emit(
            {
                "command": "render",
                "channel": channel.value,
                "renderable": False,
                "code": refusal.code.value,
                "detail": str(refusal),
                "limitation": CLI_LIMITATION,
            }
        )
        return EXIT_VIOLATION

    emit(
        {
            "command": "render",
            "channel": channel.value,
            "renderable": True,
            "declared_fields": sorted(matrix),
            "limitation": CLI_LIMITATION,
        }
    )
    return EXIT_OK


# --- simulate -----------------------------------------------------------------------------------


def _cmd_simulate(args: argparse.Namespace) -> int:
    """Report, per channel, what a simulation would exercise and what gates it.

    No payload is fabricated here. With no recorded file the command reports which governed records
    each channel waits on, so a steward learns what to declare rather than seeing an empty result.
    """
    channels = (args.channel,) if args.channel is not None else tuple(ChannelId)
    per_channel: dict[str, Any] = {}
    blocked = False
    for channel in channels:
        try:
            resolve_capability_matrix(channel)
            renderable, code = True, None
        except ContentUnresolvable as refusal:
            renderable, code = False, refusal.code.value
            blocked = True
        per_channel[channel.value] = {
            #: **Two fields since 2026-08-28, and the old one is gone rather than kept.**
            #: `OD-20-A` split the key, and a single `enabled` answered only the sending half
            #: while reading as the whole truth. A reader saw `TELEGRAM: enabled` for a channel
            #: that may not receive.
            "may_send": may_send_to(channel),
            "may_receive": may_receive_from(channel),
            "renderable": renderable,
            "code": code,
        }

    emit(
        {
            "command": "simulate",
            "channels": per_channel,
            "idempotency_scope": IDEMPOTENCY_SCOPE_STATEMENT,
            "limitation": SIMULATION_LIMITATION,
        }
    )
    return EXIT_VIOLATION if blocked else EXIT_OK


# --- capabilities -------------------------------------------------------------------------------


def _cmd_capabilities(args: argparse.Namespace) -> int:
    """**This feature's** capability records, their states, and which channels they gate.

    Read fresh on every invocation rather than cached: a withdrawal of readiness must take effect
    immediately, and a steward running this twice after a withdrawal must see the change.

    ## It said "every" and reported eleven of twelve

    On 2026-08-28 the omitted one was `d_34` — **the record that says managed custody, rotation
    and access scope are NOT declared.** So a steward running this read `d_24: READY` and
    nothing at all about the production bar, which is the one thing that record exists to say.

    The cause was upstream of this command: `CHANNEL_CAPABILITIES` did not name `d_34`. Fixed
    there, this now reports twelve by iterating the same enumeration — and the word `every` is
    gone, because the inherited records of `001`, `002` and `003` are still not reported here
    and never were.
    """
    records = {
        identifier: capability_state(identifier).value for identifier in CHANNEL_CAPABILITIES
    }

    #: **The word "enabled" did not survive the split, and it should not have.**
    #:
    #: `OD-20-A` made *may a message arrive* and *may a message be sent* two questions on
    #: 2026-08-28. This command answered `channels_enabled` and `any_channel_enabled` from the
    #: sending half alone — so it reported `TELEGRAM: true` for a channel that may not receive,
    #: and it is **the command a person runs to ask what is on**.
    #:
    #: One label over two facts is how a reader learns something that is not true. Both are
    #: reported now, and the old keys are gone rather than kept for compatibility: a key whose
    #: meaning changed is worse than a key that disappeared, because nothing tells the reader.
    sending = {channel.value: may_send_to(channel) for channel in ChannelId}
    receiving = {channel.value: may_receive_from(channel) for channel in ChannelId}
    emit(
        {
            "command": "capabilities",
            "records": records,
            "channels_may_send": sending,
            "channels_may_receive": receiving,
            "any_channel_may_send": any(sending.values()),
            "any_channel_may_receive": any(receiving.values()),
            "limitation": CLI_LIMITATION,
        }
    )
    #: **The exit code speaks for SENDING**, and says so rather than leaving it to be inferred:
    #: it is what a steward scripts against before delivering, and the inbound half has no
    #: caller that scripts it today. A reader who needs the other half reads
    #: `any_channel_may_receive`, which is right beside it.
    return EXIT_OK if any(sending.values()) else EXIT_VIOLATION


# --- messages -----------------------------------------------------------------------------------


def _cmd_messages(args: argparse.Namespace) -> int:
    """Every governed pt-BR message this feature authored, by code.

    The wording is content, so it is printed rather than judged: this command reports what is
    authored, and whether a sentence reads well is `D-28`'s and the reviewer's question.
    """
    try:
        registry = load_registry()
    except MessageRegistryMalformed as broken:
        emit(
            {
                "command": "messages",
                "readable": False,
                "detail": str(broken),
                "limitation": CLI_LIMITATION,
            }
        )
        return EXIT_VIOLATION

    emit(
        {
            "command": "messages",
            "readable": True,
            "content_version": registry.content_version,
            "language": registry.language,
            #: Codes rather than rendered strings. A stored message can carry named arguments, and
            #: rendering one here would need values this command has no business inventing — an
            #: invented argument printed beside a governed code is exactly the fabricated-evidence
            #: shape `FR-099` is about.
            "codes": sorted(code.value for code in registry.codes()),
            "limitation": CLI_LIMITATION,
        }
    )
    return EXIT_OK


# --- schema export ------------------------------------------------------------------------------


def _cmd_schema_export(args: argparse.Namespace) -> int:
    """The generated schema for this feature's governed-content documents.

    ``--check`` compares against a committed copy and exits 1 on drift, which is the deferred
    schema-drift gate `T030` recorded and `T152` asserts. Without ``--check`` the schema is printed
    and nothing on disk is touched: a command that wrote files by default would make a read-only CLI
    a writing one.
    """
    from ..governance.capabilities import (
        CAPABILITY_REQUIRED_FIELDS,
        CAPABILITY_REQUIRED_PER_CHANNEL,
    )

    schema = {
        "capability_matrix": {
            "required_fields": sorted(CAPABILITY_REQUIRED_FIELDS),
            "required_per_channel": sorted(CAPABILITY_REQUIRED_PER_CHANNEL),
        }
    }

    committed: Path | None = args.check
    if committed is None:
        emit({"command": "schema export", "schema": schema, "limitation": CLI_LIMITATION})
        return EXIT_OK

    if not committed.is_file():
        sys.stderr.write(f"{committed} does not exist\n")
        return EXIT_INVOCATION
    try:
        on_disk = _read_json(committed)
    except (OSError, json.JSONDecodeError) as broken:
        sys.stderr.write(f"{committed} is not readable JSON: {broken}\n")
        return EXIT_INVOCATION

    drifted = on_disk != schema
    emit(
        {
            "command": "schema export",
            "checked": str(committed),
            "drift": drifted,
            "limitation": CLI_LIMITATION,
        }
    )
    return EXIT_VIOLATION if drifted else EXIT_OK


# --- parser -------------------------------------------------------------------------------------


def _channel(value: str) -> ChannelId:
    try:
        return ChannelId(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a governed channel; expected one of "
            f"{', '.join(member.value for member in ChannelId)}"
        ) from None


def _instant(value: str) -> datetime:
    """An ISO-8601 instant, required to be timezone-aware.

    Naive instants are rejected rather than assumed to be UTC or local: assuming either would make
    the same recorded file convert differently depending on where it was replayed.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an ISO-8601 instant") from None
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{value!r} carries no timezone offset")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """The whole command surface, in one place so `T152` can enumerate it."""
    parser = argparse.ArgumentParser(
        prog="channel-integration",
        description=(
            "Read-only steward commands for the governed multichannel boundary. Contacts no "
            "provider and declares no readiness."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    convert = subcommands.add_parser("convert", help="replay a recorded request file")
    convert.add_argument("--file", type=Path, required=True)
    convert.add_argument("--at", type=_instant, required=False)
    convert.set_defaults(handler=_cmd_convert)

    render = subcommands.add_parser("render", help="report rendering for one channel")
    render.add_argument("--channel", type=_channel, required=True)
    render.set_defaults(handler=_cmd_render)

    simulate = subcommands.add_parser("simulate", help="report what a simulation would exercise")
    simulate.add_argument("--channel", type=_channel, required=False, default=None)
    simulate.set_defaults(handler=_cmd_simulate)

    capabilities = subcommands.add_parser("capabilities", help="declared records and channel state")
    capabilities.set_defaults(handler=_cmd_capabilities)

    messages = subcommands.add_parser("messages", help="every governed pt-BR message")
    messages.set_defaults(handler=_cmd_messages)

    schema = subcommands.add_parser("schema", help="governed-content schema operations")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    export = schema_sub.add_parser("export", help="print the schema, or --check a committed copy")
    export.add_argument("--check", type=Path, required=False, default=None)
    export.set_defaults(handler=_cmd_schema_export)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse and dispatch. Returns an exit code; raises nothing a caller must catch."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        # `argparse` exits 2 on a broken invocation, which is already this CLI's convention.
        return int(exit_request.code or EXIT_INVOCATION)
    handler: Any = args.handler
    result: int = handler(args)
    return result


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
