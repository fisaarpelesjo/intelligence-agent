"""This package owns no listener — T056 (`A-1`, `A-2`, `D-30`; SC-062).

Feature 004 is a library: contracts, ports, adapters, a CLI for internal validation. It does not
own the HTTP transport, the socket, the resident process, the scheduler or the queue. That
ownership is `D-30`, undeclared, and the boundary is load-bearing rather than tidy — a package that
quietly grew a listener would be running unreviewed network code under a spec that says it does not.

Asserted by **absence**, across three surfaces:

* no module imports a server, socket, ASGI/WSGI framework, scheduler or broker client;
* no dependency declares one;
* no deployment artifact — Dockerfile, compose file, service unit, chart, procfile — exists in the
  package.

The complement is asserted too: conversion is drivable with no transport present at all. Without
that, "owns no listener" could be satisfied by a package that does nothing.

`D-30` being undeclared is recorded here as the reason the gap exists, so a reader who wonders "then
who receives the webhook?" gets the answer instead of assuming an oversight.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.inbound.convert import convert

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    bounds_for,
    descriptor_for,
    signed_request,
)
from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
)

pytestmark = pytest.mark.contract

_PACKAGE = Path(__file__).resolve().parents[2]
_SRC = _PACKAGE / "src" / "channel_integration"

#: Modules and distributions that *are* a listener, a resident process or a broker. Importing one
#: is owning one, whatever the surrounding comment says.
_TRANSPORT_MODULES = (
    "socket",
    "socketserver",
    "http.server",
    "asyncio",
    "selectors",
    "ssl",
    "wsgiref",
    "fastapi",
    "starlette",
    "flask",
    "django",
    "uvicorn",
    "gunicorn",
    "hypercorn",
    "aiohttp",
    "tornado",
    "requests",
    "httpx",
    "urllib.request",
    "urllib3",
    "celery",
    "kombu",
    "redis",
    "pika",
    "kafka",
    "apscheduler",
    "schedule",
    "google.cloud.pubsub",
)

_IMPORT_LINE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)")

#: Filenames that only exist to run something resident.
_DEPLOYMENT_ARTIFACTS = (
    "Dockerfile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "Procfile",
    "*.service",
    "Chart.yaml",
    "values.yaml",
    "*.tf",
    "app.yaml",
    "fly.toml",
    "vercel.json",
)


def test_no_module_imports_a_transport_server_or_broker() -> None:
    """`SC-062`, by import scan over every module in the package."""
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            match = _IMPORT_LINE.match(line)
            if match is None:
                continue
            imported = match.group(1)
            for module in _TRANSPORT_MODULES:
                if imported == module or imported.startswith(f"{module}."):
                    offenders.append(f"{source.relative_to(_SRC)}:{number}: {imported}")
    assert not offenders, offenders


def test_no_module_binds_listens_or_serves() -> None:
    """The call-level version: a bind or a serve loop, however it was reached."""
    forbidden = (
        ".bind(",
        ".listen(",
        ".serve_forever(",
        "run_forever(",
        "asyncio.run(",
        "while True:",
        "app = ",
        "@app.",
    )
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{source.relative_to(_SRC)}: {token}")
    assert not offenders, offenders


def test_the_declared_dependencies_contain_no_server_or_broker() -> None:
    """A dependency is a claim about what this package needs to run."""
    manifest = tomllib.loads((_PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    project = manifest["project"]
    declared: list[str] = list(project.get("dependencies", []))
    for group in manifest.get("dependency-groups", {}).values():
        declared.extend(str(entry) for entry in group)
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(str(entry) for entry in extra)

    lowered = [entry.lower() for entry in declared]
    for module in _TRANSPORT_MODULES:
        distribution = module.split(".")[0]
        if distribution in {
            "socket",
            "socketserver",
            "http",
            "asyncio",
            "selectors",
            "ssl",
            "wsgiref",
            "urllib",
        }:
            continue  # standard library; covered by the import scan, not installable
        assert not any(entry.startswith(distribution) for entry in lowered), (
            f"a {distribution} dependency is declared"
        )


def test_the_package_declares_no_console_entry_point_yet() -> None:
    """The CLI arrives in Phase E and is invoked as a module until it exists (`T150`).

    A console script declared before the entry point exists would be a broken promise in metadata.
    """
    manifest = tomllib.loads((_PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    assert "scripts" not in manifest["project"]
    assert "gui-scripts" not in manifest["project"]


def test_the_package_contains_no_deployment_artifact() -> None:
    offenders: list[str] = []
    for pattern in _DEPLOYMENT_ARTIFACTS:
        offenders.extend(str(path.relative_to(_PACKAGE)) for path in _PACKAGE.rglob(pattern))
    assert not offenders, offenders


def test_conversion_runs_with_no_transport_present() -> None:
    """The complement. "Owns no listener" must not be satisfied by owning nothing.

    Nothing here opens a socket, and a full envelope is still produced from bytes and headers.
    """
    outcome = convert(
        signed_request(ChannelId.SLACK),
        descriptor=descriptor_for(ChannelId.SLACK),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(ChannelId.SLACK),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)


def test_the_readiness_record_still_owns_the_listener_gap() -> None:
    """`D-30` undeclared is *why* there is no listener. Asserted, so the gap stays governed."""
    readiness = (
        _PACKAGE.parents[1] / "docs" / "readiness" / "multichannel-external-readiness.yaml"
    ).read_text(encoding="utf-8")
    assert "d_30" in readiness
    section = readiness.split("d_30", 1)[1]
    assert re.search(r"declared:\s*false", section), "D-30 must remain undeclared"
