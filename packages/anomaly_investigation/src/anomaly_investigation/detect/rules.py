"""The baseline's first detection level — T018 (`FR-002`).

`proactive_insights.detection_levels.business_rules` is declared `priority: first`
and `enabled: true`, and it names **eight** methods. This module implements from
that list and refuses anything outside it.

**The other two levels are out of scope by priority, not by prohibition**, and the
distinction is worth keeping straight: `robust_statistics` is `enabled: true` and
is the baseline's *second* level, so a later feature may reach it;
`time_series_models` is `enabled: false`, and `FR-002` forbids enabling it here.
Reading "out of scope" as "forbidden" would misreport the baseline.

**Nothing here computes a figure.** A method says *which comparison a rule is
asking for*; the arithmetic is `003`'s, asked for through the ports (`FR-003`).
"""

from __future__ import annotations

from ..contracts import AnomalyReasonCode, DetectionMethod

__all__ = ["GOVERNED_METHODS", "method_or_refusal"]

#: The eight, read from the baseline rather than remembered. `DetectionMethod`
#: carries them; this name states that the enum **is** the governed list, so a
#: reader does not have to trust that the enum was built from the file.
GOVERNED_METHODS: frozenset[DetectionMethod] = frozenset(DetectionMethod)


def method_or_refusal(method: str) -> tuple[DetectionMethod | None, AnomalyReasonCode | None]:
    """Resolve a method name, or say which governed word refuses it.

    Returns a pair rather than raising, because a run reports refusals per rule
    and an exception would end the run for every other rule with it.
    """
    try:
        resolved = DetectionMethod(method)
    except ValueError:
        return None, AnomalyReasonCode.ANOMALY_RULE_METHOD_NOT_GOVERNED
    return resolved, None
