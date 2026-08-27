# Specification – Architecture Intelligence Platform
## H4 – Observed Architecture / OpenTelemetry Integration

**Version:** 0.3  
**Status:** Implementation Specification  
**Basis:** PoC Iterations 0–10C / H1–H3 completed  
**Technology:** Python 3.13, FastAPI, Pydantic, Neo4j, OpenTelemetry Collector  
**Scope:** Extending the existing Evidence-backed Architecture Knowledge Graph with actually observed runtime relationships

---

## 1. Starting Point

After completing H1–H3, the platform has:

- an Evidence-backed Architecture Knowledge Graph,
- complete provenance for declared architecture relationships,
- deterministic analyses A1–A5,
- an Intent Router that answers known questions without an LLM,
- a Security Validator for Cypher,
- a Semantic Query Validator for domain/range relationships.

All H1, H2, and H3 criteria are met. The current test suite comprises **300 passing tests**, of which 221 are unit tests and 79 are Neo4j/Testcontainers integration tests.

The current state thus corresponds to:

\[
\boxed{
Declared\ Architecture
+
Evidence
+
Deterministic\ Reasoning
+
Constrained\ LLM
}
\]

In particular, the hardening iteration achieved that facts can be traced back to their source, known questions are answered deterministically, and semantically incorrect graph relationships no longer reach Neo4j.

H4 now adds:

\[
\boxed{OBSERVED}
\]

Architecture Evidence from OpenTelemetry.

---

## 2. Objective

H4 is meant to connect the existing declared architecture with the **architecture actually observed at runtime**.

From:

```text
OpenAPI
AsyncAPI
Manifest
    |
    v
DECLARED Architecture
```

it becomes:

```text
                    Architecture Knowledge Graph

              DECLARED                    OBSERVED
                 |                           |
       OpenAPI / AsyncAPI              OpenTelemetry
                 |                           |
                 +------------+--------------+
                              |
                              v
                        Architecture Fact
```

In particular, this should make three states distinguishable:

\[
\boxed{DECLARED\_ONLY}
\]

\[
\boxed{OBSERVED\_ONLY}
\]

\[
\boxed{CONFIRMED}
\]

Example:

```text
OrderService
     |
    CALLS
     |
     v
ProductService

Evidence:
  DECLARED  -> Architecture Manifest
  OBSERVED  -> OpenTelemetry
```

Status:

```text
CONFIRMED
```

---

## 3. Core Hypothesis of H4

The central hypothesis is:

\[
\boxed{
DeclaredArchitecture
\neq
ObservedArchitecture
}
\]

and it is precisely their difference that contains valuable architectural knowledge.

In particular:

\[
Observed-Declared
\]

potentially finds **undocumented real dependencies**.

Conversely:

\[
Declared-Observed
\]

yields relationships for which no runtime evidence exists within a defined observation window.

Important:

\[
Declared-Observed
\not\Rightarrow
obsolete.
\]

"Not observed" must not automatically be interpreted as "unused" or "obsolete."

---

## 4. Scope

### 4.1 Part of H4

H4 supports:

- OpenTelemetry Traces,
- Service identification,
- REST client/server communication,
- Queue-based messaging communication,
- Observed Evidence,
- Time windows,
- Environments,
- Matching to existing graph entities,
- Creation of observed, previously unknown architecture facts,
- Comparison of `DECLARED` vs. `OBSERVED`,
- Deterministic runtime analyses.

### 4.2 Not Part of H4

Deliberately not implemented:

- Metrics,
- Logs,
- Storage of complete traces in Neo4j,
- Trace waterfall UI,
- Full event/causality graph,
- Vector database,
- GraphRAG,
- Architecture wiki,
- Anomaly detection via ML,
- Automatic architecture changes,
- SLO evaluation,
- Performance analysis,
- Long-term telemetry storage.

H4 is:

\[
\boxed{
Runtime\ Architecture\ Discovery
}
\]

and **not an observability backend**.

---

## 5. Architecture

