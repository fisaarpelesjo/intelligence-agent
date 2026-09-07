"""Guard 2 — emitted text — T054 (FR-026, FR-027, FR-028; SC-002).

The second of three independent guards. Guard 1 is the type system (``render``
accepts only a ``QueryStructure``); Guard 3 is the IAM grant, which holds even if
this code is wrong. This one inspects the text that is about to be submitted.

**A guard failure raises.** It is a defect, never a warning and never a refusal
surfaced to a caller. Reaching a guard means the compiler produced something it
should not have been able to produce, and the honest response to "my own output
is not what I believe it to be" is to stop, not to explain (execution-contract
§2).

The last assertion is the interesting one: the text may not contain any bound
parameter's value. That catches a future refactor which reintroduces
interpolation, even when guards 1 and 3 still pass — the failure mode where the
type system is satisfied because someone formatted the value into ``text``
themselves.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..execution.adapter import RenderedQuery

__all__ = ["GuardViolation", "assert_emitted_text_is_safe"]


class GuardViolation(RuntimeError):  # noqa: N818 - a defect, never a governed refusal
    """The emitted text is not what the compiler is supposed to be able to emit."""


#: A governed table reference. Anchored, and the dataset is fixed.
_SEMANTIC_TABLE = re.compile(r"^semantic\.[a-z_][a-z0-9_]*$")

#: Backtick-quoted references in the text, which is how `render` emits tables.
_QUOTED_REFERENCE = re.compile(r"`([^`]*)`")

_FORBIDDEN_DATASETS = ("raw.", "staging.", "core.")

_DDL_DML = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "TRUNCATE",
    "DROP",
    "CREATE",
    "ALTER",
    "GRANT",
    "REVOKE",
    "REPLACE",
    "CALL",
    "EXPORT",
    "LOAD",
)

_COMMENT_SEQUENCES = ("--", "/*", "*/", "#")


def assert_emitted_text_is_safe(query: RenderedQuery) -> None:
    """Assert every emitted-text property, or raise.

    Ordered cheapest-first only incidentally; every assertion runs against the
    same text and any one of them failing is equally fatal.
    """
    text = query.text
    stripped = text.strip()

    # One statement. A `;` followed by anything non-blank is a second statement.
    body, _, tail = stripped.partition(";")
    if tail.strip():
        raise GuardViolation("emitted text contains more than one statement")
    if not body.strip():
        raise GuardViolation("emitted text is empty")

    # No comment sequences: the classic channel for smuggling past a naive parser.
    for sequence in _COMMENT_SEQUENCES:
        if sequence in text:
            raise GuardViolation(f"emitted text contains a comment sequence: {sequence!r}")

    # Every table reference is a governed `semantic.` view.
    references = _QUOTED_REFERENCE.findall(text)
    if not references:
        raise GuardViolation("emitted text references no table")
    for reference in references:
        if not _SEMANTIC_TABLE.match(reference):
            raise GuardViolation(f"emitted text references a non-governed table: {reference!r}")

    # Belt and braces against the forbidden datasets, even unquoted.
    lowered = text.lower()
    for dataset in _FORBIDDEN_DATASETS:
        if dataset in lowered:
            raise GuardViolation(f"emitted text references the {dataset[:-1]} dataset")

    # Read-only: the statement opens with SELECT or WITH, and no DDL/DML verb
    # appears anywhere as a whole word.
    first = body.strip().split(None, 1)[0].upper()
    if first not in {"SELECT", "WITH"}:
        raise GuardViolation(f"emitted text does not begin with SELECT or WITH: {first!r}")
    for verb in _DDL_DML:
        if re.search(rf"\b{verb}\b", text, re.IGNORECASE):
            raise GuardViolation(f"emitted text contains the {verb} verb")

    # No bound value appears in the text. This is what catches reintroduced
    # interpolation that every other assertion would let through.
    for name, value in query.parameters.items():
        rendered = str(value)
        if rendered and rendered in text:
            raise GuardViolation(
                f"the value bound to {name!r} appears in the emitted text; "
                "values are parameters, never syntax"
            )
