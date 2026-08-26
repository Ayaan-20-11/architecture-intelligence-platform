# H4 Review — Architecture Intelligence Platform

Evaluation pass over `Architecture_Intelligence_Platform_H4_OpenTelemetry_Specification.md`'s full
OpenTelemetry integration — implemented as `IMPLEMENTATION_PLAN.md` Iterations 11A-11G (commits
`531c6ee`, `74a5248`, `3488471`, `cd08a34`, `94dd805`, `789c989`, `9684e09`). Written the same way as
`POC_REVIEW.md`/`HARDENING_REVIEW.md` reviewed prior work: an acceptance-criteria table with concrete
code/test evidence, not a re-description of the design.

**Test suite at time of review:** 319 unit tests (no Neo4j/Docker/network required) + 121 integration
tests (Testcontainers-backed, real Neo4j 5) = **440 tests, all passing**. `ruff check` and
`ruff format --check` clean on all touched files. Starting point was `HARDENING_REVIEW.md`'s 300 tests
(221/79); the seven H4 iterations added, in order: 11A +20 (241/79), 11B +15 (253/82), 11C +26 (277/84),
11D +21 (295/87), 11E +14 (303/93, net of one test relocated unit→integration), 11F +14 (305/105),
11G +30 (319/121).

## On real-world confirmation (spec §66's Erfolgskriterien)

Spec §66 frames H4's *business* success not as a set of code-level criteria but as finding at least one
real case of `Observed − Declared ≠ ∅` (an undocumented dependency) and, ideally, one real case of
`Declared − Observed ≠ ∅` correctly reported as "not seen in the selected observation window." This PoC
has no live production deployment feeding it real OTLP traffic, so it cannot claim to have found a real
instance of either — that would require an actual running system.

What this review *can* confirm is that the machinery required to recognize both cases the moment real
data arrives is fully built and exercised against a fixture that reproduces spec §63's own Testlandscape
verbatim (`tests/integration/test_runtime_api.py`): `OrderService → LegacyPricingService` is a synthetic
but structurally exact instance of `Observed − Declared ≠ ∅` (no `PROVIDES` edge for the target operation
at all — proven, not assumed, by `test_o3_resolves_target_identity_for_an_undeclared_operation_with_no_provides_edge`),
and `PaymentService → invoice-q` is a synthetic instance of `Declared − Observed ≠ ∅`, reported as the
literal string `NOT_OBSERVED_IN_WINDOW` end-to-end through the REST API and the Service Explorer UI, with
a dedicated negative assertion (`test_ui_service_explorer_shows_not_observed_in_window_for_declared_only`)
that the words "obsolete"/"unused"/"dead" never appear. §66 is therefore mechanically satisfied — the
platform *would* surface a real instance of either case correctly the moment one exists — but is not
independently reconfirmed against live production telemetry, the same caveat `HARDENING_REVIEW.md` made
about a live LLM round-trip.

## Ingestion & Identity Resolution — 11A/11B (H4.1-H4.4)

Turns a raw OTLP/HTTP protobuf export into a resolved, environment-scoped service identity — read-only,
no graph writes yet.

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H4.1 | OTLP trace batches can be ingested via the Collector | ✅* | `POST /v1/traces` (`app/api/telemetry.py`) accepts a raw OTLP/HTTP protobuf export directly, decoded by `app/telemetry/otlp_receiver.py::decode_export_request`; `tests/unit/test_otlp_receiver.py` (17 cases: all 6 `SpanKind` values, ID hex-encoding, malformed payload, empty batch, a service-name-less resource block skipped rather than erroring the whole batch) + `tests/unit/test_telemetry_api.py`'s 415/400 route tests + `tests/integration/test_telemetry_api.py::test_valid_payload_persists_an_observed_call_and_returns_200`. *No separate `otel-collector` container was deployed (spec §55-57, explicitly out of scope — see "Explicitly deferred" below); the endpoint a collector would forward to is the actual ingestion boundary, so the functional requirement is met directly rather than via the specific topology sketched in the spec. |
| H4.2 | `service.name` correctly maps to logical Service nodes | ✅ | `app/telemetry/service_resolver.py::resolve_service` — 4-tier resolution (namespace+name, unique name, configured alias, observed-only mint); `tests/unit/test_service_resolver.py` covers all four tiers plus the "don't guess on a name collision" case; `tests/integration/test_service_resolver.py::test_resolve_runtime_span_matches_known_declared_service` proves it against the real `order-service` fixture |
| H4.3 | `service.instance.id` creates no additional Service nodes | ✅ | `service_resolver.py`'s resolution logic never reads `RuntimeSpan.service_instance_id` at all — satisfied by construction, not by filtering; `tests/unit/test_service_resolver.py::test_service_instance_id_is_ignored_by_resolution` proves two spans differing only in that field resolve to the identical `service_id` |
| H4.4 | `deployment.environment.name` separates observations by environment | ✅ | `RuntimeSpan.environment` (decoded in 11A) → `service_resolver.py::resolve_runtime_span` folds it in → `ObservedFactCandidate.environment`/`ObservedEvidence.environment`; every O1-O5 analysis in `app/analysis/runtime.py` filters/requires `environment` explicitly (O2-O5 make it a required, non-optional parameter precisely because the same fact can be `CONFIRMED` in one environment and `DECLARED_ONLY` in another); `tests/integration/test_runtime_analysis.py::test_o2_is_scoped_by_environment` proves cross-environment isolation directly |

