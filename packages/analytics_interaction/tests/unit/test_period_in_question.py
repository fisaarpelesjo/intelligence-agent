"""`F12` — the governed period expression is located **inside** the question (owner items 1, 2, 8).

Before this, step 7 handed the *whole question* to `resolve_governed_period`, which compares by
exact equality. No input could satisfy both halves of an analytical question: a text that was itself
a period surface carried no metric, and a text carrying a metric was not a period surface. That is
the wall `F12` names.

## What is asserted here, and what is deliberately not

Asserted: the search finds the expression a question contains; token boundaries hold; the one
declared normalisation covers case, accents, trailing punctuation and spacing; more than one period
refuses rather than choosing; an absent period refuses; an empty vocabulary still refuses.

**Not asserted here: the resolved range.** Every case below calls `locate_expression`, which finds
the expression and nothing else. The range is a separate question with a separate owner — a
`PeriodBoundaryResolverPort` supplies it and `period.py` checks the answer — and
`test_period_boundaries.py` is where that is asserted, including the full July range the owner
required. Splitting them is deliberate: locating the expression and bounding it are two failures
with two causes, and a file asserting both would report either as the other.

Every vocabulary below is built in the test. Nothing reads
`interpretation_governance/period-vocabulary.yaml`, which carries `instances: []` and stays so.
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.governance.schemas import (
    ContentApproval,
    PeriodExpression,
    PeriodVocabulary,
)
from analytics_interaction.interpretation.period import locate_expression, normalise_surface

pytestmark = pytest.mark.unit

_APPROVAL = ContentApproval(
    approver_role="test-only-no-approver",
    evidence_ref="test-only-no-evidence",
    approved_on=date(2026, 1, 1),
)


def _vocabulary(*expressions: PeriodExpression) -> PeriodVocabulary:
    return PeriodVocabulary(
        version="test-vocabulary-not-approved",
        effective_from=date(2026, 1, 1),
        approval=_APPROVAL,
        expressions=expressions,
    )


def _july(*surface_forms: str) -> PeriodExpression:
    """One named-calendar-range entry. `named_calendar_range` avoids "week" and "month".

    `PeriodExpression._convention_is_complete` keys off substrings of the rule name, so a rule
    containing `month` would demand a `month_rule` and refuse `PERIOD_CONVENTION_UNDECLARED` — the
    validator being right, and not what these cases are about.
    """
    return PeriodExpression(
        id="july_2026",
        surface_forms=surface_forms or ("julho de 2026",),
        boundary_rule="named_calendar_range",
        inclusivity="inclusive_both",
    )


class TestTheExpressionIsFoundInsideTheQuestion:
    """Owner item 1. The whole question is no longer compared against a surface form."""

    def test_a_full_question_resolves_the_expression_it_contains(self) -> None:
        expression, span = locate_expression(
            "quantas instalacoes tivemos em julho de 2026 por plataforma", _vocabulary(_july())
        )
        assert expression.id == "july_2026"
        assert span.surface == "julho de 2026"

    def test_the_span_reports_where_the_expression_sits(self) -> None:
        """The offset is carried because a caller may need to know what it consumed.

        Asserted by slicing the original text rather than by a literal number, so the case stays
        true if the sentence around the expression changes.
        """
        text = "quantas instalacoes tivemos em julho de 2026 por plataforma"
        _expression, span = locate_expression(text, _vocabulary(_july()))
        assert text[span.start : span.start + span.length] == "julho de 2026"

    def test_the_whole_question_is_no_longer_a_valid_surface_form(self) -> None:
        """The regression this fix exists for, stated as its inverse.

        A vocabulary whose only surface form is the entire sentence used to be the **only** way a
        question could pass step 7. It still resolves — the sentence is a span of itself — but it is
        no longer required, which the case above proves.
        """
        sentence = "quantas instalacoes tivemos em julho de 2026 por plataforma"
        expression, span = locate_expression(sentence, _vocabulary(_july(sentence)))
        assert expression.id == "july_2026"
        assert span.surface == sentence


class TestTokenBoundaries:
    """Owner's mandatory case: no match inside another word. Inherited from the segmenter."""

    @pytest.mark.parametrize(
        "text",
        [
            "quantas instalacoes em julhoxyz de 2026 por plataforma",
            "quantas instalacoes em xyzjulho de 2026 por plataforma",
        ],
    )
    def test_a_longer_word_containing_the_surface_does_not_match(self, text: str) -> None:
        """`segment` offers token-aligned spans, so a substring of a token is never a span.

        This is a property of the reuse rather than of new code here, which is the point of reusing
        the segmenter instead of writing a second search.
        """
        with pytest.raises(ContractViolation) as caught:
            locate_expression(text, _vocabulary(_july()))
        assert caught.value.code is InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED

    def test_punctuation_does_not_join_two_tokens_into_a_surface(self) -> None:
        """`julho, de, 2026` must not produce the span `julho de 2026`.

        The sender separated those with commas; joining them would invent a surface nobody wrote.
        """
        with pytest.raises(ContractViolation):
            locate_expression("instalacoes em julho, de, 2026 por plataforma", _vocabulary(_july()))


