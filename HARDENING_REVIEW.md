# Hardening Review — Architecture Intelligence Platform

Evaluation pass over `Architecture_Intelligence_Platform_Core_Hardening_Specification.md`'s three
sub-projects — H1 (Evidence/Provenance), H2 (Semantic Query Validator), H3 (Deterministic Intent Router)
— implemented as `IMPLEMENTATION_PLAN.md` Iterations 10A/10B/10C (commits `a4a4e7f`, `ea813fb`, `ca365fb`).
Written the same way as `POC_REVIEW.md` reviewed the base PoC: acceptance-criteria tables with concrete
code/test evidence, not a re-description of the design.

**Test suite at time of review:** 221 unit tests (no Neo4j/Docker/network required) + 79 integration
tests (Testcontainers-backed, real Neo4j 5) = **300 tests, all passing**. `ruff check` and
`ruff format --check` clean. Starting point was 198 tests (143/55) at the `POC_REVIEW.md` baseline; H1
added 7 unit/9 integration, H2 added 35 unit/2 integration, H3 added 36 unit/13 integration.

## On live smoke testing

`POC_REVIEW.md`'s Iteration 9 live test against real OpenAI + real Neo4j is what *discovered* the bug H2
and H3 both exist to fix: a syntactically valid, safe, but semantically backwards Cypher query
(`Queue-[:SENDS]->Service`) for the question *"What queues have a consumer but no known sender?"*, which
the base validator couldn't catch and which produced wrong rows (`invoice-q`, `payment-q`,
`unknown-producer-q` instead of just `unknown-producer-q`).

This review does not repeat a live OpenAI call. It doesn't need to: H3's entire point is that this exact
question no longer reaches LLM Cypher generation at all (verified below, AC-H3-7), and H2's validator is
verified against the exact offending Cypher shape directly (AC-H2-2) rather than depending on an LLM
reproducing it again. A live call was judged not worth the API cost for confirming a property already
pinned by deterministic, reproducible tests — happy to run one if you want the live confirmation anyway.

## H1 — Evidence / Provenance (spec §4, `AC-H1-1`–`AC-H1-7`)

Turns "we produced provenance in memory" into "you can query the graph and ask where a fact came from" —
the base PoC's AC13 gap.

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| AC-H1-1 | All adapters produce Evidence | ✅ | `openapi_adapter.py`/`asyncapi_adapter.py`/`manifest_adapter.py` each stamp one `Provenance` record (carrying the H1-added `id` field) onto every relation they produce; per-adapter `test_provenance_recorded`-style cases in `tests/unit/test_{openapi,asyncapi,manifest}_adapter.py` |
| AC-H1-2 | Evidence persisted as an `Evidence` node in Neo4j | ✅ | `app/graph/importer.py:19` — `"provenance": "Evidence"` in `NODE_LABELS`, so the generic node writer MERGEs `:Evidence` nodes for free; `tests/integration/test_importer.py::test_import_service_creates_evidence_node_and_tags_relation` |
| AC-H1-3 | Essential relations carry ≥1 Evidence reference | ✅ | `app/canonical/model.py::Relation.evidence_ids`; `app/graph/importer.py:35`'s `SET r.evidence_ids = reduce(...)` accumulates onto every written relationship; `app/api/services.py`/`queues.py`'s `.../evidence` endpoints and the Service/Queue Explorer UI (`_attach_evidence` in `app/api/ui.py`) render it live |
| AC-H1-4 | Repeated imports create no duplicate Evidence | ✅ | Evidence nodes MERGE on stable `evidence_id(source_type, service_slug, revision)` (`app/canonical/ids.py:27`); `evidence_ids` accumulation uses `reduce`+dedup, not append; covered by the same idempotent-reimport tests as AC8 in the base PoC review |
| AC-H1-5 | A stale revision is correctly reconciled | ✅ | `app/graph/importer.py`'s `_STRIP_STALE_EVIDENCE_QUERY` removes exactly the reimporting service's own evidence IDs from every relation, before node expiry runs; `tests/integration/test_importer.py::test_shared_relation_accumulates_evidence_from_both_declaring_services` proves a shared `CARRIES` edge keeps one contributor's evidence while losing only the reimporting one's |
| AC-H1-6 | An API query can find a fact's source and revision | ✅ | `GET /api/evidence`, `GET /api/evidence/{id}`, `GET /api/services/{id}/evidence`, `GET /api/queues/{id}/evidence` (`app/api/evidence.py`, `services.py`, `queues.py`); `tests/integration/test_api.py::test_list_evidence`/`test_get_evidence`/`test_get_service_evidence`/`test_get_queue_evidence` (+ `_not_found` variants) exercise all four against real imported fixture data |
| AC-H1-7 | Base-PoC AC13 now fully met | ✅ | Directly follows from AC-H1-2/3/6 above — provenance is now queryable, not just produced. `GET /api/relations/{relationId}/evidence` (spec §4.10, marked optional) was intentionally not built, since `Relation` still has no stable ID |

