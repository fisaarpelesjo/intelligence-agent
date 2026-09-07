"""Governed channel rendering capability matrix — T019 (`D-28`; FR-051, FR-103; SC-021).

Per channel: maximum size, expressible structures, permitted meaning-preserving
**structural** degradations, threading and continuation mechanisms with their ordering
guarantee, and the pt-BR wording for every disclosure a degradation requires.

**While `D-28` is undeclared, nothing renders and every response withholds.** That is
deliberate rather than incidental: an unreviewed rendering rule is exactly the
mechanism ADR 0022 exists to prevent, so the matrix's absence is a lock, not a default.

**No capability and no degradation is authored here.** A degradation the matrix does
not declare is refused by the renderer (Phase C, T072); inventing one here would let
this feature decide what a channel may silently do to a governed answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ..contracts.descriptor import ChannelId
from ..contracts.reason_codes import ChannelReasonCode
from .resolve import ContentUnresolvable, effective_instance, read_instances

__all__ = [
    "CAPABILITY_FILE",
    "CAPABILITY_KIND",
    "CAPABILITY_REQUIRED_FIELDS",
    "CAPABILITY_REQUIRED_PER_CHANNEL",
    "resolve_capability_matrix",
]

CAPABILITY_FILE = "channel-capabilities.yaml"
CAPABILITY_KIND = "channel_capability_matrix"
CODE = ChannelReasonCode.CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE

CAPABILITY_REQUIRED_FIELDS: tuple[str, ...] = (
    "version",
    "effective_from",
    "approval",
    "channels",
)

#: Per channel. ``permitted_degradations`` is structural only — the matrix has no field
#: in which a content-altering adaptation could be declared, because there is no
#: permitted one (ADR 0022 § Acceptance).
CAPABILITY_REQUIRED_PER_CHANNEL: tuple[str, ...] = (
    "maximum_body_characters",
    "expressible_structures",
    "permitted_degradations",
    "continuation_mechanism",
    "ordering_guarantee",
    "disclosure_wording",
)


def resolve_capability_matrix(channel: ChannelId) -> Mapping[str, Any]:
    """The effective capability entry for ``channel``, or refuse.

    Raises :class:`ContentUnresolvable` carrying
    ``CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE`` while `D-28` declares no instance,
    which is the shipped state — so every response withholds rather than being
    rendered under an assumed capability.
    """
    instances = read_instances(CAPABILITY_FILE, CAPABILITY_KIND, CODE)
    instance = effective_instance(instances, CAPABILITY_REQUIRED_FIELDS, CODE, CAPABILITY_FILE)
    channels: object = instance["channels"]
    if not isinstance(channels, Mapping):
        raise ContentUnresolvable(CODE, "`channels` is not a mapping")
    entry: object = cast(Mapping[str, Any], channels).get(channel.value)
    if not isinstance(entry, Mapping):
        raise ContentUnresolvable(CODE, f"no capability entry for channel {channel.value}")
    missing = [field for field in CAPABILITY_REQUIRED_PER_CHANNEL if field not in entry]
    if missing:
        raise ContentUnresolvable(
            CODE, f"{channel.value} capability entry is missing {', '.join(sorted(missing))}"
        )
    return cast(Mapping[str, Any], entry)
