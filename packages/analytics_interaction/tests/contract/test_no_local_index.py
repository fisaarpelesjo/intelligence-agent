"""No local term index exists — T071 (FR-090; SC-052).

    `001`'s discovery surface is the **sole** source of candidates. — `FR-090`

    No local index, cache or derived term table exists. Building one would create
    a second, unfiltered copy of the catalog's vocabulary, and the first time it
    went stale it would resolve a term the catalog no longer governs.
    — `interpretation-contract.md` §2

Two failures, and the second is the dangerous one.

**Staleness** is the obvious risk: a copied term table outlives a deprecation and
keeps resolving a metric the catalog has retired.

**Unfiltered access** is the quiet one. `001`'s surface filters by access *before*
deciding the outcome shape, so an ambiguity a caller may not see never surfaces
as an ambiguity. A local index built once and consulted per request would have no
access context at all — every caller would see the same candidates, and the
symmetry between "not governed" and "not visible to you" would be gone.

Also asserted here: **this feature implements no matching of its own.** No fuzzy
comparison, no similarity threshold, no spell correction, no embedding, no
normalisation of the caller's phrasing. `001` owns the single threshold in the
stack and states why it is fixed; a second one here would make resolution depend
on two tuned numbers instead of one governed one.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.interpretation import resolve_terms

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
INTERPRETATION = SRC / "interpretation"

#: Names an index, cache or derived term table would arrive under.
INDEX_NAMES = (
    "term_index",
    "search_index",
    "build_index",
    "term_table",
    "term_cache",
    "vocabulary_cache",
    "candidate_cache",
    "synonym_map",
    "alias_map",
    "lookup_table",
    # ``_terms`` alone matched ``RESOLVE_TERMS`` — a telemetry span step, which
    # names a step of the sequence rather than a table of terms. A substring that
    # fires on a step name is one that gets deleted rather than narrowed, so the
    # index form is spelled out.
    "resolved_terms_index",
    "cached_terms",
)

#: Matching this feature must not implement.
MATCHING_NAMES = (
    "fuzzy",
    "similarity",
    "levenshtein",
    "jaro",
    "damerau",
    "match_ratio",
    "sequencematcher",
    "difflib",
    "embedding",
    "vector",
    "cosine",
    "spell",
    "autocorrect",
    # ``stem`` alone matched ``SystemExit`` — and would match ``Path.stem`` and
    # ``system`` too. Stemming is a technique here, not a substring; a scan that
    # fires on an exception name is one that gets deleted rather than narrowed.
    "stemmer",
    "stemming",
    "porter_stem",
    "snowball",
    "lemmat",
    "translat",
)


def _sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


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
        elif isinstance(node, ast.alias):
            found.add(node.asname or node.name)
    return found


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_the_scan_covers_the_interpretation_package() -> None:
    """A scan over nothing passes for the wrong reason."""
    assert INTERPRETATION.is_dir()
    assert len(_sources(INTERPRETATION)) >= 8


# --- no index ------------------------------------------------------------------


@pytest.mark.parametrize("name", INDEX_NAMES)
def test_no_module_declares_a_local_index(name: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {identifier}"
        for path in _sources(SRC)
        for identifier in _identifiers(path)
        if name in identifier.lower()
    ]
    assert not offenders, f"a local term index exists: {offenders}"


def test_no_module_imports_001s_index_builder() -> None:
    """``build_index`` is how `001` builds its own. Importing it would build a second.

    `001`'s ``CatalogApi.from_bundle`` builds the index it then filters through;
    this feature receives the API, never constructs the index.
    """
    offenders: list[str] = []
    for path in _sources(SRC):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "semantic_catalog.search.resolve"
            ):
                imported = {alias.name for alias in node.names}
                banned = imported & {"build_index", "SearchIndex", "normalise", "FUZZY_THRESHOLD"}
                if banned:
                    offenders.append(f"{path.relative_to(SRC).as_posix()}: {sorted(banned)}")
    assert not offenders, f"index or matching internals are imported: {offenders}"


def test_no_module_level_mutable_collection_holds_terms() -> None:
    """A dict or set at module scope is where a derived term table appears.

    Frozen mappings of *governed structure* — the match-kind map, the fill order
    — are fine and are checked for immutability elsewhere. What must not exist is
    a mutable container that could accumulate terms across requests.
    """
    offenders: list[str] = []
    for path in _sources(INTERPRETATION):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            value = node.value
            if not (
                isinstance(value, ast.List | ast.Set)
                or (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id in {"list", "set"}
                )
            ):
                continue
            targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            names = [ast.unparse(target) for target in targets]
            # `__all__` is a module-level list in every module and names exports,
            # not terms. Excluded by name rather than by shape, so a term table
            # that happened to be a list is still caught.
            if names == ["__all__"]:
                continue
            offenders.append(f"{path.relative_to(SRC).as_posix()}: " + ", ".join(names))
    assert not offenders, f"a mutable module-level collection exists: {offenders}"


def test_no_interpretation_module_is_memoised() -> None:
    """A cached resolution outlives the catalog release it was resolved against."""
    offenders: list[str] = []
    for path in _sources(INTERPRETATION):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
                "cache" in ast.unparse(decorator).lower() for decorator in node.decorator_list
            ):
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {node.name}")
    assert not offenders, f"an interpretation function is memoised: {offenders}"


# --- no matching of this feature's own -----------------------------------------


@pytest.mark.parametrize("name", MATCHING_NAMES)
def test_no_module_implements_its_own_matching(name: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {identifier}"
        for path in _sources(SRC)
        for identifier in _identifiers(path)
        if name in identifier.lower()
    ]
    assert not offenders, f"this feature implements matching of its own: {offenders}"


@pytest.mark.parametrize(
    "planted",
    [
        "def porter_stemmer(term): return term",
        "class SnowballStemmer: pass",
        "def stemming_pass(term): return term",
        "def porter_stem(term): return term",
    ],
)
def test_a_planted_stemmer_is_still_caught(planted: str, tmp_path: Path) -> None:
    """The narrowing that removed bare ``stem`` left no hole.

    ``stem`` was dropped because it matched ``SystemExit``. Dropping a token is
    only safe if the thing it was there to catch is still caught, so every
    plausible spelling of a real stemmer is planted here and must be found.
    """
    path = tmp_path / "planted.py"
    path.write_text(planted, encoding="utf-8")
    identifiers = {identifier.lower() for identifier in _identifiers(path)}
    assert any(name in identifier for name in MATCHING_NAMES for identifier in identifiers), (
        f"a planted stemmer went unnoticed: {planted}"
    )


def test_the_narrowed_tokens_do_not_fire_on_ordinary_names() -> None:
    """And the narrowing actually removed the false positive it was for."""
    benign = {"systemexit", "system", "stem", "filesystem", "path.stem"}
    assert not [name for name in MATCHING_NAMES for identifier in benign if name in identifier], (
        "a matching token still fires on an ordinary name"
    )


@pytest.mark.parametrize(
    "module", ["difflib", "rapidfuzz", "fuzzywuzzy", "Levenshtein", "jellyfish", "numpy", "re"]
)
def test_no_interpretation_module_imports_a_matching_library(module: str) -> None:
    """``re`` included: a regex over the question would be a matcher.

    `intake/parse.py` legitimately uses one for *structural* markup detection,
    which is why this is scoped to `interpretation/` rather than the package.
    """
    offenders = [
        f"{path.relative_to(SRC).as_posix()} imports {imported}"
        for path in _sources(INTERPRETATION)
        for imported in _imports(path)
        if imported == module or imported.startswith(module + ".")
    ]
    assert not offenders, f"a matching library is reachable from interpretation: {offenders}"


def test_the_only_discovery_path_is_001s_catalog_api() -> None:
    """One function reaches the catalog, and it takes an ``AuthorizedContext``."""
    source = inspect.getsource(resolve_terms)
    assert source.count("catalog.resolve(") == 1, "more than one discovery call site"

    signature = inspect.signature(resolve_terms.discover)
    assert "authorized" in signature.parameters
    assert signature.parameters["authorized"].kind is inspect.Parameter.KEYWORD_ONLY


def test_ordering_reuses_001s_sort_key() -> None:
    """A key of this feature's own could let a synonym outrank a canonical id.

    Scanned over the function **body**, not its whole source: the docstring
    explains `001`'s ordering and therefore names its components, and a
    whole-source scan would flag the explanation rather than an implementation.
    """
    source = inspect.getsource(resolve_terms.ordered_candidates)
    body = source.split('"""')[2]
    assert "sort_key" in body
    for invented in ("score", "len(", "lower()", "reverse="):
        assert invented not in body, f"a local ordering key was derived: {invented}"
