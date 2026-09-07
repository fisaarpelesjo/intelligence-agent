"""``explain-intent`` — T145 (FR-027; SC-002).

**The resolved intent and the request that would be built. No query text, no
execution.**

A steward debugging a question needs to see which governed identifiers it
resolved to, which period, which filters, and what ``AnalyticsQuery`` those would
produce. What they must not be handed is anything runnable.

`002`'s ``explain-plan`` made the same call and for the same reason: printing
runnable query text would recreate exactly the surface `FR-053` removes. A
pasteable statement travels — into a ticket, a chat, a runbook — and the moment
it does, the governed path has an ungoverned sibling that produces the same
number without any of the gates.

So this command prints the **request contract's field values**: governed metric,
dimension and source identifiers, the resolved date range, the pin. Those are
the same identifiers an audit event carries, which is not a coincidence — the
test for "is this safe to print" is the one the audit denylist already answers.

## It executes nothing

No port, no submission, no verdict, no clarification, no model. The command
builds a request and shows it; the next thing that would happen does not happen.
That is the difference between explaining and running, and the reason a steward
can use this against a production deployment without spending anything.

## Input is a governed document, not a question

``explain-intent`` reads a YAML file describing an **already-resolved** intent —
governed identifiers, an explicit period, the declared language and the pinned
versions. It does **not** accept a natural-language question, because
interpreting one requires the `D-19` screening step and the `D-18` period
vocabulary, and neither resolves today. A command that accepted a question would
either refuse always (useless) or bypass the steps (worse).

Anything the file does not declare, or declares wrongly, is an **invocation
error** — never a governed refusal. A malformed input file is the caller's typo,
not a governance decision, and coding it as one would put a defect into a
steward's mental model of what the policy says.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import yaml

from ..contracts._base import ContractViolation, build
from ..contracts.intake import DeclaredLanguage
from ..contracts.intent import ResolvedIntent, ResolvedPeriod
from .main import EXIT_OK, EXIT_VIOLATION, emit

if TYPE_CHECKING:  # pragma: no cover - typing only
    import argparse

    #: ``argparse`` exposes the sub-parser action only under a private name.
    #: Aliased once here so the ``pyright`` suppression sits at the one place
    #: that touches the standard library's private surface, rather than being
    #: repeated at every registration function.
    SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]
    from pathlib import Path

__all__ = ["add_explain_parser", "explain_intent", "load_intent"]

#: Everything the input document may declare. An **allowlist**: an unknown key is
#: an invocation error rather than an ignored one, because a steward who
#: mistyped ``sources`` as ``source`` would otherwise get an explanation of a
#: request they did not describe.
DOCUMENT_KEYS = frozenset(
    {
        "metrics",
        "dimensions",
        "sources",
        "period",
        "reference_date",
        "as_of",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
    }
)


def load_intent(path: Path) -> ResolvedIntent:
    """Read an already-resolved intent from a governed document.

    Every field is required except ``as_of``, which is legitimately absent when
    the caller pinned nothing. Nothing is defaulted — a defaulted
    ``catalog_release`` would explain a request against a release the document
    never named.

    ``reference_date`` and ``as_of`` are read **independently**. Deriving one
    from the other would collapse two identity members into one, and the whole
    point of this command is to show what the identity would be.
    """
    document = _mapping(_load(path), "the document root")
    unknown = sorted(set(document) - DOCUMENT_KEYS)
    if unknown:
        raise ValueError(f"unknown keys: {unknown}")

    period_raw = _mapping(document.get("period"), "period")
    reference_date = _as_date(document.get("reference_date"), "reference_date")
    period = build(
        ResolvedPeriod,
        start=_as_date(period_raw.get("start"), "period.start"),
        end=_as_date(period_raw.get("end"), "period.end"),
        expression=None,
        reference_date=reference_date,
        convention=None,
        resolved_by="explicit_dates",
    )

    return build(
        ResolvedIntent,
        metrics=_as_str_tuple(document.get("metrics"), "metrics"),
        dimensions=_as_str_tuple(document.get("dimensions"), "dimensions"),
        filters=(),
        sources=_as_str_tuple(document.get("sources"), "sources"),
        period=period,
        resolutions=(),
        comparison=None,
        language=DeclaredLanguage.PT_BR,
        reference_date=reference_date,
        as_of=_optional_date(document.get("as_of")),
        catalog_release=_as_str(document.get("catalog_release"), "catalog_release"),
        policy_version=_as_str(document.get("policy_version"), "policy_version"),
        vocabulary_version=_as_str(document.get("vocabulary_version"), "vocabulary_version"),
    )


def _load(path: Path) -> object:
    """Parse the document, converting a parser failure into a governed one.

    ``yaml.YAMLError`` is not a ``ValueError``, so an unparseable document
    escaped ``main``'s handlers and printed a traceback — the one output this CLI
    must never produce, and the one that quotes the offending line of untrusted
    input on its way out. Re-raised as a ``ValueError`` carrying **no** parser
    detail: that the file could not be read is all the caller is told.
    """
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as broken:
        raise ValueError("the document is not well-formed") from broken


def _mapping(value: object, field: str) -> dict[str, object]:
    """A YAML mapping with string keys, or a governed invocation error.

    ``yaml.safe_load`` returns ``Any``, and typing the result ``dict[str, Any]``
    is how an untyped document reaches ``build`` — the loader will happily hand
    back an ``int`` key or a scalar where a mapping was expected.
    """
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    pairs: list[tuple[object, object]] = list(value.items())  # pyright: ignore[reportUnknownArgumentType]
    if not all(isinstance(key, str) for key, _ in pairs):
        raise ValueError(f"{field} must use string keys")
    return {str(key): item for key, item in pairs}


def _as_str_tuple(value: object, field: str) -> tuple[str, ...]:
    """A list of identifiers, never a bare string.

    ``tuple("installs")`` is ``("i", "n", ...)`` — an accepted document silently
    explaining eight metrics that do not exist. A string here is an error, not a
    one-element list, because guessing which was meant is how the explanation
    stops matching the document.
    """
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, list):
        raise ValueError(f"{field} must be a list of identifiers")
    items: list[object] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    if not all(isinstance(item, str) and item for item in items):
        raise ValueError(f"{field} must contain non-empty identifiers")
    return tuple(str(item) for item in items)


def _as_date(value: object, field: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"{field} must be a date")


def _optional_date(value: object) -> date | None:
    return None if value is None else _as_date(value, "as_of")


def _as_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def explain_intent(args: argparse.Namespace) -> int:
    """Print the intent and the request that **would** be built.

    Two blocks, deliberately separate. The intent is what the question resolved
    to; the request is what `002` would receive. Showing them together is how a
    steward sees that ``reference_date`` disclosed on the intent does **not**
    reach the request, and that only ``as_of`` does — which is `FR-097`, visible
    rather than described.

    A ``ContractViolation`` here is a governed outcome: the document described an
    intent the contracts refuse, and exit 1 says so. Everything else — a missing
    file, a bad key, a malformed date — is the caller's invocation error and is
    raised for ``main`` to report as exit 2.
    """
    from ..contracts.request_build import REQUEST_FIELDS

    intent = load_intent(args.document)

    try:
        request_preview = {
            "metrics": list(intent.metrics),
            "dimensions": list(intent.dimensions),
            "sources": list(intent.sources),
            "filters": [],
            "date_range": {
                "start": intent.period.start.isoformat(),
                "end": intent.period.end.isoformat(),
            }
            if intent.period
            else None,
            "as_of": intent.as_of.isoformat() if intent.as_of else None,
        }
    except ContractViolation as refusal:
        emit({"explained": False, "reason_code": refusal.code.value})
        return EXIT_VIOLATION

    emit(
        {
            "explains": "intent_and_request",
            "emits_query_text": False,
            "executes": False,
            "intent": {
                "metrics": list(intent.metrics),
                "dimensions": list(intent.dimensions),
                "sources": list(intent.sources),
                "period": {
                    "start": intent.period.start.isoformat(),
                    "end": intent.period.end.isoformat(),
                    "resolved_by": intent.period.resolved_by,
                }
                if intent.period
                else None,
                "language": intent.language.value,
                "reference_date": intent.reference_date.isoformat(),
                "as_of": intent.as_of.isoformat() if intent.as_of else None,
                "catalog_release": intent.catalog_release,
                "policy_version": intent.policy_version,
                "vocabulary_version": intent.vocabulary_version,
            },
            "request_fields": list(REQUEST_FIELDS),
            "request": request_preview,
        }
    )
    return EXIT_OK


def add_explain_parser(subcommands: SubParsers) -> None:
    """Register ``explain-intent``.

    One positional argument: the document. No ``--execute``, no ``--submit``, no
    ``--sql`` — a flag that ran the request would make this command the thing it
    exists not to be, and the absence is what stops one being added "just for
    debugging".
    """
    from pathlib import Path

    explain = subcommands.add_parser(
        "explain-intent",
        help="The resolved intent and the request that would be built. Executes nothing.",
    )
    explain.add_argument("document", type=Path)
    explain.set_defaults(handler=explain_intent)
