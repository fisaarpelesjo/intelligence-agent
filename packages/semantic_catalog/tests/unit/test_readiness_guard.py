"""Readiness guard and CI configuration — T100, T101 (FR-009, FR-038, FR-069).

The guard's whole job is that the second state cannot be reached by accident:
before a capability is declared, a fixture may stand in and the report must say
so; after it is declared, a fixture standing in for it in integration or release
mode fails closed.

**Written and tested against contract fixtures now**, so it is in place before
the readiness it polices arrives. T109 depends on this task, not the reverse —
and nothing here declares anything ready.

The CI half asserts what a workflow file can be asserted about: every gate the
task requires is present, the runtime is the declared floor, and **no step is
advisory**. A gate that warns is a gate that gets ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from semantic_catalog.compliance.readiness import (
    FIXTURE_LIMITATION,
    Capability,
    GuardMode,
    ReadinessError,
    ReadinessRecord,
    ReadinessState,
    guard,
    load_readiness,
)

REPO = Path(__file__).resolve().parents[4]
RECORD = REPO / "docs" / "readiness" / "external-readiness.yaml"
WORKFLOWS = REPO / ".github" / "workflows"


def _ready(*capabilities: Capability) -> ReadinessState:
    records = {
        capability: ReadinessRecord(
            capability=capability,
            declared=capability in capabilities,
            evidence_ref="docs/readiness/evidence/example.md"
            if capability in capabilities
            else None,
            declared_by_role="data_governance" if capability in capabilities else None,
        )
        for capability in Capability
    }
    return ReadinessState(records=records, source="<test>")


# --- the governed record ----------------------------------------------------


def test_the_shipped_record_declares_nothing_ready() -> None:
    """Emendado nos ciclos 519/525/537 e 542 (OD-106: ext_a/D-12, cinco condicoes com o
    censo limpo) — CINCO prontos, cada um com a sua ordem; um sexto falha aqui. Nome
    fincado; o corpo e a verdade."""
    state = load_readiness(RECORD)
    ready_set = (
        Capability.D_1,
        Capability.D_10,
        Capability.D_2,
        Capability.EXT_A,
        Capability.EXT_B,
    )
    assert state.ready == ready_set
    for capability in Capability:
        if capability in ready_set:
            assert state.is_ready(capability)
            continue
        assert not state.is_ready(capability), capability.value


def test_the_shipped_record_names_the_task_tracking_each_capability() -> None:
    """A capability nobody can trace to a task is a capability nobody will chase."""
    text = RECORD.read_text(encoding="utf-8")
    for task in ("T107", "T108", "T109", "T110"):
        assert task in text, task


def test_a_missing_record_means_nothing_is_ready(tmp_path: Path) -> None:
    """Absent is the safe state: before anything is delivered there is nothing
    to record."""
    assert load_readiness(tmp_path / "absent.yaml").ready == ()


def test_a_malformed_record_raises_rather_than_reading_as_absent(tmp_path: Path) -> None:
    """Treating a corrupted claim as an absent one turns it into a quiet pass."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("capabilities: not-a-list\n", encoding="utf-8")
    with pytest.raises(ReadinessError):
        load_readiness(broken)

    unknown = tmp_path / "unknown.yaml"
    unknown.write_text(
        "capabilities:\n  - capability: ext_z\n    declared: false\n", encoding="utf-8"
    )
    with pytest.raises(ReadinessError):
        load_readiness(unknown)


def test_a_declaration_without_evidence_is_refused(tmp_path: Path) -> None:
    """Readiness is named evidence signed by a role, never a flag."""
    flagged = tmp_path / "flagged.yaml"
    flagged.write_text(
        "capabilities:\n  - capability: ext_a\n    declared: true\n", encoding="utf-8"
    )
    with pytest.raises(ReadinessError, match="never a flag"):
        load_readiness(flagged)


def test_a_declaration_with_evidence_but_no_role_is_refused() -> None:
    with pytest.raises(ReadinessError):
        ReadinessRecord(capability=Capability.EXT_A, declared=True, evidence_ref="doc.md")


# --- the guard --------------------------------------------------------------


@pytest.mark.parametrize("mode", list(GuardMode))
def test_a_run_that_substituted_nothing_is_permitted_with_no_limitation(
    mode: GuardMode,
) -> None:
    verdict = guard(_ready(), mode=mode, fixtures_used=())
    assert verdict.permitted
    assert verdict.limitations == ()


@pytest.mark.parametrize("mode", list(GuardMode))
def test_before_readiness_a_fixture_is_permitted_and_the_limitation_is_stated(
    mode: GuardMode,
) -> None:
    verdict = guard(_ready(), mode=mode, fixtures_used=(Capability.EXT_A,))
    assert verdict.permitted
    assert verdict.limitations and FIXTURE_LIMITATION in verdict.limitations[0]
    assert "ext_a" in verdict.limitations[0]


