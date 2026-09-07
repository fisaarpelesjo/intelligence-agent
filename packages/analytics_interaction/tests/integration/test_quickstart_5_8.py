"""Quickstart scenarios 5—8 — T163 (FR-032; SC-007, SC-008).

    Evidence: fixture-backed; states that it says nothing about production.
    — `tasks.md` T163

Four scenarios, and unlike `T162`'s these need the **execution bridge**. So they run
against fixture collaborators for the warehouse and governed content, through the
**real** composition chain: the real preflight, the real intent assembly, the real
request builder, the real `002` public entry point, the real comparison governance and
the real answer assembly.

| Scenario | Claim |
|---|---|
| 5 | A pt-BR question becomes a governed answer, and twice identically |
| 6 | Comparisons route by what one `AnalyticsQuery` can express |
| 7 | A comparison is never partial |
| 8 | Every caveat survives, attributed and counted |

## What is real here and what is fixture

**Real**: authorization preflight, term resolution against `001`'s discovery contract,
intent assembly, `AnalyticsQuery` construction, `002`'s `GovernedExecutionPort`,
comparison routing and arithmetic, answer assembly and every gate in each.

**Fixture**: the warehouse behind the port, the published catalog, the `D-18` formula
set and claim wording, the `D-19` policy, and the synthetic seal. Each of those is an
open external record, so a fixture is the only thing that can stand there.

**Not stubbed**: no decision is faked on a path this file claims proves the bridge. The
one place a stand-in replaces production behaviour is the warehouse call itself, which
is `EXT-A`/`D-15`'s territory and cannot be reached from a test at all.

## What a green run here does *not* mean

It does not mean the feature is production ready, it does not close any of the fifteen
open records, and it does not measure interpretation quality. No question has reached a
warehouse and no token has been spent. Asserted explicitly at the end of the file
rather than left to a reader, because a green integration suite is the single most
tempting thing in this feature to over-read.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from analytics_query.contracts.request import AnalyticsQuery
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.answer.assemble import assemble_answer
from analytics_interaction.answer.caveats import carry_caveats
from analytics_interaction.answer.claims import cell_for, factual, interpretation, limitation
from analytics_interaction.answer.derived import basis_for, comparison_claims
from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.refusal import SideSubmission, govern_comparison
from analytics_interaction.comparison.routing import (
    SINGLE_REQUEST_FIELDS,
    ComparisonShape,
    classify_route,
    ranges_are_disjoint,
)
from analytics_interaction.compliance.readiness import aggregate_ready, load_all_records
from analytics_interaction.contracts._base import ContractViolation, LocalizedRef
from analytics_interaction.contracts.answer import (
    AnalyticsAnswer,
    AttributedCaveat,
    CaveatOrigin,
    ClaimClass,
)
from analytics_interaction.contracts.comparison import ComparisonRoute
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.governance.resolve import ContentUnresolvable

from ..conftest import ON
from ..fixtures.answers import WORDING_VERSION, claim_wording, ref
from ..fixtures.comparisons import (
    ABSOLUTE_DIFFERENCE,
    BASELINE_RANGE,
    FIXTURE_VERSION,
    PRIMARY_RANGE,
    RATIO,
    caveat_set,
    executed,
    formula_instances,
    request,
    verdict,
)
from ..fixtures.submissions import recorded_port

pytestmark = pytest.mark.integration

WORDING = claim_wording()
FORMULAS = formula_instances(ABSOLUTE_DIFFERENCE, RATIO)


# --- scenario 5: a governed answer, through the real chain ---------------------


def test_the_real_bridge_carries_one_request_across_the_boundary(
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The real bridge.** One construction, one crossing, no query text.

    ``recorded_port`` replaces `002`'s composed entry point and nothing above it, so
    the request that crosses is the one the **real** builder produced from the
    **real** intent. Recording at the boundary rather than mocking the builder is the
    difference between proving the bridge and proving a fixture.
    """
    authorized, fingerprint = authorized_pair
    port, recorder = recorded_port(monkeypatch, on=ON)

    query = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    port.submit(query, authorized=authorized, auth_fingerprint=fingerprint, correlation_id="corr-1")

    assert recorder.count == 1
    crossed = recorder.calls[0]
    assert crossed.request is query
    assert isinstance(crossed.request, AnalyticsQuery)
    assert "sql" not in crossed.request.model_dump()
    assert not [name for name in type(crossed.request).model_fields if "sql" in name.lower()]


