"""An axis that applies to NO governed source is permitted by NO metric — T1323 (F5), T1325 (F6).

## Why a node here, when the catalogue already has an L3

`semantic/dimensions/plan.yaml` declares the axis `plan` with an EMPTY `source_applicability`,
because that is the measured truth (`T1322`, remeasured 2026-09-05): the view the daily report
reads carries no plan column, nor does the table behind it, and the table that does carry one
is not a governed source. By `FR-010`, absence from `source_applicability` means NOT APPLICABLE,
and Gate 4 (`validation/gates/combination.py`) denies the combination by name.

**The L3 does not stand guard here.** `validation/l3_reconciliation.py:_dimension_applicability`
reads an empty applicability as *"unrestricted applies everywhere"* and `continue`s — so a metric
that listed `plan` in its `allowed_dimensions` would pass L3 and be refused only at request time,
which is exactly the *advertised-and-always-refused* combination the L3 exists to catch. That is
a contradiction between L3 and Gate 4 recorded in the cycle 552 handoff; it is not repaired here,
because the catalogue package is upstream and this slice is not authorised to touch it.

So this node stands where the report is composed: **no metric contract permits an axis that no
source carries.** The dimensions with empty applicability are DERIVED from the catalogue files,
never listed here, and the node asserts `plan` and `gateway` are among them so that it is known
to bite. `gateway` joined on 2026-09-05 (`T1325`, `F6`, `FR-1316`) by the same measurement: the
view carries no gateway column and the join view of `FR-1315` does not exist yet.

## The first run of this file passed with the mutation planted, and that is recorded

The reader keyed documents on ``id``. A dimension carries ``id``; a metric carries ``name``. So
zero metrics were read, the offender set was empty by construction, and `plan` planted in
`sales_qty` went unnoticed — the `S-48` shape. The reader now keys on the file stem, which both
kinds share, and `test_every_governed_file_was_read` measures the count against the text.

**Mutation** (`tasks.md`, `T1323`): `plan` added to `sales_qty.yaml`'s `allowed_dimensions` →
`test_no_metric_permits_an_axis_that_no_source_carries` fails naming the metric and the axis.
**Mutation** (`T1325`): `gateway` added to `trial_conversion_rate.yaml`'s `allowed_dimensions` →
the same node fails naming that metric and `gateway` (`1 failed, 5 passed`, measured 2026-09-05).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
DIMENSIONS = REPO / "semantic" / "dimensions"
METRICS = REPO / "semantic" / "metrics"


def _documents(folder: Path, kind: str) -> dict[str, dict[str, Any]]:
    """Every governed file of ``kind`` under ``folder``, keyed by the file's stem."""
    if not folder.is_dir():  # pragma: no cover - a checkout without the catalogue
        pytest.skip(f"{folder} is not in this checkout; nothing was measured")
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.yaml")):
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            document = cast("dict[str, Any]", loaded)
            if document.get("kind") == kind:
                found[path.stem] = document
    return found


def _files_of_kind(folder: Path, kind: str) -> int:
    """How many files under ``folder`` state ``kind`` — read as text, apart from the parser."""
    marker = f"\nkind: {kind}\n"
    return sum(1 for path in folder.glob("*.yaml") if marker in path.read_text(encoding="utf-8"))


def _axes_no_source_carries() -> set[str]:
    """Dimension ids whose ``source_applicability`` is empty — derived, not written."""
    return {
        str(document.get("id", stem))
        for stem, document in _documents(DIMENSIONS, "dimension").items()
        if not document.get("source_applicability")
    }


def _permitted_by_metric() -> dict[str, set[str]]:
    """Every axis each metric permits, across all its versions."""
    permitted: dict[str, set[str]] = {}
    for stem, document in _documents(METRICS, "metric").items():
        axes: set[str] = set()
        versions: object = document.get("versions") or []
        if isinstance(versions, list):
            for entry in cast("list[object]", versions):
                if isinstance(entry, dict):
                    declared: object = cast("dict[str, Any]", entry).get("allowed_dimensions") or []
                    if isinstance(declared, list):
                        axes.update(str(name) for name in cast("list[object]", declared))
        permitted[stem] = axes
    return permitted


@pytest.mark.parametrize(("folder", "kind"), [(DIMENSIONS, "dimension"), (METRICS, "metric")])
def test_every_governed_file_was_read(folder: Path, kind: str) -> None:
    """The reader sees every file the text says is of ``kind`` — and at least one (`S-48`)."""
    read = _documents(folder, kind)
    assert read, f"no {kind} read under {folder}"
    assert len(read) == _files_of_kind(folder, kind), sorted(read)


def test_plan_is_declared_and_applies_to_no_source() -> None:
    """The measured state of `T1322`, held as a node: the axis exists and no source carries it."""
    dimensions = _documents(DIMENSIONS, "dimension")
    assert "plan" in dimensions, sorted(dimensions)
    assert not dimensions["plan"].get("source_applicability"), (
        "plan gained a source; if a governed view now carries it, F5 leaves the refusal behind "
        "and this node is re-derived with the measurement beside it"
    )


def test_gateway_is_declared_and_applies_to_no_source() -> None:
    """The measured state of `T1325` (remeasured 2026-09-05 13:02 -03), held as a node."""
    dimensions = _documents(DIMENSIONS, "dimension")
    assert "gateway" in dimensions, sorted(dimensions)
    assert not dimensions["gateway"].get("source_applicability"), (
        "gateway gained a source; if the join view of FR-1315 now exists, F6 leaves the refusal "
        "behind (T1327) and this node is re-derived with the measurement beside it"
    )


def test_the_derived_set_is_not_empty_so_the_guard_below_bites() -> None:
    """A guard over an empty set proves nothing (`S-48`). `plan` and `gateway` make it non-empty."""
    assert {"plan", "gateway"} <= _axes_no_source_carries()


def test_no_metric_permits_an_axis_that_no_source_carries() -> None:
    """Deny-by-default in the direction the L3 does not check — see the module docstring."""
    orphan_axes = _axes_no_source_carries()
    offenders = {
        metric: sorted(axes & orphan_axes)
        for metric, axes in _permitted_by_metric().items()
        if axes & orphan_axes
    }
    assert not offenders, (
        f"these metrics permit an axis no governed source carries, which would be advertised "
        f"and always refused: {offenders}"
    )
