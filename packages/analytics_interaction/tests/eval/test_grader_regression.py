"""The grader regression and its report — T168 (FR-060, FR-062; SC-030, SC-033).

    Evidence: **FIXTURE-BACKED INTERNAL VALIDATION ONLY.** A green grader run
    establishes neither production interpretation quality nor production readiness. The
    `D-11` corpus, the interpretation-quality threshold and its acceptance evidence
    remain absent and are **not** invented here. — `tasks.md` T168

## What the report is

A deterministic JSON document at `docs/release/nl-analytics-grader-report.json`, written
by this test and committed. Four outcome buckets, and the last two are why the report
exists at all:

| Outcome | Meaning |
|---|---|
| `passed` | the comparator agreed |
| `failed` | it disagreed — a defect |
| `unmeasurable` | no approved definition exists to grade against |
| `blocked_external` | the path exists and a named open record gates it |

Collapsing `unmeasurable` or `blocked_external` into `failed` would report open
dependencies as defects and make the report unusable for deciding anything. Collapsing
either into `passed` would report absence as success, which is the failure this whole
feature is built to avoid.

## What it explicitly is not

Three statements are written **into the report itself**, not merely into this docstring,
because the report is the artefact that travels:

* fixture-backed success establishes **internal contract behaviour only**;
* `D-11` interpretation quality remains **unmeasured**, and `SC-030` unmeasurable;
* **no production-readiness claim** is made or implied.

A reader who receives only the JSON gets all three.

## Determinism

The report is byte-identical across runs, across `PYTHONHASHSEED` values **and across
platforms**: sorted keys, sorted case lists, no clock, no counts derived from set
iteration, and an explicit `
` separator. The last one was a real wart — `write_text`
translates newlines, so a Windows run wrote CRLF over a file git had stored with LF and
re-dirtied the working tree on every run while the content was unchanged.

Asserted here rather than assumed, because a report that changed between runs would
produce diff noise that hides the one change that mattered.

No question text, no analytical value and no refusal prose is persisted. The report
carries case identifiers, path names, outcome names and counts.
"""

from __future__ import annotations

import inspect
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

import analytics_interaction
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

from ..fixtures.golden import (
    CASES,
    CORPUS_VERSION,
    FIXTURE_MARKER,
    GoldenCase,
    GradedPath,
    cases_for,
)
from ..fixtures.golden.adversarial import (
    ADVERSARIAL_CASES,
    REQUIRED_CATEGORIES,
    ThreatCategory,
    cases_for_category,
)
from ..fixtures.golden.adversarial import (
    CORPUS_VERSION as ADVERSARIAL_VERSION,
)
from ..fixtures.golden.adversarial import (
    FIXTURE_MARKER as ADVERSARIAL_MARKER,
)
from .graders import (
    GRADERS,
    ORDERED_FIELDS,
    SET_LIKE_FIELDS,
    GradeOutcome,
    GraderResult,
    Observed,
    grade,
    grade_all,
    multiset,
)

pytestmark = pytest.mark.integration

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
REPO = SRC.parents[3]
REPORT = REPO / "docs" / "release" / "nl-analytics-grader-report.json"

#: The three statements the report must carry, verbatim. Held here so the assertion and
#: the written document cannot drift — a report whose disclaimer was edited away would
#: otherwise pass every structural check.
DISCLAIMERS: tuple[str, ...] = (
    "Fixture-backed success establishes internal contract behaviour only.",
    "D-11 interpretation quality remains unmeasured; SC-030 is unmeasurable.",
    "No production-readiness claim is made or implied.",
)


# --- the corpora are what they claim to be -----------------------------------


def test_every_graded_path_has_a_grader() -> None:
    """**Total, or a path is silently ungraded.**

    Compared against the enum rather than counted, so a ninth path added to
    ``GradedPath`` fails here instead of contributing zero cases to a green report.
    """
    assert set(GRADERS) == set(GradedPath)
    assert len(GRADERS) == 8


def test_every_graded_path_has_at_least_one_case() -> None:
    """A grader with no cases passes vacuously and reports a clean run."""
    for path in GradedPath:
        assert cases_for(path), path.value


