"""The report's labels and grouping, **derived from the view** — `T805`, `T806`, `T807`.

## Why this module takes the rows as a parameter

**A derivation is held only when a CORRECT literal copy of it fails NOW**, and a
function that reaches out for its own data cannot be handed a different document, so
nothing can tell a reading from a copy. This repository has paid for that three times
in one week: `007`'s recipient, `006`'s method reader, and `006`'s method *binding* one
cycle later, where the reader had been made drivable and the constant production
actually reads had not.

**The rows are the parameter.** Handed a different view, this answers differently; a
literal answers the same to both, and
``tests/contract/test_the_shape_is_read_from_the_view.py`` drives exactly that.

## And there is no list of twenty anywhere

Not in source, not in a fixture, not in a test — `FR-803`. The KPI set, its labels and
its grouping are the view's, and this feature's job is to carry them, not to know them.
A fixture holding twenty correct strings is the same defect in the one place people
forgive.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from ..contracts import ReportReasonCode, ReportRefusal

__all__ = [
    "EVENT_DATE_COLUMN",
    "KPI_NAME_COLUMN",
    "SECTION_NAME_COLUMN",
    "Section",
    "ViewRow",
    "every_kpi_in",
    "kpi_label_of",
    "sections_from",
]

#: One row as the view answers it. Untyped values: the client ships no type
#: information, and inventing one here would be this module asserting a schema it
#: does not own.
ViewRow = Mapping[str, object]

#: The view's own column names. **These are the two columns, not the twenty labels** —
#: the distinction `FR-803` turns on. A column name is the shape of the source; a KPI
#: name is content, and content written here would be content this repository authored.
KPI_NAME_COLUMN: Final = "kpi_name"
SECTION_NAME_COLUMN: Final = "section_name"

#: The day a row belongs to — declared here for the same reason as the two above, and
#: because `T1330` gave it a second reader. It was a bare literal in two places until
#: 2026-09-05: `scope.py`'s `day_is_loaded` and, from now on, the snapshot branch of
#: `reading.aggregate`, which needs to know which day is LAST.
EVENT_DATE_COLUMN: Final = "event_date"


@dataclass(frozen=True, slots=True)
class Section:
    """One section header and the KPIs under it, **in the order the view gave them**.

    Not sorted. Sorting would impose an order this feature chose over the one the
    source declares, and `FR-805` forbids reordering a KPI out of its declared place.
    """

    name: str
    kpis: tuple[str, ...]


def _text_at(row: ViewRow, column: str) -> str:
    """The column's value as text, or a refusal naming the column that was missing."""
    value = row.get(column)
    if not isinstance(value, str) or not value.strip():
        raise ReportRefusal(
            ReportReasonCode.REPORT_KPI_NOT_DERIVABLE,
            f"a row carries no usable {column!r}, so a label cannot be derived from it",
        )
    return value.strip()


def kpi_label_of(row: ViewRow) -> str:
    """This KPI's label, **read from the row**.

    It is the view's `kpi_name` and nothing else. There is no translation table, no
    prettifier and no fallback: a row that cannot answer refuses, because a borrowed
    label is a label this repository wrote.
    """
    return _text_at(row, KPI_NAME_COLUMN)


def sections_from(
    rows: Iterable[ViewRow], *, declared_order: Sequence[str] = ()
) -> tuple[Section, ...]:
    """The sections and their KPIs — in the owner's declared order when one is handed in.

    ``declared_order`` is DATA, never names written here: `OD-70` (2026-08-31) fixed the order and
    it lives in `report_governance/section_order.yaml`, governed content in the report's own tree,
    because this package's whole claim is that it derives the view's names rather than writing
    them. The caller reads the file; this function applies it.

    KPIs keep first-seen order within their section. **A section absent from the declared list is
    NOT dropped** — it appears after the declared ones, in first-seen order. The 20→17 lesson:
    what is not on the map must not vanish in silence. And with no order handed in, first-seen
    order stands, which is what every caller got before `OD-70`.
    """
    grouped: dict[str, list[str]] = {}
    for row in rows:
        section = _text_at(row, SECTION_NAME_COLUMN)
        kpi = kpi_label_of(row)
        under = grouped.setdefault(section, [])
        if kpi not in under:
            under.append(kpi)
    declared = [name for name in declared_order if name in grouped]
    unlisted = [name for name in grouped if name not in declared_order]
    return tuple(Section(name=name, kpis=tuple(grouped[name])) for name in (*declared, *unlisted))


def every_kpi_in(sections: Sequence[Section]) -> tuple[str, ...]:
    """Every KPI across every section, still in the view's order.

    **Counted from the sections, never against a written number** — `SC-801`. A node
    asserting *twenty* would be a node that goes red the day the business gains a KPI,
    which is the opposite of what it is for.
    """
    return tuple(kpi for section in sections for kpi in section.kpis)
