# tests/fixtures/adversarial

Requests and inputs designed to get a wrong answer out of the catalog (T099).

Every case states the attack in one line, the request, and the refusal the
catalog must produce — **including the stable reason code**. A case asserting
only "DENY" would pass on a generic refusal, which is what SC-004 forbids.

| File | What it attacks |
|---|---|
| `requests.yaml` | Authorisation, incompatible sources, partial periods, grain mixing |
| `freshness/stale.yaml` | Data that is punctual-looking but out of tolerance |
| `freshness/insufficient_sample.yaml` | A load that finished on time and is incomplete |
| `queries.yaml` | Informal and misspelled pt-BR that must still resolve, or refuse cleanly |

Evaluated against `tests/fixtures/decision_matrix/catalog/`, whose sources are
approved so the later gates are reachable at all.

**Unit-test fixtures only.** They never represent production data, production
approvals or integration readiness. After EXT-A readiness (T109) is declared,
fixture fallback in integration or release CI fails closed (T101).
