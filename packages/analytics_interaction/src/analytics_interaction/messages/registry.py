"""Governed pt-BR message registry — T024 (FR-039, FR-044, FR-102; SC-028, SC-059).

Stored wording selected by reason code. **Never generated, paraphrased,
concatenated from user input or translated at answer time.** The same
``(code, language, content_version)`` returns byte-identical text on every call,
which is what makes `SC-028` a property of the design rather than a discipline
somebody maintains.

**Keyed by a plain language string, deliberately.** ``DeclaredLanguage`` gates
what a *caller* may declare at intake; the registry does not consult it. That
seam is what makes `FR-043` true: adding a language is adding a key set under the
same codes, with **zero** contract change and no edit to this module (`T026`
proves it with a synthetic language).

**Interpolation is allowlisted.** The authored document declares
``allowed_arguments``, and a message referring to anything outside it fails to
load. A metric value, a filter value, a credential or a span of the question can
therefore never be interpolated (`contracts/governed-content.md` §7) — the
allowlist is what makes that structural instead of a review note.

**Automation asserts presence, coverage and stability only.** Whether the
Portuguese is correct stays the `D-10` / `001:T117` reviewer duty and is never
claimed by a test (`FR-044`) — a passing test would otherwise read as a claim
nobody made.
"""

from __future__ import annotations

import string
from functools import lru_cache
from pathlib import Path
from typing import cast

import yaml

from ..contracts.reason_codes import InterpretationReasonCode
from ..governance.schemas import governed_content_root

__all__ = [
    "MESSAGES_DIRECTORY",
    "UNVERSIONED",
    "MessageRegistry",
    "load_registry",
    "message_for",
]

MESSAGES_DIRECTORY = "messages"

#: No approved `D-19` policy exists, so there is no policy version to key wording
#: on. This names the wording set; it is **not** a default standing in for a
#: missing policy — policy resolution refuses independently.
UNVERSIONED = "unversioned"


class MessageRegistry:
    """An immutable, fully-covering map from reason code to stored wording.

    "Fully covering" is checked at construction, not at lookup: a
    consumer-reachable code with no effective message **fails the build**,
    following `001`'s `FR-074`. Discovering it at lookup time would mean
    discovering it when a user was already being refused.
    """

    __slots__ = ("_arguments", "_messages", "content_version", "language")

    def __init__(
        self,
        language: str,
        content_version: str,
        messages: dict[InterpretationReasonCode, str],
        arguments: dict[InterpretationReasonCode, tuple[str, ...]],
    ) -> None:
        missing = sorted(code.value for code in InterpretationReasonCode if code not in messages)
        if missing:
            raise ValueError(f"the registry declares no wording for: {missing}")
        self.language = language
        self.content_version = content_version
        self._messages = dict(messages)
        self._arguments = dict(arguments)

    def text_for(self, code: InterpretationReasonCode) -> str:
        """The stored wording, verbatim.

        Raises rather than inventing a fallback sentence: a generated sentence
        would be exactly the free-form narration this feature exists to remove.
        """
        try:
            return self._messages[code]
        except KeyError as exc:  # pragma: no cover - construction guarantees coverage
            raise ValueError(f"no governed wording for {code.value}") from exc

    def arguments_for(self, code: InterpretationReasonCode) -> tuple[str, ...]:
        """The allowlisted interpolation fields this message declares."""
        return self._arguments.get(code, ())

    @property
    def codes(self) -> frozenset[InterpretationReasonCode]:
        return frozenset(self._messages)


def registry_path(language: str) -> Path:
    """Located rather than configured — a settable path is an ungoverned override."""
    return governed_content_root() / MESSAGES_DIRECTORY / f"{language.lower()}.yaml"


def _placeholders(text: str) -> frozenset[str]:
    """Named ``{field}`` placeholders in an authored message."""
    return frozenset(
        name for _, name, _, _ in string.Formatter().parse(text) if name is not None and name
    )


def load_registry(language: str = "pt-BR", *, path: Path | None = None) -> MessageRegistry:
    """Load and validate one language's governed wording.

    Validation is the point of the function, not a side effect. Four ways an
    authored document is rejected, each of which would otherwise surface as a
    wrong message shown to a real user:

    * a code that is not a member of the enum — an orphan message;
    * a code declared twice — two wordings, neither authoritative;
    * a placeholder outside ``allowed_arguments`` — an interpolation that could
      carry a value;
    * a declared argument the text never uses, or a used placeholder the entry
      never declares — the declaration and the text disagreeing about what may
      be inserted.
    """
    target = path or registry_path(language)
    raw: object = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{target.name}: expected a mapping at the document root")
    document = cast("dict[str, object]", raw)

    version = document.get("content_version", UNVERSIONED)
    if not isinstance(version, str) or not version:
        raise ValueError(f"{target.name}: `content_version` must be a non-empty string")

    raw_allowed: object = document.get("allowed_arguments", [])
    if not isinstance(raw_allowed, list):
        raise ValueError(f"{target.name}: `allowed_arguments` must be a list")
    allowed = frozenset(cast("list[str]", raw_allowed))

    entries: object = document.get("messages", [])
    if not isinstance(entries, list):
        raise ValueError(f"{target.name}: `messages` must be a list")

    messages: dict[InterpretationReasonCode, str] = {}
    arguments: dict[InterpretationReasonCode, tuple[str, ...]] = {}
    for raw_entry in cast("list[object]", entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"{target.name}: each message must be a mapping")
        entry = cast("dict[str, object]", raw_entry)

        raw_code = entry.get("code")
        if not isinstance(raw_code, str):
            raise ValueError(f"{target.name}: each message needs a `code`")
        try:
            code = InterpretationReasonCode(raw_code)
        except ValueError as exc:
            raise ValueError(f"{target.name}: {raw_code} is not an interpretation code") from exc
        if code in messages:
            raise ValueError(f"{target.name}: {code.value} is worded more than once")

        declared_language = entry.get("language")
        if declared_language != language:
            raise ValueError(
                f"{target.name}: {code.value} declares language {declared_language!r}, "
                f"but this document is {language!r}"
            )

        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{target.name}: {code.value} has no text")

        raw_args: object = entry.get("arguments", [])
        if not isinstance(raw_args, list):
            raise ValueError(f"{target.name}: {code.value}: `arguments` must be a list")
        declared = tuple(cast("list[str]", raw_args))

        used = _placeholders(text)
        outside = sorted(used - allowed)
        if outside:
            raise ValueError(
                f"{target.name}: {code.value} interpolates non-allowlisted fields: {outside}"
            )
        if used != frozenset(declared):
            raise ValueError(
                f"{target.name}: {code.value} declares arguments {sorted(declared)} "
                f"but its text uses {sorted(used)}"
            )

        messages[code] = text
        arguments[code] = declared

    return MessageRegistry(language, version, messages, arguments)


@lru_cache(maxsize=8)
def _cached_registry(language: str) -> MessageRegistry:
    return load_registry(language)


def message_for(code: InterpretationReasonCode, *, language: str = "pt-BR") -> str:
    """The governed wording for ``code``, byte-identical across repeats."""
    return _cached_registry(language).text_for(code)
