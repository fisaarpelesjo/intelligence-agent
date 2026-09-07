"""Compliance report and leakage scan — T097, T098 (FR-032, FR-041; SC-001, SC-013).

SC-001 is the claim that **zero published entries are non-compliant**. A pending
metric with unset fields is not a violation — it is the lifecycle working — so
the report separates the two and the assertion is about the published set.

SC-013 is proved by the scan, not by scenario execution. Each category is fired
deliberately against a synthetic blob, because a scan whose patterns nobody has
seen match is a scan that reports clean for the wrong reason.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.compliance.leakage_scan import (
    GOVERNED_IDENTIFIERS,
    LeakCategory,
    scan_paths,
    scan_payload,
    scan_repository,
    scan_text,
)
from semantic_catalog.compliance.report import FIXTURE_LIMITATION, compliance_report
from semantic_catalog.loader.bundle import build_bundle, load_catalog, serialise_public
from semantic_catalog.validation.l3_reconciliation import (
    ObservedCoverageSet,
    load_observed_coverage,
)

REPO = Path(__file__).resolve().parents[4]
PRODUCTION = REPO / "semantic"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VERSIONED = FIXTURES / "versioned_catalog" / "catalog"
COVERAGE = FIXTURES / "coverage" / "observed.yaml"
ON = date(2026, 8, 11)


@pytest.fixture(scope="module")
def observed() -> ObservedCoverageSet:
    return load_observed_coverage(COVERAGE)


# --- T097: compliance -------------------------------------------------------


def test_a_clean_tree_has_zero_non_compliant_published_entries(
    observed: ObservedCoverageSet,
) -> None:
    """SC-001, stated exactly: about published entries, not about pending ones."""
    report = compliance_report(
        PRODUCTION,
        current_commit="head",
        on=ON,
        coverage=observed,
        codeowners=REPO / ".github" / "CODEOWNERS",
    )
    assert report.published_non_compliant == ()
    assert report.is_compliant()


def test_pending_metrics_are_reported_but_not_non_compliant(
    observed: ObservedCoverageSet,
) -> None:
    report = compliance_report(PRODUCTION, current_commit="head", on=ON, coverage=observed)
    # TWELVE since 2026-08-26. Pending, not non-compliant: the distinction this
    # test exists for is unaffected by the count.
    #: RE-DERIVADO em 2026-08-30: era `== 12` e foi para 31 com a `T829`. A propriedade e
    #: que TODA metrica aparece como pendente e nenhuma como nao-conforme.
    assert report.pending, "nothing was reported as pending; the report measured nothing"
    assert {entry.identifier for entry in report.pending if entry.kind == "metric"} == set(
        load_catalog(PRODUCTION).metrics
    ), "the pending set and the catalog disagree on which metrics exist"
    assert all(entry.compliant for entry in report.pending)


def test_the_report_names_unset_fields_never_their_values() -> None:
    """FR-018. Naming the gap is the point; showing the draft would defeat it."""
    report = compliance_report(PRODUCTION, current_commit="head", on=ON)
    retention = next(e for e in report.entries if e.identifier == "retention_rate_d1")
    assert retention.lifecycle == "pending"
    rendered = " ".join(report.render())
    assert "calculation_basis" not in rendered
    for name in retention.missing_fields:
        assert name.startswith("retention."), name


def test_an_unresolvable_owner_makes_a_published_entry_non_compliant(tmp_path: Path) -> None:
    root = tmp_path / "semantic"
    shutil.copytree(PRODUCTION, root)
    owners = root / "owners.yaml"
    owners.write_text(
        owners.read_text(encoding="utf-8").replace("id: product_analytics", "id: renamed_team"),
        encoding="utf-8",
    )
    report = compliance_report(root, current_commit="head", on=ON)
    assert not report.is_compliant()
    assert any(e.identifier == "active_users" and not e.compliant for e in report.entries)


def test_a_fixture_backed_run_states_the_limitation(observed: ObservedCoverageSet) -> None:
    """A green report is not a statement about production until EXT-A is ready."""
    report = compliance_report(PRODUCTION, current_commit="head", on=ON, coverage=observed)
    assert report.observed_is_fixture
    assert FIXTURE_LIMITATION in report.limitations
    assert any(FIXTURE_LIMITATION in line for line in report.render())


def test_a_run_with_no_observation_says_it_reconciled_nothing() -> None:
    """Silence about a missing reconciliation reads as 'reconciled and clean'."""
    report = compliance_report(PRODUCTION, current_commit="head", on=ON)
    assert not report.reconciled
    assert any(
        "not reconciled" in text or "nothing to reconcile" in text or "was not reconciled" in text
        for text in report.limitations
    ), report.limitations


def test_the_machine_readable_form_is_stable(observed: ObservedCoverageSet) -> None:
    first = compliance_report(PRODUCTION, current_commit="head", on=ON, coverage=observed).to_dict()
    second = compliance_report(
        PRODUCTION, current_commit="head", on=ON, coverage=observed
    ).to_dict()
    assert first == second
    assert first["counts"]["published_non_compliant"] == 0


def test_a_failing_validation_makes_the_report_non_compliant(tmp_path: Path) -> None:
    """A clean entry list beside a failing layer would report a broken catalog
    as compliant."""
    root = tmp_path / "semantic"
    shutil.copytree(PRODUCTION, root)
    messages = root / "content" / "reason-messages.pt-BR.yaml"
    text = messages.read_text(encoding="utf-8")
    head, _, tail = text.partition("  - reason_code: RELEASE_WITHDRAWN")
    messages.write_text(head + tail.split("\n\n", 1)[-1], encoding="utf-8")
    report = compliance_report(root, current_commit="head", on=ON)
    assert not report.is_compliant()
    assert any("publishable_code_without_message" in line for line in report.validation.render())


# --- T098: leakage ----------------------------------------------------------


@pytest.mark.parametrize(
    ("category", "blob"),
    [
        (LeakCategory.FACT_ROW, '{"result_set": [{"day": "2026-07-01"}]}'),
        (LeakCategory.METRIC_VALUE, '{"value": 12345}'),
        (LeakCategory.DIRECT_PII, "owner: ana.silva@example.com"),
        (LeakCategory.DIRECT_PII, "requester: 123.456.789-00"),
        (LeakCategory.CREDENTIAL, "api_key: AKIAABCDEFGHIJKLMNOP"),
        (LeakCategory.CREDENTIAL, "authorization: Bearer abcdef123456"),
        (LeakCategory.PROMPT_TEXT, '{"question": "quantos usuarios ontem"}'),
        (LeakCategory.IDENTITY_CLAIM, '{"sub": "auth0|abc123"}'),
    ],
)
def test_every_category_fires(category: LeakCategory, blob: str) -> None:
    """A scan whose patterns nobody has seen match reports clean for the wrong
    reason."""
    hits = scan_text(blob, "probe")
    assert category in {hit.category for hit in hits}, [h.category.value for h in hits]


def test_a_finding_names_the_file_the_line_and_the_category() -> None:
    hits = scan_text("ok: 1\napi_key: AKIAABCDEFGHIJKLMNOP\n", "probe.yaml")
    assert hits
    hit = hits[0]
    assert hit.source == "probe.yaml"
    assert hit.line == 2
    assert hit.category is LeakCategory.CREDENTIAL
    assert "probe.yaml:2" in hit.render()


def test_a_suspected_secret_is_never_echoed_in_full() -> None:
    hits = scan_text("client_secret: " + "z" * 90, "probe")
    assert hits
    assert len(hits[0].redacted()) <= 24
    assert "z" * 90 not in hits[0].render()


def test_governed_identifiers_are_allowlisted() -> None:
    """The allowlist holds field names, never values."""
    for name in sorted(GOVERNED_IDENTIFIERS):
        assert not scan_text(f'{{"{name}": "opaque-value"}}', "probe"), name


def test_the_repository_is_clean() -> None:
    """SC-013. Zero hits across schemas, semantic, fixtures and the bundle."""
    bundle = build_bundle(
        PRODUCTION,
        current_commit="head",
        on=ON,
        source_commits={"subscription_daily": "head"},
    )
    report = scan_repository(
        REPO,
        public_bundle=serialise_public(bundle.public),
        pending_metrics=bundle.pending,
    )
    assert report.clean, [f.render() for f in report.findings]
    assert len(report.scanned) > 100


def test_the_scan_covers_every_declared_target() -> None:
    bundle = build_bundle(
        PRODUCTION,
        current_commit="head",
        on=ON,
        source_commits={"subscription_daily": "head"},
    )
    report = scan_repository(REPO, public_bundle=serialise_public(bundle.public))
    scanned = " ".join(report.scanned)
    assert "schemas/" in scanned
    assert "semantic/" in scanned
    assert "tests/fixtures" in scanned
    assert "public_bundle" in report.scanned


def test_a_draft_definition_in_the_public_bundle_is_a_leak() -> None:
    """The pending projection must not merely hide the definition — it must not
    write it (R-8).

    **The pending metric is now the one carrying the definition**, which is the
    property the rule is about. The earlier form of this test named `x` as pending
    while the leaked entry was `retention_rate_d1`, and passed because the scan looked
    for field NAMES anywhere in the bundle rather than inside a pending metric's entry.
    """
    leaked = '{"retention_rate_d1": {"calculation_basis": "rascunho"}}'
    report = scan_repository(
        REPO / "docs", public_bundle=leaked, pending_metrics=("retention_rate_d1",)
    )
    assert not report.clean
    assert LeakCategory.DRAFT_DEFINITION in {f.category for f in report.findings}


def test_anything_beyond_the_stub_is_a_leak_even_if_no_one_listed_the_field() -> None:
    """**Stricter than the field list**, and that is why the check is per entry.

    `DRAFT_FIELDS` names the definition fields somebody thought of. A pending metric's
    entry may hold the stub and nothing else, so a field nobody listed is caught too.
    """
    leaked = '{"sessions": {"name": "sessions", "status": "pending", "sql_text": "SELECT 1"}}'
    report = scan_repository(REPO / "docs", public_bundle=leaked, pending_metrics=("sessions",))
    assert not report.clean
    assert "sessions.sql_text" in {f.matched for f in report.findings}


def test_a_published_metric_s_definition_is_not_a_leak_beside_a_pending_one() -> None:
    """**The false positive this rule used to have, and it fired when the product worked.**

    The scan reported a leak whenever ANY metric was pending and ANY definition field
    name appeared anywhere in the bundle. That held while nothing was publishable; the
    first metric to reach `published` put its own legitimate definition into the public
    bundle and was reported as a draft leak.
    """
    bundle = (
        '{"new_trials": {"status": "published", "calculation_basis": "contagem", '
        '"source_availability": [{"source": "subscription_daily"}]}, '
        '"sessions": {"name": "sessions", "status": "pending", "missing_fields": []}}'
    )
    report = scan_repository(REPO / "docs", public_bundle=bundle, pending_metrics=("sessions",))
    assert LeakCategory.DRAFT_DEFINITION not in {f.category for f in report.findings}


def test_the_stub_field_list_still_equals_the_stub() -> None:
    """The copy in `leakage_scan` is measured against `PendingStub`, not trusted.

    A field added to the stub and not added here would be reported as a leak on every
    pending metric; a field REMOVED from the stub and left here would be permission by
    omission. Both are caught by comparing the two.
    """
    from dataclasses import fields

    from semantic_catalog.compliance.leakage_scan import PENDING_STUB_FIELDS
    from semantic_catalog.loader.projection import PendingStub

    assert {f.name for f in fields(PendingStub)} == PENDING_STUB_FIELDS


def test_a_clean_public_bundle_has_no_draft_findings() -> None:
    bundle = build_bundle(
        PRODUCTION,
        current_commit="head",
        on=ON,
        source_commits={"subscription_daily": "head"},
    )
    report = scan_payload(serialise_public(bundle.public), "public_bundle")
    assert report.clean


def test_scanning_an_empty_directory_scans_nothing_and_passes(tmp_path: Path) -> None:
    report = scan_paths(tmp_path)
    assert report.clean and report.scanned == ()
