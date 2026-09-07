"""The owner's five labels — and they exist as of 2026-08-27T22:03:42Z — T711.

**This module was empty until he chose, and the emptiness was the feature working.**

He decided the SHAPE on 2026-08-27 — label and value, one line per field, five fields,
no assembled sentence — and the WORDS later the same day, from four sets offered to him
with one recommended. He picked the recommended one. **The five below are his choice,
transcribed, and nothing here was authored by this repository.**

## Why the offering was not itself a fabricated approval

The rule that governs this module is that a label written here and treated as approved
is **fabricating an approval** — `D-28`. Offering candidate wordings **that only become
text when he picks one** is the same mechanism every other decision in this loop uses:
he asked for options, the options were shown, and his choice is the approval. What was
forbidden, and stayed forbidden, was writing five plausible words and shipping them.

**And no disguise was ever permitted** — not `EXAMPLE_`, not `DRAFT_`, not a fixture,
not a test constant. A node walks this package's syntax tree for exactly those, because
that is how a written-here label would arrive: labelled provisional, then read as
approved.

## What still refuses, and it is not this

`APPROVED_LABELS` no longer refuses. **A field with no approved label still does** —
which is the case that matters the day a sixth field is decided on and its word has not
been. And every other refusal is untouched: no finding is prioritisable, so nothing
reaches this module in a real run at all.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..contracts.reason_codes import DistributionReasonCode

__all__ = ["APPROVED_LABELS", "MissingLabels", "labels_for"]

#: **The owner's labels, keyed by field name. HIS WORDS, transcribed on 2026-08-27.**
#:
#: Chosen from four sets offered with one recommended; he took the recommended one. The
#: reasons he was given for it are recorded with the decision, and two are worth keeping
#: beside the words themselves:
#:
#: * **`Ressalva` promises nothing.** `Aviso` and `Nota` were offered and not chosen;
#:   neither is wrong, and `Ressalva` is the one that does not read as an explanation of
#:   the movement. The line it labels says correlation is not causation, so a label
#:   suggesting the system is about to explain WHY would work against its own content.
#: * **`Direção` and `Valor` are separate for a reason.** A set offering `Variação` for
#:   the direction was declined: it reads as the number, and the number is already on the
#:   `Valor` line — two labels pointing at one value is how two lines come to disagree.
#:
#: **Nothing may be added here except by transcribing what he wrote.** A sixth field
#: decided tomorrow arrives with no label until he supplies one, and `labels_for` refuses
#: until he does.
APPROVED_LABELS: Mapping[str, str] = {
    "metric": "Métrica",
    "period": "Período",
    "figure": "Valor",
    "direction": "Direção",
    "caveat": "Ressalva",
}


class MissingLabels(LookupError):  # noqa: N818 - a governed refusal, not an error
    """No approved label for one or more fields, and the refusal names which.

    Carries the governed code so a caller reports the reason rather than inventing one,
    and names the fields so a reader knows exactly how much is missing — five today,
    and possibly one on the day four of the five arrive.
    """

    def __init__(self, missing: tuple[str, ...]) -> None:
        self.code = DistributionReasonCode.DISTRIBUTION_LABELS_NOT_APPROVED
        self.missing = missing
        super().__init__(
            f"{self.code.value}: no approved label for {list(missing)}; the label text is the "
            "owner's and this feature may not write one"
        )


def labels_for(fields: tuple[str, ...]) -> dict[str, str]:
    """The approved label for each field, or a refusal naming the ones that have none.

    **Every field or none.** A report with four labels and one bare value is not a
    partly-labelled message; it is a message whose fifth line nobody can read, sent as
    though it were complete. So the check is over the whole set before anything is
    returned.
    """
    missing = tuple(name for name in fields if name not in APPROVED_LABELS)
    if missing:
        raise MissingLabels(missing)
    return {name: APPROVED_LABELS[name] for name in fields}
