"""No import crosses a package boundary into a private module — `FR-008`.

**This node exists because a defect walked under twelve green ones.**

`test_no_upstream_file_was_edited` opens by promising that *"upstream is consulted
through its exported surface and never widened"*. What it **measures** is whether
an upstream file was edited — against git, which is the right instrument for that
claim. An import through a private path edits nothing, so it satisfies every one
of its assertions while breaking the sentence they are written under.

Measured on 2026-08-26, in `ports/figures_port.py`:

```
from analytics_interaction.contracts._base import ContractViolation
```

`ContractViolation` **is** exported — it sits in `analytics_interaction.contracts.__all__`
— so the handoff sentence *"every name used was already exported"* was true about the
name. `FR-008` is about the exported **surface**, and `_base` is not on it. **True
about the name, false about the path**, and no instrument in the repository could
tell the two apart.

## What this asserts, and why it is structural rather than a list

Every `import` and `from ... import` in this package's `src/` that names an
**upstream package** must name a path in which **no component begins with an
underscore**. Not a list of allowed modules: a list ages, and this repository has
deleted one before for that reason. The rule reads off the path itself, so it holds
for modules that do not exist yet.

**Intra-package private imports stay legal, and that is deliberate.** `_base` inside
`anomaly_investigation` is this feature's own module, and a package reaching into its
own internals is not crossing a boundary. Measured before writing this: every other
`_base` import in the package is relative and intra-package.

It needs no credential, no network and no git, so it runs everywhere the suite runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
SRC = REPO / "packages" / "anomaly_investigation" / "src"

#: The four packages this feature consults. The same tuple
#: `test_no_upstream_file_was_edited` uses, written out rather than imported from it:
#: two nodes sharing a constant fail together, and these two are supposed to catch
#: different things.
UPSTREAM = ("semantic_catalog", "analytics_query", "analytics_interaction", "channel_integration")


def _modules() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _imported_paths(tree: ast.Module) -> list[str]:
    """Every dotted module path this file imports, absolute ones only.

    A relative import (`from ..contracts import X`) has `level > 0` and is skipped:
    it cannot name another package, so it cannot cross the boundary this node is
    about.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module)
    return found


def test_there_are_modules_to_scan() -> None:
    """**Read this before believing the node below.**

    An empty scan passes vacuously, which is the failure mode every file-walking
    assertion carries. The count is compared against the directory rather than
    against a number written here.
    """
    modules = _modules()
    assert modules, f"no module was found under {SRC}; the node below asserted nothing"


def test_the_scan_actually_sees_upstream_imports() -> None:
    """And a second guard, for a subtler emptiness.

    Modules could exist while none of them imports upstream at all — then the node
    below would also be vacuous. So the scan is required to *find* the thing it
    filters on.
    """
    seen = [
        path
        for path in _modules()
        if any(
            imported.split(".")[0] in UPSTREAM
            for imported in _imported_paths(ast.parse(path.read_text(encoding="utf-8")))
        )
    ]
    assert seen, "no module imports upstream; this file's filter matches nothing"


@pytest.mark.parametrize("module", _modules(), ids=lambda path: path.name)
def test_no_upstream_import_names_a_private_module(module: Path) -> None:
    """The property, per file so a failure names the module rather than the set."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    offending = [
        imported
        for imported in _imported_paths(tree)
        if imported.split(".")[0] in UPSTREAM
        and any(part.startswith("_") for part in imported.split("."))
    ]
    assert not offending, (
        f"{module.relative_to(REPO).as_posix()} imports upstream through a private path: "
        f"{offending}. FR-008 is about the exported SURFACE — a name being in some "
        "__all__ does not make the module it lives in part of it."
    )
