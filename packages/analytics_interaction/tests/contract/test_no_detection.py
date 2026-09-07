"""No language detection exists — T053 (FR-100; SC-058).

    The system MUST NOT detect, infer, guess or score the language of a
    question, because a probabilistic gate on answerability would make whether
    a question is answered at all depend on a non-deterministic input
    (`FR-041`). — `FR-100`

Two independent proofs, because either alone is escapable.

**By signature.** ``require_declared_language`` takes the declared value and
nothing else. There is no parameter through which the question text could reach
it, so a future edit that wanted the text to influence the decision would have to
change the signature first — a visible act rather than a quiet one.

**By scan.** No detector name, no scoring surface, and no declared dependency
that could provide one, anywhere in the package.

Scanned over **identifiers and imports**, never raw text. `intake/language.py`
explains at length why detection does not exist, and `contracts/intake.py`
documents ``detected_language`` and ``language_hint`` as deliberately absent
fields. A text scan would fail on both — turning an accurate explanation into a
build error and teaching the next author to delete the explanation instead of the
detector.
"""

from __future__ import annotations

import ast
import inspect
import tomllib
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.intake.language import (
    SUPPORTED_LANGUAGES,
    require_declared_language,
    supported_language_tags,
)

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
PYPROJECT = SRC.parents[1] / "pyproject.toml"

#: Names that would be a detector, a scorer or an inferred-language surface.
DETECTION_NAMES = (
    "detect_language",
    "language_detect",
    "detectlanguage",
    "langdetect",
    "langid",
    "guess_language",
    "infer_language",
    "identify_language",
    "language_score",
    "language_confidence",
    "language_probability",
    "detected_language",
    "language_hint",
    "predict_language",
)

#: Distributions that exist to detect language. Declaring one would put a
#: detector in the lockfile even if nothing called it yet.
DETECTION_DISTRIBUTIONS = (
    "langdetect",
    "langid",
    "pycld2",
    "pycld3",
    "cld3",
    "fasttext",
    "lingua",
    "lingua-language-detector",
    "textblob",
    "polyglot",
    "guess-language",
    "whatthelang",
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


# --- by scan ------------------------------------------------------------------


@pytest.mark.parametrize("name", DETECTION_NAMES)
def test_no_module_declares_a_detection_surface(name: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {identifier}"
        for path in _sources()
        for identifier in _identifiers(path)
        if name in identifier.lower()
    ]
    assert not offenders, f"a language-detection surface exists: {offenders}"


@pytest.mark.parametrize("distribution", DETECTION_DISTRIBUTIONS)
def test_no_detection_library_is_declared(distribution: str) -> None:
    """Runtime *and* dev. A detector reachable only from tests is still declared."""
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    declared = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)

    names = {
        requirement.split("==")[0].split(">=")[0].split("[")[0].strip().lower()
        for requirement in declared
    }
    assert distribution not in names


@pytest.mark.parametrize("distribution", DETECTION_DISTRIBUTIONS)
def test_no_detection_library_is_imported(distribution: str) -> None:
    root = distribution.replace("-", "_")
    offenders = [
        f"{path.relative_to(SRC).as_posix()} imports {imported}"
        for path in _sources()
        for imported in _imports(path)
        if imported == root or imported.startswith(root + ".")
    ]
    assert not offenders, f"a detection library is imported: {offenders}"


def test_the_scan_reads_identifiers_rather_than_prose() -> None:
    """The modules that *explain* the absence must be allowed to.

    Asserted in both directions so the distinction cannot quietly erode: the
    prose is present, the identifier is not, and a real declaration would be
    caught.
    """
    intake_contract = (SRC / "contracts" / "intake.py").read_text(encoding="utf-8")
    assert "detected_language" in intake_contract, "the deliberately-absent table is documented"
    assert not any(
        "detected_language" in name for name in _identifiers(SRC / "contracts/intake.py")
    )

    planted = ast.parse("def detect_language(text: str) -> str: ...\n")
    names = {node.name for node in ast.walk(planted) if isinstance(node, ast.FunctionDef)}
    assert any(banned in name.lower() for name in names for banned in DETECTION_NAMES)


# --- by signature -------------------------------------------------------------


def test_the_language_check_cannot_be_given_the_question_text() -> None:
    """The strongest form of the guarantee: there is no parameter for it."""
    signature = inspect.signature(require_declared_language)
    assert list(signature.parameters) == ["declared"]
    for forbidden in ("text", "question", "body", "content", "payload"):
        assert forbidden not in signature.parameters


def test_no_module_passes_question_text_to_the_language_check() -> None:
    """A single-parameter function can still be handed the wrong argument."""
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
            if called != "require_declared_language":
                continue
            rendered = ast.unparse(node)
            if any(token in rendered for token in ('"text"', "'text'", ".text")):
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {rendered}")
    assert not offenders, f"the question text reaches the language check: {offenders}"


# --- the decision is a lookup, not a judgement --------------------------------


def test_the_supported_set_comes_from_the_contract_enum() -> None:
    """Not a list restated here, which could drift from what a caller may declare."""
    assert frozenset(DeclaredLanguage) == SUPPORTED_LANGUAGES
    assert supported_language_tags() == ("pt-BR",)


def test_the_same_declaration_always_produces_the_same_answer() -> None:
    """No scoring means no run-to-run variation."""
    assert require_declared_language("pt-BR") is require_declared_language("pt-BR")
    assert require_declared_language("pt-BR") is DeclaredLanguage.PT_BR


def test_no_module_on_the_request_path_imports_a_random_source() -> None:
    """A probabilistic gate needs entropy from somewhere."""
    offenders = [
        f"{path.relative_to(SRC).as_posix()} imports {imported}"
        for path in _sources()
        for imported in _imports(path)
        if imported.split(".")[0] in {"random", "secrets", "numpy", "torch"}
    ]
    assert not offenders, f"a source of non-determinism is reachable: {offenders}"
