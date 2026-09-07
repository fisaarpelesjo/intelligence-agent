"""T141 — a hostile string in a governed answer cannot become channel markup or a second message.

The outbound direction has its own injection surface, and it is easy to overlook because the content
is **trusted**: it came from `002` through `003`, not from a stranger. The attack is indirect — a
metric label, a dimension value or a caveat that contains channel markup, a newline that a transport
reads as a message boundary, or an escape sequence a terminal or a mobile client interprets.

Two properties, and they pull in opposite directions, which is the whole difficulty:

* **the renderer may not create structure** the payload did not have — no injected markup becomes
  formatting, and no newline becomes a second delivered fragment;
* **the renderer may not alter content** either. Escaping a governed string changes its bytes, and
  `T074`'s preservation gate refuses that. So a payload that cannot be carried intact is **withheld
  whole** rather than sanitised.

That second half is the part a conventional web boundary gets wrong in the opposite direction:
escaping is the normal answer everywhere else, and here it would be silent alteration of a governed
number or caveat. Withholding is the governed answer.

Rendering runs with the **fixture** capability matrix injected, because `D-28` is undeclared and the
production entry point withholds everything — see `tests/property/test_rendering_properties.py` for
the same reasoning and the assertion that records it.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.outbound.render import render_answer
from channel_integration.outbound.withhold import NotRepresentable

from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY, FixturePayload, answer_with

pytestmark = pytest.mark.adversarial

#: Hostile strings, each aimed at a different consumer. None is a random blob: every one is
#: something a real client interprets.
_HOSTILE = {
    "slack markup": "*negrito* _itálico_ `código` <http://evil|clique>",
    "markdown link": "[clique aqui](http://evil)",
    "html": "<script>alert(1)</script><b>x</b>",
    "response splitting": "linha um\r\nlinha dois\r\n\r\nmensagem separada",
    "ansi escape": "\x1b[31mvermelho\x1b[0m",
    "zero width": "insta​lações",
    "rtl override": "‮gnitset",
    "null byte": "texto\x00oculto",
    "telegram entity": "<a href='http://evil'>x</a>",
    "template": "{{ 7*7 }} ${env:SECRET}",
}


def _payload_with_subject(subject: str) -> FixturePayload:
    """A governed answer whose claim subject carries the hostile string.

    The subject rather than the caveat, because the subject is rendered beside a governed label and
    is the field a renderer is most likely to interpolate into a formatted block.
    """
    template = CORPUS["all four claim classes"]
    claim = template.answer.claims[0].model_copy(update={"subject": subject})
    return FixturePayload(answer_with((claim,), 1, template.answer.provenance), template.wording)


@pytest.mark.parametrize("name", sorted(_HOSTILE))
@pytest.mark.parametrize("channel", list(ChannelId))
def test_a_hostile_string_is_either_carried_verbatim_or_withheld_whole(
    name: str,
    channel: ChannelId,
) -> None:
    """The central property, and it is a disjunction on purpose.

    Escaping, stripping or rewriting the string would be altering governed content, which `FR-045`
    forbids and `T074` catches. Carrying it verbatim is correct — the string is data, and a channel
    that interprets it is a channel this payload cannot be carried on, which is what withholding
    says.
    """
    hostile = _HOSTILE[name]
    payload = _payload_with_subject(hostile)
    try:
        presentation = render_answer(payload, channel, FIXTURE_CAPABILITY)
    except NotRepresentable:
        # Withheld whole. Nothing was delivered, so nothing was injected and nothing was altered.
        return

    whole = "\n".join(fragment.body for fragment in presentation.fragments)
    assert hostile in whole, (
        f"{name} was altered rather than carried or withheld; an escaped governed string is a "
        "changed governed string"
    )
    assert hostile in presentation.governed_strings or any(
        hostile in string for string in presentation.governed_strings
    ), "the hostile string is not declared as governed, so the preservation gate cannot check it"


@pytest.mark.parametrize("name", sorted(_HOSTILE))
def test_a_hostile_string_never_becomes_an_extra_fragment(name: str) -> None:
    """Response splitting, stated as a count.

    A newline pair is a message boundary on some transports. If the renderer split on it, one answer
    would arrive as two messages and the second would carry no caveats — which is how a caveat gets
    detached from the number it qualifies.
    """
    baseline = render_answer(
        _payload_with_subject("instalações em julho"), ChannelId.SLACK, FIXTURE_CAPABILITY
    )
    try:
        hostile = render_answer(
            _payload_with_subject(_HOSTILE[name]), ChannelId.SLACK, FIXTURE_CAPABILITY
        )
    except NotRepresentable:
        return
    assert len(hostile.fragments) == len(baseline.fragments), (
        f"{name} changed the fragment count from {len(baseline.fragments)} to "
        f"{len(hostile.fragments)}"
    )


@pytest.mark.parametrize("name", sorted(_HOSTILE))
def test_every_fragment_still_carries_the_caveat_block(name: str) -> None:
    """A caveat travels in **every** fragment, and a hostile string may not detach it.

    `T073` asserts this for ordinary payloads. Here it is asserted under attack, because a splitting
    or truncating renderer would produce exactly one fragment that looked complete and was not.
    """
    payload = _payload_with_subject(_HOSTILE[name])
    try:
        presentation = render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    except NotRepresentable:
        return
    caveats = tuple(caveat.message_pt_br for caveat in payload.answer.caveats.caveats)
    for fragment in presentation.fragments:
        for caveat in caveats:
            assert caveat in fragment.body, f"{name} produced a fragment without its caveat"


def test_the_declared_caveat_count_survives_a_hostile_payload() -> None:
    """`FR-047`: the rendered count must equal the payload's declared count.

    A renderer that dropped a caveat it could not carry would under-report, and under-reporting a
    limitation is the failure the count exists to prevent.
    """
    payload = _payload_with_subject(_HOSTILE["response splitting"])
    try:
        presentation = render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    except NotRepresentable:
        return
    assert presentation.caveat_count == payload.answer.caveats.total


def test_an_ordinary_payload_renders_so_the_cases_above_are_not_vacuous() -> None:
    """Anti-vacuity: if every hostile case withholds, at least prove the renderer renders."""
    presentation = render_answer(
        _payload_with_subject("instalações em julho"), ChannelId.SLACK, FIXTURE_CAPABILITY
    )
    assert presentation.fragments
    assert presentation.governed_strings


def test_at_least_one_hostile_string_actually_reaches_the_renderer() -> None:
    """Stronger anti-vacuity: the hostile corpus is not all withheld.

    If every hostile string withheld, the verbatim-carry assertion above would never execute and
    this suite would be asserting only that withholding happens.
    """
    rendered = 0
    for hostile in _HOSTILE.values():
        try:
            render_answer(_payload_with_subject(hostile), ChannelId.SLACK, FIXTURE_CAPABILITY)
        except NotRepresentable:
            continue
        rendered += 1
    assert rendered >= 1, (
        "every hostile string is withheld, so the verbatim-carry property is never exercised"
    )
