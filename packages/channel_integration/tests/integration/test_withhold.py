"""Withhold totality — T093 (ADR 0022; FR-049, FR-050; SC-020, SC-065).

Everything that cannot be carried intact is withheld. **Zero truncation, zero sampling, zero
elision, zero partial delivery** — and the zeros are asserted structurally, because a truncation
helper that exists is a truncation helper someone will call.

Conditions driven here, each a real reason a payload cannot be carried:

1. the capability matrix does not resolve at all (`D-28` undeclared — the shipped state);
2. a single governed block exceeds the channel's declared maximum, so there is nothing to split;
3. the channel declares no ordering guarantee and the payload needs more than one fragment;
4. a wording reference has no resolved string (ADR 0026);
5. an empty block list reaches continuation.

Two conditions this file originally claimed to drive turned out to be **unconstructible
upstream**, and that is recorded rather than quietly dropped: `003`'s `CaveatSet` refuses a
declared count that disagrees with the caveats carried, and `AnalyticsAnswer` requires at least
one claim. So the tests for those assert the upstream impossibility — the stronger property — and
`004`'s own guards are exercised separately, at the level where they are actually reachable.
Claiming `004` protects against something `003` already prevents would be claiming credit for
someone else's gate.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from analytics_interaction.contracts.answer import CaveatSet
from pydantic import ValidationError

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.outbound import continuation as continuation_module
from channel_integration.outbound import render as render_module
from channel_integration.outbound.continuation import fragments_for
from channel_integration.outbound.degrade import FORBIDDEN_CONTENT_OPERATIONS
from channel_integration.outbound.render import render_answer, render_for_channel
from channel_integration.outbound.withhold import NotRepresentable

from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY, FixturePayload, answer_with

pytestmark = pytest.mark.integration

_ALL_FOUR = "all four claim classes"


def test_the_shipped_state_withholds_for_every_channel() -> None:
    """`D-28` undeclared: nothing renders, and the refusal is governed rather than an error."""
    for channel in ChannelId:
        outcome = render_for_channel(CORPUS[_ALL_FOUR], channel)
        assert isinstance(outcome, ChannelRefusal)
        assert outcome.code is ChannelReasonCode.CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE
        assert outcome.sender_text().strip(), "a withheld response still needs governed wording"


def test_a_block_larger_than_the_channel_maximum_withholds() -> None:
    """Nothing to split, so nothing is cut. The alternative would be truncation with a label."""
    capability = {**FIXTURE_CAPABILITY, "maximum_body_characters": 20}
    with pytest.raises(NotRepresentable) as caught:
        render_answer(CORPUS[_ALL_FOUR], ChannelId.SLACK, capability)
    assert "exceeds the channel" in str(caught.value)


def test_no_ordering_guarantee_withholds_when_more_than_one_fragment_is_needed() -> None:
    """`R-12`, `FR-059`. A "part 2 of 3" label is not a mitigation."""
    # Wide enough that each block fits alone, narrow enough that they cannot share a fragment.
    capability = {
        **FIXTURE_CAPABILITY,
        "maximum_body_characters": 260,
        "ordering_guarantee": "none",
    }
    with pytest.raises(NotRepresentable) as caught:
        render_answer(CORPUS[_ALL_FOUR], ChannelId.SLACK, capability)
    assert "ordering guarantee" in str(caught.value)


def test_the_same_payload_is_delivered_whole_when_ordering_is_guaranteed() -> None:
    """The complement: withholding must be caused by the missing guarantee, not by the size."""
    capability = {**FIXTURE_CAPABILITY, "maximum_body_characters": 260}
    presentation = render_answer(CORPUS[_ALL_FOUR], ChannelId.SLACK, capability)
    assert len(presentation.fragments) > 1
    assert [fragment.index for fragment in presentation.fragments] == list(
        range(1, len(presentation.fragments) + 1)
    )


def test_an_unresolved_reference_withholds_rather_than_rendering_the_reference() -> None:
    with pytest.raises(NotRepresentable):
        render_answer(
            CORPUS["an unresolved wording reference"], ChannelId.SLACK, FIXTURE_CAPABILITY
        )


def test_a_caveat_count_disagreement_is_unconstructible_upstream() -> None:
    """`FR-047`, and the upstream contract turns out to be the stronger guard.

    `004`'s renderer checks that the declared count matches the caveats carried, and that check is
    real — but a payload that disagrees cannot be built at all: `003`'s `CaveatSet` refuses it,
    with a message that already names withholding as the consequence.

    So this asserts the upstream impossibility rather than `004`'s check, because that is the
    property that actually holds. `004`'s check remains as defence in depth against a future
    payload shape that is assembled differently, and this docstring says so rather than letting
    the renderer's guard look like the only thing standing between a reader and a missing caveat.
    """
    carried = CORPUS[_ALL_FOUR].answer.caveats.caveats
    with pytest.raises(ValidationError) as caught:
        CaveatSet(caveats=carried, total=len(carried) + 97)
    assert "disagrees with the" in str(caught.value)


def test_the_renderer_still_refuses_a_disagreeing_count_when_handed_one() -> None:
    """Defence in depth, exercised at the level where it lives.

    The renderer is handed a caveat set whose ``total`` was bypassed by constructing it without
    validation, which is the only way to reach `004`'s own check. If the upstream guard were ever
    relaxed, this is the test that would still fail.
    """
    original = CORPUS[_ALL_FOUR]
    carried = original.answer.caveats.caveats
    lying_set = CaveatSet.model_construct(caveats=carried, total=len(carried) + 1)
    lying_answer = original.answer.model_copy(update={"caveats": lying_set})
    payload = FixturePayload(lying_answer, original.wording)
    with pytest.raises(NotRepresentable) as caught:
        render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    assert "caveat count" in str(caught.value)


def test_an_answer_with_no_claims_is_unconstructible_upstream() -> None:
    """The same shape of finding: `003` requires at least one claim.

    `004`'s continuation refuses an empty block list, and that refusal is asserted directly below
    because it is reachable at its own level. An empty *answer*, though, cannot exist — so claiming
    `004` protects against one would be claiming credit for a guard upstream already holds.
    """
    with pytest.raises(ValidationError):
        answer_with((), 1, CORPUS[_ALL_FOUR].answer.provenance)


def test_continuation_refuses_an_empty_block_list_at_its_own_level() -> None:
    """`004`'s own guard, reached directly rather than through an impossible payload."""
    with pytest.raises(NotRepresentable) as caught:
        fragments_for((), FIXTURE_CAPABILITY)
    assert "nothing to render" in str(caught.value)


def test_no_truncation_path_exists_anywhere_in_the_package() -> None:
    """`SC-065`, structurally, across the whole package.

    The list is imported from `outbound.degrade` so the scan cannot drift from the rule. Scanned
    over identifiers rather than raw text, so a docstring may name ``truncate`` while a function
    may not be called it — the modules have to be able to explain what they refuse to do.
    """
    root = Path(inspect.getfile(render_module)).resolve().parents[1]
    offenders: list[str] = []
    for source in sorted(root.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        for identifier in defined | called:
            for forbidden in FORBIDDEN_CONTENT_OPERATIONS:
                if forbidden in identifier.lower():
                    offenders.append(f"{source.relative_to(root)}: {identifier}")
    assert not offenders, offenders


def test_continuation_never_slices_a_block() -> None:
    """A slice over a governed string is truncation, whatever it is called.

    Asserted over the continuation module's syntax: no subscript with a slice appears in it, so
    there is no expression that could take part of a block.
    """
    source = Path(inspect.getfile(continuation_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    slices = [node for node in ast.walk(tree) if isinstance(node, ast.Slice)]
    assert not slices, "continuation contains a slice expression"
