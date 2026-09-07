"""Preflight result classification — T028 (FR-011, FR-012, FR-013, FR-014; SC-009).

``AUTHORIZATION_DENIAL_CODES`` is exactly the set `001`'s gate 3 can emit,
which is where `FR-012` and `FR-013` are discharged: unknown, deprecated and
scope-mismatched tags each classify as a denial, and a deprecated tag is
never silently replaced by its successor — there is no code path that reads
``replacement_tag`` and proceeds.

`FR-014` requires an authorization failure to be terminal with **no cost
incurred**, and a read of the governed observation tables is a billed warehouse
read. So authorization is settled first, by calling `001`'s ``evaluate()`` with
``snapshot=None``: gates 1-6 run normally, including authorisation at gate 3, and
gate 7 short-circuits on the absent snapshot before anything needs observations.

Classification reads **only the public ``reason_code``** of the returned
decision. No internal state is inspected, no gate is re-implemented and no gate
order is changed — `FR-015` forbids all three, and a second authorization
implementation would be a second source of truth for who may see what.

`001` publishes no gate-scoped code constant — ``codes_with_outcome`` classifies
by *outcome*, not by gate — so the set below is declared here and pinned by a
contract test against the merged gate module and the decision contract. Upstream
drift then fails CI rather than silently mis-classifying a refusal as a pass.
Publishing that set upstream would be the better seam; ADR 0009 records it as a
future prerequisite rather than taking it now.
"""

from __future__ import annotations

from enum import StrEnum

from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.validation.decision import CatalogDecision

__all__ = [
    "AUTHORIZATION_DENIAL_CODES",
    "SNAPSHOT_ABSENCE_SENTINEL",
    "PreflightOutcome",
    "classify_preflight",
]

#: Exactly the four codes `001`'s authorisation gate can emit. Pinned by T034.
AUTHORIZATION_DENIAL_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.ACCESS_DENIED,
        ReasonCode.ACCESS_TAG_UNKNOWN,
        ReasonCode.ACCESS_TAG_DEPRECATED,
        ReasonCode.ACCESS_TAG_SCOPE_MISMATCH,
    }
)

#: Gate 7 emits this when no snapshot was supplied. In the **preflight** it can
#: only mean "snapshot absent", because this feature deliberately passed ``None``
#: and gate 7 short-circuits before gate 8 is reached. The reading is confined to
#: the preflight call and is never applied to the full evaluation, where a real
#: snapshot is always supplied and the same code carries its ordinary meaning.
SNAPSHOT_ABSENCE_SENTINEL: ReasonCode = ReasonCode.SOURCE_STATE_UNKNOWN


class PreflightOutcome(StrEnum):
    """What the preflight proved."""

    #: Gate 3 denied. Terminal: no policy resolution, no limit disclosure, no
    #: ledger entry, no observation read, zero cost.
    AUTHORIZATION_DENIED = "authorization_denied"
    #: Some other gate denied. Also terminal, also at zero cost, but the refusal
    #: is passed through verbatim rather than restated in this feature's words.
    REFUSED_UPSTREAM = "refused_upstream"
    #: Gates 1-6 all passed, including gate 3. Proceed to policy, ledger,
    #: observations and the full evaluation.
    AUTHORIZED = "authorized"


def classify_preflight(decision: CatalogDecision) -> PreflightOutcome:
    """Classify a ``snapshot=None`` evaluation using its public reason code only.

    An ``ALLOW`` or ``ALLOW_WITH_CAVEAT`` result means the request had no required
    sources for gates 7-8 to evaluate, so gate 3 passed and the request is
    authorized. Any other outcome is read from the code.
    """
    code = decision.reason_code
    if code in AUTHORIZATION_DENIAL_CODES:
        return PreflightOutcome.AUTHORIZATION_DENIED
    if decision.outcome is not Outcome.DENY:
        return PreflightOutcome.AUTHORIZED
    if code == SNAPSHOT_ABSENCE_SENTINEL:
        return PreflightOutcome.AUTHORIZED
    return PreflightOutcome.REFUSED_UPSTREAM


def incurs_cost(outcome: PreflightOutcome) -> bool:
    """Whether the request may proceed to anything that costs or writes state."""
    return outcome is PreflightOutcome.AUTHORIZED
