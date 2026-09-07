"""The steward CLI — T144 (FR-025; SC-035).

Five read-only subcommands for whoever operates this feature. **None of them
asks a question, resolves a catalog, calls a model, issues a clarification or
reaches a warehouse.** They report what the governed content says, and today all
of them report that it says nothing.

```
vocabulary show     the D-18 content in force, or why none resolves
policy show         the D-19 policy in force, or why none resolves
explain-intent      the resolved intent and the request that would be built
messages            every governed pt-BR message
schema export       the generated governed-content schema, or --check for drift
```

## Exit codes, mirroring `001` and `002`

| Code | Meaning |
|---|---|
| ``0`` | the command answered |
| ``1`` | a **governed** outcome — nothing resolves, or the drift gate found drift |
| ``2`` | a broken invocation — unknown command, bad argument, missing file |

A governed refusal and a broken invocation are different things and a caller
scripting this needs to tell them apart. Exiting 1 for both would make "the
governed content is empty" indistinguishable from "you typed the command wrong",
and a CI gate would treat the second as the first.

**Refusing is a normal outcome here.** `interpretation_governance/` holds no
approved instance while `D-18` and `D-19` are open, so ``vocabulary show`` and
``policy show`` exit 1 today by design — and say which governed code applies
rather than printing an empty object, which would read as "nothing is
restricted".

## What the CLI never does

No interactive prompt, no shell execution, no dynamic import, no environment
override of readiness or governed content, no provider argument, no credential
argument, no seal-key argument, no network. Every path a value could enter
through is simply not a parameter — and `T148`'s containment scan asserts no
`src/` module reaches a fixture, so there is no flag that makes any of this
succeed against something other than the real governed files.

Output is deterministic JSON — sorted keys, fixed separators — so two identical
invocations are byte-identical and a diff between two runs shows only what
actually changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import TYPE_CHECKING, Any

from ..governance.policy import resolve_policy
from ..governance.resolve import ContentUnresolvable
from ..governance.vocabulary import (
    resolve_claim_classes,
    resolve_comparison_formulas,
    resolve_period_vocabulary,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = [
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


def emit(payload: dict[str, Any]) -> None:
    """Deterministic JSON: sorted keys, fixed separators, no trailing whitespace.

    Byte-identical across runs, so a snapshot test is meaningful and a diff
    between two invocations shows only what changed. ``ensure_ascii=False``
    because the governed content is pt-BR and escaping every accent would make
    the output unreadable for the person it is written for.
    """
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    sys.stdout.write("\n")


def _on(args: argparse.Namespace) -> date:
    """The date to resolve governed content against — **required**, never defaulted.

    Defaulting to today was the obvious thing and was wrong. `FR-099`'s reason
    for banning a clock is that a defaulted instant makes the same invocation
    produce two different answers on two different days with nothing in the
    output to show why; that reason does not stop applying because the caller is
    a steward rather than a request. It applies harder — this output is what
    somebody pastes into a review.

    So the date is an argument with no default, and it is echoed in the payload.
    A steward who wants today types today, and the record then says which day
    that was. This feature reads no clock anywhere.
    """
    supplied: date = args.on
    return supplied


# --- vocabulary show ---------------------------------------------------------


def _cmd_vocabulary_show(args: argparse.Namespace) -> int:
    """The `D-18` content in force, or why none resolves.

    Three documents — the period vocabulary, the comparison formula set and the
    claim-class wording — resolved separately because they are separately
    authored, and reported together because a steward wants one answer to "is
    `D-18` usable".

    Each is reported independently rather than collapsed into a single verdict:
    "nothing resolves" is true today, but "the formulas resolve and the period
    vocabulary does not" is the state a partial approval would produce, and a
    single boolean could not express it.
    """
    on = _on(args)
    documents: dict[str, Any] = {}
    resolved_all = True

    for name, resolve in (
        ("period_vocabulary", resolve_period_vocabulary),
        ("comparison_formulas", resolve_comparison_formulas),
        ("claim_classes", resolve_claim_classes),
    ):
        try:
            content = resolve(on)
        except ContentUnresolvable as refusal:
            resolved_all = False
            documents[name] = {"resolved": False, "reason_code": refusal.code.value}
            continue
        documents[name] = {"resolved": True, "version": content.version}

    emit({"effective_on": on.isoformat(), "resolved": resolved_all, "documents": documents})
    return EXIT_OK if resolved_all else EXIT_VIOLATION


# --- policy show -------------------------------------------------------------


def _cmd_policy_show(args: argparse.Namespace) -> int:
    """The `D-19` policy in force, or why none resolves.

    On success it reports the **version and approver only** — not the ambiguity
    threshold, the round bound, the expiry or the question-length bound. Those
    are governed values, and a CLI that printed them would disclose policy to
    anyone with shell access, which is the same disclosure `FR-101` keeps out of
    a refusal message.

    A steward who needs the values reads the approved governed file. A steward
    who needs to know *which version is in force* is who this command is for.
    """
    on = _on(args)
    try:
        policy = resolve_policy(on)
    except ContentUnresolvable as refusal:
        emit({"effective_on": on.isoformat(), "resolved": False, "reason_code": refusal.code.value})
        return EXIT_VIOLATION

    emit(
        {
            "effective_on": on.isoformat(),
            "resolved": True,
            "version": policy.version,
            "approved_by": policy.approval.approver_role,
            "discloses_values": False,
        }
    )
    return EXIT_OK


# --- the parser --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The complete command surface. **Nothing is added at runtime.**

    Subparsers with ``required=True`` throughout, so a bare ``vocabulary`` is an
    invocation error rather than a command that guesses what was meant.

    There is deliberately no ``--provider``, ``--model``, ``--key``, ``--sink``,
    ``--fixture``, ``--readiness`` or ``--governance-root``. Each would be a way
    to point this feature at something other than the governed files, and the
    absence is what makes "no environment override" structural rather than a
    rule somebody follows.
    """
    from .explain import add_explain_parser
    from .schema import add_schema_parsers

    parser = argparse.ArgumentParser(
        prog="python -m analytics_interaction.cli",
        description="Read-only steward commands for governed analytics interaction.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    vocabulary = subcommands.add_parser("vocabulary", help="Governed D-18 content.")
    vocabulary_sub = vocabulary.add_subparsers(dest="vocabulary_command", required=True)
    vocabulary_show = vocabulary_sub.add_parser("show", help="What resolves, or why nothing does.")
    vocabulary_show.add_argument(
        "--on",
        type=date.fromisoformat,
        required=True,
        metavar="YYYY-MM-DD",
        help="Resolve governed content as of this date. Required: see _on.",
    )
    vocabulary_show.set_defaults(handler=_cmd_vocabulary_show)

    policy = subcommands.add_parser("policy", help="Governed D-19 interpretation policy.")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    policy_show = policy_sub.add_parser("show", help="Which version is in force, or why none is.")
    policy_show.add_argument(
        "--on",
        type=date.fromisoformat,
        required=True,
        metavar="YYYY-MM-DD",
        help="Resolve governed content as of this date. Required: see _on.",
    )
    policy_show.set_defaults(handler=_cmd_policy_show)

    add_explain_parser(subcommands)
    add_schema_parsers(subcommands)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand.

    A governed outcome exits 1; a broken invocation exits 2. An unexpected
    exception is **not** swallowed into a governed outcome — that would report a
    defect as a governance decision, and the next reader would look for a policy
    that explained it.

    The two caught families are the ones a *caller* can cause: a missing or
    malformed input file, and a governed content document that does not resolve.
    Neither prints a traceback: a stack trace on a steward's terminal is
    unbounded text nobody reviewed for disclosure.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_INVOCATION if exc.code else EXIT_OK

    try:
        return int(args.handler(args))
    except ContentUnresolvable as refusal:
        emit({"resolved": False, "reason_code": refusal.code.value})
        return EXIT_VIOLATION
    except (FileNotFoundError, ValueError, KeyError):
        # The message is not printed. A parser error can quote the input, and
        # the input is untrusted text — `FR-045` forbids echoing it even to say
        # it was rejected.
        sys.stderr.write("invocation error: the input could not be read as a governed document\n")
        return EXIT_INVOCATION


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(main())
