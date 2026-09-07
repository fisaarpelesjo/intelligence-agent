"""The `D-19` candidate bound has a gate — review finding V (revision notes § 11).

Step 6 of `003`'s composed entry point screens every contiguous span of a question against `001`'s
discovery surface. The cost was **measured**, not estimated: one catalog read per span, and the span
count for ``n`` tokens is ``n(n+1)/2``.

| Characters | Tokens | Catalog reads |
|---|---|---|
| 71 | 8 | 36 |
| 389 | 40 | 820 |
| 1 649 | 160 | 12 880 |
| 3 409 | 320 | **51 360** |

`D-19` declares ``question_length_bound``, which is a **character** count, and the table shows
that a character bound does not bound the candidate count usefully — fifty thousand reads fit
inside about three thousand characters. So a candidate bound is missing from `D-19`, and no value
for it is invented anywhere in this repository.

## Why this test exists, and why it lives here

Two earlier discoveries of this feature each carry a test that **fails when the governed value
arrives**: the `FR-057` per-principal share, and the deferred schema-drift gate. This one did
not, and review finding V was right that a discovery recorded only in prose dies in prose. The
concrete failure it prevents: somebody declares `D-19` with a length bound and no candidate
bound, the suite stays green, step 4 begins accepting questions, and step 6 runs at the cost the
table measured — with nothing in the repository noticing.

It lives in `004`'s suite rather than `003`'s for two reasons. `004` discovered the gap and
records it in its own revision note, so the gate belongs with the record; and adding a test to
`003` would touch an approved artifact of a merged feature, which needs authorization this
correction does not have.

**It asserts nothing about the shape of the eventual value.** A maximum token count, a maximum
span count and a maximum screening count would all satisfy it. Requiring one particular field
name here would be this feature designing `003`'s governed content, which is exactly what the
whole finding is about.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml

pytestmark = pytest.mark.contract


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


_POLICY = _repository_root() / "interpretation_governance" / "interpretation-policy.yaml"
_REVISION_NOTE = _repository_root() / "docs" / "release" / "multichannel-spec-revision-notes.md"

#: Any field name that would express a bound on how many candidates a question may produce. Broad on
#: purpose: the point is that **some** such bound is declared, not that it is spelled a chosen way.
_CANDIDATE_BOUND_HINTS = (
    "candidate",
    "span",
    "token",
    "surface",
    "screen",
    "ngram",
    "n_gram",
)


def _declared_instances() -> list[Mapping[str, object]]:
    document = cast("Mapping[str, object]", yaml.safe_load(_POLICY.read_text(encoding="utf-8")))
    declared: object = document.get("instances") or []
    if not isinstance(declared, list):
        raise AssertionError("`instances` is not a list")
    entries = cast("list[object]", declared)
    return [cast("Mapping[str, object]", entry) for entry in entries if isinstance(entry, Mapping)]


def test_the_policy_document_exists_and_is_readable() -> None:
    """Without this, every assertion below would pass over an absent file."""
    assert _POLICY.is_file(), f"{_POLICY} is missing"
    document = cast("Mapping[str, object]", yaml.safe_load(_POLICY.read_text(encoding="utf-8")))
    assert document["kind"] == "interpretation_policy"


def test_the_shipped_state_declares_no_instance() -> None:
    """`D-19` undeclared today, which is why step 4 refuses and step 6 is unreachable.

    Asserted so the next assertion's silence is explained: it passes vacuously right now, and
    this is the test that says so out loud.
    """
    assert _declared_instances() == [], (
        "D-19 now declares an instance, so the candidate-bound assertion below is live rather than "
        "vacuous — read its failure message"
    )


def test_any_declared_policy_must_carry_a_candidate_bound() -> None:
    """The gate. Fails the moment `D-19` is declared without bounding the candidate count.

    Vacuous while nothing is declared, and that is the correct shape for a gate on a future
    value: it costs nothing today and fires exactly once, at the moment the omission would
    otherwise ship.
    """
    offenders: list[str] = []
    for instance in _declared_instances():
        fields = {str(name).lower() for name in instance}
        if not any(hint in field for field in fields for hint in _CANDIDATE_BOUND_HINTS):
            version = instance.get("version", "«unversioned»")
            offenders.append(str(version))

    assert not offenders, (
        f"D-19 instance(s) {offenders} declare no candidate bound. `question_length_bound` is a "
        "character count and does not bound candidates: a 3 409-character question produces 51 360 "
        "catalog reads at step 6 (measured; see docs/release/multichannel-spec-revision-notes.md "
        "§ 11). Declare a maximum token, span or candidate-screening count, then update § 11 "
        "and this test."
    )


def test_the_measured_numbers_are_recorded_where_a_reader_will_find_them() -> None:
    """The gate and the record must not drift apart.

    If the revision note stops carrying the measurement, this test's failure message would cite a
    section that no longer explains itself.
    """
    note = _REVISION_NOTE.read_text(encoding="utf-8")
    assert "candidate bound" in note
    assert "51 360" in note, "the measured worst case is no longer recorded in the revision note"
    assert "question_length_bound" in note


def test_no_candidate_bound_is_invented_anywhere_in_this_package() -> None:
    """The other half: recording the gap must not become authoring the value.

    Scanned for an assignment naming a candidate bound in `004`'s own source. `003` owns the
    value, and a local constant would be this feature setting policy — the defect `T101` caught
    once already.
    """
    source_root = _repository_root() / "packages" / "channel_integration" / "src"
    pattern = re.compile(
        r"^\s*[A-Z_]*(?:CANDIDATE|SPAN|TOKEN|NGRAM)[A-Z_]*(?:BOUND|LIMIT|MAX)[A-Z_]*\s*[:=]",
        re.MULTILINE,
    )
    offenders: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(source_root)))
    assert not offenders, offenders
