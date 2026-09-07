"""Evidence for the foundational contracts that carry no test task of their own.

Phase 3 gives `T014`, `T031`-`T036` their own test files. `T015`/`T016`
(messages), `T024` (policy), `T025` (result) and `T026` (audit) state completion
evidence but have no dedicated test task, so their evidence is asserted here
rather than left as a claim nobody checks.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.audit import AnalyticsAuditEvent, AuditStage, PrincipalType
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result import (
    AnalyticsResult,
    Completeness,
    ResultCell,
    ResultColumn,
)
from analytics_query.messages.registry import load_registry, message_for

pytestmark = pytest.mark.contract


# --- T015 / T016: messages ---------------------------------------------------


def test_the_registry_covers_the_enum_exactly() -> None:
    """No orphan code, no orphan message."""
    assert load_registry().codes == frozenset(AnalyticsReasonCode)


def test_every_code_has_non_empty_wording() -> None:
    for code in AnalyticsReasonCode:
        assert message_for(code).strip()


def test_wording_is_byte_identical_across_repeats() -> None:
    """Determinism is the property; correctness stays the reviewer's (`D-10`)."""
    for code in AnalyticsReasonCode:
        assert message_for(code) == message_for(code)


def test_no_message_interpolates_a_value() -> None:
    """Fixed sentences only.

    A message that formatted a limit, a count or an identifier could disclose it
    to a principal the refusal exists to tell nothing. Figures a caller is
    entitled to travel in the decision payload, not in this registry.
    """
    for code in AnalyticsReasonCode:
        text = message_for(code)
        for marker in ("{", "}", "%s", "%d", "$"):
            assert marker not in text, f"{code.value} interpolates: {text}"


def test_authorisation_and_existence_wording_discloses_nothing() -> None:
    """The refusals that must reveal least reveal nothing structural."""
    for code in (
        AnalyticsReasonCode.QUERY_POLICY_UNRESOLVABLE,
        AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED,
    ):
        text = message_for(code).lower()
        for leak in ("bytes", "linhas", "maximum", "threshold", "tabela", "select"):
            assert leak not in text, f"{code.value} leaks {leak}"


# --- T024: policy ------------------------------------------------------------

_APPROVAL = PolicyApproval(
    approver_role="data_platform", evidence_ref="approval-1", approved_on=date(2026, 8, 1)
)
_LIMITS = {
    "maximum_bytes_billed": 1,
    "maximum_rows": 1,
    "execution_timeout_seconds": 1,
    "maximum_range_days": 1,
    "minimum_aggregation_threshold": 1,
}


@pytest.mark.parametrize("omitted", sorted(_LIMITS))
def test_a_policy_missing_any_of_the_five_limits_fails_construction(omitted: str) -> None:
    """Jointly required: no configuration runs with cost limits but no privacy floor."""
    limits = {k: v for k, v in _LIMITS.items() if k != omitted}
    with pytest.raises(ContractViolation):
        build(
            QueryPolicy,
            version="p-1",
            effective_from=date(2026, 8, 1),
            approval=_APPROVAL,
            **limits,
        )


def test_a_complete_policy_constructs() -> None:
    policy = build(
        QueryPolicy,
        version="p-1",
        effective_from=date(2026, 8, 1),
        approval=_APPROVAL,
        **_LIMITS,
    )
    assert policy.is_effective_on(date(2026, 8, 2))
    assert not policy.is_effective_on(date(2026, 7, 31))


def test_limits_are_strict_and_positive() -> None:
    """A limit coerced from a float or a string is a limit nobody chose."""
    for bad in ("1", 1.5, 0, -1):
        with pytest.raises(ContractViolation):
            build(
                QueryPolicy,
                version="p-1",
                effective_from=date(2026, 8, 1),
                approval=_APPROVAL,
                **{**_LIMITS, "maximum_rows": bad},
            )


# --- T025: result ------------------------------------------------------------


def test_a_truncated_result_is_not_constructible() -> None:
    """The type system prevents it; there is no rule to remember."""
    assert {c.value for c in Completeness} == {"complete", "empty"}
    assert not hasattr(Completeness, "TRUNCATED")
    with pytest.raises(ValueError):
        Completeness("truncated")


def test_a_suppressed_cell_carries_no_value_and_states_its_reason() -> None:
    cell = build(
        ResultCell,
        suppressed=True,
        suppression_reason=AnalyticsReasonCode.RESULT_CELL_SUPPRESSED,
    )
    assert cell.value is None

    with pytest.raises(ContractViolation):
        build(ResultCell, value=Decimal("1"), suppressed=True, suppression_reason=None)
    with pytest.raises(ContractViolation):
        build(ResultCell, suppressed=True)


