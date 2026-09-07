"""Shared contract base — T003's precondition.

Mirrors `005`'s ``contracts/_base.py`` in the two things that matter: models are
**frozen and forbid extra fields**, and a governed name is a constrained string
rather than a free one.

**Frozen is not tidiness here.** An ordering whose components could be mutated
after construction would let a caller change the grounds of a position without
changing the position, which is exactly the *"score that looks measured and is
not"* of `spec.md` § 2.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

__all__ = ["GovernedName", "PriorityContractViolation", "PriorityModel"]

#: Lower snake case, non-empty, bounded. The same shape the five packages before
#: this one use for an identifier that must be quotable in a governed output.
GovernedName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strip_whitespace=True),
]


class PriorityContractViolation(ValueError):  # noqa: N818 - a governed refusal, not an error
    """Raised when a contract in this package refuses a construction.

    A distinct type so a caller can tell *"this feature refused"* from *"pydantic
    could not parse"*, which are different problems with different fixes.
    """


class PriorityModel(BaseModel):
    """Frozen, extra-forbidding base for every emitted contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