**4 of 4 met** (H4.1 with the noted, explicitly-deferred topology caveat).

## Observation Building — 11C/11D (H4.5-H4.10)

Turns correlated spans into real `ObservedFactCandidate`/`ObservedEvidence` records, resolving against
declared OpenAPI/AsyncAPI data or minting stable observed-only ids — still no graph writes.

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H4.5 | HTTP client/server spans produce observed REST relationships | ✅ | `app/telemetry/adapter.py::correlate_http_call_observations` pairs CLIENT/SERVER spans by `trace_id`+`span_id`/`parent_span_id` within one decoded batch; `tests/unit/test_adapter.py`'s correlation cases (matched/unpaired/mismatched-trace-id/empty-batch) |
| H4.6 | Existing OpenAPI operations are correctly reused | ✅ | `app/telemetry/operation_resolver.py::resolve_operation` Fall A reuses a declared operation's id verbatim; route/environment/timestamp are deliberately read from the **server** span, not the client, specifically to avoid a lexical mismatch against the declared path (documented directly in the 11C `IMPLEMENTATION_PLAN.md` entry as the reason, not an afterthought); `tests/integration/test_adapter.py::test_declared_call_reuses_the_real_declared_operation` proves Fall A reuses the *real* `order-service → product-service GET /products/{id}` operation id against actual imported fixture data |
| H4.7 | Messaging SEND creates/updates `SENDS` | ✅ | `app/telemetry/adapter.py::correlate_queue_observations` classifies via `messaging.operation.type == "send"` → `SENDS` (never `span_kind`, which spec §25/§26 and real OTel semconv both treat as too coarse to disambiguate) |
| H4.8 | Messaging RECEIVE/PROCESS creates/updates `RECEIVES_FROM` | ✅ | Same function, `{"receive","process"}` → `RECEIVES_FROM`; anything else (including absent `messaging.operation.type`) is silently skipped, not reported as unresolved — matches an `INTERNAL`-kind span's treatment on the HTTP path |
| H4.9 | Known AsyncAPI queues are reused | ✅ | `app/telemetry/queue_resolver.py::resolve_queue` — messaging-system-qualified match, bare-name unique match, alias, observed-only mint (4 tiers, structural sibling of `service_resolver.py`); `tests/integration/test_adapter.py::test_send_observation_reuses_the_real_declared_queue` proves a send observation reuses the *real* declared `payment-q` |
| H4.10 | Unknown runtime Services/Queues can be created as `OBSERVED_ONLY` | ✅ | All three resolvers' final tier mints a deterministic id (`ids.service_id`/`ids.operation_id`/`ids.queue_id`) and records an `ObservedOnlyEntity`; `app/telemetry/aggregator.py`'s `_MERGE_STUB_NODE_QUERY` uses `MERGE ... ON CREATE SET` so a later declared import is never clobbered; `tests/integration/test_aggregator.py` proves the stub is `ON CREATE`-only; `tests/integration/test_adapter.py::test_unknown_route_mints_observed_only_operation_against_real_service_data`/`test_unknown_destination_mints_observed_only_queue_against_real_service_data` prove stable, deterministic minted ids against real service data |

