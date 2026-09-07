"""The four claim classes stay distinguishable — T091 (ADR 0022; FR-048; SC-022).

`003` types every answer element as `FACTUAL_RESULT`, `CALCULATED_COMPARISON`, `INTERPRETATION` or
`LIMITATION`, precisely so an interpretation cannot read as a finding. After rendering, the four
must remain distinguishable **without inference by the reader**.

"Without inference" is the load-bearing phrase, and it rules out three tempting shortcuts:

* **position** is not a label — a reader cannot know that the third paragraph is the interpretation;
* **an emoji** is not governed content — nobody approved it, and it means different things to
  different readers;
* **colour or emphasis** is not available on every channel and is not content at all.

So the distinction must be carried by a **governed label** from the capability matrix, and a
matrix that declares a label for only some of the four cannot keep the rest distinguishable —
which is why a partial label set **withholds** rather than rendering three quarters of the
distinction.

The label mapping (`CLAIM_CLASS_LABEL_KEYS`) is imported rather than retyped, so this test and the
renderer cannot disagree about which matrix key belongs to which class.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from analytics_interaction.contracts.answer import ClaimClass

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.outbound.preserve import strip_structure
from channel_integration.outbound.render import (
    BULLET_PREFIX,
    CLAIM_CLASS_LABEL_KEYS,
    claim_labels,
    render_answer,
)
from channel_integration.outbound.withhold import NotRepresentable

from ..fixtures.payloads import (
    CORPUS,
    FIXTURE_CAPABILITY,
    INTERNAL_METRIC_ID,
    INTERNAL_SUBJECT_ENTRY,
    ROW_LABEL_SUBJECT,
)

pytestmark = pytest.mark.contract

_ALL_FOUR = "all four claim classes"


def test_the_enum_has_exactly_four_members() -> None:
    """A fifth class would be a contract change upstream, not a content change."""
    assert len(ClaimClass) == 4
    assert set(CLAIM_CLASS_LABEL_KEYS) == set(ClaimClass)


@pytest.mark.parametrize("channel", list(ChannelId))
def test_every_class_present_in_the_payload_carries_its_governed_label(
    channel: ChannelId,
) -> None:
    """`SC-022`, per channel: four classes, four labels, all in the delivered bytes."""
    payload = CORPUS[_ALL_FOUR]
    presentation = render_answer(payload, channel, FIXTURE_CAPABILITY)
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    labels = claim_labels(FIXTURE_CAPABILITY)
    for claim in payload.answer.claims:
        assert labels[claim.claim_class] in delivered, (
            f"{channel.value}: {claim.claim_class.value} lost its label"
        )


def test_the_four_labels_are_distinct() -> None:
    """Four classes sharing a label would be four classes a reader cannot tell apart."""
    labels = claim_labels(FIXTURE_CAPABILITY)
    assert len(set(labels.values())) == 4


def _groups_by_label(delivered: str, labels: Mapping[ClaimClass, str]) -> dict[ClaimClass, str]:
    """The delivered body cut into the label-headed groups `F99` introduced.

    Asserting the property rather than the layout. The old node matched the literal
    ``{label}: {subject}`` a claim used to render as, which tied it to a shape the owner has
    now changed; what it was really defending is that an interpretation's text sits under the
    interpretation's label and nowhere near the factual one. That survives any layout, so this
    reads the groups and lets the caller ask which one a string fell into.

    Anything before the first label belongs to no group and is dropped. There is nothing there
    today, and attributing it to the first class would hide the day there is.
    """
    marks = sorted(
        (delivered.index(f"{label}:"), claim_class) for claim_class, label in labels.items()
    )
    groups: dict[ClaimClass, str] = {}
    for position, (start, claim_class) in enumerate(marks):
        end = marks[position + 1][0] if position + 1 < len(marks) else len(delivered)
        groups[claim_class] = delivered[start:end]
    return groups


def test_an_interpretation_is_not_presented_as_a_finding() -> None:
    """The failure this whole rule exists to prevent, asserted directly.

    The interpretation claim's text must appear beside the interpretation label and **not** beside
    the factual one, so a reader scanning for results cannot pick it up as one.
    """
    payload = CORPUS[_ALL_FOUR]
    presentation = render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    labels = claim_labels(FIXTURE_CAPABILITY)

    interpretation = next(
        claim for claim in payload.answer.claims if claim.claim_class is ClaimClass.INTERPRETATION
    )
    groups = _groups_by_label(delivered, labels)
    assert interpretation.subject in groups[ClaimClass.INTERPRETATION]
    assert interpretation.subject not in groups[ClaimClass.FACTUAL_RESULT]


@pytest.mark.parametrize("missing_key", sorted(CLAIM_CLASS_LABEL_KEYS.values()))
def test_a_partial_label_set_withholds(missing_key: str) -> None:
    """Removing any one of the four labels must withhold, not degrade.

    Parametrised over all four rather than testing one, because "we check the labels" is easy to
    satisfy for the first one and forget for the fourth.
    """
    declared = cast("dict[str, str]", FIXTURE_CAPABILITY["claim_class_labels"])
    labels = dict(declared)
    del labels[missing_key]
    capability = {**FIXTURE_CAPABILITY, "claim_class_labels": labels}
    with pytest.raises(NotRepresentable) as caught:
        render_answer(CORPUS[_ALL_FOUR], ChannelId.SLACK, capability)
    assert "claim class" in str(caught.value)


def test_a_matrix_with_no_labels_at_all_withholds() -> None:
    capability = {
        key: value for key, value in FIXTURE_CAPABILITY.items() if key != "claim_class_labels"
    }
    with pytest.raises(NotRepresentable):
        render_answer(CORPUS[_ALL_FOUR], ChannelId.SLACK, capability)


def test_no_emoji_or_colour_carries_the_distinction() -> None:
    """The shortcuts, asserted as absent rather than described as forbidden."""
    presentation = render_answer(CORPUS[_ALL_FOUR], ChannelId.SLACK, FIXTURE_CAPABILITY)
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    for character in delivered:
        assert ord(character) < 0x2190, f"a symbol carries meaning: {character!r}"
    for token in ("\x1b[", "color:", "style=", "<b>", "**"):
        assert token not in delivered


# --- F98: the label line, and which subject is allowed onto it -------------------------------


def _internal_subject_body() -> str:
    """The seventh corpus entry, rendered. One place, so the three nodes cannot drift apart."""
    presentation = render_answer(
        CORPUS[INTERNAL_SUBJECT_ENTRY], ChannelId.SLACK, FIXTURE_CAPABILITY
    )
    return (chr(10) * 2).join(fragment.body for fragment in presentation.fragments)


def test_the_metrics_internal_identifier_is_not_on_the_label_line() -> None:
    """`F97`'s property, defended inside the package rather than only by the harness.

    **`F98`, and it is a real gap and not a formality.** The reviewer planted `subject_is_internal`
    returning `False` -- the leak coming back whole -- and every one of the 425 renderer nodes in
    this package passed, because `interpreted.metrics` was empty in all six corpus entries so no
    subject could ever be internal. Only the harness caught it. The doctrine here is that deleting
    `apps/telegram-bot` must not break production; before this node,
    deleting it left the owner's correction with no defence at all.
    """
    assert INTERNAL_METRIC_ID not in _internal_subject_body(), (
        "the metric's internal identifier is on the label line the reader sees; the governed label "
        "is what belongs there"
    )


def test_a_row_label_is_still_shown() -> None:
    """The half that must NOT go with it, and the reason this entry carries two claims.

    The first attempt at `F97` dropped every subject unconditionally and deleted `Android` and `iOS`
    from a real breakdown, leaving two identical labels above two numbers with nothing saying which
    was which. A node asserting only the absence above would have called that a success.
    """
    assert ROW_LABEL_SUBJECT in _internal_subject_body(), (
        f"{ROW_LABEL_SUBJECT!r} left the body with the identifier, so the reader can no longer "
        "tell which figure belongs to which row"
    )


def test_the_governed_label_still_carries_the_class() -> None:
    """Suppressing the subject must not suppress the distinction `T091` exists to keep."""
    body = _internal_subject_body()
    labels = claim_labels(FIXTURE_CAPABILITY)
    assert labels[ClaimClass.FACTUAL_RESULT] in body


# --- F99: the bullet, and what the gate must still refuse -------------------------------------


def _delivered_body(name: str = _ALL_FOUR) -> str:
    presentation = render_answer(CORPUS[name], ChannelId.SLACK, FIXTURE_CAPABILITY)
    return "\n\n".join(fragment.body for fragment in presentation.fragments)


def test_the_class_label_is_written_once_for_a_group_of_claims() -> None:
    """**`F99`.** The owner's objection, asserted on the delivered body.

    Every claim used to open with its own label, so a reader met "resultado medido" above every
    figure. Now the label opens the group and the claims follow as bullets.

    The corpus entry used here carries **two** factual claims, which is the only shape that can tell
    the two apart: with one claim per class, "once per group" and "once per claim" are the same
    string and a node cannot distinguish them.
    """
    body = _delivered_body(INTERNAL_SUBJECT_ENTRY)
    label = claim_labels(FIXTURE_CAPABILITY)[ClaimClass.FACTUAL_RESULT]
    assert body.count(f"{label}:") == 1, (
        f"the label {label!r} appears {body.count(f'{label}:')} times for two claims of one class, "
        "so it is still being written per claim"
    )
    assert body.count(BULLET_PREFIX) == 2, "each of the two claims should be one bullet"


def test_every_claim_line_opens_with_the_bullet_the_owner_approved() -> None:
    """The character is his decision, not a default.

    "-" is the one that renders identically in Telegram, WhatsApp, Slack and an arbitrary webhook
    consumer; a Unicode bullet was never measured across the four. So the node asserts the exact
    character rather than "some bullet".
    """
    labels = set(claim_labels(FIXTURE_CAPABILITY).values())
    lines = [line for line in _delivered_body().split("\n") if line]
    claim_lines = [
        line for line in lines if not any(line.startswith(f"{label}:") for label in labels)
    ]
    assert claim_lines, "no claim lines at all, so this node proves nothing"
    bulleted = [line for line in claim_lines if line.startswith(BULLET_PREFIX)]
    # The caveat block travels outside the claim groups and is not bulleted; it is excluded by
    # asking that every line which is NOT a caveat be bulleted, rather than by counting.
    caveats = {caveat.message_pt_br for caveat in CORPUS[_ALL_FOUR].answer.caveats.caveats}
    for line in claim_lines:
        if line in caveats:
            continue
        assert line in bulleted, f"a claim line does not open with the bullet: {line!r}"


def test_the_gate_still_refuses_a_hyphen_that_is_not_the_bullet() -> None:
    """**The load-bearing node of `F99`, and it is not about the bullet.**

    `PERMITTED_SEPARATORS` exists so the differential check NOTICES a character nobody authorised.
    Every character added there is one the gate stops seeing, for ever, in every answer on every
    channel. The obvious way to ship a "-" bullet was to add it -- and measured, that is what it
    would have cost:

    ======================================  ======  =============  ==============
    invented content                        before  "-" permitted  bullet prefix
    ======================================  ======  =============  ==============
    a SIGN invented on a real figure        caught  **blind**      caught
    a divider of nothing but dashes         caught  **blind**      caught
    a hyphen inside invented prose          caught  caught         caught
    ======================================  ======  =============  ==============

    The first row decides it: stripping every "-" turns an invented ``-1234`` into the governed
    ``1234``, and a fall would be delivered where a rise was measured with nothing left over for the
    gate to see. The approved format carries signed differences, so a sign is content here.

    So the bullet is stripped as a prefix at the start of a line, and this node holds that narrowing
    in place from the outside: each case below is invented text, and each must survive as residue.
    """
    for description, invented in (
        ("a sign invented on a figure", "-1234"),
        ("a divider of dashes", "-----"),
        ("a hyphen inside prose", "nota - inventada"),
        ("a bullet with invented prose behind it", "- nota inventada"),
    ):
        assert strip_structure(invented), (
            f"{description}: the gate no longer sees {invented!r} as content nobody authorised"
        )


def test_the_bullet_itself_is_not_reported_as_invented() -> None:
    """The other direction, so the narrowing is not simply a refusal of everything."""
    assert strip_structure(f"{BULLET_PREFIX}") == "", (
        "the bullet the renderer is allowed to emit is being reported as invented content"
    )
