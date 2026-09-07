"""This package originates nothing — T028 (`FR-007`; `SC-004`).

**Written before the code it guards**, which the task list asks for in as many
words: *"T028 is best written early, so the guarantee is in place before there is
code that could break it."* A structural guarantee added after the fact only ever
proves what survived; added first, it decides what may be written.

The rule: **nothing in this package can start itself, schedule itself, or send.**
No scheduler, no timer, no thread, no event loop, no outbox write, no notify. A run
is *called*, and it receives its instant as a parameter.

This is the same shape `004` uses in ``test_reactive_only.py``, and it is why `005`
**cannot live inside** `channel_integration`: that node refuses these primitives
there, so detection would have had to either break it or pretend to be a channel
concern.

**The node fails first on an empty tree.** A walk that found nothing would pass by
doing nothing, and a green light over an unread directory is worse than no light —
so the file count is asserted before any refusal is.

`SC-004` quantifies over *"the modules this feature owns"*, and this file is where
that set is resolved: ``src/anomaly_investigation`` and nothing else.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: ``tests/security/`` -> ``tests/`` -> package root -> ``src/anomaly_investigation``.
SRC = Path(__file__).resolve().parents[2] / "src" / "anomaly_investigation"

#: Modules that would let something run without being called.
FORBIDDEN_MODULES = frozenset(
    {
        "asyncio",
        "concurrent",
        "multiprocessing",
        "sched",
        "signal",
        "socket",
        "socketserver",
        "subprocess",
        "threading",
        "http",
        "smtplib",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
    }
)

#: Names that start work, or send it somewhere.
FORBIDDEN_NAMES = frozenset(
    {
        "Thread",
        "Timer",
        "Process",
        "Pool",
        "create_task",
        "call_later",
        "call_soon",
        "run_forever",
        "run_until_complete",
        "ensure_future",
        "get_event_loop",
        "new_event_loop",
        "spawn",
        "fork",
        "notify",
        "alert",
        "broadcast",
        "publish",
        "emit",
        "send",
        "post",
        "enqueue",
    }
)

#: Substrings that make a name a scheduler whatever it is called.
FORBIDDEN_FRAGMENTS = ("schedule", "cron", "periodic", "background", "daemon", "poll", "outbox")


def _modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


MODULES = _modules()


def test_the_walk_reaches_the_package() -> None:
    """A node that read nothing would pass by doing nothing.

    This is asserted first and on purpose: every refusal below is vacuously true
    over an empty file list, and a vacuous pass is the defect the spec's own
    convention names — a criterion that can never fail is not a criterion.
    """
    assert MODULES, f"no modules found under {SRC}"
    assert (SRC / "__init__.py").is_file(), "the package root is missing"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_imports_a_way_to_start_itself(path: Path) -> None:
    """Imports are checked at the **root** of the dotted name.

    ``import concurrent.futures`` and ``from concurrent import futures`` are the
    same capability wearing two spellings, and checking the full string would
    catch neither reliably.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_MODULES]
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in FORBIDDEN_MODULES
        ):
            found.append(node.module)
    assert not found, f"{path.name} imports {found}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_defines_or_calls_something_that_originates(path: Path) -> None:
    """Definitions and calls, by identifier and by fragment.

    Both halves are needed. The identifier half catches ``Timer`` and
    ``create_task``; the fragment half catches ``_run_scheduled_sweep``, which no
    list of exact names would ever contain.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offences: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            lowered = node.name.lower()
            if node.name in FORBIDDEN_NAMES or any(f in lowered for f in FORBIDDEN_FRAGMENTS):
                offences.append(f"defines {node.name}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            offences.append(f"calls .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            offences.append(f"names {node.id}")

    assert not offences, f"{path.name}: {offences}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_defines_a_coroutine(path: Path) -> None:
    """``async def`` needs a loop to run, and a loop is something that runs on its own.

    Checked separately from the import rule because a coroutine can be defined
    without importing ``asyncio`` at all, and the caller would supply the loop.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    coroutines = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    assert not coroutines, f"{path.name} defines coroutines {coroutines}"


def test_nothing_executes_on_import() -> None:
    """Module level is declarations only — no call that does work at import time.

    Importing a package must not *do* anything. A call at module level runs the
    moment anything imports it, which is origination through the back door: the
    caller never asked for it and cannot decline it.

    Allowed at module level: imports, assignments, class and function definitions,
    docstrings. ``MappingProxyType(...)``, ``frozenset(...)`` and the like appear
    inside assignments, which is a declaration and not an action.
    """
    offences: list[str] = []
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                offences.append(f"{path.name}: bare call at module level")
    assert not offences, offences
