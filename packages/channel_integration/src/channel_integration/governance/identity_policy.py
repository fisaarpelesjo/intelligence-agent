"""Governed identity-binding rule — T020 (`D-27`; FR-019, FR-103; SC-010).

How an external channel identity becomes a governed principal within a tenant, who
owns the bindings, how one is revoked, and what an ambiguous or expired binding does.

**No binding is authored here.** The registry's content and its administration belong
to `D-27` and to whoever owns it (`NG-5`). While `D-27` is undeclared, no external
identity resolves and every inbound message refuses before any interpretation cost
(`C-4`, `FR-019`).

The distinction this module keeps: a **rule** says what resolution means; a
**registry** says which identities exist. Both live in `D-27`, and neither is
substitutable by this feature. A binding invented here would be an authorisation
decision made by a transport.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..contracts.reason_codes import ChannelReasonCode
from .resolve import ContentUnresolvable, effective_instance, read_instances

__all__ = [
    "IDENTITY_RULE_FILE",
    "IDENTITY_RULE_KIND",
    "IDENTITY_RULE_REQUIRED_FIELDS",
    "resolve_identity_rule",
]

IDENTITY_RULE_FILE = "identity-binding-rule.yaml"
IDENTITY_RULE_KIND = "channel_identity_binding_rule"
CODE = ChannelReasonCode.CHANNEL_IDENTITY_POLICY_UNRESOLVABLE

#: ``registry_ref`` names where the bindings live; it is **not** a list of bindings.
#: A rule document carrying identities would put personal data in a governed content
#: file in the repository, which `FR-077` forbids.
IDENTITY_RULE_REQUIRED_FIELDS: tuple[str, ...] = (
    "version",
    "effective_from",
    "approval",
    "registry_ref",
    "revocation_rule",
    "ambiguity_rule",
    "expiry_rule",
)


def resolve_identity_rule() -> Mapping[str, Any]:
    """The effective identity-binding rule, or refuse.

    Raises :class:`ContentUnresolvable` carrying
    ``CHANNEL_IDENTITY_POLICY_UNRESOLVABLE`` while `D-27` declares no instance, which
    is the shipped state. No mapping is defaulted, inferred or accepted from a message.
    """
    instances = read_instances(IDENTITY_RULE_FILE, IDENTITY_RULE_KIND, CODE)
    instance = effective_instance(
        instances, IDENTITY_RULE_REQUIRED_FIELDS, CODE, IDENTITY_RULE_FILE
    )
    registry_ref: object = instance["registry_ref"]
    if not isinstance(registry_ref, str) or not registry_ref.strip():
        raise ContentUnresolvable(CODE, "`registry_ref` is absent or blank")
    return instance
