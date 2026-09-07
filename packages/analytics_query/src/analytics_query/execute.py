"""The composed execution entry point — ADR 0010.

`002` ships every component of its nine-step sequence and, until now, composed
none of them. `pipeline.run_until_evaluation` implements steps **1-7** and
returns the preflight decision; step 8 (the full evaluation, with the snapshot
step 7 read) and step 9 — compile, guards, dry run, execute, shape, mid-flight,
assemble, suppress, finalise, audit — existed as parts with nothing wiring them
together, because `002` had no consumer. `003` is the first.

This module is that wiring and **nothing else**. It is additive: no existing
module, signature or behaviour changes, and it introduces no second ordering.
Steps 1-7 are delegated verbatim to `run_until_evaluation`; steps 8 and 9 call
the same components `002` already owns, in the order `execution-contract.md`
specifies. Every governed property continues to be enforced where it already
was:

* **authorization before cost** — steps 1-3 are inside the delegated pipeline,
  so an unauthorized principal reaches no adapter call, no ledger entry and no
  policy disclosure. This module adds nothing before them;
* **governed limits** — the byte ceiling and row ceiling are checked against the
  resolved policy before execution, and the enforced ceiling is carried onto the
  job so the warehouse cancels rather than reports;
* **exact shape** — the executed schema must equal the validated one;
* **mid-flight catalog change** — the catalog is sampled before and after
  execution and a change abandons the result (`002` `FR-029`);
* **suppression** — cells below the governed threshold are withheld, never
  zeroed;
* **finalisation** — `001`'s own ``finalise`` advances the decision; no finality
  logic exists here;
* **value-free, fail-closed audit** — no result is released before its
  completion event is durably accepted.

What this module deliberately does **not** do: decide anything. Every verdict
comes from `001` through the pipeline, every refusal keeps its upstream reason
code, and no governance rule is restated here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, NoReturn, cast

from semantic_catalog.contracts.audit_event import PrincipalType as CatalogPrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from .audit.emit import AuditEmissionFailed, AuditSink, emit_or_refuse
from .audit.emit import refusal_for as audit_refusal_for
from .compile.guards import assert_emitted_text_is_safe
from .compile.render import render
from .compile.slots import resolve_structure
from .contracts._base import ContractViolation, build
from .contracts.audit import AnalyticsAuditEvent, AuditStage, PrincipalType
from .contracts.provenance import CostProvenance
from .contracts.reason_codes import AnalyticsReasonCode
from .contracts.result_provenance import ResultProvenance, SourceUpdate
from .decision.bridge import evaluate_fully, is_permissive, to_catalog_request
from .decision.caveats import carry_limitations
from .decision.finalise import finalise_decision
from .execution.dryrun import DryRunFailed, perform_dry_run
from .execution.ledger import UnresolvedAuthorizationContext
from .execution.limits_bytes import assert_within_byte_ceiling
from .execution.limits_rows import assert_returned_rows_within_ceiling, assert_within_row_ceiling
from .execution.midflight import CatalogSnapshot, assert_catalog_unchanged
from .execution.run import assert_execution_completed, execute_bounded
from .execution.shape import assert_shapes_agree
from .observations.failure import ObservationsUnavailable
from .pipeline import PipelineRefusal, PipelineState, run_until_evaluation
from .results.assemble import assemble_result
from .results.completeness import ResultDisposition, classify_result

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.contracts.metric import MetricVersion
    from semantic_catalog.loader.bundle import Bundle
    from semantic_catalog.validation.decision import CatalogDecision
    from semantic_catalog.validation.pipeline import FreshnessSnapshot

    from .contracts.request import AnalyticsQuery
    from .contracts.result import AnalyticsResult, ResultColumn
    from .decision.bridge import CatalogEvaluator
    from .execution.adapter import WarehouseAdapter
    from .execution.ledger import AuthorizationContext, ExecutionLedger
    from .observations.reader import ObservationReader

__all__ = ["ExecutedAnswer", "ExecutionRefused", "execute_analytics_query"]

#: The stage emitter, bound to the fields every event shares.
Emit = Callable[[AuditStage, Outcome, "ReasonCodeLike", dict[str, int | None] | None], None]
#: Either namespace may name a refusal; the composition never re-codes one.
ReasonCodeLike = AnalyticsReasonCode | ReasonCode


class ExecutionRefused(Exception):  # noqa: N818 - a governed refusal, not an error
    """The request stopped, carrying the governed reason it stopped for.

    Mirrors ``PipelineRefusal`` so a caller sees one refusal type across all nine
    steps. A refusal raised by steps 1-8 is re-raised unchanged rather than
    re-coded: the upstream reason code is the answer.
    """

    def __init__(self, violation: ContractViolation, *, stage: str) -> None:
        self.violation = violation
        self.code: ReasonCodeLike = violation.code
        self.stage = stage
        super().__init__(f"{stage}: {violation}")


@dataclass(frozen=True, slots=True)
class ExecutedAnswer:
    """Everything a governed execution produced, released together or not at all."""

    result: AnalyticsResult
    decision: CatalogDecision
    provenance: ResultProvenance
    disposition: ResultDisposition


def execute_analytics_query(
    request: AnalyticsQuery,
    *,
    evaluate: CatalogEvaluator,
    catalog_bundle: Bundle,
    ledger: ExecutionLedger,
    observations: ObservationReader,
    adapter: WarehouseAdapter,
    sink: AuditSink,
    context: AuthorizationContext,
    correlation_id: str,
    principal_ref: str,
    on: date,
    catalog_release_id: str,
    required_sources: frozenset[str],
    columns: tuple[ResultColumn, ...],
    sample_catalog: Callable[[], CatalogSnapshot],
    metric_version_ids: tuple[str, ...],
    freshness_snapshot: FreshnessSnapshot,
    metric_version: MetricVersion,
    dimension_columns: dict[str, str] | None = None,
) -> ExecutedAnswer:
    """Run the full governed sequence and return the result, or refuse.

    Steps 1-8 are delegated. Step 9 runs here, in the order
    ``execution-contract.md`` fixes, and releases nothing until its completion
    event has been durably accepted.
    """
    try:
        state = run_until_evaluation(
            request,
            evaluate=evaluate,
            catalog_bundle=catalog_bundle,
            ledger=ledger,
            observations=observations,
            context=context,
            correlation_id=correlation_id,
            principal_ref=principal_ref,
            on=on,
            catalog_release_id=catalog_release_id,
            required_sources=required_sources,
        )
    except PipelineRefusal as refusal:
        # Passed through, never re-coded. The upstream reason is the answer.
        raise ExecutionRefused(refusal.violation, stage=refusal.stage) from refusal
    except UnresolvedAuthorizationContext as exc:
        # Raised inside the preflight, earlier than step 6: `002` refuses an
        # incomplete context the moment it is needed, not when the ledger is
        # reached. Carried through with its own governed code rather than
        # re-classified.
        raise ExecutionRefused(
            ContractViolation(
                AnalyticsReasonCode.LEDGER_UNAVAILABLE,
                "the authorization context could not be established",
            ),
            stage="authorization_context",
        ) from exc
    except ObservationsUnavailable as exc:
        # Step 7 raises its own governed refusal rather than a PipelineRefusal.
        raise ExecutionRefused(
            ContractViolation(exc.code, "the governed observation read did not succeed"),
            stage="observations",
        ) from exc

    emit = _emitter(
        sink,
        request=request,
        correlation_id=correlation_id,
        principal_ref=principal_ref,
        context=context,
        policy_version=state.policy.version,
        catalog_release_id=catalog_release_id,
        metric_version_ids=metric_version_ids,
    )

    # --- step 8: the full evaluation, with the snapshot step 7 read ----------
    #
    # `run_until_evaluation` stops after step 7 and returns the *preflight*
    # decision, so the full evaluation belongs to the composition. It is the
    # same `evaluate()` the pipeline calls, with the snapshot supplied — this
    # feature implements no gate and re-orders nothing.
    decision = evaluate_fully(
        request,
        evaluate=evaluate,
        bundle=catalog_bundle,
        snapshot=freshness_snapshot,
        principal_type=CatalogPrincipalType(context.principal_type),
        authorization_scope=context.authorization_scope,
        requester_access=tuple(sorted(context.granted_access_tags)),
        on=on,
    )
    state = replace(state, decision=decision)

    _audit(emit, AuditStage.VALIDATION, decision.outcome, decision.reason_code)

    if not is_permissive(decision):
        _audit(emit, AuditStage.REFUSAL, decision.outcome, decision.reason_code)
        raise ExecutionRefused(
            _upstream_violation(decision.reason_code, "the catalog refused the request"),
            stage="evaluation",
        )

    return _step_nine(
        request,
        state=state,
        adapter=adapter,
        emit=emit,
        columns=columns,
        sample_catalog=sample_catalog,
        metric_version_ids=metric_version_ids,
        metric_version=metric_version,
        dimension_columns=dimension_columns or {},
        required_sources=required_sources,
        catalog_release_id=catalog_release_id,
        context=context,
    )


def _step_nine(
    request: AnalyticsQuery,
    *,
    state: PipelineState,
    adapter: WarehouseAdapter,
    emit: Emit,
    columns: tuple[ResultColumn, ...],
    sample_catalog: Callable[[], CatalogSnapshot],
    metric_version_ids: tuple[str, ...],
    metric_version: MetricVersion,
    dimension_columns: dict[str, str],
    required_sources: frozenset[str],
    catalog_release_id: str,
    context: AuthorizationContext,
) -> ExecutedAnswer:
    policy = state.policy

    # --- compile -> guards ---------------------------------------------------
    #
    # ``metric_version`` is required rather than optional: a missing one is a
    # caller-contract defect, not a governed refusal, and borrowing a governed
    # reason code to report it would put a defect into the audit trail wearing a
    # governance code's name.
    structure = resolve_structure(
        request,
        metric_version=metric_version,
        metric_id=request.metrics[0],
        dimension_columns=dimension_columns,
    )
    rendered = render(structure)
    assert_emitted_text_is_safe(rendered)

    # --- dry run and the governed ceilings, before anything executes ---------
    try:
        plan = perform_dry_run(adapter, rendered)
    except DryRunFailed as failure:
        _refuse(emit, _dry_run_violation(failure))
    assert_within_byte_ceiling(plan, policy)
    assert_within_row_ceiling(plan, policy)

    before = sample_catalog()
    _audit(emit, AuditStage.EXECUTION_START, Outcome.ALLOW, state.decision.reason_code)

    # --- bounded execution ---------------------------------------------------
    record = execute_bounded(adapter, plan, policy)
    execution = assert_execution_completed(record)

    # --- exact shape, then the mid-flight catalog check ----------------------
    assert_shapes_agree(plan.schema, execution.schema)
    assert_catalog_unchanged(before, sample_catalog())

    # --- assemble, bound, suppress -------------------------------------------
    result = assemble_result(execution, columns=columns)
    assert_returned_rows_within_ceiling(len(result.rows), policy)
    disposition = classify_result(result)

    # --- finalise through `001`, never here ----------------------------------
    finalised = finalise_decision(
        state.decision,
        to_catalog_request(request, requester_access=tuple(sorted(context.granted_access_tags))),
        required_sources=tuple(sorted(required_sources)),
        snapshot=None,
        metric_version_ids=metric_version_ids,
        period_start=request.date_range.start,
        period_end=request.date_range.end,
    )

    provenance = _provenance(
        state=state,
        plan_bytes=plan.estimated_bytes,
        actual_bytes=execution.actual_bytes,
        job_ref=execution.job_ref,
        required_sources=required_sources,
        metric_version_ids=metric_version_ids,
        catalog_release_id=catalog_release_id,
        result=result,
    )

    # --- nothing is released until the completion event is accepted ----------
    _audit(
        emit,
        AuditStage.EXECUTION_COMPLETE,
        finalised.decision.outcome,
        finalised.decision.reason_code,
        costs={
            "dry_run_bytes": plan.estimated_bytes,
            "actual_bytes": execution.actual_bytes,
            "row_count": len(result.rows),
        },
    )

    return ExecutedAnswer(
        result=result,
        decision=finalised.decision,
        provenance=provenance,
        disposition=disposition,
    )


def _upstream_violation(code: ReasonCode, detail: str) -> ContractViolation:
    """Carry an upstream code through without re-coding it.

    ``ContractViolation`` is typed to this feature's namespace because `002`
    raises its own codes. An upstream refusal keeps `001`'s code, so the cast is
    the explicit statement that the code is *passed through* — never translated
    into an execution-layer equivalent (`FR-017`).
    """
    return ContractViolation(cast("AnalyticsReasonCode", code), detail)


def _dry_run_violation(failure: DryRunFailed) -> ContractViolation:
    """The dry run's own refusal, or its governed code when it names none."""
    refusal = getattr(failure, "refusal", None)
    if callable(refusal):
        return cast("ContractViolation", refusal())
    return ContractViolation(AnalyticsReasonCode.DRY_RUN_FAILED, "the dry run did not succeed")


