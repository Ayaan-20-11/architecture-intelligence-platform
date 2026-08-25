# Implementation Plan — Architecture Intelligence Platform PoC

Source of truth: `Architecture_Intelligence_Platform_PoC_Specification_Python.pdf` (repo root). This
document turns the spec's 9-iteration outline (Section 23) into concrete, file-level engineering tasks.
Each task cites the spec section it implements and, where relevant, which acceptance criteria (AC1–AC15,
§21) or validation rules (V1–V9, §10) it satisfies.

## Tooling decisions (not dictated by the spec)

The spec leaves a few engineering choices open; these are the calls made for this implementation, each
with its rationale:

| Decision | Choice | Why |
|---|---|---|
| Package/dependency manager | [`uv`](https://docs.astral.sh/uv/) | Already available in this environment; can install/pin Python 3.13 itself even though system Python is 3.12; works cleanly with `pyproject.toml` as required by spec §3. |
| Linter/formatter | `ruff` | Spec §3's tech table names no linter; ruff is a fast, low-overhead default for a Python PoC. |
| Minimal UI rendering (§16 explicitly allows either) | Server-rendered HTML via FastAPI + Jinja2 | Avoids a second (React/Node) build toolchain for a UI the spec itself calls "not core to the PoC." |
| LLM provider (§15.5 requires a swappable interface but doesn't pick a vendor) | OpenAI (gpt-4o-mini) | First concrete implementation behind the required provider abstraction; started as Anthropic Claude, switched to OpenAI in Iteration 8 at the user's request. |

**Docker status:** available (Docker 29.7.2, Compose v5.3.1; `docker ps` succeeds). Iterations 5–6, which
need a real Neo4j for their integration tests (Testcontainers per §20.2), are no longer blocked.

One session-specific quirk: the `michael` user was added to the `docker` group after this shell session
started, so group membership hasn't propagated to the persistent shell yet. Until a fresh login/WSL
session picks it up, wrap Docker commands as `sg docker -c "<command>"` (e.g.
`sg docker -c "docker compose up -d"`) rather than calling `docker`/`docker compose` directly, or they'll
fail with a socket permission error. Testcontainers (used from `pytest`) also needs this — either launch
pytest itself via `sg docker -c "uv run pytest tests/integration"`, or start a fresh shell so plain
`docker ps` works unwrapped.

## Iteration 0 — Bootstrapping
*(New — not an explicit spec iteration, but required before Iteration 1 can start.)*

- `git init` + `.gitignore` (Python bytecode, `.venv`, `uv.lock` policy, local Neo4j data volumes).
- `uv init --python 3.13`, then:
  - `uv add fastapi "uvicorn[standard]" "pydantic>=2" pyyaml jsonschema neo4j openai jinja2`
  - `uv add --dev pytest pytest-asyncio testcontainers httpx ruff`
- Create the repo skeleton exactly as specified in §22:
  ```
  app/{canonical,ingestion,provenance,validation,graph,analysis,ai,api}/
  tests/{unit,integration,fixtures}/
  examples/{order-service,product-service,payment-service,invoice-service}/
  ```
- `Dockerfile` + `docker-compose.yml` per §17.3 (written now even though it can't run locally yet here).
- Minimal `README.md`: project name, one-line purpose, pointer to the spec PDF and this plan.

## Iteration 1 — Canonical Model + stable IDs + fixtures
Spec §4, §4.2, §4.3. **Exit criterion (spec):** models validate the example architecture.

- `app/provenance/model.py` — `Provenance` (`source_type`: OPENAPI\|ASYNCAPI\|MANIFEST, `source_file`,
  `source_revision`, `evidence_type` default `"DECLARED"`) per §9.
- `app/canonical/model.py` — `Direction`, `Service`, `Operation`, `Queue`, `Message`, `Schema`,
  `Relation{type, source_id, target_id}`, `ArchitectureModel`. Use the Pydantic v2 snippet in §4.2
  verbatim; import `Provenance` from the module above instead of redefining it.
- `app/canonical/ids.py` — deterministic ID builders matching §4.3 exactly:
  `service:{id}`, `operation:{service}:{METHOD}:{path}`, `queue:{namespace}:{name}`,
  `message:{name}:{version}`, `schema:{name}:{version}`. Must never depend on filesystem/repo path.
- `tests/fixtures/` — OpenAPI/AsyncAPI/manifest YAML for the 4-service landscape from §20.3
  (OrderService, ProductService, PaymentService, InvoiceService), plus the two extra queue fixtures
  required by §21: `unused-q` (sender, no consumer) and `unknown-producer-q` (consumer, no known sender).
- `tests/unit/test_ids.py`, `tests/unit/test_canonical_model.py` — construct the full example
  `ArchitectureModel` in memory from fixtures and assert it validates.

## Iteration 2 — OpenAPI adapter
Spec §6. **Exit criterion:** REST operations/schemas correctly generated.

- `app/ingestion/openapi_adapter.py` — parses `openapi.yaml`/`.yml`/`.json` (provider side only, per
  §6). Hand-parse the loaded YAML/JSON dict with PyYAML rather than adding an OpenAPI parsing library —
  the spec's tech list (§3) only names PyYAML/stdlib json + `jsonschema`. Extracts service metadata,
  method/path, `operationId`/summary, request body schema, response schemas per status code, reused
  `components.schemas`, and security metadata as opaque properties (no security analysis, §6.1).
- Maps to `PROVIDES` relations + `Operation`/`Schema` canonical entities (§6.2).
- `examples/*/openapi.yaml` for the 4 services.
- `tests/unit/test_openapi_adapter.py`.

## Iteration 3 — AsyncAPI queue adapter
Spec §7. **Exit criterion:** queues/messages/sender/consumer correctly generated.

- `app/ingestion/asyncapi_adapter.py` — extracts queue/channel name + namespace, send/receive direction,
  message name/version, payload schema refs, protocol/binding metadata, DLQ mapping (§7.2, §7.4). Queue
  and Message stay separate entities — never merge them (§7 rationale).
- Does **not** model competing-consumer runtime instances (§7.3) — logical services only.
- Maps to `SENDS`/`RECEIVES_FROM`/`CARRIES`/`CONFORMS_TO`/`DEAD_LETTERS_TO` relations.
- `examples/*/asyncapi.yaml` for the services that send/receive.
- `tests/unit/test_asyncapi_adapter.py`.

## Iteration 4 — Architecture Manifest adapter + ingestion pipeline + validation
Spec §5.2, §8, §10. **Exit criterion:** REST callers connected in the graph; all V1–V9 enforced before
any graph write.

- `app/ingestion/manifest_adapter.py` — parses `architecture.yaml` (§8 example) into `CALLS` relations;
  rejects entries that duplicate info already reliably derivable from OpenAPI/AsyncAPI.
- `examples/order-service/architecture.yaml` — order-service calls product-service/getProduct (adapted
  from the spec's illustrative example to the actual 4-service test landscape).
- `app/validation/source_validation.py` — per-adapter syntax/reference checks (source-level, before
  mapping to canonical).
- `app/validation/canonical_validation.py` — implements V1–V9 (§10): unique service/queue/message IDs,
  operation ownership, `CALLS` → existing operation, schema-ref existence, DLQ-not-self, relation
  endpoints exist, atomic per-service import.
- `app/ingestion/pipeline.py` — orchestrates `scan → parse → source-validate → map to canonical →
  canonical-validate → reconcile/diff → transactional graph write` (§5.2). A failure at any stage before
  the graph write discards the whole in-progress service import (V9/AC14): build the complete
  per-service `ArchitectureModel` slice in memory and fully validate it before any graph-mutating call,
  so there is nothing partial to roll back.
- `app/ingestion/scanner.py` — `SpecificationSource` scan of configured directories for `openapi.*`,
  `asyncapi.*`, `architecture.yaml` (§5.1).
- `tests/unit/test_manifest_adapter.py`, `test_canonical_validation.py`, `test_pipeline.py` (pipeline
  test runs fully in-memory without Neo4j by stubbing the graph-write stage).

## Iteration 5 — Neo4j schema + importer
Spec §11, §12. **Exit criterion:** idempotent graph import. Docker is available (see Tooling decisions
above) — integration tests here run for real via Testcontainers (§20.2); remember the `sg docker -c
"..."` wrapper noted above until group membership propagates to a fresh shell.

- `app/graph/schema.py` — the 5 uniqueness constraints from §11.4, applied idempotently on startup.
- `app/graph/repository.py` — thin wrapper over the official `neo4j` driver, explicit transactions, two
  configured users per §19 (read-write for import, read-only for analysis/LLM).
- `app/graph/importer.py` — transactional per-service write: `MERGE` nodes/relations, then
  remove/expire stale `DECLARED` facts whose provenance belongs to that service and no longer appears in
  the new import (§12.1). Shared entities (Queue/Message/Schema) merge by stable ID and are only removed
  once no provenance references them (§12.2 reimport strategy).
- `app/graph/reconciliation.py` — diff logic the importer uses to compute what to add/keep/expire.
- `tests/integration/test_importer.py` — Testcontainers-backed Neo4j, asserts idempotent re-import
  (AC8) and atomic per-service replace (V9/AC14).

## Iteration 6 — Five standard analyses
Spec §13. **Exit criterion:** all Cypher analyses pass integration tests, runnable now that Neo4j via
Testcontainers is available.

- `app/analysis/queues.py` — A1 senders (§13.1), A2 consumers (§13.2), A3 queues with sender/no consumer
  (§13.3), A4 queues with consumer/no known sender (§13.4). Copy the Cypher verbatim, parameterized.
- `app/analysis/blast_radius.py` — A5 mixed sync+async blast radius (§13.5): traversal combining
  `CALLS`/`PROVIDES` and `SENDS`/`RECEIVES_FROM`, `maxDepth` default 5, configurable.
- `app/analysis/dependencies.py` — computed-view helpers for `SYNC_DEPENDS_ON`/`ASYNC_FLOW_TO` (§13.6),
  derived at query time and never materialized/stored.
- `tests/integration/test_analyses.py` against the 4-service + 2-extra-queue fixture landscape.

## Iteration 7 — FastAPI + minimal UI
Spec §14, §16. **Exit criterion:** service/queue/analysis visible.

- `app/settings.py` — config loader for the YAML shape in §17.1 plus env secrets `NEO4J_USER`,
  `NEO4J_PASSWORD`, `OPENAI_API_KEY` (renamed from spec's generic `LLM_API_KEY` per the OpenAI
  provider decision). Never persisted in repo or graph properties (§17.2, §19).
- `app/main.py` — FastAPI app wiring, health endpoints for app + Neo4j connectivity (§18).
- `app/api/{services,queues,messages,analysis,import_api}.py` — implement exactly the endpoint table in
  §14: `GET /api/services`, `.../{id}`, `GET /api/queues`, `.../{id}`, `GET /api/messages`, `.../{id}`,
  the 5 `GET /api/analysis/...` routes, `POST /api/import`, `POST /api/import/service/{id}`.
- `app/api/query.py` — `POST /api/query` route scaffolded now, wired to the AI subsystem in Iteration 8.
- UI: server-rendered Jinja2 templates for Service Explorer (§16.1), Queue Explorer (§16.2), and a
  Natural Language Query page showing question / generated Cypher / result rows / explanation (§16.3).
- Structured logging (`service_id`, `source_file`, `import_id`, `duration_ms`) per the §18 sample line.

## Iteration 8 — LLM query + validator
Spec §15. **Exit criterion:** NL question → read-only Cypher → answer.

- `app/ai/provider.py` — a `Protocol` provider interface plus an OpenAI implementation (Chat Completions
  API, `chat.completions.parse()` structured-output for Cypher generation), keeping the interface
  swappable per §15.5.
- `app/ai/cypher_generator.py` — question + fixed graph schema (node labels/relation types from §11) →
  candidate Cypher via the provider.
- `app/ai/cypher_validator.py` — **security-critical.** Allowlist only `MATCH`, `OPTIONAL MATCH`,
  `WHERE`, `WITH`, `RETURN`, `ORDER BY`, `LIMIT` (§15.2); hard-reject `CREATE`, `DELETE`,
  `DETACH DELETE`, `SET`, `REMOVE`, `MERGE`, `DROP`, `LOAD CSV`, `CALL` (§15.3); enforce default max
  traversal depth 5 and max 100 result rows; restrict to known node labels/relation types (§15.4).
- `app/ai/answer_composer.py` — builds the NL explanation strictly from returned rows + provenance; must
  not introduce claims the rows don't support (§9, §15.1).
- `app/ai/question_service.py` — orchestrates generate → validate → execute (via the **read-only** Neo4j
  user from Iteration 5, never the import user, §19) → compose.
- `tests/unit/test_cypher_validator.py` — adversarial cases (forbidden keywords disguised in strings/
  comments, depth/row-limit bypass attempts, disallowed labels). Write these tests before/alongside the
  implementation — this module is the graph's only write-safety boundary against LLM output.

## Iteration 9 — PoC review
Spec §21, §23.1. No new code — an evaluation pass.

- Walk AC1–AC15 (§21) against the implemented system.
- Evaluate against the 5 success measures in §23.1: faster than manual repo research; discovers
  non-obvious dependencies/documentation gaps; the 5 analyses are reproducible without the LLM; the LLM
  improves usability without replacing the graph as source of truth; the Canonical Model can absorb a
  future OpenTelemetry source without reworking the OpenAPI/AsyncAPI adapters.

## Getting started

Iterations 0 and 1 need no Neo4j/Docker and can start immediately:

```bash
uv init --python 3.13
uv add fastapi "uvicorn[standard]" "pydantic>=2" pyyaml jsonschema neo4j openai jinja2
uv add --dev pytest pytest-asyncio testcontainers httpx ruff
```

Once `pyproject.toml` exists, this section should be replaced with the real commands: `uv run pytest`,
`uv run pytest tests/unit -k <name>` for a single test, `uv run ruff check .` for lint, and
`uv run uvicorn app.main:app --reload` to run the API locally.