**7 of 7 met.**

## H2 — Semantic Query Validator (spec §5, `AC-H2-1`–`AC-H2-6`)

Adds the check the base validator structurally couldn't do: not just "is this Cypher safe/read-only" but
"is this Cypher's relationship direction/labels actually consistent with the graph schema."

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| AC-H2-1 | All released relation types have domain/range definitions | ✅ | `app/graph_schema/registry.py::RELATIONS` — all 9 relation types; `tests/unit/test_graph_schema_registry.py::test_registry_keys_exactly_match_known_relation_types` pins it against `app.graph.reconciliation.KNOWN_RELATION_TYPES` as a drift-safety net, not just a static count |
| AC-H2-2 | The live-test bug (`Queue-[:SENDS]->Service`) is automatically caught | ✅ | `tests/unit/test_semantic_query_validator.py::test_ac_h2_2_live_test_regression` feeds the exact offending shape and asserts `relation=="SENDS"`, `expected_source=={"Service"}`, `expected_target=={"Queue"}`; `tests/integration/test_question_service.py::test_ask_rejects_semantically_invalid_generated_cypher` proves it end-to-end through `ArchitectureQuestionService.ask()` with nothing reaching the graph |
| AC-H2-3 | Valid A1–A5-shaped Cypher stays permitted | ✅ | `test_blast_radius_shaped_query_with_anonymous_nodes_and_property_map_passes`/`..._async_branch_passes` in `tests/unit/test_semantic_query_validator.py` run the real multi-hop, anonymous-node, property-map shape from `app/analysis/blast_radius.py::_NEIGHBORS_QUERY` through the validator directly |
| AC-H2-4 | Unknown relation types are rejected | ✅ | `test_unknown_relationship_type_rejected`, `test_unknown_type_in_alternation_rejected_even_if_other_alternative_is_valid` — the latter proves an unknown type in a `TYPE1|TYPE2` alternation is rejected unconditionally even when the other alternative would be schema-valid |
| AC-H2-5 | Security validator and semantic validator are tested separately | ✅ | `tests/unit/test_cypher_validator.py` (pre-existing, untouched) and `tests/unit/test_semantic_query_validator.py` (new) are two independent files with no shared fixtures/imports between the two validators' internals |
| AC-H2-6 | No semantically invalid query reaches Neo4j | ✅ | `app/ai/question_service.py::ArchitectureQuestionService.ask()` calls `SemanticQueryValidator.validate()` after the security validator and before `open_session(...)`; `app/main.py`'s `@app.exception_handler(SemanticValidationError)` returns HTTP 422 with the spec §5.10 body shape at the API boundary too — `tests/integration/test_api.py::test_post_query_with_semantically_invalid_cypher_returns_422` confirms the full-stack response |

**6 of 6 met.**

## H3 — Deterministic Intent Router (spec §6, `AC-H3-1`–`AC-H3-7`)

