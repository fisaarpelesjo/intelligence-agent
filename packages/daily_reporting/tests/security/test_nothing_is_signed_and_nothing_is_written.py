"""Three views stay unsigned, and nothing writes to the warehouse — `T831`, `T832`.

## `T831` — the three views that do not exist

`FR-821`. `product_daily_metrics`, `store_daily_metrics` and `stability_daily_metrics` were
checked one by one and **none of them exists**. The catalog metrics that point at them stay
**without data**, and this feature signs nothing on their behalf. Asserted over the catalog
the repository carries, so it holds on a machine with no warehouse.

## `T832` — and the self-reference this node had to avoid

`FR-822`. Everything this feature needs is a `SELECT`.

**A node that forbids a list of words CONTAINS that list**, so reading its own file raw
would make it accuse itself — the shape that appeared four times in this session's reviews.
The answer is to change **what the instrument reads**, not to except itself: this sweep
walks `src/` only, and inside `src/` it looks at the syntax tree for a write verb reaching a
CALL or a string that becomes a query — never at file text.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: `tests/security/` -> `tests/` -> package.
PACKAGE = Path(__file__).resolve().parents[2]
SOURCE = PACKAGE / "src" / "daily_reporting"


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


#: The three the owner's catalog points at and the warehouse does not hold. Named here
#: because their ABSENCE is the fact — there is nothing to derive them from.
VIEWS_THAT_DO_NOT_EXIST = (
    "product_daily_metrics",
    "store_daily_metrics",
    "stability_daily_metrics",
)

#: Every way a statement writes. Lower case; the scan folds case before comparing.
WRITE_VERBS = (
    "insert",
    "update",
    "delete",
    "merge",
    "truncate",
    "drop",
    "create",
    "alter",
    "replace",
    "write_truncate",
    "write_append",
)

#: What a string has to look like before a write verb inside it means anything.
#:
#: **The first draft used "from " and "where " and it accused this package's own prose.**
#: A docstring explaining that a column is read *from* a contract matched, and so did one
#: saying a default would *create* a mistake. A marker that fires on English is a marker
#: that measures nothing, so the shape is the shape a statement actually has: it BEGINS
#: with a SQL keyword -- INCLUDING the write verbs, because `DELETE FROM x` is a statement
#: that begins with none of the reading ones, and a rule that only recognised `select`
#: would have missed every write it exists to catch. That was the second draft, and its own
#: proof node said so by failing.
QUERY_START = re.compile(
    r"^\s*(select|with|insert|update|delete|merge|truncate|drop|create|alter|replace)\b",
    re.IGNORECASE,
)

#: The BigQuery client methods that write, named EXACTLY rather than by substring. The
#: first draft matched any name containing a verb and accused `dict.update()`.
WRITING_CALLS = frozenset(
    {
        "create_table",
        "create_dataset",
        "delete_table",
        "delete_dataset",
        "update_table",
        "update_dataset",
        "insert_rows",
        "insert_rows_json",
        "copy_table",
        "load_table_from_file",
        "load_table_from_json",
        "load_table_from_uri",
        "load_table_from_dataframe",
    }
)


def _modules() -> list[Path]:
    return sorted(path for path in SOURCE.rglob("*.py") if "__pycache__" not in path.parts)


def _catalog_metrics() -> list[Path]:
    return sorted((_repository_root() / "semantic" / "metrics").glob("*.yaml"))


def test_the_sweeps_reach_something() -> None:
    """A sweep over nothing forbids nothing — the `F115` shape, stated first as always."""
    assert len(_modules()) >= 10, f"the source sweep found {len(_modules())} modules"
    assert len(_catalog_metrics()) >= 10, (
        f"the catalog sweep found {len(_catalog_metrics())} metric contracts"
    )


def _referenced_views() -> dict[str, list[str]]:
    """Which view each metric contract points at, read from the contracts themselves."""
    referenced: dict[str, list[str]] = {}
    for path in _catalog_metrics():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("source_view:"):
                view = stripped.split(":", 1)[1].strip()
                referenced.setdefault(view, []).append(path.name)
    return referenced


def test_no_view_is_declared_as_a_source_anywhere_in_the_catalog() -> None:
    """`T831`, and **this is what "unsigned" means**, corrected on 2026-08-28.

    The first draft of this node asked whether a contract naming an absent view also carried
    `status: available` — and accused eight of them. **It was wrong.** `source_availability`
    declares a SOURCE, the app the numbers come from, and the view is a different thing: a
    reference under `source_view`, owned by the transformation feature and, as those files
    say themselves, *never dereferenced here*.

    So the property is the one that actually distinguishes signing from referencing: **no
    view name appears as a declared source**. Referencing an object that does not exist is a
    dangling pointer; declaring it available is the signature this feature must never write.
    """
    signed: list[str] = []
    root = _repository_root() / "semantic"
    for path in sorted(root.rglob("*.yaml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("- source:") and not stripped.startswith("source:"):
                continue
            named = stripped.split(":", 1)[1].strip()
            if named in VIEWS_THAT_DO_NOT_EXIST or named.startswith("semantic."):
                signed.append(f"{path.relative_to(root)} declares {named!r} as a source")
    assert not signed, chr(10).join(signed)


def test_only_one_referenced_view_is_the_one_the_warehouse_holds() -> None:
    """The twelfth metric is the only one with a view, and the other eleven are named.

    **Measured 2026-08-28 with `SELECT` on `INFORMATION_SCHEMA`: the `semantic` dataset holds
    three objects and exactly ONE view**, `subscription_daily_metrics`. Every other
    `source_view` in the catalog points at something that does not exist.

    **And there are FOUR absent views, not three.** The three this repository has been naming
    all week are joined by `retention_cohort_metrics`, which three retention metrics point at
    and which nobody had checked. It is named here rather than left for the next reader.

    ## RE-DERIVADO em 2026-08-30, e o numero era a metade fraca

    Isto afirmava que **UMA** metrica apontava para a view que existe. Era verdade e deixou de
    ser: a `T829` trouxe os dezenove KPIs restantes, e agora sao **vinte** — um por KPI que a
    view carrega. **Nada regrediu**; o que mudou foi o mundo que o numero fotografava, e um
    numero escrito precisa de edicao toda vez que ele decide alguma coisa.

    A propriedade que nunca moveu, e que e a que este arquivo existe para segurar: **as
    metricas backed apontam para a UNICA view que o armazem tem, e todas as demais apontam
    para as quatro que nao existem.** A separacao e o fato; a contagem de cada lado nao e.
    """
    referenced = _referenced_views()
    assert "semantic.subscription_daily_metrics" in referenced, (
        "no metric points at the one view that exists; the catalog lost its only backed metric"
    )
    backed = referenced["semantic.subscription_daily_metrics"]
    assert backed, "no metric is backed by the one view that exists"

    absent = {
        view: names
        for view, names in referenced.items()
        if view not in {"semantic.subscription_daily_metrics"}
    }
    assert set(absent) == {
        "semantic.product_daily_metrics",
        "semantic.store_daily_metrics",
        "semantic.stability_daily_metrics",
        "semantic.retention_cohort_metrics",
    }, (
        f"the set of views the catalog points at and the warehouse does not hold has changed: "
        f"{sorted(absent)}"
    )
    without_data = sorted(name for names in absent.values() for name in names)
    assert len(without_data) == 11, (
        f"{len(without_data)} metrics point at an absent view; the count moved and either a "
        f"view appeared or a metric was declared: {without_data}"
    )


def _string_constants(tree: ast.AST) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _looks_like_a_query(text: str) -> bool:
    """Does this string BEGIN like a statement? Prose that mentions a verb does not."""
    return bool(QUERY_START.match(text))


def writes_in(tree: ast.AST) -> list[str]:
    """**The one predicate.** Where a write verb reaches a call or a query this code builds.

    It never reads file text: a node forbidding these words contains them, and a raw-text
    sweep would accuse its own prohibition.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = node.func
            name = (
                called.attr
                if isinstance(called, ast.Attribute)
                else called.id
                if isinstance(called, ast.Name)
                else ""
            )
            if name in WRITING_CALLS:
                found.append(f"calls {name}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not _looks_like_a_query(node.value):
                continue
            lowered = node.value.lower()
            found.extend(
                f"builds a query carrying {verb!r}" for verb in WRITE_VERBS if verb in lowered
            )
        if isinstance(node, ast.JoinedStr):
            literal = "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if not _looks_like_a_query(literal):
                continue
            lowered = literal.lower()
            found.extend(
                f"interpolates a query carrying {verb!r}" for verb in WRITE_VERBS if verb in lowered
            )
    return sorted(set(found))


def test_nothing_under_this_feature_writes_to_the_warehouse() -> None:
    """`T832`, `FR-822`. Both halves: the word in a call, and the word in built text."""
    offending: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offending.extend(f"{path.name}: {what}" for what in writes_in(tree))
    assert not offending, "\n".join(offending)


def test_this_feature_builds_no_query_at_all_today() -> None:
    """Stronger than the above and true today, so it is said rather than left implied."""
    building: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        building.extend(
            f"{path.name} builds {text!r}"
            for text in _string_constants(tree)
            if _looks_like_a_query(text)
        )
    assert not building, (
        "this feature builds query text; the sweep above still holds, but the claim that it "
        "touches no warehouse at all no longer does:\n" + "\n".join(building)
    )


def test_the_write_sweep_would_catch_both_halves() -> None:
    """**Proof it bites**, over source this file parses rather than over the tree.

    Two shapes, because the two halves catch different things: the verb written into a
    module, and the verb arriving through interpolation.
    """
    written = ast.parse('SQL = "DELETE FROM semantic.subscription_daily_metrics"\n')
    assert writes_in(written), "the query sweep misses a write written straight in"

    interpolated = ast.parse('def go(t):\n    return f"DROP TABLE {t} FROM x"\n')
    assert writes_in(interpolated), "the query sweep misses a write reaching by f-string"

    called = ast.parse("client.delete_table(name)\n")
    assert writes_in(called), "the call sweep misses a writing API"


def test_a_select_is_not_a_write() -> None:
    """Otherwise the node would be red on the day this feature legitimately reads."""
    reading = ast.parse('SQL = "SELECT kpi_name FROM semantic.subscription_daily_metrics"\n')
    assert not writes_in(reading), "a SELECT was counted as a write"
