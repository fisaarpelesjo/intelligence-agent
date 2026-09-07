"""Governed untrusted-text screening — T058 (FR-045; SC-022).

**Step 5.** Constitution IV requires untrusted text to be *isolated and redacted*
before it can reach a prompt. The two halves are handled differently, and
`intake-contract.md` §7 states the difference rather than blurring it:

| Half | Status |
|---|---|
| **Isolation** | Implemented structurally. The question crosses to a model
  surface only as a delimited, non-instructional data parameter (`FR-046`) |
| **Redaction** | **Governed, and undeclared.** Nothing in this repository
  states what must be stripped from a business question. That rule is `D-19`
  content, and while `D-19` is unresolvable this step cannot run — so the
  question refuses (spec `C-4`, `RK-4`) |

**This module authors no pattern.** `RedactionRule.patterns` is a tuple of
governed pattern *identifiers*, not regular expressions written here — a regex in
this file would be a privacy rule nobody reviewed. Evaluating an identifier
against text is therefore an injected collaborator, exactly as the identity
system is in `authorization/`:

* no policy → refuse ``INTERPRETATION_POLICY_UNRESOLVABLE``;
* no matcher → refuse the same way. A missing collaborator is never a pass.

**Refusal echoes nothing.** Not the question, not the matched span, not the
pattern that matched — in the response, the logs, the traces or the audit event
(`FR-045`). A refusal quoting the injected content would reproduce the attack in
whatever read the refusal, which is precisely the disclosure the rule prevents.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode
from ..governance.schemas import InterpretationPolicy, RedactionRule

__all__ = [
    "RedactionMatcher",
    "screen_question",
]


@runtime_checkable
class RedactionMatcher(Protocol):
    """Evaluates a governed pattern identifier against untrusted text.

    Narrow on purpose. It answers *whether* a governed pattern matched and
    nothing else — no span, no offset, no matched text. A richer return type
    would be a channel through which the injected content could travel into a
    refusal, a log line or an audit event.

    Supplied by the deployment alongside the `D-19` content it evaluates. This
    package ships none: an implementation here would be this feature deciding
    what a governed pattern means.
    """

    def matches(self, pattern_id: str, text: str) -> bool:
        """Whether ``pattern_id`` matches ``text``. Never returns the match."""
        ...


def screen_question(
    text: str,
    *,
    policy: InterpretationPolicy | None,
    matcher: RedactionMatcher | None,
) -> None:
    """Screen untrusted text under the governed redaction rule, or refuse.

    Both collaborators are required and both may be ``None`` in the signature,
    deliberately: the absent case is a governed outcome this function must
    produce, not a programming error a caller should be trusted to avoid.

    Today `interpretation-policy.yaml` holds no approved instance, so every
    question reaches the first branch and refuses. That is a real capability
    loss, stated rather than engineered around — the alternative is screening
    under a rule nobody approved, which is not screening.
    """
    if policy is None or matcher is None:
        raise ContractViolation(
            InterpretationReasonCode.INTERPRETATION_POLICY_UNRESOLVABLE,
            "the governed redaction rule is unresolvable, so screening cannot run",
        )

    # `rule.on_match` is a governed identifier whose meaning is `D-19` content.
    # A match refuses, which is the only behaviour expressible without authoring
    # that meaning: "redact and continue" would require this feature to decide
    # what redaction produces, and a question altered by an unreviewed rule is
    # not the question the caller asked. Honouring other values is the D-19
    # owner's decision to define, not this module's to guess.
    rule: RedactionRule = policy.redaction_rule
    for pattern_id in rule.patterns:
        if matcher.matches(pattern_id, text):
            # Names neither the pattern nor any part of the question. The caller
            # learns that the request was refused as an instruction, and nothing
            # that would help them iterate on it.
            raise ContractViolation(
                InterpretationReasonCode.INSTRUCTION_INJECTION_REFUSED,
                "the question carries content the governed redaction rule refuses",
            )
