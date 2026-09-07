"""Warehouse failure handling — T090 (FR-032; SC-020).

Unreachable, errored and credential-rejected are each reported as themselves.
None is ever a fabricated value, a stale value or an empty result.

The temptation this exists to remove is the plausible fallback: returning the
last known figure, or zero, or an empty table, when the warehouse cannot be
reached. Each of those looks like an answer and none of them is one — and the
caller has no way to tell the difference, which is exactly what makes it
dangerous.

Every class collapses to ``WAREHOUSE_UNAVAILABLE`` at the caller boundary. The
distinctions are for operators reading logs, not for callers: telling a caller
the failure was a credential rejection would disclose something about the
deployment they have no business knowing.
"""

from __future__ import annotations

from enum import StrEnum

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode

__all__ = ["FailureClass", "classify_failure", "refuse_for_failure"]

_CREDENTIAL_MARKERS = ("forbidden", "permission", "credential", "unauthorized", "denied")
_UNREACHABLE_MARKERS = ("connection", "unreachable", "dns", "network", "timeout", "refused")


class FailureClass(StrEnum):
    """Why the warehouse could not answer. Operator-facing, never caller-facing."""

    UNREACHABLE = "unreachable"
    ERRORED = "errored"
    CREDENTIAL_REJECTED = "credential_rejected"


def classify_failure(exc: BaseException) -> FailureClass:
    """Classify an adapter exception for the operator-facing record.

    Deliberately coarse. A finer taxonomy would invite branching on it, and the
    only branch that matters — did we get an answer — is already decided.
    Credential rejection is checked first: a permission failure often also
    mentions a connection, and misreading it as a network blip would send an
    operator chasing the wrong thing.
    """
    haystack = f"{type(exc).__name__} {exc}".lower()
    if any(marker in haystack for marker in _CREDENTIAL_MARKERS):
        return FailureClass.CREDENTIAL_REJECTED
    if any(marker in haystack for marker in _UNREACHABLE_MARKERS):
        return FailureClass.UNREACHABLE
    return FailureClass.ERRORED


def refuse_for_failure(failure: FailureClass) -> ContractViolation:
    """One governed refusal for every failure class.

    The wording names no host, project, credential or dataset. A caller learns
    that the warehouse could not answer, not how the deployment is assembled.
    """
    _ = failure
    return ContractViolation(
        AnalyticsReasonCode.WAREHOUSE_UNAVAILABLE,
        "the warehouse could not answer this request",
    )
