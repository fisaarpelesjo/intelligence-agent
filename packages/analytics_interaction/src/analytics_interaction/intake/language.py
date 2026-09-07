"""Declared language — T052 (FR-100, FR-101, FR-102; SC-058, SC-059).

**The language is declared. It is never detected.**

`FR-100` gives the reason, and it is not squeamishness about accuracy: detection
is probabilistic, and a short question is genuinely ambiguous between languages.
A detector would make *whether a question is answered at all* depend on a
non-deterministic input, colliding with `FR-041`'s reproducibility requirement.
Declaration also matches how `001` treats language everywhere — ``lang: pt-BR``
is explicit on every content block and never inferred.

**The absence is structural, not disciplinary.** ``require_declared_language``
takes the declared value and **nothing else**. There is no parameter through
which the question text could reach it, so no future edit can quietly let the
text influence the decision — the signature would have to change first, and
`T053` scans for exactly that.

**A pt-BR question may be written in English identifiers** (`FR-102`). `001`
makes canonical identifiers English by design while human-facing content is
pt-BR, so a legitimate question routinely mixes both:

    "quantas installs de google_play em julho?"

Refusing that on language grounds would refuse the ordinary case. Since nothing
here reads the text at all, it cannot happen — which is a stronger guarantee than
a rule saying it must not.
"""

from __future__ import annotations

from ..contracts._base import ContractViolation
from ..contracts.intake import DeclaredLanguage
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "SUPPORTED_LANGUAGES",
    "require_declared_language",
    "supported_language_tags",
]

#: The governed supported set, taken from the contract enum rather than restated.
#: Adding a language is adding governed content plus its member there; this
#: module needs no edit, which is what `FR-043` requires and `T026` proves.
SUPPORTED_LANGUAGES: frozenset[DeclaredLanguage] = frozenset(DeclaredLanguage)


def supported_language_tags() -> tuple[str, ...]:
    """The supported tags, sorted, for the ``LANGUAGE_NOT_SUPPORTED`` wording.

    Disclosing the supported set is safe: it is a property of the product, not
    of the principal or the catalog, and a caller who cannot learn it cannot
    correct their request.
    """
    return tuple(sorted(language.value for language in SUPPORTED_LANGUAGES))


def require_declared_language(declared: object) -> DeclaredLanguage:
    """The caller's declared language, or refuse. **Takes no text.**

    **Three input categories map onto the two governed codes**, exactly as
    `contracts/reason-codes.md` §3 declares them:

    | Input | Code |
    |---|---|
    | absent — nothing was declared | ``LANGUAGE_NOT_DECLARED`` |
    | malformed — a number, a blank string, a structure | ``LANGUAGE_NOT_DECLARED`` |
    | unsupported — a well-formed tag outside the governed set | ``LANGUAGE_NOT_SUPPORTED`` |

    Malformed joins absent because **a malformed value is not a declaration**.
    The alternative — routing it to ``LANGUAGE_NOT_SUPPORTED`` — would be worse
    than untidy: that code's stored wording interpolates the declared tag, so a
    malformed value would be echoed back to the caller, and echoing untrusted
    input into a response is the thing `FR-045` exists to prevent.

    ``LANGUAGE_NOT_DECLARED``'s wording therefore interpolates nothing, and this
    function passes no part of the input into either refusal.
    """
    if declared is None:
        raise ContractViolation(
            InterpretationReasonCode.LANGUAGE_NOT_DECLARED,
            "the question declares no language; language is never detected or inferred",
        )

    if isinstance(declared, DeclaredLanguage):
        return declared

    if not isinstance(declared, str) or not declared.strip():
        raise ContractViolation(
            InterpretationReasonCode.LANGUAGE_NOT_DECLARED,
            "the declared language is not a language tag",
        )

    try:
        return DeclaredLanguage(declared)
    except ValueError as exc:
        raise ContractViolation(
            InterpretationReasonCode.LANGUAGE_NOT_SUPPORTED,
            "the declared language is outside the governed supported set",
        ) from exc
