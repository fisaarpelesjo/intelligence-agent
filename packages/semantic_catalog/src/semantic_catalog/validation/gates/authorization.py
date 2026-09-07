"""Gate 3 (authorisation) — T053 (FR-042, FR-073).

**Runs before Gate 4, and that ordering is the requirement.** A combination check
that ran first would refuse "you cannot slice this by app_version" and, in doing
so, tell a requester who may not see the metric that it exists, what dimensions
it has and which source it lives on. Authorising first means a refusal discloses
nothing about shape (US2 scenario 5, decision-contract §4).

Every tag resolution failure denies, and each failure has its own stable code so
the reader knows whether to ask for access, use a different tag, or stop:

``ACCESS_TAG_UNKNOWN`` · not in the registry, or held by nobody
``ACCESS_TAG_DEPRECATED`` · retired — **the replacement is never auto-granted**
``ACCESS_TAG_SCOPE_MISMATCH`` · real tag, wrong authorisation scope
``ACCESS_DENIED`` · the principal simply does not hold what the metric requires

The replacement rule is the one worth stating twice: a deprecated tag denies even
when it names a valid successor. Inheriting authorisation from a retired tag is
how stale access survives a cleanup, so the replacement must be presented and
evaluated on its own merits.
"""

from __future__ import annotations

from ...contracts.access_tag import TagDenial
from ...contracts.reason_codes import ReasonCode
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, deny

__all__ = ["DENIAL_TO_REASON", "authorises_metric", "gate_3_authorization"]

#: One stable reason code per registry denial. ``PRINCIPAL_TYPE_MISMATCH`` maps
#: to ``ACCESS_DENIED`` rather than a tag-specific code: the tag is fine, the
#: principal is not, and saying otherwise would misdirect the reader.
DENIAL_TO_REASON = {
    TagDenial.UNKNOWN: ReasonCode.ACCESS_TAG_UNKNOWN,
    TagDenial.NOT_YET_EFFECTIVE: ReasonCode.ACCESS_TAG_UNKNOWN,
    TagDenial.DEPRECATED: ReasonCode.ACCESS_TAG_DEPRECATED,
    TagDenial.SCOPE_MISMATCH: ReasonCode.ACCESS_TAG_SCOPE_MISMATCH,
    TagDenial.PRINCIPAL_TYPE_MISMATCH: ReasonCode.ACCESS_DENIED,
}


def authorises_metric(context: GateContext, metric_id: str) -> bool:
    """Whether this principal could have asked for ``metric_id`` directly.

    Same registry, same rules, no verdict. It exists so a refusal about metric A
    can decide whether it may name metric B — disclosing a deprecation
    replacement the requester is not authorised to see would leak a relationship
    between two metrics through a refusal (FR-064).

    Fails closed on every unknown: no registry, no metric, any tag denial, or a
    tag the principal does not hold.
    """
    catalog = context.bundle.internal
    registry = catalog.access_tags
    metric = catalog.metrics.get(metric_id)
    if registry is None or metric is None:
        return False
    denial = registry.authorize(
        metric.access,
        principal_type=context.principal_type,
        authorization_scope=context.authorization_scope,
        on=context.on,
    )
    return denial is None and metric.access in frozenset(context.request.requester_access)


def gate_3_authorization(context: GateContext) -> GateVerdict | None:
    """Authorise every requested metric against the governed tag registry."""
    catalog = context.bundle.internal
    registry = catalog.access_tags

    if context.policy.authorization.require_access_tag and registry is None:
        # No registry means no defined input domain, so "authorised" would mean
        # whatever the caller passed in. Deny, do not proceed unauthenticated.
        return deny(
            ReasonCode.ACCESS_TAG_UNKNOWN,
            SubjectKind.ACCESS_TAG,
            "registry",
            "no access-tag registry is authored; authorisation cannot be resolved",
        )

    held = frozenset(context.request.requester_access)

    for metric_id in context.request.metrics:
        metric = catalog.metrics[metric_id]
        required = metric.access

        if registry is None:
            continue

        denial = registry.authorize(
            required,
            principal_type=context.principal_type,
            authorization_scope=context.authorization_scope,
            on=context.on,
        )
        if denial is not None:
            return deny(
                DENIAL_TO_REASON[denial],
                SubjectKind.ACCESS_TAG,
                required,
                f"access tag {required!r} did not authorise: {denial.value}",
            )

        # The tag is valid; the question is whether this requester holds it.
        # Reported against the METRIC, not the tag, because naming the tag the
        # requester lacks is the one disclosure this gate can safely make.
        if required not in held:
            return deny(
                ReasonCode.ACCESS_DENIED,
                SubjectKind.METRIC,
                metric_id,
                f"requester does not hold the access tag required by {metric_id!r}",
            )

    return None
