"""Whole-comparison refusal and release — T108 (FR-067, FR-068; SC-039).

**Neither side is returned. No partial state is representable.**

``GovernedComparison`` takes exactly two sides, so "return the side that worked"
is not a mistake somebody can make — it is a thing the type system will not
express. This module is the other half of that: the place where both sides are
validated **completely** before any figure is computed, and where a failure on
either one refuses the whole comparison with nothing attached.

The deliberate asymmetry is worth restating (`comparison-contract.md` §5.2): a
lone answer carrying suppressed cells is a permitted ``ALLOW_WITH_CAVEAT`` in
`002`; the **same suppression inside a comparison refuses the whole thing**. A
difference computed across a hole is a number nobody can interpret, and
presenting it would be exactly the confidently-wrong figure `001`'s `BO-4` exists
to prevent.

## Side A is validated before side B is asked for

The two sides arrive as **callables**, not as values. That is the ordering
requirement expressed structurally: :func:`govern_comparison` runs side A,
validates it fully, and only then invokes side B. A failing side A means side B's
callable is never called — one execution billed, not two, for a comparison that
was never going to be released.

Passing two already-executed answers would have made that ordering a convention
somebody follows. Passing two thunks makes it a property `T108`'s suite can count.

## Nothing partial escapes, including through the refusal

Every refusal here carries a governed code and a detail that names **no** value,
row, cell, unit, version, tag or identifier from either side. A refusal that
disclosed "side A returned 412 and side B was suppressed" would leak both the
figure and the suppression, and a caller holding access to one side would learn
about the other. The details say what class of thing went wrong and stop.

## The enumerated conditions are closed, and unrecognised fails closed

`comparison-contract.md` §5.1 enumerates seven material-mismatch conditions and
states that **anything outside the set fails closed as a mismatch** rather than
passing as unrecognised. :class:`MismatchCondition` is that set, and
:func:`mismatch` refuses any name outside it — so a condition added to the
contract without being implemented here surfaces as a refusal, never as a silent
pass.

The release path is allowlist-shaped for the same reason: a side is releasable
only when it satisfies **every** enumerated check. A property nobody thought to
check cannot make a side pass; it can only fail to make it fail.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from analytics_query.contracts.result import Completeness
from semantic_catalog.validation.decision import Finality

from ..contracts._base import ContractViolation, build
from ..contracts.comparison import GovernedComparison, SideResult
from ..contracts.reason_codes import InterpretationReasonCode
from ..governance.vocabulary import resolve_comparison_formulas
from ..identity.authorization_fingerprint import derive_authorization_fingerprint
from .compute import derive_figure, to_exact
from .formula import assert_baseline_is_usable, resolve_formula
from .permitted import is_executable
from .units import assert_units_agree, result_unit
from .window import window_for_comparison

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date
    from decimal import Decimal

    from analytics_query.contracts.request import AnalyticsQuery
    from analytics_query.contracts.result import AnalyticsResult
    from analytics_query.execute import ExecutedAnswer
    from semantic_catalog.validation.decision import CatalogDecision

    from ..authorization.context_preflight import AuthorizedContext
    from ..contracts.answer import CaveatSet
    from ..governance.schemas import ComparisonFormulas

__all__ = [
    "RELEASABLE_KINDS",
    "MismatchCondition",
    "SideSubmission",
    "assert_caveats_are_complete",
    "assert_side_is_releasable",
    "assert_sides_are_coherent",
    "govern_comparison",
    "mismatch",
    "side_value",
]

#: The one disposition a comparison side may carry. ``EMPTY`` is excluded
#: deliberately: a genuine absence of data is a valid answer on its own and a
#: missing operand in a comparison, and treating it as zero would fabricate the
#: figure. ``PARTIALLY_WITHHELD`` and ``FULLY_WITHHELD`` are §5.2's asymmetry.
#:
#: Held as the enum's **value** rather than as ``ResultKind`` itself: that type
#: lives in ``analytics_query.results``, one of the seven subpackages ADR 0010
#: forbids this feature to import. The comparison is therefore against
#: ``str(kind)``, and an unrecognised disposition — including a member `002`
#: adds later — falls outside the set and refuses, which is the direction to
#: fail in.
RELEASABLE_KINDS: frozenset[str] = frozenset({"populated"})


@dataclass(frozen=True, slots=True)
class SideSubmission:
    """One side, as a request and a way to execute it.

    The request and the execution travel together so a caller cannot validate
    one side's shape while executing the other's — and so ``submit`` stays a
    **thunk**: side B's is not invoked until side A has passed every check.
    """

    request: AnalyticsQuery
    submit: Callable[[], ExecutedAnswer]


class MismatchCondition(StrEnum):
    """`comparison-contract.md` §5.1, verbatim and closed.

    A ``StrEnum`` rather than a list of strings so a condition can be named in a
    refusal, asserted in a test and counted — and so the seven are enumerated in
    exactly one place.
    """

    UNITS = "units"
    GRAIN = "grain"
    METRIC_VERSIONS = "metric_versions"
    DIMENSIONAL_COVERAGE = "dimensional_coverage"
    REPRODUCIBILITY = "reproducibility"
    DATA_AS_OF = "data_as_of"
    GOVERNING_VERSIONS = "governing_versions"


def mismatch(condition: str) -> ContractViolation:
    """The governed refusal for one enumerated condition.

    An unrecognised name **fails closed as a mismatch** rather than raising a
    lookup error or passing: a condition the contract names and this module has
    not implemented must refuse the comparison, not slip through it. The two
    outcomes carry the same reason code because they are the same governed fact —
    the comparison is not coherent — and differ only in detail.
    """
    try:
        MismatchCondition(condition)
    except ValueError:
        return ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "an unrecognised comparison condition fails closed as a material mismatch",
        )
    return ContractViolation(
        InterpretationReasonCode.COMPARISON_SIDE_INVALID,
        f"the two sides differ in {condition}; this is an enumerated material mismatch",
    )


# --- one side, completely ---------------------------------------------------------


def assert_side_is_releasable(answer: ExecutedAnswer) -> None:
    """Every enumerated single-side condition. Governance, privacy, evidence, shape.

    Called before the other side is asked for, so a failure here costs one
    execution rather than two.

    Execution failures — failed, timed out, cancelled, shape-divergent,
    limit-breaching — do not appear as checks because `002` raises on all of them
    rather than returning an answer. Restating them here would be this feature
    re-deciding conditions `002` already refused, and the two could disagree.
    """
    if not is_executable(answer.decision):
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a side's governed decision does not permit release; the whole comparison refuses",
        )

    if str(answer.disposition.kind) not in RELEASABLE_KINDS:
        # Suppressed, fully withheld or genuinely empty. All three refuse, and
        # the detail does not say which — the difference between "withheld" and
        # "no data" is itself disclosure about the other side's population.
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a side does not carry a complete visible result; the whole comparison refuses",
        )

    if answer.result.completeness is not Completeness.COMPLETE:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a side's result is not complete for the request as asked",
        )

    if answer.decision.finality is not Finality.FINAL:
        # Evidence: a pre-evidence decision answered the governance question and
        # never asked the data question. Comparing on one would present a figure
        # whose freshness and revision basis nobody established.
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a side's evidence is not final; stale, unpublished or unestablished "
            "evidence refuses the whole comparison",
        )


def side_value(result: AnalyticsResult) -> Decimal:
    """The one exact metric value this side contributes.

    Exactly one row and one metric cell, carrying a value. Anything else is
    structurally incomplete for a comparison: no rows is nothing to compare, many
    rows is a breakdown rather than a figure, and a suppressed or absent cell is
    the hole §5.2 refuses across.

    The value is lifted through ``to_exact``, so a float arriving from a
    misconfigured adapter refuses here rather than being converted.
    """
    metric_columns = [column for column in result.columns if column.is_metric]
    if len(result.rows) != 1 or len(metric_columns) != 1:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a comparison side must carry exactly one row and one metric column",
        )

    # ``cells`` align with the ``is_metric=True`` columns in declaration order,
    # not with all columns — a positional index over ``columns`` would read a
    # dimension's position and, with one metric among several dimensions, would
    # fall off the end or return the wrong cell.
    (row,) = result.rows
    if len(row.cells) != 1:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a side's row does not carry exactly its one metric cell",
        )

    (cell,) = row.cells
    if cell.suppressed or cell.value is None:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a side's metric value is withheld or absent; the whole comparison refuses",
        )
    return to_exact(cell.value)


# --- both sides, against each other and against the verdict -----------------------


def assert_sides_are_coherent(
    verdict: CatalogDecision,
    primary: ExecutedAnswer,
    baseline: ExecutedAnswer,
    *,
    requests: tuple[AnalyticsQuery, AnalyticsQuery],
    vocabulary_version: str,
    formula_version: str,
) -> str:
    """The seven enumerated conditions. Returns the agreed operand unit.

    Each condition is checked against what the two sides and the verdict actually
    declare — never inferred, never reconciled and never converted.
    """
    unit = _units(primary, baseline)
    _grain(*requests)
    _metric_versions(verdict, primary, baseline)
    _dimensional_coverage(primary, baseline)
    _reproducibility(primary, baseline)
    _data_as_of(verdict, primary, baseline)
    _governing_versions(
        verdict,
        primary,
        baseline,
        vocabulary_version=vocabulary_version,
        formula_version=formula_version,
    )
    return unit


def _units(primary: ExecutedAnswer, baseline: ExecutedAnswer) -> str:
    """Condition 1. Exact equality, never a conversion — `units.py` owns it."""
    return assert_units_agree(primary.result, baseline.result)


def _grain(primary: AnalyticsQuery, baseline: AnalyticsQuery) -> None:
    """Condition 2 — grain and grain family.

    Grain is declared on the metric version, not on the result, so it is checked
    where it is observable: the two sides must ask for the **same metrics over
    the same dimensions**. Together with condition 3 (identical resolved metric
    versions) that is grain equality by construction — two sides resolving the
    same versions over the same dimensions cannot be at different grains.

    Checked on the requests rather than inferred from the results, because a
    result's shape reflects what came back and the grain is what was asked.
    """
    if primary.metrics != baseline.metrics or frozenset(primary.dimensions) != frozenset(
        baseline.dimensions
    ):
        raise mismatch(MismatchCondition.GRAIN)


def _metric_versions(
    verdict: CatalogDecision, primary: ExecutedAnswer, baseline: ExecutedAnswer
) -> None:
    """Condition 3 — resolved metric-definition versions.

    Differing versions refuse **unless the verdict explicitly declared them
    comparable**, which `001` expresses by carrying the spanned versions as
    ``segments``. The exemption is deliberately narrow: the verdict must name
    every version both sides resolved, so a segment list covering one side's
    change and not the other's does not license the comparison.
    """
    left = frozenset(primary.provenance.resolved_metric_versions)
    right = frozenset(baseline.provenance.resolved_metric_versions)
    if left == right:
        return

    declared = frozenset(segment.metric_version_id for segment in verdict.segments)
    if declared and (left | right) <= declared:
        return
    raise mismatch(MismatchCondition.METRIC_VERSIONS)


def _dimensional_coverage(primary: ExecutedAnswer, baseline: ExecutedAnswer) -> None:
    """Condition 4. Order-insensitive: coverage is a set, not a sequence."""
    if frozenset(primary.provenance.dimensional_coverage) != frozenset(
        baseline.provenance.dimensional_coverage
    ):
        raise mismatch(MismatchCondition.DIMENSIONAL_COVERAGE)


def _reproducibility(primary: ExecutedAnswer, baseline: ExecutedAnswer) -> None:
    """Condition 5 — one side ``limited`` while the other is ``full``.

    Written as equality rather than as the two-way test the contract phrases,
    because with two members those are the same condition and equality does not
    quietly acquire a hole if `001` adds a third.
    """
    if primary.decision.reproducibility is not baseline.decision.reproducibility:
        raise mismatch(MismatchCondition.REPRODUCIBILITY)


def _data_as_of(
    verdict: CatalogDecision, primary: ExecutedAnswer, baseline: ExecutedAnswer
) -> None:
    """Condition 6 — a differing data-as-of basis where the verdict required one.

    The verdict requires a single basis exactly when it states a comparable
    window: a window is the statement that both sides were read over the same
    governed span, and two different read points would make that statement false.
    """
    if verdict.comparable_window is None:
        return
    if primary.provenance.data_as_of != baseline.provenance.data_as_of:
        raise mismatch(MismatchCondition.DATA_AS_OF)


def _governing_versions(
    verdict: CatalogDecision,
    primary: ExecutedAnswer,
    baseline: ExecutedAnswer,
    *,
    vocabulary_version: str,
    formula_version: str,
) -> None:
    """Condition 7 — catalog release, policy version and vocabulary version.

    Identical across the verdict **and both sides** (`FR-069`). This is the
    two-evaluation seam ADR 0015 exists for: the catalog's verdict on the
    comparison and `002`'s evaluation of each side are two governance decisions
    touching one answer, and they are never allowed to disagree silently.

    The vocabulary version is `003`'s own — it is not on `002`'s provenance,
    because `002` does not read `D-18`. It is compared against the formula set
    actually resolved for this arithmetic, so an intent interpreted under one
    vocabulary and computed under another refuses.
    """
    for side in (primary, baseline):
        if side.provenance.catalog_release_id != verdict.catalog_release_id:
            raise mismatch(MismatchCondition.GOVERNING_VERSIONS)
        if side.provenance.policy_version != verdict.policy_version:
            raise mismatch(MismatchCondition.GOVERNING_VERSIONS)
    if vocabulary_version != formula_version:
        raise mismatch(MismatchCondition.GOVERNING_VERSIONS)


# --- the caveats survive the arithmetic -------------------------------------------


def assert_caveats_are_complete(verdict: CatalogDecision, caveats: CaveatSet) -> None:
    """Every limitation the verdict carried is present in the set.

    Arithmetic cannot remove or rewrite a caveat, and the way this module proves
    it is by refusing to release a comparison whose caveat set has lost one. The
    check is by **code**: the wording is upstream text that this feature must not
    re-derive, so comparing wording here would mean holding a second copy of it.

    Nothing is deduplicated. Two sides carrying the same caveat is information,
    and ``CaveatSet.total`` already makes a downstream collapse detectable.
    """
    carried = {str(caveat.code) for caveat in caveats.caveats}
    missing = [
        limitation.code for limitation in verdict.limitations if limitation.code not in carried
    ]
    if missing:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "the comparison's caveat set does not carry every governed limitation; "
            "an answer whose caveats cannot be carried in full is withheld, never trimmed",
        )


# --- release, or refuse everything -------------------------------------------------


def govern_comparison(
    verdict: CatalogDecision,
    *,
    formula_id: str,
    primary_side: SideSubmission,
    baseline_side: SideSubmission,
    caveats: CaveatSet,
    authorized: AuthorizedContext,
    auth_fingerprint: str,
    on: date,
    vocabulary_version: str,
    derived_from: tuple[str, str],
    instances: tuple[ComparisonFormulas, ...] | None = None,
) -> GovernedComparison:
    """A complete ``GovernedComparison``, or nothing at all.

    The order is the guarantee:

    1. **the fingerprint**, before any arithmetic and before either side is
       asked for — a comparison presented under a different authorization
       context releases nothing and costs nothing;
    2. **the governed formula**, resolved from `D-18`. With the shipped content
       this refuses here, so no side is ever executed for a comparison that could
       not have been computed;
    3. **the window**, taken from the verdict, never recomputed;
    4. **side A**, validated completely;
    5. **side B**, asked for only now, validated completely;
    6. **coherence**, across both sides and the verdict;
    7. **the caveats**, asserted complete against the verdict;
    8. **the arithmetic**, last, on values every gate above has already accepted.

    There is no partial-success outcome and no exception below carries a value, a
    row, a provenance fragment or a partially collected caveat. The only
    successful output is the complete contract object.
    """
    if auth_fingerprint != derive_authorization_fingerprint(authorized):
        raise ContractViolation(
            InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
            "the comparison was resolved under a different authorization context",
        )

    formula = resolve_formula(formula_id, on=on, instances=instances)
    window = window_for_comparison(verdict)

    primary = primary_side.submit()
    assert_side_is_releasable(primary)

    baseline = baseline_side.submit()
    assert_side_is_releasable(baseline)

    assert_sides_are_coherent(
        verdict,
        primary,
        baseline,
        requests=(primary_side.request, baseline_side.request),
        vocabulary_version=vocabulary_version,
        formula_version=_resolved_version(on, instances),
    )
    assert_caveats_are_complete(verdict, caveats)

    primary_value = side_value(primary.result)
    baseline_value = side_value(baseline.result)
    assert_baseline_is_usable(formula, baseline_value)

    figure = derive_figure(
        formula_id=formula.id,
        unit=result_unit(formula),
        primary=primary_value,
        baseline=baseline_value,
        derived_from=derived_from,
        basis=window.reason,
    )

    return build(
        GovernedComparison,
        verdict=verdict,
        window=window,
        formula=formula.id,
        sides=(_side(primary_side, primary), _side(baseline_side, baseline)),
        difference=figure,
        caveats=caveats,
    )


def _side(submission: SideSubmission, answer: ExecutedAnswer) -> SideResult:
    """One executed side, carried whole.

    The request, the result and the provenance travel unchanged and **unmerged**
    (`FR-033`, `FR-072`). Nothing is recomputed, abbreviated or combined with the
    other side's.
    """
    return build(
        SideResult,
        request=submission.request,
        result=answer.result,
        provenance=answer.provenance,
    )


def _resolved_version(on: date, instances: tuple[ComparisonFormulas, ...] | None) -> str:
    """The version of the formula set actually in force for this arithmetic."""
    return resolve_comparison_formulas(on, instances=instances).version
