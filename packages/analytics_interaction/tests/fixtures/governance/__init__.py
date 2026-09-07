"""Approved-**shaped** governed content — T147. **TEST-ONLY.**

`interpretation_governance/` holds no approved instance: `D-18` ships three empty
documents and `D-19` ships one, so every dependent path refuses. That is the
designed state, and it means a suite with no synthetic content could only ever
assert refusals.

So these are approved-*shaped* — they satisfy the schemas and the effectivity
rules, and they satisfy nothing else. The values are placeholders carrying
:data:`FIXTURE_MARKER`, not proposals for what a week convention, a comparison
formula, an ambiguity threshold or a redaction pattern should be. Those are the
governed decisions `D-18` and `D-19` exist to obtain, and authoring a
plausible-looking one here is exactly the invented governance the dependency
records prevent.

Reached through each resolver's ``instances`` parameter, which exists for tests.
No `src/` module supplies one, and `test_fixture_containment` asserts it.

A fixture is never evidence for an external record.
"""

from __future__ import annotations

__all__ = ["FIXTURE_MARKER"]

#: Stamped into every synthetic governed value, and asserted absent from `src/`.
#:
#: The concrete builders live beside the suites that use them —
#: ``tests/fixtures/comparisons.py`` for the `D-18` formula set,
#: ``tests/fixtures/answers.py`` for the claim-class wording, and
#: ``tests/fixtures/clarifications.py`` for the `D-19` policy. This package
#: names the boundary and the rule; splitting the builders away from their
#: suites would put a second definition of each fixture one directory from the
#: first.
FIXTURE_MARKER = "fixture-only-not-governed"
