"""The single upstream submission path — T118 (ADR 0017; `contracts/interaction-port.md`)."""

from .port import (
    INTERACTION_BOUNDARY_DETAIL,
    InteractionPort,
    intake_from_envelope,
    submit,
)

__all__ = [
    "INTERACTION_BOUNDARY_DETAIL",
    "InteractionPort",
    "intake_from_envelope",
    "submit",
]
