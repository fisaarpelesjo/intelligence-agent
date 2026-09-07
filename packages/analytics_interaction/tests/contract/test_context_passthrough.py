"""The context is carried, never constructed — T050 (FR-029; SC-053).

    The system MUST pass the principal's authorization context through
    unchanged, and MUST NOT create, name, infer, elevate, translate or assemble
    an access tag. — `FR-029`

Six verbs, and each one is a distinct way the property could fail:

* **create** — a tag the resolver never returned appears downstream;
* **name** — a literal tag string is written into this package's source;
* **infer** — a tag is derived from the scope, the principal type or a metric;
* **elevate** — the set grows between the preflight and the boundary;
* **translate** — a tag is renamed, cased, prefixed or normalised;
* **assemble** — the set is rebuilt from parts rather than carried.

The context is compared **field by field at both boundaries** the specification
names — the catalog surface and the execution port — because "unchanged" between
two points is not the same claim as "unchanged at one".

Those boundaries do not exist yet: `interpretation/resolve_terms.py` is Phase 8
and `execution/port.py` is Phase 9. Building either here would be the placeholder
the phase boundary forbids, so the test drives **recording collaborators standing
at those boundaries** and compares what arrives with what the identity system
answered. The comparison is the assertion; the collaborator is only the place to
stand.

Equality is by value, not identity. ``PrincipalContext`` is frozen and the base
revalidates, so an equal instance is what a boundary receives — and value
equality is the right notion anyway, since `FR-029` is about the tag set not
being widened or rewritten, not about object churn.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType

import analytics_interaction
from analytics_interaction.authorization.context_preflight import (
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.contracts.intake import PrincipalContext

from ..fixtures.counters import CountingResolver, Surfaces

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

CONTEXT_FIELDS = (
    "principal_ref",
    "principal_type",
    "authorization_scope",
    "granted_access_tags",
    "authorization_policy_pin",
)

RESOLVED = PrincipalContext(
    principal_ref="p-1",
    principal_type=PrincipalType.USER,
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read", "sessions:read"}),
    authorization_policy_pin="authpol-1",
)

SUPPLIED = PrincipalContext(principal_ref="p-1", principal_type=PrincipalType.USER)


@dataclass
class RecordingBoundary:
    """Stands where a downstream boundary will, and records what arrives.

    Not a stub of the catalog surface or the execution port — neither exists yet.
    It is the observation point for the comparison, and nothing more.
    """

    name: str
    received: list[PrincipalContext] = field(default_factory=list[PrincipalContext])

    def accept(self, context: PrincipalContext) -> None:
        self.received.append(context)


def _authorized() -> AuthorizedContext:
    return resolve_authorization_context(
        SUPPLIED, resolver=CountingResolver(Surfaces(), answer=RESOLVED)
    )


# --- unchanged at both boundaries ---------------------------------------------


@pytest.mark.parametrize("boundary", ["catalog surface", "execution port"])
@pytest.mark.parametrize("field_name", CONTEXT_FIELDS)
def test_every_field_arrives_unchanged_at_each_boundary(boundary: str, field_name: str) -> None:
    """Field by field, at both boundaries. A whole-object compare would hide
    which field moved, and the tag set is the one that matters."""
    observer = RecordingBoundary(boundary)
    observer.accept(_authorized().context)

    (arrived,) = observer.received
    assert getattr(arrived, field_name) == getattr(RESOLVED, field_name), (
        f"{field_name} changed on the way to the {boundary}"
    )


def test_the_whole_context_is_equal_at_both_boundaries() -> None:
    catalog = RecordingBoundary("catalog surface")
    execution = RecordingBoundary("execution port")

    authorized = _authorized()
    catalog.accept(authorized.context)
    execution.accept(authorized.context)

    assert catalog.received == execution.received == [RESOLVED]


def _canonical(context: PrincipalContext) -> str:
    """The whole context, serialised with set-valued fields ordered.

    ``granted_access_tags`` is a ``frozenset``. Pydantic serialises one in
    iteration order, and iteration order for strings depends on the process's
    hash seed — so two serialisations of the *same* tag set can differ between
    runs, and do, because ``revalidate_instances="always"`` rebuilds the set on
    the way through the preflight.

    Comparing raw JSON therefore tested the hash seed, not the passthrough: it
    passed almost always and failed on the runs where the rebuilt set happened to
    iterate the other way. Sorting first compares what `FR-029` is actually
    about — the membership of the set — while keeping the point of this test,
    which is that the comparison covers **every** field rather than the five
    somebody enumerated. It is the same reason the authorization fingerprint
    sorts before hashing.
    """
    payload: dict[str, object] = context.model_dump(mode="json")
    ordered: dict[str, object] = {
        key: sorted(cast("list[str]", value)) if isinstance(value, list) else value
        for key, value in payload.items()
    }
    return json.dumps(
        ordered,
        sort_keys=True,
        ensure_ascii=False,
    )


def test_the_serialised_context_is_byte_identical_at_both_boundaries() -> None:
    """A field-by-field compare can still miss a field nobody enumerated."""
    authorized = _authorized()
    assert _canonical(authorized.context) == _canonical(RESOLVED)


def test_the_canonical_serialisation_still_fails_on_a_changed_tag_set() -> None:
    """Ordering is not the only difference it could have hidden.

    Sorting a set before comparing is only safe if a *membership* change still
    shows. Both directions: a tag added and a tag removed.
    """
    widened = RESOLVED.model_copy(
        update={"granted_access_tags": frozenset({*RESOLVED.granted_access_tags, "revenue:read"})}
    )
    narrowed = RESOLVED.model_copy(update={"granted_access_tags": frozenset({"installs:read"})})

    assert _canonical(widened) != _canonical(RESOLVED)
    assert _canonical(narrowed) != _canonical(RESOLVED)


def test_a_mutated_tag_set_fails_the_comparison() -> None:
    """The guard must fail on a real elevation, not merely pass on a clean run."""
    observer = RecordingBoundary("execution port")
    elevated = RESOLVED.model_copy(
        update={"granted_access_tags": frozenset({*RESOLVED.granted_access_tags, "revenue:read"})}
    )
    observer.accept(elevated)

    (arrived,) = observer.received
    assert arrived.granted_access_tags != RESOLVED.granted_access_tags
    assert arrived != RESOLVED


# --- the six verbs ------------------------------------------------------------


def test_nothing_is_created_that_the_resolver_did_not_return() -> None:
    """The set that arrives is exactly the set that was answered."""
    authorized = _authorized()
    assert authorized.context.granted_access_tags == RESOLVED.granted_access_tags


def test_no_tag_literal_is_named_anywhere_in_the_package() -> None:
    """A tag written into this package's source is a tag this package named.

    Checked over string constants, so a docstring explaining tags stays legal
    while a constant carrying one does not.
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # a docstring
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and ":read" in node.value
            ):
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {node.value!r}")
    assert not offenders, f"an access tag is named in source: {offenders}"