```text
                     MICROSERVICES

         Service A                 Service B
             |                         |
             | OpenTelemetry SDK       |
             +------------+------------+
                          |
                          v
                OpenTelemetry Collector
                          |
               +----------+----------+
               |                     |
               v                     v
       Existing Trace Backend   Architecture
                               Intelligence
                               OTLP Ingestion
                                      |
                                      v
                           OpenTelemetry Adapter
                                      |
                                      v
                          Observation Resolver
                                      |
                                      v
                         Observation Aggregator
                                      |
                                      v
                                Neo4j
                                      |
                       +--------------+-------------+
                       |                            |
                       v                            v
               Runtime Analyses            Declared/Observed
                                                Comparison
```

The OpenTelemetry Collector is not meant to **replace** the existing observability solution.

Architecture Intelligence is merely an additional telemetry consumer.

---

## 6. OpenTelemetry Collector

The Collector forms the boundary between the instrumented services and the Architecture Intelligence Platform.

```text
Microservices
    |
   OTLP
    |
    v
OpenTelemetry Collector
    |
    +----> Jaeger / Tempo / existing backend
    |
    +----> Architecture Intelligence
```

This keeps the architecture platform independent of whichever trace backend is used in production.

---

## 7. Supported Signals

H4 processes exclusively:

```text
TRACE / SPAN
```

Not processed:

```text
METRIC
LOG
```

Architecture information arises from operations **between system components**, as described by OpenTelemetry through spans.

---

## 8. OTLP Ingestion

New component:

```text
app/
  telemetry/
      otlp_receiver.py
```

Primary entry point:

```text
POST /v1/traces
```

Format supported for H4:

```text
OTLP/HTTP
application/x-protobuf
```

The receiver decodes the traces using the OpenTelemetry protobuf types and then transforms them into an internal model.

---

## 9. No Direct Graph Persistence from OTLP

The central architectural principle continues to apply:

```text
External Format
      |
      v
Canonical Representation
      |
      v
Neo4j
```

in other words, **not**:

```text
OTLP -> Neo4j
```

but rather:

```text
OTLP
 |
 v
OpenTelemetryAdapter
 |
 v
ObservationBatch
 |
 v
Resolver
 |
 v
ObservedFactCandidate
 |
 v
Aggregator
 |
 v
Neo4j
```

---

## 10. Observation Model

New Pydantic structures:

```python
class RuntimeSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None

    span_name: str
    span_kind: str

    service_name: str
    service_namespace: str | None
    service_version: str | None
    service_instance_id: str | None

    environment: str | None

    start_time: datetime
    end_time: datetime

    attributes: dict[str, Any]
```

This structure is only a temporary ingestion model.

It is **not stored as a node in Neo4j**.

---

## 11. Service Identity

The primary Service ID from OpenTelemetry is:

```text
service.name
```

optionally supplemented by:

```text
service.namespace
```

Hence:

```text
service.name = PaymentService

instance 1 ┐
instance 2 ├──> one Service node
instance 3 ┘
```

Not:

```text
PaymentService-1
PaymentService-2
PaymentService-3
```

---

## 12. Service Resolver

New component:

```text
telemetry/
    service_resolver.py
```

Task:

```text
OTel Resource
     |
     v
Service Identity
     |
     v
Existing Graph Service
```

Matching order:

1. `service.namespace + service.name`
2. `service.name`
3. configured alias
4. otherwise, observed-only Service.

---

## 13. Observed-only Services

If, for example, the following is observed:

```text
service.name = FraudService
```

but no Service exists for it in the declarative graph, a new:

```text
(:Service)
```

is created.

Properties:

```text
id
name
discoveryStatus = OBSERVED_ONLY
```

It carries exclusively `OBSERVED` Evidence.

This enables the analysis:

> Which services exist at runtime but are not known in any architecture artifact?

---

## 14. Environment

Runtime architecture must be separated by environment.

The primary attribute used is:

```text
deployment.environment.name
```

So:

