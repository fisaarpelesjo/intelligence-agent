"""Continuation — T095 (`R-12`; FR-058, FR-059; SC-020).

Three properties, and the third is the one that makes a continuation safe rather than merely tidy:

* fragments are **ordered and complete** — exactly ``1..total``, in order, no gap, no repeat;
* **no ordering guarantee means withhold**, because a reader who receives fragment three first has
  been handed the end of an answer as though it were the whole of one;
* **no fragment stands alone without its caveats** — the caveat block travels in *every* fragment,
  so
  the first fragment cannot read as an uncaveated finding.

The third costs repetition, and that cost is accepted deliberately: a repeated caveat is noise, a
missing one is a false claim.

A single governed block that does not fit is **not** split. There is nothing to split it into that
would still be the governed string, so the response withholds.
"""

from __future__ import annotations

import pytest

from channel_integration.outbound.continuation import (
    ORDERING_GUARANTEED,
    fragments_for,
    maximum_body_characters,
    ordering_is_guaranteed,
)
from channel_integration.outbound.withhold import NotRepresentable

from ..fixtures.payloads import FIXTURE_CAPABILITY

pytestmark = pytest.mark.unit

_CAVEATS = "ressalva um\nressalva dois"


def _capability(limit: int, ordering: str = "ordered") -> dict[str, object]:
    return {**FIXTURE_CAPABILITY, "maximum_body_characters": limit, "ordering_guarantee": ordering}


def test_one_small_block_is_one_fragment() -> None:
    fragments = fragments_for(("bloco governado",), _capability(4000))
    assert len(fragments) == 1
    assert fragments[0].index == 1 and fragments[0].total == 1


def test_blocks_that_do_not_fit_together_become_ordered_fragments() -> None:
    blocks = tuple(f"bloco governado numero {index}" for index in range(1, 6))
    fragments = fragments_for(blocks, _capability(60), repeated_suffix=_CAVEATS)
    assert len(fragments) > 1
    assert [fragment.index for fragment in fragments] == list(range(1, len(fragments) + 1))
    assert all(fragment.total == len(fragments) for fragment in fragments)


def test_every_fragment_carries_the_repeated_caveat_block() -> None:
    """`FR-047` through continuation: no fragment stands alone as an uncaveated finding."""
    blocks = tuple(f"bloco governado numero {index}" for index in range(1, 6))
    fragments = fragments_for(blocks, _capability(60), repeated_suffix=_CAVEATS)
    assert len(fragments) > 1
    for fragment in fragments:
        assert _CAVEATS in fragment.body, f"fragment {fragment.index} lost its caveats"


def test_no_governed_block_is_split_across_fragments() -> None:
    """Fragments break **between** blocks. A block is never cut."""
    blocks = tuple(f"bloco-{index}-integro" for index in range(1, 8))
    fragments = fragments_for(blocks, _capability(60))
    delivered = "\n\n".join(fragment.body for fragment in fragments)
    for block in blocks:
        assert block in delivered, f"{block} was cut"


def test_a_single_block_larger_than_the_limit_withholds() -> None:
    with pytest.raises(NotRepresentable) as caught:
        fragments_for(
            ("um bloco governado bem mais longo do que o limite deste canal",), _capability(20)
        )
    assert "exceeds the channel" in str(caught.value)


def test_a_block_that_fits_only_without_its_caveats_withholds() -> None:
    """The caveats are not optional, so "it would fit without them" is not a way to fit."""
    block = "bloco governado de tamanho medio"
    assert len(block) < 60
    with pytest.raises(NotRepresentable):
        fragments_for((block,), _capability(40), repeated_suffix=_CAVEATS)


@pytest.mark.parametrize("declared", sorted(ORDERING_GUARANTEED))
def test_a_declared_guarantee_permits_a_continuation(declared: str) -> None:
    blocks = tuple(f"bloco governado numero {index}" for index in range(1, 5))
    fragments = fragments_for(blocks, _capability(60, declared))
    assert len(fragments) > 1


@pytest.mark.parametrize("declared", ["", "none", "best-effort", "probably", "unordered", "FIFO?"])
def test_an_undeclared_or_unrecognised_guarantee_withholds_a_continuation(declared: str) -> None:
    """Silence is not a guarantee, and neither is an unrecognised word."""
    blocks = tuple(f"bloco governado numero {index}" for index in range(1, 5))
    with pytest.raises(NotRepresentable) as caught:
        fragments_for(blocks, _capability(60, declared))
    assert "ordering guarantee" in str(caught.value)


def test_a_single_fragment_needs_no_ordering_guarantee() -> None:
    """One message cannot arrive out of order, so the rule does not over-reach."""
    fragments = fragments_for(("bloco curto",), _capability(4000, "none"))
    assert len(fragments) == 1


def test_the_guarantee_check_is_case_insensitive_but_closed() -> None:
    assert ordering_is_guaranteed({"ordering_guarantee": "ORDERED"})
    assert ordering_is_guaranteed({"ordering_guarantee": " fifo "})
    assert not ordering_is_guaranteed({"ordering_guarantee": "ordered-ish"})
    assert not ordering_is_guaranteed({})


@pytest.mark.parametrize("declared", [0, -1, "4000", None, True])
def test_a_missing_or_malformed_maximum_refuses_rather_than_being_guessed(
    declared: object,
) -> None:
    """A guessed ceiling would be a governed value this feature authored."""
    with pytest.raises(NotRepresentable) as caught:
        maximum_body_characters({"maximum_body_characters": declared})
    assert "maximum_body_characters" in str(caught.value)


def test_fragment_packing_is_deterministic() -> None:
    """`SC-050`: same blocks, same capability, byte-identical fragments."""
    blocks = tuple(f"bloco governado numero {index}" for index in range(1, 7))
    first = fragments_for(blocks, _capability(70), repeated_suffix=_CAVEATS)
    second = fragments_for(blocks, _capability(70), repeated_suffix=_CAVEATS)
    assert [f.body for f in first] == [f.body for f in second]
