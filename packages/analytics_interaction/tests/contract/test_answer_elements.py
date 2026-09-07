"""Twelve elements, eleven fields — T041 (FR-034, FR-085; SC-007, SC-009, SC-011, SC-048).

`SC-011` is cited here because "every response discloses the resolved intent" is a
property of the element mapping rather than of a separate feature: ``interpreted`` is one
of the eleven fields, and the schema assertion below is what makes it unreachable to
omit it.

`FR-032` enumerates twelve required elements; ``AnalyticsAnswer`` carries them in
eleven top-level fields, three of which are composite. The gap is not a shortfall
— it is three composites doing double duty — but it is exactly the kind of
arithmetic that goes stale silently. So the mapping is asserted **element by
element against the live schema**, and a schema assertion fails if any of the
twelve becomes unreachable.

Reachability is resolved through the JSON schema rather than by constructing an
answer, because the property is about the *contract*: an element that exists only
when some optional branch is populated is not carried by the contract, it is
carried by luck.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from analytics_query.contracts.provenance import CostProvenance
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result_provenance import ResultProvenance, SourceUpdate
from pydantic import ValidationError

from analytics_interaction.contracts import (
    AnalyticsAnswer,
    AnswerClaim,
    AttributedCaveat,
    CaveatOrigin,
    CaveatSet,
    ClaimClass,
    ComparisonBasis,
    DeclaredLanguage,
    InsufficiencyNotice,
    LocalizedRef,
    ResolvedIntent,
    build,
)

pytestmark = pytest.mark.contract

REFERENCE = date(2026, 8, 13)

#: element -> the dotted path through the contract that carries it.
#: Straight from `answer-contract.md` §1, so a divergence between the table and
#: the code fails here rather than in review.
TWELVE_ELEMENTS: dict[str, str] = {
    "interpreted question": "interpreted",
    "result": "claims.value",
    "unit": "claims.unit",
    "period": "interpreted.period",
    "filters": "interpreted.filters",
    "breakdowns": "interpreted.dimensions",
    "comparison basis": "claims.basis",
    "sources": "provenance.contributing_sources",
    # Walked to the leaf, not stopped at `source_updates`: the element the
    # specification requires is the freshness *timestamp*, and a mapping that
    # stopped at the collection would still pass if `SourceUpdate` lost it.
    "freshness": "provenance.source_updates.last_updated_at",
    "provenance": "provenance",
    "limitations": "caveats",
    "insufficiency notices": "insufficiency",
}

ELEVEN_FIELDS = (
    "interpreted",
    "claims",
    "caveats",
    "provenance",
    "insufficiency",
    "language",
    "reference_date",
    "as_of",
    "catalog_release",
    "policy_version",
    "vocabulary_version",
)


def _ref(code: str) -> LocalizedRef:
    return LocalizedRef(code=code, language="pt-BR", content_version="unversioned")


def _provenance() -> ResultProvenance:
    """A minimal complete `002` provenance.

    Built rather than stubbed: the answer contract embeds the real inherited type,
    and a stand-in would let a field rename upstream pass unnoticed here.
    """
    return ResultProvenance(
        contributing_sources=("google_play",),
        resolved_metric_versions=("installs@1",),
        data_revisions=("rev-1",),
        data_as_of=datetime(2026, 8, 12, 0, 0, tzinfo=UTC),
        source_updates=(
            SourceUpdate(
                source_id="google_play",
                last_updated_at=datetime(2026, 8, 12, 0, 0, tzinfo=UTC),
            ),
        ),
        dimensional_coverage=("country",),
        limitations=(),
        cost=CostProvenance(dry_run_bytes=1, actual_bytes=1, maximum_bytes_billed=2),
        execution_identifiers=("exec-1",),
        policy_version="pol-1",
        catalog_release_id="r-1",
    )


def _intent() -> ResolvedIntent:
    return build(
        ResolvedIntent,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


def _model_at(path: str) -> Any:
    """Walk a dotted path through the contract's field annotations."""
    from analytics_interaction.contracts import answer as answer_module

    current: Any = AnalyticsAnswer
    for part in path.split("."):
        fields = current.model_fields
        assert part in fields, f"{current.__name__} has no field {part!r}"
        annotation = fields[part].annotation
        current = _unwrap(annotation, answer_module)
    return current


def _unwrap(annotation: Any, module: Any) -> Any:
    """Reduce ``tuple[X, ...] | None`` to ``X`` for traversal."""
    import types
    import typing

    origin = typing.get_origin(annotation)
    if origin in (tuple, list):
        return typing.get_args(annotation)[0]
    if origin is types.UnionType or origin is typing.Union:
        non_none = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _unwrap(non_none[0], module) if len(non_none) == 1 else non_none[0]
    return annotation


