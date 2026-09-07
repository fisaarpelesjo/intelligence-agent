"""The authorization-fingerprint binding — T089 (FR-056; SC-006).

**Security correction, recorded.** An earlier draft excluded ``principal_ref``
from the fingerprint, reasoning that binding the principal would break retry
equality. That was wrong twice over: the same reference hashes identically every
time, so retries were never at risk — and excluding it meant two *distinct*
principals holding identical grants shared one fingerprint. Since this value
binds resolved intent and stateless clarification contracts to an authorized
identity, that collision was the precise failure the binding exists to prevent.
Corrected before the Phase 8 commit; the collision case is the second test below.

Five fields are bound: ``principal_ref``, principal type, authorization scope,
the canonically sorted granted tag set, and the governed authorization-policy
pin. Each is asserted to matter independently, because a fingerprint that ignored
any one of them would let a contract cross that boundary.

**What the output is.** A deterministic 64-character digest. It is an
identity-binding value, not an authentication token and not an authorization
decision — holding one grants nothing, and comparing two answers only "was this
the same authorized identity". No raw field survives into it, and the canonical
preimage is never returned, logged or persisted.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType

from analytics_interaction.authorization.context_preflight import (
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intake import PrincipalContext
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.identity import authorization_fingerprint as module
from analytics_interaction.identity.authorization_fingerprint import (
    FINGERPRINT_INPUTS,
    derive_authorization_fingerprint,
    fingerprints_match,
)

pytestmark = pytest.mark.contract

BASELINE = PrincipalContext(
    principal_ref="p-1",
    principal_type=PrincipalType.USER,
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read", "sessions:read"}),
    authorization_policy_pin="authpol-1",
)


def _authorize(resolved: PrincipalContext) -> AuthorizedContext:
    """Run the real step-2 preflight against a synthetic identity answer."""
    from ..fixtures.counters import CountingResolver, Surfaces

    supplied = PrincipalContext(
        principal_ref=resolved.principal_ref, principal_type=resolved.principal_type
    )
    return resolve_authorization_context(
        supplied, resolver=CountingResolver(Surfaces(), answer=resolved)
    )


def _fingerprint(**changes: object) -> str:
    return derive_authorization_fingerprint(_authorize(BASELINE.model_copy(update=changes)))


# --- 1. the same principal and grants reproduce -------------------------------


def test_the_same_principal_and_grants_reproduce_across_independent_preflights() -> None:
    """Retry equality, which the earlier exclusion was wrongly protecting.

    Three separate preflights, three separate resolver instances, one digest —
    so a genuine repeat by the same principal still attaches.
    """
    digests = {derive_authorization_fingerprint(_authorize(BASELINE)) for _ in range(3)}
    assert len(digests) == 1


def test_the_comparison_helper_agrees_with_equality() -> None:
    left = derive_authorization_fingerprint(_authorize(BASELINE))
    right = derive_authorization_fingerprint(_authorize(BASELINE))
    assert fingerprints_match(left, right)


# --- 2. a different principal never collides ----------------------------------


@pytest.mark.parametrize("other_ref", ["p-2", "p-1 ", "P-1", "p-10", "p-1​"])
def test_a_different_principal_ref_produces_a_different_fingerprint(other_ref: str) -> None:
    """**The correction.** Identical type, scope, tags and pin — different principal.

    Includes a trailing space, a case change and a zero-width character, because
    a normalising implementation would collapse exactly those into a collision.
    """
    assert _fingerprint(principal_ref=other_ref) != _fingerprint()


def test_two_principals_with_identical_grants_are_distinguishable() -> None:
    """Stated as the scenario rather than the mechanism.

    Two colleagues in the same tenant with the same tags are two identities. A
    clarification contract bound to one must not validate for the other.
    """
    alice = derive_authorization_fingerprint(
        _authorize(BASELINE.model_copy(update={"principal_ref": "alice"}))
    )
    bob = derive_authorization_fingerprint(
        _authorize(BASELINE.model_copy(update={"principal_ref": "bob"}))
    )
    assert alice != bob


def test_principal_ref_is_a_declared_fingerprint_input() -> None:
    assert "principal_ref" in FINGERPRINT_INPUTS
    assert len(FINGERPRINT_INPUTS) == 5


def test_the_payload_names_exactly_the_declared_inputs() -> None:
    """Read from the source, so the constant cannot drift from what is hashed."""
    tree = ast.parse(inspect.getsource(derive_authorization_fingerprint))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys |= {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    assert keys == set(FINGERPRINT_INPUTS)


# --- 3. tag ordering is irrelevant ---------------------------------------------


@pytest.mark.parametrize(
    "ordering",
    [
        ("installs:read", "sessions:read"),
        ("sessions:read", "installs:read"),
    ],
)
def test_tag_input_ordering_does_not_change_the_fingerprint(
    ordering: tuple[str, ...],
) -> None:
    """A set is a set. Two orderings of the same grants are one authorization."""
    assert _fingerprint(granted_access_tags=frozenset(ordering)) == _fingerprint()


def test_a_larger_tag_set_still_orders_canonically() -> None:
    """Frozenset iteration order is not stable across processes; sorting is."""
    tags = ("a:read", "b:read", "c:read", "d:read", "e:read")
    forward = _fingerprint(granted_access_tags=frozenset(tags))
    backward = _fingerprint(granted_access_tags=frozenset(reversed(tags)))
    assert forward == backward


# --- 4. every other field matters independently -------------------------------


def test_a_different_principal_type_changes_the_fingerprint() -> None:
    assert _fingerprint(principal_type=PrincipalType.SERVICE_PRINCIPAL) != _fingerprint()


def test_a_different_scope_changes_the_fingerprint() -> None:
    assert _fingerprint(authorization_scope="tenant-b") != _fingerprint()


def test_a_different_tag_set_changes_the_fingerprint() -> None:
    """Both directions: a tag added and a tag removed."""
    widened = _fingerprint(
        granted_access_tags=frozenset({"installs:read", "sessions:read", "revenue:read"})
    )
    narrowed = _fingerprint(granted_access_tags=frozenset({"installs:read"}))
    assert widened != _fingerprint()
    assert narrowed != _fingerprint()
    assert widened != narrowed


def test_a_different_policy_pin_changes_the_fingerprint() -> None:
    assert _fingerprint(authorization_policy_pin="authpol-2") != _fingerprint()


def test_all_five_fields_are_independently_load_bearing() -> None:
    """One sweep, so a field silently dropped shows up as a collision."""
    variants = {
        "principal_ref": {"principal_ref": "p-other"},
        "principal_type": {"principal_type": PrincipalType.SERVICE_PRINCIPAL},
        "authorization_scope": {"authorization_scope": "tenant-other"},
        "granted_access_tags": {"granted_access_tags": frozenset({"other:read"})},
        "authorization_policy_pin": {"authorization_policy_pin": "authpol-other"},
    }
    baseline = _fingerprint()
    digests = {name: _fingerprint(**changes) for name, changes in variants.items()}

    for name, digest in digests.items():
        assert digest != baseline, f"{name} does not affect the fingerprint"
    assert len(set(digests.values())) == len(digests), "two fields collide"
    assert set(variants) == set(FINGERPRINT_INPUTS)


# --- 5. no raw field survives into the digest ---------------------------------


@pytest.mark.parametrize(
    "raw", ["p-1", "tenant-a", "installs:read", "sessions:read", "authpol-1", "USER"]
)
def test_the_digest_contains_no_raw_identity_field(raw: str) -> None:
    digest = derive_authorization_fingerprint(_authorize(BASELINE))
    assert raw.lower() not in digest.lower()


def test_the_digest_is_a_stable_sixty_four_character_hex_string() -> None:
    digest = derive_authorization_fingerprint(_authorize(BASELINE))
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


def test_the_canonical_preimage_is_never_returned() -> None:
    """The only value leaving the function is the digest.

    A preimage carrying a principal reference beside a grant set is exactly the
    payload the digest exists to avoid handling.
    """
    tree = ast.parse(inspect.getsource(derive_authorization_fingerprint))
    returns = [
        ast.unparse(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    assert returns == ["hashlib.sha256(canonical.encode('utf-8')).hexdigest()"]


def test_the_module_neither_logs_nor_persists() -> None:
    """No logger, no write, no cache — the preimage is built and dropped."""
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    for forbidden in ("getLogger", "info", "debug", "warning", "write_text", "open", "lru_cache"):
        assert forbidden not in calls


def test_no_randomness_clock_or_undeclared_secret_participates() -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not {"random", "secrets", "time", "os", "uuid"} & {
        name.split(".")[0] for name in imported
    }
    assert "hmac" not in source, "a keyed digest would need a secret nobody declared"


# --- 6. a mismatch still constructs nothing -----------------------------------


def test_a_fingerprint_mismatch_constructs_no_intent(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """The correction must not have weakened the binding it exists for."""
    from analytics_interaction.contracts.intake import DeclaredLanguage
    from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent

    from ..conftest import REFERENCE, governed_resolution

    authorized, _ = authorized_pair
    with pytest.raises(ContractViolation) as caught:
        assemble_resolved_intent(
            (governed_resolution("installs"),),
            authorized=authorized,
            auth_fingerprint="a-fingerprint-nobody-derived",
            period=resolved_intent.period,
            language=DeclaredLanguage.PT_BR,
            reference_date=REFERENCE,
            as_of=None,
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
        )
    assert caught.value.code is Code.AUTHORIZATION_CONTEXT_UNRESOLVABLE


def test_a_fingerprint_mismatch_constructs_no_request(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    authorized, _ = authorized_pair
    with pytest.raises(ContractViolation) as caught:
        build_analytics_query(
            resolved_intent, authorized=authorized, auth_fingerprint="not-the-fingerprint"
        )
    assert caught.value.code is Code.AUTHORIZATION_CONTEXT_UNRESOLVABLE


def test_another_principals_fingerprint_does_not_unlock_an_intent(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """The collision case, end to end.

    Under the old composition these two fingerprints were equal and this would
    have succeeded.
    """
    authorized, _ = authorized_pair
    other = _authorize(
        BASELINE.model_copy(
            update={
                "principal_ref": "someone-else",
                "granted_access_tags": authorized.context.granted_access_tags,
                "authorization_scope": authorized.context.authorization_scope,
                "authorization_policy_pin": authorized.context.authorization_policy_pin,
            }
        )
    )
    with pytest.raises(ContractViolation) as caught:
        build_analytics_query(
            resolved_intent,
            authorized=authorized,
            auth_fingerprint=derive_authorization_fingerprint(other),
        )
    assert caught.value.code is Code.AUTHORIZATION_CONTEXT_UNRESOLVABLE


# --- 7. no metric-level authorization is introduced ---------------------------


def test_the_fingerprint_makes_no_access_decision() -> None:
    """It answers "was this the same identity", never "may they see this".

    A digest cannot be interrogated for a grant, and nothing here inspects a
    metric — metric-level access stays with `001`'s gate and `002`'s preflight.
    """
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    # Not bare "authorize": the module's own parameter type is
    # ``AuthorizedContext``, which is the *input* the preflight produced, not a
    # decision this module makes. The verdict-shaped names are listed instead.
    for verdict in (
        "metric",
        "may_see",
        "can_see",
        "permitted",
        "allowed",
        "authorize_metric",
        "check_access",
        "has_access",
        "grant_for",
    ):
        assert not any(verdict in name.lower() for name in names), f"names {verdict}"

    # And the narrowing is not a hole: the module reads a resolved context and
    # returns a digest, so the only authorization-shaped name it carries is the
    # type of what it was handed.
    assert {name for name in names if "authoriz" in name.lower()} <= {
        "AuthorizedContext",
        "authorized",
        "authorization_scope",
        "authorization_policy_pin",
    }


def test_the_module_performs_no_tag_arithmetic() -> None:
    """Sorting is canonicalisation; intersection or subset would be a decision."""
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    offenders = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp | ast.Compare) and "access_tags" in ast.unparse(node)
    ]
    assert not offenders, f"tag arithmetic in the fingerprint: {offenders}"
