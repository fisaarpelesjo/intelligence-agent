"""No persistence, no network, no background work — T141 (FR-055; SC-027).

    Evidence: no durable store is owned; no persistence call exists.
    — `tasks.md` T141

This feature emits events and refuses to define their transport. It holds no
ledger, no cache, no queue, no file, no database and no in-memory registry that
outlives a call — and that is not a simplification, it is the property the whole
stateless design rests on:

* a **store** would need its own access control, retention and audit, and would
  hold exactly the values every other guard exists to remove;
* a **queue** or **buffer** would let an event outlive the request that produced
  it, which is how "synchronous and fail-closed" becomes "eventually, probably";
* a **network exporter** would be an egress path nobody reviewed, carrying the
  attributes the telemetry allowlist spent its effort bounding;
* a **retry** would convert "this was not recorded" into "this will probably be
  recorded", and the caller receives an answer either way.

The scan is over AST identifiers and imports, not text, so a docstring
explaining that there is no cache does not read as a cache. Every category has
planted cases, because a denylist never shown to fire proves nothing.

`002` owns durable audit storage through `EXT-B`; the deployment owns transport.
A feature that emits an event it cannot archive is honest about the gap; one that
invents an archive claims a readiness nobody approved.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import analytics_interaction

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

#: Modules that would give this feature a store, a socket or a scheduler.
FORBIDDEN_MODULES = frozenset(
    {
        "sqlite3",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "sqlalchemy",
        "redis",
        "pymongo",
        "boto3",
        "kafka",
        "pika",
        "celery",
        "kombu",
        "rq",
        "apscheduler",
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "smtplib",
        "ftplib",
        "shelve",
        "dbm",
        "pickle",
        "marshal",
        "opentelemetry",
        "prometheus_client",
        "statsd",
        "threading",
        "multiprocessing",
        "asyncio",
        "concurrent",
        "subprocess",
        "tempfile",
    }
)

#: Memoisation names. Caught as **imports** too: ``from functools import
#: lru_cache`` introduces no attribute access and no bare ``Name`` at the call
#: site until it is applied as a decorator, so an import-only check is what
#: catches the decorator form.
CACHING_NAMES = frozenset({"lru_cache", "cache", "cached_property", "memoize"})

#: The one reviewed exemption, named rather than pattern-matched.
#:
#: ``messages/registry.py`` memoises a **read of governed content**, bounded at
#: eight languages. It holds no question, no answer, no event and no business
#: value — it is the parsed form of a file this feature reads at startup, and
#: re-parsing it per refusal would make governed wording a per-request cost with
#: no change in behaviour.
#:
#: Named here so the exemption is reviewable. A second entry on this list should
#: be argued for, not added.
CACHE_EXEMPT = frozenset({"messages/registry.py"})

#: Calls that write, connect, schedule, retry or remember.
FORBIDDEN_CALLS = frozenset(
    {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "mkdir",
        "touch",
        "unlink",
        "connect",
        "execute",
        "executemany",
        "commit",
        "cursor",
        "publish",
        "enqueue",
        "put_nowait",
        "send",
        "sendall",
        "post",
        "urlopen",
        "retry",
        "sleep",
        "Thread",
        "Timer",
        "Process",
        "create_task",
    }
)


def _source_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


#: The only two writable things this feature may touch, spelled as full chains.
#:
#: ``write`` stays on :data:`FORBIDDEN_CALLS` — a handle received as a parameter
#: and written to is exactly the persistence the scan is for, and ``open`` being
#: banned does not stop a caller passing one in. What is carved out is narrower
#: than "writing": it is these two attribute chains, on a stream the caller
#: already owns and already sees.
STANDARD_STREAMS = frozenset({"sys.stdout", "sys.stderr"})


def _is_a_standard_stream(node: ast.Attribute) -> bool:
    """``sys.stdout.write`` and ``sys.stderr.write``, and nothing that merely resembles them.

    Matched on the unparsed chain rather than the trailing name, so a local
    rebinding — ``stdout = open(path); stdout.write(...)`` — is not covered by
    this and still fails.
    """
    return node.attr == "write" and ast.unparse(node.value) in STANDARD_STREAMS


def _violations(source: str, filename: str = "<test>", *, allow_caching: bool = False) -> list[str]:
    """Persistence, network, scheduling, retry and caching surfaces, by AST."""
    tree = ast.parse(source, filename=filename)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [
                f"{node.lineno}:import:{alias.name}"
                for alias in node.names
                if alias.name.split(".")[0] in FORBIDDEN_MODULES
            ]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_MODULES:
                found.append(f"{node.lineno}:import:{node.module}")
            found += [
                f"{node.lineno}:cache:{alias.name}"
                for alias in node.names
                if alias.name in CACHING_NAMES and not allow_caching
            ]
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_CALLS and not _is_a_standard_stream(node):
                found.append(f"{node.lineno}:call:{node.attr}")
            elif node.attr in CACHING_NAMES and not allow_caching:
                found.append(f"{node.lineno}:cache:{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_CALLS:
                found.append(f"{node.lineno}:call:{node.id}")
            elif node.id in CACHING_NAMES and not allow_caching:
                found.append(f"{node.lineno}:cache:{node.id}")
    return found


def _mutations(tree: ast.Module) -> set[str]:
    """Names a module actually mutates.

    A module-level lookup table that is only ever read is not a store, however it
    is spelled — several in this package are wrapped in ``MappingProxyType``
    precisely so they cannot become one. What matters is whether anything grows.
    """
    grown: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"append", "add", "update", "extend", "setdefault", "pop"}:
                grown.add(ast.unparse(node.func.value))
        elif isinstance(node, ast.Assign):
            grown.update(
                ast.unparse(target.value)
                for target in node.targets
                if isinstance(target, ast.Subscript)
            )
    return grown


# --- the source tree is clean -----------------------------------------------------


def test_no_source_module_persists_connects_schedules_or_retries() -> None:
    """The whole package, every category at once."""
    offenders = [
        f"{relative}:{hit}"
        for path in _source_files()
        for relative in [path.relative_to(SRC).as_posix()]
        for hit in _violations(
            path.read_text(encoding="utf-8"), str(path), allow_caching=relative in CACHE_EXEMPT
        )
    ]
    assert not offenders, f"a persistence or network surface exists: {offenders}"


def test_the_audit_and_telemetry_modules_own_no_transport() -> None:
    """Scoped, because these two are where a transport would arrive first.

    An emitter that grew an exporter would look like a natural addition, and it
    would be the one place the whole feature's value-freedom stops being
    checkable.
    """
    from analytics_interaction.audit import emit
    from analytics_interaction.telemetry import spans

    for module in (emit, spans):
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        assert not _violations(source, inspect.getfile(module))


def test_no_module_level_container_is_ever_mutated() -> None:
    """A module-level container that **grows** is a store nobody called a store.

    Narrowed from "no module-level dict exists", which fired on six read-only
    lookup tables — several already wrapped in ``MappingProxyType`` precisely so
    they cannot become stores. A table that is only ever read holds nothing
    between calls, and a scan that flagged it would be deleted rather than
    narrowed. What matters is whether anything accumulates.
    """
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        grown = _mutations(tree)
        for node in tree.body:
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            if not isinstance(node.value, ast.List | ast.Dict | ast.Set):
                continue
            targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            names = [ast.unparse(target) for target in targets]
            if names != ["__all__"] and set(names) & grown:
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {names}")
    assert not offenders, f"module-level mutable state is mutated: {offenders}"


def test_the_package_declares_no_runtime_transport_dependency() -> None:
    """The manifest, not only the imports.

    A declared dependency nobody imports yet is a decision already taken.
    """
    manifest = (SRC.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    runtime = manifest.split("[project.optional-dependencies]")[0]
    for forbidden in ("sqlalchemy", "psycopg", "redis", "requests", "httpx", "opentelemetry"):
        assert forbidden not in runtime, f"{forbidden} is a declared runtime dependency"


def test_no_source_module_opens_a_file_for_writing() -> None:
    """Governed content is **read**. Nothing in this feature writes."""
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if name in {"open", "write_text", "write_bytes"}:
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
    assert not offenders, f"a write path exists: {offenders}"


# --- the scan fires ---------------------------------------------------------------


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param("import sqlite3\ndef go():\n    return sqlite3\n", id="database"),
        pytest.param("import redis\ndef go():\n    return redis\n", id="cache-server"),
        pytest.param("from celery import Celery\n", id="queue"),
        pytest.param("import httpx\ndef go():\n    return httpx\n", id="http-client"),
        pytest.param("import opentelemetry\n", id="tracing-sdk"),
        pytest.param("import threading\n", id="background-thread"),
        pytest.param("def go(p):\n    return p.write_text('x')\n", id="file-write"),
        pytest.param("def go(c):\n    return c.connect()\n", id="connect"),
        pytest.param("from functools import lru_cache\n", id="cache-decorator"),
        pytest.param("import time\ndef go():\n    time.sleep(1)\n", id="retry-sleep"),
        pytest.param("import pickle\n", id="serialisation-store"),
        pytest.param("def go(q):\n    return q.put_nowait(1)\n", id="enqueue"),
        # The stream carve-out, probed from the outside. A handle that arrives
        # as a parameter is the case bare ``write`` exists for, and carving out
        # the two standard streams must not have taken it with them.
        pytest.param("def go(handle):\n    return handle.write('x')\n", id="handed-a-handle"),
        pytest.param(
            "def go(p):\n    out = p.open('w')\n    out.write('x')\n", id="rebound-stream"
        ),
        pytest.param("def go(s):\n    return s.stdout.write('x')\n", id="not-the-sys-stdout"),
    ],
)
def test_the_scan_catches_a_planted_surface(planted: str) -> None:
    """Twelve categories, twelve plantings. A denylist never shown to fire
    proves nothing about the failures it was written for."""
    assert _violations(planted), "a persistence or network surface was not detected"


@pytest.mark.parametrize(
    "innocent",
    [
        pytest.param('"""No durable store is owned by this feature."""\n', id="docstring"),
        pytest.param("CACHE_IS_FORBIDDEN = True\n", id="similar-name"),
        pytest.param("from pathlib import Path\ndef go(p):\n    return p.read_text()\n", id="read"),
        pytest.param("def go(items):\n    return sorted(items)\n", id="pure-function"),
        pytest.param("import sys\ndef go():\n    sys.stdout.write('x')\n", id="answering-stdout"),
        pytest.param("import sys\ndef go():\n    sys.stderr.write('x')\n", id="failing-to-stderr"),
    ],
)
def test_the_scan_does_not_fire_on_prose_or_on_reading(innocent: str) -> None:
    """Governed content is read at every startup. Reading is not persistence.

    Nor is answering. The CLI writes its one JSON object to a stream the caller
    already owns and already sees — nothing outlives the process, which is the
    property this whole file is about.
    """
    assert not _violations(innocent)


def test_the_only_cache_in_the_package_is_the_governed_content_read() -> None:
    """The exemption, asserted rather than assumed.

    If a second module acquires a cache, the scan above catches it — and this
    asserts the exemption list itself has not quietly grown.
    """
    assert set(CACHE_EXEMPT) == {"messages/registry.py"}

    cached = [
        relative
        for path in _source_files()
        for relative in [path.relative_to(SRC).as_posix()]
        if any(
            hit.startswith(tuple(f"{n}:cache" for n in range(1, 10_000))) or ":cache:" in hit
            for hit in _violations(path.read_text(encoding="utf-8"), str(path))
        )
    ]
    assert cached == ["messages/registry.py"], cached


def test_the_governed_content_cache_holds_no_business_value() -> None:
    """What the exemption is exempt *for*.

    It memoises the parsed form of an authored file. Nothing about a question, an
    answer, an event or a figure enters it, and it is bounded by the number of
    languages rather than by traffic.
    """
    from analytics_interaction.messages import registry

    source = Path(inspect.getfile(registry)).read_text(encoding="utf-8")
    assert "maxsize=8" in source
    assert "_cached_registry" in source
    assert "def _cached_registry(language: str)" in source


# --- and the future store stays declared ---------------------------------------------


def test_the_future_conversation_store_is_still_unimplemented() -> None:
    """`NG-17`, re-checked from the persistence side.

    Phase 11 declared the boundary; this is the scan that would notice an
    implementation arriving behind it.
    """
    from analytics_interaction.clarification import future_store

    source = Path(inspect.getfile(future_store)).read_text(encoding="utf-8")
    assert not _violations(source, inspect.getfile(future_store))

    tree = ast.parse(source)
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    #: Amended by `OD-69` (2026-08-31): two protocols, still zero implementations in this package.
    assert {node.name for node in classes} == {"ConversationStore", "ConversationMemory"}
    for declared in classes:
        assert any("Protocol" in ast.unparse(base) for base in declared.bases), declared.name
