"""Freshness and completeness, decided **before** any rule can fire — T013.

`FR-004`, `SC-002`. **Phase 2 precedes Phase 3 on purpose**, and the reason is in
the plan: *a detector built first and guarded second is a detector that fired on
bad data at least once.* The case is not hypothetical — `004` measured two ratios
reading high because rows carry a numerator with no denominator, and a detector
without this module would have fired on both.

**Nothing here is invented that upstream already decided.** Measured before it was
written:

* `FreshnessRecord.status` is a **declared** enum with five values, and `UNKNOWN`
  is one of them — so *"freshness is unknown"* is an equality, not a `None` test;
* `completeness_ratio` is `float | None`, and `None` means **unmeasured**, which is
  neither zero nor complete;
* `FreshnessRecord.lag(now=)` derives the observed lag and returns `None` when it
  cannot be observed;
* `FreshnessRecord.within_tolerance(source, now=)` exists and returns **three**
  values — `True`, `False`, `None` — with a docstring saying callers must treat
  `None` as unknown and refuse, never as a pass;
* `FreshnessSnapshot.record_for(source_id)` returns `None` when *the snapshot says
  nothing*, which its own docstring calls an unknown state rather than a pass.

**`within_tolerance` is not called here, and that is a measured limit rather than a
shortcut.** It takes a `Source` from the catalog. So this module takes
`delay_tolerance` from its caller and uses `lag(now=)`, which needs no `Source`.

**An earlier version of this paragraph promised that the tolerance would come from
the catalog once the port landed, and nothing here would change shape. That promise
was wrong, and it is corrected here rather than left standing.** Measured in cycle
312, before the port was designed:

* `semantic/governance/freshness-approvals.yaml` carries `approvals: []`;
* its own header states that with no approvals **all six sources are
  unpublishable**, and that no candidate delay tolerance *"can reach a freshness,
  coverage, comparability or availability decision, or appear in a user-facing
  refusal"*;
* `FreshnessApprovalRegistry.evaluate` returns `NO_APPROVAL` for every source, and
  a `FreshnessApproval` **compares** the authored values rather than supplying
  them — *"it never supplies a value, never fills a gap"*;
* and the file says, in capitals, **DO NOT FABRICATE APPROVALS**, because an entry
  asserts that a named role signed off a business decision on a date.

**So the port cannot deliver a governed tolerance while `D-1` is open.** What it can
deliver is the refusal, carried verbatim. Until that is decided, a caller that omits
`delay_tolerance` is asking no question about lag — and this module answers no
question nobody asked, which is the same rule stated below for
`minimum_completeness`. **What is missing is named here rather than worked around,
and the sentence that used to promise otherwise is gone.**
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from pydantic import Field, model_validator
from semantic_catalog.freshness.external import (
    CompletenessStatus,
    FreshnessRecord,
    FreshnessSnapshot,
)

from ..contracts import AnomalyModel, AnomalyReasonCode, GovernedName

__all__ = [
    "CLASS_RANK",
    "EVIDENCE_CLASS",
    "WITHHOLDING_PRECEDENCE",
    "WITHIN_CLASS_ORDER",
    "EvidenceClass",
    "FreshnessVerdict",
    "assess_freshness",
    "evidence_class",
]


class EvidenceClass(StrEnum):
    """**What kind of thing the withholding is about.** Declared per member below.

    Three, not two. An earlier version split the ranking in half — *what the loader
    declared* and *what our instrument could not reach* — and put
    ``ANOMALY_SOURCE_NOT_OBSERVED`` in the first half. **Nobody declared it:** there
    is no row in the freshness table at all, which is the *strongest* form of our
    instrument not reaching, not an instance of the loader speaking. The module's
    own branch comment said so two screens below — *"the snapshot says nothing about
    this source"* — while the heading above claimed the opposite.

    The consequence was concrete rather than cosmetic. ``FIRST_INSTRUMENT_LIMIT``
    was exported, and a Phase 3 caller asking *"is this a limit of ours?"* would have
    been told **no** for a source that has no record — and would have sent an
    operator to ask whoever loads the data about a row that does not exist.
    """

    #: No ``FreshnessRecord`` exists. The table has no row; nothing was said at all.
    NO_RECORD = "no_record"
    #: A record exists and **states** the property we read. The criterion is
    #: *carries or does not carry*, not *asserted or computed*: a
    #: ``completeness_ratio`` of ``0.8`` compared against a rule's bar is
    #: ``DECLARED``, because the loader declared **how** complete the period is
    #: and we only compared a value it supplied. Comparing a declared value is
    #: not inventing one — and the proof the criterion is consistent is the
    #: sibling case, where ``completeness_ratio`` is ``None`` and the same
    #: property lands in ``NOT_REACHED``. **The line is what the record carries,
    #: and both sides of it are the same field.**
    DECLARED = "declared"
    #: A record exists and **does not carry** the property we need to read.
    NOT_REACHED = "not_reached"


#: Every withholding code, with the class it belongs to — **declared per member,
#: never derived from position.** A member in the wrong class is then a claim
#: somebody wrote, which a reader can dispute, rather than an accident of ordering
#: that no test can see.
EVIDENCE_CLASS: Mapping[AnomalyReasonCode, EvidenceClass] = MappingProxyType(
    {
        AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED: EvidenceClass.NO_RECORD,
        AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED: EvidenceClass.DECLARED,
        AnomalyReasonCode.ANOMALY_FRESHNESS_UNKNOWN: EvidenceClass.DECLARED,
        AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE: EvidenceClass.DECLARED,
        AnomalyReasonCode.ANOMALY_FRESHNESS_STALE: EvidenceClass.DECLARED,
        AnomalyReasonCode.ANOMALY_FRESHNESS_NOT_OBSERVABLE: EvidenceClass.NOT_REACHED,
        AnomalyReasonCode.ANOMALY_COMPLETENESS_UNMEASURED: EvidenceClass.NOT_REACHED,
    }
)

#: The classes in rank order, most decisive first.
#:
#: **`NO_RECORD` outranks everything**, and the reason is measured rather than
#: aesthetic: total absence is worse than a declared `PARTIAL`, because a partial
#: row still says how partial. **`DECLARED` outranks `NOT_REACHED`** because a
#: `PARTIAL` somebody asserted is a fact about the *data*, and an unobservable lag
#: is a fact about *us* — reporting the second while the first is true tells an
#: operator to go look at our freshness table when the data itself is incomplete.
CLASS_RANK: tuple[EvidenceClass, ...] = (
    EvidenceClass.NO_RECORD,
    EvidenceClass.DECLARED,
    EvidenceClass.NOT_REACHED,
)

#: Within one class, the order below decides. **A failed load is also late**, and
#: reporting *stale* when the truth is *the load failed* sends an operator to look
#: at the clock instead of at the error — so the more actionable reason wins.
WITHIN_CLASS_ORDER: tuple[AnomalyReasonCode, ...] = (
    AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED,
    AnomalyReasonCode.ANOMALY_FRESHNESS_UNKNOWN,
    AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE,
    AnomalyReasonCode.ANOMALY_FRESHNESS_STALE,
    AnomalyReasonCode.ANOMALY_FRESHNESS_NOT_OBSERVABLE,
    AnomalyReasonCode.ANOMALY_COMPLETENESS_UNMEASURED,
    AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED,
)


def _precedence() -> tuple[AnomalyReasonCode, ...]:
    """The ranking, **derived from the declared classes** rather than hand-ordered.

    This is the direction that matters. When the tuple came first and the classes
    were read back out of it by slicing, a member sitting in the wrong half was
    invisible — the test sliced by index and then checked the index, which no
    permutation could fail. Deriving the order from the classification makes the
    classification the thing under review.
    """
    return tuple(
        code for rank in CLASS_RANK for code in WITHIN_CLASS_ORDER if EVIDENCE_CLASS[code] is rank
    )


#: The order in which reasons are checked. **Derived**, never written by hand.
WITHHOLDING_PRECEDENCE: tuple[AnomalyReasonCode, ...] = _precedence()


def evidence_class(code: AnomalyReasonCode) -> EvidenceClass:
    """Which kind of evidence a withholding rests on. Raises rather than defaulting.

    A default would make a code missing from the map indistinguishable from one
    deliberately classified, and the classification is the governed fact.
    """
    return EVIDENCE_CLASS[code]


class FreshnessVerdict(AnomalyModel):
    """Whether a rule may fire, and — when it may not — which reason says so.

    **The verdict is an object rather than a boolean** for the same reason
    `within_tolerance` returns three values: *may fire*, *may not fire because X*
    and *may not fire because Y* collapse into one `False` that no run could
    report, and `SC-002` is precisely the claim that they must not collapse.
    """

    permits_firing: bool
    reason_code: AnomalyReasonCode | None = Field(
        default=None, description="Present exactly when permits_firing is False."
    )
    record: FreshnessRecord | None = Field(
        default=None, description="The record that decided it, when one exists."
    )
    sources_examined: tuple[GovernedName, ...] = Field(
        default=(),
        description=(
            "Which sources were actually looked at. A verdict that examined nothing "
            "is refused below rather than permitted by vacuity."
        ),
    )
    observed_from_fixture: bool = Field(
        default=False,
        description=(
            "The snapshot declares itself a fixture. This does NOT withhold — a "
            "fixture is a legitimate way to run a unit test. It travels so that a "
            "claim about the real warehouse cannot be built on one (SC-001)."
        ),
    )

    @model_validator(mode="after")
    def _the_verdict_defends_itself(self) -> FreshnessVerdict:
        """Three impossible states, refused by the type rather than by prose.

        The field descriptions said *"present exactly when permits_firing is
        False"* and **nothing enforced it**. All three of these were constructible:

        **A withholding with no reason** is a refusal nobody can act on — the same
        class `001` enforces by refusing a ``FAILED`` record with no ``last_error``
        (*"a failure nobody can act on is not a report"*). That lesson arrived in
        this feature as a corrected test; here it is applied to the contract.

        **A permission carrying a reason** is a contradiction that a caller could
        read either way, and the two readings are *fire* and *do not fire*.

        **A permission that examined nothing** is the vacuous pass
        :func:`assess_freshness` already refuses at its door — but the function
        guarding while the type does not means anyone assembling a verdict by hand
        gets no guard at all. Every other contract in this package couples its
        fields this way; this one was the exception.
        """
        if self.permits_firing and self.reason_code is not None:
            raise ValueError("a verdict that permits firing carries no reason code")
        if not self.permits_firing and self.reason_code is None:
            raise ValueError("a withholding must name its reason")
        if self.permits_firing and not self.sources_examined:
            raise ValueError("a verdict that examined no source may not permit firing")
        return self


def _reason_for(
    record: FreshnessRecord,
    *,
    now: datetime,
    delay_tolerance: timedelta | None,
    minimum_completeness: Decimal | None,
) -> AnomalyReasonCode | None:
    """Every reason this record gives, resolved by declared precedence."""
    reasons: set[AnomalyReasonCode] = set()

    if record.status is CompletenessStatus.FAILED:
        reasons.add(AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED)
    if record.status is CompletenessStatus.UNKNOWN:
        reasons.add(AnomalyReasonCode.ANOMALY_FRESHNESS_UNKNOWN)
    if record.status is CompletenessStatus.PARTIAL:
        reasons.add(AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE)
    if record.status is CompletenessStatus.DELAYED:
        reasons.add(AnomalyReasonCode.ANOMALY_FRESHNESS_STALE)

    # Lag is consulted even when the status looks healthy: a status is what the
    # loader believed, and the clock is what happened.
    if delay_tolerance is not None:
        observed = record.lag(now=now)
        if observed is None:
            # Unobservable lag withholds, and the three-valued rule
            # `within_tolerance` documents is why. But the code is **not**
            # ``ANOMALY_FRESHNESS_UNKNOWN``: that one means the loader *declared*
            # the status unknown, and here the record exists and may say COMPLETE.
            # The distinction is the operator's — one is a question for whoever
            # loads the data, the other is a question about what the freshness
            # table records.
            reasons.add(AnomalyReasonCode.ANOMALY_FRESHNESS_NOT_OBSERVABLE)
        elif observed > delay_tolerance:
            reasons.add(AnomalyReasonCode.ANOMALY_FRESHNESS_STALE)

    if minimum_completeness is not None:
        if record.completeness_ratio is None:
            reasons.add(AnomalyReasonCode.ANOMALY_COMPLETENESS_UNMEASURED)
        elif Decimal(str(record.completeness_ratio)) < minimum_completeness:
            reasons.add(AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE)

    for candidate in WITHHOLDING_PRECEDENCE:
        if candidate in reasons:
            return candidate
    return None


def assess_freshness(
    snapshot: FreshnessSnapshot,
    *,
    sources: tuple[str, ...],
    now: datetime,
    delay_tolerance: timedelta | None = None,
    minimum_completeness: Decimal | None = None,
) -> FreshnessVerdict:
    """Decide whether any rule over these sources may fire.

    **Called before detection exists, and its answer is the precondition for it.**

    ``minimum_completeness`` and ``delay_tolerance`` are the caller's, never this
    module's. Choosing a bar here would be inventing a governed threshold — which
    ratio is too low is a rule's declaration, and how late is too late is the
    catalog's. Passing ``None`` means *that question was not asked*, and this
    module does not answer questions nobody asked.

    The baseline's ``block_incomplete_comparisons`` is **honoured, not restated**:
    a `PARTIAL` status withholds because the baseline already decided that an
    incomplete period may not be compared.
    """
    if not sources:
        # A verdict over no source examined nothing. Permitting a rule to fire on
        # that would be the vacuous pass this repository has now measured four
        # times: a check that reaches nothing reports success by doing nothing.
        return FreshnessVerdict(
            permits_firing=False,
            reason_code=AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED,
            sources_examined=(),
            observed_from_fixture=snapshot.is_fixture,
        )

    worst: tuple[int, AnomalyReasonCode, FreshnessRecord | None] | None = None

    for source in sources:
        record = snapshot.record_for(source)
        if record is None:
            # The snapshot says nothing about this source. Its own docstring calls
            # that an unknown state rather than a pass, and this honours that.
            reason = AnomalyReasonCode.ANOMALY_SOURCE_NOT_OBSERVED
            rank = WITHHOLDING_PRECEDENCE.index(reason)
            if worst is None or rank < worst[0]:
                worst = (rank, reason, None)
            continue

        reason = _reason_for(
            record,
            now=now,
            delay_tolerance=delay_tolerance,
            minimum_completeness=minimum_completeness,
        )
        if reason is None:
            continue
        rank = WITHHOLDING_PRECEDENCE.index(reason)
        if worst is None or rank < worst[0]:
            worst = (rank, reason, record)

    examined = tuple(sources)

    if worst is None:
        return FreshnessVerdict(
            permits_firing=True,
            sources_examined=examined,
            observed_from_fixture=snapshot.is_fixture,
        )

    _rank, reason, record = worst
    return FreshnessVerdict(
        permits_firing=False,
        reason_code=reason,
        record=record,
        sources_examined=examined,
        observed_from_fixture=snapshot.is_fixture,
    )
