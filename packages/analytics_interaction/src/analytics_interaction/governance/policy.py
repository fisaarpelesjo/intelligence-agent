"""`D-19` interpretation policy loader — T033 (FR-025; SC-035).

One document, one code: ``INTERPRETATION_POLICY_UNRESOLVABLE`` covers the
ambiguity threshold, the round bound, the expiry, the length bound, the redaction
rule and the cross-question disclosure rule. Deliberately one, so **no
configuration can run with some of them and not others** — the same
single-failure-mode design `002` used for `D-14` and `D-16`.

The six are enforced twice, for different failure modes. ``InterpretationPolicy``
requires them at construction, so a partially authored policy is not
representable. ``resolve_policy`` re-checks them, so a policy that reached
resolution without passing through the contract is caught — which would mean the
policy in force is not the policy that was approved.

`interpretation-policy.yaml` holds no approved instance, so resolution refuses
every dependent path today: no question can be judged ambiguous, no clarification
contract can be issued, the governed length bound cannot be applied or named, and
**screening cannot run**, so the question refuses (spec `C-4`).

Nothing here supplies a threshold, a bound, an expiry or a rule. The refusal
messages name none of them either: an unresolvable policy must not disclose the
policy by way of the message that says it is missing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import yaml

from ..contracts._base import ContractViolation, build
from ..contracts.reason_codes import InterpretationReasonCode
from .resolve import ContentUnresolvable, resolve_effective
from .schemas import (
    POLICY_REQUIRED_FIELDS,
    ContentApproval,
    DisclosureRule,
    InterpretationPolicy,
    RedactionRule,
    governed_content_root,
)

__all__ = [
    "INTERPRETATION_POLICY_FILE",
    "POLICY_CODE",
    "load_policies",
    "refusal_for",
    "resolve_policy",
]

INTERPRETATION_POLICY_FILE = "interpretation-policy.yaml"

POLICY_CODE = InterpretationReasonCode.INTERPRETATION_POLICY_UNRESOLVABLE


def load_policies(path: Path | None = None) -> tuple[InterpretationPolicy, ...]:
    """Parse every authored policy instance.

    A malformed document raises rather than yielding an empty tuple — "no
    policies" and "the policy file is broken" must not look the same, because the
    first is a designed state and the second is a defect.
    """
    target = path or governed_content_root() / INTERPRETATION_POLICY_FILE
    raw: object = yaml.safe_load(target.read_text(encoding="utf-8"))
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ValueError(f"{target.name}: expected a mapping at the document root")
    document = cast("dict[str, object]", raw)

    entries: object = document.get("instances", [])
    if entries is None:
        return ()
    if not isinstance(entries, list):
        raise ValueError(f"{target.name}: `instances` must be a list")

    policies: list[InterpretationPolicy] = []
    for raw_entry in cast("list[object]", entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"{target.name}: each policy instance must be a mapping")
        entry = dict(cast("dict[str, object]", raw_entry))

        raw_approval = entry.pop("approval", None)
        if not isinstance(raw_approval, dict):
            raise ValueError(f"{target.name}: each policy needs an `approval` mapping")
        approval = build(ContentApproval, **cast("dict[str, object]", raw_approval))

        raw_redaction = entry.pop("redaction_rule", None)
        if not isinstance(raw_redaction, dict):
            raise ValueError(f"{target.name}: each policy needs a `redaction_rule` mapping")
        redaction = build(RedactionRule, **cast("dict[str, object]", raw_redaction))

        raw_disclosure = entry.pop("cross_question_disclosure", None)
        if not isinstance(raw_disclosure, dict):
            raise ValueError(
                f"{target.name}: each policy needs a `cross_question_disclosure` mapping"
            )
        disclosure = build(DisclosureRule, **cast("dict[str, object]", raw_disclosure))

        policies.append(
            build(
                InterpretationPolicy,
                approval=approval,
                redaction_rule=redaction,
                cross_question_disclosure=disclosure,
                **entry,
            )
        )
    return tuple(policies)


def resolve_policy(
    on: date, *, policies: tuple[InterpretationPolicy, ...] | None = None
) -> InterpretationPolicy:
    """The single complete policy effective on ``on``, or refuse.

    ``policies`` is injectable for tests only; production resolves from governed
    content. It is not a *runtime* switch — no flag or environment setting
    reaches it, and the fixture-containment scan asserts no `src/` module
    supplies one.
    """
    candidates = load_policies() if policies is None else policies
    return resolve_effective(
        candidates,
        on=on,
        code=POLICY_CODE,
        required=POLICY_REQUIRED_FIELDS,
        kind="interpretation policy",
    )


def refusal_for(exc: ContentUnresolvable) -> ContractViolation:
    """Express unresolvable governed content as a governed refusal.

    The message names no threshold, bound, expiry or rule. A principal refused by
    a policy must learn nothing about the policy from being refused by it — the
    same non-disclosure `002` applies to its query limits.
    """
    return ContractViolation(exc.code, "the governed interpretation content is unresolvable")