```text
PaymentService
```

remains a single Service.

The observation carries:

```text
environment = production
```

or:

```text
environment = staging
```

---

## 15. Extending the Evidence Model

Existing:

```python
class EvidenceType(StrEnum):
    DECLARED = "DECLARED"
```

becomes:

```python
class EvidenceType(StrEnum):
    DECLARED = "DECLARED"
    OBSERVED = "OBSERVED"
```

SourceType:

```python
class SourceType(StrEnum):
    OPENAPI = "OPENAPI"
    ASYNCAPI = "ASYNCAPI"
    MANIFEST = "MANIFEST"
    OPENTELEMETRY = "OPENTELEMETRY"
```

---

## 16. Observed Evidence

Observed Evidence extends the existing provenance data.

```python
class ObservedEvidence(Evidence):
    environment: str

    bucket_start: datetime
    bucket_end: datetime

    first_seen: datetime
    last_seen: datetime

    observation_count: int

    sample_trace_ids: list[str] = []

    service_version: str | None = None
```

---

## 17. Evidence Buckets

An important design decision:

**Not every span creates an Evidence node.**

For example, with:

```text
20,000 REST calls / hour
```

this must not result in:

```text
20,000 Evidence Nodes
```

Instead, aggregation is used.

For the PoC:

\[
bucket=1\ day.
\]

Example:

```text
evidence:otel:production:2026-08-26:<fact-hash>
```

Properties:

```text
firstSeen
lastSeen
observationCount
sampleTraceIds
```

---

## 18. Limited Trace Samples

An Evidence node stores at most:

```text
5 trace IDs
```

for example:

```json
{
  "sampleTraceIds": [
    "abc...",
    "def...",
    "123..."
  ]
}
```

This keeps a sample available for technical verification.

The Architecture Graph, however, does **not** become a trace store.

---

## 19. Observation Count

`observationCount` serves as an indicator:

```text
CALLS relation observed approximately 12,431 times
```

not as a billing/monitoring metric.

OTLP retries can lead to overcounting.

Therefore:

\[
observationCount=best\ effort.
\]

For architecture classification purposes, it is sufficient that:

\[
count>0.
\]

---

## 20. REST – Observed Architecture

REST communication is primarily derived from HTTP client/server spans.

Example:

```text
OrderService

CLIENT span:
GET /products/{id}

              |
              v

ProductService

SERVER span:
GET /products/{id}
```

From this:

```text
OrderService
     |
   CALLS
     |
     v
GET /products/{id}
     ^
     |
 PROVIDES
     |
ProductService
```

plus `OBSERVED` Evidence.

---

## 21. REST Provider Resolution

The most reliable mapping arises from correlated client/server spans:

```text
Client Span
   |
 trace / parent-child
   |
   v
Server Span
```

The server span carries:

```text
resource.service.name
```

and thereby identifies the actual target service.

As a result, there is no need to guess based on hostnames.

---

## 22. HTTP Operation Resolution

Operation identity:

```text
provider service
+
HTTP method
+
route/template
```

Example:

```text
operation:product-service:GET:/products/{id}
```

Attributes used:

```text
http.request.method
http.route
url.template
```

Consequently, for example:

```text
/products/4711
```

must not automatically create a new `Operation` node.

---

## 23. REST Mapping

### Case A – existing declared operation

```text
GET /products/{id}
```

already exists from OpenAPI.

In that case:

```text
OrderService -[:CALLS]-> Operation
```

receives additional:

```text
OBSERVED Evidence
```

### Case B – operation observed, but not declared

If a stable route/template is available:

```text
GET /internal/products/{id}
```

an:

```text
Observed-only Operation
```

can be created.

Status:

```text
OBSERVED_ONLY
```

### Case C – no stable route

Only:

```text
/products/4711
```

is known.

In that case:

```text
UNRESOLVED observation
```

and **no Operation node**.

This prevents:

```text
/products/4711
/products/4712
/products/4713
...
```

from becoming graph nodes.

---

