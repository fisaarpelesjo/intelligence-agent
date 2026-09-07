"""Metric contracts — T009 (FR-001, FR-003, FR-004; ADR 0002).

The required-field set here is a **superset** of the constitution's enumeration.
ADR 0002 records why: the constitutional list is a floor, not a ceiling, and a
cohort-grained ratio without a numerator, a denominator and an identity rule does
not describe a computable number. Nothing constitutional is relaxed.

Three structural rules carry most of the weight:

* **version blocks are contiguous and non-overlapping** — as-of resolution (T085)
  must return exactly one version for any date, or historical answers become
  ambiguous;
* **``allowed_dimensions`` is deny-by-default** — a dimension not listed is
  forbidden, not merely undocumented (FR-008);
* **``source_view`` is a reference, never dereferenced** — the object it names is
  owned by the transformation feature (research §R-2, NG-1, NG-2).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from ._base import CatalogModel, Identifier, PtBrContent, PtBrText
from .dimension import Synonym
from .retention import RetentionContract

__all__ = [
    "Additivity",
    "Aggregation",
    "AvailabilityStatus",
    "Deprecation",
    "GrainFamily",
    "Lifecycle",
    "Metric",
    "MetricContent",
    "MetricVersion",
    "SourceAvailability",
    "Unit",
    "ValueColumn",
]


class GrainFamily(StrEnum):
    """Day-grained (event date) or cohort-grained (cohort formation date).

    Mixing the two without declared weighting is refused by Gate 5 (FR-050, A-14).
    """

    DAY = "day"
    COHORT = "cohort"


class Aggregation(StrEnum):
    SUM = "sum"
    COUNT_DISTINCT = "count_distinct"
    RATIO = "ratio"
    SNAPSHOT_LAST = "snapshot_last"


class Additivity(StrEnum):
    """How a metric may legitimately be combined (FR-003)."""

    ADDITIVE = "additive"
    NON_ADDITIVE = "non_additive"
    RATIO = "ratio"
    POINT_IN_TIME = "point_in_time"


class Unit(StrEnum):
    """What one of the metric's numbers counts.

    **The five money and count members were added on 2026-08-30**, when the nineteen KPIs
    of `semantic.subscription_daily_metrics` entered the catalog. Declaring `users` for a
    figure in reais would have been false, and the enum existing in a shape that forces a
    false answer is not a reason to give one.

    ``COUNT`` is deliberately vague and that vagueness is measured: for `Sales (qty)`,
    `Cancellations (qty)`, `Not renewed (qty)` and `Chargeback (qty)` the view declares a
    count and **does not declare what is counted**. The thing counted is a named gap in
    each contract, not a guess here.
    """

    USERS = "users"
    SESSIONS = "sessions"
    EVENTS = "events"
    RATE = "rate"
    STARS = "stars"
    COUNT = "count"
    SUBSCRIPTIONS = "subscriptions"
    MONTHS = "months"
    CURRENCY_BRL = "currency_brl"
    CURRENCY_USD = "currency_usd"


class ValueColumn(StrEnum):
    """Which column of the source view carries this metric's number — `FR-806`.

    **This exists because of a published error.** MRR and Revenue were reported as having
    no value, from reading only `value`; they do have values and they live in `value_usd`.
    So the column is DECLARED per metric and read from the declaration, and above all it is
    **never defaulted to `value`** — that default is precisely what produced the error.

    The rule an author follows is ``usd_*`` -> ``value_usd``, ``brl`` -> ``value_brl``,
    everything else -> ``value``. **That rule governs the author, not this enum**: written
    into code it would be a second copy of a fact the contracts already carry, and two
    copies of one fact disagree the day one of them moves.
    """

    VALUE = "value"
    VALUE_USD = "value_usd"
    VALUE_BRL = "value_brl"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Lifecycle(StrEnum):
    """Derived, never authored (data-model §5). Only ``published`` is requestable."""

    PENDING = "pending"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class MetricContent(PtBrContent):
    label: PtBrText
    description: PtBrText
    limitations: tuple[PtBrText, ...] = ()


class MetricVersion(CatalogModel):
    """One immutable definition of a metric over an effective date range."""

    version: StrictInt = Field(ge=1)
    effective_from: date
    effective_to: date | None = Field(
        default=None,
        description="None means current. A closed version accepts Descriptive edits only.",
    )

    source_view: Identifier | str = Field(
        description="Reference to a semantic.* object owned elsewhere; never dereferenced.",
    )

    #: Which row of the source view is this metric — the view's own `kpi_name`, verbatim.
    #:
    #: **Declared rather than derived from `name`.** `mrr_usd` and `MRR (US$)` are not the
    #: same string, and a rule that turned one into the other would be a rule nobody wrote
    #: down being applied to governed content. Optional because the twelve contracts that
    #: point at views the warehouse does not hold have no row to name.
    kpi_name: PtBrText | None = None

    #: Which column carries the number — `FR-806`, and never defaulted.
    #:
    #: Optional in this model **on purpose**: a metric whose view does not exist cannot
    #: honestly declare a column. What makes it mandatory where it can be honest is a
    #: node, not a default — `daily_reporting` refuses at read time, and the guard in
    #: `008` requires it of every contract naming a KPI the view holds.
    value_column: ValueColumn | None = None
    grain: PtBrText
    aggregation: Aggregation
    additivity: Additivity
    unit: Unit
    time_dimension: Identifier
    numerator: PtBrText | None = None
    denominator: PtBrText | None = None
    calculation_basis: PtBrText
    exclusions: tuple[PtBrText, ...] = Field(
        default=(),
        description="What the number explicitly does not cover (FR-004).",
    )

    allowed_dimensions: tuple[Identifier, ...] = Field(
        default=(),
        description="Deny-by-default: anything absent is forbidden (FR-008).",
    )

    #: Which direction is GOOD for this metric — `D-1303` (`OD-113`), `FR-1307`.
    #:
    #: **It lived in the view's own column until 2026-09-04**, which meant a property of the
    #: METRIC was answered by the transformation feature's table: a metric added to the
    #: catalogue had no direction until somebody edited a view in another repository, and the
    #: report could not colour its movement. His decision moved it to where metric properties
    #: already are, so a new metric is born with its own polarity.
    #:
    #: ``None`` is a real answer and the safe one: *the direction is not declared*, and the
    #: report prints no colour rather than an opinion. That is the same rule the view's column
    #: already carried, kept rather than tightened — a metric whose direction genuinely depends
    #: on context must be able to say so.
    lower_is_better: bool | None = Field(
        default=None,
        description="True when a fall is good. None means the direction is not declared.",
    )
    content: MetricContent

    @model_validator(mode="after")
    def _ratio_needs_both_terms(self) -> MetricVersion:
        if self.aggregation is Aggregation.RATIO and not (self.numerator and self.denominator):
            raise ValueError(
                f"version {self.version} is a ratio and must declare both numerator and "
                "denominator; a ratio without an explicit denominator is not reproducible"
            )
        return self

    @model_validator(mode="after")
    def _range_ordered(self) -> MetricVersion:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError(
                f"version {self.version} ends {self.effective_to} before it starts "
                f"{self.effective_from}"
            )
        return self


class SourceAvailability(CatalogModel):
    """Where a metric may be answered — a dated decision, not a version bump (FR-052)."""

    source: Identifier
    status: AvailabilityStatus
    effective_from: date
    available_from: date | None = None
    reason_code: str | None = None
    reversible: StrictBool = False
    review_trigger: str | None = None
    #: OD-106 (2026-09-03, ciclo 542; a semantica do OD-22): a janela declarada e a DO
    #: PROPRIO source — 13 meses corridos deslizando com o rebuild diario. Num sliding,
    #: ``available_from`` vira PROVENIENCIA (a leitura feita na assinatura), nao um claim
    #: de dias: a L3 mantem a exigencia de par vivo e dispensa o predates (a data fixa
    #: contra janela que desliza SEMPRE divergiria — new_trials provou isso em 27/08); o
    #: portao de consumo continua respondendo pela janela OBSERVADA, entao nenhum dia que
    #: o source nao tem chega a um usuario por esta via.
    sliding: StrictBool = False

    @model_validator(mode="after")
    def _status_consistency(self) -> SourceAvailability:
        if self.sliding and self.status is not AvailabilityStatus.AVAILABLE:
            raise ValueError(
                f"sliding availability on {self.source!r} only makes sense while AVAILABLE"
            )
        if self.status is AvailabilityStatus.AVAILABLE:
            if self.available_from is None:
                raise ValueError(f"available source {self.source!r} must declare available_from")
            if self.reason_code is not None:
                raise ValueError(
                    f"available source {self.source!r} must not carry a refusal reason_code"
                )
        elif self.reason_code is None:
            raise ValueError(
                f"unavailable source {self.source!r} must declare a reason_code; "
                "an unexplained refusal cannot be acted on (FR-012)"
            )
        return self


class Deprecation(CatalogModel):
    """Adds a boundary; never mutates or deletes a historical definition (FR-061)."""

    deprecated_from: date
    successor: Identifier | None = None
    replacement_metric_id: Identifier | None = None
    content: PtBrContent | None = None


class Metric(CatalogModel):
    """``semantic/metrics/{name}.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["metric"]

    name: Identifier
    owner: Identifier
    access: Identifier = Field(description="Access tag; gates published metrics and pending stubs.")
    grain_family: GrainFamily

    versions: tuple[MetricVersion, ...] = Field(min_length=1)
    source_availability: tuple[SourceAvailability, ...] = ()
    synonyms: tuple[Synonym, ...] = ()
    deprecation: Deprecation | None = None
    retention: RetentionContract | None = None

    @model_validator(mode="after")
    def _retention_iff_cohort_grained(self) -> Metric:
        if self.grain_family is GrainFamily.COHORT and self.retention is None:
            raise ValueError(
                f"cohort-grained metric {self.name!r} must declare a retention contract"
            )
        if self.grain_family is GrainFamily.DAY and self.retention is not None:
            raise ValueError(
                f"day-grained metric {self.name!r} must not declare a retention contract"
            )
        return self

    @model_validator(mode="after")
    def _versions_contiguous_and_unique(self) -> Metric:
        ordered = sorted(self.versions, key=lambda v: v.effective_from)
        numbers = [v.version for v in ordered]
        if len(set(numbers)) != len(numbers):
            raise ValueError(f"metric {self.name!r} has duplicate version numbers {numbers}")
        if numbers != sorted(numbers):
            raise ValueError(
                f"metric {self.name!r} version numbers {numbers} do not increase with "
                "effective_from"
            )
        for earlier, later in pairwise(ordered):
            if earlier.effective_to is None:
                raise ValueError(
                    f"metric {self.name!r} version {earlier.version} is open but is followed by "
                    f"version {later.version}; only the newest version may be open"
                )
            if later.effective_from <= earlier.effective_to:
                raise ValueError(
                    f"metric {self.name!r} versions {earlier.version} and {later.version} overlap"
                )
        return self

    @model_validator(mode="after")
    def _unique_source_availability(self) -> Metric:
        seen: set[tuple[str, date]] = set()
        for entry in self.source_availability:
            key = (entry.source, entry.effective_from)
            if key in seen:
                raise ValueError(
                    f"metric {self.name!r} declares two availability decisions for "
                    f"{entry.source!r} effective {entry.effective_from}"
                )
            seen.add(key)
        return self

    def unset_required_fields(self) -> tuple[str, ...]:
        """Required fields still unset — names only, never draft values (FR-018)."""
        if self.retention is None:
            return ()
        return tuple(f"retention.{name}" for name in self.retention.unset_required_fields())
