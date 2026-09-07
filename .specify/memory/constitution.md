<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.1.0
Bump rationale: MINOR. No principle removed or redefined incompatibly. One new section
added (Source of Truth Hierarchy) and multiple principles materially expanded with
scoping, conditional applicability, and corrected architecture. Several concrete tool
mandates were relaxed to ADR-level decisions, which loosens rather than breaks compliance.

Modified principles (titles unchanged, content amended):
  - I. Governed Semantic Access (NON-NEGOTIABLE)
      + Prohibition scoped to agent runtime, LLM-facing services, and query workers
      + Explicit carve-out: transformation pipelines may access raw/staging/core under
        isolated least-privilege service accounts
  - II. Deterministic First, Narrative Second — unchanged in substance
  - III. Provenance or Abstention (NON-NEGOTIABLE)
      ~ Lowest-common-coverage rule no longer applies to single-source analysis
      + Cross-source comparisons require an explicitly comparable window
      + Partial-vs-complete period comparison forbidden; equivalent partial-vs-partial
        comparison permitted when labeled partial
      + Evidence validation: every published number traces to structured evidence;
        material analytical claims reference evidence IDs; automated claim validation
        rolls out progressively and is mandatory for higher-risk autonomous delivery
  - IV. Least Privilege and Data Boundaries
      ~ Tenant isolation now conditional on multiple organizations/business units/domains
      ~ MCP requirements now conditional on MCP adoption
      ~ Human approval relaxation path clarified (per channel, insight type, risk level)
  - V. Idempotent, Auditable Delivery
      ~ Outbox architecture corrected: transaction is in PostgreSQL; insight creation and
        delivery scheduling write to the outbox in the same transaction; an idempotent
        publisher emits committed events to Pub/Sub; workers consume and deliver

Modified sections:
  - Technology and Architecture Constraints
      - Removed mandates for specific libraries (SQLAlchemy, Alembic, httpx, Ruff,
        Pyright, mypy) — now ADR-level choices in the architecture document
      + Retained durable requirements: Python version floor, static typing, automated
        tests, linting, reproducible dependencies, versioned migrations, quality gates
      ~ LangGraph demoted from constitutional mandate to initial implementation choice
        recorded in the architecture document; replacement requires an ADR, not an
        amendment
      ~ LLMProvider abstraction MUST support fallback; running multiple providers is not
        required for the MVP
      = Retained unchanged: BigQuery, semantic layer, read-only business access,
        operational PostgreSQL, reproducible infrastructure, Power BI outside the agent
  - Development Workflow and Quality Gates — human approval relaxation path aligned
  - Governance — architecture document path corrected

Added sections:
  - Source of Truth Hierarchy (6-level precedence order, no silent override)

Removed sections: none

Corrections: none

Follow-up TODOs: none

---

Version change: 1.1.0 → 1.1.1
Bump rationale: PATCH. Non-semantic correction only — the architecture document
reference was pointed at a filename that does not exist. No principle, section, or rule
changed.

Corrections:
  - Architecture document path reverted to the actual file on disk:
    docs/product-intelligence-agent.yaml → docs/intelligence-agent.yaml
-->

# Intelligence Agent Constitution

## Core Principles

### I. Governed Semantic Access (NON-NEGOTIABLE)

The agent runtime, every service exposed to the LLM, and every query worker MUST NOT read
the `raw`, `staging`, or `core` datasets, and MUST NOT generate or execute unrestricted
SQL. Transformation pipelines (Dataform, Airflow, and equivalent batch jobs) MAY read and
write those datasets, provided they run under isolated service accounts holding only the
privileges that pipeline needs, and provided no such credential is reachable from the agent
runtime or any LLM-facing surface.

All business data access on the agent path happens through the `AnalyticsQuery` contract
against the `semantic` dataset only. Every query MUST pass validation before execution:
metric allowlist, dimension allowlist, operator allowlist, semantic compatibility, access
control, mandatory temporal filter, dry run, `maximum_bytes_billed`, and `maximum_rows`.
Multiple statements, DDL, and DML are forbidden on this path. Metrics and dimensions exist
only if declared in the semantic catalog with the full metric contract (name, label,
description, source_view, grain, aggregation, unit, time_dimension, allowed_dimensions,
source_availability, owner, version, limitations). Retrieval (RAG) serves documentation,
glossary, and rules — never fact-table rows, user events, PII, or credentials.

Rationale: an LLM with open SQL is an unbounded cost, correctness, and security risk. The
constraint belongs to the agent's execution path, not to the data platform that builds the
warehouse; separating the two keeps the boundary enforceable by IAM instead of convention.

### II. Deterministic First, Narrative Second

Numbers, comparisons, anomaly detection, dimensional investigation, and relevance scoring
MUST be computed by deterministic code — business rules first, robust statistics second,
time-series models only after progressive rollout. The LLM's role is to interpret
structured evidence and produce narrative; it MUST NOT invent, recompute, or adjust any
figure. Detection MUST NOT emit causal claims: permitted language is correlation, temporal
association, or hypothesis, and every such statement carries the causality warning. New
capability MUST be implemented deterministically when a deterministic implementation is
feasible; using the model instead requires written justification in the plan.

