"""Authorization preflight — T062 (FR-011, FR-014, FR-015, FR-035, FR-078; SC-009, SC-036).

Calls `001`'s ``evaluate()`` **once**, with ``snapshot=None``. Gates 1-6 run
normally — authorisation is gate 3 — and gate 7 short-circuits on the absent
snapshot before anything needs observations. That is what makes "an authorization
failure costs nothing" true rather than aspirational: reading the governed
observation tables is a billed warehouse read, so it must not happen until the
principal is known to be entitled (`FR-014`).

No gate is re-implemented, re-ordered or inspected internally. Classification
reads the **public reason code only** (`FR-015`). A second authorization
implementation here would be a second source of truth for who may see what, and
the two would drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..decision.bridge import CatalogEvaluator, to_catalog_request
from ..execution.ledger import AuthorizationContext, UnresolvedAuthorizationContext
from ..identity.authorization_context import derive_authorization_fingerprint
from .classify import PreflightOutcome, classify_preflight

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date

    from semantic_catalog.contracts.audit_event import PrincipalType
    from semantic_catalog.loader.bundle import Bundle
    from semantic_catalog.validation.decision import CatalogDecision

    from ..contracts.request import AnalyticsQuery

__all__ = ["PreflightResult", "run_preflight"]


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """What the preflight established, and nothing more.

    ``fingerprint`` is present only when the request is authorized. An
    unauthorized principal produces no fingerprint, which is one more reason no
    ledger entry can exist for it.
    """

    outcome: PreflightOutcome
    decision: CatalogDecision
    fingerprint: str | None = None

    @property
    def may_incur_cost(self) -> bool:
        """Whether the request may proceed to anything that costs or writes state."""
        return self.outcome is PreflightOutcome.AUTHORIZED


def run_preflight(
    request: AnalyticsQuery,
    *,
    evaluate: CatalogEvaluator,
    bundle: Bundle,
    principal_type: PrincipalType,
    authorization_scope: str,
    granted_access_tags: frozenset[str],
    authorization_policy_pin: str,
    on: date,
) -> PreflightResult:
    """Settle authorisation before anything costs anything.

    Derives the authorization-context fingerprint from the same context this
    call resolved — so the fingerprint is a *record* of the authorization
    decision, never an independent one.
    """
    decision = evaluate(
        to_catalog_request(request, requester_access=tuple(sorted(granted_access_tags))),
        bundle,
        principal_type=principal_type,
        authorization_scope=authorization_scope,
        on=on,
        # Deliberately absent. Gates 1-6 run, gate 7 short-circuits, and no
        # observation is read until the principal is known to be entitled.
        snapshot=None,
    )
    outcome = classify_preflight(decision)
    if outcome is not PreflightOutcome.AUTHORIZED:
        # Terminal. No policy resolution, no limit disclosure, no ledger entry,
        # no observation read, zero cost.
        return PreflightResult(outcome=outcome, decision=decision)

    context = AuthorizationContext(
        authorization_scope=authorization_scope,
        granted_access_tags=granted_access_tags,
        principal_type=str(principal_type),
        authorization_policy_pin=authorization_policy_pin,
    )
    # Raises when the context is incomplete, so an unresolved context refuses
    # here — before ledger acquisition — rather than acquiring under a partial key.
    fingerprint = derive_authorization_fingerprint(context)
    return PreflightResult(outcome=outcome, decision=decision, fingerprint=fingerprint)


def unresolved_context_is_terminal(exc: UnresolvedAuthorizationContext) -> str:
    """The caller-safe wording for an unresolved authorization context.

    Names no scope, tag or pin: a principal whose context could not be resolved
    learns that the request refused, not what was missing.
    """
    _ = exc
    return "the authorization context could not be established"
