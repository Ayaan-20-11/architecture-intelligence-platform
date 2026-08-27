# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository currently contains **no source code** — only the design document
`Architecture_Intelligence_Platform_PoC_Specification_Python.pdf`. There is no `pyproject.toml`,
no application code, no tests, and no git history yet. Treat this as a greenfield implementation:
the spec below is the authoritative design to implement against, not a description of existing code.

See `docs/` (architecture, canonical model, graph/evidence model, ingestion, analyses, adapter
development) and `ROADMAP.md` for the current state of the system before re-deriving a plan from the
PDF.

Because no build system exists yet, there are no real build/lint/test commands to document. Once a
`pyproject.toml` is created, it should follow the stack in the spec (Section 3): Python 3.13, FastAPI,
Pydantic v2, PyYAML, `jsonschema`, the official `neo4j` Python driver, and `pytest` + `testcontainers`
for integration tests. Update this file with the actual commands (install, lint, `pytest`, single-test
invocation, `docker compose up`) as soon as they exist.

## What this project is

The Architecture Intelligence Platform PoC proves that an **Architecture Knowledge Graph** can be
built automatically from existing OpenAPI and AsyncAPI specifications, unifying synchronous REST
communication and asynchronous queue communication in one model.

Core hypothesis / data flow:

```
OpenAPI + AsyncAPI + minimal architecture.yaml manifest
    -> Canonical Architecture Model (technology-independent, Pydantic)
    -> Neo4j (property graph)
    -> Cypher analyses (deterministic)  +  LLM query (read-only NL -> Cypher -> explanation)
```

The graph is the single source of truth. Standard architecture analyses run as fixed, parameterized
Cypher queries — no LLM involved. The LLM's *only* job is translating natural-language questions into
validated, read-only Cypher and explaining the resulting rows; it is never the knowledge base itself
and can never write to the graph.

Explicitly out of scope for this PoC: Kubernetes/cloud discovery, OpenTelemetry/runtime traces, vector
DB / document RAG, ADR/ticket/source-code analysis, auto-generated LLM wiki, team ownership graph,
CI/CD policy gates, full Promise Theory / Semantic Spacetime modeling.

## Architecture

### Pipeline

The system is a modular Python monolith (single FastAPI process); Neo4j is the only external
persistent infrastructure dependency. The ingestion pipeline is strictly staged and each stage must
fully succeed before the next runs — **a partial import must never be left in the graph**:

```
scan -> parse -> source-level validate -> map to Canonical Model -> canonical validate
     -> reconcile/diff -> transactional graph write
```

A service's import is atomic: it either fully succeeds or is entirely discarded (this is validation
rule V9 / acceptance criterion AC14).

### Canonical Architecture Model

Source adapters (OpenAPI, AsyncAPI, Architecture Manifest) never write directly to Neo4j. Each adapter
first maps its input into a **shared Canonical Model** (Pydantic v2), decoupling parsers, graph
persistence, and future data sources (e.g. OpenTelemetry post-PoC) from one another.

Core entities: `Service`, `Operation` (REST), `Queue`, `Message`, `Schema`, `Relation`, `Provenance`.

Entity IDs are stable, deterministic, and must not depend on local repository paths, so imports from
multiple repos merge conflict-free and repeated imports don't create duplicates:

```
service:order-service
operation:product-service:GET:/products/{id}
queue:asb:commerce:payment-q
message:PaymentRequested:v2
schema:PaymentRequested:v2
```

### Source adapters

- **OpenAPI adapter** — extracts the *provider* side only (service metadata, HTTP method/path,
  operationId, request/response schemas). It cannot know who *calls* an operation.
- **AsyncAPI adapter** — extracts queue-based communication: queue/channel name, send/receive
  direction, message name+version, payload schema, DLQ mapping. Queue and Message are deliberately
  **separate entities** from Schema — queue/DLQ/transport semantics must stay independent of message
  payload semantics so they can be analyzed and versioned independently. Competing consumers (multiple
  runtime instances of the same logical service) are *not* modeled as separate nodes in this static PoC.
- **Architecture Manifest** (`architecture.yaml`) — the only way to close the "who calls this REST
  operation" gap, since OpenAPI alone only describes providers. The manifest must only contain
  information not already reliably derivable from OpenAPI/AsyncAPI (e.g. future versions may derive
  `CALLS` from OpenTelemetry or client code instead).

### Neo4j graph model

Node labels: `Service`, `Operation`, `Queue`, `Message`, `Schema`, `Evidence`.

`Evidence` (added post-PoC, Iteration 10A / hardening spec §4) persists what was previously only an
in-memory `Provenance` record: `id`, `source_type`, `source_file`, `source_revision`, `evidence_type`.
Every relationship below also carries an `evidence_ids: list[str]` property naming the `Evidence.id`(s)
that declared it — there is no direct graph edge from a relationship to `Evidence`; look up the IDs and
`MATCH (e:Evidence) WHERE e.id IN r.evidence_ids`. Queryable via `GET /api/evidence`,
`GET /api/evidence/{id}`, `GET /api/services/{id}/evidence`, `GET /api/queues/{id}/evidence` — this is
what makes AC13 (traceable provenance) fully met rather than only produced-but-unpersisted.

| Relation | From -> To | Meaning |
|---|---|---|
| `PROVIDES` | Service -> Operation | REST provider |
| `CALLS` | Service -> Operation | REST caller |
| `REQUEST_SCHEMA` / `RESPONSE_SCHEMA` | Operation -> Schema | REST payloads |
| `SENDS` | Service -> Queue | async sender |
| `RECEIVES_FROM` | Service -> Queue | async consumer |
| `CARRIES` | Queue -> Message | message type on queue |
| `CONFORMS_TO` | Message -> Schema | message payload schema |
| `DEAD_LETTERS_TO` | Queue -> Queue | DLQ relationship |

