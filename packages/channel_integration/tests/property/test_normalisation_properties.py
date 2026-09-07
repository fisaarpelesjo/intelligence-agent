"""T149 — normalisation never changes analytical meaning, and ambiguity always refuses (`SC-051`).

Normalisation is the one place this feature is allowed to alter a sender's text, so it is the place
where a quiet meaning change would be hardest to notice and most damaging: a question that asked
about July answered about August is worse than a refusal, because nobody sees a refusal and believes
it.

The rule set is small and named — Unicode NFC, remove a quoted reply, remove a threading marker,
remove a **leading** mention, trim surrounding whitespace — and the outcome carries which rules
applied and a ruleset version. That is what makes these properties statable.

## What "never changes analytical meaning" is asserted as

Three checkable statements rather than one unfalsifiable one:

* **idempotence** — normalising twice equals normalising once. A rule set that is not idempotent has
  no fixed point, so the "normalised" text depends on how many times somebody ran it.
* **determinism** — the same input yields a byte-identical outcome, including which rules applied.
* **subtraction only** — every alphanumeric character in the result was already in the input, in the
  same order. The rules delete decoration and re-compose Unicode; none of them may introduce a digit
  or a letter, because a digit that was not written is a number nobody asked about.

The third is the load-bearing one. NFC composition is why it is stated over the **NFC form** of the
input rather than the raw input: composing `e` plus a combining acute into `é` changes the character
count without adding anything a reader did not write.

## Ambiguity refuses, and the two cases are separate

A non-leading mention could be decoration or could be a value the question filters on, and the rule
set cannot tell. A text where nothing distinguishable survives could have been all decoration or not
a question at all. Both refuse with `CHANNEL_NORMALISATION_AMBIGUOUS`, and refusing is what stops
the rule set from choosing a reading on the sender's behalf.
"""

from __future__ import annotations

import re
import unicodedata

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from channel_integration.contracts._base import ChannelViolation
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.inbound.normalise import (
    NORMALISATION_RULESET_VERSION,
    normalise_question,
)

pytestmark = pytest.mark.property

#: Text a sender could write. Combining marks, quotation and whitespace runs are in scope on
#: purpose: those are what the rules act on, and a generator that avoided them would exercise
#: nothing.
#: Any mention, in the form `normalise.py` recognises. Restated here rather than imported,
#: because a property test that shared the implementation's own regex would agree with it by
#: construction.
_MENTION_ANYWHERE = re.compile(r"@[A-Za-z0-9_.\-]{2,64}")

_TEXT = st.text(
    alphabet=st.characters(codec="utf-8", exclude_categories=("Cs", "Co")),
    min_size=1,
    max_size=160,
)


def _alphanumeric(text: str) -> str:
    return "".join(character for character in text if character.isalnum())


def _outcome_or_refusal(text: str) -> tuple[str, tuple[str, ...]] | ChannelReasonCode:
    """The normalised text and applied rules, or the code it refused with.

    Written as a total helper so each property below states one thing. `normalise_question` raises
    rather than returning a union — it is an internal step whose refusal `convert` collapses — so
    the conversion happens here once instead of in every test.
    """
    try:
        outcome = normalise_question(text)
    except ChannelViolation as violation:
        return violation.code
    return outcome.text, outcome.applied


@settings(max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_TEXT)
def test_normalisation_is_idempotent(text: str) -> None:
    """Normalising a normalised text changes nothing, and does not start refusing either.

    The second half matters: a rule set whose output its own ambiguity check rejects would make the
    normalised form unusable by the very pipeline that produced it.
    """
    first = _outcome_or_refusal(text)
    if isinstance(first, ChannelReasonCode):
        return
    once, _ = first
    second = _outcome_or_refusal(once)
    assert not isinstance(second, ChannelReasonCode), (
        f"normalising the normalised form of {text!r} refused with {second}"
    )
    assert second[0] == once


@settings(max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_TEXT)
def test_normalisation_is_deterministic_including_which_rules_applied(text: str) -> None:
    """Two runs agree on the text **and** on the named rules.

    The rule list is part of the outcome because a text that changed shape must be explainable
    without retaining the original, so a nondeterministic rule list is a nondeterministic
    explanation.
    """
    assert _outcome_or_refusal(text) == _outcome_or_refusal(text)


