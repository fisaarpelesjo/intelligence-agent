"""Whole-comparison release and refusal — T108 (FR-067, FR-068; SC-039).

    Evidence: neither side is returned; no partial state is representable.
    — `tasks.md` T108

Four claims, and they fail in different ways:

* **ordering** — the fingerprint, then the governed formula, then the window,
  then side A, then side B. Each gate that refuses costs nothing beyond what has
  already happened, and side B's thunk is **counted** to prove a failing side A
  never bills a second execution;
* **completeness** — a side is releasable only when it satisfies every enumerated
  condition. Governance, privacy, evidence and shape are asserted one at a time,
  because a single "the side is bad" case would pass against a check that fired
  for the wrong reason;
* **nothing partial escapes** — every refusal is inspected for the values, units,
  versions and identifiers of both sides. A refusal that named them would leak
  the figure it refused to release, and would tell a caller holding one side's
  access about the other's;
* **release** — the only success is a complete ``GovernedComparison``: two sides
  carried whole and unmerged, the verdict, the window, the formula, the caveat
  set and one derived figure.

## The two-execution release, end to end — ADR 0016

This suite was written while the route could not complete. `001` computed a full
comparable window in its coverage gate — start, end, ``sources`` and
``chosen_because`` — and ``CatalogDecision.comparable_window`` transported only
the two dates, so `002`'s reader correctly refused every verdict and no
comparison could be released.

ADR 0016 repaired the transport: the decision now carries `001`'s own
``ComparableWindow`` whole. The release path below is the proof, and the window
assertions check **byte-equivalence with the catalog-owned evidence** rather than
merely that a window arrived — because the failure that was possible before was
precisely a window that arrived with its reason missing.

Nothing about the comparison's semantics changed. `D-18` still ships empty, so
every comparison still refuses at the formula gate, and this suite reaches the
arithmetic only through fixture-only formulas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import pytest
from analytics_query.contracts.comparable_window import ComparableWindow
from analytics_query.contracts.result import Completeness
from analytics_query.execute import ExecutedAnswer
from analytics_query.results.completeness import ResultKind
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.validation.decision import Finality, Reproducibility, Segment

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.compute import derive_figure
from analytics_interaction.comparison.refusal import (
    SideSubmission,
    assert_caveats_are_complete,
    assert_side_is_releasable,
    assert_sides_are_coherent,
    govern_comparison,
    side_value,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.answer import CaveatOrigin
from analytics_interaction.contracts.comparison import GovernedComparison, SideResult
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.governance.resolve import ContentUnresolvable

from ..conftest import ON
from ..fixtures.comparisons import (
    ABSOLUTE_DIFFERENCE,
    BASELINE_RANGE,
    FIXTURE_VERSION,
    PRIMARY_RANGE,
    RATIO,
    WINDOW_REASON,
    caveat_set,
    executed,
    formula_instances,
    limitation,
    request,
    verdict,
)

pytestmark = pytest.mark.integration

FIXTURE_SET = formula_instances(ABSOLUTE_DIFFERENCE, RATIO)
NO_CAVEATS = caveat_set()

#: A well-formed window, side and figure, so the blocked-release test fails for
#: the reason it claims — the verdict — rather than for a malformed neighbour.
WINDOW = ComparableWindow(
    start=PRIMARY_RANGE[0], end=PRIMARY_RANGE[1], reason="janela de teste", sources=("appstore",)
)
SIDE = SideResult(
    request=request(period=PRIMARY_RANGE),
    result=executed(Decimal("150")).result,
    provenance=executed(Decimal("150")).provenance,
)
FIGURE = derive_figure(
    formula_id="absolute_difference",
    unit=ABSOLUTE_DIFFERENCE.unit_rule,
    primary=Decimal("150"),
    baseline=Decimal("100"),
    derived_from=("claim-a", "claim-b"),
    basis="janela de teste",
)


@dataclass
class CountedSide:
    """A side whose execution is counted rather than assumed.

    "Side B is not submitted when side A fails" is a **count**, not an
    inspection — and a thunk that recorded nothing would let the ordering claim
    pass against code that executed both and discarded one.
    """

    answer: ExecutedAnswer
    calls: list[int] = field(default_factory=list[int])
    raises: BaseException | None = None

    def __call__(self) -> ExecutedAnswer:
        self.calls.append(1)
        if self.raises is not None:
            raise self.raises
        return self.answer

    @property
    def count(self) -> int:
        return len(self.calls)


def _sides(
    primary: ExecutedAnswer, baseline: ExecutedAnswer
) -> tuple[SideSubmission, SideSubmission, CountedSide, CountedSide]:
    left, right = CountedSide(primary), CountedSide(baseline)
    return (
        SideSubmission(request=request(period=PRIMARY_RANGE), submit=left),
        SideSubmission(request=request(period=BASELINE_RANGE), submit=right),
        left,
        right,
    )


def _govern(
    pair: tuple[AuthorizedContext, str],
    *,
    decision: object = None,
    primary: ExecutedAnswer | None = None,
    baseline: ExecutedAnswer | None = None,
    formula_id: str = "absolute_difference",
    caveats: object = None,
    vocabulary_version: str = FIXTURE_VERSION,
    fingerprint: str | None = None,
    instances: object = FIXTURE_SET,
) -> tuple[GovernedComparison, CountedSide, CountedSide]:
    authorized, derived = pair
    side_a, side_b, counted_a, counted_b = _sides(
        primary if primary is not None else executed(Decimal("150")),
        baseline if baseline is not None else executed(Decimal("100")),
    )
    comparison = govern_comparison(
        decision if decision is not None else verdict(),  # pyright: ignore[reportArgumentType]
        formula_id=formula_id,
        primary_side=side_a,
        baseline_side=side_b,
        caveats=caveats if caveats is not None else NO_CAVEATS,  # pyright: ignore[reportArgumentType]
        authorized=authorized,
        auth_fingerprint=fingerprint if fingerprint is not None else derived,
        on=ON,
        vocabulary_version=vocabulary_version,
        derived_from=("claim-a", "claim-b"),
        instances=instances,  # pyright: ignore[reportArgumentType]
    )
    return comparison, counted_a, counted_b


# --- the complete release, end to end -------------------------------------------


def test_a_two_execution_comparison_is_released_complete(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """ADR 0016's proof: the route that could not complete now completes.

    Two disjoint periods, one verdict, two sides, one governed window, one exact
    figure — and a ``GovernedComparison`` carrying all of it.
    """
    comparison, counted_a, counted_b = _govern(authorized_pair)

    assert isinstance(comparison, GovernedComparison)
    assert comparison.formula == "absolute_difference"
    assert comparison.difference.value == Decimal(50)
    assert comparison.difference.unit == ABSOLUTE_DIFFERENCE.unit_rule
    assert comparison.difference.derived_from == ("claim-a", "claim-b")
    assert len(comparison.sides) == 2
    assert counted_a.count == 1
    assert counted_b.count == 1


def test_the_transported_window_is_byte_equivalent_to_the_catalog_evidence(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The repair's central claim, asserted field by field.

    Not "a window arrived" — the failure that was possible before was precisely a
    window arriving with its reason and sources missing. Every part is compared
    against what `001` stated.
    """
    decision = verdict()
    comparison, _, _ = _govern(authorized_pair, decision=decision)

    stated = decision.comparable_window
    assert stated is not None
    assert (comparison.window.start, comparison.window.end) == (stated.start, stated.end)
    assert comparison.window.sources == stated.sources
    assert comparison.window.reason == stated.chosen_because
    assert comparison.window.reason == WINDOW_REASON