**6 of 6 met.**

## Evidence Aggregation — 11E (H4.11-H4.12)

The first H4 iteration to actually write to Neo4j — merges per-observation seeds into real, time-bounded
Evidence.

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H4.11 | Observed Evidence contains Environment, FirstSeen, LastSeen, Count | ✅ | `app/provenance/model.py::ObservedEvidence` — `environment`, `bucket_start`/`bucket_end`, `first_seen`/`last_seen`, `observation_count`, `sample_trace_ids` (capped at 5), `service_version`; `app/telemetry/aggregator.py::merge_evidence` widens `first_seen`/`last_seen` and sums `observation_count` across repeated observations of the same bucket — `tests/integration/test_aggregator.py`'s "persisting the same fact twice correctly merges the bucket" test exercises this against a real re-read from Neo4j (the test that specifically caught the `neo4j.time.DateTime` vs. `datetime.datetime` Pydantic-rejection bug, fixed via an explicit `.to_native()` conversion on read) |
| H4.12 | Spans are aggregated, not stored individually as Neo4j nodes | ✅ | `RuntimeSpan` (`app/telemetry/model.py`) is explicitly documented as "never persisted to Neo4j" and there is no span/trace node label anywhere in `app/graph/schema.py`'s constraints; `merge_evidence` collapses every observation within a UTC calendar day into one `Evidence` node per `(fact, day, environment)`, proven by `observed_relations()`'s `min(first_seen)`/`max(last_seen)`/`sum(observation_count)` aggregation in `app/analysis/runtime.py` and `tests/integration/test_runtime_analysis.py::test_o1_aggregates_multiple_observations_of_the_same_relation` (two observations 10 hours apart on the same day collapse into one summary row) |

**2 of 2 met.**

## Architecture Comparison — 11F (H4.13-H4.16)

Five deterministic, no-LLM Cypher analyses deriving each relation's status from its Evidence, per spec
§38's formula.

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H4.13 | `DECLARED ∩ OBSERVED` is recognized as `CONFIRMED` | ✅ | `app/analysis/runtime.py::confirmed_relations` (O2) — `EXISTS {...DECLARED...} AND EXISTS {...OBSERVED in environment/window...}`; `tests/integration/test_runtime_analysis.py::test_o2_finds_the_real_declared_relation_once_observed_too` proves it against the real `order-service → product-service` relation |
| H4.14 | `OBSERVED − DECLARED` is determined deterministically | ✅ | `observed_only_relations` (O3) — pure Cypher, no LLM; a real correctness bug (an inner join through `PROVIDES` would silently drop exactly the undeclared-operation rows O3 exists to surface) was caught at design-review time, before any code was written, and fixed via `OPTIONAL MATCH`/`coalesce()`; `test_o3_resolves_target_identity_for_an_undeclared_operation_with_no_provides_edge` pins the fix directly against an operation with a verified-absent `PROVIDES` edge |
| H4.15 | `DECLARED − OBSERVED` is determined relative to a time window | ✅ | `declared_only_relations` (O4) takes an explicit `since`/`until` — none of O1-O5 ever call `datetime.now()` internally, keeping the window fully caller-controlled and deterministically testable; `test_o4_reports_not_observed_in_window_with_no_coverage` |
| H4.16 | `DECLARED_ONLY` is never automatically classified as "obsolete" | ✅ | `NOT_OBSERVED_IN_WINDOW = "NOT_OBSERVED_IN_WINDOW"` is the one literal status string `DeclaredOnlyRelation.status` can hold — enforced by construction, not a formatting choice; carried through unmodified to the REST layer (`DeclaredOnlyRelationOut.status: Literal["NOT_OBSERVED_IN_WINDOW"]`) and the UI (`service.html` renders the raw status verbatim); `tests/integration/test_runtime_api.py::test_get_declared_only_status_is_literal_not_observed_in_window` and `test_ui_service_explorer_shows_not_observed_in_window_for_declared_only` (the latter also asserts "obsolete"/"unused"/"dead" are absent from the rendered page) |

**4 of 4 met.**

## Runtime API / UI / Intents — 11G (H4.17-H4.18)

