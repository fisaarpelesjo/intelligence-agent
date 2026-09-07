"""Structural intake parsing — T051 (FR-003; SC-002).

**Step 1 of the sixteen-step sequence.** Runs before the authorization-context
preflight, which is exactly what constrains it: at this point the principal is
not yet proven entitled to be told anything, so every refusal here **names no
governed limit** (`intake-contract.md` §6).

That is the whole reason there are two length codes. This module raises
``QUESTION_EXCEEDS_STRUCTURAL_LIMIT``, whose stored wording carries no number and
no interpolation. The governed bound is `D-19` content, applied at step 4 by
`bounds.py`, and only there may it name itself.

**Five structural conditions, five governed codes.** Each is distinguishable
because each tells the caller a different thing about their own request, and none
of them discloses anything about the system:

| Condition | Code |
|---|---|
| Unknown field, wrong type, missing required field | ``INTAKE_MALFORMED`` |
| Empty, or punctuation only | ``QUESTION_EMPTY`` |
| Longer than the structural ceiling | ``QUESTION_EXCEEDS_STRUCTURAL_LIMIT`` |
| Control characters, embedded markup, non-textual content | ``QUESTION_CONTENT_NOT_TEXTUAL`` |
| Declared language absent, malformed or unsupported | `language.py` |

**Nothing here inspects meaning.** No classifier, no heuristic, no vocabulary, no
model — the checks are about *shape*, and shape is decidable without knowing what
the question says. Whether the question is analytical is `analytical.py`, and it
runs on resolved terms rather than on text.

The question text is **untrusted data at every stage**. It is never persisted,
never logged, and never echoed into a refusal.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

from ..contracts._base import ContractViolation
from ..contracts.intake import STRUCTURAL_TEXT_CEILING, QuestionIntake
from ..contracts.reason_codes import InterpretationReasonCode
from .language import require_declared_language

__all__ = [
    "assert_structurally_valid_text",
    "parse_intake",
]

#: An opening tag: ``<`` followed by a name or a closing slash, with a ``>``
#: later on the same run. Deliberately narrow — a bare ``<`` is arithmetic, and
#: "vendas < 100" is a legitimate pt-BR question.
_MARKUP = re.compile(r"<\s*/?\s*[A-Za-z][^<>]*>")

#: An SGML/HTML entity. Markup that survived a naive tag strip somewhere upstream.
_ENTITY = re.compile(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]{1,10});")

#: Characters that are not text. Tab and newline are ordinary formatting in a
#: typed question and are permitted; everything else unprintable is not.
_PERMITTED_WHITESPACE = frozenset("\t\n")


def _refuse(code: InterpretationReasonCode, detail: str) -> ContractViolation:
    """A governed refusal that never carries any part of the question.

    ``detail`` is developer-facing and built from fixed strings only. The
    caller-facing wording comes from the stored registry, selected by ``code``.
    """
    return ContractViolation(code, detail)


def assert_structurally_valid_text(text: object) -> str:
    """The four text conditions, in the order that discloses least.

    Order matters. Type before content, length before character inspection: a
    caller who sent a 40 MB blob should be told it is too long without the
    system first walking every character of it.
    """
    if not isinstance(text, str):
        raise _refuse(
            InterpretationReasonCode.INTAKE_MALFORMED,
            "the question must be text",
        )

    if len(text) > STRUCTURAL_TEXT_CEILING:
        # Names no number. The principal is not yet proven entitled to be told a
        # governed one, and the structural ceiling is not the governed one.
        raise _refuse(
            InterpretationReasonCode.QUESTION_EXCEEDS_STRUCTURAL_LIMIT,
            "the question exceeds the structural ceiling of the intake contract",
        )

    if not any(character.isalnum() for character in text):
        raise _refuse(
            InterpretationReasonCode.QUESTION_EMPTY,
            "the question is empty or punctuation only",
        )

    if any(
        not character.isprintable() and character not in _PERMITTED_WHITESPACE for character in text
    ):
        raise _refuse(
            InterpretationReasonCode.QUESTION_CONTENT_NOT_TEXTUAL,
            "the question carries control characters or non-textual content",
        )

    if _MARKUP.search(text) or _ENTITY.search(text):
        # Refused rather than stripped. Silently normalising untrusted input is
        # how a screening step gets bypassed: the stripped form is not what the
        # caller sent, and the screening that follows would run on something
        # nobody submitted.
        raise _refuse(
            InterpretationReasonCode.QUESTION_CONTENT_NOT_TEXTUAL,
            "the question carries embedded markup",
        )

    return text


def parse_intake(payload: object) -> QuestionIntake:
    """Build a ``QuestionIntake`` from an untrusted payload, or refuse.

    The structural checks run **before** construction so each condition reaches
    its own governed code. Pydantic would collapse all of them into a single
    validation error, and a caller told only "malformed" cannot tell an empty
    question from an over-long one.

    Unknown fields are refused by the contract's ``extra="forbid"`` rather than
    by a denylist here — ``sql``, ``access_tags``, ``max_rows``, ``fixture`` and
    ``channel`` are all refused because the field does not exist.

    No value is defaulted. A missing ``reference_date`` is malformed input, not
    an invitation to read a clock (`FR-099`).
    """
    if not isinstance(payload, Mapping):
        raise _refuse(InterpretationReasonCode.INTAKE_MALFORMED, "the intake must be a mapping")

    untrusted = cast("Mapping[object, object]", payload)
    fields: dict[str, Any] = {str(key): value for key, value in untrusted.items()}

    # Language first: it is required, and it is the one field whose absence must
    # not be reported as a generic malformation (`FR-101`).
    language = require_declared_language(fields.get("language"))

    text = assert_structurally_valid_text(fields.get("text"))

    try:
        # `model_validate` rather than `**fields`: the payload is untrusted, so
        # its keys are not known to be the contract's. Unknown ones are still
        # refused by `extra="forbid"` — which is the point — but spreading them
        # into a typed constructor would claim at the type level that they were
        # the declared fields.
        return QuestionIntake.model_validate({**fields, "text": text, "language": language})
    except ContractViolation:
        raise
    except Exception as exc:
        # Missing `reference_date`, an unparseable date, an unknown field, a
        # principal that is not a `PrincipalContext`. One code, because each is
        # the same fact: the payload does not match the contract.
        raise _refuse(
            InterpretationReasonCode.INTAKE_MALFORMED,
            "the intake does not match the question contract",
        ) from exc
