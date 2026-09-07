"""Multi-process deployment guard — T083 (FR-036; SC-012).

`InMemoryExecutionLedger` is atomic within one process. Two processes each see
an empty ledger and both execute, so `FR-036` — two concurrent requests sharing
one execution key resolve to a single execution of record — is simply false
across processes.

**This is a readiness condition, not a runtime fallback.** A multi-process
deployment without the shared atomic ledger (`D-17`) is a forbidden
configuration, and the guard refuses to start. It does **not** silently downgrade
to per-process single-flight, because a downgrade satisfies `FR-036` in every
test that runs in one process and violates it in production — which is the worst
combination available, since nothing fails until real money is being double-spent.

The guard reads the governed readiness record. `D-17` is undeclared today, so
any multi-process configuration refuses; declaring it is an evidence decision
that belongs to a steward, not a flag someone can set here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..compliance.readiness import ReadinessRecord, load_record, readiness_root

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

__all__ = [
    "SHARED_LEDGER_CAPABILITY",
    "ForbiddenDeployment",
    "assert_deployment_is_permitted",
    "shared_ledger_is_available",
]

#: The capability whose evidence a multi-process deployment requires (`D-17`).
SHARED_LEDGER_CAPABILITY = "d_17"


class ForbiddenDeployment(RuntimeError):  # noqa: N818 - a configuration refusal, not a runtime error
    """The deployment is not a permitted configuration.

    Raised at start-up rather than on a request. A process that would violate
    single-flight must not begin serving and then discover it, because by then
    the duplicate execution has already been billed.
    """


#: The 002-owned readiness record. Named rather than globbed: `001` keeps its
#: own record in the same directory under a different schema, and this feature
#: must not read it, parse it or overload it.
READINESS_FILE = "analytics-query-external-readiness.yaml"


def _records() -> Iterable[ReadinessRecord]:
    """The 002 readiness record, or nothing.

    A missing file yields no records, and `aggregate` reads that as *nothing is
    ready* — so the guard fails closed on an absent record rather than treating
    absence as permission.
    """
    path = readiness_root() / READINESS_FILE
    return [load_record(path)] if path.is_file() else []


def shared_ledger_is_available(records: Iterable[ReadinessRecord] | None = None) -> bool:
    """Whether `D-17` is declared **and** evidenced across every readiness record.

    Conjunctive, and a missing record reads *not available* rather than *no
    constraint* — so adding a record can only ever narrow what is permitted.
    """
    from ..compliance.readiness import aggregate

    return SHARED_LEDGER_CAPABILITY in aggregate(records if records is not None else _records())


def assert_deployment_is_permitted(
    *, process_count: int, records: Iterable[ReadinessRecord] | None = None
) -> None:
    """Refuse a multi-process deployment without a shared atomic ledger.

    ``records`` is injectable for tests. It is not a runtime switch: nothing on
    the request path supplies it, and no flag or environment setting reaches it —
    the fixture-containment scan asserts as much.
    """
    if process_count < 1:
        raise ForbiddenDeployment("a deployment must run at least one process")
    if process_count == 1:
        return
    if shared_ledger_is_available(records):
        return
    raise ForbiddenDeployment(
        f"a {process_count}-process deployment requires a shared atomic execution ledger; "
        "its external evidence is undeclared, and per-process single-flight is not a "
        "permitted downgrade"
    )


def readiness_path() -> Path:  # pragma: no cover - convenience for stewards
    """Where the guard reads its evidence from."""
    return readiness_root()
