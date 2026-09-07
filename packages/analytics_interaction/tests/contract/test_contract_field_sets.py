"""Contract field sets — T040 (FR-002, FR-096, FR-097; SC-056).

Three properties, each of which is the mechanism for something else.

**Frozen and ``extra="forbid"`` on every model.** This is what makes "no query
text", "no caller-asserted access tag", "no caller-supplied governed limit" and
"no fixture selector" structural. Each is refused because the field does not
exist, not because a validator rejected it — so the guarantee cannot rot as
somebody forgets to extend a denylist.

**Two dates, no derivation.** ``reference_date`` resolves period expressions and
never affects version resolution; ``as_of`` pins version resolution and never
affects period resolution. Constructed in isolation in both directions, because
the failure mode is silent: a default that filled one from the other would make
every relative-period answer quietly depend on the wrong day.

**No clock, no detector.** Both are asserted by scanning the source of the intake
path rather than by behaviour, because both are absences — and an absence is not
observable from a passing call.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from semantic_catalog.contracts.access_tag import PrincipalType

from analytics_interaction import contracts
from analytics_interaction.contracts import (
    STRUCTURAL_TEXT_CEILING,
    DeclaredLanguage,
    InteractionModel,
    PrincipalContext,
    QuestionIntake,
    build,
)

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(contracts)).resolve().parent

PRINCIPAL = PrincipalContext(
    principal_ref="p-1",
    principal_type=PrincipalType.USER,
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    authorization_policy_pin="authpol-1",
)

#: Every governed model this feature declares, discovered from the public
#: surface rather than listed — a model added without the base would otherwise
#: simply not be checked.
GOVERNED_MODELS = sorted(
    (
        obj
        for obj in vars(contracts).values()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not InteractionModel
    ),
    key=lambda model: model.__name__,
)


def test_the_discovery_found_the_models_it_should_have() -> None:
    """A parametrized sweep over an empty list passes for the wrong reason."""
    names = {model.__name__ for model in GOVERNED_MODELS}
    assert {
        "AnalyticsAnswer",
        "AnswerClaim",
        "AttributedCaveat",
        "CandidateRef",
        "CaveatSet",
        "ClarificationContract",
        "ComparisonIntent",
        "GovernedComparison",
        "QuestionIntake",
        "ResolvedIntent",
        "ResolvedPeriod",
        "Seal",
        "SideResult",
        "TermResolution",
    } <= names


@pytest.mark.parametrize("model", GOVERNED_MODELS, ids=lambda m: m.__name__)
def test_every_governed_model_is_frozen_and_forbids_extras(model: type[BaseModel]) -> None:
    assert model.model_config.get("frozen") is True, f"{model.__name__} is mutable"
    assert model.model_config.get("extra") == "forbid", f"{model.__name__} accepts extras"


@pytest.mark.parametrize("model", GOVERNED_MODELS, ids=lambda m: m.__name__)
def test_every_governed_model_rejects_an_undeclared_field(model: type[BaseModel]) -> None:
    """Checked on every model, because one permissive model is the whole hole."""
    with pytest.raises(ValidationError, match=r"extra_forbidden|Extra inputs"):
        model.model_validate({"definitely_not_a_field": 1})


# --- what intake deliberately does not offer ----------------------------------

FORBIDDEN_INTAKE_FIELDS = (
    "sql",
    "query",
    "query_text",
    "filter_expression",
    "access_tags",
    "role",
    "elevate",
    "max_bytes",
    "max_rows",
    "threshold",
    "limit",
    "freshness",
    "coverage",
    "data_revision",
    "catalog_release",
    "policy_version",
    "vocabulary_version",
    "fixture",
    "mode",
    "debug",
    "format",
    "channel",
    "template",
    "detected_language",
    "language_hint",
    "observation",
)


@pytest.mark.parametrize("field", FORBIDDEN_INTAKE_FIELDS)
def test_question_intake_declares_no_such_field(field: str) -> None:
    assert field not in QuestionIntake.model_fields


@pytest.mark.parametrize("field", FORBIDDEN_INTAKE_FIELDS)
def test_supplying_a_forbidden_field_fails_construction(field: str) -> None:
    """Refused as an unknown field — not by a rule that had to name it."""
    with pytest.raises(Exception, match=r"extra_forbidden|Extra inputs|INTAKE_MALFORMED"):
        build(
            QuestionIntake,
            text="quantas instalações em julho?",
            language=DeclaredLanguage.PT_BR,
            reference_date=date(2026, 8, 13),
            principal=PRINCIPAL,
            **{field: "x"},
        )


def test_question_intake_carries_exactly_the_five_contract_fields() -> None:
    assert tuple(QuestionIntake.model_fields) == (
        "text",
        "language",
        "reference_date",
        "as_of",
        "principal",
    )


# --- the two dates ------------------------------------------------------------


def test_a_reference_date_is_constructible_without_an_as_of() -> None:
    intake = build(
        QuestionIntake,
        text="quantas instalações na semana passada?",
        language=DeclaredLanguage.PT_BR,
        reference_date=date(2026, 8, 13),
        principal=PRINCIPAL,
    )
    assert intake.reference_date == date(2026, 8, 13)
    assert intake.as_of is None, "an omitted as_of must stay omitted, never filled"


def test_an_as_of_is_constructible_without_changing_the_reference_date() -> None:
    intake = build(
        QuestionIntake,
        text="quantas instalações em julho?",
        language=DeclaredLanguage.PT_BR,
        reference_date=date(2026, 8, 13),
        as_of=date(2026, 7, 1),
        principal=PRINCIPAL,
    )
    assert intake.reference_date == date(2026, 8, 13)
    assert intake.as_of == date(2026, 7, 1)


def test_the_reference_date_is_required() -> None:
    """Required unconditionally, so no parse precedes a validation (`R-9`)."""
    with pytest.raises(Exception, match=r"reference_date|INTAKE_MALFORMED"):
        build(
            QuestionIntake,
            text="quantas instalações?",
            language=DeclaredLanguage.PT_BR,
            principal=PRINCIPAL,
        )


def test_neither_date_is_derived_from_the_other_in_either_direction() -> None:
    """The same as_of under two reference dates, and the reverse.

    If either defaulted from the other, one of these pairs would collapse.
    """
    common = {
        "text": "quantas instalações?",
        "language": DeclaredLanguage.PT_BR,
        "principal": PRINCIPAL,
    }
    a = build(QuestionIntake, reference_date=date(2026, 8, 13), as_of=date(2026, 1, 1), **common)
    b = build(QuestionIntake, reference_date=date(2026, 8, 14), as_of=date(2026, 1, 1), **common)
    assert a.as_of == b.as_of and a.reference_date != b.reference_date

    c = build(QuestionIntake, reference_date=date(2026, 8, 13), as_of=date(2026, 2, 2), **common)
    assert a.reference_date == c.reference_date and a.as_of != c.as_of


# --- language is declared -----------------------------------------------------


def test_the_declared_language_is_required() -> None:
    with pytest.raises(Exception, match=r"language|INTAKE_MALFORMED"):
        build(
            QuestionIntake,
            text="quantas instalações?",
            reference_date=date(2026, 8, 13),
            principal=PRINCIPAL,
        )


def test_a_language_outside_the_governed_set_is_refused() -> None:
    with pytest.raises(Exception, match=r"language|INTAKE_MALFORMED"):
        build(
            QuestionIntake,
            text="how many installs?",
            language="en-US",
            reference_date=date(2026, 8, 13),
            principal=PRINCIPAL,
        )


def test_a_pt_br_question_may_carry_english_canonical_identifiers() -> None:
    """`001` makes identifiers English while human content is pt-BR.

    A legitimate question routinely mixes both, so mixing must not be evidence
    of a wrong declaration (`FR-102`).
    """
    intake = build(
        QuestionIntake,
        text="quantas installs de google_play em julho?",
        language=DeclaredLanguage.PT_BR,
        reference_date=date(2026, 8, 13),
        principal=PRINCIPAL,
    )
    assert intake.language is DeclaredLanguage.PT_BR


# --- structural bounds, disclosing nothing ------------------------------------


def test_an_empty_question_is_refused() -> None:
    for empty in ("", "   ", "?!.", "\n\t"):
        with pytest.raises(Exception, match=r"empty|INTAKE_MALFORMED|too_short|at least"):
            build(
                QuestionIntake,
                text=empty,
                language=DeclaredLanguage.PT_BR,
                reference_date=date(2026, 8, 13),
                principal=PRINCIPAL,
            )


def test_a_question_over_the_structural_ceiling_is_refused() -> None:
    with pytest.raises(Exception, match=r"at most|too_long|INTAKE_MALFORMED"):
        build(
            QuestionIntake,
            text="a" * (STRUCTURAL_TEXT_CEILING + 1),
            language=DeclaredLanguage.PT_BR,
            reference_date=date(2026, 8, 13),
            principal=PRINCIPAL,
        )


def test_control_characters_are_refused_rather_than_stripped() -> None:
    """Silently normalising untrusted input is how a screening step gets bypassed."""
    with pytest.raises(Exception, match=r"control characters|INTAKE_MALFORMED"):
        build(
            QuestionIntake,
            text="quantas insta\x00lações?",
            language=DeclaredLanguage.PT_BR,
            reference_date=date(2026, 8, 13),
            principal=PRINCIPAL,
        )


# --- absences, asserted against the source ------------------------------------


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _identifiers(path: Path) -> set[str]:
    """Every name the module actually binds or reads.

    Names, attributes, arguments, keywords, imports and definitions — but never
    docstrings or comments. A module that *documents* a forbidden field is doing
    the right thing; a module that *declares* one is not, and only an
    identifier-level scan can tell the two apart.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.keyword):
            # A `**kwargs` call site has no name to record.
            found.add(node.arg or "")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.alias):
            found.add(node.asname or node.name)
    return found


