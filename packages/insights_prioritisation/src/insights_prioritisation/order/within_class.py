"""One ordering per aggregation class, or one under a declared normalisation — T013 (`FR-005`).

`FR-005` permits two answers and forbids a third. The two: an ordering per aggregation
class, or a single ordering under a **declared** normalisation that appears in the
output. The third, which is forbidden: one ordering across classes on a scale nobody
declared.

**`004` measured the three classes as not interchangeable, and `005` refuses a rule
applied to the wrong one.** A snapshot movement and a count movement are numbers in
different worlds; putting them in one order without saying how is not a small
imprecision, it is an ordering whose meaning nobody can state.

## This module does not rank, and that is not a gap

Ranking needs a composed score, and how the declared components compose is `D-A` — the
owner's, exactly as *which* components exist is. These functions take findings that are
**already in rank order** and decide what may be published as one ordering.

So what is owned here is the part that is not a business decision: **what may be put in
one ordering together**.

## And this module is what makes the contract's fifth refusal true

`Ordering`'s validator documents five refusals and can implement four. The fifth —
*"a member outside the declared class"* — is unreachable there, because
`PrioritisedFinding` carries no aggregation class: the class is a property of the
**rule** that produced the candidate, and the placed finding does not carry it.

**So the claim is made true by construction here instead.** `one_ordering_per_class`
takes findings already grouped by class and never mixes two groups, so every member of
every ordering it builds is of the declared class — not because something checked
afterwards, but because nothing else was ever possible. The contract docstring now says
where the refusal lives rather than implying a check that is not there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from anomaly_investigation.contracts import AggregationClass

from ..contracts import Normalisation, NotPrioritisable, Ordering, PriorityContractViolation

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping, Sequence

    from ..contracts import PrioritisedFinding

__all__ = ["one_ordering_per_class", "single_normalised_ordering"]

#: One class's rank groups, best first. ``(a,), (b, c)`` is *a* first and *b*, *c* tied.
RankGroups = "tuple[tuple[PrioritisedFinding, ...], ...]"


def one_ordering_per_class(
    ranked: Mapping[AggregationClass, Sequence[Sequence[PrioritisedFinding]]],
    *,
    not_prioritisable: Sequence[NotPrioritisable] = (),
) -> tuple[Ordering, ...]:
    """One `Ordering` per class present, each declaring the class its members share.

    **The classes are never merged**, and that is the whole guarantee. A caller cannot
    ask this function for a single ordering across classes, because it has no parameter
    that would express one — `FR-005`'s forbidden third answer is not refused here, it
    is **unsayable**.

    ``not_prioritisable`` attaches to the FIRST ordering by class order, and this is
    stated because it is a choice: a finding that could not be placed has no class to
    belong to — its components are missing, which is why it is here at all — and
    duplicating it across every ordering would make `SC-002`'s "appears in both" refusal
    fire on a finding nobody placed twice. One ordering carries them; the rest carry
    none.

    Returns them ordered by the class enum so two runs over the same input produce the
    same sequence. **A run that answers a different order for the same input is a run
    whose output cannot be diffed**, and `005` paid for that lesson on figures.
    """
    orderings: list[Ordering] = []
    for index, aggregation_class in enumerate(
        sorted(ranked, key=lambda item: list(AggregationClass).index(item))
    ):
        groups = tuple(tuple(group) for group in ranked[aggregation_class])
        orderings.append(
            Ordering(
                aggregation_class=aggregation_class,
                positions=groups,
                not_prioritisable=tuple(not_prioritisable) if index == 0 else (),
            )
        )
    return tuple(orderings)


def single_normalised_ordering(
    ranked: Sequence[Sequence[PrioritisedFinding]],
    *,
    normalisation: Normalisation,
    classes_present: Sequence[AggregationClass],
    not_prioritisable: Sequence[NotPrioritisable] = (),
) -> Ordering:
    """One ordering across classes, and **only** under a normalisation that covers them.

    ``normalisation`` has no default and cannot be ``None``. That is the refusal, and it
    is a **signature** rather than a check: there is no way to call this function
    without declaring the basis, so the forbidden answer cannot be produced by omission.

    ``classes_present`` is required and is compared against what the normalisation
    claims to cover. Without it a caller could declare a normalisation over `COUNT` and
    `RATIO` and quietly include a `SNAPSHOT` — the vacuously-satisfied condition
    `Normalisation` already refuses in the small, extended here to the ordering it
    licenses.

    **Covering MORE than is present is refused too**, and that is deliberate: a
    normalisation claiming three classes over an ordering that holds two is a
    declaration nobody can check against this output, and it would let the same
    declaration license a later ordering that does hold the third.
    """
    present = set(classes_present)
    covered = set(normalisation.covers)

    if not present:
        raise PriorityContractViolation(
            "a normalised ordering must state which classes it holds; with none stated, "
            "the normalisation covers nothing that can be checked"
        )
    if present != covered:
        raise PriorityContractViolation(
            f"normalisation {normalisation.basis!r} covers "
            f"{sorted(c.value for c in covered)} but the ordering holds "
            f"{sorted(c.value for c in present)}; a normalisation licenses exactly the "
            "classes it names, and no others"
        )

    return Ordering(
        normalisation=normalisation,
        positions=tuple(tuple(group) for group in ranked),
        not_prioritisable=tuple(not_prioritisable),
    )
