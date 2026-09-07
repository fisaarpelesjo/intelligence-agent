"""Eight deterministic graders — T167 (FR-005, FR-006, FR-020; SC-001, SC-012, SC-015).

    Evidence: graders are deterministic comparators over governed identifiers — **no
    model, no heuristic scoring, no invented threshold**. — `tasks.md` T167

## What a grader is here, and what it is not

A grader is an **exact comparator** over governed identifiers and structured outcomes.
It returns pass or fail. It does not return a score, a similarity, a confidence or a
percentage, and there is no threshold anywhere in this file.

That is not minimalism. Every alternative would import a decision nobody approved:

* a **model judge** would make the evaluation depend on a provider, which `D-20` gates
  and which would also let the thing under test grade itself;
* a **fuzzy score** would need a cutoff, and the cutoff would be this feature inventing
  the interpretation-quality threshold that `D-11` owns and `SC-030` declares
  unmeasurable;
* an **accuracy target** would be a claim about production behaviour drawn from a corpus
  written by the same process that wrote the implementation.

So: exact comparison, or nothing.

## Order matters where the contract says it does, and only there

`metrics`, `dimensions` and `sources` are **set-like** by contract — a question naming
two metrics in either order asks one thing — so they are compared as sorted tuples.
Everything else is compared in order, including:

* `claims`, because the operands must precede the figure derived from them;
* `caveats`, because encounter order carries origin sequence and a sort would need a
  tiebreaker, and the obvious tiebreaker is the collapse that must not happen;
* `filters`, because a filter list is a conjunction whose evaluation order upstream may
  observe.

A grader that canonicalised an ordered field would pass a reordering that changes
meaning. One that ordered a set-like field would fail two spellings of one question.
Both are recorded per field rather than inferred.

## Multiplicity is never collapsed

Caveats are compared as a **multiset**, so three identical occurrences do not match one.
`Counter`, not `set`: a set here is exactly how a repeated caveat passes grading while
only one occurrence reached the reader.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from ..fixtures.golden import GoldenCase, GradedPath

__all__ = [
    "GRADERS",
    "ORDERED_FIELDS",
    "SET_LIKE_FIELDS",
    "GradeOutcome",
    "GraderResult",
    "Observed",
    "grade",
    "grade_all",
]

#: Fields the contract declares **set-like**. Compared sorted, and only these.
#:
#: Named rather than inferred, because "does order matter here" is a contract question
#: and a grader that guessed would be answering it.
SET_LIKE_FIELDS: frozenset[str] = frozenset({"metrics", "dimensions", "sources"})

#: Fields whose order is **semantic**. Compared as given, and a reordering fails.
ORDERED_FIELDS: frozenset[str] = frozenset({"claims", "caveats", "filters", "provenance"})


class GradeOutcome(StrEnum):
    """Four outcomes, and the distinction between the last two is the point.

    ``UNMEASURABLE`` means no approved definition exists to grade against — `SC-030`
    while `D-11` is absent. ``BLOCKED_EXTERNAL`` means the path exists but a named
    external record gates it. Collapsing them into ``FAILED`` would report an open
    dependency as a defect; collapsing either into ``PASSED`` would report absence as
    success.
    """

    PASSED = "passed"
    FAILED = "failed"
    UNMEASURABLE = "unmeasurable"
    BLOCKED_EXTERNAL = "blocked_external"


@dataclass(frozen=True, slots=True)
class Observed:
    """What actually happened for one case.

    Every field is optional because a case that abstained has no metrics and a case that
    resolved has no reason code — and a dataclass with required fields would force a
    caller to invent one of them.

    ``value`` is a ``Decimal`` or ``None``. Never a ``float``: a grader comparing floats
    would pass or fail on binary representation, which is the failure the whole
    comparison module exists to avoid.
    """

    metrics: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()
    filters: tuple[tuple[str, str, str], ...] = ()
    sources: tuple[str, ...] = ()
    resolved_range: tuple[date, date] | None = None
    reference_date: date | None = None
    as_of: date | None = None
    reason_code: str | None = None
    value: Decimal | None = None
    value_source: str | None = None
    accessible: bool | None = None
    released: bool = False
    caveats: tuple[tuple[str, str], ...] = ()
    refusal_text: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.value, float):
            raise TypeError("an observed value is exact or absent; never a float")


@dataclass(frozen=True, slots=True)
class GraderResult:
    """One grader's verdict on one case. Pass or fail, plus why.

    ``detail`` names the field that disagreed and nothing else — never the expected or
    observed *value*, because a grader report is an artefact that gets read by people
    who were not entitled to the values in the corpus.
    """

    path: GradedPath
    case_id: str
    outcome: GradeOutcome
    detail: str = ""


def _sorted(values: tuple[str, ...]) -> tuple[str, ...]:
    """Set-like canonicalisation: sorted, duplicates kept.

    Duplicates are kept deliberately. ``sorted`` rather than ``sorted(set(...))``,
    because a metric named twice is a question somebody should see rather than a
    duplicate to tidy — and tidying it here would hide it from every grader.
    """
    return tuple(sorted(values))


def _compare(
    path: GradedPath,
    case_id: str,
    checks: tuple[tuple[str, object, object], ...],
) -> GraderResult:
    """Every check, exactly. The first disagreement names its field and stops.

    Stopping at the first is deliberate: a grader reporting five disagreements for one
    root cause makes a report look worse than the defect is, and the fix for the first
    usually resolves the rest.
    """
    for field, expected, observed in checks:
        if expected != observed:
            return GraderResult(
                path=path,
                case_id=case_id,
                outcome=GradeOutcome.FAILED,
                detail=f"{field} disagrees",
            )
    return GraderResult(path=path, case_id=case_id, outcome=GradeOutcome.PASSED)


# --- the eight graders ---------------------------------------------------------


def grade_intent_resolution(case: GoldenCase, observed: Observed) -> GraderResult:
    """The resolved identifiers, exactly. Set-like fields sorted, nothing else.

    This is the broadest grader and the one that would be most tempting to soften: an
    intent that resolved four of five identifiers is *nearly* right, and nearly right is
    a wrong answer disclosed as authoritative.
    """
    return _compare(
        GradedPath.INTENT_RESOLUTION,
        _case_id(case),
        (
            ("metrics", _sorted(case.expected_metrics), _sorted(observed.metrics)),
            (
                "dimensions",
                _sorted(case.expected_dimensions),
                _sorted(observed.dimensions),
            ),
            ("sources", _sorted(case.expected_sources), _sorted(observed.sources)),
            ("reason_code", case.expected_reason_code, observed.reason_code),
        ),
    )


def grade_metric_selection(case: GoldenCase, observed: Observed) -> GraderResult:
    """The metric identifiers. Sorted, because metrics are set-like by contract."""
    return _compare(
        GradedPath.METRIC_SELECTION,
        _case_id(case),
        (
            ("metrics", _sorted(case.expected_metrics), _sorted(observed.metrics)),
            ("reason_code", case.expected_reason_code, observed.reason_code),
        ),
    )


def grade_dimension_selection(case: GoldenCase, observed: Observed) -> GraderResult:
    """The dimension identifiers, sorted."""
    return _compare(
        GradedPath.DIMENSION_SELECTION,
        _case_id(case),
        (
            (
                "dimensions",
                _sorted(case.expected_dimensions),
                _sorted(observed.dimensions),
            ),
            ("reason_code", case.expected_reason_code, observed.reason_code),
        ),
    )


def grade_filter_selection(case: GoldenCase, observed: Observed) -> GraderResult:
    """Filters **in order**, and values **case-sensitively**.

    A conjunction whose order upstream may observe, so not sorted. And the value is
    compared byte-for-byte: the warehouse distinguishes ``Brasil`` from ``brasil``, so a
    grader that folded case would pass a filter that asks a different question.
    """
    return _compare(
        GradedPath.FILTER_SELECTION,
        _case_id(case),
        (
            ("filters", case.expected_filters, observed.filters),
            ("reason_code", case.expected_reason_code, observed.reason_code),
        ),
    )


def grade_date_resolution(case: GoldenCase, observed: Observed) -> GraderResult:
    """The resolved range, and both dates **independently**.

    Three separate checks rather than one, because `FR-097` forbids either date being
    filled from the other and a combined check would pass a derivation that happened to
    produce a consistent pair.
    """
    return _compare(
        GradedPath.DATE_RESOLUTION,
        _case_id(case),
        (
            ("resolved_range", case.expected_range, observed.resolved_range),
            (
                "reference_date",
                case.expected_reference_date,
                observed.reference_date,
            ),
            ("as_of", case.expected_as_of, observed.as_of),
            ("reason_code", case.expected_reason_code, observed.reason_code),
        ),
    )


def grade_groundedness(case: GoldenCase, observed: Observed) -> GraderResult:
    """Every released figure traces to a cell or to a governed formula.

    Two checks and the second is the one that matters. The value being right is not
    groundedness — a recomputed value could be right. What is graded is where it *came
    from*: ``value_source`` names the port's cell or the formula identifier, and a claim
    with neither is ungrounded however correct its number.
    """
    expected_value = case.expected_value
    checks: tuple[tuple[str, object, object], ...] = (
        ("value", expected_value, observed.value),
        ("reason_code", case.expected_reason_code, observed.reason_code),
    )
    result = _compare(GradedPath.GROUNDEDNESS, _case_id(case), checks)
    if result.outcome is not GradeOutcome.PASSED:
        return result
    if expected_value is not None and not observed.value_source:
        return GraderResult(
            path=GradedPath.GROUNDEDNESS,
            case_id=_case_id(case),
            outcome=GradeOutcome.FAILED,
            detail="value_source is absent; a figure with no origin is ungrounded",
        )
    return result


def grade_abstention(case: GoldenCase, observed: Observed) -> GraderResult:
    """The exact reason code, **and** that nothing was released.

    Both halves. A refusal carrying the right code beside a released value is the
    failure this grader exists for, and a code-only check would pass it.
    """
    result = _compare(
        GradedPath.ABSTENTION,
        _case_id(case),
        (("reason_code", case.expected_reason_code, observed.reason_code),),
    )
    if result.outcome is not GradeOutcome.PASSED:
        return result
    if observed.released or observed.value is not None:
        return GraderResult(
            path=GradedPath.ABSTENTION,
            case_id=_case_id(case),
            outcome=GradeOutcome.FAILED,
            detail="something was released alongside the abstention",
        )
    return result


def grade_access_control(case: GoldenCase, observed: Observed) -> GraderResult:
    """The access decision, and that an inaccessible concept looks absent.

    ``accessible`` is graded, and separately the refusal text is checked to carry no
    identifier — because an access decision that is correct and *disclosed* has still
    leaked which concepts exist.
    """
    result = _compare(
        GradedPath.ACCESS_CONTROL,
        _case_id(case),
        (
            ("accessible", case.expected_accessible, observed.accessible),
            ("reason_code", case.expected_reason_code, observed.reason_code),
        ),
    )
    if result.outcome is not GradeOutcome.PASSED:
        return result
    leaked = [
        identifier
        for identifier in case.expected_metrics
        if identifier and identifier in observed.refusal_text
    ]
    if leaked:
        return GraderResult(
            path=GradedPath.ACCESS_CONTROL,
            case_id=_case_id(case),
            outcome=GradeOutcome.FAILED,
            detail="the refusal names a governed identifier",
        )
    return result


def _case_id(case: GoldenCase) -> str:
    return case.case_id


#: Path to grader. Read-only, and asserted total against ``GradedPath`` by the
#: regression — a path with no grader would be silently ungraded.
_GRADERS: dict[GradedPath, Callable[[GoldenCase, Observed], GraderResult]] = {
    GradedPath.INTENT_RESOLUTION: grade_intent_resolution,
    GradedPath.METRIC_SELECTION: grade_metric_selection,
    GradedPath.DIMENSION_SELECTION: grade_dimension_selection,
    GradedPath.FILTER_SELECTION: grade_filter_selection,
    GradedPath.DATE_RESOLUTION: grade_date_resolution,
    GradedPath.GROUNDEDNESS: grade_groundedness,
    GradedPath.ABSTENTION: grade_abstention,
    GradedPath.ACCESS_CONTROL: grade_access_control,
}

GRADERS: Mapping[GradedPath, Callable[[GoldenCase, Observed], GraderResult]] = MappingProxyType(
    _GRADERS
)


def grade(case: GoldenCase, observed: Observed) -> GraderResult:
    """Run the grader that owns this case's path.

    Dispatched on the case's own declared path rather than on inspection of the
    expectation, so a case cannot be graded by whichever grader happens to pass.
    """
    path = case.path
    return GRADERS[path](case, observed)


def grade_all(pairs: tuple[tuple[GoldenCase, Observed], ...]) -> tuple[GraderResult, ...]:
    """Grade every pair, in order. No short-circuit.

    Every case is graded even after a failure: a report that stopped at the first
    failure would understate how much is broken, and the count is what somebody reads.
    """
    return tuple(grade(case, observed) for case, observed in pairs)


def multiset(caveats: tuple[tuple[str, str], ...]) -> Counter[tuple[str, str]]:
    """Caveats as a **multiset**. Exposed so the regression can assert it is one.

    ``Counter``, never ``set``. Three identical occurrences do not match one, because
    multiplicity may represent three decisions and a set is precisely how the count
    stops being graded.
    """
    return Counter(caveats)
