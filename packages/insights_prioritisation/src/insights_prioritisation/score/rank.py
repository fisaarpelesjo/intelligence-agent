"""The rank key, and it is a tuple compared term by term — `D-A`, `D-A2`.

`nota(finding) = (magnitude * confidence, reach * confidence)`. Compare the first term;
compare the second **only** where the first ties. **No total, no sum, no weighted mean.**

## Why a tuple and not a number

The owner refused a composed score, and the refusal is not stylistic: a sum can rank a
finding first for reasons no reader can recover, because the number that comes out does
not say which ingredient produced it. A tuple keeps every ingredient visible in the
output and makes *"why is this first"* answerable by pointing at a term.

It also leaves `T014` untouched. That node compares component by component and never by
a composed score — a decision that needed a gate rewritten to fit it would have been a
decision loosening a gate.

## Confidence multiplies each term, and it can only push DOWN

`completeness_ratio` is bounded to [0, 1] by `001`'s own contract, so weighting never
promotes a finding above its unweighted position. That is `D-C` exactly: a big doubtful
finding **descends and stays visible**, and confidence is not a veto.

## What this module does NOT do

It does not filter by direction — that is `read/direction.py` and it happens BEFORE
ranking, because a fall and a rise do not compete inside one rule. It does not decide
which findings may share an ordering — that is `order/within_class.py`. And it never
places a finding whose components are not all obtained: `compose.may_compose` refuses
first, and a partial key would rank a finding by the ingredients that happened to
arrive.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts import PriorityContractViolation
from .components import DECLARED_COMPONENTS

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence
    from decimal import Decimal

    from ..contracts import PrioritisedFinding

__all__ = ["DECLARED_ORDER", "Z_SCORE_PER_METRIC", "rank_findings", "rank_key"]

#: The normalisation `D-B` chose, named so it can appear in the output.
#:
#: `FR-005` permits ordering stock and flow together and **forbids doing it silently**.
#: The owner chose *together, by z-score of each metric*, so an ordering that mixes
#: aggregation classes must carry this name in its `Normalisation` — a reader who cannot
#: see which scale was used cannot check the order they are being shown.
Z_SCORE_PER_METRIC = "z_score_per_metric"

#: The order the terms are compared in. Read from the declared registry rather than
#: written again here, so the two cannot disagree: a component added to the registry
#: without a place in the order would otherwise be silently ignored by the ranking.
DECLARED_ORDER: tuple[str, ...] = tuple(reader.name for reader in DECLARED_COMPONENTS)


def rank_key(finding: PrioritisedFinding) -> tuple[Decimal, ...]:
    """The tuple this finding is ordered by, highest first.

    **Every declared component must be present and carry a value.** A finding missing
    one is not ranked lower — it is not ranked at all, and `PrioritisedFinding` already
    refuses to exist with an absent component. Raising here rather than substituting is
    the same rule one layer up: a key built from what happened to arrive would order
    findings by which ingredients were available.
    """
    obtained = {component.name: component.value for component in finding.components}
    missing = [name for name in DECLARED_ORDER if obtained.get(name) is None]
    if missing:
        raise PriorityContractViolation(
            f"{finding.finding_id!r} cannot be ranked: {missing} carry no value. A key built "
            "from the components that happened to arrive orders findings by availability."
        )
    return tuple(obtained[name] for name in DECLARED_ORDER)  # type: ignore[misc]


def rank_findings(findings: Sequence[PrioritisedFinding]) -> tuple[PrioritisedFinding, ...]:
    """Order findings by the declared key, largest first.

    **Stable**, so two findings with equal keys keep the order they arrived in — and
    that order carries no claim: `order/ties.py` is what reports them as a tie, and this
    function never decides that two equal findings are ranked against each other.
    """
    return tuple(sorted(findings, key=rank_key, reverse=True))
