"""Gate 6 (comparability) adapter — T082 (FR-029, FR-030, FR-031).

The rules live in ``comparability/gate.py``; this is the pipeline-facing gate
that turns them into a verdict.

**Denials outrank caveats within the gate.** A request forming three pairs where
one is ``not_comparable`` and another is ``comparable_with_caveat`` is refused —
a caveat cannot soften a pair the catalog says must not be compared at all. And a
missing rule is a denial, not a shrug: absence of a rule is not permission.
"""

from __future__ import annotations

from ...comparability.gate import check_comparability
from ...contracts.reason_codes import ReasonCode
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, caveat, deny

__all__ = ["gate_6_comparability"]

#: Checked in this order so the blunter refusal is the one reported.
_DENIALS = (ReasonCode.METRICS_NOT_COMPARABLE, ReasonCode.COMPARABILITY_RULE_MISSING)


def gate_6_comparability(context: GateContext) -> GateVerdict | None:
    """Refuse any pair no governed rule authorises."""
    checks = check_comparability(
        context.bundle.internal.comparability_rules,
        context.request.metrics,
        context.request.sources,
    )
    if not checks:
        return None

    for code in _DENIALS:
        offending = next((c for c in checks if c.reason_code is code), None)
        if offending is None:
            continue
        detail = f"{offending.pair.describe()}: " + (
            offending.rule.content.reason
            if offending.rule is not None and offending.rule.content.reason
            else "no governed comparability rule authorises this pair"
        )
        return deny(code, SubjectKind.REQUEST, offending.pair.describe(), detail)

    caveated = next((c for c in checks if c.is_caveat), None)
    if caveated is not None:
        return caveat(
            ReasonCode.COMPARABLE_WITH_CAVEAT,
            SubjectKind.REQUEST,
            caveated.pair.describe(),
            f"{caveated.pair.describe()}: comparison permitted with the declared caveat",
        )

    return None
