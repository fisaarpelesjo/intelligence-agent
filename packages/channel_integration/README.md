# channel-integration

Governed multichannel integration — Feature `004`.

The authenticity, identity, normalisation, preservation and transport boundary between an external
channel and the governed core. It adds no analytical capability: `001` decides whether a question may be
answered, `002` executes a permitted request, `003` interprets a question and assembles a
channel-agnostic answer, and this package moves bytes in and governed bytes back out.

**A channel is a transport, never an authority.** No contract field, parameter or header can assert
authenticity, identity, tenant, language, reference date, authorisation or a governed limit.

## State

Phase A only: contracts, the 31-code channel reason-code namespace, the six audit stages, the governed
content shapes, the message registry and the readiness guard. Nothing verifies, renders or delivers yet —
those are Phases B and C.

Every channel is disabled and fail-closed while `D-22` – `D-25`, `D-26` – `D-31` are undeclared, and the
interaction port has no constructible implementation until Phase D0 ships the entry point ADR 0017
authorized. Aggregated external readiness is **NONE**.

## Not in this package

No HTTP listener, socket, server, resident process, scheduler, queue or deploy artifact (`FR-106`); the
inbound transport surface is platform-owned (`D-30`, ADR 0020). No provider SDK, credential, endpoint,
token or secret. No warehouse, SQL, catalog, compiler, executor or policy resolver.

See `specs/004-multichannel-integration/` for the governing specification, plan and contracts.