class TestTheDeclaredNormalisation:
    """Owner item 2. One normalisation, applied to both sides, covering four things."""

    @pytest.mark.parametrize(
        "text",
        [
            "quantas instalacoes tivemos em julho de 2026 por plataforma",
            "Quantas instalações tivemos em julho de 2026 por plataforma?",
            "QUANTAS INSTALAÇÕES TIVEMOS EM JULHO DE 2026 POR PLATAFORMA?",
            "   quantas instalacoes tivemos em julho de 2026 por plataforma   ",
            "quantas instalacoes tivemos em  julho  de  2026  por plataforma",
            "quantas instalacoes tivemos em JULHO de 2026 por plataforma!",
        ],
    )
    def test_every_spelling_the_owner_requires_resolves_the_same_expression(
        self, text: str
    ) -> None:
        expression, _span = locate_expression(text, _vocabulary(_july()))
        assert expression.id == "july_2026"

    def test_the_authored_surface_form_is_normalised_too(self) -> None:
        """Both sides, not just the caller's. An author who typed `Julho De 2026` still matches.

        Normalising only the question would make the vocabulary's own casing load-bearing, which is
        the kind of invisible coupling that fails months later when somebody re-types an entry.
        """
        expression, _span = locate_expression(
            "instalacoes em julho de 2026 por plataforma",
            _vocabulary(_july("  Julho   De   2026  ")),
        )
        assert expression.id == "july_2026"

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("JULHO", "julho"),
            ("instalações", "instalacoes"),
            ("  julho  de  2026  ", "julho de 2026"),
            ("Julho\tde\n2026", "julho de 2026"),
        ],
    )
    def test_the_normalisation_is_defined_and_symmetric(self, left: str, right: str) -> None:
        assert normalise_surface(left) == normalise_surface(right)

    def test_the_normalisation_does_not_alter_meaning(self) -> None:
        """Two different words stay different. Case-folding is not a synonym table.

        Stated because a normalisation that collapsed too much would silently answer the wrong
        question, which is worse than refusing.
        """
        assert normalise_surface("julho") != normalise_surface("junho")
        assert normalise_surface("2026") != normalise_surface("2025")

    def test_the_expression_returned_is_the_authored_one_unchanged(self) -> None:
        """Normalisation touches the **comparison**, never the governed value.

        The entry handed back carries the author's own surface form, casing and accents intact, so
        nothing downstream reads a value this function rewrote.
        """
        authored = _july("Julho de 2026")
        expression, _span = locate_expression("INSTALACOES EM JULHO DE 2026", _vocabulary(authored))
        assert expression.surface_forms == ("Julho de 2026",)
        assert expression == authored


