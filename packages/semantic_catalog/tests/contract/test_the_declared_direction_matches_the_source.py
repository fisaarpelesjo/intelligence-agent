"""The direction a metric declares is the direction its source carries — `T1311`, `D-1303`.

`lower_is_better` moved into the metric contract on 2026-09-04 (`OD-113`). Until then it was
answered by the VIEW's own column — which meant a property of the METRIC was decided by
another repository's table, and a metric added to the catalogue had no direction until
somebody edited that view.

## Why this file exists at all, and it is a trade-off written down rather than hidden

The field was classified **Descriptive**, and that decision was measured rather than argued.
Semantic is the tempting reading: flipping a polarity flips the COLOUR of an entire series
without a single number moving, and the reader sees the opposite of what they saw yesterday.
It was classified `_SEM` first for exactly that reason — and then the version gate answered:
`diff` against `main` demanded a NEW VERSION BLOCK on all twenty metrics bound to the view,
to declare a direction the view already carried and nobody was changing.

Twenty new version blocks change the historical answer of twenty metrics ("exactly one
version for any date") in order to record a fill-in. **Declaring for the first time is not
changing**, and the gate cannot tell them apart.

So the risk is carried by an INSTRUMENT instead of by a classification: this file. A silent
inversion lights up here, where a `Descriptive` classification would have let it through.

## What this does NOT claim

It does not claim the view is authoritative — the whole point of `D-1303` is that it is not.
It claims the two agree *while both exist*, which is what a migration means. The day the
view stops carrying the column, this node skips honestly and the contract stands alone,
which is the intended end state and not a failure.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
METRICS = REPO / "semantic" / "metrics"
VIEW_REFERENCE = "semantic.subscription_daily_metrics"
VIEW = "example-project-id.semantic.subscription_daily_metrics"


def _declared() -> dict[str, bool | None]:
    """``{kpi_name: lower_is_better}`` for every version bound to the view."""
    found: dict[str, bool | None] = {}
    for path in sorted(METRICS.glob("*.yaml")):
        document = cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))
        if document.get("kind") != "metric":
            continue
        for version in cast("list[dict[str, Any]]", document.get("versions") or []):
            if version.get("source_view") != VIEW_REFERENCE:
                continue
            kpi = version.get("kpi_name")
            if isinstance(kpi, str):
                found[kpi] = version.get("lower_is_better")
    return found


def test_every_metric_bound_to_the_view_declares_a_direction() -> None:
    """Non-vacuity, and the point of the move: the catalogue answers for itself.

    A metric may legitimately leave the direction undeclared — the report then prints no
    colour, which is a true statement. But of the twenty bound to this view, every one has a
    direction the source already knew, so silence here would mean the migration stopped
    halfway and nobody noticed.
    """
    declared = _declared()
    assert declared, "no metric is bound to the view; this node would assert nothing"
    silent = sorted(kpi for kpi, value in declared.items() if value is None)
    assert not silent, f"bound to the view and declaring no direction: {silent}"


def test_the_declared_direction_is_a_boolean_and_not_something_truthy() -> None:
    """The `S-41` shape, one feature over: a value of the wrong type is not an answer."""
    wrong = {kpi: value for kpi, value in _declared().items() if not isinstance(value, bool)}
    assert not wrong, f"declared a direction that is not a boolean: {wrong}"


@pytest.mark.skipif(
    not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    reason="no Google credential is configured; the view could not be asked and nothing about "
    "the agreement between contract and source was measured",
)
def test_the_contract_and_the_view_agree_while_both_carry_the_direction() -> None:
    """**The instrument that carries the risk the classification stopped carrying.**

    A silent inversion — the failure that made `Semantic` tempting — lights up right here.
    """
    from google.cloud import bigquery

    client = bigquery.Client()
    query = (
        "SELECT kpi_name, ANY_VALUE(lower_is_better) AS lower_is_better, "
        "COUNT(DISTINCT CAST(lower_is_better AS STRING)) AS distinct_values "
        f"FROM `{VIEW}` WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) "
        "GROUP BY kpi_name"
    )
    source: dict[str, tuple[bool | None, int]] = {}
    for row in cast("list[dict[str, object]]", list(client.query(query).result())):
        kpi = cast("str", row["kpi_name"])
        source[kpi] = (
            cast("bool | None", row["lower_is_better"]),
            cast("int", row["distinct_values"]),
        )
    assert source, "the view returned no KPI; this node measured nothing"

    declared = _declared()
    disagreeing: list[str] = []
    for kpi, (view_value, distinct) in source.items():
        if kpi not in declared or view_value is None:
            continue
        assert distinct == 1, f"{kpi}: the view carries {distinct} directions for one KPI"
        if declared[kpi] != bool(view_value):
            disagreeing.append(
                f"{kpi}: contract says {declared[kpi]}, view says {bool(view_value)}"
            )
    assert not disagreeing, (
        "the contract and the source disagree about which way is good: "
        f"{disagreeing}. One of them was changed without the other."
    )