@pytest.mark.parametrize("mode", [GuardMode.INTEGRATION, GuardMode.RELEASE])
def test_after_readiness_a_fixture_fails_closed(mode: GuardMode) -> None:
    verdict = guard(_ready(Capability.EXT_A), mode=mode, fixtures_used=(Capability.EXT_A,))
    assert not verdict.permitted
    assert any("declared ready" in reason for reason in verdict.reasons)
    assert verdict.limitations == ()


def test_local_mode_permits_a_fixture_even_after_readiness() -> None:
    """A steward validating a branch on their laptop has no warehouse."""
    verdict = guard(
        _ready(Capability.EXT_A), mode=GuardMode.LOCAL, fixtures_used=(Capability.EXT_A,)
    )
    assert verdict.permitted
    assert verdict.limitations


def test_readiness_for_one_capability_does_not_gate_another() -> None:
    verdict = guard(
        _ready(Capability.EXT_B), mode=GuardMode.RELEASE, fixtures_used=(Capability.EXT_A,)
    )
    assert verdict.permitted


def test_an_unknown_capability_reads_as_not_ready() -> None:
    """Fails closed on readiness, so an incomplete record cannot grant one."""
    partial = ReadinessState(records={}, source="<test>")
    assert not partial.is_ready(Capability.EXT_A)
    assert partial.ready == ()


def test_the_verdict_is_machine_readable() -> None:
    verdict = guard(
        _ready(Capability.EXT_A), mode=GuardMode.RELEASE, fixtures_used=(Capability.EXT_A,)
    )
    payload = verdict.to_dict()
    assert payload["permitted"] is False
    assert payload["mode"] == "release"
    assert payload["reasons"]


# --- T100: the CI configuration --------------------------------------------


def _workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_the_ci_workflow_exists_and_parses() -> None:
    assert (WORKFLOWS / "catalog.yml").is_file()
    assert _workflow("catalog.yml")["jobs"]


