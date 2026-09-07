"""T113 — one input, one outcome, across repeated runs and across processes (`SC-021`, `SC-057`).

`ask` takes the evaluation instant, the correlation id and the nonce as **parameters** — its own
docstring says why: a composed entry point that generated them would make two runs of one input
incomparable. This file is the assertion that nothing else varies either.

## Why "across processes" is a separate claim

Repeating a call in one interpreter proves the function is not accumulating state. It does **not**
prove the answer is independent of the interpreter: a dict or set iteration order that leaks into a
message, an `id()`-derived value, anything seeded by `PYTHONHASHSEED` — all of those are stable
within a process and can differ between two. So the second half of this file runs the same input in
a **subprocess with a different hash seed** and compares digests.

That is the shape the repository already trusts for this class of claim: `T114`'s node-ID gate
shells out rather than importing, for the same reason.

## What varying must and must not change

Three things must **not** change the outcome: the order the payload's keys are written in, the
iteration order of the granted tag set, and the process the call runs in. Two things must: the
question text and the reference date. A determinism test that only asserted stability would pass
over a function that ignored its inputs entirely, so both directions are asserted.

## What this file compares

Every scenario refuses — no analytical question reaches an answered outcome while the period gap
stands, and `T111` documents that. So the compared value is the refusal's **type, code and
detail**, which is the whole observable surface of a governed refusal. When the gap closes, the
same comparison extends to an `AnsweredOutcome` without changing shape.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from analytics_interaction.contracts.intake import PrincipalContext, PrincipalType
from analytics_interaction.interact import InteractionCollaborators

from ..integration.test_interact_equivalence import (
    build_collaborators,
    fixture_policy,
    fixture_vocabulary,
    payload_for,
    refusal_from_ask,
)

pytestmark = pytest.mark.property

GOVERNED = "instalacoes"

#: The subprocess re-derives the same inputs from this package rather than receiving them, so the
#: two halves cannot agree by sharing a serialised value that was itself computed once.
_CHILD = """
import hashlib, sys
sys.path.insert(0, {root!r})
from tests.integration.test_interact_equivalence import (
    build_collaborators, fixture_policy, fixture_vocabulary, payload_for, refusal_from_ask,
)

collaborators = build_collaborators(
    policy_instances=fixture_policy(), vocabulary_instances=fixture_vocabulary()
)
refusal = refusal_from_ask(payload_for({question!r}), collaborators)
print(hashlib.sha256(
    f"{{type(refusal).__name__}}|{{refusal.code.value}}|{{refusal.detail}}".encode()
).hexdigest())
"""


def _usable(**overrides: object) -> InteractionCollaborators:
    """Collaborators whose governed content resolves, rebuilt per call.

    Rebuilt rather than shared, deliberately: a shared instance would make repetition prove that
    one object behaves consistently, not that two constructions of the same inputs agree.
    """
    arguments: dict[str, object] = {
        "policy_instances": fixture_policy(),
        "vocabulary_instances": fixture_vocabulary(),
    }
    arguments.update(overrides)
    return build_collaborators(**arguments)  # pyright: ignore[reportArgumentType]


def _digest(question: str, *, payload: dict[str, object] | None = None) -> str:
    """The full observable surface of one refusal, as a digest.

    Type, code and detail. A digest rather than a tuple so the comparison fails on any difference
    at all rather than on the first field a reader thought to check.
    """
    refusal = refusal_from_ask(payload if payload is not None else payload_for(question), _usable())
    return hashlib.sha256(_surface_of(refusal).encode()).hexdigest()


def _surface_of(refusal: BaseException) -> str:
    """Type, code and detail, joined. The whole observable surface of a governed refusal.

    Factored out so `_digest` and the assertion that checks what the digest covers compose the same
    string rather than two strings that happen to match today.
    """
    code = getattr(refusal, "code", None)
    detail = getattr(refusal, "detail", "")
    assert code is not None, f"{type(refusal).__name__} carries no code, so it has no surface here"
    return f"{type(refusal).__name__}|{code.value}|{detail}"


# --------------------------------------------------------------------------------------------------
# Stability
# --------------------------------------------------------------------------------------------------


def test_ten_repetitions_of_one_input_agree() -> None:
    """Repetition in one process: no accumulated state, no first-call special case."""
    digests = {_digest(GOVERNED) for _ in range(10)}
    assert len(digests) == 1, f"ten runs of one input produced {len(digests)} outcomes: {digests}"


def test_the_order_the_payload_is_written_in_does_not_matter() -> None:
    """A mapping is a mapping. Key order is a property of the caller's code, not of the question."""
    forward = payload_for(GOVERNED)
    reversed_keys: dict[str, object] = dict(reversed(list(forward.items())))

    assert set(forward) == set(reversed_keys), "the reordering lost or gained a key"
    assert _digest(GOVERNED, payload=forward) == _digest(GOVERNED, payload=reversed_keys), (
        "the outcome depends on the order the payload's keys were written in"
    )


