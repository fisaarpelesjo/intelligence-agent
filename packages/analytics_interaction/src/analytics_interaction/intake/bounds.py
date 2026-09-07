"""The governed question-length bound — T057 (FR-003; SC-002).

**Step 4, and the first step permitted to disclose a governed value.**

`intake-contract.md` §6 draws the line precisely. Step 1 enforces a *structural
contract ceiling* and refuses without naming a number, because the principal is
not yet proven entitled to be told one. Step 2 proves they are. Step 4 therefore
applies the governed `D-19` bound and **may name it** (`FR-003` and `FR-101`
together).

The ordering is enforced by the signature, not by a comment: ``authorized`` is a
required ``AuthorizedContext``, which only the step-2 preflight produces. A caller
cannot reach this function without having passed authorization, and nothing here
has to remember to check.

**Nothing is invented.** ``question_length_bound`` is `D-19` content. This module
declares no default, no fallback and no "reasonable" value — while the policy is
unresolvable the question refuses with the governed code, which is the designed
state, not a gap.
"""

from __future__ import annotations

from ..authorization.context_preflight import AuthorizedContext
from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode
from ..governance.schemas import InterpretationPolicy

__all__ = ["apply_governed_length_bound"]


def apply_governed_length_bound(
    text: str,
    *,
    authorized: AuthorizedContext,
    policy: InterpretationPolicy,
) -> None:
    """Refuse a question longer than the governed bound, naming the bound.

    ``authorized`` is unused by the arithmetic and required by the contract. That
    is the point: it is the type-level proof that step 2 ran, and it is what makes
    "disclosure follows authorization" a property of the call graph rather than a
    convention. A future edit that dropped it would have to delete a documented
    parameter.

    ``policy`` is passed in already resolved rather than resolved here, so this
    function has one job and the fail-closed behaviour lives in one place —
    `governance/policy.py`, which refuses with
    ``INTERPRETATION_POLICY_UNRESOLVABLE`` when no single complete instance is in
    force. A caller that could not resolve a policy never reaches this function.

    The refusal names the bound because, by this step, the caller has been proven
    entitled to hear it — and a length refusal that will not say the length is a
    refusal the caller cannot act on.
    """
    _ = authorized  # required for ordering; see the docstring

    if len(text) > policy.question_length_bound:
        raise ContractViolation(
            InterpretationReasonCode.QUESTION_EXCEEDS_GOVERNED_LIMIT,
            f"the question exceeds the governed length bound of "
            f"{policy.question_length_bound} characters",
        )
