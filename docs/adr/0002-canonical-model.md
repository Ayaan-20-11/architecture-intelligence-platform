# 2. A shared Canonical Model decouples adapters from the graph

Status: Accepted

## Context

This project ingests architecture facts from multiple, structurally different source formats —
OpenAPI (REST providers), AsyncAPI (queue-based communication), and a hand-written Architecture
Manifest (the one thing OpenAPI can't express: who calls a REST operation). A future source
(OpenTelemetry, already added in H4/11H) needed to slot in without reworking the three existing
parsers. If each adapter wrote directly to Neo4j, every adapter would need to know the graph schema,
every graph-schema change would ripple into every adapter, and adding a new source would mean
touching persistence code that has nothing to do with the new source format.

## Decision

Every adapter maps its input into a shared, technology-independent Canonical Model
(`app/canonical/model.py`, Pydantic v2) — `Service`, `Operation`, `Queue`, `Message`, `Schema`,
`Relation`, `Provenance` — before anything is written to Neo4j. No adapter writes directly to the
graph.

## Consequences

- Parsers, graph persistence, and future data sources are decoupled from one another: the
  OpenTelemetry adapter (H4) was added without changing `openapi_adapter.py`, `asyncapi_adapter.py`,
  or `manifest_adapter.py` — exactly what this ADR predicted it should allow.
- Entity IDs are deterministic and stable (`app/canonical/ids.py`), built from stable identifiers
  (service name, method+path, queue/message name+version) and never from a local filesystem path —
  so imports from multiple repos merge conflict-free and repeated imports don't create duplicates.
  See [`canonical-model.md`](../canonical-model.md) for the exact ID formats and the specific bug
  class this prevents.
- A runtime source (OpenTelemetry) produces a parallel but distinct shape — `ObservationBatch`
  (`app/telemetry/model.py`), not `ArchitectureModel` — because runtime observation has different
  failure modes (unresolved identities, partial instrumentation) that a declared-source model
  doesn't need to represent. See [0006](0006-declared-vs-observed.md).
