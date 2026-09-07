"""Nothing outside `compliance.readiness` calls `channel_enabled` — `S-1` of cycle 393.

## The defect this exists because of

`OD-20-A` split the key on 2026-08-28: *may a message arrive* and *may a message be sent*
became two questions. **The split existed inside `compliance/readiness.py` and nowhere that
consumes it.** Eight call sites still asked the undivided `channel_enabled` — the four
delivery adapters, the CLI twice, `007`, `008` — and **zero asked either half**, while
`channel_enabled`'s own docstring already said *callers ask `may_receive_from` or
`may_send_to`*.

A prose sentence describing a world the code had not reached is the class this loop hunts,
and it was in the one function the whole split turns on.

## Why this walks the tree instead of checking behaviour

**Behaviour cannot tell the two apart today.** `may_send_to` is `channel_enabled`, so every
call site returns the same answer either way — and it would go on returning the same answer
right up to the day a second condition is added to sending, which is exactly when the
difference would matter and nothing would say so.

The reviewer's acceptance criterion is that mutation: **a condition added to `may_send_to`
must turn the sending paths red.** It cannot while they ask the undivided function, so what
is asserted is the reach, the same way `T832` asserts writes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


REPO = _repository_root()

#: The module the split lives in. It is the ONE place `channel_enabled` may be called, because
#: both halves are built on it.
OWNER = REPO / "packages/channel_integration/src/channel_integration/compliance/readiness.py"

#: The undivided question, and the two halves that replaced it at every call site.
UNDIVIDED = "channel_enabled"
HALVES = ("may_send_to", "may_receive_from")

#: Callers permitted to stay on the undivided question, each NAMED with its reason. **Empty
#: today, and that is the point**: a middle ground with nobody in it cannot be widened by
#: habit. An entry here is a decision somebody makes in a diff.
PERMITTED_UNDIVIDED_CALLERS: dict[str, str] = {}


def _production_modules() -> list[Path]:
    return sorted(
        path
        for path in REPO.glob("packages/*/src/**/*.py")
        if "__pycache__" not in path.parts and path != OWNER
    )


def calls_to(tree: ast.AST, name: str) -> list[int]:
    """**The one predicate.** Line numbers where ``name`` is CALLED, however it is spelled.

    A call through an attribute (`readiness.channel_enabled(...)`) counts the same as a bare
    one: what matters is that the undivided question was asked, not how the caller reached it.
    """
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        reached = (
            called.attr
            if isinstance(called, ast.Attribute)
            else called.id
            if isinstance(called, ast.Name)
            else ""
        )
        if reached == name:
            found.append(node.lineno)
    return found


def test_the_sweep_reaches_the_packages() -> None:
    """A sweep over nothing forbids nothing — the `F115` shape, stated first as always."""
    modules = _production_modules()
    assert len(modules) > 60, f"the sweep found {len(modules)} production modules"
    packages = {path.relative_to(REPO).parts[1] for path in modules}
    assert len(packages) >= 7, f"the sweep reached only {sorted(packages)}"


def test_the_owning_module_still_declares_both_halves() -> None:
    """Read this before believing anything below: a missing half forbids nothing."""
    source = OWNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert UNDIVIDED in defined, f"{OWNER.name} no longer defines {UNDIVIDED}"
    for half in HALVES:
        assert half in defined, f"{OWNER.name} no longer defines {half}"


def test_nothing_outside_the_owning_module_asks_the_undivided_question() -> None:
    """`S-1`. Every caller asks the half that is theirs, or is named here with a reason."""
    offending: list[str] = []
    for path in _production_modules():
        relative = path.relative_to(REPO).as_posix()
        if relative in PERMITTED_UNDIVIDED_CALLERS:
            continue
        for line in calls_to(ast.parse(path.read_text(encoding="utf-8")), UNDIVIDED):
            offending.append(f"{relative}:{line}")
    assert not offending, (
        "these call the undivided question, so a condition added to one half would not reach "
        "them:\n" + "\n".join(offending)
    )


def test_the_halves_are_actually_asked_somewhere() -> None:
    """**The other direction, and it is what the first version of this file lacked.**

    A repository where nobody calls either half satisfies the assertion above completely — by
    calling nothing at all. That is how the split came to exist inside one module and nowhere
    else, and a node that only forbade the undivided question would have passed over it.
    """
    asked: dict[str, list[str]] = {half: [] for half in HALVES}
    for path in _production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for half in HALVES:
            if calls_to(tree, half):
                asked[half].append(path.relative_to(REPO).as_posix())
    for half, callers in asked.items():
        assert callers, (
            f"nothing in production asks {half}; the split exists in one module and reaches "
            f"nobody, which is the defect this file was written for"
        )


def test_the_delivery_adapters_ask_the_sending_half() -> None:
    """The four gates that decide whether a message leaves, named one by one.

    Counted from the directory rather than listed: a fifth adapter is caught by this, and a
    fifth channel is exactly what `test_fifth_channel.py` exists to make survivable.
    """
    adapters = sorted(
        (REPO / "packages/channel_integration/src/channel_integration/adapters").glob(
            "*/delivery.py"
        )
    )
    assert len(adapters) == 4, f"{len(adapters)} delivery adapters found"
    for path in adapters:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert calls_to(tree, "may_send_to"), f"{path.parent.name} does not ask may_send_to"
        assert not calls_to(tree, UNDIVIDED), f"{path.parent.name} still asks {UNDIVIDED}"


def test_the_scan_would_catch_a_caller_that_slid_back() -> None:
    """**Proof it bites**, over source this file parses rather than over the tree.

    Both spellings, because a caller reaching through the module namespace is the one a
    plain-text search would miss.
    """
    bare = ast.parse("if not channel_enabled(CHANNEL):\n    pass\n")
    assert calls_to(bare, UNDIVIDED), "the scan misses a bare call"

    through_module = ast.parse("if not readiness.channel_enabled(CHANNEL):\n    pass\n")
    assert calls_to(through_module, UNDIVIDED), "the scan misses a call through the module"

    imported_only = ast.parse("from x import channel_enabled\n")
    assert not calls_to(imported_only, UNDIVIDED), "an import with no call was counted"