Closes the loop: for the five questions the system can already answer with 100% determinism, it no
longer asks an LLM to reinvent the answer.

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| AC-H3-1 | All A1–A5 analyses have an intent | ✅ | `app/intent/model.py::ArchitectureIntent` (5 members + `UNKNOWN`); `app/analysis/registry.py::INTENT_HANDLERS` maps every non-`UNKNOWN` member to its existing analysis function; `tests/unit/test_analysis_registry.py::test_all_non_unknown_intents_have_a_handler` |
| AC-H3-2 | DE/EN standard phrasings are recognized | ✅ | `app/intent/patterns.py`; `tests/unit/test_intent_patterns_and_router.py` parametrizes ≥5 EN+DE phrasings per intent (`Who sends to X?`/`Wer sendet an X?`, `What depends on X?`/`Welche Services hängen von X ab?`, etc. — 28 cases across the 5 intents plus synonyms) |
| AC-H3-3 | Known intents produce no LLM Cypher | ✅ | `app/answer_router.py::answer_question()` only ever touches `question_service`/the LLM provider in the `UNKNOWN` branch; `tests/integration/test_answer_router.py` uses an `ExplodingProvider` whose `generate_cypher`/`compose_answer` raise `AssertionError` if called, and every one of the 5 deterministic-intent tests passes it in and succeeds |
| AC-H3-4 | A1–A5 via `/api/query` match their deterministic REST endpoints exactly | ✅ | `app/analysis/registry.py`'s `BLAST_RADIUS` handler deliberately reuses `blast_radius.DEFAULT_MAX_DEPTH` (not a separately-configurable settings value) so this holds exactly, not coincidentally; `tests/integration/test_api.py::test_post_query_deterministic_rows_match_analysis_endpoint_a1`/`_a4` assert row-for-row equality between `POST /api/query` and `GET /api/analysis/...` |
| AC-H3-5 | Unsafe/ambiguous questions are treated as UNKNOWN | ✅ | `app/intent/entity_resolver.py::resolve()` returns `None` (→ `UNKNOWN`) on 2+ matches, never guessing; `tests/unit/test_intent_patterns_and_router.py::test_ambiguous_entity_mention_is_unknown` uses the real `payment-q`/`payment-dlq` fixture pair; `tests/integration/test_answer_router.py::test_ambiguous_question_falls_back_to_llm` proves the *system-level* fallback behavior, not just the classifier's return value |
| AC-H3-6 | The Execution Mode field shows DETERMINISTIC or LLM | ✅ | `app/api/query.py::QueryResponse.execution_mode: Literal["DETERMINISTIC","LLM"]`; rendered in `app/templates/query.html`; `tests/integration/test_api.py::test_post_query_deterministic_intent_works_without_llm_configured` and `test_ui_query_page_deterministic_intent_shown_without_provider` check both the JSON field and the rendered HTML |
| AC-H3-7 | The Iteration 9 live A4 bug is no longer reproducible via the normal NL endpoint | ✅ | `tests/integration/test_answer_router.py::test_ac_h3_7_live_test_regression` and `tests/integration/test_api.py::test_post_query_ac_h3_7_live_test_regression` both feed the exact live-test sentence *"What queues have a consumer but no known sender?"* through the real endpoint (one at the `answer_question()` level, one through the full FastAPI `TestClient`) and assert `execution_mode == "DETERMINISTIC"`, `intent == "A4_QUEUES_WITHOUT_SENDERS"`, rows `== ["unknown-producer-q"]` — the wrong extra rows (`invoice-q`, `payment-q`) the live LLM produced in `POC_REVIEW.md` cannot appear, because no Cypher is generated for this question at all |

**7 of 7 met.**

## Consolidated gate (spec §11)

The spec's own cross-cutting acceptance table (§11, `H1.1`–`H3.6`) is a coarser regrouping of the same
20 criteria above, included here as the single canonical checklist analogous to `POC_REVIEW.md`'s AC1–15:

