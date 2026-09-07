"""This feature reads readiness and never writes it — `FR-208`, `FR-209`, T716.

**`T703` is what gave this node a reason to exist**, and until it landed there was none.
While the channel condition was a parameter, nothing here went near a readiness record,
and a node asserting *no record is touched* would have been asserting over an absence it
did not have to work for — green because the subject was missing, not because a boundary
held.

Now the feature **reads** those records on every permission check. So the property is
real and worth holding: **it reads and it never writes.**

## Why the distinction matters more than it sounds

ADR 0035's second condition is that the channel is **already** enabled. A feature that
could write a readiness record could satisfy its own precondition — the exact shape of
*a gate whose subject includes the gate* this repository has corrected three times this
week. Enabling a channel is a different act with a different authorization, and the
owner's decision of 2026-08-27 covers **his own chat and no other**.

## What is scanned, and why the syntax tree rather than the text

A write would arrive as a **call**: `write_text`, `open` in a writing mode, `dump`,
`unlink`, `mkdir`. Reading the raw text would flag this docstring, which names those
methods in order to forbid them — the self-reference that cost two cycles here already.
So the walk is over the tree, and the docstring is not a call.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from channel_integration.compliance.readiness import READINESS_RECORDS, readiness_root

pytestmark = pytest.mark.security

#: `tests/security/` -> `tests/` -> package.
PACKAGE = Path(__file__).resolve().parents[2]
SRC = PACKAGE / "src" / "proactive_distribution"

#: Every way a file gets written that this package could plausibly reach for. Named
#: rather than guessed: a scan for "anything that might write" cannot be checked, and a
#: named list is one a reader can disagree with.
WRITING_CALLS = frozenset(
    {"write_text", "write_bytes", "writelines", "unlink", "mkdir", "touch", "rename", "replace"}
)

#: `open` and `yaml.dump` take the mode or the target as an argument, so they are checked
#: separately from the bare method names above.
WRITING_FUNCTIONS = frozenset({"open", "dump", "safe_dump", "dump_all"})


def _modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


MODULES = _modules()


def test_the_walk_reaches_this_package() -> None:
    """A scan that read nothing would report success by doing nothing."""
    assert MODULES, "the scan found no module, so every assertion below is vacuous"
    assert {p.name for p in MODULES} >= {"conditions.py"}


def test_the_feature_really_does_read_a_readiness_record() -> None:
    """**The premise that stops this file being a green tick over nothing.**

    Until `T703`, no module here went near readiness, and *nothing writes a record* was
    true for the uninteresting reason. This asserts the subject exists: the reader is
    imported and called, so the prohibition below has something to prohibit.
    """
    conditions = (SRC / "distribute" / "conditions.py").read_text(encoding="utf-8")
    tree = ast.parse(conditions)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if node.module is not None and "readiness" in node.module
    }
    #: **The read MOVED on 2026-08-28 and this node moved with it**, which is what its own
    #: message asked for. `OD-20-A` split the key, and this feature asks the SENDING half:
    #: `may_send_to`. Any of the three is a readiness read, so any of the three satisfies the
    #: premise -- naming one alone would send this node red for a rename rather than for the
    #: subject disappearing.
    readers = {"channel_enabled", "may_send_to", "may_receive_from"}
    assert imported & readers, (
        f"no module here reads a readiness record any more -- imported {sorted(imported)} -- "
        f"so this file guards nothing; if the read moved again, this node moves with it "
        f"rather than staying green"
    )


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_calls_anything_that_writes(path: Path) -> None:
    """No write anywhere in the package — not to readiness, and not to anything else.

    **Wider than the requirement on purpose.** `FR-208` and `FR-209` are about readiness
    records, and a scan narrowed to those paths would have to recognise the path, which a
    variable defeats. A feature that writes no file at all cannot write that one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offences: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in WRITING_CALLS:
            offences.append(ast.unparse(node)[:70])
        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
        )
        if name in WRITING_FUNCTIONS:
            offences.append(ast.unparse(node)[:70])
    assert not offences, f"{path.name} calls something that writes: {offences}"


def test_no_module_names_a_readiness_record_file() -> None:
    """A record named here is a path this feature is one edit away from writing to.

    It reads readiness through `004`'s function, which locates the directory itself. A
    filename spelled out in this package would be a second way to reach those files,
    bypassing the reader that owns them.
    """
    offences: list[str] = []
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value.count(" ") > 3:  # a docstring or a message, not a path
                continue
            offences.extend(
                f"{path.name}: {node.value}" for record in READINESS_RECORDS if record in node.value
            )
    assert not offences, f"a readiness record is named in this package: {offences}"


def test_the_scan_would_catch_a_write() -> None:
    """**Proof the scan bites**, over source this file parses rather than over the package.

    A node asserting "nothing writes" while the package writes nothing is green for two
    different reasons and cannot tell them apart. This is the second reason, measured.
    """
    writing = ast.parse(
        'Path("docs/readiness/multichannel-external-readiness.yaml").write_text(x)\n'
    )
    caught = [
        node
        for node in ast.walk(writing)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in WRITING_CALLS
    ]
    assert caught, "the write scan does not recognise a `write_text` call"

    opening = ast.parse('handle = open(target, "w")\n')
    caught_open = [
        node
        for node in ast.walk(opening)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in WRITING_FUNCTIONS
    ]
    assert caught_open, "the write scan does not recognise `open`"


def test_the_records_are_where_the_reader_says_and_this_package_owns_none_of_them() -> None:
    """The four records exist and live outside this package, measured rather than assumed.

    If one ever appeared **inside** this package, every scan above would still pass while
    the feature carried its own copy of the thing it must not control.
    """
    root = readiness_root()
    present = [name for name in READINESS_RECORDS if (root / name).is_file()]
    assert present, f"no readiness record exists under {root}; the reader guards nothing"
    inside = sorted(str(p) for p in PACKAGE.rglob("*external-readiness.yaml"))
    assert not inside, f"this package carries its own readiness record: {inside}"