def test_ci_runs_the_declared_python_floor() -> None:
    """A newer interpreter would let a 3.13-only construct merge and break every
    steward still on the floor."""
    import tomllib

    spec = tomllib.loads(
        (REPO / "packages" / "semantic_catalog" / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["requires-python"]
    floor = spec.removeprefix(">=")
    workflow = _workflow("catalog.yml")
    assert workflow["env"]["PYTHON_VERSION"] == floor
    assert _workflow("readiness-guard.yml")["env"]["PYTHON_VERSION"] == floor


@pytest.mark.parametrize(
    "needle",
    [
        "ruff format --check",
        "ruff check",
        "pyright",
        "pytest",
        "schema export --check",
        "validate\n          --path semantic --strict --check-schema-version",
        "--release",
        "compliance",
        "leakage-scan",
        "tests/contract",
    ],
)
def test_every_required_gate_is_present(needle: str) -> None:
    text = (WORKFLOWS / "catalog.yml").read_text(encoding="utf-8")
    assert needle.split("\n")[0].strip() in text, needle


def test_no_ci_step_is_advisory() -> None:
    """`continue-on-error` anywhere would make a blocking gate a suggestion."""
    for name in ("catalog.yml", "readiness-guard.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "continue-on-error" not in text, name
        assert "|| true" not in text, name
        assert "if: always()" not in text, name


def test_the_readiness_workflow_runs_the_guard_in_the_strict_modes() -> None:
    text = (WORKFLOWS / "readiness-guard.yml").read_text(encoding="utf-8")
    assert "--mode integration" in text
    assert "--mode release" in text
    assert "external-readiness.yaml" in text


def test_the_readiness_workflow_does_not_require_ext_a_to_exist() -> None:
    """T109 depends on this workflow, not the reverse."""
    workflow = _workflow("readiness-guard.yml")
    text = " ".join((WORKFLOWS / "readiness-guard.yml").read_text(encoding="utf-8").split())
    assert "T109 depends on this workflow, not the reverse" in text
    # Structural, not prose: the guard must reach no warehouse to run.
    for step in _steps(workflow):
        rendered = str(step).lower()
        assert "bigquery" not in rendered
        assert "google.cloud" not in rendered
    assert all("--mode" not in str(s) or "readiness" in str(s) for s in _steps(workflow))


def test_no_workflow_claims_an_undelivered_capability() -> None:
    for name in ("catalog.yml", "readiness-guard.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8").lower()
        for claim in ("ext-a is ready", "ext_a: ready", "readiness: declared", "sc-002"):
            assert claim not in text, f"{name}: {claim}"


# --- OD-110 / S-41: the loader's own promise, made executable ----------------
#
# `load_readiness`'s docstring has always said a malformed record is an error, "the
# alternative is treating a broken readiness record as an absent one, which turns a
# corrupted claim into a quiet pass". The code then built
# `declared=bool(entry.get("declared", False))`, which is exactly that alternative: silence
# became `False`, anything truthy became a declaration, and an unrecognised key was dropped.
#
# The finding (S-41) was measured one layer up, in the CI step that derives its regime from
# this record: an entry that lost its `declared:` line made the step print "not declared",
# permit the fixture and exit 0 — green, on a damaged record. Hardening the loader is the
# same repair one layer down, and it is the owner's call because it changes a `001` contract
# (OD-110, 2026-09-03).
#
# One node per class, and each was driven against the OLD loader first: every one of them
# passed silently there, which is what made them worth writing.


def _record(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "record.yaml"
    target.write_text(body, encoding="utf-8")
    return target


def test_an_entry_without_declared_raises_instead_of_reading_as_not_declared(
    tmp_path: Path,
) -> None:
    """Silence is not "not declared" — THE class, at its root.

    Before OD-110 this loaded clean, with `ext_a` reading as not ready.
    """
    record = _record(tmp_path, "capabilities:\n  - capability: ext_a\n")
    with pytest.raises(ReadinessError, match="states no 'declared'"):
        load_readiness(record)


def test_a_non_boolean_declared_raises_because_truthiness_is_not_a_declaration(
    tmp_path: Path,
) -> None:
    """`bool("false")` is `True`, so the old loader read `declared: "false"` as READY.

    The string case is worse than silence: it does not merely fail to answer, it answers
    the opposite of what the file plainly means.
    """
    assert bool("false") is True, "the premise of this node stopped holding"
    record = _record(
        tmp_path,
        'capabilities:\n  - capability: ext_a\n    declared: "false"\n',
    )
    with pytest.raises(ReadinessError, match="not a boolean"):
        load_readiness(record)


@pytest.mark.parametrize("value", ["0", "[]", "''"])
def test_every_falsy_non_boolean_declared_raises_rather_than_reading_as_not_declared(
    tmp_path: Path, value: str
) -> None:
    """The quiet half of the same class: `0`, `[]` and `''` all read as not-declared.

    Parametrised because one example would leave the others free to keep passing silently,
    and "did not measure" is not "passed".
    """
    record = _record(tmp_path, f"capabilities:\n  - capability: ext_a\n    declared: {value}\n")
    with pytest.raises(ReadinessError, match="not a boolean"):
        load_readiness(record)


def test_an_unknown_key_in_an_entry_raises_instead_of_being_dropped(tmp_path: Path) -> None:
    """A misspelt key is silence wearing the right shape.

    `declared_ready: true` next to no `declared:` is how the first class arrives in
    practice — and dropping the key is what let it arrive unseen.
    """
    record = _record(
        tmp_path,
        "capabilities:\n  - capability: ext_a\n    declared: false\n    declared_ready: true\n",
    )
    with pytest.raises(ReadinessError, match="which this record does not define"):
        load_readiness(record)


def test_an_unparseable_record_raises_the_contract_error_not_a_raw_yaml_error(
    tmp_path: Path,
) -> None:
    """It always blocked — as a `yaml.YAMLError` nobody downstream catches.

    Every caller catches `ReadinessError`; a raw parser error escaped as a traceback, so
    the refusal was indistinguishable from a crash.
    """
    record = _record(tmp_path, "capabilities: [\n  - capability: ext_a\n")
    with pytest.raises(ReadinessError, match="not parseable YAML"):
        load_readiness(record)


def test_every_field_of_the_record_type_is_accepted_as_an_entry_key(tmp_path: Path) -> None:
    """A typed-out key list is the next thing to read as true after the record grows.

    DRIVEN, not read: asserting against the module's private set would restate the
    implementation under a second name and would keep passing if that set were frozen by
    hand. This loads one record per field instead — if `ReadinessRecord` gains a field, an
    entry using it stops being an unknown key without anyone remembering this module, and
    if the set is ever typed out and falls behind, the field it dropped fails here.
    """
    import dataclasses

    for field in dataclasses.fields(ReadinessRecord):
        if field.name in {"capability", "declared"}:
            continue  # carried by every entry already; the loop is about the optional ones
        lines = [
            "capabilities:",
            "  - capability: ext_a",
            "    declared: false",
            f"    {field.name}: null",
            "",
        ]
        record = _record(tmp_path, "\n".join(lines))
        state = load_readiness(record)
        assert not state.is_ready(Capability.EXT_A), field.name


def test_the_governed_record_of_this_repository_still_loads() -> None:
    """Non-vacuity, and the measurement that made the hardening safe to make.

    Four readiness records exist in the repository and only this one reaches this loader;
    the other three carry a richer shape and already raise here today. If the hardening had
    failed a record that exists, this is where it would show.
    """
    state = load_readiness(RECORD)
    assert state.ready, "the governed record declares nothing; this node asserts nothing"
    assert state.is_ready(Capability.EXT_A)