## 24. Messaging / Queue Architecture

The existing graph has:

```text
Service -[:SENDS]-> Queue

Service -[:RECEIVES_FROM]-> Queue
```

These relations are confirmed or newly discovered from OpenTelemetry messaging spans.

---

## 25. Queue SEND Detection

A producer/send span such as:

```text
service.name = OrderService

messaging.system = ...
messaging.destination.name = payment-q
messaging.operation.type = send
```

leads to:

```text
OrderService
     |
   SENDS
     |
     v
 payment-q
```

with:

```text
OBSERVED Evidence
```

---

## 26. Queue RECEIVE Detection

Consumer/process spans:

```text
service.name = PaymentService

messaging.destination.name = payment-q
messaging.operation.type = receive
```

or:

```text
process
```

lead to:

```text
PaymentService
       |
RECEIVES_FROM
       |
       v
 payment-q
```

with `OBSERVED` Evidence.

---

## 27. Queue Identity

Queue identity is determined from:

```text
messaging.system
+
broker/system instance
+
messaging.destination.name
```

Example:

```text
queue:<system>:<namespace>:payment-q
```

The same ID generator as used by the AsyncAPI importer should be used here.

Goal:

```text
AsyncAPI Queue
       =
OpenTelemetry Queue
```

and not two parallel nodes.

---

## 28. Messaging Destination Resolver

New component:

```text
telemetry/
    queue_resolver.py
```

Matching:

1. exact Canonical Queue ID,
2. messaging system + destination name,
3. configured namespace/alias,
4. otherwise, observed-only Queue.

---

## 29. Observed-only Queue

If the following is observed:

```text
legacy-payment-q
```

but it does not exist anywhere in AsyncAPI:

```text
(:Queue {
    name: "legacy-payment-q",
    discoveryStatus: "OBSERVED_ONLY"
})
```

with:

```text
OBSERVED Evidence
```

This immediately makes:

\[
Observed-Declared
\]

visible.

---

## 30. Message Types

OpenTelemetry does not necessarily provide the domain-level message type that is modeled in AsyncAPI as:

```text
PaymentRequested
```

Therefore, H4 is initially limited to:

```text
Service -> Queue
```

Not guaranteed:

```text
Service -> exact Message Type
```

A later extension could introduce a project-specific low-cardinality attribute, for example:

```text
architecture.message.type
```

This is **not part of H4**.

---

## 31. No Payloads

Not stored:

- Message body,
- HTTP request body,
- HTTP response body,
- Authorization header,
- Cookies,
- Query parameters,
- Personal data values,
- Full URLs,
- Exception stack traces.

Architecture Intelligence uses an explicit **attribute allowlist**.

---

## 32. Attribute Allowlist

REST, for example:

```text
service.name
service.namespace
service.version
service.instance.id

deployment.environment.name

http.request.method
http.route
url.template

server.address
server.port
```

Messaging:

```text
service.name
service.namespace
service.version

deployment.environment.name

messaging.system
messaging.destination.name
messaging.destination.template
messaging.operation.name
messaging.operation.type
```

---

## 33. OpenTelemetry Semantic Convention Versioning

The adapter must not scatter OTel attribute names throughout the code.

New component:

```text
telemetry/
    semconv/
        http.py
        messaging.py
        resources.py
```

This allows different semantic convention versions to be normalized centrally.

---

## 34. ObservedFactCandidate

Canonical runtime model:

```python
class ObservedFactCandidate(BaseModel):
    subject_id: str
    relation_type: str
    object_id: str

    environment: str

    timestamp: datetime

    trace_id: str | None

    source_service_version: str | None

    evidence: ObservedEvidence
```

Example:

```text
subject:
  service:order-service

predicate:
  SENDS

object:
  queue:asb:commerce:payment-q
```

---

## 35. ObservationBatch

```python
class ObservationBatch(BaseModel):
    entities: list[ArchitectureEntity]
    facts: list[ObservedFactCandidate]
    unresolved: list[UnresolvedObservation]
```

