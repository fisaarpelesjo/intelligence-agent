"""Fixtures stay in the tests — T148 (FR-063; SC-034).

    Evidence: no `src/` module references a fixture; no flag, env var or mode
    selects one. — `tasks.md` T148

Every fixture in this package exercises a path production refuses. The synthetic
`D-18` formulas make the arithmetic runnable; the synthetic `D-19` policy makes
the round bound applicable; the synthetic `D-21` key makes sealing possible; the
fake execution port makes submission countable. Each stands in for an **open**
external record.

That is exactly why containment matters. A fixture that leaked into `src/` would
not look like a governance failure — it would look like the feature working, and
the suite would go green for the wrong reason. The failure mode is a *success*
that nobody questions.

## Three separate claims

* **no reference** — no `src/` module imports a fixture module or names a
  fixture marker;
* **no selector** — no flag, environment variable, mode or constructor default
  can choose one. The injection parameters exist (`instances`, `records`,
  `port`), and **no production path supplies an argument to them**;
* **no mutation** — no fixture writes to `interpretation_governance/` or
  `docs/readiness/`. A fixture that edited governed content would make the
  refusal it was written to work around disappear for everybody.

## Why markers rather than paths

A path-based scan catches ``from tests.fixtures import ...`` and misses a value
copied out of one. The markers are carried in the *text* of every synthetic
value — the key, the version strings, the formula unit rules — so a copied value
brings its own evidence with it.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

import analytics_interaction

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
TESTS = Path(__file__).resolve().parents[1]
#: The repository root: ``packages/analytics_interaction/src/analytics_interaction``
#: is four levels down, and an off-by-one here would silently scan a directory
#: that does not exist and pass.
REPO = SRC.parents[3]


#: Every fixture marker in the package. Collected from the modules that declare
#: them rather than restated, so a new fixture family joining without a marker
#: fails the completeness check below rather than being silently uncovered.
def _markers() -> dict[str, str]:
    from ..fixtures import answers, clarifications, comparisons
    from ..fixtures import execution as execution_fixtures
    from ..fixtures import governance as governance_fixtures
    from ..fixtures import seal as seal_fixtures

    return {
        "answers": answers.FIXTURE_MARKER,
        "clarifications": clarifications.FIXTURE_MARKER,
        "comparisons": comparisons.FIXTURE_MARKER,
        "execution": execution_fixtures.FIXTURE_MARKER,
        "governance": governance_fixtures.FIXTURE_MARKER,
        "seal": seal_fixtures.FIXTURE_MARKER,
    }


#: Names a `src/` module would use to select a fixture. Each is a way "test mode"
#: arrives — and a feature with a test mode has two behaviours, only one of which
#: is reviewed.
SELECTOR_NAMES = frozenset(
    {
        "fixture",
        "fixtures",
        "test_mode",
        "testing",
        "use_fixture",
        "fake",
        "stub",
        "mock",
        "sandbox",
        "dry_run",
        "offline",
    }
)

#: Injection parameters that legitimately exist on production functions. They are
#: how a **test** reaches a fixture; the rule is that no production call site
#: passes one.
INJECTION_PARAMETERS = frozenset({"instances", "records", "port", "sink", "resolver"})


def _source_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _fixture_files() -> list[Path]:
    return sorted(p for p in (TESTS / "fixtures").rglob("*.py") if "__pycache__" not in p.parts)


# --- no `src/` module references a fixture -----------------------------------------


def test_every_fixture_family_declares_a_marker() -> None:
    """Otherwise the scans below cover fewer families than exist.

    Six families today. A seventh arriving without a marker fails here rather
    than being quietly uncovered by every scan in the file.
    """
    markers = _markers()
    assert len(markers) == 6
    for family, marker in markers.items():
        assert marker.startswith("fixture-only"), f"{family} has no fixture marker"


@pytest.mark.parametrize("family", sorted(_markers()))
def test_no_source_module_carries_a_fixture_marker(family: str) -> None:
    """**The load-bearing scan.**

    Catches a value copied out of a fixture as well as an import of one — the
    marker travels in the text, so a pasted formula, key or version string brings
    its own evidence.
    """
    marker = _markers()[family]
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in _source_files()
        if marker in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"the {family} fixture marker reached src/: {offenders}"


def test_no_source_module_imports_the_test_tree() -> None:
    """A direct import is the obvious form, and still worth asserting."""
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "tests" in node.module.split(".")
            ):
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
            elif isinstance(node, ast.Import):
                offenders += [
                    f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
                    for alias in node.names
                    if "tests" in alias.name.split(".")
                ]
    assert not offenders, f"a source module imports the test tree: {offenders}"


def test_no_source_module_reaches_a_fixture_directory() -> None:
    """By path as well as by import. A literal path is an import with extra steps."""
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in _source_files()
        if "tests/fixtures" in path.read_text(encoding="utf-8").replace("\\\\", "/")
    ]
    assert not offenders, f"a source module names a fixture path: {offenders}"


# --- no flag, env var or mode selects one --------------------------------------------


@pytest.mark.parametrize("name", sorted(SELECTOR_NAMES))
def test_no_source_module_declares_a_fixture_selector(name: str) -> None:
    """A feature with a test mode has two behaviours, one of them unreviewed."""
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.arg | ast.Name | ast.Attribute):
                continue
            declared = (
                node.arg
                if isinstance(node, ast.arg)
                else node.id
                if isinstance(node, ast.Name)
                else node.attr
            )
            if declared == name:
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
    assert not offenders, f"a fixture selector named {name!r} exists: {offenders}"


def test_no_source_module_reads_the_environment() -> None:
    """The commonest selector of all, and the one that needs no code change."""
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders += [
            f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute | ast.Name)
            and (node.attr if isinstance(node, ast.Attribute) else node.id)
            in {"environ", "getenv", "environb"}
        ]
    assert not offenders, f"the environment is read: {offenders}"


def test_the_injection_parameters_are_never_supplied_by_a_source_call_site() -> None:
    """**The subtle half.**

    ``instances``, ``records``, ``port``, ``sink`` and ``resolver`` exist so a
    *test* can inject. The rule is that no production call site passes one — a
    default would be this package choosing a governed environment, and an
    argument would be it choosing a specific fixture.

    Forwarding is permitted and is what the exclusion below allows: a function
    that received ``records`` and passes it on is threading its caller's choice,
    not making one.
    """
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg not in INJECTION_PARAMETERS:
                    continue
                # Forwarding a parameter of the enclosing function, or ``None``,
                # is threading a caller's choice rather than making one.
                if isinstance(keyword.value, ast.Name | ast.Attribute) or (
                    isinstance(keyword.value, ast.Constant) and keyword.value.value is None
                ):
                    continue
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno} {keyword.arg}")
    assert not offenders, f"a source call site supplies an injected collaborator: {offenders}"


def test_no_injection_parameter_has_a_non_none_default() -> None:
    """A default collaborator is one this package chose.

    ``None`` is the only permitted default, and it means "refuse" everywhere it
    appears — never "use the built-in one".
    """
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            arguments = node.args
            named = [*arguments.args, *arguments.kwonlyargs]
            defaults = [*arguments.defaults, *arguments.kw_defaults]
            for argument, default in zip(named[-len(defaults) :], defaults, strict=False):
                if argument.arg not in INJECTION_PARAMETERS or default is None:
                    continue
                if isinstance(default, ast.Constant) and default.value is None:
                    continue
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno} {argument.arg}")
    assert not offenders, f"an injected collaborator has a default: {offenders}"


# --- no fixture mutates governed content or readiness ------------------------------------


def test_no_fixture_writes_anywhere() -> None:
    """A fixture that edited governed content would make the refusal disappear.

    Not for that suite — for **everybody**, including the tests asserting the
    shipped state refuses, which would then pass by having changed the shipped
    state.
    """
    offenders: list[str] = []
    for path in _fixture_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if name in {"open", "write_text", "write_bytes", "mkdir", "unlink", "rmtree"}:
                offenders.append(f"{path.relative_to(TESTS).as_posix()}:{node.lineno} {name}")
    assert not offenders, f"a fixture writes: {offenders}"


@pytest.mark.parametrize("guarded", ["interpretation_governance", "docs/readiness"])
def test_no_fixture_names_a_governed_directory_for_writing(guarded: str) -> None:
    """Reading the shipped state is how the refusal tests work; writing it is not."""
    offenders: list[str] = []
    for path in _fixture_files():
        text = path.read_text(encoding="utf-8").replace("\\\\", "/")
        if guarded in text and any(
            write in text for write in ("write_text", "write_bytes", "open(")
        ):
            offenders.append(path.relative_to(TESTS).as_posix())
    assert not offenders, f"a fixture may write to {guarded}: {offenders}"


def test_the_shipped_governed_content_is_still_empty() -> None:
    """The state every fixture exists to work around, asserted directly.

    If a fixture ever did leak into the governed files, this is where it would
    show — and it would show as content appearing, which is the shape the leak
    takes.

    **`comparison-formulas.yaml` stopped being empty on 2026-08-26**, by the owner's
    decision — *"Autorizar as duas (Recomendado)"*, recorded in the governed channel
    at 17:17:40Z. So emptiness can no longer be the test for that one file, and the
    property has to be stated as what it always was: **content appears here only by an
    authored governed act, never by a fixture leaking in.**

    An authored instance and a leaked one differ in something checkable: an authored
    one carries an `approval` naming a role and a date. A fixture has no reason to,
    and the fixture-marker direction is covered by the sibling node below, which scans
    every file in this directory for the markers.

    The other three files are asserted empty exactly as before. **Only the file the
    decision named moved**, and a fourth file appearing here fails.
    """
    root = REPO / "interpretation_governance"
    # OD-104 (2026-09-02): dois outros arquivos do D-18 foram AUTORADOS pelo dono —
    # a emptiness deixa de ser o teste para eles tambem, e a propriedade e a mesma de
    # 26/08: conteudo aparece aqui SO por ato governado com approval nomeada e datada.
    for name in ("interpretation-policy.yaml",):
        assert _mapping(root / name).get("instances") == [], f"{name} declares an approved instance"

    for name in (
        "comparison-formulas.yaml",
        "period-vocabulary.yaml",
        "claim-classes.yaml",
    ):
        document = _mapping(root / name)
        instances = _entries(document, "instances")
        assert len(instances) == 1, (
            f"{name} holds one authored instance; a different count is a "
            "governed decision to be re-derived here rather than absorbed"
        )
        approval = instances[0].get("approval")
        assert isinstance(approval, dict), f"{name}: the authored instance carries no approval"
        declared = cast("dict[str, object]", approval)
        for field in ("approver_role", "evidence_ref", "approved_on"):
            assert declared.get(field), f"{name}: the approval declares no {field}"


def _mapping(path: Path) -> dict[str, object]:
    """Read a governed YAML document as a mapping, with the shape declared where it is read.

    **This replaced four `# pyright: ignore` comments, none of which carried a reason.**
    `yaml.safe_load` answers `Any`, so every value taken out of the document is untyped and
    strict mode reports it at each USE. Silencing it at each use is the shape that hides the
    next unknown too; declaring it once, at the boundary the file enters, is the rule this
    repository already applies to a figure.

    A document that is not a mapping answers the EMPTY mapping rather than raising, which is
    what the callers below already relied on: an empty governed file declares no instance,
    and that is exactly what they assert.
    """
    import yaml

    loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast("dict[str, object]", loaded) if isinstance(loaded, dict) else {}


def _entries(document: Mapping[str, object], key: str) -> tuple[dict[str, object], ...]:
    """The mappings listed under `key`, empty when the key is absent or holds no list."""
    listed = document.get(key)
    if not isinstance(listed, list):
        return ()
    return tuple(
        cast("dict[str, object]", entry)
        for entry in cast("list[object]", listed)
        if isinstance(entry, dict)
    )


def test_no_governed_or_readiness_file_carries_a_fixture_marker() -> None:
    """The other direction: a fixture value written into governance."""
    markers = set(_markers().values())
    for directory in ("interpretation_governance", "docs/readiness"):
        root = REPO / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in markers:
                assert marker not in text, f"{path.name} carries the fixture marker {marker!r}"


# --- the scans fire ------------------------------------------------------------------


def test_the_marker_scan_would_catch_a_copied_value() -> None:
    """A pasted fixture value brings its own evidence.

    Demonstrated rather than asserted in prose: the marker is a substring of the
    value, so copying the value copies the marker.
    """
    from ..fixtures.seal import FIXTURE_KEY, FIXTURE_MARKER

    pasted = f'SEAL_KEY = "{FIXTURE_KEY}"'
    assert FIXTURE_MARKER in pasted


def test_the_selector_scan_would_catch_a_planted_flag() -> None:
    """A ``use_fixture`` parameter is how a test mode arrives."""
    planted = ast.parse("def resolve(*, use_fixture: bool = False):\n    return use_fixture\n")
    names = {node.arg for node in ast.walk(planted) if isinstance(node, ast.arg)} | {
        node.id for node in ast.walk(planted) if isinstance(node, ast.Name)
    }
    assert names & SELECTOR_NAMES


def test_the_default_scan_would_catch_a_planted_default() -> None:
    """A defaulted collaborator is a governed environment this package chose."""
    planted = ast.parse("def resolve(*, instances=FIXTURE_SET):\n    return instances\n")
    function = next(node for node in ast.walk(planted) if isinstance(node, ast.FunctionDef))
    default = function.args.kw_defaults[0]
    assert default is not None
    assert not (isinstance(default, ast.Constant) and default.value is None)
