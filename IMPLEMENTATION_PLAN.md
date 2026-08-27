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
  observations at this point in the codebase's history. At the time of this iteration this was treated as
  an accepted, permanent PoC limitation (real Collector batch processors flush by time/size, not trace
  completeness) rather than a bug worth a stateful cross-batch buffer — **this position was later
  superseded by Iteration 11H-B**, which adds exactly such a buffer under spec's own tighter, explicitly
  bounded constraints (TTL-based, never a Neo4j Span store, allowlisted metadata only — deliberately not
  the unbounded "trace store"/causality graph this note originally worried about). Environment/method/route/timestamp are
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

## Iteration 11G — Runtime API / UI / Intent Router (H4)
`Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md` §47-52, §63, §65 (H4.13-H4.18),
§67. **Exit criterion:** the last H4 sub-iteration — 11F's five pure O1-O5 analysis functions become
reachable via REST, the Service Explorer UI, and deterministic NL intents, closing out H4 end-to-end.

- **Two judgment calls, made explicit up front:**
  - *Response envelope*: every existing route module (`analysis.py`, `services.py`, `queues.py`,
    `evidence.py`) returns raw dataclasses/dicts, snake_case, no envelope; spec §48 is the only place
    in the spec+codebase giving an explicit camelCase-enveloped JSON contract
    (`{environment, window: {from, to}, relations: [...]}}`). Decision: the new `app/api/runtime.py`
    module alone uses Pydantic response models with camelCase aliases, applied uniformly to all six
    endpoints (not just the one spec gave an example for) — a bounded exception, not a repo-wide
    convention change. The NL/intent-router path (`/api/query`) deliberately keeps the existing flat
    `dataclasses.asdict()` shape, so the same O-analysis returns differently-shaped JSON via REST vs.
    NL — a documented, accepted consequence, not an oversight.
  - *Environment/window defaulting for NL questions*: O2-O5 require a concrete `environment` (11F: the
    same fact can be `CONFIRMED` in production and `DECLARED_ONLY` in staging simultaneously). Spec's
    own O3/O4/O5 example questions inconsistently name an environment/window inline, and the existing
    `classify()`/`IntentPattern`/`entity_resolver.py` machinery only extracts one named graph entity per
    pattern — no free-text environment/date parsing. Decision: every O-intent always uses a configured
    default environment (`RuntimeAnalysisConfig.default_environment = "production"`, new) and default
    window (`default_window_hours`, from 11F), regardless of question wording — never parsed from text.
- `app/settings.py`, `config.yaml` — `RuntimeAnalysisConfig.default_environment` (new field).
- `app/analysis/runtime.py` — additive only, 11F's five functions untouched: `DEFAULT_ENVIRONMENT`,
  `RuntimeRelationStatus`, `ServiceRuntimeProfile`, `service_runtime_profile()` (composes
  `confirmed_relations`/`observed_only_relations`/`declared_only_relations`/`telemetry_coverage`,
  filtered to one `source_id` in Python — deliberately not adding a `from_id` filter to those four
  tested functions — backing both the new per-service REST endpoint and the Service Explorer's
  Observed section so both consumers get byte-identical results, mirroring how `BLAST_RADIUS` already
  shares `blast_radius.DEFAULT_MAX_DEPTH` with its REST endpoint for the same reason).
- `app/api/runtime.py` (new) — two `APIRouter`s matching spec §47's literal prefix split:
  `runtime_router` (`/api/runtime/relations` for O1, `/api/runtime/services/{id}` for the new profile
  endpoint) and `runtime_analysis_router` (`/api/analysis/runtime/{confirmed,observed-only,declared-only,coverage}`
  for O2-O5, mirroring how `/api/analysis` already houses A1-A5). All Pydantic response models carry a
  `_native()` conversion on `first_seen`/`last_seen` before serialization — Neo4j returns temporal
  properties as `neo4j.time.DateTime`, not `datetime.datetime`, which Pydantic rejects outright on
  serialize (the same class of gotcha 11E's `.to_native()` fix addressed on the read side, now hit for
  the first time on the *write*/response side since 11F's dataclasses are plain and never validate).
  Mounted in `app/main.py`.
- `app/api/ui.py`, `app/templates/service.html` — `service_explorer()` gains an `environment` query
  param + `Settings` dependency, computing an `observed` profile via `service_runtime_profile()`; the
  template's four duplicated inline evidence-rendering snippets are factored into one Jinja macro
  (net simplification) gaining an OBSERVED branch (environment/first_seen/last_seen/observation_count,
  spec §50) alongside the existing DECLARED branch; a new "Observed" section renders each relation with
  a ✓/!/○ (`CONFIRMED`/`OBSERVED_ONLY`/`NOT_OBSERVED_IN_WINDOW`) glyph + legend (spec §49) — the raw
  `status` string is rendered verbatim, never re-worded as "obsolete"/"unused"/"dead" (H4.16, pinned by
  a dedicated negative-assertion test). `_EVIDENCE_BY_IDS_QUERY` (shared with `queue_explorer()`) gains
  the three OBSERVED-only columns; harmless unused columns for `queue.html`, which is explicitly out of
  scope here (spec §49: "existing page is extended," singular).
- `app/intent/model.py`, `app/intent/patterns.py`, `app/analysis/registry.py`, `app/answer_router.py` —
  five new `O#_`-prefixed `ArchitectureIntent` members (spec gives bare names only); five new
  keyword-combination `IntentPattern`s with no `entity_label` (O1-O5 answer "what happened," scoped by
  config defaults, not a named entity) — spec gives verbatim German examples for O3/O4/O5, EN and O1/O2
  phrasings invented consistent with the existing style; `registry.execute()` gains optional
  `since`/`environment` kwargs merged into the handler's `parameters` dict (backward-compatible — the
  existing 2-arg call convention and monkeypatch-based test still work unmodified) plus a `_to_native()`
  conversion mirroring the REST layer's fix, since `QueryResponse.rows` is JSON-serialized too;
  `answer_question()` gains matching kwargs defaulted to `runtime.py`'s own constants, so every existing
  call site (including all tests) keeps working unmodified; `post_query()`/`query_page()` each pass
  `settings.config.runtime_analysis.*` through at their existing call sites.
- 30 new tests (319 unit / 121 integration, up from 305/105): `service_runtime_profile()` composing all
  three statuses correctly for one service + returning `None` for an unknown service; a new
  `tests/integration/test_runtime_api.py` implementing spec §63's Testlandscape verbatim (OrderService →
  ProductService `CONFIRMED`, OrderService → LegacyPricingService `OBSERVED_ONLY`, PaymentService →
  invoice-q `DECLARED_ONLY`) — all six REST endpoints (envelope shape, camelCase keys, §48's literal JSON
  contract pinned exactly on `/observed-only`), the UI Observed section (H4.16 negative-wording assertion,
  OBSERVED evidence block rendering), and NL routing for all five O-intents against a real graph; five new
  parametrized EN/DE intent-recognition blocks in `test_intent_patterns_and_router.py` (pinning
  `result.parameters == {}` — confirms `classify()` stays entirely environment/window-agnostic); two new
  `registry.execute()` tests for the `since`/`environment` merge behavior. One real bug caught by the
  first integration test run (not by design review): building Pydantic response models around 11F's
  `RelationObservation` rows surfaced the `neo4j.time.DateTime` non-serializability gotcha for the first
  time on the response/write side — fixed with a `_native()`/`_to_native()` helper at both new call sites
  (REST layer, NL/registry layer) rather than reopening 11F's tested dataclasses.
- Explicitly deferred beyond 11G (and confirmed out of scope for all of H4, not just this iteration, per
  spec review — not assigned to any of 11A-11G, not required by any H4.# acceptance criterion): §55-57's
  Docker Compose `otel-collector` service (an optional production-hardening layer; `POST /v1/traces`
  already accepts OTLP directly since 11A); §59-60's retention/cleanup job (§59 itself frames 90-day
  retention as a proposal, not a requirement).

