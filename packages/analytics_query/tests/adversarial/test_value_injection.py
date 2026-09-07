"""Bound-parameter injection — T056 (FR-002; SC-001).

A filter value carrying statement terminators, comment sequences, quotes or a
subquery must travel as **data** and never become syntax. The classic payload
``'; DROP TABLE x; --`` is the named case, but the property is general: whatever
the value contains, it appears in ``parameters`` and never in ``text``.

This is why the design binds rather than escapes. Escaping is a function someone
can get wrong for one input class; binding removes the question — the value is
never in a position where syntax is parsed.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.metric import Aggregation

from analytics_query.compile.guards import assert_emitted_text_is_safe
from analytics_query.compile.plan import (
    BoundParameter,
    PredicateSlot,
    ProjectionSlot,
    QueryStructure,
    TableSlot,
)
from analytics_query.compile.render import render
from analytics_query.contracts.operators import GovernedOperator

pytestmark = pytest.mark.adversarial

PAYLOADS = [
    "'; DROP TABLE x; --",
    "' OR '1'='1",
    '" OR ""="',
    "BR'; DELETE FROM `semantic.metric_installs`; --",
    "*/ UNION SELECT * FROM `raw.events` /*",
    "(SELECT password FROM users)",
    "BR--",
    "BR/*comment*/",
    "BR\nUNION ALL SELECT 1",
    "BR; SELECT 1",
    "`semantic.other`",
    "\\'; DROP TABLE x",
]


def _structure(value: str) -> QueryStructure:
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
        predicates=(
            PredicateSlot(
                dimension_id="country",
                column="country",
                operator=GovernedOperator.EQ,
                parameters=(BoundParameter(name="p0", value=value),),
            ),
        ),
        date_column="event_date",
        date_start=BoundParameter(name="p1", value=date(2026, 7, 1)),
        date_end=BoundParameter(name="p2", value=date(2026, 7, 31)),
    )


@pytest.mark.parametrize("payload", PAYLOADS)
def test_a_hostile_value_never_appears_in_the_text(payload: str) -> None:
    rendered = render(_structure(payload))
    assert payload not in rendered.text
    assert rendered.parameters["p0"] == payload


@pytest.mark.parametrize("payload", PAYLOADS)
def test_a_hostile_value_never_becomes_syntax(payload: str) -> None:
    """The rendered text still passes every emitted-text assertion."""
    rendered = render(_structure(payload))
    assert_emitted_text_is_safe(rendered)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_the_text_is_identical_whatever_the_value_is(payload: str) -> None:
    """Proof the value contributes nothing to the text at all.

    Stronger than "the payload is absent": the text is *byte-identical* to the
    benign case, so no value can influence the shape of the statement.
    """
    assert render(_structure(payload)).text == render(_structure("BR")).text


def test_dates_bind_rather_than_render() -> None:
    rendered = render(_structure("BR"))
    assert "2026-07-01" not in rendered.text
    assert rendered.parameters["p1"] == "2026-07-01"