def _refuse(emit: Emit, violation: ContractViolation) -> NoReturn:
    _audit(emit, AuditStage.REFUSAL, Outcome.DENY, violation.code)
    raise ExecutionRefused(violation, stage="dry_run")


def _provenance(
    *,
    state: PipelineState,
    plan_bytes: int,
    actual_bytes: int,
    job_ref: str,
    required_sources: frozenset[str],
    metric_version_ids: tuple[str, ...],
    catalog_release_id: str,
    result: AnalyticsResult,
) -> ResultProvenance:
    """All ten elements, or construction fails. Incomplete provenance abstains."""
    observations = state.observations
    updates = tuple(
        SourceUpdate(source_id=o.source_id, last_updated_at=o.last_loaded_at)
        for o in observations.freshness
    )
    revisions = tuple(o.revision_id for o in observations.revisions if o.revision_id is not None)
    return build(
        ResultProvenance,
        contributing_sources=tuple(sorted(required_sources)),
        resolved_metric_versions=metric_version_ids,
        data_revisions=revisions,
        data_as_of=observations.read_at,
        source_updates=updates,
        dimensional_coverage=tuple(str(d) for d in result.columns if not d.is_metric),
        limitations=tuple(limit.code for limit in carry_limitations(state.decision)),
        cost=CostProvenance(
            dry_run_bytes=plan_bytes,
            actual_bytes=actual_bytes,
            maximum_bytes_billed=state.policy.maximum_bytes_billed,
        ),
        execution_identifiers=(state.execution_key.query_identity, job_ref),
        policy_version=state.policy.version,
        catalog_release_id=catalog_release_id,
    )


