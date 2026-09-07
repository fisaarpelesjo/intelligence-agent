"""`catalog release` end to end — T096 (FR-065, FR-075; quickstart Scenario 21).

The library already refuses identifier reuse, unvalidated publication and the
reactivation of a withdrawn release. What is proved here is that the **CLI**
carries those refusals through a real file round trip rather than losing them at
the boundary — and that a refusal leaves the ledger untouched, which is the part
a persistence layer is most likely to get wrong.

The ledger is **not catalog content**: it records which builds were published,
withdrawn and activated. It has no default path, so no invocation writes
anything the steward did not name.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from semantic_catalog.cli.main import EXIT_INVOCATION, EXIT_OK, EXIT_VIOLATION, main

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[4]
PRODUCTION = REPO / "semantic"
ON = "2026-08-11"


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


def _ledger(path: Path) -> dict[str, list[dict[str, str]]]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "release-ledger.json"


def _publish(
    capsys: pytest.CaptureFixture[str], ledger: Path, path: Path = PRODUCTION
) -> tuple[int, str]:
    return _run(
        capsys,
        "release",
        "publish",
        "--ledger",
        str(ledger),
        "--reason",
        "initial release",
        "--actor-role",
        "data_governance",
        "--path",
        str(path),
        "--on",
        ON,
        "--commit",
        "head",
    )


def test_status_on_an_absent_ledger_reports_no_active_release(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    """An absent ledger is an empty one, not a pass."""
    code, out = _run(capsys, "release", "status", "--ledger", str(ledger_path))
    assert code == EXIT_OK
    assert "(none)" in out
    assert not ledger_path.exists(), "status must not create the ledger it reads"


def test_publishing_a_valid_release_records_it(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    code, out = _publish(capsys, ledger_path)
    assert code == EXIT_OK
    assert "is now active" in out
    stored = _ledger(ledger_path)
    assert len(stored["releases"]) == 1
    assert stored["releases"][0]["state"] == "active"
    assert stored["events"][0]["kind"] == "publish"
    assert stored["events"][0]["validated_commit"] == "head"


def test_publishing_an_invalid_release_refuses_and_writes_nothing(
    capsys: pytest.CaptureFixture[str], ledger_path: Path, tmp_path: Path
) -> None:
    """The active pointer moves only after validation succeeds (FR-075)."""
    root = tmp_path / "broken"
    shutil.copytree(PRODUCTION, root)
    owners = root / "owners.yaml"
    owners.write_text(
        owners.read_text(encoding="utf-8").replace("id: product_analytics", "id: renamed_team"),
        encoding="utf-8",
    )
    code, out = _publish(capsys, ledger_path, root)
    assert code == EXIT_VIOLATION
    assert "refusing to publish" in out
    assert not ledger_path.exists(), "a refused publication must leave no ledger behind"


def test_publishing_the_same_identifier_twice_is_refused(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    _publish(capsys, ledger_path)
    before = ledger_path.read_text(encoding="utf-8")
    code, out = _publish(capsys, ledger_path)
    assert code == EXIT_VIOLATION
    assert "never reused" in out
    assert ledger_path.read_text(encoding="utf-8") == before


def test_withdrawal_keeps_the_release_resolvable(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    _publish(capsys, ledger_path)
    release_id = _ledger(ledger_path)["releases"][0]["release_id"]

    code, out = _run(
        capsys,
        "release",
        "withdraw",
        release_id,
        "--ledger",
        str(ledger_path),
        "--reason",
        "incorrect aggregation",
        "--actor-role",
        "data_governance",
    )
    assert code == EXIT_OK
    assert "is now withdrawn" in out

    stored = _ledger(ledger_path)
    entry = next(r for r in stored["releases"] if r["release_id"] == release_id)
    assert entry["state"] == "withdrawn"
    assert "withdrawn_at" in entry
    assert [e["kind"] for e in stored["events"]] == ["publish", "withdraw"]

    code, out = _run(capsys, "release", "status", "--ledger", str(ledger_path))
    assert release_id in out
    assert "(no new decisions)" in out


def test_a_withdrawn_release_denies_a_new_decision(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    _publish(capsys, ledger_path)
    release_id = _ledger(ledger_path)["releases"][0]["release_id"]
    _run(
        capsys,
        "release",
        "withdraw",
        release_id,
        "--ledger",
        str(ledger_path),
        "--reason",
        "wrong",
        "--actor-role",
        "data_governance",
    )
    code, out = _run(
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
        "--commit",
        "head",
        "--ledger",
        str(ledger_path),
        "--release-id",
        release_id,
    )
    assert code == EXIT_VIOLATION
    assert "RELEASE_WITHDRAWN" in out


def test_a_withdrawn_release_is_never_reactivated(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    _publish(capsys, ledger_path)
    release_id = _ledger(ledger_path)["releases"][0]["release_id"]
    _run(
        capsys,
        "release",
        "withdraw",
        release_id,
        "--ledger",
        str(ledger_path),
        "--reason",
        "wrong",
        "--actor-role",
        "data_governance",
    )
    before = ledger_path.read_text(encoding="utf-8")
    code, out = _run(
        capsys,
        "release",
        "activate",
        release_id,
        "--ledger",
        str(ledger_path),
        "--reason",
        "rollback",
        "--actor-role",
        "data_governance",
    )
    assert code == EXIT_VIOLATION
    assert "corrective release" in out
    assert ledger_path.read_text(encoding="utf-8") == before


def test_rollback_appends_a_new_activation_event(
    capsys: pytest.CaptureFixture[str], ledger_path: Path, tmp_path: Path
) -> None:
    _publish(capsys, ledger_path)
    first = _ledger(ledger_path)["releases"][0]["release_id"]

    # A second release whose PUBLIC bundle differs, so its content hash differs.
    # A comment or a descriptive edit would not move it: the id is a hash of the
    # public projection, and a pending metric's projection carries neither.
    variant = tmp_path / "variant"
    shutil.copytree(PRODUCTION, variant)
    source = variant / "metrics" / "sessions.yaml"
    (variant / "metrics" / "sessions_weekly.yaml").write_text(
        source.read_text(encoding="utf-8").replace("name: sessions", "name: sessions_weekly"),
        encoding="utf-8",
    )
    code, out = _publish(capsys, ledger_path, variant)
    assert code == EXIT_OK, out

    code, _ = _run(
        capsys,
        "release",
        "activate",
        first,
        "--ledger",
        str(ledger_path),
        "--reason",
        "rollback",
        "--actor-role",
        "data_governance",
    )
    assert code == EXIT_OK

    stored = _ledger(ledger_path)
    kinds = [e["kind"] for e in stored["events"]]
    assert kinds == ["publish", "publish", "activate"]
    assert len({e["event_id"] for e in stored["events"]}) == 3
    active = [r for r in stored["releases"] if r["state"] == "active"]
    assert [r["release_id"] for r in active] == [first]


def test_a_malformed_ledger_fails_closed(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    ledger_path.write_text('{"releases": [{"release_id": "x"}]}', encoding="utf-8")
    assert main(["release", "status", "--ledger", str(ledger_path)]) == EXIT_INVOCATION
    capsys.readouterr()


def test_a_ledger_with_a_duplicate_identifier_is_refused(
    capsys: pytest.CaptureFixture[str], ledger_path: Path
) -> None:
    """Two releases that cannot be told apart make every decision citing one of
    them unauditable.

    Exit 1, not 2: the file parsed, and what is wrong is its **content**. A
    ledger that will not parse at all is a caller-supplied input that could not
    be read, and that is the usage error.
    """
    _publish(capsys, ledger_path)
    stored = _ledger(ledger_path)
    stored["releases"].append(dict(stored["releases"][0]))
    ledger_path.write_text(json.dumps(stored), encoding="utf-8")
    code, out = _run(capsys, "release", "status", "--ledger", str(ledger_path))
    assert code == EXIT_VIOLATION
    assert "never reused" in out


def test_the_ledger_has_no_default_path() -> None:
    """Nothing is written unless the steward names the file."""
    assert main(["release", "status"]) == EXIT_INVOCATION
