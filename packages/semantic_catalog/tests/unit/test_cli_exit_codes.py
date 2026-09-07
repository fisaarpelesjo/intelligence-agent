"""CLI exit-code compliance — T096 (library-and-cli-contract §2, §4).

The contract pins three codes and one table row:

    | CLI exit codes | `0` clean, `1` violations, `2` usage error |

The line between 1 and 2 is **not** severity — it is whether the command got to
do its job:

``1``  the work was done and the answer is no: *governed, version-controlled
       content is wrong*. The catalog at any layer, the generated schemas, the
       governed readiness record, the release ledger's own integrity, a
       release-validation refusal, a governed decision denial.
``2``  the work never started: *the call is wrong*. Unknown subcommand, missing
       or invalid argument, a path that does not exist, or a caller-supplied
       evidence file that will not load.

**A catalog that will not parse is exit 1**, and that is the contract's answer
rather than a judgement call: ``validate_tree`` exists to turn an unloadable
file into a *finding* rather than an exception, precisely so a broken file is
reported instead of silently skipped. A steward whose YAML does not parse has a
violation to fix, not a command they typed wrong.

The matrix below is exhaustive across subcommands x failure categories. It is
built as data so a new subcommand that is not classified fails the coverage
test rather than quietly going unchecked.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path

import pytest

from semantic_catalog.cli.main import (
    EXIT_INVOCATION,
    EXIT_OK,
    EXIT_VIOLATION,
    build_parser,
    main,
)
from semantic_catalog.contracts._base import SCHEMA_VERSION

REPO = Path(__file__).resolve().parents[4]
PRODUCTION = REPO / "semantic"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
COVERAGE = FIXTURES / "coverage" / "observed.yaml"
READINESS = REPO / "docs" / "readiness" / "external-readiness.yaml"
ON = "2026-08-11"


class Category(StrEnum):
    """Every failure category the contract distinguishes."""

    # --- governed content: exit 1 ------------------------------------------
    MALFORMED_YAML = "malformed_yaml"
    UNKNOWN_KIND = "unknown_kind"
    UNSUPPORTED_VERSION = "unsupported_schema_version"
    SCHEMA_VIOLATION = "schema_violation"
    REFERENTIAL_FAILURE = "referential_failure"
    POLICY_FAILURE = "l4_policy_failure"
    VERSION_GATE_FAILURE = "l4_version_failure"
    RECONCILIATION_FAILURE = "l3_reconciliation_failure"
    SCHEMA_DRIFT = "schema_drift"
    READINESS_MALFORMED = "readiness_record_malformed"
    RELEASE_VALIDATION_REFUSAL = "release_validation_refusal"
    RELEASE_LEDGER_INVALID = "release_ledger_invalid"
    DECISION_DENIAL = "governed_decision_denial"

    # --- the call: exit 2 --------------------------------------------------
    UNKNOWN_COMMAND = "unknown_command"
    MISSING_ARGUMENT = "missing_argument"
    INVALID_ARGUMENT = "invalid_argument"
    NONEXISTENT_CATALOG_PATH = "nonexistent_catalog_path"
    NONEXISTENT_INPUT_FILE = "nonexistent_input_file"
    UNLOADABLE_CALLER_INPUT = "unloadable_caller_input"


GOVERNED = {
    Category.MALFORMED_YAML,
    Category.UNKNOWN_KIND,
    Category.UNSUPPORTED_VERSION,
    Category.SCHEMA_VIOLATION,
    Category.REFERENTIAL_FAILURE,
    Category.POLICY_FAILURE,
    Category.VERSION_GATE_FAILURE,
    Category.RECONCILIATION_FAILURE,
    Category.SCHEMA_DRIFT,
    Category.READINESS_MALFORMED,
    Category.RELEASE_VALIDATION_REFUSAL,
    Category.RELEASE_LEDGER_INVALID,
    Category.DECISION_DENIAL,
}
INVOCATION = set(Category) - GOVERNED

SUBCOMMANDS: tuple[str, ...] = (
    "validate",
    "explain",
    "check",
    "matrix",
    "diff",
    "compliance",
    "schema",
    "release",
    "leakage-scan",
)


# --- catalog mutations ------------------------------------------------------


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "semantic"
    shutil.copytree(PRODUCTION, root)
    return root


def _malformed(root: Path) -> None:
    (root / "metrics" / "sessions.yaml").write_text("kind: [broken\n", encoding="utf-8")


def _unknown_kind(root: Path) -> None:
    path = root / "metrics" / "sessions.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("kind: metric", "kind: nonsense"), encoding="utf-8"
    )


def _unsupported_version(root: Path) -> None:
    # ciclo 495: os yamls migraram a v2 -- a troca acompanha (e afirma que trocou, para a
    # fixture nunca mais produzir um catalogo valido em silencio quando a versao andar).
    #
    # ciclo 545: a troca passou a ser DERIVADA de `SCHEMA_VERSION` em vez de digitada, e o
    # motivo e que ela me pegou. O `D-1303` subiu o schema para 3, a fixture continuou
    # procurando o `2` literal, e o assert acima disparou em catorze casos -- exatamente o que
    # o comentario de 495 previu. Ele estava certo sobre o risco e errado sobre o remedio:
    # "a troca acompanha" e uma promessa que alguem tem de lembrar de cumprir. Derivada, ela
    # cumpre sozinha, e o assert continua de pe para o caso de a fixture perder o campo.
    path = root / "metrics" / "sessions.yaml"
    text = path.read_text(encoding="utf-8")
    current = f"catalog_schema_version: {SCHEMA_VERSION}"
    assert current in text, "a fixture perdeu o alvo da versao"
    path.write_text(text.replace(current, "catalog_schema_version: 99"), encoding="utf-8")


def _schema_violation(root: Path) -> None:
    path = root / "metrics" / "sessions.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("aggregation: sum", "aggregation: avarage"),
        encoding="utf-8",
    )


def _referential_failure(root: Path) -> None:
    path = root / "owners.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("id: product_analytics", "id: renamed_team"),
        encoding="utf-8",
    )


def _policy_failure(root: Path) -> None:
    """Drop a canonical message a publishable code needs (FR-074)."""
    path = root / "content" / "reason-messages.pt-BR.yaml"
    text = path.read_text(encoding="utf-8")
    head, _, tail = text.partition("  - reason_code: RELEASE_WITHDRAWN")
    path.write_text(head + tail.split("\n\n", 1)[-1], encoding="utf-8")


def _version_gate_failure(root: Path) -> None:
    """A hole between version blocks: days with no governed definition.

    Built from the file's own dates rather than hard-coded ones, so the
    mutation stays a *gap* and does not decay into a different violation the
    moment an authored effective_from changes.
    """
    path = root / "metrics" / "sessions.yaml"
    text = path.read_text(encoding="utf-8")
    opened = date.fromisoformat(
        next(
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.strip().startswith("effective_from:")
        )
    )
    closes = opened + timedelta(days=30)
    reopens = closes + timedelta(days=60)  # 59 uncovered days in between

    text = text.replace("effective_to: null", f"effective_to: {closes}", 1)
    block = "\n".join(
        [
            "",
            "  - version: 2",
            f"    effective_from: {reopens}",
            "    source_view: semantic.sessions_daily",
            "    grain: date x product x platform",
            "    aggregation: sum",
            "    additivity: additive",
            "    unit: sessions",
            "    time_dimension: date",
            "    calculation_basis: Sessoes iniciadas no dia.",
            "    content:",
            "      lang: pt-BR",
            "      label: Sessoes",
            "      description: Sessoes iniciadas no dia.",
            "",
        ]
    )
    head, marker, tail = text.partition("source_availability:")
    path.write_text(head.rstrip("\n") + block + marker + tail, encoding="utf-8")


MUTATIONS: dict[Category, Callable[[Path], None]] = {
    Category.MALFORMED_YAML: _malformed,
    Category.UNKNOWN_KIND: _unknown_kind,
    Category.UNSUPPORTED_VERSION: _unsupported_version,
    Category.SCHEMA_VIOLATION: _schema_violation,
    Category.REFERENTIAL_FAILURE: _referential_failure,
    Category.POLICY_FAILURE: _policy_failure,
    Category.VERSION_GATE_FAILURE: _version_gate_failure,
}

#: Categories that stop the catalog loading at all. Every command that touches
#: the catalog must exit 1 on these, whatever it was asked to do: there is no
#: catalog to answer from.
LOAD_BLOCKING = {
    Category.MALFORMED_YAML,
    Category.UNKNOWN_KIND,
    Category.UNSUPPORTED_VERSION,
    Category.SCHEMA_VIOLATION,
}

#: Categories a loadable catalog can still carry. Only the commands that
#: *assert validity* are required to fail on these.
LOADABLE_VIOLATIONS = {
    Category.REFERENTIAL_FAILURE,
    Category.POLICY_FAILURE,
    Category.VERSION_GATE_FAILURE,
}

#: Commands whose contract line is a verdict on the catalog. These run the
#: layers and must exit 1 on **any** governed violation.
ASSERTING: tuple[tuple[str, Callable[[Path], list[str]]], ...] = (
    ("validate", lambda root: ["validate", "--path", str(root), "--on", ON]),
    ("validate --release", lambda root: ["validate", "--release", "--path", str(root), "--on", ON]),
    ("compliance", lambda root: ["compliance", "--path", str(root), "--on", ON]),
)

#: Commands whose contract line is an *answer* — the resolved contract, a
#: decision, the answerable surface, a leakage report. They need the catalog to
#: load; they do not re-run validation nobody asked for.
#:
#: The distinction is deliberate and it is the steward's, not the
#: implementation's: `explain` is exactly the tool somebody reaches for **while**
#: the catalog has outstanding issues, and a version of it that refused to
#: describe `sessions` because an unrelated metric's owner was renamed would be
#: useless at the moment it is most needed. `validate` is where "is this
#: catalog correct" is asked, and it answers for all of L1-L4.
ANSWERING: tuple[tuple[str, Callable[[Path], list[str]]], ...] = (
    ("explain", lambda root: ["explain", "sessions", "--path", str(root), "--on", ON]),
    (
        "check",
        lambda root: [
            "check",
            "sessions",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--path",
            str(root),
            "--on",
            ON,
        ],
    ),
    ("matrix", lambda root: ["matrix", "--path", str(root), "--on", ON]),
    ("leakage-scan", lambda root: ["leakage-scan", "--path", str(root), "--on", ON, "--repo", "."]),
)

CATALOG_READING = ASSERTING + ANSWERING


@dataclass(frozen=True, slots=True)
class Case:
    """One cell of the matrix."""

    command: str
    category: Category
    argv: list[str]
    expected: int


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- governed content: every catalog-reading command must exit 1 ------------


def _cases(
    commands: tuple[tuple[str, Callable[[Path], list[str]]], ...],
    categories: set[Category],
) -> list[tuple[str, Category]]:
    return [(name, category) for name, _ in commands for category in sorted(categories)]


LOAD_BLOCKED_CASES = _cases(CATALOG_READING, LOAD_BLOCKING)
ASSERTED_CASES = _cases(ASSERTING, LOADABLE_VIOLATIONS)


@pytest.mark.parametrize(
    ("command", "category"),
    LOAD_BLOCKED_CASES,
    ids=[f"{c}-{k.value}" for c, k in LOAD_BLOCKED_CASES],
)
def test_a_catalog_that_will_not_load_exits_one_from_every_command(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    command: str,
    category: Category,
) -> None:
    """The correction this module exists for.

    A malformed file, an unknown kind, an unsupported schema version and a
    schema violation are all **violations**, not usage errors: the content
    exists, is governed, and is wrong. Every command that touches the catalog
    says so with the same code.
    """
    root = _copy(tmp_path)
    MUTATIONS[category](root)
    argv = next(builder for name, builder in CATALOG_READING if name == command)(root)

    code, out, err = _run(capsys, argv)
    assert code == EXIT_VIOLATION, f"{command}/{category.value}: exit {code}\n{out}\n{err}"
    assert "Traceback" not in out + err, "a crash is not a verdict"
    assert out.strip(), "a violation must be reported, not merely returned"


@pytest.mark.parametrize(
    ("command", "category"),
    ASSERTED_CASES,
    ids=[f"{c}-{k.value}" for c, k in ASSERTED_CASES],
)
def test_an_asserting_command_exits_one_on_any_layer_failure(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    command: str,
    category: Category,
) -> None:
    """L2, L4-policy and L4-version failures in a catalog that loads fine."""
    root = _copy(tmp_path)
    MUTATIONS[category](root)
    argv = next(builder for name, builder in ASSERTING if name == command)(root)

    code, out, err = _run(capsys, argv)
    assert code == EXIT_VIOLATION, f"{command}/{category.value}: exit {code}\n{out}\n{err}"
    assert "Traceback" not in out + err


@pytest.mark.parametrize(
    ("command", "category"),
    LOAD_BLOCKED_CASES + ASSERTED_CASES,
    ids=[f"{c}-{k.value}" for c, k in LOAD_BLOCKED_CASES + ASSERTED_CASES],
)
def test_a_governed_failure_leaks_no_partial_verdict(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    command: str,
    category: Category,
) -> None:
    """No command may report a result beside the failure it just found."""
    root = _copy(tmp_path)
    MUTATIONS[category](root)
    builder = next(b for name, b in CATALOG_READING if name == command)
    _, out, _ = _run(capsys, builder(root))
    for verdict in ("ALLOW / ", ": COMPLIANT", "leakage scan: CLEAN"):
        assert verdict not in out, f"{command}/{category.value} leaked a verdict: {verdict!r}"


@pytest.mark.parametrize(
    "category", sorted(LOADABLE_VIOLATIONS), ids=[c.value for c in sorted(LOADABLE_VIOLATIONS)]
)
def test_an_answering_command_still_answers_a_loadable_catalog(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, category: Category
) -> None:
    """The deliberate half of the split, asserted so it cannot drift silently.

    `explain` is the tool a steward reaches for **while** the catalog has
    outstanding issues. Refusing to describe one metric because an unrelated
    one has an unresolved owner would make it useless exactly when it is most
    needed — and `validate` is where that question is asked and answered.
    """
    root = _copy(tmp_path)
    MUTATIONS[category](root)
    code, out, err = _run(capsys, ["explain", "sessions", "--path", str(root), "--on", ON])
    assert code == EXIT_OK, f"{category.value}: exit {code}\n{out}\n{err}"
    # ...and the asserting command does refuse the same tree.
    code, _, _ = _run(capsys, ["validate", "--path", str(root), "--on", ON])
    assert code == EXIT_VIOLATION, category.value


# --- the remaining governed categories --------------------------------------


def test_schema_drift_exits_one(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "schemas"
    shutil.copytree(REPO / "schemas", target)
    drifted = target / "metric.schema.json"
    drifted.write_text(
        drifted.read_text(encoding="utf-8").replace('"title"', '"x"', 1), encoding="utf-8"
    )
    code, out, _ = _run(capsys, ["schema", "export", "--check", "--out", str(target)])
    assert code == EXIT_VIOLATION
    assert "DRIFT" in out


def test_a_malformed_readiness_record_exits_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Governed content. A record nobody can parse must not read as
    'nothing is declared'."""
    broken = tmp_path / "readiness.yaml"
    broken.write_text("capabilities: not-a-list\n", encoding="utf-8")
    code, out, err = _run(
        capsys,
        ["compliance", "--path", str(PRODUCTION), "--on", ON, "--readiness", str(broken)],
    )
    assert code == EXIT_VIOLATION, err
    assert "malformed" in out


