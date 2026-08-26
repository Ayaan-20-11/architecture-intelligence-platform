# Specification – Architecture Intelligence Platform
## Iteration 11H – Runtime Correctness & Robustness

**Version:** 0.1  
**Status:** Implementation Specification  
**Basis:** H4 Review / Iterations 11A–11G  
**Scope:** Correctness and robustness hardening of the OpenTelemetry-based runtime architecture model before H5 – Open Source Readiness  
**Out of Scope:** New architecture-intelligence features, new AI functionality, GraphRAG, Desired-State modeling, DDD/Promise modeling, production-scale observability backend

---

## 1. Motivation

H4 is functionally complete against its twenty acceptance criteria. The implementation can ingest OTLP traces, resolve services, operations and queues, persist aggregated observed evidence, compare declared and observed architecture, expose deterministic runtime analyses O1–O5, and preserve privacy by persisting only explicitly allowlisted architecture metadata.

The H4 review identified one genuine correctness risk and several runtime robustness concerns that should be addressed before the project is prepared for public Open-Source release.

The purpose of Iteration 11H is therefore:

\[
\boxed{
H4\ Functional\ Completeness
\rightarrow
Runtime\ Correctness\ Hardening
\rightarrow
H5\ Open\ Source\ Readiness
}
\]

11H introduces no new product vision. It strengthens the semantic correctness of the runtime evidence model under realistic telemetry and re-import conditions.

---

## 2. Goals

Iteration 11H shall ensure that:

1. observed evidence can never be accidentally deleted merely because declared evidence disappears,
2. runtime HTTP dependencies can still be discovered under partial instrumentation or cross-batch delivery,
3. runtime-discovered provider operations can be represented consistently,
4. the public demo uses a realistic OpenTelemetry Collector topology,
5. negative runtime statements such as `NOT_OBSERVED_IN_WINDOW` can be qualified by telemetry coverage.

The resulting runtime model must remain evidence-first:

\[
\boxed{
Fact\ exists\ iff\ supporting\ Evidence\ exists
}
\]

and:

\[
\boxed{
DeclaredEvidence
\perp
ObservedEvidence
}
\]

Declared and observed evidence are independent evidence sources. Removing one source must never remove facts still supported by another.

---

# 3. Non-Goals

11H explicitly does **not** implement:

```text
new O1-O5 analyses
new LLM functions
metrics ingestion
SLO evaluation
trace storage in Neo4j
full distributed trace reconstruction
long-term telemetry backend
automatic architecture transformation
Desired State
DDD model
Promise model
GraphRAG
Architecture Wiki
```

11H also does not turn AIP into a general observability backend.

---

# 4. Runtime Correctness Principle

The central invariant is:

\[
Delete(F)
\iff
Evidence(F)=\emptyset
\]

A fact must not be deleted merely because:

```text
DeclaredSources(F) = empty
```

if:

```text
ObservedEvidence(F) != empty
```

Likewise, a fact that is currently only observed may later become declared without losing its observed evidence.

The relation state must remain derivable from evidence:

```text
DECLARED only
OBSERVED only
DECLARED + OBSERVED
```

with runtime status derived at query time.

---

# 5. R1 – Fix Relation Reconciliation

## 5.1 Problem

The H4 review identified a risk in:

```text
importer.py::_EXPIRE_RELATIONS_QUERY
```

The current implementation can remove a relation when its declaration sources disappear during a re-import, even if the same relation still carries `OBSERVED` evidence.

Example:

### Before re-import

```text
OrderService -[:SENDS]-> payment-q

Evidence:
  DECLARED
  OBSERVED
```

### New AsyncAPI revision

The declared `SENDS` relation is removed from the specification.

Incorrect current outcome:

```text
relation deleted
```

Required outcome:

```text
OrderService -[:SENDS]-> payment-q

Evidence:
  OBSERVED
```

The runtime analysis must then classify it as:

```text
OBSERVED_ONLY
```

---

## 5.2 Required Behavior

Relation reconciliation must operate on evidence, not merely on declaration source bookkeeping.