Dependency semantics (Appendix A of the spec):
- Sync: `A -[:CALLS]-> Operation <-[:PROVIDES]- B` means A synchronously depends on B.
- Async: `A -[:SENDS]-> Queue <-[:RECEIVES_FROM]- B` means a message flow A -> Queue -> B.

Import strategy: MERGE-based, idempotent, per-service full reimport. All `DECLARED` facts whose
provenance belongs to a given service are replaced in one transaction; globally shared entities
(Queues, Messages, Schemas, Evidence) are merged via stable IDs and only removed once no provenance
references them anymore. A relation declared by multiple services (e.g. a shared `CARRIES` edge) keeps
accumulating each contributor's evidence independently, and only loses one contributor's evidence when
that specific service stops declaring the relation.

Derived relations like `SYNC_DEPENDS_ON`/`ASYNC_FLOW_TO` are intentionally treated as **computed views**,
not materialized/stored facts, to keep the graph free of redundant truths.

### Analysis engine

Five deterministic, parameterized Cypher analyses (no LLM):
- **A1** senders of a queue, **A2** consumers of a queue
- **A3** queues with a sender but no consumer, **A4** queues with a consumer but no known sender
- **A5** mixed-architecture blast radius — traverses both `CALLS`/`PROVIDES` (sync) and
  `SENDS`/`RECEIVES_FROM` (async) edges, default max traversal depth 5 (configurable)

### LLM query subsystem

Pipeline: `Question -> Cypher generation -> Cypher validator -> read-only Neo4j execution -> rows + provenance -> LLM explanation`.

Key components (see intended module layout below): `ArchitectureQuestionService` orchestrates the
flow; `CypherGenerator` produces Cypher from the question + fixed graph schema; `CypherValidator`
enforces an allowlist + depth/result limits; `ReadOnlyGraphExecutor` runs against a read-only Neo4j
user; `AnswerComposer` builds the answer strictly from result rows + provenance (never invents facts).

Only `MATCH`, `OPTIONAL MATCH`, `WHERE`, `WITH`, `RETURN`, `ORDER BY`, `LIMIT` are permitted.
`CREATE`, `DELETE`, `DETACH DELETE`, `SET`, `REMOVE`, `MERGE`, `DROP`, `LOAD CSV`, `CALL` are forbidden
at the validator level — the LLM must never be able to mutate the graph (AC12) and never gets direct
access to Neo4j credentials. Default limits: max traversal depth 5, max 100 result rows. The generated
Cypher is shown to the user for traceability. Use a provider-abstraction interface so the PoC isn't
locked to one LLM vendor.

### Provenance

Every architecture fact must carry `Provenance` (`source_type`: OPENAPI|ASYNCAPI|MANIFEST,
`source_file`, `source_revision`, `evidence_type`). Only `evidence_type: DECLARED` (derived from
spec/manifest) is populated in this PoC; `OBSERVED` (runtime/OpenTelemetry) and `INFERRED`
(documents/LLM/rules) are reserved for later phases. The LLM answer layer may only state things whose
underlying graph facts have traceable provenance.

## Intended repository structure

The spec (Section 22) prescribes this layout for the implementation — follow it when scaffolding the
project so structure matches the design docs:

```
app/
  main.py, settings.py
  canonical/        model.py, ids.py
  ingestion/         scanner.py, openapi_adapter.py, asyncapi_adapter.py, manifest_adapter.py
  provenance/        model.py
  validation/        source_validation.py, canonical_validation.py
  graph/             repository.py, importer.py, reconciliation.py, schema.py
  analysis/          queues.py, dependencies.py, blast_radius.py
  ai/                question_service.py, provider.py, cypher_generator.py, cypher_validator.py, answer_composer.py
  api/               services.py, queues.py, messages.py, analysis.py, import_api.py, query.py, evidence.py
tests/
  unit/, integration/, fixtures/
examples/
  order-service/, product-service/, payment-service/, invoice-service/
```

`examples/` holds the reference test fixture landscape used across unit/integration tests: OrderService
calls ProductService and sends to `payment-q`; ProductService only provides `getProduct`; PaymentService
receives `payment-q` and sends `invoice-q`; InvoiceService only receives `invoice-q`. Additional fixtures
should include `unused-q` (sender, no consumer) and `unknown-producer-q` (consumer, no known sender) to
exercise analyses A3/A4.

## Design decisions worth knowing (from spec Appendix B)

- Python + FastAPI monolith chosen over microservice-splitting to minimize PoC operational overhead.
- Neo4j chosen for direct modeling of typed relationships and native Cypher traversal/impact analysis.
- Queue and Message are always separate entities/nodes — never conflate transport concerns with
  payload/schema concerns.
- The Architecture Manifest exists solely to supply REST caller info that OpenAPI cannot express.
- LLM access is read-only by design, permanently — this is a hard architectural constraint, not a
  temporary PoC shortcut.
- OpenTelemetry integration (DECLARED vs OBSERVED comparison) is the planned first post-PoC extension;
  the Canonical Model is deliberately designed so adding it won't require reworking the OpenAPI/AsyncAPI
  adapters.

## Reference

Full spec: `Architecture_Intelligence_Platform_PoC_Specification_Python.pdf` (in repo root). Consult it
directly for exact Cypher query text (Section 13), full Pydantic reference model (Section 4.2), all 21
acceptance criteria (Section 21), and the 9-iteration implementation plan (Section 23).
