"""No KPI name and no section name is written in this package — `T830`, `FR-803`.

## The half `T830` promised and did not measure

Its docstring said *"a package that carries a KPI name, A SECTION NAME, or the number
twenty cannot fill to twenty without being edited"*. The numbers half was measured; **the
names half was prose.** The reviewer's mutation proved it: ``_SECOES = ("Acquisition",
"Retention", "Revenue")`` inserted into `view/shape.py` — the module that DERIVES the
sections — left the package at **96 passed** and nothing bit.

Two reasons, and neither was vacuity:

* `tests/contract/test_the_loop_enumerates_nothing.py` walks every module but forbids only
  the two value columns and three counts;
* `tests/contract/test_only_his_words_are_authored_here.py` catches an authored string but
  reads **two** modules, and `view/shape.py` is not one of them.

**The undefended place was exactly where an enumeration would be born.**

## Why the forbidden names come from the view

A list written here would age the day the business gains a KPI — which is the defect
`T830` exists to prevent, reproduced inside its own guard. So the names are read from the
source, with `SELECT` and nothing else.

**Without a credential this SKIPS**, loudly, and that is the honest weakness: on a machine
that cannot reach the warehouse this file guards nothing, and
`test_the_name_sweep_would_catch_the_reviewers_mutation` is what still holds without one.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

#: `tests/integration/` -> `tests/` -> package.
PACKAGE = Path(__file__).resolve().parents[2]
SOURCE = PACKAGE / "src" / "daily_reporting"

VIEW = "`example-project-id.semantic.subscription_daily_metrics`"


def _modules() -> list[Path]:
    return sorted(path for path in SOURCE.rglob("*.py") if "__pycache__" not in path.parts)


def strings_in(path: Path) -> list[str]:
    """Every string literal in ``path``, docstrings and ``__all__`` entries excluded.

    Docstrings are for the reader of the source; ``__all__`` holds NAMES, not content. Both
    exclusions were earned by earlier runs of this package's own guards.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
    }
    exported: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
            and isinstance(node.value, ast.List | ast.Tuple)
        ):
            exported.update(
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
        and node.value not in exported
    ]


def names_written_in_source(forbidden: Iterable[str]) -> list[str]:
    """**The one predicate**, used by the node that reads the view and by its proof.

    Defined once so the proof measures this function rather than a second copy of its
    reasoning — the recommendation the reviewer left on `006` and this package applies
    rather than relearns.
    """
    wanted = {name.strip() for name in forbidden if name and name.strip()}
    found: list[str] = []
    for path in _modules():
        found.extend(
            f"{path.name} carries {text!r}" for text in strings_in(path) if text.strip() in wanted
        )
    return sorted(found)


def _names_from_the_view() -> tuple[set[str], set[str]]:
    """Every `kpi_name` and `section_name` the view states. `SELECT` and nothing else."""
    try:
        from google.cloud import bigquery
    except ImportError:  # pragma: no cover - environment without the client
        pytest.skip("google-cloud-bigquery is not installed; NOTHING was checked here")
    try:
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
    except ImportError:  # pragma: no cover - environment without the auth library
        pytest.skip("google-auth is not installed; NOTHING was checked here")
    try:
        client = bigquery.Client()
        rows = list(client.query(f"SELECT DISTINCT kpi_name, section_name FROM {VIEW}").result())
    except DefaultCredentialsError:  # pragma: no cover - a machine with no credential
        pytest.skip("no Google credential is configured; NOTHING was checked here")
    except RefreshError as expired:  # pragma: no cover - an expired credential
        pytest.skip(
            "the BigQuery credential is absent or expired; since OD-62 the remedy is the "
            "service account via GOOGLE_APPLICATION_CREDENTIALS "
            f"(docs/credencial-bigquery-service-account.md): {expired}; NOTHING was checked here"
        )
    return (
        {str(row["kpi_name"]) for row in rows},
        {str(row["section_name"]) for row in rows},
    )


def test_the_view_answers_names_at_all() -> None:
    """Read this before believing the node below: an empty set forbids nothing."""
    kpis, sections = _names_from_the_view()
    assert kpis and sections, "the view answered no names, so nothing below is forbidden"


def test_no_module_writes_a_name_the_view_states() -> None:
    """`FR-803`. The set and its labels are the view's, and this package carries neither."""
    kpis, sections = _names_from_the_view()
    offending = names_written_in_source(kpis | sections)
    assert not offending, (
        "these are names the view states, written into a package whose whole claim is that "
        "it derives them:\n" + "\n".join(offending)
    )
