"""Question intake: typed parse, declared-language validation, the two separate
date inputs, governed bounds and untrusted-text screening. The question is data
at every stage, never an instruction.

Two steps of the sixteen live here, and the split between them is the reason the
module is shaped this way:

* **Step 1** — `parse.py`, `language.py`, `dates.py`. Runs *before* the
  authorization-context preflight, so it discloses nothing: the structural
  ceiling refuses without naming a number, and the language check reads only the
  declared field.
* **Steps 4 and 5** — `bounds.py`, `screening.py`. Run *after* it, so the
  governed bound may name itself and the governed redaction rule may be applied.
  Both take an ``AuthorizedContext`` or a resolved policy, which is what makes
  the ordering a property of the call graph rather than a convention.

`analytical.py` is the `FR-004` refusal. It reads no text — the judgement is
derived from resolved terms, because a text classifier would be a probabilistic
gate on answerability.
"""

from .analytical import assert_analytical, is_analytical
from .bounds import apply_governed_length_bound
from .dates import IntakeDates, intake_dates, period_anchor, version_pin
from .language import (
    SUPPORTED_LANGUAGES,
    require_declared_language,
    supported_language_tags,
)
from .parse import assert_structurally_valid_text, parse_intake
from .screening import RedactionMatcher, screen_question

__all__ = [
    "SUPPORTED_LANGUAGES",
    "IntakeDates",
    "RedactionMatcher",
    "apply_governed_length_bound",
    "assert_analytical",
    "assert_structurally_valid_text",
    "intake_dates",
    "is_analytical",
    "parse_intake",
    "period_anchor",
    "require_declared_language",
    "screen_question",
    "supported_language_tags",
    "version_pin",
]
