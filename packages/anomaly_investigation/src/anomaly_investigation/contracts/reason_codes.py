"""This feature's reason-code namespace — T011.

**Four disjoint namespaces already exist, and the count was measured rather than
remembered** (`research.md` § 6): `001`'s ``ReasonCode`` has 41 codes, `002`'s
``AnalyticsReasonCode`` 25, `003`'s ``InterpretationReasonCode`` 32, and `004`'s
``ChannelReasonCode`` 31 — **129 codes**. An earlier draft of the task list said
*"disjoint from the two that exist"*, which would have checked half the universe
and let a collision with `003` or `004` pass.

This adds a **fifth disjoint namespace of 19 codes**. It adds no precedent; it
follows the one `002`, `003` and `004` already set.

**The ownership rule is narrow, and it is the one `004` wrote:** a code here may
only describe a condition none of the four upstream layers can observe. `001`
cannot know a detection rule exists; `002` cannot know a threshold was crossed;
`003` cannot know nobody asked. **An upstream refusal is carried, never restated**
— ``ANOMALY_RULE_METRIC_NOT_BOUND`` and ``ANOMALY_FIGURE_UNAVAILABLE`` both travel
with the upstream code that produced them, because re-classifying an upstream
refusal into a local vocabulary is how the original reason stops being readable.

**The ``ANOMALY_`` prefix was measured free** across all unique member names and
values of the four enums before it was chosen. But the disjointness assertion in
``tests/`` is a **set intersection over the four enums**, not a prefix check: a
prefix convention that only checks itself passes while colliding.

**Two of the nineteen have no ``FR`` and no ``SC``, and both are declared rather
than given an invented one** — see ``contracts/reason-codes.md`` § 3 and the
owner's ledger at ``docs/roadmap-capacidade-de-negocio.md`` § 4.3.
``ANOMALY_RULE_THRESHOLD_UNCROSSABLE`` is anchored in the spec's Edge Cases, a
weaker anchor than a requirement. ``ANOMALY_SEGMENT_VALUE_SUPPRESSED`` is anchored
in measurement: `002`'s ``ResultCell`` carries ``suppressed``, so the case exists
in the data whether or not a requirement names it. **Code anchored in measured data
is not orphaned; it is code whose requirement has not been written yet.** Stretching
`FR-011` over one and `FR-001` over the other is exactly how a code ends up used
for something that was never its job.

``Outcome`` is imported rather than redeclared, as `004` does. Five enums naming
the same three outcome classes would eventually disagree.

Mirrors ``specs/005-anomaly-investigation/contracts/reason-codes.md`` § 3, whose
tables are authoritative.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from semantic_catalog.contracts.reason_codes import Outcome

__all__ = [
    "ANOMALY_REASON_CODE_OUTCOME",
    "AnomalyReasonCode",
    "Outcome",
    "anomaly_codes_with_outcome",
    "anomaly_outcome_for",
]


class AnomalyReasonCode(StrEnum):
    """19 codes: 18 DENY, 1 ALLOW_WITH_CAVEAT.

    Adding a code is a **new decision**, not a routine addition, exactly as
    upstream; changing a code's meaning is breaking.
    """

    # --- withholding, before any rule fires (7) -- FR-004 ---------------------
    #: ``FreshnessRecord.status`` is ``UNKNOWN``. **A declared status, not a
    #: missing record** — the enum carries it, so this is an equality and not a
    #: ``None`` test.
    ANOMALY_FRESHNESS_UNKNOWN = "ANOMALY_FRESHNESS_UNKNOWN"
    #: Status is ``DELAYED``, or the observation is older than the rule allows.
    ANOMALY_FRESHNESS_STALE = "ANOMALY_FRESHNESS_STALE"
    #: Status is ``FAILED``. ``last_error`` travels with it as evidence.
    ANOMALY_SOURCE_INGESTION_FAILED = "ANOMALY_SOURCE_INGESTION_FAILED"
    #: Status is ``PARTIAL``, or ``completeness_ratio`` is below the rule's bar.
    #: Honours the baseline's ``block_incomplete_comparisons`` rather than
    #: restating it. **This is the case `004` measured**: rows with a numerator
    #: and no denominator read high, and a detector without it would have fired.
    ANOMALY_PERIOD_INCOMPLETE = "ANOMALY_PERIOD_INCOMPLETE"
    #: ``completeness_ratio`` is ``None``. **Unknown is not zero and not
    #: complete**, and collapsing the three is how a hole becomes a movement.
    ANOMALY_COMPLETENESS_UNMEASURED = "ANOMALY_COMPLETENESS_UNMEASURED"
    #: No ``FreshnessRecord`` for a contributing source, so freshness cannot be
    #: validated at all and nothing may fire.
    ANOMALY_SOURCE_NOT_OBSERVED = "ANOMALY_SOURCE_NOT_OBSERVED"
    #: The record exists and may even say ``COMPLETE``, but its **lag cannot be
    #: observed** — neither a last successful update nor a source event time.
    #:
    #: **Deliberately not ``ANOMALY_FRESHNESS_UNKNOWN``.** That code means *the
    #: loader declared the status unknown*; this one means *our instrument does not
    #: reach the property*. The two look alike and an operator acts differently on
    #: each: the first is a question for whoever loads the data, the second is a
    #: question about what the freshness table records. Collapsing them would be
    #: this feature's own rule broken — a code used for something that was never
    #: its job.
    ANOMALY_FRESHNESS_NOT_OBSERVABLE = "ANOMALY_FRESHNESS_NOT_OBSERVABLE"

    # --- rule validity (5) ---------------------------------------------------
    #: The metric does not resolve through `001`. **The upstream refusal is
    #: carried, not replaced** (`FR-001`).
    ANOMALY_RULE_METRIC_NOT_BOUND = "ANOMALY_RULE_METRIC_NOT_BOUND"
    #: A rule written for one aggregation class applied to another. The refusal
    #: **names the class it was written for** (`FR-010`, `SC-006`).
    ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH = "ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH"
    #: A method outside the baseline's closed eight (`FR-002`).
    ANOMALY_RULE_METHOD_NOT_GOVERNED = "ANOMALY_RULE_METHOD_NOT_GOVERNED"
    #: The threshold cannot be crossed. **Reported, never silently normal** — a
    #: configuration defect that a quiet KPI would hide.
    #: **No ``FR``, no ``SC``**: anchored in the spec's Edge Cases.
    ANOMALY_RULE_THRESHOLD_UNCROSSABLE = "ANOMALY_RULE_THRESHOLD_UNCROSSABLE"
    #: The period name does not resolve in the catalog (`FR-012`).
    ANOMALY_RULE_PERIOD_NOT_GOVERNED = "ANOMALY_RULE_PERIOD_NOT_GOVERNED"

    # --- figure acquisition (4) -- FR-003 ------------------------------------
    #: `002`/`003` refused. The upstream reason code travels with it.
    ANOMALY_FIGURE_UNAVAILABLE = "ANOMALY_FIGURE_UNAVAILABLE"
    #: ``assert_baseline_is_usable`` raised — the governed zero-baseline
    #: decision, carried rather than re-decided.
    ANOMALY_BASELINE_NOT_USABLE = "ANOMALY_BASELINE_NOT_USABLE"
    #: ``assert_units_agree`` refused the two sides.
    ANOMALY_UNITS_DISAGREE = "ANOMALY_UNITS_DISAGREE"
    #: Disposition is ``PARTIALLY_WITHHELD`` or ``FULLY_WITHHELD``, so the
    #: evidence a candidate requires does not exist. **Withheld is not zero.**
    ANOMALY_RESULT_WITHHELD = "ANOMALY_RESULT_WITHHELD"

    # --- investigation (3) -- FR-011 -----------------------------------------
    #: Zero declared dimensions. **A reported fact, not an error** — the
    #: investigation still emits, which is why it is an entity and not a set.
    #: The one ``ALLOW_WITH_CAVEAT`` of this namespace.
    ANOMALY_NO_DIMENSION_DECLARED = "ANOMALY_NO_DIMENSION_DECLARED"
    #: Segment contributions do not reconcile against the total (`SC-005`).
    ANOMALY_CONTRIBUTIONS_DID_NOT_RECONCILE = "ANOMALY_CONTRIBUTIONS_DID_NOT_RECONCILE"
    #: A cell came back suppressed. Reported per segment, **never coerced to
    #: zero**. **No ``FR``, no ``SC``**: anchored in measurement of `002`.
    ANOMALY_SEGMENT_VALUE_SUPPRESSED = "ANOMALY_SEGMENT_VALUE_SUPPRESSED"


#: Every code's outcome class, frozen. A code with no entry is a defect the
#: contract test catches, not a silent ``DENY``.
ANOMALY_REASON_CODE_OUTCOME: Mapping[AnomalyReasonCode, Outcome] = MappingProxyType(
    {
        AnomalyReasonCode.ANOMALY_FRESHNESS_UNKNOWN: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_FRESHNESS_STALE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_COMPLETENESS_UNMEASURED: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_FRESHNESS_NOT_OBSERVABLE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_RULE_METRIC_NOT_BOUND: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_RULE_METHOD_NOT_GOVERNED: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_RULE_THRESHOLD_UNCROSSABLE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_RULE_PERIOD_NOT_GOVERNED: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_BASELINE_NOT_USABLE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_UNITS_DISAGREE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_RESULT_WITHHELD: Outcome.DENY,
        # The investigation still emits; the absence is reported, not refused.
        AnomalyReasonCode.ANOMALY_NO_DIMENSION_DECLARED: Outcome.ALLOW_WITH_CAVEAT,
        AnomalyReasonCode.ANOMALY_CONTRIBUTIONS_DID_NOT_RECONCILE: Outcome.DENY,
        AnomalyReasonCode.ANOMALY_SEGMENT_VALUE_SUPPRESSED: Outcome.DENY,
    }
)


def anomaly_outcome_for(code: AnomalyReasonCode) -> Outcome:
    """The outcome class of one code. Raises rather than defaulting.

    A default would make a code missing from the map indistinguishable from one
    deliberately classified ``DENY``, and the map is the governed fact.
    """
    return ANOMALY_REASON_CODE_OUTCOME[code]


def anomaly_codes_with_outcome(outcome: Outcome) -> tuple[AnomalyReasonCode, ...]:
    """Every code of one outcome class, in declaration order."""
    return tuple(code for code, value in ANOMALY_REASON_CODE_OUTCOME.items() if value is outcome)
