"""Query identity — T036 (FR-033, FR-035, FR-078; SC-014, SC-036).

Two requests that ask the same thing share one identity however they were
written, and the principal is deliberately **not** part of it.

That exclusion carries two guarantees at once. Identity must never become an
authorization artifact (`FR-035`) — every execution is authorized on the
requesting principal's own tags, so an identity that encoded a principal could be
mistaken for one. And including it would hide that the same query was asked
twice, which is exactly what the ledger exists to notice.

**Identity alone is not an execution key.** Because it is principal-independent,
two differently-authorized callers derive the same identity. Keying an execution
on it alone would let the second attach to the first's execution and inherit its
status, cost, warehouse job, audit-recovery path and result. The execution key is
therefore the pair `(QueryIdentity, AuthorizationContextFingerprint)` (`FR-078`,
execution-contract §7.0). The fingerprint half arrived with the ledger in Phase 4;
what this module must guarantee is that no acquisition surface is reachable with
an identity and nothing else.

**Normalization is scoped.** Case and whitespace folding applies to governed
identifiers and structural formatting only — never to filter values. Folding
values would make identity coarser than the semantics the warehouse executes, and
single-flight would then resolve two different questions to one answer.
"""

from __future__ import annotations

import inspect
import re
from datetime import date
from pathlib import Path

import pytest

import analytics_query
from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.operators import GovernedOperator
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange, GovernedFilter
from analytics_query.identity import normalize as normalize_module
from analytics_query.identity.normalize import QueryIdentity, canonical_form, derive_identity

pytestmark = pytest.mark.unit

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
PINS = {"policy_version": "p-1", "catalog_release_id": "r-1"}


def _query(**overrides: object) -> AnalyticsQuery:
    payload: dict[str, object] = {"metrics": ("installs",), "date_range": JULY}
    payload.update(overrides)
    return build(AnalyticsQuery, **payload)


# --- cosmetic variation collapses -------------------------------------------


def test_the_same_request_yields_the_same_identity() -> None:
    assert derive_identity(_query(), **PINS) == derive_identity(_query(), **PINS)


def test_metric_ordering_does_not_change_the_identity() -> None:
    a = _query(metrics=("installs", "sessions"))
    b = _query(metrics=("sessions", "installs"))
    assert derive_identity(a, **PINS) == derive_identity(b, **PINS)


def test_dimension_and_source_ordering_do_not_change_the_identity() -> None:
    a = _query(dimensions=("country", "platform"), sources=("google_play", "ios_app"))
    b = _query(dimensions=("platform", "country"), sources=("ios_app", "google_play"))
    assert derive_identity(a, **PINS) == derive_identity(b, **PINS)


def test_filter_and_value_ordering_do_not_change_the_identity() -> None:
    left = build(
        GovernedFilter, dimension="country", operator=GovernedOperator.IN, values=("BR", "AR")
    )
    right = build(
        GovernedFilter, dimension="platform", operator=GovernedOperator.EQ, values=("android",)
    )
    swapped = build(
        GovernedFilter, dimension="country", operator=GovernedOperator.IN, values=("AR", "BR")
    )
    a = _query(filters=(left, right))
    b = _query(filters=(right, swapped))
    assert derive_identity(a, **PINS) == derive_identity(b, **PINS)


# --- semantic difference separates ------------------------------------------


def test_a_different_request_yields_a_different_identity() -> None:
    assert derive_identity(_query(), **PINS) != derive_identity(
        _query(metrics=("sessions",)), **PINS
    )


def test_the_as_of_pin_participates() -> None:
    assert derive_identity(_query(), **PINS) != derive_identity(
        _query(as_of=date(2026, 6, 30)), **PINS
    )


def test_the_policy_version_and_release_participate() -> None:
    base = derive_identity(_query(), **PINS)
    assert derive_identity(_query(), policy_version="p-2", catalog_release_id="r-1") != base
    assert derive_identity(_query(), policy_version="p-1", catalog_release_id="r-2") != base


def test_a_different_date_range_separates() -> None:
    august = DateRange(start=date(2026, 8, 1), end=date(2026, 8, 31))
    assert derive_identity(_query(), **PINS) != derive_identity(_query(date_range=august), **PINS)


# --- deliberate exclusions ---------------------------------------------------


def test_the_principal_is_not_an_input() -> None:
    """Two principals asking the same question share one identity (`FR-035`)."""
    canonical = canonical_form(_query(), **PINS).lower()
    for term in ("principal", "actor", "subject", "granted", "access_tag"):
        assert term not in canonical


def test_the_clock_is_not_an_input() -> None:
    """A per-request identity would de-duplicate nothing."""
    canonical = canonical_form(_query(), **PINS).lower()
    for term in ("timestamp", "requested_at", "emitted_at", "evaluated_at"):
        assert term not in canonical


# --- determinism -------------------------------------------------------------


def test_the_canonical_form_is_deterministic_bytes() -> None:
    assert canonical_form(_query(), **PINS) == canonical_form(_query(), **PINS)


def test_the_canonical_form_is_sorted_json() -> None:
    canonical = canonical_form(_query(dimensions=("platform", "country")), **PINS)
    assert canonical.startswith("{")
    assert '"country","platform"' in canonical.replace(" ", "")


