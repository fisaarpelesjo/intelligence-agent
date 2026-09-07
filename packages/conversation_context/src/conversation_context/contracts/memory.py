"""What a conversation remembers — the envelope, the turn, and the three-state read.

## The two decisions that shaped this file are HIS, with dates

- **`OD-67`, 2026-08-31**: the memory lasts **one day** — *a conversa de hoje lembra até amanhã*.
  `MEMORY_DURATION` carries it; expiry is derived at READ time from the stamped basis, never stored
  as a label that goes stale by calendar (the `S-25` defect, refused from birth).
- **`OD-68`, 2026-08-31**: what is remembered is **a window of STRUCTURED turns** — *cada emenda
  herda o contexto*. A turn is the structured form of a governed question and can carry **none** of
  what `003:FR-082` forbids: no raw question text, no free-text replies, no metric values, no
  filter values. The slots below are the whole surface, and there is no free-text slot to smuggle
  through.

## The window's size is a DESIGN bound, and its successor is written

`WINDOW_TURNS` caps **cost** (file growth, read length); his expiry caps **meaning**. There is no
governed number to derive it from today — `D-19`'s interpretation policy is *empty and unapproved
by design*, and its own header forbids inventing a bound there. So 16 is design headroom, and the
day that policy gains an instance, this constant **shrinks to the governed
`clarification_round_bound`**: a real derivation deferred to the instrument that will exist.

## The three-state read — `FR-1108`

`recall` answers exactly one of `Remembered`, `NothingRemembered`, `Unreadable` — and the caller
cannot confuse them, because *could not read* impersonating *fresh conversation* is the silent
failure this repository keeps paying for (`did not measure` is never `empty`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

__all__ = [
    "MEMORY_DURATION",
    "WINDOW_TURNS",
    "NothingRemembered",
    "RecallResult",
    "Remembered",
    "RememberedTurn",
    "StructuredTurn",
    "Unreadable",
]

#: `OD-67`. Injected where the read happens; multiplied at read time, never stored as a deadline.
MEMORY_DURATION = timedelta(days=1)

#: Design bound with a written successor — see the module docstring. Not his, and not governed yet.
WINDOW_TURNS = 16


@dataclass(frozen=True, slots=True)
class StructuredTurn:
    """The structured form of one governed question. **No slot can hold what `FR-082` forbids.**

    ``intent`` is the governed question kind; ``metric_ids`` are catalog names (`new_trials`),
    which are identifiers and not values; ``period`` is a governed period DESCRIPTOR
    (`last_week`), not dates somebody typed; ``filter_fields`` are the NAMES of filtered fields —
    **never their values**, which `003:FR-082` forbids the store to own.

    Frozen and slotted so a later field is a visible schema change, not a quiet addition.
    """

    intent: str
    metric_ids: tuple[str, ...]
    period: str
    filter_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RememberedTurn:
    """One remembered item: the envelope around a turn.

    ``identity`` and ``scope`` come from `004`'s resolver — the owner is DERIVED (`FR-1101`).
    ``expires_basis`` is the STAMP expiry derives from; the duration multiplies at read time.
    Both stamps carry zones (`FR-1110`).
    """

    identity: str
    scope: str
    message_id: str
    stored_at_utc: str
    stored_at_local: str
    expires_basis: str
    turn: StructuredTurn


@dataclass(frozen=True, slots=True)
class Remembered:
    """The window, oldest first, already filtered by expiry and capped at `WINDOW_TURNS`."""

    turns: tuple[RememberedTurn, ...]


@dataclass(frozen=True, slots=True)
class NothingRemembered:
    """A fresh conversation, or one whose every turn expired. **Safe to answer context-free.**"""


@dataclass(frozen=True, slots=True)
class Unreadable:
    """The store failed to answer. **Not empty, and never to be treated as empty.**

    The caller proceeds context-free AND SAYS SO — a governed refusal to rely on context, not a
    silent fresh start.
    """

    reason: str


RecallResult = Remembered | NothingRemembered | Unreadable


def is_expired(
    expires_basis: datetime, now: datetime, duration: timedelta = MEMORY_DURATION
) -> bool:
    """Expiry, derived at read time — `FR-1104`. Both instants must carry zones."""
    if expires_basis.tzinfo is None or now.tzinfo is None:
        message = "an instant without a zone cannot anchor an expiry"
        raise ValueError(message)
    return now - expires_basis >= duration