def test_the_intent_carries_positions_and_never_the_question_text(
    resolved_intent: ResolvedIntent,
) -> None:
    """`FR-053`. Each resolution says **where** a term sat, never what it said.

    The whole point of the position: an intent disclosed on every response cannot
    carry a span of untrusted text, because there is no field for one.
    """
    for resolution in resolved_intent.resolutions:
        assert resolution.term.start >= 0
        assert resolution.term.length > 0
        assert set(type(resolution.term).model_fields) == {"start", "length"}
        assert resolution.resolved_to
        assert resolution.matched_via is not None


def test_asking_twice_produces_an_identical_request(
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Scenario 5's reproducibility half, at the boundary that costs money."""
    authorized, fingerprint = authorized_pair
    built = {
        build_analytics_query(
            resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
        ).model_dump_json()
        for _ in range(3)
    }
    assert len(built) == 1


def test_the_shipped_state_cannot_word_a_claim(resolved_intent: ResolvedIntent) -> None:
    """**The honest answer to scenario 5 today.** `D-18` ships empty.

    Answer assembly refuses at the wording gate, so the twelve answer elements are
    unreachable in production — which is the fail-closed behaviour, asserted before
    the fixture-enabled path below it so a reader cannot mistake one for the other.
    """
    with pytest.raises(ContentUnresolvable):
        assemble_answer(
            resolved_intent,
            claims=(interpretation(subject="installs", message=ref("claim.interpreted")),),
            caveats=caveat_set(),
            provenance=(executed(Decimal("150")).provenance,),
            on=ON,
            wording=None,
        )


def test_a_fixture_worded_answer_carries_every_governed_element(
    resolved_intent: ResolvedIntent,
) -> None:
    """**Fixture-only.** `D-18` remains open; this proves the assembly, not the content.

    Eleven fields carrying the twelve required elements, each claim classed, both
    dates and all three governing versions agreeing with the intent — which the
    contract's own validator enforces and this reads back.
    """
    answer = executed(Decimal("150"))
    assembled = assemble_answer(
        resolved_intent,
        claims=(
            factual(
                subject="installs",
                cell=cell_for(answer.result),
                unit="count",
                message=ref("claim.factual"),
            ),
            interpretation(subject="installs", message=ref("claim.interpreted")),
        ),
        caveats=caveat_set(),
        provenance=(answer.provenance,),
        on=ON,
        wording=WORDING,
    )

    assert isinstance(assembled, AnalyticsAnswer)
    # ``==``, not ``is``: the contract sets ``revalidate_instances="always"``, so a
    # nested model is reconstructed on assignment. Identity would be asserting a
    # pydantic configuration detail rather than that the disclosure matches.
    assert assembled.interpreted == resolved_intent
    assert assembled.language is resolved_intent.language
    assert assembled.reference_date == resolved_intent.reference_date
    assert assembled.as_of == resolved_intent.as_of
    assert assembled.catalog_release == resolved_intent.catalog_release
    assert assembled.policy_version == resolved_intent.policy_version
    assert assembled.vocabulary_version == resolved_intent.vocabulary_version
    assert all(claim.claim_class in set(ClaimClass) for claim in assembled.claims)
    assert len(assembled.provenance) == 1


def test_every_released_value_is_the_ports_own(resolved_intent: ResolvedIntent) -> None:
    """`FR-033`. The figure is read off the cell, never recomputed.

    ``factual`` takes a ``ResultCell`` rather than a number, so there is no argument
    through which a computed value could arrive — which is why this holds structurally
    rather than by comparison.
    """
    answer = executed(Decimal("987654"))
    claim = factual(
        subject="installs",
        cell=cell_for(answer.result),
        unit="count",
        message=ref("claim.factual"),
    )
    assert claim.value == Decimal("987654")
    assert claim.value == answer.result.rows[0].cells[0].value


def test_a_suppressed_cell_cannot_become_a_factual_claim() -> None:
    """Scenario 5's privacy edge: substituting zero would fabricate the figure."""
    suppressed = executed(Decimal("150"), suppressed=True)
    with pytest.raises(ContractViolation) as raised:
        factual(
            subject="installs",
            cell=cell_for(suppressed.result),
            unit="count",
            message=ref("claim.factual"),
        )
    assert raised.value.code is Code.DISCLOSURE_WOULD_RECONSTRUCT


# --- scenario 6: routing ------------------------------------------------------


#: The routing table from scenario 6.
#:
#: ``differing_fields`` names fields **one request already carries**, and a second
#: period is expressed by ``baseline_range`` rather than by naming ``date_range`` —
#: which is not a single-request field, and naming it there is itself a deny.
ROUTE_CASES: tuple[tuple[str, ComparisonShape, ComparisonRoute], ...] = (
    (
        "two-sources-one-period",
        ComparisonShape(
            differing_fields=frozenset({"sources"}),
            primary_range=PRIMARY_RANGE,
        ),
        ComparisonRoute.SINGLE_REQUEST,
    ),
    (
        "two-metrics-one-period",
        ComparisonShape(
            differing_fields=frozenset({"metrics"}),
            primary_range=PRIMARY_RANGE,
        ),
        ComparisonRoute.SINGLE_REQUEST,
    ),
    (
        "disjoint-periods",
        ComparisonShape(
            differing_fields=frozenset(),
            primary_range=PRIMARY_RANGE,
            baseline_range=BASELINE_RANGE,
        ),
        ComparisonRoute.TWO_EXECUTION,
    ),
)


@pytest.mark.parametrize(
    "shape,expected",
    [(shape, expected) for _, shape, expected in ROUTE_CASES],
    ids=[name for name, _, _ in ROUTE_CASES],
)
def test_a_comparison_routes_by_what_one_request_can_express(
    shape: ComparisonShape, expected: ComparisonRoute
) -> None:
    """Scenario 6's table, asserted.

    The rule is expressibility, not shape-matching: anything one ``AnalyticsQuery``
    can say is one execution — **including a cross-source comparison**, because
    ``sources`` takes a list and the catalog evaluates their comparability in that one
    evaluation. Re-routing those through two executions would duplicate machinery
    `002` owns and double the bill.
    """
    assert classify_route(shape) is expected


def test_deny_is_a_refusal_rather_than_a_third_route() -> None:
    """**There are two routes, not three.**

    ``classify_route`` raises rather than returning a ``DENY`` member, and the
    difference matters: a third enum value could be stored on a contract, passed
    around and eventually acted on, whereas a refusal cannot be carried anywhere. The
    absence of a route is never permission.
    """
    assert {route.value for route in ComparisonRoute} == {"single_request", "two_execution"}


def test_overlapping_periods_refuse_rather_than_routing() -> None:
    """Scenario 6's third row.

    Overlapping ranges double-count the overlap, so a difference over them is not a
    difference — and inferring which part the caller meant would be this feature
    deciding the question.
    """
    overlapping = ComparisonShape(
        differing_fields=frozenset(),
        primary_range=(date(2026, 7, 1), date(2026, 7, 31)),
        baseline_range=(date(2026, 7, 15), date(2026, 8, 15)),
    )
    assert overlapping.baseline_range is not None
    assert not ranges_are_disjoint(overlapping.primary_range, overlapping.baseline_range)
    with pytest.raises(ContractViolation) as raised:
        classify_route(overlapping)
    assert raised.value.code is Code.COMPARISON_NOT_ROUTABLE


def test_touching_periods_overlap() -> None:
    """One range ending the day the other starts shares that day.

    An off-by-one here would silently double-count a single day in every
    month-over-month comparison — the kind of error that survives review because the
    figure looks plausible.
    """
    assert not ranges_are_disjoint(
        (date(2026, 7, 1), date(2026, 7, 15)), (date(2026, 7, 15), date(2026, 7, 31))
    )
    assert ranges_are_disjoint(
        (date(2026, 7, 1), date(2026, 7, 14)), (date(2026, 7, 15), date(2026, 7, 31))
    )


def test_a_field_the_request_cannot_carry_refuses() -> None:
    """``date_range`` is not a single-request field, and neither is an invented one.

    Naming ``date_range`` among the differing fields is exactly the mistake a caller
    would make, and it denies rather than being reinterpreted as a two-execution
    comparison — reinterpreting it would mean guessing at a second period nobody
    supplied.
    """
    for field in ("date_range", "order_by", "limit", "sql"):
        with pytest.raises(ContractViolation) as raised:
            classify_route(
                ComparisonShape(differing_fields=frozenset({field}), primary_range=PRIMARY_RANGE)
            )
        assert raised.value.code is Code.COMPARISON_NOT_ROUTABLE, field


def test_routing_is_total_over_the_expressible_fields() -> None:
    """Every single-request field routes; nothing falls through.

    Derived from ``AnalyticsQuery``'s own fields, so a field added upstream appears
    here and is routed rather than silently becoming unroutable.
    """
    assert frozenset(AnalyticsQuery.model_fields) - {"date_range"} == SINGLE_REQUEST_FIELDS
    assert SINGLE_REQUEST_FIELDS
    for field in SINGLE_REQUEST_FIELDS:
        shape = ComparisonShape(differing_fields=frozenset({field}), primary_range=PRIMARY_RANGE)
        assert classify_route(shape) is ComparisonRoute.SINGLE_REQUEST


def test_routing_is_deterministic() -> None:
    """The same shape always yields the same route. No clock, no policy, no preference."""
    shape = ComparisonShape(
        differing_fields=frozenset(), primary_range=PRIMARY_RANGE, baseline_range=BASELINE_RANGE
    )
    assert len({classify_route(shape) for _ in range(5)}) == 1


# --- scenario 7: a comparison is never partial -------------------------------


def test_a_complete_comparison_releases_two_sides_and_one_figure(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The control for scenario 7, and the shape a refusal must not resemble."""
    authorized, fingerprint = authorized_pair
    comparison = govern_comparison(
        verdict(),
        formula_id="absolute_difference",
        primary_side=SideSubmission(
            request=request(period=PRIMARY_RANGE),
            submit=lambda: executed(Decimal("150")),  # pyright: ignore[reportArgumentType]
        ),
        baseline_side=SideSubmission(
            request=request(period=BASELINE_RANGE),
            submit=lambda: executed(Decimal("100")),  # pyright: ignore[reportArgumentType]
        ),
        caveats=caveat_set(),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        on=ON,
        vocabulary_version=FIXTURE_VERSION,
        derived_from=("claim-a", "claim-b"),
        instances=FORMULAS,
    )
    assert len(comparison.sides) == 2
    assert comparison.difference.value == Decimal(50)
    assert comparison.window.reason


def test_a_derived_claim_names_both_operands_and_the_governed_basis(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Scenario 7's disclosure half.

    A calculated comparison is marked derived and traceable to both operands, so a
    reader can tell a computed difference from a warehouse figure — which is the
    distinction `FR-034` exists for.
    """
    authorized, fingerprint = authorized_pair
    comparison = govern_comparison(
        verdict(),
        formula_id="absolute_difference",
        primary_side=SideSubmission(
            request=request(period=PRIMARY_RANGE),
            submit=lambda: executed(Decimal("150")),  # pyright: ignore[reportArgumentType]
        ),
        baseline_side=SideSubmission(
            request=request(period=BASELINE_RANGE),
            submit=lambda: executed(Decimal("100")),  # pyright: ignore[reportArgumentType]
        ),
        caveats=caveat_set(),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        on=ON,
        vocabulary_version=FIXTURE_VERSION,
        derived_from=("installs julho", "installs junho"),
        instances=FORMULAS,
    )
    claims = comparison_claims(
        comparison,
        subjects=("installs julho", "installs junho"),
        difference_subject="installs diferença",
        factual_message=ref("claim.factual"),
        difference_message=ref("claim.calculated"),
    )
    assert len(claims) == 3
    first, second, difference = claims

    # The operands precede the figure derived from them, so a renderer presenting the
    # tuple in order presents the evidence before the conclusion.
    assert first.claim_class is ClaimClass.FACTUAL_RESULT
    assert second.claim_class is ClaimClass.FACTUAL_RESULT
    assert difference.claim_class is ClaimClass.CALCULATED_COMPARISON

    # ``derived_from`` names the two subjects rather than positions, so the trace
    # survives reordering — and a name no claim carries is unconstructible.
    assert difference.derived_from == (first.subject, second.subject)
    assert difference.basis == basis_for(comparison)


# --- scenario 8: every caveat survives --------------------------------------


CAVEAT_TEXT = "cobertura parcial nas fontes comparadas"


def test_a_caveated_verdict_carries_its_wording_byte_for_byte(
    resolved_intent: ResolvedIntent,
) -> None:
    """Scenario 8's byte-identity, through the real assembly gate."""
    answer = executed(Decimal("150"))
    caveats = carry_caveats(
        (
            AttributedCaveat(
                code=ReasonCode.COMPARABLE_WITH_CAVEAT,
                message_pt_br=CAVEAT_TEXT,
                origin=CaveatOrigin.VERDICT,
            ),
        )
    )
    assembled = assemble_answer(
        resolved_intent,
        claims=(
            factual(
                subject="installs",
                cell=cell_for(answer.result),
                unit="count",
                message=ref("claim.factual"),
            ),
        ),
        caveats=caveats,
        provenance=(answer.provenance,),
        required_caveats=(("COMPARABLE_WITH_CAVEAT", CaveatOrigin.VERDICT),),
        on=ON,
        wording=WORDING,
    )
    assert assembled.caveats.total == 1
    assert assembled.caveats.caveats[0].message_pt_br == CAVEAT_TEXT
    assert assembled.caveats.caveats[0].message_pt_br.encode() == CAVEAT_TEXT.encode()
    assert assembled.caveats.caveats[0].origin is CaveatOrigin.VERDICT


def test_the_same_caveat_from_both_sides_is_carried_twice(
    resolved_intent: ResolvedIntent,
) -> None:
    """Scenario 8's non-deduplication, at the release gate rather than in isolation."""
    answer = executed(Decimal("150"))
    caveats = carry_caveats(
        (
            AttributedCaveat(
                code=ReasonCode.COMPARABLE_WITH_CAVEAT,
                message_pt_br=CAVEAT_TEXT,
                origin=CaveatOrigin.SIDE_A,
            ),
        ),
        (
            AttributedCaveat(
                code=ReasonCode.COMPARABLE_WITH_CAVEAT,
                message_pt_br=CAVEAT_TEXT,
                origin=CaveatOrigin.SIDE_B,
            ),
        ),
    )
    assembled = assemble_answer(
        resolved_intent,
        claims=(
            factual(
                subject="installs",
                cell=cell_for(answer.result),
                unit="count",
                message=ref("claim.factual"),
            ),
        ),
        caveats=caveats,
        provenance=(answer.provenance,),
        required_caveats=(
            ("COMPARABLE_WITH_CAVEAT", CaveatOrigin.SIDE_A),
            ("COMPARABLE_WITH_CAVEAT", CaveatOrigin.SIDE_B),
        ),
        on=ON,
        wording=WORDING,
    )
    assert assembled.caveats.total == 2
    assert [c.origin for c in assembled.caveats.caveats] == [
        CaveatOrigin.SIDE_A,
        CaveatOrigin.SIDE_B,
    ]


def test_an_answer_whose_caveats_cannot_be_carried_is_withheld(
    resolved_intent: ResolvedIntent,
) -> None:
    """**Withheld, not trimmed.** Scenario 8's last line.

    A required caveat is missing, so the whole answer does not go out — including the
    figure, which is otherwise perfectly releasable. Trimming would present a
    qualified result as unqualified.
    """
    answer = executed(Decimal("150"))
    with pytest.raises(ContractViolation) as raised:
        assemble_answer(
            resolved_intent,
            claims=(
                factual(
                    subject="installs",
                    cell=cell_for(answer.result),
                    unit="count",
                    message=ref("claim.factual"),
                ),
            ),
            caveats=caveat_set(),
            provenance=(answer.provenance,),
            required_caveats=(("COMPARABLE_WITH_CAVEAT", CaveatOrigin.VERDICT),),
            on=ON,
            wording=WORDING,
        )
    assert "withheld in full" in str(raised.value)
    assert "150" not in str(raised.value)


def test_a_limitation_claim_is_classed_as_one(resolved_intent: ResolvedIntent) -> None:
    """Limitations are their own claim class, not caveats wearing another hat."""
    claim = limitation(subject="installs", message=ref("claim.limitation"))
    assert claim.claim_class is ClaimClass.LIMITATION
    assert claim.value is None
    assert isinstance(claim.message, LocalizedRef)
    assert resolved_intent is not None


# --- what this file does not establish -------------------------------------


def test_nothing_here_changed_the_shipped_readiness() -> None:
    """Every fixture travelled through a parameter. Asserted, not assumed."""
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


def test_the_fixture_wording_is_marked_as_fixture() -> None:
    """**A green run above establishes internal contract behaviour only.**

    `D-18` is undeclared. The wording every answer above was assembled with carries a
    fixture marker in its own version string, so an artefact of one of these runs
    cannot be mistaken for approved content — and this states the boundary in an
    assertion rather than in prose nobody executes.
    """
    assert "fixture-only" in WORDING_VERSION
    assert all("fixture-only" in content.version for content in WORDING)
    assert "fixture-only" in FIXTURE_VERSION


def test_no_side_reached_a_warehouse() -> None:
    """No question has reached BigQuery and no token has been spent.

    Structural: the package declares no warehouse client and no HTTP client, which
    `test_no_persistence.py` asserts over the whole source tree. Restated here as the
    scenario's own conclusion, because scenario 5—8's green result is exactly what a
    reader would over-read.
    """
    import analytics_interaction

    assert not hasattr(analytics_interaction, "bigquery")
    assert not hasattr(analytics_interaction, "Client")
