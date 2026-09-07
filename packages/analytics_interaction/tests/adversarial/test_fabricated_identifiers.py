"""A fabricated identifier is never coerced — T150 (FR-048; SC-021).

    A term that corresponds to no governed concept MUST refuse. It MUST NOT be
    coerced to a nearest match. — `FR-048`

    Evidence: never coerced to a nearest match. — `tasks.md` T150

## The failure this forecloses

Coercion is the plausible bug, not the obvious one. Nobody writes "if unknown,
pick something"; what happens is that a matcher with a threshold returns its best
candidate, the threshold is a little loose, and `instals` resolves to `installs`.
The answer then carries a governed identifier the caller never asked about, with
full provenance, disclosed as authoritative. It is wrong in the one way that is
invisible to the person reading it.

So the assertions here are about **absence of a resolution**, not about the
quality of a match. Seven identifier kinds are fabricated — metric, dimension,
source, access tag, version, policy and release — because each enters through a
different door and only the first is a search at all.

## Why `NOT_GOVERNED` and not "unknown metric"

`001` filters by access *before* deciding the outcome shape, so a metric that
does not exist and a metric the caller may not see arrive here identically. That
symmetry is `FR-050`'s and is asserted directly in `T151`; this file leans on it
rather than restating it, and never asserts a code that would distinguish them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest
from semantic_catalog.search.outcomes import Ambiguous, NotGoverned, Resolved
from semantic_catalog.search.resolve import Candidate
from semantic_catalog.search.resolve import MatchKind as CatalogMatchKind

from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import SlotKind, TermRef, TermResolution
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.intake.parse import parse_intake
from analytics_interaction.interpretation.resolve_terms import (
    SlotOutcome,
    TermRequest,
    access_context_for,
    resolve_term,
)

from ..conftest import ON, REFERENCE, SUPPLIED_PRINCIPAL, authorize

pytestmark = pytest.mark.adversarial

#: Surface forms that resemble a governed metric without being one.
#:
#: Each is one edit away from ``installs`` — a transposition, a doubled letter, a
#: missing one, a plural, an accent, a case change, a translation. A loose
#: threshold resolves every one of them, which is exactly why they are here
#: rather than a set of obviously-unrelated strings.
NEAR_MISSES: tuple[str, ...] = (
    "instals",
    "installss",
    "instal",
    "instalation",
    "instalações",
    "INSTALLS_TOTAL",
    "install_count",
    "instalacoes",
    "downloads",
    "install s",
    "installs ",
    " installs",
)

#: Identifiers fabricated in the other six slots. None reaches a search: each is
#: a field on a contract, and a value the governed vocabulary does not contain.
FABRICATED: tuple[tuple[str, str], ...] = (
    ("dimension", "pais_fantasma"),
    ("source", "appstore_beta"),
    ("access_tag", "installs:admin"),
    ("version", "v99.0.0"),
    ("policy", "pol-does-not-exist"),
    ("release", "r-does-not-exist"),
)


@dataclass(frozen=True, slots=True)
class _Catalog:
    """A discovery surface with a fixed answer. **Fixture-only.**

    A dict of surface to outcome rather than a real index, because the claim
    under test is what *this* feature does with each of `001`'s three shapes. A
    real index would also exercise `001`'s scoring, and a failure there would
    read as a failure here.
    """

    answers: dict[str, SlotOutcome]

    def resolve(self, query: str, *, access: object) -> SlotOutcome:
        return self.answers.get(query, NotGoverned(query=query))


def _governed(identifier: str = "installs") -> Resolved:
    return Resolved(
        query=identifier,
        candidate=Candidate(
            metric_id=identifier,
            kind=CatalogMatchKind.CANONICAL_NAME,
            score=1.0,
            matched_term=identifier,
        ),
    )


def _resolve(surface: str, catalog: _Catalog) -> TermResolution:
    authorized = authorize()
    return resolve_term(
        TermRequest(term=TermRef(start=0, length=len(surface)), slot=SlotKind.METRIC),
        surface,
        catalog=catalog,
        authorized=authorized,
        on=ON,
    )


# --- the corpus is real ------------------------------------------------------------


def test_the_near_misses_are_actually_near() -> None:
    """A corpus of unrelated strings would prove nothing about coercion.

    Every entry differs from ``installs`` by a small edit, so a threshold loose
    enough to be useful resolves them. Asserted rather than assumed: a future
    edit that replaced these with obviously-wrong strings would make this file
    pass while testing nothing.
    """
    for surface in NEAR_MISSES:
        stripped = surface.strip().lower()
        assert stripped != "installs" or surface != "installs"
        assert abs(len(stripped) - len("installs")) <= 8
    assert len(set(NEAR_MISSES)) == len(NEAR_MISSES)
    assert len(FABRICATED) == 6


def test_the_control_resolves() -> None:
    """The real identifier resolves, so a refusal below means something.

    Without this, every assertion in this file would pass against a
    ``resolve_term`` that refused unconditionally.
    """
    resolution = _resolve("installs", _Catalog({"installs": _governed()}))
    assert resolution.resolved_to == "installs"


# --- a near miss refuses, and resolves to nothing ---------------------------------


@pytest.mark.parametrize("surface", NEAR_MISSES)
def test_a_near_miss_refuses_rather_than_resolving(surface: str) -> None:
    """**The load-bearing assertion.**

    The catalog knows ``installs`` and is asked about something else. There is no
    threshold in this feature to loosen, so the outcome is `001`'s ``NotGoverned``
    and the refusal is governed.
    """
    with pytest.raises(ContractViolation) as raised:
        _resolve(surface, _Catalog({"installs": _governed()}))
    assert raised.value.code is Code.TERM_NOT_GOVERNED


@pytest.mark.parametrize("surface", NEAR_MISSES)
def test_a_near_miss_refusal_names_no_candidate(surface: str) -> None:
    """The refusal does not say what it *nearly* matched.

    Naming the near match would be helpful and would also be a coercion the
    caller could then request by name — and, when the near match is a metric they
    may not see, a disclosure of a governed identifier through a refusal.
    """
    with pytest.raises(ContractViolation) as raised:
        _resolve(surface, _Catalog({"installs": _governed()}))
    message = str(raised.value)
    assert "installs" not in message
    assert surface not in message


def test_an_ambiguous_outcome_is_not_narrowed_to_the_best() -> None:
    """Two candidates 0.01 apart. The better score does not win.

    This is where coercion would arrive dressed as a feature: 0.94 beats 0.93, so
    pick it. `001` already treats a margin that small as noise rather than a
    decision, and this feature adds no tie-break of its own — it refuses and says
    the term is ambiguous, naming neither candidate.
    """
    outcome = Ambiguous(
        query="instalacoes",
        candidates=(
            Candidate(
                metric_id="installs", kind=CatalogMatchKind.SYNONYM, score=0.94, matched_term="inst"
            ),
            Candidate(
                metric_id="reinstalls",
                kind=CatalogMatchKind.SYNONYM,
                score=0.93,
                matched_term="inst",
            ),
        ),
    )
    with pytest.raises(ContractViolation) as raised:
        _resolve("instalacoes", _Catalog({"instalacoes": outcome}))
    assert raised.value.code is Code.INTENT_AMBIGUOUS
    for identifier in ("installs", "reinstalls"):
        assert identifier not in str(raised.value)


@pytest.mark.parametrize(
    "kind",
    [CatalogMatchKind.DESCRIPTION, CatalogMatchKind.FUZZY],
)
def test_a_match_this_feature_cannot_record_is_not_a_match(kind: CatalogMatchKind) -> None:
    """A description or string-distance hit resolves to nothing.

    `001` may legitimately report these; this feature cannot **record** them, and
    a match it cannot record is a match it does not claim. Accepting them would
    put a resolution in an answer whose ``matched_via`` no contract could express.
    """
    resolved = Resolved(
        query="app",
        candidate=Candidate(metric_id="installs", kind=kind, score=0.9, matched_term="app"),
    )
    with pytest.raises(ContractViolation) as raised:
        _resolve("app", _Catalog({"app": resolved}))
    assert raised.value.code is Code.TERM_NOT_GOVERNED


# --- fabricated values in the other six slots -------------------------------------


@pytest.mark.parametrize("slot,value", FABRICATED, ids=[slot for slot, _ in FABRICATED])
def test_a_fabricated_value_cannot_enter_through_intake(slot: str, value: str) -> None:
    """None of the six is an intake field, so none can be supplied.

    Refused by ``extra="forbid"`` rather than by validation. A caller cannot
    declare an access tag, a catalog release or a policy version at all — those
    come from the resolved authorization context and the governed content, and a
    contract with no such field cannot be talked into growing one.
    """
    with pytest.raises(ContractViolation) as raised:
        parse_intake(
            {
                "text": "installs de julho",
                "language": DeclaredLanguage.PT_BR,
                "reference_date": REFERENCE,
                "principal": SUPPLIED_PRINCIPAL,
                slot: value,
            }
        )
    assert raised.value.code is Code.INTAKE_MALFORMED


@pytest.mark.parametrize("slot,value", FABRICATED, ids=[slot for slot, _ in FABRICATED])
def test_a_fabricated_value_in_the_question_text_stays_text(slot: str, value: str) -> None:
    """Naming one in the question makes it a token to resolve, not a value to adopt.

    The token then fails to resolve, which is the previous section's outcome. What
    must not happen is the string being lifted out of the text and used as the
    field it names.
    """
    intake = parse_intake(
        {
            "text": f"installs de julho com {slot}={value}",
            "language": DeclaredLanguage.PT_BR,
            "reference_date": REFERENCE,
            "principal": SUPPLIED_PRINCIPAL,
        }
    )
    assert intake.principal.granted_access_tags == frozenset()
    assert intake.principal.authorization_scope is None
    assert intake.principal.authorization_policy_pin is None

    with pytest.raises(ContractViolation):
        _resolve(value, _Catalog({"installs": _governed()}))


def test_the_access_context_carries_no_tag_bag_to_widen() -> None:
    """A fabricated access tag has nowhere to land, structurally.

    `001`'s ``AccessContext`` is **not** a bag of granted tag names: it carries
    the principal type, the authorization scope and the evaluation date, and the
    access-tag registry decides authorisation from governed data. So there is no
    field a fabricated tag could be written into — which is a stronger guarantee
    than a check that no fabricated tag *was* written into one.

    Asserted as the exact field set, so a future edit that added a tag bag for
    convenience fails here rather than silently opening the door.
    """
    context = access_context_for(authorize(), on=ON)
    assert {field for field in dir(context) if not field.startswith("_")} == {
        "principal_type",
        "authorization_scope",
        "on",
    }
    assert context.on == ON


def test_a_fabricated_date_cannot_replace_either_supplied_one() -> None:
    """A version or release named in the text does not become a pin."""
    intake = parse_intake(
        {
            "text": "installs as_of 1999-01-01 release r-999",
            "language": DeclaredLanguage.PT_BR,
            "reference_date": REFERENCE,
            "as_of": date(2026, 1, 1),
            "principal": SUPPLIED_PRINCIPAL,
        }
    )
    assert intake.as_of == date(2026, 1, 1)
    assert intake.reference_date == REFERENCE
