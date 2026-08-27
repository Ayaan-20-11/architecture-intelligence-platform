# Architecture Intelligence Platform

Build an evidence-backed architecture knowledge graph from OpenAPI, AsyncAPI and OpenTelemetry —
and discover where declared and observed architecture diverge.

![Pipeline: declared sources (OpenAPI, AsyncAPI, architecture.yaml) and observed OpenTelemetry traces both feed the Canonical Architecture Model, which imports into Neo4j, which serves deterministic Cypher analyses and read-only natural-language query.](images/pipeline-light.svg#gh-light-mode-only)
![Pipeline: declared sources (OpenAPI, AsyncAPI, architecture.yaml) and observed OpenTelemetry traces both feed the Canonical Architecture Model, which imports into Neo4j, which serves deterministic Cypher analyses and read-only natural-language query.](images/pipeline-dark.svg#gh-dark-mode-only)

## Why?

Architecture documentation drifts from reality the moment it's written by hand. AIP builds its
knowledge graph automatically from artifacts that already exist and are already kept up to date as
part of normal development — OpenAPI/AsyncAPI specs, a minimal manifest for the one thing they can't
express (who calls what), and, optionally, real OpenTelemetry traffic — so every fact in the graph
traces back to real evidence, never to a stale diagram someone forgot to update.

## Features

**Ingestion**
- ✓ OpenAPI ingestion
- ✓ AsyncAPI queue topology
- ✓ Architecture manifest support (the one place declared REST *callers* come from)
- ✓ Evidence / provenance on every fact, independently for declared and observed evidence

**Graph & analysis**
- ✓ Neo4j architecture knowledge graph
- ✓ Deterministic dependency analyses (queue senders/consumers, orphan queues)
- ✓ Architecture blast radius (mixed sync + async traversal)
- ✓ Semantic Cypher validation (a hard allowlist gate, not an LLM guardrail)
- ✓ Natural-language architecture queries — deterministic where possible, validated read-only Cypher otherwise

**Runtime telemetry (OpenTelemetry)**
- ✓ Runtime discovery of undeclared operations, services and queues
- ✓ Cross-batch HTTP correlation (a CLIENT and SERVER span arriving in separate OTLP requests still
  correlate to one observed dependency)
- ✓ Partial-instrumentation tolerance (a stable one-sided observation still counts, an unreliable one
  never gets guessed)
- ✓ Declared vs. observed architecture, and architecture drift detection
- ✓ Telemetry coverage qualification for negative findings

See [`docs/opentelemetry.md`](docs/opentelemetry.md) for what the `CLIENT_SERVER`/`CLIENT_ONLY`/
`SERVER_ONLY`/`UNRESOLVED` correlation modes above actually mean.

## Declared vs Observed

Every relation in the graph carries evidence, and its evidence can be `DECLARED` (from a spec/
manifest), `OBSERVED` (from real telemetry), or both. That's what turns into a status:

| Status | Meaning |
|---|---|
| `CONFIRMED` | Declared **and** observed |
| `OBSERVED_ONLY` | Observed, but never declared anywhere — an undocumented real dependency |
| `NOT_OBSERVED_IN_WINDOW` | Declared, but not seen in this window — never "obsolete"/"unused"/"dead", just not observed *yet or here* |

Removing a stale declaration never deletes a relation that still has observed evidence — it degrades
`CONFIRMED` to `OBSERVED_ONLY` instead. See [`docs/graph-model.md`](docs/graph-model.md) for the
exact invariant this guarantees and why it matters.

## Quick Start

Requires Docker and Docker Compose (Python 3.13 only if you want to run it outside a container):

```bash
git clone <repository>
cd architecture-intelligence
docker compose up
```

Then open <http://localhost:8000>. `config.yaml` already points at this repo's `examples/` fixture
services, so `POST /api/import` works immediately against them. See
[`docs/development.md`](docs/development.md) for running locally without Docker, the test suite, and
linting.

## Example

The bundled `examples/` fixture is a small, fully synthetic four-service landscape:

```text
OrderService
   |
   +---- REST ----> ProductService
   |
   +---- SENDS ---> payment-q
                        |
                        v
                  PaymentService
                        |
                        v
                    invoice-q
                        |
                        v
                  InvoiceService
```

`unused-q` (a sender with no consumer) and `unknown-producer-q` (a consumer with no known sender) are
included specifically to exercise the orphan-queue analyses. `POST /api/import` loads all of it in
one call.

## Architecture

A modular Python monolith (a single FastAPI process); Neo4j is the only external persistent
dependency. Ingestion is a strictly staged pipeline — `scan -> parse -> source-validate -> map to
canonical model -> canonical-validate -> reconcile/diff -> transactional graph write` — where a
service's import either fully succeeds or is entirely discarded, never left partial. Source adapters
never write to Neo4j directly; they all map into one shared Canonical Model first. Full details,
including the graph/evidence model and every API route: [`docs/architecture.md`](docs/architecture.md).

## Deterministic Analyses

Five fixed, parameterized Cypher analyses over declared architecture (queue senders/consumers,
orphan queues, mixed-architecture blast radius) plus five over declared-vs-observed runtime data
(what was actually observed, what's confirmed, what's observed-only, what's declared-only, and
per-service telemetry coverage). None of these involve the LLM — see
[`docs/analyses.md`](docs/analyses.md) for the full list and what each one answers.

## OpenTelemetry

`POST /v1/traces` is AIP's OTLP/HTTP ingestion boundary. It resolves incoming spans against whatever
is already declared in the graph and persists observed facts and evidence alongside the declared
ones — never inventing a fact it can't trace back to real telemetry.

**AIP is an additional telemetry consumer, not the primary observability backend.** It must never be
the only thing an OTel Collector forwards to, and its own availability must never affect an
application's normal observability:

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

Failure isolation, buffering, and retry behavior belong in the Collector/deployment configuration —
`/v1/traces` does no buffering or retry of its own, by design. Full attribute allowlist, correlation
modes, and coverage-qualification model: [`docs/opentelemetry.md`](docs/opentelemetry.md).

### Runtime demo

```bash
docker compose -f docker-compose.demo.yml up --build
```

Brings up `architecture-intelligence` + `neo4j` (as above) plus an `otel-collector` service and a
`traffic-generator` that emits realistic synthetic OTLP traces for the `examples/` fixture topology
every few seconds (see `examples/runtime-demo/traffic_generator.py`'s docstring for why this repo
generates spans directly rather than running real HTTP services). The Collector forwards every batch
to AIP's `/v1/traces` and, in parallel, to a `debug` exporter — standing in for "an additional
tracing backend" in the topology above.

Once it's running, `POST /api/import` to declare the fixture topology, then watch
`GET /api/runtime/relations?environment=demo` fill in with `OBSERVED`/`CONFIRMED` relations as the
generator's traffic lands — a live demonstration of the `DECLARED + OBSERVED -> CONFIRMED` and, on a
later reimport with a declaration removed, `-> OBSERVED_ONLY` transition described above. The
generator also emits an undeclared `OrderService -> LegacyPricingService` call (surfacing as
`OBSERVED_ONLY` on its own, with no reimport needed) and periodically splits one CLIENT/SERVER pair
across two OTLP requests to demonstrate cross-batch correlation. The same states are also visible in
the web UI at <http://localhost:8000/> — the Service Explorer shows declared vs. observed side by
side, and <http://localhost:8000/query> answers questions like "Which dependencies are observed but
undocumented?" without needing an LLM configured. See
[`examples/runtime-demo/README.md`](examples/runtime-demo/README.md) for the full step-by-step
walkthrough — every state (`CONFIRMED`, `OBSERVED_ONLY`, `NOT_OBSERVED_IN_WINDOW`) and the
reconciliation scenario, each with exact `curl` commands and expected results.

## Natural Language Queries

`POST /api/query` answers a plain-language question either by routing it to an existing
deterministic analysis (above) or, if it doesn't recognize the question, by generating Cypher that
must pass a strict read-only allowlist validator before it ever touches Neo4j. The LLM never holds
write credentials and its Cypher is always shown back alongside the answer for traceability. Fully
optional — the platform works completely without any LLM provider configured. See
[`docs/semantic-validation.md`](docs/semantic-validation.md).

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — pipeline, API surface
- [`docs/canonical-model.md`](docs/canonical-model.md) — entities and deterministic ids
- [`docs/graph-model.md`](docs/graph-model.md) — relations, fact/evidence invariants, observed `PROVIDES`
- [`docs/evidence.md`](docs/evidence.md) — provenance, the `Evidence` node, correlation modes
- [`docs/ingestion.md`](docs/ingestion.md) — the three declared source adapters
- [`docs/analyses.md`](docs/analyses.md) — A1-A5 and O1-O5
- [`docs/semantic-validation.md`](docs/semantic-validation.md) — the NL query pipeline
- [`docs/opentelemetry.md`](docs/opentelemetry.md) — runtime observation, attribute allowlist, coverage
- [`docs/configuration.md`](docs/configuration.md) — every setting and its default
- [`docs/security-model.md`](docs/security-model.md) — trust boundaries
- [`docs/development.md`](docs/development.md) — local dev, tests, linting
- [`docs/adapter-development.md`](docs/adapter-development.md) — extending AIP with a new source
- [`docs/adr/`](docs/adr/) — Architecture Decision Records: why Neo4j, why a Canonical Model, why
  the LLM is read-only and never a source of truth, and more
- [`docs/specifications/`](docs/specifications/) — the original design specifications, as a
  traceable history of how the platform got here
- [`ROADMAP.md`](ROADMAP.md) / [`CHANGELOG.md`](CHANGELOG.md) — where this is headed, and what's
  shipped so far

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup, test/lint/format commands, and the
adapter contribution guide. Questions and ideas go in [Discussions](../../discussions); bugs and
feature requests use the issue templates. Security vulnerabilities should never be reported as
public issues — see [`SECURITY.md`](SECURITY.md). This project follows the
[Contributor Covenant](CODE_OF_CONDUCT.md).

## Project Status

The original PoC (Canonical Model, OpenAPI/AsyncAPI/manifest ingestion, Neo4j graph, five
deterministic analyses, LLM query layer), the H1-H4 hardening/OpenTelemetry iterations, the full 11H
runtime-correctness roadmap (evidence reconciliation, cross-batch correlation, partial
instrumentation, observed provider relations, coverage qualification, the Collector-based demo), and
H5 (open-source readiness — this document, `docs/`, licensing, CI, community files) are all complete.
See [`ROADMAP.md`](ROADMAP.md) for what's shipped and what's planned next.

## License

Licensed under the Apache License, Version 2.0.
See [LICENSE](LICENSE). Third-party dependency licenses: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
