"""Caveat integrity, over generated sets — T159 (FR-084; SC-047).

    Every `ALLOW_WITH_CAVEAT` caveat MUST survive byte-identically, attributed to
    its origin, with every occurrence preserved. — `FR-084`

    Evidence: byte-identity, origin attribution and non-deduplication hold across
    generated caveat sets. — `tasks.md` T159

## Three properties, three different failures

**Byte-identity.** The wording is upstream's, carried verbatim. Rewriting it —
softening "cobertura parcial" to "dados aproximados", or normalising whitespace —
changes a governed disclosure into this feature's paraphrase of one. Asserted as
byte equality on the exact string, generated over wording that includes the things
a normaliser would touch: leading spaces, doubled spaces, newlines, accents in both
Unicode compositions.

**Origin attribution.** A caveat from side B attributed to the verdict tells a
reader the whole comparison is qualified when one side is, or the reverse. Origins
are carried per occurrence and never merged.

**Multiplicity.** The dangerous one, because deduplication is a *reasonable-looking*
edit. Two identical caveats with the same code and the same origin may represent two
decisions, two evaluations or two pieces of evidence, and this layer cannot tell
which — so it carries the count. A `set` anywhere on the path collapses them
silently, and the reader is told once about something stated twice.

## Why generated rather than tabulated

The multiplicity property is about *counts*, and counts are where a table stops
being convincing: a fixture with two duplicates proves nothing about seven. Generated
multisets cover the shapes a naive implementation collapses — all-identical, identical
except origin, identical except one character of wording, interleaved across groups.

Bounded and fixture-only: a handful of governed codes, a handful of authored
wordings, at most a dozen occurrences. Nothing here infers how often real caveats
repeat.
"""

from __future__ import annotations

import unicodedata
from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.answer.caveats import carry_caveats
from analytics_interaction.answer.withhold import assert_caveats_are_releasable
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.answer import AttributedCaveat, CaveatOrigin, CaveatSet

pytestmark = pytest.mark.property

SETTINGS = settings(max_examples=250, deadline=None)

#: Governed codes upstream can state. **Fixture-only** and small: the property is
#: about carriage, not about how many codes exist.
CODES = st.sampled_from(
    [
        ReasonCode.COMPARABLE_WITH_CAVEAT,
        ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE,
        ReasonCode.EQUIVALENT_PARTIAL_COMPARISON,
        ReasonCode.REPRODUCIBILITY_LIMITED,
    ]
)

ORIGINS = st.sampled_from(list(CaveatOrigin))

#: Wording that includes everything a normaliser would want to touch: a leading
#: space, a doubled space, a trailing newline, an accent in NFC and the same accent
#: in NFD. Each must survive byte-for-byte.
WORDINGS = st.sampled_from(
    [
        "cobertura parcial",
        " cobertura parcial",
        "cobertura  parcial",
        "cobertura parcial\n",
        "fonte com atraso tolerado",
        unicodedata.normalize("NFC", "período reproduzível com limitações"),
        unicodedata.normalize("NFD", "período reproduzível com limitações"),
        "COBERTURA PARCIAL",
    ]
)


@st.composite
def caveats(
    draw: st.DrawFn, *, min_size: int = 1, max_size: int = 8
) -> tuple[AttributedCaveat, ...]:
    """A bounded multiset of attributed caveats, duplicates permitted.

    Drawn as a list without ``unique``, on purpose: duplicates are the interesting
    case and a unique strategy would generate exactly the corpus that cannot fail.
    """
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    return tuple(
        AttributedCaveat(code=draw(CODES), message_pt_br=draw(WORDINGS), origin=draw(ORIGINS))
        for _ in range(size)
    )


def _multiset(caveat_set: CaveatSet) -> Counter[tuple[str, str, str]]:
    """Code, origin and wording, counted. The whole identity of an occurrence."""
    return Counter(
        (str(caveat.code), caveat.origin.value, caveat.message_pt_br)
        for caveat in caveat_set.caveats
    )


# --- property 1: nothing is deduplicated ----------------------------------------


@SETTINGS
@given(group=caveats())
def test_every_occurrence_is_carried(group: tuple[AttributedCaveat, ...]) -> None:
    """**The load-bearing property.** Count in, count out.

    Asserted as a multiset rather than a length, because a length can be preserved
    by an implementation that dropped one duplicate and added something else.
    """
    carried = carry_caveats(group)
    assert _multiset(carried) == Counter(
        (str(caveat.code), caveat.origin.value, caveat.message_pt_br) for caveat in group
    )
    assert len(carried.caveats) == len(group)


