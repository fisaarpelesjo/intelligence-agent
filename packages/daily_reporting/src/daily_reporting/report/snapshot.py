"""The mark a LEVEL carries in the message — `SC-1306`, `FR-1318`, slice `F7`.

`T1330` made the arithmetic right: a `SNAPSHOT` is the last day the rows cover and never their
sum, because seven days of `MAU` added together counts the same people seven times. This module
holds the other half of the same success criterion, which asks the MESSAGE to say so where the
number appears.

## Why a number that is right still needs a word beside it

Two figures in one message answer different questions — `New trials` is *how many happened over
the period* and `MRR` is *where the level stood at the end of it* — and nothing on the screen
tells them apart. The reader who adds a weekly `MRR` to the next weekly `MRR` is doing the exact
arithmetic this package now refuses to do, and the only thing that stops them is being told.

## The word arrives as data, for the reason the second reference's words do

`_every_word_is_his` refuses any token carrying a letter that comes from no named vocabulary,
and this phrase is four such tokens. Growing `AUTHORED_WORDS` would be the wrong repair twice
over: that budget counts what the PACKAGE holds, and the phrasing is not the package's choice.
It arrives from `report_governance/snapshot_mark.yaml`, word for word out of the example
contract he approved, on the same path the section order and the second reference already take.

## Absence refuses, and never defaults

The `S-41` rule, unchanged: a governed file that fails to state something must not be answered
for. A missing key, a non-string, or an empty phrase all refuse rather than mark nothing — a
level silently rendered like an accumulation is the defect this file exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

__all__ = ["SnapshotMarkGovernance", "SnapshotMarkGovernanceError"]


class SnapshotMarkGovernanceError(ValueError):
    """The governed mark cannot be trusted. Never silently replaced by a default."""


@dataclass(frozen=True, slots=True)
class SnapshotMarkGovernance:
    """His phrase for *this number is a level, read on the last day of the period*."""

    mark: str

    def __post_init__(self) -> None:
        #: Only the emptiness is asked here. **That a phrase is a phrase is checked where the
        #: untyped document is read**, in `from_document`: a governed file states whatever it
        #: states, and the annotation on this field is a promise about callers rather than a
        #: fact about YAML. Asking twice puts a check the type system calls impossible in the
        #: path every construction takes.
        if not self.mark.strip():
            raise SnapshotMarkGovernanceError(
                "the mark is empty; a level rendered exactly like an accumulation invites the "
                "reader to add two of them, which is the arithmetic this file exists to stop"
            )

    @property
    def words(self) -> tuple[str, ...]:
        """The vocabulary this file contributes, for `_every_word_is_his`.

        A word that reaches the reader and not the condition is a word nobody checked — the
        defect measured in the caller on 2026-09-04, where the delivered text carried four
        words the permission had never been shown.
        """
        return (self.mark,)

    @classmethod
    def from_document(cls, document: object) -> SnapshotMarkGovernance:
        """Build from the parsed governed file, refusing anything it fails to state."""
        if not isinstance(document, dict):
            raise SnapshotMarkGovernanceError(
                f"the governed mark is {type(document).__name__} and not a mapping"
            )
        stated = cast("dict[str, object]", document)
        if "mark" not in stated:
            raise SnapshotMarkGovernanceError(
                "the governed file states no 'mark'; silence is not a value"
            )
        mark = stated["mark"]
        if not isinstance(mark, str):
            raise SnapshotMarkGovernanceError(f"the mark is {type(mark).__name__} and not a phrase")
        return cls(mark=mark)