def test_values_are_decimal_not_float() -> None:
    """`float` cannot promise byte-identical warehouse figures (`SC-006`)."""
    cell = build(ResultCell, value=Decimal("1.10"))
    assert isinstance(cell.value, Decimal)
    assert str(cell.value) == "1.10"


def test_row_width_must_match_the_declared_columns() -> None:
    column = ResultColumn(identifier="installs", unit="count", is_metric=True)
    with pytest.raises(ContractViolation):
        build(
            AnalyticsResult,
            columns=(column,),
            rows=((ResultCell(value=1), ResultCell(value=2)),),
            completeness=Completeness.COMPLETE,
        )


def test_an_empty_result_may_not_carry_rows() -> None:
    column = ResultColumn(identifier="installs", unit="count", is_metric=True)
    with pytest.raises(ContractViolation):
        build(
            AnalyticsResult,
            columns=(column,),
            rows=((ResultCell(value=1),),),
            completeness=Completeness.EMPTY,
        )


# --- T026: audit -------------------------------------------------------------


def _event(**overrides: object) -> AnalyticsAuditEvent:
    payload: dict[str, object] = {
        "stage": AuditStage.VALIDATION,
        "correlation_id": "c-1",
        "emitted_at": datetime(2026, 8, 12, tzinfo=UTC),
        "principal_ref": "opaque-1",
        "principal_type": PrincipalType.USER,
        "outcome": Outcome.DENY,
        "reason_code": AnalyticsReasonCode.QUERY_TIMEOUT,
    }
    payload.update(overrides)
    return build(AnalyticsAuditEvent, **payload)


def test_the_four_stages_are_declared() -> None:
    assert [s.value for s in AuditStage] == [
        "validation",
        "refusal",
        "execution_start",
        "execution_complete",
    ]


def test_no_field_can_carry_a_value_row_or_query_text() -> None:
    """Enforced by the field set, not by review."""
    declared = set(AnalyticsAuditEvent.model_fields)
    for forbidden in (
        "value",
        "values",
        "rows",
        "result",
        "sql",
        "query_text",
        "question",
        "credential",
        "token",
        "filter_values",
        "principal_name",
        "email",
    ):
        assert forbidden not in declared


def test_an_event_may_not_disagree_with_its_codes_outcome() -> None:
    """Two call sites disagreeing about whether a refusal is a refusal ends the audit."""
    with pytest.raises(ContractViolation):
        _event(outcome=Outcome.ALLOW, reason_code=AnalyticsReasonCode.QUERY_TIMEOUT)


def test_an_upstream_code_is_accepted_and_checked_against_its_own_mapping() -> None:
    """Upstream refusals pass through verbatim, outcome included."""
    event = _event(reason_code=ReasonCode.ACCESS_DENIED, outcome=Outcome.DENY)
    assert event.reason_code is ReasonCode.ACCESS_DENIED


def test_a_pre_authorization_refusal_reports_absent_counts_not_zeroes() -> None:
    """Absent means no execution was contemplated; zero would claim one that measured nothing."""
    event = _event(stage=AuditStage.REFUSAL, query_identity=None)
    assert event.dry_run_bytes is None and event.actual_bytes is None and event.row_count is None

    with pytest.raises(ContractViolation):
        _event(stage=AuditStage.REFUSAL, query_identity=None, actual_bytes=0)


def test_the_event_is_frozen() -> None:
    event = _event()
    with pytest.raises(ValidationError):
        event.stage = AuditStage.REFUSAL  # pyright: ignore[reportAttributeAccessIssue]


# --- S-33 (ciclo 517, 2026-09-02): o zero do OD-97 e representavel ------------------


def test_a_zero_aggregation_threshold_constructs() -> None:
    """O valor que o dono aprovou (OD-97) constroi — um tipo que o proibe mente ao registro."""
    policy = build(
        QueryPolicy,
        version="p-s33",
        effective_from=date(2026, 9, 2),
        approval=_APPROVAL,
        **{**_LIMITS, "minimum_aggregation_threshold": 0},
    )
    assert policy.minimum_aggregation_threshold == 0


def test_a_negative_aggregation_threshold_still_refuses() -> None:
    """O outro sentido: ge nao afrouxou a fronteira — negativo segue irrepresentavel."""
    with pytest.raises(ContractViolation):
        build(
            QueryPolicy,
            version="p-s33",
            effective_from=date(2026, 9, 2),
            approval=_APPROVAL,
            **{**_LIMITS, "minimum_aggregation_threshold": -1},
        )
