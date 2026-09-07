"""Ordered gate pipeline — T056 (FR-011, FR-040; decision-contract §4).

The first denial short-circuits. Gates run in a fixed order, and the order is
load-bearing:

```
0  Release state  →  0  Policy resolution
1  Existence      →  2  Lifecycle     →  3  Authorisation →  4  Combination →  5  Grain
               →  6  Comparability →  7  Coverage      →  8  Freshness   →  9  Period
              → 11  As-of segmentation
```

**Release state and policy resolve before any gate**, and neither is a gate. A
withdrawn release denies every *new* decision under ``RELEASE_WITHDRAWN`` while
staying resolvable for the decisions already issued under it (FR-075); a policy
that cannot be resolved denies under ``POLICY_UNRESOLVABLE`` (FR-072). Both are
preconditions for evaluating anything, not questions about the request.

**As-of segmentation is last and never denies** (decision-contract §4). A range
crossing a definition change is a legitimate question; the illegitimate answer is
a single blended figure, so it produces a caveat plus ordered segments (FR-035).

**Comparability before coverage.** Whether two things may be compared at all is
settled before the system reasons about whether the days behind them exist — a
comparison nobody authorised is refused on that ground, not on a coverage
technicality that would send the reader to fix the wrong thing.

**Freshness before period, coverage before freshness.** A stale source is
refused before the system reasons about whether its period is complete, and
whether the days exist at all is settled before whether they are current.
Coverage and freshness are **independent** (FR-071): being on time does not
manufacture a missing day, and covering the period does not make a stale load
fresh.

**Authorisation precedes combination.** Otherwise a rejection discloses the
shape of a metric the requester is not permitted to see — "you cannot slice this
by app_version" tells them the metric exists, has dimensions, and which. A test
asserts this ordering directly, because it is the kind of property that survives
review and dies in a refactor.

Policy resolves first, before any gate. A decision must record the governed
policy version it was evaluated under, and there is no default to fall back on:
zero effective policies and more than one both deny under
``POLICY_UNRESOLVABLE`` (FR-072).

Gate 10 (retention) is a later phase. It is absent from ``GATES`` rather than
stubbed, because a stub that always passes is indistinguishable from a gate that
does not work.

**Unknown input denies.** Every gate refuses what it does not recognise, and an
unhandled exception inside a gate becomes a denial rather than propagating: a
crash is not an authorisation.

**Caveats accumulate; the first denial wins.** A gate may return a caveat
(ALLOW_WITH_CAVEAT) instead of a denial — a deprecated metric, for instance.
Evaluation continues past it, so a later gate that denies still produces the
denial, and no caveat raised earlier leaks anything about a metric the requester
turns out not to be authorised to see. A run reaching the end with caveats is
ALLOW_WITH_CAVEAT; a run with none is ALLOW carrying ``REQUEST_ALLOWED``.

**Every decision here is PRE_EVIDENCE.** The pipeline answers the governance
question and touches no data revision, so its output is provisional by
construction and says so (FR-068). T073 establishes final identity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, time

from ..comparability.caveats import caveat_limitations
from ..comparability.gate import check_comparability
from ..contracts.access_tag import PrincipalType
from ..contracts.audit_event import EvidenceKind, EvidenceRef
from ..contracts.reason_codes import Outcome, ReasonCode, outcome_for
from ..contracts.reason_message import MissingReasonMessageError, ReasonMessageRegistry
from ..freshness.external import FreshnessSnapshot
from ..freshness.limitations import limitations_for
from ..loader.bundle import Bundle
from ..loader.release_state import CatalogRelease
from ..periods.canonical import canonical_period
from ..provenance.evidence import evidence_refs_for
from ..resolution.as_of import segment, spans_definition_change
from ..resolution.deprecation import replacement_guidance
from .decision import (
    CatalogDecision,
    CatalogValidationRequest,
    FreshnessVerdict,
    Limitation,
    Segment,
    Subject,
    SubjectKind,
    derive_decision_id,
)
from .disclosure import PROTECTS_SOURCE_METADATA, answerable_subset
from .gates.as_of import gate_11_as_of, request_segments
from .gates.authorization import authorises_metric, gate_3_authorization
from .gates.combination import gate_4_combination
from .gates.comparability import gate_6_comparability
from .gates.context import GateContext, GateVerdict
from .gates.coverage import ComparableWindow, gate_7_coverage, window_for
from .gates.existence import dated_deprecation, gate_1_existence, gate_2_lifecycle
from .gates.freshness import gate_8_freshness
from .gates.grain import gate_5_grain
from .gates.period import gate_9_period
from .policy_runtime import resolve_policy

__all__ = ["GATES", "GateName", "evaluate", "gate_order", "resolved_version_ids"]

GateName = str

#: The ordered pipeline. Position is the contract, not an implementation detail.
GATES: Sequence[tuple[GateName, Callable[[GateContext], GateVerdict | None]]] = (
    ("existence", gate_1_existence),
    ("lifecycle", gate_2_lifecycle),
    ("authorization", gate_3_authorization),
    ("combination", gate_4_combination),
    ("grain", gate_5_grain),
    ("comparability", gate_6_comparability),
    ("coverage", gate_7_coverage),
    ("freshness", gate_8_freshness),
    ("period", gate_9_period),
    ("as_of", gate_11_as_of),
)


def gate_order() -> tuple[GateName, ...]:
    """The gate names in evaluation order. Asserted by the ordering test."""
    return tuple(name for name, _ in GATES)


def _interpolation_values(
    bundle: Bundle,
    request: CatalogValidationRequest,
    subject: Subject,
    policy_version: str,
    context: GateContext | None = None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Allowlisted interpolation values, all governed identifiers.

    Everything here is a catalog identifier, a role, a field **name**, a
    canonical-zone date or a release id. No metric value, no draft definition, no
    credential and no prompt text can reach a message through this map, because
    none of them is in it — the registry's allowlist is the second guard, not the
    only one.

    ``extra`` carries values the decision computed and this function cannot —
    the resolved ``metric_version_id`` for a segmented range, and a replacement
    metric that has passed its own disclosure check. It is applied last, so a
    caller-computed value wins over the generic fallback below.
    """
    values: dict[str, str] = {
        "catalog_release_id": bundle.release_id,
        "policy_version": policy_version,
        "period_start": request.date_range.start.isoformat(),
        "period_end": request.date_range.end.isoformat(),
    }
    if subject.kind is SubjectKind.METRIC:
        values["metric_id"] = subject.id
    if subject.kind is SubjectKind.DIMENSION:
        values["dimension_id"] = subject.id
    if subject.kind is SubjectKind.SOURCE:
        values["source_id"] = subject.id
    if subject.kind is SubjectKind.ACCESS_TAG:
        values["access_tag"] = subject.id

    values.setdefault("metric_id", ", ".join(sorted(request.metrics)))
    if request.dimensions:
        values.setdefault("dimension_id", ", ".join(sorted(request.dimensions)))
    if request.sources:
        values.setdefault("source_id", ", ".join(sorted(request.sources)))

    metric = bundle.internal.metrics.get(values["metric_id"])
    if metric is not None:
        values["owner"] = metric.owner
        values["access_tag"] = values.get("access_tag", metric.access)
        state = bundle.lifecycles.get(metric.name)
        if state is not None:
            values["missing_fields"] = ", ".join(state.missing_fields)

    # Freshness wording needs observed values. They are identifiers, timestamps
    # and durations — never a metric value, and never anything a caller typed.
    values.update(_freshness_values(bundle, subject, context))
    if extra:
        values.update(extra)
    return values


