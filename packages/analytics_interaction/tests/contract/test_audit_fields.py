"""The audit denylist, as a field set — T138 (FR-053; SC-026).

    Evidence: no field can hold question text, a value, a filter value, a caveat
    embedding a figure, or key material. — `tasks.md` T138

This is the **first** of the denylist's two enforcements. It asserts that no
field on the event *can* hold a forbidden value — a claim about the schema,
provable without running anything. `T139`'s content scan is the second, over a
fully populated event, catching a value smuggled into a field whose name sounds
innocent. `002` established that either alone misses the other's failure mode:

* a field-set test passes while ``metric_ids`` carries ``("installs=42",)``;
* a content scan passes while a ``notes: str`` field sits unused, waiting.

## The types are the enforcement

Every field is an enum, a governed identifier, an opaque reference, a date or a
bounded integer. None is ``float``, ``Decimal``, ``dict``, ``Any`` or an open
object — so a metric value, a fact row, a computed difference or a filter value
has nowhere to land before a scan looks for one.

The strongest assertion here is the negative one: there is no ``payload``, no
``metadata``, no ``context``, no ``details``, no ``extra`` and no ``attributes``.
Those are the names a value arrives under when nobody declared a field for it,
and a single one would make the whole contract advisory.
"""

from __future__ import annotations

import typing
from datetime import date
from decimal import Decimal

import pytest
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result import AnalyticsResult, ResultCell, ResultRow
from analytics_query.contracts.result_provenance import ResultProvenance
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_interaction.contracts.audit import (
    AUDIT_EVENT_FIELDS,
    AuditPeriod,
    InterpretationAuditEvent,
    InterpretationStage,
)
from analytics_interaction.contracts.comparison import ComparisonRoute, DerivedFigure
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

pytestmark = pytest.mark.contract

#: Field names a value would arrive under if nobody declared one for it. A single
#: one makes the whole contract advisory, because anything fits in it.
OPEN_FIELD_NAMES = frozenset(
    {
        "payload",
        "metadata",
        "context",
        "details",
        "extra",
        "attributes",
        "notes",
        "annotations",
        "tags",
        "properties",
        "data",
        "body",
        "raw",
    }
)

#: Names that would hold the content the denylist forbids.
FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "question",
        "question_text",
        "text",
        "prompt",
        "reply",
        "utterance",
        "transcript",
        "history",
        "value",
        "values",
        "result",
        "rows",
        "cells",
        "difference",
        "figure",
        "filters",
        "filter_values",
        "caveats",
        "caveat_text",
        "message",
        "message_pt_br",
        "sql",
        "query",
        "plan",
        "credential",
        "token",
        "secret",
        "key",
        "key_material",
        "seal",
        "email",
        "name",
        "ip",
        "device_id",
        "session_id",
    }
)

#: Types that can carry an analytical value or an unbounded payload.
FORBIDDEN_TYPES = (
    Decimal,
    float,
    AnalyticsResult,
    ResultRow,
    ResultCell,
    ResultProvenance,
    DerivedFigure,
)

#: What each declared field may be. An allowlist, because the failure mode is
#: additive: a new field of a new type slips past a denylist that never heard of
#: it.
PERMITTED_TYPES: tuple[object, ...] = (
    str,
    int,
    bool,
    date,
    InterpretationStage,
    PrincipalType,
    Outcome,
    ReasonCode,
    AnalyticsReasonCode,
    ComparisonRoute,
    AuditPeriod,
    InterpretationReasonCode,
    type(None),
    # Not types a field holds: pydantic's ``Strict`` marker and the ``...`` of a
    # variadic tuple. Named rather than filtered out silently, so the allowlist
    # stays an inventory of what the walker actually sees.
    type(Ellipsis),
)


def _declared_types(annotation: object, seen: set[object] | None = None) -> set[object]:
    """Every concrete type an annotation can resolve to, transitively.

    Depth matters: ``AuditPeriod`` is a nested model, and a one-level check would
    call an event clean while its period carried anything at all.
    """
    seen = seen if seen is not None else set()
    if annotation is None or annotation in seen:
        return seen

    arguments = typing.get_args(annotation)
    if arguments:
        for argument in arguments:
            _declared_types(argument, seen)
        return seen

    seen.add(annotation)
    fields = getattr(annotation, "model_fields", None)
    if fields is not None:
        for info in fields.values():  # pyright: ignore[reportUnknownVariableType]
            _declared_types(getattr(info, "annotation", None), seen)
    return seen


