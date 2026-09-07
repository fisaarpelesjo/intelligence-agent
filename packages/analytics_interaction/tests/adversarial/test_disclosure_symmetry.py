"""Inaccessible and nonexistent are indistinguishable — T151 (FR-019, FR-050; SC-023).

    A concept the caller may not see and a concept that does not exist MUST
    produce byte-identical responses. — `FR-050`

    Evidence: unauthorized and not-governed responses byte-identical.
    — `tasks.md` T151

## The attack this closes

Ask about a metric you may not see. If the refusal differs in *any* observable
way from the refusal for a metric that does not exist, the pair of refusals is an
oracle: iterate over guessed names and the ones that come back "differently" are
the ones that exist. The caller has then enumerated the governed vocabulary
without ever being authorised to read any of it — and each individual response
was a correct refusal.

So the assertion is **equality of the whole observable response**, not equality of
the reason code. A matching code with a differing message, a differing exception
type, a differing number of candidates, or a differing audit event is the same
leak arriving somewhere else.

## Why this is structural rather than checked

`001` filters by access *before* deciding the outcome shape. A metric the caller
may not see is not "a `Resolved` that then gets denied" — it never becomes a
`Resolved` at all, so the two cases converge upstream of this feature and there is
nothing here to keep in sync. This file asserts that the convergence holds through
every surface a caller can observe, and that no code path re-introduces a
distinction downstream.

## The matrix

Six observable surfaces x the two conditions. A test per surface rather than one
big comparison, because each fails differently and a single assertion would report
the first difference and hide the rest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from semantic_catalog.search.outcomes import NotGoverned, Resolved
from semantic_catalog.search.resolve import Candidate
from semantic_catalog.search.resolve import MatchKind as CatalogMatchKind

from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intent import SlotKind, TermRef
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.interpretation.resolve_terms import (
    SlotOutcome,
    TermRequest,
    candidate_refs,
    discover,
    ordered_candidates,
    resolve_term,
)

from ..conftest import ON, authorize

pytestmark = pytest.mark.adversarial

#: The name of a governed metric the caller is **not** authorised to see, and the
#: name of one that does not exist. Both must be answered identically.
#:
#: Deliberately the same length and shape, so a length-based side channel in a
#: message or an identifier would show up as a difference rather than being
#: masked by the names themselves differing in size.
INACCESSIBLE = "revenue_secret"
NONEXISTENT = "revenue_absent"

#: Every slot the symmetry must hold in. A metric-only assertion would leave five
#: doors open, and the dimension door is the one a caller reaches most easily.
SLOTS: tuple[SlotKind, ...] = tuple(SlotKind)


@dataclass(frozen=True, slots=True)
class _AccessFiltered:
    """`001`'s surface, filtering by access **before** choosing the shape.

    This is the real upstream behaviour modelled at its narrowest: ``visible``
    holds what this caller may see, and everything else — governed but hidden,
    or simply absent — returns ``NotGoverned``. Building the two conditions from
    one code path is the point: a fixture with a separate "denied" branch could
    make them differ and this file would be asserting its own fixture.
    """

    visible: frozenset[str]

    def resolve(self, query: str, *, access: object) -> SlotOutcome:
        if query in self.visible:
            return Resolved(
                query=query,
                candidate=Candidate(
                    metric_id=query,
                    kind=CatalogMatchKind.CANONICAL_NAME,
                    score=1.0,
                    matched_term=query,
                ),
            )
        return NotGoverned(query=query)


CATALOG = _AccessFiltered(visible=frozenset({"installs"}))

CONDITIONS = (("inaccessible", INACCESSIBLE), ("nonexistent", NONEXISTENT))


def _refusal(surface: str, slot: SlotKind = SlotKind.METRIC) -> ContractViolation:
    with pytest.raises(ContractViolation) as raised:
        resolve_term(
            TermRequest(term=TermRef(start=0, length=len(surface)), slot=slot),
            surface,
            catalog=CATALOG,
            authorized=authorize(),
            on=ON,
        )
    return raised.value


# --- the fixture models the real thing -------------------------------------------


def test_the_two_names_are_shaped_alike() -> None:
    """Otherwise a length difference in a message would read as symmetry.

    Same length, same prefix, same character classes. The only difference is the
    suffix, and nothing observable may depend on it.
    """
    assert len(INACCESSIBLE) == len(NONEXISTENT)
    assert INACCESSIBLE != NONEXISTENT
    assert INACCESSIBLE.split("_")[0] == NONEXISTENT.split("_")[0]


def test_the_visible_metric_resolves() -> None:
    """The control. Without it, symmetric refusals could mean nothing resolves."""
    resolution = resolve_term(
        TermRequest(term=TermRef(start=0, length=8), slot=SlotKind.METRIC),
        "installs",
        catalog=CATALOG,
        authorized=authorize(),
        on=ON,
    )
    assert resolution.resolved_to == "installs"


# --- surface 1: the outcome shape ------------------------------------------------


def test_the_discovery_outcome_is_the_same_shape() -> None:
    """Both converge on ``NotGoverned`` upstream, so nothing here has to match them."""
    hidden = discover(INACCESSIBLE, catalog=CATALOG, authorized=authorize(), on=ON)
    absent = discover(NONEXISTENT, catalog=CATALOG, authorized=authorize(), on=ON)
    assert type(hidden) is type(absent) is NotGoverned


# --- surface 2: the exception type and code -------------------------------------


@pytest.mark.parametrize("slot", SLOTS, ids=[slot.value for slot in SLOTS])
def test_the_reason_code_is_identical_in_every_slot(slot: SlotKind) -> None:
    """One code, every slot. A slot-specific code would be a per-slot oracle."""
    hidden = _refusal(INACCESSIBLE, slot)
    absent = _refusal(NONEXISTENT, slot)
    assert hidden.code is absent.code is Code.TERM_NOT_GOVERNED
    assert type(hidden) is type(absent)


# --- surface 3: the message, byte for byte -------------------------------------


@pytest.mark.parametrize("slot", SLOTS, ids=[slot.value for slot in SLOTS])
def test_the_message_is_byte_identical(slot: SlotKind) -> None:
    """**The load-bearing assertion.**

    Byte equality, not "both mention not-governed". A message that interpolated
    the term would differ here — and would also echo untrusted text, which is a
    second violation arriving through the same line of code.
    """
    hidden = str(_refusal(INACCESSIBLE, slot))
    absent = str(_refusal(NONEXISTENT, slot))
    assert hidden == absent
    assert hidden.encode() == absent.encode()


@pytest.mark.parametrize("slot", SLOTS, ids=[slot.value for slot in SLOTS])
def test_neither_message_names_the_term(slot: SlotKind) -> None:
    """The symmetry would hold trivially if both echoed their own term.

    Both messages naming their own input would be byte-*different*, so the test
    above already catches it. This states the stronger property directly: neither
    message contains either name, so no future edit can satisfy symmetry by
    echoing both.
    """
    for message in (str(_refusal(INACCESSIBLE, slot)), str(_refusal(NONEXISTENT, slot))):
        assert INACCESSIBLE not in message
        assert NONEXISTENT not in message
        assert "revenue" not in message


# --- surface 4: candidate counts and ordering ----------------------------------


def test_neither_condition_exposes_a_candidate_count() -> None:
    """A count is an oracle even when no identifier is disclosed.

    "Zero candidates" versus "one candidate you may not see" enumerates the
    catalog just as well as a name would. Both produce an empty tuple, from the
    same code path.
    """
    for _, surface in CONDITIONS:
        outcome = discover(surface, catalog=CATALOG, authorized=authorize(), on=ON)
        assert ordered_candidates(getattr(outcome, "candidates", ())) == ()
        assert (
            candidate_refs(
                outcome,
                slot=SlotKind.METRIC,
                content_version="fixture-only-not-governed-wording-v1",
                language="pt-BR",
            )
            == ()
        )


# --- surface 5: timing-independent structural equality of the whole response ----


@pytest.mark.parametrize("slot", SLOTS, ids=[slot.value for slot in SLOTS])
def test_the_whole_observable_response_is_equal(slot: SlotKind) -> None:
    """Everything a caller can see, compared as one canonical object.

    Serialised and compared as JSON rather than field by field, so a field added
    later is included automatically. A per-field comparison is a list somebody has
    to remember to extend, and the field they forget is the channel.
    """

    def observable(surface: str) -> str:
        violation = _refusal(surface, slot)
        return json.dumps(
            {
                "type": type(violation).__name__,
                "code": violation.code.value,
                "message": str(violation),
                "args": [str(arg) for arg in violation.args],
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    assert observable(INACCESSIBLE) == observable(NONEXISTENT)


# --- surface 6: the symmetry survives repetition and ordering -------------------


def test_the_symmetry_does_not_depend_on_which_is_asked_first() -> None:
    """A cache or an accumulated state would break this and nothing else.

    Asked in both orders, twice each. An implementation that remembered the first
    refusal and answered the second from it would still pass every assertion
    above.
    """
    first = [str(_refusal(name)) for name in (INACCESSIBLE, NONEXISTENT, INACCESSIBLE)]
    second = [str(_refusal(name)) for name in (NONEXISTENT, INACCESSIBLE, NONEXISTENT)]
    assert len(set(first + second)) == 1


def test_repeating_one_condition_never_diverges() -> None:
    """Determinism, per condition. A response that drifted would be its own oracle."""
    for _, surface in CONDITIONS:
        assert len({str(_refusal(surface)) for _ in range(5)}) == 1
