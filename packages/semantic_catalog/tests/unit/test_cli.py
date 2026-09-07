"""Steward CLI — T096 (SC-011; library-and-cli-contract §2).

Three things are proved here, and the third is the one that matters most:

**Exit codes are stable and mean different things.** ``0`` passed, ``1`` the
catalog is wrong, ``2`` the invocation is wrong. CI reads these; collapsing 1
and 2 would leave it unable to tell a bad catalog from a broken pipeline.

**Output is deterministic and machine-readable where specified.** The same
invocation twice produces the same bytes, and ``--format json`` parses.

**No command writes catalog content.** Asserted by running every read command
against a copied tree and comparing the bytes before and after — not by reading
the source and trusting it.
"""

from __future__ import annotations

import filecmp
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from semantic_catalog.cli.main import EXIT_INVOCATION, EXIT_OK, EXIT_VIOLATION, build_parser, main

REPO = Path(__file__).resolve().parents[4]
PRODUCTION = REPO / "semantic"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VERSIONED = FIXTURES / "versioned_catalog" / "catalog"
VERSIONED_FRESHNESS = FIXTURES / "versioned_catalog" / "freshness.yaml"
COVERAGE = FIXTURES / "coverage" / "observed.yaml"
ON = "2026-08-11"


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _json(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, Any]:
    code, out, _ = _run(capsys, *argv)
    return code, json.loads(out)


# --- exit codes -------------------------------------------------------------


def test_a_clean_catalog_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "validate", "--path", str(PRODUCTION), "--on", ON)
    assert code == EXIT_OK
    assert "OK" in out


