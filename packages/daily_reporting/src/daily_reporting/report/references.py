"""The second reference each indicator carries — `FR-1306`, `SC-1305`, slice `F2`.

His approved contract asks every indicator for TWO references: the day before yesterday, and
the **same weekday a week back**. The first has been in the report since `OD-31`; this module
holds the shape of the second.

**Everything here that is a decision arrives as data**, for the reason the breakdown's labels
already do: `_every_word_is_his` refuses any token with a letter that comes from no named
vocabulary, and the word naming this reference carries a letter. The answer is not to drop it
— that was the `S-44`
defect, measured — nor to grow `AUTHORED_WORDS`, which counts what the PACKAGE holds. It
arrives from `report_governance/references.yaml`, the same path the section order takes.

## Seven is not a preference

The same weekday is the point: a daily series is noisy and a Saturday does not compare with a
Tuesday. That is the reasoning `OD-14-E` used to choose weeks in the first place, kept as the
SECOND reference after `OD-31` made the first one daily — so the report now carries both the
sensitive comparison and the stable one, which is what the contract asks for.

## Absence refuses, and never defaults

The `S-41` rule: a governed file that fails to state something must not be answered for. A
missing key, a non-integer window, a window of zero or an empty word all refuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

__all__ = ["ReferenceGovernance", "ReferenceGovernanceError"]


class ReferenceGovernanceError(ValueError):
    """The governed reference file cannot be trusted. Never silently replaced by a default."""


@dataclass(frozen=True, slots=True)
class ReferenceGovernance:
    """How far back the second reference sits, and the words that name it."""

    days_back: int
    label: str
    against: str
    #: **The word that says the number in the parentheses is the OLD one** — `OD-147`,
    #: 2026-09-06. The reference used to close as `(654)`, a bare number in brackets at the end
    #: of a line already carrying three others; he chose `(era 654)`.
    #:
    #: It is one word and it changes what the bracket means: without it the number is an
    #: annotation of unknown tense, and with it the line reads as a comparison against a day
    #: that is over. **Governed rather than authored**, for the reason ``label`` and ``against``
    #: are: it belongs to this clause, and the clause is data.
    #:
    #: Empty is permitted and is the declared absence: the reference then closes with the bare
    #: parentheses it always did, rather than with a word this package chose.
    was: str = ""

    def __post_init__(self) -> None:
        # Exact type, not `isinstance`: a governed file states `true` and Python hands back a
        # `bool`, which IS an `int` by inheritance and is not a number of days.
        if type(self.days_back) is not int:
            raise ReferenceGovernanceError(
                f"days_back is {type(self.days_back).__name__} and not an integer"
            )
        if self.days_back < 1:
            raise ReferenceGovernanceError(
                f"days_back is {self.days_back}; a reference at zero days back is the day "
                "itself, which compares a number with itself"
            )
        if not self.label.strip() or not self.against.strip():
            raise ReferenceGovernanceError(
                "the reference is unnamed; a second number beside the first, with no word "
                "saying what it is, is a number the reader cannot use"
            )

    @classmethod
    def from_document(cls, document: object) -> ReferenceGovernance:
        """Build from the parsed governed file, refusing anything it fails to state."""
        if not isinstance(document, dict):
            raise ReferenceGovernanceError(
                f"the governed references are {type(document).__name__} and not a mapping"
            )
        stated = cast("dict[str, object]", document)
        for key in ("days_back", "label", "against"):
            if key not in stated:
                raise ReferenceGovernanceError(
                    f"the governed references state no {key!r}; silence is not a value"
                )
        label = stated["label"]
        against = stated["against"]
        if not isinstance(label, str) or not isinstance(against, str):
            raise ReferenceGovernanceError("label and against are words, and one of them is not")
        #: `OD-147`. Optional in the DOCUMENT and refused when stated as a non-word: a file that
        #: says nothing declares the absence the field's default already carries, and a file that
        #: says something unreadable is the `S-41` case — never answered for.
        was = stated.get("was", "")
        if not isinstance(was, str):
            raise ReferenceGovernanceError(f"was is {type(was).__name__} and not a word")
        return cls(
            days_back=cast("int", stated["days_back"]),
            label=label,
            against=against,
            was=was,
        )
