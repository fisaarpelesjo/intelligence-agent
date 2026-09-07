"""`D-18` vocabulary loaders — T032 (FR-010, FR-071; SC-018).

Loads and resolves the three `D-18` documents: the period vocabulary, the
comparison formula set and the claim-class wording. Each resolves separately —
they are separately versioned instances of separately authored content — but all
three refuse with the **same** code, ``INTERPRETATION_VOCABULARY_UNRESOLVABLE``,
because all three are `D-18` and a caller learns nothing useful from knowing
which of the three files was the problem.

**All three ship with zero approved instances**, so every dependent path refuses:
every question carrying a relative or named period, every comparison, and every
answer assembly. That is the designed state while `D-18` is open.

A malformed document **raises** rather than resolving to empty. "No approved
content" and "the content file is broken" must not look the same: the first is a
governed state and the second is a defect, and collapsing them would let a
YAML typo read as a governance decision.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import yaml

from ..contracts._base import InteractionModel, build
from ..contracts.reason_codes import InterpretationReasonCode
from .resolve import ContentUnresolvable, resolve_effective
from .schemas import (
    ClaimClassContent,
    ClaimClassWording,
    ComparisonFormula,
    ComparisonFormulas,
    ContentApproval,
    GovernedContent,
    PeriodExpression,
    PeriodVocabulary,
    governed_content_root,
)

__all__ = [
    "CLAIM_CLASSES_FILE",
    "COMPARISON_FORMULAS_FILE",
    "PERIOD_VOCABULARY_FILE",
    "VOCABULARY_CODE",
    "load_claim_classes",
    "load_comparison_formulas",
    "load_period_vocabulary",
    "resolve_claim_classes",
    "resolve_comparison_formulas",
    "resolve_period_vocabulary",
]

PERIOD_VOCABULARY_FILE = "period-vocabulary.yaml"
COMPARISON_FORMULAS_FILE = "comparison-formulas.yaml"
CLAIM_CLASSES_FILE = "claim-classes.yaml"

#: One code for all three `D-18` documents. See the module docstring.
VOCABULARY_CODE = InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE


def _read_document(path: Path) -> dict[str, object]:
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected a mapping at the document root")
    return cast("dict[str, object]", raw)


def _entries(document: dict[str, object], key: str, path: Path) -> list[dict[str, object]]:
    value: object = document.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{path.name}: `{key}` must be a list")
    entries: list[dict[str, object]] = []
    for item in cast("list[object]", value):
        if not isinstance(item, dict):
            raise ValueError(f"{path.name}: each entry under `{key}` must be a mapping")
        entries.append(cast("dict[str, object]", item))
    return entries


def _instances[C: GovernedContent, M: InteractionModel](
    model: type[C], path: Path, *, collection: str, member: type[M]
) -> tuple[C, ...]:
    """Parse every authored instance of one governed document.

    An authored document holds a list of *instances* — one per version — so a
    replacement can be authored with a future ``effective_from`` and reviewed
    before it takes effect. An empty list is a document with no approved
    instance, which is exactly the state all four files ship in.
    """
    document = _read_document(path)
    instances: list[C] = []
    for raw_instance in _entries(document, "instances", path):
        entry = dict(raw_instance)
        raw_approval = entry.pop("approval", None)
        if not isinstance(raw_approval, dict):
            raise ValueError(f"{path.name}: each instance needs an `approval` mapping")
        approval = build(ContentApproval, **cast("dict[str, object]", raw_approval))
        raw_members: object = entry.pop(collection, [])
        if raw_members is None:
            raw_members = []
        if not isinstance(raw_members, list):
            raise ValueError(f"{path.name}: `{collection}` must be a list")
        members: tuple[M, ...] = tuple(
            build(member, **cast("dict[str, object]", item))
            for item in cast("list[object]", raw_members)
        )
        instances.append(build(model, approval=approval, **{collection: members}, **entry))
    return tuple(instances)


def load_period_vocabulary(path: Path | None = None) -> tuple[PeriodVocabulary, ...]:
    """Every authored period-vocabulary instance. Empty today, by design."""
    target = path or governed_content_root() / PERIOD_VOCABULARY_FILE
    return _instances(PeriodVocabulary, target, collection="expressions", member=PeriodExpression)


def load_comparison_formulas(path: Path | None = None) -> tuple[ComparisonFormulas, ...]:
    """Every authored comparison-formula instance. Empty today, by design."""
    target = path or governed_content_root() / COMPARISON_FORMULAS_FILE
    return _instances(ComparisonFormulas, target, collection="formulas", member=ComparisonFormula)


def load_claim_classes(path: Path | None = None) -> tuple[ClaimClassContent, ...]:
    """Every authored claim-class wording instance. Empty today, by design."""
    target = path or governed_content_root() / CLAIM_CLASSES_FILE
    return _instances(ClaimClassContent, target, collection="classes", member=ClaimClassWording)


def resolve_period_vocabulary(
    on: date, *, instances: tuple[PeriodVocabulary, ...] | None = None
) -> PeriodVocabulary:
    """The vocabulary in force on ``on``, or refuse.

    ``expressions`` is required non-empty: a vocabulary declaring no expression
    cannot resolve the period a caller asked about, and returning it would push
    the refusal to a caller that might read empty as "no restriction".

    ``instances`` is injectable for tests only. It is not a *runtime* switch —
    nothing reads a flag or an environment setting to reach it, and the
    fixture-containment scan asserts no `src/` module supplies one.
    """
    candidates = load_period_vocabulary() if instances is None else instances
    return resolve_effective(
        candidates,
        on=on,
        code=VOCABULARY_CODE,
        required=("expressions",),
        kind="period vocabulary",
    )


def resolve_comparison_formulas(
    on: date, *, instances: tuple[ComparisonFormulas, ...] | None = None
) -> ComparisonFormulas:
    """The formula set in force on ``on``, or refuse.

    The set is closed, so an empty set means **every comparison refuses** rather
    than every comparison being unconstrained. Requiring ``formulas`` non-empty
    is what makes that direction the one the code takes.
    """
    candidates = load_comparison_formulas() if instances is None else instances
    return resolve_effective(
        candidates,
        on=on,
        code=VOCABULARY_CODE,
        required=("formulas",),
        kind="comparison formula set",
    )


def resolve_claim_classes(
    on: date, *, instances: tuple[ClaimClassContent, ...] | None = None
) -> ClaimClassContent:
    """The claim-class wording in force on ``on``, or refuse.

    Non-empty is necessary but not sufficient: every contract-declared class must
    have wording, because an answer carrying an unworded class would have a claim
    nobody could read. ``ClaimClassContent.is_complete`` decides that, and the
    refusal is the same governed code.
    """
    candidates = load_claim_classes() if instances is None else instances
    resolved = resolve_effective(
        candidates,
        on=on,
        code=VOCABULARY_CODE,
        required=("classes",),
        kind="claim-class wording",
    )
    if not resolved.is_complete():
        raise ContentUnresolvable(
            VOCABULARY_CODE,
            "the effective claim-class wording does not cover every contract-declared class",
        )
    return resolved
