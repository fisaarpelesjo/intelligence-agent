"""Decision contract — T050 (FR-039; decision-contract §1, §2).

Every catalog answer to "may this be asked?" is a :class:`CatalogDecision`. It is
this feature's primary output and the unit downstream features cite as evidence.

Two invariants, enforced by construction rather than by convention:

**Deny-by-default.** An input the catalog does not recognise is denied, never
passed through.

**No generic refusals.** ``outcome``, ``reason_code``, ``subject`` and at least
one ``evidence_refs`` entry are required with no defaults, so a decision that
does not say *what* it is about and *what it stood on* cannot be constructed at
all (FR-012, SC-004). A refusal that names nothing sends the reader to build
their own number.

``message_pt_br`` is **looked up, never generated**. FR-055 and FR-074 forbid
producing provenance wording by translation at answer time, so the string comes
from the governed registry and this model only carries it.

**Every outcome carries a code.** A clean allow emits ``REQUEST_ALLOWED``
(Outcome.ALLOW), so ``reason_code`` and ``message_pt_br`` are unconditionally
required. That matters beyond tidiness: ``CatalogDecisionAuditEvent`` requires a
code and validates it against the outcome, so an allow carrying none could not be
audited at all.

**Finality is explicit, and it fails closed.** ``finality`` separates a
``PRE_EVIDENCE`` result — the output of the gate pipeline, before any data
revision or freshness evidence exists — from a ``FINAL`` consumer-ready decision.
The model enforces the rule so no caller can assert otherwise:

* a permissive outcome (ALLOW or ALLOW_WITH_CAVEAT) with **no** ``data_revisions``
  is ``PRE_EVIDENCE`` and ``reproducibility: limited``;
* ``FULL`` reproducibility requires at least one data revision, always;
* a **DENY may be FINAL with no revisions** — nothing was read, so no revision
  contributed to the refusal, and requiring one would leave every refusal
  permanently provisional.

Without this, a Phase 6 allow would claim ``reproducibility: full`` while
standing on nothing, and a consumer could cite it as settled (FR-068).

**Provenance travels with the decision** (Constitution Principle III, FR-039).
``freshness`` names every contributing source with its status, its required flag
and its last successful update; ``evidence_refs`` carries the data-as-of instant
inside each ``freshness_snapshot`` id and the observed window inside each
``coverage_window`` id; ``limitations`` carries the rest. A decision that cannot
state those is one nobody can check.

``segments`` and ``comparable_window`` remain declared-and-empty: they belong to
as-of resolution and comparability, which are later phases. Declaring the shape
is not implementing the gate. **T073** establishes final decision identity once
required revisions exist.

``comparable_window`` carries the **complete** window gate 7 computes — range,
sources and the governed reason — rather than the bare range an earlier form
transported. ADR 0016 records why: the two discarded fields were computed,
required downstream and unrecoverable anywhere else, so the loss made the
approved two-execution comparison route impossible to complete.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import Field, StrictBool, model_validator

from ..contracts._base import CatalogModel, Identifier, PtBrText
from ..contracts.audit_event import EvidenceKind, EvidenceRef
from ..contracts.reason_codes import Outcome, ReasonCode, outcome_for

__all__ = [
    "CatalogDecision",
    "CatalogValidationRequest",
    "ComparableWindow",
    "Comparison",
    "DateRange",
    "Finality",
    "FreshnessVerdict",
    "Limitation",
    "Reproducibility",
    "Segment",
    "Subject",
    "SubjectKind",
    "derive_decision_id",
    "metric_version_evidence",
    "subject_for",
]


class SubjectKind(StrEnum):
    """What a reason is about. A refusal always names one."""

    METRIC = "metric"
    DIMENSION = "dimension"
    SOURCE = "source"
    PERIOD = "period"
    POLICY = "policy"
    ACCESS_TAG = "access_tag"
    REQUEST = "request"


class Reproducibility(StrEnum):
    FULL = "full"
    LIMITED = "limited"


class Finality(StrEnum):
    """Whether a decision is consumer-ready.

    ``PRE_EVIDENCE`` is the honest description of a gate result produced before
    any data revision exists: the governance question is answered, the data
    question has not been asked. ``FINAL`` is what T073 produces once required
    revisions and freshness evidence are present.

    Two named states rather than a boolean, because the names are the
    documentation — ``is_provisional=False`` reads as an absence, ``FINAL`` reads
    as a claim somebody has to justify.
    """

    PRE_EVIDENCE = "pre_evidence"
    FINAL = "final"


class DateRange(CatalogModel):
    """Canonical-zone dates, always. Never a source's native day (R-10, FR-027)."""

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.end < self.start:
            raise ValueError(f"date range ends {self.end} before it starts {self.start}")
        return self


class Comparison(CatalogModel):
    kind: Identifier
    baseline_range: DateRange