def test_no_tag_is_inferred_from_the_scope_or_the_principal_type() -> None:
    """Deriving a tag would be manufacturing authorization from a fact about identity.

    **Target-aware.** What must not exist is a *tag* produced from a scope or a
    principal type — an assignment whose left side is tag-shaped and whose right
    side reads identity. Reading all four context fields together is not that:
    `identity/authorization_fingerprint.py` hashes the whole context into one
    opaque digest, which is the fingerprint's entire job and produces no tag at
    all. Flagging it would force the fingerprint to read its inputs one at a
    time, which would be worse code for no gain in safety.
    """
    identity_fields = ("authorization_scope", "principal_type")
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            target_names = " ".join(ast.unparse(target) for target in targets)
            if not any(token in target_names for token in ("tag", "grant")):
                continue
            value = ast.unparse(node.value) if node.value is not None else ""
            if any(field in value for field in identity_fields):
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {target_names} = {value}")
    assert not offenders, f"a tag is derived from identity: {offenders}"


def test_the_derivation_guard_would_catch_a_real_manufactured_tag() -> None:
    """A guard narrowed without a regression case is a guard quietly removed."""
    planted = ast.parse("granted_access_tags = frozenset({authorization_scope + ':read'})")
    assignment = planted.body[0]
    assert isinstance(assignment, ast.Assign)
    target_names = " ".join(ast.unparse(target) for target in assignment.targets)
    assert "tag" in target_names
    assert "authorization_scope" in ast.unparse(assignment.value)


