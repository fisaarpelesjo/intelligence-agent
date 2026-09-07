"""The first catalog a repository ever gets — CI bootstrap for ``catalog diff``.

``catalog diff --base origin/main`` is the steward-facing half of the version
gate. It assumes the base ref carries a catalog to compare against. Exactly once
in a repository's life that assumption is false: the pull request introducing
the **first** catalog has a base that legitimately has none.

The failure mode being guarded here is not "the command errored". It is the
opposite: that a base ref which resolves to nothing useful — a typo, a deleted
branch, an unrelated repository — gets read as "this is the first catalog" and
the version gate waves the change through. So the bootstrap path is reached only
after two proofs: the base ref resolves to a real commit, and the current
catalog loads. Everything else stays an error, and the errors stay distinct.

Each test builds a throwaway Git repository rather than leaning on this one, so
the bootstrap case remains testable after this repository stops having one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from semantic_catalog.cli.main import EXIT_INVOCATION, EXIT_OK, EXIT_VIOLATION, main

REPO = Path(__file__).resolve().parents[4]
PRODUCTION = REPO / "semantic"


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _repo_with_empty_base(tmp_path: Path) -> Path:
    """A repository whose first commit carries no catalog at all.

    This is the real shape of the bootstrap case: ``main`` exists, is a valid
    ref, and has nothing at ``semantic/`` because the catalog arrives in the
    branch under review.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch", "main")
    _git(repo, "config", "user.email", "ci@example.invalid")
    _git(repo, "config", "user.name", "CI")
    (repo / "README.md").write_text("no catalog yet\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial commit without a catalog")
    return repo


def _add_catalog(repo: Path) -> Path:
    """Copy the production catalog in as a working-tree change, uncommitted.

    Uncommitted on purpose — ``diff`` reads the base from Git and the current
    catalog from disk, which is exactly how CI sees a pull request.
    """
    root = repo / "semantic"
    shutil.copytree(PRODUCTION, root)
    return root


def _run(
    capsys: pytest.CaptureFixture[str], repo: Path, root: Path, *extra: str
) -> tuple[int, str]:
    code = main(["diff", "--base", "main", "--repo", str(repo), "--path", str(root), *extra])
    return code, capsys.readouterr().out


# --- the bootstrap case itself ----------------------------------------------


def test_a_base_without_a_catalog_is_the_initial_governed_addition(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)

    code, out = _run(capsys, repo, root)

    assert code == EXIT_OK
    assert "initial governed addition" in out


def test_the_bootstrap_verdict_is_machine_readable_and_explicit(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A consumer must be able to tell bootstrap from "nothing changed".

    Both exit ``0``. Only the payload distinguishes them, so the distinction has
    to be a field rather than a sentence in the human-readable output.
    """
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)

    code, out = _run(capsys, repo, root, "--format", "json")
    payload = json.loads(out)

    assert code == EXIT_OK
    assert payload["bootstrap"] is True
    assert payload["base_catalog_present"] is False
    assert payload["requires_new_version"] is False
    assert payload["base"] == "main"
    assert payload["changes"], "the first catalog is an addition, not an empty diff"
    assert {c["classification"] for c in payload["changes"]} == {"initial_catalog"}
    assert not any(c["requires_new_version"] for c in payload["changes"])
    assert not any(c["closed"] for c in payload["changes"])


def test_the_bootstrap_verdict_is_deterministic(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)

    _, first = _run(capsys, repo, root, "--format", "json")
    _, second = _run(capsys, repo, root, "--format", "json")

    assert first == second, "the same invocation produced different bytes"


def test_bootstrap_classifies_every_authored_metric(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """No metric may be silently omitted from the initial classification."""
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)

    _, out = _run(capsys, repo, root, "--format", "json")
    payload = json.loads(out)

    authored = {path.stem for path in (root / "metrics").glob("*.yaml")}
    assert {c["metric"] for c in payload["changes"]} == authored


# --- what bootstrap must NOT swallow ----------------------------------------


def test_an_invalid_base_ref_is_an_invocation_error_not_a_bootstrap(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The whole point of the guard: a typo must not read as "first catalog"."""
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)

    code = main(["diff", "--base", "no-such-ref", "--repo", str(repo), "--path", str(root)])
    out = capsys.readouterr().out

    assert code == EXIT_INVOCATION
    assert "bootstrap" not in out
    assert "initial governed addition" not in out


def test_a_missing_current_catalog_is_an_invocation_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """An absent catalog on *both* sides is a broken call, not an empty diff."""
    repo = _repo_with_empty_base(tmp_path)

    code = main(["diff", "--base", "main", "--repo", str(repo), "--path", str(repo / "semantic")])
    out = capsys.readouterr().out

    assert code == EXIT_INVOCATION
    assert "initial governed addition" not in out


def test_a_malformed_current_catalog_is_a_violation_not_a_bootstrap(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Unloadable content is a finding even when there is nothing to compare to.

    Exit 1, not 2: the catalog exists and is wrong. Bootstrap must not become
    the path where a broken tree goes unreported for want of a baseline.
    """
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)
    (root / "metrics" / "sessions.yaml").write_text("kind: [broken\n", encoding="utf-8")

    code, out = _run(capsys, repo, root)

    assert code == EXIT_VIOLATION
    assert "initial governed addition" not in out


def test_a_repository_that_is_not_one_is_an_invocation_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    root = plain / "semantic"
    shutil.copytree(PRODUCTION, root)

    code = main(["diff", "--base", "main", "--repo", str(plain), "--path", str(root)])
    out = capsys.readouterr().out

    assert code == EXIT_INVOCATION
    assert "initial governed addition" not in out


# --- and what it must not weaken --------------------------------------------


def test_a_base_that_has_a_catalog_still_takes_the_normal_path(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Bootstrap is reachable once. After that the version gate is unchanged."""
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)
    _git(repo, "add", "semantic")
    _git(repo, "commit", "-m", "add the first catalog")

    code, out = _run(capsys, repo, root, "--format", "json")
    payload = json.loads(out)

    assert code == EXIT_OK
    assert payload["bootstrap"] is False
    assert payload["base_catalog_present"] is True
    assert payload["changes"] == [], "an unchanged tree against its own commit"
    assert "initial governed addition" not in out


def test_semantic_enforcement_survives_once_the_base_has_a_catalog(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The regression that would matter most: a Semantic edit still blocks.

    Edits ``calculation_basis`` on a committed version block without appending a
    new one. Before the bootstrap change this exited 1; it must still exit 1.
    """
    repo = _repo_with_empty_base(tmp_path)
    root = _add_catalog(repo)
    _git(repo, "add", "semantic")
    _git(repo, "commit", "-m", "add the first catalog")

    path = root / "metrics" / "sessions.yaml"
    text = path.read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if line.strip().startswith("calculation_basis:"))
    path.write_text(
        text.replace(line, f"{line.split(':', 1)[0]}: something materially different"),
        encoding="utf-8",
    )

    code, out = _run(capsys, repo, root, "--format", "json")
    payload = json.loads(out)

    assert code == EXIT_VIOLATION
    assert payload["bootstrap"] is False
    assert payload["requires_new_version"] is True
    assert any(c["classification"] == "semantic" for c in payload["changes"])
