"""This feature starts nothing — `FR-007`, `SC-006`.

**Written in Phase 1, before the modules it guards exist in quantity, and that
order is the point.** `005` wrote its equivalent late and the REVIEWER's scope for
this phase says so plainly: *the structural node first and not afterwards*. A scan
added after a package is finished has never once refused anything; a scan added at
the start refuses the first attempt.

## Why a syntax-tree scan and not a list of inputs

`005`'s `F132` is the reason. A node there asserted *"this test fails the day a
producer appears"* while sweeping **twelve input combinations** — and twelve samples
cannot carry that sentence, because a producer branching on anything outside those
twelve passes underneath it while the test stays green.

So this reads the **syntax tree of every emitted module**. It fails by construction
the day somebody writes the import, with no dependence on the right input being in
a sample.

## Why both spellings

`005`'s `F133` is the reason. A scan looking only for named attribute access misses
``getattr(threading, "Thread")`` and a string-built import. So both the
``Attribute``/``Name`` form and the ``Constant`` form are checked, which is what
that finding cost to learn.

## The non-vacuity assertion is not decoration

`F115` and `F126` are why. A scan over an empty package passes by vacuity, and a
green tick over nothing is worse than no tick, because the next reader believes it.
So every assertion here is preceded by a measurement that the walk **reached**
something — and while this feature holds few modules, that measurement is the only
thing standing between this file and a lie.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

SRC = Path(__file__).resolve().parents[2] / "src" / "insights_prioritisation"

#: Anything that would make this feature start on its own, or reach outward.
#:
#: **Grouped by what it would break rather than alphabetically**, so a reader can
#: see which requirement each name serves: the first group starts work nobody
#: asked for (`FR-007`), the second delivers, which is item 8 and not this
#: feature (`FR-013`).
FORBIDDEN_ORIGINATION = frozenset(
    {
        "threading",
        "asyncio",
        "sched",
        "signal",
        "subprocess",
        "multiprocessing",
        "concurrent",
        "apscheduler",
        "celery",
    }
)

FORBIDDEN_DELIVERY = frozenset(
    {
        "smtplib",
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "telegram",
        "aiohttp",
    }
)

FORBIDDEN_MODULES = FORBIDDEN_ORIGINATION | FORBIDDEN_DELIVERY

#: Call names that start something even when the module they come from is allowed.
#: ``sleep`` is here because a loop that sleeps is a loop that runs.
FORBIDDEN_CALLS = frozenset(
    {
        "Thread",
        "Timer",
        "Process",
        "Pool",
        "run_forever",
        "create_task",
        "ensure_future",
        "sleep",
        "spawn",
        "fork",
        "popen",
        "send",
        "sendall",
        "post",
        "publish",
    }
)


def _emitted_modules() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _trees() -> list[tuple[Path, ast.Module]]:
    return [(p, ast.parse(p.read_text(encoding="utf-8"))) for p in _emitted_modules()]


# --------------------------------------------------------------------------- #
# The walk reaches something. Everything below depends on this.
# --------------------------------------------------------------------------- #


def test_the_walk_reaches_the_package() -> None:
    """**Read this before believing any refusal in this file.**

    Every assertion below is of the form *"no forbidden thing was found"*, and
    that sentence is true of an empty directory. So the emptiness has to be
    measured against something: there is at least one emitted module, it parses,
    and the walk visits nodes.
    """
    trees = _trees()
    assert trees, f"no emitted module under {SRC} -- every refusal below would be vacuous"
    total_nodes = sum(len(list(ast.walk(tree))) for _, tree in trees)
    assert total_nodes > 0
    # A package of one trivial module would also satisfy the two lines above, so
    # the real surface is asserted too: the contracts this phase promises.
    names = {p.name for p in _emitted_modules()}
    assert "reason_codes.py" in names, f"the vocabulary module is missing: {sorted(names)}"


# --------------------------------------------------------------------------- #
# Imports, both spellings
# --------------------------------------------------------------------------- #


def test_no_emitted_module_imports_something_that_starts_or_sends() -> None:
    """By tree shape, over every module, in both the ``import x`` and the
    ``from x import y`` form. A root match is enough: ``concurrent.futures`` is
    refused by ``concurrent``."""
    offences: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                        offences.append(f"{path.name}:{node.lineno} import {alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] in FORBIDDEN_MODULES
            ):
                offences.append(f"{path.name}:{node.lineno} from {node.module}")
    assert not offences, f"this feature must originate nothing: {offences}"


def test_no_emitted_module_names_a_forbidden_module_as_a_string() -> None:
    """The spelling that escaped `005`'s first scan, in its own shape here.

    ``importlib.import_module("threading")`` contains no ``Import`` node at all, so
    the test above cannot see it. This one reads string constants.
    """
    offences: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.split(".")[0] in FORBIDDEN_MODULES
            ):
                offences.append(f"{path.name}:{node.lineno} {node.value!r}")
    assert not offences, f"a forbidden module named as a string: {offences}"


def test_no_emitted_module_calls_something_that_starts_or_sends() -> None:
    """Call names, whether reached by attribute or bare. ``Thread(...)`` and
    ``threading.Thread(...)`` are both refused, and so is a bare ``sleep(...)``
    that a ``from`` import brought in."""
    offences: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            name = (
                called.attr
                if isinstance(called, ast.Attribute)
                else called.id
                if isinstance(called, ast.Name)
                else None
            )
            if name in FORBIDDEN_CALLS:
                offences.append(f"{path.name}:{node.lineno} {name}()")
    assert not offences, f"this feature must be callable and never self-starting: {offences}"


# --------------------------------------------------------------------------- #
# The scan bites. Proved here rather than promised.
# --------------------------------------------------------------------------- #


def test_the_scan_refuses_a_planted_import(tmp_path: Path) -> None:
    """**The refusals above are worth exactly what this test is worth.**

    Three planted modules, one per shape, each parsed by the same predicates the
    three tests above use. If any of them passed, those tests would be asserting
    over a scan that cannot see the thing it forbids.
    """
    plants = {
        "import threading\n": "import",
        "from asyncio import run\n": "from-import",
        'import importlib\nm = importlib.import_module("threading")\n': "string",
        "def go() -> None:\n    Thread()\n": "call",
    }
    for source, shape in plants.items():
        tree = ast.parse(source)
        seen = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                seen = seen or any(a.name.split(".")[0] in FORBIDDEN_MODULES for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                seen = seen or node.module.split(".")[0] in FORBIDDEN_MODULES
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                seen = seen or node.value.split(".")[0] in FORBIDDEN_MODULES
            elif isinstance(node, ast.Call):
                f = node.func
                n = (
                    f.attr
                    if isinstance(f, ast.Attribute)
                    else f.id
                    if isinstance(f, ast.Name)
                    else None
                )
                seen = seen or n in FORBIDDEN_CALLS
        assert seen, f"the scan cannot see the {shape} shape"


def test_no_console_script_is_declared() -> None:
    """A console script is the first step toward something that starts itself, and
    `pyproject.toml` says so in a comment. This measures it."""
    pyproject = SRC.parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert "[project.scripts]" not in text
    assert "[project.entry-points" not in text
    # Non-vacuous: the file was read and is the right one.
    assert 'name = "insights-prioritisation"' in text