@settings(max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_TEXT)
def test_normalisation_only_ever_subtracts(text: str) -> None:
    """No letter and no digit appears that the sender did not write, in that order.

    Compared against the **NFC form** of the input, because composing a base character and a
    combining mark is precisely the rule that changes the character sequence without adding content.
    """
    result = _outcome_or_refusal(text)
    if isinstance(result, ChannelReasonCode):
        return
    normalised, _ = result

    source = _alphanumeric(unicodedata.normalize("NFC", text))
    produced = _alphanumeric(normalised)

    # Subsequence check: every produced character appears in the source, in order. Stronger than a
    # set comparison, which would accept a reordering, and a reordered number is a different one.
    position = 0
    for character in produced:
        found = source.find(character, position)
        assert found >= 0, (
            f"normalisation produced {character!r}, which is not in the input's NFC form in order; "
            f"input {text!r} produced {normalised!r}"
        )
        position = found + 1


@settings(max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_TEXT)
def test_every_refusal_is_the_ambiguity_code_or_the_unusable_code(text: str) -> None:
    """Only two refusals exist here, and both name what could not be decided.

    A third code appearing would mean the rule set grew a failure mode nobody declared.
    """
    result = _outcome_or_refusal(text)
    if not isinstance(result, ChannelReasonCode):
        return
    assert result in {
        ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS,
        ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE,
    }


#: The prefixes that put the mention somewhere other than in the question. A line beginning `>` is
#: a **quoted reply** and `normalise_question` removes the whole line — including any mention on
#: it — before the mention rule runs, by declared design: a quoted reply is somebody else's text
#: and never becomes part of the question. `test_a_mention_inside_a_quoted_reply_is_removed_with_it`
#: asserts that case directly.
_QUOTED_REPLY_LINE = re.compile(r"^\s*>", re.M)

