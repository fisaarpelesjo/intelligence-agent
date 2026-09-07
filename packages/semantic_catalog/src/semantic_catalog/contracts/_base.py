"""Shared base types for every authored catalog contract.

Three properties are enforced here rather than repeated per model:

* **fail-closed** — ``extra="forbid"`` rejects any field the contract does not
  declare, so a typo or an unknown key is an error rather than silent data loss;
* **immutable** — ``frozen=True``; a loaded contract is a value, not a mutable
  record;
* **no silent numeric or boolean coercion** — every integer and boolean field is
  declared ``StrictInt`` / ``StrictBool``, so authored YAML saying ``version: "2"``
  fails instead of quietly becoming ``2``. Enums and dates are parsed from their
  string form, because that is the only form YAML can express.

Identifiers are English (FR-053); human-facing content is pt-BR (FR-054) and
carries an explicit ``lang`` marker so its language is declared, not inferred.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

__all__ = [
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "CatalogModel",
    "Identifier",
    "IsoDuration",
    "PtBrContent",
    "PtBrText",
]

#: Current authored-file schema version. The loader (T023) accepts every version in
#: `SUPPORTED_SCHEMA_VERSIONS`, which is THREE wide today and was two until `D-1303`.
#: The count is stated by that tuple and not repeated here in words.
#:
#: **Moved to 2 on 2026-08-30, and `FR-808` is why it had to move.** A metric may now
#: declare which column carries its number (`value_column`) and which KPI of the view it
#: is (`kpi_name`). Adding a field a validator does not know about would be a declaration
#: nobody checks, so the version moves with the field rather than after it.
SCHEMA_VERSION = 3

#: Accepted window, newest first. Widening it is a deliberate migration (R-12).
#:
#: Version 1 stays accepted because the twelve contracts that predate the field are still
#: correct at their own version — they point at views the warehouse does not hold, and a
#: metric with no observable column cannot honestly declare one.
#:
#: Version 2 stays accepted for the same shape of reason after `D-1303` added
#: ``lower_is_better`` in version 3: a contract that does not declare a direction is not
#: wrong, it is undeclared — and the report already prints no colour for that case. Widening
#: this window is what lets the twenty contracts bound to the view move one at a time instead
#: of in a single edit nobody can review.
SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (3, 2, 1)

_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]*$"

#: English canonical identifier: metric names, dimension names, enum values,
#: contract field names and source-view references (FR-053).
Identifier = Annotated[str, StringConstraints(pattern=_IDENTIFIER_PATTERN, min_length=1)]

#: Non-empty human-facing text. Always pt-BR in practice; the language marker
#: lives on the enclosing :class:`PtBrContent` block.
PtBrText = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

_ISO_DURATION = re.compile(
    r"^P(?!$)(?:(\d+)D)?(?:T(?!$)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$",
)


def _parse_iso_duration(value: object) -> object:
    """Accept an ISO-8601 duration string from authored YAML.

    Strict mode would otherwise demand a real ``timedelta``, which YAML cannot
    express. Only day-and-below components are permitted: months and years are
    not fixed-length, so a tolerance expressed in them would be ambiguous.
    """
    if not isinstance(value, str):
        return value
    match = _ISO_DURATION.match(value)
    if match is None:
        raise ValueError(
            "expected an ISO-8601 duration of days or smaller "
            f"(for example 'P2D', 'PT6H'), got {value!r}"
        )
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


#: ISO-8601 duration limited to days and below, authored as a string.
IsoDuration = Annotated[timedelta, BeforeValidator(_parse_iso_duration)]


class CatalogModel(BaseModel):
    """Base for every authored contract: frozen and closed to extras.

    Strictness is applied per field rather than globally: ``strict=True`` on the
    model would reject the string form of every enum and date, which is the only
    form authored YAML can express. Numeric and boolean fields use
    ``StrictInt`` / ``StrictBool``, which is where silent coercion actually
    causes harm.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
    )


class PtBrContent(CatalogModel):
    """A human-facing content block, declared pt-BR (FR-054, FR-056).

    The marker is required and fixed. Automated validation checks presence and
    the declaration; whether the Portuguese is *correct* is a reviewer duty
    (D-10) and is deliberately not claimed here.
    """

    lang: Literal["pt-BR"] = Field(
        description="Explicit language declaration; never inferred.",
    )
