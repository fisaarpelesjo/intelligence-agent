"""Observation atomicity and per-request reads — T049 (FR-076, FR-077; SC-033).

Two properties, and both fail closed.

**Atomic.** A bundle missing any required source in any of its three parts is not
a smaller true answer — it is an unknown state wearing the shape of an answer.
Every partial shape refuses with the same code as a total failure, because from
the caller's side there is no difference worth exposing.

**Per request.** A bundle stamped with another request's correlation id has
escaped the request it was read for. Reusing it could answer from data a fresh
read would have refused, which is the exact failure `FR-077` names.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.observations.failure import ObservationsUnavailable, read_bundle_or_refuse
from analytics_query.observations.reader import ObservationBundle

from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.unit

SOURCES = frozenset({"google_play", "ios_app"})
CID = "corr-1"


def test_a_complete_bundle_is_returned() -> None:
    bundle = read_bundle_or_refuse(
        FixtureObservationReader(), source_ids=SOURCES, correlation_id=CID
    )
    assert bundle.source_ids() == SOURCES
    assert bundle.request_correlation_id == CID


@pytest.mark.parametrize("part", ["freshness", "coverage", "revisions"])
def test_a_bundle_missing_any_part_refuses(part: str) -> None:
    """All three parts, or none. There is no two-thirds answer."""
    with pytest.raises(ObservationsUnavailable) as caught:
        read_bundle_or_refuse(
            FixtureObservationReader(drop_part=part), source_ids=SOURCES, correlation_id=CID
        )
    assert caught.value.code is AnalyticsReasonCode.OBSERVATIONS_UNAVAILABLE


def test_a_bundle_missing_one_required_source_refuses() -> None:
    """Partial coverage cannot say whether the unobserved source is stale."""
    with pytest.raises(ObservationsUnavailable):
        read_bundle_or_refuse(
            FixtureObservationReader(omit_sources=frozenset({"ios_app"})),
            source_ids=SOURCES,
            correlation_id=CID,
        )


def test_a_failed_read_refuses_with_the_same_code() -> None:
    with pytest.raises(ObservationsUnavailable) as caught:
        read_bundle_or_refuse(
            FixtureObservationReader(fail_with=RuntimeError("warehouse unreachable")),
            source_ids=SOURCES,
            correlation_id=CID,
        )
    assert caught.value.code is AnalyticsReasonCode.OBSERVATIONS_UNAVAILABLE


def test_an_empty_read_refuses_rather_than_reporting_nothing_stale() -> None:
    with pytest.raises(ObservationsUnavailable):
        read_bundle_or_refuse(
            FixtureObservationReader(omit_sources=SOURCES), source_ids=SOURCES, correlation_id=CID
        )


def test_a_bundle_from_another_request_is_refused() -> None:
    """A reused snapshot is detectable, and detection is the point of the stamp."""
    with pytest.raises(ObservationsUnavailable) as caught:
        read_bundle_or_refuse(
            FixtureObservationReader(stamp_correlation_id="corr-OTHER"),
            source_ids=SOURCES,
            correlation_id=CID,
        )
    assert "another request" in caught.value.detail


def test_no_fallback_path_exists() -> None:
    """No previous snapshot, no default, no assumption of freshness."""
    import inspect

    from analytics_query.observations import failure

    source = inspect.getsource(failure)
    for marker in ("last_known", "previous_bundle", "default_bundle", "assume_fresh", "cache"):
        assert marker not in source


def test_each_read_produces_its_own_bundle() -> None:
    reader = FixtureObservationReader()
    first = read_bundle_or_refuse(reader, source_ids=SOURCES, correlation_id="a")
    second = read_bundle_or_refuse(reader, source_ids=SOURCES, correlation_id="b")
    assert first is not second
    assert first.request_correlation_id != second.request_correlation_id


def test_atomicity_is_a_property_of_the_bundle_itself() -> None:
    empty = ObservationBundle(
        freshness=(),
        coverage=(),
        revisions=(),
        read_at=datetime.now(UTC),
        request_correlation_id=CID,
    )
    assert empty.is_atomic_for(frozenset()) is True
    assert empty.is_atomic_for(SOURCES) is False
