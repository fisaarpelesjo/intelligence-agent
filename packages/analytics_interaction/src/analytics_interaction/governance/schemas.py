"""Schemas for the governed interpretation content — T027-T030.

`D-18` (period vocabulary, comparison formulas, claim-class wording) and `D-19`
(interpretation policy). Mirrors `contracts/governed-content.md`, whose opening
line is the rule this module obeys:

    **This contract defines schemas and declares zero values.**

Every instance ships empty and unapproved, exactly as
`query_governance/query-policy.yaml` holds no approved instance today. Inventing
a week convention, a rounding rule, an ambiguity threshold or a redaction pattern
here would be inventing the governed decision the dependency exists to obtain.

So: shapes, required-field rules and effectivity arithmetic live here. Not one
expression, formula, threshold, bound, expiry or rule does.

``StrictInt`` throughout the policy: a bound silently coerced from a float or a
string is a bound nobody chose, and these govern how long a question may be, how
many clarification rounds it gets and how long a sealed contract lives.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import Field, StrictInt, model_validator

from ..contracts._base import InteractionModel
from ..contracts.answer import ClaimClass

__all__ = [
    "POLICY_REQUIRED_FIELDS",
    "ClaimClassContent",
    "ClaimClassWording",
    "ComparisonFormula",
    "ComparisonFormulas",
    "ContentApproval",
    "DisclosureRule",
    "GovernedContent",
    "InterpretationPolicy",
    "PeriodExpression",
    "PeriodVocabulary",
    "RedactionRule",
    "governed_content_root",
]


def governed_content_root() -> Path:
    """``interpretation_governance/``, located by walking up.

    Located rather than configured, for the reason `002` records: a settable
    path would be a runtime switch over governed content, and a runtime switch
    over governed content is an ungoverned override.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "interpretation_governance"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("interpretation_governance/ not found above " + str(here))


class ContentApproval(InteractionModel):
    """Who approved a governed content instance. A role, never an individual.

    Naming a person orphans the approval path the moment they leave — the rule
    `001` applies to every approver and `002` repeated for its query policy
    (ADR 0003).
    """

    approver_role: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    approved_on: date


class GovernedContent(InteractionModel):
    """Shared effectivity envelope for every governed content document.

    Effectivity is here rather than repeated in four places because "exactly one
    effective instance" is resolved by one function over all four
    (`resolve.py`), and a per-document interpretation of *effective* would let
    that function silently mean different things for different content.
    """

    version: str = Field(min_length=1)
    effective_from: date
    effective_to: date | None = None
    approval: ContentApproval

    @model_validator(mode="after")
    def _window_is_ordered(self) -> GovernedContent:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        return self

    def is_effective_on(self, on: date) -> bool:
        """Whether this instance is in force on ``on``. Both bounds inclusive."""
        if on < self.effective_from:
            return False
        return self.effective_to is None or on <= self.effective_to


# --- T027: period-vocabulary.yaml (D-18) -------------------------------------


class PeriodExpression(InteractionModel):
    """One governed period expression.

    ``id`` is English and ``surface_forms`` are pt-BR, unchanged from `001`'s
    `FR-053` / `FR-054`: identifiers are the stable machine-facing name, surfaces
    are what a person actually types.

    **The conditional fields are the point.** A week-relative boundary rule with
    no ``week_start`` does not resolve — it refuses
    ``PERIOD_CONVENTION_UNDECLARED`` rather than assuming Sunday or Monday.
    Whether "semana passada" starts on a Sunday or a Monday changes every weekly
    number in the product, and nothing in this repository declares it. A library
    picking one would be a library deciding a reporting standard.
    """

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    surface_forms: tuple[str, ...] = Field(min_length=1)
    boundary_rule: str = Field(min_length=1)
    inclusivity: str = Field(min_length=1)
    week_start: str | None = None
    month_rule: str | None = None

    @model_validator(mode="after")
    def _convention_is_complete(self) -> PeriodExpression:
        """A relative rule without its convention is undeclared, not defaulted.

        The rule vocabulary itself is `D-18` content, so this cannot enumerate
        which rules are week-relative. It keys off the substring the authored
        rule name carries, which is checkable without knowing the closed set.
        """
        rule = self.boundary_rule.lower()
        if "week" in rule and self.week_start is None:
            raise ValueError(
                f"boundary_rule {self.boundary_rule!r} is week-relative but declares no week_start"
            )
        if "month" in rule and self.month_rule is None:
            raise ValueError(
                f"boundary_rule {self.boundary_rule!r} is month-relative but declares no month_rule"
            )
        return self


class PeriodVocabulary(GovernedContent):
    """`D-18`. **Ships with zero expressions, by design.**

    While ``expressions`` is empty every question carrying a relative or named
    period refuses ``PERIOD_EXPRESSION_NOT_GOVERNED``. Absence is refusal, never
    approximation to the nearest listed entry (`FR-010`).
    """

    expressions: tuple[PeriodExpression, ...] = ()

    @model_validator(mode="after")
    def _expression_ids_are_unique(self) -> PeriodVocabulary:
        ids = [expression.id for expression in self.expressions]
        if len(set(ids)) != len(ids):
            raise ValueError("period expression ids must be unique within a vocabulary")
        return self


# --- T028: comparison-formulas.yaml (D-18) -----------------------------------


