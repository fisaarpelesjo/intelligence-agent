"""Projection leakage — T047 (FR-002, FR-018; quickstart Scenario 2).

The round-trip assertion the contract calls for: serialise the public bundle,
grep it for every draft value present in the internal projection, require zero
hits.

This is a **round-trip over the real catalog**, not a shape check. A shape check
asks "does the stub have the right keys"; this asks "is that draft sentence
anywhere in the bytes we would ship". The second question is the one that catches
a field leaking through a nested structure, a repr, a serialiser default or a
future refactor that swaps allowlist construction for filtering.

Every metric in the catalog is pending today (D-1 open, D-8 open), so every draft
definition in the tree is a value that must not appear.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.loader.bundle import Bundle, build_bundle, serialise_public
from semantic_catalog.loader.projection import PendingStub

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[4]
SEMANTIC = REPO / "semantic"
COMMIT = "0000000"
ON = date(2026, 8, 11)

#: Keys that must never appear in a serialised pending projection, whatever the
#: value. Names alone leak shape, and shape invites the next field.
FORBIDDEN_KEYS = (
    "calculation_basis",
    "numerator",
    "denominator",
    "aggregation",
    "additivity",
    "grain",
    "unit",
    "time_dimension",
    "source_view",
    "exclusions",
    "allowed_dimensions",
    "source_availability",
    "available_from",
    "reason_code",
    "review_trigger",
    "retention",
    "cohort_timezone",
    "eligible_event",
    "identity_rule",
    "versions",
    "synonyms",
    "deprecation",
    "limitations",
    "description",
)


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        SEMANTIC,
        current_commit=COMMIT,
        on=ON,
        source_commits={"subscription_daily": COMMIT},
    )


@pytest.fixture(scope="module")
def serialised(bundle: Bundle) -> str:
    return serialise_public(bundle.public)


def test_every_metric_is_pending_in_this_release(bundle: Bundle) -> None:
    """Precondition. If this changes, the leakage surface changes with it."""
    # TWELVE since 2026-08-26 -- `new_trials` joined, and it is pending like the
    # rest because its source carries no approval.
    #: RE-DERIVADO em 2026-08-30: era `== 12`, e o numero moveu para 31 com a `T829`. O que
    #: se afirma e a COBERTURA -- a projecao publica carrega uma entrada por metrica --, e
    #: isso vale em qualquer contagem.
    assert bundle.public, "the public projection is empty; it would leak nothing by leaking"
    assert len(bundle.public) == len(bundle.internal.metrics)
    assert all(isinstance(p, PendingStub) for p in bundle.public.values())


def test_no_draft_value_survives_serialisation(bundle: Bundle, serialised: str) -> None:
    """The round trip: every draft string in the internal projection, grepped."""
    leaked: list[str] = []
    for name, metric in bundle.internal.metrics.items():
        drafts: list[str] = []
        for version in metric.versions:
            drafts += [
                version.calculation_basis,
                version.grain,
                str(version.source_view),
                version.content.description,
                *version.content.limitations,
                *version.exclusions,
            ]
            if version.numerator:
                drafts.append(version.numerator)
            if version.denominator:
                drafts.append(version.denominator)
        if metric.retention is not None:
            drafts += [metric.retention.numerator, metric.retention.denominator]
        for draft in drafts:
            if draft and draft in serialised:
                leaked.append(f"{name}: {draft[:60]!r}")

    assert not leaked, f"draft values present in the public bundle: {leaked}"


def test_no_availability_claim_is_made_about_a_pending_metric(serialised: str) -> None:
    """An availability claim on an unapproved definition is still a claim."""
    for source_id in (
        "android_app",
        "ios_app",
        "website",
        "google_play",
        "apple_app_store",
        "galaxy_store",
    ):
        assert source_id not in serialised, source_id
    assert "IDENTITY_RULE_UNSATISFIABLE" not in serialised


def test_no_forbidden_key_appears_anywhere_in_the_public_bundle(serialised: str) -> None:
    present = [key for key in FORBIDDEN_KEYS if f'"{key}"' in serialised]
    assert not present, f"forbidden keys serialised: {present}"


def test_the_stub_carries_exactly_the_allowlisted_keys(bundle: Bundle) -> None:
    """Six fields maximum, and only the three unconditional ones today."""
    allowed = {
        "name",
        "status",
        "missing_fields",
        "public_name",
        "owner",
        "expected_available_from",
    }
    for name, stub in bundle.public.items():
        keys = set(stub.to_public_dict())
        assert keys <= allowed, f"{name}: unexpected keys {sorted(keys - allowed)}"
        assert {"name", "status", "missing_fields"} <= keys, name


def test_missing_fields_lists_names_never_draft_values(bundle: Bundle) -> None:
    for window in (1, 7, 30):
        stub = bundle.public[f"retention_rate_d{window}"]
        assert isinstance(stub, PendingStub)
        assert stub.missing_fields == (
            "retention.cohort_timezone",
            "retention.eligible_event",
            "retention.identity_rule",
        )


def test_unapproved_public_name_is_absent_not_null(bundle: Bundle, serialised: str) -> None:
    """No approval exists, so the key must not be written at all."""
    assert '"public_name"' not in serialised
    assert '"expected_available_from"' not in serialised
    for name, metric in bundle.internal.metrics.items():
        for version in metric.versions:
            assert version.content.label not in serialised, f"{name}: label leaked"


def test_the_release_id_is_stable_and_content_addressed() -> None:
    """Same content, same id — a rebuild is provably a no-op."""
    first = build_bundle(
        SEMANTIC,
        current_commit=COMMIT,
        on=ON,
        source_commits={"subscription_daily": COMMIT},
    )
    second = build_bundle(
        SEMANTIC,
        current_commit="ffffff9",
        on=ON,
        source_commits={"subscription_daily": "ffffff9"},
    )
    assert first.release_id == second.release_id
    assert first.release_id.startswith("sha256:")
