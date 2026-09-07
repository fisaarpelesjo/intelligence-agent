"""Stable reason codes — T015 (FR-012, decision-contract §3).

Forty-one codes, each mapped to **exactly one** outcome class. The mapping is the
contract: a code whose outcome is undetermined would let two call sites disagree
about whether the same refusal is a refusal.

**Every outcome class is inhabited.** ``ALLOW`` was declared in the decision
contract and named by no code, which made a clean allow unrepresentable: the
decision had nothing to carry, and ``CatalogDecisionAuditEvent`` — which requires
a code and matches it against the outcome — could not record one at all. So
allowing something was, literally, unauditable. ``REQUEST_ALLOWED`` closes that.

Codes are English identifiers; the wording a user sees is pt-BR and comes from
the governed message registry (T018). Adding a code is a minor change; changing
what a code *means* is breaking.

Two distinctions this table encodes deliberately:

* ``METRIC_NOT_GOVERNED`` vs ``METRIC_PENDING`` — the first sends a user away to
  build their own number, the second sends them to the owner;
* ``SOURCE_STATE_PARTIAL`` **denies** while ``SOURCE_LAGGING_WITHIN_TOLERANCE``
  allows with a caveat — lag and completeness measure different things, and a
  punctual but incomplete load is the shortest route to a confidently wrong
  number (FR-070).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

__all__ = ["REASON_CODE_OUTCOME", "Outcome", "ReasonCode", "codes_with_outcome", "outcome_for"]


class Outcome(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_CAVEAT = "ALLOW_WITH_CAVEAT"


class ReasonCode(StrEnum):
    """Stable enum. Renaming or repurposing a member is a breaking change."""

    # Permitted
    REQUEST_ALLOWED = "REQUEST_ALLOWED"

    # Existence and lifecycle
    METRIC_NOT_GOVERNED = "METRIC_NOT_GOVERNED"
    DIMENSION_NOT_GOVERNED = "DIMENSION_NOT_GOVERNED"
    SOURCE_NOT_GOVERNED = "SOURCE_NOT_GOVERNED"
    METRIC_PENDING = "METRIC_PENDING"
    METRIC_AMBIGUOUS = "METRIC_AMBIGUOUS"

    # Authorisation
    ACCESS_DENIED = "ACCESS_DENIED"

    # Combination and grain
    METRIC_NOT_AVAILABLE_FOR_SOURCE = "METRIC_NOT_AVAILABLE_FOR_SOURCE"
    DIMENSION_NOT_APPLICABLE_TO_SOURCE = "DIMENSION_NOT_APPLICABLE_TO_SOURCE"
    DIMENSION_NOT_ALLOWED_FOR_METRIC = "DIMENSION_NOT_ALLOWED_FOR_METRIC"
    GRAIN_FAMILY_MISMATCH = "GRAIN_FAMILY_MISMATCH"
    AGGREGATION_INVALID_FOR_ADDITIVITY = "AGGREGATION_INVALID_FOR_ADDITIVITY"

    # Comparability
    METRICS_NOT_COMPARABLE = "METRICS_NOT_COMPARABLE"
    COMPARABILITY_RULE_MISSING = "COMPARABILITY_RULE_MISSING"
    COMPARABLE_WITH_CAVEAT = "COMPARABLE_WITH_CAVEAT"

    # Coverage and freshness
    RANGE_OUTSIDE_COVERAGE = "RANGE_OUTSIDE_COVERAGE"
    SOURCE_BEYOND_TOLERANCE = "SOURCE_BEYOND_TOLERANCE"
    SOURCE_STATE_FAILED = "SOURCE_STATE_FAILED"
    SOURCE_STATE_UNKNOWN = "SOURCE_STATE_UNKNOWN"
    SOURCE_STATE_PARTIAL = "SOURCE_STATE_PARTIAL"
    SOURCE_LAGGING_WITHIN_TOLERANCE = "SOURCE_LAGGING_WITHIN_TOLERANCE"
    COVERAGE_ENDS_BEFORE_PERIOD = "COVERAGE_ENDS_BEFORE_PERIOD"

    # Period semantics
    PARTIAL_VS_COMPLETE_COMPARISON = "PARTIAL_VS_COMPLETE_COMPARISON"
    EQUIVALENT_PARTIAL_COMPARISON = "EQUIVALENT_PARTIAL_COMPARISON"
    PERIOD_INCOMPLETE = "PERIOD_INCOMPLETE"
    TIMEZONE_OFFSET_MATERIAL = "TIMEZONE_OFFSET_MATERIAL"

    # Retention
    COHORT_NOT_MATURED = "COHORT_NOT_MATURED"
    RETENTION_SOURCE_UNAVAILABLE = "RETENTION_SOURCE_UNAVAILABLE"
    RETENTION_NOT_SUMMABLE = "RETENTION_NOT_SUMMABLE"

    # Versioning and deprecation
    SPANS_DEFINITION_CHANGE = "SPANS_DEFINITION_CHANGE"
    DEPRECATED_METRIC = "DEPRECATED_METRIC"
    METRIC_DEPRECATED_FOR_PERIOD = "METRIC_DEPRECATED_FOR_PERIOD"
    SPANS_DEPRECATION_BOUNDARY = "SPANS_DEPRECATION_BOUNDARY"
    COMPARISON_REQUIRES_DEPRECATED_PERIOD = "COMPARISON_REQUIRES_DEPRECATED_PERIOD"
    PERIOD_RESTATED = "PERIOD_RESTATED"
    REPRODUCIBILITY_LIMITED = "REPRODUCIBILITY_LIMITED"

    # Governance and release
    POLICY_UNRESOLVABLE = "POLICY_UNRESOLVABLE"
    ACCESS_TAG_UNKNOWN = "ACCESS_TAG_UNKNOWN"
    ACCESS_TAG_DEPRECATED = "ACCESS_TAG_DEPRECATED"
    ACCESS_TAG_SCOPE_MISMATCH = "ACCESS_TAG_SCOPE_MISMATCH"
    RELEASE_WITHDRAWN = "RELEASE_WITHDRAWN"


_OUTCOMES: dict[ReasonCode, Outcome] = {
    ReasonCode.REQUEST_ALLOWED: Outcome.ALLOW,
    ReasonCode.METRIC_NOT_GOVERNED: Outcome.DENY,
    ReasonCode.DIMENSION_NOT_GOVERNED: Outcome.DENY,
    ReasonCode.SOURCE_NOT_GOVERNED: Outcome.DENY,
    ReasonCode.METRIC_PENDING: Outcome.DENY,
    ReasonCode.METRIC_AMBIGUOUS: Outcome.DENY,
    ReasonCode.ACCESS_DENIED: Outcome.DENY,
    ReasonCode.METRIC_NOT_AVAILABLE_FOR_SOURCE: Outcome.DENY,
    ReasonCode.DIMENSION_NOT_APPLICABLE_TO_SOURCE: Outcome.DENY,
    ReasonCode.DIMENSION_NOT_ALLOWED_FOR_METRIC: Outcome.DENY,
    ReasonCode.GRAIN_FAMILY_MISMATCH: Outcome.DENY,
    ReasonCode.AGGREGATION_INVALID_FOR_ADDITIVITY: Outcome.DENY,
    ReasonCode.METRICS_NOT_COMPARABLE: Outcome.DENY,
    ReasonCode.COMPARABILITY_RULE_MISSING: Outcome.DENY,
    ReasonCode.COMPARABLE_WITH_CAVEAT: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.RANGE_OUTSIDE_COVERAGE: Outcome.DENY,
    ReasonCode.SOURCE_BEYOND_TOLERANCE: Outcome.DENY,
    ReasonCode.SOURCE_STATE_FAILED: Outcome.DENY,
    ReasonCode.SOURCE_STATE_UNKNOWN: Outcome.DENY,
    ReasonCode.SOURCE_STATE_PARTIAL: Outcome.DENY,
    ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD: Outcome.DENY,
    ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON: Outcome.DENY,
    ReasonCode.EQUIVALENT_PARTIAL_COMPARISON: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.PERIOD_INCOMPLETE: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.TIMEZONE_OFFSET_MATERIAL: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.COHORT_NOT_MATURED: Outcome.DENY,
    ReasonCode.RETENTION_SOURCE_UNAVAILABLE: Outcome.DENY,
    ReasonCode.RETENTION_NOT_SUMMABLE: Outcome.DENY,
    ReasonCode.SPANS_DEFINITION_CHANGE: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.DEPRECATED_METRIC: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.METRIC_DEPRECATED_FOR_PERIOD: Outcome.DENY,
    ReasonCode.SPANS_DEPRECATION_BOUNDARY: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.COMPARISON_REQUIRES_DEPRECATED_PERIOD: Outcome.DENY,
    ReasonCode.PERIOD_RESTATED: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.REPRODUCIBILITY_LIMITED: Outcome.ALLOW_WITH_CAVEAT,
    ReasonCode.POLICY_UNRESOLVABLE: Outcome.DENY,
    ReasonCode.ACCESS_TAG_UNKNOWN: Outcome.DENY,
    ReasonCode.ACCESS_TAG_DEPRECATED: Outcome.DENY,
    ReasonCode.ACCESS_TAG_SCOPE_MISMATCH: Outcome.DENY,
    ReasonCode.RELEASE_WITHDRAWN: Outcome.DENY,
}

#: Read-only code to outcome mapping. Every member of :class:`ReasonCode` appears,
#: and every member of :class:`Outcome` is inhabited by at least one code.
REASON_CODE_OUTCOME: Mapping[ReasonCode, Outcome] = MappingProxyType(_OUTCOMES)


def outcome_for(code: ReasonCode) -> Outcome:
    """Outcome class for ``code``.

    Raises rather than defaulting: an unmapped code means the enum and the table
    have drifted, and guessing an outcome would let a denial read as an allow.
    """
    try:
        return REASON_CODE_OUTCOME[code]
    except KeyError as exc:  # pragma: no cover - guarded by test_every_code_has_one_outcome
        raise ValueError(f"reason code {code!r} has no declared outcome class") from exc


def codes_with_outcome(outcome: Outcome) -> tuple[ReasonCode, ...]:
    """All codes classified as ``outcome``, in declaration order."""
    return tuple(code for code in ReasonCode if REASON_CODE_OUTCOME[code] is outcome)
