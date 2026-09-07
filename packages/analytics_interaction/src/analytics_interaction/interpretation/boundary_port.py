"""The port that turns a governed period expression into concrete dates (`R-8`).

Authorized by the owner on 2026-08-20, item B. **No task number**: `T156` through `T165` are the
ten `[BLOCKED-EXTERNAL]` credential tasks and none of them is this, so citing one would be a false
reference to an authorization that does not exist.

**This module computes no dates.** It declares who may, and what the answer has to look like.

## Why a port rather than a function here

A named calendar range — "julho de 2026" — needs a mapping from the name to a pair of dates. Three
places could hold it and only one is defensible.

* **Here, as arithmetic.** Forbidden. `R-8` puts date arithmetic and IANA resolution in `001`, and
  this module's own docstring promises none of its own. A month-length table here would be a second
  calendar in the repository.
* **On the `D-18` entry, as absolute start and end fields.** Rejected by the owner as a general
  solution, and rightly: every named range in every year would become authored content, and a typo
  in it would be indistinguishable from a governed decision.
* **Behind a port the deployment supplies.** What this is. The deployment knows which calendar its
  business runs on, states it once, and this feature checks the answer against `D-18` and `001`
  instead of trusting it.

## What the port receives, and why each of the four is there

``expression`` is the `D-18` entry already located in the question, so the resolver never sees
user text and cannot be steered by it. ``reference_date`` is what a relative rule would resolve
against. ``timezone`` is handed **in** rather than read by the resolver, so the business zone has
exactly one source. ``convention`` is the governed rule set restated as a type, so a resolver can
branch on the rule without reaching back into the vocabulary.

## What this feature checks about the answer

Three things, at the call site in `period.py`, and each one exists because a resolver is deployment
code that this feature does not own:

1. the zone must be `001`'s canonical zone — any other value refuses;
2. the inclusivity must be the one the `D-18` entry declares — a resolver may not restate it;
3. the interval must order, which `GovernedInterval` refuses on construction and `001` refuses
   again in ``canonical_period``.

A rule the resolver does not know is the resolver's refusal to raise, not this module's to guess:
``PERIOD_CONVENTION_UNDECLARED`` is the code for it, and it is the same code this feature already
raises when `D-18` declares a rule without its convention.

**No implementation ships in this package**, for the reason `RedactionMatcher` ships none: a
calendar mapping here would be this feature deciding a reporting standard. It arrives from the
deployment beside the `D-18` content it resolves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from ..contracts.intent import GovernedInterval, PeriodConvention
    from ..governance.schemas import PeriodExpression

__all__ = ["PeriodBoundaryResolverPort"]


@runtime_checkable
class PeriodBoundaryResolverPort(Protocol):
    """Resolve one governed period expression to one concrete interval.

    One method, four inputs, one typed output. It cannot be asked for a range it was not given an
    expression for, cannot be handed the question text, and cannot be told which zone to answer in,
    because none of those is a parameter it controls.

    No annotation here is ``Any`` or ``object``. A permissive annotation on the one call that
    decides which days an answer covers would make the port a hole with a docstring.
    """

    def __call__(
        self,
        *,
        expression: PeriodExpression,
        reference_date: date,
        timezone: str,
        convention: PeriodConvention,
    ) -> GovernedInterval:
        """The interval the governed rule produces, or a refusal.

        Refuse ``PERIOD_CONVENTION_UNDECLARED`` for a ``boundary_rule`` this resolver has no
        calendar for. Returning a plausible interval for an unrecognised rule is the one failure
        this port exists to prevent: it would make an unsupported convention look supported, and
        every number under it would be attributed to a rule nobody implemented.
        """
        ...
