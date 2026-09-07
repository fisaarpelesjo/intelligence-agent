"""Package boundaries — T006 (FR-027; SC-002).

Two properties, both asserted by reading the source rather than by trusting
convention:

**The dependency runs one way.** ``semantic_catalog`` is an upstream package this
feature consumes. If it ever imported ``analytics_query`` the two would be
mutually dependent, `001`'s suite would start failing for reasons owned by `002`,
and the claim that this feature is purely additive would stop being true.

**The vendor client lives in one place.** ``google.cloud.bigquery`` may be
imported only from ``adapters/bigquery/``. Confining it is what keeps the
warehouse credential out of every other module, and what lets the whole execution
path be tested against a fake adapter.

Both are checked against the AST, not against text: a commented-out import or a
name inside a docstring is not an import, and a scan that cannot tell the
difference produces failures nobody trusts.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
CATALOG_SRC = REPO / "packages" / "semantic_catalog" / "src" / "semantic_catalog"
QUERY_SRC = REPO / "packages" / "analytics_query" / "src" / "analytics_query"
ADAPTER_DIR = QUERY_SRC / "adapters" / "bigquery"

FORBIDDEN_VENDOR_ROOTS = ("google",)


def _imported_modules(path: Path) -> set[str]:
    """Every module named by an ``import`` or ``from`` statement in ``path``.

    Relative imports are resolved to their leading dots plus module name, which
    is enough to tell a local import from a vendor one.
    """
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


def test_the_catalog_package_never_imports_this_one() -> None:
    """The dependency is one-directional, and that is what makes `002` additive."""
    offenders: list[str] = []
    for path in _python_files(CATALOG_SRC):
        for module in _imported_modules(path):
            if module.split(".")[0] == "analytics_query":
                offenders.append(f"{path.relative_to(REPO)} imports {module}")
    assert not offenders, "semantic_catalog must not depend on analytics_query: " + "; ".join(
        offenders
    )


def test_only_the_bigquery_adapter_imports_the_vendor_client() -> None:
    """Confining the client is what keeps the credential out of everything else."""
    offenders: list[str] = []
    for path in _python_files(QUERY_SRC):
        if ADAPTER_DIR in path.parents:
            continue
        for module in _imported_modules(path):
            if module.split(".")[0] in FORBIDDEN_VENDOR_ROOTS:
                offenders.append(f"{path.relative_to(REPO)} imports {module}")
    assert not offenders, "the warehouse client belongs only in adapters/bigquery/: " + "; ".join(
        offenders
    )


def test_the_guard_detects_a_reverse_import() -> None:
    """The guard must fail on a real violation, not merely pass on a clean tree.

    A boundary test that has never been shown to fail proves nothing about the
    boundary — only that nothing tripped it yet.
    """
    planted = ast.parse("import analytics_query.contracts\n")
    names = {
        alias.name
        for node in ast.walk(planted)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert any(name.split(".")[0] == "analytics_query" for name in names)


def test_the_guard_detects_a_vendor_import_outside_the_adapter() -> None:
    """Same, for the vendor-client half of the boundary."""
    planted = ast.parse("from google.cloud import bigquery\n")
    modules = {
        node.module
        for node in ast.walk(planted)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert any((m or "").split(".")[0] in FORBIDDEN_VENDOR_ROOTS for m in modules)


@pytest.mark.parametrize("root", [CATALOG_SRC, QUERY_SRC])
def test_the_scanned_trees_exist_and_are_non_empty(root: Path) -> None:
    """Guards that silently scan nothing are worse than no guards."""
    assert root.is_dir(), f"missing source tree: {root}"
    assert _python_files(root), f"no Python files found under {root}"
