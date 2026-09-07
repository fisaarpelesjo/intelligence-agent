"""What this package imports, against what THIS package declares.

**The red that was invisible from inside the monorepo** -- `catalog.yml`, red since 2026-09-04.

Every workflow installs ONE package and then type-checks it: `pip install -e ".[dev]"` run
from inside `packages/semantic_catalog`. So the environment a gate builds for this package is
exactly what this package's own `[project]` table asks for -- and nothing else. A module
imported here but pinned one directory over is present on every developer machine, present in
the monorepo venv, present to `pytest`, and ABSENT on the runner.

That is why the defect could not be seen locally. `test_the_declared_direction_matches_the_source`
does `from google.cloud import bigquery` inside a credential-gated test; `google-cloud-bigquery`
is pinned by `packages/analytics_query`, never here. Locally pyright resolves it from the shared
venv and the push gate goes green. On the runner pyright reported

    tests/contract/test_the_declared_direction_matches_the_source.py:96:30
      - error: "bigquery" is unknown import symbol (reportAttributeAccessIssue)
    7 errors, 0 warnings, 0 informations

-- one unresolved import and six cascade errors behind it. Seventeen consecutive red runs.

The `@pytest.mark.skipif` on the credential protects EXECUTION and protects nothing else: a
static checker reads the body regardless, and a function-local import shields nothing from it.

The sibling instrument in `apps/telegram-bot/tests/test_dependencies.py` asks a different
question -- whether a name is pinned SOMEWHERE across the monorepo -- because the harness
declares nothing on purpose and is installed by installing the packages it exercises. This
package is installed alone, so the question here has to be narrower: pinned HERE.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

PACKAGE = Path(__file__).resolve().parent.parent.parent
MANIFEST = PACKAGE / "pyproject.toml"

#: Import name -> distribution name, for the cases where the two differ. A mapping rather than a
#: normalisation rule, because no rule connects `yaml` to `PyYAML` or `google` to any one of the
#: dozen distributions that share the namespace. Guessing here is how an undeclared import passes.
DISTRIBUTION_OF = {
    "google": "google-cloud-bigquery",
    "yaml": "PyYAML",
}


def _local_module_names() -> set[str]:
    """Names that are this package's own, so an internal import is not read as third-party."""
    local = {path.stem for path in (PACKAGE / "src").glob("*")}
    local |= {path.stem for path in (PACKAGE / "tests").rglob("*.py")}
    local.add("tests")
    return local


def imported_names() -> set[str]:
    """Every top-level module this package imports that is neither stdlib nor its own.

    Walked whole rather than top-level only, and that is the point rather than thoroughness for
    its own sake: the import that broke the runner lives INSIDE a function body, under a skip
    decorator. A scan reading only module-level imports would have called this package clean.
    """
    local = _local_module_names()
    stdlib = set(sys.stdlib_module_names)
    found: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            for module in modules:
                top = module.split(".")[0]
                if top not in stdlib and top not in local:
                    found.add(top)
    return found


def declared_distributions() -> set[str]:
    """Every distribution THIS manifest pins, runtime and extras alike.

    The extras are read as well as the runtime list, and they have to be: the runner installs
    `.[dev]`, so a name pinned only in `dev` IS present there. Reading `dependencies` alone
    would report `pytest` as undeclared and make the node lie in the opposite direction.
    """
    data = tomllib.loads(MANIFEST.read_bytes().decode("utf-8"))
    project = data["project"]
    requirements = list(project.get("dependencies", ()))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    return {
        re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0].strip() for requirement in requirements
    }


def test_every_third_party_import_is_pinned_by_THIS_package() -> None:  # noqa: N802
    """The property the runner enforces and no local run can: installed alone, this is enough.

    **Mutation**: drop `google-cloud-bigquery` from the manifest -> this fails and names it,
    which is the state the repository was in for seventeen red runs.
    """
    declared = declared_distributions()
    missing = {
        module: DISTRIBUTION_OF.get(module, module)
        for module in imported_names()
        if DISTRIBUTION_OF.get(module, module) not in declared
    }
    assert not missing, (
        "imported here and pinned nowhere in this package's own manifest, so the environment "
        f"the runner builds for it does not contain them: {missing}. Pinning it one package "
        "over is what made this invisible from inside the monorepo venv."
    )


def test_the_scan_reaches_an_import_INSIDE_a_function_body() -> None:  # noqa: N802
    """Proof the instrument bites where the defect actually lived.

    A module-level-only scan is green on this repository today, and would have been green on the
    day the runner went red. Asserting the scan's REACH keeps the check honest independently of
    whether any import happens to be missing right now: without this, narrowing the walk back to
    `ast.parse(...).body` would pass every node in this file.
    """
    source = (
        PACKAGE / "tests" / "contract" / "test_the_declared_direction_matches_the_source.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "google" not in top_level, (
        "the fixture this node depends on changed: the import moved to module level, so it no "
        "longer demonstrates the case a shallow scan misses"
    )
    assert "google" in imported_names(), (
        "the scan stopped reaching imports inside function bodies, which is exactly where the "
        "import that broke the runner lives"
    )
