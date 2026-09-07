"""Comparability caveat attachment — T083 (FR-031).

A permitted-but-not-identical comparison carries **the caveat its rule
declares**, in the pt-BR a reviewer wrote, not a sentence composed at answer
time.

The distinction matters and is easy to lose. The governed message registry
supplies the wording for the *reason code* — "a comparação é permitida com
ressalva…" — which is generic by design, because one message serves every
caveated pair. The **rule's** caveat is specific: it says why *these two* differ
and what that does to the number. Emitting only the generic one would tell a
reader that something is off without telling them what, which is the same as not
telling them.

So both travel: the reason code carries its governed message, and the declared
caveat rides as a :class:`Limitation` naming the pair it applies to.

A refusal is treated the same way. FR-030 requires the **business reason** for a
non-combinable pair, and the rule states it; a bare ``METRICS_NOT_COMPARABLE``
sends the reader to build their own number.
"""

from __future__ import annotations

from ..contracts.reason_codes import ReasonCode
from ..validation.decision import Limitation
from .gate import ComparabilityCheck

__all__ = ["caveat_limitations", "declared_text"]


def declared_text(check: ComparabilityCheck) -> str | None:
    """The authored pt-BR the rule carries for this outcome.

    ``caveat`` for a permitted comparison, ``reason`` for a refusal. ``None``
    when the rule is absent — there is nothing authored to quote, and inventing
    a sentence is exactly what FR-055 forbids.
    """
    if check.rule is None:
        return None
    if check.reason_code is ReasonCode.COMPARABLE_WITH_CAVEAT:
        return check.rule.content.caveat or check.rule.content.reason
    if check.reason_code is ReasonCode.METRICS_NOT_COMPARABLE:
        return check.rule.content.reason
    return None


def caveat_limitations(checks: tuple[ComparabilityCheck, ...]) -> tuple[Limitation, ...]:
    """Declared caveats and reasons, as limitations on the decision.

    Sorted by the pair they apply to so two identical requests produce identical
    limitations — an answer whose caveats reorder between runs is an answer two
    readers would quote differently.
    """
    limitations: list[Limitation] = []
    for check in checks:
        text = declared_text(check)
        if not text or check.reason_code is None:
            continue
        limitations.append(
            Limitation(
                code=check.reason_code.value,
                message_pt_br=text,
                applies_to=check.pair.describe(),
            )
        )
    return tuple(sorted(limitations, key=lambda limitation: limitation.applies_to))
