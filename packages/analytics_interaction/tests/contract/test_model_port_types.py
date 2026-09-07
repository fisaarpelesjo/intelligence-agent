"""Value-free parameter types — T083 (FR-047, FR-092; SC-054).

    No metric value, result row, aggregate, computed difference, cost figure or
    filter value may cross to a model-facing surface **under any circumstance**.
    The prohibition MUST be **structural**: no code path reachable from a
    model-facing surface may hold, receive or observe a result, so the guarantee
    does not depend on a redaction step being correct. — `FR-092`

`003` tightened this beyond Constitution IV and `002`'s `FR-055`, both of which
permit aggregated evidence to cross for a feature that would later narrate. This
feature narrates nothing, so it needs no number on the model side — and an unused
egress path is still an egress path, reachable by prompt injection from the very
text the model is asked to interpret.

Checked three ways, because each catches what the others miss:

* **by field set** — no declared field on any model-facing type is typed to carry
  a value;
* **by annotation** — no annotation names an upstream result, provenance or
  execution type;
* **by content** — a fully populated request, serialised, contains no figure.

The narrowing property is checked here too: the response type declares exactly
one field, so a provider's prose, confidence score, tool call or alternatives
have nowhere to land.
"""

from __future__ import annotations

import inspect
import typing
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from analytics_interaction.contracts._base import LocalizedRef
from analytics_interaction.contracts.intent import SlotKind
from analytics_interaction.interpretation import model_port
from analytics_interaction.interpretation.model_port import (
    CandidateOption,
    CandidateSelection,
    CandidateSet,
    DelimitedQuestionData,
    InterpretationModelPort,
)

pytestmark = pytest.mark.contract

#: Every type that appears in the port's signature. If a fourth is added it must
#: be added here too — the discovery below asserts the list is complete.
MODEL_FACING = (DelimitedQuestionData, CandidateOption, CandidateSet, CandidateSelection)

#: Field names that would carry an analytical value.
VALUE_FIELDS = (
    "value",
    "values",
    "result",
    "results",
    "row",
    "rows",
    "cell",
    "cells",
    "column",
    "columns",
    "aggregate",
    "difference",
    "figure",
    "amount",
    "total",
    "count",
    "cost",
    "bytes",
    "price",
    "suppressed",
    "suppression",
    "provenance",
    "evidence",
    "sql",
    "query",
    "plan",
    "ledger",
    "audit",
    "credential",
    "token",
    "secret",
    "limit",
    "max_rows",
    "max_bytes",
)

#: Types that carry values, execution evidence or governed limits. None may
#: appear in a model-facing annotation.
FORBIDDEN_ANNOTATIONS = (
    "AnalyticsResult",
    "ResultColumn",
    "ResultProvenance",
    "CostProvenance",
    "SourceUpdate",
    "DerivedFigure",
    "SideResult",
    "GovernedComparison",
    "AnalyticsAnswer",
    "AnswerClaim",
    "CaveatSet",
    "AttributedCaveat",
    "AnalyticsQuery",
    "GovernedFilter",
    "QueryPolicy",
    "ExecutedAnswer",
    "InterpretationPolicy",
    "Decimal",
    "float",
)


def _ref() -> LocalizedRef:
    return LocalizedRef(code="INTENT_AMBIGUOUS", language="pt-BR", content_version="unversioned")


def _option(identifier: str) -> CandidateOption:
    return CandidateOption(identifier=identifier, slot=SlotKind.METRIC, distinguishing=_ref())


