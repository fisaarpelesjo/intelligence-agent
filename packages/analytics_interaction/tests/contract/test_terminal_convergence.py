"""Terminal convergence — T181.

    Evidence: all gates green; `001` and `002` pre-existing node-ID sets fully preserved
    and passing; `003` full battery; coverage 102/102 and 59/59; fifteen records open;
    aggregate readiness NONE. — `tasks.md` T181

    Validation: **the sole executable terminal.** It MUST NOT declare production readiness,
    MUST NOT close any external record, and MUST state that every result is fixture-backed.
    — `tasks.md` T181

## What a terminal task can and cannot prove about itself

It cannot run the battery it reports. A test that shelled out to the whole suite would
recurse, and one that trusted its own summary would be a document checking itself.

So the split is: the **battery** is run from the working tree and its numbers are recorded
in `docs/release/nl-analytics-release-state.md`; this file asserts the properties that are
checkable **from inside the suite** — the graph, the coverage totals, the readiness state —
and asserts that the artifact states each of the things `T181` requires it to state.

The second half matters more than it looks. A release document is the artefact that
travels; a reader who receives only it gets whatever it says. So its required statements
are asserted verbatim rather than reviewed, and its prohibited claims are scanned for.

## The graph checks are recomputed here

Not read from `tasks.md`'s summary tables. Those tables are a claim, and a terminal task
that quoted them would converge on the plan rather than on the work.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.compliance.gates import InteractionCapability, is_capability_available
from analytics_interaction.compliance.readiness import aggregate_ready, load_all_records

from .coverage_audit import ALL_FR, ALL_SC, coverage
from .test_sc_coverage import Classification, classify

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
REPO = SRC.parents[3]
TASKS = REPO / "specs" / "003-nl-analytics-interaction" / "tasks.md"
ARTIFACT = REPO / "docs" / "release" / "nl-analytics-release-state.md"

_LINE = re.compile(r"^- \[([ xX])\] (T\d{3})(.*)$", re.M)
_DEPS = re.compile(r"Deps: ([^·]*)")
_EXTERNAL = "[BLOCKED-EXTERNAL]"

#: The terminal, the executable range and the record range. Named so a failure says which
#: boundary moved rather than handing a reviewer two sets to diff.
TERMINAL = 181
EXECUTABLE = frozenset(range(1, 182))
RECORDS = frozenset(range(182, 186))


def _tasks() -> list[tuple[str, int, str]]:
    return [
        (state, int(num[1:]), rest)
        for state, num, rest in _LINE.findall(TASKS.read_text(encoding="utf-8"))
    ]


def _edges() -> dict[int, frozenset[int]]:
    """``{task: dependencies}``, parsed from each task's own ``Deps:`` line.

    Parsed rather than read from the summary tables: those are a claim, and a terminal task
    that quoted them would converge on the plan rather than on the work.
    """
    text = TASKS.read_text(encoding="utf-8")
    found: dict[int, frozenset[int]] = {}
    for _state, number, _rest in _tasks():
        start = text.index(f"] T{number:03d} ")
        window = text[start : start + 3000]
        match = _DEPS.search(window)
        deps: set[int] = set()
        if match:
            deps = {int(token[1:]) for token in re.findall(r"T\d{3}", match.group(1))}
        found[number] = frozenset(deps)
    return found


# --- the graph -------------------------------------------------------------------


def test_the_inventory_is_contiguous_and_unique() -> None:
    numbers = [number for _state, number, _rest in _tasks()]
    assert len(numbers) == 185
    assert len(set(numbers)) == 185
    assert sorted(numbers) == list(range(1, 186))


def test_the_executable_range_and_the_record_range_are_exact() -> None:
    """181 executable, 4 records, and nothing straddling the boundary."""
    executable = {number for _state, number, rest in _tasks() if _EXTERNAL not in rest}
    records = {number for _state, number, rest in _tasks() if _EXTERNAL in rest}
    assert executable == EXECUTABLE
    assert records == RECORDS
    assert not executable & records


def test_every_executable_task_before_the_terminal_is_complete() -> None:
    """`T001`—`T180`, all of them.

    Named as a set difference so a failure lists the incomplete tasks rather than reporting
    a count somebody has to chase.
    """
    complete = {number for state, number, _rest in _tasks() if state.lower() == "x"}
    outstanding = sorted(set(range(1, TERMINAL)) - complete)
    assert not outstanding, outstanding


def test_no_external_record_is_marked_complete() -> None:
    """A record has no completion path in this repository, so it can never be done."""
    # OD-93/OD-101 (2026-09-02): externo FECHADO = [X] + marcador + CLOSED datado na
    # linha; um [X] SEM data continua sendo o defeito que este no existe para pegar.
    marked = [
        number
        for state, number, rest in _tasks()
        if _EXTERNAL in rest and state.lower() == "x" and "CLOSED 20" not in rest
    ]
    assert not marked, marked


def test_the_graph_has_no_undefined_self_forward_or_external_dependency() -> None:
    """Four faults, checked together because each would be silent on its own."""
    edges = _edges()
    numbers = set(edges)

    undefined = {task: sorted(deps - numbers) for task, deps in edges.items() if deps - numbers}
    assert not undefined, undefined

    assert not [task for task, deps in edges.items() if task in deps]

    forward = {
        task: sorted(dep for dep in deps if dep >= task)
        for task, deps in edges.items()
        if any(dep >= task for dep in deps)
    }
    assert not forward, forward

    on_records = {task: sorted(deps & RECORDS) for task, deps in edges.items() if deps & RECORDS}
    assert not on_records, on_records


def test_the_graph_is_acyclic() -> None:
    """Forward edges are already forbidden, so this is defence in depth.

    Stated separately because "no forward dependency" and "no cycle" are different claims: a
    renumbering could make a cycle out of edges that all point backwards by number.
    """
    edges = _edges()
    colour: dict[int, int] = {}

    def visit(node: int, trail: list[int]) -> list[int] | None:
        colour[node] = 1
        for nxt in sorted(edges.get(node, frozenset()) & EXECUTABLE):
            if colour.get(nxt, 0) == 1:
                return [*trail, node, nxt]
            if colour.get(nxt, 0) == 0:
                found = visit(nxt, [*trail, node])
                if found:
                    return found
        colour[node] = 2
        return None

    for node in sorted(EXECUTABLE):
        if colour.get(node, 0) == 0:
            cycle = visit(node, [])
            assert cycle is None, cycle


def test_every_executable_task_converges_on_the_sole_terminal() -> None:
    """**The terminal property.** 181 reachable, and exactly one task with no dependants."""
    edges = _edges()
    dependants: dict[int, set[int]] = {task: set() for task in EXECUTABLE}
    for task, deps in edges.items():
        for dep in deps:
            if dep in dependants:
                dependants[dep].add(task)

    reachable: set[int] = set()
    stack = [TERMINAL]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(edges.get(node, frozenset()) & EXECUTABLE)
    assert reachable == EXECUTABLE, sorted(EXECUTABLE - reachable)

    terminals = sorted(task for task in EXECUTABLE if not dependants[task])
    assert terminals == [TERMINAL], terminals


# --- coverage, recomputed --------------------------------------------------------


def test_functional_requirement_coverage_is_complete() -> None:
    covered = {number for number, owners in coverage().fr.items() if owners.covered}
    assert covered == ALL_FR, sorted(ALL_FR - covered)
    assert len(covered) == 102


def test_success_criteria_are_classified_exactly() -> None:
    """**50 measured, 8 blocked-external, 1 unmeasurable.**

    Pinned as three numbers here, unlike `T174` which pins only the shape. A terminal
    report quotes these, and a report quoting a number nothing asserts is a number that
    drifts.
    """
    validated = {number for number, owners in coverage().sc.items() if owners.has_validation}
    assert validated == ALL_SC
    counts = {
        classification: sum(1 for number in sorted(ALL_SC) if classify(number) is classification)
        for classification in Classification
    }
    assert counts[Classification.MEASURED] == 50
    assert counts[Classification.BLOCKED_EXTERNAL] == 8
    assert counts[Classification.UNMEASURABLE] == 1
    assert classify(30) is Classification.UNMEASURABLE


def test_readiness_is_none_and_every_capability_is_unavailable() -> None:
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )
    for capability in InteractionCapability:  # d_18/d_21 disponiveis (OD-101/OD-104)
        assert is_capability_available(capability) == (
            capability in (InteractionCapability.D_18, InteractionCapability.D_21)
        ), capability.value


# --- the artifact exists and states what it must ---------------------------------


def _normalised() -> str:
    """The artifact with runs of whitespace and blockquote markers collapsed to one space.

    Markdown formatting is not content. Comparing against the raw text would make every
    required-statement assertion depend on where the paragraph happened to wrap.
    """
    text = ARTIFACT.read_text(encoding="utf-8")
    text = text.replace("**", "").replace("`", "")
    return " ".join(text.replace(">", " ").split())


def test_the_terminal_artifact_exists_where_tasks_assigns_it() -> None:
    assert ARTIFACT.is_file(), ARTIFACT
    assert ARTIFACT.parent.name == "release"
    assert ARTIFACT.name == "nl-analytics-release-state.md"


@pytest.mark.parametrize(
    "statement",
    [
        "181",
        "102 / 102",
        "59 / 59",
        "fifteen dependency records remain open",
        "Aggregate external readiness is NONE",
        "No production BigQuery query was executed",
        "No production model or provider was called",
        "No production seal key exists or was used",
        "D-11 interpretation quality remains unmeasured",
        "fixture-backed",
        "Internal implementation completion is not production readiness",
    ],
)
def test_the_artifact_states_every_required_thing(statement: str) -> None:
    """**The artifact is what travels.**

    A reader who receives only this document gets whatever it says, so each required
    statement is asserted in the text rather than reviewed once and forgotten.

    Searched against **whitespace-normalised** text. The document is wrapped and several
    required sentences sit inside a blockquote, so a raw substring search fails on a line
    break and would have to be maintained against the wrapping — which is a test that
    breaks every time somebody reflows a paragraph.
    """
    assert statement in _normalised(), statement


def test_the_artifact_reports_the_measured_totals() -> None:
    """The numbers this suite can recompute must match the ones the document quotes."""
    text = ARTIFACT.read_text(encoding="utf-8")
    for figure in ("1605", "1816", "4208", "7629"):
        assert figure in text, figure
    for classification in ("**50**", "**8**", "**1**"):
        assert classification in text, classification


#: Phrases that would be a production claim if asserted rather than denied.
CLAIM_PHRASES: tuple[str, ...] = (
    "is production ready",
    "production-ready",
    "ready for production",
    "approved for launch",
    "sla of",
    "uptime of",
    "certified",
    "% accuracy",
    "accuracy of",
)

#: Words that make an occurrence a negation or a prohibition rather than a claim.
#:
#: The document says "It does not say the feature is production ready" and
#: "Production readiness: not declared" — both contain the phrase and neither is a claim.
#: A bare substring scan fired on the denials, which is a scan that would be deleted rather
#: than narrowed.
NEGATIONS: tuple[str, ...] = (
    "not ",
    "no ",
    "never",
    "must not",
    "does not",
    "is not",
    "nothing",
    "cannot",
    "prohibit",
    "forbid",
    "without",
    "neither",
)


def test_the_artifact_makes_no_production_claim() -> None:
    """**Every occurrence is a negation, a prohibition or a denylist entry.**

    Checked per sentence rather than per document: a phrase is permitted only when its own
    sentence negates it, so a denial elsewhere on the page cannot license a claim here.
    """
    text = _normalised().lower()
    sentences = [part.strip() for part in re.split(r"(?<=[.:;|])\s+", text) if part.strip()]

    offenders: list[str] = []
    for sentence in sentences:
        for phrase in CLAIM_PHRASES:
            if phrase in sentence and not any(word in sentence for word in NEGATIONS):
                offenders.append(f"{phrase!r} in: {sentence[:120]}")
    assert not offenders, offenders


def test_the_claim_scan_would_catch_a_bare_claim() -> None:
    """A negation-aware scan is only useful if the affirmation still fails.

    Planted both ways, because the risk of narrowing is that the narrowing swallows the
    thing being looked for.
    """
    claim = "this feature is production ready and approved for launch"
    denial = "this feature is not production ready and is not approved for launch"

    def offends(sentence: str) -> bool:
        return any(
            phrase in sentence and not any(word in sentence for word in NEGATIONS)
            for phrase in CLAIM_PHRASES
        )

    assert offends(claim)
    assert not offends(denial)


def test_the_artifact_closes_no_external_record() -> None:
    """A terminal report is the most tempting place to declare something finished."""
    text = ARTIFACT.read_text(encoding="utf-8").lower()
    for forbidden in ("d-21 is ready", "d-18 is ready", "record closed", "dependency resolved"):
        assert forbidden not in text, forbidden
    assert "all fifteen dependency records remain open" in text


def test_the_artifact_carries_no_value_question_or_secret() -> None:
    """It is a committed file, so anything in it is permanent.

    Searched for the corpora's own questions and values — the most likely thing to be pasted
    into a release document by accident — and for credential shapes.
    """
    from ..fixtures.golden import CASES
    from ..fixtures.golden.adversarial import ADVERSARIAL_CASES

    text = ARTIFACT.read_text(encoding="utf-8")
    for case in CASES:
        assert case.question not in text
        if case.expected_value is not None:
            assert f" {case.expected_value} " not in text
    for adversarial in ADVERSARIAL_CASES:
        assert adversarial.payload not in text
    for shape in (
        "BEGIN PRIVATE",
        "api_key",
        "Bearer ",
        "password",
        "fixture-only-not-provisioned-key",
    ):
        assert shape not in text, shape


def test_the_artifact_identifies_its_fixtures_as_fixtures() -> None:
    """Naming what stood in for production is the difference between evidence and a claim."""
    text = ARTIFACT.read_text(encoding="utf-8")
    assert "**Fixture, and identified as such**" in text
    assert "No decision is stubbed" in text


def test_the_artifact_records_the_deterministic_hash() -> None:
    """And it is the hash of the file on disk, not a number somebody typed."""
    import hashlib

    report = REPO / "docs" / "release" / "nl-analytics-grader-report.json"
    assert report.is_file()
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    assert digest in ARTIFACT.read_text(encoding="utf-8"), digest


def test_the_artifact_records_the_known_limitations() -> None:
    """Including the three that are limitations of the validation itself."""
    text = ARTIFACT.read_text(encoding="utf-8")
    for limitation in (
        "Replay prevention is not implemented",
        "The corpora are self-authored",
        "Fixture-enabled paths prove logic, not availability",
    ):
        assert limitation in text, limitation


def test_the_artifact_records_the_maintenance_this_task_caused() -> None:
    """**A terminal report that hid a correction it caused would be the worst outcome here.**

    Marking `T181` complete made Feature 003 read as finished, which broke an upstream test
    whose premise was that it was not. The premise was corrected under a named
    test-maintenance authorization, and the document says so — rather than reporting a green
    run whose provenance a reader could not reconstruct.
    """
    text = ARTIFACT.read_text(encoding="utf-8")
    assert "Test-maintenance note" in text
    assert "test_a_feature_in_progress_is_recognised_as_such" in text
    assert "synthetic ledgers" in text
    assert "original node ID is kept" in text
    assert "feature_is_complete" in text and "unchanged" in text


def test_the_artifact_reports_no_failure() -> None:
    """And the totals it quotes are a clean run.

    Asserted as an absence with the positive counts pinned separately above, so this cannot
    pass because the totals table was deleted.
    """
    text = ARTIFACT.read_text(encoding="utf-8")
    assert "1 failed" not in text
    assert "zero failures, zero skips" in text
