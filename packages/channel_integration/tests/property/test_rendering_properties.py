"""T146 — rendering adds nothing the payload did not carry.

Rendering may change **form**. It may never change **content**. `T074`'s preservation gate asserts
that over the fixture corpus; this asserts it over generated answers, which is a different question:
the corpus was written by someone who knew what the gate checks, and a generator was not.

## What "adds nothing" is measured against

Every string a rendered presentation contains must come from one of three places: the payload's own
governed strings, the governed capability matrix, or the structural scaffolding that is neither — a
newline, a separator. So the check strips the first two from the rendered text and asserts what
remains carries no letters or digits.

That is the same differential shape `T074` uses, and it inherits `T074`'s ordering fix: governed
strings are stripped **longest first**, because stripping a short string that is a prefix of a
longer one corrupts the longer one and the residue then reads as invented content. That was a real
defect, found by review, and repeating it here would make this test agree with a broken renderer.

## The vacuity this test had to avoid, stated because it nearly shipped

The first version drove `render_for_channel`, and every one of its 230 generated examples passed. It
passed because `D-28` is undeclared, so `resolve_capability_matrix` refuses and **no rendering ever
happened** — three green tests asserting nothing about a renderer they never reached.

So the properties drive `render_answer` with the **fixture** capability matrix injected, which is
how `T072` and `T074` reach the renderer too, and one assertion below states the shipped behaviour
out loud: through the production entry point every payload is withheld today. The fixture matrix is
a fixture value and proves nothing about production, which is the whole reason it must be passed in
rather than resolved.

## What this test refuses to assert

Not that the wording is good, idiomatic or correct pt-BR. Those are `D-28` and `D-18` judgements
about governed content this repository does not author. A property test that graded language would
be this feature grading someone else's vocabulary.
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal
from typing import cast

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.outbound.render import render_answer, render_for_channel
from channel_integration.outbound.withhold import NotRepresentable

from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY, FixturePayload, answer_with

pytestmark = pytest.mark.property

_CHANNEL = ChannelId.SLACK


#: Every governed string the fixture capability matrix can contribute to a rendering: the four claim
#: class labels and the degradation disclosures. Read from the matrix rather than restated, so a
#: matrix change cannot leave this test asserting against strings nobody renders.
def _matrix_strings() -> tuple[str, ...]:
    """Every governed string the fixture matrix may contribute, read from the matrix itself."""
    collected: list[str] = []
    for key in ("claim_class_labels", "disclosure_wording"):
        entry = FIXTURE_CAPABILITY[key]
        if isinstance(entry, dict):
            collected.extend(str(value) for value in cast("dict[str, object]", entry).values())
    return tuple(collected)


_MATRIX_STRINGS: tuple[str, ...] = _matrix_strings()


def _payload_strings(payload: FixturePayload) -> tuple[str, ...]:
    """Every string the payload authorises a renderer to emit.

    The claim subjects, values and units, the resolved wording, the caveat wording carried verbatim,
    and the provenance strings a rendering may disclose. Nothing is inferred: if a renderer emits a
    string that is in neither this tuple nor the governed matrix, it authored content.
    """
    answer = payload.answer
    collected: list[str] = []
    for claim in answer.claims:
        collected.append(claim.subject)
        if claim.value is not None:
            collected.append(str(claim.value))
        if claim.unit is not None:
            collected.append(claim.unit)
        resolved = payload.wording.text_for(claim.message.code)
        if resolved is not None:
            collected.append(resolved)
    for caveat in answer.caveats.caveats:
        # A caveat's wording travels verbatim rather than as a reference — it is the one governed
        # string in the answer that is already text, precisely so this layer cannot re-word it.
        collected.append(caveat.message_pt_br)
    for entry in answer.provenance:
        collected.extend(entry.contributing_sources)
        collected.extend(entry.limitations)
    collected.append(str(answer.caveats.total))
    return tuple(string for string in collected if string)


def _residue(rendered: str, permitted: tuple[str, ...]) -> str:
    """What remains of ``rendered`` after every permitted string is removed, longest first.

    Longest first is the `T074` ordering fix, not a preference: with a short string removed before a
    longer one that contains it, the longer one is left mangled and its fragments look invented.
    """
    remaining = rendered
    for string in sorted({*permitted, *_MATRIX_STRINGS}, key=len, reverse=True):
        remaining = remaining.replace(string, " ")
    return remaining


def _informative(residue: str) -> str:
    """The characters in ``residue`` that could carry meaning.

    Letters, digits and currency-like symbols. Punctuation, whitespace and separators are structural
    scaffolding a renderer is allowed to add: a newline between two governed strings adds no
    content.
    """
    return "".join(
        character
        for character in residue
        if unicodedata.category(character)[0] in {"L", "N"}
        or unicodedata.category(character) == "Sc"
    )


@st.composite
def _payloads(draw: st.DrawFn) -> FixturePayload:
    """A payload built from the corpus's own claim shapes, with generated values.

    The **structure** stays governed — a claim carries a class, a subject, a wording reference — and
    only the parts a sender or the warehouse could vary are generated: how many claims, which
    classes, what decimal value, how many caveats. Generating governed structure would be this test
    inventing a contract.
    """
    base = draw(st.sampled_from(sorted(CORPUS)))
    template = CORPUS[base]
    claims = draw(
        st.lists(st.sampled_from(template.answer.claims), min_size=1, max_size=4)
        if template.answer.claims
        else st.just(list(template.answer.claims))
    )
    caveats = draw(st.integers(min_value=0, max_value=12))
    return FixturePayload(
        answer_with(tuple(claims), caveats, template.answer.provenance),
        template.wording,
    )


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(payload=_payloads())
def test_no_rendered_presentation_carries_content_the_payload_did_not(
    payload: FixturePayload,
) -> None:
    """The property, over a rendering that actually happened."""
    try:
        outcome = render_answer(payload, _CHANNEL, FIXTURE_CAPABILITY)
    except NotRepresentable:
        # A payload the channel cannot carry intact is withheld whole. Withholding carries no
        # governed content, so there is nothing to invent — a pass, not a skip.
        return

    permitted = _payload_strings(payload)
    for fragment in outcome.fragments:
        leftover = _informative(_residue(fragment.body, permitted))
        assert not leftover, (
            f"the rendering carries {leftover!r}, which is in neither the payload nor the governed "
            "capability matrix"
        )


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(payload=_payloads())
def test_every_value_the_payload_carries_survives_rendering_exactly(
    payload: FixturePayload,
) -> None:
    """The other direction: form may change, content may not be dropped either.

    A renderer that satisfied the previous test by emitting nothing would be preserving content the
    way an empty page preserves a manuscript.
    """
    try:
        outcome = render_answer(payload, _CHANNEL, FIXTURE_CAPABILITY)
    except NotRepresentable:
        return

    whole = "\n".join(fragment.body for fragment in outcome.fragments)
    for claim in payload.answer.claims:
        if claim.value is None:
            continue
        assert str(claim.value) in whole, (
            f"the value {claim.value} did not survive rendering; a rounded, localised or truncated "
            "number is a changed number"
        )


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(value=st.decimals(allow_nan=False, allow_infinity=False, places=4))
def test_a_decimal_is_rendered_as_its_own_digits(value: Decimal) -> None:
    """No rounding, no separator, no locale — asserted at the one function that formats a value.

    Separate from the payload properties because it is the narrowest statement of the same rule, and
    a failure here names the formatter rather than the whole rendering.
    """
    template = CORPUS["all four claim classes"]
    #: Selected by *carrying a value* rather than by claim class, so this test names no member of a
    #: `003` enum: which class carries a number is that feature's decision, not this one's.
    numeric = next(claim for claim in template.answer.claims if claim.value is not None)
    claim = numeric.model_copy(update={"value": value})
    payload = FixturePayload(answer_with((claim,), 1, template.answer.provenance), template.wording)
    try:
        outcome = render_answer(payload, _CHANNEL, FIXTURE_CAPABILITY)
    except NotRepresentable:
        return
    whole = "\n".join(fragment.body for fragment in outcome.fragments)
    assert str(value) in whole


def test_the_corpus_actually_reaches_the_renderer() -> None:
    """The anti-vacuity assertion, and it exists because vacuity already happened here.

    Measured: five of the six corpus payloads render through the fixture matrix, and the sixth is
    withheld because it carries a wording reference with no resolved string — ADR 0026's rule, not a
    defect. If a change made all six withhold, every property above would pass by never rendering
    anything, which is exactly what the first version of this file did.
    """
    rendered = 0
    for payload in CORPUS.values():
        try:
            render_answer(payload, _CHANNEL, FIXTURE_CAPABILITY)
        except NotRepresentable:
            continue
        rendered += 1
    assert rendered >= 2, (
        f"only {rendered} of {len(CORPUS)} corpus payloads reach the renderer, so the properties "
        "above are close to vacuous"
    )


def test_the_production_entry_point_withholds_every_payload_today() -> None:
    """The shipped state, asserted so the properties above cannot be mistaken for it.

    `D-28` is undeclared, so `resolve_capability_matrix` cannot answer and every payload is withheld
    whole. That is what makes the injected fixture matrix necessary above, and this is the assertion
    that fails the day the matrix resolves — at which point these properties begin to cover
    production and this test must be re-derived rather than deleted.
    """
    for name, payload in sorted(CORPUS.items()):
        outcome = render_for_channel(payload, _CHANNEL)
        assert isinstance(outcome, ChannelRefusal), (
            f"{name} rendered through the production entry point, so D-28 now resolves and the "
            "properties above are no longer fixture-only"
        )
