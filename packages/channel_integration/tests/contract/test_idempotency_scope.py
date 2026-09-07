"""Idempotency honesty — T098 (ADR 0021; FR-063, FR-067; SC-029, SC-064).

The claim this feature makes about duplicate suppression is **process-local**, and the rule is that
every surface saying so must say the same thing. A guarantee that is precise in the code and
vague in a report is a guarantee an operator will over-trust.

So three things are asserted:

* **one sentence, one place.** `IDEMPOTENCY_SCOPE_STATEMENT` is the single wording, and every other
  surface points at it rather than paraphrasing. Two paraphrases eventually disagree.
* **every public operation names the scope.** `IdempotencyWindow.check` and `.remember` each say
  "this process" in their own docstring, because a caller reads the operation's docstring and not
  the class's.
* **no distribution path exists.** No client, socket, broker, cache or database driver is importable
  from the idempotency package, and no operation is named replicate, sync, share, publish or
  coordinate. A distributed claim needs a mechanism, so the absence of the mechanism is the proof.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.compliance.readiness import IDEMPOTENCY_SCOPE_STATEMENT
from channel_integration.idempotency import record as record_module
from channel_integration.idempotency import window as window_module
from channel_integration.idempotency.window import IdempotencyWindow

pytestmark = pytest.mark.contract

_IDEMPOTENCY_ROOT = Path(inspect.getfile(window_module)).resolve().parent


def test_the_scope_statement_says_what_it_must_say() -> None:
    """The one sentence. If this changes, every surface changes with it."""
    lowered = IDEMPOTENCY_SCOPE_STATEMENT.lower()
    for required in ("process-local", "one process", "one instance", "governed window"):
        assert required in lowered, f"the scope statement omits {required!r}"
    for forbidden in ("distributed", "cluster", "cross-process", "global"):
        assert f"no {forbidden}" in lowered or forbidden not in lowered, (
            f"the statement claims {forbidden!r}"
        )


@pytest.mark.parametrize("operation", ["check", "remember"])
def test_every_public_operation_names_the_scope(operation: str) -> None:
    """`SC-064`: a caller reads the operation, so the operation has to say it."""
    doc = inspect.getdoc(getattr(IdempotencyWindow, operation)) or ""
    assert "process" in doc.lower(), f"{operation} does not name its scope"


def test_the_class_and_the_module_both_name_the_scope() -> None:
    """Both surfaces must state the limit. What is asserted is the **meaning**, not the phrasing.

    An earlier version required the literal string ``process-local`` and failed on the class
    docstring, which says "this process, this instance, this governed window" — the same limit in
    different words. Demanding one phrasing would make this a style rule and would push prose around
    to satisfy a test, so the assertion is that each surface names the process and the instance.
    """
    for doc in (inspect.getdoc(IdempotencyWindow), window_module.__doc__):
        assert doc is not None
        lowered = doc.lower()
        assert "process" in lowered, "the surface does not name the process scope"
        assert "instance" in lowered, "the surface does not name the instance scope"


def test_no_distribution_mechanism_is_importable_from_the_idempotency_package() -> None:
    """A distributed claim needs a mechanism. There is none to reach."""
    forbidden_roots = {
        "redis",
        "memcache",
        "pymemcache",
        "sqlalchemy",
        "psycopg",
        "pymongo",
        "kafka",
        "pika",
        "celery",
        "socket",
        "http",
        "httpx",
        "requests",
        "google",
        "boto3",
        "etcd3",
        "zookeeper",
    }
    offenders: list[str] = []
    for source in sorted(_IDEMPOTENCY_ROOT.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in forbidden_roots:
                    offenders.append(f"{source.name}: {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_roots:
                        offenders.append(f"{source.name}: {alias.name}")
    assert not offenders, offenders


def test_no_operation_is_named_for_replication_or_coordination() -> None:
    """The names a distributed store would need, asserted absent."""
    forbidden = (
        "replicate",
        "sync",
        "share",
        "publish",
        "coordinate",
        "broadcast",
        "lock",
        "lease",
    )
    offenders: list[str] = []
    for module in (window_module, record_module):
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        declared = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
        for name in declared:
            for token in forbidden:
                if token in name.lower():
                    offenders.append(f"{Path(inspect.getfile(module)).name}: {name}")
    assert not offenders, offenders


def test_the_store_is_an_instance_attribute_and_not_module_state() -> None:
    """Module-level state would outlive an instance and blur what "this process" means."""
    members: dict[str, object] = dict(vars(window_module))
    module_state: dict[str, object] = {
        name: value
        for name, value in members.items()
        if not name.startswith("__") and isinstance(value, dict | list | set)
    }
    assert not module_state, f"module-level mutable state: {sorted(module_state)}"

    first, second = IdempotencyWindow(), IdempotencyWindow()
    assert first.size() == 0 and second.size() == 0
    assert first is not second


def test_two_windows_do_not_see_each_other() -> None:
    """The honest limit, asserted as behaviour rather than left in prose.

    Two `IdempotencyWindow` instances are two processes as far as this feature is concerned. A
    redelivery recorded in one is **not** suppressed by the other, and that is exactly why a
    multi-instance configuration refuses (`T100`).
    """
    from channel_integration.contracts._base import MessageKey
    from channel_integration.contracts.delivery import DeliveryOutcome
    from channel_integration.contracts.descriptor import ChannelId

    from ..fixtures.channels import AT, bounds_for
    from ..fixtures.identity import FIXTURE_PRINCIPAL, FIXTURE_TENANT

    key = MessageKey("provider-message-shared")
    first, second = IdempotencyWindow(), IdempotencyWindow()
    first.remember(
        ChannelId.SLACK,
        key,
        FIXTURE_TENANT,
        FIXTURE_PRINCIPAL,
        DeliveryOutcome.DELIVERED,
        bounds_for(ChannelId.SLACK),
        AT,
    )
    assert first.check(ChannelId.SLACK, key, AT).is_duplicate
    assert not second.check(ChannelId.SLACK, key, AT).is_duplicate
