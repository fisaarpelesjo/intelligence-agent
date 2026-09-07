"""T120 — no analytical machinery is **reachable** from this feature (`SC-046`, `FR-092`).

`004` transports questions and answers. It must not be able to compute one. That is asserted here
as a reachability property rather than a style rule: the concern is not that a module looks like a
query engine, but that starting from any `channel_integration` entry point and following imports
there is
**no path** to a warehouse client, a SQL string, a catalog loader, a compiler, an executor, a
decision pipeline or a policy resolver.

## Why this is not `test_dependency_direction`

That file asserts which upstream *modules* are imported, and `T119` asserts which upstream *names*
are. Both stop at the first hop. This one is about what those hops make reachable, and about
machinery that needs no import at all — an f-string holding `SELECT ... FROM` is a SQL string
whether or not anything upstream was imported, and a locally written cost model is a decision
pipeline nobody imported from anywhere.

So the three gates compose: the direction gate says which doors exist, `T119` says which names come
through them, and this one says what is on the other side.

## The transitive closure is computed, not assumed

`_reachable_from` walks first-party imports from every `src/` module until the set stops growing. A
forbidden surface two hops away is reachable, and "we only import the safe wrapper" is exactly the
shape this is built to catch.

Upstream packages are **boundaries, not frontier**: `003` legitimately reaches an executor, and
following imports into it would report `004` as reaching one too, which is false. What `004` may
name upstream is already enumerated by `T119`, so the walk stops at the package edge and the
allowlist carries that half.

## Textual surfaces are matched on source, and the scan excludes nothing

A gate naming `SELECT` in its own body would match itself — so this file lives under `tests/` and
the scan reads `src/` only. That is asserted below rather than trusted, because the cheapest way to
make a static scan pass is to stop scanning.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _package_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "channel_integration").is_dir():
            return parent
    raise AssertionError("package root not found")


_PACKAGE = _package_root()
_SRC = _PACKAGE / "src" / "channel_integration"
_THIS_FILE = Path(__file__).resolve()

#: Client libraries and drivers. Reaching one means this feature can talk to a warehouse.
_FORBIDDEN_CLIENTS = frozenset(
    {
        "google",
        "bigquery",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "pyodbc",
        "sqlite3",
        "duckdb",
        "pandas",
        "polars",
        "pyarrow",
        "numpy",
    }
)

#: Upstream modules whose job **is** the analytical machinery. `004` may reach the published
#: contracts of `002` and `003`; it may not reach the parts that decide, compile or execute.
#: Enumerated as prefixes because a submodule of an executor is an executor.
_FORBIDDEN_UPSTREAM = (
    "analytics_query.execution",
    "analytics_query.compilation",
    "analytics_query.compile",
    "analytics_query.plan",
    "analytics_query.cost",
    "analytics_query.warehouse",
    "analytics_interaction.orchestration",
    "analytics_interaction.interpretation",
    "analytics_interaction.governance",
    "semantic_catalog.loader",
    "semantic_catalog.load",
    "semantic_catalog.search",
    "semantic_catalog.resolution",
    "semantic_catalog.governance",
)

#: SQL written as text. Matched as paired keywords: one keyword alone appears in prose, a pair in
#: order does not appear by accident.
_SQL_SHAPES = (
    re.compile(r"\bSELECT\b[\s\S]{0,200}?\bFROM\b", re.IGNORECASE),
    re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"\b(?:UPDATE|DELETE)\s+\w+\s+(?:SET|WHERE)\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)\b", re.IGNORECASE),
    re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE),
)

#: Names that would mean this feature grew its own decision machinery. Matched against **defined**
#: names — a `def` or `class` — never against arbitrary text, so prose describing the absence of a
#: compiler does not fail the gate that proves the absence.
_FORBIDDEN_DEFINITIONS = re.compile(
    r"(?:^|_)(?:compile|compiler|executor|execute_query|policy_resolver|resolve_policy|"
    r"load_catalog|catalog_loader|interpret|rank_candidates|estimate_cost|build_sql|"
    r"render_sql|plan_query)(?:_|$)",
    re.IGNORECASE,
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _module_name(path: Path) -> str:
    relative = path.relative_to(_SRC.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports_of(path: Path) -> set[str]:
    """Every module ``path`` imports, with relative imports resolved to absolute names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    own = _module_name(path)
    package = own if path.name == "__init__.py" else own.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                if node.level > 1:
                    base = base[: len(base) - (node.level - 1)]
                prefix = ".".join(base)
                found.add(f"{prefix}.{node.module}" if node.module else prefix)
            elif node.module:
                found.add(node.module)
    return found


def _reachable_from(start: Path) -> set[str]:
    """The transitive closure of first-party imports, stopping at every package edge.

    Only `channel_integration` modules are expanded. Anything else is recorded and not followed:
    following an upstream module would attribute its whole import graph to this feature.
    """
    by_name = {_module_name(path): path for path in _python_files(_SRC)}
    seen: set[str] = set()
    frontier = [_module_name(start)]
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        path = by_name.get(name)
        if path is None:
            #: A module outside this package. Recorded — every gate above reads `seen` — but not
            #: expanded, so an upstream package's own import graph is never attributed here.
            continue
        for imported in _imports_of(path):
            if imported not in seen:
                frontier.append(imported)
    return seen