This keeps the telemetry pipeline similar to the existing adapter model:

```text
Source
   |
Adapter
   |
Canonical Representation
   |
Graph
```

---

## 36. Observation Aggregator

New component:

```text
telemetry/
    aggregator.py
```

Tasks:

1. Normalize fact,
2. Determine Evidence bucket,
3. Look up existing relation,
4. Add `OBSERVED` Evidence,
5. Update counter,
6. Update `first_seen` / `last_seen`,
7. Limit trace samples.

---

## 37. No New Relation Types for Observed

Important design decision:

Not:

```text
OBSERVED_CALLS
DECLARED_CALLS
```

but rather, still:

```text
CALLS
SENDS
RECEIVES_FROM
```

The evidence determines the status.

Example:

```text
OrderService -[:CALLS]-> getProduct
```

Evidence:

```text
E1 DECLARED
E2 OBSERVED
```

Status:

```text
CONFIRMED
```

---

## 38. Fact Status

The status is **derived**, not stored as the primary source of truth.

For fact \(F\):

\[
D(F)=
\exists e:
EvidenceType(e)=DECLARED
\]

\[
O(F,W,E)=
\exists e:
EvidenceType(e)=OBSERVED
\land e\in Window(W)
\land environment(e)=E
\]

Then:

\[
D\land O
\Rightarrow CONFIRMED
\]

\[
D\land\neg O
\Rightarrow DECLARED\_ONLY
\]

\[
\neg D\land O
\Rightarrow OBSERVED\_ONLY.
\]

---

## 39. Observation Window

Runtime questions always require a time window.

Default:

```text
last 24h
```

or configurable:

```text
7d
30d
```

Example:

```text
Declared but not observed
during production / last 7 days
```

Not:

```text
Declared but never used
```

---

## 40. Not Observed Is Not Negative Evidence

Fundamental rule:

\[
\boxed{
Absence\ of\ observation
\neq
evidence\ of\ absence
}
\]

Therefore, the UI and API must never automatically phrase things as:

```text
unused
dead
obsolete
```

but exclusively as:

```text
NOT_OBSERVED_IN_WINDOW
```

---

## 41. Telemetry Coverage

To aid interpretation, coverage is additionally determined.

Example:

```text
PaymentService

environment: production
window: 7d

telemetry:
  spansObserved: true
  httpObserved: true
  messagingObserved: true
```

This allows distinguishing between:

```text
Relation not observed
```

and:

```text
Service emitted no usable telemetry at all
```

---

## 42. Analysis O1 – Observed Relations

New deterministic analysis:

> Which architecture relationships were actually observed?

```text
O1 OBSERVED_RELATIONS
```

Filters:

```text
environment
from
to
relationType
timeWindow
```

---

## 43. Analysis O2 – Confirmed Architecture

```text
O2 CONFIRMED_RELATIONS
```

Sought:

\[
Declared\cap Observed.
\]

Example:

```text
OrderService -> payment-q

DECLARED AsyncAPI
OBSERVED OpenTelemetry
```

---

## 44. Analysis O3 – Observed but not Declared

```text
O3 OBSERVED_ONLY_RELATIONS
```

Sought:

\[
Observed-Declared.
\]

Example:

```text
OrderService
    |
   CALLS
    |
LegacyPricingService
```

OpenTelemetry:

```text
yes
```

OpenAPI/Manifest:

```text
no
```

Result:

> Undocumented runtime dependency.

This is likely the most important H4 analysis.

---

## 45. Analysis O4 – Declared but not Observed

```text
O4 DECLARED_ONLY_RELATIONS
```

Sought:

\[
Declared-Observed.
\]

The output must always include:

```text
environment
observation window
telemetry coverage
```

Example:

```text
ProductService CALLS PricingService

Declared: yes
Observed in production / last 7d: no
Coverage: available
```

Interpretation:

> No observation within the specified time period.

Not:

> Dependency is obsolete.

---

## 46. Analysis O5 – Telemetry Coverage

