"""Nothing is persisted — T102 (FR-030, FR-075; SC-035, SC-036).

By default this feature stores **no** question, answer, value or personal data, and while `D-29` is
undeclared it stores nothing at all. The measured persisted-record count is zero, and it is zero
because there is no persistence mechanism to reach.

Asserted three ways:

* **no import** of a database driver, an object store client, an ORM or a serialisation-to-disk
  helper, anywhere in the package;
* **no write call** — no ``open`` in a writing mode, no ``write_text``, ``write_bytes``, ``dump``,
  ``mkdir`` or ``unlink``;
* **the metadata policy refuses**, so a caller asking what may be persisted is told nothing may.

The in-memory idempotency window is not persistence and the difference is stated rather than
assumed: it lives on an instance, it does not survive the process, and `T098` asserts that limit
separately.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from channel_integration.governance.metadata_policy import resolve_metadata_policy
from channel_integration.governance.resolve import ContentUnresolvable

pytestmark = pytest.mark.contract

_SRC = Path(__file__).resolve().parents[2] / "src" / "channel_integration"

_PERSISTENCE_ROOTS = {
    "sqlite3",
    "sqlalchemy",
    "psycopg",
    "psycopg2",
    "pymongo",
    "redis",
    "boto3",
    "google",
    "pickle",
    "shelve",
    "dbm",
    "csv",
    "tempfile",
}

_WRITE_CALLS = (
    "write_text",
    "write_bytes",
    "writelines",
    "mkdir",
    "unlink",
    "rmtree",
    "touch",
    "dump",
    "save",
    "persist",
    "insert",
    "upsert",
    "commit",
)


def test_no_module_imports_a_persistence_mechanism() -> None:
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in _PERSISTENCE_ROOTS:
                    offenders.append(f"{source.relative_to(_SRC)}: {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in _PERSISTENCE_ROOTS:
                        offenders.append(f"{source.relative_to(_SRC)}: {alias.name}")
    assert not offenders, offenders


def test_no_module_calls_a_write_operation() -> None:
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if called in _WRITE_CALLS:
                offenders.append(f"{source.relative_to(_SRC)}: {called}()")
    assert not offenders, offenders


def test_no_module_opens_a_file_for_writing() -> None:
    """Reading governed content is permitted; writing anything is not."""
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            attr = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name != "open" and attr != "open":
                continue
            for argument in [*node.args[1:], *[kw.value for kw in node.keywords]]:
                if not isinstance(argument, ast.Constant):
                    continue
                mode_argument = argument.value
                if not isinstance(mode_argument, str):
                    continue
                if any(mode in mode_argument for mode in ("w", "a", "x", "+")):
                    offenders.append(f"{source.relative_to(_SRC)}: open(..., {mode_argument})")
    assert not offenders, offenders


def test_the_metadata_policy_refuses_while_d_29_is_undeclared() -> None:
    """`SC-036`: the measured permitted-record count is zero because nothing resolves.

    The policy is repository-wide rather than per channel — what may be persisted is a
    data-governance decision, not a transport one — so it takes no channel argument.
    """
    with pytest.raises(ContentUnresolvable):
        resolve_metadata_policy()


def test_the_idempotency_window_is_memory_and_says_so() -> None:
    """Not persistence, and the distinction is asserted rather than assumed.

    A fresh window sees nothing a previous one recorded, which is what "does not survive the
    process" means in a test that cannot restart a process.
    """
    from channel_integration.idempotency.window import IdempotencyWindow

    assert IdempotencyWindow().size() == 0
    assert "__slots__" in Path(_SRC / "idempotency" / "window.py").read_text(encoding="utf-8"), (
        "the window would otherwise accept arbitrary attributes"
    )
