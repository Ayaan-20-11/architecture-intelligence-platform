# Roadmap

## Versioning

[Semantic Versioning](https://semver.org/). The first public release is `v0.1.0` (or
`v0.1.0-alpha.1` — see `IMPLEMENTATION_PLAN.md`'s 12F entry for that call).

Not yet guaranteed stable pre-1.0 — expect breaking changes on a minor version bump:

- Canonical Model (`app/canonical/model.py`)
- REST API surface
- Graph Schema (node labels, relationship types/properties)
- Adapter SPI (`docs/adapter-development.md`'s `Protocol` contracts)
- Configuration format (`config.yaml`)

## v0.1 — shipped

- ✓ OpenAPI adapter
- ✓ AsyncAPI adapter
- ✓ Evidence (persisted `Evidence`/`Provenance`, queryable via `/api/evidence`)
- ✓ Five deterministic analyses (queue senders/consumers, orphan queues, mixed-architecture blast
  radius)
- ✓ Semantic validation (Graph Schema + Semantic Query Validator for the LLM layer)
- ✓ OpenTelemetry (OTLP ingestion, service/environment resolution, REST + queue observation,
  evidence aggregation, a Collector-based demo)
- ✓ Declared vs observed (`CONFIRMED`/`OBSERVED_ONLY`/`NOT_OBSERVED_IN_WINDOW`, with the 11H
  evidence-reconciliation invariant and cross-batch HTTP correlation)

## v0.2 — planned

- Kubernetes discovery (declared-architecture source: Deployments/Services as an additional
  `ArchitectureSourceAdapter`)
- Additional adapters (candidates: gRPC/protobuf service definitions, Kafka Connect configs — see
  the "New adapter proposal" issue template for the extension-point contract)
- Improved runtime analysis (deeper mixed-architecture blast radius over observed edges, richer
  telemetry-coverage classification)

## Future

- Architecture trajectories (how the declared/observed graph changes over time, not just a single
  snapshot)
- Causal runtime flow analysis (beyond pairwise CLIENT/SERVER and send/receive correlation)
- GraphRAG (retrieval over the graph as LLM context, distinct from today's Cypher-generation-only
  query layer)
- Architecture Wiki (auto-generated narrative documentation from the graph)
- Backstage integration (surfacing the Architecture Knowledge Graph as a Backstage catalog/plugin)

None of the above are committed dates — this is a direction, not a schedule. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) if you want to help with any of it, and open an issue before
starting significant work on a v0.2/Future item so it doesn't go to waste.
