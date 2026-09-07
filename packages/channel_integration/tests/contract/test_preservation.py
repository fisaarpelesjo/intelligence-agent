"""Preservation, byte for byte — T089 (ADR 0022; FR-043 to FR-047; SC-015, SC-016, SC-019).

The corpus against four channels, and for each pairing three claims:

1. every governed string the payload carries appears in the delivered bytes, **byte-identical**;
2. the rendered caveat count equals the payload's **declared** count;
3. the preservation gate accepts the rendering — the same rendering, checked by a component written
   to distrust the renderer.

The corpus is deliberately the hard cases: maximum caveats, two-sided provenance, a suppressed cell,
a zero-row result, all four claim classes, and a reference with no resolved string. The last one is
expected to **withhold**, and that expectation is asserted rather than skipped: a corpus whose every
entry succeeds would not be testing the boundary.

Byte-identity is asserted by substring containment against the payload's own strings. Containment
rather than equality because channel syntax may legitimately surround content; what it may not do is
alter a single byte of it.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.outbound.preserve import assert_preserved, payload_governed_strings
from channel_integration.outbound.render import render_answer
from channel_integration.outbound.withhold import NotRepresentable

from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY

pytestmark = pytest.mark.contract

#: The one corpus entry expected to withhold, and why. Named so a future entry that also withholds
#: has to be added here deliberately rather than silently joining the exemption.
_EXPECTED_TO_WITHHOLD = {"an unresolved wording reference"}

_RENDERABLE = sorted(set(CORPUS) - _EXPECTED_TO_WITHHOLD)
_CHANNELS = list(ChannelId)


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("name", _RENDERABLE)
def test_every_governed_string_survives_byte_for_byte(name: str, channel: ChannelId) -> None:
    """`SC-015`: the corpus, every channel, every string."""
    payload = CORPUS[name]
    presentation = render_answer(payload, channel, FIXTURE_CAPABILITY)
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    for string in payload_governed_strings(payload):
        assert string in delivered, f"{name} on {channel.value}: {string!r} did not survive"


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("name", _RENDERABLE)
def test_the_rendered_caveat_count_equals_the_declared_count(name: str, channel: ChannelId) -> None:
    """`FR-047`, `SC-019`: a renderer showing a subset is detectable, not merely wrong."""
    payload = CORPUS[name]
    presentation = render_answer(payload, channel, FIXTURE_CAPABILITY)
    assert presentation.caveat_count == payload.answer.caveats.total


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("name", _RENDERABLE)
def test_the_preservation_gate_accepts_the_rendering(name: str, channel: ChannelId) -> None:
    """The gate and the renderer must agree, and the gate is the one that distrusts."""
    payload = CORPUS[name]
    presentation = render_answer(payload, channel, FIXTURE_CAPABILITY)
    assert assert_preserved(presentation, payload, FIXTURE_CAPABILITY) is presentation


def test_a_reference_with_no_resolved_string_withholds() -> None:
    """ADR 0026: absence is a withhold, never a fallback that renders the reference."""
    payload = CORPUS["an unresolved wording reference"]
    with pytest.raises(NotRepresentable) as caught:
        render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    assert "resolved string" in str(caught.value)


def test_the_corpus_covers_the_cases_it_claims_to() -> None:
    """The corpus is the instrument, so its coverage is asserted rather than assumed."""
    for required in (
        "all four claim classes",
        "maximum caveat count",
        "multi-side provenance",
        "a suppressed cell",
        "a zero-row result",
        "an unresolved wording reference",
    ):
        assert required in CORPUS
    assert CORPUS["maximum caveat count"].answer.caveats.total >= 12
    assert len(CORPUS["multi-side provenance"].answer.provenance) == 2


def test_a_zero_value_is_rendered_as_zero_and_not_as_absence() -> None:
    """The quiet failure this closes: a zero result rendered as "no data", or dropped."""
    payload = CORPUS["a zero-row result"]
    presentation = render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    assert "0 un" in delivered
    for absence in ("sem dados", "nenhum dado", "n/a", "N/A", "vazio"):
        assert absence not in delivered


def test_a_value_is_never_reformatted() -> None:
    """`FR-044`: no rounding, no separator, no locale, no unit conversion."""
    payload = CORPUS["all four claim classes"]
    presentation = render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    assert "1234 un" in delivered, "the value was reformatted"
    assert "1.234" not in delivered and "1,234" not in delivered
    assert "-12.5 %" in delivered
    assert "-13" not in delivered and "-12,5" not in delivered
