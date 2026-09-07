"""The report fills to twenty without the loop being touched — `T829`, `T830`.

## What Phase F actually has to prove

`FR-816`: step two wires the remaining nineteen KPIs **and the report fills to twenty with
no edit to the loop**. That is a property of the code, not of a diff somebody remembers to
look at — so it is asserted here as *the loop knows no KPI by name and counts to no total*.

**If Phase B had enumerated instead of derived**, this is where it would show: a package that
carries a KPI name, a section name, or the number twenty cannot fill to twenty without being
edited, because the twenty-first would need a line adding.

## And the value column is the one place inference would hide

`FR-806` says the column carrying a KPI's number is **declared in that metric's catalog
contract** and read from there — *the loop MUST NOT infer it*. A mapping from `format_type`
to a column, written in this package, would be that inference wearing a table. It is asserted
absent here rather than trusted.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package.
PACKAGE = Path(__file__).resolve().parents[2]
SOURCE = PACKAGE / "src" / "daily_reporting"

#: The view's own value columns. Naming one in this package would be the loop deciding
#: where a number lives, which is the metric contract's job.
VALUE_COLUMNS = ("value_usd", "value_brl")

#: Totals a package that enumerated would carry. Twenty is the KPI count and five is the
#: section count, and either one written here is a number that ages the day the business
#: gains a KPI.
ENUMERATED_TOTALS = (20, 5, 19)


def _modules() -> list[Path]:
    return sorted(path for path in SOURCE.rglob("*.py") if "__pycache__" not in path.parts)


def test_the_sweep_reaches_this_package() -> None:
    """A sweep over nothing forbids nothing — the `F115` shape."""
    assert len(_modules()) >= 8, f"the sweep found {len(_modules())} modules"


def _string_constants(tree: ast.Module) -> list[str]:
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]


def test_no_module_names_a_currency_value_column() -> None:
    """`FR-806`. The column is the metric contract's answer, never this package's."""
    offending: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offending.extend(
            f"{path.name} names {text!r}"
            for text in _string_constants(tree)
            if text in VALUE_COLUMNS
        )
    assert not offending, "\n".join(offending)


def test_the_column_sweep_would_catch_an_inferred_mapping() -> None:
    """**Proof it bites**, over the shape the inference actually takes."""
    smuggled = ast.parse('COLUMN_FOR = {"brl": "value_brl", "usd_avg": "value_usd"}\n')
    found = _string_constants(smuggled)
    assert any(text in VALUE_COLUMNS for text in found), f"the sweep misses {found}"


def test_no_module_carries_a_kpi_or_section_total() -> None:
    """Nothing here counts to twenty, to five, or to nineteen.

    Excludes the numbers this feature legitimately owns: a complete week is seven, and the
    displayed precision is two. Neither is a count of KPIs.
    """
    offending: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
                continue
            if isinstance(node.value, int) and node.value in ENUMERATED_TOTALS:
                offending.append(f"{path.name}:{node.lineno} carries {node.value}")
    assert not offending, (
        "these are counts of KPIs or sections, and a package that carries one cannot fill "
        "to twenty without being edited:\n" + "\n".join(offending)
    )


def test_the_total_sweep_would_catch_an_enumeration() -> None:
    """**Proof it bites**, over the shape an enumeration takes."""
    smuggled = ast.parse("EXPECTED_KPIS = 20\n")
    found = [
        node.value
        for node in ast.walk(smuggled)
        if isinstance(node, ast.Constant) and isinstance(node.value, int)
    ]
    assert any(value in ENUMERATED_TOTALS for value in found), f"the sweep misses {found}"


# --------------------------------------------------------------------------- #
# THE NAMES HALF, WHICH THIS FILE PROMISED AND DID NOT MEASURE UNTIL 2026-08-28.
#
# The module docstring above said "a package that carries a KPI name, A SECTION NAME, or
# the number twenty cannot fill to twenty without being edited". The numbers half was
# measured; the names half was prose. The reviewer's mutation proved it: `_SECOES =
# ("Acquisition", "Retention", "Revenue")` inserted into `view/shape.py` -- the module that
# DERIVES the sections -- left the package at 96 passed and nothing bit.
#
# `tests/integration/test_no_name_from_the_view_is_written_here.py` now forbids every name
# the VIEW states, derived from the source rather than listed. It SKIPS on a machine with
# no credential, and the node below is what holds without one: it drives the same predicate
# with the reviewer's own mutation, so the sweep cannot go quietly vacuous.
# --------------------------------------------------------------------------- #


def test_the_name_sweep_would_catch_the_reviewers_mutation(tmp_path: Path) -> None:
    """**Proof the sweep bites**, over the exact edit that slipped past 96 nodes.

    Fed through the same `names_written_in_source` the view-driven node uses, so this
    measures that function rather than a second copy of its reasoning.
    """
    from tests.integration.test_no_name_from_the_view_is_written_here import strings_in

    smuggled = tmp_path / "shape_with_an_enumeration.py"
    smuggled.write_text('_SECOES = ("Acquisition", "Retention", "Revenue")\n', encoding="utf-8")
    written = set(strings_in(smuggled))
    forbidden = {"Acquisition", "Retention", "Revenue", "New trials"}
    assert written & forbidden == {"Acquisition", "Retention", "Revenue"}, (
        f"the sweep does not see the enumeration it exists to catch: {sorted(written)}"
    )


def test_the_name_sweep_ignores_what_this_package_legitimately_says(tmp_path: Path) -> None:
    """Otherwise it would be red always, which is a node nobody keeps.

    Column names, refusal vocabulary and exported symbols are the SHAPE of the source and
    of this package. Only the view's own content is forbidden.
    """
    from tests.integration.test_no_name_from_the_view_is_written_here import strings_in

    legitimate = tmp_path / "shape_without_one.py"
    legitimate.write_text(
        '__all__ = ["Section"]\nKPI_NAME_COLUMN = "kpi_name"\nRATE = "pct"\n',
        encoding="utf-8",
    )
    written = set(strings_in(legitimate))
    assert "Section" not in written, "an __all__ entry was counted as content"
    assert written == {"kpi_name", "pct"}, sorted(written)
