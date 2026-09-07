"""Shared contract base — T709's precondition.

Mirrors `006`'s ``contracts/_base.py``, which mirrors `005`'s, in the two things
that matter: models are **frozen and forbid extra fields**, and a governed name is a
constrained string rather than a free one.

**Frozen is not tidiness here.** A report whose fields could be mutated after
construction would let a caller change what is said without changing what was
measured -- and this feature exists to send what was measured to a person who did
not ask, which is the one place that gap is invisible.

**And `extra="forbid"` is load-bearing for the shape the owner chose.** A sixth
field smuggled into a report is a field nobody decided on, and the model refuses it
at construction rather than letting a node catch it later.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

__all__ = ["DistributionContractViolation", "DistributionModel", "GovernedName"]

#: Lower snake case, non-empty, bounded. The same shape the five packages before
#: this one use for an identifier that must be quotable in a governed output.
GovernedName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strip_whitespace=True),
]


class DistributionContractViolation(ValueError):  # noqa: N818 - a governed refusal, not an error
    """Raised when a contract in this package refuses a construction.

    A distinct type so a caller can tell *"this feature refused"* from *"pydantic
    could not parse"*, which are different problems with different fixes.
    """


class DistributionModel(BaseModel):
    """Frozen, extra-forbidding base for every emitted contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