Required algorithm:

```text
1. identify declared evidence made stale by the re-import
2. remove only that stale DECLARED evidence
3. recompute remaining evidence for the relation
4. delete relation only if no Evidence remains
5. retain relation if OBSERVED evidence remains
```

Formal invariant:

\[
Evidence_{after}(F)
=
Evidence_{before}(F)
-
StaleDeclaredEvidence(F)
\]

and:

\[
Evidence_{after}(F)\neq\emptyset
\Rightarrow
F\ remains.
\]

---

## 5.3 Shared Evidence

The implementation must also preserve facts supported by multiple declared or observed sources.

Example:

```text
Relation R

Evidence:
  DECLARED from asyncapi-A.yaml
  DECLARED from manifest.yaml
  OBSERVED from OTel bucket 2026-08-26
```

Re-importing `asyncapi-A.yaml` without the relation must result in:

```text
Evidence:
  DECLARED from manifest.yaml
  OBSERVED from OTel bucket 2026-08-26
```

The relation remains unchanged.

---

## 5.4 Required Integration Test

Add an integration test equivalent to:

```text
1. import declared relation
2. persist observed evidence for same relation
3. verify O2 => CONFIRMED
4. re-import declaring artifact without relation
5. verify relation still exists
6. verify stale DECLARED evidence is removed
7. verify OBSERVED evidence remains
8. verify O3 => OBSERVED_ONLY
```

This test must run against real Neo4j using Testcontainers.

---

# 6. R2 – Cross-Batch HTTP Correlation

## 6.1 Problem

H4 currently correlates HTTP CLIENT and SERVER spans inside one decoded OTLP batch.

In real OpenTelemetry deployments, matching spans may arrive:

```text
in different ExportTraceServiceRequests
at different times
through different collectors
```

Example:

```text
OrderService CLIENT span
        |
        | batch A
        v

PaymentService SERVER span
        |
        | batch B
        v
```

Both spans belong to the same distributed trace, but a batch-local correlation algorithm cannot correlate them.

---

## 6.2 Required Design

11H must remove the assumption:

\[
ClientSpan\ and\ ServerSpan
\in same\ OTLP\ batch.
\]

Two implementation strategies are acceptable:

### Strategy A – Short-Lived Correlation Buffer

Maintain a bounded temporary correlation store keyed by:

```text
trace_id
span_id
parent_span_id
```

Characteristics:

```text
bounded TTL
bounded memory
not persisted as Neo4j span nodes
architecture metadata only
```

Example TTL:

```text
30–120 seconds
```

The exact value shall be configurable.

### Strategy B – Single-Sided Observation with Later Enrichment

Persist or aggregate a lower-confidence observation immediately from one side and enrich it if the counterpart later arrives.

This strategy is acceptable only if duplicate fact creation and evidence aggregation remain deterministic.

---

## 6.3 Preferred Initial Implementation

For 11H, prefer the smallest robust implementation:

```text
bounded in-memory correlation buffer
```

with explicit cleanup.

It must not become a trace store.

---

## 6.4 Correlation Result

Matched CLIENT/SERVER pair:

```text
correlationMode = CLIENT_SERVER
```

This is the strongest runtime evidence for a service-to-service REST interaction.

---

# 7. R3 – Partial Instrumentation / Single-Sided HTTP Observation

## 7.1 Motivation

Real systems are rarely fully instrumented.

Possible scenarios:

```text
client instrumented, server not instrumented
server instrumented, client not instrumented
legacy target without OTel
third-party API
sampling removes one side
collector drops one side
```

AIP must not equate:

\[
MissingCounterpartSpan
\]

with:

\[
NoRuntimeDependency.
\]

---

## 7.2 CLIENT_ONLY Observation

If a CLIENT span contains sufficient low-cardinality target identity:

```text
service.name
http.request.method
http.route or url.template
server.address or another stable target identifier
```

AIP may create an observed dependency candidate with:

```text
correlationMode = CLIENT_ONLY
```

The target must only be resolved if the identity is sufficiently stable.