def test_no_contract_module_reads_a_system_clock() -> None:
    """`FR-099`: no field is ever populated from a clock.

    Matched on the call, not the import, so ``from datetime import date`` for a
    type annotation stays legal while ``date.today()`` does not.
    """
    forbidden = {"today", "now", "utcnow", "time", "monotonic", "time_ns"}
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden
            ):
                offenders.append(f"{path.name}:{node.lineno} {node.func.attr}()")
    assert not offenders, f"a clock is read on the contract path: {offenders}"


def test_no_contract_module_detects_infers_or_scores_a_language() -> None:
    """`SC-058`: detection does not exist, anywhere.

    Whether a question is answered at all must not depend on a probabilistic
    input (`FR-041`).
    """
    forbidden = (
        "detect_language",
        "language_detect",
        "langdetect",
        "guess_language",
        "infer_language",
        "language_score",
        "language_confidence",
        "detected_language",
        "language_hint",
    )
    offenders = [
        f"{path.name}: {name}"
        for path in _sources()
        for name in _identifiers(path)
        if any(token in name.lower() for token in forbidden)
    ]
    assert not offenders, f"language detection surface found: {offenders}"


def test_the_detection_scan_reads_identifiers_rather_than_prose() -> None:
    """`intake.py` *documents* the absent fields, and must be allowed to.

    Scanning raw text would flag the very table that records why
    ``detected_language`` and ``language_hint`` do not exist — turning an
    accurate explanation into a build failure and pressuring the next author to
    delete the explanation rather than the field. The scan therefore reads
    identifiers, and this asserts the distinction holds in both directions.
    """
    intake_source = (SRC / "intake.py").read_text(encoding="utf-8")
    assert "language_hint" in intake_source, "the deliberately-absent table is documented"
    assert not any("language_hint" in name for name in _identifiers(SRC / "intake.py"))

    planted = ast.parse("detected_language: str = ''\n")
    names = {node.id for node in ast.walk(planted) if isinstance(node, ast.Name)}
    assert any("detected_language" in name for name in names), "the scan would catch a real field"


def test_the_only_confidence_concept_is_a_categorical_basis_not_a_score() -> None:
    """``confidence_basis`` is a closed enum, and that distinction is the point.

    A numeric confidence would reintroduce exactly what `FR-041` forbids —
    whether a term resolves depending on a threshold over a probabilistic score.
    ``ResolutionBasis`` instead records *what kind of proof* the resolution has:
    enumerated membership, open-text shape, or a governed expression. There is
    no ordering on it and nothing to threshold.
    """
    from analytics_interaction.contracts import ResolutionBasis, TermResolution

    annotation = TermResolution.model_fields["confidence_basis"].annotation
    assert annotation is ResolutionBasis
    assert sorted(member.value for member in ResolutionBasis) == [
        "enumerated_membership",
        "governed_expression",
        "open_text_shape",
    ]


def test_no_contract_module_declares_a_sql_or_query_text_field() -> None:
    """No field can carry replayable query text into this layer."""
    offenders: list[str] = []
    for model in GOVERNED_MODELS:
        for name in model.model_fields:
            if any(token in name.lower() for token in ("sql", "query_text", "statement")):
                offenders.append(f"{model.__name__}.{name}")
    assert not offenders, f"query-text fields declared: {offenders}"