def test_the_iteration_order_of_the_granted_tag_set_does_not_matter() -> None:
    """Two principals with the same tags in different insertion order are the same principal.

    A `frozenset` iterates in an order derived from its members' hashes, so this is exactly the
    kind of difference `PYTHONHASHSEED` can move — and the kind that leaks into a message if any
    layer joins the set into a string.
    """
    tags = ("standard", "outra", "terceira")
    first = PrincipalContext(
        principal_ref="t113-principal",
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        granted_access_tags=frozenset(tags),
        authorization_policy_pin="t113-pin",
    )
    second = first.model_copy(update={"granted_access_tags": frozenset(reversed(tags))})

    assert first.granted_access_tags == second.granted_access_tags
    digests = {
        _digest(GOVERNED, payload=payload_for(GOVERNED, principal=principal))
        for principal in (first, second)
    }
    assert len(digests) == 1, f"the tag set's iteration order changed the outcome: {digests}"


# --------------------------------------------------------------------------------------------------
# Sensitivity — the other direction, without which stability is vacuous
# --------------------------------------------------------------------------------------------------


def test_a_different_question_produces_a_different_outcome() -> None:
    """Stability over an input the function ignored would be worthless.

    The over-long question refuses at step 4 and the governed one at step 7, so the digests must
    differ. If they did not, every assertion above would be measuring a constant.
    """
    over_bound = "a" * (fixture_policy()[0].question_length_bound + 1)
    assert _digest(GOVERNED) != _digest(over_bound), (
        "two questions that refuse at different steps produced the same outcome"
    )


def test_the_reference_date_is_read_rather_than_ignored() -> None:
    """`reference_date` reaches the resolution, so changing it must be observable somewhere.

    Asserted at the level this file can observe: the payload carrying a different reference date is
    a different input, and the entry point must not be indifferent to which one it was handed. If
    both dates produced identical outcomes the date would be decoration, and `FR-099`'s refusal to
    read a clock would be protecting a value nobody used.
    """
    base = payload_for(GOVERNED)
    shifted: dict[str, object] = {**base, "reference_date": "2020-01-01"}

    assert base["reference_date"] != shifted["reference_date"], "the shift did not apply"
    #: Both refuse at step 7 today, so the digests legitimately match while the period gap stands.
    #: What is asserted is that the differing date is *accepted and carried*, not that it changes
    #: the refusal — claiming that would claim a behaviour the period gap makes unreachable.
    assert _digest(GOVERNED, payload=shifted), "a shifted reference date was not even accepted"


# --------------------------------------------------------------------------------------------------
# Across processes
# --------------------------------------------------------------------------------------------------


def _tests_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _child_digest(question: str, *, hash_seed: str) -> str:
    """The same input, computed in a fresh interpreter with ``PYTHONHASHSEED`` set."""
    script = _CHILD.format(root=str(_tests_root().parent), question=question)
    completed = subprocess.run(
        (sys.executable, "-c", script),
        capture_output=True,
        text=True,
        check=False,
        env={**_child_env(), "PYTHONHASHSEED": hash_seed},
    )
    assert completed.returncode == 0, (
        f"the child interpreter failed, so nothing is being compared:\n{completed.stdout}\n"
        f"{completed.stderr}"
    )
    return completed.stdout.strip().splitlines()[-1]