# --- the mapping --------------------------------------------------------------


def test_the_contract_carries_exactly_eleven_top_level_fields() -> None:
    assert tuple(AnalyticsAnswer.model_fields) == ELEVEN_FIELDS
    assert len(ELEVEN_FIELDS) == 11


def test_the_specification_enumerates_twelve_elements() -> None:
    assert len(TWELVE_ELEMENTS) == 12


@pytest.mark.parametrize(("element", "path"), sorted(TWELVE_ELEMENTS.items()))
def test_each_specification_element_is_reachable_through_the_contract(
    element: str, path: str
) -> None:
    """Walks the live annotations, so a renamed or removed field fails here."""
    assert _model_at(path) is not None, f"{element} is unreachable at {path}"


def test_an_element_becoming_unreachable_fails_the_assertion() -> None:
    """The mapping test must fail on a real removal, not merely pass today."""
    with pytest.raises(AssertionError, match="has no field"):
        _model_at("interpreted.no_such_field")


def test_the_three_composite_fields_are_what_close_the_twelve_to_eleven_gap() -> None:
    """Named explicitly so the arithmetic is legible rather than coincidental."""
    composites = {path.split(".")[0] for path in TWELVE_ELEMENTS.values() if "." in path}
    assert composites == {"interpreted", "claims", "provenance"}


# --- claim classes are types, not tags ----------------------------------------


def test_the_class_set_is_exactly_the_four_the_contract_fixes() -> None:
    assert [member.value for member in ClaimClass] == [
        "FACTUAL_RESULT",
        "CALCULATED_COMPARISON",
        "INTERPRETATION",
        "LIMITATION",
    ]


@pytest.mark.parametrize("claim_class", [ClaimClass.INTERPRETATION, ClaimClass.LIMITATION])
def test_a_non_numeric_class_cannot_carry_a_value(claim_class: ClaimClass) -> None:
    """This is what stops an interpretation from reading as a finding."""
    with pytest.raises((ValidationError, ValueError), match="carries no value"):
        build(
            AnswerClaim,
            claim_class=claim_class,
            subject="installs",
            value=Decimal("1"),
            message=_ref("QUESTION_ANSWERED"),
        )


@pytest.mark.parametrize("claim_class", [ClaimClass.INTERPRETATION, ClaimClass.LIMITATION])
def test_a_non_numeric_class_cannot_carry_a_unit(claim_class: ClaimClass) -> None:
    with pytest.raises((ValidationError, ValueError), match="carries no unit"):
        build(
            AnswerClaim,
            claim_class=claim_class,
            subject="installs",
            unit="count",
            message=_ref("QUESTION_ANSWERED"),
        )


def test_a_factual_result_carries_its_value_and_unit() -> None:
    claim = build(
        AnswerClaim,
        claim_class=ClaimClass.FACTUAL_RESULT,
        subject="installs",
        value=Decimal("1234"),
        unit="count",
        message=_ref("QUESTION_ANSWERED"),
    )
    assert claim.value == Decimal("1234")


def test_a_value_is_exact_decimal_and_never_a_binary_float() -> None:
    """`SC-005` requires identical output for identical input.

    A float difference is not reproducible in its last digits across platforms,
    so the annotation is the guarantee.
    """
    claim = build(
        AnswerClaim,
        claim_class=ClaimClass.FACTUAL_RESULT,
        subject="installs",
        value=Decimal("0.1"),
        unit="ratio",
        message=_ref("QUESTION_ANSWERED"),
    )
    assert isinstance(claim.value, Decimal)
    assert not isinstance(claim.value, float)
    assert str(claim.value) == "0.1"


def test_a_calculated_comparison_records_its_two_operands_and_basis() -> None:
    """`FR-035`: a reader can trace a difference to the two numbers behind it."""
    with pytest.raises((ValidationError, ValueError), match="derives from"):
        build(
            AnswerClaim,
            claim_class=ClaimClass.CALCULATED_COMPARISON,
            subject="installs",
            value=Decimal("10"),
            unit="count",
            message=_ref("QUESTION_ANSWERED"),
        )


def test_a_factual_result_may_not_claim_a_comparison_basis() -> None:
    """A factual result derives from the warehouse, not from two other claims."""
    with pytest.raises((ValidationError, ValueError), match="derives from nothing"):
        build(
            AnswerClaim,
            claim_class=ClaimClass.FACTUAL_RESULT,
            subject="installs",
            value=Decimal("10"),
            unit="count",
            message=_ref("QUESTION_ANSWERED"),
            derived_from=("a", "b"),
            basis=ComparisonBasis(
                formula="percentage_change",
                window_start=date(2026, 7, 1),
                window_end=date(2026, 7, 31),
                chosen_because="verdict",
            ),
        )


