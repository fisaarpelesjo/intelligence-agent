"""No clock on the request path — T054 (`R-5`; FR-105, FR-106).

Every instant this feature uses arrives as a parameter. Nothing reads the wall clock.

Three reasons the rule is absolute rather than a preference:

* a replay window evaluated against ``now()`` is untestable at its own boundary — the exact
  second the decision flips is the second the test cannot pin;
* two processes reading their own clocks disagree, so an idempotency window and a replay window
  become per-host policies;
* a refusal that depends on when it was evaluated is not reproducible, and `FR-105` requires the
  same input to yield the same answer for a listener, a simulator, a test and the CLI.

Asserted **structurally**, over the whole of `src`: a clock read is decidable by reading the
source, so it is checked by reading the source rather than by hoping a test happens to catch one.

The one permitted mention is a **type annotation**: ``datetime`` as a parameter type is the
mechanism that makes the instant injectable, so importing the class is required. Reading it —
``datetime.now``, ``datetime.utcnow``, ``date.today``, ``time.time`` — is what is forbidden.

``at.timestamp()`` on an **injected** instant is likewise permitted and deliberately not listed:
converting a value someone handed you is not obtaining one. The forbidden set is the set of calls
that *produce* the current instant, which is the thing that makes an outcome depend on when it ran.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_SRC = Path(__file__).resolve().parents[2] / "src" / "channel_integration"

#: Every way the current instant can be obtained in the standard library, plus the monotonic
#: clocks — a monotonic read is still a read, and would make a duration decision unreproducible.
_CLOCK_READS = (
    "datetime.now(",
    "datetime.utcnow(",
    ".now(",
    ".utcnow(",
    "date.today(",
    ".today(",
    "time.time(",
    "time.monotonic(",
    "time.perf_counter(",
    "time.process_time(",
    "time.time_ns(",
    "getdate(",
    "gmtime(",
    "localtime(",
)

#: Modules whose whole purpose is the current instant. Importing one on the request path is a
#: clock read waiting to happen, even if the read is not written yet.
_CLOCK_IMPORTS = re.compile(r"^\s*(?:from|import)\s+(?:time|calendar|sched)\b")


def _sources() -> list[Path]:
    return sorted(_SRC.rglob("*.py"))


def test_src_is_not_empty() -> None:
    """Without this, a scan over zero files would pass every assertion below."""
    sources = _sources()
    assert len(sources) >= 20, f"only {len(sources)} modules were scanned"


def test_no_module_reads_the_current_instant() -> None:
    """`R-5`, over every module: the instant is a parameter, never a read."""
    offenders: list[str] = []
    for source in _sources():
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            if '"""' in code or code.strip().startswith("*"):
                continue
            for token in _CLOCK_READS:
                if token in code:
                    offenders.append(f"{source.relative_to(_SRC)}:{number}: {token}")
    assert not offenders, offenders


def test_no_module_imports_a_clock_module() -> None:
    offenders: list[str] = []
    for source in _sources():
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if _CLOCK_IMPORTS.match(line):
                offenders.append(f"{source.relative_to(_SRC)}:{number}: {line.strip()}")
    assert not offenders, offenders


def test_the_datetime_import_is_type_only_where_it_appears() -> None:
    """`datetime` may be imported, because an injected instant needs a type. Nothing more.

    Stated as an allowance rather than left implicit, so a reader knows the import is deliberate
    and a future `datetime.now()` is not covered by "we already import datetime".
    """
    importers = [
        source
        for source in _sources()
        if re.search(r"^\s*from datetime import", source.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert importers, "no module accepts an injected instant, which would be its own defect"
    for source in importers:
        text = source.read_text(encoding="utf-8")
        assert "now(" not in text and "today(" not in text, (
            f"{source.relative_to(_SRC)} imports datetime and reads it"
        )


def test_the_conversion_signature_still_requires_the_instant() -> None:
    """The positive half. A clock-free module that took no instant would fail closed silently."""
    import inspect

    from channel_integration.inbound.convert import convert
    from channel_integration.inbound.verify import verify_authenticity

    assert "at" in inspect.signature(convert).parameters
    assert "at" in inspect.signature(verify_authenticity).parameters