@SETTINGS
@given(group=caveats())
def test_the_total_counts_occurrences_not_distinct_pairs(
    group: tuple[AttributedCaveat, ...],
) -> None:
    """``total`` is occurrences carried, never distinct ``(code, origin)`` pairs.

    Generated sets routinely contain repeats, so ``total`` and the distinct count
    genuinely differ — which is what makes this assertion able to fail. A corpus of
    all-unique caveats would satisfy both readings.
    """
    carried = carry_caveats(group)
    assert carried.total == len(group)
    assert carried.total == len(carried.caveats)


@SETTINGS
@given(code=CODES, origin=ORIGINS, wording=WORDINGS, repeats=st.integers(1, 7))
def test_n_identical_caveats_produce_a_total_of_n(
    code: ReasonCode, origin: CaveatOrigin, wording: str, repeats: int
) -> None:
    """The exact shape a ``set`` collapses to one.

    Same code, same origin, same wording, `n` times. There is no reading of this
    input under which a set-based implementation survives.
    """
    group = tuple(
        AttributedCaveat(code=code, message_pt_br=wording, origin=origin) for _ in range(repeats)
    )
    carried = carry_caveats(group)
    assert carried.total == repeats
    assert len(carried.caveats) == repeats


@SETTINGS
@given(first=caveats(), second=caveats(), third=caveats())
def test_multiplicity_survives_across_groups(
    first: tuple[AttributedCaveat, ...],
    second: tuple[AttributedCaveat, ...],
    third: tuple[AttributedCaveat, ...],
) -> None:
    """Three groups, concatenated. Duplicates *across* groups are still duplicates.

    The plausible bug is deduplicating at the seam — collapsing what side A and
    side B independently stated, on the grounds that it is "the same caveat". It is
    the same caveat stated by two origins about two sides.
    """
    carried = carry_caveats(first, second, third)
    assert carried.total == len(first) + len(second) + len(third)
    assert _multiset(carried) == (
        Counter((str(c.code), c.origin.value, c.message_pt_br) for c in first + second + third)
    )


# --- property 2: wording is byte-identical --------------------------------------


@SETTINGS
@given(group=caveats())
def test_every_wording_survives_byte_for_byte(group: tuple[AttributedCaveat, ...]) -> None:
    """No trimming, no whitespace collapse, no case change, no recomposition.

    Compared as encoded bytes, not as strings, so an NFC/NFD change — which two
    Python strings can differ by while looking identical in a diff — is visible.
    """
    carried = carry_caveats(group)
    for original, kept in zip(group, carried.caveats, strict=True):
        assert kept.message_pt_br == original.message_pt_br
        assert kept.message_pt_br.encode() == original.message_pt_br.encode()


@SETTINGS
@given(group=caveats())
def test_nothing_is_reordered(group: tuple[AttributedCaveat, ...]) -> None:
    """Encounter order, preserved.

    Not cosmetic: sorting occurrences with no total order between them needs a
    tiebreaker, and the obvious tiebreaker is the collapse this path exists not to
    perform. Order preservation is how the absence of that sort is observable.
    """
    carried = carry_caveats(group)
    assert [(str(c.code), c.origin.value, c.message_pt_br) for c in carried.caveats] == [
        (str(c.code), c.origin.value, c.message_pt_br) for c in group
    ]


# --- property 3: origins are per-occurrence and never merged --------------------


@SETTINGS
@given(code=CODES, wording=WORDINGS)
def test_the_same_caveat_from_two_origins_stays_two_caveats(code: ReasonCode, wording: str) -> None:
    """Side A and side B each stated it. The reader is told twice, correctly.

    Merging them would report a comparison-wide qualification where two per-side
    ones exist — or, worse, attribute a side-B limitation to the verdict, which
    describes the whole answer.
    """
    group = (
        AttributedCaveat(code=code, message_pt_br=wording, origin=CaveatOrigin.SIDE_A),
        AttributedCaveat(code=code, message_pt_br=wording, origin=CaveatOrigin.SIDE_B),
    )
    carried = carry_caveats(group)
    assert carried.total == 2
    assert {caveat.origin for caveat in carried.caveats} == {
        CaveatOrigin.SIDE_A,
        CaveatOrigin.SIDE_B,
    }


@SETTINGS
@given(group=caveats())
def test_every_origin_is_carried_unchanged(group: tuple[AttributedCaveat, ...]) -> None:
    """Per occurrence, not per code."""
    carried = carry_caveats(group)
    assert [c.origin for c in carried.caveats] == [c.origin for c in group]


# --- the release gate counts, and does not set-compare -------------------------


@SETTINGS
@given(group=caveats())
def test_a_complete_set_is_releasable(group: tuple[AttributedCaveat, ...]) -> None:
    """The control. Without it, universal refusal would look like a working gate."""
    carried = carry_caveats(group)
    required = [(str(caveat.code), caveat.origin) for caveat in group]
    assert assert_caveats_are_releasable(carried, required=required) is None