def test_a_violation_exits_one(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """A catalog problem the steward must fix — not a broken invocation."""
    root = tmp_path / "semantic"
    shutil.copytree(PRODUCTION, root)
    owners = root / "owners.yaml"
    owners.write_text(
        owners.read_text(encoding="utf-8").replace("id: product_analytics", "id: renamed_team"),
        encoding="utf-8",
    )
    code, out, _ = _run(capsys, "validate", "--path", str(root), "--on", ON)
    assert code == EXIT_VIOLATION
    assert "FAIL" in out


@pytest.mark.parametrize(
    "argv",
    [
        ("validate", "--path", "no/such/directory"),
        ("explain", "active_users", "--on", "not-a-date"),
        ("check", "active_users", "--from", "2026-07-31", "--to", "2026-07-01"),
        (
            "check",
            "active_users",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--freshness",
            "no/such/file.yaml",
        ),
        ("compliance", "--coverage", "no/such/file.yaml"),
        ("schema", "export", "--check", "--out", "no/such/directory"),
        ("release", "status", "--ledger", "no/such/dir/ledger.json", "--format", "bogus"),
        ("bogus-command",),
    ],
)
def test_a_bad_invocation_exits_two(
    capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    assert main(list(argv)) == EXIT_INVOCATION
    capsys.readouterr()


def test_a_malformed_catalog_fails_closed(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Unparseable governed content is a **violation**, not a usage error.

    L1 exists to turn an unloadable file into a finding rather than an
    exception, and the contract classifies exit 1 as "violations" against exit 2
    as "usage error". A steward whose YAML does not parse has a catalog to fix.
    The full matrix lives in ``test_cli_exit_codes.py``.
    """
    root = tmp_path / "semantic"
    shutil.copytree(PRODUCTION, root)
    (root / "metrics" / "downloads.yaml").write_text("kind: [not, a, mapping\n", encoding="utf-8")
    code, out, err = _run(capsys, "validate", "--path", str(root), "--on", ON)
    assert code == EXIT_VIOLATION
    assert "downloads.yaml" in out, out
    assert "Traceback" not in out + err


# --- no command writes catalog content --------------------------------------


_READ_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("validate", "--on", ON),
    ("validate", "--on", ON, "--strict", "--check-schema-version"),
    ("validate", "--on", ON, "--release"),
    ("explain", "active_users", "--on", ON),
    ("check", "active_users", "--from", "2026-07-01", "--to", "2026-07-31", "--on", ON),
    ("matrix", "--on", ON),
    ("compliance", "--on", ON),
    ("leakage-scan", "--on", ON),
)


def test_no_read_command_writes_catalog_content(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Authoring is editing YAML and opening a pull request (R-1, FR-037).

    Proved by comparing the tree byte-for-byte before and after, rather than by
    reading the code and believing it.
    """
    root = tmp_path / "semantic"
    reference = tmp_path / "reference"
    shutil.copytree(PRODUCTION, root)
    shutil.copytree(PRODUCTION, reference)

    for argv in _READ_COMMANDS:
        main([argv[0], *argv[1:], "--path", str(root)])
        capsys.readouterr()

    comparison = filecmp.dircmp(str(root), str(reference))
    assert not comparison.diff_files, comparison.diff_files
    assert not comparison.left_only and not comparison.right_only
    for sub in comparison.subdirs.values():
        assert not sub.diff_files, sub.diff_files
        assert not sub.left_only and not sub.right_only


# --- determinism and machine-readability ------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ("validate", "--on", ON, "--format", "json"),
        ("explain", "active_users", "--on", ON, "--format", "json"),
        (
            "check",
            "active_users",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--on",
            ON,
            "--evaluated-at",
            "2026-08-11T06:00:00Z",
            "--format",
            "json",
        ),
        ("compliance", "--on", ON, "--format", "json"),
        ("leakage-scan", "--on", ON, "--format", "json"),
        ("schema", "export", "--check", "--out", str(REPO / "schemas"), "--format", "json"),
    ],
)
def test_json_output_parses_and_is_deterministic(
    capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    """Byte-identical across runs. `check` needs `--evaluated-at`, because the
    stamp on a decision is a real instant and is not derived from `--on`."""
    extra = () if argv[0] == "schema" else ("--path", str(PRODUCTION))
    first_code, first, _ = _run(capsys, *argv, *extra)
    second_code, second, _ = _run(capsys, *argv, *extra)
    assert first_code == second_code
    assert first == second, "the same invocation produced different bytes"
    json.loads(first)


def test_pt_br_content_survives_the_json_round_trip(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """FR-055: the governed wording is printed, never escaped into noise."""
    code, payload = _json(
        capsys,
        "check",
        "active_users",
        "--from",
        "2026-07-01",
        "--to",
        "2026-07-31",
        "--on",
        ON,
        "--path",
        str(PRODUCTION),
        "--format",
        "json",
    )
    assert code == EXIT_VIOLATION
    message = payload["message_pt_br"]
    assert "métrica" in message, message
    assert "\\u" not in json.dumps(payload, ensure_ascii=False)


# --- the commands themselves ------------------------------------------------


def test_explain_reports_a_pending_metric_by_field_name_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """FR-018: name the gap, never show the draft."""
    _, payload = _json(
        capsys, "explain", "active_users", "--on", ON, "--path", str(PRODUCTION), "--format", "json"
    )
    assert payload["lifecycle"] == "pending"
    assert "calculation_basis" not in json.dumps(payload["public_projection"])
    assert payload["pending_reasons"] == ["source_not_approved"]


def test_explain_resolves_as_of_the_requested_date(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for on, expected in (("2025-06-30", "fixture_metric@1"), ("2025-08-01", "fixture_metric@2")):
        _, payload = _json(
            capsys,
            "explain",
            "fixture_metric",
            "--on",
            on,
            "--path",
            str(VERSIONED),
            "--commit",
            "fixture0",
            # ADR 0033: the caller states the content commit, because only the caller
            # knows this catalog is a fixture rather than a Git tree. `fixture0` is what
            # its own approval names, so the binding is satisfied honestly instead of
            # being weakened to let a fixture through.
            "--source-commit",
            "fixture_source=fixture0",
            "--format",
            "json",
        )
        assert payload["metric_version_id"] == expected


def test_explain_refuses_an_ungoverned_metric(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "explain", "nao_existe", "--on", ON, "--path", str(PRODUCTION))
    assert code == EXIT_VIOLATION
    assert "not governed" in out


def test_check_prints_the_decision_and_denies_on_a_denial(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = _run(
        capsys,
        "check",
        "active_users",
        "--from",
        "2026-07-01",
        "--to",
        "2026-07-31",
        "--on",
        ON,
        "--path",
        str(PRODUCTION),
    )
    assert code == EXIT_VIOLATION
    assert "DENY / METRIC_PENDING" in out
    assert "decision  sha256:" in out


def test_check_allows_a_healthy_request_against_the_fixture_catalog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = _run(
        capsys,
        "check",
        "fixture_metric",
        "--sources",
        "fixture_source",
        "--from",
        "2025-02-01",
        "--to",
        "2025-03-31",
        "--access",
        "standard",
        "--on",
        ON,
        "--path",
        str(VERSIONED),
        "--commit",
        "fixture0",
        # ADR 0033: the caller states the content commit, because only the caller
        # knows this catalog is a fixture rather than a Git tree. `fixture0` is what
        # its own approval names, so the binding is satisfied honestly instead of
        # being weakened to let a fixture through.
        "--source-commit",
        "fixture_source=fixture0",
        "--freshness",
        str(VERSIONED_FRESHNESS),
    )
    assert code == EXIT_OK
    assert "ALLOW / REQUEST_ALLOWED" in out


def test_check_reports_segments_for_a_range_crossing_a_definition_change(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, payload = _json(
        capsys,
        "check",
        "fixture_metric",
        "--sources",
        "fixture_source",
        "--from",
        "2025-06-01",
        "--to",
        "2025-08-31",
        "--access",
        "standard",
        "--on",
        ON,
        "--path",
        str(VERSIONED),
        "--commit",
        "fixture0",
        # ADR 0033: the caller states the content commit, because only the caller
        # knows this catalog is a fixture rather than a Git tree. `fixture0` is what
        # its own approval names, so the binding is satisfied honestly instead of
        # being weakened to let a fixture through.
        "--source-commit",
        "fixture_source=fixture0",
        "--freshness",
        str(VERSIONED_FRESHNESS),
        "--format",
        "json",
    )
    assert payload["reason_code"] == "SPANS_DEFINITION_CHANGE"
    assert [s["metric_version_id"] for s in payload["segments"]] == [
        "fixture_metric@1",
        "fixture_metric@2",
    ]


@pytest.mark.parametrize("fmt", ["md", "csv", "json"])
def test_matrix_exports_every_declared_format(capsys: pytest.CaptureFixture[str], fmt: str) -> None:
    code, out, _ = _run(
        capsys,
        "matrix",
        "--on",
        ON,
        "--path",
        str(VERSIONED),
        "--commit",
        "fixture0",
        # ADR 0033: the caller states the content commit, because only the caller
        # knows this catalog is a fixture rather than a Git tree. `fixture0` is what
        # its own approval names, so the binding is satisfied honestly instead of
        # being weakened to let a fixture through.
        "--source-commit",
        "fixture_source=fixture0",
        "--access",
        "standard",
        "--freshness",
        str(VERSIONED_FRESHNESS),
        "--format",
        fmt,
    )
    assert code == EXIT_OK
    assert "metric_id" in out
    if fmt == "json":
        assert json.loads(out)["rows"]


def test_matrix_is_empty_without_observed_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No snapshot means no evidence, and an unevidenced surface is empty."""
    _, payload = _json(
        capsys,
        "matrix",
        "--on",
        ON,
        "--path",
        str(VERSIONED),
        "--commit",
        "fixture0",
        # ADR 0033: the caller states the content commit, because only the caller
        # knows this catalog is a fixture rather than a Git tree. `fixture0` is what
        # its own approval names, so the binding is satisfied honestly instead of
        # being weakened to let a fixture through.
        "--source-commit",
        "fixture_source=fixture0",
        "--access",
        "standard",
        "--format",
        "json",
    )
    assert payload["rows"] == []


def test_schema_check_detects_drift(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "schemas"
    shutil.copytree(REPO / "schemas", target)
    drifted = target / "metric.schema.json"
    drifted.write_text(
        drifted.read_text(encoding="utf-8").replace('"title"', '"tampered"', 1), encoding="utf-8"
    )
    code, out, _ = _run(capsys, "schema", "export", "--check", "--out", str(target))
    assert code == EXIT_VIOLATION
    assert "DRIFT" in out
    assert "never hand-edit" in out


def test_schema_export_writes_only_to_the_named_directory(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "generated"
    code, _, _ = _run(capsys, "schema", "export", "--out", str(target))
    assert code == EXIT_OK
    assert sorted(p.name for p in target.glob("*.json")) == sorted(
        p.name for p in (REPO / "schemas").glob("*.json")
    )


def test_diff_against_head_reports_no_change_on_a_clean_tree(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Also a regression guard: pt-BR content must decode as UTF-8.

    Decoding ``git show`` with the platform codec mangles every accent, and the
    version gate then demands a bump on every metric whose calculation_basis
    contains one.
    """
    code, out, _ = _run(
        capsys, "diff", "--base", "HEAD", "--repo", str(REPO), "--path", str(PRODUCTION)
    )
    assert code == EXIT_OK
    assert "no Semantic-class change" in out


def test_diff_states_whether_the_base_carried_a_catalog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ "Nothing changed" and "there was nothing to compare to" both exit 0.

    A consumer that cannot tell them apart cannot tell an enforced version gate
    from a skipped one, so the distinction is a field rather than an inference
    from an empty change list. See tests/integration/test_diff_bootstrap.py for
    the bootstrap side.
    """
    code, payload = _json(
        capsys,
        "diff",
        "--base",
        "HEAD",
        "--repo",
        str(REPO),
        "--path",
        str(PRODUCTION),
        "--format",
        "json",
    )
    assert code == EXIT_OK
    assert payload["base_catalog_present"] is True
    assert payload["bootstrap"] is False


def test_diff_rejects_a_base_ref_that_does_not_resolve(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2: the call is wrong. Never 0 by way of "the base had no catalog"."""
    code, _, _ = _run(
        capsys,
        "diff",
        "--base",
        "refs/heads/no-such-branch-here",
        "--repo",
        str(REPO),
        "--path",
        str(PRODUCTION),
    )
    assert code == EXIT_INVOCATION


def test_the_cli_exposes_no_sql_and_no_warehouse_access() -> None:
    """The library holds no credentials; the CLI must not acquire any."""
    source = (
        Path(__file__).resolve().parents[2] / "src" / "semantic_catalog" / "cli" / "main.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "bigquery",
        "google.cloud",
        "--sql",
        "execute_query",
        "psycopg",
        "sqlalchemy",
    ):
        assert forbidden not in source.lower(), forbidden


def test_every_subcommand_in_the_contract_exists() -> None:
    parser = build_parser()
    subparsers = parser._subparsers
    assert subparsers is not None
    choices = next(a.choices for a in subparsers._group_actions if a.choices)
    commands = set(choices)
    assert {
        "validate",
        "explain",
        "check",
        "matrix",
        "diff",
        "compliance",
        "schema",
        "release",
    } <= commands
