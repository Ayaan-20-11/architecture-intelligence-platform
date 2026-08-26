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

## Iteration 10A — Evidence / Provenance persistence (H1)
`Architecture_Intelligence_Platform_Core_Hardening_Specification.md` §4. **Exit criterion:** AC13 fully
met — provenance is queryable in the graph, not just produced by adapters. First of the hardening spec's
three sub-projects (H1 Evidence, H2 Semantic Validator, H3 Intent Router); built alone per the spec's own
"don't implement in parallel" guidance — H2/H3 are separate future iterations.

- `app/canonical/ids.py` — `evidence_id(source_type, service_slug, revision=None)` →
  `evidence:{type}:{service}[:{revision}]`, same optional-trailing-segment convention as the other 5 ID
  builders. Built from the service slug, never a file path.
- `app/provenance/model.py::Provenance` — gained a required `id` field. Kept the existing class name
  (not renamed to `Evidence`) since it's the same concept the spec's own §4.1 starts from; exposed as a
  graph node labeled `:Evidence` and a `/api/evidence` REST prefix instead.
- `app/canonical/model.py::Relation` — gained `evidence_ids: list[str] = Field(default_factory=list)`.
- All three adapters (`openapi_adapter.py`, `asyncapi_adapter.py`, `manifest_adapter.py`) — one evidence
  record built per adapter call, stamped onto every relation that call produces via `r.model_copy(update=
  {"evidence_ids": [evidence.id]})` right before the final `return ArchitectureModel(...)`.
- `app/validation/canonical_validation.py` — new check: every `relation.evidence_ids` entry must appear
  in the model's `provenance` ids.
- `app/graph/reconciliation.py::model_node_ids` — now includes provenance/evidence ids, so `Evidence`
  automatically participates in the existing stale-node detection with no new reconciliation concept.