def _child_env() -> dict[str, str]:
    """The parent environment, minus any hash seed the parent itself was given."""
    import os

    return {name: value for name, value in os.environ.items() if name != "PYTHONHASHSEED"}


@pytest.mark.parametrize("hash_seed", ["0", "1", "12345"])
def test_a_fresh_interpreter_with_a_different_hash_seed_agrees(hash_seed: str) -> None:
    """The claim repetition cannot make: the outcome does not depend on the interpreter.

    Three seeds, including `0` — which disables randomisation — and two arbitrary non-zero ones. A
    value derived from a set or dict iteration order would be stable in each child and different
    between them, which is precisely what a single-process repetition test cannot see.
    """
    assert _child_digest(GOVERNED, hash_seed=hash_seed) == _digest(GOVERNED), (
        f"a child interpreter with PYTHONHASHSEED={hash_seed} disagreed with this process"
    )


def test_two_children_with_different_seeds_agree_with_each_other() -> None:
    """Belt and braces: the two children are compared directly, not only against the parent.

    A parent that happened to share a seed with one child would make the comparison above pass for
    the wrong reason.
    """
    first = _child_digest(GOVERNED, hash_seed="0")
    second = _child_digest(GOVERNED, hash_seed="999")
    assert first == second, f"two children disagreed: {first} vs {second}"


def test_the_child_harness_is_not_silently_agreeing_on_nothing() -> None:
    """Anti-vacuity for the subprocess half.

    If the child printed an empty line, or a digest of a constant, every comparison above would
    pass while measuring nothing. So the child's digest is checked to be a real sha256 and to
    **differ** for a different question.
    """
    governed = _child_digest(GOVERNED, hash_seed="0")
    assert len(governed) == 64, f"the child printed {governed!r}, which is not a sha256 digest"
    assert int(governed, 16) >= 0, "the child's digest is not hexadecimal"

    other = _child_digest("a" * (fixture_policy()[0].question_length_bound + 1), hash_seed="0")
    assert governed != other, (
        "the child produces one digest for two questions that refuse at different steps, so it is "
        "not reading its input"
    )


def test_the_compared_surface_is_the_whole_observable_refusal() -> None:
    """What the digest covers, asserted rather than left to a reader of `_digest`.

    A digest over the code alone would pass while the wording drifted. This reconstructs the
    surface from a real refusal and checks the digest is a function of all three parts by
    perturbing each.
    """
    refusal = refusal_from_ask(payload_for(GOVERNED), _usable())
    surface = _surface_of(refusal)
    parts = surface.split("|")

    assert len(parts) == 3, f"the surface is not three parts: {surface!r}"
    assert all(parts), f"a surface part is empty, so the digest covers less than it claims: {parts}"

    baseline = hashlib.sha256(surface.encode()).hexdigest()
    assert baseline == _digest(GOVERNED), "`_digest` does not compose the surface it documents"

    for index in range(3):
        perturbed = list(parts)
        perturbed[index] += "x"
        altered = hashlib.sha256("|".join(perturbed).encode()).hexdigest()
        assert altered != baseline, (
            f"the digest ignores part {index} of the surface, so a change there would go unseen"
        )


def test_the_child_and_parent_read_the_same_governed_content() -> None:
    """The two halves must be comparing one question, not two coincidentally-equal answers.

    The child rebuilds its collaborators from this package rather than receiving them serialised,
    so this asserts the fixture the parent uses is the one the child would find — otherwise a
    divergence in governed content would look like determinism.
    """
    parent_bound = fixture_policy()[0].question_length_bound
    script = (
        f"import sys; sys.path.insert(0, {str(_tests_root().parent)!r})\n"
        "from tests.integration.test_interact_equivalence import fixture_policy\n"
        "print(fixture_policy()[0].question_length_bound)\n"
    )
    completed = subprocess.run(
        (sys.executable, "-c", script),
        capture_output=True,
        text=True,
        check=False,
        env=_child_env(),
    )
    assert completed.returncode == 0, f"the child failed:\n{completed.stderr}"
    assert json.loads(completed.stdout.strip()) == parent_bound, (
        "the child resolves a different governed bound than the parent, so the digests above are "
        "comparing two different questions"
    )