def test_a_release_validation_refusal_exits_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = _copy(tmp_path)
    _referential_failure(root)
    code, out, _ = _run(
        capsys,
        [
            "release",
            "publish",
            "--ledger",
            str(tmp_path / "l.json"),
            "--reason",
            "x",
            "--actor-role",
            "data_governance",
            "--path",
            str(root),
            "--on",
            ON,
            "--commit",
            "head",
        ],
    )
    assert code == EXIT_VIOLATION
    assert "refusing to publish" in out
    assert not (tmp_path / "l.json").exists()


def test_a_ledger_with_a_reused_identifier_exits_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The file parsed; its content breaks a governance rule."""
    ledger = tmp_path / "ledger.json"
    entry = {
        "release_id": "sha256:x",
        "state": "active",
        "activated_at": "2026-08-01T00:00:00+00:00",
        "activation_event_id": "evt:1",
    }
    ledger.write_text(
        json.dumps({"releases": [entry, dict(entry)], "events": []}), encoding="utf-8"
    )
    code, out, _ = _run(capsys, ["release", "status", "--ledger", str(ledger)])
    assert code == EXIT_VIOLATION
    assert "never reused" in out


def test_a_governed_decision_denial_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(
        capsys,
        [
            "check",
            "active_users",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--path",
            str(PRODUCTION),
            "--on",
            ON,
        ],
    )
    assert code == EXIT_VIOLATION
    assert "METRIC_PENDING" in out


def test_a_reconciliation_failure_exits_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Declared-but-absent coverage is an L3 error (FR-009)."""
    thin = tmp_path / "coverage.yaml"
    thin.write_text("coverage: []\n", encoding="utf-8")
    code, out, _ = _run(
        capsys,
        ["compliance", "--path", str(PRODUCTION), "--on", ON, "--coverage", str(thin)],
    )
    assert code == EXIT_VIOLATION
    assert "declared_without_coverage" in out