def _all_declared_types() -> set[object]:
    found: set[object] = set()
    for info in InterpretationAuditEvent.model_fields.values():
        _declared_types(info.annotation, found)
    return found


# --- no open field ------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(OPEN_FIELD_NAMES))
def test_no_open_extension_field_is_declared(name: str) -> None:
    """**The strongest assertion here.**

    A single open field makes the contract advisory: anything fits in it, and
    every other guarantee becomes a convention somebody follows.
    """
    assert name not in AUDIT_EVENT_FIELDS


@pytest.mark.parametrize("name", sorted(FORBIDDEN_FIELD_NAMES))
def test_no_field_names_forbidden_content(name: str) -> None:
    """Question text, values, filters, caveats, SQL, secrets and PII."""
    assert name not in AUDIT_EVENT_FIELDS


def test_the_event_declares_nineteen_fields_and_no_more() -> None:
    """Counted, so a field added without review is visible here.

    Not a style rule: a new field is a new place a value can be put, and the
    count is the cheapest way to notice one arriving.
    """
    assert len(AUDIT_EVENT_FIELDS) == 19


# --- no field can hold a value --------------------------------------------------------


@pytest.mark.parametrize("forbidden", FORBIDDEN_TYPES, ids=lambda t: getattr(t, "__name__", str(t)))
def test_no_declared_type_can_carry_an_analytical_value(forbidden: type) -> None:
    """``Decimal`` and ``float`` especially: those are what a figure looks like."""
    assert forbidden not in _all_declared_types()


def test_every_declared_type_is_on_the_permitted_list() -> None:
    """An allowlist, because a new field of a new type slips past a denylist."""
    unexpected = [
        declared
        for declared in _all_declared_types()
        if declared not in PERMITTED_TYPES
        and declared is not Ellipsis
        and type(declared).__name__ != "Strict"
    ]
    assert not unexpected, f"an unexpected type is declared on the audit event: {unexpected}"


def test_no_field_is_a_mapping_or_an_open_object() -> None:
    """A ``dict`` field is an open field wearing a type."""
    for declared in _all_declared_types():
        assert declared is not dict
        assert declared is not typing.Any


def test_the_nested_period_carries_only_two_dates() -> None:
    """Depth: a nested model is where a one-level check stops looking."""
    assert set(AuditPeriod.model_fields) == {"start", "end"}
    for info in AuditPeriod.model_fields.values():
        assert info.annotation is date


# --- and the identifier fields are identifiers -------------------------------------------


@pytest.mark.parametrize(
    "name", ["metric_ids", "dimension_ids", "source_ids", "granted_access_tags"]
)
def test_the_identifier_collections_are_string_tuples(name: str) -> None:
    """Governed identifiers describe the ask without reproducing the typing."""
    annotation = InterpretationAuditEvent.model_fields[name].annotation
    assert "tuple[str" in str(annotation)


def test_the_principal_reference_is_a_plain_opaque_string() -> None:
    """Stable and opaque. Resolvable only through the identity system.

    Stability matters as much as opacity: an identifier that rotated per question
    would satisfy privacy and destroy the audit, because "this principal was
    refused eleven times" would be unobservable.
    """
    assert InterpretationAuditEvent.model_fields["principal_ref"].annotation is str


def test_the_reason_code_is_a_union_of_the_three_governed_namespaces() -> None:
    """Never a free string. A code outside the three has no representation."""
    annotation = str(InterpretationAuditEvent.model_fields["reason_code"].annotation)
    assert "ReasonCode" in annotation
    assert "AnalyticsReasonCode" in annotation
    assert "InterpretationReasonCode" in annotation


def test_an_arbitrary_string_is_not_an_acceptable_reason_code() -> None:
    from ..fixtures.audits import populated_event

    with pytest.raises(ValueError):
        InterpretationAuditEvent.model_validate(
            {**populated_event().model_dump(), "reason_code": "SOMETHING_WENT_WRONG"}
        )
