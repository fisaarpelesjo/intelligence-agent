"""One function per declared component — T009 (`FR-004`).

**Each returns a value or an absence naming itself. No default, no substitution, no
zero**, and the way that is kept is that this module cannot express a default: the
only thing it builds is a `PriorityComponent`, and that contract refuses a component
carrying neither a value nor a named absence.

## `D-A` IS ANSWERED, AND THE REGISTRY NAMES HIS TWO

The owner decided on 2026-08-27: **magnitude and reach**, compared term by term with
magnitude first, each multiplied by a confidence factor. `spec.md` listed five
candidates — magnitude, reach, direction, trust, recency — and the decision keeps two of
them, moves direction to a **filter**, and drops the rest.

**Duration was offered and withdrawn, and the reason is measurable:** nothing in this
package persists a run, `FR-007` forbids originating one, so *"how many consecutive
days"* has no source to read. A component that cannot be obtained is not a component.

**Both readers answer `None` today, and the registry is still not a stub.** No mean per
metric travels the governed seams yet and `005` produces no investigation, so every
finding comes back `NotPrioritisable` with each component **naming its own absence**.
That is the same refusal the empty registry produced, reached now for a stated reason
per component instead of for the absence of a decision.

## Why a reader is a protocol and not a subclass

A component is *a name, a source entity, and a way to obtain a number*. Expressing that
as a protocol means a reader can be a function, a closure or a class, and — more
importantly — that adding one does not require touching this module's types. `D-A` will
arrive as a list of names, and each name needs exactly the three things the protocol
states.

## The one thing this module refuses to do, said plainly

It never converts a failure into a number. A reader that cannot obtain its value
returns ``None``, and this module turns that into a `ComponentAbsence` carrying a
governed code. **The conversion only runs in that direction.** There is no branch here
that turns an absence into a value, because that branch is the defect: `005` measured
`Not renewed (qty)` running 95 to 137 for 396 days and then vanishing, and a rule that
read the absence as a value reported **minus one hundred per cent** — a fall — instead
of *incomplete day*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast, runtime_checkable

from ..contracts import (
    ComponentAbsence,
    PriorityComponent,
    PriorityContractViolation,
    PriorityReasonCode,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

__all__ = [
    "DECLARED_COMPONENTS",
    "DECLARED_METHODS",
    "ComponentReader",
    "MagnitudeZScore",
    "MetricStatistics",
    "ReachOfInvestigation",
    "declared_methods",
    "read_component",
    "read_components",
]


@runtime_checkable
class ComponentReader(Protocol):
    """A name, where it is read from, and a way to obtain the number.

    ``read_from`` is part of the reader rather than of the call, because the source
    entity is a property of the component and not of the finding: *reach* is read from
    the investigation whatever finding it is about. A component whose source varied
    per call could not be checked by a reader of the output, which is `FR-002`.

    The call returns ``None`` for *"could not obtain"*. **Not zero, and not a
    sentinel number** — a number returned for a failure is the exact shape of the
    defect this feature exists to prevent, and a type that cannot carry one is a
    stronger guarantee than a rule that forbids it.
    """

    # Declared as READ-ONLY properties rather than as attributes, and the difference is not
    # cosmetic: an attribute in a protocol requires the implementation to allow ASSIGNMENT, so
    # every reader here -- all of them frozen dataclasses, deliberately -- failed to satisfy
    # its own protocol under a strict checker. A reader must EXPOSE its name and its source;
    # nothing should be able to rewrite them, least of all through this interface.
    @property
    def name(self) -> str: ...

    @property
    def read_from(self) -> str: ...

    def __call__(self, finding: object) -> Decimal | None: ...


#: The detection methods the owner's baseline declares for its SECOND level, read from
#: his document rather than copied into this one.
#:
#: **The list is derived because copying it would age.** `docs/intelligence-agent.yaml`
#: is his, `robust_statistics` there is `enabled: true` at `priority: second`, and the
#: eight methods it names are the only ones a statistic in this package may claim.
#:
#: **And not one of them is "mean" or "standard deviation".** They are `rolling_median`,
#: `median_absolute_deviation`, `robust_z_score` and their siblings -- ROBUST centre and
#: dispersion. That is why the fields below stopped being called `mean` and `deviation`.
#: The baseline this package reads, and the ONLY place its location is written.
BASELINE = Path(__file__).resolve().parents[5] / "docs" / "intelligence-agent.yaml"


def declared_methods(baseline: Path = BASELINE) -> frozenset[str]:
    """The second level's methods, **read from the document handed to it**.

    ## Why the document is a parameter

    A first version took none, and the derivation it claimed was held by nothing:
    **replacing the whole function with a correct literal copy of the eight methods left
    the package at 255 passed and not one node bit.** Every node read the same module
    constant, so none could tell a reading from a copy — and the node whose title named
    the property, `test_the_methods_are_read_from_his_baseline_and_there_are_some`, was
    precisely the one that did not measure it.

    **A parameter is what makes the derivation drivable.** Handed a different document,
    a reader answers differently; a literal answers the same to both, and the node
    notices. That is the shape `007` already uses for its recipient — *the node a correct
    literal fails* — and it is applied here rather than relearned.

    ## What a document it cannot read produces

    The EMPTY set, and every statistic then refuses to be constructed. That is the honest
    failure: a package that cannot read which methods are authorized must not accept one.
    Six levels up to the repository root, COUNTED rather than guessed -- a first draft
    stopped one short, the file was not there, and the empty set it answered then refused
    every statistic. Failing closed is the right direction for a wrong path, and it was
    still a wrong path.
    """
    import yaml

    if not baseline.is_file():  # pragma: no cover - a checkout without the baseline
        return frozenset()
    loaded: object = yaml.safe_load(baseline.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):  # pragma: no cover - a malformed baseline
        return frozenset()
    document = cast("dict[str, object]", loaded)
    levels = document.get("proactive_insights")
    if not isinstance(levels, dict):
        return frozenset()
    detection = cast("dict[str, object]", levels).get("detection_levels")
    if not isinstance(detection, dict):
        return frozenset()
    robust = cast("dict[str, object]", detection).get("robust_statistics")
    if not isinstance(robust, dict):
        return frozenset()
    methods = cast("dict[str, object]", robust).get("methods")
    if not isinstance(methods, list):
        return frozenset()
    return frozenset(str(m) for m in cast("list[object]", methods))


DECLARED_METHODS: Final[frozenset[str]] = declared_methods()


@dataclass(frozen=True, slots=True)
class MetricStatistics:
    """One metric's own normal, **and the method that produced it, named**.

    ## What this docstring used to say, and why it was false

    It said *"as `002`/`003` measured it"*, and neither seam produces this. Measured on
    2026-08-27: the word *mean* appears in those packages only in prose; `002` asks for a
    figure over a WINDOW and has no surface for a statistic over a SERIES; `003` derives
    between exactly TWO values. **Prose attributing a figure to a source without the
    capability is the class this loop hunts**, and it was sitting in the socket meant to
    receive that figure.

    ## And the classic pair is not what the baseline authorizes

    `mean` and `deviation` are the textbook pair. The owner's baseline names neither: its
    second detection level declares `rolling_median`, `median_absolute_deviation`,
    `robust_z_score` and five more -- **robust centre and dispersion**. So the fields are
    `centre` and `dispersion`, which is what they are, and each record must NAME THE
    METHOD that produced it.

    **The method is validated against his document and never invented here.** Which method
    this feature will use is a decision for the specification that builds the second level,
    not for this socket -- and until that decision exists no statistic is constructed, so
    magnitude keeps answering `None` and the finding stays not prioritisable.
    """

    centre: Decimal
    dispersion: Decimal
    #: One of the baseline's declared methods. **Never a description, never a guess.**
    method: str

    def __post_init__(self) -> None:
        """A statistic that cannot say how it was produced is a number with no provenance."""
        if not DECLARED_METHODS:
            raise PriorityContractViolation(
                "the baseline declares no detection method this package can read, so no "
                "statistic may claim one"
            )
        if self.method not in DECLARED_METHODS:
            raise PriorityContractViolation(
                f"{self.method!r} is not a method the baseline declares; the authorized ones "
                f"are {sorted(DECLARED_METHODS)}"
            )


@dataclass(frozen=True, slots=True)
class MagnitudeZScore:
    """How far outside its OWN normal a finding's figure sits — `D-B`.

    The owner decided that stock and flow order **together**, each expressed as *"how
    many deviations outside its own normal"*. So the component is a z-score per metric
    rather than a raw movement: `paid_subscribers` and `new_trials` live on scales that
    do not compare, and ordering the raw numbers together would rank by scale.

    **The cost was stated before he decided and is not a finding:** a z-score suppresses
    amplitude — two sigma on a small metric ties with two sigma on revenue.

    ``statistics`` is empty by default and the reader then answers ``None``. That is the
    honest state today: **no method has been chosen**, so no statistic can be constructed,
    so the component is **absent rather than invented**. A dispersion of zero also answers
    ``None`` — dividing by it is undefined, and a metric that never moves has no
    *"outside its normal"*.
    """

    # The factory is SUBSCRIPTED, so the empty default is an empty mapping OF A DECLARED
    # TYPE rather than one whose contents are unknown -- a bare `dict` factory makes every
    # value read out of it untyped, at every use, far from here.
    statistics: Mapping[str, MetricStatistics] = field(default_factory=dict[str, MetricStatistics])
    name: str = "magnitude"
    read_from: str = "candidate_finding"

    def __call__(self, finding: object) -> Decimal | None:
        stats = self.statistics.get(str(getattr(finding, "rule_id", "")))
        figure = getattr(getattr(finding, "figure", None), "value", None)
        if stats is None or figure is None or stats.dispersion == 0:
            return None
        return abs((Decimal(figure) - stats.centre) / stats.dispersion)


@dataclass(frozen=True, slots=True)
class ReachOfInvestigation:
    """How broadly a movement is spread — read from the investigation, never the rule.

    **The reading is a choice and it is declared here rather than left implicit:**
    reach is the **number of segments that contributed and were not suppressed**. A
    movement spread across eleven countries reaches more of the business than the same
    movement concentrated in one, and breadth is the property the word names.

    **The alternative was considered and rejected in the open:** summing the
    contributions measures how much of the movement the investigation could ATTRIBUTE,
    which is a statement about the investigation rather than about the finding — and
    `005` already reports that as its reconciliation verdict.

    ``investigations`` is empty by default, so the reader answers ``None`` and the
    component is absent. `005` produces no candidate today, so there is no investigation
    to read, and a number invented here would be the substitution this package exists
    to prevent.
    """

    investigations: Mapping[str, object] = field(default_factory=dict[str, object])
    name: str = "reach"
    read_from: str = "investigation"

    def __call__(self, finding: object) -> Decimal | None:
        investigation = self.investigations.get(str(getattr(finding, "rule_id", "")))
        contributions = getattr(investigation, "contributions", None)
        if contributions is None:
            return None
        return Decimal(sum(1 for entry in contributions if not getattr(entry, "suppressed", False)))


#: The components an ordering is made of. **`D-A` was answered on 2026-08-27 and these
#: are his two**, in the order they are compared.
#:
#: `nota = (magnitude * confidence, reach * confidence)`, compared **term by term**:
#: magnitude first, and reach only where magnitude ties. No total, no sum, no composed
#: score — `D-A` refuses one and `T014`'s tie rule already compares component by
#: component.
#:
#: **What is NOT here is as decided as what is.** Direction is a FILTER and not a
#: component: a fall and a rise do not compete inside one rule. Recency is out. Duration
#: is out too, and the reason is measurable rather than editorial — nothing in this
#: package persists a run, `FR-007` forbids originating one, so *"how many consecutive
#: days"* has no source to read.
#:
#: **Both readers answer `None` today**, and that is the honest state rather than a
#: stub: no mean per metric travels the governed seams yet, and `005` produces no
#: investigation. Every finding is therefore `NotPrioritisable` with each component
#: naming its own absence — which is what this package does instead of guessing.
DECLARED_COMPONENTS: tuple[ComponentReader, ...] = (MagnitudeZScore(), ReachOfInvestigation())


def read_component(reader: ComponentReader, finding: object) -> PriorityComponent:
    """Obtain one component, or name why it could not be obtained.

    **The absence carries a governed code and never a sentence**, so it can be counted,
    compared and refused — and so no prose about a failure is composed by this feature,
    which `FR-006` forbids on emitted fields.

    A reader that raises is **not** caught here. An exception is a defect in the reader,
    and swallowing it into `PRIORITY_COMPONENT_UNAVAILABLE` would report a broken reader
    as missing data — the two need different fixes, and a code that covers both tells
    nobody which.
    """
    value = reader(finding)
    if value is None:
        return PriorityComponent(
            name=reader.name,
            read_from=reader.read_from,
            absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
        )
    return PriorityComponent(name=reader.name, read_from=reader.read_from, value=value)


def read_components(
    finding: object, *, readers: tuple[ComponentReader, ...] = DECLARED_COMPONENTS
) -> tuple[PriorityComponent, ...]:
    """Every declared component for one finding, obtained or named absent.

    **Both kinds are returned together**, because `NotPrioritisable` carries *what was
    obtained and what was not* — a reader of the output sees the gap rather than a
    shorter list whose shortness means nothing.

    ``readers`` is injectable for the reason `003`'s governed content is: a test needs
    to exercise the machinery while the registry is legitimately empty. **No production
    path supplies it**, and the default is the declared registry, so an empty `D-A`
    cannot be worked around by a caller.
    """
    return tuple(read_component(reader, finding) for reader in readers)
