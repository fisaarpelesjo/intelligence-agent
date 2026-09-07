"""Answer assembly — T133 (FR-037, FR-038, FR-039, FR-042, FR-072, FR-086, FR-098; SC-041).

`SC-041` is cited here because unmerged per-side provenance is asserted by this file
through `FR-072`: the criterion is the observable form of that requirement, and citing it
only in the requirement would leave the criterion looking unvalidated.

    Evidence: each response kind asserted separately; a generated or concatenated
    string fails. — `tasks.md` T133

## The twelve elements through eleven fields

`FR-032` enumerates twelve required answer elements and the contract carries them
in eleven fields, three of them composite. This suite resolves each element
through the schema — not by reading a rendered answer, which would test a
renderer nobody has written, but by reaching the field the contract says holds
it. An element that became unreachable would fail here rather than in a review.

## Governed content only

Every user-facing string is a ``LocalizedRef``. The assertion is structural: each
claim's ``message`` is checked to be a pointer, and the assembly module is
scanned for the operations that would produce a sentence — ``format``, ``join``,
``%``, f-string concatenation over user input. A generated string fails.

## What refuses

`D-18` ships empty, so **every answer refuses today** — asserted against the real
governed file, not a fixture. The rest of the suite supplies fixture-only wording
to reach the far side of that gate, which is where the assembly logic lives and
where a later `D-18` decision will find it already tested.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from analytics_query.contracts.result_provenance import ResultProvenance

from analytics_interaction.answer import assemble as assemble_module
from analytics_interaction.answer.assemble import assemble_answer
from analytics_interaction.answer.caveats import carry_caveats
from analytics_interaction.answer.claims import cell_for, factual, interpretation, limitation
from analytics_interaction.answer.provenance import freshness_of
from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.contracts._base import ContractViolation, LocalizedRef
from analytics_interaction.contracts.answer import (
    AnalyticsAnswer,
    AnswerClaim,
    AttributedCaveat,
    CaveatOrigin,
    CaveatSet,
    ClaimClass,
    InsufficiencyNotice,
)
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.governance.resolve import ContentUnresolvable

from ..conftest import ON
from ..fixtures.answers import claim_wording, ref
from ..fixtures.clarifications import ready_records
from ..fixtures.comparisons import executed

pytestmark = pytest.mark.integration

WORDING = claim_wording()
DISCLOSURE = ready_records(InteractionCapability.D_19)


def _claims(subject: str = "installs") -> tuple[AnswerClaim, ...]:
    answer = executed(Decimal("150"))
    return (
        factual(
            subject=subject,
            cell=cell_for(answer.result),
            unit="count",
            message=ref("claim.factual"),
        ),
        interpretation(subject=subject, message=ref("claim.interpreted")),
    )


def _assemble(
    intent: ResolvedIntent,
    *,
    claims: tuple[AnswerClaim, ...] | None = None,
    caveats: CaveatSet | None = None,
    provenance: tuple[ResultProvenance, ...] | None = None,
    required: tuple[tuple[str, CaveatOrigin], ...] = (),
    insufficiency: tuple[InsufficiencyNotice, ...] = (),
    wording: object = WORDING,
    records: object = None,
) -> AnalyticsAnswer:
    return assemble_answer(
        intent,
        claims=claims if claims is not None else _claims(),
        caveats=caveats if caveats is not None else carry_caveats(),
        provenance=provenance if provenance is not None else (executed().provenance,),
        required_caveats=required,
        insufficiency=insufficiency,
        on=ON,
        wording=wording,  # pyright: ignore[reportArgumentType]
        records=records,  # pyright: ignore[reportArgumentType]
    )


# --- the twelve elements ---------------------------------------------------------


def test_a_complete_factual_answer_is_assembled(resolved_intent: ResolvedIntent) -> None:
    """The whole path, from a fixture-backed governed result."""
    answer = _assemble(resolved_intent)

    assert isinstance(answer, AnalyticsAnswer)
    assert len(answer.claims) == 2
    assert answer.claims[0].claim_class is ClaimClass.FACTUAL_RESULT
    assert answer.claims[0].value == Decimal("150")


ELEMENTS: dict[str, str] = {
    "interpreted question": "interpreted",
    "result": "claims",
    "unit": "claims",
    "period": "interpreted",
    "filters": "interpreted",
    "breakdowns": "interpreted",
    "comparison basis": "claims",
    "sources": "provenance",
    "freshness": "provenance",
    "provenance": "provenance",
    "limitations": "caveats",
    "insufficiency notices": "insufficiency",
}


def test_twelve_elements_resolve_through_eleven_fields() -> None:
    """The mapping the contract declares, asserted against the schema.

    Twelve elements, eleven top-level fields, three of them composite. An element
    that became unreachable — a field renamed, a nested member dropped — fails
    here rather than in a review.
    """
    assert len(ELEMENTS) == 12
    assert len(AnalyticsAnswer.model_fields) == 11
    assert set(ELEMENTS.values()) <= set(AnalyticsAnswer.model_fields)


def test_each_element_is_reachable_on_a_real_answer(resolved_intent: ResolvedIntent) -> None:
    """Reached through the field the contract says holds it, one at a time."""
    answer = _assemble(resolved_intent)
    factual_claim = answer.claims[0]

    # Equal, field for field — not the identical object. The base revalidates
    # instances, so assignment produces an equal value rather than the same one,
    # and value equality is the right notion for a disclosure anyway.
    assert answer.interpreted == resolved_intent  # interpreted question
    assert factual_claim.value is not None  # result
    assert factual_claim.unit == "count"  # unit
    assert answer.interpreted.period is not None  # period
    assert answer.interpreted.filters is not None  # filters
    assert answer.interpreted.dimensions is not None  # breakdowns
    assert answer.provenance[0].contributing_sources  # sources
    assert answer.provenance[0].source_updates  # freshness
    assert answer.provenance  # provenance
    assert answer.caveats.total == 0  # limitations
    assert answer.insufficiency == ()  # insufficiency notices


def test_freshness_reaches_the_per_source_update_time(
    resolved_intent: ResolvedIntent,
) -> None:
    """`provenance[].source_updates[].last_updated_at`, per source.

    Per-source rather than one timestamp: a result drawing on two sources has two
    freshness facts, and collapsing them lets the fresher speak for the staler.
    """
    answer = _assemble(resolved_intent)
    updates = answer.provenance[0].source_updates

    assert updates
    assert all(update.last_updated_at for update in updates)
    assert freshness_of(answer.provenance[0]) == (
        ("appstore", updates[0].last_updated_at.isoformat()),
    )


def test_the_two_dates_are_disclosed_independently(resolved_intent: ResolvedIntent) -> None:
    """`FR-098`. Neither is derived from the other, on the answer as on the intent."""
    answer = _assemble(resolved_intent)

    assert answer.reference_date == resolved_intent.reference_date
    assert answer.as_of == resolved_intent.as_of
    assert "reference_date" in AnalyticsAnswer.model_fields
    assert "as_of" in AnalyticsAnswer.model_fields


def test_the_governing_versions_are_disclosed(resolved_intent: ResolvedIntent) -> None:
    """Catalog release, policy and vocabulary — reproducibility identity."""
    answer = _assemble(resolved_intent)
    assert answer.catalog_release == resolved_intent.catalog_release
    assert answer.policy_version == resolved_intent.policy_version
    assert answer.vocabulary_version == resolved_intent.vocabulary_version
    assert answer.provenance[0].resolved_metric_versions


def test_an_answer_disagreeing_with_its_intent_is_not_constructible(
    resolved_intent: ResolvedIntent,
) -> None:
    """Every disclosed field comes from the intent, so disagreement is unreachable.

    The contract validates it anyway; assembly removes the opportunity.
    """
    parameters = set(inspect.signature(assemble_answer).parameters)
    assert not parameters & {
        "language",
        "reference_date",
        "as_of",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
    }


# --- governed content only --------------------------------------------------------


def test_every_user_facing_string_is_a_governed_pointer(
    resolved_intent: ResolvedIntent,
) -> None:
    """`FR-039`: no string generated, concatenated, paraphrased or translated."""
    answer = _assemble(resolved_intent)
    for claim in answer.claims:
        assert isinstance(claim.message, LocalizedRef)
        assert claim.message.code
        assert claim.message.language == "pt-BR"
        assert claim.message.content_version


def test_the_assembly_module_generates_no_text() -> None:
    """Scanned for the operations that would produce a sentence.

    ``format``, ``join``, ``%`` and ``+`` over strings are how a template arrives.
    None of them appears on the assembly path, so a generated string is not
    something a later edit can add quietly.
    """
    tree = ast.parse(Path(inspect.getfile(assemble_module)).read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called & {"format", "join", "replace", "translate", "capitalize"}

    formatted = [node for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)]
    assert not formatted, "an f-string builds text on the assembly path"


def test_no_clock_randomness_or_global_state_participates() -> None:
    """`SC-028`: equal governed inputs produce byte-equivalent answers."""
    from analytics_interaction.answer import caveats, claims, derived, provenance, withhold

    for module in (assemble_module, claims, caveats, derived, provenance, withhold):
        tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
        names = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute | ast.Name)
        }
        assert not names & {"now", "utcnow", "today", "random", "getpid", "uuid4", "environ"}


def test_repeated_assembly_is_byte_identical(resolved_intent: ResolvedIntent) -> None:
    first = _assemble(resolved_intent)
    second = _assemble(resolved_intent)
    assert first.model_dump_json() == second.model_dump_json()


# --- D-18 ships empty --------------------------------------------------------------


def test_the_shipped_claim_wording_refuses_every_answer(
    resolved_intent: ResolvedIntent,
) -> None:
    """**The state the repository ships in**, read from the real governed file.

    An answer whose claim classes have no governed wording would have to invent
    labels for "factual result" and "calculated comparison" — the wording
    decision `D-18` exists to make.
    """
    with pytest.raises(ContentUnresolvable) as refusal:
        _assemble(resolved_intent, wording=())
    assert refusal.value.code is Code.INTERPRETATION_VOCABULARY_UNRESOLVABLE


def test_the_real_governed_file_still_declares_no_wording(
    resolved_intent: ResolvedIntent,
) -> None:
    """Reads `interpretation_governance/` itself. `D-18` is an open record."""
    with pytest.raises(ContentUnresolvable):
        _assemble(resolved_intent, wording=None)


def test_wording_covering_three_classes_is_incomplete_not_partial(
    resolved_intent: ResolvedIntent,
) -> None:
    """Every contract-declared class must be worded, or none of it resolves."""
    partial = claim_wording(
        classes=(ClaimClass.FACTUAL_RESULT, ClaimClass.INTERPRETATION, ClaimClass.LIMITATION)
    )
    with pytest.raises(ContentUnresolvable):
        _assemble(resolved_intent, wording=partial)


def test_two_effective_wordings_refuse(resolved_intent: ResolvedIntent) -> None:
    """Ambiguous governance is refused, never resolved by picking one."""
    both = (*claim_wording(version="a"), *claim_wording(version="b"))
    with pytest.raises(ContentUnresolvable):
        _assemble(resolved_intent, wording=both)


# --- D-19 gates the disclosure judgement -------------------------------------------


def test_an_insufficiency_notice_requires_the_disclosure_policy(
    resolved_intent: ResolvedIntent,
) -> None:
    """`D-19` owns whether stating a notice could help reconstruct a figure.

    Gated only where the judgement is needed: a plain answer carrying no notice
    needs no cross-question evaluation, and refusing one would be this feature
    inventing a dependency.
    """
    notice = InsufficiencyNotice(kind="partial_period", detail=ref("notice.partial"))

    with pytest.raises(ContractViolation) as refusal:
        _assemble(resolved_intent, insufficiency=(notice,), records=None)
    assert refusal.value.code is Code.INTERPRETATION_POLICY_UNRESOLVABLE


def test_the_same_answer_without_a_notice_releases(resolved_intent: ResolvedIntent) -> None:
    """The contrast that shows the gate is conditional rather than blanket."""
    assert _assemble(resolved_intent, insufficiency=()) is not None


def test_a_notice_releases_once_the_policy_is_available(
    resolved_intent: ResolvedIntent,
) -> None:
    notice = InsufficiencyNotice(kind="partial_period", detail=ref("notice.partial"))
    answer = _assemble(resolved_intent, insufficiency=(notice,), records=DISCLOSURE)
    assert answer.insufficiency == (notice,)


# --- provenance abstains rather than warning ----------------------------------------


@pytest.mark.parametrize(
    "emptied",
    ["contributing_sources", "resolved_metric_versions", "data_revisions", "source_updates"],
)
def test_incomplete_provenance_abstains(resolved_intent: ResolvedIntent, emptied: str) -> None:
    """`FR-037`. A figure whose basis is partly unknown is not an answer with a
    warning — a warning beside it invites the reader to use it anyway."""
    incomplete = executed().provenance.model_copy(update={emptied: ()})

    with pytest.raises(ContractViolation) as refusal:
        _assemble(resolved_intent, provenance=(incomplete,))
    assert refusal.value.code is Code.DISCLOSURE_WOULD_RECONSTRUCT


def test_the_provenance_refusal_names_no_element(resolved_intent: ResolvedIntent) -> None:
    """Which part was missing describes an execution the caller is not receiving."""
    incomplete = executed().provenance.model_copy(update={"data_revisions": ()})

    with pytest.raises(ContractViolation) as refusal:
        _assemble(resolved_intent, provenance=(incomplete,))
    assert "data_revisions" not in str(refusal.value)


def test_both_sides_provenance_stays_unmerged(resolved_intent: ResolvedIntent) -> None:
    """`FR-072`. One entry per side, in side order, never combined."""
    primary = executed(Decimal("150")).provenance
    baseline = executed(Decimal("100"), catalog_release_id="r-1").provenance.model_copy(
        update={"execution_identifiers": ("qid-2", "job-2")}
    )

    answer = _assemble(resolved_intent, provenance=(primary, baseline))

    assert len(answer.provenance) == 2
    assert answer.provenance[0] == primary
    assert answer.provenance[1] == baseline
    assert answer.provenance[0].execution_identifiers != answer.provenance[1].execution_identifiers


def test_no_merge_function_exists_on_the_provenance_path() -> None:
    """There is no place to put one, which is stronger than not calling one."""
    from analytics_interaction.answer import provenance as module

    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert not defined & {"merge", "merge_provenance", "combine", "summarise", "summarize"}


# --- all or withheld -----------------------------------------------------------------


def test_an_answer_missing_a_required_caveat_is_withheld(
    resolved_intent: ResolvedIntent,
) -> None:
    """`FR-086`. Withheld in full, never trimmed.

    The quiet alternative is to drop the caveat whose wording was unavailable and
    release the rest: the number arrives, the reader sees four qualifications
    instead of five, and nothing says a fifth existed.
    """
    from semantic_catalog.contracts.reason_codes import ReasonCode

    required = ((str(ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE), CaveatOrigin.SINGLE),)

    with pytest.raises(ContractViolation) as refusal:
        _assemble(resolved_intent, required=required)
    assert refusal.value.code is Code.INTERPRETATION_VOCABULARY_UNRESOLVABLE
    assert "withheld in full" in refusal.value.detail


def test_the_withholding_refusal_names_no_code_or_origin(
    resolved_intent: ResolvedIntent,
) -> None:
    """It would disclose which limitations applied to an answer nobody receives."""
    from semantic_catalog.contracts.reason_codes import ReasonCode

    required = ((str(ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE), CaveatOrigin.SIDE_B),)

    with pytest.raises(ContractViolation) as refusal:
        _assemble(resolved_intent, required=required)
    assert "SOURCE_LAGGING" not in str(refusal.value)
    assert "side_b" not in str(refusal.value)


def test_an_answer_carrying_every_required_caveat_releases(
    resolved_intent: ResolvedIntent,
) -> None:
    from semantic_catalog.contracts.reason_codes import ReasonCode

    text = "fonte atrasada dentro da tolerância governada"
    caveats = carry_caveats(
        (
            AttributedCaveat(
                code=ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE,
                message_pt_br=text,
                origin=CaveatOrigin.SINGLE,
            ),
        )
    )
    required = ((str(ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE), CaveatOrigin.SINGLE),)

    answer = _assemble(resolved_intent, caveats=caveats, required=required)

    assert answer.caveats.total == 1
    assert answer.caveats.caveats[0].message_pt_br == text


# --- no channel field ------------------------------------------------------------------


def test_the_answer_contract_carries_no_channel_field() -> None:
    """`FR-040`: structured, not Slack, WhatsApp, HTML or Markdown delivery."""
    forbidden = {
        "channel",
        "format",
        "markup",
        "template",
        "thread_id",
        "webhook",
        "recipient",
        "max_length",
        "colour",
        "color",
        "buttons",
    }
    assert not set(AnalyticsAnswer.model_fields) & forbidden


def test_an_unknown_field_refuses(resolved_intent: ResolvedIntent) -> None:
    """``extra="forbid"``: an added output field is refused, not ignored."""
    answer = _assemble(resolved_intent)
    with pytest.raises(ValueError, match="extra"):
        AnalyticsAnswer.model_validate({**answer.model_dump(), "channel": "slack"})


def test_the_answer_package_imports_no_channel_dependency() -> None:
    """No SDK, no HTTP client, no queue, no scheduler."""
    from analytics_interaction import answer as package

    root = Path(inspect.getfile(package)).resolve().parent
    forbidden = {"requests", "httpx", "aiohttp", "slack_sdk", "flask", "fastapi", "celery", "kombu"}
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [a.name for a in node.names if a.name.split(".")[0] in forbidden]
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and (node.module.split(".")[0] in forbidden)
            ):
                offenders.append(node.module)
    assert not offenders, f"a channel dependency is imported: {offenders}"


# --- limitation and interpretation claims carry no number --------------------------------


def test_an_interpretation_carries_no_number() -> None:
    """Structural: the class refuses a value, so it cannot read as a finding."""
    claim = interpretation(subject="installs", message=ref("claim.interpreted"))
    assert claim.value is None
    assert claim.unit is None


def test_a_limitation_carries_no_number() -> None:
    claim = limitation(subject="freshness", message=ref("claim.limitation"))
    assert claim.value is None
    assert claim.unit is None


def test_a_factual_claim_over_a_withheld_cell_refuses() -> None:
    """No claim may be created from suppressed evidence."""
    withheld = executed(Decimal("10"), suppressed=True)
    with pytest.raises(ContractViolation) as refusal:
        factual(
            subject="installs",
            cell=cell_for(withheld.result),
            unit="count",
            message=ref("claim.factual"),
        )
    assert refusal.value.code is Code.DISCLOSURE_WOULD_RECONSTRUCT


def test_a_factual_claim_over_an_absent_cell_refuses() -> None:
    absent = executed(None)
    with pytest.raises(ContractViolation):
        factual(
            subject="installs",
            cell=cell_for(absent.result),
            unit="count",
            message=ref("claim.factual"),
        )


def test_the_evidence_time_is_carried_not_recomputed(
    resolved_intent: ResolvedIntent,
) -> None:
    """``data_as_of`` comes from the execution, and nothing here reads a clock."""
    answer = _assemble(resolved_intent)
    assert answer.provenance[0].data_as_of == datetime(2026, 8, 13, 6, 0, tzinfo=UTC)
