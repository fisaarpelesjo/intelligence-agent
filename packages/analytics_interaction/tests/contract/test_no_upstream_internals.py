"""Port narrowness — T019 (FR-028; SC-003, SC-004).

ADR 0010's load-bearing clause: `003` composes nothing. It calls one public
entry point and receives a result or a governed refusal.

    `003` imports **no** module under `analytics_query.compile`,
    `analytics_query.execution`, `analytics_query.results`,
    `analytics_query.decision`, `analytics_query.policy`,
    `analytics_query.observations` or `analytics_query.identity`.
    A blocking CI gate asserts it. — ADR 0010

This file is that gate.

**Why an import ban and not a review note.** Every one of those seven subpackages
is a *stage* of `002`'s approved ordering — compile, guards, dry run, bounded
execution, shape verification, mid-flight check, assembly, suppression,
`finalise()`. A consumer that can import them can assemble its own ordering: the
same stages, one of them dropped, and nothing in the type system objects. The
result would still typecheck, still return an `AnalyticsResult`, and would have
skipped a gate. Refusing the import is what makes "one path" structural instead
of aspirational.

The ban is on `003`'s source tree. Fixtures under `tests/` may reach further —
building a fake port means naming the contracts it satisfies — but no production
module may.

`002`'s own `test_single_execution_path.py` guards the other half from the other
side: that the entry point does not become a second path alongside
`run_until_evaluation`. Together they say there is exactly one way in and exactly
one thing it does.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
INTERACTION_SRC = REPO / "packages" / "analytics_interaction" / "src" / "analytics_interaction"
QUERY_SRC = REPO / "packages" / "analytics_query" / "src" / "analytics_query"

#: The seven internal subpackages ADR 0010 names, verbatim.
FORBIDDEN_SUBPACKAGES = (
    "compile",
    "execution",
    "results",
    "decision",
    "policy",
    "observations",
    "identity",
)

#: What `003` may reach in `002`: the composed entry point, and the typed
#: contracts needed to name its inputs and read its outputs. `contracts` is data,
#: not ordering — importing `AnalyticsQuery` cannot execute anything.
PERMITTED_QUERY_MODULES = ("analytics_query.execute", "analytics_query.contracts")

#: `002`'s internals that are *not* under one of the seven names — private by the
#: leading underscore rather than by subpackage. `pipeline` is the steps 1-7
#: stage the entry point composes; calling it directly is the precise bypass ADR
#: 0010's "single path" clause forbids.
FORBIDDEN_QUERY_MODULES = (
    "analytics_query.pipeline",
    "analytics_query.adapters",
    "analytics_query.audit",
    "analytics_query.authorization",
    "analytics_query.compliance",
    "analytics_query.messages",
    "analytics_query.cli",
)


def _imported_modules(path: Path) -> set[str]:
    """Absolute module names imported by ``path``.

    Relative imports are skipped deliberately: a relative import inside
    `analytics_interaction` can only reach `analytics_interaction`, so it can
    never be an upstream-internal violation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _upstream_imports() -> list[tuple[Path, str]]:
    return [
        (path, module)
        for path in _python_files(INTERACTION_SRC)
        for module in _imported_modules(path)
        if module.split(".")[0] == "analytics_query"
    ]


def _is_within(module: str, root: str) -> bool:
    """``module`` is ``root`` or lives under it.

    Prefix comparison alone would match ``analytics_query.executed_elsewhere``
    against ``analytics_query.execute``; the dot boundary is what makes the
    match a package relationship rather than a string one.
    """
    return module == root or module.startswith(root + ".")


# --- the seven named subpackages ---------------------------------------------


@pytest.mark.parametrize("subpackage", FORBIDDEN_SUBPACKAGES)
def test_no_source_module_imports_a_named_internal(subpackage: str) -> None:
    root = f"analytics_query.{subpackage}"
    offenders = [
        f"{path.relative_to(REPO)} imports {module}"
        for path, module in _upstream_imports()
        if _is_within(module, root)
    ]
    assert not offenders, f"ADR 0010 forbids importing {root}: " + "; ".join(offenders)


@pytest.mark.parametrize("subpackage", FORBIDDEN_SUBPACKAGES)
def test_each_forbidden_subpackage_actually_exists_upstream(subpackage: str) -> None:
    """A ban on a module that does not exist guards nothing.

    If `002` renames one of these, this fails immediately rather than leaving a
    silently dead clause behind — which is how an import ban rots into a comment.
    """
    assert (QUERY_SRC / subpackage).is_dir(), (
        f"ADR 0010 names analytics_query.{subpackage}, which is no longer present"
    )