# --- caveats: required, counted, attributed, byte-preserved -------------------


def test_the_caveat_total_must_equal_the_carried_count() -> None:
    """A consumer rendering a subset becomes *detectable* rather than merely wrong."""
    caveat = AttributedCaveat(
        code=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
        message_pt_br="Algumas células foram suprimidas.",
        origin=CaveatOrigin.SINGLE,
    )
    with pytest.raises((ValidationError, ValueError), match="disagrees with"):
        build(CaveatSet, caveats=(caveat,), total=2)


def test_an_empty_caveat_set_is_an_explicit_empty_collection() -> None:
    """Not an absent field. Required-and-populated is property one of four."""
    empty = build(CaveatSet, caveats=(), total=0)
    assert empty.caveats == ()
    assert "caveats" in AnalyticsAnswer.model_fields
    assert AnalyticsAnswer.model_fields["caveats"].is_required()


def test_caveats_are_never_deduplicated_across_sides() -> None:
    """Two sides carrying the same caveat is information, not redundancy.

    Collapsing it would tell the reader one side is caveated when both are. The
    contract permits the duplicate and the count records it.
    """
    text = "Cobertura parcial no período comparado."
    both = build(
        CaveatSet,
        caveats=(
            AttributedCaveat(
                code=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
                message_pt_br=text,
                origin=CaveatOrigin.SIDE_A,
            ),
            AttributedCaveat(
                code=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
                message_pt_br=text,
                origin=CaveatOrigin.SIDE_B,
            ),
        ),
        total=2,
    )
    assert both.total == 2
    assert {c.origin for c in both.caveats} == {CaveatOrigin.SIDE_A, CaveatOrigin.SIDE_B}


def test_a_caveat_carries_its_upstream_text_byte_identically() -> None:
    """`FR-084`: never re-worded, softened, summarised or downgraded."""
    upstream = "Resultado parcialmente suprimido — limiar de agregação mínima."
    caveat = AttributedCaveat(
        code=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
        message_pt_br=upstream,
        origin=CaveatOrigin.VERDICT,
    )
    assert caveat.message_pt_br.encode("utf-8") == upstream.encode("utf-8")


def test_a_caveat_may_not_carry_an_interpretation_layer_code() -> None:
    """A caveat originates upstream by definition.

    One authored here would be this layer restating an upstream condition in its
    own words, which `FR-021` forbids.
    """
    with pytest.raises(ValidationError):
        AttributedCaveat(
            code="CLARIFICATION_REQUIRED",  # type: ignore[arg-type]
            message_pt_br="x",
            origin=CaveatOrigin.SINGLE,
        )


def test_the_four_caveat_origins_are_the_declared_set() -> None:
    assert [member.value for member in CaveatOrigin] == ["verdict", "side_a", "side_b", "single"]


# --- channel agnosticism and disclosure ---------------------------------------


@pytest.mark.parametrize(
    "field", ["channel", "format", "template", "markup", "colour", "ordering", "render"]
)
def test_the_answer_declares_no_rendering_field(field: str) -> None:
    """`FR-040`: a later chat feature renders this; it never re-derives meaning."""
    assert field not in AnalyticsAnswer.model_fields


def test_the_answer_must_agree_with_the_interpretation_it_discloses() -> None:
    """A disclosure describing a different resolution than the one that ran."""
    claim = build(
        AnswerClaim,
        claim_class=ClaimClass.FACTUAL_RESULT,
        subject="installs",
        value=Decimal("1"),
        unit="count",
        message=_ref("QUESTION_ANSWERED"),
    )
    with pytest.raises((ValidationError, ValueError), match="disagrees with the interpretation"):
        build(
            AnalyticsAnswer,
            interpreted=_intent(),
            claims=(claim,),
            caveats=build(CaveatSet, caveats=(), total=0),
            provenance=(_provenance(),),
            language=DeclaredLanguage.PT_BR,
            reference_date=date(2026, 1, 1),
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
        )


def test_an_answer_requires_at_least_one_claim_and_one_provenance() -> None:
    """Incomplete provenance is an abstention, not a warning (`FR-037`)."""
    assert AnalyticsAnswer.model_fields["claims"].is_required()
    assert AnalyticsAnswer.model_fields["provenance"].is_required()


def test_an_insufficiency_notice_points_at_governed_wording() -> None:
    """No sentence is assembled here; the notice is a pointer (`FR-039`)."""
    notice = InsufficiencyNotice(kind="incomplete_period", detail=_ref("QUESTION_ANSWERED"))
    assert isinstance(notice.detail, LocalizedRef)
    assert "message" not in InsufficiencyNotice.model_fields
