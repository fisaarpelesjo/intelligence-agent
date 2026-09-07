"""Policy fail-closed behaviour — T061 (FR-048, FR-049, FR-069, FR-070, FR-071; SC-027).

Three ways to be unresolvable, one outcome, and no substitution of any kind.

The load-bearing case is the last group: a policy carrying cost limits but no
minimum-aggregation threshold is **unresolvable**, not partially usable. Treating
it as usable would run real queries with a privacy floor nobody approved, and
cost limits are exactly the sort of thing that gets approved first — so this is
the state the system is most likely to find itself in while `D-16` is open.
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.policy.resolve import (
    PolicyUnresolvable,
    load_policies,
    policy_path,
    refusal_for,
    resolve_policy,
)

pytestmark = pytest.mark.unit

ON = date(2026, 8, 12)
APPROVAL = PolicyApproval(
    approver_role="data_platform", evidence_ref="approval-1", approved_on=date(2026, 8, 1)
)
LIMITS = {
    "maximum_bytes_billed": 1_000_000,
    "maximum_rows": 1_000,
    "execution_timeout_seconds": 30,
    "maximum_range_days": 92,
    "minimum_aggregation_threshold": 5,
}


def _policy(version: str = "p-1", **overrides: object) -> QueryPolicy:
    payload: dict[str, object] = {
        "version": version,
        "effective_from": date(2026, 8, 1),
        "approval": APPROVAL,
        **LIMITS,
    }
    payload.update(overrides)
    return build(QueryPolicy, **payload)


# --- the three unresolvable shapes ------------------------------------------


def test_zero_effective_policies_refuses() -> None:
    with pytest.raises(PolicyUnresolvable) as caught:
        resolve_policy(ON, policies=())
    assert caught.value.code is AnalyticsReasonCode.QUERY_POLICY_UNRESOLVABLE


def test_a_policy_not_yet_effective_does_not_count() -> None:
    future = _policy(effective_from=date(2027, 1, 1))
    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON, policies=(future,))


def test_more_than_one_effective_policy_refuses() -> None:
    """Two authoritative limit sets. Picking one would be picking arbitrarily."""
    with pytest.raises(PolicyUnresolvable) as caught:
        resolve_policy(ON, policies=(_policy("p-1"), _policy("p-2")))
    assert "ambiguous" in caught.value.detail


def test_exactly_one_effective_policy_resolves() -> None:
    resolved = resolve_policy(ON, policies=(_policy(),))
    assert resolved.version == "p-1"
    assert resolved.minimum_aggregation_threshold == 5


# --- no substitution, ever ---------------------------------------------------


@pytest.mark.parametrize("omitted", sorted(LIMITS))
def test_a_policy_missing_any_limit_cannot_be_constructed(omitted: str) -> None:
    """Incompleteness is caught at the contract, so it never reaches resolution."""
    limits = {k: v for k, v in LIMITS.items() if k != omitted}
    with pytest.raises(ContractViolation):
        build(
            QueryPolicy,
            version="p-1",
            effective_from=date(2026, 8, 1),
            approval=APPROVAL,
            **limits,
        )


def test_cost_limits_without_a_privacy_floor_are_unresolvable() -> None:
    """The state the system is most likely to be in while `D-16` is open."""
    with pytest.raises(ContractViolation):
        build(
            QueryPolicy,
            version="p-1",
            effective_from=date(2026, 8, 1),
            approval=APPROVAL,
            maximum_bytes_billed=1,
            maximum_rows=1,
            execution_timeout_seconds=1,
            maximum_range_days=1,
        )


def test_no_previously_seen_value_is_carried_forward() -> None:
    """Resolving once must not leave a usable value behind."""
    resolve_policy(ON, policies=(_policy(),))
    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON, policies=())


def test_no_default_appears_in_the_resolver_code() -> None:
    """Scans executable code, not prose.

    The module *discusses* fallbacks at length — explaining why there are none
    is the point. What must not exist is a default in the code.
    """
    import ast
    import inspect

    from analytics_query.policy import resolve

    tree = ast.parse(inspect.getsource(resolve))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")  # blank every docstring
    code = ast.unparse(tree)
    for marker in ("DEFAULT_", "fallback", "or 1000", "except PolicyUnresolvable: pass"):
        assert marker not in code


# --- governed content is empty by design ------------------------------------


def test_the_governed_policy_file_holds_no_approved_instance() -> None:
    """The designed state while `D-14` and `D-16` are open, not a gap."""
    assert load_policies() == ()


def test_resolution_against_governed_content_refuses_today() -> None:
    with pytest.raises(PolicyUnresolvable):
        resolve_policy(ON)


def test_the_policy_path_is_located_not_configured() -> None:
    assert policy_path().name == "query-policy.yaml"
    assert policy_path().parent.name == "query_governance"


# --- the refusal discloses nothing ------------------------------------------


def test_the_refusal_names_no_limit_or_threshold() -> None:
    """A principal refused by the policy learns nothing about the policy."""
    with pytest.raises(PolicyUnresolvable) as caught:
        resolve_policy(ON, policies=())
    violation = refusal_for(caught.value)
    text = violation.detail.lower()
    for leak in ("bytes", "rows", "timeout", "threshold", "days", "5", "1000"):
        assert leak not in text
    assert violation.code is AnalyticsReasonCode.QUERY_POLICY_UNRESOLVABLE
