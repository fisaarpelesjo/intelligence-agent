"""Governed operational metadata and retention rule — T021 (`D-29`; FR-076; SC-036).

Exactly which operational metadata may persist, for how long, under whose approval, and
the assertion that it carries no analytical value and no unrestricted user content.

**While `D-29` is undeclared, nothing persists.** Not "nothing important" — nothing.
The measured persisted-record count is zero (`SC-036`), and this feature owns no store
for one to accumulate in (`FR-075`).

**No retention value is authored here.** "Minimal operational metadata" is not a
specification until someone names the fields and the period; naming them here would be
inventing a privacy decision (`research.md` `R-14`).

The in-memory idempotency structure (Phase C, T081) is **not** persistence: it is
process-local, window-bounded, and carries no question text, answer content, value or
personal data. It does not become permissible by this document and does not wait for it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..contracts.reason_codes import ChannelReasonCode
from .resolve import ContentUnresolvable, effective_instance, read_instances

__all__ = [
    "METADATA_POLICY_FILE",
    "METADATA_POLICY_KIND",
    "METADATA_POLICY_REQUIRED_FIELDS",
    "persistence_permitted",
    "resolve_metadata_policy",
]

METADATA_POLICY_FILE = "metadata-policy.yaml"
METADATA_POLICY_KIND = "channel_metadata_policy"
CODE = ChannelReasonCode.CHANNEL_METADATA_POLICY_UNRESOLVABLE

METADATA_POLICY_REQUIRED_FIELDS: tuple[str, ...] = (
    "version",
    "effective_from",
    "approval",
    "permitted_fields",
    "retention_days",
    "carries_no_analytical_value",
)


def resolve_metadata_policy() -> Mapping[str, Any]:
    """The effective metadata policy, or refuse.

    Raises :class:`ContentUnresolvable` carrying ``CHANNEL_METADATA_POLICY_UNRESOLVABLE``
    while `D-29` declares no instance, which is the shipped state.
    """
    instances = read_instances(METADATA_POLICY_FILE, METADATA_POLICY_KIND, CODE)
    instance = effective_instance(
        instances, METADATA_POLICY_REQUIRED_FIELDS, CODE, METADATA_POLICY_FILE
    )
    permitted: object = instance["permitted_fields"]
    if not isinstance(permitted, Sequence) or isinstance(permitted, str | bytes):
        raise ContentUnresolvable(CODE, "`permitted_fields` is not a list")
    if instance["carries_no_analytical_value"] is not True:
        raise ContentUnresolvable(
            CODE, "the policy does not assert that the metadata carries no analytical value"
        )
    return instance


def persistence_permitted() -> bool:
    """May **anything** be persisted?

    ``False`` while `D-29` is undeclared, which is the shipped state. A boolean rather
    than a raise, because the answer is a governed fact a caller may need to record —
    and because "nothing persists" is a normal operating state here, not a failure.
    """
    try:
        resolve_metadata_policy()
    except ContentUnresolvable:
        return False
    return True
