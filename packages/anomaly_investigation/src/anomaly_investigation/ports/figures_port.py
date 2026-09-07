"""The figures port — T017 (`FR-003`, `FR-008`, `FR-071`).

Asks `002` for the figure and its provenance, and asks `003` for the movement
between the two. **It performs no arithmetic of its own** — `FR-003` — and the
way that is kept is structural rather than promised: this module imports no
operator, holds no ``Decimal`` expression, and every number it returns arrived
from one of the two upstream surfaces.

**The zero baseline comes first, and that ordering is the point of the task.**
A percentage-change rule meets a zero baseline before it meets anything
interesting: a KPI that had no trials on the baseline day, a country that appears
for the first time, a game launched last week. Written the other way round --
derive first, inspect afterwards -- the division has already happened and the
only remaining choices are to raise, to substitute infinity, or to invent a
fallback. `003` already owns that decision and refuses to invent one, so this
port asks it **before** anything is derived.

## What it asks, and of whom

| question | asked of | surface |
|---|---|---|
| what is the figure, over this window? | `002` | ``execute_analytics_query`` |
| where did it come from? | `002` | ``ExecutedAnswer.provenance``, carried whole |
| is this baseline usable at all? | `003` | ``assert_baseline_is_usable`` |
| what is the movement between them? | `003` | ``derive_figure`` |

**Both sides' provenance is carried, never merged.** `003`'s own ``SideResult``
keeps them apart for `FR-072` and `FR-033`, and merging them here would undo
upstream of the layer that protects it. A reader of a run sees which execution
produced the primary figure and which produced the baseline, separately.

## Every cross-package import here names a PUBLIC path

`ContractViolation` used to be imported from ``analytics_interaction.contracts._base``.
The **name** is exported -- it is in that package's ``__all__`` -- but the **path**
is a private module, and `FR-008` is about the exported *surface*, not about the
identifier happening to be public somewhere. So the handoff sentence *"every name
used was already exported"* was true about the name and false about the path.

**And no node caught it**, which is the part worth keeping: `005`'s own
``test_no_upstream_file_was_edited`` opens by promising *"upstream is consulted
through its exported surface"*, and what it actually measures is **whether an
upstream file was edited**. An import through a private path edits nothing, so it
passed under twelve green nodes. ``test_no_private_upstream_import.py`` now states
the promise structurally.

## The seam is a protocol, deliberately

``execute_analytics_query`` takes eighteen parameters, all of them infrastructure
this feature does not own -- a ledger, an adapter, an audit sink, a bundle. A
direct call here would mean this module knowing how to build them, which is the
reaching-around that `FR-008` forbids. So the caller binds them once and hands
this port a callable, exactly as ``catalog_port`` does with ``CatalogEvaluator``.

## `ANOMALY_FIGURE_UNAVAILABLE` and `ANOMALY_BASELINE_NOT_USABLE` are not the same

The first says **an execution did not produce a figure** -- it refused, or it
answered a shape with no single value in it. The second says **the figure exists
and the comparison cannot be made over it**, which today means a zero baseline
under a governed rule that refuses. Collapsing them would report *"we could not
get the number"* for a case where the number is sitting right there, and the
distinction is what tells an operator whether to look at the pipeline or at the
period.

**And the upstream word travels on both**, the same rule ``catalog_port`` follows:
our code says *which layer stopped*, and ``upstream_code`` says *in whose words*.

## `ANOMALY_BASELINE_NOT_USABLE` also carries "there is no governed formula", and
## the carrier is imperfect

The same imperfection ``catalog_port`` declares about ``NOT_BOUND``. When `D-18`
resolves no formula set at all -- which is the **shipped state**, measured: zero
effective instances of `comparison-formulas.yaml` -- the comparison cannot be made,
and this port carries that under ``ANOMALY_BASELINE_NOT_USABLE``. The words do not
fit: nothing is wrong with the baseline.

**Coining a code that fits is not this feature's to do**, so what keeps the
imperfect carrier from lying is the same mechanism: the upstream word travels
verbatim, and a reader sees ``INTERPRETATION_VOCABULARY_UNRESOLVABLE`` beside ours
and learns that the governed vocabulary, not the data, is what stopped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

from analytics_interaction.comparison.compute import derive_figure, to_exact
from analytics_interaction.comparison.formula import assert_baseline_is_usable, resolve_formula
from analytics_interaction.contracts import ContractViolation
from analytics_interaction.contracts.comparison import DerivedFigure
from analytics_interaction.governance.resolve import ContentUnresolvable
from analytics_query.contracts.result import AnalyticsResult
from analytics_query.contracts.result_provenance import ResultProvenance
from analytics_query.execute import ExecutionRefused
from pydantic import ConfigDict, Field

from ..contracts import AnomalyModel, AnomalyReasonCode, GovernedName

# The three types above are imported at RUNTIME rather than under `TYPE_CHECKING`,
# and that is forced rather than chosen: they are FIELD types on the two models
# below, and pydantic resolves field annotations at class-construction time. Under
# `TYPE_CHECKING` the models build but refuse to instantiate --
# "`MovementResolution` is not fully defined" -- which is a failure that only
# appears the first time somebody constructs one.
if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date

    from analytics_query.contracts.request import AnalyticsQuery
    from analytics_query.execute import ExecutedAnswer

#: The two side labels, named as constants rather than written at the call site.
#: They reach ``DerivedFigure.derived_from``, which is part of a governed figure's
#: trace -- and a literal typed twice is a trace that can disagree with itself.
PRIMARY = "primary"
BASELINE = "baseline"

__all__ = [
    "BASELINE",
    "PRIMARY",
    "FigureExecutor",
    "MovementResolution",
    "SideFigure",
    "resolve_movement",
]


class FigureExecutor(Protocol):
    """`002`'s execution, as this feature consumes it.

    One query in, one ``ExecutedAnswer`` out, or ``ExecutionRefused``. Everything
    `002` needs to run -- ledger, adapter, sink, bundle, context -- is bound by
    the caller, because this feature owns none of it and building one here would
    be reaching around the seam rather than asking through it.
    """

    def __call__(self, request: AnalyticsQuery) -> ExecutedAnswer: ...


class SideFigure(AnomalyModel):
    """One executed side: the result and its provenance, both carried whole.

    Deliberately **not** a value plus a source string. `002` produces an
    ``AnalyticsResult`` and a ``ResultProvenance``, and narrowing them to a number
    here would be this feature deciding which parts of an upstream answer matter
    -- the decision `FR-072` reserves for the layer that produced them.
    """

    label: str = Field(min_length=1, description="Which side this is, for the figure's trace.")
    result: AnalyticsResult
    provenance: ResultProvenance

    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)


class MovementResolution(AnomalyModel):
    """What the two layers said about one rule's movement.

    **Derived or refused, never partially either**, the same shape
    ``MetricResolution`` uses: a resolution that derived carries the movement and
    both sides; one that refuses carries our code **and** the upstream word.
    """

    rule_id: GovernedName
    derived: bool
    movement: DerivedFigure | None = Field(
        default=None,
        description="`003`'s exact-decimal difference. This feature computes none of it (FR-003).",
    )
    primary: SideFigure | None = None
    baseline: SideFigure | None = None
    reason_code: AnomalyReasonCode | None = Field(
        default=None, description="Ours. Present exactly when derived is False."
    )
    upstream_code: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "The refusing layer's own reason, verbatim. Present on every refusal, because "
            "without it our carrier would assert more than it measured."
        ),
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    @property
    def provenance_is_separate(self) -> bool:
        """Whether both sides kept their own provenance (`FR-033`).

        A property rather than a validator, because on a refusal there is nothing
        to keep separate and asserting the invariant there would fail an honest
        outcome.
        """
        if self.primary is None or self.baseline is None:
            return False
        return self.primary.provenance is not self.baseline.provenance


def _single_value(result: AnalyticsResult) -> object | None:
    """The one cell a rule's figure is, or ``None`` when the shape is not one.

    A rule compares **one** number against **one** baseline. A result with no
    rows, or with more than one, is not a figure this port can hand to `003` --
    and picking the first row would be this feature deciding which of several
    numbers the rule meant.
    """
    if len(result.rows) != 1:
        return None
    cells = result.rows[0].cells
    if len(cells) != 1:
        return None
    return cells[0].value


def _execute(
    executor: FigureExecutor, request: AnalyticsQuery, label: str
) -> tuple[SideFigure | None, str | None]:
    """Run one side, or say which upstream word refused it."""
    try:
        answer = executor(request)
    except ExecutionRefused as refused:
        # `.code`, not `.reason_code`. **This line raised `AttributeError` in every refusal it
        # was written to handle**, until the strict type gate reached this package on
        # 2026-08-27: `ContractViolation` carries `code`, and `ExecutionRefused` re-exposes it
        # as `.code` for exactly this read. Nothing caught it because nothing DROVE it -- the
        # suite covered the paths where every layer answers, and never one where a layer
        # refuses, which is the branch this function exists for.
        return None, refused.code.value
    return (
        SideFigure(label=label, result=answer.result, provenance=answer.provenance),
        None,
    )


def resolve_movement(
    rule_id: str,
    *,
    formula_id: str,
    primary_request: AnalyticsQuery,
    baseline_request: AnalyticsQuery,
    execute: FigureExecutor,
    basis: str,
    on: date,
) -> MovementResolution:
    """Ask `002` for both figures and `003` for the movement between them.

    The order is the task's own and is not incidental:

    ``basis`` is **carried, never composed here.** It is the governed decision's
    chosen-because, and the caller -- which holds the decision, because
    ``catalog_port`` produced it -- passes it through. An earlier draft built it
    from an f-string with the rule id in it, and `005`'s own security node refused
    that: a value interpolated into prose is this feature writing a sentence, which
    is the one thing it must never do. The node was right and the fix is to ask the
    caller for the sentence rather than to write one.

    1. **resolve the formula** against `D-18`. A formula this feature cannot
       compute, or one declaring a quantisation or a zero-baseline rule outside
       the executable set, refuses **before** a single query is submitted -- there
       is no reason to read a warehouse for a comparison that cannot be made;
    2. **execute both sides**, each refusing on its own upstream word;
    3. **apply the governed zero-baseline rule**, before deriving anything;
    4. **derive**, in `003`.

    Step 3 before step 4 is what the task asks for. Reversed, the division has
    already happened and the only choices left are bad ones.
    """
    try:
        formula = resolve_formula(formula_id, on=on)
    except ContractViolation as violation:
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            reason_code=AnomalyReasonCode.ANOMALY_BASELINE_NOT_USABLE,
            upstream_code=violation.code.value,
        )
    except ContentUnresolvable as unresolvable:
        # `resolve_formula` raises TWO unrelated types and this branch was missing
        # from the first draft -- found by running it against the real repository
        # rather than by reading, because a fixture that supplies `instances`
        # never reaches this path.
        #
        # It is the SHIPPED state, not an edge case: `comparison-formulas.yaml`
        # has no effective instance, so NO governed formula resolves at all.
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            reason_code=AnomalyReasonCode.ANOMALY_BASELINE_NOT_USABLE,
            upstream_code=unresolvable.code.value,
        )

    primary, refused = _execute(execute, primary_request, PRIMARY)
    if primary is None:
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            reason_code=AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE,
            upstream_code=refused,
        )

    baseline, refused = _execute(execute, baseline_request, BASELINE)
    if baseline is None:
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            primary=primary,
            reason_code=AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE,
            upstream_code=refused,
        )

    primary_value = _single_value(primary.result)
    baseline_value = _single_value(baseline.result)
    if primary_value is None or baseline_value is None:
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            primary=primary,
            baseline=baseline,
            reason_code=AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE,
            upstream_code="ANOMALY_FIGURE_SHAPE_IS_NOT_ONE_VALUE",
        )

    # `003` owns the lift and refuses a float rather than converting it. Asking it
    # here rather than at derivation keeps the zero-baseline question below over an
    # exact decimal, which is the only form the governed rule is defined against.
    try:
        exact_baseline = to_exact(baseline_value)
        exact_primary = to_exact(primary_value)
    except ContractViolation as violation:
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            primary=primary,
            baseline=baseline,
            reason_code=AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE,
            upstream_code=violation.code.value,
        )

    # THE ZERO BASELINE, AND IT IS ASKED BEFORE ANYTHING IS DERIVED.
    try:
        assert_baseline_is_usable(formula, exact_baseline)
    except ContractViolation as violation:
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            primary=primary,
            baseline=baseline,
            reason_code=AnomalyReasonCode.ANOMALY_BASELINE_NOT_USABLE,
            upstream_code=violation.code.value,
        )

    try:
        movement = derive_figure(
            formula_id=formula.id,
            unit=formula.unit_rule,
            primary=exact_primary,
            baseline=exact_baseline,
            derived_from=(PRIMARY, BASELINE),
            basis=basis,
        )
    except ContractViolation as violation:
        return MovementResolution(
            rule_id=rule_id,
            derived=False,
            primary=primary,
            baseline=baseline,
            reason_code=AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE,
            upstream_code=violation.code.value,
        )

    return MovementResolution(
        rule_id=rule_id,
        derived=True,
        movement=movement,
        primary=primary,
        baseline=baseline,
    )
