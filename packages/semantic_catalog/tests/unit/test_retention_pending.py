"""Retention-pending guard — T049 (FR-048; SC-020).

One job: make an accidental default fail CI.

D-8 and D-9 are open, so ``identity_rule``, ``eligible_event`` and
``cohort_timezone`` are unauthored. The failure this guards against is somebody
making the build green by supplying one — a canonical time zone that "looks
right", an eligible event copied from another metric, an identity rule inferred
from the source. Each would publish a retention figure nobody agreed to, and the
number would look completely ordinary.

So the assertions are deliberately blunt: all three fields unset in the authored
catalog, and *any* of them set-but-incomplete still yields ``pending``. Only the
complete set publishes, and that set does not exist yet.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.metric import Lifecycle, Metric
from semantic_catalog.contracts.retention import EXTERNALLY_AUTHORED_FIELDS
from semantic_catalog.loader.lifecycle import PendingReason, derive_lifecycle, derive_lifecycles
from semantic_catalog.loader.load import LoadedCatalog, load_catalog

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
SEMANTIC = REPO / "semantic"
RETENTION = ("retention_rate_d1", "retention_rate_d7", "retention_rate_d30")
EXPECTED_UNSET = (
    "retention.cohort_timezone",
    "retention.eligible_event",
    "retention.identity_rule",
)


@pytest.fixture(scope="module")
def catalog() -> LoadedCatalog:
    return load_catalog(SEMANTIC)


def test_the_three_metrics_exist_and_are_distinct(catalog: LoadedCatalog) -> None:
    """One metric per window, never one parameterised metric (FR-044, A-16)."""
    windows: dict[str, int] = {}
    for name in RETENTION:
        retention = catalog.metrics[name].retention
        assert retention is not None
        windows[name] = retention.window_days
    assert windows == {
        "retention_rate_d1": 1,
        "retention_rate_d7": 7,
        "retention_rate_d30": 30,
    }


@pytest.mark.parametrize("name", RETENTION)
def test_all_three_externally_authored_fields_are_unset(catalog: LoadedCatalog, name: str) -> None:
    retention = catalog.metrics[name].retention
    assert retention is not None
    for field in EXTERNALLY_AUTHORED_FIELDS:
        assert getattr(retention, field) is None, f"{name}.{field} was supplied — D-8/D-9 are open"
    assert retention.unset_required_fields() == EXTERNALLY_AUTHORED_FIELDS
    assert not retention.is_publishable


@pytest.mark.parametrize("name", RETENTION)
def test_each_derives_as_pending_naming_its_unset_fields(catalog: LoadedCatalog, name: str) -> None:
    state = derive_lifecycle(
        catalog.metrics[name],
        owner_known=True,
        publication_eligible=True,  # isolate the retention cause from the D-1 cause
    )
    assert state.lifecycle is Lifecycle.PENDING
    assert state.missing_fields == EXPECTED_UNSET
    assert PendingReason.REQUIRED_FIELDS_UNSET in state.reasons
    assert not state.is_requestable


@pytest.mark.parametrize("name", RETENTION)
@pytest.mark.parametrize("supplied", EXTERNALLY_AUTHORED_FIELDS)
def test_supplying_only_some_fields_still_yields_pending(
    catalog: LoadedCatalog,
    name: str,
    supplied: str,
) -> None:
    """A partial default is still a default. Two of three is still pending."""
    metric: Metric = catalog.metrics[name]
    assert metric.retention is not None
    value = "America/Sao_Paulo" if supplied == "cohort_timezone" else "Valor inventado."
    patched = metric.model_copy(
        update={"retention": metric.retention.model_copy(update={supplied: value})}
    )
    state = derive_lifecycle(patched, owner_known=True, publication_eligible=True)
    assert state.lifecycle is Lifecycle.PENDING
    assert len(state.missing_fields) == 2
    assert f"retention.{supplied}" not in state.missing_fields


@pytest.mark.parametrize("name", RETENTION)
def test_only_the_complete_set_would_publish(catalog: LoadedCatalog, name: str) -> None:
    """Proves the guard is not vacuous — the mechanism does flip when authored.

    The values here exist for the length of this assertion and are never written
    to the catalog. Authoring them for real is D-8 / D-9 and belongs to T108.
    """
    metric: Metric = catalog.metrics[name]
    assert metric.retention is not None
    patched = metric.model_copy(
        update={
            "retention": metric.retention.model_copy(
                update={
                    "cohort_timezone": "America/Sao_Paulo",
                    "eligible_event": "Evento hipotético de teste.",
                    "identity_rule": "Regra hipotética de teste.",
                }
            )
        }
    )
    state = derive_lifecycle(patched, owner_known=True, publication_eligible=True)
    assert state.lifecycle is Lifecycle.PUBLISHED
    assert state.missing_fields == ()


def test_in_the_real_catalog_all_three_are_pending_today(catalog: LoadedCatalog) -> None:
    """SC-020 over the authored tree, with the real D-1 state in play."""
    # ADR 0033: a commit PER SOURCE. The fixture is not in Git, so every source is
    # given the same one -- which is what this node always meant by one commit.
    states = derive_lifecycles(
        catalog,
        source_commits=dict.fromkeys(catalog.sources, "0000000"),
        on=date(2026, 8, 11),
    )
    for name in RETENTION:
        state = states[name]
        assert state.lifecycle is Lifecycle.PENDING
        assert state.missing_fields == EXPECTED_UNSET
        assert PendingReason.REQUIRED_FIELDS_UNSET in state.reasons
        assert PendingReason.SOURCE_NOT_APPROVED in state.reasons
    assert not any(s.is_published for s in states.values())