def test_no_warehouse_client_is_reachable_from_any_entry_point() -> None:
    """Transitively, from every module. A client two hops away is still a client."""
    offenders: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        hits = sorted(
            name for name in _reachable_from(source) if name.split(".")[0] in _FORBIDDEN_CLIENTS
        )
        if hits:
            offenders[str(source.relative_to(_PACKAGE))] = hits
    assert not offenders, (
        f"a warehouse or dataframe client is reachable: {offenders}. `004` transports an answer it "
        "was given; a client here would let it fetch one"
    )


def test_no_upstream_decision_or_execution_module_is_reachable() -> None:
    """The published contracts are permitted. The machinery behind them is not."""
    offenders: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        hits = sorted(
            name
            for name in _reachable_from(source)
            if any(name == bad or name.startswith(bad + ".") for bad in _FORBIDDEN_UPSTREAM)
        )
        if hits:
            offenders[str(source.relative_to(_PACKAGE))] = hits
    assert not offenders, (
        f"an upstream compiler, executor, loader, decision pipeline or policy resolver is "
        f"reachable: "
        f"{offenders}. Reaching one would give this feature a second path to an answer, and no "
        "upstream gate would see it"
    )


def _executable_strings(path: Path) -> list[str]:
    """Every string literal that is **not** a docstring, plus the literal parts of every f-string.

    Scanning raw source instead was measurably wrong: `inbound/schemes/generic.py` says "the
    registry can select material per client ... instead of sharing one secret" and a
    `SELECT ... FROM` shape
    matched the English. Prose lives in docstrings and comments; a query would live in a value.

    So the scan reads values. That is narrower than the file text and it is the narrowing that makes
    the gate mean something — a hit is now a string the program could hand to something.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))

    values: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            values.append(node.value)
    return values


def test_no_module_holds_a_sql_string() -> None:
    """SQL as text, which needs no import and would therefore pass every import gate."""
    offenders: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        hits = sorted(
            {
                shape.pattern
                for shape in _SQL_SHAPES
                for value in _executable_strings(source)
                if shape.search(value)
            }
        )
        if hits:
            offenders[str(source.relative_to(_PACKAGE))] = hits
    assert not offenders, f"SQL text found in a string literal under src: {offenders}"


def test_the_sql_scan_reads_values_and_would_catch_one() -> None:
    """The narrowing is proven not to have narrowed the gate to nothing.

    Two facts, both measured rather than asserted about the code: the scan sees a real query when
    one is present in a value, and it does not see the docstring prose that made the raw-source form
    report a false hit.
    """
    planted = ast.parse('QUERY = "SELECT total FROM revenue GROUP BY month"')
    values = [
        node.value
        for node in ast.walk(planted)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert any(shape.search(value) for shape in _SQL_SHAPES for value in values), (
        "the shapes do not match an actual query, so the scan above is decorative"
    )

    prose = _SRC / "inbound" / "schemes" / "generic.py"
    assert prose.is_file(), "the module that produced the false positive moved; re-derive this node"
    assert any(shape.search(prose.read_text(encoding="utf-8")) for shape in _SQL_SHAPES), (
        "the false positive is gone from the source, so this node no longer proves the narrowing"
    )
    assert not any(
        shape.search(value) for shape in _SQL_SHAPES for value in _executable_strings(prose)
    ), "the value scan reports the prose too, so nothing was actually narrowed"


def test_no_module_defines_analytical_machinery() -> None:
    """Locally written machinery: a compiler nobody imported is still a compiler.

    Matched against `def` and `class` names collected with `ast`, so prose describing the absence of
    a thing cannot be mistaken for the thing.
    """
    offenders: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        defined = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        ]
        hits = sorted(name for name in defined if _FORBIDDEN_DEFINITIONS.search(name))
        if hits:
            offenders[str(source.relative_to(_PACKAGE))] = hits
    assert not offenders, (
        f"this feature defines analytical machinery: {offenders}. Writing one locally is the same "
        "capability as importing one, and it is the form no import gate can see"
    )


def test_the_scan_covers_src_and_skips_nothing() -> None:
    """Every file under `src/` is scanned, and this gate is not one of them.

    A static scan is worth exactly its coverage. This node exists because the cheapest way to make
    every assertion above pass is to stop scanning, and that failure mode is silent.
    """
    scanned = {path.resolve() for path in _python_files(_SRC)}
    assert _THIS_FILE not in scanned, "this gate lives under tests/, never under src/"
    assert scanned, "no src module was scanned, so every assertion above passed over nothing"

    on_disk = {path.resolve() for path in _SRC.rglob("*.py") if "__pycache__" not in path.parts}
    assert scanned == on_disk, f"these src modules are not scanned: {sorted(on_disk - scanned)}"

    modules = {path.name for path in scanned}
    for expected in ("convert.py", "render.py", "attempt.py", "port.py", "preserve.py"):
        assert expected in modules, f"{expected} is not being scanned"


def test_the_reachability_walk_actually_walks() -> None:
    """The closure is transitive, proven on a real multi-hop path rather than asserted.

    A walk that returned only direct imports would pass every gate above while missing exactly what
    they exist to catch. So: pick a module, and require that the closure holds substantially more
    than the module imports itself.
    """
    entry = _SRC / "cli" / "main.py"
    assert entry.is_file(), "the CLI entry point moved; pick another multi-hop module"

    direct = _imports_of(entry)
    closure = _reachable_from(entry)
    assert closure > direct, (
        "the closure equals the direct imports, so the walk is not transitive and every gate above "
        "is only checking one hop"
    )
    assert len(closure) > len(direct) + 2, (
        f"the closure adds only {len(closure) - len(direct)} modules beyond the direct imports, "
        "which is too shallow to be a real walk"
    )