Raw concrete URL paths must still not create operations.

---

## 7.3 SERVER_ONLY Observation

If a SERVER span exists without the corresponding client span, AIP may create:

```text
correlationMode = SERVER_ONLY
```

only if the calling service can be resolved from safe, low-cardinality telemetry context.

If the caller cannot be identified reliably, the observation remains unresolved rather than guessed.

---

## 7.4 Confidence Semantics

11H does not require a numeric confidence score.

Use an explicit source/correlation classification:

```text
CLIENT_SERVER
CLIENT_ONLY
SERVER_ONLY
```

Suggested evidence ordering:

\[
CLIENT\_SERVER
>
CLIENT\_ONLY
\]

and:

\[
CLIENT\_SERVER
>
SERVER\_ONLY.
\]

The platform must not present all three modes as equivalent evidence strength.

---

## 7.5 No Guessing Rule

If stable target or caller identity cannot be established:

```text
UnresolvedObservation
```

must be emitted.

Do not infer dependencies from:

```text
raw arbitrary URL
IP address alone
ambiguous hostname
free-form span name
```

unless an explicit resolver or alias configuration exists.

---

# 8. R4 – Observed Provider Relation for Runtime-Discovered Operations

## 8.1 Problem

H4 can create an observed-only operation discovered from runtime traffic, but provider-side `PROVIDES` semantics are incomplete for undeclared operations.

Example:

```text
OrderService
    |
  CALLS
    v
POST /prices
    ^
    |
runtime server span says:
service.name = LegacyPricingService
```

If the provider identity and stable route are known, AIP possesses runtime evidence that:

```text
LegacyPricingService PROVIDES POST /prices
```

---

## 8.2 Required Behavior

When all of the following are known:

```text
provider logical service
stable HTTP method
stable route/template
server-side runtime observation
```

then the graph may contain:

```text
LegacyPricingService -[:PROVIDES]-> ObservedOnlyOperation
```

with:

```text
OBSERVED evidence only
```

No `DECLARED` evidence may be synthesized.

---

## 8.3 Resulting Model

Example:

```text
OrderService
    |
 CALLS [OBSERVED]
    |
    v
POST /prices
    ^
    |
PROVIDES [OBSERVED]
    |
LegacyPricingService
```

This preserves the canonical REST model for both declared and observed-only operations.

---

## 8.4 Later Declaration

If a later OpenAPI import declares the same stable operation:

```text
ObservedOnlyOperation
```

must be reconciled with the declared operation identity where possible.

The operation must then be supported by:

```text
DECLARED
OBSERVED
```

evidence without duplication.

---

# 9. R5 – OpenTelemetry Collector Demo Topology

## 9.1 Motivation

The direct endpoint:

```text
POST /v1/traces
```

is the valid AIP ingestion boundary.

For the public project and realistic deployment guidance, however, the reference topology should demonstrate that AIP is an additional telemetry consumer rather than the primary observability backend.

---

## 9.2 Required Demo Topology

Add an OpenTelemetry Collector service to the runtime demo:

```text
Demo Services
      |
      v
OTel Collector
      |
      +------> AIP
      |
      +------> optional trace backend / debug exporter
```

The minimum requirement is Collector → AIP forwarding.

An additional tracing backend is optional.

---

## 9.3 Docker Compose

The demo compose file shall contain at least:

```text
architecture-intelligence
neo4j
otel-collector
demo services
traffic generator
```

Suggested file:

```text
docker-compose.demo.yml
```

---

## 9.4 Collector Configuration

Add:

```text
examples/runtime-demo/otel-collector-config.yaml
```

with OTLP receiver and AIP exporter configuration.

The configuration must use environment-neutral, synthetic demo values.

---

# 10. R6 – Failure Isolation Guidance

11H does not require production-grade persistent Collector queues.

However, documentation must make the following operational principle explicit:

\[
\boxed{
AIP\ failure\ must\ not\ break\ normal\ observability
}
\]

Recommended production topology:

```text
Applications
     |
     v
OTel Collector
     |
     +----> Primary observability backend
     |
     +----> Architecture Intelligence Platform
```

The public documentation should explain that failure isolation, buffering and retry behavior belong in Collector/deployment configuration.

---

# 11. R7 – Coverage Qualification for Negative Findings

## 11.1 Motivation

The statement:

```text
NOT_OBSERVED_IN_WINDOW
```

has different meaning depending on telemetry coverage.

Examples:

```text
Case A:
7 days of good telemetry coverage
relation not observed

Case B:
service emitted no usable telemetry
relation not observed
```

These must not be interpreted as equally strong evidence.

---

## 11.2 Coverage Classification

Introduce a qualitative coverage classification:

```text
SUFFICIENT
PARTIAL
NONE
UNKNOWN
```

No arbitrary numeric confidence score is required in 11H.

---

## 11.3 Runtime Result

A declared-only result should be able to expose:

```json
{
  "status": "NOT_OBSERVED_IN_WINDOW",
  "environment": "prod",
  "since": "...",
  "until": "...",
  "coverage": "SUFFICIENT"
}
```

or:

```json
{
  "status": "NOT_OBSERVED_IN_WINDOW",
  "coverage": "UNKNOWN"
}
```

---

## 11.4 Semantics

The platform must continue to avoid terms such as:

```text
obsolete
unused
dead
```

unless a future explicit analysis defines and proves such semantics.

The interpretation remains:

\[
NOT\_OBSERVED\_IN\_WINDOW
\]

not:

\[
DOES\_NOT\_EXIST.
\]

---

# 12. Observation Count Semantics

`observation_count` remains an architecture-evidence statistic.

It must be documented that:

\[
ObservationCount
\neq
ExactRequestCount.
\]

Possible causes:

```text
OTLP retries
duplicate export
sampling
collector loss
instrumentation differences
```

The field may be used for:

```text
evidence strength
relative activity indication
first/last seen aggregation
```

but not for:

```text
billing
exact traffic accounting
SLO calculation
request-volume reporting
```

---

# 13. Privacy Constraints

11H must preserve H4's privacy model.

Persisted architecture evidence must not include:

```text
request bodies
response bodies
message payloads
authorization headers
cookies
query parameters
full URLs
raw span attribute maps
stack traces
PII
```

Any correlation buffer must obey the same allowlist principle.

The buffer must not become an alternate store for unrestricted span content.

---

# 14. Data Model Extensions

Where necessary, extend observed evidence metadata with:

```text
correlation_mode
```

Allowed values:

```text
CLIENT_SERVER
CLIENT_ONLY
SERVER_ONLY
MESSAGING_SEND
MESSAGING_RECEIVE
MESSAGING_PROCESS
```

Exact enum naming may differ, but it must remain explicit and queryable.

Recommended model:

```python
class CorrelationMode(StrEnum):
    CLIENT_SERVER = "CLIENT_SERVER"
    CLIENT_ONLY = "CLIENT_ONLY"
    SERVER_ONLY = "SERVER_ONLY"
    MESSAGING_SEND = "MESSAGING_SEND"
    MESSAGING_RECEIVE = "MESSAGING_RECEIVE"
    MESSAGING_PROCESS = "MESSAGING_PROCESS"
```

If multiple observations with different modes support the same daily Evidence bucket, preserve the strongest mode or a deduplicated set of modes.

---

# 15. Temporary Correlation Model

Suggested internal model:

```python
class PendingHttpSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None
    span_kind: str
    service_name: str
    environment: str
    method: str | None
    route: str | None
    target_identity: str | None
    timestamp: datetime
```

This model is transient only.

It must never be persisted as a Neo4j `Span` node.

---

# 16. Correlation Buffer Requirements

The correlation buffer must be:

```text
bounded
TTL-based
environment-aware
thread-safe / async-safe as required
observable via lightweight counters
```

Suggested configuration:

```yaml
telemetry:
  http-correlation:
    enabled: true
    ttl-seconds: 60
    max-pending-spans: 10000
```

If the buffer limit is reached:

```text
oldest/expired entries are evicted
```

