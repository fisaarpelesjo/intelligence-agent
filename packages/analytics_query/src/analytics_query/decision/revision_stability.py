"""Re-request value stability — T085 (FR-067; SC-015).

A re-request under the same query identity and as-of pin returns **identical
values** whenever the contributing data revisions are unchanged, and reports
``PERIOD_RESTATED`` with the new revision when they are not.

The load-bearing clause is *how* that guarantee is produced. It derives from
governed as-of resolution and revision comparison — never from a stored or
cached result (`FR-068`). A cache would make the two cases indistinguishable
from the outside while quietly changing what "identical" means: identical to
what was computed once, rather than identical to what the data still says.

So stability here is a **claim about revisions**, not a promise to replay an
answer. If the revisions match, re-executing genuinely reproduces the figures.
If they do not, the honest report is that the period was restated — and the
caller is given the new revision id and the superseded decision so they can see
which number changed and why, rather than being handed a silently different
figure that looks like the old one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from semantic_catalog.contracts.reason_codes import ReasonCode

__all__ = ["Stability", "StabilityVerdict", "compare_revisions"]


class Stability(StrEnum):
    """Whether the contributing data still says the same thing."""

    #: Every contributing revision is unchanged: a re-execution reproduces the
    #: figures exactly.
    REPRODUCIBLE = "reproducible"
    #: At least one revision moved: the period was restated upstream.
    RESTATED = "restated"
    #: A revision is missing on one side or the other, so no comparison can be
    #: made. Not the same as "unchanged".
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class StabilityVerdict:
    """The comparison and what it means for the caller."""

    stability: Stability
    #: Revisions that moved between the two evaluations, sorted for determinism.
    changed_sources: tuple[str, ...] = ()
    #: The governed code to report. `None` when the values are reproducible and
    #: there is nothing to qualify.
    reason_code: ReasonCode | None = None

    @property
    def values_are_reproducible(self) -> bool:
        """Only an outright match reproduces. Undetermined does not."""
        return self.stability is Stability.REPRODUCIBLE


def compare_revisions(
    previous: dict[str, str | None],
    current: dict[str, str | None],
) -> StabilityVerdict:
    """Compare contributing revisions across two evaluations of one identity.

    Maps source id to revision id. A ``None`` revision means the source could
    not supply a stable one — that is `UNDETERMINED`, never "unchanged", because
    two unknowns are not evidence of sameness. Treating them as equal would
    claim reproducibility the system cannot back.

    A source appearing or disappearing between evaluations is also undetermined:
    the two runs did not read the same thing, so no statement about stability
    covers them.
    """
    if previous.keys() != current.keys():
        return StabilityVerdict(
            stability=Stability.UNDETERMINED,
            reason_code=ReasonCode.REPRODUCIBILITY_LIMITED,
        )

    if any(revision is None for revision in (*previous.values(), *current.values())):
        return StabilityVerdict(
            stability=Stability.UNDETERMINED,
            reason_code=ReasonCode.REPRODUCIBILITY_LIMITED,
        )

    changed = tuple(sorted(s for s, revision in current.items() if previous[s] != revision))
    if not changed:
        return StabilityVerdict(stability=Stability.REPRODUCIBLE)

    return StabilityVerdict(
        stability=Stability.RESTATED,
        changed_sources=changed,
        reason_code=ReasonCode.PERIOD_RESTATED,
    )