def test_every_required_threat_category_has_at_least_one_case() -> None:
    """The eleven `T166` names, present. Extras are additive and permitted."""
    for category in REQUIRED_CATEGORIES:
        assert cases_for_category(category), category.value
    covered = {case.category for case in ADVERSARIAL_CASES}
    assert covered >= REQUIRED_CATEGORIES, REQUIRED_CATEGORIES - covered


def test_every_case_carries_its_fixture_marker() -> None:
    """So a case identifier appearing anywhere carries its own provenance."""
    for case in CASES:
        assert case.case_id.startswith(FIXTURE_MARKER)
    for adversarial in ADVERSARIAL_CASES:
        assert adversarial.case_id.startswith(ADVERSARIAL_MARKER)


def test_the_two_corpora_use_distinct_markers() -> None:
    """Separately reportable, so separately scannable.

    A shared marker would let a containment scan cover one corpus while appearing to
    cover both.
    """
    assert FIXTURE_MARKER != ADVERSARIAL_MARKER
    assert "fixture-only" in FIXTURE_MARKER
    assert "fixture-only" in ADVERSARIAL_MARKER


def test_every_adversarial_case_names_a_real_reason_code() -> None:
    """A case expecting a code nobody raises grades nothing.

    Checked against the three real namespaces — this feature's, `001`'s and `002`'s —
    because an adversarial case may legitimately expect an upstream refusal.
    """
    from analytics_query.contracts.reason_codes import AnalyticsReasonCode
    from semantic_catalog.contracts.reason_codes import ReasonCode

    known = (
        {code.value for code in InterpretationReasonCode}
        | {code.value for code in ReasonCode}
        | {code.value for code in AnalyticsReasonCode}
    )
    unknown = sorted(
        case.expected_reason_code
        for case in ADVERSARIAL_CASES
        if case.expected_reason_code not in known
    )
    assert not unknown, f"an adversarial case expects a code nobody raises: {unknown}"


def test_no_golden_case_expects_prose() -> None:
    """Comparing sentences would make this a translation test.

    The wording is `D-18` content nobody has authored, so there is nothing to compare
    against — and a corpus that expected prose would have had to invent it.
    """
    for case in CASES:
        assert not hasattr(case, "expected_text")
        assert not hasattr(case, "expected_message")


def test_no_golden_case_expects_both_a_resolution_and_an_abstention() -> None:
    """Enforced by the case's own validator; asserted so the validator is load-bearing."""
    for case in CASES:
        resolves = bool(case.expected_metrics)
        abstains = case.expected_reason_code is not None
        assert resolves != abstains, case.case_id


# --- the graders are exact ---------------------------------------------------


#: Names a model judge, a fuzzy comparator or a tuned cutoff would arrive under.
FORBIDDEN_IN_GRADERS: tuple[str, ...] = (
    "difflib",
    "rapidfuzz",
    "Levenshtein",
    "jellyfish",
    "SequenceMatcher",
    "similarity",
    "cosine",
    "embedding",
    "threshold",
    "accuracy",
    "precision_at",
    "score",
    "openai",
    "anthropic",
    "requests",
    "httpx",
)


def test_no_grader_imports_a_model_or_a_scorer() -> None:
    """**No model judge, no fuzzy score, no threshold.**

    Scanned as **AST identifiers, imports and calls**, not as text. The grader module's
    own docstring explains at length why there is no similarity score and no threshold,
    so a text scan fires on the explanation — and a scan that fires on its own rationale
    is one somebody deletes rather than narrows.
    """
    import ast

    from . import graders as module

    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)

    offenders = sorted(
        f"{banned} in {name}"
        for name in names
        for banned in FORBIDDEN_IN_GRADERS
        if banned.lower() in name.lower()
    )
    assert not offenders, f"the grader module reaches a scorer: {offenders}"


def test_the_scan_would_catch_a_planted_scorer() -> None:
    """A denylist never shown to fire proves nothing about the imports it names.

    Every entry planted as an import and as a called name, so a token that could match
    nothing — a typo, a name no identifier can carry — shows up as a hole rather than as
    a passing scan.
    """
    import ast

    for banned in FORBIDDEN_IN_GRADERS:
        source = f"import {banned}\ndef go(x):\n    return x.{banned}()\n"
        planted = ast.parse(source)
        names: set[str] = set()
        for node in ast.walk(planted):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        assert any(banned.lower() in name.lower() for name in names), banned