and the system must remain available.

---

# 17. Unresolved Observation Reasons

Extend or standardize reason codes as needed:

```text
MISSING_TARGET_IDENTITY
MISSING_CALLER_IDENTITY
UNSTABLE_HTTP_ROUTE
AMBIGUOUS_SERVICE
CORRELATION_EXPIRED
UNSUPPORTED_SPAN
```

Only short reason codes and safe identifiers may be persisted.

No raw span payload is required.

---

# 18. Runtime Analysis Compatibility

Existing O1–O5 analyses must continue to work.

No existing intent is renamed.

```text
O1 OBSERVED_RELATIONS
O2 CONFIRMED_RELATIONS
O3 OBSERVED_ONLY_RELATIONS
O4 DECLARED_ONLY_RELATIONS
O5 TELEMETRY_COVERAGE
```

11H may extend returned metadata but must not silently change the semantic meaning of these analyses.

---

# 19. Required Tests

## Unit Tests

Add tests for at least:

```text
stale declared evidence removal
observed evidence preservation
cross-batch HTTP correlation
correlation expiry
CLIENT_ONLY candidate creation
SERVER_ONLY unresolved behavior
stable-route enforcement
observed PROVIDES candidate creation
coverage classification
observation_count semantics
```

---

## Integration Tests

Use real Neo4j via Testcontainers for at least:

### I1 – Declared becomes observed-only

```text
DECLARED + OBSERVED
→ remove declaration
→ OBSERVED_ONLY remains
```

### I2 – Cross-batch correlation

```text
CLIENT span in OTLP request A
SERVER span in OTLP request B
→ one observed CALLS relation
```

### I3 – Client-only dependency

```text
CLIENT span only
stable target
→ observed dependency candidate
```

### I4 – Observed provider operation

```text
runtime server route
provider known
OpenAPI route absent
→ observed-only Operation
→ OBSERVED PROVIDES
```

### I5 – Later declaration reconciliation

```text
observed-only operation
→ later OpenAPI import
→ same logical operation
→ DECLARED + OBSERVED
```

### I6 – Coverage qualification

```text
declared relation not observed
coverage sufficient
→ NOT_OBSERVED_IN_WINDOW + SUFFICIENT
```

---

# 20. Regression Requirement

All existing H4 tests must remain green.

Starting baseline:

```text
319 unit
121 integration
440 total
```

No existing H4 acceptance behavior may regress.

---

# 21. API Compatibility

Existing endpoints remain valid:

```text
POST /v1/traces

GET /api/runtime/relations
GET /api/runtime/services/{serviceId}

GET /api/analysis/runtime/confirmed
GET /api/analysis/runtime/observed-only
GET /api/analysis/runtime/declared-only
GET /api/analysis/runtime/coverage
```

Optional additional metadata must be backward-compatible where practical.

---

# 22. Configuration

New configuration should remain optional with safe defaults.

Suggested additions:

```yaml
telemetry:

  http-correlation:
    enabled: true
    ttl-seconds: 60
    max-pending-spans: 10000

  coverage:
    qualification-enabled: true
```

The application must still start if these properties are absent.

---

# 23. Logging and Diagnostics

11H should add lightweight diagnostics for:

```text
correlated client/server pairs
client-only observations
server-only observations
expired correlations
unresolved observations
correlation-buffer evictions
```

Do not log sensitive span data.

Log IDs only where safe and useful.

---

# 24. Acceptance Criteria

