"""Which KPIs the report must carry, and whether the day is there to report — `OD-54`, `T837`.

## Why this module exists, and it is a correction of where the last one landed

The report's description used to say *"Os vinte indicadores"*, and that sentence was doing a
count nobody had asked it to do: on 2026-08-31 it said twenty while the report carried
**seventeen**. Two KPIs lag — `Chargeback (qty)` by two days, `Not renewed (qty)` by one — so
neither had a row on the closed day, and the sections were built **from that day's rows**.
Both vanished without a trace.

`OD-54` took the number out of the sentence, and the node that replaced it **landed one layer
away from the defect**: it handed a list of KPIs to the renderer and asserted the renderer
gave those KPIs back. Measured by the reviewer, driving the mutation: reintroducing the
original defect — deriving the active set from the closed day's rows — left every suite
**green**. The mutation was comparing a list with itself.

**The defect was never in the rendering. It was in who CHOOSES the lines**, and that choice
lived in a script no test imports. So it lives here, where a node can drive it.

## What is deliberately NOT here

The bold mark and the `parse_mode` stay in the thing that carries the message. **Markup is
transport; which KPI appears is the shape of the report**, and the two are different questions
that were briefly confused because both looked like presentation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ..view.shape import EVENT_DATE_COLUMN, KPI_NAME_COLUMN, SECTION_NAME_COLUMN

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable, Mapping, Sequence
    from datetime import date

    from ..view.shape import ViewRow

__all__ = [
    "active_kpis",
    "day_is_loaded",
    "declares_inactive",
    "scoped_kpis",
    "shape_rows",
]


def declares_inactive(contract: Mapping[str, object]) -> bool:
    """Does the catalog declare this metric's source unavailable? — `OD-40`.

    The model refuses an `unavailable` entry with no `reason_code`, so a KPI can only leave
    the report **with a written reason and a date**. That is the difference between a decision
    and somebody quietly dropping a line.
    """
    entries = contract.get("source_availability") or ()
    if not isinstance(entries, list | tuple):
        return False
    return any(
        isinstance(entry, dict) and cast("dict[str, Any]", entry).get("status") == "unavailable"
        for entry in cast("tuple[object, ...] | list[object]", entries)
    )


def active_kpis(contracts: Iterable[Mapping[str, object]], *, view: str) -> dict[str, str]:
    """The KPIs the report must carry, as ``{kpi_name: metric name}``.

    **Read from the CONTRACTS and from nothing else.** Deriving this from rows is the defect
    that made twenty read as seventeen: a KPI whose source lags has no row for the closed day
    and would disappear, while the catalog still governs it and the reader still needs to see
    that it is missing.
    """
    found: dict[str, str] = {}
    for contract in contracts:
        if declares_inactive(contract):
            continue
        name = contract.get("name")
        versions = contract.get("versions")
        if not isinstance(versions, list | tuple):
            continue
        for raw in cast("tuple[object, ...] | list[object]", versions):
            if not isinstance(raw, dict):
                continue
            version = cast("dict[str, Any]", raw)
            if version.get("source_view") != view:
                continue
            kpi = version.get("kpi_name")
            if isinstance(kpi, str) and kpi and isinstance(name, str):
                found[kpi] = name
    return found


def scoped_kpis(wanted: Mapping[str, str], indicators: Sequence[str]) -> dict[str, str]:
    """The DAILY's KPIs: the active set restricted to the indicators his file names — `T1329`.

    `OD-107` split the report in two: the 08:00 daily carries the indicators, the weekly carries
    the rest (`FR-1319`). ``indicators`` is governed data (`report_governance/daily_scope.yaml`),
    read by the caller and applied here, where a node can drive it.

    **Fail-closed in both directions.** An indicator the file names that no active contract
    carries is refused, not skipped: a misspelt name would otherwise drop a line in silence,
    which is the `OD-54` defect again. An empty list is refused too — a daily that says nothing
    is not the product. The order of the result is the FILE's order.
    """
    if not indicators:
        raise ValueError("daily_scope names no indicator; the daily would say nothing")
    unknown = [name for name in indicators if name not in wanted]
    if unknown:
        raise ValueError(f"daily_scope names indicators no active contract carries: {unknown}")
    return {name: wanted[name] for name in indicators}


def shape_rows(
    contracts: Iterable[Mapping[str, object]],
    rows: Sequence[ViewRow],
    *,
    view: str,
) -> list[ViewRow]:
    """One row per ACTIVE KPI, carrying the section the view gives it.

    ``rows`` supplies only the SECTION each KPI belongs to; **which KPIs there are comes from
    the contracts**. A KPI the rows never mention cannot be placed — the view is the only
    thing that says which section it is in — and it is reported as missing rather than
    silently dropped, by coming back with no section.
    """
    wanted = active_kpis(contracts, view=view)
    sections: dict[str, str] = {}
    for row in rows:
        kpi = row.get(KPI_NAME_COLUMN)
        section = row.get(SECTION_NAME_COLUMN)
        if isinstance(kpi, str) and kpi in wanted and isinstance(section, str) and section:
            sections.setdefault(kpi, section)
    return [
        {KPI_NAME_COLUMN: kpi, SECTION_NAME_COLUMN: sections.get(kpi, "")} for kpi in sorted(wanted)
    ]


def day_is_loaded(rows: Sequence[ViewRow], day: date) -> bool:
    """Does the source hold **any** row for the closed day?

    ## The refusal this answers, and why it is not silence

    The source rebuilds at 06:00 UTC and a run can fall before it — measured 2026-08-31 at
    05:00 UTC, where **every one of the nineteen lines carried a dash**. Sending that is not
    honesty about an absence: it is nineteen absences dressed as a daily report, and the only
    thing the reader learns is that something is broken.

    A caller scheduled after the rebuild never sees this answer, **which is why the trigger of
    `T837` has an hour and not merely an existence.**
    """
    return any(str(row.get(EVENT_DATE_COLUMN)) == str(day) for row in rows)
