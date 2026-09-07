"""This feature composes no prose and starts nothing — `T804`, `T810`.

## No prose

`SC-809`, and it is the property that decided `OD-15-A`: **where there is no prose,
there is no sentence claiming more than was measured.** The check is that no formatted
string in the emitting modules carries a literal fragment of more than one word — `": "`
and `" ("` are separators, *"rose by"* is a claim.

## Nothing originates

`FR-823`. A run is CALLED and receives its instant as a parameter — the same constraint
`005`, `006` and `007` carry. No scheduler, no timer, no thread, no event loop, and no
console script, measured over the tree rather than promised in a comment.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: `tests/security/` -> `tests/` -> package.
PACKAGE = Path(__file__).resolve().parents[2]
SOURCE = PACKAGE / "src" / "daily_reporting"

#: Modules and calls that make something happen without being asked.
FORBIDDEN_IMPORTS = {
    "asyncio",
    "sched",
    "schedule",
    "threading",
    "multiprocessing",
    "signal",
    "apscheduler",
    "socket",
    "http",
    "urllib",
    "requests",
    "httpx",
}
FORBIDDEN_CALLS = {"sleep", "Timer", "Thread", "Process", "run_forever", "call_later", "now"}


def _modules() -> list[Path]:
    return sorted(path for path in SOURCE.rglob("*.py") if "__pycache__" not in path.parts)


def test_the_sweep_reaches_this_package() -> None:
    """A sweep over nothing forbids nothing."""
    assert len(_modules()) >= 8, f"the sweep found {len(_modules())} modules"


def _literal_fragments(tree: ast.AST) -> list[str]:
    """The literal parts of every f-string, which is where a sentence would hide.

    **What a `raise` carries is excluded, and the exclusion is STRUCTURAL.** A refusal message
    is read by a developer reading a traceback; it never reaches his chat, so a sentence there
    is not composed prose. The exclusion used to be the name prefix `_refuse`, and that was a
    convention rather than a fact: `breakdown.py` and `references.py` refuse from
    `__post_init__` and `from_document`, and a name-matching guard called their refusals prose.
    A string that only ever reaches a `raise` cannot reach a person, whatever its function is
    called.
    """
    excluded = {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        for inner in ast.walk(node)
    }
    fragments: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and id(node) not in excluded:
            fragments.extend(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
    return fragments


def _is_a_sentence(fragment: str) -> bool:
    """More than one word joined by a space is a claim, not a separator."""
    return len([word for word in fragment.split() if any(c.isalpha() for c in word)]) > 1


def test_no_emitted_string_carries_a_sentence() -> None:
    """Refusal messages are excluded by :func:`_literal_fragments`: a traceback is not his chat."""
    # DERIVED, not listed. A fixed pair was the defect: `report/contribution.py` was born
    # after the list and would have composed prose behind a guard that never looked at it.
    # Everything that renders lives under `report/`, so everything under `report/` is scanned.
    emitting = tuple(sorted((SOURCE / "report").glob("*.py")))
    assert emitting, "the rendering package has no modules; the scan would pass over nothing"
    offending: list[str] = []
    for path in emitting:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            offending.extend(
                f"{path.name}:{function.name} composes {fragment!r}"
                for fragment in _literal_fragments(function)
                if _is_a_sentence(fragment)
            )
    assert not offending, "\n".join(offending)


def test_the_prose_scan_would_catch_a_sentence() -> None:
    """**Proof it bites.** The plausible one: a report that read a little bluntly."""
    smuggled = ast.parse('def r(kpi, n):\n    return f"{kpi} subiu para {n} esta semana"\n')
    fragments = _literal_fragments(smuggled)
    assert any(_is_a_sentence(fragment) for fragment in fragments), (
        f"the scan accepts a composed sentence: {fragments}"
    )


def test_a_separator_is_not_a_sentence() -> None:
    """Otherwise the node would be red always, which is a node nobody keeps."""
    for separator in (": ", " (", ")", " *", " ", ""):
        assert not _is_a_sentence(separator), f"{separator!r} was counted as a sentence"


def test_nothing_here_imports_a_way_to_start_itself() -> None:
    offending: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            line = 0
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                line = node.lineno
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
                line = node.lineno
            offending.extend(
                f"{path.name}:{line} imports {name}"
                for name in names
                if name.split(".")[0] in FORBIDDEN_IMPORTS
            )
    assert not offending, "\n".join(offending)


def test_nothing_here_calls_a_way_to_start_itself() -> None:
    """`now()` is on the list: a run receives its instant, it does not read a clock."""
    offending: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            name = (
                called.attr
                if isinstance(called, ast.Attribute)
                else called.id
                if isinstance(called, ast.Name)
                else ""
            )
            if name in FORBIDDEN_CALLS:
                offending.append(f"{path.name}:{node.lineno} calls {name}")
    assert not offending, "\n".join(offending)


def test_the_origination_scan_would_catch_a_scheduler() -> None:
    """**Proof it bites**, in both the import spelling and the call spelling."""
    smuggled = ast.parse("import threading\n\nthreading.Timer(60, run).start()\n")
    imported = [
        alias.name
        for node in ast.walk(smuggled)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    called = [
        node.func.attr
        for node in ast.walk(smuggled)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert any(name in FORBIDDEN_IMPORTS for name in imported), "the import scan misses it"
    assert any(name in FORBIDDEN_CALLS for name in called), "the call scan misses it"


def test_this_package_declares_no_console_script() -> None:
    """A console script is the first step toward something that starts itself."""
    manifest = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    project = manifest.get("project", {})
    assert "scripts" not in project, "this package declares a console script"
    assert "entry-points" not in project, "this package declares an entry point"
    assert "gui-scripts" not in project