# --- and everything else that is not the entry point -------------------------


@pytest.mark.parametrize("module_name", FORBIDDEN_QUERY_MODULES)
def test_no_source_module_imports_another_upstream_internal(module_name: str) -> None:
    """The seven are the named cases, not the whole rule.

    `pipeline` in particular: it is steps 1-7, which the entry point composes
    with 8 and 9. Reaching it directly gets a preflight decision with no
    execution behind it — the single-path clause's exact failure mode.
    """
    offenders = [
        f"{path.relative_to(REPO)} imports {module}"
        for path, module in _upstream_imports()
        if _is_within(module, module_name)
    ]
    assert not offenders, f"{module_name} is a 002 internal: " + "; ".join(offenders)


def test_every_upstream_import_resolves_to_the_permitted_surface() -> None:
    """Stated positively, so a *new* `002` module is denied by default.

    The parametrized bans above enumerate what is known today. This one closes
    the set: anything not on the permitted list fails, including a subpackage
    that does not exist yet.
    """
    offenders = [
        f"{path.relative_to(REPO)} imports {module}"
        for path, module in _upstream_imports()
        if not any(_is_within(module, allowed) for allowed in PERMITTED_QUERY_MODULES)
    ]
    assert not offenders, (
        f"only {list(PERMITTED_QUERY_MODULES)} are reachable from 003: " + "; ".join(offenders)
    )


def test_no_private_upstream_name_is_imported() -> None:
    """An underscore-prefixed module is private however it is spelled.

    `002` marks internals both ways — by subpackage and by leading underscore.
    ``analytics_query.contracts._base`` is on the permitted *package* but is not
    part of the public surface.
    """
    offenders = [
        f"{path.relative_to(REPO)} imports {module}"
        for path, module in _upstream_imports()
        if any(part.startswith("_") for part in module.split("."))
    ]
    assert not offenders, "private upstream modules are not importable: " + "; ".join(offenders)


# --- the guard fails on a real violation --------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "from analytics_query.execution.bounded import execute_bounded\n",
        "import analytics_query.compile\n",
        "from analytics_query.pipeline import run_until_evaluation\n",
        "from analytics_query.contracts._base import build\n",
        "from analytics_query.results import assemble_result\n",
    ],
)
def test_the_guard_rejects_a_planted_internal_import(source: str) -> None:
    """Each planted line is a bypass someone could plausibly write.

    Run through the same extractor and the same predicates the guard uses, so a
    weakening of either shows up here.
    """
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)

    permitted = all(
        any(_is_within(module, allowed) for allowed in PERMITTED_QUERY_MODULES)
        and not any(part.startswith("_") for part in module.split("."))
        for module in modules
    )
    assert not permitted, f"the guard would have allowed: {source!r}"


def test_the_guard_accepts_the_entry_point_itself() -> None:
    """It must not fire on the one import the whole design depends on.

    Without this the suite could pass with a guard that rejected everything —
    which would block the feature rather than protect it.
    """
    tree = ast.parse("from analytics_query.execute import execute_analytics_query\n")
    modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert all(
        any(_is_within(module, allowed) for allowed in PERMITTED_QUERY_MODULES)
        for module in modules
    )


def test_the_entry_point_exists_and_exports_what_the_port_will_wrap() -> None:
    """The permitted surface is real, not a name this file made up.

    T097 builds the port over exactly these three; naming them here means a
    change to `002`'s public surface fails at this boundary rather than nine
    phases later.
    """
    entry_point = QUERY_SRC / "execute.py"
    assert entry_point.is_file(), "ADR 0010's composed entry point is missing"

    tree = ast.parse(entry_point.read_text(encoding="utf-8"), filename=str(entry_point))
    exported: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
            and isinstance(node.value, ast.List)
        ):
            exported = {
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    assert exported == {"ExecutedAnswer", "ExecutionRefused", "execute_analytics_query"}


def test_the_scanned_tree_exists_and_is_non_empty() -> None:
    """A guard that scans nothing passes for the wrong reason."""
    assert INTERACTION_SRC.is_dir(), f"missing source tree: {INTERACTION_SRC}"
    assert _python_files(INTERACTION_SRC), f"no Python files under {INTERACTION_SRC}"
