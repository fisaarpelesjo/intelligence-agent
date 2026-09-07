"""No query text exists anywhere — T091 (FR-027; SC-002).

    Zero questions produce SQL, a query fragment or any query text, verified by
    static scan of every artifact that can reach the execution boundary and of
    every response payload. — `SC-002`

This is the prohibition both upstream features exist to make structural, and
this feature inherits it whole. `002` compiles the request; compiling is `002`'s
alone (ADR 0010), and `003` submits a **typed contract** through the port rather
than anything resembling text.

**There is no path from question text to query text**, and the reason is worth
stating rather than asserting: the question is a ``str`` on ``QuestionIntake``,
and every step after intake consumes governed identifiers. The only place a
question crosses to anything is `001`'s search — which takes a term and returns
candidates — and the model port, which takes delimited data and returns an
identifier. Neither returns text this feature then puts anywhere.

Scanned by **identifier and by string constant**, never by whole-file text. Every
module that explains the prohibition necessarily writes the words "SQL" and
"query"; a text scan would fail on the explanation and teach the next author to
delete it. What must not exist is a *field* that could hold query text, a
*constant* that looks like a statement, or a *call* that would compile one.
"""

from __future__ import annotations

import ast
import inspect
import re
from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel

import analytics_interaction
from analytics_interaction import contracts
from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_interaction.contracts.request_build import build_analytics_query

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

#: Field or identifier names that could carry query text.
QUERY_TEXT_NAMES = (
    "sql",
    "query_text",
    "querystring",
    "statement",
    "predicate",
    "where_clause",
    "select_clause",
    "from_clause",
    # Not bare `join`: `str.join` is how every governed identifier list is
    # rendered into a refusal message. The SQL sense is spelled out instead.
    "join_clause",
    "inner_join",
    "left_join",
    "subquery",
    "explain_plan",
    "query_plan",
    "compiled",
    "rendered_sql",
    "raw_query",
    "dml",
    "ddl",
)

#: Calls that compile or emit query text. `002` owns every one of them.
COMPILATION_CALLS = (
    "compile_query",
    "render_sql",
    "resolve_structure",
    "assert_emitted_text_is_safe",
    "perform_dry_run",
    "execute_bounded",
)

#: A string constant that looks like a statement. Anchored so ordinary prose
#: containing the word "select" does not match a fragment nobody wrote.
_STATEMENT = re.compile(
    r"\b(select\s+.+\s+from\s|insert\s+into\s|update\s+\w+\s+set\s|delete\s+from\s|"
    r"create\s+(table|view)\s|drop\s+table\s|with\s+\w+\s+as\s*\()",
    re.IGNORECASE,
)


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _identifiers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
    return found


def _string_constants(path: Path) -> list[str]:
    """String literals that are not docstrings.

    Docstrings are excluded deliberately: the modules that explain why no SQL
    exists have to write the word, and flagging the explanation would be the
    wrong lesson.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_the_scan_covers_the_package() -> None:
    """A scan over nothing passes for the wrong reason."""
    assert len(_sources()) > 40


# --- no field, identifier or constant can hold query text -----------------------


@pytest.mark.parametrize("name", QUERY_TEXT_NAMES)
def test_no_module_declares_a_query_text_surface(name: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {identifier}"
        for path in _sources()
        for identifier in _identifiers(path)
        if name in identifier.lower()
    ]
    assert not offenders, f"a query-text surface exists: {offenders}"


@pytest.mark.parametrize("name", QUERY_TEXT_NAMES)
def test_no_governed_contract_declares_a_query_text_field(name: str) -> None:
    """Checked on the models as well as the source, so a dynamic field is caught."""
    offenders: list[str] = []
    for candidate in vars(contracts).values():
        if not (isinstance(candidate, type) and issubclass(candidate, BaseModel)):
            continue
        offenders.extend(
            f"{candidate.__name__}.{field}"
            for field in candidate.model_fields
            if name in field.lower()
        )
    assert not offenders, f"a contract can hold query text: {offenders}"


def test_no_string_constant_looks_like_a_statement() -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {constant[:60]!r}"
        for path in _sources()
        for constant in _string_constants(path)
        if _STATEMENT.search(constant)
    ]
    assert not offenders, f"a query fragment is authored: {offenders}"


@pytest.mark.parametrize("call", COMPILATION_CALLS)
def test_no_module_invokes_compilation(call: str) -> None:
    """Compiling is `002`'s, and ADR 0010 keeps it there."""
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if called == call:
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
    assert not offenders, f"compilation is invoked: {offenders}"


def test_the_scan_reads_identifiers_and_constants_rather_than_prose() -> None:
    """The modules that explain the prohibition must be allowed to.

    `request_build.py` writes "No SQL, no fragment, no predicate, no plan" in its
    docstring — that is the documentation working, and a text scan would fail on
    it.
    """
    source = (SRC / "contracts" / "request_build.py").read_text(encoding="utf-8")
    assert "No SQL" in source, "the prohibition is documented"
    assert not any(
        "sql" in name.lower() for name in _identifiers(SRC / "contracts/request_build.py")
    )


def test_the_scan_would_catch_a_planted_fragment() -> None:
    """A denylist never shown to fire proves nothing."""
    assert _STATEMENT.search("SELECT installs FROM semantic.metrics")
    assert _STATEMENT.search("with recent as (select 1)")
    assert not _STATEMENT.search("the system selects from the governed vocabulary")


# --- the built request carries no text -----------------------------------------


def test_a_built_request_serialises_to_identifiers_and_dates_only(
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    authorized, fingerprint = authorized_pair
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    rendered = request.model_dump_json()

    assert not _STATEMENT.search(rendered)
    for forbidden in ("select", "where", "from ", "join", "quantas", "instalações"):
        assert forbidden not in rendered.lower(), f"the request carried {forbidden!r}"


def test_the_request_contract_declares_no_text_field_at_all() -> None:
    """`002`'s six public fields, and none of them is text a caller wrote."""
    from analytics_query.contracts.request import AnalyticsQuery

    assert tuple(AnalyticsQuery.model_fields) == (
        "metrics",
        "dimensions",
        "sources",
        "filters",
        "date_range",
        "as_of",
    )


def test_no_path_carries_the_question_into_the_request(
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The intent holds positions, not spans, so there is nothing to carry.

    Asserted end to end: a request built from an intent whose resolutions record
    offsets contains no offset either — the positions are for the caller to
    highlight with, and they stop at the intent.
    """
    authorized, fingerprint = authorized_pair
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    rendered = request.model_dump_json()
    assert "start" in rendered  # the date range's, not a term's
    assert '"length"' not in rendered
    assert "matched_via" not in rendered
    assert date(2026, 7, 1).isoformat() in rendered
