"""Dependency direction — T018 (SC-004).

`001` and `002` are upstream. Neither may import `analytics_interaction`.

The reason is not tidiness. If `002` imported this package, `002`'s suite would
begin failing for reasons this feature owns, and ADR 0010's claim that the
upstream change was *additive* would stop being checkable — you could no longer
run `001` and `002` and conclude anything about them alone. The one-way arrow is
what keeps the three suites independently meaningful.

Checked against the AST, matching `002`'s own boundary guard: a module name in a
docstring or behind a comment is not an import, and a scan that cannot tell the
difference produces failures nobody trusts.

This file also carries the **packaging-level** half of the structural
prohibitions the feature is built around. The behavioural halves belong to their
own later tasks — no SQL surface (T053), no model narration (T091), no value
reachable from a model-facing type (T084, T085) — and those tasks assert against
implemented code. What is assertable *today*, with only a scaffold on disk, is
that the tree contains no place for them to hide: no declared provider
dependency, no SQL-named module, no result-value module. Asserting it now means a
later task cannot introduce one quietly and have its own guard written around it.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
TASKS_003 = REPO / "specs" / "003-nl-analytics-interaction" / "tasks.md"
CATALOG_SRC = REPO / "packages" / "semantic_catalog" / "src" / "semantic_catalog"
QUERY_SRC = REPO / "packages" / "analytics_query" / "src" / "analytics_query"
INTERACTION_SRC = REPO / "packages" / "analytics_interaction" / "src" / "analytics_interaction"
PYPROJECT = REPO / "packages" / "analytics_interaction" / "pyproject.toml"

THIS_PACKAGE = "analytics_interaction"

#: Roots that would put a model provider, an HTTP client or a warehouse client
#: inside this package's runtime. `D-20` is undeclared: there is no approved
#: provider, so declaring one here would be inventing the decision the record
#: exists to hold open. A future provider arrives behind its own ADR and its own
#: confined adapter subpackage, exactly as `002`'s ADR 0007 did for BigQuery.
FORBIDDEN_RUNTIME_ROOTS = frozenset(
    {
        "openai",
        "anthropic",
        "google",
        "google-cloud-bigquery",
        "google-generativeai",
        "vertexai",
        "cohere",
        "litellm",
        "langchain",
        "transformers",
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "asyncpg",
    }
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." * node.level + (node.module or ""))
    return found


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _declared_dependencies() -> list[str]:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    declared: list[str] = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)
    return declared


def _distribution_name(requirement: str) -> str:
    """The bare distribution name from a requirement string.

    ``"pydantic==2.11.9"`` -> ``"pydantic"``. Enough to recognise a root; this is
    not a full PEP 508 parser and does not need to be.
    """
    name = requirement.strip()
    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";", " @"):
        name = name.split(separator)[0]
    return name.strip().lower()


# --- the arrow points one way ------------------------------------------------


@pytest.mark.parametrize(
    ("root", "package"),
    [(CATALOG_SRC, "semantic_catalog"), (QUERY_SRC, "analytics_query")],
)
def test_an_upstream_package_never_imports_this_one(root: Path, package: str) -> None:
    offenders = [
        f"{path.relative_to(REPO)} imports {module}"
        for path in _python_files(root)
        for module in _imported_modules(path)
        if module.split(".")[0] == THIS_PACKAGE
    ]
    assert not offenders, f"{package} must not depend on {THIS_PACKAGE}: " + "; ".join(offenders)


def test_the_guard_detects_a_reverse_import() -> None:
    """A boundary test that has never been shown to fail proves nothing.

    The planted source is what a violation would actually look like, run through
    the same extractor the guard uses.
    """
    planted = REPO / "packages" / "analytics_query" / "src" / "analytics_query" / "__init__.py"
    tree = ast.parse("import analytics_interaction.contracts\n", filename=str(planted))
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert any(name.split(".")[0] == THIS_PACKAGE for name in names)


def test_the_guard_detects_a_reverse_from_import() -> None:
    """`from x import y` is the form the plain-import check would miss."""
    tree = ast.parse("from analytics_interaction.execution import port\n")
    modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert any(module.split(".")[0] == THIS_PACKAGE for module in modules)


@pytest.mark.parametrize("root", [CATALOG_SRC, QUERY_SRC, INTERACTION_SRC])
def test_the_scanned_trees_exist_and_are_non_empty(root: Path) -> None:
    """Guards that silently scan nothing are worse than no guards."""
    assert root.is_dir(), f"missing source tree: {root}"
    assert _python_files(root), f"no Python files found under {root}"


# --- the scaffold declares no way to bypass the governed path ----------------


def test_no_model_provider_warehouse_or_http_dependency_is_declared() -> None:
    """`D-20` is undeclared, so no provider may be declared here.

    Runtime *and* dev: a provider reachable only from tests is still a provider
    in the lockfile, and a test that reaches one is a test that leaves the
    fixture-backed world this feature is required to stay inside.
    """
    offenders = [
        requirement
        for requirement in _declared_dependencies()
        if _distribution_name(requirement) in FORBIDDEN_RUNTIME_ROOTS
    ]
    assert not offenders, (
        "no LLM provider, warehouse client, HTTP client or database driver may be declared "
        f"while D-20 is undeclared: {offenders}"
    )


def test_the_only_upstream_distributions_are_the_two_approved_packages() -> None:
    """Everything else in the stack is reached through `001` and `002`.

    A third first-party distribution appearing here would be a new dependency
    edge nobody approved.
    """
    first_party = {
        _distribution_name(requirement)
        for requirement in _declared_dependencies()
        if _distribution_name(requirement).startswith(("semantic-", "analytics-"))
    }
    assert first_party == {"semantic-catalog", "analytics-query"}


def test_the_source_tree_declares_no_sql_or_result_value_module() -> None:
    """No place for query text or a result-value type to live.

    The behavioural guards are later tasks — T053 for the SQL surface, T084/T085
    for value reachability. This is the structural precondition: a module named
    for either concept cannot appear during scaffolding and then have its guard
    written around it.
    """
    named = {
        path.relative_to(INTERACTION_SRC).as_posix()
        for path in _python_files(INTERACTION_SRC)
        if any(
            token in path.stem.lower() for token in ("sql", "query_text", "rows", "cells", "values")
        )
    }
    assert not named, f"the scaffold must contain no SQL or result-value module: {sorted(named)}"


#: Phase 1 is exactly T013-T019: the package, its trees, the empty governed
#: content and these two guards. Implementation belongs to T020 onward.
PHASE_1 = tuple(range(13, 20))

_EXTERNAL_RECORD = "[BLOCKED-EXTERNAL]"
_TASK_LINE = re.compile(r"^- \[([ xX])\] T(\d{3})\b(?P<rest>.*)$", re.MULTILINE)


def executable_task_states(tasks_markdown: str) -> dict[int, bool]:
    """``{task number: complete}`` for every executable task.

    External records are excluded rather than read as incomplete: they are not
    work items and no automation may complete one, so counting them would make
    every derived verdict permanently false.
    """
    return {
        int(match.group(2)): match.group(1) in {"x", "X"}
        for match in _TASK_LINE.finditer(tasks_markdown)
        if _EXTERNAL_RECORD not in match.group("rest")
    }


def phase_1_incomplete(states: dict[int, bool]) -> list[int]:
    """Which of T013-T019 are not yet done, missing tasks included.

    Fail-closed on absence: a task the ledger does not mention is not evidence
    of completion.
    """
    return [number for number in PHASE_1 if not states.get(number, False)]


def implementation_modules() -> list[str]:
    """Every source module that is not a documented package marker."""
    return sorted(
        path.relative_to(INTERACTION_SRC).as_posix()
        for path in _python_files(INTERACTION_SRC)
        if path.name != "__init__.py"
    )


def violates_phase_ordering(tasks_markdown: str, has_implementation: bool) -> bool:
    """The invariant: implementation exists ⇒ Phase 1 is complete.

    A predicate rather than an inline assertion so the regression cases exercise
    the same code path the live check does.
    """
    if not has_implementation:
        return False
    return bool(phase_1_incomplete(executable_task_states(tasks_markdown)))


def test_implementation_may_exist_only_once_phase_1_is_complete() -> None:
    """The persistent form of the scaffolding boundary.

    This replaced a spent assertion — *"Phase 1 adds no implementation module"* —
    which was true only while Phase 1 was in flight and expired the moment `T020`
    legitimately added `contracts/_base.py`. An assertion that fails on correct
    work is not protection; it is noise waiting to be deleted, and deleting it
    would lose the ordering it was there for.

    The property worth keeping does not expire: **implementation may exist only
    once the package, its trees, the governed content and the two boundary
    guards do.** It is derived from `003`'s recorded task states — not the branch
    name, not the commit history, not the presence of files — for the same reason
    the Phase A0 guard in `002` is: the task ledger is what records whether the
    prerequisite was met.
    """
    tasks = TASKS_003.read_text(encoding="utf-8")
    outstanding = phase_1_incomplete(executable_task_states(tasks))
    if implementation_modules():
        assert not outstanding, (
            "implementation exists while Phase 1 is unfinished; outstanding: "
            + ", ".join(f"T{number:03d}" for number in outstanding)
        )


def test_the_phase_1_task_ledger_is_readable_and_complete() -> None:
    """A guard that reads no tasks would fire against correct work.

    If `003`'s ledger stopped parsing, ``phase_1_incomplete`` would report all
    seven outstanding. Better to fail here, naming the cause.
    """
    assert TASKS_003.is_file(), f"missing Feature 003 task ledger: {TASKS_003}"
    states = executable_task_states(TASKS_003.read_text(encoding="utf-8"))
    missing = [number for number in PHASE_1 if number not in states]
    assert not missing, f"Phase 1 tasks absent from the ledger: {missing}"


_PHASE_1_COMPLETE = "\n".join(f"- [X] T{n:03d} Phase 1 task" for n in PHASE_1)
_PHASE_1_PARTIAL = "\n".join(f"- [{'X' if n < 19 else ' '}] T{n:03d} Phase 1 task" for n in PHASE_1)


def test_no_implementation_with_phase_1_incomplete_passes() -> None:
    """Mid-Phase-1, before T020. The ordinary state during scaffolding."""
    assert not violates_phase_ordering(_PHASE_1_PARTIAL, has_implementation=False)


def test_implementation_with_phase_1_incomplete_fails() -> None:
    """The violation the guard exists for."""
    assert violates_phase_ordering(_PHASE_1_PARTIAL, has_implementation=True)


def test_implementation_with_phase_1_complete_passes() -> None:
    """The state that legitimately expired the old assertion."""
    assert not violates_phase_ordering(_PHASE_1_COMPLETE, has_implementation=True)


def test_a_completed_later_task_does_not_substitute_for_phase_1() -> None:
    """T020+ progress is not evidence the prerequisite was met."""
    ledger = _PHASE_1_PARTIAL + "\n- [X] T020 Implement the frozen base"
    assert violates_phase_ordering(ledger, has_implementation=True)
    assert phase_1_incomplete(executable_task_states(ledger)) == [19]


@pytest.mark.parametrize("marker", [" ", "X"])
def test_external_record_state_has_no_effect_on_the_decision(marker: str) -> None:
    """T182-T185 are dependency records, not work.

    Asserted against a complete ledger and an incomplete one, so the
    parametrization cannot pass by both sides being false.
    """
    records = "\n".join(
        f"- [{marker}] T{n} `{_EXTERNAL_RECORD}` **D-{n - 164} — external capability**"
        for n in range(182, 186)
    )
    assert not violates_phase_ordering(f"{_PHASE_1_COMPLETE}\n{records}", has_implementation=True)
    assert violates_phase_ordering(f"{_PHASE_1_PARTIAL}\n{records}", has_implementation=True)
    assert executable_task_states(records) == {}