```text
O5 TELEMETRY_COVERAGE
```

Example:

```text
OrderService          HTTP ✓ Messaging ✓
PaymentService        HTTP ✓ Messaging ✓
InvoiceService        HTTP - Messaging ✓
LegacyService         no telemetry
```

This allows assessing the trustworthiness of O4.

---

## 47. REST API

New endpoints:

```text
GET /api/runtime/relations
```

Parameters:

```text
environment
since
until
relationType
```

```text
GET /api/runtime/services/{serviceId}
```

```text
GET /api/analysis/runtime/confirmed
```

```text
GET /api/analysis/runtime/observed-only
```

```text
GET /api/analysis/runtime/declared-only
```

```text
GET /api/analysis/runtime/coverage
```

---

## 48. Example O3 Response

```json
{
  "environment": "production",
  "window": {
    "from": "2026-08-19T00:00:00Z",
    "to": "2026-08-26T00:00:00Z"
  },
  "relations": [
    {
      "source": "OrderService",
      "relation": "CALLS",
      "target": "LegacyPricingService",
      "status": "OBSERVED_ONLY",
      "firstSeen": "...",
      "lastSeen": "...",
      "observationCount": 721
    }
  ]
}
```

---

## 49. UI – Service Explorer

The existing page is extended.

```text
OrderService
```

### Declared

```text
CALLS ProductService
SENDS payment-q
```

### Observed – production / last 7 days

```text
✓ CALLS ProductService
✓ SENDS payment-q

! CALLS LegacyPricingService
```

Legend:

```text
✓ CONFIRMED
! OBSERVED_ONLY
○ DECLARED_ONLY
```

---

## 50. UI – Relation Detail

Example:

```text
OrderService
      |
    SENDS
      |
  payment-q
```

### Evidence

```text
DECLARED

AsyncAPI
order-service/asyncapi.yaml
revision abc123
```

```text
OBSERVED

OpenTelemetry
production
first seen 2026-08-24 08:12
last seen  2026-08-26 09:22
observations 12,431
```

---

## 51. Natural-Language Intent Router

The H3 architecture remains in place.

New deterministic intents:

```python
OBSERVED_RELATIONS
CONFIRMED_RELATIONS
OBSERVED_ONLY_RELATIONS
DECLARED_ONLY_RELATIONS
TELEMETRY_COVERAGE
```

Examples:

> Which undocumented REST dependencies were observed in production?

→ O3.

> Which declared communication was not observed in the last seven days?

→ O4.

> For which services do we have no telemetry?

→ O5.

These questions are meant to require **no LLM-generated Cypher**.

---

## 52. LLM Remains a Fallback

New pipeline:

```text
Question
   |
   v
Intent Router
   |
   +---- A1-A5 deterministic
   |
   +---- O1-O5 deterministic
   |
   +---- UNKNOWN
             |
             v
            LLM
             |
             v
       Security Validator
             |
             v
       Semantic Validator
             |
             v
           Neo4j
```

H4 therefore does not increase reliance on the LLM.

---

## 53. Graph Schema Registry

H2 is not extended with parallel `OBSERVED_*` relations.

The existing domain/range definitions remain valid:

```text
Service -> CALLS -> Operation
Service -> SENDS -> Queue
Service -> RECEIVES_FROM -> Queue
```

The only addition is:

```text
EvidenceType = OBSERVED
```

This keeps Semantic Validation usable unchanged.

---

## 54. Python Package Structure

```text
app/
│
├── telemetry/
│   ├── otlp_receiver.py
│   ├── adapter.py
│   ├── model.py
│   ├── aggregator.py
│   │
│   ├── service_resolver.py
│   ├── operation_resolver.py
│   ├── queue_resolver.py
│   │
│   └── semconv/
│       ├── resources.py
│       ├── http.py
│       └── messaging.py
│
├── runtime_analysis/
│   ├── observed.py
│   ├── confirmed.py
│   ├── observed_only.py
│   ├── declared_only.py
│   └── coverage.py
│
├── evidence/
│   └── ...
│
├── graph/
│   └── ...
│
├── intent/
│   └── ...
│
└── api/
    ├── runtime.py
    └── ...
```