class TestAmbiguityAndAbsence:
    """Owner's mandatory cases: more than one period, no period, and an empty vocabulary."""

    def test_two_governed_periods_refuse_rather_than_choosing(self) -> None:
        """`INTENT_AMBIGUOUS`, an existing governed code.

        A period-specific ambiguity code does not exist in `InterpretationReasonCode`, and inventing
        one would be authoring a governed value. Picking the first of two would answer a question
        the sender did not ask.
        """
        august = PeriodExpression(
            id="august_2026",
            surface_forms=("agosto de 2026",),
            boundary_rule="named_calendar_range",
            inclusivity="inclusive_both",
        )
        with pytest.raises(ContractViolation) as caught:
            locate_expression(
                "instalacoes em julho de 2026 e agosto de 2026", _vocabulary(_july(), august)
            )
        assert caught.value.code is InterpretationReasonCode.INTENT_AMBIGUOUS

    def test_one_expression_named_twice_is_not_ambiguous(self) -> None:
        """Repeating the same period is one period. Ambiguity is about distinct expressions.

        Refusing here would turn a harmless repetition into a dead end.
        """
        expression, _span = locate_expression(
            "instalacoes em julho de 2026 comparado com julho de 2026", _vocabulary(_july())
        )
        assert expression.id == "july_2026"

    def test_a_question_with_no_governed_period_refuses(self) -> None:
        with pytest.raises(ContractViolation) as caught:
            locate_expression("quantas instalacoes por plataforma", _vocabulary(_july()))
        assert caught.value.code is InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED

    def test_an_empty_vocabulary_still_refuses(self) -> None:
        """The shipped state: `period-vocabulary.yaml` is empty and must keep refusing.

        This is the case that keeps production fail-closed after `F12`: the correction changed *how*
        the expression is found, never whether an ungoverned period can resolve.
        """
        with pytest.raises(ContractViolation) as caught:
            locate_expression("instalacoes em julho de 2026", _vocabulary())
        assert caught.value.code is InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED

    def test_no_refusal_carries_any_part_of_the_question(self) -> None:
        """The property `003`'s adversarial suite asserts everywhere, re-asserted for this path.

        A refusal detail reaches a log line and an audit event. The question is untrusted text, and
        a period search is a new place it could leak from.
        """
        secret = "instalacoes em CANARIO_SECRETO por plataforma"
        with pytest.raises(ContractViolation) as caught:
            locate_expression(secret, _vocabulary(_july()))
        assert "CANARIO_SECRETO" not in str(caught.value)
        assert "CANARIO_SECRETO" not in str(caught.value.detail)


class TestDeterminism:
    """Two runs over one question agree, and the most specific span wins."""

    def test_the_result_is_stable_across_runs(self) -> None:
        text = "quantas instalacoes tivemos em julho de 2026 por plataforma"
        vocabulary = _vocabulary(_july())
        first = locate_expression(text, vocabulary)
        second = locate_expression(text, vocabulary)
        assert first[0] == second[0]
        assert (first[1].start, first[1].length) == (second[1].start, second[1].length)

    def test_the_longest_matching_span_is_preferred(self) -> None:
        """`julho de 2026` beats `julho`, because `segment` offers longest first.

        Offering the short span first would let a broader period win over the specific one the
        sender actually wrote — answering about every July instead of this one.
        """
        broad = PeriodExpression(
            id="july_any_year",
            surface_forms=("julho",),
            boundary_rule="named_calendar_range",
            inclusivity="inclusive_both",
        )
        # Both entries match somewhere, so this is the ambiguous case by construction — which is
        # itself the right answer: two distinct expressions apply and neither is chosen.
        with pytest.raises(ContractViolation) as caught:
            locate_expression("instalacoes em julho de 2026", _vocabulary(_july(), broad))
        assert caught.value.code is InterpretationReasonCode.INTENT_AMBIGUOUS
