"""Fixture containment — T047 (FR-075; SC-032).

Fixtures may prove internal behaviour. They may never be reachable on the request
path, because a fixture observation reachable in production is a governed
decision made from invented evidence.

Containment is asserted structurally rather than promised: `src/` is scanned for
any reference to a fixture module, and for any runtime switch that could select
one. A flag would be the failure mode here — code that reads the governed tables
"unless configured otherwise" satisfies every unit test and violates `FR-075` in
production.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import analytics_query

pytestmark = pytest.mark.contract

SRC = Path(analytics_query.__file__).parent
_SOURCES = sorted(SRC.rglob("*.py"))


def test_the_scan_actually_sees_the_package() -> None:
    """A containment scan over zero files would pass silently."""
    assert len(_SOURCES) >= 10


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_src_module_references_a_fixture(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in (
        "FixtureObservationReader",
        "FakeWarehouseAdapter",
        "tests.fixtures",
        "tests/fixtures",
    ):
        assert marker not in text, f"{path.relative_to(SRC)} references {marker}"


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_src_module_reads_a_runtime_switch(path: Path) -> None:
    """No environment variable, flag or deployment mode reaches governed content."""
    text = path.read_text(encoding="utf-8")
    for marker in ("os.environ", "getenv", "USE_FIXTURE", "FIXTURE_MODE", "DEPLOYMENT_MODE"):
        assert marker not in text, f"{path.relative_to(SRC)} reads a runtime switch: {marker}"


def test_the_bigquery_client_is_imported_in_exactly_one_module() -> None:
    """ADR 0007: the dependency's blast radius is one file, not the package."""
    importers = [
        p.relative_to(SRC).as_posix()
        for p in _SOURCES
        if re.search(r"^\s*(from google|import google)", p.read_text(encoding="utf-8"), re.M)
    ]
    assert importers == ["adapters/bigquery/client.py"], importers


def test_the_fixture_reader_satisfies_the_real_port() -> None:
    """Fixtures exercise the governed contract, not a parallel one."""
    from analytics_query.observations.reader import ObservationReader

    from ..fixtures.observations.reader import FixtureObservationReader

    assert isinstance(FixtureObservationReader(), ObservationReader)


def test_the_fake_adapter_satisfies_the_real_port() -> None:
    from analytics_query.execution.adapter import WarehouseAdapter

    from ..fixtures.adapter.fake import FakeWarehouseAdapter

    assert isinstance(FakeWarehouseAdapter(), WarehouseAdapter)