class ComparisonFormula(InteractionModel):
    """One governed comparison formula.

    ``unit_rule``, ``zero_baseline`` and ``quantisation`` are **required to be
    declared, never chosen here**. This feature applies no presentation rounding
    of its own: inventing one would silently decide how every percentage in the
    product reads (`R-12`). ``quantisation`` is optional because *no governed
    rounding* is a legitimate governed decision; ``unit_rule`` and
    ``zero_baseline`` are not, because every formula has some behaviour at a zero
    baseline and something has to say which.
    """

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    surface_forms: tuple[str, ...] = Field(min_length=1)
    unit_rule: str = Field(min_length=1)
    zero_baseline: str = Field(min_length=1)
    quantisation: str | None = None


class ComparisonFormulas(GovernedContent):
    """`D-18`. **Ships with zero formulas, by design.**

    The set is closed: a question implying a formula outside it refuses rather
    than being approximated by one inside it (`FR-071`). Empty therefore means
    every comparison refuses.
    """

    formulas: tuple[ComparisonFormula, ...] = ()

    @model_validator(mode="after")
    def _formula_ids_are_unique(self) -> ComparisonFormulas:
        ids = [formula.id for formula in self.formulas]
        if len(set(ids)) != len(ids):
            raise ValueError("comparison formula ids must be unique within a formula set")
        return self


# --- T029: claim-classes.yaml (D-18) -----------------------------------------


class ClaimClassWording(InteractionModel):
    """Governed pt-BR wording for one claim class.

    The class itself is a contract type, not content — see below.
    """

    claim_class: ClaimClass
    label: str = Field(min_length=1)
    disclosure: str = Field(min_length=1)


class ClaimClassContent(GovernedContent):
    """`D-18`. **The four classes are fixed by contract; only wording is content.**

    ``ClaimClass`` is imported from `contracts/answer.py` rather than re-declared
    as a string, so a fifth class is a **contract change, not a content change**.
    That asymmetry is deliberate: the typed class set is what makes `SC-009` a
    contract assertion instead of a text-inspection exercise, and authored YAML
    must not be able to widen it.

    Ships with zero wordings, so answer assembly refuses.
    """

    classes: tuple[ClaimClassWording, ...] = ()

    @model_validator(mode="after")
    def _each_class_appears_at_most_once(self) -> ClaimClassContent:
        declared = [wording.claim_class for wording in self.classes]
        if len(set(declared)) != len(declared):
            raise ValueError("each claim class may be worded at most once per content version")
        return self

    def is_complete(self) -> bool:
        """Whether every contract-declared class has governed wording.

        Not a validator: a partially worded instance is representable so that
        `resolve.py` can refuse it with the governed code rather than raising a
        parse error. "The file is broken" and "the content is incomplete" are
        different facts and must not look the same.
        """
        return {wording.claim_class for wording in self.classes} == set(ClaimClass)


# --- T030: interpretation-policy.yaml (D-19) ---------------------------------


class RedactionRule(InteractionModel):
    """Constitution IV's redaction half — **declared by `D-19`, not by this code**.

    Nothing in this repository states what must be stripped from a business
    question before it may reach a prompt. The shape is here; the patterns are
    not, and while none is declared the screening step cannot run, so the
    question refuses (spec `C-4`).

    ``patterns`` is a tuple of governed pattern identifiers, not regular
    expressions authored here. A regex written in this module would be a
    privacy rule nobody reviewed.
    """

    rule_id: str = Field(min_length=1)
    patterns: tuple[str, ...] = Field(min_length=1)
    on_match: str = Field(min_length=1)


class DisclosureRule(InteractionModel):
    """The cross-question disclosure rule — `D-19`.

    Governs whether a sequence of questions by one principal could reconstruct a
    suppressed figure. Absent it, any question needing that judgement refuses.
    """

    rule_id: str = Field(min_length=1)
    window_questions: StrictInt = Field(gt=0)
    on_reconstruction_risk: str = Field(min_length=1)


class InterpretationPolicy(GovernedContent):
    """`D-19`. **All six fields required together.**

    A policy carrying bounds but no redaction rule does not resolve — it is not
    partially usable. Pydantic enforces that at construction, which is what makes
    the single-failure-mode design real: there is no representable configuration
    in which the system runs with ambiguity controls but no untrusted-text
    screening, or the reverse. Same design `002` used for `D-14` and `D-16`.

    ``ambiguity_threshold`` is the count of governed candidates at or above which
    clarification becomes mandatory. Typed as an integer because the quantity it
    bounds is a candidate count, not a score — but its **value** is `D-19`
    content and no default exists.

    `interpretation-policy.yaml` holds no instance, so every question needing any
    of these six refuses ``INTERPRETATION_POLICY_UNRESOLVABLE``.
    """

    ambiguity_threshold: StrictInt = Field(gt=0)
    clarification_round_bound: StrictInt = Field(gt=0)
    clarification_expiry_seconds: StrictInt = Field(gt=0)
    question_length_bound: StrictInt = Field(gt=0)
    redaction_rule: RedactionRule
    cross_question_disclosure: DisclosureRule


#: The six field names `D-19` requires jointly. Named once, so the resolver's
#: completeness re-check and the tests cannot drift from the contract.
POLICY_REQUIRED_FIELDS: tuple[str, ...] = (
    "ambiguity_threshold",
    "clarification_round_bound",
    "clarification_expiry_seconds",
    "question_length_bound",
    "redaction_rule",
    "cross_question_disclosure",
)
