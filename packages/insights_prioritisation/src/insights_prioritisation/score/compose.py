"""Compose the declared components, or refuse — T011.

**Refuses to compose when ANY declared component is absent, rather than composing what
is present.** That is the whole content of this module, and the reason is arithmetic:
composing three of four components produces a number on a different scale from a
finding that had all four, and the two then sort against each other as if they were
comparable. A finding placed on partial grounds is not placed *lower* — it is placed
**wrongly**, and nothing downstream can tell.

## Why the composition itself is not written here

**How the declared components combine is `D-A`**, exactly as *which* components exist
is. A sum, a product, a weighted mean and a lexicographic order all "compose" and they
rank differently; picking one here would answer a question `spec.md` records as the
owner's, by shipping.

So this module owns the part that is **not** a business decision: **whether composing is
permitted at all**. It answers that from the components themselves — every one carries a
value, or it does not — and hands the arithmetic to a rule that arrives with `D-A`.

`spec.md` § 2 names the defect this prevents in its own words: *a missing component
defaulted to zero silently ranks something last*, and zero *"does not express ignorance
— it expresses this finding is unimportant"*.

## The empty case, and it is not a special case

With no component declared -- which is where `D-A` leaves things today -- a finding has
no grounds at all. **That refuses too**, and it refuses through the same door: `Ordering`
is a placed finding plus the not-prioritisable ones, and a finding placed on zero
components would be a position with nothing behind it, which `FR-002` forbids by
requiring the position to be reconstructible from its output.

**It is not written as an `if not components` branch**, because that would make "no
grounds" a case somebody could later special-case away. It falls out of the rule that
every declared component must carry a value: with none declared, none carries one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts import PriorityComponent

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = ["absent_components", "may_compose"]


def absent_components(components: Sequence[PriorityComponent]) -> tuple[PriorityComponent, ...]:
    """Every component that carries an absence instead of a value.

    Returns the components rather than their names, because
    :class:`NotPrioritisable` carries *what was obtained and what was not* — a caller
    building one needs the absences themselves, and re-deriving them from names would
    be the second lookup that drifts.
    """
    return tuple(component for component in components if component.absence is not None)


def may_compose(components: Sequence[PriorityComponent]) -> bool:
    """Whether these components may be composed into a position at all.

    **True only when there is at least one component and every one carries a value.**

    The first half is not a guard bolted on: a position resting on nothing is not a
    position, and `FR-002` requires an ordering to be reconstructible from its output.
    Today it is the only half that fires, because `D-A` is open and
    `DECLARED_COMPONENTS` is empty.

    The second half is `FR-004`. **It says nothing about which components should be
    there** — only that whatever the caller obtained must be complete. A caller that
    passed a shorter list would pass this and be wrong, which is why the list comes
    from `read_components` over the declared registry rather than from the caller's
    judgement.
    """
    return bool(components) and not absent_components(components)