---

## 55. Docker Compose

PoC runtime:

```text
docker-compose.yml

architecture-intelligence
neo4j
otel-collector
```

Optional existing trace backend:

```text
jaeger / tempo
```

---

## 56. Collector Concept

```text
receivers:
  OTLP
      |
      v
processors
      |
      +---------> normal observability exporter
      |
      +---------> architecture-intelligence exporter
```

This ensures a failure of the Architecture Intelligence Platform does not affect the normal telemetry path.

---

## 57. Backpressure / Failure

If Architecture Intelligence fails:

```text
OpenTelemetry Collector
        |
        X architecture exporter
        |
        +---- normal trace backend continues
```

Architecture Intelligence must **not become a single point of failure for observability**.

---

## 58. Privacy and Security

H4 processes exclusively the metadata necessary for determining architecture relationships.

Principle:

\[
\boxed{Minimum\ Telemetry\ Principle}
\]

Not persisted:

- Payloads,
- Headers,
- User IDs,
- Query strings,
- Message bodies,
- Stack traces.

---

## 59. Retention

Neo4j stores only aggregated Observed Evidence.

PoC proposal:

```text
observed evidence retention = 90 days
```

Configurable:

```yaml
telemetry:
  evidence-retention-days: 90
  bucket-size: 1d
  sample-trace-ids: 5
```

---

## 60. Cleanup

Periodic job:

```text
EvidenceCleanupJob
```

removes:

```text
OBSERVED Evidence older than retention
```

If an `OBSERVED_ONLY` fact subsequently has no evidence left at all, it can be deleted.

A `DECLARED` fact is retained.

---

## 61. Tests – Unit

New unit tests at minimum for:

### OTLP Decoder

- Resource extraction
- Span extraction
- Malformed payload

### Service Resolver

- Exact match
- Namespace match
- Instance ignored
- Observed-only service

### HTTP Resolver

- Client/server pair
- Existing operation
- Observed-only operation
- Raw URI rejected

### Messaging Resolver

- SEND
- RECEIVE
- PROCESS
- Existing queue
- Observed-only queue

### Aggregator

- Bucket aggregation
- Evidence deduplication
- First/last seen
- Trace sample limit

---

## 62. Integration Tests

With:

```text
real Neo4j 5
+
FastAPI
+
OTLP protobuf
```

Test path:

```text
OTLP batch
    |
    v
/v1/traces
    |
    v
Observed Fact
    |
    v
Neo4j
```

---

## 63. Test Landscape

Existing services:

```text
OrderService
ProductService
PaymentService
InvoiceService
```

Additional runtime test cases:

```text
OrderService -> ProductService
```

declared + observed:

```text
CONFIRMED
```

```text
OrderService -> LegacyPricingService
```

observed only:

```text
OBSERVED_ONLY
```

```text
PaymentService -> invoice-q
```

declared, but not observed within the test window:

```text
DECLARED_ONLY
```

---

## 64. Regression

All existing:

\[
300
\]

tests must continue to pass.

H4 must not:

- break H1 Evidence,
- bypass H2 Semantic Validation,
- bypass H3 Intent Routing.

---

## 65. H4 Acceptance Criteria

