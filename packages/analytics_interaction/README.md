# analytics-interaction

Natural-language analytics interaction for the `intelligence-agent`. Adds **interpretation and
presentation** to the governed stack — and nothing else.

`semantic-catalog` decides whether a question may be answered. `analytics-query` executes a permitted
request and says what the number is made of. This package takes a business question in pt-BR,
resolves it exclusively against the governed vocabulary, constructs the governed `AnalyticsQuery`
deterministically, submits it through `analytics-query`'s public composed entry point, and assembles
an evidence-backed answer from stored governed content.

It re-implements no catalog gate and no execution gate, generates no query text, and holds no state
between turns.

## Status

**Scaffolding only. Not production-ready, and no production readiness is claimed.**

Phase 1 of `specs/003-nl-analytics-interaction/tasks.md` creates the package, its module boundaries
and the two dependency-direction guards. No interpretation behaviour exists yet.

Aggregate readiness was **NONE** until 2026-09-02; since **OD-101** and **OD-104** exactly
**d_21** (the clarification-seal key) and **d_18** (the governed interpretation vocabulary)
are ready and every other lock stays closed. **13** of the 15 external dependency records
are open — the 11 inherited from Features 001 and 002, plus four this feature added (D-21
and D-18 closed dated on 2026-09-02):

| Record | Holds open |
|---|---|
| `D-18` | The governed interpretation vocabulary. **Declared 2026-09-02 (OD-104)** — eleven period expressions with Monday week and civil-month conventions declared with validator teeth, the closed formula set (percentage_change), and the four claim-class wordings |
| `D-19` | The governed interpretation policy: ambiguity threshold, round bound, expiry, length bound, redaction rule, cross-question disclosure |
| `D-20` | An approved model provider. While undeclared, interpretation is deterministic-only and the model port is unreachable |
| `D-21` | The clarification-seal key. **Declared 2026-09-02 (OD-101)** — key-as-code on the VM, monthly rotation, HMAC of the canonical preimage, bot-process-only scope. A deployment without a configured key still refuses every ambiguous question |

No test in this package closes any of them. Fixtures prove internal behaviour and are never evidence
for an external capability.

## Boundaries

| Property | How it holds |
|---|---|
| One execution path | The narrow port over `analytics_query.execute`; a CI gate asserts no `002` internal is importable |
| No query text | This package generates none, holds no field that could carry it, and prints none |
| No value reaches a model | The model-facing types are structurally unable to hold a result, row, cell, comparison or suppression detail |
| No language detection | The caller declares the language; nothing infers it |
| No invented governed value | Every threshold, formula, expiry and key comes from governed content or the request refuses |
| Stateless | No conversation store. A clarification is a self-contained sealed contract, not a session |
| Nothing sensitive at rest | Audit and telemetry record decisions and identifiers — never an unrestricted question, never a figure |

## Layout

```
src/analytics_interaction/
├── contracts/       intake, resolved intent, clarification, comparison, answer, reason codes, audit
├── authorization/   authorization-context preflight — runs before any catalog read or model call
├── governance/      D-18 vocabulary and D-19 policy loading, exactly-one-effective resolution
├── intake/          typed pt-BR question intake, declared language, bounds, untrusted-text screening
├── interpretation/  slot and period resolution, and the narrowing-only model port
├── identity/        value-free interpretation identity and authorization fingerprint
├── clarification/   stateless versioned sealed clarification contracts
├── comparison/      routing, comparability, exact arithmetic, whole-comparison refusal
├── execution/       the narrow port over 002's public composed entry point
├── answer/          deterministic assembly, typed claim classes, caveat propagation
├── messages/        stored pt-BR wording selected by code, never generated
├── audit/           synchronous fail-closed emission of the six interpretation stages
├── telemetry/       spans, guarded by the same content scan as audit
├── compliance/      additive readiness aggregation across all three records
└── cli/             read-only steward commands
```

## Development

```bash
python -m pip install -e "packages/semantic_catalog[dev]"      # upstream, install first
python -m pip install -e "packages/analytics_query[dev]"       # upstream, install second
python -m pip install -e "packages/analytics_interaction[dev]"

python -m ruff format --check packages/analytics_interaction
python -m ruff check packages/analytics_interaction
cd packages/analytics_interaction && python -m pyright && cd ../..
python -m pytest packages/analytics_interaction -q
```

Both upstream packages are path dependencies inside this monorepo and are not published, so both must
be installed editable before this one.

## Governance

The specification, plan, contracts and task graph live in `specs/003-nl-analytics-interaction/`.
Governed content owned by this feature — the period vocabulary, comparison formulas, claim-class
wording, interpretation policy and the pt-BR message registry — lives in `interpretation_governance/`
at the repository root.

The four `D-18` and `D-19` documents are **empty and unapproved**: populating one is the owner's
governed act, not an implementation step. `messages/pt-br.yaml` is different in kind and is authored
— it is this layer's reason-code wording, the direct analogue of `query_governance/messages/pt-br.yaml`
in `002`, and it declares no threshold, formula, convention or policy value. Its interpolation fields
are allowlisted, so no message can carry a metric value, a filter value, a credential or a span of the
question.
