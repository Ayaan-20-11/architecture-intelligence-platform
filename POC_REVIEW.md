# PoC Review — Architecture Intelligence Platform

Iteration 9 of `IMPLEMENTATION_PLAN.md` (spec §21 acceptance criteria + §23.1 success measures). No new
code was written for this iteration except where noted; this is an evaluation pass against the system
built in Iterations 0–8 (commits `72698a1`..`e00bdc0`).

**Test suite at time of review:** 143 unit tests (no Neo4j/Docker/network required) + 55 integration
tests (Testcontainers-backed, real Neo4j 5) = **198 tests, all passing**. `ruff check` and
`ruff format --check` clean.

## Live smoke test

Iteration 8 had verified the LLM subsystem only against mocked (`unittest.mock`) and fake, in-process
providers — no call had ever reached a real LLM API. With a real `OPENAI_API_KEY` now available, this
iteration ran a genuine end-to-end smoke test: a throwaway Neo4j container, a real `uvicorn` server,
`POST /api/import` against `examples/`, then `POST /api/query` with a real natural-language question.

**Result:** the request reached OpenAI successfully — authentication succeeded and the request was
well-formed — but the account returned `429 insufficient_quota` (no billing credits on the key). The
app's error handling worked exactly as designed: `OpenAIProvider.generate_cypher` caught `openai.APIError`
and re-raised it as `LLMProviderError`, visible as a clean 500 with a full traceback rather than an
unhandled crash. This is a billing/account issue, not a code defect — it's meaningful partial evidence
(the SDK integration, model name, and request shape are all correct as far as OpenAI's API is concerned)
but **a fully successful live round-trip (real Cypher generated, real answer composed) is still
unverified.** Recommend re-running this smoke test once the key has credits, before relying on the LLM
subsystem for anything beyond the automated test suite.

## AC1–AC15 (spec §21)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| AC1 | OpenAPI files of multiple services import reproducibly | ✅ | `app/ingestion/openapi_adapter.py`; `tests/unit/test_openapi_adapter.py` (9 tests); `tests/integration/test_importer.py::test_import_all_sources_is_idempotent` |
| AC2 | AsyncAPI files with queue communication import reproducibly | ✅ | `app/ingestion/asyncapi_adapter.py`; `tests/unit/test_asyncapi_adapter.py` (13 tests, including cross-adapter ID consistency between producer/consumer documents) |
| AC3 | REST providers are correctly recognized | ✅ | `openapi_adapter.py` → `PROVIDES` relations; `test_openapi_adapter.py::test_provides_relation_created`; V2 canonical validation enforces exactly one provider per operation |
| AC4 | REST callers are correctly connected via the Architecture Manifest | ✅ | `app/ingestion/manifest_adapter.py` + `pipeline.py`'s cross-service `operation_index`; `tests/integration/test_pipeline.py::test_import_sources_real_examples_end_to_end` asserts the real `order-service → product-service` `CALLS` edge |
| AC5 | Queue senders and consumers are correctly recognized | ✅ | `asyncapi_adapter.py` → `SENDS`/`RECEIVES_FROM`; A1/A2 analyses; `tests/integration/test_analyses.py` |
| AC6 | Queue, Message, and Schema are correctly linked as separate entities | ✅ | Canonical model keeps 3 distinct entity types (`app/canonical/model.py`); `CARRIES`/`CONFORMS_TO` relations; `test_asyncapi_adapter.py` |
| AC7 | DLQ relationships are represented | ✅ | `DEAD_LETTERS_TO` in `asyncapi_adapter.py` (via `x-dead-letter-queue`); V7 rejects DLQ self-reference; `tests/integration/test_api.py::test_ui_queue_explorer` shows `payment-dlq` live in the UI |
| AC8 | Repeated imports produce no duplicates | ✅ | MERGE-based importer (`app/graph/importer.py`) tagged with a `sources[]` reconciliation property; `tests/integration/test_importer.py::test_import_service_is_idempotent`, `test_import_all_sources_is_idempotent` |
| AC9 | The five standard analyses produce deterministic results | ✅ | Every A1–A5 query has an explicit `ORDER BY`; `tests/integration/test_analyses.py` (11 tests) asserts exact result sets against the known fixture graph |
| AC10 | Blast radius combines synchronous and asynchronous paths | ✅ | `blast_radius.py`'s `_NEIGHBORS_QUERY` unions `CALLS/PROVIDES` (SYNC) and `SENDS/RECEIVES_FROM` (ASYNC) in one BFS; `test_a5_blast_radius_from_order_service` asserts both `via` values and correct depths |
| AC11 | A natural-language question is translated into a safe read-only Cypher query | ⚠️ mostly | Full pipeline (`cypher_generator.py` → `cypher_validator.py` → `question_service.py`) exercised end-to-end against real Neo4j with a fake provider (`tests/integration/test_question_service.py`, 6 tests). **Gap:** no fully successful live LLM round-trip yet (see smoke test above) — only the request-reaches-OpenAI-correctly path is confirmed live |
| AC12 | The LLM cannot alter Neo4j | ✅ | Two independent layers: `cypher_validator.py`'s allowlist blocks every write/admin keyword (40 adversarial unit tests, including disguised-in-string/comment bypass attempts), *and* `question_service.py` executes only over a read-only Neo4j session. `test_ask_rejects_generated_cypher_that_violates_the_validator` proves a rejected write never touches the graph |
| AC13 | Essential relationships carry traceable provenance | ⚠️ partial | Every adapter *produces* full `Provenance` records (`source_type`/`source_file`/`source_revision`/`evidence_type`) as part of its `ArchitectureModel` output, verified per-adapter (`test_provenance_recorded` in each adapter's test file). **Gap:** `app/graph/importer.py` never persists these records into Neo4j — it only writes a lightweight `sources: list[str]` (service-slug) tag used for §12.2 reimport bookkeeping. A user querying the live graph today cannot ask "which spec file / revision did this fact come from" — only "which currently-imported service(s) declare it." `Provenance` was never one of the 5 queryable node labels in §11.1, so this was a known design gap flagged as early as Iteration 5, not a new discovery |
| AC14 | A failed import produces no inconsistent partial state | ✅ | `pipeline.parse_sources()` builds the complete per-service model in memory and `validate_canonical_model()` runs before any graph-mutating call, both at the pipeline level and again in `import_all_sources()`; `test_import_sources_raises_on_unresolvable_manifest_call`, `test_import_sources_raises_on_canonical_violation` both raise before touching Neo4j at all |
| AC15 | A developer can understand service/queue relationships without manual repo search | ✅ | REST API (12 endpoints) + server-rendered UI (index, Service Explorer, Queue Explorer, NL Query page); `tests/integration/test_api.py` (30 tests) exercises every JSON endpoint and all four HTML pages against the real fixture graph |

**13 of 15 fully met; 2 partially met** (AC11's live LLM path unverified due to a billing block, not a
code defect; AC13's provenance is captured but not persisted to the queryable graph).

## Success measures (spec §23.1)

1. **Faster than manual repository research** — structurally plausible (one HTTP call / UI page replaces
   grepping across N repos for who-calls-whom), but this is a claim about real-world usage the spec
   itself frames as something to *evaluate*, not something a code review can prove. Needs an actual user
   trying it against a real multi-service codebase.
2. **Discovers non-obvious dependencies or documentation gaps** — concretely demonstrated: the fixture
   landscape itself contains a `unused-q` (sender declared, no consumer — a likely-orphaned queue A3
   surfaces automatically) and an `unknown-producer-q` (consumer with no known sender — an undocumented
   external producer A4 surfaces automatically). This is the exact scenario the spec describes, working
   end-to-end without any manual annotation.
3. **The five analyses are reproducible without an LLM** — fully proven: A1–A5 are parameterized Cypher
   only, zero LLM code paths, 11 integration tests with exact expected results.
4. **The LLM improves usability without replacing the source of truth** — architecturally enforced, not
   just asserted: the LLM can only ever produce a candidate query (rejected outright if it isn't
   read-only) and an explanation strictly grounded in the rows that query actually returned; all 5
   deterministic analyses remain fully independent of the LLM. Whether it *actually* improves usability
   in practice is, like measure 1, a real-usage question outside a code review's reach — and still
   depends on completing the live smoke test above.
5. **The Canonical Model can absorb OpenTelemetry later without reworking the OpenAPI/AsyncAPI adapters**
   — supported by design analysis rather than a test (nothing exercises a not-yet-built adapter): each
   adapter independently produces a partial `ArchitectureModel` that `pipeline.merge_models()` combines;
   a future `otel_adapter.py` could produce Service/Operation entities tagged
   `Provenance(evidence_type="OBSERVED")` and plug into the same merge → validate → import pipeline
   without touching `openapi_adapter.py` or `asyncapi_adapter.py` at all. Untestable today by
   construction — this is the intended shape of the extension point, not a verified property.

## Known PoC-scope simplifications (carried forward from earlier iterations, not new findings)

These were each flagged explicitly in the iteration where they were introduced; collected here for a
single point of reference:

- **Read-only vs. read-write Neo4j users** (spec §19) are approximated via the driver's per-session
  access mode, not genuinely separate Neo4j accounts/roles (Iteration 5/7).
- **Two ID namespaces coexist** in the REST API: service/queue/message GET endpoints take the full graph
  ID (`service:order-service`); import endpoints take the source-layer slug (`order-service`) — different
  pipeline stages, not reconcilable into one shape without changing what either endpoint addresses
  (Iteration 7).
- **`CypherValidator` is a hand-rolled allowlist/blocklist**, not a full Cypher grammar/AST parser — it
  correctly handles every case tested (including adversarial disguise attempts), but an exhaustive
  enumeration of all Cypher keywords was explicitly out of scope for a PoC (Iteration 8).
- **Provenance is produced but not persisted** — see AC13 above.

## Verdict

The PoC's core hypothesis holds: OpenAPI + AsyncAPI + a minimal manifest reliably assemble into one
Neo4j graph (198 passing tests, including real multi-service, multi-source-type import scenarios), the
five standard analyses answer real architecture questions deterministically without any LLM involvement,
and the LLM query layer is architecturally boxed in — provably unable to mutate the graph and unable to
state anything beyond what the graph actually returned — even though a fully successful live call is
still pending real API credits. The two open items (live LLM round-trip, graph-persisted provenance) are
both well-understood, narrow, and don't call the architecture into question — they're the natural next
steps, not blockers discovered late.