# --- the call: exit 2 -------------------------------------------------------


INVOCATION_CASES: tuple[Case, ...] = (
    Case("<none>", Category.UNKNOWN_COMMAND, ["nonsense"], EXIT_INVOCATION),
    Case("<none>", Category.MISSING_ARGUMENT, [], EXIT_INVOCATION),
    Case("check", Category.MISSING_ARGUMENT, ["check", "sessions"], EXIT_INVOCATION),
    Case("explain", Category.MISSING_ARGUMENT, ["explain"], EXIT_INVOCATION),
    Case("diff", Category.MISSING_ARGUMENT, ["diff"], EXIT_INVOCATION),
    Case("release", Category.MISSING_ARGUMENT, ["release", "status"], EXIT_INVOCATION),
    Case(
        "release",
        Category.MISSING_ARGUMENT,
        ["release", "withdraw", "--ledger", "l.json"],
        EXIT_INVOCATION,
    ),
    Case("schema", Category.MISSING_ARGUMENT, ["schema"], EXIT_INVOCATION),
    Case(
        "explain",
        Category.INVALID_ARGUMENT,
        ["explain", "sessions", "--on", "not-a-date"],
        EXIT_INVOCATION,
    ),
    Case(
        "check",
        Category.INVALID_ARGUMENT,
        ["check", "sessions", "--from", "2026-07-31", "--to", "2026-07-01"],
        EXIT_INVOCATION,
    ),
    Case(
        "check",
        Category.INVALID_ARGUMENT,
        [
            "check",
            "sessions",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--evaluated-at",
            "half past four",
        ],
        EXIT_INVOCATION,
    ),
    Case(
        "check",
        Category.INVALID_ARGUMENT,
        [
            "check",
            "sessions",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--principal-type",
            "robot",
        ],
        EXIT_INVOCATION,
    ),
    Case("matrix", Category.INVALID_ARGUMENT, ["matrix", "--format", "xml"], EXIT_INVOCATION),
    Case(
        "compliance", Category.INVALID_ARGUMENT, ["compliance", "--mode", "prod"], EXIT_INVOCATION
    ),
    Case(
        "validate",
        Category.NONEXISTENT_CATALOG_PATH,
        ["validate", "--path", "no/such/dir"],
        EXIT_INVOCATION,
    ),
    Case(
        "explain",
        Category.NONEXISTENT_CATALOG_PATH,
        ["explain", "sessions", "--path", "no/such/dir"],
        EXIT_INVOCATION,
    ),
    Case(
        "matrix",
        Category.NONEXISTENT_CATALOG_PATH,
        ["matrix", "--path", "no/such/dir"],
        EXIT_INVOCATION,
    ),
    Case(
        "compliance",
        Category.NONEXISTENT_CATALOG_PATH,
        ["compliance", "--path", "no/such/dir"],
        EXIT_INVOCATION,
    ),
    Case(
        "leakage-scan",
        Category.NONEXISTENT_CATALOG_PATH,
        ["leakage-scan", "--path", "no/such/dir"],
        EXIT_INVOCATION,
    ),
    Case(
        "diff",
        Category.NONEXISTENT_CATALOG_PATH,
        ["diff", "--base", "HEAD", "--path", "no/such/dir"],
        EXIT_INVOCATION,
    ),
    Case(
        "schema",
        Category.NONEXISTENT_INPUT_FILE,
        ["schema", "export", "--check", "--out", "no/such/dir"],
        EXIT_INVOCATION,
    ),
    Case(
        "check",
        Category.NONEXISTENT_INPUT_FILE,
        [
            "check",
            "sessions",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--freshness",
            "no/such/file.yaml",
        ],
        EXIT_INVOCATION,
    ),
    Case(
        "compliance",
        Category.NONEXISTENT_INPUT_FILE,
        ["compliance", "--coverage", "no/such/file.yaml"],
        EXIT_INVOCATION,
    ),
    Case(
        "validate",
        Category.NONEXISTENT_INPUT_FILE,
        ["validate", "--coverage", "no/such/file.yaml"],
        EXIT_INVOCATION,
    ),
)