Rationale: deterministic components are testable, reproducible, and cheap to audit. Keeping
the model on the narration side makes every published number traceable to code.

### III. Provenance or Abstention (NON-NEGOTIABLE)

Every answer and every insight MUST carry its provenance: contributing sources, data-as-of
timestamp, source update time, dimensional coverage, and known limitations. Freshness and
data-quality checks run before detection and before answering. When data is missing, stale,
insufficient in sample, or the request falls outside declared coverage, the system MUST
abstain with an explicit reason rather than answer.

**Coverage rules.**
- Single-source analysis MAY use the full coverage available for that source. It MUST state
  its scope and limitations. The lowest-common-coverage rule does NOT apply to it.
- Cross-source comparison MUST use an explicitly comparable window across the participating
  sources, and MUST state which window was used and why.
- Comparing a partial period against a complete period is forbidden.
- Comparing equivalent partial periods is permitted — for example, today up to 12:00 versus
  yesterday up to 12:00 — and the output MUST explicitly identify the comparison as partial
  and name the cutoff.

**Evidence validation.**
- Every published number MUST point directly to the structured evidence that produced it.
- Material analytical claims MUST reference evidence IDs.
- Automated claim validation is introduced progressively. It is MANDATORY for
  higher-risk autonomous delivery — any insight published to a channel without human
  review — and RECOMMENDED elsewhere until coverage is complete.

Rationale: a product-intelligence agent is only useful if its users can trust an answer
without re-deriving it. Blanket coverage-narrowing hides real signal; unlabeled partial
comparisons manufacture fake ones. Both failures are avoided by stating the window.

### IV. Least Privilege and Data Boundaries

Business data is read-only on the agent path. Writes are scoped to the agent's operational
tables in PostgreSQL (conversations, agent_runs, insights, insight_evidence,
delivery_outbox, delivery_attempts, user_feedback, channel_configuration,
rule_configuration). Each worker runs under its own service account with only the roles it
needs; `raw` and `core` access is never granted to agent-path identities.

Payloads sent to any LLM provider MUST contain aggregated evidence only — no raw rows, no
PII, no credentials, no channel tokens. Untrusted text (reviews, user input) MUST be
isolated and redacted before it can reach a prompt. Tools are exposed through allowlists and
every tool call is audited.

**Isolation is conditional.** The system is not assumed to be multi-tenant. Tenant or domain
isolation is REQUIRED only when multiple organizations, business units, or otherwise
separated domains share the deployment. Where required, that separation MUST be enforced by
IAM, authorization checks, and query scoping — never by prompt instructions alone.

**MCP is conditional.** MCP is not required. If MCP is adopted, its server MUST expose only
authenticated, authorized, allowlisted tools; MUST NOT offer unrestricted SQL; MUST NOT
offer write operations against business data; and MUST audit every call.

**Human approval** gates the initial rollout of automated delivery (see Development Workflow
and Quality Gates for the relaxation path).

Rationale: the agent handles cross-product business data over an interface that is
inherently susceptible to prompt injection. Boundaries must be enforced by IAM and
validation, not by prompt wording. Mandating isolation machinery for a single-tenant
deployment buys complexity, not safety.

### V. Idempotent, Auditable Delivery

Insight delivery MUST use the transactional outbox pattern, with the transaction in
PostgreSQL:

1. Insight creation and delivery scheduling write to the outbox table **within the same
   PostgreSQL transaction**. Either both are durable or neither is.
2. An idempotent publisher reads committed outbox rows and emits the corresponding events
   to Pub/Sub. Re-publishing a row MUST NOT produce a duplicate delivery.
3. Workers consume those events and perform the deliveries, applying deduplication, retries
   with exponential backoff, timeouts, per-channel rate limits, and dead-letter handling.
   Every attempt terminates in an explicit status or a dead letter.

Insights MUST be deduplicated by fingerprint (rule_id, metric, affected_dimensions,
period_start, period_end) and subject to cooldown, per-channel daily limits, and
configurable suppression. Every request and pipeline run MUST carry a correlation ID and
emit OpenTelemetry spans across the declared stages, from `request_received` through
`channel_delivery`. No raw PII, credentials, or channel tokens are ever persisted in logs or
traces.

Rationale: a proactive system that double-sends, silently drops, or cannot explain what it
sent will be muted by its users within a week. Binding the insight and its delivery intent
to one transaction is what makes "exactly the insights we computed, delivered once" a
property of the system rather than a hope.

## Technology and Architecture Constraints

Durable requirements — changing any of these requires a constitutional amendment:

- **Runtime**: Python at or above the supported minimum version declared in the architecture
  document (currently 3.12). Static type checking, automated tests, and linting MUST run in
  CI and MUST pass before merge.
- **Reproducibility**: dependencies MUST be pinned and reproducible; schema changes MUST
  ship as versioned, ordered migrations; infrastructure MUST be provisioned as code with no
  console-only changes.
