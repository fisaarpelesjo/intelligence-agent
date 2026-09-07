"""A tie is reported as a tie — T014 (`FR-010`).

**Input order must not break a tie**, and the reason is that input order carries no
meaning at all here: `005` hands over candidates in whatever order its rules ran, which
depends on a dict, a file listing and the day. Letting that decide which of two equal
findings a person looks at first invents a priority out of an implementation detail —
and it invents it *invisibly*, because the output looks exactly like a real ordering.

## Equal on every declared component, not equal on a score

Two findings tie when **every declared component holds the same value**. That is
checkable without knowing how the components combine, which matters because *how* is
`D-A` and is the owner's: a composed score could collapse two genuinely different
findings onto one number, and calling that a tie would report an artefact of the
arithmetic as a fact about the findings.

**So this module compares component by component**, and it never needs the composition
rule. It works today, with the registry empty, and it works unchanged the day `D-A` is
answered.

## The empty case, and where it is actually refused

With no declared component, every pair of findings is trivially "equal on every
component" — which would make **everything** one enormous tie. That is a vacuous truth,
and reporting it as a tie would be the `F115` shape: a condition satisfied because there
was nothing to satisfy it.

**It cannot arrive here, and the refusal is not this module's.** `PrioritisedFinding`
refuses to be built with no components at all, so an ungrounded candidate never reaches
`group_ties` — it travels as `NotPrioritisable`, which these functions do not take.

The guard below is kept anyway, because that refusal lives in another file and this one
should not depend on it silently: a finding that somehow arrives with nothing in it gets
a group of its own rather than a key that ties it to every other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

    from ..contracts import PrioritisedFinding

__all__ = ["group_ties", "tie_key"]


def tie_key(finding: PrioritisedFinding) -> tuple[tuple[str, str], ...] | None:
    """What makes two findings tie: every component's name and value.

    ``None`` for a finding with no components — **ungrounded is not tied**, and
    returning a key for it would make every such finding equal to every other. The
    contract refuses to build one, so this is defence against that refusal moving, not
    a case this module expects.

    The value is compared as its exact decimal string rather than as a `Decimal`,
    because `Decimal("0.5")` and `Decimal("0.50")` compare EQUAL while carrying
    different precision. Two components measured to different precision are not the
    same measurement, and treating them as one would report a tie the data does not
    support.

    Sorted by name, so a component list built in a different order still ties.
    """
    if not finding.components:
        return None
    return tuple(
        sorted(
            (component.name, "" if component.value is None else str(component.value))
            for component in finding.components
        )
    )


def group_ties(
    findings: Sequence[PrioritisedFinding],
) -> tuple[tuple[PrioritisedFinding, ...], ...]:
    """Collapse findings that are equal on every component into one rank group.

    **Input order decides nothing about WHO is first**, only about the order within a
    reported tie, where it carries no claim — a tie is stated as a tie, and the members
    of one are not ranked against each other.

    The groups come back in the order their first member appeared, which keeps the
    caller's ranking intact: this function reports ties, it does not reorder. A function
    that both grouped and sorted would be deciding rank, and rank needs the composition
    rule that `D-A` has not answered.

    A finding with no components gets a group of its own — see `tie_key`.
    """
    groups: list[list[PrioritisedFinding]] = []
    seen: dict[tuple[tuple[str, str], ...], int] = {}

    for finding in findings:
        key = tie_key(finding)
        if key is None:
            groups.append([finding])
            continue
        index = seen.get(key)
        if index is None:
            seen[key] = len(groups)
            groups.append([finding])
        else:
            groups[index].append(finding)

    return tuple(tuple(group) for group in groups)
