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

## Iteration 11A — OTLP Foundation (H4)
`Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md` §8-§11, §32-§33, §54, §61, §67.
**Exit criterion:** an OTLP/HTTP protobuf trace export can be posted to `POST /v1/traces` and correctly
decoded into the internal `RuntimeSpan` model — no graph update yet. First of H4's seven sub-iterations
(11A-11G); scoped to just this slice per the user's explicit choice, continuing H1-H3's one-sub-iteration-
at-a-time approach.

- `pyproject.toml` — new runtime dependency `opentelemetry-proto>=1.44.0` (pulls in `protobuf` only) —
  ships just the generated protobuf message classes for the OTLP wire format, no SDK/exporters.
- `app/telemetry/model.py` — `RuntimeSpan(BaseModel)` per spec §10 literally; explicitly a temporary
  ingestion model, never persisted to Neo4j.
- `app/telemetry/semconv/resources.py` — the 5 resource-attribute key constants the receiver needs
  (`service.name`/`service.namespace`/`service.version`/`service.instance.id`/
  `deployment.environment.name`), centralizing OTel attribute names per spec §33. `semconv/http.py`/
  `messaging.py` deferred to 11C/11D, which don't exist yet.
- `app/telemetry/otlp_receiver.py` — `OtlpDecodeError(ValueError)` (matching the `CypherValidationError`/
  `SemanticValidationError` precedent) and `decode_export_request(raw: bytes) -> list[RuntimeSpan]`:
  parses the protobuf, extracts each `ResourceSpans` block's service identity once, and builds one
  `RuntimeSpan` per `Span` (hex-encoding trace/span/parent-span IDs, mapping the `SpanKind` enum to a
  friendly string, converting nanosecond timestamps to UTC `datetime`, unwrapping `AnyValue` attributes
  unfiltered — allowlisting deferred to whichever later iteration actually persists data). A
  `ResourceSpans` block with no `service.name` has its spans silently skipped, not erroring the whole
  batch — OTLP batches legitimately mix multiple services per export, so one misconfigured SDK shouldn't
  black-hole every other service's data in the same request.
- `app/api/telemetry.py` (new) — `POST /v1/traces` (top-level path, not `/api`-prefixed, per OTLP/HTTP
  convention): validates `Content-Type: application/x-protobuf` (415 otherwise), decodes the body,
  returns an empty protobuf `ExportTraceServiceResponse` ack on success or 400 on `OtlpDecodeError`. Zero
  `Depends()` — no Neo4j/settings needed yet, unlike every other existing route. `app/main.py` registers
  the router; decoded `RuntimeSpan`s are discarded after decoding, since 11A has nothing to do with them.
- Explicitly deferred: everything downstream of `RuntimeSpan` (`adapter.py`, `service_resolver.py`/
  `operation_resolver.py`/`queue_resolver.py`, `aggregator.py`, any Neo4j writes — 11B-11E); O1-O5
  runtime analyses, `/api/runtime/*`, Service Explorer UI additions, new intent-router entries (11F-11G);
  Docker Compose/OTel Collector infrastructure (no value before more of the pipeline exists to receive
  the data); attribute allowlisting (deferred to the iteration that actually persists data).
- 20 new tests (241 unit / 79 integration, up from 221/79): pure-decode cases (resource identity
  extraction, optional-field defaults, no cross-contamination between resource blocks, all 6 `SpanKind`
  values, ID hex-encoding, root vs. child `parent_span_id`, scalar attribute decoding, a service-name-less
  block skipped not erroring, malformed payload, empty batch) and a `TestClient`-based route suite (valid
  payload → 200 + parseable ack, wrong content-type → 415, malformed body → 400) — placed in `tests/unit/`
  despite being FastAPI-based, since the route needs zero Neo4j/Docker and reusing `test_api.py`'s
  container-backed fixtures would add infra this route never touches.

## Iteration 11B — Service & Environment Resolution (H4)
`Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md` §11-§14, §67. **Exit criterion:**
a `RuntimeSpan`'s service identity can be matched against declared Services (or correctly identified as
previously-undocumented) with a deterministic, stable id - no graph write yet. Per spec §5's pipeline
(`OTLP Ingestion → Adapter → Observation Resolver → Observation Aggregator → Neo4j`) and §36 (only the
Aggregator, Iteration 11E, writes to Neo4j), the Resolver is a pure/read-mostly decision-maker; §67's
11B diagram (`Resource attributes → Service Resolver → Environment`) is the only one of the six H4
iteration diagrams with no terminal write-shaped box, confirming this reading.