class ComparableWindow(CatalogModel):
    """The window an answer may use, and **why that one** — ADR 0016.

    All four parts travel together, and that is the whole point of the type. An
    earlier form of ``CatalogDecision`` transported only the range, which meant
    this gate computed a governed reason and a source list that no consumer could
    ever read. The window was correct and unusable.

    ``chosen_because`` is the load-bearing half. Two sources rarely cover the same
    period exactly, so a cross-source comparison silently narrows to the
    intersection — and a reader who sees only the dates cannot tell whether they
    are comparing January to January or January to three weeks of it. A window
    stated without its reason reads as a choice somebody made rather than a
    constraint the data imposed.

    ``sources`` are the sources the window was narrowed to **accommodate**, which
    is not the same set as the ones the caller asked about: a request naming
    three sources where one has no coverage narrows to the two that do.

    Both are required and non-empty, so an incompletely described window is not
    constructible. The refusal happens where the value is authored rather than
    three layers downstream, where the missing part would look like a consumer's
    problem.

    Lives here rather than in ``gates/coverage.py`` because it is now part of the
    published decision contract; the gate imports it and continues to export the
    name, so every construction site is unchanged.
    """

    start: date
    end: date
    sources: tuple[Identifier, ...] = Field(min_length=1)
    chosen_because: PtBrText

    @model_validator(mode="after")
    def _ordered(self) -> ComparableWindow:
        if self.end < self.start:
            raise ValueError(f"comparable window ends {self.end} before it starts {self.start}")
        return self

    @property
    def is_cross_source(self) -> bool:
        return len(self.sources) > 1


class Subject(CatalogModel):
    """The specific thing a decision is about."""

    kind: SubjectKind
    id: str = Field(min_length=1)


class Segment(CatalogModel):
    metric_version_id: str
    start: date
    end: date


class Limitation(CatalogModel):
    code: str
    message_pt_br: PtBrText
    applies_to: str


class FreshnessVerdict(CatalogModel):
    """One contributing source, as decision-contract §2 declares it.

    ``required`` is the load-bearing field: it distinguishes a source that feeds
    the requested metrics from one merely named in the request. Only required
    sources gate the outcome, and a reader who cannot tell them apart cannot
    tell why a stale source did or did not matter.

    ``last_successful_update`` is what makes an answer checkable — Principle III
    requires the source update time on every answer, not only on refusals.
    """

    source: Identifier
    required: StrictBool
    status: str
    last_successful_update: datetime | None = None
    lag: timedelta | None = None
    tolerance: timedelta | None = None


class CatalogValidationRequest(CatalogModel):
    """decision-contract §1.

    ``date_range`` is canonical-zone by definition. ``requester_access`` is what
    the principal *holds*; whether any of it authorises anything is the access
    registry's decision, not the request's claim.
    """

    metrics: tuple[Identifier, ...] = Field(min_length=1)
    dimensions: tuple[Identifier, ...] = ()
    sources: tuple[Identifier, ...] = ()
    date_range: DateRange
    comparison: Comparison | None = None
    requester_access: tuple[str, ...] = ()
    aggregate: Identifier | None = Field(
        default=None,
        description="Aggregation the caller intends to apply; checked against additivity (FR-003).",
    )

    def normalised(self) -> dict[str, Any]:
        """Order-independent form, for ``decision_id`` derivation.

        Sorted, because ``metrics=[a,b]`` and ``metrics=[b,a]`` are the same
        question and must produce the same decision id.
        """
        return {
            "metrics": sorted(self.metrics),
            "dimensions": sorted(self.dimensions),
            "sources": sorted(self.sources),
            "date_range": [self.date_range.start.isoformat(), self.date_range.end.isoformat()],
            "comparison": (
                None
                if self.comparison is None
                else {
                    "kind": self.comparison.kind,
                    "baseline_range": [
                        self.comparison.baseline_range.start.isoformat(),
                        self.comparison.baseline_range.end.isoformat(),
                    ],
                }
            ),
            "aggregate": self.aggregate,
        }


