"""The answer contract carries no channel — T152 (FR-040; SC-007).

    Response contracts MUST be channel-agnostic and structured for future
    delivery through chat and other channels, without implementing those channels
    here. — `FR-040`

    Evidence: no formatting, markup, template or rendering hint in the answer
    contract. — `tasks.md` T152

## Why an absence needs a test

"Channel-agnostic" is the kind of property that is true on the day it is written
and false a month later, because adding a channel hint is always locally
reasonable: one `markdown` flag for the chat adapter, one `emoji` field because
Slack renders them, one `max_width` because a terminal wraps. Each is a small
convenience and each moves a presentation decision into a governed contract, where
it becomes something the next channel has to honour or contradict.

The failure is not cosmetic. A contract that carries `**bold**` in its wording has
put markup into governed content, so the wording a reviewer approved is not the
wording a caller sees, and the reviewer approved a string with syntax in it whose
meaning depends on a renderer nobody named.

## What is asserted

Three things, and the third is the one that survives a refactor:

* **field names** — no field on any answer-side contract names a channel, a
  format, a template or a rendering concern;
* **field values** — every governed string reachable from the contracts is a code
  or a governed identifier, never a rendered fragment;
* **field types** — the wording fields are `LocalizedRef`s, which are pointers
  into governed content. A pointer cannot carry markup, so the property holds by
  the shape of the type rather than by a scan that has to be kept current.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import BaseModel

import analytics_interaction
from analytics_interaction.contracts import answer as answer_contracts
from analytics_interaction.contracts._base import LocalizedRef
from analytics_interaction.contracts.answer import (
    AnalyticsAnswer,
    AnswerClaim,
    AttributedCaveat,
    CaveatSet,
    ComparisonBasis,
    InsufficiencyNotice,
)

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
CONTRACTS = SRC / "contracts"

#: The answer-side contracts. Named rather than discovered, so a new one added
#: without being listed fails the completeness test below rather than being
#: silently exempt from every scan in this file.
ANSWER_CONTRACTS: tuple[type[BaseModel], ...] = (
    AnalyticsAnswer,
    AnswerClaim,
    AttributedCaveat,
    CaveatSet,
    ComparisonBasis,
    InsufficiencyNotice,
)

#: Names a channel, a format, a template or a rendering hint would arrive under.
#:
#: Substrings, matched against **declared field names** rather than raw text, so
#: a docstring explaining that there is no channel does not read as a channel.
CHANNEL_NAMES: tuple[str, ...] = (
    "channel",
    "format",
    "template",
    "render",
    "markdown",
    "markup",
    "html",
    "css",
    "style",
    "theme",
    "emoji",
    "icon",
    "colour",
    "color",
    "font",
    "width",
    "layout",
    "block",
    "attachment",
    "thread",
    "slack",
    "teams",
    "whatsapp",
    "webhook",
    "mention",
    "button",
    "card",
    "chart",
    "plot",
    "image",
    "truncate",
    "ellipsis",
    "indent",
    "bullet",
)

#: Markup a rendered fragment would carry. Checked against governed string
#: **values**, not names.
MARKUP_FRAGMENTS: tuple[str, ...] = (
    "**",
    "__",
    "<b>",
    "<br",
    "<p>",
    "<div",
    "<span",
    "</",
    "\\n\\n",
    "```",
    "* ",
    "- [",
    "|---",
    "{{",
    "}}",
    "%s",
    "{0}",
    ":smile:",
)


def _contract_classes() -> list[type[BaseModel]]:
    """Every pydantic model declared under `contracts/`, discovered.

    Discovery *and* the named list above: the list is what the scans iterate, and
    discovery is what proves the list is complete. Either alone would let a new
    contract escape.
    """
    found: list[type[BaseModel]] = []
    for module_name in dir(answer_contracts):
        candidate = getattr(answer_contracts, module_name)
        if (
            isinstance(candidate, type)
            and issubclass(candidate, BaseModel)
            # Defined here, not merely imported here. The module legitimately
            # re-exports `ResolvedIntent`, `ResultProvenance` and `LocalizedRef`,
            # which are other files' contracts and are scanned by their own
            # suites; treating an import as a declaration would make this file
            # responsible for them and would still miss a genuinely new one.
            and candidate.__module__ == answer_contracts.__name__
        ):
            found.append(candidate)
    return found


# --- the scan covers what it claims to ------------------------------------------


def test_every_answer_contract_is_listed() -> None:
    """A new answer contract cannot be added without joining the scans."""
    declared = {cls.__name__ for cls in _contract_classes()}
    listed = {cls.__name__ for cls in ANSWER_CONTRACTS}
    assert declared == listed, declared ^ listed


def test_the_contract_set_is_not_empty() -> None:
    """A scan over nothing passes for the wrong reason."""
    assert len(ANSWER_CONTRACTS) == 6
    assert all(cls.model_fields for cls in ANSWER_CONTRACTS)


# --- no field names a channel ---------------------------------------------------


@pytest.mark.parametrize("contract", ANSWER_CONTRACTS, ids=lambda c: c.__name__)
def test_no_field_names_a_channel_or_a_format(contract: type[BaseModel]) -> None:
    """**The load-bearing assertion.**

    Every field name, lowercased, against every forbidden substring. A ``width``
    or a ``block`` is as much a rendering decision as a ``markdown`` flag, and the
    former is the one that arrives looking harmless.
    """
    offenders = [
        f"{contract.__name__}.{name}"
        for name in contract.model_fields
        for banned in CHANNEL_NAMES
        if banned in name.lower()
    ]
    assert not offenders, f"a channel or formatting field exists: {offenders}"


def test_the_scan_would_catch_a_planted_field() -> None:
    """A denylist never shown to fire proves nothing about the fields it names.

    Every entry planted in turn, so a token that matched nothing — a typo, a name
    that cannot occur — is visible as a hole rather than as a passing scan.
    """
    for banned in CHANNEL_NAMES:
        planted = {f"answer_{banned}_hint": str}
        assert [name for name in planted for token in CHANNEL_NAMES if token in name.lower()], (
            banned
        )


# --- wording is a pointer, so it cannot carry markup ----------------------------


def test_every_wording_field_is_a_governed_pointer() -> None:
    """The structural half, and the half that survives a refactor.

    ``AnswerClaim.message`` and ``AttributedCaveat`` wording are ``LocalizedRef``
    — a code, a language and a content version. A pointer into approved content
    cannot carry a rendered fragment, so this property does not depend on anybody
    remembering to check for one.
    """
    assert AnswerClaim.model_fields["message"].annotation is LocalizedRef
    localised = [
        (contract.__name__, name)
        for contract in ANSWER_CONTRACTS
        for name, field in contract.model_fields.items()
        if field.annotation is LocalizedRef
    ]
    assert localised, "no wording field is a governed pointer"


def test_a_localized_ref_carries_no_rendered_text() -> None:
    """Three identifiers and an allowlisted argument list.

    ``arguments`` is the one place a string a caller influenced could reach
    governed wording, and it is not free-form: the registry allowlists which field
    names may be interpolated, so a metric value, a filter value, a credential or
    a span of the question has no name to arrive under.

    Pinned as a set. A fifth field — a ``rendered``, a ``formatted``, a
    ``fallback_text`` — would be the moment this stops being a pointer, and it
    fails here.
    """
    assert set(LocalizedRef.model_fields) == {
        "code",
        "language",
        "content_version",
        "arguments",
    }
    assert LocalizedRef.model_fields["arguments"].default == ()


def test_no_localized_ref_argument_can_carry_markup() -> None:
    """The argument list is pairs of strings, so markup is *expressible* there.

    What forecloses it is the registry's allowlist of interpolable field names,
    which lives in `governed-content.md` §7 and is enforced where the wording is
    resolved. Asserted here as the shape — pairs, not a rendered blob — so a
    future edit widening it to ``str`` or ``Any`` fails at this boundary rather
    than at the moment somebody reads an answer.
    """
    annotation = str(LocalizedRef.model_fields["arguments"].annotation)
    assert "tuple" in annotation and "str" in annotation
    assert "Any" not in annotation and "object" not in annotation


# --- no governed string value is a rendered fragment ----------------------------


def test_no_default_value_in_the_contracts_carries_markup() -> None:
    """A default is authored text, and authored text is where markup arrives."""
    offenders: list[str] = []
    for contract in ANSWER_CONTRACTS:
        for name, field in contract.model_fields.items():
            default = field.default
            if isinstance(default, str):
                offenders += [
                    f"{contract.__name__}.{name}"
                    for fragment in MARKUP_FRAGMENTS
                    if fragment in default
                ]
    assert not offenders, f"a contract default carries markup: {offenders}"


def test_no_contract_module_declares_a_format_string() -> None:
    """An f-string or a ``.format`` call in a contract is a renderer.

    Scanned as AST, not as text: a docstring that shows what markup looks like is
    documentation, and a scan that fired on it would be deleted rather than fixed.
    """
    offenders: list[str] = []
    for path in sorted(CONTRACTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"format", "format_map"}
            ):
                offenders.append(f"{path.name}:{node.lineno} .{node.func.attr}()")
    assert not offenders, f"a contract renders a string: {offenders}"


# --- the answer is complete without a channel -----------------------------------


def test_the_answer_declares_exactly_its_eleven_governed_fields() -> None:
    """Pinned as a set, so a twelfth arriving is a decision somebody makes here.

    The count is not the point — the enumeration is. A channel field added
    alongside these would satisfy every substring scan if it were named something
    innocuous, and would still fail this.
    """
    assert set(AnalyticsAnswer.model_fields) == {
        "interpreted",
        "claims",
        "caveats",
        "provenance",
        "insufficiency",
        "language",
        "reference_date",
        "as_of",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
    }


def test_the_answer_forbids_an_unknown_field() -> None:
    """A channel cannot be attached at runtime either.

    ``extra="forbid"`` rather than a validator: a contract that has no such field
    and refuses to grow one needs no rule about channels at all.
    """
    assert AnalyticsAnswer.model_config.get("extra") == "forbid"
    for contract in ANSWER_CONTRACTS:
        assert contract.model_config.get("extra") == "forbid", contract.__name__


def test_no_answer_contract_imports_a_channel_library() -> None:
    """The absence of a dependency, asserted where somebody would add one."""
    forbidden = {"slack_sdk", "discord", "telegram", "twilio", "jinja2", "markdown", "rich"}
    for path in sorted(CONTRACTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, f"{path.name}: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, f"{path.name}: {node.module}"