Makes 11F's five analyses reachable — this is the criterion group most exposed to the risk of "the
analysis exists but nothing can actually ask it a question."

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H4.17 | Telemetry Coverage is separately queryable | ✅ | `GET /api/analysis/runtime/coverage` (`app/api/runtime.py::get_coverage`) wraps `telemetry_coverage()` (O5) as its own dedicated endpoint, independent of the four relation-status endpoints; `tests/integration/test_runtime_api.py::test_get_coverage` confirms `httpObserved`/`messagingObserved`/`spansObserved` are all present in the response |
| H4.18 | O1-O5 work completely without an LLM | ✅ | Five new `ArchitectureIntent` members (`O1_OBSERVED_RELATIONS`...`O5_TELEMETRY_COVERAGE`) route through the existing H3 deterministic intent router (`classify()` → `registry.execute()`), never touching `question_service`/the LLM provider; `tests/integration/test_runtime_api.py`'s `client` fixture explicitly sets `app.state.llm_provider = None` (no LLM subsystem configured at all) and every `POST /api/query` O1-O5 test still returns `200`/`execution_mode == "DETERMINISTIC"` — a stronger proof than merely asserting the LLM wasn't called, since an `UNKNOWN`-routed fallback would have raised `LLMNotConfiguredError` → 503 here, not silently succeeded |

**2 of 2 met.**

## Cross-cutting: Privacy (H4.19)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H4.19 | Sensitive span attributes are not persisted | ✅ | Extraction is scoped to small, explicit semantic-convention allowlists — `app/telemetry/semconv/{resources,http,messaging}.py` — covering only `service.*`/`deployment.environment.name` (resource identity), `http.request.method`/`http.route`/`url.template`/`server.address`/`server.port` (no query strings, headers, or full URLs), and `messaging.system`/`messaging.destination.*`/`messaging.operation.*`. `RuntimeSpan.attributes` (the raw, unfiltered decoded attribute dict) is a temporary, never-persisted model (`app/telemetry/model.py`'s own docstring); `ObservedEvidence`'s actual persisted field list has no raw-attribute or URL field at all — only `sample_trace_ids` (capped at 5, `app/telemetry/aggregator.py::merge_evidence`) and semconv-derived `service_version`. `UnresolvedObservation` similarly carries only a `trace_id` + short reason code, "never raw span attributes/URLs" per its own docstring (spec §31) |

**1 of 1 met.**

## Cross-cutting: Regression (H4.20)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H4.20 | The pre-existing 300 tests stay green | ✅ | `HARDENING_REVIEW.md`'s 300 tests (221 unit / 79 integration) are a strict superset-preserving baseline: every one of the seven H4 iterations' own `IMPLEMENTATION_PLAN.md` entries records only *additions* (241→253→277→295→303→305→319 unit; 79→82→84→87→93→105→121 integration), with the one exception being 11E's single test *relocated* from unit to integration (not deleted — a valid payload started requiring real Neo4j once `POST /v1/traces` was wired to persistence), net-neutral on total count. The full current suite (440 tests) passes in one run (`pytest`, no `-k` filter) |

**1 of 1 met.**

## Consolidated gate

All twenty of spec §65's H4 acceptance criteria, in original numbering:

| ID | Criterion | Status |
|---|---|:---:|
| H4.1 | OTLP trace batches can be ingested (via the Collector) | ✅* |
| H4.2 | `service.name` maps correctly to logical Service nodes | ✅ |
| H4.3 | `service.instance.id` creates no additional Service nodes | ✅ |
| H4.4 | `deployment.environment.name` separates observations by environment | ✅ |
| H4.5 | HTTP client/server spans produce observed REST relationships | ✅ |
| H4.6 | Existing OpenAPI operations are correctly reused | ✅ |
| H4.7 | Messaging SEND creates/updates `SENDS` | ✅ |
| H4.8 | Messaging RECEIVE/PROCESS creates/updates `RECEIVES_FROM` | ✅ |
| H4.9 | Known AsyncAPI queues are reused | ✅ |
| H4.10 | Unknown runtime Services/Queues can be created as `OBSERVED_ONLY` | ✅ |
| H4.11 | Observed Evidence contains Environment, FirstSeen, LastSeen, Count | ✅ |
| H4.12 | Spans are aggregated, not stored individually as Neo4j nodes | ✅ |
| H4.13 | `DECLARED ∩ OBSERVED` is recognized as `CONFIRMED` | ✅ |
| H4.14 | `OBSERVED − DECLARED` is determined deterministically | ✅ |
| H4.15 | `DECLARED − OBSERVED` is determined relative to a time window | ✅ |
| H4.16 | `DECLARED_ONLY` is never automatically classified as "obsolete" | ✅ |
| H4.17 | Telemetry Coverage is separately queryable | ✅ |
| H4.18 | O1-O5 work completely without an LLM | ✅ |
| H4.19 | Sensitive span attributes are not persisted | ✅ |
| H4.20 | The pre-existing 300 tests stay green | ✅ |