def derive_decision_id(
    request: CatalogValidationRequest,
    *,
    catalog_release_id: str,
    metric_version_ids: tuple[str, ...],
    policy_version: str,
    freshness_snapshot_ids: tuple[str, ...] = (),
    data_revision_ids: tuple[str, ...] = (),
) -> str:
    """``decision_id`` from exactly the six declared inputs (FR-066).

    An identical request against an identical catalog, policy and data revision
    returns an identical id — which is what makes SC-021 testable.

    The last two inputs are **parameters**, not lookups. Phase 6 owns none of
    freshness or data revisions and passes empty tuples; Phase 7 supplies them
    without this function changing. Deriving them here would be implementing a
    later phase's gate by the back door.
    """
    payload = {
        "request": request.normalised(),
        "catalog_release_id": catalog_release_id,
        "metric_version_ids": sorted(metric_version_ids),
        "policy_version": policy_version,
        "freshness_snapshot_ids": sorted(freshness_snapshot_ids),
        "data_revision_ids": sorted(data_revision_ids),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


class CatalogDecision(CatalogModel):
    """decision-contract §2. Immutable once constructed."""

    decision_id: str = Field(min_length=1)
    supersedes_decision_id: str | None = None

    policy_version: str = Field(min_length=1)
    catalog_release_id: str = Field(min_length=1)
    evaluated_at: datetime

    outcome: Outcome
    reason_code: ReasonCode = Field(
        description="Always present. A clean allow carries REQUEST_ALLOWED (Outcome.ALLOW).",
    )
    message_pt_br: PtBrText = Field(
        description="Looked up from the governed registry. Never generated or translated here.",
    )
    subject: Subject
    evidence_refs: tuple[EvidenceRef, ...] = Field(
        min_length=1,
        description="At least one. A decision that stood on nothing is not evidence.",
    )

    # Later-phase fields. Declared because the contract declares them; Phase 6
    # populates none of them.
    data_revisions: tuple[str, ...] = ()
    freshness: tuple[FreshnessVerdict, ...] = ()
    reproducibility: Reproducibility = Reproducibility.LIMITED
    finality: Finality = Finality.PRE_EVIDENCE
    segments: tuple[Segment, ...] = ()
    limitations: tuple[Limitation, ...] = ()
    comparable_window: ComparableWindow | None = None
    answerable_subset: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def _outcome_matches_the_reason_code(self) -> CatalogDecision:
        """The code decides the outcome; the caller may not disagree with it.

        Each reason code maps to exactly one outcome class. Letting a caller
        pass ``ALLOW_WITH_CAVEAT`` with a DENY code would let two call sites
        disagree about whether the same refusal is a refusal.
        """
        expected = outcome_for(self.reason_code)
        if self.outcome is not expected:
            raise ValueError(
                f"reason code {self.reason_code.value} is classified {expected.value}, "
                f"but the decision claims {self.outcome.value}"
            )
        return self

    @model_validator(mode="after")
    def _answerable_subset_is_disclosure_not_a_result(self) -> CatalogDecision:
        """FR-022: a decision carrying an answerable subset is still a denial."""
        if self.answerable_subset and self.outcome is not Outcome.DENY:
            raise ValueError(
                "answerable_subset is disclosure on a denial, never a substitute payload; "
                f"outcome is {self.outcome.value}"
            )
        return self

    @model_validator(mode="after")
    def _a_denial_carries_no_executable_window(self) -> CatalogDecision:
        """ADR 0016: a refusal must not ship evidence a consumer can execute against.

        A stated comparable window is an instruction — *these are the days both
        sides may be read over*. On a denial it would be an instruction attached
        to an answer nobody is getting, and the inference a downstream reader
        would draw is exactly the wrong one: the window is present, so the
        comparison may proceed.

        The disclosure a denial *is* entitled to make travels in ``limitations``
        and ``answerable_subset``, both of which are already governed as
        disclosure rather than as payload.
        """
        if self.comparable_window is not None and self.outcome is Outcome.DENY:
            raise ValueError(
                "a denied decision may not carry a comparable window; "
                "a refusal states no window an answer could be computed over"
            )
        return self

    @model_validator(mode="after")
    def _finality_and_reproducibility_require_evidence(self) -> CatalogDecision:
        """A permissive outcome may not claim more than its evidence supports.

        The failure this prevents is quiet: a gate result that passed every
        governance check, standing on no data revision at all, presenting itself
        as settled and fully reproducible. A consumer citing it would be citing a
        half-finished evaluation (FR-068).
        """
        if not self.data_revisions and self.reproducibility is Reproducibility.FULL:
            raise ValueError(
                "reproducibility 'full' requires at least one data_revision_id; "
                "a decision that stood on no revision is not fully reproducible (FR-068)"
            )
        if self.outcome is Outcome.DENY:
            # Nothing was read, so no data revision contributed to the refusal.
            return self
        if not self.data_revisions and self.finality is Finality.FINAL:
            raise ValueError(
                f"a {self.outcome.value} decision with no data_revision_id is PRE_EVIDENCE; "
                "final identity is established by T073 once required revisions exist"
            )
        return self

    @property
    def is_denial(self) -> bool:
        return self.outcome is Outcome.DENY

    @property
    def is_final(self) -> bool:
        return self.finality is Finality.FINAL


def metric_version_evidence(metric_id: str, version: int) -> EvidenceRef:
    """``EvidenceRef`` for a resolved metric version, e.g. ``active_users@2``."""
    return EvidenceRef(kind=EvidenceKind.METRIC_VERSION, id=f"{metric_id}@{version}")


def subject_for(kind: SubjectKind, identifier: str) -> Subject:
    return Subject(kind=kind, id=identifier)
