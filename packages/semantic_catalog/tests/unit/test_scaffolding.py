"""Structural scaffolding checks for the T001-T004 skeleton.

These assert the package and test trees exist as the plan describes. They carry no
domain logic; the first behavioural tests arrive with T047 onward.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

SUBPACKAGES = (
    "contracts",
    "loader",
    "resolution",
    "periods",
    "freshness",
    "comparability",
    "validation",
    "provenance",
    "search",
    "compliance",
    "cli",
)

FIXTURE_DIRS = (
    "decision_matrix",
    "versioned_catalog",
    "deprecated_catalog",
    "coverage",
    "freshness",
    "revisions",
    "policy",
    "approvals",
    "adversarial",
)

TEST_ROOTS = ("contract", "unit", "integration")


@pytest.mark.unit
@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_importable(name: str) -> None:
    """T001: every declared subpackage imports."""
    assert importlib.import_module(f"semantic_catalog.{name}") is not None


@pytest.mark.unit
@pytest.mark.parametrize("root", TEST_ROOTS)
def test_test_root_exists(root: str) -> None:
    """T004: pytest discovers all three test roots."""
    assert (Path(__file__).parents[1] / root).is_dir()


@pytest.mark.unit
@pytest.mark.parametrize("name", FIXTURE_DIRS)
def test_fixture_dir_exists(name: str) -> None:
    """T004: every fixture directory named in quickstart.md exists."""
    assert (Path(__file__).parents[1] / "fixtures" / name).is_dir()
