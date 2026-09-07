"""Continuation — T073 (`R-12`; FR-058, FR-059; SC-020).

A payload too large for one message is delivered **whole**, as an ordered sequence of fragments each
carrying ``(index, total)``, through the mechanism the channel's `D-28` entry declares.

**No declared ordering guarantee means withhold.** This is the rule that looks like an over-
reaction and is not. Without an ordering guarantee, fragment three may arrive before fragment one,
and a reader who sees "part 3 of 3" first has been handed the end of an answer as though it were
the whole of one. A "part 2 of 3" label is not a mitigation: it tells the reader something is
missing, not what it said.

**No fragment carries a subset of the caveats.** Splitting caveats across fragments would let the
first fragment stand alone as an uncaveated finding, which is the precise failure `FR-047` exists
to prevent. So the caveat block travels in **every** fragment, and the cost — repetition — is
accepted deliberately: a repeated caveat is noise, a missing one is a false claim.

**Splitting never cuts a governed string.** Fragments break on the boundaries between governed
blocks. Where a single block does not fit the channel's declared maximum, there is nothing to
split and the response is withheld — because cutting the block would be truncation with a label on
it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..contracts.presentation import PresentationFragment
from .withhold import NotRepresentable

__all__ = [
    "ORDERING_GUARANTEED",
    "fragments_for",
    "maximum_body_characters",
    "ordering_is_guaranteed",
]

#: The values a `D-28` entry may use to declare that fragment order is preserved end to end.
#: Closed: an unrecognised value is **not** a guarantee, so it withholds rather than being read
#: optimistically.
ORDERING_GUARANTEED: frozenset[str] = frozenset({"ordered", "guaranteed", "fifo"})


def ordering_is_guaranteed(capability: Mapping[str, Any]) -> bool:
    """Does this channel's entry declare an ordering guarantee?

    Absent, empty or unrecognised means **no**. A guarantee is something a channel states, never
    something this feature infers from silence.
    """
    declared: object = capability.get("ordering_guarantee")
    return isinstance(declared, str) and declared.strip().lower() in ORDERING_GUARANTEED


def maximum_body_characters(capability: Mapping[str, Any]) -> int:
    """The channel's declared maximum body length, or refuse.

    Refuses rather than assuming a limit. A guessed ceiling is a governed value this feature
    authored, which `D-26` and `D-28` exist to prevent.
    """
    declared: object = capability.get("maximum_body_characters")
    if not isinstance(declared, int) or isinstance(declared, bool) or declared <= 0:
        raise NotRepresentable("the capability entry declares no positive maximum_body_characters")
    return declared


def fragments_for(
    blocks: Sequence[str],
    capability: Mapping[str, Any],
    *,
    repeated_suffix: str = "",
) -> tuple[PresentationFragment, ...]:
    """Pack ``blocks`` into ordered fragments, or refuse.

    ``blocks`` are the governed blocks in the payload's own order, already rendered, and
    ``repeated_suffix`` is the caveat block that must appear in **every** fragment. The suffix is
    passed rather than inferred, so the renderer stays the only thing deciding what a caveat block
    contains.

    Refuses when: the channel declares no ordering guarantee and more than one fragment is needed; a
    single block plus the repeated suffix cannot fit; or there is nothing to send.
    """
    if not blocks:
        raise NotRepresentable("there is nothing to render")

    limit = maximum_body_characters(capability)
    separator = "\n\n"
    suffix = f"{separator}{repeated_suffix}" if repeated_suffix else ""

    packed: list[str] = []
    current = ""
    for block in blocks:
        if len(block) + len(suffix) > limit:
            # One indivisible governed block does not fit. Splitting it would cut a governed string,
            # which is truncation wearing a continuation's clothes.
            raise NotRepresentable("a single governed block exceeds the channel's declared maximum")
        candidate = block if not current else f"{current}{separator}{block}"
        if len(candidate) + len(suffix) > limit:
            packed.append(current)
            current = block
        else:
            current = candidate
    packed.append(current)

    if len(packed) > 1 and not ordering_is_guaranteed(capability):
        raise NotRepresentable(
            "the channel declares no ordering guarantee, so a continuation cannot arrive in order"
        )

    total = len(packed)
    return tuple(
        PresentationFragment(index=index, total=total, body=f"{body}{suffix}")
        for index, body in enumerate(packed, start=1)
    )