def _freshness_values(
    bundle: Bundle, subject: Subject, context: GateContext | None
) -> dict[str, str]:
    """Allowlisted freshness fields for the source a refusal names."""
    if context is None or context.snapshot is None:
        return {}
    source = bundle.internal.sources.get(subject.id)
    record = context.snapshot.record_for(subject.id)
    if source is None or record is None:
        return {}
    values: dict[str, str] = {"delay_tolerance": str(source.delay_tolerance)}
    if record.last_successful_update is not None:
        values["last_successful_update"] = record.last_successful_update.isoformat()
    if record.completeness_ratio is not None:
        values["completeness_ratio"] = f"{record.completeness_ratio:.0%}"
    return values


def _message(
    registry: ReasonMessageRegistry | None,
    code: ReasonCode,
    detail: str,
    values: dict[str, str],
) -> str:
    """The governed pt-BR message for ``code``, rendered from allowlisted values.

    Never generated and never translated at answer time (FR-055). Two failures
    surface as explicit error text rather than as prose: no registry, and no
    canonical message for a reachable code. A missing interpolation value also
    surfaces rather than half-rendering — a stray ``{placeholder}`` in a
    user-visible refusal is worse than an error.
    """
    if registry is None:
        return f"[sem registro de mensagens] {code.value}: {detail}"
    try:
        message = registry.require(code)
    except MissingReasonMessageError:
        return f"[sem mensagem canônica] {code.value}: {detail}"
    try:
        return message.render(values)
    except ValueError as exc:
        return f"[mensagem não renderizável] {code.value}: {exc}"


