"""Interpretation quality is unmeasurable — T068 (FR-062; SC-030).

    The system MUST NOT claim interpretation or synonym-resolution quality while
    the pt-BR benchmark corpus (`D-11`, record `001:T107`) is absent, and MUST
    declare the corresponding criterion unmeasurable rather than substituting an
    invented threshold. — `FR-062`

`D-11` is the **primary measurement blocker** for this feature. `002` could
treat it as of bounded relevance because it accepted governed identifiers rather
than natural language; that reasoning does not carry here, where resolving pt-BR
phrasings *is* the feature (spec `C-3`).

The temptation this test exists to prevent is specific and reasonable-sounding:
run the resolver over the seed synonyms already in the catalog, count how many
resolve, and report the percentage. That number would be real, reproducible, and
**not a measurement of interpretation quality** — it would measure the resolver
against terms authored to make it pass. Publishing it would answer `SC-030` with
a figure nobody could act on, and the criterion would look satisfied.

So three separate assertions, because a proxy can enter three different ways:

* **no threshold** — no accuracy, precision, recall or score constant exists;
* **no figure** — no artifact reports one;
* **stated, not implied** — the artifacts say the criterion is unmeasurable, so a
  reader who checks does not have to infer it from an absence.

`D-11`'s state is read through the readiness reader rather than assumed, so the
day the corpus lands, this test's premise changes with the record instead of
silently outliving it.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.compliance.readiness import (
    CapabilityState,
    capability_state,
    load_all_records,
)

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
PACKAGE = Path(inspect.getfile(analytics_interaction)).resolve().parents[2]
SRC = PACKAGE / "src" / "analytics_interaction"
SPECS = REPO / "specs" / "003-nl-analytics-interaction"

RECORDS = load_all_records()

#: `D-11` lives in `001`'s record. Read, never restated.
D_11 = "d_11"

SCANNED = (
    PACKAGE,
    SPECS,
    REPO / "interpretation_governance",
)

_SELF = Path(__file__).resolve()


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _artifacts() -> list[Path]:
    files: list[Path] = []
    for root in SCANNED:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".md", ".yaml", ".yml", ".toml"}
            and "__pycache__" not in path.parts
            and ".pytest_cache" not in path.parts
            and path.resolve() != _SELF
        )
    return sorted(set(files))


ARTIFACTS = _artifacts()


# --- the premise --------------------------------------------------------------


def test_d_11_is_still_open() -> None:
    """The whole test rests on this. If `D-11` lands, the premise changes.

    Read from `001`'s readiness record rather than assumed, so this fails
    honestly on the day the corpus exists instead of asserting a stale world.
    """
    assert capability_state(D_11, records=RECORDS) is CapabilityState.UNDECLARED


def test_the_scan_covers_this_feature_s_artifacts() -> None:
    assert len(ARTIFACTS) > 40, f"only {len(ARTIFACTS)} artifacts scanned"
    assert any(path.name == "spec.md" for path in ARTIFACTS)


# --- no proxy threshold exists -------------------------------------------------


#: Names a proxy would arrive under. Quality-shaped, not merely numeric.
PROXY_NAMES = (
    "accuracy",
    "precision_at",
    "recall",
    "f1",
    "match_rate",
    "resolution_rate",
    "hit_rate",
    "quality_score",
    "confidence_threshold",
    "similarity_threshold",
    "fuzzy_threshold",
    "min_score",
    "score_floor",
    "benchmark_score",
)


@pytest.mark.parametrize("name", PROXY_NAMES)
def test_no_module_declares_a_proxy_quality_measure(name: str) -> None:
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            identifier = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.name
                if isinstance(node, ast.FunctionDef | ast.ClassDef)
                else node.arg
                if isinstance(node, ast.arg)
                else ""
            )
            if name in identifier.lower():
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {identifier}")
    assert not offenders, f"a proxy quality measure exists: {offenders}"


def test_no_module_declares_a_numeric_threshold_constant() -> None:
    """A bare float at module scope is how a tuned threshold arrives.

    `001` owns the one fuzzy threshold in the stack and states why it is fixed.
    This feature adds none — it calls `001`'s surface and scores nothing.
    """
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, float):
                targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
                names = ", ".join(ast.unparse(t) for t in targets)
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {names} = {value.value}")
    assert not offenders, f"a numeric threshold constant exists: {offenders}"


# --- no artifact claims a figure ----------------------------------------------


#: A percentage or ratio adjacent to a quality word. The pairing is the claim;
#: neither half alone is.
_QUALITY_FIGURE = re.compile(
    r"(accuracy|precision|recall|quality|resolution rate|match rate)[^.\n]{0,40}"
    r"\d+(\.\d+)?\s*%|"
    r"\d+(\.\d+)?\s*%[^.\n]{0,40}(accuracy|precision|recall|interpretation quality)",
    re.IGNORECASE,
)

#: Words that make an occurrence a denial or a statement of absence.
_NEGATION = re.compile(
    r"\b(?:not|no|never|none|nothing|zero|without|cannot|unmeasurable|absent|"
    r"claims?|must|declared?|refuses?|would|until|open)\b",
    re.IGNORECASE,
)


def test_no_artifact_claims_an_interpretation_quality_figure() -> None:
    offenders: list[str] = []
    for path in ARTIFACTS:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _QUALITY_FIGURE.search(line) and not _NEGATION.search(line):
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{number} {line.strip()}")
    assert not offenders, "an interpretation-quality figure was claimed:\n" + "\n".join(offenders)


def test_the_figure_scan_would_catch_a_report(tmp_path: Path) -> None:
    """A report containing an accuracy figure fails the assertion.

    `tasks.md` T068's evidence line, exercised directly — a denylist never shown
    to fire proves nothing about the denylist.
    """
    report = tmp_path / "report.md"
    report.write_text("Interpretation accuracy: 94.2% across the seed corpus.\n", encoding="utf-8")
    line = report.read_text(encoding="utf-8").strip()
    assert _QUALITY_FIGURE.search(line)
    assert not _NEGATION.search(line)


@pytest.mark.parametrize(
    "line",
    [
        "Resolution rate: 98%.",
        "Achieved 91.5% precision on pt-BR synonyms.",
        "interpretation quality is 87%",
    ],
)
def test_each_figure_form_is_caught(line: str) -> None:
    assert _QUALITY_FIGURE.search(line), f"the scan missed: {line}"


def test_a_statement_of_absence_is_permitted() -> None:
    """Artifacts must be able to say the criterion carries no figure."""
    permitted = "Zero reports claim an accuracy figure of 90% or any other."
    assert _NEGATION.search(permitted)


# --- the criterion is stated unmeasurable, not merely unmentioned --------------


def test_the_specification_declares_the_criterion_unmeasurable() -> None:
    """`SC-030` says it in the artifact a reader consults."""
    spec = (SPECS / "spec.md").read_text(encoding="utf-8")
    assert "SC-030" in spec
    assert "unmeasurable" in spec.lower()
    assert "D-11" in spec


def test_the_readiness_record_names_d_11_as_the_measurement_blocker() -> None:
    ledger = (SPECS / "tasks.md").read_text(encoding="utf-8")
    assert "001:T107" in ledger
    assert "D-11" in ledger
    assert "unmeasurable" in ledger.lower()


def test_no_fixture_is_presented_as_benchmark_evidence() -> None:
    """Synthetic fixtures exercise resolution; they are not `D-11`.

    A fixture corpus scored against itself would be exactly the proxy this test
    exists to prevent, and calling it a benchmark would make it look like
    evidence.
    """
    pattern = re.compile(
        r"fixture[^.\n]{0,60}benchmark|benchmark[^.\n]{0,60}fixture", re.IGNORECASE
    )
    offenders = [
        f"{path.relative_to(REPO).as_posix()}: {match.group(0)}"
        for path in ARTIFACTS
        for match in pattern.finditer(path.read_text(encoding="utf-8"))
        if not _NEGATION.search(match.group(0))
    ]
    assert not offenders, f"a fixture is presented as benchmark evidence: {offenders}"


def test_the_benchmark_corpus_directory_does_not_exist_in_this_repository() -> None:
    """`D-11`'s evidence is a corpus at `semantic/examples/benchmark/`.

    Its absence is the state; a directory appearing here without the record
    being declared would be evidence nobody governed.
    """
    corpus = REPO / "semantic" / "examples" / "benchmark"
    assert not corpus.exists(), "a benchmark corpus exists while D-11 is undeclared"
