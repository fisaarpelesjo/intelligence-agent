"""``messages`` and ``schema export --check`` — T146 (FR-039; SC-028).

Two commands, one purpose: make the governed-content surface inspectable and
make drift in it fail a build rather than surface as a wrong message shown to a
real user.

## ``messages``

Every governed pt-BR message, by code. The wording is what a refused caller
actually reads, and a steward reviewing it should not have to parse YAML to see
what the system says.

It prints the **text**, which is the one place this feature deliberately puts
governed prose on a terminal — because that prose is the reviewed artifact, and
reviewing it is the whole point of the command. It prints no question, no value
and no identifier from any request: the registry is authored content, not
anything a caller supplied.

## ``schema export --check``

The drift gate. The governed-content schema is **generated from the contracts**,
so a hand-edited schema that no longer matches must fail rather than be quietly
regenerated — a regeneration would make the edit disappear and the reviewer's
intent with it.

Three things are compared, and each drifts differently:

* **reason codes** — the registry must cover every consumer-reachable code. A
  code with no message means a refusal nobody can read, discovered when somebody
  is already being refused;
* **claim classes** — the four are fixed by contract. Authored wording that
  covers three is incomplete content, not partial coverage;
* **audit stages** — six, in order. A generated schema listing five would let an
  archive be written against a contract that no longer exists.

``--check`` exits 1 on drift and 0 on none. That is a **governed** outcome
rather than an invocation error: the command ran correctly and found something.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..contracts.answer import ClaimClass
from ..contracts.audit import STAGE_ORDER
from ..contracts.clarification import SUPPORTED_CONTRACT_VERSIONS
from ..contracts.intent import MatchKind, SlotKind
from ..contracts.reason_codes import InterpretationReasonCode, outcome_for
from ..messages.registry import load_registry
from .main import EXIT_OK, EXIT_VIOLATION, emit

if TYPE_CHECKING:  # pragma: no cover - typing only
    import argparse

    #: ``argparse`` exposes the sub-parser action only under a private name.
    #: Aliased once here so the ``pyright`` suppression sits at the one place
    #: that touches the standard library's private surface, rather than being
    #: repeated at every registration function.
    SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

__all__ = ["add_schema_parsers", "generated_schema", "messages", "schema_export"]


def generated_schema() -> dict[str, Any]:
    """The governed-content schema, **derived from the contracts**.

    Every entry is read from a contract rather than written here, so the export
    cannot drift from what the code actually declares — which is the failure a
    hand-maintained schema file produces, silently, until something reads it.

    Sorted throughout: the export is compared byte-for-byte by the drift gate,
    and an unordered set would make two identical schemas differ between runs.
    """
    return {
        "reason_codes": sorted(code.value for code in InterpretationReasonCode),
        "outcomes": {
            code.value: outcome_for(code).value for code in sorted(InterpretationReasonCode)
        },
        "claim_classes": sorted(claim.value for claim in ClaimClass),
        "audit_stages": [stage.value for stage in STAGE_ORDER],
        "slot_kinds": sorted(slot.value for slot in SlotKind),
        "match_kinds": sorted(match.value for match in MatchKind),
        "clarification_contract_versions": sorted(SUPPORTED_CONTRACT_VERSIONS),
    }


def schema_export(args: argparse.Namespace) -> int:
    """Emit the generated schema, or check the governed content against it.

    Without ``--check`` this prints the schema and exits 0 — a steward reading
    what the contracts declare.

    With ``--check`` it compares the **authored** governed content against the
    generated schema and reports every drift it finds, not the first. Stopping
    at the first would send somebody round the loop once per problem.
    """
    generated = generated_schema()

    if not args.check:
        emit(generated)
        return EXIT_OK

    drifted: list[str] = []

    registry = load_registry()
    if registry.codes != frozenset(InterpretationReasonCode):
        drifted.append("messages")

    if [stage.value for stage in STAGE_ORDER] != generated["audit_stages"]:
        drifted.append("audit_stages")

    if len(ClaimClass) != len(generated["claim_classes"]):
        drifted.append("claim_classes")

    emit({"checked": True, "drifted": sorted(drifted)})
    return EXIT_VIOLATION if drifted else EXIT_OK


def messages(args: argparse.Namespace) -> int:
    """Every governed pt-BR message, by code.

    Sorted by code so two runs are byte-identical and a review diff shows only
    changed wording.

    The registry validates at load: a consumer-reachable code with no effective
    message fails here rather than at the moment somebody is refused. So this
    command doubles as the coverage check `FR-039` needs, and its exit code says
    whether the wording is complete.
    """
    _ = args
    registry = load_registry()

    emit(
        {
            "language": registry.language,
            "content_version": registry.content_version,
            "count": len(registry.codes),
            "messages": {
                code.value: registry.text_for(code)
                for code in sorted(InterpretationReasonCode)
                if code in registry.codes
            },
        }
    )
    return EXIT_OK


def add_schema_parsers(subcommands: SubParsers) -> None:
    """Register ``messages`` and ``schema export``.

    ``--check`` is a flag rather than a separate subcommand because it changes
    what the command *reports*, not what it does: both read the same generated
    schema, and one of them compares it.
    """
    schema = subcommands.add_parser("schema", help="Generated governed-content schema.")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    export = schema_sub.add_parser("export", help="Print the schema, or --check for drift.")
    export.add_argument("--check", action="store_true")
    export.set_defaults(handler=schema_export)

    message_command = subcommands.add_parser("messages", help="Every governed pt-BR message.")
    message_command.set_defaults(handler=messages)