- `app/graph/importer.py` — `"provenance": "Evidence"` added to `NODE_LABELS` (the generic node writer
  then MERGEs `:Evidence` nodes for free); `_MERGE_RELATION_TEMPLATE` extended to accumulate
  `evidence_ids` on relationships the same way `sources` already accumulates (a relation can be declared
  by multiple services in separate import transactions — e.g. a shared `CARRIES` edge — and must keep
  every contributor's evidence); a new stale-evidence-stripping query runs alongside node expiry so a
  persisting relation loses exactly the evidence of a service that stops declaring it.
- `app/api/evidence.py` (new) — `GET /api/evidence`, `GET /api/evidence/{id}`. `app/api/services.py` /
  `queues.py` — `GET .../{id}/evidence` (undirected relationship pattern, one query covers both
  incoming/outgoing). `GET /api/relations/{relationId}/evidence` intentionally **not** implemented — the
  spec marks it optional, and `Relation` has no stable ID today.
- `app/api/ui.py` + `service.html`/`queue.html` — Service/Queue Explorer render `Source: / Revision: /
  Evidence:` per relation (spec §4.11 mockup), via a small batch-resolve helper (`_attach_evidence`).
- `app/ai/cypher_generator.py::GRAPH_SCHEMA_DESCRIPTION` — documents the new `Evidence` node and the
  `evidence_ids` relationship property. No `cypher_validator.py` changes needed — its `KNOWN_NODE_LABELS`
  already derives from `app.graph.importer.NODE_LABELS`, so `Evidence` became an allowed label
  automatically.
- Explicitly deferred: `StrEnum` typing for `source_type`/`evidence_type` (not needed for AC13); real
  `source_revision` computation in the scanner (evidence IDs stay stable across reimports without it);
  `answer_composer.py` citing evidence in LLM answers (not in H1's acceptance criteria).
- 9 new tests (150 unit / 64 integration, up from 143/55): ID builder cases, adapter evidence-stamping
  assertions, a canonical-validation case, a reconciliation case, and — most importantly — a
  Testcontainers test proving the same relation accumulates evidence from two independently-importing
  services and correctly loses just one contributor's evidence on that service's reimport.

## Iteration 10B — Graph Schema + Semantic Query Validator (H2)
`Architecture_Intelligence_Platform_Core_Hardening_Specification.md` §5. **Exit criterion:** the live
Iteration 9 failure — the LLM generating syntactically valid, security-validator-passing Cypher with a
relationship's direction backwards (`(q:Queue)-[:SENDS]->(s:Service)`) — is caught before it reaches
Neo4j. Second of the hardening spec's three sub-projects, built alone after H1 per the spec's own
"don't implement in parallel" guidance; H3 (Intent Router) remains a separate future iteration.

- `app/graph_schema/model.py` — `RelationDefinition(name, source_labels: frozenset[str],
  target_labels: frozenset[str])`. `frozenset` instead of the spec's literal `set[str]`, matching
  `app/graph/reconciliation.py`'s existing frozenset-for-registry/set-for-working-values distinction.
- `app/graph_schema/registry.py` — `RELATIONS: dict[str, RelationDefinition]` for all 9 known relation
  types (spec §5.3's table).
- `app/ai/semantic_query_validator.py` (new) — co-located with `cypher_validator.py`, not the
  pre-existing `app/validation/` package (which holds ingestion-pipeline model validation, a different
  concern). `SemanticQueryValidator.validate(cypher)` and `SemanticValidationError` (carrying
  `relation`/`expected_source`/`expected_target`/`actual_source`/`actual_target`, spec §5.9/§5.10).
  Implementation is a hand-written depth-counting tokenizer (spec §5.8 Variante A — no Cypher-parser
  dependency exists or is needed, since the LLM's permitted subset is already hard-restricted by
  `cypher_generator.py`'s prompt): balanced-bracket scanning for node `(...)` and relationship
  `-[...]->`/`<-[...]-`/`-[...]-` patterns (handles nested parens in property maps, e.g.
  `{id: toLower($id)}`, which a flat regex cannot), a global variable→labels symbol table (resolves
  alias reuse across separate `MATCH` clauses and correlated `EXISTS {...}` subqueries), adjacency-based
  chain grouping (multiple `MATCH`/`OPTIONAL MATCH` blocks fall out for free), and domain/range checking
  per relationship-chain triple. An unknown relation type in a `TYPE1|TYPE2` alternation is rejected
  unconditionally (AC-H2-4); domain/range compatibility across an alternation is OR'd (valid if any
  known alternative matches, since that's what the alternation means at query time), and an undirected
  `-[...]-` pattern is checked against either orientation (matching Neo4j's own undirected semantics). A
  label the validator can't resolve (never stated on that variable anywhere in the query) is treated
  permissively — the validator judges schema-correctness, not answer-completeness (spec §5.7).
- `app/ai/question_service.py::ArchitectureQuestionService` — constructs a `SemanticQueryValidator()`
  in `__init__` (no injectable kwarg: unlike `max_depth`/`max_result_rows`, it's stateless and has no
  per-deployment configuration) and calls `.validate(cypher)` in `ask()` right after the existing
  security `validate_cypher(...)` and before the read-only Neo4j session opens.
- `app/main.py::create_app()` — `@app.exception_handler(SemanticValidationError)` returning HTTP 422
  with the spec §5.10 JSON body (`code: SEMANTIC_QUERY_INVALID`, `message`, `relation`,
  `expectedSource`, `expectedTarget`). Applies globally, so it also converts an otherwise-unhandled
  error on the HTML `/query` page into the same JSON body — a pre-existing gap shared with
  `CypherValidationError`, not fixed for either validator in this iteration.
- Explicitly deferred: the optional dev-only `POST /api/debug/validate-cypher` endpoint (spec §5.9
  marks it optional; not needed for any AC-H2 criterion).
- 37 new tests (185 unit / 66 integration, up from 150/64): the spec §5.11 valid/invalid table, the
  exact AC-H2-2 live-test regression, unknown-relation-type rejection (independent of the security
  validator per AC-H2-5), permissive handling of unresolvable labels, alias reuse across `MATCH`
  clauses and a correlated `EXISTS` subquery, `OPTIONAL MATCH`, variable-length traversal, the real
  multi-hop/anonymous-node/property-map shape from `app/analysis/blast_radius.py`, nested-parens-in-
  property-map (pinning the balanced-bracket-scanner fix over a flat regex), alternation OR-semantics,
  a graph-schema-registry drift check against `KNOWN_RELATION_TYPES`, an `ArchitectureQuestionService`
  Testcontainers test proving a semantically invalid query never reaches the graph, and an end-to-end
  FastAPI test asserting the 422 body shape through `POST /api/query`.

## Iteration 10C — Deterministic Intent Router (H3)
`Architecture_Intelligence_Platform_Core_Hardening_Specification.md` §6. **Exit criterion:** the
Iteration 9 live-test question "What queues have a consumer but no known sender?" resolves
deterministically to A4 through the normal NL endpoint, never invoking LLM Cypher generation. Third and
final hardening sub-project, built alone after H1/H2 per the spec's own "don't implement in parallel"
guidance.

- `app/intent/model.py` — `ArchitectureIntent(StrEnum)` (5 analyses + `UNKNOWN`) and
  `IntentResult(intent, confidence, parameters)`, per spec §6.4/§6.5 literally. No `AMBIGUOUS` member —
  spec §6.9 marks it explicitly optional/future, and `UNKNOWN` already covers both "no pattern matched"
  and "matched but entity ambiguous."
- `app/intent/entity_resolver.py` — pure matching logic decoupled from Neo4j I/O (mirrors
  `blast_radius.py`'s existing injected-callable style): `resolve(candidates, raw_text)` normalizes by
  stripping all separators (not collapsing whitespace to `-`, which would fail to equate `"OrderService"`
  with `"order-service"`), tries an exact match first (unique → return it, 2+ → ambiguous → `None`),
  else falls back to substring match (unique → return it, 0 or 2+ → `None`) — never guesses (spec §6.10).
  `fetch_candidates(session, label)` is the thin Neo4j-touching wrapper.
- `app/intent/patterns.py` — regex templates for EN/DE phrasings of A1/A2/A5 (mandatory anchor words
  `"to"`/`"from"`/`"von"`/`"vom"` — never optional, so free text can't accidentally match) plus
  keyword-combination matching for A3/A4 (`"queue"` + a no-sender/no-consumer phrase, order-independent
  via `.search`, since the spec itself uses two different A4 phrasings that no single fixed sentence
  would both match).
- `app/intent/router.py` — `classify(question, *, candidates, threshold=0.90)`, a plain function
  (matching the majority convention in `app/ai/*.py`, not a class) taking a pre-fetched
  `dict[str, list[tuple[str,str]]]` of `Service`/`Queue` candidates rather than an injected callable —
  simpler given both label lists are small and always needed together at this PoC scale. Confidence is
  only ever 1.0 or 0.0 (rule-based, not statistical); the `deterministic_threshold` comparison is still
  wired per spec §6.8. LLM-based classification as a fallback tier (spec §6.6) and depth-phrase parsing
  for A5 ("at depth 3") are explicitly deferred — not required by any AC-H3-x, and both would reintroduce
  the non-determinism H3 exists to eliminate for the known-intent path.
- `app/analysis/registry.py` — `INTENT_HANDLERS` maps each intent to the **existing** analysis function
  (`senders_of_queue` etc., not the spec's literal `QueueProducerAnalysis`-style names) and
  `execute(session, intent, parameters)` converts dataclass rows to dicts. `BLAST_RADIUS` deliberately
  omits a `max_depth` override, relying on `blast_radius.DEFAULT_MAX_DEPTH` — the same default the REST
  endpoint uses, so AC-H3-4 holds exactly rather than coincidentally.
- `app/answer_router.py` (new, top-level, not under `app/ai/` — its entire point is deciding whether to
  reach into that LLM-specific package at all, and it composes `intent`/`analysis.registry`/`ai` equally)
  — `answer_question(...)` classifies first; a known intent runs the existing analysis directly with no
  provider involved at all (AC-H3-3); `UNKNOWN` falls back to `ArchitectureQuestionService.ask()`, which
  stays completely untouched (still H1/H2-hardened, `provider` still mandatory — deterministic answers
  must work with zero LLM configured, which can't live inside a class requiring a provider to construct).
  Raises `LLMNotConfiguredError` only when an `UNKNOWN` question has no provider available.
- `app/settings.py`/`config.yaml` — `IntentRouterConfig(deterministic_threshold: float = 0.90)`, snake_case
  (`intent_router: deterministic_threshold: 0.9`), not the spec's literal kebab-case example, matching
  this repo's actual config convention. No `enabled` toggle — no AC needs a kill-switch.
- `app/api/query.py` — `QueryResponse` gains `execution_mode: Literal["DETERMINISTIC","LLM"]` and
  `intent: str | None` (additive, snake_case to match the model's existing fields rather than the spec's
  literal camelCase mockup). `POST /api/query` drops the hard `Depends(get_question_service)` (which
  503'd before the route body even ran) for `Depends(build_question_service)` (already existed, already
  returns `None` gracefully) plus a session/settings dependency, calling `answer_question(...)` and
  translating `LLMNotConfiguredError` to the same 503.
- `app/api/ui.py::query_page` — same treatment, sharing `answer_question` with the JSON API rather than
  letting the HTML page diverge; `app/templates/query.html` gained a small "Execution: Deterministic
  Analysis ({intent}) / LLM-generated Cypher" section (spec §6.12).
- 49 new tests (221 unit / 79 integration, up from 185/66): entity-resolver normalization/ambiguity
  cases, `classify()` over EN/DE phrasings for all 5 intents plus synonyms/ambiguity/unknown/threshold
  cases (including two invariant-pinning cases proving the router doesn't hijack the pre-existing
  `/api/query` test suite's own question text), the analysis registry's dataclass→dict conversion, a
  Testcontainers suite exercising all 5 intents end-to-end (including a provider whose
  `generate_cypher` raises if called, pinning AC-H3-3) and the exact AC-H3-7 regression, and `test_api.py`
  additions proving a deterministic question succeeds with zero LLM configured and that its rows match
  the equivalent `GET /api/analysis/...` endpoint exactly (AC-H3-4).

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
