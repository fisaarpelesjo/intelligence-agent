"""Governed reason codes (`FR-046`, `FR-047`, `FR-048`).

`FR-046` is the namespace decision: every refusal carries a code from this
stable enum, which **extends** `001`'s codes rather than redefining any of
them. The two sets are disjoint, asserted by contract test.
Execution-layer reason codes — T013 (FR-047, FR-048; SC-008).

`001`'s ``ReasonCode`` is a closed enum whose outcome mapping is frozen and whose
``outcome_for`` raises on an unknown member. Adding to it would mean editing a
merged, approved artifact — and editing the very contract whose stability lets
more than one consumer trust it. So this feature declares a **disjoint**
namespace instead (ADR 0004).

The ownership rule is narrow: a code here may only describe a condition `001`
cannot observe. Anything about metric existence, lifecycle, authorisation,
combination, grain, comparability, coverage, freshness, period, retention or
versioning stays upstream, and an upstream refusal is passed through **verbatim**
rather than restated in this vocabulary. That is what keeps a refusal's
non-disclosure properties intact: `002` cannot leak a metric's shape by
paraphrasing a refusal it did not originate.

``Outcome`` is imported rather than redeclared. Two enums naming the same three
outcome classes would eventually disagree.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from semantic_catalog.contracts.reason_codes import Outcome

__all__ = [
    "REASON_CODE_OUTCOME",
    "AnalyticsReasonCode",
    "Outcome",
    "codes_with_outcome",
    "outcome_for",
]


class AnalyticsReasonCode(StrEnum):
    """25 codes: 23 DENY, 1 ALLOW_WITH_CAVEAT, 1 ALLOW.

    Mirrors ``contracts/reason-codes.md`` §3 exactly. Adding a code is a minor
    change; changing a code's meaning is breaking, exactly as upstream.
    """

    # --- request malformation ------------------------------------------------
    REQUEST_MALFORMED = "REQUEST_MALFORMED"
    OPERATOR_NOT_GOVERNED = "OPERATOR_NOT_GOVERNED"
    FILTER_VALUE_SET_EMPTY = "FILTER_VALUE_SET_EMPTY"
    FILTER_VALUE_NOT_GOVERNED = "FILTER_VALUE_NOT_GOVERNED"
    FILTER_VALUE_NULL = "FILTER_VALUE_NULL"
    DATE_DIMENSION_NOT_FILTERABLE = "DATE_DIMENSION_NOT_FILTERABLE"
    FILTER_RANGE_INVALID = "FILTER_RANGE_INVALID"
    OPERATOR_NOT_APPLICABLE = "OPERATOR_NOT_APPLICABLE"
    DIMENSION_TYPE_UNDECLARED = "DIMENSION_TYPE_UNDECLARED"
    DATE_RANGE_INVALID = "DATE_RANGE_INVALID"
    DATE_RANGE_TOO_LONG = "DATE_RANGE_TOO_LONG"

    # --- policy --------------------------------------------------------------
    QUERY_POLICY_UNRESOLVABLE = "QUERY_POLICY_UNRESOLVABLE"

    # --- cost and bounds -----------------------------------------------------
    QUERY_COST_LIMIT_EXCEEDED = "QUERY_COST_LIMIT_EXCEEDED"
    QUERY_ROW_LIMIT_EXCEEDED = "QUERY_ROW_LIMIT_EXCEEDED"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"

    # --- execution integrity -------------------------------------------------
    DRY_RUN_FAILED = "DRY_RUN_FAILED"
    RESULT_SHAPE_MISMATCH = "RESULT_SHAPE_MISMATCH"
    CATALOG_CHANGED_DURING_EXECUTION = "CATALOG_CHANGED_DURING_EXECUTION"
    WAREHOUSE_UNAVAILABLE = "WAREHOUSE_UNAVAILABLE"
    LEDGER_UNAVAILABLE = "LEDGER_UNAVAILABLE"
    AUDIT_EMISSION_FAILED = "AUDIT_EMISSION_FAILED"

    # --- observations --------------------------------------------------------
    OBSERVATIONS_UNAVAILABLE = "OBSERVATIONS_UNAVAILABLE"

    # --- privacy -------------------------------------------------------------
    RESULT_CELL_SUPPRESSED = "RESULT_CELL_SUPPRESSED"
    RESULT_FULLY_SUPPRESSED = "RESULT_FULLY_SUPPRESSED"

    # --- permitted -----------------------------------------------------------
    QUERY_EXECUTED = "QUERY_EXECUTED"


#: Descriptive grouping, **not** a second classification axis. Every member is an
#: independent code whose outcome is DENY; none is an alias for another. The one
#: classification axis is outcome.
REQUEST_MALFORMATION_GROUP: frozenset[AnalyticsReasonCode] = frozenset(
    {
        AnalyticsReasonCode.REQUEST_MALFORMED,
        AnalyticsReasonCode.OPERATOR_NOT_GOVERNED,
        AnalyticsReasonCode.OPERATOR_NOT_APPLICABLE,
        AnalyticsReasonCode.FILTER_VALUE_SET_EMPTY,
        AnalyticsReasonCode.FILTER_VALUE_NOT_GOVERNED,
        AnalyticsReasonCode.FILTER_VALUE_NULL,
        AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE,
        AnalyticsReasonCode.FILTER_RANGE_INVALID,
        AnalyticsReasonCode.DATE_RANGE_INVALID,
        AnalyticsReasonCode.DATE_RANGE_TOO_LONG,
        AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED,
    }
)


_OUTCOMES: dict[AnalyticsReasonCode, Outcome] = {
    AnalyticsReasonCode.REQUEST_MALFORMED: Outcome.DENY,
    AnalyticsReasonCode.OPERATOR_NOT_GOVERNED: Outcome.DENY,
    AnalyticsReasonCode.FILTER_VALUE_SET_EMPTY: Outcome.DENY,
    AnalyticsReasonCode.FILTER_VALUE_NOT_GOVERNED: Outcome.DENY,
    AnalyticsReasonCode.FILTER_VALUE_NULL: Outcome.DENY,
    AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE: Outcome.DENY,
    AnalyticsReasonCode.FILTER_RANGE_INVALID: Outcome.DENY,
    AnalyticsReasonCode.OPERATOR_NOT_APPLICABLE: Outcome.DENY,
    AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED: Outcome.DENY,
    AnalyticsReasonCode.DATE_RANGE_INVALID: Outcome.DENY,
    AnalyticsReasonCode.DATE_RANGE_TOO_LONG: Outcome.DENY,
    AnalyticsReasonCode.QUERY_POLICY_UNRESOLVABLE: Outcome.DENY,
    AnalyticsReasonCode.QUERY_COST_LIMIT_EXCEEDED: Outcome.DENY,
    AnalyticsReasonCode.QUERY_ROW_LIMIT_EXCEEDED: Outcome.DENY,
    AnalyticsReasonCode.QUERY_TIMEOUT: Outcome.DENY,
    AnalyticsReasonCode.DRY_RUN_FAILED: Outcome.DENY,
    AnalyticsReasonCode.RESULT_SHAPE_MISMATCH: Outcome.DENY,
    AnalyticsReasonCode.CATALOG_CHANGED_DURING_EXECUTION: Outcome.DENY,
    AnalyticsReasonCode.WAREHOUSE_UNAVAILABLE: Outcome.DENY,
    AnalyticsReasonCode.LEDGER_UNAVAILABLE: Outcome.DENY,
    AnalyticsReasonCode.AUDIT_EMISSION_FAILED: Outcome.DENY,
    AnalyticsReasonCode.OBSERVATIONS_UNAVAILABLE: Outcome.DENY,
    AnalyticsReasonCode.RESULT_FULLY_SUPPRESSED: Outcome.DENY,
    AnalyticsReasonCode.RESULT_CELL_SUPPRESSED: Outcome.ALLOW_WITH_CAVEAT,
    AnalyticsReasonCode.QUERY_EXECUTED: Outcome.ALLOW,
}

#: Read-only code-to-outcome mapping. Every member appears exactly once, and
#: every outcome class is inhabited — a declared outcome no code can express is a
#: state nothing may emit or audit.
REASON_CODE_OUTCOME: Mapping[AnalyticsReasonCode, Outcome] = MappingProxyType(_OUTCOMES)


def outcome_for(code: AnalyticsReasonCode) -> Outcome:
    """Outcome class for ``code``.

    Raises rather than defaulting: an unmapped code means the enum and the table
    have drifted, and guessing an outcome would let a denial read as an allow.
    """
    try:
        return REASON_CODE_OUTCOME[code]
    except KeyError as exc:  # pragma: no cover - guarded by the contract test
        raise ValueError(f"reason code {code!r} has no declared outcome class") from exc


def codes_with_outcome(outcome: Outcome) -> tuple[AnalyticsReasonCode, ...]:
    """All codes classified as ``outcome``, in declaration order."""
    return tuple(code for code in AnalyticsReasonCode if REASON_CODE_OUTCOME[code] is outcome)
