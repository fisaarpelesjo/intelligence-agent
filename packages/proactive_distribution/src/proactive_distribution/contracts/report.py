"""The report: five labelled fields, one line each, and no sentence anywhere — T709.

**The owner chose this shape on 2026-08-27, over three others, and the reason he
chose it is the reason it is worth writing down.** The alternatives put everything
in one sentence, or split the causality caveat away from the number, or repeated the
number in two places that can disagree.

**Where there is no prose, there is no sentence that claims more than was measured.**
The shape he chose *cannot commit* this repository's oldest defect, rather than
merely avoiding it by discipline — and that is a property of the form, not of whoever
writes the next line.

## What this module holds, and what it deliberately does not

It holds **the container**: five fields, their order, and the rule that each carries a
value or the report refuses. **It holds no labels.** The label text is the owner's, and
until he writes the five, `labels.py` is empty and every attempt refuses with its own
code.

**No example label, under any name.** Not `EXAMPLE_`, not `DRAFT_`, not a fixture.
Five plausible labels called a container is exactly what the plan's Phase C forbids,
because a plausible label read by anyone downstream is a word this repository wrote
and attributed to him.

## The caveat is a field like the others, and that changes where it lives, not whether
it may change

`005` requires its causality warning to travel **byte for byte**, never composed and
never paraphrased. Putting it in a field does not soften that: the value is compared
against `005`'s own constant, and a single character apart is a refusal.
"""

from __future__ import annotations

from anomaly_investigation.contracts.candidate import REQUIRED_CAUSALITY_WARNING
from pydantic import Field, field_validator

from ._base import DistributionContractViolation, DistributionModel

__all__ = ["FIELD_READERS", "Report", "field_names_of_the_model"]


class Report(DistributionModel):
    """Five fields, each a value the upstream seams measured. **Never a sentence.**

    Every field is a plain value: the model carries no text this feature composed, and
    `tests/security/test_no_composed_prose.py` measures that over the emitted tree
    rather than trusting this docstring.

    **The field set is the model's**, and `FIELD_READERS` below is a second,
    independent declaration of the same set. They are compared by a node: a field
    added to one and not the other is red, naming which. Deriving both from one source
    would make that node compare a derivation against itself, which is the `G-1`
    defect this repository has already paid for twice.
    """

    #: Which metric moved. A governed metric id, carried from `006`'s finding.
    metric: str = Field(min_length=1)

    #: Over which period. Carried, never computed here — this feature owns no calendar.
    period: str = Field(min_length=1)

    #: What the figure was. A string because it is **transported**, not arithmetic: this
    #: feature must not re-derive, re-round or re-unit a number that upstream already
    #: decided the presentation of.
    figure: str = Field(min_length=1)

    #: Which way it moved, read off the measurement rather than chosen.
    direction: str = Field(min_length=1)

    #: `005`'s required warning, byte for byte.
    caveat: str = Field(min_length=1)

    @field_validator("caveat")
    @classmethod
    def _the_caveat_is_the_baselines_own_words(cls, value: str) -> str:
        """**Byte for byte, and this is where that rule is enforced rather than hoped.**

        `005` transports this warning without composing it, and moving it into a field
        changes where it lives, not whether it may change. One character apart is a
        different claim about causality, so it is refused here — at construction, before
        anything can read it.
        """
        if value != REQUIRED_CAUSALITY_WARNING:
            raise DistributionContractViolation(
                "the causality caveat is not the baseline's own text, byte for byte; "
                "a warning this feature edited is a claim this feature made"
            )
        return value


def field_names_of_the_model() -> tuple[str, ...]:
    """The report's fields, in declaration order, read from the model itself."""
    return tuple(Report.model_fields)


#: **The second, independent declaration of the field set.**
#:
#: Each entry names a field and where its value is READ FROM. It exists so the node
#: that guards the set has two sources to compare instead of one derivation compared
#: with itself — and so a reader can see, per field, which seam owns the value.
#:
#: **Nothing here is a label.** These are the names of the fields; the words a person
#: reads beside each value are the owner's, and they do not exist yet.
FIELD_READERS: dict[str, str] = {
    "metric": "the finding's metric id, carried from 006",
    "period": "the governed window, carried from 001's decision",
    "figure": "the delivered figure, carried from 003's arithmetic",
    "direction": "read off the measured movement, never chosen",
    "caveat": "005's required warning, byte for byte",
}