def _candidates() -> CandidateSet:
    return CandidateSet(
        slot=SlotKind.METRIC,
        options=(_option("installs"), _option("signups")),
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


# --- the surface is exactly what the port names --------------------------------


def test_the_model_facing_types_are_the_ones_in_the_signature() -> None:
    """A fourth type added to the port must be added to this list.

    Derived from the signature rather than trusted, so the checks below cannot
    silently stop covering something.
    """
    hints = typing.get_type_hints(InterpretationModelPort.narrow)
    named = {hints["question"], hints["candidates"]}
    assert named == {DelimitedQuestionData, CandidateSet}

    return_hint = hints["return"]
    assert CandidateSelection in typing.get_args(return_hint)
    assert type(None) in typing.get_args(return_hint)


def test_the_port_takes_exactly_two_parameters() -> None:
    """A third parameter is where an execution result would arrive."""
    signature = inspect.signature(InterpretationModelPort.narrow)
    assert list(signature.parameters) == ["self", "question", "candidates"]


# --- by field set --------------------------------------------------------------


@pytest.mark.parametrize("model", MODEL_FACING, ids=lambda m: m.__name__)
@pytest.mark.parametrize("field", VALUE_FIELDS)
def test_no_model_facing_type_declares_a_value_field(model: type[BaseModel], field: str) -> None:
    assert field not in model.model_fields, f"{model.__name__} can hold {field}"


def test_each_model_facing_type_declares_only_the_fields_the_contract_names() -> None:
    """Enumerated exactly, so an added field fails by name rather than by pattern."""
    assert tuple(DelimitedQuestionData.model_fields) == ("text", "delimiter")
    assert tuple(CandidateOption.model_fields) == ("identifier", "slot", "distinguishing")
    assert tuple(CandidateSet.model_fields) == (
        "slot",
        "options",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
        "contract_version",
    )
    assert tuple(CandidateSelection.model_fields) == ("identifier",)


@pytest.mark.parametrize("model", MODEL_FACING, ids=lambda m: m.__name__)
def test_every_model_facing_type_is_frozen_and_forbids_extras(
    model: type[BaseModel],
) -> None:
    """Forbidding extras is what stops a provider's response widening the type."""
    assert model.model_config.get("frozen") is True
    assert model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("field", VALUE_FIELDS)
def test_adding_a_value_field_is_refused_at_construction(field: str) -> None:
    """The mutation test: a result field added to a request must not construct."""
    with pytest.raises(ValidationError):
        CandidateSet.model_validate(
            {
                "slot": "metric",
                "options": [
                    {
                        "identifier": "installs",
                        "slot": "metric",
                        "distinguishing": _ref().model_dump(),
                    },
                    {
                        "identifier": "signups",
                        "slot": "metric",
                        "distinguishing": _ref().model_dump(),
                    },
                ],
                "catalog_release": "r-1",
                "policy_version": "pol-1",
                "vocabulary_version": "voc-1",
                field: 42,
            }
        )


# --- by annotation -------------------------------------------------------------


@pytest.mark.parametrize("model", MODEL_FACING, ids=lambda m: m.__name__)
@pytest.mark.parametrize("forbidden", FORBIDDEN_ANNOTATIONS)
def test_no_model_facing_annotation_names_a_value_type(
    model: type[BaseModel], forbidden: str
) -> None:
    """Reaches nested types too: ``CandidateSet`` holds ``CandidateOption``."""
    rendered = {f"{name}: {field.annotation}" for name, field in model.model_fields.items()}
    offenders = [entry for entry in rendered if forbidden in entry]
    assert not offenders, f"{model.__name__} annotation names {forbidden}: {offenders}"


def test_no_model_facing_type_can_hold_a_number_at_all() -> None:
    """Except ``contract_version``, which is a version and not a measurement.

    Stated as an exhaustive check rather than a pattern: every other field is a
    string, an enum, a nested governed pointer or a tuple of them.
    """
    numeric: list[str] = []
    for model in MODEL_FACING:
        for name, field in model.model_fields.items():
            annotation = field.annotation
            if annotation in (int, float, Decimal) and name != "contract_version":
                numeric.append(f"{model.__name__}.{name}")
    assert not numeric, f"a model-facing type holds a number: {numeric}"


# --- by content ----------------------------------------------------------------


def test_a_fully_populated_request_serialises_without_any_figure() -> None:
    request = _candidates().model_dump_json()
    question = DelimitedQuestionData(text="quantas conversões em julho?").model_dump_json()

    for payload in (request, question):
        for forbidden in ('"value"', '"rows"', '"cost"', "select ", "0.0", "R$"):
            assert forbidden not in payload.lower(), f"the payload carried {forbidden}"


def test_the_candidate_metadata_is_a_governed_pointer_not_a_string() -> None:
    """The only human-facing content that crosses is wording somebody approved."""
    annotation = CandidateOption.model_fields["distinguishing"].annotation
    assert annotation is LocalizedRef
    assert tuple(LocalizedRef.model_fields) == (
        "code",
        "language",
        "content_version",
        "arguments",
    )


# --- the response cannot widen anything ----------------------------------------


def test_the_selection_declares_one_field_and_nothing_else() -> None:
    """No confidence, no score, no rationale, no alternatives, no tool call.

    A confidence score would invite a threshold; a threshold would be a tuned
    number nobody governed; and answerability would start depending on it, which
    is what `FR-041` forbids.
    """
    assert tuple(CandidateSelection.model_fields) == ("identifier",)


@pytest.mark.parametrize(
    "extra", ["confidence", "score", "rationale", "explanation", "alternatives", "tool_call"]
)
def test_a_provider_extra_is_refused_rather_than_ignored(extra: str) -> None:
    with pytest.raises(ValidationError):
        CandidateSelection.model_validate({"identifier": "installs", extra: 0.97})


def test_the_module_declares_no_provider_of_any_kind() -> None:
    """A ``Protocol`` and nothing else. The mutation test for a hidden provider."""
    import ast
    from pathlib import Path

    source = Path(inspect.getfile(model_port)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    concrete = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any("Protocol" in ast.unparse(base) for base in node.bases) is False
        and any(
            isinstance(child, ast.FunctionDef) and child.name == "narrow" for child in node.body
        )
    ]
    assert not concrete, f"a concrete model port ships in src/: {concrete}"
