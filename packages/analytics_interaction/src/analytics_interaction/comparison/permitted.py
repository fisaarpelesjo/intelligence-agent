"""Permitted verdicts — T101 (FR-065; SC-019, SC-020).

**Two outcomes execute. Everything else refuses, and refuses the whole
comparison.**

```
ALLOW               → execute
ALLOW_WITH_CAVEAT   → execute, carrying every caveat unchanged
DENY                → refuse, with 001's own reason code
anything else       → refuse
```

**Why ``ALLOW_WITH_CAVEAT`` executes.** A caveat is a governed statement about
the answer, not a soft denial. Refusing one would throw away comparisons the
catalog said were valid — two sources that are **equivalently partial**, for
instance, where both sides are missing the same days and the comparison is
therefore sound while each side alone is qualified. `001` already made that call
in the comparability gate; second-guessing it here would be this feature
overruling the catalog on a governance question it does not own.

What executing does **not** mean is presenting the caveat quietly. The caveats
ride through both executions byte-for-byte, attributed to their origin, never
deduplicated across origins and never merged — `T125` and `T127` own that
carriage; this module's job is to make sure a caveated verdict still gets there.

**Why "partial versus complete" is different.** That is not a caveat, it is a
mismatch: one side complete, the other missing days. The difference between them
is an artefact of the missing days, and a reader cannot tell that from the
number. `001` denies it, and this module passes that denial through.

**Nothing is re-coded.** A denied verdict raises ``ComparisonDenied`` carrying
`001`'s decision whole — its reason code, its pt-BR message, its limitations, its
evidence. Restating it in this feature's vocabulary would tell a caller that the
*interaction* layer refused when the *catalog* did, and `FR-021` requires that a
refusal name where it actually came from.

**Nothing executes on the way through.** No port, no adapter, no bundle: this
module reads an outcome. `T102` counts the execution-port calls behind a denial
and expects zero — which is only assertable because there is no call site here
that could make one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from semantic_catalog.contracts.reason_codes import Outcome, outcome_for
from semantic_catalog.validation.decision import CatalogDecision

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.contracts.reason_codes import ReasonCode

__all__ = [
    "EXECUTABLE_OUTCOMES",
    "ComparisonDenied",
    "is_executable",
    "permitted_verdict",
]

#: The closed set. Written as a frozenset of `001`'s own members rather than as
#: two ``is`` comparisons, so that a third permissive outcome added upstream
#: fails `T101`'s membership test loudly instead of being silently excluded — or,
#: worse, silently included by an ``is not DENY`` inversion.
EXECUTABLE_OUTCOMES: frozenset[Outcome] = frozenset({Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT})


class ComparisonDenied(Exception):  # noqa: N818 - a governed refusal, not an error
    """`001` refused the comparison. The **whole** comparison, not a side.

    Carries the decision rather than a code alone: the pt-BR message, the
    limitations and the evidence refs are what a caller is entitled to see, and
    reducing them to a code here would make the refusal less accountable than the
    one the catalog issued.
    """

    def __init__(self, decision: CatalogDecision) -> None:
        self.decision = decision
        self.code: ReasonCode = decision.reason_code
        super().__init__(f"{decision.reason_code.value}: comparison denied")


def is_executable(decision: CatalogDecision) -> bool:
    """Whether this verdict permits execution. A question, not a gate.

    Separate from ``permitted_verdict`` so a caller that needs to *ask* — an
    audit stage, a disclosure that says which route was taken — does not have to
    catch an exception to find out, and so no caller is tempted to reimplement
    the membership test inline.
    """
    return decision.outcome in EXECUTABLE_OUTCOMES


def permitted_verdict(decision: object) -> CatalogDecision:
    """The verdict, if it permits execution. Otherwise refuse.

    Returns the decision unchanged so the caller keeps everything `001` said —
    the caveats especially, which must reach the answer intact.

    The parameter is typed ``object`` on purpose: this function's whole job is to
    be the thing that refuses what should not have arrived, and a signature that
    only admits a well-formed decision would make the malformed case a type
    error at the *call site* — where a caller with an ``Any`` in hand would sail
    straight past it. Fail-closed has to hold at runtime.

    Four ways in that are not a permitted verdict, and all four refuse:

    * **missing** — no verdict was obtained. Absence is never permission, and
      this is the shape the "forgot to evaluate" defect actually takes;
    * **malformed** — something that is not a ``CatalogDecision``. A duck-typed
      stand-in with an ``outcome`` attribute would pass an ``in`` test while
      carrying no evidence, no message and no reason code;
    * **denied** — `001` said no. Its own decision is raised;
    * **contradictory** — an outcome that disagrees with its reason code. `001`'s
      own validator rejects this at construction, so it is unreachable through
      the contract; checked anyway, because the alternative to a redundant check
      here is a comparison executing on a verdict that says two things.
    """
    if decision is None:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "no governed comparison verdict was obtained; absence is not permission",
        )

    if not isinstance(decision, CatalogDecision):
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "the comparison verdict is not a governed catalog decision",
        )

    if not is_executable(decision):
        raise ComparisonDenied(decision)

    # Read through `001`'s own mapping, never restated here — a second table
    # would be a second opinion about what a reason code means.
    if decision.outcome is not outcome_for(decision.reason_code):
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "the comparison verdict's outcome disagrees with its reason code",
        )

    return decision
