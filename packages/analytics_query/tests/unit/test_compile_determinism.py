"""Compiler determinism — T058 (FR-002; SC-001).

The same governed request must render byte-identical text and parameters across
runs and across processes. Reproducibility depends on it: a query identity that
described a statement which rendered differently the second time would identify
nothing useful, and `SC-015`'s "identical values on re-issue" would rest on
nothing.

Placeholder names are generated positionally rather than derived from the
dimension or the value, so naming is stable *and* carries no caller-controlled
characters.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.metric import Aggregation

from analytics_query.compile.plan import (
    BoundParameter,
    GroupBySlot,
    PredicateSlot,
    ProjectionSlot,
    QueryStructure,
    TableSlot,
    parameter_name,
)
from analytics_query.compile.render import render
from analytics_query.contracts.operators import GovernedOperator

pytestmark = pytest.mark.unit


def _structure() -> QueryStructure:
    return QueryStructure(
        table=TableSlot(view="semantic.metric_installs"),
        projections=(
            ProjectionSlot(
                metric_id="installs",
                aggregation=Aggregation.SUM,
                column="installs",
                alias="installs",
                unit="users",
            ),
        ),
        group_by=(
            GroupBySlot(dimension_id="country", column="country"),
            GroupBySlot(dimension_id="platform", column="platform"),
        ),
        predicates=(
            PredicateSlot(
                dimension_id="platform",
                column="platform",
                operator=GovernedOperator.IN,
                parameters=(
                    BoundParameter(name="p0", value="android"),
                    BoundParameter(name="p1", value="ios"),
                ),
            ),
        ),
        date_column="event_date",
        date_start=BoundParameter(name="p2", value=date(2026, 7, 1)),
        date_end=BoundParameter(name="p3", value=date(2026, 7, 31)),
    )


def test_two_renders_are_byte_identical() -> None:
    first, second = render(_structure()), render(_structure())
    assert first.text == second.text
    assert first.parameters == second.parameters


def test_the_text_is_stable_across_repeated_calls_on_one_structure() -> None:
    structure = _structure()
    assert len({render(structure).text for _ in range(20)}) == 1


def test_placeholder_names_are_positional_and_carry_no_caller_input() -> None:
    assert parameter_name(0) == "p0"
    assert parameter_name(7) == "p7"
    rendered = render(_structure())
    assert set(rendered.parameters) == {"p0", "p1", "p2", "p3"}


def test_every_bound_value_reaches_the_parameters() -> None:
    rendered = render(_structure())
    assert rendered.parameters["p0"] == "android"
    assert rendered.parameters["p1"] == "ios"
    assert rendered.parameters["p2"] == "2026-07-01"


def test_group_by_and_projection_order_follow_the_structure() -> None:
    text = render(_structure()).text
    assert text.index("country") < text.index("platform AS platform")
    assert text.endswith("GROUP BY country, platform")


def test_an_ungoverned_aggregation_fails_loudly() -> None:
    """`ratio` has no single governed column; rendering one would invent the calculation."""
    from analytics_query.compile.slots import CompilationDefect

    structure = QueryStructure(
        table=TableSlot(view="semantic.metric_x"),
        projections=(
            ProjectionSlot(
                metric_id="x",
                aggregation=Aggregation.RATIO,
                column="x",
                alias="x",
                unit="rate",
            ),
        ),
    )
    with pytest.raises(CompilationDefect):
        render(structure)