def _freshness_verdicts(context: GateContext) -> tuple[FreshnessVerdict, ...]:
    """One verdict per named source, required flag included (contract §2).

    Named-but-unused sources appear with ``required: false`` rather than being
    dropped: a reader needs to see that the stale source they named was not the
    reason for the outcome. A source the snapshot says nothing about is reported
    ``unknown`` — silence is a state, not an absence of one.
    """
    required = set(context.required_source_ids)
    verdicts: list[FreshnessVerdict] = []
    for requirement in context.requirements:
        source = context.bundle.internal.sources.get(requirement.source)
        record = (
            context.snapshot.record_for(requirement.source)
            if context.snapshot is not None
            else None
        )
        verdicts.append(
            FreshnessVerdict(
                source=requirement.source,
                required=requirement.source in required,
                status=record.status.value if record is not None else "unknown",
                last_successful_update=record.last_successful_update if record else None,
                lag=(
                    record.lag(now=context.snapshot.observed_at)
                    if record is not None and context.snapshot is not None
                    else None
                ),
                tolerance=source.delay_tolerance if source is not None else None,
            )
        )
    return tuple(verdicts)


#: Codes whose limitation may name a replacement metric. Only the dated
#: deprecation outcomes — the plain caveat says the metric is deprecated and
#: nothing more.
_DEPRECATION_CODES = frozenset(
    {
        ReasonCode.METRIC_DEPRECATED_FOR_PERIOD,
        ReasonCode.SPANS_DEPRECATION_BOUNDARY,
        ReasonCode.COMPARISON_REQUIRES_DEPRECATED_PERIOD,
    }
)


def _deprecation_limitations(
    context: GateContext, message: str, code: ReasonCode
) -> tuple[Limitation, ...]:
    """The unavailable half of a deprecated range, named and dated (FR-063, FR-064).

    A post-boundary span is reported as an explicit limitation rather than
    quietly dropped, so a reader sees which days the answer does not cover.

    ``applies_to`` encodes the disclosure: ``{metric}:{start}..{end}`` normally,
    with ``:replacement={id}`` appended when the governed policy permits naming a
    replacement **and** the requester is authorised for it. Both gates must open.
    A replacement is guidance in a refusal; it is never substituted for the
    metric that was asked for, and the answer carries no figure from it.

    The wording is the governed canonical message, not prose composed here —
    ``message`` is what the registry already rendered for this code.
    """
    if code not in _DEPRECATION_CODES:
        return ()
    limitations: list[Limitation] = []
    for verdict in dated_deprecation(context):
        replacement = replacement_guidance(
            verdict,
            policy_allows=context.policy.refusal.disclose_replacement_metric_id,
            # Both metrics, not just the replacement. A requester who is not
            # authorised for the deprecated metric may not learn what replaced
            # it either — the pair is the relationship being protected.
            requester_authorised=(
                verdict.replacement_metric_id is not None
                and authorises_metric(context, verdict.metric_id)
                and authorises_metric(context, verdict.replacement_metric_id)
            ),
        )
        suffix = f":replacement={replacement}" if replacement else ""
        for segment_span in verdict.segments:
            if segment_span.available:
                continue
            limitations.append(
                Limitation(
                    code=verdict.reason_code.value,
                    message_pt_br=message,
                    applies_to=(
                        f"{verdict.metric_id}:{segment_span.start}..{segment_span.end}{suffix}"
                    ),
                )
            )
    return tuple(limitations)


