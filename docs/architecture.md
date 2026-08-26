# Architecture

Architecture Intelligence Platform (AIP) is a modular Python monolith (a single FastAPI process);
Neo4j is its only external persistent infrastructure dependency. It builds an **Architecture
Knowledge Graph** by ingesting OpenAPI/AsyncAPI/manifest documents (declared architecture) and,
optionally, OpenTelemetry traces (observed architecture), and answers questions about it either
through fixed, deterministic Cypher analyses or a read-only natural-language query layer.

## Ingestion pipeline

The pipeline is strictly staged, and each stage must fully succeed before the next runs:

```
scan -> parse -> source-level validate -> map to Canonical Model -> canonical validate
     -> reconcile/diff -> transactional graph write
```

`app/ingestion/pipeline.py` drives scanning and parsing; `app/graph/importer.py` drives
reconciliation and the write. A service's import is **atomic**: it either fully succeeds or is
entirely discarded — a partial import is never left in the graph (this is validation rule V9 /
acceptance criterion AC14 of the original PoC spec). Per-service reimport is MERGE-based and
idempotent: importing the same service twice produces the same graph state, and a relation that's
still supported by evidence from another declaring service is never wrongly deleted (see
[`evidence.md`](evidence.md) and [`graph-model.md`](graph-model.md) for the exact invariant this
guarantees).

Source adapters never write directly to Neo4j. Each adapter first maps its input into a shared
**Canonical Model** ([`canonical-model.md`](canonical-model.md)), decoupling parsers, graph
persistence, and different data sources from one another — see
[`adapter-development.md`](adapter-development.md) for what a new adapter needs to produce.

## Runtime observation pipeline

Independently of declared ingestion, `POST /v1/traces` accepts OpenTelemetry OTLP/HTTP trace
exports, resolves them against whatever is already declared in the graph, and persists observed
facts/evidence alongside the declared ones — see [`opentelemetry.md`](opentelemetry.md) for the
full contract.

## API surface

Every endpoint is mounted in `app/main.py`; each router lives in its own `app/api/*.py` module:

| Router | Prefix | Covers |
|---|---|---|
| `services.py` | `/api/services` | List/get services; per-service evidence |
| `queues.py` | `/api/queues` | List/get queues; per-queue evidence |
| `messages.py` | `/api/messages` | List/get messages |
| `evidence.py` | `/api/evidence` | List/get raw `Evidence` nodes by id |
| `analysis.py` | `/api/analysis` | Deterministic A1-A5 (senders/consumers/orphan-queue/blast-radius) |
| `runtime.py` (`runtime_router`) | `/api/runtime` | Observed relations, per-service runtime profile |
| `runtime.py` (`runtime_analysis_router`) | `/api/analysis/runtime` | O1-O5 (confirmed/observed-only/declared-only/coverage) |
| `import_api.py` | `/api/import` | Trigger a full or per-service (re)import from configured source directories |
| `query.py` | `/api/query` | Natural-language question -> deterministic analysis or validated read-only Cypher |
| `telemetry.py` | `/v1/traces` | OTLP/HTTP trace ingestion |
| `ui.py` | `/`, `/services/{id}`, `/queues/{id}`, `/query` | Minimal server-rendered HTML UI |

See [`analyses.md`](analyses.md) for what each deterministic analysis actually computes,
[`semantic-validation.md`](semantic-validation.md) for the NL-query pipeline, and
[`configuration.md`](configuration.md) for every setting that shapes this behavior.
