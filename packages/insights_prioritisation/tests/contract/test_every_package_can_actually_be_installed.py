"""A package whose tests pass and whose build fails is a package nobody has assembled.

**This file exists because `insights_prioritisation` was not installable for as long as it
existed, and every gate was green the whole time.** Its `pyproject.toml` declared `readme =
"README.md"` and the file was never written, so `pip install -e .` failed with *"Readme file
does not exist"*. Nothing noticed, and the reason nothing noticed is worth writing down: every
gate runs each suite through pytest's own rootdir, with the sources reachable by path. **No gate
ever installed anything.** So the whole repository could be un-buildable and every suite would
stay green.

It was found the only way it could be — by something outside the suites trying to use the
package. The bot harness was wired to import `005` and `006` and could not, because neither was
installed, and installing revealed the broken metadata.

## What is asserted, and why it is derived rather than listed

The packages are discovered on disk. A list written here would pass by not naming the package
somebody added last week, which is the failure this repository keeps paying for in other files.

Two properties, and they fail for different reasons:

1. **every file a package's metadata REFERENCES exists** — the readme today, and the criterion
   is the declaration rather than the filename, so a package pointing at `DESCRIPTION.rst`
   is checked against `DESCRIPTION.rst`;
2. **every package is importable**, which is the one that proves an install actually happened.
   A path a test bends to reach is not an install, so this asks the interpreter, not the disk.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path
from typing import cast

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
PACKAGES = REPO / "packages"


def _declared_packages() -> list[tuple[str, Path, dict[str, object]]]:
    """Every package on disk, with the name its own metadata declares.

    The distribution name is READ rather than derived from the directory: they agree today by
    convention, and a convention is not a guarantee. `importlib` needs the module name, which is
    the distribution name with hyphens turned back into underscores -- that mapping is Python's
    own and is applied here rather than hardcoded per package.
    """
    found: list[tuple[str, Path, dict[str, object]]] = []
    for manifest in sorted(PACKAGES.glob("*/pyproject.toml")):
        with manifest.open("rb") as handle:
            document = tomllib.load(handle)
        raw = document.get("project")
        if not isinstance(raw, dict):
            continue
        # `tomllib.load` answers a mapping whose values are untyped, so everything taken out of
        # it is untyped too. Declared once, where the file is read, rather than at each use.
        project = cast("dict[str, object]", raw)
        name = project.get("name")
        assert isinstance(name, str), f"{manifest} declares no project name"
        found.append((name, manifest.parent, project))
    return found


def test_there_are_packages_to_check() -> None:
    """The premise. An empty sweep would make every assertion below vacuously true."""
    assert _declared_packages(), "no package was found under packages/, so nothing was checked"


def test_every_file_a_package_declares_actually_exists() -> None:
    """**The exact defect, for every package at once.**

    `readme` is the field that broke, and it is checked by READING THE DECLARATION rather than
    by looking for `README.md`: a package that points somewhere else must be checked against
    where it points, and a package that declares no readme must not be invented one.
    """
    missing: list[str] = []
    for name, directory, project in _declared_packages():
        readme = project.get("readme")
        if readme is None:
            continue
        assert isinstance(readme, str), (
            f"{name} declares a readme this node cannot read as a path: {readme!r}"
        )
        if not (directory / readme).is_file():
            missing.append(f"{name} -> {readme}")
    assert not missing, (
        "these packages declare a file their build will look for and will not find, so they "
        f"cannot be installed at all: {missing}"
    )


def test_every_package_is_importable() -> None:
    """**Installed, not merely on disk.**

    This is what a path-based suite cannot tell you. Every gate reaches these sources by rootdir,
    so a package that was never installed looks identical to one that was -- until something
    outside the suites tries to import it, which is how the defect was found.
    """
    unimportable: list[str] = []
    for name, _directory, _project in _declared_packages():
        module = name.replace("-", "_")
        try:
            importlib.import_module(module)
        except ImportError as exc:
            unimportable.append(f"{module}: {exc}")
    assert not unimportable, (
        "these packages are on disk and not importable, so the environment does not hold what "
        f"the repository declares: {unimportable}"
    )
