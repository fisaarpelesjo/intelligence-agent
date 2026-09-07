"""Four-way reason-code disjointness — T014 (ADR 0018; SC-060).

The claim that makes a single ``code`` field safe: a consumer switches on one string
without asking which of the four layers produced it. Asserted pairwise rather than by
one big union, because a union that happened to be the right size could still hide two
namespaces sharing a member with a third.
"""

from __future__ import annotations

import pytest
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from channel_integration.contracts.reason_codes import ChannelReasonCode

pytestmark = pytest.mark.contract

_NAMESPACES = {
    "001 ReasonCode": frozenset(code.value for code in ReasonCode),
    "002 AnalyticsReasonCode": frozenset(code.value for code in AnalyticsReasonCode),
    "003 InterpretationReasonCode": frozenset(code.value for code in InterpretationReasonCode),
    "004 ChannelReasonCode": frozenset(code.value for code in ChannelReasonCode),
}


#: The six unordered pairs. Enumerated rather than filtered from a product, so the suite
#: reports **zero skips**: a skipped diagonal comparison is an unrun check displayed as a
#: passing one, which is the same defect as a warning gate.
_PAIRS = tuple(
    (left, right)
    for index, left in enumerate(sorted(_NAMESPACES))
    for right in sorted(_NAMESPACES)[index + 1 :]
)


def test_every_unordered_pair_is_covered() -> None:
    """Four namespaces, six pairs. A missing pair would hide a shared member."""
    assert len(_PAIRS) == 6
    assert len({frozenset(pair) for pair in _PAIRS}) == 6


@pytest.mark.parametrize(("left", "right"), _PAIRS)
def test_namespaces_are_pairwise_disjoint(left: str, right: str) -> None:
    shared = _NAMESPACES[left] & _NAMESPACES[right]
    assert not shared, f"{left} and {right} share: {sorted(shared)}"


def test_the_four_namespaces_have_their_declared_sizes() -> None:
    """Sizes are asserted so a silent addition to any of them is visible here.

    `001` is closed at 41, `002` at 25, `003` at 32. `004` declares 31 (ADR 0018), and
    a 32nd is a new decision rather than an addition — a change here is the first place
    that would show.
    """
    assert len(_NAMESPACES["001 ReasonCode"]) == 41
    assert len(_NAMESPACES["002 AnalyticsReasonCode"]) == 25
    assert len(_NAMESPACES["003 InterpretationReasonCode"]) == 32
    assert len(_NAMESPACES["004 ChannelReasonCode"]) == 31


def test_no_channel_code_restates_an_upstream_condition() -> None:
    """Ownership rule: a channel code names a condition no upstream layer observes.

    Checked structurally rather than semantically — a semantic check would need a
    judgement this test cannot make. What it can prove: no channel code reuses an
    upstream code's **name**, and none of the upstream vocabularies' distinctive words
    for conditions this layer must pass through appear in a channel code.
    """
    upstream = (
        _NAMESPACES["001 ReasonCode"]
        | _NAMESPACES["002 AnalyticsReasonCode"]
        | _NAMESPACES["003 InterpretationReasonCode"]
    )
    for code in ChannelReasonCode:
        assert code.value not in upstream
    # Conditions that belong upstream and must be passed through, never restated
    # (`FR-045`). A channel code naming one of these would be this layer forming its
    # own opinion about a decision it does not own.
    forbidden_stems = (
        "METRIC",
        "DIMENSION",
        "FRESHNESS",
        "COVERAGE",
        "SUPPRESS",
        "COMPARAB",
        "GRAIN",
        "RETENTION",
        "DRY_RUN",
        "COST",
        "TERM_",
        "PERIOD_",
        "CLARIFICATION",
    )
    for code in ChannelReasonCode:
        for stem in forbidden_stems:
            assert stem not in code.value, f"{code.value} restates an upstream condition"
