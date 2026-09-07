"""The six slots and the order they fill — T069 (FR-005; SC-001).

Interpretation is **slot-filling over a governed vocabulary**, and there are
exactly six slots. Filling them is all interpretation does: it produces no free
text, no derived concept and no identifier the catalog does not already declare.

``SlotKind`` itself lives in `contracts/intent.py`, where it is a closed enum. A
seventh kind would be a contract change, not an implementation one — the closed
set is what lets a clarification name its unresolved slot without a free-text
field.

**The fill order is not arbitrary, and it is not a preference.** Each step
depends on what the previous one established:

| # | Slot | Why here |
|---|---|---|
| 1 | ``metric`` | Nothing else has meaning without it. Which dimensions
  exist, which sources contribute and which comparisons are governed are
  all properties *of a metric* |
| 2 | ``source`` | Narrows which dimension values can occur, and settles
  the `google_play` role question before the value slot has to guess |
| 3 | ``dimension`` | The breakdown axes, which the metric declares |
| 4 | ``dimension_value`` | A filter value is meaningless until its
  dimension is known — ``permitted_values`` is a property of the
  dimension, not of the question |
| 5 | ``period`` | Independent of the above, and placed after them so a
  period refusal never precedes the metric refusal that would have made
  it moot |
| 6 | ``comparison`` | Last, because a comparison is over resolved metrics
  and resolved periods |

Ordering also decides **which refusal a caller sees first**, and that matters for
disclosure: refusing "no such metric" before "no such dimension" means a caller
probing for dimension names learns nothing without first naming a metric they are
authorised to see.
"""

from __future__ import annotations

from ..contracts.intent import SlotKind

__all__ = ["FILL_ORDER", "SLOT_KINDS", "fill_position", "ordered_slots"]

#: The six kinds, exactly as `contracts/intent.py` declares them. Derived from
#: the enum rather than restated, so the two cannot drift.
SLOT_KINDS: frozenset[SlotKind] = frozenset(SlotKind)

#: The order interpretation fills them in. See the module docstring.
FILL_ORDER: tuple[SlotKind, ...] = (
    SlotKind.METRIC,
    SlotKind.SOURCE,
    SlotKind.DIMENSION,
    SlotKind.DIMENSION_VALUE,
    SlotKind.PERIOD,
    SlotKind.COMPARISON,
)


def fill_position(slot: SlotKind) -> int:
    """Where ``slot`` sits in the fill order.

    Raises rather than defaulting: a slot with no position would be one this
    module silently placed last, and a missing entry means the enum and the
    order have drifted.
    """
    try:
        return FILL_ORDER.index(slot)
    except ValueError as exc:  # pragma: no cover - guarded by the contract test
        raise ValueError(f"slot {slot!r} has no declared fill position") from exc


def ordered_slots(slots: frozenset[SlotKind]) -> tuple[SlotKind, ...]:
    """``slots``, in fill order.

    Deterministic by construction: the output order comes from ``FILL_ORDER``,
    never from the input's iteration order. A frozenset's iteration order is
    stable within a process and not across them, so sorting by the governed
    order is what makes two runs agree.
    """
    return tuple(slot for slot in FILL_ORDER if slot in slots)
