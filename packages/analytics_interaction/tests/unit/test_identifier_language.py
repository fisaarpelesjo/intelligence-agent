"""English identifiers in a pt-BR question — T054 (FR-102; SC-059).

    A question declared pt-BR MUST NOT be refused on language grounds for
    containing English canonical identifiers: `001` makes identifiers English by
    design while human-facing content is pt-BR, so a legitimate question
    routinely mixes both. — `FR-102`

This is not an edge case. Every real question about `installs` from
`google_play` broken down by `country` mixes two languages, because `001`'s
`FR-053` and `FR-054` deliberately put identifiers in English and surfaces in
pt-BR. A system that treated mixing as evidence of a wrong declaration would
refuse the ordinary case.

The guarantee holds **structurally**: nothing on the language path reads the
text, so no proportion of English can affect the decision. The tests below
therefore push it to the limit — a question written *entirely* in canonical
identifiers, with no Portuguese at all, must still be accepted under a pt-BR
declaration.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType

from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intake import (
    DeclaredLanguage,
    PrincipalContext,
    QuestionIntake,
)
from analytics_interaction.intake.language import require_declared_language
from analytics_interaction.intake.parse import parse_intake

pytestmark = pytest.mark.unit

PRINCIPAL = PrincipalContext(principal_ref="p-1", principal_type=PrincipalType.USER)
REFERENCE = date(2026, 8, 13)

#: Canonical identifiers as `001` declares them: English, snake_case.
IDENTIFIERS = ("installs", "google_play", "app_version", "country", "sessions", "product")

MIXED_QUESTIONS = (
    "quantas installs de google_play em julho?",
    "installs por country na semana passada",
    "compare sessions entre google_play e app_store",
    "qual o total de installs por app_version?",
    "mostre product e country para installs",
)


def _intake(text: str, language: object = "pt-BR") -> QuestionIntake:
    return parse_intake(
        {
            "text": text,
            "language": language,
            "reference_date": REFERENCE,
            "principal": PRINCIPAL,
        }
    )


# --- mixed questions are ordinary ---------------------------------------------


@pytest.mark.parametrize("question", MIXED_QUESTIONS)
def test_a_pt_br_question_carrying_english_identifiers_is_accepted(question: str) -> None:
    intake = _intake(question)
    assert intake.language is DeclaredLanguage.PT_BR
    assert intake.text == question


def test_a_question_written_entirely_in_identifiers_is_accepted() -> None:
    """The limit case. No Portuguese at all, and still not a language refusal.

    A detector would almost certainly call this English. Nothing here calls it
    anything, because nothing here reads it.
    """
    intake = _intake(" ".join(IDENTIFIERS))
    assert intake.language is DeclaredLanguage.PT_BR


@pytest.mark.parametrize("identifier", IDENTIFIERS)
def test_no_single_identifier_changes_the_declared_language(identifier: str) -> None:
    intake = _intake(f"quantas {identifier} em julho?")
    assert intake.language is DeclaredLanguage.PT_BR


def test_english_prose_under_a_pt_br_declaration_is_also_accepted() -> None:
    """Deliberate, and worth stating rather than leaving as a side effect.

    The declaration is the caller's assertion about which governed content set
    their answer should be drawn from. It is **not** a claim about the grammar of
    their sentence, and the system has no standing to second-guess it — that
    would be detection wearing a different name.

    A caller who declares pt-BR and writes English gets a pt-BR answer, which is
    what they asked for.
    """
    intake = _intake("how many installs from google_play in July?")
    assert intake.language is DeclaredLanguage.PT_BR


# --- the text cannot influence the decision -----------------------------------


def test_the_same_declaration_resolves_identically_whatever_the_text() -> None:
    """Varying only the text, the language outcome is constant."""
    languages = {
        _intake(question).language
        for question in (*MIXED_QUESTIONS, " ".join(IDENTIFIERS), "olá, tudo bem?")
    }
    assert languages == {DeclaredLanguage.PT_BR}


def test_the_language_check_never_sees_the_text() -> None:
    """Called with the declaration alone, and it is the only thing it can use."""
    assert require_declared_language("pt-BR") is DeclaredLanguage.PT_BR


def test_an_unsupported_declaration_is_refused_however_portuguese_the_text_is() -> None:
    """The converse. Perfect pt-BR does not rescue a declaration outside the set.

    Without this the suite could pass against a system that quietly fell back to
    inspecting the text when the declaration looked wrong — which is detection.
    """
    with pytest.raises(ContractViolation) as caught:
        _intake("quantas instalações de google_play em julho?", language="en-US")
    assert caught.value.code.value == "LANGUAGE_NOT_SUPPORTED"


def test_a_missing_declaration_is_refused_however_portuguese_the_text_is() -> None:
    """Never defaulted to pt-BR because the text looks Portuguese."""
    with pytest.raises(ContractViolation) as caught:
        _intake("quantas instalações de google_play em julho?", language=None)
    assert caught.value.code.value == "LANGUAGE_NOT_DECLARED"
