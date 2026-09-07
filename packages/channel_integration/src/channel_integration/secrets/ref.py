"""Opaque credential references — T046 (FR-068 — FR-070; SC-031, SC-032).

A `SecretRef` names credential material. It **does not carry it**.

The distinction is the whole design. Redaction can be forgotten; a value that was never in the
object cannot leak from it. So this type holds a **name and a custody declaration**, and the
material itself is fetched inside an adapter through `secrets.resolver`, at the moment of use,
and never returned to the core (`FR-071`).

Four properties, each closing a way a secret normally escapes:

* ``repr`` and ``str`` are the redacted name, so an f-string, a traceback, a pydantic error and
  a debug print all yield the same non-disclosing text;
* there is **no field** holding a value — not even an optional one;
* equality and hashing are over the *name*, so a reference can be a dict key without a value
  existing to compare;
* nothing is serialised: the model refuses to be dumped with a value because there is none.

No material is invented, generated, defaulted or silently provisioned (`FR-069`). While
`D-22` to `D-25` are undeclared, every reference resolves to nothing and the channel refuses.
"""

from __future__ import annotations

from pydantic import Field

from ..contracts._base import ChannelModel
from ..contracts.descriptor import ChannelId, CredentialRecord

__all__ = ["SecretRef"]


class SecretRef(ChannelModel):
    """A pointer to credential material, with its custody declared."""

    #: Stable, non-secret name. Appears in an operator-facing message; never a value.
    name: str = Field(min_length=1)
    channel: ChannelId
    #: Which external record must be declared before this reference resolves to anything.
    credential_record: CredentialRecord
    #: Who holds the material. Prose, for a human reading a refusal — not a lookup key.
    custody: str = Field(min_length=1)
    #: Rotation cadence as the record declares it. Present so a rotation is a governed fact
    #: rather than an operational habit (`FR-074`).
    rotation: str = Field(min_length=1)

    def __repr__(self) -> str:
        return f"SecretRef(name={self.name!r}, value=<redacted>)"

    def __str__(self) -> str:
        return f"{self.name}=<redacted>"