- `app/canonical/ids.py::service_id` — extended to `service_id(slug, namespace=None)`, mirroring
  `queue_id`'s existing exact shape. `service_id` was the outlier among the five ID builders in lacking
  an optional namespace param, not a deliberate boundary - no declared-Service query anywhere selected a
  namespace column before this, and no existing single-arg call site breaks.
- `app/telemetry/model.py` — new `DiscoveryStatus(StrEnum)`: `DECLARED`/`OBSERVED_ONLY` (spec §13's
  literal property values), placed in the shared telemetry model since operations (§23) and queues (§29)
  will reference the same concept in 11C/11D - though the exact mechanism there may differ from Service's,
  re-check those sections' own property lists rather than assuming 1:1 reuse.
- `app/telemetry/service_resolver.py` (new) — `resolve_service(candidates, *, service_name,
  service_namespace, aliases)`: **exact match only** (not fuzzy/normalized like `app/intent/
  entity_resolver.py`, since OTel's `service.name`/`service.namespace` are structured attributes, not
  free-text human phrasing). Four tiers per spec §12: (1) namespace+name exact match - only fires once
  declared Services carry a namespace, which none do yet, kept forward-compatible without rework; (2)
  name alone, but only if it uniquely identifies one candidate - two declared services can plausibly
  share a display name today (adapters derive `id` from a slug but `name` from free-text document
  metadata, and `graph/schema.py` only enforces uniqueness on `id`), so 2+ matches fall through rather
  than guessing; (3) a configured alias; (4) observed-only - mints a deterministic id via
  `ids.service_id(_slugify(service_name), namespace=service_namespace)`. `service.instance.id` is never
  read anywhere in this logic, satisfying H4.3 by construction. `resolve_runtime_span(candidates, span,
  *, aliases)` is a thin wrapper folding in `span.environment` (already decoded by 11A) - satisfying the
  diagram's third box without a separate "environment resolver" module. `fetch_candidates(session)` is
  the one Neo4j-touching function, a single `MATCH (s:Service) RETURN s.id, s.name, s.namespace` query.
- `app/settings.py`/`config.yaml` — new `TelemetryConfig(service_aliases: dict[str, str] = {})`,
  registered as `AppConfig.telemetry`. Scoped to Services only per spec §12's tier 3 - not preemptively
  generalized to operations/queues before 11C/11D's own spec sections confirm the same mechanism applies.
- Explicitly deferred: wiring `service_resolver.py` into `POST /v1/traces` (nothing productive to do
  with a resolved identity until 11C/11D build real `CALLS`/`SENDS` fact candidates from it); physically
  creating an `OBSERVED_ONLY` `(:Service)` node in Neo4j (11E's Aggregator, or whichever iteration first
  needs a real node to attach a relation to); `EvidenceType`/`SourceType` as real `StrEnum`s (spec §15,
  not assigned to 11B by §67's own table - `Provenance.source_type`/`evidence_type` remain plain `str`
  fields today); extracting a shared "mint an id for tier 4" helper across future resolvers (YAGNI with
  only one call site so far - kept internally parallel-shaped for easy extraction once 11C/11D exist).
