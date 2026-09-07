"""The fixture-backed CI steps assert the guard's VERDICT — S-40 (T101; FR-009, SC-001).

Declaring `ext_a` on 2026-09-03 put three CI steps into exit 1: `catalog.yml`'s
declared-versus-observed reconciliation and both strict-mode steps of
`readiness-guard.yml`. Nothing was broken. The guard **fails closed** once a capability is
declared, and those steps were wired to demand that the command *succeed* — so they
asserted the permissive regime and only the permissive regime, and went red the day the
strict one arrived.

**The shape of the mistake matters more than the three reds.** A step wired to "this must
exit 0" asserts whatever today's answer happens to be. It cannot tell *the gate works* from
*the gate is gone*, because both regimes are a property of the record, not of the command.
Two ways out were available and only one of them keeps the property:

* moving the steps to `--mode local` turns them green by **removing the gate** — the
  fail-closed stops being exercised at the exact moment it starts being true. That is a
  reduction of a fail-closed, and it is refused here;
* asserting the **verdict due for the regime the record declares** keeps both halves
  checked, forever, with nothing typed: `tools/ci/assert_fixture_fallback.py` reads
  `ReadinessState.is_ready` — the same function the guard reads — and demands a refusal
  while the capability is declared, a permission-with-limitation while it is not.

## This file DRIVES the script, it does not read its source

The two regimes below are executed end to end against the real script and the real CLI:
once against the repository's record, and once against a copy with the capability
withdrawn. A node that grepped the script for an `if` would describe a shape instead of a
behaviour, and would keep passing if the branch were rewritten to accept anything.

The three ways the assertion must go RED are driven through `main`, with the compliance
call replaced by the payload that describes each failure — the payloads a real run cannot
be made to produce on demand without corrupting the catalogue. What is driven is the
script's judgement of a verdict, which is the whole of what it adds.

## And the wiring is checked separately

Driving the script proves the script. It does not prove the workflows still call it — a
YAML edit could restore `compliance ... --mode integration` verbatim and every behavioural
node here would stay green while the three steps went back to exit 1. The last node reads
the two workflow files for exactly that.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from semantic_catalog.compliance.readiness import Capability, load_readiness

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "tools" / "ci" / "assert_fixture_fallback.py"
RECORD = REPO / "docs" / "readiness" / "external-readiness.yaml"
FIXTURE = (
    REPO / "packages" / "semantic_catalog" / "tests" / "fixtures" / "coverage" / "observed.yaml"
)
WORKFLOWS = REPO / ".github" / "workflows"
STRICT_MODES = ("integration", "release")


def _drive(mode: str, readiness: Path) -> subprocess.CompletedProcess[str]:
    """Run the assertion script end to end, exactly as a workflow step runs it."""
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--path",
            "semantic",
            "--mode",
            mode,
            "--coverage",
            FIXTURE.as_posix(),
            "--readiness",
            readiness.as_posix(),
            "--codeowners",
            ".github/CODEOWNERS",
            "--capability",
            "ext_a",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _record_without_ext_a(tmp_path: Path) -> Path:
    """The repository's record with `ext_a` withdrawn — the regime before 2026-09-03.

    Withdrawn by editing the parsed document rather than by writing a small record from
    scratch: a hand-made record would exercise a file this repository does not have, and
    the point is that the SAME record in the other regime moves the step by itself.
    """
    document = yaml.safe_load(RECORD.read_text(encoding="utf-8"))
    for entry in document["capabilities"]:
        if entry["capability"] == "ext_a":
            entry["declared"] = False
            entry.pop("declared_by_role", None)
            entry.pop("evidence_ref", None)
    target = tmp_path / "external-readiness.yaml"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


@pytest.mark.parametrize("mode", STRICT_MODES)
def test_a_declared_capability_makes_the_step_demand_the_refusal(mode: str) -> None:
    """The regime of today: the fixture is refused, and the step is GREEN for it."""
    assert load_readiness(RECORD).is_ready(Capability.EXT_A), (
        "this node describes the declared regime; ext_a is not declared in the record"
    )
    result = _drive(mode, RECORD)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "requires a REFUSAL" in result.stdout
    assert "REFUSED as required" in result.stdout
    assert "ext_a is declared ready" in result.stdout
    assert f"in {mode} mode" in result.stdout


@pytest.mark.parametrize("mode", STRICT_MODES)
def test_withdrawing_the_capability_moves_the_step_to_the_other_regime(
    mode: str, tmp_path: Path
) -> None:
    """Nothing is typed: the same step demands the permission once nothing is declared.

    This is what makes the repair safe to leave in place. If `ext_a` is ever withdrawn —
    a governed edit, but a possible one — the step does not have to be remembered.
    """
    withdrawn = _record_without_ext_a(tmp_path)
    assert not load_readiness(withdrawn).is_ready(Capability.EXT_A)
    result = _drive(mode, withdrawn)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "requires a PERMISSION with a stated limitation" in result.stdout
    assert "permitted with the limitation stated" in result.stdout


def _load_script() -> ModuleType:
    """Load the CI script from its path — it is a script, not an installed module.

    Loaded by location rather than by putting `tools/ci` on `sys.path`: the workflow steps
    invoke it by path too, so this exercises the same file the runner does and leaves no
    import route behind that only the tests have.
    """
    spec = importlib.util.spec_from_file_location("assert_fixture_fallback", SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - a checkout without the script
        pytest.skip(
            #: LIDERA POR FRASE FIXA. O motivo comecava pelo caminho ABSOLUTO, que muda de
            #: maquina para maquina, e nenhuma particao declarada pode casar com isso.
            f"the fixture script is not in this checkout ({SCRIPT}); nothing was measured"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _main_over(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    payload: dict[str, Any],
    code: int,
) -> tuple[int, str]:
    """Drive the script's judgement over a verdict a real run will not produce on demand.

    Returns the exit status **and the reason printed**, because a non-zero status alone is
    not evidence that the intended check fired. Measured here: removing the
    permitted-where-refusal-is-due branch still returned 1 — the next check caught the same
    payload for a different reason — and a node asserting only the status stayed green
    through the removal. Asserting the named cause is what makes each branch its own.
    """
    module = _load_script()

    def _stub(args: object) -> tuple[int, dict[str, Any], str, str]:
        return code, payload, "<stdout>", "<stderr>"

    monkeypatch.setattr(module, "_run_compliance", _stub)
    status = module.main(
        [
            "--mode",
            "integration",
            "--coverage",
            FIXTURE.as_posix(),
            "--readiness",
            RECORD.as_posix(),
            "--capability",
            "ext_a",
        ]
    )
    return status, capsys.readouterr().err


def test_a_permitted_fixture_where_a_refusal_is_due_is_the_red(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fail-closed being REMOVED is the failure this step exists to catch.

    A step that demanded exit 0 would have read this exact payload as success.
    """
    payload = {
        "readiness": {
            "mode": "integration",
            "permitted": True,
            "reasons": [],
            "limitations": ["a fixture stood in"],
        }
    }
    status, reported = _main_over(monkeypatch, capsys, payload, code=0)
    assert status == 1
    assert "the fail-closed is gone" in reported, reported


