"""The answer contract — T037 (FR-032, FR-034, FR-040, FR-085; SC-007, SC-009, SC-048).

**Twelve specification elements, eleven top-level fields.** `FR-032` enumerates
twelve required elements; the contract carries them in eleven fields, three of
which are composite. The mapping is asserted element by element, and a schema
assertion fails if any of the twelve becomes unreachable (`T041`):

| Specification element | Where it lives |
|---|---|
| Interpreted question | ``interpreted`` |
| Result | ``claims[].value`` on a ``FACTUAL_RESULT`` |
| Unit | ``claims[].unit`` |
| Period | ``interpreted.period`` |
| Filters | ``interpreted.filters`` |
| Breakdowns | ``interpreted.dimensions`` |
| Comparison basis | ``claims[]`` of class ``CALCULATED_COMPARISON``, plus ``ComparisonBasis`` |
| Sources | ``provenance[].contributing_sources`` |
| Freshness | ``provenance[].source_updates[].last_updated_at`` |
| Provenance | ``provenance`` |
| Limitations | ``caveats`` |
| Insufficiency notices | ``insufficiency`` |

Freshness resolves through `002`'s public
``source_updates: tuple[SourceUpdate, ...]``, each entry carrying ``source_id``
and ``last_updated_at``. Per-source rather than a single timestamp, because a
result drawing on two sources has two freshness facts and collapsing them would
let the fresher one speak for the staler.

**Channel-agnostic** (`FR-040`): no formatting, markup, template, colour,
ordering hint or rendering instruction. A later chat or email feature renders
this contract; it does not re-derive meaning from it, and it cannot be given a
shortcut that changes what the answer says.

**Values are carried, never touched.** No arithmetic exists in this module and
none will exist in `answer/assemble.py`; ``Decimal`` is used throughout because
a binary float difference is not reproducible in its last digits across
platforms and `SC-005` requires identical output for identical input.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result_provenance import ResultProvenance
from pydantic import Field, StrictInt, model_validator
from semantic_catalog.contracts.reason_codes import ReasonCode

from ._base import InteractionModel, LocalizedRef
from .intake import DeclaredLanguage
from .intent import ResolvedIntent

__all__ = [
    "AnalyticsAnswer",
    "AnswerClaim",
    "AttributedCaveat",
    "CaveatOrigin",
    "CaveatSet",
    "ClaimClass",
    "ComparisonBasis",
    "InsufficiencyNotice",
]


class ClaimClass(StrEnum):
    """Claim classes are **types, not tags**.

    A tag on prose would make `SC-009` a text-inspection exercise; a type makes
    it a contract test, and it structurally prevents an interpretation from
    reading as a finding.

    | Class | Source | Carries a number? |
    |---|---|---|
    | ``FACTUAL_RESULT`` | Warehouse value, unaltered | Yes |
    | ``CALCULATED_COMPARISON`` | Deterministic arithmetic over results | Yes, derived |
    | ``INTERPRETATION`` | What the system understood the question to mean | **No** |
    | ``LIMITATION`` | Upstream caveat, suppression note, insufficiency notice | **No** |

    The set is fixed by this contract. `claim-classes.yaml` governs the pt-BR
    wording of each, never the membership — a fifth class is a contract change,
    not a content change.
    """

    FACTUAL_RESULT = "FACTUAL_RESULT"
    CALCULATED_COMPARISON = "CALCULATED_COMPARISON"
    INTERPRETATION = "INTERPRETATION"
    LIMITATION = "LIMITATION"


#: The two classes that may carry a number, named once so the validator below and
#: the contract tests cannot drift apart.
NUMERIC_CLAIM_CLASSES = frozenset({ClaimClass.FACTUAL_RESULT, ClaimClass.CALCULATED_COMPARISON})


class CaveatOrigin(StrEnum):
    """Which part of the answer a caveat came from.

    Attribution is one of the four structural properties that make "prominent"
    testable: a reader can tell whether a caveat applies to the verdict or to a
    specific side of a comparison.
    """

    VERDICT = "verdict"
    SIDE_A = "side_a"
    SIDE_B = "side_b"
    SINGLE = "single"


class AttributedCaveat(InteractionModel):
    """An upstream caveat, carried **byte-identical** and attributed.

    ``message_pt_br`` is the upstream text verbatim — `001`'s message registry or
    `002`'s provenance limitations — never re-worded, softened, summarised,
    truncated or downgraded (`FR-084`). It is the one string in this feature that
    is not a ``LocalizedRef``, precisely because rendering it through this
    layer's registry would *be* the re-wording the rule forbids.

    ``code`` accepts a `001` or a `002` code and **not** an
    ``InterpretationReasonCode``: a caveat by definition originates upstream. A
    caveat this layer authored would be this layer restating an upstream
    condition in its own words, which `FR-021` forbids.
    """

    code: ReasonCode | AnalyticsReasonCode
    message_pt_br: str = Field(min_length=1)
    origin: CaveatOrigin


class CaveatSet(InteractionModel):
    """Required, always populated, and **counted**.

    "Prominent" expressed as "put it near the top" would be untestable and
    unenforceable across channels a later feature will build. Expressed as
    required-populated-counted-attributed, it is a contract test (`FR-085`):

    1. **Required.** An empty set is an explicit empty collection, not an absent
       field.
    2. **Counted.** ``total`` must equal the carried count, so a consumer
       rendering a subset is *detectable* rather than merely wrong.
    3. **Origin-attributed.** See ``CaveatOrigin``.
    4. **Byte-preserved.** See ``AttributedCaveat``.

    **Never merged or deduplicated across sides.** Two sides carrying the same
    caveat is information; collapsing it would tell the reader one side is
    caveated when both are. Nothing here deduplicates, and the count makes a
    deduplication downstream visible.
    """

    caveats: tuple[AttributedCaveat, ...] = ()
    total: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _total_matches_the_carried_count(self) -> CaveatSet:
        if self.total != len(self.caveats):
            raise ValueError(
                f"caveat total {self.total} disagrees with the {len(self.caveats)} carried; "
                "an answer whose caveat set cannot be carried in full is withheld"
            )
        return self


class ComparisonBasis(InteractionModel):
    """What was compared against what, and why that window.

    Sourced from the governed comparability verdict and **never recomputed**
    (`FR-066`). Carrying ``chosen_because`` alongside the window is what lets a
    reader see that the window was governed rather than convenient.
    """

    formula: str = Field(min_length=1)
    window_start: date
    window_end: date
    chosen_because: str = Field(min_length=1)


class InsufficiencyNotice(InteractionModel):
    """A named way the data behind the answer is insufficient.

    Travels **with** the answer rather than replacing it: an incomplete period, a
    limited reproducibility, suppressed cells or narrowed coverage are facts a
    reader needs next to the number, not instead of it.

    ``detail`` is a ``LocalizedRef``, so the notice is governed wording selected
    by code — never a sentence assembled here.
    """

    kind: str = Field(min_length=1)
    detail: LocalizedRef


class AnswerClaim(InteractionModel):
    """One typed element of an answer.

    ``value`` is ``Decimal`` and never ``float``: exact decimal throughout the
    path, asserted by a type scan. ``message`` is a pointer into governed
    content, never a built string.

    ``derived_from`` records the two factual claims a ``CALCULATED_COMPARISON``
    came from, so a reader can trace a difference back to the two numbers behind
    it (`FR-035`).
    """

    claim_class: ClaimClass
    subject: str = Field(min_length=1)
    value: Decimal | None = None
    unit: str | None = None
    message: LocalizedRef
    derived_from: tuple[str, str] | None = None
    basis: ComparisonBasis | None = None

    @model_validator(mode="after")
    def _only_numeric_classes_carry_a_number(self) -> AnswerClaim:
        """``INTERPRETATION`` and ``LIMITATION`` carry no number, structurally.

        This is what stops an interpretation from reading as a finding. Without
        it the class would be a label on a model that could hold a figure
        anyway, and `SC-009` would be back to inspecting text.
        """
        if self.claim_class not in NUMERIC_CLAIM_CLASSES:
            if self.value is not None:
                raise ValueError(f"a {self.claim_class.value} claim carries no value")
            if self.unit is not None:
                raise ValueError(f"a {self.claim_class.value} claim carries no unit")
        return self

    @model_validator(mode="after")
    def _a_comparison_records_what_it_derives_from(self) -> AnswerClaim:
        """A derived figure states its two operands and its governed basis.

        ``derived_from`` and ``basis`` belong to ``CALCULATED_COMPARISON`` alone:
        a factual result derives from the warehouse, and claiming otherwise would
        make `FR-033`'s prohibition on recomputation unobservable.
        """
        is_comparison = self.claim_class is ClaimClass.CALCULATED_COMPARISON
        if is_comparison and (self.derived_from is None or self.basis is None):
            raise ValueError(
                "a calculated comparison must record the two factual claims it derives from "
                "and the basis the verdict supplied"
            )
        if not is_comparison and (self.derived_from is not None or self.basis is not None):
            raise ValueError(
                f"a {self.claim_class.value} claim derives from nothing and has no comparison basis"
            )
        return self


class AnalyticsAnswer(InteractionModel):
    """Eleven top-level fields carrying twelve required specification elements.

    ``provenance`` is a list with **one entry per side, unmerged and
    unsummarised** (`FR-072`). A merged or abbreviated provenance is never
    substituted for them, and every per-side limitation is preserved —
    incomplete provenance in any required element is an abstention, not a
    warning (`FR-037`).

    There is **no channel field**, no format, no template. See the module
    docstring.
    """

    interpreted: ResolvedIntent
    claims: tuple[AnswerClaim, ...] = Field(min_length=1)
    caveats: CaveatSet
    provenance: tuple[ResultProvenance, ...] = Field(min_length=1)
    insufficiency: tuple[InsufficiencyNotice, ...] = ()
    language: DeclaredLanguage
    reference_date: date
    as_of: date | None = None
    catalog_release: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    vocabulary_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _the_interpretation_is_disclosed_consistently(self) -> AnalyticsAnswer:
        """The answer and the intent it discloses must agree.

        ``interpreted`` is carried on every response, so a disagreement between
        the answer's declared language, dates or governing versions and the
        intent's would mean the disclosure describes a different resolution than
        the one that produced the number.
        """
        mismatched = [
            name
            for name in (
                "language",
                "reference_date",
                "as_of",
                "catalog_release",
                "policy_version",
                "vocabulary_version",
            )
            if getattr(self, name) != getattr(self.interpreted, name)
        ]
        if mismatched:
            raise ValueError(
                "the answer disagrees with the interpretation it discloses on: "
                + ", ".join(mismatched)
            )
        return self
