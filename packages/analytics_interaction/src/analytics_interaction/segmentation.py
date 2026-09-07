"""Slot-surface segmentation — the element ADR 0017's stop condition surfaced (ADR 0027).

```
segment(text)            -> tuple[QuestionSpan, ...]
candidate_surfaces(text) -> tuple[tuple[str, int, SlotKind], ...]
```

**Where a candidate term sits. Never what it means.**

Step 6 of the sixteen-step ordering resolves slots, and `resolve_term` resolves **one surface at a
time** from a `TermRef` carrying that surface's position and length. Nothing in this feature
turned a question into the set of surfaces to resolve, so the composed entry point could not
reach step 6 at all: it returned an empty surface tuple, every question routed to clarification,
and `T108` was marked complete over a gap. ADR 0027 records that episode and authorizes this
module.

## What this module decides: nothing

It offers **spans**, deterministically, and enumerates them against the slot kinds a caller may
attempt. It does not resolve, read a catalog, call a model, consult governed content or judge that a
span names a metric rather than a dimension. Every semantic question stays with `resolve_term`,
which is access-filtered and catalog-backed, exactly as before.

That distinction matters for a reason worth stating: deciding that a span is a metric surface **is**
interpretation, and ADR 0017 exists so interpretation stays with this feature's own components
rather than being re-created behind a composed entry point.

### The tension in ADR 0027's own signature, and how it is resolved

ADR 0027 fixes the shape as ``(surface, start, SlotKind)`` and, in the same section, forbids this
module from deciding a slot. Read as an assignment — "this span *is* a metric" — those two
requirements contradict each other.

They are consistent under the other reading, which is the one implemented here: the ``SlotKind`` in
each tuple is not an assignment but an **enumeration**. :func:`candidate_surfaces` emits every span
paired with every slot kind a caller may attempt, and the caller discovers which pairings the
catalog recognises. The module decides nothing; it lists what may be asked.

## No authored value, and the cost that choice carries — measured

There is no window size, no maximum n-gram length, no stopword list and no minimum token length.
Each of those would be a governed value this feature has no authority to set, and `T101` is the
scan that catches exactly that mistake — it already caught one in this repository.

**The cost is measured rather than described.** Worst case is one `discover` call per span, and the
span count for `n` tokens is `n(n+1)/2` — every contiguous window. Longest-wins suppression reduces
it only when spans actually resolve, so a question where nothing is governed pays the full amount:

| Characters | Tokens | Spans | `discover` calls |
|---|---|---|---|
| 71 | 8 | 36 | 36 |
| 389 | 40 | 820 | 820 |
| 789 | 80 | 3 240 | 3 240 |
| 1 649 | 160 | 12 880 | 12 880 |
| 3 409 | 320 | 51 360 | 51 360 |

**`D-19` bounds the question in characters and nothing bounds the candidate count.** Step 4 applies
``question_length_bound``, which is a character count, and a character bound does not bound tokens
usefully: the table above is what a long question costs. So the honest statement is not
"quadratic and therefore fine" — it is that **a candidate bound is missing from `D-19`**,
recorded as a discovered dependency in `004`'s revision notes rather than invented here.

Until that value exists the measured numbers are the behaviour, and they are written here so
nobody has to rediscover them. An earlier version of this docstring said the cost was stated and
left it at that; review finding S was right that stating a cost is not measuring one.

## Punctuation is a boundary, and that is not a vocabulary decision

Tokens are runs of characters that are neither whitespace nor punctuation, using Python's own
Unicode categories rather than a list this module wrote down. A comma does not join two terms in
any language this feature supports, so treating it as a boundary is a fact about writing systems
rather than a judgement about vocabulary. Accents, case and word order are left exactly as the
sender wrote them: normalisation is `004`'s declared-rules concern on the way in, and nothing
here rewrites a span.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from itertools import pairwise

from .contracts.clarification import SlotKind

__all__ = [
    "SLOT_KINDS_IN_FILL_ORDER",
    "QuestionSpan",
    "candidate_surfaces",
    "segment",
    "tokens",
]

#: The slot kinds a caller may attempt, in this feature's own declaration order. Derived from the
#: enum rather than re-declared, so a fifth slot kind reaches this module without an edit here.
SLOT_KINDS_IN_FILL_ORDER: tuple[SlotKind, ...] = tuple(SlotKind)


@dataclass(frozen=True, slots=True)
class QuestionSpan:
    """One contiguous span of the question: its text, and where it sits.

    ``start`` and ``length`` are what a `TermRef` carries, so a caller builds one without this
    module knowing about `TermRef` at all. The text is present because `resolve_term` takes the
    surface as a separate argument; it is carried, never stored, and never reaches an audit
    surface — `FR-053` of this feature keeps question text out of records, and a span is not a
    record.
    """

    surface: str
    start: int
    length: int


def tokens(text: str) -> tuple[QuestionSpan, ...]:
    """Every token in ``text``, with its offset. Deterministic, and total over any string.

    A token is a maximal run of characters that are neither whitespace nor punctuation, decided by
    Unicode category rather than by a character list written here. Empty input yields no tokens
    rather than raising: an empty question is step 1's refusal to make, not this module's.
    """
    found: list[QuestionSpan] = []
    start: int | None = None
    for index, character in enumerate(text):
        category = unicodedata.category(character)
        is_boundary = character.isspace() or category.startswith("P")
        if is_boundary:
            if start is not None:
                found.append(QuestionSpan(text[start:index], start, index - start))
                start = None
        elif start is None:
            start = index
    if start is not None:
        found.append(QuestionSpan(text[start:], start, len(text) - start))
    return tuple(found)


def _contiguous(text: str, window: tuple[QuestionSpan, ...]) -> bool:
    """Is every gap inside ``window`` whitespace only?

    A gap containing punctuation means the sender separated two things, so joining them would
    invent a term nobody wrote. Checked against the original text rather than reconstructed,
    because a reconstruction would decide what the separator was.

    A single-token window has no gap at all and is vacuously contiguous, which ``pairwise`` gives
    for free by yielding nothing.
    """
    for earlier, later in pairwise(window):
        gap = text[earlier.start + earlier.length : later.start]
        if gap.strip():
            return False
    return True


def segment(text: str) -> tuple[QuestionSpan, ...]:
    """Every contiguous run of tokens in ``text``, as a span, longest first.

    Longest first is deliberate and is the one ordering decision here. A caller resolving greedily
    should see "instalações na Google Play" before "instalações", because offering the short span
    first would let a broader concept win over the specific one the sender actually wrote. The
    ordering is **stable**: equal-length spans keep their position in the question, so two runs
    over one question produce byte-identical output.

    Punctuation does not join spans: a run stops at any boundary, so "julho, agosto" never produces
    "julho agosto".
    """
    units = tokens(text)
    spans: list[QuestionSpan] = []
    for size in range(len(units), 0, -1):
        for first in range(0, len(units) - size + 1):
            window = units[first : first + size]
            if not _contiguous(text, window):
                continue
            start = window[0].start
            end = window[-1].start + window[-1].length
            spans.append(QuestionSpan(text[start:end], start, end - start))
    return tuple(spans)


def candidate_surfaces(text: str) -> tuple[tuple[str, int, SlotKind], ...]:
    """Every span paired with every slot kind, in the shape ADR 0027 fixes.

    An **enumeration**, not an assignment: the slot kind says which resolution a caller may
    attempt for that span, and the catalog decides whether the pairing means anything. This
    module has formed no opinion about any of them.

    Ordering is span order — longest first, stable — then slot-kind declaration order, so the
    output is deterministic and a caller resolving in order tries the most specific span first.
    """
    return tuple(
        (span.surface, span.start, slot)
        for span in segment(text)
        for slot in SLOT_KINDS_IN_FILL_ORDER
    )
