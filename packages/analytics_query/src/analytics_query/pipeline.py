"""The ordered request pipeline — T063 (FR-011, FR-014, FR-016; SC-009).

The order **is** the security property. Steps 1-3 are the entire
pre-authorization surface, and none of them costs anything, discloses a policy
limit, or touches the ledger:

======  ============================================  ========  =======  ==========
 Step    What happens                                   Costs    Ledger   Discloses
======  ============================================  ========  =======  ==========
  1      Parse and structurally validate                  no       no        no
  2      Authorization preflight, ``snapshot=None``       no       no        no
  3      Denied → terminal refusal, refusal audit         no       no        no
  4      Resolve governed ``QueryPolicy``                 no       no        —
  5      Enforce range length                             no       no       yes
  6      Derive ``ExecutionKey``; acquire on the ledger   no      yes        —
  7      Self-read one atomic ``ObservationBundle``      yes        —        —
  8      Full evaluation with the snapshot                —        —         —
======  ============================================  ========  =======  ==========

Step 5 discloses a limit only because step 2 already proved the principal is
entitled to be told one. Step 6 is the first write of any kind; step 7 is the
first billed read. An unauthorized principal terminates at step 3 having caused
neither.

The `001` gates are called, never re-implemented — `evaluate()` is the sole gate
entry point in both phases (`FR-015`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from .authorization.classify import PreflightOutcome
from .authorization.preflight import run_preflight
from .contracts._base import ContractViolation
from .contracts.reason_codes import AnalyticsReasonCode
from .execution.ledger import UnresolvedAuthorizationContext
from .identity.authorization_context import execution_key_for
from .identity.normalize import derive_identity
from .observations.failure import read_bundle_or_refuse
from .policy.limits import assert_range_within_limit
from .policy.resolve import PolicyUnresolvable, refusal_for, resolve_policy

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date

    from semantic_catalog.contracts.audit_event import PrincipalType
    from semantic_catalog.loader.bundle import Bundle
    from semantic_catalog.validation.decision import CatalogDecision

    from .contracts.policy import QueryPolicy
    from .contracts.request import AnalyticsQuery
    from .decision.bridge import CatalogEvaluator
    from .execution.ledger import AuthorizationContext, ExecutionKey, ExecutionLedger
    from .observations.reader import ObservationBundle, ObservationReader

__all__ = ["PipelineRefusal", "PipelineState", "run_until_evaluation"]


class PipelineRefusal(Exception):  # noqa: N818 - a governed refusal, not an error
    """The request stopped, with the governed reason it stopped for."""

    def __init__(self, violation: ContractViolation, *, stage: str) -> None:
        self.violation = violation
        self.code = violation.code
        self.stage = stage
        super().__init__(f"{stage}: {violation}")


@dataclass(frozen=True, slots=True)
class PipelineState:
    """Everything established by the time the full evaluation is reachable."""

    decision: CatalogDecision
    policy: QueryPolicy
    execution_key: ExecutionKey
    observations: ObservationBundle


def run_until_evaluation(
    request: AnalyticsQuery,
    *,
    evaluate: CatalogEvaluator,
    catalog_bundle: Bundle,
    ledger: ExecutionLedger,
    observations: ObservationReader,
    context: AuthorizationContext,
    correlation_id: str,
    principal_ref: str,
    on: date,
    catalog_release_id: str,
    required_sources: frozenset[str],
) -> PipelineState:
    """Drive steps 2-7 in order and return what they established.

    Step 1 (structural validation) already happened: ``request`` exists, and it
    could not have been constructed from a malformed input.
    """
    # --- steps 2-3: authorisation, before anything costs or writes -----------
    preflight = run_preflight(
        request,
        evaluate=evaluate,
        bundle=catalog_bundle,
        principal_type=cast("PrincipalType", context.principal_type),
        authorization_scope=context.authorization_scope,
        granted_access_tags=context.granted_access_tags,
        authorization_policy_pin=context.authorization_policy_pin,
        on=on,
    )
    if preflight.outcome is PreflightOutcome.AUTHORIZATION_DENIED:
        raise PipelineRefusal(
            ContractViolation(
                preflight.decision.reason_code,  # type: ignore[arg-type]
                "the request is not authorized",
            ),
            stage="authorization",
        )
    if preflight.outcome is PreflightOutcome.REFUSED_UPSTREAM:
        # Passed through verbatim rather than restated in this feature's words.
        raise PipelineRefusal(
            ContractViolation(
                preflight.decision.reason_code,  # type: ignore[arg-type]
                "the catalog refused the request",
            ),
            stage="upstream",
        )

    # --- step 4: governed policy, or refuse ---------------------------------
    try:
        policy = resolve_policy(on)
    except PolicyUnresolvable as exc:
        raise PipelineRefusal(refusal_for(exc), stage="policy") from exc

    # --- step 5: limits, now that disclosure is permitted -------------------
    try:
        assert_range_within_limit(request.date_range, policy)
    except ContractViolation as exc:
        raise PipelineRefusal(exc, stage="limits") from exc

    # --- step 6: execution key, then the first write ------------------------
    identity = derive_identity(
        request, policy_version=policy.version, catalog_release_id=catalog_release_id
    )
    try:
        key = execution_key_for(identity.fingerprint, context)
    except UnresolvedAuthorizationContext as exc:
        # Before acquisition, deliberately. A partial key would file the request
        # into the wrong isolation class.
        raise PipelineRefusal(
            ContractViolation(
                AnalyticsReasonCode.LEDGER_UNAVAILABLE,
                "the authorization context could not be established",
            ),
            stage="execution_key",
        ) from exc

    ledger.acquire(key, correlation_id=correlation_id, principal_ref=principal_ref)

    # --- step 7: the first billed read --------------------------------------
    observations_bundle = read_bundle_or_refuse(
        observations, source_ids=required_sources, correlation_id=correlation_id
    )

    return PipelineState(
        decision=preflight.decision,
        policy=policy,
        execution_key=key,
        observations=observations_bundle,
    )
