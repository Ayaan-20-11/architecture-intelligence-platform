# Canonical Model

Source adapters (OpenAPI, AsyncAPI, Architecture Manifest, and — for runtime data — the
OpenTelemetry adapter) never write directly to Neo4j. Each first maps its input into a shared
**Canonical Model** (`app/canonical/model.py`, Pydantic v2), decoupling parsers, graph persistence,
and different data sources from one another.

## Entities (`app/canonical/model.py`)

| Entity | Key fields |
|---|---|
| `Service` | `id`, `name`, `version` |
| `Operation` | `id`, `service_id`, `operation_id` (the OpenAPI `operationId`, optional), `method`, `path`, `request_schema_ids`, `response_schema_ids` |
| `Queue` | `id`, `name`, `protocol`, `namespace`, `queue_type` |
| `Message` | `id`, `name`, `version`, `schema_id` |
| `Schema` | `id`, `name`, `version`, `format`, `canonical_hash` (a content hash used to detect payload drift) |
| `Relation` | `type`, `source_id`, `target_id`, `evidence_ids` |
| `Provenance` / `Evidence` | see [`evidence.md`](evidence.md) |

`ArchitectureModel` is the container all of the above are collected into and passed between
pipeline stages: `services`, `operations`, `queues`, `messages`, `schemas`, `relations`,
`provenance`.

## Deterministic IDs (`app/canonical/ids.py`)

Every entity id is a stable, deterministic string, never a database-generated surrogate key and
never dependent on a local filesystem path — this is what lets imports from multiple repositories
merge conflict-free and lets a repeated import of the same source not create duplicates.

| Id kind | Format | Example |
|---|---|---|
| Service | `service:<slug>` or `service:<namespace>:<slug>` | `service:order-service` |
| Operation | `operation:<full-service-id>:<METHOD>:<path>` | `operation:service:product-service:GET:/products/{id}` |
| Queue | `queue:<name>` or `queue:<namespace>:<name>` | `queue:payment-q` |
| Message | `message:<name>` or `message:<name>:<version>` | `message:PaymentRequested:v2` |
| Schema | `schema:<name>` or `schema:<name>:<version>` | `schema:PaymentRequested:v2` |
| Evidence (declared) | `evidence:<source_type>:<service_slug>[:<revision>]` | `evidence:manifest:order-service` |
| Evidence (observed) | `evidence:otel:<environment>:<day>:<fact-hash>` | `evidence:otel:production:2026-08-26:b1d283d583bd` |

One detail worth calling out because it was the source of a real bug this project fixed
(11H-D): the `operation:` id is **always built from the full opaque service id** (e.g.
`service:product-service`), never from the bare source-layer slug (e.g. `product-service`). Every
place that mints an operation id — the OpenAPI adapter for declared operations
(`app/ingestion/openapi_adapter.py`) and the runtime resolver for a route it discovers but has
never seen declared (`app/telemetry/operation_resolver.py`) — must agree on this convention, or a
runtime-discovered operation and its later real OpenAPI declaration silently land on two different
graph nodes instead of reconciling onto one. See [`graph-model.md`](graph-model.md) for the
resulting `OBSERVED PROVIDES` reconciliation guarantee this enables.