def test_a_refusal_that_still_exits_zero_is_the_red(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A verdict nobody enforces is prose. CI must go red, not just print the refusal."""
    payload = {
        "readiness": {
            "mode": "integration",
            "permitted": False,
            "reasons": ["ext_a is declared ready (...), so a fixture must not stand in for it"],
            "limitations": [],
        }
    }
    status, reported = _main_over(monkeypatch, capsys, payload, code=0)
    assert status == 1
    assert "still exited 0" in reported, reported


def test_a_refusal_for_another_cause_is_not_read_as_this_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-zero is not enough. Some other capability's refusal would satisfy an exit-code
    check while saying nothing about the one this step guards."""
    payload = {
        "readiness": {
            "mode": "integration",
            "permitted": False,
            "reasons": ["ext_b is declared ready (...), so a fixture must not stand in for it"],
            "limitations": [],
        }
    }
    status, reported = _main_over(monkeypatch, capsys, payload, code=1)
    assert status == 1
    assert "no reason names ext_a" in reported, reported


def _steps(name: str) -> list[dict[str, Any]]:
    workflow = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_every_fixture_backed_step_stays_strict_and_goes_through_the_assertion() -> None:
    """The three steps of S-40, by the property that put them in exit 1.

    Selected by the FIXTURE, not by the mode — and that is the whole point of the
    selector. Choosing them by `--mode integration` would let the forbidden repair pass
    unseen: a step downgraded to `--mode local` would simply stop being selected, and a
    node that stops looking at what it guards is green for the wrong reason. Selected by
    the fixture, a downgrade is a step this node still sees and now refuses.

    So both halves are asserted on the same three steps: the mode stays strict (the gate is
    not reduced), and the assertion is invoked (the verdict is judged rather than the exit
    code). Restoring a bare `compliance --mode integration --coverage <fixture>` puts that
    step back in exit 1, and this names it before CI does.
    """
    fixture_ref = "tests/fixtures/coverage/observed.yaml"
    seen: list[str] = []
    for name in ("catalog.yml", "readiness-guard.yml"):
        for step in _steps(name):
            run = str(step.get("run") or "")
            if fixture_ref not in run:
                continue
            where = f"{name}: {step.get('name')}"
            seen.append(where)
            assert any(f"--mode {mode}" in run for mode in STRICT_MODES), (
                f"{where}: a fixture-backed step left the strict modes; the fail-closed is "
                "exercised only in integration and release"
            )
            assert "tools/ci/assert_fixture_fallback.py" in run, where
    assert len(seen) == 3, f"expected the three fixture-backed steps, measured {seen}"


# --- S-41: absence is not an answer ----------------------------------------
#
# The second occurrence of one class, and the reason these nodes exist as a group rather
# than as one more `if`. S-40 was a gate that could not tell *the gate works* from *the gate
# is gone*. S-41 was this script reading a record's SILENCE as "not declared": an entry that
# lost its `declared:` line moved the step to the permissive regime and exited 0, green,
# with a damaged record.
#
# The nodes below drive `read_declared_flag` — the one place the rule is written — once per
# way a record can fail to say. They are separate on purpose: a single "malformed record is
# refused" node would go green the day four of the five checks were deleted, because the
# fifth would still catch the one case it happened to test.
#
# **Why the class had no watch until now.** `_record_without_ext_a` above builds a
# WELL-FORMED withdrawal — `declared: false`, every key in place. It proves the derivation is
# real and proves nothing at all about a record that does not say. That gap is the finding.


def _record_with(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    name: str = "record.yaml",
) -> Path:
    """The repository's record with one thing wrong with the `ext_a` entry, and nothing else."""
    document: dict[str, Any] = yaml.safe_load(RECORD.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = document["capabilities"]
    for entry in entries:
        if entry["capability"] == "ext_a":
            mutate(entry)
    target = tmp_path / name
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


def _refusal_of(readiness: Path) -> subprocess.CompletedProcess[str]:
    """Drive the real script, as a workflow step drives it, over a record that does not say."""
    return _drive("integration", readiness)


def test_the_real_record_states_the_regime_for_every_capability() -> None:
    """Non-vacuity, and it is what makes silence *malformation* rather than my preference.

    Every entry of the governed record carries `declared` explicitly. So an entry without it
    is not "the terse spelling of false" — it is a record that lost a line.
    """
    document = yaml.safe_load(RECORD.read_text(encoding="utf-8"))
    entries = document["capabilities"]
    assert entries, "the record declares no capabilities; these nodes would assert nothing"
    silent = [
        entry["capability"] for entry in entries if not isinstance(entry.get("declared"), bool)
    ]
    assert not silent, f"entries without an explicit boolean 'declared': {silent}"


def test_a_missing_declared_line_refuses_instead_of_reading_as_not_declared(
    tmp_path: Path,
) -> None:
    """THE finding, driven end to end: this exact record printed "not declared" and exited 0."""

    def drop_declared(entry: dict[str, Any]) -> None:
        entry.pop("declared", None)

    record = _record_with(tmp_path, drop_declared)
    result = _refusal_of(record)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "does not state the regime" in result.stderr, result.stderr
    assert "states no 'declared'" in result.stderr, result.stderr
    assert "not declared, so this step requires a PERMISSION" not in result.stdout


def test_an_unknown_key_refuses_rather_than_being_ignored(tmp_path: Path) -> None:
    """A misspelt key is silence wearing the right shape.

    `declared` is left in place here, so this drives the unknown-key check alone rather than
    riding on the missing-line one.
    """

    def add_unknown_key(entry: dict[str, Any]) -> None:
        entry["declared_ready"] = True

    record = _record_with(tmp_path, add_unknown_key)
    result = _refusal_of(record)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "declared_ready" in result.stderr, result.stderr
    assert "the contract does not define" in result.stderr, result.stderr


def test_a_non_boolean_declared_refuses_because_truthiness_is_not_a_declaration(
    tmp_path: Path,
) -> None:
    """`bool("false")` is `True` — measured. A string would have INVERTED the regime.

    Worse than silence: silence picked the permissive regime, and `declared: "false"` picks
    the strict one while the record plainly means the opposite. Neither is an answer.
    """

    def make_declared_a_string(entry: dict[str, Any]) -> None:
        entry["declared"] = "false"

    record = _record_with(tmp_path, make_declared_a_string)
    result = _refusal_of(record)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not a boolean" in result.stderr, result.stderr
    assert bool("false") is True, "the premise of this node stopped holding"


def test_a_missing_entry_refuses_rather_than_meaning_not_ready(tmp_path: Path) -> None:
    """A capability the record never mentions has not been declared *not* ready."""
    document = yaml.safe_load(RECORD.read_text(encoding="utf-8"))
    document["capabilities"] = [
        entry for entry in document["capabilities"] if entry["capability"] != "ext_a"
    ]
    record = tmp_path / "no-entry.yaml"
    record.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = _refusal_of(record)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "no entry for ext_a" in result.stderr, result.stderr


def test_an_unparseable_record_refuses_by_the_named_path_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    """It blocked before this — with a `yaml.parser.ParserError` traceback.

    Blocking was never the problem; the problem is that a step whose failure is a traceback
    has left the path it documents, and nobody can tell that refusal from a crash.
    """
    record = tmp_path / "unparseable.yaml"
    record.write_text("capabilities: [\n  - capability: ext_a\n", encoding="utf-8")
    result = _refusal_of(record)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "does not state the regime" in result.stderr, result.stderr
    assert "not parseable YAML" in result.stderr, result.stderr
    assert "Traceback (most recent call last)" not in result.stderr, result.stderr


def test_the_known_keys_are_derived_from_the_contract_not_typed_here() -> None:
    """A hand-written key list is one more thing that reads as true after the contract moves.

    If `ReadinessRecord` gains a field, an entry using it must stop being an unknown key
    without anyone remembering this file.
    """
    import dataclasses

    from semantic_catalog.compliance.readiness import ReadinessRecord

    module = _load_script()
    assert (
        frozenset(field.name for field in dataclasses.fields(ReadinessRecord))
        == module.KNOWN_ENTRY_KEYS
    )


def test_the_refusal_uses_the_governed_exit_code_of_this_repository() -> None:
    """`READINESS_MALFORMED` sits in `GOVERNED`, and governed content is exit 1 here.

    The first version of this script used 2, which this repository reserves for the call
    being wrong. An unparseable record is not a wrong call.
    """
    module = _load_script()
    assert module.EXIT_RECORD_DOES_NOT_SAY == 1
    assert module.EXIT_BAD_CALL == 2
