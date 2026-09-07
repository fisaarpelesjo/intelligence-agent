"""No artifact claims production readiness — T067 (FR-060, FR-061; SC-033).

    The system MUST NOT claim production readiness, and MUST NOT represent an
    unavailable integration, model surface or metric as available. — `FR-061`

    The system MUST NOT represent fixture-backed validation as evidence of
    production behaviour; every fixture-backed report MUST state that
    limitation. — `FR-060`

A content scan over everything this feature owns: its package, its
specification and planning artifacts, its governed content and its readiness
record.

**The rule is not "never write the phrase".** Artifacts must be able to say
*"this is not production-ready"* — that sentence is the whole point of `FR-061`,
and a scan that banned the words outright would delete the disclaimers along with
the claims. So every occurrence must sit in a **negating context**: a denial, a
prohibition, a statement of absence, or this file's own denylist.

That is a weaker check than banning the phrase and a much stronger one than
nothing, and it fails on the case that actually matters — a bare assertion that
something is ready.

Fixture-backed reporting is checked from the other direction: no artifact may
present a fixture as production evidence, and the phrase pairing that would do so
is scanned for directly.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import analytics_interaction

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
PACKAGE = Path(inspect.getfile(analytics_interaction)).resolve().parents[2]

#: Everything this feature owns. `001`'s and `002`'s artifacts are theirs to
#: govern and are deliberately out of scope — scanning them would make this
#: feature's suite fail for another feature's wording.
OWNED = (
    PACKAGE,
    REPO / "specs" / "003-nl-analytics-interaction",
    REPO / "interpretation_governance",
    REPO / "docs" / "readiness" / "nl-analytics-external-readiness.yaml",
)

SCANNED_SUFFIXES = frozenset({".py", ".md", ".yaml", ".yml", ".toml"})

#: Phrases that assert readiness. Matched case-insensitively on word boundaries.
READINESS_PHRASES = (
    r"production[- ]ready",
    r"production readiness",
    r"release[- ]ready",
    r"ready for production",
    r"generally available",
    r"\bGA\b",
    r"production[- ]certified",
    r"fit for production",
)

#: Words that make an occurrence a denial, a prohibition or a statement of
#: absence rather than a claim. Matched on **word boundaries**, not as
#: substrings: the artifacts write ``**not**`` and ``neither ... nor``, and a
#: substring test for ``"not "`` misses both while a bare ``"not"`` would match
#: inside "notably".
#:
#: Deliberately generous. The failure this test exists for is a *bare* claim, and
#: a sentence carrying any of these is not one.
NEGATIONS = (
    "not",
    "no",
    "neither",
    "nor",
    "never",
    "none",
    "nothing",
    "zero",
    "without",
    "cannot",
    "unavailable",
    "unproven",
    "refuse",
    "refuses",
    "denylist",
    "forbid",
    "forbids",
    "prohibit",
    "prohibits",
    "claim",
    "claims",
    "declare",
    "declared",
    "declares",
    "assert",
    "asserts",
    "establishes",
    "before",
    "until",
    "requires",
    "would",
    "nobody",
    "open",
)

_NEGATION = re.compile(r"\b(?:" + "|".join(NEGATIONS) + r")\b", re.IGNORECASE)

_PATTERN = re.compile("|".join(READINESS_PHRASES), re.IGNORECASE)

#: Files that **author a denylist** and are therefore exempt from it. Named explicitly
#: rather than skipped by heuristic.
#:
#: Two of them, and the second is why this is a set rather than a constant.
#: `test_terminal_convergence.py` scans the terminal release artifact for the same class of
#: claim, so it necessarily spells the phrases out. A scan that fired on another scan's
#: denylist would force the second one to obfuscate its own patterns, which is worse than
#: the exemption: an obfuscated denylist is one nobody can review.
#:
#: The exemption is by **path**, so it cannot spread. A third file wanting it has to be
#: added here and argued for.
_DENYLIST_AUTHORS = frozenset(
    {
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("test_terminal_convergence.py"),
    }
)

#: Kept as an alias so the existing self-referential assertions read unchanged.
_SELF = Path(__file__).resolve()


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for root in OWNED:
        if root.is_file():
            files.append(root)
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in SCANNED_SUFFIXES
            and "__pycache__" not in path.parts
            and ".pytest_cache" not in path.parts
        )
    return sorted(set(files))


FILES = _scanned_files()


def _claims(path: Path) -> list[tuple[int, str]]:
    """Occurrences of a readiness phrase in a non-negating line."""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not _PATTERN.search(line):
            continue
        if _NEGATION.search(line):
            continue
        found.append((number, line.strip()))
    return found


# --- the scan -----------------------------------------------------------------


def test_the_scan_covers_this_feature_s_artifacts() -> None:
    """A content scan over nothing passes for the wrong reason."""
    assert len(FILES) > 40, f"only {len(FILES)} files scanned"
    names = {path.name for path in FILES}
    assert "spec.md" in names
    assert "tasks.md" in names
    assert "nl-analytics-external-readiness.yaml" in names
    assert "pyproject.toml" in names


def test_no_artifact_claims_production_readiness() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{number} {line}"
        for path in FILES
        if path.resolve() not in _DENYLIST_AUTHORS
        for number, line in _claims(path)
    ]
    assert not offenders, "a readiness claim was found:\n" + "\n".join(offenders)


def test_the_scan_would_catch_a_bare_claim(tmp_path: Path) -> None:
    """A denylist never shown to fire proves nothing about the denylist."""
    target = tmp_path / "claim.md"
    target.write_text("This feature is production-ready.\n", encoding="utf-8")
    assert _claims(target) == [(1, "This feature is production-ready.")]


@pytest.mark.parametrize(
    "line",
    [
        "This feature is production-ready.",
        "Release-ready as of today.",
        "The model surface is generally available.",
        "Fit for production use.",
    ],
)
def test_each_phrase_form_is_caught(line: str, tmp_path: Path) -> None:
    target = tmp_path / "claim.md"
    target.write_text(line + "\n", encoding="utf-8")
    assert _claims(target), f"the scan missed: {line}"


@pytest.mark.parametrize(
    "line",
    [
        "**Not production-ready, and no production readiness is claimed.**",
        "This feature MUST NOT claim production readiness.",
        "Zero artifacts produced by this feature claim production readiness.",
        "Release-ready requires evidence per record.",
    ],
)
def test_a_negated_occurrence_is_permitted(line: str, tmp_path: Path) -> None:
    """Artifacts must be able to state the absence.

    A scan that banned the words outright would delete the disclaimers `FR-061`
    exists to require.
    """
    target = tmp_path / "denial.md"
    target.write_text(line + "\n", encoding="utf-8")
    assert _claims(target) == []


# --- fixtures are never production evidence -----------------------------------


def test_no_artifact_presents_a_fixture_as_production_evidence() -> None:
    """`FR-060`. The pairing is what makes the claim, so the pairing is scanned.

    The same negation rule applies. `spec.md` writes *"MUST NOT represent
    fixture-backed validation as evidence of production behaviour"*, which is the
    requirement itself — banning the sentence would ban the rule.
    """
    pattern = re.compile(
        r"fixture[^.\n]{0,80}(proves|evidence of|demonstrates)[^.\n]{0,40}production",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in FILES:
        if path.resolve() in _DENYLIST_AUTHORS:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line) and not _NEGATION.search(line):
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{number} {line.strip()}")
    assert not offenders, f"a fixture is presented as production evidence: {offenders}"


def test_the_fixture_evidence_scan_would_catch_a_bare_pairing(tmp_path: Path) -> None:
    target = tmp_path / "claim.md"
    target.write_text(
        "The fixture suite demonstrates production behaviour end to end.\n", encoding="utf-8"
    )
    line = target.read_text(encoding="utf-8").strip()
    pattern = re.compile(
        r"fixture[^.\n]{0,80}(proves|evidence of|demonstrates)[^.\n]{0,40}production",
        re.IGNORECASE,
    )
    assert pattern.search(line) and not _NEGATION.search(line)


def test_the_readiness_record_states_every_capability_undeclared() -> None:
    """The record is the artifact a reader consults; it must say so plainly."""
    import yaml

    record = REPO / "docs" / "readiness" / "nl-analytics-external-readiness.yaml"
    document = yaml.safe_load(record.read_text(encoding="utf-8"))
    for entry in document["capabilities"]:
        # OD-101/OD-104 (2026-09-02): d_21 e d_18 declarados COM evidencia e nota
        # datada; d_19 e d_20 continuam dizendo false/None com todas as letras.
        if entry["id"] in ("d_18", "d_21"):
            ordem = "OD-104" if entry["id"] == "d_18" else "OD-101"
            assert entry["declared"] is True
            assert entry["evidence_ref"], f"{entry['id']} declarado sem evidencia"
            assert ordem in str(entry.get("note", "")), "a nota nao cita a ordem"
            continue
        assert entry["declared"] is False, f"{entry['id']} is declared"
        assert entry["evidence_ref"] is None, f"{entry['id']} names evidence"


def test_the_package_readme_states_the_status_rather_than_implying_it() -> None:
    """A reader who opens only the README must not have to infer it."""
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8").lower()
    assert "not production-ready" in readme
    assert "no production readiness is claimed" in readme
    # OD-101/OD-104 (2026-09-02): o README diz a verdade nova — d_18 e d_21 prontos.
    assert "since **od-101** and **od-104** exactly" in readme
    assert "every other lock stays closed" in readme


def test_no_module_declares_a_readiness_constant_that_could_be_flipped() -> None:
    """A module-level ``READY = True`` would be a claim one edit away."""
    import ast

    source_root = PACKAGE / "src"
    offenders: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if "ready" in target.id.lower() and isinstance(node.value, ast.Constant):
                    offenders.append(f"{path.name}: {target.id} = {node.value.value!r}")
    assert not offenders, f"a flippable readiness constant exists: {offenders}"
