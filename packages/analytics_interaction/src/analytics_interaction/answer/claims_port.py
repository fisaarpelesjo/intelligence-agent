"""The port that turns an execution result into typed claims (`FR-033`, `SC-009`).

Authorized by the owner on 2026-08-20, item A. **No task number**, for the reason
`interpretation/boundary_port.py` records: the nearby `T1xx` numbers belong to the blocked
credential tasks.

Step 16 assembles an answer from claims. Nothing built them. ``ask()`` passed ``claims=()`` against
a contract requiring at least one, so **no question could be answered through this entry point**,
whatever the governed content said. That was measured, not inferred.

## Why the construction is behind a port

Deciding which claims a result produces is interpretation, and interpretation of a *result* is not
the same act as interpretation of a *question*. The question side is slot-filling over a governed
vocabulary and lives in this package. The result side needs to know what the deployment considers a
finding — one claim per row, one per metric, a total, a comparison — and that is a reporting
decision this feature has no authority to make.

So the shape is fixed here and the choice is the deployment's, exactly as `ExecutionPort` fixes what
may be asked of the warehouse without deciding what the warehouse holds.

## What crosses the port, and what cannot

**In:** the governed plan, the result the plan produced, and the claim classes `D-18` words. Three
values, and deliberately not a fourth — the question text is **not** among them. A constructor that
could read the question could build a claim from what the user typed, which is the one thing
`FR-053` forbids an answer to contain.

**Out:** ``AnswerClaim`` values, the contract that already exists. The port produces no new type: a
claim shape invented here would be a second definition of what an answer element is, and
``AnalyticsAnswer`` would then accept two.

## What this feature checks about what comes back

:func:`assert_claims_are_authorised` runs on every returned tuple, at the call site, because a
constructor is deployment code:

1. **every subject is traceable.** A claim's subject must be an identifier the plan authorised or a
   dimension label the result itself carried. A subject that is neither is a fabricated identifier —
   ``IDENTIFIER_FABRICATED`` — and that is the check that structurally prevents a span of the
   question from arriving as a claim subject.
2. **every unit was declared by the result.** A number presented in a unit no column declared is a
   number whose meaning was chosen after the fact.
3. **numeric classes carry numbers and the others do not**, which ``AnswerClaim`` already enforces
   on construction; the assertion here names it so the port's contract reads completely in one
   place.

## An empty result refuses, and refuses through the existing contract

A result with no rows produces no factual claims, and an answer with no claims is refused by
``AnalyticsAnswer.claims`` requiring ``min_length=1``. That refusal is deliberate and is not
re-implemented here: an empty warehouse answer is not an answer of zero, and turning it into one
would be the fabrication this whole path exists to prevent.

**No implementation ships in this package.** Same reason as `RedactionMatcher` and
`PeriodBoundaryResolverPort`: what counts as a finding is the deployment's declaration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..contracts._base import ContractViolation
from ..contracts.answer import NUMERIC_CLAIM_CLASSES
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:
    from analytics_query.contracts.request import AnalyticsQuery
    from analytics_query.contracts.result import AnalyticsResult

    from ..contracts.answer import AnswerClaim
    from ..governance.schemas import ClaimClassContent

__all__ = ["ClaimConstructionPort", "assert_claims_are_authorised"]


@runtime_checkable
class ClaimConstructionPort(Protocol):
    """Build the typed claims one governed result supports.

    No annotation here is ``Any`` or ``object``. The question text is absent from the signature by
    design — see the module docstring.
    """

    def __call__(
        self,
        *,
        plan: AnalyticsQuery,
        result: AnalyticsResult,
        classes: tuple[ClaimClassContent, ...],
    ) -> tuple[AnswerClaim, ...]:
        """The claims this result supports, or an empty tuple.

        Returning ``()`` is the honest answer for a result that supports none, and assembly refuses
        it. Inventing a claim to avoid the refusal is the failure this port exists to prevent.
        """
        ...


def assert_claims_are_authorised(
    claims: tuple[AnswerClaim, ...],
    *,
    plan: AnalyticsQuery,
    result: AnalyticsResult,
) -> None:
    """Refuse any claim naming something the plan did not authorise or the result did not carry.

    Reads the allowlist off the plan and the result rather than accepting one, because a caller that
    supplied the allowlist would be a caller that could widen it.
    """
    subjects = set(plan.metrics) | set(plan.dimensions)
    for row in result.rows:
        subjects.update(row.labels)
    units = {column.unit for column in result.columns}

    for claim in claims:
        if claim.subject not in subjects:
            raise ContractViolation(
                InterpretationReasonCode.IDENTIFIER_FABRICATED,
                "a claim names a subject the authorised plan did not carry and the result did "
                "not label; no subject is accepted from outside those two",
            )
        if claim.unit is not None and claim.unit not in units:
            raise ContractViolation(
                InterpretationReasonCode.IDENTIFIER_FABRICATED,
                "a claim presents a unit no result column declared",
            )
        if claim.claim_class not in NUMERIC_CLAIM_CLASSES and claim.value is not None:
            raise ContractViolation(  # pragma: no cover - AnswerClaim refuses this on construction
                InterpretationReasonCode.IDENTIFIER_FABRICATED,
                "a non-numeric claim class carries a value",
            )