def test_the_fingerprint_is_a_sha256_hex_digest() -> None:
    fingerprint = derive_identity(_query(), **PINS).fingerprint
    assert len(fingerprint) == 64
    assert all(char in "0123456789abcdef" for char in fingerprint)


def test_identity_equality_and_hashing_follow_the_fingerprint() -> None:
    a = derive_identity(_query(), **PINS)
    b = derive_identity(_query(), **PINS)
    assert a == b
    assert len({a, b}) == 1


# --- normalization scope: identifiers fold, values do not (FR-033; SC-014) ----


def _with_country(*values: str) -> AnalyticsQuery:
    return _query(
        filters=(
            build(
                GovernedFilter,
                dimension="country",
                operator=GovernedOperator.EQ,
                values=values,
            ),
        )
    )


@pytest.mark.parametrize(
    ("left", "right", "why"),
    [
        ("br", "BR", "plain ASCII case"),
        ("1.0.0-a", "1.0.0-A", "version suffix case"),
        ("strasse", "straße", "German sharp s — casefold maps ß to ss"),
        ("i", "İ", "Turkish dotted capital I — casefold maps it to i + combining dot"),
        ("é", "é", "combining acute vs precomposed é — same glyph, different bytes"),
    ],
)
def test_filter_values_differing_only_by_case_or_unicode_stay_distinct(
    left: str, right: str, why: str
) -> None:
    """Values are data, not identifiers.

    The warehouse compares them byte- and case-sensitively, so an identity that
    folded them would be coarser than the query it identifies. Single-flight would
    then hand one caller the answer to a different question — the failure mode is
    a wrong number, not a duplicate execution.
    """
    assert derive_identity(_with_country(left), **PINS) != derive_identity(
        _with_country(right), **PINS
    ), why


def test_the_canonical_form_preserves_filter_values_verbatim() -> None:
    canonical = canonical_form(_with_country("BR"), **PINS)
    assert '"BR"' in canonical
    assert '"br"' not in canonical


def test_a_non_lowercase_identifier_is_refused_rather_than_folded() -> None:
    """The request contract is stricter than `FR-033` requires, deliberately.

    `FR-033` promises that identifier case does not split an identity. The
    contract delivers that by **refusing** a non-canonical identifier at parse
    rather than by quietly folding it, so two *valid* requests can never differ
    in identifier case at all. Refusing is the stronger of the two: a folded
    identifier would let a caller's typo silently resolve to a governed object it
    did not name.
    """
    for bad in ("INSTALLS", "Installs"):
        with pytest.raises(ContractViolation) as caught:
            _query(metrics=(bad,))
        assert caught.value.code is AnalyticsReasonCode.REQUEST_MALFORMED

    with pytest.raises(ContractViolation):
        _query(dimensions=("Country",))


def test_identifier_folding_remains_as_defence_in_depth() -> None:
    """`normalize` still folds, for identities derived outside the request contract."""
    payload = canonical_form(_query(metrics=("installs",)), **PINS)
    assert '"installs"' in payload


def test_pins_are_never_folded() -> None:
    """A pin is an exact reference; folding one could collide two distinct pins."""
    assert derive_identity(
        _query(), policy_version="P-1", catalog_release_id="r-1"
    ) != derive_identity(_query(), policy_version="p-1", catalog_release_id="r-1")


# --- identity alone is not an execution key (FR-078; SC-036) -----------------


def test_query_identity_exposes_no_execution_key_surface() -> None:
    """No `acquire`, `attach` or key-like member may hang off identity."""
    members = {name.lower() for name, _ in inspect.getmembers(QueryIdentity)}
    for forbidden in ("acquire", "attach", "complete", "execution_key", "key", "ledger"):
        assert forbidden not in members, f"QueryIdentity exposes {forbidden}"


def test_the_identity_module_declares_no_ledger_operation() -> None:
    """Identity derives a fingerprint. It does not reserve, observe or own work."""
    exported = set(getattr(normalize_module, "__all__", ()))
    assert exported == {"QueryIdentity", "canonical_form", "derive_identity"}


def test_no_module_keys_an_execution_on_identity_alone() -> None:
    """The permanent invariant behind `FR-078`.

    Phase 4 introduced the ledger, so the question is no longer "does an
    acquisition surface exist" but "can any of them be reached with a query
    identity and nothing else". Every `acquire`/`attach`/`complete`/`get` in
    the package must take an `ExecutionKey` as its first argument; a parameter
    named for the identity would be this defect reintroduced.
    """
    src = Path(analytics_query.__file__).parent
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        for match in re.finditer(
            r"^\s+def (acquire|attach|complete|get)\(\s*self,\s*([^,)]+)",
            path.read_text(encoding="utf-8"),
            re.M,
        ):
            first = match.group(2).split(":")[0].strip()
            if first != "key":
                offenders.append(f"{path.relative_to(src)}: {match.group(1)}({first} ...)")
    assert not offenders, (
        "an execution is keyed on something other than an ExecutionKey: " + "; ".join(offenders)
    )


def test_identity_is_only_ever_half_of_an_execution_key() -> None:
    """A key without its authorization half is refused at construction."""
    from analytics_query.execution.ledger import ExecutionKey, UnresolvedAuthorizationContext

    identity = derive_identity(_query(), **PINS)
    with pytest.raises(UnresolvedAuthorizationContext):
        ExecutionKey(identity.fingerprint, "")
