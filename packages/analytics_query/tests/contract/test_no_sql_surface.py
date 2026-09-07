"""SQL-surface static scan — T059 (FR-002; SC-001).

No module in the package may expose a parameter, field or function that accepts
SQL text. Asserted by inspection of the whole package rather than of the modules
someone remembered to check, because the defect this prevents is additive: a new
module with a `sql=` parameter would be invisible to every behavioural test.

`compile/guards.py` and `observations/bigquery_reader.py` legitimately *contain*
SQL — one inspects governed text, the other holds two fixed governed statements —
but neither accepts it from a caller. The distinction the scan enforces is
"accepts", not "mentions".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import analytics_query

pytestmark = pytest.mark.contract

SRC = Path(analytics_query.__file__).parent
_MODULES = sorted(SRC.rglob("*.py"))

_SQL_SHAPED = {
    "sql",
    "query_text",
    "statement",
    "raw_sql",
    "text_sql",
    "where",
    "predicate_sql",
    "expression",
}


def test_the_scan_sees_the_package() -> None:
    assert len(_MODULES) >= 15


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_function_accepts_sql_text(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for arg in [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]:
            if arg.arg.lower() not in _SQL_SHAPED:
                continue
            # A SQL-shaped *name* is only a surface if it carries text. The
            # observation runner names a statement from a closed enum, which is
            # the opposite of accepting one.
            annotation = ast.unparse(arg.annotation).strip().strip('"') if arg.annotation else "str"
            if annotation == "str" or annotation.endswith("| str"):
                offenders.append(f"{node.name}({arg.arg}: {annotation})")
    assert not offenders, f"{path.relative_to(SRC)} accepts SQL text: {offenders}"


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_class_declares_a_sql_field(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if (
                isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id.lower() in _SQL_SHAPED
            ):
                offenders.append(f"{node.name}.{stmt.target.id}")
    assert not offenders, f"{path.relative_to(SRC)} declares a SQL field: {offenders}"


def test_the_request_contract_exposes_no_sql_field() -> None:
    from analytics_query.contracts.request import AnalyticsQuery

    declared = {f.lower() for f in AnalyticsQuery.model_fields}
    assert not (declared & _SQL_SHAPED)


def test_the_only_module_holding_governed_statements_does_not_accept_them() -> None:
    """The observation reader's two statements are constants, not parameters."""
    import inspect

    from analytics_query.observations import bigquery_reader

    signature = inspect.signature(bigquery_reader.BigQueryObservationReader.read)
    assert set(signature.parameters) == {"self", "source_ids", "correlation_id"}


def test_the_observation_runner_names_a_statement_rather_than_supplying_one() -> None:
    """No SQL string crosses the runner boundary at all."""
    from analytics_query.observations.bigquery_reader import GovernedObservationStatement

    assert [s.value for s in GovernedObservationStatement] == [
        "source_freshness",
        "metric_availability",
    ]
    with pytest.raises(ValueError, match="is not a valid"):
        GovernedObservationStatement("SELECT * FROM `raw.events`")
