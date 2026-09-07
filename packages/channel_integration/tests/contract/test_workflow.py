"""This feature's own CI workflow, as a contract — T030 (ADR 0024; FR-099, FR-100).

`004` validates `multichannel.yml` **in its own suite**, by content and behaviour. `003`'s
guard asserts that its protected workflows are present and intact; it does not, and must
not, acquire an opinion about a later feature's CI (ADR 0024 § Acceptance).

Two kinds of assertion, mirroring how `003` validates its own workflow:

* **structural** — the workflow parses, declares one job, installs the four packages in
  dependency order, and runs every Phase A gate;
* **negative and load-bearing** — it references no secret, no service container, no
  provider, no endpoint and no credential; every step is a local, deterministic command; no
  gate is advisory, `continue-on-error` or `if: always()`.

The negative half is the point. A workflow is the one artifact in this feature that could
quietly acquire a credential, and a workflow that warns instead of failing is a workflow
whose gates nobody reads.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import channel_integration

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(channel_integration)).resolve().parent
REPO = SRC.parents[3]
WORKFLOWS = REPO / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "multichannel.yml"

#: Workflows this feature must leave alone. `003`'s guard owns the same claim from its side;
#: asserted here too, because the feature that adds a workflow is the one able to break them.
FOREIGN_WORKFLOWS = (
    "catalog.yml",
    "analytics-query.yml",
    "readiness-guard.yml",
    "nl-analytics.yml",
)


def _workflow() -> dict[str, Any]:
    loaded: object = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def _steps() -> list[dict[str, Any]]:
    jobs = cast("dict[str, Any]", _workflow()["jobs"])
    return cast("list[dict[str, Any]]", jobs["multichannel"]["steps"])


def _runs() -> list[str]:
    return [str(step["run"]) for step in _steps() if "run" in step]


# --- structural -----------------------------------------------------------------


def test_the_workflow_exists_and_parses_with_one_job() -> None:
    """A malformed workflow would make every assertion below vacuous."""
    workflow = _workflow()
    assert set(workflow["jobs"]) == {"multichannel"}
    assert _steps()


def test_the_workflow_is_additive_and_touches_no_foreign_workflow() -> None:
    """`004` adds one workflow and leaves the four protected ones alone (ADR 0024)."""
    for name in FOREIGN_WORKFLOWS:
        assert (WORKFLOWS / name).is_file(), f"{name} must still be present"
    assert WORKFLOW.is_file()
    for run in _runs():
        for name in FOREIGN_WORKFLOWS:
            assert name not in run, f"a step references the foreign workflow {name}"


def test_it_installs_the_four_packages_in_dependency_order() -> None:
    """The install order is what supplies each path dependency.

    `semantic_catalog` ← `analytics_query` ← `analytics_interaction` ← `channel_integration`,
    and every install carries `[dev]`: `001`'s readiness workflow once installed without the
    extra and failed on a missing module rather than on anything it guarded.
    """
    script = "\n".join(_runs())
    positions = [
        script.index(f"packages/{package}[dev]")
        for package in (
            "semantic_catalog",
            "analytics_query",
            "analytics_interaction",
            "channel_integration",
        )
    ]
    assert positions == sorted(positions), "packages are installed out of dependency order"


@pytest.mark.parametrize(
    "gate",
    [
        "ruff format --check packages/channel_integration",
        "ruff check packages/channel_integration",
        "pyright",
        "pytest -q",
        "test_reason_code_namespaces.py",
        "test_reason_code_totality.py",
        "test_audit_stages.py",
        "test_contract_hygiene.py",
        "test_messages.py",
        "test_readiness.py",
        "test_dependency_direction.py",
        "test_no_readiness_claim.py",
        "test_cross_artifact_links.py",
    ],
)
def test_every_phase_a_gate_is_run(gate: str) -> None:
    """Each Phase A guarantee has a named step, so a failure names what broke."""
    assert any(gate in run for run in _runs()), f"no step runs {gate}"


def test_the_upstream_suites_are_run_whole() -> None:
    """Node-ID preservation is checked by running the three suites, not by counting."""
    script = "\n".join(_runs())
    for package in ("semantic_catalog", "analytics_query", "analytics_interaction"):
        assert f"pytest -q packages/{package}" in script, f"{package} is not run whole"


# --- negative, and load-bearing -------------------------------------------------


def test_no_secret_credential_or_provider_is_referenced() -> None:
    """`FR-097`, `NG-10`: no credential, endpoint, bot, number or secret is introduced."""
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in (
        "secrets.",
        "${{ secrets",
        "GITHUB_TOKEN",
        "api.telegram.org",
        "hooks.slack.com",
        "graph.facebook.com",
        "xoxb-",
        "Bearer ",
        "services:",
        "container:",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "gcloud",
        "bq ",
    ):
        assert forbidden not in text, f"the workflow references {forbidden!r}"


def test_no_step_reaches_the_network_beyond_its_package_install() -> None:
    """Every gate is a local, deterministic command over this repository.

    `pip install` is the one network operation, and it installs the four local packages plus
    their pinned dependencies — no provider SDK, no HTTP client, no warehouse client
    (`R-20`).
    """
    for run in _runs():
        for forbidden in ("curl", "wget", "nc ", "ssh ", "docker "):
            assert forbidden not in run, f"a step runs {forbidden!r}"


def test_no_gate_is_advisory() -> None:
    """A gate that warns is a gate that gets ignored."""
    for step in _steps():
        assert step.get("continue-on-error") is not True, f"{step.get('name')} continues on error"
        assert str(step.get("if", "")).strip() != "always()", f"{step.get('name')} is if: always()"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "continue-on-error: true" not in text
    assert "|| true" not in text, "a step swallows its own failure"


def test_permissions_are_read_only_and_concurrency_is_declared() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    concurrency = cast("dict[str, Any]", workflow["concurrency"])
    assert concurrency["cancel-in-progress"] is True
    assert "multichannel-" in str(concurrency["group"])


def test_it_claims_no_readiness_and_declares_its_phase_a_scope() -> None:
    """`FR-100`: the workflow states what it does not do, so a reader cannot infer more."""
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    assert "phase a scope" in text
    for statement in ("must not", "no `secrets` reference", "fixture-backed"):
        assert statement.lower() in text, f"the workflow does not state: {statement}"


def test_the_absent_schema_drift_gate_is_recorded_as_deferred() -> None:
    """A missing gate must be a recorded decision, not an unexplained absence.

    The three earlier workflows each run a schema-drift check. This one does not, because
    the surface it would check does not exist yet: the exporting CLI is `T150` and the
    no-drift contract test is `T152`, both Phase E. A gate over an absent CLI would pass
    because nothing could drift — a guarantee nobody is holding.

    Two halves, so neither the omission nor its record can drift from the other: no step
    runs a schema gate today, **and** the deferral names its owning tasks.
    """
    assert not any("schema" in run.lower() for run in _runs()), (
        "a schema gate exists; the deferral record is now wrong"
    )
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "SCHEMA EXPORT AND SCHEMA-DRIFT GATE: DEFERRED" in text
    for owner_task in ("T150", "T152"):
        assert owner_task in text, f"the deferral does not name {owner_task}"