@SETTINGS
@given(code=CODES, origin=ORIGINS, wording=WORDINGS, wanted=st.integers(2, 6))
def test_a_repeated_requirement_carried_once_is_withheld(
    code: ReasonCode, origin: CaveatOrigin, wording: str, wanted: int
) -> None:
    """**The assertion a set-based gate fails.**

    Upstream stated it `n` times; one occurrence is carried. A set comparison sees
    the code present and releases — and the reader is told once about something
    stated `n` times.
    """
    carried = carry_caveats((AttributedCaveat(code=code, message_pt_br=wording, origin=origin),))
    with pytest.raises(ContractViolation) as raised:
        assert_caveats_are_releasable(carried, required=[(str(code), origin)] * wanted)
    assert "withheld in full" in str(raised.value)


@SETTINGS
@given(group=caveats(min_size=2), extra=CODES, extra_origin=ORIGINS)
def test_a_missing_requirement_is_withheld(
    group: tuple[AttributedCaveat, ...], extra: ReasonCode, extra_origin: CaveatOrigin
) -> None:
    """One more required than carried, whatever the set already contains."""
    carried = carry_caveats(group)
    required = [(str(caveat.code), caveat.origin) for caveat in group]
    required.append((str(extra), extra_origin))
    wanted = Counter(required)
    have = Counter((str(c.code), c.origin) for c in carried.caveats)
    if all(have[key] >= count for key, count in wanted.items()):
        # The extra happened to already be carried enough times; not a gap.
        assert assert_caveats_are_releasable(carried, required=required) is None
        return
    with pytest.raises(ContractViolation):
        assert_caveats_are_releasable(carried, required=required)


@SETTINGS
@given(group=caveats())
def test_the_withholding_refusal_names_no_code_or_origin(
    group: tuple[AttributedCaveat, ...],
) -> None:
    """A refusal listing them would disclose which limitations applied.

    Including, on a comparison, facts about a side the caller may not have access
    to — through the error path, where nobody was looking for a disclosure.
    """
    carried = carry_caveats(group)
    required = [(str(caveat.code), caveat.origin) for caveat in group]
    required.append(("A_CODE_NOBODY_CARRIED", CaveatOrigin.VERDICT))
    with pytest.raises(ContractViolation) as raised:
        assert_caveats_are_releasable(carried, required=required)
    message = str(raised.value)
    assert "A_CODE_NOBODY_CARRIED" not in message
    for caveat in group:
        assert str(caveat.code) not in message
        assert caveat.message_pt_br.strip() not in message or not caveat.message_pt_br.strip()


@SETTINGS
@given(group=caveats())
def test_a_disagreeing_total_cannot_even_be_constructed(
    group: tuple[AttributedCaveat, ...],
) -> None:
    """**Stronger than the release gate**: the set does not exist to be released.

    ``CaveatSet``'s own validator refuses a total that disagrees with the caveats
    carried, so a lying set is unrepresentable rather than merely unreleasable. The
    equivalent check inside ``assert_caveats_are_releasable`` is defence in depth
    for a set that arrived some other way, and it is asserted separately below by
    calling the gate's own comparison directly.

    Both directions, because an off-by-one in either is the same class of bug: a
    total that over-counts suggests a caveat the reader never saw, and one that
    under-counts hides one they should have.
    """
    for total in (len(group) + 1, len(group) - 1):
        if total < 0:
            continue
        with pytest.raises(ValidationError) as raised:
            CaveatSet(caveats=group, total=total)
        assert "disagrees" in str(raised.value)


@SETTINGS
@given(group=caveats())
def test_a_blank_wording_is_withheld(group: tuple[AttributedCaveat, ...]) -> None:
    """A caveat with no wording is a disclosure nobody can read.

    Released, it would appear in the count and say nothing — which is worse than a
    refusal, because the count would suggest the reader had been told.
    """
    blank = AttributedCaveat(
        code=ReasonCode.COMPARABLE_WITH_CAVEAT, message_pt_br="   ", origin=CaveatOrigin.VERDICT
    )
    carried = carry_caveats(group, (blank,))
    required = [(str(c.code), c.origin) for c in carried.caveats]
    with pytest.raises(ContractViolation) as raised:
        assert_caveats_are_releasable(carried, required=required)
    assert "no governed wording" in str(raised.value)


# --- no collapsing container is reachable --------------------------------------


def test_the_carrier_returns_a_sequence_not_a_set() -> None:
    """Structural. A ``frozenset`` field could not hold duplicates at all.

    Asserted on the type rather than on behaviour, so a change of container fails
    here rather than as a mysterious count mismatch in a suite three files away.
    """
    group = (
        AttributedCaveat(
            code=ReasonCode.COMPARABLE_WITH_CAVEAT,
            message_pt_br="cobertura parcial",
            origin=CaveatOrigin.VERDICT,
        ),
    ) * 3
    carried = carry_caveats(group)
    assert isinstance(carried.caveats, tuple)
    assert carried.total == 3