def resolved_version_ids(bundle: Bundle, request: CatalogValidationRequest) -> tuple[str, ...]:
    """``metric_version_id`` set resolved **as of the requested range** (FR-034).

    Not the newest version. Taking the newest would make ``decision_id`` — which
    folds this set in — change for a closed historical period the moment somebody
    appended a version 3, and a figure already published for that period must not
    move because the metric was redefined afterwards (SC-021).

    A range no version covers falls back to the newest, so the decision still
    cites something: the range is refused elsewhere, and a refusal that stood on
    nothing would be unauditable.
    """
    refs: set[str] = set()
    for metric_id in sorted(set(request.metrics)):
        metric = bundle.internal.metrics.get(metric_id)
        if metric is None:
            continue
        spans = segment(metric, request.date_range.start, request.date_range.end)
        if spans:
            refs.update(span.metric_version_id for span in spans)
            continue
        newest = max(metric.versions, key=lambda v: (v.effective_from, v.version))
        refs.add(f"{metric_id}@{newest.version}")
    return tuple(sorted(refs))


def evaluate(
    request: CatalogValidationRequest,
    bundle: Bundle,
    *,
    principal_type: PrincipalType,
    authorization_scope: str,
    on: date,
    snapshot: FreshnessSnapshot | None = None,
    partial_cutoff: time | None = None,
    evaluated_at: datetime | None = None,
    release: CatalogRelease | None = None,
) -> CatalogDecision:
    """Run the ordered pipeline and return exactly one decision.

    Always returns a decision. A caller must be able to audit why something was
    refused, and an exception is not auditable.

    ``release`` is the governed state of the release this bundle came from. When
    the caller supplies one that no longer admits new decisions, evaluation stops
    before any gate: a withdrawn release must not back a new answer, however
    healthy every other input is (FR-075). Supplying none is unchanged behaviour
    for callers that keep no ledger.
    """
    stamp = evaluated_at or datetime.now(tz=UTC)
    registry = bundle.internal.reason_messages
    version_ids = resolved_version_ids(bundle, request)
    refs = tuple(EvidenceRef(kind=EvidenceKind.METRIC_VERSION, id=ref) for ref in version_ids) or (
        EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id=bundle.release_id),
    )

    if release is not None and not release.admits_new_decisions:
        return _decision(
            request=request,
            bundle=bundle,
            policy_version=resolve_policy(bundle.internal, on=on).version,
            code=ReasonCode.RELEASE_WITHDRAWN,
            subject=Subject(kind=SubjectKind.POLICY, id=release.release_id),
            detail=(
                f"catalog release {release.release_id} is {release.state.value} and no longer "
                "backs new decisions; it stays resolvable for the decisions already issued "
                "under it"
            ),
            registry=registry,
            refs=refs,
            version_ids=version_ids,
            stamp=stamp,
        )

    resolution = resolve_policy(bundle.internal, on=on)
    if not resolution.resolved:
        code = resolution.reason_code or ReasonCode.POLICY_UNRESOLVABLE
        return _decision(
            request=request,
            bundle=bundle,
            policy_version=resolution.version,
            code=code,
            subject=Subject(kind=SubjectKind.POLICY, id="catalog_policy"),
            detail=resolution.detail,
            registry=registry,
            refs=refs,
            version_ids=version_ids,
            stamp=stamp,
        )

    context = GateContext(
        request=request,
        bundle=bundle,
        policy=resolution.require(),
        principal_type=principal_type,
        authorization_scope=authorization_scope,
        on=on,
        snapshot=snapshot,
        partial_cutoff=partial_cutoff,
    )

    caveats: list[GateVerdict] = []
    for name, gate in GATES:
        try:
            verdict = gate(context)
        except Exception as exc:  # a crash must not authorise
            return _decision(
                request=request,
                bundle=bundle,
                policy_version=resolution.version,
                code=ReasonCode.POLICY_UNRESOLVABLE,
                subject=Subject(kind=SubjectKind.REQUEST, id=name),
                detail=f"gate {name!r} failed to evaluate: {exc}",
                registry=registry,
                refs=refs,
                version_ids=version_ids,
                stamp=stamp,
                context=context,
            )
        if verdict is None:
            continue
        if verdict.is_denial:
            # The denial wins, and it wins over any caveat already collected: a
            # caveat about a metric the requester may not see would leak it.
            return _decision(
                request=request,
                bundle=bundle,
                policy_version=resolution.version,
                code=verdict.reason_code,
                subject=verdict.subject,
                detail=verdict.detail,
                registry=registry,
                refs=refs,
                version_ids=version_ids,
                stamp=stamp,
                context=context,
            )
        caveats.append(verdict)

    if caveats:
        first = caveats[0]
        return _decision(
            request=request,
            bundle=bundle,
            policy_version=resolution.version,
            code=first.reason_code,
            subject=first.subject,
            detail=first.detail,
            registry=registry,
            refs=refs,
            version_ids=version_ids,
            stamp=stamp,
            context=context,
        )

    return _decision(
        request=request,
        bundle=bundle,
        policy_version=resolution.version,
        code=ReasonCode.REQUEST_ALLOWED,
        subject=Subject(kind=SubjectKind.REQUEST, id=",".join(sorted(request.metrics))),
        detail="every implemented gate passed",
        registry=registry,
        refs=refs,
        version_ids=version_ids,
        stamp=stamp,
        context=context,
    )


