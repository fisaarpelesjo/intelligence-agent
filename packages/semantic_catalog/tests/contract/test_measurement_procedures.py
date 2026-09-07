"""Measurement procedures — T104, T105, T106 (`[PROCEDURE-ONLY]`).

The `[PROCEDURE-ONLY]` contract is the whole point of these tasks: the procedure
is defined, the owner and expected evidence are named, and **the criterion is
not measured**. The failure mode is a procedure document quietly reading as
evidence — a table of thresholds and a green heading, cited six months later as
though somebody had run it.

So these tests check two different things. That each procedure is **complete
enough to execute**: owner, inputs, sample, method, calculation, threshold,
cadence, output artifact, retention, interpretation. And that each one **claims
nothing**: no results, no participant quotes, no rates, no fabricated evidence.

The second half is the one that matters. A procedure missing a section is
obvious on reading; a procedure that has quietly acquired a result is not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
MEASUREMENT = REPO / "docs" / "measurement"
TASKS = REPO / "specs" / "001-semantic-catalog" / "tasks.md"

PROCEDURES = {
    "SC-012": ("sc-012-answerability-comprehension.md", "product_analytics", 104),
    "SC-015": ("sc-015-dispute-tracking.md", "data_governance", 105),
    "SC-028": ("sc-028-pending-comprehension.md", "product_analytics", 106),
}

#: Every section a procedure must carry to be executable by somebody who did not
#: write it.
REQUIRED_SECTIONS = (
    "criterion, verbatim",
    "owner role",
    "required inputs",
    "calculation",
    "threshold",
    "cadence and trigger",
    "output artifact",
    "evidence retention",
    "pass/fail interpretation",
    "what this procedure does not establish",
)


def _text(name: str) -> str:
    return (MEASUREMENT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(("criterion", "spec"), sorted(PROCEDURES.items()))
def test_the_procedure_exists_where_the_task_says(
    criterion: str, spec: tuple[str, str, int]
) -> None:
    name, _, task = spec
    assert (MEASUREMENT / name).is_file(), name
    assert f"docs/measurement/{name}" in TASKS.read_text(encoding="utf-8"), (
        f"T{task} names a path this file does not occupy"
    )
    assert criterion in _text(name)


@pytest.mark.parametrize(("criterion", "spec"), sorted(PROCEDURES.items()))
def test_every_required_section_is_present(criterion: str, spec: tuple[str, str, int]) -> None:
    name, _, _ = spec
    lowered = _text(name).lower()
    missing = [section for section in REQUIRED_SECTIONS if section not in lowered]
    assert not missing, f"{criterion}: {missing}"


@pytest.mark.parametrize(("criterion", "spec"), sorted(PROCEDURES.items()))
def test_the_owner_role_is_named_and_resolves(criterion: str, spec: tuple[str, str, int]) -> None:
    """A procedure owned by nobody is a procedure nobody runs."""
    name, owner, _ = spec
    assert owner in _text(name), f"{criterion}: {owner} not named"
    owners = (REPO / "semantic" / "owners.yaml").read_text(encoding="utf-8")
    assert f"id: {owner}" in owners, f"{owner} is not in the owner registry"


@pytest.mark.parametrize(("criterion", "spec"), sorted(PROCEDURES.items()))
def test_the_procedure_states_it_is_unmeasured(criterion: str, spec: tuple[str, str, int]) -> None:
    """The `[PROCEDURE-ONLY]` contract, stated where somebody will read it."""
    name, _, _ = spec
    text = _text(name)
    # Normalised: these sentences are line-wrapped inside a blockquote, so a
    # literal substring check would pass or fail on where the wrap landed, and
    # the `>` marker would survive into the middle of a sentence.
    flat = " ".join(" ".join(line.lstrip("> ").split()) for line in text.splitlines())
    assert "PROCEDURE ONLY" in flat, criterion
    assert f"{criterion} is UNMEASURED" in flat or f"{criterion} remains unmeasured" in flat
    assert "do not fabricate results" in flat.lower()
    # The warning must be at the top, where it is read before the thresholds.
    assert flat.index("PROCEDURE ONLY") < 400, "the warning is buried below the fold"


@pytest.mark.parametrize(("criterion", "spec"), sorted(PROCEDURES.items()))
def test_the_procedure_reports_no_result(criterion: str, spec: tuple[str, str, int]) -> None:
    """No procedure may quietly acquire a measurement.

    A rate, a participant count in the past tense, or a verdict would turn a
    plan into a claim. The document defines how to produce those; it holds none.
    """
    name, _, _ = spec
    text = _text(name)

    # Only unambiguous past-tense reports of a run that happened. Phrases like
    # "the criterion is met" appear in these documents exclusively inside their
    # own denial — "may not be cited as evidence that the criterion is met" —
    # and forbidding them would fail the warning that exists to prevent the
    # claim.
    forbidden = (
        "sessions were run",
        "participants reported",
        "we measured",
        "the result was",
        "was measured on",
        "passed with",
        "achieved a rate",
        "observed rate of",
    )
    hits = [phrase for phrase in forbidden if phrase in text.lower()]
    assert not hits, f"{criterion} reports a result: {hits}"

    # A concrete outcome would read as evidence. Rather than allowlisting every
    # legitimate use of "%" — thresholds, worked examples, counterfactual prose —
    # match the shape a *reported* figure takes. An allowlist grows every time
    # somebody rephrases a sentence; this does not.
    flat = " ".join(" ".join(line.lstrip("> ").split()) for line in text.splitlines())
    reported = re.compile(
        r"(?:was|were|is|are|reached|scored|achieved|observed|came out at)\s+\d{1,3}\s?%"
        r"|\d{1,3}\s?%\s+of\s+participants\s+(?:did|were|could|correctly|failed)"
        r"|rate\s+(?:was|of)\s+\d",
        re.IGNORECASE,
    )
    found = reported.findall(flat)
    assert not found, f"{criterion} reports a measured figure: {found}"


@pytest.mark.parametrize(("criterion", "spec"), sorted(PROCEDURES.items()))
def test_no_results_directory_has_been_populated(
    criterion: str, spec: tuple[str, str, int]
) -> None:
    """The procedures name `docs/measurement/results/`. Nothing may be in it.

    A results file committed alongside the procedure that describes it would be
    fabricated evidence by construction: no sessions have been run.
    """
    _ = criterion, spec
    results = MEASUREMENT / "results"
    assert not results.exists() or not list(results.glob("*.md")), (
        "a results file exists; no measurement has been performed"
    )


@pytest.mark.parametrize(("criterion", "spec"), sorted(PROCEDURES.items()))
def test_the_procedure_reuses_existing_interfaces(
    criterion: str, spec: tuple[str, str, int]
) -> None:
    """Measurement reads the catalog through the interfaces the catalog exposes.

    A procedure that described its own way to compute a governed answer would
    eventually disagree with the catalog, invisibly.
    """
    name, _, _ = spec
    text = _text(name)
    if criterion in {"SC-012", "SC-028"}:
        assert "catalog explain" in text
        assert "catalog check" in text
    if criterion == "SC-015":
        assert "catalog release status" in text
    assert "bigquery" not in text.lower(), "no procedure reads the warehouse directly"


def test_the_index_lists_every_procedure_as_unmeasured() -> None:
    index = _text("README.md")
    for criterion, (name, owner, _) in sorted(PROCEDURES.items()):
        assert name in index, criterion
        assert criterion in index
        assert owner in index
    # One row per procedure, each marked unmeasured.
    assert index.count("**No — unmeasured**") == len(PROCEDURES)


def test_the_index_names_the_blocked_external_dependencies() -> None:
    """Criteria blocked on D-8, D-11, D-12 or D-13 must not look procedural."""
    index = _text("README.md")
    for dependency, task in (("D-11", "T107"), ("D-8", "T108"), ("D-12", "T109"), ("D-13", "T110")):
        assert dependency in index, dependency
        assert task in index, task
    assert "SC-002" in index and "not ready" in index


def test_no_procedure_claims_external_readiness() -> None:
    """Nothing here may present EXT-A, EXT-B, D-8 or D-11 as delivered."""
    claims = re.compile(
        r"(?i)(ext-a|ext-b|d-8|d-11|d-12|d-13)\s+(is\s+)?(ready|delivered|available)"
    )
    for name, _, _ in PROCEDURES.values():
        assert not claims.search(_text(name)), name
    assert not claims.search(_text("README.md"))


def test_the_tasks_declare_these_as_procedure_only() -> None:
    """If the task list ever drops the marker, these tests are checking the
    wrong contract."""
    text = TASKS.read_text(encoding="utf-8")
    for criterion, (_, _, task) in sorted(PROCEDURES.items()):
        block = next(line for line in text.splitlines() if f"T{task:03d} " in line)
        assert "[PROCEDURE-ONLY]" in block, f"T{task:03d}"
        assert criterion.replace("SC-", "SC-") in text
    assert "DO NOT FABRICATE RESULTS" in text