@pytest.mark.parametrize(
    "case",
    INVOCATION_CASES,
    ids=[f"{c.command}-{c.category.value}-{i}" for i, c in enumerate(INVOCATION_CASES)],
)
def test_invocation_failures_exit_two(capsys: pytest.CaptureFixture[str], case: Case) -> None:
    code, out, err = _run(capsys, case.argv)
    assert code == case.expected, f"{case.category.value}: exit {code}\n{out}\n{err}"
    assert "Traceback" not in out + err


@pytest.mark.parametrize(
    "case",
    INVOCATION_CASES,
    ids=[f"{c.command}-{c.category.value}-{i}" for i, c in enumerate(INVOCATION_CASES)],
)
def test_an_invocation_failure_prints_no_verdict(
    capsys: pytest.CaptureFixture[str], case: Case
) -> None:
    """Nothing was validated, so stdout carries nothing that reads as a result."""
    _, out, _ = _run(capsys, case.argv)
    assert out.strip() == "" or out.startswith("usage:"), out


def test_an_unloadable_caller_supplied_file_exits_two(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A fixture the caller named is an input, not governed content."""
    broken_snapshot = tmp_path / "snapshot.yaml"
    broken_snapshot.write_text("observed_at: [not, a, timestamp\n", encoding="utf-8")
    code, _, _ = _run(
        capsys,
        [
            "check",
            "sessions",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--path",
            str(PRODUCTION),
            "--on",
            ON,
            "--freshness",
            str(broken_snapshot),
        ],
    )
    assert code == EXIT_INVOCATION

    broken_coverage = tmp_path / "coverage.yaml"
    broken_coverage.write_text("coverage: [\n", encoding="utf-8")
    code, _, _ = _run(
        capsys,
        ["compliance", "--path", str(PRODUCTION), "--on", ON, "--coverage", str(broken_coverage)],
    )
    assert code == EXIT_INVOCATION

    broken_ledger = tmp_path / "ledger.json"
    broken_ledger.write_text("{not json", encoding="utf-8")
    code, _, _ = _run(capsys, ["release", "status", "--ledger", str(broken_ledger)])
    assert code == EXIT_INVOCATION


def test_malformed_existing_yaml_and_a_nonexistent_path_are_different(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The distinction the contract turns on, asserted side by side.

    Same command, same shape of complaint to a human, two different answers:
    one is a catalog to fix, the other is a command to retype.
    """
    root = _copy(tmp_path)
    _malformed(root)

    malformed_code, malformed_out, _ = _run(capsys, ["validate", "--path", str(root), "--on", ON])
    missing_code, missing_out, missing_err = _run(capsys, ["validate", "--path", "no/such/dir"])

    assert malformed_code == EXIT_VIOLATION
    assert missing_code == EXIT_INVOCATION
    assert malformed_out.strip(), "a violation is reported"
    assert missing_out.strip() == "", "a usage error prints no verdict"
    assert missing_err.strip(), "a usage error explains itself on stderr"


# --- clean runs -------------------------------------------------------------


def test_a_clean_catalog_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in (
        ["validate", "--path", str(PRODUCTION), "--on", ON],
        ["validate", "--path", str(PRODUCTION), "--on", ON, "--release"],
        ["explain", "sessions", "--path", str(PRODUCTION), "--on", ON],
        ["matrix", "--path", str(PRODUCTION), "--on", ON],
        [
            "compliance",
            "--path",
            str(PRODUCTION),
            "--on",
            ON,
            "--coverage",
            str(COVERAGE),
            "--readiness",
            str(READINESS),
        ],
        ["leakage-scan", "--path", str(PRODUCTION), "--on", ON, "--repo", str(REPO)],
        ["schema", "export", "--check", "--out", str(REPO / "schemas")],
    ):
        code, out, err = _run(capsys, argv)
        assert code == EXIT_OK, f"{argv[0]}: exit {code}\n{out}\n{err}"


# --- JSON error output ------------------------------------------------------


_JSON_ERROR_CASES = (
    ["validate", "--format", "json"],
    ["explain", "sessions", "--format", "json"],
    ["check", "sessions", "--from", "2026-07-01", "--to", "2026-07-31", "--format", "json"],
    ["compliance", "--format", "json"],
    ["leakage-scan", "--format", "json"],
)


@pytest.mark.parametrize("argv", _JSON_ERROR_CASES, ids=[a[0] for a in _JSON_ERROR_CASES])
def test_json_error_output_is_machine_readable_and_deterministic(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, argv: list[str]
) -> None:
    root = _copy(tmp_path)
    _malformed(root)
    full = [*argv, "--path", str(root), "--on", ON]

    first_code, first, _ = _run(capsys, full)
    second_code, second, _ = _run(capsys, full)

    assert first_code == second_code == EXIT_VIOLATION
    assert first == second, "the same failure produced different bytes"
    payload = json.loads(first)
    assert payload["valid"] is False
    assert payload["errors"] >= 1
    assert payload["findings"], "a machine-readable failure must name what broke"


def test_json_error_output_is_pt_br_safe(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A governed refusal carries pt-BR wording; JSON must not mangle it."""
    code, out, _ = _run(
        capsys,
        [
            "check",
            "active_users",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--path",
            str(PRODUCTION),
            "--on",
            ON,
            "--format",
            "json",
        ],
    )
    assert code == EXIT_VIOLATION
    payload = json.loads(out)
    assert "métrica" in payload["message_pt_br"]
    assert "\\u" not in out

    # And a validation failure whose finding quotes an accented authored value.
    root = _copy(tmp_path)
    _schema_violation(root)
    code, out, _ = _run(capsys, ["validate", "--path", str(root), "--on", ON, "--format", "json"])
    assert code == EXIT_VIOLATION
    json.loads(out)
    assert "\\u00" not in out, "authored content was escaped instead of emitted as UTF-8"


# --- the matrix is exhaustive ----------------------------------------------


def test_every_subcommand_appears_in_the_matrix() -> None:
    """A new subcommand that nobody classified fails here rather than going
    unchecked."""
    parser = build_parser()
    subparsers = parser._subparsers
    assert subparsers is not None
    choices = next(a.choices for a in subparsers._group_actions if a.choices)
    assert set(choices) == set(SUBCOMMANDS), sorted(set(choices) ^ set(SUBCOMMANDS))

    covered: set[str] = {case.command for case in INVOCATION_CASES}
    covered |= {name.split()[0] for name, _ in CATALOG_READING}
    covered |= {"schema", "release", "diff"}
    missing = sorted(set(SUBCOMMANDS) - covered)
    assert not missing, f"subcommands with no exit-code case: {missing}"


def test_every_failure_category_is_exercised() -> None:
    """Each category must be asserted somewhere in this module."""
    source = Path(__file__).read_text(encoding="utf-8")
    for category in Category:
        if category in MUTATIONS or category in {c.category for c in INVOCATION_CASES}:
            continue
        assert category.value in source, f"{category.value} has no case"


def test_the_two_code_classes_do_not_overlap() -> None:
    assert GOVERNED.isdisjoint(INVOCATION)
    assert set(Category) == GOVERNED | INVOCATION