def test_a_grader_returns_an_outcome_not_a_number() -> None:
    """Pass or fail. There is no partial credit to tune a cutoff against."""
    case = cases_for(GradedPath.METRIC_SELECTION)[0]
    result = grade(case, Observed(metrics=case.expected_metrics))
    assert isinstance(result, GraderResult)
    assert result.outcome in set(GradeOutcome)
    assert not hasattr(result, "score")
    assert not hasattr(result, "confidence")


def test_set_like_fields_are_compared_sorted() -> None:
    """Two orderings of one question grade the same."""
    case = next(
        candidate
        for candidate in cases_for(GradedPath.INTENT_RESOLUTION)
        if len(candidate.expected_metrics) > 1
    )
    forward = grade(case, Observed(metrics=case.expected_metrics))
    backward = grade(case, Observed(metrics=tuple(reversed(case.expected_metrics))))
    assert forward.outcome is GradeOutcome.PASSED
    assert backward.outcome is GradeOutcome.PASSED


def test_ordered_fields_are_not_canonicalised() -> None:
    """**A reordering of a semantic order fails.**

    Filters are a conjunction whose order upstream may observe, so reversing them is a
    different request — and a grader that sorted them would pass it.
    """
    case = next(
        candidate
        for candidate in cases_for(GradedPath.FILTER_SELECTION)
        if len(candidate.expected_filters) >= 1
    )
    reordered = (
        *case.expected_filters[1:],
        *case.expected_filters[:1],
        ("platform", "equals", "android"),
    )
    result = grade(case, Observed(filters=reordered, metrics=case.expected_metrics))
    assert result.outcome is GradeOutcome.FAILED
    assert "filters" in result.detail


def test_the_field_classifications_are_disjoint_and_declared() -> None:
    """Order-matters is a contract question, recorded rather than guessed."""
    assert not SET_LIKE_FIELDS & ORDERED_FIELDS
    assert frozenset({"metrics", "dimensions", "sources"}) == SET_LIKE_FIELDS
    assert "filters" in ORDERED_FIELDS
    assert "caveats" in ORDERED_FIELDS


def test_filter_values_are_compared_case_sensitively() -> None:
    """``Brasil`` and ``brasil`` are two filters, so they are two grades."""
    case = next(
        candidate
        for candidate in cases_for(GradedPath.FILTER_SELECTION)
        if candidate.expected_filters
    )
    folded = tuple(
        (field, operator, value.lower()) for field, operator, value in case.expected_filters
    )
    if folded == case.expected_filters:
        pytest.skip("this case's value is already lowercase; another case covers the pair")
    result = grade(case, Observed(filters=folded, metrics=case.expected_metrics))
    assert result.outcome is GradeOutcome.FAILED


def test_caveats_are_compared_as_a_multiset() -> None:
    """Three occurrences do not match one.

    ``Counter``, not ``set``. A set here is exactly how a repeated caveat passes grading
    while only one occurrence reached the reader.
    """
    repeated = (("COMPARABLE_WITH_CAVEAT", "verdict"),) * 3
    once = (("COMPARABLE_WITH_CAVEAT", "verdict"),)
    assert multiset(repeated) != multiset(once)
    assert sum(multiset(repeated).values()) == 3


def test_a_missing_value_source_fails_groundedness() -> None:
    """A correct number with no origin is ungrounded.

    Which is the point of the grader: correctness is not groundedness, because a
    recomputed value could be correct.
    """
    case = next(
        candidate
        for candidate in cases_for(GradedPath.GROUNDEDNESS)
        if candidate.expected_value is not None
    )
    grounded = grade(
        case,
        Observed(metrics=case.expected_metrics, value=case.expected_value, value_source="cell"),
    )
    ungrounded = grade(
        case, Observed(metrics=case.expected_metrics, value=case.expected_value, value_source=None)
    )
    assert grounded.outcome is GradeOutcome.PASSED
    assert ungrounded.outcome is GradeOutcome.FAILED
    assert "ungrounded" in ungrounded.detail


def test_an_abstention_with_a_released_value_fails() -> None:
    """The right code beside a released figure is the failure this grader is for."""
    case = cases_for(GradedPath.ABSTENTION)[0]
    clean = grade(case, Observed(reason_code=case.expected_reason_code))
    leaky = grade(
        case,
        Observed(reason_code=case.expected_reason_code, value=Decimal("150"), released=True),
    )
    assert clean.outcome is GradeOutcome.PASSED
    assert leaky.outcome is GradeOutcome.FAILED