| ID | Criterion | Status |
|---|---|:---:|
| H1.1 | Provenance is queryable in Neo4j | ✅ |
| H1.2 | Every essential relation has Evidence | ✅ |
| H1.3 | Evidence revision changes are reconciled | ✅ |
| H1.4 | Original AC13 is fully met | ✅ |
| H2.1 | Domain/range of all graph relations defined | ✅ |
| H2.2 | Wrong relation direction is detected | ✅ |
| H2.3 | Unknown relations are blocked | ✅ |
| H2.4 | Semantically invalid Cypher never reaches Neo4j | ✅ |
| H3.1 | A1–A5 have deterministic intents | ✅ |
| H3.2 | Known questions bypass LLM query generation | ✅ |
| H3.3 | UNKNOWN still uses controlled LLM Cypher | ✅ |
| H3.4 | `/api/query` shows Execution Mode | ✅ |
| H3.5 | Live A4 regression test gives the correct result | ✅ |
| H3.6 | The pre-existing 198 tests stay green | ✅ |

**14 of 14 met.** (H3.6 verified directly: all 198 base-PoC-era tests are a strict subset of the current
300, still passing — including, notably, the exact `"who sends payment-q?"`/`"who sends to services?"`
questions the pre-existing `/api/query`/`/query` tests already used, which the new intent router had to
be built carefully around rather than accidentally hijack; see `tests/unit/test_intent_patterns_and_router.py`'s
two invariant-pinning tests.)

## Known limitations / explicitly deferred (carried forward, not new findings)

Collected from the three iterations' own "Explicitly deferred" notes in `IMPLEMENTATION_PLAN.md`:

- **H1:** `StrEnum` typing for `source_type`/`evidence_type` (plain strings today); real
  `source_revision` computation in the scanner (evidence IDs stay stable without it); `answer_composer.py`
  doesn't cite evidence in LLM answers yet; `GET /api/relations/{relationId}/evidence` not built (`Relation`
  has no stable ID).
- **H2:** the optional dev-only `POST /api/debug/validate-cypher` endpoint. Also, `CypherValidationError`
  (the pre-existing security validator's exception) still has no dedicated exception handler — it
  propagates as an unhandled 500 today, same as before H2; only `SemanticValidationError` got a proper
  422 handler. Both validators remain hand-rolled tokenizers/scanners, not a full Cypher grammar/AST
  parser (deliberate per spec §5.8 Variante A — the LLM's permitted subset is already narrow).
- **H3:** LLM-based intent classification as a fallback tier (spec §6.6) and depth-phrase parsing for A5
  ("blast radius of X at depth 3") — both would reintroduce non-determinism into the one path H3 exists
  to make deterministic, and neither is required by any AC-H3-x. No `AMBIGUOUS` intent value (spec marks
  it explicitly optional/future) — `UNKNOWN` already covers ambiguous entity mentions.
- **Carried forward from `POC_REVIEW.md`, still true:** read-only vs. read-write Neo4j users are still
  approximated via driver session access mode, not separate Neo4j accounts/roles; the two REST ID
  namespaces (full graph ID vs. import-time slug) still coexist.

## Verdict

All three hardening sub-projects meet every one of their acceptance criteria (20 of 20 across the
detailed per-subproject lists, 14 of 14 on the spec's own consolidated gate), and the platform now
matches the spec's closing description: an evidence-backed architecture knowledge graph, with
deterministic reasoning preferred over generative reasoning wherever a deterministic answer already
exists, and the LLM path constrained by two independent layers (security + semantic validation) when it
is used at all. The specific bug that motivated this entire hardening iteration — a live LLM producing
safe-but-backwards Cypher for a real question — is now unreachable for that question through the normal
endpoint (H3) and would be caught even if it recurred for a different question in a different shape (H2),
with the fact that caught it fully traceable to its source (H1). The one thing this review does not
independently reconfirm is a fresh live OpenAI round-trip (see "On live smoke testing" above) — everything
else is backed by the 300-test suite run against real Neo4j via Testcontainers, not mocks.
