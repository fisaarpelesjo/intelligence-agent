"""Governed pt-BR message registry (`FR-057`, `FR-058`, `FR-059`).

Stored wording selected by reason code — never generated, translated or
composed at answer time (`FR-057`). Automation reports presence and
determinism only; linguistic correctness is the reviewer duty `D-10`
records (`FR-059`).
Deterministic pt-BR message lookup — T016 (FR-058, FR-059, FR-060; SC-021).

Stored wording, selected by reason code. Never generated, never translated at
answer time, and never produced by a language model. The same
``(code, policy_version)`` returns byte-identical text on every call, which is
what makes a refusal reproducible rather than merely plausible.

Automation asserts **presence, coverage and stability only**. Linguistic
correctness stays the reviewer duty carried by inherited record `001:T117`
(`D-10`) and is never claimed by a test here — a passing test would otherwise
read as a claim nobody made.
"""

from __future__ import annotations

from functools import lru_cache
from typing import cast

import yaml

from ..contracts.operators import governed_content_root
from ..contracts.reason_codes import AnalyticsReasonCode

__all__ = ["UNVERSIONED", "MessageRegistry", "load_registry", "message_for"]

#: Wording is keyed by (code, policy_version). Until an approved policy exists
#: there is no version to key on, so the authored registry uses this sentinel.
#: It is not a default that hides a missing policy — policy resolution refuses
#: independently (`FR-050`); this only names the wording set.
UNVERSIONED = "unversioned"


class MessageRegistry:
    """An immutable, fully-covering map from reason code to stored pt-BR wording."""

    __slots__ = ("_messages", "policy_version")

    def __init__(self, policy_version: str, messages: dict[AnalyticsReasonCode, str]) -> None:
        missing = sorted(code.value for code in AnalyticsReasonCode if code not in messages)
        if missing:
            raise ValueError(f"the registry declares no wording for: {missing}")
        self.policy_version = policy_version
        self._messages = dict(messages)

    def text_for(self, code: AnalyticsReasonCode) -> str:
        """The stored wording. Raises rather than inventing a fallback sentence."""
        try:
            return self._messages[code]
        except KeyError as exc:  # pragma: no cover - construction guarantees coverage
            raise ValueError(f"no governed wording for {code.value}") from exc

    @property
    def codes(self) -> frozenset[AnalyticsReasonCode]:
        return frozenset(self._messages)


@lru_cache(maxsize=1)
def load_registry() -> MessageRegistry:
    """Load the governed registry from ``query_governance/messages/pt-br.yaml``."""
    path = governed_content_root() / "messages" / "pt-br.yaml"
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("pt-br.yaml: expected a mapping at the document root")
    document = cast(dict[str, object], raw)

    version = document.get("policy_version", UNVERSIONED)
    if not isinstance(version, str) or not version:
        raise ValueError("pt-br.yaml: `policy_version` must be a non-empty string")

    entries: object = document.get("messages", [])
    if not isinstance(entries, list):
        raise ValueError("pt-br.yaml: `messages` must be a list")

    messages: dict[AnalyticsReasonCode, str] = {}
    for raw_entry in cast(list[object], entries):
        if not isinstance(raw_entry, dict):
            raise ValueError("pt-br.yaml: each message must be a mapping")
        entry = cast(dict[str, object], raw_entry)
        code_value = entry.get("code")
        text = entry.get("text")
        if not isinstance(code_value, str) or not isinstance(text, str):
            raise ValueError("pt-br.yaml: each message needs a string `code` and `text`")
        try:
            code = AnalyticsReasonCode(code_value)
        except ValueError as exc:
            raise ValueError(f"pt-br.yaml: {code_value} is not a governed reason code") from exc
        if code in messages:
            raise ValueError(f"pt-br.yaml: {code_value} appears more than once")
        messages[code] = text.strip()

    return MessageRegistry(version, messages)


def message_for(code: AnalyticsReasonCode) -> str:
    """The governed pt-BR wording for ``code``."""
    return load_registry().text_for(code)
