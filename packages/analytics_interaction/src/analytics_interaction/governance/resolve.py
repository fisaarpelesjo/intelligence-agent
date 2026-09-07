"""Exactly-one-effective resolution — T031 (FR-025; SC-035).

Four ways to be unresolvable, one outcome each for vocabulary and for policy:

| Condition at evaluation time | Result |
|---|---|
| Exactly one effective instance, all required fields present | Resolved |
| Zero effective | ``INTERPRETATION_*_UNRESOLVABLE`` — refuse |
| More than one effective | ``INTERPRETATION_*_UNRESOLVABLE`` — refuse |
| One effective, any required field missing | ``INTERPRETATION_*_UNRESOLVABLE`` — refuse |

**Nothing is ever substituted.** Not a default, not an inferred value, not a
value seen on a previous request, not a carry-forward from the last effective
instance. The pattern mirrors `002`'s `policy/resolve.py`, which already proves
that none-effective and many-effective both fail closed.

**Vocabulary and policy resolve separately** and carry separate versions, because
they are separately owned and separately approved (`DEP-3`, `DEP-4`). Merging
them would let a vocabulary addition ship without privacy review — which is the
whole reason there are two reason codes rather than one.

Today every governed file holds no approved instance, so resolution refuses every
dependent path. Designed, not missing.
"""

from __future__ import annotations

from collections.abc import Sized
from datetime import date

from ..contracts.reason_codes import InterpretationReasonCode
from .schemas import GovernedContent

__all__ = [
    "ContentUnresolvable",
    "is_absent",
    "resolve_effective",
]


class ContentUnresolvable(RuntimeError):  # noqa: N818 - named for its reason code
    """No single complete governed instance is in force.

    Carries the reason code rather than a message alone: the code selects the
    stored pt-BR wording and is what an audit event records. Which of the two
    codes it carries is supplied by the caller, because *this* function cannot
    know whether it was handed vocabulary or policy — and inferring it from the
    model type would silently pick a code when a new content kind arrived.
    """

    def __init__(self, code: InterpretationReasonCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


def resolve_effective[C: GovernedContent](
    candidates: tuple[C, ...],
    *,
    on: date,
    code: InterpretationReasonCode,
    required: tuple[str, ...] = (),
    kind: str,
) -> C:
    """The single instance effective on ``on``, or refuse.

    ``required`` names fields that must be present **and non-empty** on the
    surviving instance. It is re-checked here rather than trusted from
    construction: construction already requires them, so a failure can only mean
    an instance reached resolution without passing through the contract — which
    would mean the content in force is not the content that was approved.

    An empty collection counts as missing. A vocabulary with zero expressions is
    a legitimately empty *document*, but it is not a usable vocabulary for a
    question that needs one, and the difference between "the file is fine" and
    "the content answers nothing" must not be blurred at the point a question
    depends on it.

    The detail strings name no threshold, bound, expiry or rule. An unresolvable
    policy must not disclose the policy by way of the message that says it is
    missing.
    """
    effective = tuple(candidate for candidate in candidates if candidate.is_effective_on(on))

    if len(effective) != 1:
        # Zero and many are one refusal with two details. Zero means nobody has
        # approved this content; many means two governed answers are
        # simultaneously authoritative and picking one would be picking
        # arbitrarily. Same code either way — the caller learns that the content
        # does not resolve, not how the governed files are arranged.
        raise ContentUnresolvable(
            code,
            f"no approved {kind} is in force; no default is substituted"
            if not effective
            else f"more than one governed {kind} is effective; the content is ambiguous",
        )

    resolved = effective[0]
    missing = [name for name in required if is_absent(getattr(resolved, name, None))]
    if missing:
        raise ContentUnresolvable(
            code,
            f"the effective governed {kind} is incomplete; it is unresolvable, "
            "not partially usable",
        )
    return resolved


def is_absent(value: object) -> bool:
    """``None``, or an empty collection.

    Zero and ``False`` are **present**: a governed value of zero is a decision
    somebody made, and treating it as absent would substitute a refusal for an
    approved answer. Public because the distinction is a governed rule worth
    asserting directly, not an implementation detail of this module.
    """
    if value is None:
        return True
    return isinstance(value, Sized) and len(value) == 0
