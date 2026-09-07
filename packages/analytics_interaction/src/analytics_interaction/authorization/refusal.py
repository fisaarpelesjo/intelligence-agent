"""The single authorization refusal — T045 (FR-087; SC-050).

**One code, one message, for every way the authorization context can fail to
resolve.**

`contracts/reason-codes.md` §3 declares exactly one authorization code —
deliberately, not for economy:

    Deliberately **one** code, not four. Distinguishing *which* part of the
    context failed to resolve would tell an unauthenticated caller something
    about the identity system's shape.

The same argument extends past the four parts to the mechanics. "No resolver was
configured", "the resolver timed out", "that principal is unknown" and "your
scope does not match" are four different sentences, and a caller who can tell
them apart can map the identity system by probing it. So the refusal carries a
fixed detail string, built from no input and varying with nothing.

That constancy is a **security property**, and it is asserted rather than
documented: `T047` drives every failure mode through and compares the serialised
refusals byte for byte.

Nothing here reads or echoes the question, the principal reference, a token, a
claim or any part of the resolver's answer. A refusal that quoted the input would
put an identity claim into whatever logged the refusal.
"""

from __future__ import annotations

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "AUTHORIZATION_REFUSAL_DETAIL",
    "AuthorizationRefused",
    "authorization_refusal",
]

#: The one detail string. A module-level constant rather than a literal at each
#: raise site, so "every failure mode produces identical output" is true by
#: construction instead of by six authors agreeing.
#:
#: It names no part of the context, no resolver, no principal and no limit. It
#: states what happened — the context did not completely resolve — and what
#: follows from it, which is the only thing the caller can act on.
AUTHORIZATION_REFUSAL_DETAIL = (
    "the authorization context did not completely resolve; no catalog read, "
    "term resolution, clarification, governed request or limit disclosure was performed"
)


class AuthorizationRefused(Exception):  # noqa: N818 - named for the governed outcome
    """Raised by the step-2 preflight. Terminal, and carries no diagnostic.

    Takes **no arguments**. A constructor accepting a reason would be a
    constructor through which a caller could eventually be told one, and the
    first well-meaning `except` clause that surfaced it would undo the
    non-disclosure this class exists for.

    Deriving from ``Exception`` rather than ``ContractViolation`` keeps the two
    distinguishable in a handler: a contract violation says a structure was
    malformed, this says the asker was never established.
    """

    code = InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE
    detail = AUTHORIZATION_REFUSAL_DETAIL

    def __init__(self) -> None:
        super().__init__(f"{self.code.value}: {self.detail}")


def authorization_refusal() -> ContractViolation:
    """The refusal as a governed contract violation, for a caller that wants one.

    Takes no arguments for the same reason ``AuthorizationRefused`` does, and
    returns a value equal to every other call — the code selects the stored pt-BR
    wording, and the wording is what the caller actually sees.
    """
    return ContractViolation(
        InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
        AUTHORIZATION_REFUSAL_DETAIL,
    )
