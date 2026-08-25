# PoC Review — Architecture Intelligence Platform

Iteration 9 of `IMPLEMENTATION_PLAN.md` (spec §21 acceptance criteria + §23.1 success measures). No new
code was written for this iteration except where noted; this is an evaluation pass against the system
built in Iterations 0–8 (commits `72698a1`..`e00bdc0`).

**Test suite at time of review:** 143 unit tests (no Neo4j/Docker/network required) + 55 integration
tests (Testcontainers-backed, real Neo4j 5) = **198 tests, all passing**. `ruff check` and
`ruff format --check` clean.

## Live smoke test

Iteration 8 had verified the LLM subsystem only against mocked (`unittest.mock`) and fake, in-process
providers — no call had ever reached a real LLM API. Two live attempts were made against a throwaway
Neo4j container + real `uvicorn` server with a real `OPENAI_API_KEY`, `POST /api/import` against
`examples/`, then `POST /api/query` with real natural-language questions.

**First attempt:** the request reached OpenAI successfully (auth + request shape both correct) but the
key had `429 insufficient_quota` (no billing credits). `OpenAIProvider.generate_cypher` correctly caught
`openai.APIError` and re-raised `LLMProviderError` as a clean 500 rather than an unhandled crash.

**Second attempt, after credits were added:** two full, successful live round-trips.

1. *"Which service sends messages to the payment-q queue?"* → generated
   `MATCH (s:Service)-[:SENDS]->(q:Queue {name: 'payment-q'}) RETURN s.name, s.version LIMIT 100`,
   executed correctly, answered accurately: *"OrderService ... sends messages to the payment-q queue."*
   Verified in both the JSON API and the HTML `/query` page, which correctly displayed the generated
   Cypher for traceability (spec §15.4).
2. *"What queues have a consumer but no known sender?"* — this one **surfaced a real, live semantic bug
   in the LLM's generated Cypher**, not in our code: it produced
   `MATCH (q:Queue)<-[:RECEIVES_FROM]-(s:Service) WHERE NOT (s)<-[:SENDS]-(q) RETURN q.name AS queue_name
   LIMIT 100` — syntactically valid, safe, and accepted by the validator, but semantically backwards (it
   checks for a `Queue -[:SENDS]-> Service` edge, which never exists given the schema's actual direction,
   so the `WHERE NOT` is close to a no-op). It returned `invoice-q`, `payment-q`, and `unknown-producer-q`.
   The deterministic `GET /api/analysis/queues/without-senders` endpoint (A4), queried directly as a
   cross-check, correctly returns only `unknown-producer-q`. The pipeline itself worked exactly as
   designed end to end — generation, validation, safe read-only execution, and an answer faithfully
   describing what those (wrong) rows contained — the LLM's interpretation of the question was simply
   incorrect. This is precisely the scenario the spec's design anticipates: the five deterministic
   analyses are the authoritative source for this kind of question, the LLM layer is best-effort natural
   language convenience on top, and the generated Cypher is always shown to the user specifically so
   mistakes like this one are auditable rather than hidden — which is exactly how this was caught.

Both smoke-test environments were torn down (uvicorn stopped, Neo4j containers removed) after each run.

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
| AC11 | A natural-language question is translated into a safe read-only Cypher query | ✅ | Full pipeline verified twice live against real OpenAI + real Neo4j (see smoke test above), plus `tests/integration/test_question_service.py` (6 tests) with a fake provider. The criterion is about safety/read-only-ness, not semantic correctness of the translation — both live queries were safe and read-only; one was also semantically correct, one was not (a live-observed LLM limitation, see below, not a validator or pipeline defect) |
| AC12 | The LLM cannot alter Neo4j | ✅ | Two independent layers: `cypher_validator.py`'s allowlist blocks every write/admin keyword (40 adversarial unit tests, including disguised-in-string/comment bypass attempts), *and* `question_service.py` executes only over a read-only Neo4j session. `test_ask_rejects_generated_cypher_that_violates_the_validator` proves a rejected write never touches the graph |
| AC13 | Essential relationships carry traceable provenance | ⚠️ partial | Every adapter *produces* full `Provenance` records (`source_type`/`source_file`/`source_revision`/`evidence_type`) as part of its `ArchitectureModel` output, verified per-adapter (`test_provenance_recorded` in each adapter's test file). **Gap:** `app/graph/importer.py` never persists these records into Neo4j — it only writes a lightweight `sources: list[str]` (service-slug) tag used for §12.2 reimport bookkeeping. A user querying the live graph today cannot ask "which spec file / revision did this fact come from" — only "which currently-imported service(s) declare it." `Provenance` was never one of the 5 queryable node labels in §11.1, so this was a known design gap flagged as early as Iteration 5, not a new discovery |
| AC14 | A failed import produces no inconsistent partial state | ✅ | `pipeline.parse_sources()` builds the complete per-service model in memory and `validate_canonical_model()` runs before any graph-mutating call, both at the pipeline level and again in `import_all_sources()`; `test_import_sources_raises_on_unresolvable_manifest_call`, `test_import_sources_raises_on_canonical_violation` both raise before touching Neo4j at all |
| AC15 | A developer can understand service/queue relationships without manual repo search | ✅ | REST API (12 endpoints) + server-rendered UI (index, Service Explorer, Queue Explorer, NL Query page); `tests/integration/test_api.py` (30 tests) exercises every JSON endpoint and all four HTML pages against the real fixture graph |

**14 of 15 fully met; 1 partially met** (AC13's provenance is captured but not persisted to the queryable
graph).

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
   deterministic analyses remain fully independent of the LLM and were used live to catch the LLM's
   mistake in the smoke test above. That live test is itself a good demonstration of measure 4 in
   practice: the "source of truth" property held even when the LLM's query generation didn't — the
   system never silently trusted the LLM's interpretation, it showed the generated Cypher for scrutiny
   and left the deterministic analyses as the reliable cross-check. Whether the NL layer *saves time*
   versus going straight to the deterministic endpoints is still a real-usage question outside a code
   review's reach.
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
- **LLM-generated Cypher can be semantically wrong even when it's safe** — live-observed in this
  iteration's smoke test (see above): the validator guarantees safety and read-only-ness, never semantic
  correctness. This is inherent to using an LLM for query generation, not something Iteration 8's design
  could have prevented outright — it's exactly why the spec keeps the 5 analyses deterministic and
  authoritative, and always shows the generated Cypher to the user rather than hiding it.

## Verdict

The PoC's core hypothesis holds: OpenAPI + AsyncAPI + a minimal manifest reliably assemble into one
Neo4j graph (198 passing tests, including real multi-service, multi-source-type import scenarios), the
five standard analyses answer real architecture questions deterministically without any LLM involvement,
and the LLM query layer is architecturally boxed in — provably unable to mutate the graph and unable to
state anything beyond what the graph actually returned. Two full live round-trips against real OpenAI
confirmed the pipeline end to end, including a live example of the LLM generating an unsafe-free but
semantically wrong query — caught immediately via the transparent generated-Cypher display and a
cross-check against the deterministic A4 endpoint, exactly as the spec's design intends. The one
remaining open item (provenance captured but not yet persisted to the queryable graph) is narrow and
well-understood — a natural next step, not a blocker discovered late.
