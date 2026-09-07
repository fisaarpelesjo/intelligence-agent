"""Declared normalisation — T060 (FR-037 to FR-039; SC-050, SC-051).

Three claims: the declared rules apply deterministically, **ambiguity refuses**, and nothing in
this module can change the meaning of a question.

The third is asserted the only honest way available — over a corpus, checking that the surviving
text is a **subsequence-preserving** subset of the original with no substitution: no word appears
that was not there, and no word that was there is silently replaced.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts._base import ChannelViolation
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.inbound.normalise import (
    NORMALISATION_RULESET_VERSION,
    normalise_question,
)

pytestmark = pytest.mark.unit

_QUESTION = "quantas instalações tivemos na Google Play em julho?"


def test_a_canonical_question_survives_untouched() -> None:
    outcome = normalise_question(_QUESTION)
    assert outcome.text == _QUESTION
    assert outcome.applied == ()
    assert outcome.ruleset_version == NORMALISATION_RULESET_VERSION


@pytest.mark.parametrize(
    ("raw", "rule"),
    [
        (f"@bot {_QUESTION}", "remove-leading-mention"),
        (f"> citação anterior\n{_QUESTION}", "remove-quoted-reply"),
        (f"Re: {_QUESTION}", "remove-threading-marker"),
        (f"   {_QUESTION}   ", "trim-surrounding-whitespace"),
    ],
)
def test_each_declared_rule_is_named_when_it_applies(raw: str, rule: str) -> None:
    outcome = normalise_question(raw)
    assert rule in outcome.applied
    assert _QUESTION in outcome.text


def test_normalisation_is_deterministic_across_repeats() -> None:
    """`SC-050`: byte-identical, every run."""
    raw = f"  @bot Re: {_QUESTION}  "
    first = normalise_question(raw)
    second = normalise_question(raw)
    assert first.text == second.text
    assert first.applied == second.applied


def test_a_mention_that_is_not_leading_refuses_rather_than_being_removed() -> None:
    """It might be decoration; it might be a filter value. The rule set cannot tell (`FR-039`)."""
    with pytest.raises(ChannelViolation) as caught:
        normalise_question("quantas instalações @bot em julho?")
    assert caught.value.code is ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS


def test_text_that_is_only_decoration_refuses() -> None:
    with pytest.raises(ChannelViolation) as caught:
        normalise_question("@bot")
    assert caught.value.code is ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS


def test_blank_text_refuses_as_unusable_not_as_ambiguous() -> None:
    """Different conditions, different codes: nothing arrived versus nothing survived."""
    with pytest.raises(ChannelViolation) as caught:
        normalise_question("   ")
    assert caught.value.code is ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE


def test_no_rule_substitutes_expands_or_translates() -> None:
    """`FR-038`, over a corpus: every surviving word was in the original.

    A rule that corrected spelling, expanded an abbreviation or translated a term would introduce
    a word the sender did not write, and this is what would catch it.
    """
    corpus = [
        _QUESTION,
        "instalacoes na google play?",  # unaccented, must NOT be "corrected"
        "qtd de instalações em jul?",  # abbreviated, must NOT be expanded
        "how many installs in July?",  # another language, must NOT be translated
        f"@bot {_QUESTION}",
        f"> anterior\n{_QUESTION}",
    ]
    for raw in corpus:
        outcome = normalise_question(raw)
        original_words = set(raw.split())
        for word in outcome.text.split():
            assert word in original_words, f"normalisation introduced {word!r}"


def test_unicode_is_normalised_without_changing_the_visible_question() -> None:
    """NFC composition is a representation change, not a content change."""
    decomposed = "quantas instalações?"
    outcome = normalise_question(decomposed)
    assert "unicode-nfc" in outcome.applied
    assert outcome.text == "quantas instalações?"