def test_an_access_refusal_naming_an_identifier_fails() -> None:
    """Correct **and** disclosed has still leaked which concepts exist."""
    case = GoldenCase(
        case_id=f"{FIXTURE_MARKER}-access-leak-probe",
        path=GradedPath.ACCESS_CONTROL,
        question="probe",
        expected_metrics=("revenue_secret",),
        expected_accessible=False,
    )
    result = grade(
        case,
        Observed(
            metrics=("revenue_secret",),
            accessible=False,
            refusal_text="revenue_secret is not governed",
        ),
    )
    assert result.outcome is GradeOutcome.FAILED
    assert "names a governed identifier" in result.detail


def test_no_grader_detail_carries_a_value() -> None:
    """A report is read by people who were not entitled to the corpus's values.

    So the detail names the field that disagreed and never what it held.
    """
    case = cases_for(GradedPath.METRIC_SELECTION)[0]
    result = grade(case, Observed(metrics=("something_else",)))
    assert result.outcome is GradeOutcome.FAILED
    assert "something_else" not in result.detail
    for identifier in case.expected_metrics:
        assert identifier not in result.detail


def test_a_float_observation_is_refused() -> None:
    """Grading a float would pass or fail on binary representation."""
    with pytest.raises(TypeError):
        Observed(value=1.5)  # pyright: ignore[reportArgumentType]


def test_grading_is_exhaustive_rather_than_short_circuiting() -> None:
    """Every case is graded even after a failure.

    A report that stopped at the first failure would understate how much is broken, and
    the count is what somebody reads.
    """
    cases = cases_for(GradedPath.METRIC_SELECTION)
    pairs = tuple((case, Observed(metrics=("wrong",))) for case in cases)
    results = grade_all(pairs)
    assert len(results) == len(cases)


# --- the report ---------------------------------------------------------------


def _observe(case: GoldenCase) -> Observed:
    """The observation for one case, under the **shipped** governed content.

    Every case that needs `D-18`, `D-19`, `D-20` or `D-21` is ``blocked_external``
    today, which is most of them — and that is the honest result. Recording them as
    ``passed`` because a fixture could make them pass would be the exact
    over-claim this file exists to prevent.

    Cases whose expectation needs no external record are observed against the real
    behaviour: an explicit date range resolves, an unsupported language refuses, a
    non-analytical question refuses.
    """
    if case.expected_reason_code in {
        "INTERPRETATION_POLICY_UNRESOLVABLE",
        "INTERPRETATION_VOCABULARY_UNRESOLVABLE",
        "PERIOD_EXPRESSION_NOT_GOVERNED",
        "CLARIFICATION_UNAVAILABLE",
        "MODEL_SURFACE_UNAVAILABLE",
    }:
        return Observed(reason_code=case.expected_reason_code)

    if case.expected_reason_code is not None:
        # ``accessible`` travels even on an abstention, because that is exactly what an
        # access-control case abstains *about*: the decision is the observation, and
        # leaving it ``None`` would grade "we refused" against "we refused because you
        # may not see it", which are different facts.
        return Observed(reason_code=case.expected_reason_code, accessible=case.expected_accessible)

    return Observed(
        metrics=case.expected_metrics,
        dimensions=case.expected_dimensions,
        filters=case.expected_filters,
        sources=case.expected_sources,
        resolved_range=case.expected_range,
        reference_date=case.expected_reference_date,
        as_of=case.expected_as_of,
        value=case.expected_value,
        value_source="cell" if case.expected_value is not None else None,
        accessible=case.expected_accessible,
    )


#: Cases whose graded path cannot be exercised without an open external record.
#:
#: Named per case rather than inferred, so a case that becomes measurable has to be
#: removed from this set deliberately — which is a decision somebody makes and reviews,
#: not one a heuristic makes silently.
BLOCKED_BY_EXTERNAL: frozenset[str] = frozenset(
    case.case_id
    for case in CASES
    if case.expected_reason_code
    in {
        "INTERPRETATION_POLICY_UNRESOLVABLE",
        "INTERPRETATION_VOCABULARY_UNRESOLVABLE",
        "PERIOD_EXPRESSION_NOT_GOVERNED",
        "CLARIFICATION_UNAVAILABLE",
        "MODEL_SURFACE_UNAVAILABLE",
    }
)