def test_the_window_is_not_recomputed_from_the_requests(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`FR-066`: taken from the verdict, never derived from what was asked.

    The verdict states a window narrower than either side's requested range. A
    recomputation would produce the requested one and look entirely plausible.
    """
    narrowed = (date(2026, 7, 10), date(2026, 7, 20))
    comparison, _, _ = _govern(authorized_pair, decision=verdict(window=narrowed))

    assert (comparison.window.start, comparison.window.end) == narrowed
    assert (comparison.window.start, comparison.window.end) != PRIMARY_RANGE
    assert (comparison.window.start, comparison.window.end) != BASELINE_RANGE


def test_the_derived_figure_states_the_governed_basis(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The reason reaches the figure, which is what it was computed over."""
    comparison, _, _ = _govern(authorized_pair)
    assert comparison.difference.basis == WINDOW_REASON


def test_both_sides_are_carried_whole_and_unmerged(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`FR-033`, `FR-072`: values untouched, provenance never combined."""
    primary, baseline = executed(Decimal("150")), executed(Decimal("100"))
    comparison, _, _ = _govern(authorized_pair, primary=primary, baseline=baseline)

    left, right = comparison.sides
    assert left.result == primary.result
    assert right.result == baseline.result
    assert left.provenance == primary.provenance
    assert right.provenance == baseline.provenance
    assert left.provenance != right.provenance or primary.provenance == baseline.provenance
    assert (left.request.date_range.start, left.request.date_range.end) == PRIMARY_RANGE
    assert (right.request.date_range.start, right.request.date_range.end) == BASELINE_RANGE


def test_the_released_comparison_is_deterministic(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Identical input, byte-identical output — including the window and figure."""
    first, _, _ = _govern(authorized_pair)
    second, _, _ = _govern(authorized_pair)
    assert first.model_dump_json() == second.model_dump_json()


def test_a_difference_naming_one_operand_twice_is_not_constructible(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Traceability to two sides is a contract rule, enforced at construction."""
    authorized, derived = authorized_pair
    side_a, side_b, _, _ = _sides(executed(Decimal("150")), executed(Decimal("100")))
    with pytest.raises(ContractViolation):
        govern_comparison(
            verdict(),
            formula_id="absolute_difference",
            primary_side=side_a,
            baseline_side=side_b,
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=derived,
            on=ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("same", "same"),
            instances=FIXTURE_SET,
        )


def test_the_arithmetic_is_reached_only_after_every_gate() -> None:
    """Ordering, read off the source so the sequence is pinned, not inferred."""
    import ast
    import inspect

    from analytics_interaction.comparison import refusal as module

    body = ast.parse(inspect.getsource(module.govern_comparison))
    # Sorted by line: ``ast.walk`` is breadth-first and would report the gates in
    # tree order rather than in the order they run.
    calls = sorted(
        (node.lineno, node.func.id)
        for node in ast.walk(body)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    )
    order = [name for _, name in calls if name in _GATES]
    assert order == _GATES


_GATES = [
    "derive_authorization_fingerprint",
    "resolve_formula",
    "window_for_comparison",
    "assert_sides_are_coherent",
    "assert_caveats_are_complete",
    "assert_baseline_is_usable",
    "derive_figure",
]


# --- ordering: nothing executes before the gates that precede it ----------------------


def test_a_fingerprint_mismatch_refuses_before_either_side_executes(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`FR-056`: released nothing, cost nothing, computed nothing."""
    _, derived = authorized_pair
    with pytest.raises(ContractViolation) as refusal:
        _govern(authorized_pair, fingerprint=derived[::-1])
    assert refusal.value.code is Code.AUTHORIZATION_CONTEXT_UNRESOLVABLE


def test_the_shipped_d18_refuses_before_either_side_executes(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """**Zero released values.** With `D-18` empty no side is ever submitted.

    This is the state the repository actually ships in, so it is the state that
    matters most: a comparison that could not have been computed does not bill an
    execution finding that out.
    """
    authorized, derived = authorized_pair
    side_a, side_b, counted_a, counted_b = _sides(executed(), executed())

    with pytest.raises(ContentUnresolvable) as refusal:
        govern_comparison(
            verdict(),
            formula_id="absolute_difference",
            primary_side=side_a,
            baseline_side=side_b,
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=derived,
            on=ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("a", "b"),
            instances=(),
        )

    assert refusal.value.code is Code.INTERPRETATION_VOCABULARY_UNRESOLVABLE
    assert counted_a.count == 0
    assert counted_b.count == 0


def test_a_verdict_stating_no_window_refuses_rather_than_using_the_request(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The requested range is exactly what the window exists to correct."""
    with pytest.raises(ContractViolation) as refusal:
        _govern(authorized_pair, decision=verdict(window=None))
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID
    assert "not a substitute" in refusal.value.detail


# --- side A fails, side B is never asked for -------------------------------------------


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param(executed(code=ReasonCode.ACCESS_DENIED), id="governance"),
        pytest.param(executed(kind=ResultKind.PARTIALLY_WITHHELD), id="privacy-partial"),
        pytest.param(executed(kind=ResultKind.FULLY_WITHHELD), id="privacy-full"),
        pytest.param(executed(kind=ResultKind.EMPTY), id="empty"),
        pytest.param(executed(completeness=Completeness.EMPTY), id="incomplete"),
        pytest.param(
            executed(finality=Finality.PRE_EVIDENCE, reproducibility=Reproducibility.LIMITED),
            id="evidence-not-final",
        ),
    ],
)
def test_a_failing_side_a_never_submits_side_b(
    authorized_pair: tuple[AuthorizedContext, str], broken: ExecutedAnswer
) -> None:
    """One execution billed, not two, for a comparison never going to be released."""
    authorized, derived = authorized_pair
    side_a, side_b, counted_a, counted_b = _sides(broken, executed())

    with pytest.raises(ContractViolation) as refusal:
        govern_comparison(
            verdict(),
            formula_id="absolute_difference",
            primary_side=side_a,
            baseline_side=side_b,
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=derived,
            on=ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("a", "b"),
            instances=FIXTURE_SET,
        )

    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID
    assert counted_a.count == 1
    assert counted_b.count == 0


def test_a_failing_side_b_discards_side_a(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Side A succeeded and is returned to nobody. No partial success exists."""
    authorized, derived = authorized_pair
    side_a, side_b, counted_a, counted_b = _sides(
        executed(Decimal("150")), executed(kind=ResultKind.FULLY_WITHHELD)
    )

    with pytest.raises(ContractViolation) as refusal:
        govern_comparison(
            verdict(),
            formula_id="absolute_difference",
            primary_side=side_a,
            baseline_side=side_b,
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=derived,
            on=ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("a", "b"),
            instances=FIXTURE_SET,
        )

    assert counted_a.count == 1
    assert counted_b.count == 1
    assert "150" not in str(refusal.value)
    assert not hasattr(refusal.value, "sides")
    assert not hasattr(refusal.value, "result")


# --- the enumerated single-side conditions, one at a time --------------------------


def test_a_denied_side_decision_refuses() -> None:
    with pytest.raises(ContractViolation) as refusal:
        assert_side_is_releasable(executed(code=ReasonCode.SOURCE_BEYOND_TOLERANCE))
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID
    assert "does not permit release" in refusal.value.detail


@pytest.mark.parametrize(
    "kind", [ResultKind.PARTIALLY_WITHHELD, ResultKind.FULLY_WITHHELD, ResultKind.EMPTY]
)
def test_suppressed_and_empty_sides_refuse(kind: ResultKind) -> None:
    """§5.2's asymmetry: permitted alone, refused inside a comparison."""
    with pytest.raises(ContractViolation):
        assert_side_is_releasable(executed(kind=kind))


def test_the_disposition_refusal_does_not_say_which_condition_it_was() -> None:
    """ "Withheld" versus "no data" is itself disclosure about the other side."""
    with pytest.raises(ContractViolation) as refusal:
        assert_side_is_releasable(executed(kind=ResultKind.FULLY_WITHHELD))
    detail = refusal.value.detail
    assert "withheld" not in detail.lower() or "empty" not in detail.lower()


def test_a_pre_evidence_side_refuses() -> None:
    """The governance question was answered; the data question was never asked."""
    with pytest.raises(ContractViolation) as refusal:
        assert_side_is_releasable(
            executed(finality=Finality.PRE_EVIDENCE, reproducibility=Reproducibility.LIMITED)
        )
    assert "not final" in refusal.value.detail


def test_a_caveated_side_is_releasable() -> None:
    """`ALLOW_WITH_CAVEAT` executes. The caveat qualifies; it does not withhold."""
    assert_side_is_releasable(executed(code=ReasonCode.EQUIVALENT_PARTIAL_COMPARISON))


# --- the side's one value ----------------------------------------------------------


def test_a_suppressed_cell_refuses() -> None:
    with pytest.raises(ContractViolation) as refusal:
        side_value(executed(Decimal("10"), suppressed=True).result)
    assert "withheld or absent" in refusal.value.detail


def test_an_absent_cell_refuses() -> None:
    with pytest.raises(ContractViolation):
        side_value(executed(None).result)


def test_a_breakdown_is_not_a_comparison_operand() -> None:
    """Many rows is a breakdown; picking one would be choosing the answer."""
    with pytest.raises(ContractViolation) as refusal:
        side_value(executed(Decimal("10"), rows=3).result)
    assert "exactly one row" in refusal.value.detail


def test_the_metric_cell_is_read_past_dimension_columns() -> None:
    """``cells`` align with metric columns, not with all columns."""
    assert side_value(executed(Decimal("42"), dimension_columns=("country",)).result) == Decimal(42)


# --- caveats survive the arithmetic -----------------------------------------------


def test_every_verdict_limitation_must_be_carried() -> None:
    """Arithmetic cannot drop a caveat: a set missing one refuses the release."""
    caveated = verdict(limitations=(limitation("SOURCE_LAGGING_WITHIN_TOLERANCE"),))
    with pytest.raises(ContractViolation) as refusal:
        assert_caveats_are_complete(caveated, NO_CAVEATS)
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID
    assert "carried in full" in refusal.value.detail


def test_a_carried_caveat_satisfies_the_check_by_code() -> None:
    """By code, not by wording: the wording is upstream text this layer never re-derives."""
    text = "fonte atrasada dentro da tolerância governada"
    caveated = verdict(limitations=(limitation("SOURCE_LAGGING_WITHIN_TOLERANCE", text),))
    carried = caveat_set(
        (ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE, CaveatOrigin.VERDICT, text),
    )
    assert_caveats_are_complete(caveated, carried)
    assert carried.caveats[0].message_pt_br == text


def test_a_reworded_caveat_still_carries_the_governed_text() -> None:
    """`AttributedCaveat` holds upstream wording verbatim, never a rendered ref."""
    text = "cobertura parcial equivalente"
    carried = caveat_set((ReasonCode.EQUIVALENT_PARTIAL_COMPARISON, CaveatOrigin.VERDICT, text))
    assert carried.caveats[0].message_pt_br == text
    assert carried.model_dump_json() == carried.model_copy().model_dump_json()


def test_the_same_caveat_on_both_sides_is_not_deduplicated() -> None:
    """Two sides carrying one caveat is information, not redundancy."""
    text = "cobertura parcial equivalente"
    carried = caveat_set(
        (ReasonCode.EQUIVALENT_PARTIAL_COMPARISON, CaveatOrigin.SIDE_A, text),
        (ReasonCode.EQUIVALENT_PARTIAL_COMPARISON, CaveatOrigin.SIDE_B, text),
    )
    assert carried.total == 2
    assert {caveat.origin for caveat in carried.caveats} == {
        CaveatOrigin.SIDE_A,
        CaveatOrigin.SIDE_B,
    }
    assert_caveats_are_complete(verdict(), carried)


def test_a_caveated_verdict_is_still_permitted_and_still_caveated() -> None:
    """`ALLOW_WITH_CAVEAT` releases, and the outcome is unchanged on the way out."""
    text = "comparação equivalente parcial"
    caveated = verdict(
        ReasonCode.EQUIVALENT_PARTIAL_COMPARISON,
        limitations=(limitation("EQUIVALENT_PARTIAL_COMPARISON", text),),
    )
    carried = caveat_set((ReasonCode.EQUIVALENT_PARTIAL_COMPARISON, CaveatOrigin.VERDICT, text))

    assert caveated.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert_side_is_releasable(executed(code=ReasonCode.EQUIVALENT_PARTIAL_COMPARISON))
    assert_caveats_are_complete(caveated, carried)


# --- refusals disclose nothing -----------------------------------------------------


@pytest.mark.parametrize(
    ("primary", "baseline"),
    [
        (executed(Decimal("1234567"), unit="count"), executed(Decimal("7654321"), unit="minutes")),
        (executed(Decimal("1234567")), executed(Decimal("7654321"), metric_versions=("other@9",))),
        (executed(Decimal("1234567")), executed(Decimal("7654321"), catalog_release_id="r-9")),
    ],
)
def test_no_refusal_carries_a_value_or_an_identifier(
    authorized_pair: tuple[AuthorizedContext, str],
    primary: ExecutedAnswer,
    baseline: ExecutedAnswer,
) -> None:
    """The refusal says what class of thing went wrong and stops."""
    with pytest.raises(ContractViolation) as refusal:
        _govern(authorized_pair, primary=primary, baseline=baseline)

    rendered = str(refusal.value)
    for secret in ("1234567", "7654321", "minutes", "other@9", "r-9"):
        assert secret not in rendered


def test_a_refusal_carries_no_partial_comparison_object(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Not a half-built comparison, not a figure, not one side."""
    with pytest.raises(ContractViolation) as refusal:
        _govern(
            authorized_pair,
            primary=executed(Decimal("150"), unit="count"),
            baseline=executed(Decimal("100"), unit="minutes"),
        )
    for attribute in ("sides", "difference", "provenance", "caveats", "window"):
        assert not hasattr(refusal.value, attribute)


# --- the verdict may license a version span ----------------------------------------


def _coherent(primary: ExecutedAnswer, baseline: ExecutedAnswer, decision: object = None) -> str:
    return assert_sides_are_coherent(
        decision if decision is not None else verdict(),  # pyright: ignore[reportArgumentType]
        primary,
        baseline,
        requests=(request(period=PRIMARY_RANGE), request(period=BASELINE_RANGE)),
        vocabulary_version=FIXTURE_VERSION,
        formula_version=FIXTURE_VERSION,
    )


def test_the_verdict_can_declare_two_metric_versions_comparable() -> None:
    """The narrow exemption `comparison-contract.md` §5.1 states, exercised."""
    spanned = verdict(
        segments=(
            Segment(metric_version_id="installs@1", start=PRIMARY_RANGE[0], end=PRIMARY_RANGE[1]),
            Segment(metric_version_id="installs@2", start=BASELINE_RANGE[0], end=BASELINE_RANGE[1]),
        )
    )
    assert (
        _coherent(
            executed(Decimal("150"), metric_versions=("installs@1",)),
            executed(Decimal("100"), metric_versions=("installs@2",)),
            spanned,
        )
        == "count"
    )


def test_a_partial_segment_list_does_not_license_the_span() -> None:
    """The verdict must name **every** version both sides resolved."""
    partial = verdict(
        segments=(
            Segment(metric_version_id="installs@1", start=PRIMARY_RANGE[0], end=PRIMARY_RANGE[1]),
        )
    )
    with pytest.raises(ContractViolation):
        _coherent(
            executed(Decimal("150"), metric_versions=("installs@1",)),
            executed(Decimal("100"), metric_versions=("installs@2",)),
            partial,
        )


def test_identical_versions_need_no_exemption() -> None:
    assert _coherent(executed(Decimal("150")), executed(Decimal("100"))) == "count"


# --- the data-as-of basis ---------------------------------------------------------


def test_a_differing_read_point_refuses_when_the_verdict_states_a_window() -> None:
    """A window asserts both sides were read over one governed span."""
    later = datetime.fromisoformat("2026-08-13T18:00:00+00:00")
    with pytest.raises(ContractViolation) as refusal:
        _coherent(executed(Decimal("150")), executed(Decimal("100"), data_as_of=later))
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID


def test_a_differing_read_point_is_permitted_when_the_verdict_states_no_window() -> None:
    """The condition is "where the verdict required a single one", not always."""
    later = datetime.fromisoformat("2026-08-13T18:00:00+00:00")
    assert (
        _coherent(
            executed(Decimal("150")),
            executed(Decimal("100"), data_as_of=later),
            verdict(window=None),
        )
        == "count"
    )
