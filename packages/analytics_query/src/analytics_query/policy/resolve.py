"""Governed policy resolution — T060 (FR-048, FR-049, FR-069, FR-070, FR-071; SC-027).

Three ways to be unresolvable, one outcome. Zero effective policies, more than
one, or one that is incomplete — each refuses with ``QUERY_POLICY_UNRESOLVABLE``.

**Nothing is ever substituted.** Not a default, not an inferred value, not a
value seen on a previous request. The minimum-aggregation threshold is external
evidence supplied by the data owner (`D-16`), and its absence is a refusal rather
than a fallback (`FR-071`) — a privacy floor this feature invented would be a
number nobody approved, applied to real people.

Because `QueryPolicy` requires all five limits jointly at construction, "cost
limits present but privacy floor missing" is not a partially usable state. It is
simply not a policy.

**Today `query_governance/query-policy.yaml` holds no approved instance**, so
resolution refuses every request. That is the designed state while `D-14` and
`D-16` are open, not a gap.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import yaml

from ..contracts._base import ContractViolation, build
from ..contracts.policy import PolicyApproval, QueryPolicy
from ..contracts.reason_codes import AnalyticsReasonCode

__all__ = ["PolicyUnresolvable", "load_policies", "policy_path", "resolve_policy"]


class PolicyUnresolvable(RuntimeError):  # noqa: N818 - named for its reason code
    """No single complete governed policy is in force."""

    def __init__(self, detail: str) -> None:
        self.code = AnalyticsReasonCode.QUERY_POLICY_UNRESOLVABLE
        self.detail = detail
        super().__init__(f"{self.code.value}: {detail}")


def policy_path() -> Path:
    """``query_governance/query-policy.yaml``, located by walking up.

    Located rather than configured: a settable path would be a runtime switch
    over governed content.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "query_governance" / "query-policy.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("query_governance/query-policy.yaml not found above " + str(here))


def load_policies(path: Path | None = None) -> tuple[QueryPolicy, ...]:
    """Parse every authored policy.

    A malformed document raises rather than yielding an empty list — "no
    policies" and "the policy file is broken" must not look the same, because
    the first is a designed state and the second is a defect.
    """
    document_path = path or policy_path()
    raw: object = yaml.safe_load(document_path.read_text(encoding="utf-8"))
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ValueError(f"{document_path.name}: expected a mapping at the document root")
    document = cast("dict[str, object]", raw)

    entries: object = document.get("policies", [])
    if not isinstance(entries, list):
        raise ValueError(f"{document_path.name}: `policies` must be a list")

    policies: list[QueryPolicy] = []
    for raw_entry in cast("list[object]", entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"{document_path.name}: each policy must be a mapping")
        entry = dict(cast("dict[str, object]", raw_entry))
        raw_approval = entry.pop("approval", None)
        if not isinstance(raw_approval, dict):
            raise ValueError(f"{document_path.name}: each policy needs an `approval` mapping")
        approval = build(PolicyApproval, **cast("dict[str, object]", raw_approval))
        policies.append(build(QueryPolicy, approval=approval, **entry))
    return tuple(policies)


def resolve_policy(on: date, *, policies: tuple[QueryPolicy, ...] | None = None) -> QueryPolicy:
    """The single policy effective on ``on``, or refuse.

    ``policies`` is injectable for tests only; production resolves from governed
    content. Note it is not a *runtime* switch — there is no flag or environment
    setting that reaches it, and the fixture-containment scan asserts no `src/`
    module supplies one.
    """
    candidates = load_policies() if policies is None else policies
    effective = [p for p in candidates if p.is_effective_on(on)]

    if not effective:
        raise PolicyUnresolvable(
            "no approved query-limit policy is in force; no default is substituted"
        )
    if len(effective) > 1:
        # Two effective policies means two different sets of limits are
        # simultaneously authoritative. Picking one would be picking arbitrarily.
        raise PolicyUnresolvable(
            "more than one governed policy is effective; the governed limits are ambiguous"
        )

    policy = effective[0]
    _assert_complete(policy)
    return policy


def _assert_complete(policy: QueryPolicy) -> None:
    """Re-assert the five limits at resolution time.

    Construction already requires them, so this can only fail if a policy
    reached here without passing through the contract. That is worth catching:
    it would mean the limits in force are not the limits that were approved.
    """
    missing = [
        name
        for name in (
            "maximum_bytes_billed",
            "maximum_rows",
            "execution_timeout_seconds",
            "maximum_range_days",
            "minimum_aggregation_threshold",
        )
        if getattr(policy, name, None) is None
    ]
    if missing:
        raise PolicyUnresolvable(
            "the effective governed policy is incomplete; a policy missing any required "
            "limit is unresolvable, not partially usable"
        )


def refusal_for(exc: PolicyUnresolvable) -> ContractViolation:
    """Express an unresolvable policy as a governed refusal.

    The message names no limit and no threshold — an unauthorized principal must
    learn nothing about the policy from being refused by it (`SC-009`).
    """
    return ContractViolation(exc.code, "the governed query policy is unresolvable")
