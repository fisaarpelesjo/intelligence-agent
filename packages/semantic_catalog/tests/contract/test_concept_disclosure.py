"""Dimension disclosure is gated, and absence denies — ADR 0029.

`Metric.access` is required and every disclosure path gates on it. `Dimension` had no such field, so
a surface answering "does this term name a dimension" would have disclosed governed vocabulary under
no authorisation rule at all. ADR 0029 authorized the field and the gate; this asserts them.

## Re-derived 2026-08-19, and two node names now record an expired premise

This file was written while **no** authored dimension carried a tag, and it said so in its
assertions and in two of its node names. On 2026-08-19 the owner instructed that the six authored
axes carry `standard`, and that the registry definition of `standard` be corrected to state the
class it actually governs — product metrics **and** semantic dimensions, explicitly not an
individual identifier.

That expired the premise, exactly as `test_every_authored_dimension_carries_no_access_tag_today`
predicted it would, and its own failure message said what to do: *re-derive* the assertions rather
than edit them. So the assertions below assert the property each node was really protecting, over
the catalog that now ships.

**The node names are kept unchanged on purpose**, on the same instruction: preserve the existing
node IDs. Two of them — `..._carries_no_access_tag_today` and `..._reports_no_dimension_today` —
therefore read as the opposite of what they now assert. Each carries the correction at the top of
its own docstring rather than relying on a reader finding this paragraph. The residue is recorded
for the reviewer instead of being resolved by a rename, because a rename is a removal to the
node-ID gate and a name is not worth spending that.

Seven properties:

* **the authored access state is exactly the intended one.** The six axes carry `standard` and
  nothing else does. This is the sentinel: any drift in what is tagged, or in which tag, fails here
  and must be re-derived rather than absorbed.
* **every authored tag is one the registry admits.** Authoring values created a failure mode that
  did not exist while the field was empty everywhere: a typo in the YAML denies silently, and a
  dimension that quietly stops being disclosable looks identical to one that was never governed.
* **the registry definition covers dimensions.** The tag application is legitimate only because the
  governed definition was corrected first. Reverting the description while leaving the six tagged
  re-creates the silent widening the owner forbade, so the description is asserted, not assumed.
* **a tag authorises, and only the right one.** Clearing the tag denies, restoring it discloses, and
  a principal the registry does not admit stays denied. The transition is asserted in both
  directions so "gated" cannot be satisfied by a surface that simply always answers.
* **an unregistered tag denies.** That is the case a typo produces, and treating an unknown tag as
  permissive is how a typo becomes a disclosure.
* **a denial is indistinguishable from a non-match.** All three denial shapes — no tag, an unknown
  tag, an unadmitted scope — return exactly what a word absent from the catalog returns. Otherwise a
  caller enumerates the catalog by watching which terms refuse.
* **metrics answer exactly as `get_metric` answers.** The concept surface re-derives the three
  visibility conditions rather than calling a private helper — ADR 0028 required additive-only —
  so the two answers are asserted equal rather than assumed equal.

## What tagging the axes did not do

Nothing here claims a dimension slot is reachable end to end. `004`'s step 6 screens every candidate
span through `001`'s **metric** resolver before it consults the concept surface, and no authored
dimension term resolves as a metric, so the composed entry point still reports no dimension slot.
That is `004`'s measurement to make and its task to close; this file asserts the catalog surface and
stops there.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.loader.load import load_catalog
from semantic_catalog.search.api import AccessContext, CatalogApi, authorize
from semantic_catalog.search.concepts import ConceptKind, build_concept_index, identify
from semantic_catalog.search.outcomes import NotGoverned

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
SEMANTIC = REPO / "semantic"

_ON = date(2026, 8, 18)
#: Any commit id works here: no assertion below depends on an approval, and the registry consulted
#: for dimension access is the access-tag registry rather than the approval one.
_ANY_COMMIT = "0000000"

#: The authored access state this file was re-derived against, 2026-08-19 and again 2026-08-26.
#: Written out rather than read from the catalog, because a sentinel that derives its expectation
#: from the thing it is guarding cannot fail: it would agree with any state the YAML happened to be
#: in.
#:
#: **`game` arrived on 2026-08-26 and this is the re-derivation the node itself demands.** Its own
#: failure message says a seventh axis is a governed decision that must be re-derived here rather
#: than absorbed -- so this is the decision being written down, not the expectation being edited to
#: agree with the YAML. The decision: `game` is authored by OD-3, on the owner's literal words
#: "concordo com sua recomendacao", and it carries `standard` for the reason all six carry it --
#: the tag discloses THE AXIS AS A CONCEPT and publishes no metric, no source and no cell value.
#:
#: **`plan` arrived on 2026-09-05 (spec 013, F5, OD-127: "declarar plano como eixo"), and this is
#: the re-derivation once more.** The axis is authored with an EMPTY `source_applicability` -- the
#: measured truth of `T1322`: no governed source carries a plan column -- and it carries `standard`
#: for the reason the seven carry it: the tag discloses THE AXIS AS A CONCEPT and publishes no
#: metric, no source and no cell value. Disclosing the concept is exactly what a breakdown that
#: refuses BY NAME needs: the name has to be a governed word before the refusal can say it.
#:
#: **`gateway` arrived the same afternoon (spec 013, F6, OD-128), by the same reasoning and the
#: same measurement (remeasured 13:02 -03: no governed source carries a gateway column; the join
#: view of `FR-1315` does not exist yet). Empty `source_applicability`, `standard` for the same
#: reason: the refusal has to be able to say the name.**
#:
#: **And the property is unchanged: the WHOLE mapping is still asserted.** A tenth axis, a removed
#: tag, a different tag or a rename all still fail here. Nothing was widened and nothing was
#: loosened -- one entry was added each time one axis was authored.
EXPECTED_DIMENSION_ACCESS: dict[str, str | None] = {
    "app_version": "standard",
    "country": "standard",
    "date": "standard",
    "game": "standard",
    "gateway": "standard",
    "plan": "standard",
    "platform": "standard",
    "product": "standard",
    "store": "standard",
}

#: The one tag the registry holds, and the class its corrected description must name. `standard`
#: covered *metrics* by its own wording until 2026-08-19; applying it to dimensions was authorized
#: only together with correcting that wording, so the word is asserted rather than trusted.
_TAG = "standard"
_DIMENSION_WORD_IN_TAG_DESCRIPTION = "dimens"


def _access(
    principal_type: PrincipalType = PrincipalType.USER,
    scope: str = "default",
) -> AccessContext:
    return AccessContext(principal_type=principal_type, authorization_scope=scope, on=_ON)


@pytest.fixture(scope="module", name="bundle")
def fixture_bundle() -> Bundle:
    """The **authored** catalog, not a fixture one.

    The authored content is the point: a synthetic catalog could be handed a tagged dimension and
    would then prove nothing about what ships.
    """
    return build_bundle(
        SEMANTIC,
        current_commit=_ANY_COMMIT,
        on=_ON,
        source_commits={"subscription_daily": _ANY_COMMIT},
    )


def _with_dimension_access(bundle: Bundle, identifier: str, tag: str | None) -> Bundle:
    """The same catalog with one dimension's access tag replaced, in memory only.

    Rebuilt through `build_bundle` so the projection and the release id are derived the way
    production derives them. The authored YAML on disk is untouched: this changes a value for one
    test, it does not author one.
    """
    dimensions = dict(bundle.internal.dimensions)
    dimensions[identifier] = dimensions[identifier].model_copy(update={"access": tag})
    return build_bundle(
        replace(bundle.internal, dimensions=dimensions),
        current_commit=_ANY_COMMIT,
        on=_ON,
        source_commits={"subscription_daily": _ANY_COMMIT},
    )


def test_every_authored_dimension_carries_no_access_tag_today() -> None:
    """**The name records the premise that expired on 2026-08-19.** It now asserts the opposite.

    Until then no authored dimension carried a tag, and this node was the sentinel that would notice
    if one ever did. It did notice; the owner authored `standard` on all six axes, and its own
    failure message required the assertions to be *re-derived*. This is that re-derivation, and it
    is still the sentinel — the direction of what it guards changed, not its job.

    The property it was really protecting is that **the authored access state of every dimension is
    the one the repository intends**, never an accident of the data and never a default. So the
    whole mapping is asserted, not just its emptiness: a seventh dimension, a removed tag, a
    different tag or a renamed axis all fail here and have to be decided rather than absorbed.

    The node ID is preserved on the owner's instruction. See this module's docstring.
    """
    catalog = load_catalog(SEMANTIC)
    assert catalog.dimensions, "no dimension is authored, so this file proves nothing"

    authored = {
        identifier: dimension.access for identifier, dimension in sorted(catalog.dimensions.items())
    }
    assert authored == EXPECTED_DIMENSION_ACCESS, (
        f"the authored dimension access state is {authored}, and this file was re-derived against "
        f"{EXPECTED_DIMENSION_ACCESS}. Whatever changed is a governed decision: re-derive the "
        "assertions below against the new state rather than editing this expectation to match"
    )


def test_every_authored_dimension_tag_is_one_the_registry_admits(bundle: Bundle) -> None:
    """Added 2026-08-19: authoring values created a failure mode that empty fields could not have.

    While every dimension was untagged, a wrong tag was unreachable. Now a typo in the YAML is a
    denial — `authorize` refuses an identifier the registry does not hold — and a dimension that
    silently stops being disclosable is indistinguishable from one that was never governed. That is
    the correct **security** behaviour and a terrible **authoring** outcome, so the typo is caught
    here instead of being discovered as a missing answer.

    Two failures, kept separate: a tag the registry does not hold at all, and a tag it holds but
    which does not admit the ordinary principal these axes were tagged for.
    """
    registry = bundle.internal.access_tags
    assert registry is not None, "no access-tag registry is loaded, so every tag would deny"
    known = {tag.id for tag in registry.tags}

    for identifier, dimension in sorted(bundle.internal.dimensions.items()):
        tag = dimension.access
        if tag is None:
            continue
        assert tag in known, (
            f"dimension {identifier} carries {tag!r}, which the registry does not hold "
            f"({sorted(known)}). It denies silently, so this is an authoring error and not a policy"
        )
        assert authorize(tag, registry, _access()) is None, (
            f"dimension {identifier} carries {tag!r}, which the registry holds but does not admit "
            "for an ordinary authorized user"
        )


def test_the_registry_definition_of_standard_covers_dimensions(bundle: Bundle) -> None:
    """Added 2026-08-19: the authored tags are legitimate only because the definition says so.

    `contracts/dimension.py` used to give a specific reason a dimension could not reuse this tag —
    the registry described it as covering *metrics* — and reusing it anyway would have widened a
    governed class by editorial decision. The owner's instruction closed that by correcting the
    definition **first**, and the six tags rest on the corrected wording.

    So the wording is asserted. Reverting the description to a metric-only sentence while leaving
    six dimensions tagged would re-create precisely the silent widening that was forbidden, and
    prose is the one part of this change that no other assertion would notice.

    Asserted on a stem rather than a full sentence: the check is that the class is **named**, not
    that a particular phrasing survives. A governed description is editable pt-BR content, and
    pinning it exactly would make every wording improvement a test failure.
    """
    registry = bundle.internal.access_tags
    assert registry is not None, "no access-tag registry is loaded"
    tags = {tag.id: tag for tag in registry.tags}
    assert _TAG in tags, f"{_TAG!r} is not in the registry ({sorted(tags)})"

    description = tags[_TAG].content.description.casefold()
    assert _DIMENSION_WORD_IN_TAG_DESCRIPTION in description, (
        f"{_TAG!r} is authored on {sorted(EXPECTED_DIMENSION_ACCESS)} but its governed description "
        f"does not name dimensions: {tags[_TAG].content.description!r}. Either the description is "
        "corrected or the tags are removed; a metric-only description with tagged dimensions is "
        "the silent widening ADR 0029 refused"
    )
    assert "métric" in description, (
        f"{_TAG!r}'s description no longer names metrics: {tags[_TAG].content.description!r}. The "
        "correction was meant to add a class, not to drop the one every authored metric carries"
    )


def test_the_concept_surface_reports_no_dimension_today(bundle: Bundle) -> None:
    """**The name records the premise that expired on 2026-08-19.** It now asserts both directions.

    It used to assert that no dimension came back at all, which was deny-by-default over data where
    nothing was tagged. With the six axes tagged, the property that survives is the one that was
    actually load-bearing: **the surface reports a dimension exactly when the registry authorises
    it, and never otherwise.**

    Both halves run over every authored dimension's own terms — canonical id, label and every
    synonym, the three routes the index carries — because a gate that held for the id and leaked
    through a synonym would be a gate in name only.

    The node ID is preserved on the owner's instruction. See this module's docstring.
    """
    index = build_concept_index(bundle.internal)
    admitted = _access()
    #: A scope the registry does not admit. The tag exists, the dimension exists, and the answer
    #: must still be nothing — the half this node protected before anything was tagged.
    unadmitted = _access(scope="scope-the-registry-does-not-admit")

    for identifier, dimension in sorted(bundle.internal.dimensions.items()):
        terms = [identifier, dimension.content.label, *(s.text for s in dimension.synonyms)]
        for term in terms:
            disclosed = [
                match.concept_id
                for match in identify(term, index, bundle=bundle, access=admitted)
                if match.kind is ConceptKind.DIMENSION
            ]
            assert identifier in disclosed, (
                f"{term!r} does not disclose dimension {identifier} to an admitted principal, "
                f"though it carries {dimension.access!r}; the route reported {disclosed}"
            )

            denied = [
                match
                for match in identify(term, index, bundle=bundle, access=unadmitted)
                if match.kind is ConceptKind.DIMENSION
            ]
            assert not denied, (
                f"{term!r} disclosed dimension {identifier} to a scope the registry does not admit"
            )


def test_a_tagged_dimension_becomes_disclosable(bundle: Bundle) -> None:
    """The gate opens for a registered tag, which is what makes the denial meaningful.

    Without this the previous test would pass over a surface that simply never reports a dimension,
    and "gated" would be indistinguishable from "not implemented".

    **Re-derived 2026-08-19 to stay a transition rather than a state.** `platform` now carries
    `standard` on disk, so setting the tag and observing disclosure would have observed the shipped
    catalog and proved nothing about the tag causing it. The tag is therefore **cleared first** and
    the denial asserted, then restored and the disclosure asserted — the same two points as before,
    with the causal direction still measured.
    """
    identifier = "platform"

    cleared = _with_dimension_access(bundle, identifier, None)
    cleared_index = build_concept_index(cleared.internal)
    assert not [
        match
        for match in identify(identifier, cleared_index, bundle=cleared, access=_access())
        if match.kind is ConceptKind.DIMENSION
    ], f"{identifier} is disclosed with its tag cleared, so the tag is not what opens the gate"

    tagged = _with_dimension_access(bundle, identifier, _TAG)
    index = build_concept_index(tagged.internal)

    dimensions = [
        match
        for match in identify(identifier, index, bundle=tagged, access=_access())
        if match.kind is ConceptKind.DIMENSION
    ]
    assert dimensions, f"{identifier} is tagged and still not disclosed"
    assert all(match.concept_id == identifier for match in dimensions)


def test_a_tagged_dimension_stays_denied_to_an_unadmitted_principal(bundle: Bundle) -> None:
    """A tag is not a blanket permission: the registry decides per principal and per scope."""
    tagged = _with_dimension_access(bundle, "platform", "standard")
    index = build_concept_index(tagged.internal)
    denied = identify(
        "platform",
        index,
        bundle=tagged,
        access=_access(scope="scope-the-registry-does-not-admit"),
    )
    assert not [match for match in denied if match.kind is ConceptKind.DIMENSION]


def test_a_tag_the_registry_does_not_know_denies(bundle: Bundle) -> None:
    """An unregistered tag is not a permission either, which is what makes a typo safe."""
    tagged = _with_dimension_access(bundle, "platform", "tag_that_is_not_registered")
    index = build_concept_index(tagged.internal)
    assert not [
        match
        for match in identify("platform", index, bundle=tagged, access=_access())
        if match.kind is ConceptKind.DIMENSION
    ]


def test_a_denial_is_indistinguishable_from_a_non_match(bundle: Bundle) -> None:
    """Both return an empty tuple, so a refusal discloses nothing about what exists.

    **Re-derived 2026-08-19.** The denial used to be free: `platform` was untagged, so asking for it
    was already a refusal. It is tagged now, so each denial shape has to be produced deliberately —
    and producing all three is stronger than the single one this node used to compare, because the
    oracle it closes does not care *why* the surface refused.
    """
    absent_term = "palavra-que-nao-existe-no-catalogo"

    shapes = {
        "no tag authored": _with_dimension_access(bundle, "platform", None),
        "a tag the registry does not know": _with_dimension_access(
            bundle, "platform", "nao_existe"
        ),
    }
    for reason, catalog in shapes.items():
        index = build_concept_index(catalog.internal)
        denied = identify("platform", index, bundle=catalog, access=_access())
        absent = identify(absent_term, index, bundle=catalog, access=_access())
        assert denied == absent == (), f"{reason}: {denied!r} is distinguishable from {absent!r}"

    #: The third shape needs no altered catalog: the dimension and its tag both exist, and the scope
    #: is what the registry refuses. This is the shape a real caller produces.
    index = build_concept_index(bundle.internal)
    unadmitted = _access(scope="scope-the-registry-does-not-admit")
    denied = identify("platform", index, bundle=bundle, access=unadmitted)
    absent = identify(absent_term, index, bundle=bundle, access=unadmitted)
    assert denied == absent == (), f"an unadmitted scope: {denied!r} differs from {absent!r}"


def test_metric_answers_agree_with_get_metric(bundle: Bundle) -> None:
    """The concept surface re-derives metric visibility, so its answer must equal the existing one.

    ADR 0028 permitted a new module and no edit to an existing one, which means the three visibility
    conditions are written twice. Two copies of a rule drift; this is the assertion that notices.
    """
    api = CatalogApi.from_bundle(bundle)
    index = build_concept_index(bundle.internal)
    access = _access()

    for name in sorted(bundle.internal.metrics):
        through_api = api.get_metric(name, access=access)
        through_concepts = [
            match
            for match in identify(name, index, bundle=bundle, access=access)
            if match.kind is ConceptKind.METRIC
        ]
        assert bool(through_concepts) is not isinstance(through_api, NotGoverned), (
            f"{name}: get_metric and identify disagree about visibility"
        )


def test_at_least_one_metric_is_disclosed_so_the_agreement_is_not_vacuous(
    bundle: Bundle,
) -> None:
    """Anti-vacuity for the agreement above.

    If every metric were denied, `get_metric` and `identify` would agree by both saying nothing, and
    the comparison would prove that neither works.
    """
    index = build_concept_index(bundle.internal)
    disclosed = [
        name
        for name in bundle.internal.metrics
        if identify(name, index, bundle=bundle, access=_access())
    ]
    assert disclosed, "no metric is disclosed at all, so the agreement test is vacuous"


def test_identification_is_deterministic(bundle: Bundle) -> None:
    """Two runs over one catalog produce identical answers, including order."""
    first = build_concept_index(bundle.internal)
    second = build_concept_index(bundle.internal)
    assert first.terms.keys() == second.terms.keys()
    for term in sorted(first.terms):
        assert first.exact(term) == second.exact(term)


def test_the_concept_kinds_are_the_two_that_are_authored() -> None:
    """No `PERIOD` member, because no authored period vocabulary exists to populate one.

    ADR 0029 records that gap and does not authorize closing it. An enum member for a kind the
    catalog cannot answer for would be a promise a caller would reasonably rely on.
    """
    assert {kind.value for kind in ConceptKind} == {"metric", "dimension"}