def _emitter(
    sink: AuditSink,
    *,
    request: AnalyticsQuery,
    correlation_id: str,
    principal_ref: str,
    context: AuthorizationContext,
    policy_version: str,
    catalog_release_id: str,
    metric_version_ids: tuple[str, ...],
) -> Emit:
    """Bind the fields every stage shares, leaving the stage-specific ones open."""

    def _emit(
        stage: AuditStage,
        outcome: Outcome,
        reason_code: ReasonCodeLike,
        costs: dict[str, int | None] | None = None,
    ) -> None:
        event = build(
            AnalyticsAuditEvent,
            stage=stage,
            correlation_id=correlation_id,
            emitted_at=datetime.now(UTC),
            principal_ref=principal_ref,
            principal_type=PrincipalType(context.principal_type),
            authorization_scope=context.authorization_scope,
            granted_access_tags=tuple(sorted(context.granted_access_tags)),
            metric_ids=tuple(str(m) for m in request.metrics),
            dimension_ids=tuple(str(d) for d in request.dimensions),
            source_ids=tuple(str(s) for s in request.sources),
            date_range_start=request.date_range.start.isoformat(),
            date_range_end=request.date_range.end.isoformat(),
            outcome=outcome,
            reason_code=reason_code,
            resolved_versions=metric_version_ids,
            policy_version=policy_version,
            catalog_release_id=catalog_release_id,
            **(costs or {}),
        )
        emit_or_refuse(sink, event)

    return _emit


def _audit(
    emit: Emit,
    stage: AuditStage,
    outcome: Outcome,
    reason_code: ReasonCodeLike,
    costs: dict[str, int | None] | None = None,
) -> None:
    """Emit synchronously; a rejected stage is fail-closed, never best-effort."""
    try:
        emit(stage, outcome, reason_code, costs)
    except AuditEmissionFailed as failure:
        raise ExecutionRefused(audit_refusal_for(failure), stage=f"audit:{stage}") from failure
