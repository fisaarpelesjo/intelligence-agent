"""Governed-content validation — T034 (FR-025, FR-095; SC-035).

`FR-095` is this module's because it requires the claim prohibition to be verified by the
**same automated content scan** that guards audit content, rather than by a separate
review step. This module is that scan's production half; `tests/contract/` holds the
assertions that run it.

Backs the read-only ``interaction validate-governance`` steward command (wired in
Phase 14). Validates the *shape and coherence* of everything under
`interpretation_governance/` and reports violations; it approves nothing, writes
nothing and never marks a dependency ready.

**Zero violations against the empty governed files is the expected result.** An
empty document is valid content — it is the designed state while `D-18` and
`D-19` are open. This tool answers "is the authored content well-formed", not
"is there enough of it to answer a question"; the second question is
`governance/resolve.py`'s, and its answer today is a refusal.

Two rules here are not shape checks and are worth naming:

* **No causal wording.** Constitution II forbids causal claims, and the wording
  is authored data, so it can be checked at build time by a denylist scan rather
  than by review (`answer-contract.md` §8).
* **No overlapping effectivity.** Two instances effective on the same day makes
  resolution ambiguous *later*, at the moment a user asks a question. Catching it
  when the content is authored turns a runtime refusal into a review comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..governance.policy import INTERPRETATION_POLICY_FILE, load_policies
from ..governance.schemas import GovernedContent, governed_content_root
from ..governance.vocabulary import (
    CLAIM_CLASSES_FILE,
    COMPARISON_FORMULAS_FILE,
    PERIOD_VOCABULARY_FILE,
    load_claim_classes,
    load_comparison_formulas,
    load_period_vocabulary,
)
from ..messages.registry import load_registry

__all__ = ["ContentViolation", "validate_governance"]

#: pt-BR causal connectives. Correlation, temporal association and hypothesis are
#: permitted; asserting that one thing *caused* another is not (`FR-036`).
_CAUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcaus(a|ou|ado|ada|am|aram)\b", re.IGNORECASE),
    re.compile(r"\bprovoc(a|ou|ado|ada|am|aram)\b", re.IGNORECASE),
    re.compile(r"\bpor causa d", re.IGNORECASE),
    re.compile(r"\bdevido a\b", re.IGNORECASE),
    re.compile(r"\bresult(a|ou|ante) d", re.IGNORECASE),
)


@dataclass(frozen=True)
class ContentViolation:
    """One problem with authored governed content."""

    document: str
    detail: str

    def __str__(self) -> str:
        return f"{self.document}: {self.detail}"


def _overlaps(instances: tuple[GovernedContent, ...], document: str) -> list[ContentViolation]:
    """Any two instances effective on the same day.

    Compared at the window endpoints rather than by sampling every date: an
    overlap, if one exists, necessarily includes the later instance's
    ``effective_from`` or the earlier one's ``effective_to``.
    """
    violations: list[ContentViolation] = []
    for index, first in enumerate(instances):
        for second in instances[index + 1 :]:
            probes = [first.effective_from, second.effective_from]
            probes += [d for d in (first.effective_to, second.effective_to) if d is not None]
            if any(first.is_effective_on(p) and second.is_effective_on(p) for p in probes):
                violations.append(
                    ContentViolation(
                        document,
                        f"versions {first.version!r} and {second.version!r} are effective "
                        "on the same day; resolution would be ambiguous",
                    )
                )
    return violations


def _approval_is_dated_sanely(
    instances: tuple[GovernedContent, ...], document: str
) -> list[ContentViolation]:
    """Approval must not postdate the day the content took effect.

    Content in force before anyone approved it is content that was never
    governed, whatever the file says.
    """
    return [
        ContentViolation(
            document,
            f"version {instance.version!r} took effect on {instance.effective_from} "
            f"but was approved on {instance.approval.approved_on}",
        )
        for instance in instances
        if instance.approval.approved_on > instance.effective_from
    ]


def _no_causal_wording(text: str, document: str, where: str) -> list[ContentViolation]:
    return [
        ContentViolation(document, f"{where} asserts causation: {pattern.pattern!r}")
        for pattern in _CAUSAL_PATTERNS
        if pattern.search(text)
    ]


def validate_governance() -> list[ContentViolation]:
    """Every violation found under `interpretation_governance/`, in document order.

    An empty list means the authored content is well-formed. It does **not** mean
    a question can be answered — see the module docstring.
    """
    violations: list[ContentViolation] = []
    root = governed_content_root()
    if not root.is_dir():  # pragma: no cover - the locator raises first
        return [ContentViolation("interpretation_governance", "directory is missing")]

    periods = load_period_vocabulary()
    formulas = load_comparison_formulas()
    classes = load_claim_classes()
    policies = load_policies()

    documents: tuple[tuple[str, tuple[GovernedContent, ...]], ...] = (
        (PERIOD_VOCABULARY_FILE, periods),
        (COMPARISON_FORMULAS_FILE, formulas),
        (CLAIM_CLASSES_FILE, classes),
        (INTERPRETATION_POLICY_FILE, policies),
    )
    for name, instances in documents:
        violations.extend(_overlaps(instances, name))
        violations.extend(_approval_is_dated_sanely(instances, name))

    for vocabulary in periods:
        for expression in vocabulary.expressions:
            for surface in expression.surface_forms:
                violations.extend(
                    _no_causal_wording(surface, PERIOD_VOCABULARY_FILE, expression.id)
                )

    for wording_set in classes:
        for wording in wording_set.classes:
            for field, text in (("label", wording.label), ("disclosure", wording.disclosure)):
                violations.extend(
                    _no_causal_wording(
                        text, CLAIM_CLASSES_FILE, f"{wording.claim_class.value}.{field}"
                    )
                )

    registry = load_registry()
    for code in sorted(registry.codes, key=lambda c: c.value):
        violations.extend(
            _no_causal_wording(registry.text_for(code), "messages/pt-br.yaml", code.value)
        )

    return violations
