"""Governed pt-BR message registry — T024 (FR-045; SC-060).

Stored wording selected by reason code. **Never generated, paraphrased, concatenated
from a payload or translated at delivery time.** The same
``(code, language, content_version)`` returns byte-identical text on every call, which
is what makes message stability a property of the design rather than a discipline.

**Keyed by a plain language string, deliberately.** Adding a language is adding a key
set under the same codes, with zero contract change and no edit to this module.

**Interpolation is allowlisted**, and the allowlist here is deliberately tiny: only
``channel`` and ``message_kind``. A secret, header, signature, raw identifier, payload,
question, answer, value or provider error text can therefore never be interpolated —
not because a reviewer would catch it, but because the document fails to load.

**Coverage is checked at construction, not at lookup.** A consumer-reachable code with
no effective message fails the build, following `001`'s `FR-074`. Discovering it at
lookup time would mean discovering it while a sender was already being refused.

**Automation asserts presence, coverage and stability only.** Whether the Portuguese is
correct stays the `D-10` / `001:T117` reviewer duty and is never claimed by a test.
"""

from __future__ import annotations

import string
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any, cast

import yaml

from ..contracts.reason_codes import ChannelReasonCode
from ..governance.resolve import governed_content_root

__all__ = [
    "MESSAGES_DIRECTORY",
    "MESSAGES_FILE",
    "UNVERSIONED",
    "MessageRegistry",
    "load_registry",
    "message_for",
]

MESSAGES_DIRECTORY = "messages"
MESSAGES_FILE = "pt-br.yaml"

#: No approved `D-26` policy exists, so there is no policy version to key wording on.
#: This names the wording set; it is **not** a default standing in for a missing
#: policy — policy resolution refuses independently.
UNVERSIONED = "unversioned"


class MessageRegistryMalformed(ValueError):  # noqa: N818 - the document is malformed
    """The authored message document cannot be read as written.

    Distinct from a governed refusal: this is a defect in authored content, and a
    build must fail on it rather than a sender being refused with a missing message.
    """


class MessageRegistry:
    """An immutable, fully-covering map from channel reason code to stored wording."""

    __slots__ = ("_arguments", "_messages", "content_version", "language")

    def __init__(
        self,
        language: str,
        content_version: str,
        messages: Mapping[ChannelReasonCode, str],
        arguments: Mapping[ChannelReasonCode, tuple[str, ...]],
    ) -> None:
        missing = [code.value for code in ChannelReasonCode if code not in messages]
        if missing:
            raise MessageRegistryMalformed(
                f"no {language} wording for: {', '.join(sorted(missing))}"
            )
        self.language = language
        self.content_version = content_version
        self._messages = dict(messages)
        self._arguments = dict(arguments)

    def text_for(self, code: ChannelReasonCode, **arguments: str) -> str:
        """The stored wording for ``code``, with allowlisted arguments substituted.

        An argument the message does not declare is refused rather than ignored: a
        silently dropped argument is how a value ends up in a message that was
        supposed to have none, and an unexpected one usually means a caller believes
        it is disclosing something.
        """
        declared = self._arguments.get(code, ())
        unexpected = sorted(set(arguments) - set(declared))
        if unexpected:
            raise MessageRegistryMalformed(
                f"{code.value} declares no argument named {', '.join(unexpected)}"
            )
        absent = sorted(set(declared) - set(arguments))
        if absent:
            raise MessageRegistryMalformed(f"{code.value} requires argument {', '.join(absent)}")
        template = self._messages[code]
        return template.format(**arguments) if declared else template

    def codes(self) -> frozenset[ChannelReasonCode]:
        return frozenset(self._messages)


def _document() -> Mapping[str, Any]:
    path = governed_content_root() / MESSAGES_DIRECTORY / MESSAGES_FILE
    if not path.is_file():
        raise MessageRegistryMalformed(f"{MESSAGES_DIRECTORY}/{MESSAGES_FILE} does not exist")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        raise MessageRegistryMalformed(f"{MESSAGES_FILE} is not a mapping")
    return cast(Mapping[str, Any], loaded)


@lru_cache(maxsize=1)
def load_registry() -> MessageRegistry:
    """Read and validate the authored pt-BR wording.

    Cached because the document is authored content that cannot change while a process
    runs — unlike a readiness record, which is deliberately re-read on every call
    because a withdrawal of readiness must take effect immediately.
    """
    document = _document()
    if document.get("schema_version") != 1:
        raise MessageRegistryMalformed(f"{MESSAGES_FILE} declares an unknown schema_version")
    if document.get("kind") != "channel_messages":
        raise MessageRegistryMalformed(f"{MESSAGES_FILE} declares kind {document.get('kind')!r}")
    content_version = document.get("content_version")
    if not isinstance(content_version, str) or not content_version:
        raise MessageRegistryMalformed(f"{MESSAGES_FILE} declares no content_version")

    allowed: object = document.get("allowed_arguments", [])
    if not isinstance(allowed, Sequence) or isinstance(allowed, str | bytes):
        raise MessageRegistryMalformed("`allowed_arguments` is not a list")
    allowlist = frozenset(str(name) for name in cast(Sequence[object], allowed))

    raw_entries: object = document.get("messages", [])
    if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, str | bytes):
        raise MessageRegistryMalformed("`messages` is not a list")
    entries = cast(Sequence[object], raw_entries)

    messages: dict[ChannelReasonCode, str] = {}
    arguments: dict[ChannelReasonCode, tuple[str, ...]] = {}
    language = "pt-BR"
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise MessageRegistryMalformed("a message entry is not a mapping")
        fields = cast(Mapping[str, Any], entry)
        raw_code: object = fields.get("code")
        try:
            code = ChannelReasonCode(raw_code)
        except ValueError as exc:
            raise MessageRegistryMalformed(f"unknown reason code {raw_code!r}") from exc
        if code in messages:
            raise MessageRegistryMalformed(f"{code.value} has more than one message")
        text: object = fields.get("text")
        if not isinstance(text, str) or not text.strip():
            raise MessageRegistryMalformed(f"{code.value} has no text")
        raw_arguments: object = fields.get("arguments", ())
        if not isinstance(raw_arguments, Sequence) or isinstance(raw_arguments, str | bytes):
            raise MessageRegistryMalformed(f"{code.value} declares a non-list `arguments`")
        declared = tuple(str(name) for name in cast(Sequence[object], raw_arguments))
        outside = sorted(set(declared) - allowlist)
        if outside:
            raise MessageRegistryMalformed(
                f"{code.value} interpolates non-allowlisted {', '.join(outside)}"
            )
        used = {
            field
            for _, field, _, _ in string.Formatter().parse(text)
            if field is not None and field != ""
        }
        if used != set(declared):
            raise MessageRegistryMalformed(
                f"{code.value} declares arguments {sorted(declared)} but uses {sorted(used)}"
            )
        messages[code] = text
        arguments[code] = declared
        language = str(fields.get("language", language))

    return MessageRegistry(language, content_version, messages, arguments)


def message_for(code: ChannelReasonCode, **arguments: str) -> str:
    """The governed pt-BR wording for ``code``."""
    return load_registry().text_for(code, **arguments)
