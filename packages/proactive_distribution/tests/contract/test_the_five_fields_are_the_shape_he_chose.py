"""Five fields, no sentence, and the caveat byte for byte — T709, and `T703` of the form.

The owner chose this shape on 2026-08-27 over three alternatives: one sentence
carrying everything, a form that split the caveat away from the number, and a form
that repeated the number in two places that can disagree. **Label and value, one line
per field, five fields, no assembled sentence.**

## Why the field set is asserted against TWO declarations

`Report`'s fields are one declaration. `FIELD_READERS` is a second, written separately
and saying where each value is read from. **They are compared against each other**, and
that is the whole design: deriving both from one source and comparing them would be a
check reading a derivation against itself — the `G-1` defect this repository paid for
twice this week, once in a vacuity guard that could not fail and once in a boundary
replacement that was a tautology.

So a field added to the model and not to the readers is red, naming it; a reader
without a field is red, naming it; and the count is asserted against the owner's
decision, which said **five**.
"""

from __future__ import annotations

import pytest
from anomaly_investigation.contracts.candidate import REQUIRED_CAUSALITY_WARNING
from pydantic import ValidationError

from proactive_distribution.contracts import (
    FIELD_READERS,
    Report,
    field_names_of_the_model,
)

pytestmark = pytest.mark.contract

#: What the owner decided, written here because it is HIS number and not a derivation.
#: A node comparing two derivations of the same thing would agree with itself whatever
#: the truth; this is the one place the decision enters, and it enters as a decision.
FIELDS_HE_CHOSE = 5


def test_the_model_carries_exactly_the_five_he_chose() -> None:
    """His decision, against the model. Five, and a sixth is a field nobody decided on."""
    names = field_names_of_the_model()
    assert len(names) == FIELDS_HE_CHOSE, (
        f"the report carries {len(names)} fields and the owner chose {FIELDS_HE_CHOSE}: {names}"
    )


def test_the_two_declarations_of_the_field_set_agree() -> None:
    """**The node the form requires, and it names which field diverged.**

    Two independently written declarations. A field in one and not the other is a field
    whose value nobody said where to read, or a reader for a field that is not emitted.
    """
    model = set(field_names_of_the_model())
    readers = set(FIELD_READERS)
    assert model == readers, (
        f"in the model and not in the readers: {sorted(model - readers)}; "
        f"in the readers and not in the model: {sorted(readers - model)}"
    )


def test_every_field_says_where_its_value_comes_from() -> None:
    """A reader entry with no source named is a field this feature would fill from nowhere."""
    empty = sorted(name for name, source in FIELD_READERS.items() if not source.strip())
    assert not empty, f"these fields name no source for their value: {empty}"


class TestTheCaveatTravelsByteForByte:
    """`005`'s rule, and the chosen form changes WHERE it lives, not whether it may change.

    **These nodes assert `ValidationError` and not this package's own violation type, and
    that is a correction rather than a shortcut.** A first draft expected
    `DistributionContractViolation`, because the validator raises one. It never arrives:
    pydantic **wraps** whatever a field validator raises into a `ValidationError`, so the
    package's type cannot escape through that path. A node asserting it would have been
    asserting something that never happens to any caller.

    What does survive the wrapping is the MESSAGE, so that is what is asserted — the rule
    reaches whoever reads the failure, which is the property that matters.
    """

    def _report(self, caveat: str) -> Report:
        return Report(
            metric="new_trials",
            period="2026-08-11..2026-08-20",
            figure="3.44",
            direction="increase",
            caveat=caveat,
        )

    def test_the_baselines_own_text_is_accepted(self) -> None:
        """The premise. A validator that refused everything would satisfy the node below."""
        assert self._report(REQUIRED_CAUSALITY_WARNING).caveat == REQUIRED_CAUSALITY_WARNING

    def test_one_character_apart_is_refused(self) -> None:
        """A warning this feature edited is a claim this feature made."""
        with pytest.raises(ValidationError, match="byte for byte"):
            self._report(REQUIRED_CAUSALITY_WARNING[:-1])

    def test_a_paraphrase_is_refused(self) -> None:
        """Not merely truncation: any other text at all, however reasonable it reads."""
        with pytest.raises(ValidationError, match="byte for byte"):
            self._report("os dados sugerem associacao e nao causalidade")


def test_a_sixth_field_cannot_be_smuggled_into_a_report() -> None:
    """`extra="forbid"`, driven rather than described.

    A sixth field arriving at construction is a field nobody decided on, and it is
    refused there rather than caught later by something that might not run.
    """
    with pytest.raises(ValueError, match="extra"):
        Report(
            metric="new_trials",
            period="2026-08-11..2026-08-20",
            figure="3.44",
            direction="increase",
            caveat=REQUIRED_CAUSALITY_WARNING,
            confidence="high",  # type: ignore[call-arg] - the point of the node
        )


def test_no_field_is_optional() -> None:
    """A field with a default is a field that can be silently absent from a message."""
    optional = sorted(
        name for name, field in Report.model_fields.items() if not field.is_required()
    )
    assert not optional, (
        f"these fields have defaults, so a report can be sent without them: {optional}"
    )