#: The second prefix that puts the mention somewhere other than in the question, and this one is
#: about **the mention rule itself**. `_LEADING_MENTION` in `normalise.py` carries a `+`: it matches
#: a *run* of mentions at the front and removes the whole run, by declared design — `@bot @equipe
#: quantas instalacoes?` is one address to two handles, not a handle followed by a filter value. So
#: a `before` that is itself a leading mention **extends the run**, and the `@equipe` that follows
#: it is still at the front of the question rather than inside it.
#:
#: Mirrored here rather than imported because a copy that drifts from `normalise.py` is caught by
#: `test_the_leading_run_exclusion_is_narrow_and_the_run_is_removed_whole`, which drives the real
#: rule set through both sides of the boundary.
_LEADING_MENTION_RUN = re.compile(r"^\s*(?:@[A-Za-z0-9_.\-]{2,64}\s+)+")


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(before=_TEXT, after=_TEXT)
def test_a_mention_that_is_not_leading_always_refuses(before: str, after: str) -> None:
    """Ambiguity case one, stated as a property over where the mention sits.

    A leading mention is addressing the bot and is removed. The same characters in the middle of a
    sentence could be a value the question filters on, so the rule set refuses rather than guessing
    — and it must refuse for **every** surrounding text, not for the one example somebody tried.

    **Premise corrected 2026-08-19, under `test_maintenance_policy`.** Hypothesis produced
    `before='>0'`, which makes `f"{before} @equipe {after}"` begin a **quoted-reply line** — so the
    mention was never in the question at all, and removing it with the quoted line is correct
    rather than a missed refusal. The premise this node was built on, that any non-empty `before`
    places the mention inside the question, is simply false for that one prefix.

    Three things the policy requires, all of them true here. **The permanent property survives
    intact**: a mention anywhere but the front of the question still refuses, for every surrounding
    text, and that is what is asserted below. **The failure came only from the false premise** — the
    counterexample differs from a passing one solely by opening a quoted line. **The correction
    strengthens rather than relaxes**: the excluded case is not dropped, it is asserted explicitly
    in the node that follows, so behaviour the old premise covered by accident is now covered on
    purpose. Nothing is skipped, xfailed, deselected or widened.

    **Premise corrected again 2026-08-20, same policy, second false case.** Hypothesis produced
    `before='@00'`, making the text `@00 @equipe 0` — where `@equipe` is the *second* member of a
    leading run of mentions, not a mention inside a question. `_LEADING_MENTION` is written with a
    `+` precisely so a run is removed whole, which the docstring above already cites as the rule
    this node is about, so removing it is the declared behaviour rather than a missed refusal. The
    same three requirements hold: the permanent property — a mention anywhere but the front refuses,
    for every surrounding text — is asserted unchanged below; the counterexample differs from a
    passing one only by opening the run; and the excluded case is asserted **on purpose** in
    `test_the_leading_run_exclusion_is_narrow_and_the_run_is_removed_whole`, which also proves the
    exclusion still admits ordinary prefixes. No xfail, no skip, no widened property.
    """
    assume(any(character.isalnum() for character in before))
    assume(not _QUOTED_REPLY_LINE.search(f"{before} @equipe {after}"))
    assume("@equipe" in _LEADING_MENTION_RUN.sub("", f"{before} @equipe {after}"))
    text = f"{before} @equipe {after}"
    result = _outcome_or_refusal(text)
    assert result is ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS, (
        f"a non-leading mention in {text!r} produced {result!r} rather than refusing"
    )


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(quoted=_TEXT, question=_TEXT)
def test_a_mention_inside_a_quoted_reply_is_removed_with_it(quoted: str, question: str) -> None:
    """The case the premise above hid, asserted deliberately instead of by accident.

    `normalise_question` removes quoted-reply lines **before** it looks for a non-leading mention,
    and the ordering is the point: a quoted reply is text somebody else wrote, so a mention inside
    one is not a mention in this question and cannot be a value this question filters on. Refusing
    on it would make every reply to a message that mentioned the bot unanswerable.

    Stated as a **differential** property, which is the only form that isolates the quoted line.
    The first attempt asserted "the outcome is not the ambiguity refusal", and Hypothesis produced
    `question=':'` — which refuses as ambiguous for the *other* reason, nothing distinguishable
    survived, and the two reasons share one code. A test that cannot tell them apart is measuring
    the code rather than the rule.

    Stated as a **differential** property, which is the only form that isolates the quoted line, and
    narrowed twice by measurement:

    * the *applied rule list* is excluded. The first attempt compared it and failed on
      `question='0'`: prefixing genuinely adds `remove-quoted-reply` and
      `trim-surrounding-whitespace`, because a quoted line genuinely was removed. Requiring those
      to match would require the rule set not to record work it performed;
    * the *refusal code* is excluded, and only the direction is asserted. The second attempt
      compared codes and failed on `question='\r'`: alone it is blank and refuses
      `CHANNEL_TEXT_NOT_USABLE`, prefixed it is not blank on entry and refuses
      `CHANNEL_NORMALISATION_AMBIGUOUS` instead. Both refuse; which refusal a *already-refusing*
      question collapses to is not what this ordering guarantees.

    What is left is the property that matters and nothing else. **A question that normalises on its
    own must still normalise, to exactly the same text, when a quoted line carrying a mention is
    put in front of it** — so the mention on that line never reaches the ambiguity rule. And a
    question that refuses on its own must not start succeeding because of a prefix, which closes
    the other direction.
    """
    assume("\n" not in quoted)
    assume(not _MENTION_ANYWHERE.search(question))
    assume(not _QUOTED_REPLY_LINE.search(question))

    alone = _outcome_or_refusal(question)
    prefixed = _outcome_or_refusal(f">{quoted} @equipe\n{question}")

    if isinstance(alone, tuple):
        assert isinstance(prefixed, tuple), (
            f"{question!r} normalises on its own but refuses with {prefixed!r} once a quoted line "
            "carrying a mention is put in front of it: the quoted line must be removed before the "
            "mention rule runs, or every reply to a message that mentioned the bot is unanswerable"
        )
        assert prefixed[0] == alone[0], (
            f"the quoted line changed the surviving question from {alone[0]!r} to {prefixed[0]!r}"
        )
    else:
        assert not isinstance(prefixed, tuple), (
            f"{question!r} refuses on its own with {alone!r} but succeeds once a quoted line is "
            "put in front of it, which would make a prefix a way past a governed refusal"
        )