def _decision(
    *,
    request: CatalogValidationRequest,
    bundle: Bundle,
    policy_version: str,
    code: ReasonCode,
    subject: Subject,
    detail: str,
    registry: ReasonMessageRegistry | None,
    refs: tuple[object, ...],
    version_ids: tuple[str, ...],
    stamp: datetime,
    context: GateContext | None = None,
) -> CatalogDecision:
    """Build the decision. The only place a decision is constructed.

    Every outcome carries a governed code and its governed message, a clean allow
    included — ``REQUEST_ALLOWED`` exists so an allow is representable in a
    decision *and* in an audit event.

    The result is always ``PRE_EVIDENCE`` with ``limited`` reproducibility: this
    pipeline reads no data revision, so claiming more would overstate what it
    stood on.
    """
    outcome = outcome_for(code)

    # As-of segmentation (T085, FR-034, FR-035). Computed once and used twice:
    # as the decision's segments, and as the resolved metric_version_id a
    # SPANS_DEFINITION_CHANGE message names. Withheld on a protected refusal for
    # the same reason the freshness verdicts are — it names versions of a metric
    # the requester may not be permitted to see.
    protected = code in PROTECTS_SOURCE_METADATA
    segments: tuple[Segment, ...] = ()
    extra: dict[str, str] = {}
    if version_ids:
        extra["metric_version_id"] = version_ids[0]
    if context is not None and not protected:
        resolved = request_segments(context)
        # Populated **only when the range crosses a definition change**, exactly
        # as decision-contract §2 declares. A single-version range needs no
        # segmentation, and emitting one span there would put something on every
        # denial that a reader could mistake for a narrowed answer.
        crossing = {
            metric_id
            for metric_id in {s.metric_id for s in resolved}
            if spans_definition_change([s for s in resolved if s.metric_id == metric_id])
        }
        segments = tuple(
            Segment(metric_version_id=s.metric_version_id, start=s.start, end=s.end)
            for s in resolved
            if s.metric_id in crossing
        )
        for_subject = [s for s in resolved if s.metric_id == subject.id] or list(resolved)
        if for_subject:
            newest = max(for_subject, key=lambda s: (s.start, s.version))
            extra["metric_version_id"] = newest.metric_version_id

    message = _message(
        registry,
        code,
        detail,
        _interpolation_values(bundle, request, subject, policy_version, context, extra),
    )

    # Provenance travels with the decision (T074, FR-039, Principle III).
    # An authorisation or existence refusal carries none of it: the requester is
    # not permitted to learn which sources a metric draws on, or when they last
    # loaded.
    verdicts: tuple[FreshnessVerdict, ...] = ()
    if protected:
        # The release id alone. Citing the resolved metric versions would tell a
        # requester who may not see the metric how many times it has been
        # redefined and when — a version history is a shape, and Gate 3 runs
        # early precisely so a refusal discloses none of it. The version ids
        # still derive ``decision_id``; they simply are not published.
        refs = (EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id=bundle.release_id),)
    elif context is not None:
        verdicts = _freshness_verdicts(context)
        refs = evidence_refs_for(
            version_ids,
            bundle.release_id,
            context.snapshot,
            None,
            context.required_source_ids,
        )

    # Authored outages and restatements touching the period (T071, FR-028).
    limitations: tuple[Limitation, ...] = ()
    if context is not None:
        period = canonical_period(request.date_range.start, request.date_range.end, on=context.on)
        limitations = tuple(
            Limitation(
                code=item.code.value,
                message_pt_br=item.reason_pt_br,
                applies_to=f"{item.source}:{item.applies_from}..{item.applies_to}",
            )
            for item in limitations_for(
                bundle.internal.sources, context.required_source_ids, period
            )
        )
        # The declared comparability caveat or business reason (T083, FR-030,
        # FR-031). Withheld on a protected refusal for the same reason the
        # freshness verdicts are: it names the metrics involved.
        if not protected:
            limitations += caveat_limitations(
                check_comparability(
                    bundle.internal.comparability_rules,
                    request.metrics,
                    request.sources,
                )
            )
            limitations += _deprecation_limitations(context, message, code)

    # The comparable window this request's coverage produced (T067, FR-023,
    # FR-024, SC-005) — ADR 0016. Published only on a permitted decision, and
    # only for a request whose answer is qualified by one.
    #
    # The object is the coverage gate's own return value, assigned whole. Not
    # rebuilt, not copied field by field, not normalised: `chosen_because` is
    # governed wording and `sources` is the set the coverage was narrowed to
    # accommodate, and either one reassembled here would be this pipeline
    # restating a value the gate already decided.
    window: ComparableWindow | None = None
    if (
        context is not None
        and not protected
        and outcome is not Outcome.DENY
        and _states_a_window(request)
    ):
        window = window_for(context)

    # Disclosure on a denial, never a substitute payload (T070, FR-022).
    subset: tuple[str, ...] = ()
    if context is not None and outcome is Outcome.DENY:
        subset = answerable_subset(
            bundle.internal,
            context.policy,
            context.requirements,
            context.snapshot,
            outcome=outcome,
            reason_code=code,
        )

    return CatalogDecision(
        segments=segments,
        decision_id=derive_decision_id(
            request,
            catalog_release_id=bundle.release_id,
            metric_version_ids=version_ids,
            policy_version=policy_version,
        ),
        policy_version=policy_version,
        catalog_release_id=bundle.release_id,
        evaluated_at=stamp,
        outcome=outcome,
        reason_code=code,
        message_pt_br=message,
        subject=subject,
        evidence_refs=refs,  # type: ignore[arg-type]
        answerable_subset=subset,
        limitations=limitations,
        freshness=verdicts,
        comparable_window=window,
    )


def _states_a_window(request: CatalogValidationRequest) -> bool:
    """Whether this request's answer is qualified by a comparable window.

    Two triggers, both from approved requirements and neither invented here:

    * the request **declares a comparison** — `SC-005` measures "cross-source
      comparisons return the comparable window that was used";
    * the request is **cross-source** — `FR-024` requires a cross-source request
      to "state which window was selected and why".

    A single-source request that compares nothing gets none. `FR-023` gives it
    the source's full coverage rather than a narrowed window, so there is no
    choice to explain, and attaching one would put a qualification on an answer
    that was never qualified.
    """
    return request.comparison is not None or len(request.sources) > 1