| ID | Criterion |
|---|---|
| 11H.1 | Removing stale declared evidence never deletes a relation that still has observed evidence |
| 11H.2 | A `DECLARED + OBSERVED` relation becomes `OBSERVED_ONLY` after its declaration is removed |
| 11H.3 | Shared declared evidence from another source survives reconciliation |
| 11H.4 | HTTP CLIENT and SERVER spans can be correlated across separate OTLP requests |
| 11H.5 | Correlation state is bounded and TTL-based |
| 11H.6 | CLIENT-only observations can produce runtime dependency candidates when target identity is stable |
| 11H.7 | Ambiguous CLIENT-only observations remain unresolved rather than guessed |
| 11H.8 | SERVER-only observations do not invent an unknown caller |
| 11H.9 | Runtime-discovered stable provider operations can receive an OBSERVED `PROVIDES` relation |
| 11H.10 | Later declaration of an observed-only operation reconciles without duplication |
| 11H.11 | `NOT_OBSERVED_IN_WINDOW` can expose qualitative telemetry coverage |
| 11H.12 | Negative runtime findings still never imply `obsolete`, `unused`, or `dead` |
| 11H.13 | `observation_count` is explicitly documented as non-exact traffic evidence |
| 11H.14 | Correlation buffering persists no unrestricted/raw telemetry payload |
| 11H.15 | Runtime demo contains an OpenTelemetry Collector forwarding OTLP to AIP |
| 11H.16 | Documentation states that AIP is an additional telemetry consumer, not the primary observability backend |
| 11H.17 | Existing O1–O5 deterministic analyses remain LLM-independent |
| 11H.18 | Existing 440 H4 tests remain green |
| 11H.19 | New 11H unit and integration tests are green |
| 11H.20 | `ruff check` and `ruff format --check` are clean |

---

# 25. Implementation Sequence

## 11H-A – Evidence Reconciliation Correctness

```text
fix stale evidence reconciliation
        ↓
preserve observed evidence
        ↓
integration regression test
```

This is the highest-priority part of 11H.

---

## 11H-B – HTTP Correlation Robustness

```text
correlation buffer
      ↓
cross-batch matching
      ↓
TTL / eviction
      ↓
tests
```

---

## 11H-C – Partial Instrumentation

```text
CLIENT_ONLY
SERVER_ONLY
unresolved rules
correlation mode metadata
```

---

## 11H-D – Provider-Side Runtime Semantics

```text
observed-only operation
       ↓
OBSERVED PROVIDES
       ↓
later declaration reconciliation
```

---

## 11H-E – Coverage Qualification

```text
coverage categories
      ↓
O4 metadata
      ↓
API/UI representation
```

---

## 11H-F – Collector Demo

```text
otel-collector config
       ↓
docker-compose.demo.yml
       ↓
synthetic traffic
       ↓
AIP ingestion
```

---

# 26. Priority

| Priority | Item |
|---|---|
| P0 | R1 Evidence reconciliation correctness |
| P0 | Cross-batch HTTP correlation |
| P1 | CLIENT_ONLY partial instrumentation |
| P1 | OBSERVED `PROVIDES` |
| P1 | Coverage qualification |
| P1 | Collector-based public demo |
| P2 | Additional diagnostic counters / UI refinements |

---

# 27. Definition of Done

Iteration 11H is complete when the following runtime transition works correctly end-to-end:

```text
OpenAPI / AsyncAPI declaration
          +
OpenTelemetry observation
          |
          v
      CONFIRMED
          |
declaration removed on re-import
          |
          v
     OBSERVED_ONLY
```

without loss of observed evidence.

Additionally, a realistic split telemetry flow:

```text
CLIENT span
   |
 OTLP batch A

SERVER span
   |
 OTLP batch B
```

must still result in the correct runtime dependency.

And the public demo must show:

```text
Demo Service
     |
     v
OTel Collector
     |
     v
Architecture Intelligence Platform
```

without requiring AIP to act as the application's primary observability backend.

---

# 28. Resulting State After 11H

After 11H, H4 remains functionally unchanged but gains stronger real-world semantics:

\[
\boxed{
H4
=
ObservedArchitecture
+
Evidence
}
\]

becomes:

\[
\boxed{
H4+11H
=
RobustObservedArchitecture
+
IndependentEvidence
+
PartialInstrumentationTolerance
+
RealisticOTelTopology
}
\]

This forms the preferred technical baseline for:

```text
H5 – Open Source Readiness
```

and later:

```text
Desired State
Architecture Conformance
Promise Analysis
Transformation Planning
```

without requiring those later concepts to be implemented in 11H.