- 15 new tests (253 unit / 82 integration, up from 241/79): the four matching tiers plus "don't guess on
  a name collision," alias fallback, deterministic/namespace-qualified id minting, environment folding,
  and the spec §61-named "instance ignored" case (two spans differing only in `service_instance_id`
  resolve to the identical `service_id`) as pure unit tests with hand-built candidates (mirroring
  `test_entity_resolver.py`'s fixture-free style); a first H4 integration test (Testcontainers) proving
  `fetch_candidates` reads real declared Service data correctly and an end-to-end resolution both matches
  a known service and mints an unmatched one - with an explicit assertion that no `Service` node was
  written to the graph, since this iteration's resolver stays read-only.

## Iteration 11C — REST Observations (H4)
`Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md` §16-23, §31-36, §67. **Exit
criterion:** correlated HTTP CLIENT/SERVER span pairs produce real `ObservedFactCandidate`/
`ObservedEvidence` records (spec §34's exact data contract) - resolving the called Operation against
declared OpenAPI operations, or minting a stable observed-only id. Independent review of §5/§9/§16-19/
§34-36/§67 confirmed constructing the real evidence-shaped output is this Resolver stage's own job, not
deferred to the later Aggregator (11E) - 11E's role is *merging many* single-observation "seeds" (a
degenerate bucket-of-one: `bucket_start == bucket_end`'s day, `first_seen == last_seen == timestamp`,
`observation_count = 1`) into the real persisted, time-bounded bucket. **No Neo4j writes** - consistent
with 11A/11B.

- `app/canonical/ids.py` — new `observed_evidence_id(environment, bucket_start, subject_id,
  relation_type, object_id)`, matching spec §17's literal example format
  (`evidence:otel:production:2026-08-26:<fact-hash>`). Has no trace/span-specific component
  deliberately - every seed for the same `(fact, day, environment)` gets the identical id, the
  precondition for 11E's Aggregator to `MERGE` rather than search.
- `app/provenance/model.py` — new `SourceType`/`EvidenceType` `StrEnum`s (spec §15's first real
  implementation - previously just documented as plain strings) and `ObservedEvidence(Provenance)`
  (spec §16's exact fields), with `source_type`/`source_file`/`evidence_type` overridden as **class-level
  defaults** (every instance has the same values for all three, so no per-call-site magic strings).
  `Provenance`'s own field *types* stay plain `str` - not retyped, since a `StrEnum` member is a valid
  `str` and this avoids touching a stable H1-era contract.
- `app/telemetry/semconv/http.py` (new) — HTTP attribute key constants (spec §32), mirroring
  `semconv/resources.py`.
- `app/telemetry/model.py` — new `day_bucket()` (UTC calendar-day truncation, shared since 11D's queue
  observations need the same computation), `ObservedFactCandidate`, `ObservedOnlyEntity` (a deliberate
  simplification of spec's `ArchitectureEntity`, which is referenced in §35 but never actually defined
  anywhere in the spec - just `id`/`label`/`name`, not the full declared `Service`/`Operation` models'
  many required fields), `UnresolvedObservation`, `ObservationBatch` (spec §35's exact shape).
- `app/telemetry/operation_resolver.py` (new, structural sibling of `service_resolver.py`) —
  `resolve_operation(candidates, *, provider_service_id, method, route)`: Fall A (spec §23) reuses an
  existing declared operation's id verbatim; Fall B mints via the *existing* `ids.operation_id()`
  formatter, passing the full `provider_service_id` (not a bare slug, which `service_resolver.py` never
  exposes for either declared or observed-only resolutions) - visually distinguishing minted ids from
  declared ones as a side effect, not a special case; Fall C (no stable route) is `None`/`None` -
  UNRESOLVED, never a graph node (prevents `/products/4711`, `/products/4712`, ... from each minting a
  distinct Operation).
- `app/telemetry/adapter.py` (new - matches spec §54/§9's own "OpenTelemetryAdapter" naming) —
  `correlate_http_call_observations()`. Correlation is **scoped to spans within one decoded OTLP batch
  only**: a call whose client/server spans are exported in different `/v1/traces` POSTs produces zero
  observations - an accepted, permanent PoC limitation (real Collector batch processors flush by
  time/size, not trace completeness), not a bug; building cross-batch stateful pairing would be exactly
  the "trace store"/causality graph spec §4.2 explicitly excludes. Environment/method/route/timestamp are
  read from the **server** span, not the client - necessary, not just stylistic: declared `Operation`
  ids are minted from the provider's own OpenAPI path, so sourcing the route from the client's
  `url.template` risks a lexical mismatch that would silently break Fall A (H4.6).
  `source_service_version` comes from the **client** span. A missing environment is treated as
  `UnresolvedObservation(reason=NO_ENVIRONMENT)`, never a fabricated `"unknown"` sentinel - matching
  every prior iteration's "never guess" principle.
- Explicitly deferred: wiring into `POST /v1/traces` (still decodes-and-discards); any Neo4j write
  (11E); a combined `adapt(raw_bytes) -> ObservationBatch` orchestrator (waits for 11D so it can combine
  both HTTP and queue observations in one call); queue observations (11D); merging multiple
  `ObservedEvidence` seeds into a real persisted bucket (11E).
- 26 new tests (277 unit / 84 integration, up from 253/82): `observed_evidence_id` determinism/
  sensitivity; the operation resolver's three Falls plus method case-insensitivity and wrong-provider
  non-matching; the adapter's correlation pairing (matched/unpaired/mismatched-trace-id/empty-batch
  cases, locking in the within-batch-only scope decision), both unresolved reasons, full evidence-field
  correctness (defaults, determinism, bucket bounds), and `ObservedOnlyEntity` deduplication; two
  Testcontainers integration tests proving Fall A reuses the *real* declared `order-service →
  product-service GET /products/{id}` operation id (direct H4.6 proof) and Fall B mints a stable
  observed-only id against real service data, both with explicit "nothing written to Neo4j" assertions.

## Iteration 11D — Queue Observations (H4)
`Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md` §24-30, §32, §67. **Exit
criterion:** `SENDS`/`RECEIVES_FROM` facts built from messaging spans, reusing declared AsyncAPI queues
or minting stable observed-only ids. Unlike 11C, **no client/server correlation is needed** - spec §24
already models `SENDS`/`RECEIVES_FROM` as independent relations, each derivable from a single span
alone. Also fulfills 11C's own deferred note by building the combined `adapt()` orchestrator now that
both HTTP and queue correlation exist. **No Neo4j writes** - consistent with 11A-11C.

- Resolved spec §27's "broker/system instance" ambiguity: the spec's illustrative 3-segment queue id
  doesn't match the actual, already-implemented 2-segment `ids.queue_id(name, namespace=None)`, and
  §27's own instruction ("use the same id generator as the AsyncAPI importer") means reuse that
  function, not invent a new scheme. §32's messaging allowlist has no distinct broker-instance
  attribute either - only `messaging.system` (a broker type, not a specific instance) is readable, so
  it's folded into `queue_id`'s single `namespace` parameter. Confirmed via the real fixtures:
  `app/ingestion/asyncapi_adapter.py` derives a declared Queue's `namespace` from an unused `x-namespace`
  vendor extension - no real `asyncapi.yaml` sets it, so every real declared `Queue.namespace` is `None`
  today, identical to `Service.namespace` in 11B.
- `app/telemetry/semconv/messaging.py` (new) — messaging attribute key constants (spec §32), mirroring
  `http.py`.
- `app/telemetry/queue_resolver.py` (new, third structural sibling of `service_resolver.py`/
  `operation_resolver.py`) — `resolve_queue(candidates, *, messaging_system, destination_name, aliases)`:
  a `messaging_system`-qualified exact match (dormant against today's real data, forward-compatible,
  mirroring `service_resolver`'s own tier-1 situation), a bare-`destination_name` match (unique-match-
  required, what actually unifies AsyncAPI-declared and OTel-observed queues today), a configured alias,
  and observed-only minting via `ids.queue_id(destination_name, namespace=messaging_system)` (embeds
  the system in a *freshly minted* id, unlike tier-1 matching which only checks field equality).
- `app/telemetry/adapter.py` — **generalized `_record_if_observed_only`** from a `ResolvedObservation`-
  specific, `label="Service"`-hardcoded helper to a fully generic `(entities, *, entity_id,
  discovery_status, label, name)`, since `QueueResolution` has neither `.service_id` nor `.environment`
  and literally couldn't be passed to the old signature; rerouted the existing HTTP-path Operation
  entity-recording (previously an inline `if` block) through the same helper for consistency. New
  `correlate_queue_observations(spans, *, service_candidates, queue_candidates, service_aliases,
  queue_aliases) -> ObservationBatch` — no pairing step; classifies each span via
  `messaging.operation.type` alone (never `span_kind`, matching spec §25/§26's own literal examples and
  the fact that `messaging.operation.type` exists in real OTel semconv specifically because `span_kind`
  is too coarse to disambiguate `receive` from `process`): `"send"` → `SENDS`, `{"receive","process"}` →
  `RECEIVES_FROM`, anything else (including absent) → silently skipped, never reported as unresolved
  (same status as an `INTERNAL`-kind span in the HTTP path — `unresolved` stays reserved for "recognized
  but incomplete", not "not applicable to H4"). Missing destination name or environment produce
  `UnresolvedObservation`s; both the resolved service and queue are recorded as `ObservedOnlyEntity` when
  observed-only, satisfying H4.10 for the queue side the same way the HTTP path already does for
  services/operations. New `adapt(spans, *, service_candidates, operation_candidates, queue_candidates,
  service_aliases, queue_aliases) -> ObservationBatch` combines both correlation functions' outputs,
  re-deduplicating entities across paths. Deliberately narrower than 11C's noted `adapt(raw_bytes)` shape
  — still takes already-decoded spans; composing decode-then-adapt and wiring into `POST /v1/traces`
  stays deferred to whichever iteration first needs it (11E at the earliest).
- Explicitly deferred: wiring into `POST /v1/traces`; any Neo4j write (11E); message-type-specific facts
  (spec §30 permanently scopes H4 to `Service -> Queue`, not just for this iteration); merging multiple
  `ObservedEvidence` seeds into a real persisted bucket (11E).
- 21 new tests (295 unit / 87 integration, up from 277/84): the queue resolver's four tiers plus a
  bare-name-collision guard and graceful handling of a missing `messaging_system`; the adapter's SEND/
  RECEIVE/PROCESS classification, silent-skip-vs-unresolved boundary, both unresolved reasons, dual
  entity recording, and evidence-shape correctness; `adapt()` combining facts from both paths and
  deduplicating a service discovered via both; two Testcontainers integration tests proving a send
  observation reuses the *real* declared `payment-q` (H4.9) and an unknown destination mints a stable
  observed-only queue against real service data (H4.10), both with explicit "nothing written to Neo4j"
  assertions, plus a `fetch_queue_candidates` real-data check.

## Iteration 11E — Evidence Aggregation (H4)
`Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md` §17-19, §36-40, §54, §61-62, §67.
**Exit criterion:** `ObservedFactCandidate`s are merged into real Neo4j Evidence nodes/relations with
correct bucket semantics (spec §36: normalize fact → determine bucket → find/merge relation → add
OBSERVED evidence → update counters/first-last-seen → cap trace samples). **This is the first H4
iteration that writes to Neo4j** — 11A-11D built a fully read-only pipeline.

- **Scope reversal, recorded deliberately**: this iteration also wires `POST /v1/traces` all the way
  through to persistence (decode → fetch declared candidates → `adapt()` → `persist_observation_batch()`),
  rather than deferring once more as every prior H4 iteration did. Reasons: spec §62's own Integration
  Tests section names the target path explicitly ("OTLP batch → `/v1/traces` → Observed Fact → Neo4j");
  §9's pipeline diagram terminates in Neo4j as the steady-state architecture; `app/api/telemetry.py`'s
  own docstring was a live "not yet, next iteration" pointer; the plumbing cost was low (`app/deps.py`
  already had the exact `Depends(get_driver)` idiom to reuse); and 11G's theme ("Runtime API + Service
  Explorer + O1-O5 intents") is about the *read* side, with no natural home for finishing the write path.
- `app/graph/schema.py` — added the missing `Evidence.id` uniqueness constraint (every other node label
  had one; `Evidence` was a real gap even before H4).
- `app/telemetry/aggregator.py` (new) — `merge_evidence(existing: ObservedEvidence | None, seed) ->
  ObservedEvidence`, a **pure** bucket-merge function (mirrors the pure-function/thin-I/O-wrapper split
  already established across the three resolvers): widens `first_seen`/`last_seen`, sums
  `observation_count`, dedup-caps `sample_trace_ids` at 5; `bucket_start`/`bucket_end` come from the seed
  unchanged (same-day by construction, since `observed_evidence_id()` is deterministic per (fact, day,
  environment)). Caught and fixed a real, non-obvious bug before it shipped: Neo4j returns temporal
  properties as `neo4j.time.DateTime`, not `datetime.datetime` — Pydantic v2 rejects it outright, so
  reading an existing Evidence node back requires an explicit `.to_native()` conversion (write-direction
  needs none). Entity stubs use `MERGE ... ON CREATE SET` only (never touches an existing DECLARED node's
  real properties); facts are persisted **sequentially inside one transaction**, not a bulk `UNWIND` —
  this is what correctly handles the same fact appearing more than once within one OTLP batch, since each
  read sees the previous iteration's already-written merge. The relation-evidence accumulation mirrors
  (does not call) `importer.py`'s existing dedup-append `reduce()` expression, deliberately never touching
  `r.sources` (declared-import-only reconciliation bookkeeping that must not apply to incremental runtime
  observation, per spec §40's "absence of observation ≠ evidence of absence").
- `app/settings.py::TelemetryConfig` gained `queue_aliases` (only `service_aliases` existed since 11B) —
  completes the config surface `correlate_queue_observations` already needed as a parameter.
- `app/api/telemetry.py` — `POST /v1/traces` gained `Depends(get_driver)`/`Depends(get_settings)`.
  Content-type/decode validation still happens first in the route body, but this does **not** avoid the
  new dependencies at the FastAPI level — `Depends()` params are resolved before the route body runs
  regardless of where an early exception is raised, so both existing 415/400 unit tests needed
  `app.state.driver`/`settings` stubbed (to *something*, even `None`/a bare default `Settings()`, since
  those code paths never actually use them) to keep passing without Docker.
- Explicitly deferred and documented as a known, not-fixed risk: `importer.py::_EXPIRE_RELATIONS_QUERY`
  unconditionally deletes a relation once a declared reimport empties its `sources`, regardless of
  whether it also carries OBSERVED `evidence_ids` — after 11E, a `CONFIRMED` relation losing its declared
  side could have its accumulated observed evidence silently discarded too. A correct fix needs to check
  evidence *type*, not just presence, with an ordering-sensitive interaction with stale-evidence-stripping
  not fully verified within this iteration's scope — left for a dedicated follow-up (11F, when this would
  first become visible) rather than risking a regression in well-tested H1 code.
- Also explicitly deferred: any Runtime API surface for reading the new Evidence properties (11G);
  O1-O5 comparison analyses and the derived `CONFIRMED`/`OBSERVED_ONLY`/`DECLARED_ONLY` status (spec §38:
  status is derived at query time, not stored — confirmed as 11F's job, not 11E's); retention/cleanup
  (spec §59-60, not assigned to any of H4's seven named sub-iterations).
- 14 new tests (303 unit / 93 integration, up from 295/87 minus one moved): `merge_evidence`'s widening/
  summing/capping/preservation behavior as pure unit tests; Testcontainers tests proving a stub node is
  `ON CREATE`-only (idempotent, never clobbers a declared node), a fact adds observed evidence *alongside*
  a relation's pre-existing declared evidence (direct proof of spec §37/§38's "evidence decides status"
  model), and persisting the same fact twice correctly merges the bucket (the test that actually exercises
  the `.to_native()` fix, since it's the only path reading back a previously-written Evidence node); the
  `/v1/traces` happy-path test (moved from unit to `tests/integration/test_telemetry_api.py`, since a
  valid payload now requires real Neo4j) proving the full spec §62 path end-to-end — a real OTLP payload
  results in a queryable `CALLS` relation with an `OPENTELEMETRY`/`OBSERVED` Evidence node attached.

## Iteration 11F — Architecture Comparison (H4)
`Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md` §38-48, §54, §67.
**Exit criterion:** five deterministic, no-LLM Cypher analyses (O1-O5) deriving each relation's status
from its `Evidence`, per spec §38's formula: `D ∧ O ⇒ CONFIRMED`, `D ∧ ¬O ⇒ DECLARED_ONLY`,
`¬D ∧ O ⇒ OBSERVED_ONLY`, where `D` (declared) has no window/environment and `O` (observed) is scoped to
a specific window+environment. Pure analysis functions only — no REST/UI/intent-router wiring (spec §67
assigns that to 11G, mirroring how the base PoC's A1-A5 were built before their Iteration 7 API exposure).

- `app/settings.py` — new `RuntimeAnalysisConfig(default_window_hours: int = 24)`, its own
  `AppConfig.runtime_analysis` section (mirrors `IntentRouterConfig`'s precedent, not folded into the
  ingestion-scoped `TelemetryConfig`); `config.yaml` gained the matching `runtime_analysis:` block.
- `app/analysis/runtime.py` (new) — `observed_relations` (O1, all filters optional: `environment`,
  `from_id`, `to_id`, `relation_type`), `confirmed_relations` (O2), `observed_only_relations` (O3),
  `declared_only_relations` (O4, `status` always the literal `NOT_OBSERVED_IN_WINDOW`, per spec §40/H4.16
  — never "obsolete"/"unused"/"dead"), `telemetry_coverage` (O5, `http_observed`/`messaging_observed`/
  `spans_observed`). None read wall-clock time internally — all take an explicit `since`/optional `until`;
  a separate `default_since()` helper does, kept apart for deterministic testing. Mirrors `queues.py`'s
  "multiple analyses, one file" precedent rather than spec §54's suggested new `app/runtime_analysis/`
  package (confirmed the repo has never adopted any of the spec's originally-suggested package splits).
  A real correctness bug was caught and fixed at design-review time, before any code was written: `CALLS`
  always goes `Service -> Operation`, never `Service -> Service`; `Operation` has no reliable `.name`; and
  `PROVIDES` (the only edge resolving an Operation back to its provider Service) is written only by the
  declared OpenAPI import path — never by 11C's aggregator for an undeclared/Fall-B operation. Resolving
  the provider via an inner join through `PROVIDES` would have silently dropped exactly the rows O3
  ("probably the most important H4 analysis", spec §44) exists to surface. Every relation-listing query
  uses `OPTIONAL MATCH (o)<-[:PROVIDES]-(provider)` plus a `coalesce(provider.id, o.id)`/
  `coalesce(provider.name, o.name, o.method + ' ' + o.path, o.id)` fallback chain instead — meaning a
  `CALLS` row's `target_id`/`target_name` is the *provider service's* identity when one is declared, and
  the bare operation's identity otherwise, never a dropped row.
- O1-O3 each `UNION` a CALLS branch with a SENDS/RECEIVES_FROM branch (mirrors
  `blast_radius.py::_NEIGHBORS_QUERY`'s existing SYNC/ASYNC UNION precedent); multiple matching daily
  Evidence buckets within the window collapse into one summary row per relation via Cypher's standard
  implicit-GROUP-BY-on-mixed-aggregates behavior (`min(first_seen)`/`max(last_seen)`/
  `sum(observation_count)` alongside the non-aggregate columns). O2/O3/O4 require `environment` (not
  optional, unlike O1's filters) — spec §38's `O(F,W,E)` bakes in one specific environment; the same fact
  can be `CONFIRMED` in production and `DECLARED_ONLY` in staging simultaneously.
- O4's `telemetry_coverage_available` is composed from O5 in Python (not duplicated Cypher): each row's
  *subject* (always a real, directly-identified Service — O4 never needs `PROVIDES` resolution on that
  side) is checked against `telemetry_coverage()`'s `http_observed` (for a `CALLS` row) or
  `messaging_observed` (for `SENDS`/`RECEIVES_FROM`).
- O5's "HTTP as provider" check has a documented, inherited PoC-scope limitation (from 11C, not fixed
  here): it can only see `PROVIDES` edges, which the H4 pipeline never writes for an undeclared/Fall-B
  operation — a service that is only ever an undeclared provider shows `http_observed: false` even with
  real observed traffic reaching it. Documented in the `ServiceTelemetryCoverage` docstring and pinned by
  a dedicated integration test (`test_o5_provider_side_gap_is_pinned`), not just a comment, so a future
  fix to the underlying gap is forced to update a real assertion.
- Explicitly deferred: any REST endpoint, UI, or intent-router wiring for O1-O5 (11G); an explicit "now"
  upper bound beyond O1-O4's optional `until` param (spec §48's `window: {from, to}` response envelope
  belongs to 11G); fixing the inherited `PROVIDES`-for-undeclared-operations gap (11C-era, documented not
  changed, matching 11E's own precedent for an adjacent, higher-risk pre-existing gap).
- 14 new tests (305 unit / 105 integration, up from 303/93): `default_since()`'s window arithmetic as
  pure unit tests; Testcontainers tests combining `import_all_sources` (declared baseline) with
  `persist_observation_batch` (observed facts on top, mirroring `test_aggregator.py`'s own pattern) —
  O1's aggregation and independent per-filter behavior; O2 finding the real `order-service ->
  product-service` relation as `CONFIRMED` once both declared and observed evidence coexist on it (and
  correctly resolving `target_id` to the *provider service*, not the raw operation, through `PROVIDES`);
  O3 surfacing an observed-only relation with **no `PROVIDES` edge at all**, proving the
  `OPTIONAL MATCH`/`coalesce()` fix actually matters, not just a theoretical concern; O4's literal
  `NOT_OBSERVED_IN_WINDOW` status and `telemetry_coverage_available` correctness for both a covered and
  an uncovered subject; environment scoping across O2-O4; O5's four coverage signals for a caller, a
  sender/receiver, a service with zero telemetry, and the pinned provider-side gap.

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
