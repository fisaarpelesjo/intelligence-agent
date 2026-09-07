"""This feature's reason-code namespace — T002.

**Five disjoint namespaces already exist, and the count is measured rather than
remembered** — `001`'s ``ReasonCode``, `002`'s ``AnalyticsReasonCode``, `003`'s
``InterpretationReasonCode``, `004`'s ``ChannelReasonCode`` and `005`'s
``AnomalyReasonCode``. This adds a **sixth**, and adds no precedent: it follows the
one the four before it set.

**The ownership rule is the narrow one `004` wrote and `005` kept:** a code here may
only describe a condition none of the five upstream layers can observe. `001` cannot
know a component was unavailable; `005` cannot know two findings were compared with
each other, because a rule that fired knows its own threshold and nothing about any
other rule. **An upstream refusal is carried, never restated.**

**Five codes, and the list was closed at four until the REVIEWER's word opened it.**
The fifth arrived on 2026-08-27 carrying the owner's `D-C1`: confidence **is**
`completeness_ratio`, and `None` refuses instead of standing in as 1.0. That is the
`001` dead-vocabulary rule working as intended rather than an exception to it — the
code was minted **with its producer**, in the same commit, and each of the five below
is **used by a contract in this same package**:

============================================  ==========================================
code                                          the contract that uses it
============================================  ==========================================
``PRIORITY_COMPONENT_UNAVAILABLE``            ``ComponentAbsence`` in ``component.py``
``PRIORITY_DIRECTION_NOT_DECLARED``           ``ComponentAbsence`` in ``component.py``
``PRIORITY_CLASSES_NOT_COMPARABLE``           ``Ordering`` in ``ordering.py``
``PRIORITY_RUN_DID_NOT_COMPLETE``             ``PrioritisationRun`` in ``run.py``
``PRIORITY_CONFIDENCE_NOT_MEASURED``          ``ComponentAbsence`` in ``component.py``
============================================  ==========================================

**The ``PRIORITY_`` prefix was measured free** across every unique member name and
value of the five existing enums before it was chosen. But the disjointness
assertion in ``tests/`` is a **set intersection over the five enums**, not a prefix
check: a prefix convention that only checks itself passes while colliding.

``Outcome`` is imported rather than redeclared, as `004` and `005` do. Six enums
naming the same three outcome classes would eventually disagree.

**All five are ``DENY``.** There is no ``ALLOW_WITH_CAVEAT`` here yet, and the
absence is the honest state rather than an oversight: `005`'s single one exists
because *"nothing was declared to look at"* is a caveat and not a refusal. This
feature has not yet met a case of that shape, and inventing one to fill the column
would be the defect this docstring opens by naming.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from semantic_catalog.contracts.reason_codes import Outcome

__all__ = [
    "PRIORITY_REASON_CODE_OUTCOME",
    "Outcome",
    "PriorityReasonCode",
    "priority_outcome_for",
]


class PriorityReasonCode(StrEnum):
    """5 codes, all ``DENY``.

    Adding a code is a **new decision**, not a routine addition; changing a code's
    meaning is breaking. The fifth arrived with `D-C1` on 2026-08-27, and the owner's
    decision is what minted it: *confidence is `completeness_ratio`, and `None`
    **refuses** with a code of this namespace rather than assuming 1.0*.
    """

    #: A declared component could not be obtained for a finding. **Named, never
    #: substituted** — the whole point of `FR-004`. Zero is a measurement, not an
    #: absence, and treating an absence as zero would rank the finding last in
    #: silence: the exact shape of `Not renewed (qty)` missing and reading as
    #: minus 100 per cent instead of *incomplete day*.
    PRIORITY_COMPONENT_UNAVAILABLE = "priority_component_unavailable"

    #: The metric carries no declared direction, so *"is this movement good or
    #: bad"* has no answer this feature may supply. Distinct from the code above
    #: because the two are actionable differently: an unavailable component may
    #: arrive later, while an undeclared direction is a governance gap.
    PRIORITY_DIRECTION_NOT_DECLARED = "priority_direction_not_declared"

    #: Findings of different aggregation classes were offered for one ordering
    #: with no declared normalisation. `004` measured the three classes as not
    #: interchangeable; ranking a snapshot movement against a count movement
    #: without declaring how is inventing a common unit.
    PRIORITY_CLASSES_NOT_COMPARABLE = "priority_classes_not_comparable"

    #: The run did not finish. **Carried on the run and never inferred from an
    #: empty ordering**, because *"nothing deserved attention"* and *"the
    #: prioritiser broke"* must never look the same (`FR-009`).
    PRIORITY_RUN_DID_NOT_COMPLETE = "priority_run_did_not_complete"

    #: The confidence factor could not be measured for a finding, so no component
    #: may be weighted by it. `D-C1` decided that confidence **is**
    #: `FreshnessRecord.completeness_ratio`, which is declared ``float | None`` —
    #: and that ``None`` **refuses** rather than standing in as 1.0.
    #:
    #: **Assuming 1.0 would be the zero-substitution defect running the other way:**
    #: an unmeasured completeness would silently promote a finding to full
    #: confidence, and the output would look exactly like one where completeness
    #: was measured and found perfect.
    PRIORITY_CONFIDENCE_NOT_MEASURED = "priority_confidence_not_measured"


#: Frozen, and exhaustive by assertion rather than by intention: the test suite
#: compares this mapping's key set against the enum's members, so a code added
#: without an outcome fails rather than defaulting.
PRIORITY_REASON_CODE_OUTCOME: Mapping[PriorityReasonCode, Outcome] = MappingProxyType(
    {
        PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE: Outcome.DENY,
        PriorityReasonCode.PRIORITY_DIRECTION_NOT_DECLARED: Outcome.DENY,
        PriorityReasonCode.PRIORITY_CLASSES_NOT_COMPARABLE: Outcome.DENY,
        PriorityReasonCode.PRIORITY_RUN_DID_NOT_COMPLETE: Outcome.DENY,
        PriorityReasonCode.PRIORITY_CONFIDENCE_NOT_MEASURED: Outcome.DENY,
    }
)


def priority_outcome_for(code: PriorityReasonCode) -> Outcome:
    """The outcome of ``code``.

    Raises rather than defaulting on a code absent from the map. A default here
    would be a silent ``ALLOW`` for vocabulary nobody classified.
    """
    try:
        return PRIORITY_REASON_CODE_OUTCOME[code]
    except KeyError as exc:  # pragma: no cover - unreachable while the test above holds
        raise ValueError(f"{code!r} has no declared outcome") from exc
