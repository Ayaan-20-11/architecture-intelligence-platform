# Ingestion & Source Adapters

Three source adapters map declared architecture documents into the Canonical Model
(`app/canonical/model.py`). None of them ever writes to Neo4j directly — see
[`architecture.md`](architecture.md) for where they sit in the pipeline.

## OpenAPI adapter (`app/ingestion/openapi_adapter.py`)

Extracts the **provider** side only: service metadata, HTTP method/path, `operationId`, and
request/response schemas. It cannot know who *calls* an operation — OpenAPI documents describe
what a service offers, not who consumes it.

## AsyncAPI adapter (`app/ingestion/asyncapi_adapter.py`)

Extracts queue-based communication: queue/channel name, send/receive direction, message name and
version, payload schema, and dead-letter-queue mapping. `Queue` and `Message` are deliberately kept
as **separate entities** — queue/DLQ/transport semantics stay independent of message payload
semantics so they can be analyzed and versioned independently. Competing consumers (multiple
runtime instances of the same logical service) are not modeled as separate nodes in this static
model.

## Architecture Manifest adapter (`app/ingestion/manifest_adapter.py`)

Reads `architecture.yaml` — the only source that can close the "who calls this REST operation" gap,
since OpenAPI alone only describes providers. The manifest is deliberately minimal: it must only
contain information not already reliably derivable from OpenAPI/AsyncAPI. It resolves each declared
call against a pre-built `operation_index` (built once, in `app/ingestion/pipeline.py`, from every
scanned service's real `Operation.id` values) — the manifest adapter itself never constructs an
operation id independently, so it can never drift out of sync with however operation ids are
actually minted.

## Runtime observation adapter

Independently of the three above, `app/telemetry/adapter.py` maps OpenTelemetry spans into observed
facts. It's architecturally a different kind of adapter — it produces an `ObservationBatch`
(possibly-new entities + evidence-backed facts + unresolved observations), not an
`ArchitectureModel` — see [`opentelemetry.md`](opentelemetry.md) for its full contract and
[`adapter-development.md`](adapter-development.md) for how it fits the general extension point.