## Iteration 11H-A — Evidence Reconciliation Correctness (Runtime Correctness & Robustness)
`Architecture_Intelligence_Platform_11H_Runtime_Correctness_Robustness_Specification.md` §4-5, §19 (I1),
§24 (11H.1-11H.3), §25-26. **Exit criterion:** a relation with both DECLARED and OBSERVED evidence
survives a re-import that drops the declaration, retaining exactly its OBSERVED evidence and
reclassifying as `OBSERVED_ONLY`; a relation shared by two independent declaring services loses only the
reimporting service's evidence; a relation with zero remaining evidence is still deleted. First (P0,
"the highest-priority part of 11H") of six planned 11H sub-iterations (11H-A..11H-F) hardening the H4
runtime model before H5 — only 11H-A is implemented now; 11H-B..F are fully designed in the approved plan
but deliberately not built yet.

- **Root cause, confirmed by direct inspection** (already flagged as a known, unfixed risk in
  `H4_REVIEW.md`'s "known limitations" section since 11E): `app/graph/importer.py::_EXPIRE_RELATIONS_QUERY`
  unconditionally `DELETE`d a stale relation the instant its `sources` array emptied, without ever
  inspecting `r.evidence_ids`/`evidence_type` — discarding any OBSERVED evidence a relation had
  accumulated from the H4 telemetry pipeline, purely because its *declared* side stopped being declared.
  Root cause of why `sources` was the wrong signal: `ObservedEvidence` has no `sources` field at all
  (`aggregator.py` never sets one), so OBSERVED evidence was never eligible for the *node*-level
  staleness path either — it just silently vanished with the deleted relation edge, becoming an orphaned
  Evidence node no query could reach (O1-O5 traverse from the relation's `evidence_ids`, never
  Evidence→relation).
- **Fix**: `_EXPIRE_RELATIONS_QUERY` now recomputes `r.evidence_ids` before deciding whether to delete —
  excluding only the ids that are (a) `evidence_type = 'DECLARED'` **and** (b) attributed to the
  reimporting `$service_id` via that specific Evidence node's own `sources` array — and deletes the
  relation only once `evidence_ids` is truly empty. This correctly preserves another service's DECLARED
  evidence on a shared relation (spec §5.3) and all OBSERVED evidence unconditionally, while still
  deleting genuinely evidence-less stale relations exactly as before. Uses a list-comprehension +
  `EXISTS {}` form (not `UNWIND ... collect(...)`) deliberately: `UNWIND` over an empty `evidence_ids`
  list produces zero rows and would silently drop the relation from the rest of the query pipeline,
  incorrectly letting an evidence-less relation survive forever — the list comprehension evaluates to
  `[]` on empty input and keeps the relation in scope. Mirrors the `EXISTS { UNWIND r.evidence_ids AS eid
  MATCH (e:Evidence {id: eid}) WHERE ... }` idiom already established in `app/analysis/runtime.py`'s
  `_OBSERVED_EXISTS`/`_DECLARED_EXISTS` constants rather than inventing a new one. No changes needed in
  `plan_reconciliation()` (`app/graph/reconciliation.py`) — its pure set-difference computation of *which*
  relation keys are stale was already correct; only what happens once a key is flagged stale changes.
  Confirmed non-conflicting with the existing node-level staleness path
  (`_STRIP_STALE_EVIDENCE_QUERY`/`_EXPIRE_NODES_QUERY`, which fires only when an entire Evidence node
  itself disappears, e.g. a whole source file/revision — a different, complementary trigger from "one
  relation triple dropped from an otherwise-still-live import").
- Explicitly deferred (11H-B through 11H-F, fully designed in the approved plan, not built yet):
  cross-batch HTTP CLIENT/SERVER correlation via a new bounded TTL buffer (11H-B, P0); CLIENT_ONLY/
  SERVER_ONLY partial-instrumentation observations (11H-C, depends on 11H-B); an OBSERVED `PROVIDES`
  relation for runtime-discovered provider operations (11H-D — plan design work already surfaced a real,
  independently-reproduced operation-id normalization bug between `openapi_adapter.py`'s declared minting
  and `operation_resolver.py`'s Fall-B minting that would silently break 11H.10's reconciliation
  requirement; documented with its ~30-occurrence blast radius, not yet fixed since 11H-D isn't built);
  qualitative telemetry coverage classification for `NOT_OBSERVED_IN_WINDOW` results (11H-E); an OTel
  Collector-based public demo topology (11H-F). See `/home/michael/.claude/plans/scalable-soaring-grove.md`
  for the complete, code-level design of all six sub-iterations.
- 2 new tests (319 unit unchanged / 123 integration, up from 121 — Cypher-only fix, no unit-level surface):
  a Testcontainers test combining `import_service` (declare) + `persist_observation_batch` (observe) + a
  re-import dropping the declaration on the same relation — a combination the test suite had never
  exercised before — asserting the relation survives, the declared evidence id is gone, the observed
  evidence id remains, and O2/O3 (`confirmed_relations`/`observed_only_relations`) correctly reclassify
  it from `CONFIRMED` to `OBSERVED_ONLY`; a second test extending the existing
  `test_shared_relation_accumulates_evidence_from_both_declaring_services` scenario with OBSERVED
  evidence layered on top, proving the multi-declarer case survives with exactly the other declarer's
  DECLARED evidence and the OBSERVED evidence intact (genuinely new coverage — the original test never
  combined the multi-declarer case with observed evidence).

## Iteration 11H-B — HTTP Correlation Robustness (Runtime Correctness & Robustness)
`Architecture_Intelligence_Platform_11H_Runtime_Correctness_Robustness_Specification.md` R2/§6/§15/§16,
§19 (I2), acceptance criteria 11H.4/11H.5/11H.14. **Exit criterion:** a CLIENT span delivered in one
`POST /v1/traces` and its matching SERVER span delivered in a later, separate `POST /v1/traces` still
produce exactly one `CALLS` observed fact. Second of six 11H sub-iterations; 11H-A (evidence
reconciliation) is already committed.

- `app/telemetry/correlation_buffer.py` (new) — `PendingHttpSpan` (11H spec §15's suggested shape,
  extended with `service_namespace`/`service_version` — already-structured identity fields this codebase
  reads from `RuntimeSpan` today, not raw/unbounded attribute data, so including them doesn't violate the
  "no raw payload" allowlist principle spec §6.3/§13/§14 require) and `HttpCorrelationBuffer` — this
  codebase's **first** stateful, TTL/lock/in-process-mutable construct (confirmed zero prior precedent
  anywhere in `app/`: no cachetools, no `threading.Lock`/`asyncio.Lock`, no background task). Deliberately
  simple: no background sweep task (matches `POST /v1/traces`'s fully synchronous, request-driven style —
  Neo4j calls run directly on the event loop thread, so there's no true concurrent request processing to
  defend against beyond cheap insurance); lazy, on-access eviction only, both by TTL and by a hard
  `max_pending_spans` bound (oldest entry evicted first via `OrderedDict`'s insertion-order guarantee) —
  must never become an unbounded trace store (spec §6.3). Both `_pending_clients`/`_pending_servers` maps
  key on the same pairing identity a matching counterpart would look itself up under, so whichever side
  arrives second finds the other already waiting, regardless of arrival order.
- `app/telemetry/adapter.py` — `_find_correlated_pairs` now also returns the batch's leftover (unpaired)
  CLIENT/SERVER spans; `correlate_http_call_observations` gains a keyword-only `correlation_buffer:
  HttpCorrelationBuffer | None = None` parameter (default preserves exactly the original single-batch-only
  behavior — all 23 pre-existing unit tests pass unmodified). The per-pair fact-construction logic
  (operation resolution, evidence, the fact itself) was factored into a shared `_build_call_fact()` helper
  reused by both the in-batch loop (unchanged behavior, confirmed via the untouched 23-test suite) and the
  new cross-batch phase, avoiding two divergent implementations of the same core logic. Cross-batch
  matches resolve caller/provider identity via `resolve_service()` directly (not `resolve_runtime_span()`,
  since a buffered `PendingHttpSpan` isn't a full `RuntimeSpan`) and get `correlationMode = CLIENT_SERVER`
  — identical to an in-batch pair (spec §6.4: the mode distinguishes evidence *strength*, not batch
  locality; persisting `correlation_mode` itself is 11H-C's job, not built yet). A leftover SERVER span's
  environment/method/route are validated (and reported `NO_ENVIRONMENT`/`NO_STABLE_ROUTE` if missing)
  *before* ever being buffered — a SERVER-kind `PendingHttpSpan` in the buffer is therefore always known
  to carry valid environment/method/route by construction, asserted explicitly where a match is consumed.
  Rewrote the function's own docstring, which previously stated cross-batch correlation was "an accepted,
  permanent PoC limitation... not a bug" and that a stateful buffer would be "exactly the trace store...
  spec §4.2 explicitly excludes" — this iteration's spec deliberately supersedes that position with a
  narrower, explicitly-bounded construct; `IMPLEMENTATION_PLAN.md`'s own 11C entry (above) making the
  identical claim was also corrected, so no contradictory permanent-looking claims remain in the repo.
- `app/settings.py`, `config.yaml` — new `HttpCorrelationConfig(enabled, ttl_seconds, max_pending_spans)`
  nested under `TelemetryConfig.http_correlation` (kebab-case YAML aliases, following the existing
  `import_`/`alias="import"` precedent — this codebase has no alias-generator convention).
  `model_config = {"populate_by_name": True}` added to both so tests can construct these directly by
  Python attribute name while YAML loading still works via the kebab-case alias. Defaults are safe and the
  block is fully optional — the app starts unchanged if absent (spec §22).
- `app/main.py` — `lifespan()` constructs `app.state.http_correlation_buffer` (or `None` if
  `enabled=False`), mirroring the existing `app.state.driver`/`app.state.llm_provider` pattern exactly.
  `app/deps.py` — new `get_http_correlation_buffer()` accessor, mirroring `llm_provider`'s
  `getattr(..., None)` optional-object pattern. `app/api/telemetry.py::post_traces` injects it and passes
  it through to `adapt()`.
- Explicitly deferred (11H-C's job, not built yet): `CorrelationMode` enum / `correlation_mode` field
  persistence and read-stack exposure; the `PEER_SERVICE` semconv constant; CLIENT_ONLY/SERVER_ONLY
  single-sided observation emission (depends on this buffer existing, which it now does). Also deferred:
  any UI/API surfacing of the buffer's diagnostic counters (spec §23 only requires they exist/are
  loggable); Strategy B (single-sided-observation-with-later-enrichment) — spec §6.3 explicitly prefers
  the bounded-buffer Strategy A implemented here.
- 11 new tests (329 unit / 124 integration, up from 319/123 after 11H-A): buffer unit tests
  (`test_correlation_buffer.py`) for both arrival orders, mismatched-trace-id non-matching, a SERVER span
  with no `parent_span_id` never buffering/matching, TTL expiry, and `max_pending_spans` oldest-eviction;
  additive `test_adapter.py` cases proving cross-batch correlation works in both arrival orders through
  the real `correlate_http_call_observations()` function, that `correlation_buffer=None` preserves
  original behavior exactly, and that a leftover SERVER span missing method/route is reported unresolved
  rather than buffered uselessly; a new Testcontainers integration test (I2,
  `test_telemetry_api.py`) posting a CLIENT-only OTLP batch then a separate SERVER-only OTLP batch against
  the real FastAPI app, asserting zero `CALLS` relations after the first POST and exactly one after the
  second — targeting an undeclared `OrderService -> ReviewService` pair distinct from the module's other
  test's declared relation, since this test module has no per-test Neo4j reset.

## Iteration 11H-C — Partial Instrumentation / Single-Sided HTTP Observation (Runtime Correctness & Robustness)
`Architecture_Intelligence_Platform_11H_Runtime_Correctness_Robustness_Specification.md` R3/§7/§14/§17,
§19 (I3), acceptance criteria 11H.6/11H.7/11H.8/11H.14. **Exit criterion:** a CLIENT span with a stable,
resolvable target service identity produces an observed `CALLS` candidate even with no SERVER span ever
arriving; a SERVER span alone never invents a caller; ambiguous/incomplete cases stay
`UnresolvedObservation`, never guessed. Third of six 11H sub-iterations; 11H-A (evidence reconciliation,
`12a7a0d`) and 11H-B (cross-batch correlation buffer, `e2da3ef`) are already committed.

- **A real design gap surfaced re-verifying the plan against 11H-B's actual code, before writing any new
  code**: `_pending_span_from_client` extracted no `method`/`route`/target-identity from a CLIENT span at
  all, since the paired/cross-batch `CALLS` path always sources those from the SERVER side (H4.6).
  CLIENT_ONLY has no SERVER side to source from — the CLIENT span's own attributes are the *only* place
  spec §7.2's method/route/target-identity can come from, so this iteration extends
  `_pending_span_from_client` to also read them (harmless/inert for the existing `CLIENT_SERVER` paths,
  which never read these fields back off a matched client).
- `app/telemetry/semconv/http.py` — new `PEER_SERVICE = "peer.service"`, the **sole** allowlisted way to
  resolve a CLIENT-only call's target service identity (spec §7.5: never guess from `server.address`/an
  IP alone).
- `app/telemetry/correlation_buffer.py` — new `sweep_expired()` (returns `(expired_clients,
  expired_servers)` instead of silently discarding what ages out — `_evict_expired_locked` is now a thin
  wrapper around the same underlying `_pop_expired_locked`, so `offer_server`/`offer_client`'s existing
  pre-match housekeeping and all of 11H-B's tests are unaffected). `correlate_http_call_observations` calls
  it once, at the very start, before processing this batch's own leftover spans.
- `app/telemetry/adapter.py` — CLIENT_ONLY emission (spec §7.2): for each expired CLIENT span, resolves
  caller identity via `resolve_service()`, requires `method`+`route` present (else `CORRELATION_EXPIRED`),
  requires `target_identity` (`peer.service`) present (else `MISSING_TARGET_IDENTITY`), requires
  `environment` present (else `NO_ENVIRONMENT`), then resolves the target the same way and builds a
  `CALLS` fact with `correlation_mode="CLIENT_ONLY"`. SERVER_ONLY (spec §7.3): every SERVER
  `PendingHttpSpan` the buffer stores was already validated (environment/method/route present) before
  being offered, so the *only* thing a SERVER_ONLY case can lack is the caller — which nothing in this
  codebase's current semconv allowlist can identify from a SERVER span alone — so this always reports
  `MISSING_CALLER_IDENTITY`, satisfying 11H.8 as a real, tested structural guarantee rather than an
  accident of missing data. New `MISSING_TARGET_IDENTITY`/`MISSING_CALLER_IDENTITY`/`CORRELATION_EXPIRED`
  reason constants (spec §17 lists three more with an "extend as needed" framing; not added since none has
  a concrete trigger site yet — `NO_STABLE_ROUTE` already covers route instability). Messaging retrofit in
  `correlate_queue_observations`: `receive`/`process` both still map to `RECEIVES_FROM` at the
  relation-type level (unchanged) but now carry distinct `MESSAGING_RECEIVE`/`MESSAGING_PROCESS`
  `correlation_mode` values, alongside `MESSAGING_SEND` for the send path — every `ObservedFactCandidate`
  in the system now gets a populated `correlation_mode`, not just the HTTP ones.
- `app/telemetry/model.py` — new `CorrelationMode(StrEnum)`: `CLIENT_SERVER`/`CLIENT_ONLY`/`SERVER_ONLY`/
  `MESSAGING_SEND`/`MESSAGING_RECEIVE`/`MESSAGING_PROCESS` — a source of named constants only, matching
  how `Provenance.evidence_type` stays a plain `str` even with `EvidenceType` as a companion enum.
  `app/provenance/model.py::ObservedEvidence` gains `correlation_mode: str | None = None` — **optional**,
  not required, so every pre-11H-C construction site across `test_adapter.py`/`test_runtime_analysis.py`/
  `test_aggregator.py`/`test_importer.py`/`test_telemetry_api.py` keeps working unmodified. Not duplicated
  onto `ObservedFactCandidate` itself — `fact.evidence.correlation_mode` is the one source of truth.
- `app/telemetry/aggregator.py` — `merge_evidence` now keeps the *stronger* of two differing
  `correlation_mode`s on the same bucket (spec §14: "preserve the strongest mode"), via a small
  `_CORRELATION_MODE_STRENGTH` ordering (`CLIENT_SERVER` > `CLIENT_ONLY`/`SERVER_ONLY` >
  `MESSAGING_*` > `None`). `_READ_EVIDENCE_QUERY` gains the new column.
- Explicitly deferred, corrected from the original roadmap sketch written before 11H-B existed: that
  sketch proposed a SERVER_ONLY case emitting a one-sided `PROVIDES` fact via "11H-D's mechanism" — 11H-D
  is not implemented yet, so there's no such mechanism to hook into; revisit specifically when 11H-D
  lands. Also deferred: full read-stack exposure of `correlation_mode` (API/UI — none of 11H.6/11H.7/
  11H.8 name a response shape, and spec §21 only requires new metadata be "backward-compatible where
  practical"); the `UNSTABLE_HTTP_ROUTE`/`AMBIGUOUS_SERVICE`/`UNSUPPORTED_SPAN` reason codes (no concrete
  trigger site yet); `server.address`/`server.port`-based target resolution (spec §7.5 forbids guessing
  from network identifiers alone).
- 14 new tests (342 unit / 125 integration, up from 329/124): buffer `sweep_expired()` tests (returns and
  clears only genuinely-expired entries, idempotent, reports both clients and servers); adapter tests for
  `correlation_mode == "CLIENT_SERVER"` on both in-batch and cross-batch-matched pairs, CLIENT_ONLY's four
  branches (`peer.service` present → fact; absent → `MISSING_TARGET_IDENTITY`; no method/route at all →
  `CORRELATION_EXPIRED`; no environment → `NO_ENVIRONMENT`), and SERVER_ONLY always reporting
  `MISSING_CALLER_IDENTITY` while still recording the provider as an observed-only entity; `correlation_mode`
  assertions added to the existing SEND/RECEIVE/PROCESS messaging tests; aggregator strength-ordering merge
  tests (existing-stronger, seed-stronger, `None`-vs-real-mode in both directions); a new Testcontainers
  integration test (I3) using a short-TTL buffer, a real `time.sleep` past the TTL, and a second unrelated
  `POST /v1/traces` to trigger `sweep_expired()`, asserting a real, persisted `CALLS` relation with
  `correlation_mode = "CLIENT_ONLY"`. One test-authoring bug self-caught before landing: the first draft of
  the CLIENT_ONLY unit tests reused `_client_server_pair()`'s fixture helper, whose `**kwargs` only ever
  applied to the SERVER half — fixed by constructing the CLIENT span directly via `_span(...)`. A second,
  identical-shaped bug in the integration test (the new CLIENT-only span's resource was missing
  `deployment.environment.name` entirely) was caught the same way, by reading the resulting
  `NO_ENVIRONMENT` unresolved reason rather than assuming the feature itself was broken.

## Iteration 11H-D — Observed Provider Relation for Runtime-Discovered Operations (Runtime Correctness & Robustness)
`Architecture_Intelligence_Platform_11H_Runtime_Correctness_Robustness_Specification.md` R4/§8, acceptance
criteria 11H.9/11H.10. **Exit criterion:** a runtime-discovered, stable provider operation (resolved
`OBSERVED_ONLY`, spec §22/§23 Fall B) receives its own observed `PROVIDES` relation, not just the `CALLS`
edge pointing at it; a later real OpenAPI declaration of that same method+path for that same service
reconciles onto the *same* Operation node, never a duplicate. Fourth of six 11H sub-iterations; 11H-A
(`12a7a0d`), 11H-B (`e2da3ef`), 11H-C (`d9c513a`) are already committed.

- **A real, pre-existing correctness bug surfaced and fixed first, as a required prerequisite**: declared
  operation ids were minted from the *bare service slug* (`app/ingestion/openapi_adapter.py`'s
  `ids.operation_id(service_id, method, path)`, using the raw `"product-service"` parameter) while
  `operation_resolver.py`'s Fall-B minting always used the *full* canonical service id
  (`ids.operation_id(provider_service_id, ...)`, e.g. `"service:product-service"`) — every other canonical
  id in the system uses the full opaque form, this was the sole outlier. Left unfixed, a runtime-discovered
  operation and a later-declared version of the exact same logical operation would land on two different
  Neo4j nodes, silently breaking reconciliation — exactly what 11H.10 exists to guarantee against. Fixed at
  the root in `openapi_adapter.py` (mint from `full_service_id`), not by special-casing
  `operation_resolver.py`'s already-correct Fall B. Required updating every test asserting a *real*
  `parse_openapi()`/pipeline/Neo4j-imported operation id (`test_openapi_adapter.py`, `test_pipeline.py`,
  `test_manifest_adapter.py`'s real-fixture test, `test_importer.py`'s end-to-end test, `test_adapter.py`,
  `test_runtime_api.py`, `test_aggregator.py`, `test_telemetry_api.py`, `test_runtime_analysis.py` — roughly
  15 real call sites across 9 files); left untouched every test using a fully synthetic, internally
  self-consistent id/candidate fixture (confirmed file-by-file, not assumed), since those never depended on
  the real minting convention in the first place.
- `app/telemetry/adapter.py::_build_call_fact` now returns `list[ObservedFactCandidate]` instead of
  `ObservedFactCandidate | None` (empty list when the operation can't be resolved, same as before). When
  the resolved operation's `discovery_status == OBSERVED_ONLY`, it also builds and returns a second
  `PROVIDES` fact (`provider_service_id -> operation_id`) alongside the `CALLS` fact, with its own
  deterministic `observed_evidence_id(..., "PROVIDES", ...)` and `correlation_mode` copied from whichever
  mode produced the call (`CLIENT_SERVER`/`CLIENT_ONLY`). Never emitted for an already-`DECLARED` operation
  — it already has a real `PROVIDES` edge from the OpenAPI import; a redundant observed one would be pure
  noise. All four call sites (in-batch pairs, cross-batch CLIENT_ONLY, cross-batch leftover-servers,
  cross-batch leftover-clients) updated to `facts.extend(...)` the returned list; gained an optional
  `provider_service_version` parameter, threaded from the SERVER/`PendingHttpSpan` side wherever available
  (unavailable for CLIENT_ONLY, which has no SERVER-side span at all — left `None` there, an already-
  optional field).
- **A second, previously-latent bug this feature's own change exposed, found via a real integration-test
  failure rather than assumed**: `operation_resolver.py`'s `_CANDIDATES_QUERY` (`MATCH
  (s:Service)-[:PROVIDES]->(o:Operation)`) never needed to handle an `OBSERVED_ONLY` operation before, since
  such an operation never had a `PROVIDES` edge at all prior to this iteration. Once it does, the query
  starts returning candidates whose `method`/`path` properties are `null` (an `OBSERVED_ONLY` Operation node
  is only ever `MERGE`d via the stub-entity path — id/name/discovery_status — never given real method/path
  properties), and `resolve_operation`'s Fall-A comparison loop crashed on `candidate.method.upper()`. Fixed
  by adding `WHERE o.method IS NOT NULL AND o.path IS NOT NULL` to `_CANDIDATES_QUERY`, correctly scoping
  Fall-A matching to genuinely declared operations only — exactly what it always implicitly was before
  `OBSERVED_ONLY` operations could reach this query.
- 3 new unit tests (345, up from 342): an `OBSERVED_ONLY` in-batch pair produces both `CALLS` and
  `PROVIDES` facts with distinct evidence ids and matching `correlation_mode`; a `DECLARED` (Fall A) pair
  still produces only `CALLS`; a `CLIENT_ONLY`-resolved `OBSERVED_ONLY` operation also produces the second
  `PROVIDES` fact. One existing integration test (`test_adapter.py::test_unknown_route_mints_observed_...`)
  updated from asserting exactly one fact to asserting two, since its scenario is itself an `OBSERVED_ONLY`
  resolution.
- 2 new integration tests (127, up from 125): **I4** (`test_telemetry_api.py`) — a real `POST /v1/traces`
  CLIENT/SERVER pair for an undeclared route on a real declared provider (`ProductService`) persists an
  `Operation` node with `discovery_status = OBSERVED_ONLY` *and* a `PROVIDES` edge from the provider
  `Service`, backed by `OBSERVED` evidence. **I5** — runs the same scenario, then imports a real OpenAPI
  document declaring that exact method+path for the same service via `import_service()`; asserts exactly
  one `Operation` node exists (not two) and its `PROVIDES` edge now carries both `DECLARED` and `OBSERVED`
  evidence types — the test the id-normalization fix exists to make pass for the right reason, not silently
  pass-by-coincidence or fail.
- Explicitly deferred (unchanged from the original roadmap): SERVER_ONLY's own one-sided `PROVIDES`
  emission (11H-C left this for "when 11H-D lands" — SERVER_ONLY still never identifies a caller at all per
  spec §7.3, so there is no `CALLS`-fact code path to attach a `PROVIDES` fact to the way this iteration's
  mechanism assumes; revisit only if a future iteration gives SERVER_ONLY its own fact-emission path).

## Iteration 11H-E — Coverage Qualification for Negative Findings (Runtime Correctness & Robustness)
`Architecture_Intelligence_Platform_11H_Runtime_Correctness_Robustness_Specification.md` R7/§11,
acceptance criteria 11H.11/11H.12. **Exit criterion:** an O4 `NOT_OBSERVED_IN_WINDOW` result can expose a
qualitative `SUFFICIENT`/`PARTIAL`/`NONE`/`UNKNOWN` coverage classification (no numeric confidence score,
per spec §11.2), so a caller can tell "we watched for this and didn't see it" apart from "we have no idea
whether we'd have seen it" — without ever implying `obsolete`/`unused`/`dead` (11H.12, already enforced,
re-verified unchanged). Fifth of six 11H sub-iterations; 11H-A/B/C/D (`12a7a0d`/`e2da3ef`/`d9c513a`/
`0559509`) are already committed.

- `app/analysis/runtime.py` — new `COVERAGE_SUFFICIENT`/`COVERAGE_PARTIAL`/`COVERAGE_NONE`/
  `COVERAGE_UNKNOWN` string constants (matching this file's existing plain-constant style, e.g.
  `NOT_OBSERVED_IN_WINDOW`) and `_classify_coverage(service_coverage, relation_type, *,
  qualification_enabled)`, derived entirely from O5's already-computed per-service `http_observed`/
  `messaging_observed`/`spans_observed` signals — no new Cypher. `SUFFICIENT` when the service has observed
  traffic of the *same* relation kind as the not-observed row (`CALLS` → `http_observed`,
  `SENDS`/`RECEIVES_FROM` → `messaging_observed`) in this window/environment; `PARTIAL` when it emits some
  telemetry but not of that kind; `NONE` when it emitted no usable telemetry at all (spec §11.1's Case B);
  `UNKNOWN` when qualification is disabled or there's no coverage row for the subject at all. `coverage:
  str` added to `DeclaredOnlyRelation`/`RuntimeRelationStatus` alongside the existing
  `telemetry_coverage_available: bool` (kept, unchanged semantics — additive, backward-compatible per spec
  §21). `declared_only_relations()`/`service_runtime_profile()` gain an optional `qualification_enabled:
  bool = True` parameter (spec §22's `telemetry.coverage.qualification-enabled` kill switch).
- `app/settings.py` — new `CoverageConfig` (`qualification_enabled: bool = True`, alias
  `qualification-enabled`) nested under `TelemetryConfig.coverage`; `config.yaml` gets the matching example
  block. Must start unchanged with the section absent (spec §22) — covered by a new settings test.
- `app/api/runtime.py` — `DeclaredOnlyRelationOut`/`ServiceRuntimeRelationOut` gain `coverage: str`/
  `coverage: str | None`; `get_declared_only`/`get_service_runtime_profile` thread
  `settings.config.telemetry.coverage.qualification_enabled` through and populate the new field.
  `app/templates/service.html` shows `(coverage: X)` next to a `NOT_OBSERVED_IN_WINDOW` row (the
  implementation sequence's "API/UI representation" step) — checked against the existing
  obsolete/unused/dead forbidden-word tests, which still pass unchanged.
- **A real, pre-existing correctness bug found and fixed, not introduced by this iteration**: writing a
  test that (correctly, for the first time) exercised O2/O3/O4 together against a graph where the *same*
  environment has both a `CONFIRMED` and a `DECLARED_ONLY` relation surfaced that `_O1_QUERY`/
  `_status_query` (O2/O3)/`_O4_QUERY` were all silently leaking rows into the wrong category. Root cause:
  Cypher parses a `WHERE` clause written directly after `OPTIONAL MATCH` as part of that `OPTIONAL MATCH`'s
  own pattern, not as a row filter — when the declared/observed `EXISTS{}` guard evaluated false, the row
  wasn't dropped, it was kept with `provider` wrongly null-padded (falling back to the raw operation id via
  `coalesce(provider.id, o.id)`). Every existing O1/O2/O3/O4 test happened to use a fresh, single-purpose
  environment where no relation's guard was ever false while another relation's guard was true in the same
  query execution, so this was invisible until now — but it would affect *any* real deployment where a
  service has both confirmed and non-confirmed relations in the same environment, which is the normal case,
  not an edge case. Fixed by inserting `WITH a, r, o, provider` between the `OPTIONAL MATCH` and `WHERE` in
  all three queries, forcing the guard to filter the row instead of the optional pattern. Locked in with a
  dedicated regression test (`test_o2_o3_o4_do_not_cross_leak_when_the_same_environment_has_both_confirmed_and_declared_only`)
  reproducing the exact scenario, plus corrected assertions in two tests that had been silently passing for
  the wrong reason (`test_get_service_runtime_profile`, `test_service_runtime_profile_combines_...`) — both
  now assert the real `PARTIAL` coverage classification the bug had been masking as `SUFFICIENT`.
- 7 new unit tests (352, up from 345): `_classify_coverage`'s five cases (disabled → `UNKNOWN`; no
  coverage row → `UNKNOWN`; same-kind observed → `SUFFICIENT` for both `CALLS` and `SENDS`/`RECEIVES_FROM`;
  different-kind observed → `PARTIAL`; nothing observed → `NONE`) plus two new settings tests
  (`qualification-enabled` defaults true when absent, can be set false).
- 4 new integration tests (131, up from 127): two new O4 coverage-classification tests (`PARTIAL`,
  qualification-disabled → `UNKNOWN`; `NONE`/`SUFFICIENT` covered by corrected assertions on two already-
  existing O4 tests), the cross-leak regression test above, and a new declared-only API test asserting
  `"coverage"` in the JSON envelope. Plus corrected/extended assertions (not new test functions) in four
  existing tests: the two O4 coverage tests now also assert `NONE`/`SUFFICIENT`, the UI declared-only test
  now asserts `"coverage: NONE"` renders, and the two profile tests the bug fix changed now assert the real
  `PARTIAL` classification.

## Iteration 11H-F — OpenTelemetry Collector Demo Topology (Runtime Correctness & Robustness)
`Architecture_Intelligence_Platform_11H_Runtime_Correctness_Robustness_Specification.md` R5/R6/§9/§10,
acceptance criteria 11H.15/11H.16. **Exit criterion:** the public demo shows `Demo Services -> OTel
Collector -> Architecture Intelligence Platform` end-to-end, without requiring AIP to act as the
application's primary observability backend; documentation states that principle explicitly. Sixth and
final 11H sub-iteration; 11H-A through 11H-E (`12a7a0d`/`e2da3ef`/`d9c513a`/`0559509`/`64bf0cd`) are already
committed.

- `examples/runtime-demo/otel-collector-config.yaml` — new OTel Collector config: an `otlp` receiver
  (grpc+http), a `batch` processor, and two exporters - `otlphttp/aip` (the required leg, spec §9.2:
  forwards to AIP's `/v1/traces`) and `debug` (the optional second leg, standing in for "an additional
  tracing backend"). Environment-neutral/synthetic values throughout (spec §9.4).
- `examples/runtime-demo/traffic_generator.py` — new standalone script playing the role of "Demo Services"
  in the topology diagram. Rather than standing up four real, separately-running HTTP microservices (the
  `examples/` fixtures are OpenAPI/AsyncAPI *documents*, not runnable applications - explicitly out of
  scope per this repo's own CLAUDE.md), it builds realistic `ExportTraceServiceRequest` protobuf batches
  matching the exact `examples/` topology (order-service CLIENT/SERVER pair calling product-service's
  `GET /products/{id}`; order-service SENDS payment-q; payment-service RECEIVES payment-q and SENDS
  invoice-q; invoice-service RECEIVES invoice-q) and POSTs them to the Collector's OTLP/HTTP receiver on a
  loop, using only `opentelemetry-proto` (already a project dependency, and the same building pattern this
  repo's own integration tests already use) - no OpenTelemetry SDK, no new dependencies.
  `examples/runtime-demo/Dockerfile` packages it as its own tiny image.
- `docker-compose.demo.yml` (new, repo root) — `architecture-intelligence` + `neo4j` (mirroring
  `docker-compose.yml`) plus `otel-collector` (official `otel/opentelemetry-collector` image, config
  bind-mounted) and `traffic-generator` (spec §9.3's five required compose services). `OPENAI_API_KEY` is
  optional here (`${OPENAI_API_KEY:-}`), unlike the base compose file - this demo is about runtime
  telemetry, not the LLM query layer, and forcing an API key would be an unnecessary barrier to trying it.
- **Two real, pre-existing bugs found and fixed by actually running the demo stack end-to-end** (Docker was
  available in this session, so `docker compose -f docker-compose.demo.yml up --build` was run for real
  rather than trusting the YAML/Dockerfile by inspection alone):
  1. `Dockerfile` never copied `config.yaml` or `examples/` into the image - `app/main.py`'s
     `CONFIG_PATH` defaults to the relative path `config.yaml`, resolved against the container's `WORKDIR`,
     so the app crashed on startup with `FileNotFoundError` on *every* `docker compose up`, including the
     pre-existing base `docker-compose.yml` - apparently never previously exercised via a real container
     run in this project's history. Fixed by adding `COPY config.yaml ./` and `COPY examples ./examples`
     alongside the existing `COPY app ./app`.
  2. The OTel Collector's `otlphttp` exporter defaults to gzip-compressing its outgoing HTTP body, but
     AIP's `/v1/traces` reads the raw request body as an uncompressed protobuf message and doesn't negotiate
     `Content-Encoding` (spec §8's ingestion contract) - every Collector→AIP export failed with a 400 until
     `compression: none` was added to the `otlphttp/aip` exporter's config. Confirmed fixed by watching a
     real `200 OK` in the app's own logs and then querying `GET /api/runtime/relations?environment=demo`
     against the live stack and seeing the generator's synthetic relations actually land in the graph.
- `README.md` — new "Runtime telemetry (OpenTelemetry)" section: documents `/v1/traces` as the ingestion
  boundary, states explicitly that AIP is an additional telemetry consumer, never the primary observability
  backend (11H.16), reproduces R6/spec §10's recommended production topology (Collector fans out to both a
  primary observability backend and AIP in parallel) and its failure-isolation principle (buffering/retry
  belongs in Collector/deployment config, not AIP), and gives the `docker-compose.demo.yml` usage
  instructions.
- No new unit/integration tests - this iteration is infrastructure (Docker Compose/Collector config) and
  documentation, not application code; its real verification was the actual end-to-end run described above,
  not something meaningfully expressible as a `pytest` test. 352 unit / 131 integration tests unchanged and
  still green (confirmed via a full re-run after all changes).
- Explicitly out of scope (per spec §9.2/§10 and this repo's own non-goals list): a persistent-queue/
  production-grade Collector configuration (spec §10 explicitly says 11H doesn't require this - it only
  requires the *documentation* to state the principle); running the `examples/` fixtures as real, separately
  addressable HTTP services.

## Iteration 12B — Documentation (Open Source Readiness)
`Architecture_Intelligence_Platform_H5_Open_Source_Readiness_Specification.md` §10-12 (README),
§16-19 (docs/ target structure, canonical model, graph/evidence model, adapter extension point), §33-34
(security model, OpenTelemetry privacy model), acceptance criteria H5.6/H5.12-H5.19/H5.25/H5.26/H5.33.
**Exit criterion:** the platform is documented as a real public-facing docs set, not just spec PDFs/
markdown and code comments - every 11H-era invariant (fact/evidence, observed `PROVIDES`, correlation
modes, coverage qualification) explicitly written down, not just implemented. Second of six H5
sub-iterations; only 12A (Legal & Repository Sanitization, `e641370`) was committed before this one.

- `README.md` - full rewrite to spec §10's structure (`Why? / Features / Declared vs Observed /
  Quick Start / Example / Architecture / Deterministic Analyses / OpenTelemetry / Natural Language
  Queries / Documentation / Contributing / Project Status / License`), replacing the previous
  minimal README that still framed the project as "9 iterations of the PoC complete" with no
  mention of H4/11H/runtime telemetry at all. Uses spec §10's literal hero line and spec §57's
  literal License footer. Project Status now accurately lists the PoC + H1-H4 hardening + the full
  11H roadmap as complete and H5 as in progress.
- New `docs/` directory - all 12 files from spec §16's target structure (`architecture.md`,
  `canonical-model.md`, `graph-model.md`, `evidence.md`, `ingestion.md`, `analyses.md`,
  `semantic-validation.md`, `opentelemetry.md`, `configuration.md`, `security-model.md`,
  `development.md`, `adapter-development.md`), each grounded in the actual current implementation
  (function/file names, real constant values, real config defaults - never invented), matching the
  project's own "no fact without traceable provenance" principle. Highlights:
  - `graph-model.md` states the two 11H fact/evidence invariants explicitly (`Fact exists iff
    supporting Evidence exists`; `Removing DECLARED evidence ⇏ removing OBSERVED evidence`, H5.13)
    and documents the 11H-D observed-`PROVIDES`-for-runtime-discovered-operations extension and its
    later-declaration reconciliation guarantee (H5.14).
  - `opentelemetry.md` is the largest file - the full attribute allowlist (all 16 semconv
    constants across `resources.py`/`http.py`/`messaging.py`), explicit definitions of
    `CLIENT_SERVER`/`CLIENT_ONLY`/`SERVER_ONLY`/`UNRESOLVED` (H5.15), cross-batch correlation
    (H5.16), the fixed unresolved-reason-code table, the `SUFFICIENT`/`PARTIAL`/`NONE`/`UNKNOWN`
    coverage classification (H5.17), and the explicit `observation_count ≠ exact request count`
    caveat (H5.18).
  - `security-model.md` documents the bounded/TTL-based/no-raw-payload/no-Span-node HTTP
    correlation buffer as its own explicit trust boundary (H5.25), with an explicit sentence
    distinguishing short-lived correlation state from persisted Architecture Evidence (H5.26).
  - `adapter-development.md` presents spec §19's two conceptual `Protocol` interfaces honestly -
    today's adapters are plain functions honoring the same contract, not classes implementing these
    Protocols yet; the doc says so explicitly rather than overstating current code (H5.19).
  - `configuration.md` states the LLM-optional guarantee (H5.20) - verified against
    `app/main.py:37-40`'s existing `llm_provider = None` fallback, no code change needed.
- `docs/specifications/` (H5.33) - **copied, not moved**, the four existing root-level spec markdown
  files under spec §16's suggested clean names (`h1-h3-hardening.md`, `h4-opentelemetry.md`,
  `11h-runtime-correctness-robustness.md`, `h5-open-source-readiness.md`), plus a new `poc.md`
  pointer to the root PDF spec (not a PDF-to-markdown conversion - disproportionate, ungrounded work
  for a frozen historical document). Copied rather than moved specifically to avoid rewriting
  `IMPLEMENTATION_PLAN.md`'s own ~15 existing citations to the root-level filenames, a large,
  purely-organizational blast radius for what spec §16 itself frames as an optional structure -
  H5.33 only requires `docs/specifications/` to *contain* the design history, not that the root
  copies disappear.
- No application code touched - 352 unit / 131 integration tests unchanged and still green (a
  documentation-only iteration, mirroring 11H-F's own precedent for verification: direct inspection
  and cross-reference spot-checks against the cited source, not new pytest cases).
- Explicitly out of scope (later H5 iterations per spec §52): `CONTRIBUTING.md`/`SECURITY.md`/
  `CODE_OF_CONDUCT.md`/`SUPPORT.md`/issue and PR templates (12E); GitHub Actions/CodeQL/container
  scanning/GHCR publishing (12D); screenshots/GIF, repository topics, social preview, good-first-issue
  tickets, CHANGELOG/ROADMAP, the version tag/release itself (12C tail end/12E/12F). The README's
  Contributing section is worded as a placeholder rather than linking a `CONTRIBUTING.md` that
  doesn't exist yet.

## Iteration 12C — Demo & Quick Start (Open Source Readiness)
`Architecture_Intelligence_Platform_H5_Open_Source_Readiness_Specification.md` §12-15 (Quick Start,
demo data/landscape, Collector-based runtime demo), §50 (Release Gate's 11H reconciliation and
cross-batch scenarios), acceptance criteria implied by H5.6/H5.15/H5.16. Third of six H5
sub-iterations; 12A (`e641370`) and 12B (`99cb48c`) were committed before this one.

**Exit criterion:** a previously uninvolved developer can run `docker compose -f
docker-compose.demo.yml up` and, following nothing but `examples/runtime-demo/README.md`, actually
observe all three declared-vs-observed states plus the two scenarios spec §50 names as release-
blocking if broken - not just read about them.

- `examples/runtime-demo/traffic_generator.py`:
  - Adds an `OrderService -> LegacyPricingService` CLIENT/SERVER pair to every cycle (spec §14's
    "Zusätzlich H4" topology addendum) - `LegacyPricingService` is declared nowhere in `examples/`,
    so this surfaces as a live `OBSERVED_ONLY` finding instead of something only described in prose.
  - Adds `send_cross_batch_pair()`, run every 4th cycle: sends the OrderService/ProductService
    CLIENT and SERVER spans as two separate OTLP requests ~3s apart (well inside the correlation
    buffer's 60s default TTL) - exercises spec §50's "CLIENT span in request A, SERVER span in
    request B -> one resolved dependency" release-gate scenario live, not just in the unit tests
    that already covered `HttpCorrelationBuffer` in isolation.
  - Adds `wait_for_declared_import()`, blocking the send loop until `service:order-service` shows
    up via `GET /api/services` before sending anything. **Found by actually running the demo**: with
    `docker-compose.demo.yml`'s original `depends_on: [otel-collector]` and a 5s traffic interval,
    the generator's first batch reliably lands *before* a human running the walkthrough manages to
    call `POST /api/import`. `app/telemetry/service_resolver.py`'s tier-2 match is exact-name and
    only fires when exactly one Service node has that name; the observed-only path mints its own
    `service:orderservice` node (slugified) for "OrderService" milliseconds after startup, and the
    later declared import then creates a *second*, never-merging `service:order-service` node with
    the same name - two candidates, so tier-2's uniqueness check permanently stops matching. Verified
    by reproducing this exact split (`MATCH (s:Service) RETURN s.id, s.name` showed both
    `service:order-service`/`service:orderservice` pairs for all four fixture services) before
    adding the fix, then confirming a clean `docker compose down -v` + `up` no longer splits them.
- `docker-compose.demo.yml`: adds `AIP_BASE_URL` (for the new readiness poll) and an explicit
  `architecture-intelligence` entry in `traffic-generator`'s `depends_on`; adds a read-only
  `./examples:/app/examples` bind mount on `architecture-intelligence` itself (previously `COPY`'d
  into the image at build time only) so the reconciliation scenario below can edit
  `examples/order-service/architecture.yaml` on the host and re-import without an image rebuild.
- New `examples/runtime-demo/README.md` - full step-by-step walkthrough with literal `curl`
  commands: import, `NOT_OBSERVED_IN_WINDOW` (checked in the gap before traffic arrives),
  `CONFIRMED`, `OBSERVED_ONLY`, the cross-batch log lines, and the 11H reconciliation scenario
  (remove `order-service`'s `calls` entry, `POST /api/import/service/order-service`, watch
  `product-service` move from `confirmed` to `observed-only`, restore the fixture). Linked from
  root `README.md`'s "Runtime demo" section.
- **All of the above was run for real**, not just read for plausibility: `docker compose -f
  docker-compose.demo.yml up --build`, `POST /api/import`, confirmed `NOT_OBSERVED_IN_WINDOW`
  immediately after import, confirmed `CONFIRMED`/`OBSERVED_ONLY` after traffic landed, confirmed
  the cross-batch demo's log lines, then walked the reconciliation scenario end-to-end (edited
  `architecture.yaml`, reimported, watched `product-service` degrade to `observed-only` via
  `GET /api/analysis/runtime/{confirmed,observed-only}`, restored the fixture - `git diff` on
  `examples/order-service/architecture.yaml` is empty). Full suite re-run after: 483 passed
  (352 unit / 131 integration, unchanged from 12B).
- Explicitly out of scope / deferred:
  - Demo screenshot/GIF (spec §48) - spec §48 itself frames this as a "Vor Release" (before-release)
    requirement, and it isn't in spec §50's release-gate blocking list (unlike the reconciliation and
    cross-batch scenarios above, which are and are now verified). No headless-browser/screenshot
    tooling is available in this environment to produce one honestly; deferred to 12F (Release),
    which is also where repository topics, social preview, and the version tag live per spec §52.
  - CI/CD, CodeQL, container scanning, GHCR publishing (12D); CONTRIBUTING/SECURITY/CODE_OF_CONDUCT/
    SUPPORT/issue and PR templates/good-first-issues (12E); CHANGELOG/ROADMAP/release tag (12F).

## Iteration 12D — CI/CD & Security (Open Source Readiness)
`Architecture_Intelligence_Platform_H5_Open_Source_Readiness_Specification.md` §26-31 (GitHub
Actions CI, Docker build workflow, Dependabot, `pip-audit`, CodeQL, Trivy container scanning), §50
(Release Gate). Fourth of six H5 sub-iterations; 12A/12B/12C (`e641370`/`99cb48c`/`b233e40`) were
committed before this one.

**Exit criterion:** pushing a commit or opening a PR actually runs lint + the full unit/integration
baseline + a dependency audit; tagging/publishing a release actually builds, scans, and publishes an
image to GHCR; static analysis and dependency-update PRs run on a schedule - all as real, working
GitHub Actions, not just described.

- `.github/workflows/ci.yml` - spec §26's exact pipeline (checkout -> `uv sync` -> `ruff check` ->
  `ruff format --check` -> unit tests -> integration tests) as one job, plus a second
  `dependency-audit` job (spec §29) running `uv run --with pip-audit pip-audit` *inside* the
  project's synced venv (auditing packages actually installed here, not `pip-audit`'s own ephemeral
  tool env - verified locally: `uvx pip-audit` alone audits the wrong environment and would
  silently report clean regardless of this project's actual dependencies). Both jobs run on every
  `push`/`pull_request`, so a dependency CVE gets fast, unavoidable feedback (unlike Trivy below).
  Verified locally before committing: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest tests/unit` (352 passed), and `uv run --with pip-audit pip-audit` ("No known
  vulnerabilities found") all green as of this iteration.
- **Found and fixed a real problem by actually running these commands, not just writing the
  workflow**: `ruff format --check .` failed before this iteration - ruff 0.16 formats Markdown
  code fences by default, and it wanted to rewrite `Protocol` stub bodies (`def f(...) -> str:
  ...`) inside the frozen historical spec documents (`Architecture_Intelligence_Platform_Core_
  Hardening_Specification.md`, the H5 spec itself, `docs/specifications/*.md`). Fixed by adding
  `extend-exclude = ["*.md"]` to `[tool.ruff]` in `pyproject.toml` - this repo's Markdown is docs/
  specs, not code, and auto-reformatting a frozen design document's embedded snippets is not a goal
  here. `ruff format --check .` now matches `docs/development.md`'s already-documented command
  (`uv run ruff format .`) with no doc change needed.
- `.github/workflows/codeql.yml` - spec §30's minimum (`python`, `actions`), `build-mode: none` for
  both (interpreted/no compilation step), on push/PR to `main` plus a weekly schedule.
- `.github/workflows/docker.yml` - spec §27, triggered on `release: published` or a `v*` tag push:
  builds the root `Dockerfile` image, tags it `<ref>` and `latest`, pushes to
  `ghcr.io/<owner>/<repo>` (lowercased explicitly - `github.repository` preserves this repo's actual
  mixed case, which GHCR rejects), then runs Trivy (spec §31) against the pushed image and uploads
  SARIF to the Security tab. Trivy's `exit-code` is deliberately `0` (report, don't block) - unlike
  `dependency-audit` above, this only runs at release time, and hard-failing a release over an
  unfixed base-image (`python:3.13-slim`/`neo4j:5`) CVE the maintainer doesn't control would be
  impractical; spec §29/§50 both say "no *unreviewed* critical finding", not "zero findings", and
  the SARIF upload is what makes it reviewed rather than silently ignored.
- `.github/dependabot.yml` - spec §28's three ecosystems, weekly. Deliberately uses
  `package-ecosystem: "uv"`, not the spec's literal `"pip"` wording - confirmed via GitHub's own
  changelog that Dependabot's `uv` ecosystem (reading `pyproject.toml` + `uv.lock` directly) reached
  general availability 2025-03-13, which is what this project (spec §3 mandates `uv`) actually
  needs; the classic `pip` ecosystem doesn't resolve `uv.lock`. Two `docker` entries (root
  `Dockerfile` and `examples/runtime-demo/Dockerfile`) cover both images in this repo.
- Every third-party Action is pinned to its exact current release tag rather than a floating major
  (e.g. `astral-sh/setup-uv@v10.0.1`, not `@v7`) - checked directly against each repo's GitHub API
  `tags` listing rather than assumed, because `setup-uv` specifically turned out to have *stopped*
  moving its floating major tag at `v7` while shipping real releases up to `v10.0.1` - using `@v7`
  would have silently pinned CI to a stale, unmaintained tag.
- No application code touched - 352 unit / (integration suite unchanged, not re-run this iteration
  since nothing in `app/` changed) tests still green per the ruff/pip-audit checks above.
- Explicitly out of scope (later H5 iterations per spec §52): `CONTRIBUTING.md`/`SECURITY.md`/
  `CODE_OF_CONDUCT.md`/`SUPPORT.md`/issue and PR templates/good-first-issues/Discussions (12E);
  CHANGELOG/ROADMAP/the version tag and actual release/announcement (12F). CI badges were
  deliberately not added to `README.md` - this repository has no `git remote` configured yet, so
  there is no real `owner/repo` path to point a badge at without fabricating one.

## Iteration 12E — Community Readiness (Open Source Readiness)
`Architecture_Intelligence_Platform_H5_Open_Source_Readiness_Specification.md` §32/§35-40 (SECURITY,
CONTRIBUTING, PR requirements, community files, issue templates, PR template, good first issues).
Fifth of six H5 sub-iterations; 12A-12D (`e641370`/`99cb48c`/`b233e40`/`38c4b85`) were committed
before this one.

**Exit criterion:** a newcomer opening this repository has an unambiguous path in - how to ask a
question, file a bug, propose a feature or adapter, contribute code, or report a security issue -
without inventing any of it themselves.

- New root files: `CONTRIBUTING.md` (dev setup, test/lint/format commands, branch workflow, commit
  expectations, PR checklist mirroring spec §36, adapter contribution guide grounded in
  `docs/adapter-development.md`), `SECURITY.md` (spec §32), `CODE_OF_CONDUCT.md` (Contributor
  Covenant v2.1, standard/unmodified except the enforcement contact), `SUPPORT.md` (spec §37's
  fourth community file).
- **Asked the user, rather than assuming, how to handle SECURITY.md's contact channel** - publishing
  a real personal email in a public OSS file forever is exactly the kind of call that isn't mine to
  make silently. Chose: GitHub's private vulnerability reporting (Security tab) only, no email
  published. `CODE_OF_CONDUCT.md`'s enforcement contact follows the same choice for consistency
  (private GitHub report rather than a personal address) - there's no known GitHub handle to name
  either, since this repo has no remote yet.
- `.github/ISSUE_TEMPLATE/{bug,feature,adapter,documentation}.yml` (spec §38's exact four files, as
  GitHub issue *forms* - structured fields, not free-text templates) and
  `.github/pull_request_template.md` (spec §39's exact five checkboxes).
- **Caught and fixed a real dead-link risk before committing**: issue-template body markdown doesn't
  get the same repo-relative link resolution as a normal file view (GitHub resolves relative links
  in issue-creation forms differently, and recommends absolute URLs for reliability) - initial drafts
  used `../../discussions`/`../../SECURITY.md`-style links copied from `SUPPORT.md` (where that
  pattern *is* correct, since those render as an actual file view two directories under
  `blob/main/`). Since this repo has no GitHub remote yet, there's no real absolute URL to hardcode
  either, so the issue templates reference `SECURITY.md`/Discussions by plain filename/name instead
  of a link. Dropped a planned `.github/ISSUE_TEMPLATE/config.yml` entirely for the same reason -
  its `contact_links` field requires real absolute URLs, and an `OWNER/REPO` placeholder would have
  published a dead link.
- `README.md`'s "Contributing" section rewritten from its 12B-era placeholder ("planned but not yet
  published") to point at all of the above.
- Prepared, not yet filed, five good-first-issue candidates (spec §40 - "at least five small,
  clearly-described tasks before launch") - filing them as real GitHub Issues needs an actual
  GitHub remote and `gh` auth, neither of which exist in this environment (`git remote -v` is empty;
  `gh` isn't installed). Recorded here so 12F can file them verbatim once the repo is pushed:
  1. **[good first issue, help wanted]** Add a `.dockerignore` (confirmed missing) - `.venv`, `.git`,
     `__pycache__`, `.pytest_cache`, `.ruff_cache` are currently sent into the Docker build context.
  2. **[good first issue]** Add a `HEALTHCHECK` to the root `Dockerfile` (confirmed missing) using
     the existing `GET /health` endpoint (`app/main.py`).
  3. **[good first issue, documentation]** Add a "Troubleshooting" section to
     `docs/development.md` for common local-dev issues (Neo4j auth, port conflicts, stale `.venv`).
  4. **[good first issue, documentation, adapter]** `docs/adapter-development.md` currently only
     describes the `Protocol` contract abstractly - add one small, concrete worked example (a toy
     adapter, start to finish).
  5. **[good first issue, documentation]** Add CI/license status badges to `README.md` - explicitly
     deferred in 12D's own notes pending a real `owner/repo` GitHub path.
- Explicitly deferred (needs a live GitHub remote, not available in this environment):
  - Filing the five good-first-issues above as real Issues, and applying spec §40's four labels
    (`good first issue`/`help wanted`/`documentation`/`adapter`) to the repo.
  - Enabling GitHub Discussions (spec §37) - a repository setting, not a file.
  - Repository topics (spec §41) and social preview image (spec §42) - both explicitly out of scope
    for 12E per the iteration breakdown anyway (12F territory), and both need a live repo regardless.
- No application code touched; `uv run ruff check .` / `uv run ruff format --check .` still pass
  (114 files, unchanged from 12D - none of this iteration's new files are Python).

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