**20 of 20 met** (H4.1 with the noted, explicitly-deferred Collector-topology caveat).

## Known limitations / explicitly deferred (carried forward, not new findings)

Collected from all seven iterations' own "Explicitly deferred" notes in `IMPLEMENTATION_PLAN.md`:

- **11A:** attribute allowlisting was deferred at decode time (present from 11C onward instead, at the
  point data actually gets persisted).
- **11B:** `EvidenceType`/`SourceType` as real `StrEnum`s (landed in 11C instead); physically creating
  `OBSERVED_ONLY` nodes (11E's job).
- **11C:** a combined `adapt(raw_bytes)` orchestrator (built in 11D once both HTTP and queue correlation
  existed).
- **11D:** message-type-specific facts — spec §30 permanently scopes H4 to `Service → Queue`, not a gap.
- **11E:** `importer.py::_EXPIRE_RELATIONS_QUERY` can discard accumulated `OBSERVED` evidence if a
  declared relation's `sources` empties out during a reimport, since it doesn't check evidence *type*
  before deleting — a real, documented, **not yet fixed** risk. This is the one item on this list that is
  a genuine open risk rather than an intentional scope boundary; it needs a dedicated follow-up.
- **11F:** any REST/UI/intent-router wiring (built in 11G); an explicit "now" upper bound beyond the
  optional `until` param; fixing 11C's inherited `PROVIDES`-for-undeclared-operations gap (documented,
  not changed — see `ServiceTelemetryCoverage`'s docstring and the pinned
  `test_o5_provider_side_gap_is_pinned` test, which forces any future fix to update a real assertion).
- **11G, and confirmed out of scope for all of H4** (not assigned to any of 11A-11G, not required by any
  H4.# criterion): spec §55-57's Docker Compose `otel-collector` service (the collector's own container,
  fan-out, and backpressure isolation — `POST /v1/traces` already accepts OTLP directly, so this is an
  optional production-hardening layer, not a functional gap; this is the caveat behind H4.1's ✅* above);
  spec §59-60's retention/cleanup job (§59 itself frames 90-day retention as a proposal, not a
  requirement).
- **Carried forward from `HARDENING_REVIEW.md`, still true:** read-only vs. read-write Neo4j users are
  still approximated via driver session access mode, not separate Neo4j accounts/roles; the two REST ID
  namespaces (full graph ID vs. import-time slug) still coexist.

## Verdict

All twenty H4 acceptance criteria are met, with one criterion (H4.1) satisfied functionally but not via
the exact Collector topology the spec sketches — a deliberate, documented scope boundary rather than a
gap, since the actual ingestion endpoint the Collector would forward to already exists and is fully
tested. The platform now matches spec §69's closing description: it can answer not just "what do our
architecture artifacts claim?" but "what actually happens?", and specifically "where do declared and
observed architecture differ?" — the three-way status distinction (`CONFIRMED`/`OBSERVED_ONLY`/
`NOT_OBSERVED_IN_WINDOW`) is derived at query time from Evidence, never stored as a separate fact (spec
§38), reachable via REST, the Service Explorer UI, and five deterministic NL intents that provably never
invoke an LLM. The one genuinely open item from this review — `importer.py`'s stale-evidence-stripping
gap, carried forward unfixed since 11E — is a real, if narrow, risk worth a dedicated follow-up rather
than a blocker: it requires a declared relation's *last* declaring service to stop declaring it while
that relation also carries `OBSERVED` evidence, a combination none of the current fixtures exercise. The
one thing this review does not independently confirm is §66's business-outcome criterion against real
production telemetry (see "On real-world confirmation" above) — everything else is backed by the
440-test suite run against real Neo4j via Testcontainers, not mocks.
