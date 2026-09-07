"""Provider artifacts stay in the adapters — T103 (ADR 0020; FR-008, FR-071; SC-033).

The core may not reach a provider SDK, endpoint or credential. The adapters may — that is what they
are for — and even there, nothing is created while `D-22` to `D-25` are undeclared.

Four assertions:

* **no provider SDK is importable from the core**, and none is declared as a dependency at all, so
  the import could not succeed even if someone wrote it;
* **no endpoint literal** — no URL, no host, no path template — exists anywhere in the package;
* **the core cannot resolve credential material**: `SecretResolver` is reachable only from
  `secrets/`
  and the adapters, never from `inbound/`, `outbound/`, `delivery/` or `governance/`;
* **the construction-only upstream names stay out of `src`**, which is the split the twenty-one-name
  allowlist rests on (`contracts/interaction-port.md` §3).
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_PACKAGE = Path(__file__).resolve().parents[2]
_SRC = _PACKAGE / "src" / "channel_integration"
_ADAPTERS = _SRC / "adapters"

#: Provider SDKs and transport clients. None is a declared dependency, and none is imported.
_PROVIDER_SDKS = {
    "slack_sdk",
    "slack",
    "telegram",
    "telethon",
    "pyrogram",
    "twilio",
    "heyoo",
    "whatsapp",
    "meta",
    "facebook",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
}


def _core_sources() -> list[Path]:
    return [
        source
        for source in sorted(_SRC.rglob("*.py"))
        if _ADAPTERS not in source.parents and source.parent != _ADAPTERS
    ]


def test_the_core_is_not_empty() -> None:
    assert len(_core_sources()) >= 25


def test_no_provider_sdk_is_importable_from_the_core() -> None:
    offenders: list[str] = []
    for source in _core_sources():
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in _PROVIDER_SDKS:
                    offenders.append(f"{source.relative_to(_SRC)}: {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in _PROVIDER_SDKS:
                        offenders.append(f"{source.relative_to(_SRC)}: {alias.name}")
    assert not offenders, offenders


def test_no_provider_sdk_is_a_declared_dependency() -> None:
    """Stronger than an import scan: the import could not succeed even if written."""
    manifest = tomllib.loads((_PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    declared = [entry.lower() for entry in manifest["project"].get("dependencies", [])]
    for group in manifest.get("dependency-groups", {}).values():
        declared.extend(str(entry).lower() for entry in group)
    for sdk in _PROVIDER_SDKS:
        assert not any(entry.startswith(sdk) for entry in declared), f"{sdk} is declared"


def test_no_endpoint_literal_exists_anywhere_in_the_package() -> None:
    """`FR-008`: an endpoint is a provider artifact, and none is created (`D-22` to `D-25`)."""
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                first = node.body[0] if node.body else None
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            for marker in ("https://", "http://", "wss://", "api.", ".com/", ".org/"):
                if marker in node.value:
                    offenders.append(f"{source.relative_to(_SRC)}: {node.value[:40]}")
    assert not offenders, offenders


def test_the_core_cannot_resolve_credential_material() -> None:
    """`FR-071`: resolution is adapter-side. The core holds references only.

    Scanned over **imports and calls**, not raw text. An earlier version matched the string
    ``SecretResolver`` anywhere and reported `delivery/ports.py`, whose docstring explains that the
    port deliberately takes no credential because material is resolved inside the adapter through
    the injected resolver. A module must be able to say what it refuses to do.
    """
    permitted = {"secrets", "adapters"}
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        if source.relative_to(_SRC).parts[0] in permitted:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "secrets" in node.module:
                imported = ", ".join(alias.name for alias in node.names)
                if "SecretResolver" in imported:
                    offenders.append(f"{source.relative_to(_SRC)}: imports {imported}")
            elif isinstance(node, ast.Call):
                called = node.func.attr if isinstance(node.func, ast.Attribute) else ""
                if called == "material_for":
                    offenders.append(f"{source.relative_to(_SRC)}: material_for()")
    assert not offenders, offenders


def test_every_adapter_implements_the_port_and_nothing_more() -> None:
    """One operation. A second is where a proactive send would eventually live."""
    for channel in ("whatsapp", "slack", "telegram", "generic"):
        source = _ADAPTERS / channel / "delivery.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        assert len(classes) == 1, f"{channel} declares {len(classes)} classes"
        methods = [
            node.name
            for node in classes[0].body
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
        ]
        assert methods == ["send"], f"{channel} exposes {methods}"


def test_no_src_module_reaches_a_construction_only_upstream_name() -> None:
    """The split behind the twenty-one-name allowlist, asserted from the adapter side too."""
    construction_only = (
        "analytics_interaction.contracts.intent",
        "analytics_query.contracts.provenance",
    )
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for module in construction_only:
            if module in text:
                offenders.append(f"{source.relative_to(_SRC)}: {module}")
    assert not offenders, offenders
