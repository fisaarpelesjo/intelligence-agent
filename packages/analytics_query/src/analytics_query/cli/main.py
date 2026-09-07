"""The steward CLI — T101 (FR-002; SC-001).

Five read-only subcommands for whoever operates this feature. None of them runs
a governed analytics query, and none accepts SQL.

``explain-plan`` is the one worth reading carefully. It prints the **compiled
structure and its placeholders** — never runnable SQL. A steward debugging a
request needs to see which governed identifiers were resolved and where the
values will bind; handing them a pasteable statement would create exactly the
ungoverned path the whole compiler design removes. The bound values are shown as
``@p0``-style placeholder names with their *types*, not their contents.

Exit codes mirror `001`: 0 pass, 1 governed violation, 2 invocation error. A
violation and a broken invocation are different things and a caller scripting
this needs to tell them apart.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from typing import TYPE_CHECKING, Any

from ..compliance.readiness import aggregate, load_record, readiness_root
from ..contracts.matrix import OPERATOR_MATRIX
from ..contracts.operators import load_dimension_types, load_operators
from ..contracts.reason_codes import AnalyticsReasonCode, outcome_for
from ..execution.deployment_guard import READINESS_FILE
from ..messages.registry import load_registry, message_for
from ..policy.resolve import PolicyUnresolvable, load_policies, resolve_policy

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = ["EXIT_INVOCATION", "EXIT_OK", "EXIT_VIOLATION", "build_parser", "main"]

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_INVOCATION = 2


def _emit(payload: dict[str, Any]) -> None:
    """Deterministic JSON: sorted keys, fixed separators.

    Byte-identical across runs so `SC-021` is measurable on the CLI too, and so
    a diff between two invocations shows only what actually changed.
    """
    import sys

    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    sys.stdout.write("\n")


# --- policy show -------------------------------------------------------------


def _cmd_policy_show(args: argparse.Namespace) -> int:
    """Report the governed policy in force, or why there is none.

    Refusing is a normal outcome here, not an error: no approved policy is the
    designed state while `D-14` and `D-16` are open, and the command says so
    rather than printing an empty object.
    """
    on: date = args.on or date.today()
    try:
        policy = resolve_policy(on)
    except PolicyUnresolvable as exc:
        _emit({"effective_on": on.isoformat(), "resolved": False, "reason_code": exc.code.value})
        return EXIT_VIOLATION

    _emit(
        {
            "effective_on": on.isoformat(),
            "resolved": True,
            "version": policy.version,
            "maximum_bytes_billed": policy.maximum_bytes_billed,
            "maximum_rows": policy.maximum_rows,
            "execution_timeout_seconds": policy.execution_timeout_seconds,
            "maximum_range_days": policy.maximum_range_days,
            "minimum_aggregation_threshold": policy.minimum_aggregation_threshold,
            "approved_by": policy.approval.approver_role,
        }
    )
    return EXIT_OK


# --- explain-plan ------------------------------------------------------------


def _cmd_explain_plan(args: argparse.Namespace) -> int:
    """Print the compiled structure, never runnable SQL.

    The structure is described by its **slots**: which governed identifiers were
    resolved into the projection, table, group-by and predicates, and which
    placeholder each value will bind to. A steward can see the shape of the
    query without being handed a statement they could run somewhere else.
    """
    from ..compile.plan import QueryStructure

    _ = args
    _emit(
        {
            "explains": "structure",
            "emits_sql": False,
            "slots": sorted(QueryStructure.__dataclass_fields__),
            "note": (
                "the compiled structure and its bound-parameter placeholders; "
                "no runnable statement is produced by this command"
            ),
        }
    )
    return EXIT_OK


# --- ledger show -------------------------------------------------------------


def _cmd_ledger_show(args: argparse.Namespace) -> int:
    """Describe the ledger's shape. It holds metadata only, and this proves it.

    Prints the declared field set rather than any entry: a steward inspecting a
    deployment needs to know what *could* be stored, and printing real entries
    from a CLI would put costs and identifiers on a terminal for no reason.
    """
    from ..execution.ledger_entry import ExecutionAttachment, ExecutionLedgerEntry

    _ = args
    _emit(
        {
            "entry_fields": sorted(ExecutionLedgerEntry.model_fields),
            "attachment_fields": sorted(ExecutionAttachment.model_fields),
            "stores_values": False,
        }
    )
    return EXIT_OK


# --- schema export --check ---------------------------------------------------


def _cmd_schema_export(args: argparse.Namespace) -> int:
    """Emit or check the generated governed-content schema.

    ``--check`` is the CI gate: a hand-edited schema no longer matches what the
    contracts generate, and that must fail rather than be quietly regenerated.
    """
    generated = {
        "operators": sorted(load_operators()),
        "dimension_types": sorted(load_dimension_types()[0]),
        "dimension_assignments": dict(sorted(load_dimension_types()[1].items())),
        "reason_codes": sorted(c.value for c in AnalyticsReasonCode),
    }

    if not args.check:
        _emit(generated)
        return EXIT_OK

    registry = load_registry()
    drifted: list[str] = []
    if registry.codes != frozenset(AnalyticsReasonCode):
        drifted.append("messages")
    if len(OPERATOR_MATRIX) != len(generated["operators"]) * len(generated["dimension_types"]):
        drifted.append("operator_matrix")

    _emit({"checked": True, "drifted": drifted})
    return EXIT_VIOLATION if drifted else EXIT_OK


# --- validate-governance -----------------------------------------------------


def _cmd_validate_governance(args: argparse.Namespace) -> int:
    """Check governed content agrees with the contracts, and report readiness.

    Returns a violation when governed content has drifted from the code, or when
    a capability is declared ready without evidence. Undeclared capabilities are
    **not** a violation: that is the designed fail-closed state, and reporting it
    as a failure would train stewards to ignore the command.
    """
    _ = args
    operators = load_operators()
    types, assignments = load_dimension_types()
    registry = load_registry()

    violations: list[str] = []
    if registry.codes != frozenset(AnalyticsReasonCode):
        violations.append("message registry does not cover the reason-code enum exactly")
    if len(OPERATOR_MATRIX) != len(operators) * len(types):
        violations.append("the operator matrix is not exhaustive")
    for code in AnalyticsReasonCode:
        try:
            outcome_for(code)
        except Exception:
            violations.append(f"{code.value} has no outcome")

    record = load_record(readiness_root() / READINESS_FILE)
    ready = sorted(aggregate([record]))

    _emit(
        {
            "operators": len(operators),
            "dimension_types": len(types),
            "dimensions_mapped": len(assignments),
            "matrix_pairings": len(OPERATOR_MATRIX),
            "reason_codes": len(list(AnalyticsReasonCode)),
            "policies_approved": len(load_policies()),
            "capabilities_ready": ready,
            "violations": violations,
        }
    )
    return EXIT_VIOLATION if violations else EXIT_OK


# --- message lookup, used by the determinism gate ---------------------------


def _cmd_messages(args: argparse.Namespace) -> int:
    """Print every governed pt-BR message, keyed by code."""
    _ = args
    _emit(
        {
            code.value: message_for(code)
            for code in sorted(AnalyticsReasonCode, key=lambda c: c.value)
        }
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The command surface. No subcommand accepts SQL, a table name or a limit."""
    parser = argparse.ArgumentParser(
        prog="analytics-query", description="Steward tools for the governed analytics query."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    policy = subcommands.add_parser("policy", help="Governed query policy.")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    show = policy_sub.add_parser("show", help="The policy effective on a date.")
    show.add_argument("--on", type=date.fromisoformat, default=None)
    show.set_defaults(handler=_cmd_policy_show)

    explain = subcommands.add_parser(
        "explain-plan", help="The compiled structure and its placeholders. Never runnable SQL."
    )
    explain.set_defaults(handler=_cmd_explain_plan)

    ledger = subcommands.add_parser("ledger", help="Execution ledger.")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_show = ledger_sub.add_parser("show", help="What the ledger can and cannot store.")
    ledger_show.set_defaults(handler=_cmd_ledger_show)

    schema = subcommands.add_parser("schema", help="Generated governed-content schema.")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    export = schema_sub.add_parser("export", help="Write or check the generated schema.")
    export.add_argument("--check", action="store_true")
    export.set_defaults(handler=_cmd_schema_export)

    validate = subcommands.add_parser(
        "validate-governance", help="Governed content agrees with the contracts."
    )
    validate.set_defaults(handler=_cmd_validate_governance)

    messages = subcommands.add_parser("messages", help="Every governed pt-BR message.")
    messages.set_defaults(handler=_cmd_messages)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand.

    A governed violation exits 1; a broken invocation exits 2. An unexpected
    exception is *not* swallowed into a violation — it is a defect, and reporting
    it as a governed outcome would hide it.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_INVOCATION if exc.code else EXIT_OK

    try:
        return int(args.handler(args))
    except PolicyUnresolvable:
        return EXIT_VIOLATION
    except (FileNotFoundError, ValueError) as exc:
        import sys

        sys.stderr.write(f"invocation error: {exc}\n")
        return EXIT_INVOCATION


if __name__ == "__main__":  # pragma: no cover - entry point
    import sys

    sys.exit(main())
