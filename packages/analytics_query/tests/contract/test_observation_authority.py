"""Observation authority — T048 (FR-073, FR-074, FR-075; SC-030, SC-031).

The governed tables are the sole authority for freshness, coverage and
availability on the request path. A caller may not supply, override, weaken or
hint at any of them.

That is asserted by **contract inspection**, not by a runtime check: the request
model declares no field capable of carrying an observation, and `extra="forbid"`
rejects one that is offered anyway. A caller-supplied observation is therefore
unrepresentable rather than merely ignored — there is no field to ignore.
"""

from __future__ import annotations

import pytest

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.request import AnalyticsQuery
from analytics_query.observations.reader import ObservationBundle, ObservationReader

pytestmark = pytest.mark.contract

_OBSERVATION_SHAPED = (
    "freshness",
    "last_loaded_at",
    "coverage",
    "covered_from",
    "covered_to",
    "availability",
    "available",
    "data_revision",
    "data_revision_id",
    "revision_id",
    "observed_at",
    "snapshot",
    "as_of_instant",
    "staleness",
    "tolerance",
)


def test_the_request_declares_no_observation_field() -> None:
    declared = set(AnalyticsQuery.model_fields)
    for name in _OBSERVATION_SHAPED:
        assert name not in declared, f"AnalyticsQuery exposes {name}"


@pytest.mark.parametrize("name", _OBSERVATION_SHAPED)
def test_a_caller_supplied_observation_is_refused(name: str) -> None:
    """Offered anyway, it is an unknown field — not a silently dropped one."""
    from datetime import date

    from analytics_query.contracts.request import DateRange

    with pytest.raises(ContractViolation):
        build(
            AnalyticsQuery,
            metrics=("installs",),
            date_range=DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)),
            **{name: "anything"},
        )


def test_the_reader_port_offers_no_partial_read() -> None:
    """Three separate reads could observe three different instants."""
    methods = {m for m in dir(ObservationReader) if not m.startswith("_")}
    assert "read" in methods
    for forbidden in ("read_freshness", "read_coverage", "read_revisions", "freshness_only"):
        assert forbidden not in methods


def test_the_bundle_carries_all_three_parts_together() -> None:
    fields = set(ObservationBundle.__dataclass_fields__)
    assert {"freshness", "coverage", "revisions"} <= fields
    # The stamps are what make a reused bundle detectable at all.
    assert {"read_at", "request_correlation_id"} <= fields


def test_the_governed_tables_are_constants_not_parameters() -> None:
    """A settable table name would be a runtime switch over governed content."""
    import inspect

    from analytics_query.observations import bigquery_reader

    assert bigquery_reader.FRESHNESS_TABLE == "semantic.source_freshness"
    assert bigquery_reader.AVAILABILITY_TABLE == "semantic.metric_availability"

    signature = inspect.signature(bigquery_reader.BigQueryObservationReader.__init__)
    for name in signature.parameters:
        assert "table" not in name and "dataset" not in name
