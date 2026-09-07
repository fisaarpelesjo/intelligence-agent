"""Runtime policy resolution — T051 (FR-072).

Every decision records the **resolved** ``policy_version``, because a behaviour
change can come from the catalog changing *or* from the gate policy changing, and
an audit that cannot tell them apart cannot explain either.

Two failures, one outcome. Zero effective policies and more than one effective
policy both resolve to ``POLICY_UNRESOLVABLE`` / DENY. Neither falls back:

* **zero** — there is no default policy to assume, and evaluating under one
  nobody approved is unauditable;
* **more than one** — preferring the newest, the first, or the one with the
  higher version number would be this module inventing the tie-break that the
  governance process is supposed to make impossible.

The resolver returns a *result*, not an exception, at the pipeline boundary: the
pipeline must be able to emit a well-formed denial carrying the reason code, and
an exception escaping to the caller is not a decision anyone can audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..contracts.policy import CatalogPolicy, PolicySet, PolicyUnresolvableError
from ..contracts.reason_codes import ReasonCode
from ..loader.load import LoadedCatalog

__all__ = ["PolicyResolution", "resolve_policy"]


@dataclass(frozen=True, slots=True)
class PolicyResolution:
    """Either a resolved policy, or the reason no decision may proceed."""

    policy: CatalogPolicy | None
    reason_code: ReasonCode | None
    detail: str

    @property
    def resolved(self) -> bool:
        return self.policy is not None

    def require(self) -> CatalogPolicy:
        """The policy, or raise. For callers that cannot emit a decision."""
        if self.policy is None:
            raise PolicyUnresolvableError(self.detail)
        return self.policy

    @property
    def version(self) -> str:
        """``<policy_id>@<policy_version>`` — recorded on every decision."""
        if self.policy is None:
            return "unresolved"
        return f"{self.policy.policy_id}@{self.policy.policy_version}"


def resolve_policy(catalog: LoadedCatalog, *, on: date) -> PolicyResolution:
    """Resolve the governed policy effective on ``on``. Fails closed."""
    if not catalog.policies:
        return PolicyResolution(
            policy=None,
            reason_code=ReasonCode.POLICY_UNRESOLVABLE,
            detail=(
                f"no catalog policy is effective on {on.isoformat()}; "
                "no default policy is ever assumed"
            ),
        )
    try:
        policy = PolicySet(policies=catalog.policies).resolve_effective(on)
    except PolicyUnresolvableError as exc:
        return PolicyResolution(
            policy=None,
            reason_code=ReasonCode.POLICY_UNRESOLVABLE,
            detail=str(exc),
        )
    return PolicyResolution(policy=policy, reason_code=None, detail=f"resolved on {on.isoformat()}")
