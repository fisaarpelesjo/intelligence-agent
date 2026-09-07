"""Phase 10 test support: executed sides and **fixture-only** governed formulas.

## The formulas here are fixture-only, and that is load-bearing

`D-18` ships empty. Every comparison refuses today, and that is the designed
state — so an arithmetic suite has nothing to exercise unless it supplies its own
formula set.

These are it, and they are marked so at every level: the module says it, the
constants say it, the ``version`` strings say it, and :data:`FIXTURE_MARKER` is
asserted by ``test_no_local_index``-style containment scans to appear in **no**
`src/` module. They are passed through ``resolve_comparison_formulas``'s
``instances`` parameter, which is injectable for fixtures and is not a runtime
switch: nothing in `src/` supplies one, and no environment setting reaches it.

**Nothing here is evidence for `D-18`.** Not the formula ids, not the unit rules,
not the zero-baseline rule, not the approval block — the approver role is a
literal ``fixture`` and the evidence ref says so. Authoring a plausible-looking
governed formula would be exactly the invented governance the dependency record
exists to prevent, and a later reader must not be able to mistake one of these
for content somebody approved.

## The executed sides

``ExecutedAnswer`` is what the ADR 0010 entry point returns: a result, the side's
own finalised catalog decision, ten-element provenance and a disposition. Built
directly here rather than by running `002`, because Phase 10 asserts what happens
to two answers **after** they exist, and running the full pipeline to obtain one
would make the arithmetic suite depend on `001`'s fixture catalog and a warehouse
adapter.

Built through the real contracts, though — every validator runs, so a side this
module can express is a side `002` could have returned.

TEST-ONLY.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from analytics_query.contracts.provenance import CostProvenance
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.contracts.result import (
    AnalyticsResult,
    Completeness,
    ResultCell,
    ResultColumn,
    ResultRow,
)
from analytics_query.contracts.result_provenance import ResultProvenance, SourceUpdate
from analytics_query.execute import ExecutedAnswer
from analytics_query.results.completeness import ResultDisposition, ResultKind
from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode, outcome_for
from semantic_catalog.validation.decision import (
    CatalogDecision,
    Finality,
    Limitation,
    Reproducibility,
    Segment,
    Subject,
    SubjectKind,
)
from semantic_catalog.validation.decision import (
    ComparableWindow as CatalogComparableWindow,
)

from analytics_interaction.contracts.answer import AttributedCaveat, CaveatOrigin, CaveatSet
from analytics_interaction.governance.schemas import (
    ComparisonFormula,
    ComparisonFormulas,
    ContentApproval,
)

__all__ = [
    "ABSOLUTE_DIFFERENCE",
    "BASELINE_RANGE",
    "FIXTURE_MARKER",
    "FIXTURE_VERSION",
    "PERCENTAGE_CHANGE",
    "PRIMARY_RANGE",
    "RATIO",
    "WINDOW_REASON",
    "caveat_set",
    "executed",
    "formula_instances",
    "request",
    "verdict",
]

#: Stamped into every fixture-only governed value here. A containment scan
#: asserts it appears in no `src/` module, so fixture content cannot leak into
#: production paths without the scan noticing.
FIXTURE_MARKER = "fixture-only-not-governed"

#: The formula-set version these fixtures declare. Distinct and obviously
#: synthetic, so a version-equality assertion cannot pass by coincidence.
FIXTURE_VERSION = f"{FIXTURE_MARKER}-v1"

PRIMARY_RANGE = (date(2026, 7, 1), date(2026, 7, 31))
BASELINE_RANGE = (date(2026, 6, 1), date(2026, 6, 30))

READ_AT = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)

#: The three formula ids `contracts/governed-content.md` names for the `D-18`
#: ``id`` field. Declared here **only** so the arithmetic can be exercised; the
#: unit rules and the zero-baseline rule are fixture values, not proposals.
ABSOLUTE_DIFFERENCE = ComparisonFormula(
    id="absolute_difference",
    surface_forms=("diferença absoluta",),
    unit_rule=FIXTURE_MARKER,
    zero_baseline="refuse_comparison",
)
RATIO = ComparisonFormula(
    id="ratio",
    surface_forms=("razão",),
    unit_rule=f"{FIXTURE_MARKER}-ratio",
    zero_baseline="refuse_comparison",
)
PERCENTAGE_CHANGE = ComparisonFormula(
    id="percentage_change",
    surface_forms=("variação percentual",),
    unit_rule=f"{FIXTURE_MARKER}-percent",
    zero_baseline="refuse_comparison",
)


def formula_instances(
    *formulas: ComparisonFormula,
    version: str = FIXTURE_VERSION,
    effective_from: date = date(2026, 1, 1),
    effective_to: date | None = None,
) -> tuple[ComparisonFormulas, ...]:
    """One fixture-only formula-set instance.

    Returns a tuple because ``resolve_comparison_formulas`` resolves *exactly
    one effective* instance from a collection — so a test can pass zero (the
    shipped state), one (usable) or two overlapping (ambiguous, refuses) without
    a different helper for each.
    """
    return (
        ComparisonFormulas(
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            approval=ContentApproval(
                approver_role="fixture",
                evidence_ref=FIXTURE_MARKER,
                approved_on=date(2026, 1, 1),
            ),
            formulas=formulas,
        ),
    )


def request(
    *,
    period: tuple[date, date] = PRIMARY_RANGE,
    metrics: tuple[str, ...] = ("installs",),
    dimensions: tuple[str, ...] = (),
    sources: tuple[str, ...] = ("appstore",),
) -> AnalyticsQuery:
    start, end = period
    return AnalyticsQuery(
        metrics=metrics,
        dimensions=dimensions,
        sources=sources,
        date_range=DateRange(start=start, end=end),
    )


#: The governed reason `001` states beside a comparable window. Carried verbatim
#: through `002`'s reader into ``GovernedComparison.window`` — so a test asserting
#: byte-equivalence has a distinctive string to assert against.
WINDOW_REASON = (
    "janela comparável entre appstore, playstore: interseção das coberturas "
    "observadas, de 2026-07-01 a 2026-07-31 (FR-024)"
)


def verdict(
    code: ReasonCode = ReasonCode.REQUEST_ALLOWED,
    *,
    catalog_release_id: str = "r-1",
    policy_version: str = "pol-1",
    window: tuple[date, date] | None = PRIMARY_RANGE,
    window_sources: tuple[str, ...] = ("appstore", "playstore"),
    window_reason: str = WINDOW_REASON,
    limitations: tuple[Limitation, ...] = (),
    segments: tuple[Segment, ...] = (),
) -> CatalogDecision:
    """A comparison verdict carrying the **complete** window — ADR 0016.

    Before the transport repair this fixture could only state a bare range, and
    `002`'s reader refused it — which is how the defect surfaced. The window is
    now `001`'s own ``ComparableWindow``, built through the real contract, so
    every validator that guards it runs here too.
    """
    start, end = window if window is not None else (None, None)
    return CatalogDecision(
        decision_id="dec-1",
        policy_version=policy_version,
        catalog_release_id=catalog_release_id,
        evaluated_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
        outcome=outcome_for(code),
        reason_code=code,
        message_pt_br="decisão de teste",
        subject=Subject(kind=SubjectKind.REQUEST, id="req-1"),
        evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r-1"),),
        comparable_window=(
            None
            if start is None or end is None
            else CatalogComparableWindow(
                start=start, end=end, sources=window_sources, chosen_because=window_reason
            )
        ),
        limitations=limitations,
        segments=segments,
    )


def executed(
    value: Decimal | int | None = Decimal("100"),
    *,
    unit: str = "count",
    code: ReasonCode = ReasonCode.REQUEST_ALLOWED,
    kind: ResultKind = ResultKind.POPULATED,
    completeness: Completeness = Completeness.COMPLETE,
    finality: Finality = Finality.FINAL,
    reproducibility: Reproducibility = Reproducibility.FULL,
    metric_versions: tuple[str, ...] = ("installs@1",),
    data_revisions: tuple[str, ...] = ("rev-1",),
    coverage: tuple[str, ...] = (),
    catalog_release_id: str = "r-1",
    policy_version: str = "pol-1",
    data_as_of: datetime = READ_AT,
    suppressed: bool = False,
    rows: int = 1,
    dimension_columns: tuple[str, ...] = (),
) -> ExecutedAnswer:
    """One executed side, exactly as the port would have returned it."""
    columns = (
        *(
            ResultColumn(identifier=name, unit="label", is_metric=False)
            for name in dimension_columns
        ),
        ResultColumn(identifier="installs", unit=unit, is_metric=True),
    )
    # A suppressed cell may not also carry a value — `002` refuses that shape,
    # because a withheld figure that is still present is not withheld.
    cell = (
        ResultCell(
            value=None,
            suppressed=True,
            suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
        )
        if suppressed
        else ResultCell(value=value)
    )
    result = AnalyticsResult(
        columns=columns,
        rows=(
            ()
            if completeness is Completeness.EMPTY
            else tuple(
                ResultRow(labels=tuple(f"d{index}" for index in dimension_columns), cells=(cell,))
                for _ in range(rows)
            )
        ),
        completeness=completeness,
    )
    decision = CatalogDecision(
        decision_id="side-1",
        policy_version=policy_version,
        catalog_release_id=catalog_release_id,
        evaluated_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
        outcome=outcome_for(code),
        reason_code=code,
        message_pt_br="lado de teste",
        subject=Subject(kind=SubjectKind.REQUEST, id="side"),
        evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id=catalog_release_id),),
        finality=finality,
        reproducibility=reproducibility,
        # `001` couples the two: ``full`` requires at least one revision, and an
        # ALLOW decision with none is ``PRE_EVIDENCE`` whatever it claims. So the
        # revisions travel with every side rather than being set apart.
        data_revisions=data_revisions,
    )
    provenance = ResultProvenance(
        contributing_sources=("appstore",),
        resolved_metric_versions=metric_versions,
        data_revisions=data_revisions,
        data_as_of=data_as_of,
        source_updates=(SourceUpdate(source_id="appstore", last_updated_at=READ_AT),),
        dimensional_coverage=coverage,
        limitations=(),
        cost=CostProvenance(dry_run_bytes=1, actual_bytes=1, maximum_bytes_billed=2),
        execution_identifiers=("qid-1", "job-1"),
        policy_version=policy_version,
        catalog_release_id=catalog_release_id,
    )
    return ExecutedAnswer(
        result=result,
        decision=decision,
        provenance=provenance,
        disposition=ResultDisposition(kind=kind),
    )


def caveat_set(*codes: tuple[ReasonCode, CaveatOrigin, str]) -> CaveatSet:
    """A caveat set carrying upstream text verbatim.

    The message is supplied per caveat rather than generated, because
    ``AttributedCaveat.message_pt_br`` is upstream wording carried byte-identical
    and a helper that composed one would be modelling the thing the contract
    forbids.
    """
    caveats = tuple(
        AttributedCaveat(code=code, message_pt_br=message, origin=origin)
        for code, origin, message in codes
    )
    return CaveatSet(caveats=caveats, total=len(caveats))


def limitation(code: str, message: str = "limitação de teste") -> Limitation:
    return Limitation(code=code, message_pt_br=message, applies_to="request")


#: Convenient aliases so a suite reads as prose rather than as enum access.
VERDICT_ORIGIN = CaveatOrigin.VERDICT
SIDE_A = CaveatOrigin.SIDE_A
SIDE_B = CaveatOrigin.SIDE_B
ALLOWED = ReasonCode.REQUEST_ALLOWED
CAVEATED = ReasonCode.EQUIVALENT_PARTIAL_COMPARISON
DENIED = ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON
PERMISSIVE = Outcome.ALLOW
