"""Which column carries a KPI's number — `T811`, `T812`, `T813`.

## The error this module exists because of, and it was published

MRR and Revenue were reported as having **no value**, from reading only the `value`
column. They do have values — MRR reaches `16.000,69` USD, Revenue `1.073,60` — and
they live in `value_usd`. The reading was wrong, not the data.

**So the column is declared, per metric, in that metric's catalog contract**, and this
module reads the declaration. It does not infer, and above all it does not *default to
`value`* — the default is precisely the shape that produced the published error, and a
default would have made the same mistake silently the next time.

The rule an author follows when filling that declaration is `usd_*` → `value_usd`,
`brl` → `value_brl`, everything else → `value`. **That rule governs the author, not
this code**: written here it would be a second copy of a fact that already lives in the
contracts, and two copies of one fact disagree the day one of them moves.

## Why the schema version is load-bearing

A contract at the old version **cannot** carry the new field — `FR-808`. Otherwise a
metric could be read as declaring a column while every validator in the repository
still believes the old shape, which is a declaration nobody checked.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from ..contracts import ReportReasonCode, ReportRefusal

__all__ = [
    "SCHEMA_VERSION_DECLARING_THE_COLUMN",
    "VALUE_COLUMN_FIELD",
    "value_column_for",
]

#: The field a metric contract declares its value column in.
VALUE_COLUMN_FIELD: Final = "value_column"

#: The first catalog schema version in which the field above may appear. A contract
#: below it that carries the field is **refused**, not read leniently.
SCHEMA_VERSION_DECLARING_THE_COLUMN: Final = 2


def _refuse(metric: str, detail: str) -> ReportRefusal:
    return ReportRefusal(
        ReportReasonCode.REPORT_VALUE_COLUMN_NOT_DECLARED,
        f"{metric}: {detail}",
    )


def value_column_for(contract: Mapping[str, object], *, version: Mapping[str, object]) -> str:
    """The column this metric's number lives in, read from its own contract.

    ``contract`` is the metric document; ``version`` is the effective version block
    inside it. **Both are parameters**, which is what makes this readable against a
    different contract and therefore drivable: handed another metric's document it
    answers another column, and a literal answers the same to both.
    """
    name = contract.get("name")
    metric = name if isinstance(name, str) and name else "<unnamed metric>"

    schema = contract.get("catalog_schema_version")
    if not isinstance(schema, int):
        raise _refuse(metric, "the contract declares no integer catalog_schema_version")

    declared = version.get(VALUE_COLUMN_FIELD)
    if schema < SCHEMA_VERSION_DECLARING_THE_COLUMN:
        if declared is not None:
            raise _refuse(
                metric,
                f"declares {VALUE_COLUMN_FIELD!r} at catalog_schema_version {schema}, which "
                f"predates it; the field is readable from "
                f"{SCHEMA_VERSION_DECLARING_THE_COLUMN} onwards and a declaration nobody "
                f"validates is not a declaration",
            )
        raise _refuse(
            metric,
            f"catalog_schema_version {schema} predates {VALUE_COLUMN_FIELD!r}, so this metric "
            f"cannot say where its number lives",
        )

    if not isinstance(declared, str) or not declared.strip():
        raise _refuse(
            metric,
            f"declares no {VALUE_COLUMN_FIELD!r}; it is NOT defaulted to 'value', because that "
            f"default is what published MRR and Revenue as valueless",
        )
    return declared.strip()