def test_the_quoted_reply_exclusion_is_narrow_and_the_ordering_is_real() -> None:
    """Anti-vacuity for the `assume` above, which could otherwise discard everything.

    Two facts. The excluded prefix genuinely changes the outcome — the same mention refuses without
    it and does not with it — so the exclusion describes a real behavioural boundary rather than a
    convenient filter. And it excludes only that: an ordinary `before` still reaches the refusal.
    """
    assert _outcome_or_refusal("quantas @equipe instalacoes?") is (
        ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS
    ), "an ordinary non-leading mention no longer refuses, so the property above is vacuous"

    quoted = _outcome_or_refusal(">quantas @equipe\ninstalacoes em julho?")
    assert quoted is not ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS, (
        "a mention on a quoted-reply line now refuses, so the exclusion describes nothing"
    )

    assert _QUOTED_REPLY_LINE.search(">0 @equipe \n0"), (
        "the recorded counterexample is no longer matched by the exclusion, so the premise "
        "correction above no longer covers the case that caused it"
    )
    assert not _QUOTED_REPLY_LINE.search("quantas @equipe instalacoes?")


def test_the_leading_run_exclusion_is_narrow_and_the_run_is_removed_whole() -> None:
    """The `F39` case, asserted deliberately instead of discarded.

    Driven through the **real rule set**, not through the mirrored regex, so a copy that drifts from
    `normalise.py` fails here. Three facts, and the middle one is the behaviour the exclusion buys.

    First, an ordinary non-leading mention still refuses, so excluding the run did not empty the
    property above. Second, a **run** of leading mentions is removed entirely and the question
    normalises: `@bot @equipe quantas ...` addresses two handles and keeps no `@` afterwards, which
    is what the `+` in `_LEADING_MENTION` is for. Third, the recorded counterexample is the case the
    exclusion names — `@00 @equipe 0` is a run, and it normalises rather than refusing.
    """
    assert _outcome_or_refusal("quantas @equipe instalacoes?") is (
        ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS
    ), "an ordinary non-leading mention no longer refuses, so the property above is vacuous"

    run = _outcome_or_refusal("@bot @equipe quantas instalações tivemos na Google Play em julho?")
    assert not isinstance(run, ChannelReasonCode), (
        "a run of leading mentions now refuses, so the exclusion above describes nothing and the "
        "`+` in `_LEADING_MENTION` no longer removes the run it was written for"
    )
    text, applied = run
    assert "@" not in text, f"the run was not removed whole: {text!r} still carries a mention"
    assert "remove-leading-mention" in applied

    recorded = _outcome_or_refusal("@00 @equipe 0")
    assert not isinstance(recorded, ChannelReasonCode), (
        "the recorded `F39` counterexample now refuses, so the premise correction above covers a "
        "case that no longer exists"
    )

    assert "@equipe" not in _LEADING_MENTION_RUN.sub("", "@00 @equipe 0"), (
        "the mirrored run pattern no longer excludes the counterexample that caused `F39`"
    )
    assert "@equipe" in _LEADING_MENTION_RUN.sub("", "quantas @equipe instalacoes?"), (
        "the mirrored run pattern now excludes an ordinary prefix, so it is too wide"
    )


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(decoration=st.text(alphabet=" \t\n.,;:!?-—…", min_size=1, max_size=30))
def test_text_with_nothing_distinguishable_always_refuses(decoration: str) -> None:
    """Ambiguity case two. Whatever this was, it was not a question, and choosing is what
    refusing avoids.
    """
    result = _outcome_or_refusal(decoration)
    assert result in {
        ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS,
        ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE,
    }


def test_the_generator_reaches_both_a_normalised_text_and_a_refusal() -> None:
    """Anti-vacuity. Without it, a generator that only refused would satisfy every property."""
    accepted = _outcome_or_refusal("quantas instalações tivemos na Google Play em julho?")
    refused = _outcome_or_refusal("   ")
    assert not isinstance(accepted, ChannelReasonCode), "the fixture question no longer normalises"
    assert isinstance(refused, ChannelReasonCode), "blank text no longer refuses"


def test_the_ruleset_version_travels_with_every_outcome() -> None:
    """A normalised text is attributable to the rule set that made it, or it is unexplainable."""
    outcome = normalise_question("  quantas instalações em julho?  ")
    assert outcome.ruleset_version == NORMALISATION_RULESET_VERSION
    assert "trim-surrounding-whitespace" in outcome.applied
