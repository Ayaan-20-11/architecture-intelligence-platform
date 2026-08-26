# Architecture Intelligence Platform — PoC

Proves that an Architecture Knowledge Graph can be built automatically from existing OpenAPI and
AsyncAPI specifications, unifying synchronous REST communication and asynchronous queue communication
in one Neo4j-backed model, with deterministic Cypher analyses and a read-only LLM query layer on top.

- Full design: `Architecture_Intelligence_Platform_PoC_Specification_Python.pdf`
- Engineering task breakdown: `IMPLEMENTATION_PLAN.md`
- Guidance for AI coding agents working in this repo: `CLAUDE.md`
- Final PoC review (AC1–AC15, success measures, known gaps): `POC_REVIEW.md`

## Status

All 9 iterations of `IMPLEMENTATION_PLAN.md` complete: canonical model, OpenAPI/AsyncAPI/manifest
adapters, ingestion pipeline + validation, Neo4j importer, the five standard analyses, a FastAPI app
with a minimal server-rendered UI, and the LLM query subsystem (OpenAI-backed). See `POC_REVIEW.md` for
the acceptance-criteria walkthrough and two known open items (live LLM round-trip pending API credits,
provenance captured but not yet persisted to the graph).

## Development

```bash
uv sync                                # install dependencies
uv run pytest tests/unit               # fast unit tests (no Neo4j needed)
uv run pytest tests/integration        # Testcontainers-backed tests (needs Docker)
uv run ruff check .                    # lint
uv run ruff format .                   # format
```

Copy `.env.example` to `.env` and fill in `NEO4J_PASSWORD` and `OPENAI_API_KEY` (the LLM query
subsystem is disabled with a friendly message if `OPENAI_API_KEY` is unset). To run the app locally
against a Neo4j you start yourself:

```bash
export NEO4J_PASSWORD=devpassword     # and NEO4J_USER/OPENAI_API_KEY as needed
uv run uvicorn app.main:app --reload
```

`config.yaml` (spec §17.1 shape) points `sources.directories` at `examples/`, so `POST /api/import`
works out of the box against this repo's fixture services. Or run the full stack via Docker Compose:

```bash
docker compose up
```

## Runtime telemetry (OpenTelemetry)

`POST /v1/traces` is AIP's OTLP/HTTP ingestion boundary (protobuf `ExportTraceServiceRequest`,
`Content-Type: application/x-protobuf`) - the only valid way to send AIP runtime observations. It
resolves incoming spans against whatever's already declared in the graph and persists observed
facts/evidence alongside the declared ones, never inventing a fact it can't trace back to real
telemetry.

**AIP is an additional telemetry consumer, not the primary observability backend.** It must never
be the only thing an OTel Collector forwards to, and its own availability must never affect an
application's normal observability. The recommended production topology fans a Collector's export
out to both:

```text
Applications
     |
     v
OTel Collector
     |
     +----> Primary observability backend (Jaeger, Tempo, a vendor APM, ...)
     |
     +----> Architecture Intelligence Platform
```

Failure isolation, buffering, and retry behavior belong in the Collector/deployment configuration
(the exporter queue, sending-queue persistence, retry-on-failure), not in AIP - `/v1/traces` does
no buffering or retry of its own, by design.

### Runtime demo

```bash
docker compose -f docker-compose.demo.yml up --build
```

Brings up `architecture-intelligence` + `neo4j` (as above) plus an `otel-collector` service
(config: `examples/runtime-demo/otel-collector-config.yaml`) and a `traffic-generator` that emits
realistic synthetic OTLP traces for the `examples/` fixture topology (order-service calling
product-service, order-service sending to payment-q, payment-service relaying to invoice-q) every
few seconds - see `examples/runtime-demo/traffic_generator.py`'s docstring for why this repo
generates spans directly rather than running real HTTP services. The Collector forwards every
batch to AIP's `/v1/traces` and, in parallel, to a `debug` exporter that prints spans to its own
stdout - standing in for "an additional tracing backend" in the topology diagram above.

Once it's running, `POST /api/import` (as above) to declare the fixture topology, then watch
`GET /api/runtime/relations?environment=demo` fill in with `OBSERVED`/`CONFIRMED` relations as the
generator's traffic lands.