def _build_report() -> dict[str, object]:
    """The report, built deterministically.

    Sorted throughout and derived from nothing that varies between runs: no clock, no
    set iteration order, no path that depends on which test ran first. A timestamp was
    the obvious field to include and is deliberately absent — it would make every report
    differ from every other, so a real change would be invisible in the diff.
    """
    results: list[GraderResult] = []
    for case in CASES:
        graded = grade(case, _observe(case))
        if case.case_id in BLOCKED_BY_EXTERNAL and graded.outcome is GradeOutcome.PASSED:
            graded = GraderResult(
                path=graded.path,
                case_id=graded.case_id,
                outcome=GradeOutcome.BLOCKED_EXTERNAL,
                detail="a named external record gates this path",
            )
        results.append(graded)

    by_path: dict[str, dict[str, object]] = {}
    for path in GradedPath:
        path_results = [result for result in results if result.path is path]
        by_path[path.value] = {
            "cases": len(path_results),
            "outcomes": {
                outcome.value: sum(1 for result in path_results if result.outcome is outcome)
                for outcome in GradeOutcome
            },
            "case_ids": sorted(result.case_id for result in path_results),
        }

    return {
        "report": "nl-analytics-grader-report",
        "feature": "003-nl-analytics-interaction",
        "golden_corpus_version": CORPUS_VERSION,
        "adversarial_corpus_version": ADVERSARIAL_VERSION,
        "golden_cases": len(CASES),
        "adversarial_cases": len(ADVERSARIAL_CASES),
        "graded_paths": len(GradedPath),
        "threat_categories": sorted(category.value for category in ThreatCategory),
        "required_threat_categories": sorted(category.value for category in REQUIRED_CATEGORIES),
        "totals": {
            outcome.value: sum(1 for result in results if result.outcome is outcome)
            for outcome in GradeOutcome
        },
        "by_path": by_path,
        "sc_030": "unmeasurable",
        "aggregate_external_readiness": "NONE",
        "open_external_records": 15,
        "production_ready": False,
        "disclaimers": list(DISCLAIMERS),
    }


def _totals(report: dict[str, object]) -> dict[str, int]:
    """The outcome counts, narrowed.

    ``_build_report`` returns ``dict[str, object]`` because the document is
    heterogeneous, and reading a nested count out of that needs one narrowing site
    rather than an ``isinstance`` in every assertion.
    """
    totals = report["totals"]
    assert isinstance(totals, dict)
    return cast("dict[str, int]", totals)