- **Warehouse**: BigQuery is the consolidated analytical source. Power BI is not part of the
  agent architecture.
- **Semantic layer**: a governed semantic layer sits between the agent and the warehouse.
  Agent-path access to business data is read-only.
- **Operational store**: PostgreSQL holds transactional state, configuration, conversations,
  orchestration checkpoints, and the outbox.
- **LLM access**: managed provider APIs behind an `LLMProvider` abstraction.
  Provider-specific code stays inside its implementation. Timeouts, bounded retries,
  rate-limit handling, and token and cost limits are MANDATORY. The abstraction MUST permit
  provider fallback, but operating multiple providers is NOT required for the MVP; a second
  provider is enabled only when availability requirements and evaluations justify the
  added complexity.
- **Agent orchestration**: a single orchestrator is the initial architecture. States,
  transitions, retries, and tool calls MUST be explicit, testable, and observable.
  Multi-agent architecture stays out of scope for the MVP and requires an amendment.

Decisions recorded as ADRs in the architecture document, changeable without amending this
constitution: the ORM, migration tool, HTTP client, linter, type checker, orchestration
framework (LangGraph is the initial choice), transformation tool, workflow scheduler,
vector store, and delivery channel implementations. Replacing any of them requires an
accepted ADR, not a constitutional amendment.

Out of scope for the MVP — adding any of these requires an amendment: Power BI integration,
model-generated unrestricted SQL, multi-agent architecture, RAG over fact rows, self-hosted
production LLM, Kubernetes, Kafka, autonomous causal claims, unlimited conversational
memory, fine-tuning.

## Development Workflow and Quality Gates

- **Eval-driven development**: behavior changes to the agent, detection, or narration MUST
  ship with or update golden datasets and graders. Regression suites cover on-demand
  accuracy (intent, metric/dimension/filter/date selection, tool selection and arguments,
  numeric and source accuracy, groundedness, abstention, access control), proactive quality
  (precision, recall, false-positive rate, duplicate rate, time to detect), and delivery
  (success rate, retry rate, dead-letter rate, duplicate delivery rate).
- **Adversarial coverage**: evaluation datasets MUST include prompt injection, unauthorized
  access, missing data, stale data, incompatible sources, insufficient sample, partial
  periods, ambiguous questions, and informal/misspelled Portuguese.
- **Rollout order** for any new detector or automated delivery: historical backtest →
  shadow mode → human review → pilot channel → high-confidence automation → progressive
  expansion. Skipping a stage requires written justification.
- **Human in the loop**: automated delivery to a channel starts behind human approval.
  Approval MAY be relaxed per channel, per insight type, and per risk level — never
  globally at once — and only after evaluation evidence supports it and the relaxation is
  approved and recorded in writing. Higher-risk autonomous delivery additionally requires
  automated claim validation (Principle III).
- **Change gates**: a change merges only when tests, linting, and type checking pass; new
  metrics carry a complete metric contract; new tools declare access level and
  authorization; data-model changes ship with pipeline assertions; schema changes ship with
  a versioned migration.

## Source of Truth Hierarchy

When artifacts disagree, precedence runs top to bottom:

1. **Constitution** — global, non-negotiable principles.
2. **Approved feature specification** — behavior and acceptance criteria.
3. **Accepted ADRs** — approved technical decisions.
4. **`docs/intelligence-agent.yaml`** — architectural baseline.
5. **Current implementation plan and tasks.**
6. **Existing implementation.**

A lower artifact MUST NOT silently override a higher one. When a conflict is found, it MUST
be resolved in the documents — by amending the constitution, revising the spec, or
recording an ADR — before the implementation proceeds. Discovering that the code already
does something else is not a resolution.

## Governance

This constitution supersedes other practices and conventions in this repository. Where a
plan, spec, ADR, or task conflicts with it, the constitution wins and the conflicting
artifact MUST be corrected.

**Amendments** require: a written rationale, an explicit version bump, an updated Sync
Impact Report in this file, and a migration note when existing behavior or data is
affected. Amendments that relax a NON-NEGOTIABLE principle or move an item out of
"Out of scope for the MVP" require explicit owner approval recorded in the pull request.

**Versioning policy** follows semantic versioning of governance impact:
- **MAJOR**: a principle is removed or redefined in a backward-incompatible way.
- **MINOR**: a principle or section is added, or guidance is materially expanded.
- **PATCH**: clarification, wording, or non-semantic refinement.

**Compliance review**: every pull request MUST state which principles it touches and how it
satisfies them. Any added complexity — a new service, a new dependency, a new agent, a
bypass of a deterministic path — MUST be justified against Principle II and the MVP scope.
Reviewers verify the change gates above before approval. Runtime development guidance lives
in `CLAUDE.md`; the architectural baseline lives in `docs/intelligence-agent.yaml`.

**Version**: 1.1.1 | **Ratified**: 2026-08-10 | **Last Amended**: 2026-08-10
