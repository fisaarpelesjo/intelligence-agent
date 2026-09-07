"""Absent-data-revision tests — T079 (FR-066, FR-068; quickstart Scenario 17).

Evidence: a missing revision yields ``REPRODUCIBILITY_LIMITED``, and autonomous
publication is denied.

The distinction this suite exists to hold: a decision with limited
reproducibility is not *wrong*. It may be read, cited and acted on by a person.
What it may not do is be published autonomously, because nobody could reproduce
it later and an unreproducible published number is a claim no one can check.

An **unstable** revision is treated exactly like an absent one, and is worse in
practice: the producer reported an identifier it cannot guarantee, so the answer
looks reproducible and is not.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode, outcome_for
from semantic_catalog.provenance.revision import (
    DataRevision,
    RevisionSnapshot,
    load_revisions,
    resolve_revisions,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "revisions"
MAY = (date(2026, 5, 1), date(2026, 5, 31))


def _resolve(fixture: str | None, sources: tuple[str, ...] = ("store_a",)):  # type: ignore[no-untyped-def]
    snapshot = load_revisions(FIXTURES / fixture) if fixture else None
    return resolve_revisions(sources, snapshot, period_start=MAY[0], period_end=MAY[1])


# --- absent and unstable ----------------------------------------------------


def test_no_snapshot_at_all_leaves_every_source_missing() -> None:
    """A caller that supplied nothing has proven nothing."""
    resolution = _resolve(None)
    assert resolution.missing_sources == ("store_a",)
    assert not resolution.is_reproducible
    assert resolution.limitation_code is ReasonCode.REPRODUCIBILITY_LIMITED


def test_an_absent_revision_yields_limited_reproducibility() -> None:
    resolution = _resolve("absent.yaml")
    assert resolution.revision_ids == ()
    assert resolution.missing_sources == ("store_a",)
    assert resolution.limitation_code is ReasonCode.REPRODUCIBILITY_LIMITED


def test_an_unstable_revision_is_treated_as_absent() -> None:
    """Reported but not durable. It looks reproducible, which is the danger."""
    resolution = _resolve("unstable.yaml")
    assert resolution.revision_ids == ()
    assert resolution.unstable_sources == ("store_a",)
    assert not resolution.is_reproducible


@pytest.mark.parametrize("fixture", ["absent.yaml", "unstable.yaml", None])
def test_autonomous_publication_is_denied_without_a_stable_revision(
    fixture: str | None,
) -> None:
    """FR-068, stated as the property the code must hold."""
    assert not _resolve(fixture).permits_autonomous_publication


def test_the_limitation_code_is_a_caveat_not_a_refusal() -> None:
    """The answer may be read; it may not be auto-published."""
    assert outcome_for(ReasonCode.REPRODUCIBILITY_LIMITED) is Outcome.ALLOW_WITH_CAVEAT


def test_a_stable_revision_permits_publication() -> None:
    """Proves the guard is not vacuous."""
    resolution = _resolve("rev6.yaml")
    assert resolution.revision_ids == ("store_a@rev6",)
    assert resolution.is_reproducible
    assert resolution.permits_autonomous_publication
    assert resolution.limitation_code is None


def test_one_unstable_source_limits_the_whole_answer() -> None:
    """Partial evidence is not evidence for the answer as a whole."""
    resolution = resolve_revisions(
        ("app_a", "store_a"),
        load_revisions(FIXTURES / "one_unstable.yaml"),
        period_start=MAY[0],
        period_end=MAY[1],
    )
    assert resolution.unstable_sources == ("store_a",)
    assert not resolution.permits_autonomous_publication


# --- restatements -----------------------------------------------------------


def test_a_restatement_is_reported_for_the_period_it_touches() -> None:
    resolution = _resolve("rev7.yaml")
    assert resolution.restatement_code is ReasonCode.PERIOD_RESTATED
    assert [r.data_revision_id for r in resolution.restatements] == ["store_a@rev7"]


def test_a_restatement_outside_the_period_is_not_reported() -> None:
    snapshot = load_revisions(FIXTURES / "rev7.yaml")
    resolution = resolve_revisions(
        ("store_a",), snapshot, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31)
    )
    assert resolution.restatements == ()
    assert resolution.restatement_code is None
    assert resolution.is_reproducible, "an untouched restatement does not limit anything"


def test_a_restatement_names_its_predecessor_without_rewriting_it() -> None:
    """The link is additive and one-directional (FR-067)."""
    earlier = load_revisions(FIXTURES / "rev6.yaml").for_source("store_a")
    later = load_revisions(FIXTURES / "rev7.yaml").for_source("store_a")
    assert earlier is not None and later is not None
    assert later.supersedes_revision_id == earlier.data_revision_id
    assert earlier.supersedes_revision_id is None
    assert earlier.data_revision_id != later.data_revision_id


def test_a_restatement_must_state_a_reason() -> None:
    with pytest.raises(ValidationError, match="no stated reason"):
        DataRevision(
            data_revision_id="x@1",
            source="store_a",
            revised_at=datetime(2026, 6, 15),
            restates_from=date(2026, 5, 1),
            restates_to=date(2026, 5, 31),
        )


def test_half_a_restatement_window_is_refused() -> None:
    with pytest.raises(ValidationError, match="half a restatement window"):
        DataRevision(
            data_revision_id="x@1",
            source="store_a",
            revised_at=datetime(2026, 6, 15),
            restates_from=date(2026, 5, 1),
        )


def test_a_reversed_restatement_window_is_refused() -> None:
    with pytest.raises(ValidationError, match="ending before it starts"):
        DataRevision(
            data_revision_id="x@1",
            source="store_a",
            revised_at=datetime(2026, 6, 15),
            reason="Motivo.",
            restates_from=date(2026, 5, 31),
            restates_to=date(2026, 5, 1),
        )


# --- snapshot integrity -----------------------------------------------------


def test_two_revisions_for_one_source_are_refused() -> None:
    """Which one an answer stood on must not depend on ordering."""
    with pytest.raises(ValidationError, match="two revisions for the same source"):
        RevisionSnapshot(
            observed_at=datetime(2026, 8, 11),
            revisions=(
                DataRevision(
                    data_revision_id="a", source="store_a", revised_at=datetime(2026, 8, 11)
                ),
                DataRevision(
                    data_revision_id="b", source="store_a", revised_at=datetime(2026, 8, 11)
                ),
            ),
        )


def test_a_fixture_can_never_claim_production_readiness() -> None:
    for path in sorted(FIXTURES.glob("*.yaml")):
        assert load_revisions(path).is_fixture, path.name


def test_revision_ids_are_sorted_for_a_stable_answer() -> None:
    resolution = resolve_revisions(
        ("store_a", "app_a"),
        load_revisions(FIXTURES / "both_stable.yaml"),
        period_start=MAY[0],
        period_end=MAY[1],
    )
    assert resolution.revision_ids == ("app_a@rev3", "store_a@rev8")
