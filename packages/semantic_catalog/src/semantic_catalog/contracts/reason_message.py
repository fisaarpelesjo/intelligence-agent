"""Canonical pt-BR reason messages — T018 (FR-055, FR-074).

FR-055 forbids producing provenance wording by translation at answer time, so
the wording has to exist somewhere governed. This is that registry: one canonical
message per consumer-reachable reason code, versioned, owned and reviewed.

**Interpolation is allowlisted per message.** A message may only substitute
fields it declares, and every declared field must be on the registry-wide
allowlist. Metric values, credentials, personal data and prompt text are never
interpolatable — not because a validator strips them, but because they are not
in the vocabulary at all.

``render`` raises on a missing or unexpected field. A consumer that cannot render
a message must surface that as an error; **it may not invent or translate one**.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from ._base import CatalogModel, Identifier, PtBrText
from .reason_codes import ReasonCode

__all__ = [
    "ALLOWED_INTERPOLATION_FIELDS",
    "MissingReasonMessageError",
    "ReasonMessage",
    "ReasonMessageRegistry",
]

#: Registry-wide interpolation vocabulary. Nothing outside this set may appear in
#: a message. Metric values, credentials, PII and prompt text are absent by
#: construction, not by filtering.
ALLOWED_INTERPOLATION_FIELDS: frozenset[str] = frozenset(
    {
        "metric_id",
        "dimension_id",
        "source_id",
        "missing_fields",
        "owner",
        "last_successful_update",
        "delay_tolerance",
        "completeness_ratio",
        "period_start",
        "period_end",
        "cutoff",
        "cohort_date",
        "required_maturity",
        "available_from",
        "replacement_metric_id",
        "metric_version_id",
        "policy_version",
        "catalog_release_id",
        "access_tag",
    }
)

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class MissingReasonMessageError(Exception):
    """No canonical message for a consumer-reachable code. Fails the build."""


class ReasonMessage(CatalogModel):
    """One canonical pt-BR message."""

    reason_code: ReasonCode
    version: StrictInt = Field(ge=1)
    effective_from: date
    owner_role: Identifier
    reviewed_by_role: Identifier = Field(
        description="Who signed off the Portuguese. Automation checks presence, not correctness.",
    )
    interpolation_fields: tuple[Identifier, ...] = ()
    message: PtBrText

    @model_validator(mode="after")
    def _interpolation_is_declared_and_allowlisted(self) -> ReasonMessage:
        used = set(_PLACEHOLDER.findall(self.message))
        declared = set(self.interpolation_fields)

        outside = sorted(declared - ALLOWED_INTERPOLATION_FIELDS)
        if outside:
            raise ValueError(
                f"message for {self.reason_code.value} declares interpolation fields outside the "
                f"allowlist: {outside}; metric values, credentials, personal data and prompt text "
                "are never interpolatable (FR-074)"
            )
        undeclared = sorted(used - declared)
        if undeclared:
            raise ValueError(
                f"message for {self.reason_code.value} interpolates undeclared fields {undeclared}"
            )
        unused = sorted(declared - used)
        if unused:
            raise ValueError(
                f"message for {self.reason_code.value} declares unused interpolation fields "
                f"{unused}; an unused declaration widens the vocabulary for nothing"
            )
        return self

    def render(self, values: Mapping[str, str]) -> str:
        """Substitute the declared fields.

        Raises on a missing value rather than emitting a half-rendered message —
        a placeholder leaking into a user-visible refusal is worse than an error.
        """
        missing = sorted(set(self.interpolation_fields) - set(values))
        if missing:
            raise ValueError(
                f"cannot render {self.reason_code.value}: missing interpolation values {missing}"
            )
        return _PLACEHOLDER.sub(lambda m: values[m.group(1)], self.message)


class ReasonMessageRegistry(CatalogModel):
    """``semantic/content/reason-messages.pt-BR.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["reason_messages"]
    lang: Literal["pt-BR"]
    messages: tuple[ReasonMessage, ...] = ()

    @model_validator(mode="after")
    def _one_message_per_code(self) -> ReasonMessageRegistry:
        codes = [m.reason_code for m in self.messages]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate reason_code in the message registry")
        return self

    def get(self, code: ReasonCode) -> ReasonMessage | None:
        return next((m for m in self.messages if m.reason_code is code), None)

    def require(self, code: ReasonCode) -> ReasonMessage:
        """The message for ``code``, or raise.

        Never falls back to the code name or an English string: a consumer that
        cannot find a canonical message must not invent or translate one.
        """
        message = self.get(code)
        if message is None:
            raise MissingReasonMessageError(
                f"no canonical pt-BR message for {code.value}; messages are authored and reviewed, "
                "never translated at answer time (FR-055)"
            )
        return message

    def missing_codes(self, publishable: frozenset[ReasonCode]) -> tuple[ReasonCode, ...]:
        """Consumer-reachable codes with no message. Non-empty fails the build."""
        return tuple(code for code in ReasonCode if code in publishable and self.get(code) is None)