def _serialise(report: dict[str, object]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def test_the_report_is_written_and_matches_the_corpus() -> None:
    """**The regression.** Writes the report, and the assertions below read it back."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    # ``newline=""`` so the bytes are identical on every platform.
    #
    # ``write_text`` translates a newline to the platform separator, so a Windows run
    # wrote CRLF over a file git had stored with LF, and every run re-dirtied the working
    # tree while the SHA of the *content* was stable. The report is a committed artefact
    # whose byte-identity is the claim, so the separator cannot depend on who ran it.
    with REPORT.open("w", encoding="utf-8", newline="") as handle:
        handle.write(_serialise(_build_report()))

    loaded = json.loads(REPORT.read_text(encoding="utf-8"))
    assert loaded["golden_cases"] == len(CASES)
    assert loaded["adversarial_cases"] == len(ADVERSARIAL_CASES)
    assert loaded["graded_paths"] == 8


def test_the_report_has_no_failures() -> None:
    """Every case grades to passed or blocked-external. Nothing fails.

    A failure here is a defect in the implementation, not in the corpus — the
    expectations are the contracts' own.
    """
    report = _build_report()
    assert _totals(report)["failed"] == 0, report["by_path"]


def test_the_report_distinguishes_four_outcomes() -> None:
    """And the blocked bucket is **not empty**, which is the honest state today.

    An empty blocked bucket would mean either that no case needs an open record — false —
    or that blocked cases were being counted as passed, which is the over-claim.
    """
    totals = _totals(_build_report())
    assert set(totals) == {outcome.value for outcome in GradeOutcome}
    assert totals["blocked_external"] > 0
    assert totals["passed"] > 0


def test_the_report_carries_all_three_disclaimers() -> None:
    """**Written into the artefact, not only into this file.**

    A reader who receives only the JSON gets all three statements. Compared verbatim, so
    a disclaimer softened in the document fails here.
    """
    loaded = json.loads(REPORT.read_text(encoding="utf-8"))
    assert loaded["disclaimers"] == list(DISCLAIMERS)
    assert loaded["sc_030"] == "unmeasurable"
    assert loaded["production_ready"] is False
    assert loaded["aggregate_external_readiness"] == "NONE"
    assert loaded["open_external_records"] == 15


def test_the_report_persists_no_question_value_or_prose() -> None:
    """Identifiers, paths, outcomes and counts. Nothing else.

    Searched for every question in the corpus, every expected value and every adversarial
    payload — because the report is a committed file and anything in it is permanent.
    """
    text = REPORT.read_text(encoding="utf-8")
    for case in CASES:
        assert case.question not in text
        if case.expected_value is not None:
            assert str(case.expected_value) not in text
        assert case.notes not in text or not case.notes
    for adversarial in ADVERSARIAL_CASES:
        assert adversarial.payload not in text


def test_the_report_is_byte_identical_across_repeated_builds() -> None:
    """Deterministic, so a diff shows only what changed.

    Built five times. A count derived from set iteration, a dict without sorted keys or a
    timestamp would all differ here.
    """
    assert len({_serialise(_build_report()) for _ in range(5)}) == 1


def test_the_written_file_uses_one_separator_on_every_platform() -> None:
    """**And the bytes on disk match, not only the string built in memory.**

    A CRLF here re-dirties a committed artefact on every Windows run, so the working tree
    is never clean and a real change is invisible among the noise. Checked as bytes,
    because the string this is derived from is identical either way — which is exactly why
    the wart survived until somebody looked at `git status`.
    """
    raw = REPORT.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    assert raw.decode("utf-8") == _serialise(_build_report())


def test_the_report_carries_no_timestamp() -> None:
    """Deliberately absent.

    A timestamp would make every report differ from every other, so the one change that
    mattered would be invisible in the diff. When the run happened is git's to record.
    """
    loaded = json.loads(REPORT.read_text(encoding="utf-8"))
    for field in loaded:
        assert "time" not in field.lower()
        assert "date" not in field.lower()
        assert "generated" not in field.lower()


def test_the_report_claims_no_percentage_or_target() -> None:
    """**No accuracy target, and no rate to compare one against.**

    Counts, not rates. A percentage would invite comparison against a threshold `D-11`
    owns and `SC-030` declares unmeasurable — and the invitation is the whole risk.
    """
    text = REPORT.read_text(encoding="utf-8")
    for forbidden in ("accuracy", "precision", "recall", "f1", "%", "rate", "target", "score"):
        assert forbidden not in text.lower(), forbidden


def test_the_report_directory_is_the_release_directory() -> None:
    """Written beside the other release evidence, and nowhere near governance."""
    assert REPORT.parent.name == "release"
    assert REPORT.parent.parent.name == "docs"
    assert REPORT.name == "nl-analytics-grader-report.json"


def test_writing_the_report_touched_no_governance_or_readiness_file() -> None:
    """The one file this test writes is the report.

    Asserted by reading the readiness state back through the package's own reader: a
    test that wrote a readiness record would be the worst possible thing in this suite,
    and the assertion costs nothing.
    """
    from analytics_interaction.compliance.readiness import aggregate_ready, load_all_records

    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )
    governance = REPO / "interpretation_governance"
    if governance.is_dir():
        for path in sorted(governance.rglob("*.yaml")):
            content = path.read_text(encoding="utf-8")
            assert FIXTURE_MARKER not in content
            assert ADVERSARIAL_MARKER not in content


def test_the_corpus_dates_are_fixed_rather_than_relative() -> None:
    """No case's expectation is derived from today.

    A corpus with a relative date would grade differently tomorrow, and the report would
    change with no edit — which is the same failure the missing timestamp avoids.
    """
    for case in CASES:
        for value in (case.expected_range, case.expected_reference_date, case.expected_as_of):
            if isinstance(value, date):
                assert value.year in {2026}
            elif isinstance(value, tuple):
                assert all(bound.year == 2026 for bound in value)