def test_the_fingerprint_reads_the_context_without_producing_a_tag() -> None:
    """The case the narrowing permits, asserted so the permission is deliberate.

    The fingerprint's payload names all four context fields and its output is a
    hex digest — no tag is created, named, inferred, elevated, translated or
    assembled.
    """
    from analytics_interaction.identity.authorization_fingerprint import (
        derive_authorization_fingerprint,
    )

    context = PrincipalContext(
        principal_ref="p-9",
        principal_type=PrincipalType.USER,
        authorization_scope="tenant-a",
        granted_access_tags=frozenset({"installs:read"}),
        authorization_policy_pin="authpol-1",
    )
    authorized = resolve_authorization_context(
        PrincipalContext(principal_ref="p-9", principal_type=PrincipalType.USER),
        resolver=CountingResolver(Surfaces(), answer=context),
    )
    digest = derive_authorization_fingerprint(authorized)
    assert len(digest) == 64
    assert "installs" not in digest
    assert "tenant-a" not in digest


def test_the_set_never_grows_between_the_preflight_and_a_boundary() -> None:
    authorized = _authorized()
    assert not (authorized.context.granted_access_tags - RESOLVED.granted_access_tags)


def test_no_tag_is_translated_cased_or_prefixed() -> None:
    """Normalising a tag renames it, and a renamed tag is a different grant."""
    mixed = RESOLVED.model_copy(
        update={"granted_access_tags": frozenset({"Installs:Read", "SESSIONS:READ"})}
    )
    authorized = resolve_authorization_context(
        SUPPLIED, resolver=CountingResolver(Surfaces(), answer=mixed)
    )
    assert authorized.context.granted_access_tags == frozenset({"Installs:Read", "SESSIONS:READ"})


def test_the_set_is_carried_rather_than_reassembled() -> None:
    """An empty answer stays empty; a reassembly would show up as a default."""
    empty = RESOLVED.model_copy(update={"granted_access_tags": frozenset()})
    authorized = resolve_authorization_context(
        SUPPLIED, resolver=CountingResolver(Surfaces(), answer=empty)
    )
    assert authorized.context.granted_access_tags == frozenset()


# --- the caller cannot assert their own authorization -------------------------


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("granted_access_tags", frozenset({"revenue:read"})),
        ("authorization_scope", "tenant-z"),
        ("authorization_policy_pin", "authpol-forged"),
    ],
)
def test_a_caller_asserting_a_wider_authorization_is_refused(
    field_name: str, value: object
) -> None:
    """Not silently narrowed to the true answer — refused.

    Proceeding under the narrower answer would let a caller probe for what they
    hold by watching which assertions are accepted.
    """
    from analytics_interaction.authorization.refusal import AuthorizationRefused

    with pytest.raises(AuthorizationRefused):
        resolve_authorization_context(
            SUPPLIED.model_copy(update={field_name: value}),
            resolver=CountingResolver(Surfaces(), answer=RESOLVED),
        )


def test_a_caller_echoing_the_true_context_is_accepted() -> None:
    """The check is for *disagreement*, not for the caller having said anything.

    Without this the suite would pass against a preflight that rejected every
    caller who filled the field in, which is a broken feature rather than a safe
    one.
    """
    authorized = resolve_authorization_context(
        RESOLVED, resolver=CountingResolver(Surfaces(), answer=RESOLVED)
    )
    assert authorized.context == RESOLVED


def test_the_resolvers_answer_wins_over_anything_the_caller_left_unset() -> None:
    """Unset is not an assertion, so the resolver simply fills it."""
    authorized = _authorized()
    assert SUPPLIED.authorization_scope is None
    assert authorized.context.authorization_scope == "tenant-a"
    assert authorized.context.authorization_policy_pin == "authpol-1"
