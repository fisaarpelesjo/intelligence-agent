# Pull request

> Git records **who** changed something and **when**. This template records **why** — which is the
> other half of FR-037. Every section is required; write "none" where a section genuinely does not
> apply, but do not delete it.

## 1. Change rationale

<!-- Why is this change being made? What breaks, or stays wrong, without it? -->

## 2. Affected identifiers

<!-- Every metric, dimension, source, policy, access tag or reason code this touches.
     Use canonical English identifiers. Write "none" for code-only changes. -->

| Kind | Identifier(s) |
|---|---|
| Metrics | |
| Dimensions | |
| Sources | |
| Policy / access tags / reason codes | |

## 3. Field-change classification

<!-- Per the authoritative table in
     specs/001-semantic-catalog/contracts/catalog-file-contracts.md §4.4.
     Tick every class this change touches. -->

- [ ] **Stable Identity** — immutable once published
- [ ] **Semantic** — changes what the number means → **requires a new metric-definition version**
- [ ] **Descriptive** — human-facing wording that cannot alter the number
- [ ] **Availability** — where or by whom a metric may be requested → dated decision, no version bump
- [ ] **Lifecycle** — governs which definition applies to which period → fingerprint-protected
- [ ] **Governance** — ownership, approval or policy attribution
- [ ] None of the above (code-only change)

## 4. Version-bump decision

- [ ] **New metric-definition version required** — new block, new `effective_from`, prior block closed
- [ ] **No version bump** — Descriptive, Availability or Governance change only
- [ ] **Schema version bump** (`catalog_schema_version`) — contract *shape* changed
- [ ] **Policy version bump** (`policy_version`) — decision, authorisation, publication, projection
      or refusal **behaviour** changed
- [ ] Not applicable

**If a Descriptive edit could change how a reader computes the number**, say so here and explain why
`calculation_basis` did not also change:

<!-- A description that contradicts an unchanged calculation_basis is a review failure.
     The semantic fingerprint cannot detect it — that is what this question is for. -->

## 5. Owner and reviewer roles

<!-- Roles from semantic/owners.yaml. NEVER name individuals. -->

- **Owner role**:
- **Reviewer role(s)**:
- **Change class** (see ADR 0003): single-metric / cross-cutting / policy
- [ ] I confirm this is **not** a self-approval, or that the policy explicitly permits it for this role

## 6. Backward-compatibility impact

- [ ] Closed version blocks untouched in their Semantic fields
- [ ] No metric name reused for a different concept
- [ ] Previously published closed-period figures unchanged
- [ ] Deprecated metrics remain resolvable for historical periods
- [ ] Loader still accepts `catalog_schema_version` N−1

**Anything that breaks a consumer, and how it is handled:**

## 7. Rollout / corrective-release notes

<!-- New detector or automated delivery? State where it sits in:
     backtest → shadow → human review → pilot → progressive expansion.
     Corrective release? State the withdrawn release id and why forward-only correction was used. -->

## 8. Constitution principles touched

<!-- specs/../.specify/memory/constitution.md — tick each and say how it is satisfied. -->

- [ ] **I. Governed Semantic Access** — no raw/staging/core access, no unrestricted SQL, no BigQuery object created
- [ ] **II. Deterministic First** — numbers computed by code, not by a model
- [ ] **III. Provenance or Abstention** — provenance carried; abstains rather than degrades
- [ ] **IV. Least Privilege** — read-only business data, no PII, deny-by-default
- [ ] **V. Idempotent, Auditable Delivery** — *not applicable to this feature (delivers to no channel)*
- [ ] None touched

## 9. Blocked-external check

- [ ] This PR does **not** mark any `[BLOCKED-EXTERNAL]` record complete
- [ ] This PR does **not** claim a success criterion whose evidence is absent
      (notably **SC-002**, which requires the D-11 real-user corpus)
- [ ] Retention metrics remain `pending` unless D-8 evidence is attached
