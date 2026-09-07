"""Assert the fixture-fallback verdict a CI step is supposed to get — T101 (FR-009; SC-001).

The readiness guard has **two regimes**, and ``readiness-guard.yml`` says so at the top:
before a capability is declared, a fixture may stand in and the report must state the
limitation; after it is declared, a fixture standing in for it in ``integration`` or
``release`` mode **fails closed**.

A step wired as ``compliance --mode integration --coverage <fixture>`` only ever asserted
the first regime, and it asserted it by *succeeding* — which meant that on the day the
second regime arrived, the step went red for the guard **working**. That is what declaring
``ext_a`` did on 2026-09-03: three steps in exit 1, each printing the refusal it was
designed to produce (finding S-40).

**The repair is not to weaken the mode.** Dropping those steps to ``--mode local`` would
turn the red green by removing the gate, and the property — *a fixture never substitutes
for a declared capability* — would stop being checked at the exact moment it started being
true.

**This asserts the verdict rather than the exit code**, and it derives which verdict to
expect from the readiness record itself, through the same public function the guard uses
(``load_readiness`` / ``ReadinessState.is_ready``). So:

* while the capability is declared, the step demands a **refusal**: a non-zero exit *and*
  ``readiness.permitted is false`` *and* a reason naming that capability. A bare non-zero
  exit is not enough — an import error also exits non-zero, and "it failed" would read as
  "it refused";
* while it is **not** declared, the step demands the permission *and* the stated
  limitation, which is the older regime, unchanged;
* if the command ever *succeeds* where a refusal is due, this exits non-zero naming the
  cause: the fail-closed is gone.

Neither regime is typed here. Declaring or withdrawing a capability moves this step to the
other regime on its own, and the verdict is read from the payload rather than grepped from
prose, so a reworded refusal cannot read as a missing one.

## The class this file exists twice for: ABSENCE IS NOT AN ANSWER (S-41)

Deriving the regime from a record introduced a second way to be quietly wrong, and it is the
**same shape** as the one above one layer down. S-40 was a gate that could not tell *the gate
works* from *the gate is gone*, because it asserted today's answer. S-41 was this file
reading **silence as "not declared"**: a record whose `ext_a` entry had simply lost its
`declared:` line — to an edit, a bad merge — printed *"ext_a is not declared"*, permitted the
fixture, and exited 0. **Green.** A damaged record moved the gate to its permissive regime
and no instrument said a word.

So the rule is stated once, executably, in `read_declared_flag` below, and it is the rule for
**any** step that derives a regime from a governed record:

> **A record that does not SAY is never read as saying no.** Absence, an unknown key, a
> non-boolean value, an unreadable file and a record the contract itself rejects are all
> *"did not say"* — each refuses, naming which one it was. Only an explicit boolean answers.

Concretely, `read_declared_flag` requires: the file reads and parses; `capabilities` is a
list; the capability has an entry; that entry carries `declared` as a **`bool`, not merely
something truthy** (`declared: "false"` is a string, and `bool("false")` is `True` — measured);
the entry carries no key the contract does not define (the known set is derived from
`ReadinessRecord`'s own fields, so a contract that grows one does not leave this behind); and
the flag agrees with what `load_readiness` built. Anything else exits **1** — the house's
governed-content code, which is where `READINESS_MALFORMED` sits in
`packages/semantic_catalog/tests/unit/test_cli_exit_codes.py`. Exit 2 is reserved for the
call being wrong, and an unparseable record is not a wrong call.

**The root of S-41 is upstream and is NOT fixed here**: `load_readiness` builds
`declared=bool(entry.get("declared", False))`, which manufactures `False` out of silence and
ignores unknown keys, while its own docstring promises the opposite. Hardening it changes a
`001` contract; that is the owner's decision and is recorded as a named debt. This file
refuses to depend on it either way.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from semantic_catalog.compliance.readiness import (
    Capability,
    ReadinessError,
    ReadinessRecord,
    load_readiness,
)

#: ``tools/ci/`` -> ``tools/`` -> repository.
REPO = Path(__file__).resolve().parents[2]

#: The keys a capability entry may carry, DERIVED from the contract rather than typed. A
#: hand-written list is one more thing that reads as true after the contract moves on.
KNOWN_ENTRY_KEYS = frozenset(
    field.name for field in dataclasses.fields(ReadinessRecord)
)

#: Governed content is exit 1 in this repository — see ``Category.READINESS_MALFORMED`` in
#: ``packages/semantic_catalog/tests/unit/test_cli_exit_codes.py``, which puts it in
#: ``GOVERNED``. Exit 2 means the call itself was wrong.
EXIT_RECORD_DOES_NOT_SAY = 1
EXIT_BAD_CALL = 2


class RecordDoesNotSay(Exception):
    """The record failed to state the regime — for any of the reasons above.

    One exception for the whole class, on purpose. Each raise names its own cause in the
    message, but they share a type because they share a consequence: the step refuses rather
    than inferring an answer nobody wrote down.
    """


def read_declared_flag(record: Path, capability: Capability) -> bool:
    """Return what the record SAYS about ``capability``, or refuse because it did not say.

    This is the rule of the class, in one place, so that a second script deriving a regime
    has something to call instead of something to re-derive.
    """
    try:
        text = record.read_text(encoding="utf-8")
    except OSError as exc:
        raise RecordDoesNotSay(f"the record could not be read: {exc}") from exc
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RecordDoesNotSay(
            f"the record is not parseable YAML, which is not the same as declaring nothing: {exc}"
        ) from exc

    if not isinstance(document, dict) or not isinstance(
        document.get("capabilities"), list
    ):
        raise RecordDoesNotSay("the record has no 'capabilities' list to read")

    entries = [
        entry
        for entry in document["capabilities"]
        if isinstance(entry, dict) and entry.get("capability") == capability.value
    ]
    if not entries:
        raise RecordDoesNotSay(
            f"the record has no entry for {capability.value}; a missing entry is not a "
            "declaration that it is not ready"
        )
    if len(entries) > 1:
        raise RecordDoesNotSay(
            f"the record has {len(entries)} entries for {capability.value}; which one speaks "
            "is not something to guess"
        )
    entry = entries[0]

    unknown = sorted(set(entry) - KNOWN_ENTRY_KEYS)
    if unknown:
        raise RecordDoesNotSay(
            f"the entry for {capability.value} carries {unknown}, which the contract does not "
            "define; a misspelt key is silence wearing the right shape"
        )
    if "declared" not in entry:
        raise RecordDoesNotSay(
            f"the entry for {capability.value} states no 'declared'; silence is not 'not "
            "declared', and every entry of this record states it explicitly"
        )
    declared = entry["declared"]
    if not isinstance(declared, bool):
        raise RecordDoesNotSay(
            f"the entry for {capability.value} states declared={declared!r}, which is "
            f"{type(declared).__name__} and not a boolean; truthiness is not a declaration "
            '(bool("false") is True)'
        )

    try:
        state = load_readiness(record)
    except ReadinessError as exc:
        raise RecordDoesNotSay(f"the contract refuses this record: {exc}") from exc
    if state.is_ready(capability) is not declared:
        raise RecordDoesNotSay(
            f"the record's own line says declared={declared} while the contract built "
            f"{state.is_ready(capability)}; two readings of one record is not an answer"
        )
    return declared


def _run_compliance(
    args: argparse.Namespace,
) -> tuple[int, dict[str, Any] | None, str, str]:
    """Run the compliance command once, in JSON, and return everything it said."""
    command = [
        sys.executable,
        "-m",
        "semantic_catalog.cli",
        "compliance",
        "--path",
        args.path,
        "--mode",
        args.mode,
        "--coverage",
        args.coverage,
        "--readiness",
        args.readiness,
        "--codeowners",
        args.codeowners,
        "--format",
        "json",
    ]
    completed = subprocess.run(
        command,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    return completed.returncode, payload, completed.stdout, completed.stderr


def _fail(message: str, stdout: str, stderr: str) -> int:
    """Report the assertion that broke, with everything the command said underneath."""
    print(f"fixture-fallback assertion FAILED: {message}", file=sys.stderr)
    if stdout.strip():
        print("--- command stdout ---", file=sys.stderr)
        print(stdout, file=sys.stderr)
    if stderr.strip():
        print("--- command stderr ---", file=sys.stderr)
        print(stderr, file=sys.stderr)
    return 1


def _require_refusal(
    args: argparse.Namespace,
    capability: Capability,
    verdict: dict[str, Any],
    code: int,
    stdout: str,
    stderr: str,
) -> int:
    """The declared regime: the fixture must be refused, for this capability, and block."""
    if verdict.get("permitted") is not False:
        return _fail(
            f"{capability.value} is declared ready and a fixture was still PERMITTED in "
            f"{args.mode} mode — the fail-closed is gone",
            stdout,
            stderr,
        )
    reasons = [str(reason) for reason in verdict.get("reasons") or ()]
    if not any(
        reason.startswith(f"{capability.value} is declared ready") for reason in reasons
    ):
        return _fail(
            f"the run was refused, but no reason names {capability.value}; a refusal for "
            "another cause must not be read as this one",
            stdout,
            stderr,
        )
    if code == 0:
        return _fail(
            "the verdict refused and the command still exited 0 — CI would go green on a run "
            "that reported on a fixture",
            stdout,
            stderr,
        )
    print(
        f"fixture-fallback [{args.mode}]: REFUSED as required (exit {code}). Reasons:"
    )
    for reason in reasons:
        print(f"  - {reason}")
    return 0


def _require_permission(
    args: argparse.Namespace,
    capability: Capability,
    verdict: dict[str, Any],
    code: int,
    stdout: str,
    stderr: str,
) -> int:
    """The undeclared regime: permitted, but only because the limitation is stated."""
    if verdict.get("permitted") is not True:
        return _fail(
            f"{capability.value} is not declared and the run was still refused in "
            f"{args.mode} mode",
            stdout,
            stderr,
        )
    limitations = [str(limitation) for limitation in verdict.get("limitations") or ()]
    if not limitations:
        return _fail(
            "a fixture stood in and the report stated no limitation — the permissive regime "
            "exists only because the limitation is stated",
            stdout,
            stderr,
        )
    if code != 0:
        return _fail(
            f"the verdict permitted the run and the command exited {code}",
            stdout,
            stderr,
        )
    print(
        f"fixture-fallback [{args.mode}]: permitted with the limitation stated (exit {code})."
    )
    for limitation in limitations:
        print(f"  - {limitation}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="assert-fixture-fallback",
        description="Assert the verdict a fixture-backed compliance run must get.",
    )
    parser.add_argument("--path", default="semantic")
    parser.add_argument("--mode", required=True, choices=("integration", "release"))
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--readiness", default="docs/readiness/external-readiness.yaml")
    parser.add_argument("--codeowners", default=".github/CODEOWNERS")
    parser.add_argument(
        "--capability",
        default="ext_a",
        help="The capability the coverage fixture stands in for.",
    )
    args = parser.parse_args(argv)

    try:
        capability = Capability(args.capability)
    except ValueError:
        known = sorted(member.value for member in Capability)
        print(
            f"unknown capability {args.capability!r}; known: {known}", file=sys.stderr
        )
        return EXIT_BAD_CALL

    # The regime is READ, never typed — and a record that does not SAY is refused rather
    # than read as "not declared". See `read_declared_flag` and the S-41 section above: this
    # is the whole point of the second pass over this file.
    try:
        refusal_is_due = read_declared_flag(REPO / args.readiness, capability)
    except RecordDoesNotSay as exc:
        print(
            f"fixture-fallback [{args.mode}]: the readiness record does not state the regime "
            f"for {capability.value}, so no regime is assumed — {exc}",
            file=sys.stderr,
        )
        return EXIT_RECORD_DOES_NOT_SAY

    required = "REFUSAL" if refusal_is_due else "PERMISSION with a stated limitation"
    regime = "declared ready" if refusal_is_due else "not declared"
    print(
        f"fixture-fallback [{args.mode}]: {capability.value} is {regime} in {args.readiness}, "
        f"so this step requires a {required}."
    )

    code, payload, stdout, stderr = _run_compliance(args)

    if payload is None:
        return _fail(
            "the compliance command produced no JSON payload to judge", stdout, stderr
        )
    verdict = payload.get("readiness")
    if not isinstance(verdict, dict):
        return _fail("the payload carries no readiness verdict", stdout, stderr)
    if verdict.get("mode") != args.mode:
        return _fail(
            f"the verdict reports mode {verdict.get('mode')!r}, not {args.mode!r}",
            stdout,
            stderr,
        )

    if refusal_is_due:
        return _require_refusal(args, capability, verdict, code, stdout, stderr)
    return _require_permission(args, capability, verdict, code, stdout, stderr)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