| ID | Criterion |
|---|---|
| H4.1 | OTLP trace batches can be ingested via the Collector |
| H4.2 | `service.name` is correctly mapped to logical Service nodes |
| H4.3 | `service.instance.id` does not create additional Service nodes |
| H4.4 | `deployment.environment.name` separates observations by environment |
| H4.5 | HTTP client/server spans produce observed REST relationships |
| H4.6 | existing OpenAPI operations are correctly reused |
| H4.7 | messaging SEND creates/updates `SENDS` |
| H4.8 | messaging RECEIVE/PROCESS creates/updates `RECEIVES_FROM` |
| H4.9 | known AsyncAPI queues are reused |
| H4.10 | unknown runtime services/queues can be created as `OBSERVED_ONLY` |
| H4.11 | Observed Evidence includes environment, FirstSeen, LastSeen, and count |
| H4.12 | spans are aggregated and not stored individually as Neo4j nodes |
| H4.13 | `DECLARED ∩ OBSERVED` is recognized as `CONFIRMED` |
| H4.14 | `OBSERVED - DECLARED` is determined deterministically |
| H4.15 | `DECLARED - OBSERVED` is determined relative to a time window |
| H4.16 | `DECLARED_ONLY` is not automatically classified as "obsolete" |
| H4.17 | Telemetry Coverage is separately queryable |
| H4.18 | O1–O5 work entirely without an LLM |
| H4.19 | sensitive span attributes are not persisted |
| H4.20 | the existing 300 tests remain green |

---

## 66. Success Criteria

H4 is considered functionally successful if at least one real-world use case is found in which:

\[
Observed-Declared\neq\emptyset.
\]

That is, for example, a real REST or queue dependency that was not present in the declarative knowledge graph.

A second important outcome would be:

\[
Declared-Observed\neq\emptyset,
\]

where the platform correctly states only:

> "Not seen within the selected observation period."

---

## 67. Implementation Order

### Iteration 11A – OTLP Foundation

```text
Collector
   ↓
OTLP Receiver
   ↓
RuntimeSpan
```

No graph update yet.

### Iteration 11B – Service & Environment Resolution

```text
Resource attributes
      ↓
Service Resolver
      ↓
Environment
```

### Iteration 11C – REST Observations

```text
HTTP spans
   ↓
Client/server correlation
   ↓
Operation Resolver
   ↓
CALLS + OBSERVED Evidence
```

### Iteration 11D – Queue Observations

```text
Messaging spans
   ↓
Queue Resolver
   ↓
SENDS / RECEIVES_FROM
   ↓
OBSERVED Evidence
```

### Iteration 11E – Evidence Aggregation

```text
Span
   ↓
Fact
   ↓
daily Evidence bucket
   ↓
firstSeen / lastSeen / count
```

### Iteration 11F – Architecture Comparison

Implement:

```text
O1 Observed
O2 Confirmed
O3 Observed only
O4 Declared only
O5 Coverage
```

### Iteration 11G – API / UI / Intent Router

```text
Runtime API
+
Service Explorer
+
O1-O5 intents
```

---

## 68. Definition of Done

After H4, the platform has the following data pipeline:

```text
                DECLARED SOURCES
         OpenAPI / AsyncAPI / Manifest
                    |
                    v
                Evidence
                    |
                    v
               Architecture
                   Facts
                    ^
                    |
                Evidence
                    ^
                    |
              OpenTelemetry
                    ^
                    |
               Runtime
```

and can deterministically distinguish:

\[
\boxed{
CONFIRMED
=
DECLARED\cap OBSERVED
}
\]

\[
\boxed{
UNDOCUMENTED
=
OBSERVED-DECLARED
}
\]

\[
\boxed{
NOT\_OBSERVED\_IN\_WINDOW
=
DECLARED-OBSERVED
}
\]

---

## 69. Target State After H4

Before H4:

\[
\boxed{
Architecture\ Knowledge\ Graph
}
\]

After H4:

\[
\boxed{
Architecture\ Intelligence\ Platform
}
\]

because the platform can then no longer answer only:

> What do our architecture artifacts claim?

but additionally:

> What is actually happening?

and in particular:

\[
\boxed{
\text{Where do declared and observed architecture differ?}
}
\]

This exact difference is the decisive additional insight gained from H4.

A further, conceptually important step follows from this: as soon as `OBSERVED` evidence is available over time, the platform for the first time has a robust **temporal dimension of architecture**. This would subsequently make H5 conceivable: no longer just "which relation was observed?", but **causal runtime flows and architecture trajectories**.
