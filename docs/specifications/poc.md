# Architecture Intelligence Platform — PoC Specification

Proof of Concept — Technical Specification. Python reference implementation.

> OpenAPI + AsyncAPI (Queues) → Canonical Model → Neo4j → Architecture Analysis → LLM Query

| | |
|---|---|
| Version | 1.0 |
| Status | PoC Specification |
| Reference stack | Python 3.13, FastAPI, Pydantic, Neo4j |
| Communication | Synchronous REST + asynchronous queues |

This is the original design document the very first implementation iterations were built against —
the Canonical Model, the OpenAPI/AsyncAPI/manifest adapters, the Neo4j graph model, the five
deterministic analyses (A1-A5), and the read-only LLM query subsystem. Everything documented under
[`docs/`](..) today builds on top of what this PoC established. Converted to Markdown and translated
to English from the original PDF; content is otherwise unchanged from the original specification.

## Contents

1. Goal and PoC boundaries
2. System context and target architecture
3. Technology stack
4. Canonical Architecture Model
5. Source and ingestion layer
6. OpenAPI adapter
7. AsyncAPI queue adapter
8. Architecture Manifest
9. Provenance and evidence
10. Validation
11. Neo4j graph model
12. Graph import and reconciliation
13. Analysis engine
14. REST API
15. LLM query subsystem
16. Minimal UI
17. Configuration and operations
18. Logging and observability
19. Security
20. Tests
21. Acceptance criteria
22. Repository structure
23. Implementation plan
24. Extension beyond the PoC

## 1. Goal and PoC boundaries

The PoC is meant to prove that an Architecture Knowledge Graph can be built automatically from
existing OpenAPI and AsyncAPI specifications, mapping synchronous REST communication and
asynchronous queue communication into one shared model.

The graph is the structured fact base. Standard analyses run deterministically via Cypher. An LLM
serves purely as a natural-language query and explanation layer over the graph.

### 1.1 Core hypothesis

```text
OpenAPI + AsyncAPI + minimal Architecture Manifest
                 |
                 v
       Canonical Architecture Model
                 |
                 v
              Neo4j
                 |
       +---------+---------+
       |                   |
       v                   v
  Cypher analyses       LLM Query
```

### 1.2 In scope

- Import of multiple OpenAPI specifications (OpenAPI 3.0/3.1).
- Import of multiple AsyncAPI specifications with queue-based communication.
- Mapping of REST providers and callers.
- Mapping of queue senders, queue consumers, messages, schemas, and DLQ relationships.
- Canonical Model as a technology-independent intermediate layer.
- Persistence and querying in Neo4j.
- Five defined architecture analyses.
- Read-only LLM query: natural language → validated Cypher → graph result → explanation.
- Minimal REST API and an optional small web UI.
- Provenance for all essential architecture facts.

### 1.3 Deliberately not in the first PoC

- Kubernetes/cloud discovery.
- OpenTelemetry and runtime traces.
- Vector database and document RAG.
- ADR/ticket/source-code analysis.
- Auto-generated LLM wiki.
- Team ownership and organization graph.
- CI/CD policy gates.
- A full Promise Theory or Semantic Spacetime implementation.

## 2. System context and target architecture

The PoC is implemented as a modular Python monolith. All functional subcomponents run in one
FastAPI process; Neo4j is the only external persistent infrastructure component.

```text
Git / local repositories
  |-- openapi.yaml
  |-- asyncapi.yaml
  `-- architecture.yaml (optional)
              |
              v
+----------------------------------+
| Architecture Intelligence API    |
| Python 3.13 + FastAPI            |
|                                  |
| Scanner -> Parser -> Canonical   |
|          -> Validation           |
|          -> Graph Import         |
|          -> Analyses             |
|          -> LLM Query            |
+----------------+-----------------+
                 |
                 v
              Neo4j
```

### 2.1 Communication model

| Communication | Canonical flow | Source |
|---|---|---|
| Synchronous / REST | Caller Service -[:CALLS]-> Operation <-[:PROVIDES]- Provider Service | OpenAPI + Architecture Manifest |
| Asynchronous / Queue | Sender Service -[:SENDS]-> Queue <-[:RECEIVES_FROM]- Consumer Service | AsyncAPI |
| Payload | Queue -[:CARRIES]-> Message -[:CONFORMS_TO]-> Schema | AsyncAPI |
| REST payload | Operation -[:REQUEST_SCHEMA / :RESPONSE_SCHEMA]-> Schema | OpenAPI |

## 3. Technology stack

| Area | Technology | Rationale |
|---|---|---|
| Runtime | Python 3.13 | Fast iteration, strong parsing/graph/LLM ecosystem. |
| Web/API | FastAPI | Typed API, OpenAPI generation, low PoC complexity. |
| Models | Pydantic v2 | Validation and serialization of the Canonical Model. |
| YAML/JSON | PyYAML / stdlib json | Direct handling of OpenAPI/AsyncAPI/manifest. |
| Schema validation | jsonschema | Validation of JSON-Schema-based artifacts. |
| Graph DB | Neo4j | Property graph, Cypher, visualization, traversal/impact analysis. |
| Graph driver | neo4j Python driver | Official driver; explicit transactions. |
| Tests | pytest + Testcontainers | Unit and Neo4j integration tests. |
| Packaging | pyproject.toml | Modern dependency and build setup. |
| Local runtime | Docker Compose | Simple local startup of app + Neo4j. |
| Optional analysis | NetworkX | Later experimental graph metrics; not MVP-critical. |

## 4. Canonical Architecture Model

OpenAPI and AsyncAPI are never written directly into the Neo4j schema. Each source adapter first
produces a shared Canonical Model. This keeps parsers, graph persistence, and later data sources
decoupled from one another.

### 4.1 Core entities

| Entity | Required fields | Meaning |
|---|---|---|
| Service | id, name | Logical microservice. |
| Operation | id, service_id, method, path | REST operation. |
| Queue | id, name | Asynchronous transport/buffer endpoint. |
| Message | id, name | Semantic message type. |
| Schema | id, name, format | Payload or API data schema. |
| Relation | type, source_id, target_id | Typed architecture relationship. |
| Provenance | source_type, source_file, revision | Origin of a fact. |

### 4.2 Pydantic reference model

```python
from enum import StrEnum
from pydantic import BaseModel, Field

class Direction(StrEnum):
    SEND = "SEND"
    RECEIVE = "RECEIVE"

class Service(BaseModel):
    id: str
    name: str
    version: str | None = None

class Operation(BaseModel):
    id: str
    service_id: str
    operation_id: str | None = None
    method: str
    path: str
    request_schema_ids: list[str] = Field(default_factory=list)
    response_schema_ids: list[str] = Field(default_factory=list)

class Queue(BaseModel):
    id: str
    name: str
    protocol: str | None = None
    namespace: str | None = None
    queue_type: str = "STANDARD"

class Message(BaseModel):
    id: str
    name: str
    version: str | None = None
    schema_id: str | None = None

class Schema(BaseModel):
    id: str
    name: str
    version: str | None = None
    format: str | None = None
    canonical_hash: str | None = None

class ArchitectureModel(BaseModel):
    services: list[Service] = Field(default_factory=list)
    operations: list[Operation] = Field(default_factory=list)
    queues: list[Queue] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    schemas: list[Schema] = Field(default_factory=list)
    relations: list["Relation"] = Field(default_factory=list)
    provenance: list["Provenance"] = Field(default_factory=list)
```

### 4.3 Stable IDs

| Type | Example |
|---|---|
| Service | `service:order-service` |
| Operation | `operation:product-service:GET:/products/{id}` |
| Queue | `queue:asb:commerce:payment-q` |
| Message | `message:PaymentRequested:v2` |
| Schema | `schema:PaymentRequested:v2` |

IDs must not depend on the local repository path. They must be stable across repeated imports and
able to merge multiple repositories without conflict.

## 5. Source and ingestion layer

### 5.1 Specification scanner

The scanner finds relevant files in configured directories, or via explicit source definitions.

```text
openapi.yaml | openapi.yml | openapi.json
asyncapi.yaml | asyncapi.yml | asyncapi.json
architecture.yaml
```

```python
class SpecificationSource(BaseModel):
    path: Path
    type: SpecificationType
    service_id: str
    revision: str | None = None
```

### 5.2 Ingestion pipeline

```text
scan
  -> parse
  -> source-level validate
  -> map to Canonical Model
  -> canonical validate
  -> reconcile / diff
  -> transactional graph write
```

An error before the graph write must never leave a partial import behind. A service artifact's
import either fully succeeds or is discarded.

## 6. OpenAPI adapter

The OpenAPI adapter extracts offered REST capabilities. For the PoC, the provider side is derived
automatically from the specification; the caller side is supplied via the Architecture Manifest.

### 6.1 Information to extract

- Service metadata.
- HTTP method and path.
- `operationId` and summary.
- Request body schema.
- Response schemas per status code.
- Reused component schemas.
- Optional security metadata as properties; no deep security analysis in the MVP.

### 6.2 Mapping

```text
ProductService
      |
   PROVIDES
      |
      v
GET /products/{id}
      |
      +-- REQUEST_SCHEMA --> ProductId
      `-- RESPONSE_SCHEMA -> Product
```

### 6.3 Example

```yaml
paths:
  /products/{id}:
    get:
      operationId: getProduct
      responses:
        "200":
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Product"
```

## 7. AsyncAPI queue adapter

The AsyncAPI adapter is scoped to queue-based communication. Queue and Message remain separate
entities, because queue properties, DLQ behavior, and message types represent distinct architecture
information.

### 7.1 Target model

```text
OrderService
    |
  SENDS
    v
 payment-q
    |
  CARRIES
    v
PaymentRequested
    |
 CONFORMS_TO
    v
PaymentRequestedSchema:v2

PaymentService
    |
RECEIVES_FROM
    v
 payment-q
```

### 7.2 Information to extract

- Queue/channel name and technical namespace information, where available.
- Send/receive direction of the operation.
- Message name and version.
- Payload schema and references.
- Protocol/binding metadata, where available.
- DLQ mapping, if present in the specification or in extension metadata.

### 7.3 Competing consumers

Multiple runtime instances of the same consumer service are not modeled as separate Service nodes
in the static PoC. The Canonical Model describes logical services. Pod/instance information belongs
in a later runtime layer.

### 7.4 DLQ

```text
payment-q -[:DEAD_LETTERS_TO]-> payment-dlq
```

## 8. Architecture Manifest

OpenAPI typically describes what a provider offers, but not which other service actually calls the
operation. For the narrow PoC, this gap is closed via a minimal `architecture.yaml`.

```yaml
service: order-service
calls:
  - service: product-service
    operationId: getProduct
  - service: customer-service
    operationId: getCustomer
```

The manifest may only contain information that isn't already reliably derivable from OpenAPI or
AsyncAPI. A later version could derive `CALLS` from OpenTelemetry, client code, or service
configuration instead.

## 9. Provenance and evidence

Provenance is introduced as a required concept from the PoC onward. The LLM may only state things
whose underlying graph facts have a traceable source.

```python
class Provenance(BaseModel):
    source_type: str       # OPENAPI | ASYNCAPI | MANIFEST
    source_file: str
    source_revision: str | None = None
    evidence_type: str = "DECLARED"
```

| Evidence type | Meaning | In PoC |
|---|---|---|
| DECLARED | Derived from specification/manifest. | Yes |
| OBSERVED | Observed at runtime, e.g. OpenTelemetry. | Later |
| INFERRED | Derived from documents/LLM/rules. | Later |

## 10. Validation

Validation is split into source validation and canonical validation. Source validation checks the
syntax and references of the input artifact; canonical validation checks architecture rules of the
normalized model.

| ID | Rule |
|---|---|
| V1 | Every service has a unique, stable ID. |
| V2 | Every REST operation belongs to exactly one provider service. |
| V3 | Every queue has a unique technical ID. |
| V4 | Every message has a unique ID. |
| V5 | Every `CALLS` entry references an existing operation. |
| V6 | A schema reference points to an existing schema. |
| V7 | A DLQ must not point to itself. |
| V8 | Relations only reference existing source/target entities. |
| V9 | A service import is atomic: no partial update on error. |

## 11. Neo4j graph model

### 11.1 Node labels

```text
Service
Operation
Queue
Message
Schema
```

### 11.2 Relations

| Relation | From -> To | Meaning |
|---|---|---|
| PROVIDES | Service -> Operation | REST provider. |
| CALLS | Service -> Operation | REST caller. |
| REQUEST_SCHEMA | Operation -> Schema | Request payload. |
| RESPONSE_SCHEMA | Operation -> Schema | Response payload. |
| SENDS | Service -> Queue | Asynchronous sender. |
| RECEIVES_FROM | Service -> Queue | Asynchronous consumer. |
| CARRIES | Queue -> Message | Message type on the queue. |
| CONFORMS_TO | Message -> Schema | Message payload schema. |
| DEAD_LETTERS_TO | Queue -> Queue | DLQ relationship. |

### 11.3 Example graph

```text
                         ProductService
                              |
                           PROVIDES
                              v
                       GET /products/{id}
                              ^
                            CALLS
                              |
                         OrderService
                              |
                            SENDS
                              v
                          payment-q
                           /      \
                    CARRIES      RECEIVES_FROM
                       |              ^
                       v              |
               PaymentRequested  PaymentService
                       |
                  CONFORMS_TO
                       v
             PaymentRequested:v2
```

### 11.4 Constraints and indexes

```cypher
CREATE CONSTRAINT service_id IF NOT EXISTS
FOR (s:Service) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT operation_id IF NOT EXISTS
FOR (o:Operation) REQUIRE o.id IS UNIQUE;

CREATE CONSTRAINT queue_id IF NOT EXISTS
FOR (q:Queue) REQUIRE q.id IS UNIQUE;

CREATE CONSTRAINT message_id IF NOT EXISTS
FOR (m:Message) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT schema_id IF NOT EXISTS
FOR (s:Schema) REQUIRE s.id IS UNIQUE;
```

## 12. Graph import and reconciliation

The graph importer writes the validated Canonical Model into Neo4j transactionally. Persistent
entities are handled with `MERGE`. The import must be idempotent.

### 12.1 Reference flow

```text
Canonical Model
      |
      v
Reconciliation / Diff
      |
      v
Neo4j Transaction
      |
      +-- MERGE nodes
      +-- MERGE current relations
      `-- remove/expire stale facts for imported service
```

### 12.2 PoC reimport strategy

For the first PoC, a per-service full reimport is acceptable: all `DECLARED` facts whose provenance
belongs to that service are replaced in one transaction. Globally shared entities such as Queues,
Messages, and Schemas are merged via stable IDs and only removed once no provenance references them
anymore.

## 13. Analysis engine

The standard analyses are deterministic and need no LLM. They're implemented as fixed, parameterized
Cypher queries.

### 13.1 A1 — Senders of a queue

```cypher
MATCH (s:Service)-[:SENDS]->(q:Queue {id:$queue_id})
RETURN s.id, s.name
ORDER BY s.name
```

### 13.2 A2 — Consumers of a queue

```cypher
MATCH (s:Service)-[:RECEIVES_FROM]->(q:Queue {id:$queue_id})
RETURN s.id, s.name
ORDER BY s.name
```

### 13.3 A3 — Queues with a sender but no consumer

```cypher
MATCH (q:Queue)
WHERE EXISTS { MATCH (:Service)-[:SENDS]->(q) }
  AND NOT EXISTS { MATCH (:Service)-[:RECEIVES_FROM]->(q) }
RETURN q.id, q.name
ORDER BY q.name
```

### 13.4 A4 — Consumer queues with no known sender

```cypher
MATCH (consumer:Service)-[:RECEIVES_FROM]->(q:Queue)
WHERE NOT EXISTS { MATCH (:Service)-[:SENDS]->(q) }
RETURN consumer.name, q.id, q.name
ORDER BY q.name, consumer.name
```

### 13.5 A5 — Mixed architecture blast radius

The blast radius follows both synchronous REST dependencies and asynchronous queue flows. Direct
service-to-service edges are derived from the primary facts; the primary facts themselves are kept.

```text
SYNC:
A -[:CALLS]-> Operation <-[:PROVIDES]- B

ASYNC:
A -[:SENDS]-> Queue <-[:RECEIVES_FROM]- B

Traversal:
Service -> {SYNC | ASYNC} -> Service -> ...
maxDepth = 5 (configurable)
```

### 13.6 Derived relations

`SYNC_DEPENDS_ON` and `ASYNC_FLOW_TO` could be materialized for faster visualization, but in the
PoC are better treated as a computed view. This keeps the graph free of redundant truths.

## 14. PoC REST API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/services` | List services. |
| GET | `/api/services/{serviceId}` | Service detail. |
| GET | `/api/queues` | List queues. |
| GET | `/api/queues/{queueId}` | Queue detail. |
| GET | `/api/messages` | List messages. |
| GET | `/api/messages/{messageId}` | Message detail. |
| GET | `/api/analysis/queues/{queueId}/senders` | A1. |
| GET | `/api/analysis/queues/{queueId}/consumers` | A2. |
| GET | `/api/analysis/queues/without-consumers` | A3. |
| GET | `/api/analysis/queues/without-senders` | A4. |
| GET | `/api/analysis/services/{serviceId}/blast-radius` | A5. |
| POST | `/api/import` | Import all configured sources. |
| POST | `/api/import/service/{serviceId}` | Service reimport. |
| POST | `/api/query` | Natural-language graph question. |

### 14.1 FastAPI skeleton

```python
from fastapi import FastAPI

app = FastAPI(title="Architecture Intelligence PoC")

@app.get("/api/services/{service_id}")
def get_service(service_id: str):
    return service_query.get_service(service_id)

@app.get("/api/analysis/services/{service_id}/blast-radius")
def blast_radius(service_id: str, depth: int = 5):
    return analysis_service.blast_radius(service_id, depth)
```

## 15. LLM query subsystem

The LLM component has a single function: map natural language onto safe graph queries and explain
the result. The graph remains the source of facts; the LLM is not the knowledge base.

```text
Question
   |
   v
Intent / Cypher Generation
   |
   v
Cypher Validator
   |
   v
Neo4j read-only
   |
   v
Rows + Provenance
   |
   v
LLM Explanation
```

### 15.1 Components

| Component | Responsibility |
|---|---|
| ArchitectureQuestionService | Orchestrates question, query, execution, and explanation. |
| CypherGenerator | Generates Cypher from the question + fixed graph schema. |
| CypherValidator | Checks allowlist, depth, and result limits. |
| ReadOnlyGraphExecutor | Runs the query via a read-only Neo4j user. |
| AnswerComposer | Composes the answer strictly from result rows and provenance. |

### 15.2 Permitted Cypher constructs

```text
MATCH
OPTIONAL MATCH
WHERE
WITH
RETURN
ORDER BY
LIMIT
```

### 15.3 Forbidden constructs

```text
CREATE
DELETE
DETACH DELETE
SET
REMOVE
MERGE
DROP
LOAD CSV
CALL
```

### 15.4 Additional limits

- Neo4j user with read-only access.
- Maximum traversal depth: 5 by default.
- Maximum result rows: 100 by default.
- Only permitted node labels and relation types.
- In the PoC, the generated Cypher statement is displayed for traceability.
- No direct tool access from the LLM to Neo4j credentials.

### 15.5 LLM provider abstraction

The implementation should use a provider adapter so the PoC isn't tied to a single model vendor. The
interface expects structured outputs for Cypher and answer composition; concrete provider
configuration belongs in environment/config.

## 16. Minimal UI

The UI isn't core to the PoC, but should make three use cases visible. It can be built as a small
React application or a very simple server-side/HTML interface.

### 16.1 Service Explorer

```text
OrderService

Provides REST
  POST /orders
  GET /orders/{id}

Calls REST
  ProductService / getProduct

Sends to queues
  payment-q

Receives from queues
  payment-result-q

Downstream
  ProductService (sync)
  PaymentService (async)
```

### 16.2 Queue Explorer

```text
payment-q

Protocol: AMQP
Senders: OrderService
Consumers: PaymentService
Messages: PaymentRequested:v2
DLQ: payment-dlq
```

### 16.3 Natural Language Query

The query page shows the user's question, the generated Cypher, the result rows, and the explained
answer. This transparency matters more in the PoC than an elaborate UI.

## 17. Configuration and operations

### 17.1 Example configuration

```yaml
architecture_intelligence:
  sources:
    directories:
      - ./repositories
  graph:
    uri: bolt://neo4j:7687
    database: neo4j
    max_traversal_depth: 5
  import:
    openapi: true
    asyncapi: true
    architecture_manifest: true
  llm:
    enabled: true
    max_result_rows: 100
```

### 17.2 Environment secrets

```text
NEO4J_USER
NEO4J_PASSWORD
LLM_API_KEY
```

Secrets must not be stored in the repository or in graph properties.

### 17.3 Docker Compose

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - neo4j
  neo4j:
    image: neo4j
    ports:
      - "7474:7474"
      - "7687:7687"
```

## 18. PoC logging and observability

Even though OpenTelemetry itself isn't yet an architecture source, the PoC needs enough technical
observability for import and query errors.

- Structured logging with `service_id`, `source_file`, `import_id`, and `duration_ms`.
- Metrics: import duration, number of nodes/relations per import, validation errors, LLM query
  count, Cypher validation rejects.
- Health endpoints for the app and Neo4j connectivity.
- No storage of sensitive prompt/credential data in logs.

```text
Imported service=order-service
openapi_operations=12
asyncapi_queues=4
messages=6
relations=31
duration_ms=423
warnings=0
```

## 19. Security

| Area | PoC requirement |
|---|---|
| Neo4j | Separate read-write user for import; separate read-only user for analyses/LLM. |
| LLM | No direct DB write access; Cypher must be validated. |
| Secrets | Environment/secret store only; never in source or the graph. |
| Files | Scanner limited to configured root directories; no arbitrary path traversal. |
| API | PoC runs local or internal; production-grade authentication is a later stage. |
| Prompt injection | LLM receives the graph schema and query results, not uncontrolled documents in the MVP. |

## 20. Tests

### 20.1 Unit tests

- Canonical ID generator.
- OpenAPI adapter.
- AsyncAPI queue adapter.
- Architecture Manifest adapter.
- Canonical validation.
- Provenance mapping.
- Cypher validator.
- Blast radius traversal logic.

### 20.2 Integration tests

Neo4j is started via Testcontainers. A test imports specifications, runs Cypher, and checks nodes,
relations, and analyses.

```text
Specification fixtures
       |
       v
Python Importer
       |
       v
Neo4j Testcontainer
       |
       v
Cypher assertions
```

### 20.3 Test landscape

| Service | REST | Queue |
|---|---|---|
| OrderService | calls ProductService | sends payment-q |
| ProductService | provides getProduct | - |
| PaymentService | optional external REST call | receives payment-q; sends invoice-q |
| InvoiceService | - | receives invoice-q |

Additional fixtures: `unused-q` with a sender but no consumer, and `unknown-producer-q` with a
consumer but no known sender.

## 21. Acceptance criteria

- **AC1**: OpenAPI files from multiple services are imported reproducibly.
- **AC2**: AsyncAPI files with queue communication are imported reproducibly.
- **AC3**: REST providers are correctly recognized.
- **AC4**: REST callers are correctly connected via the Architecture Manifest.
- **AC5**: Queue senders and consumers are correctly recognized.
- **AC6**: Queue, Message, and Schema are correctly linked as separate entities.
- **AC7**: DLQ relationships are represented.
- **AC8**: Repeated imports produce no duplicates.
- **AC9**: The five standard analyses produce deterministic results.
- **AC10**: The blast radius combines synchronous and asynchronous paths.
- **AC11**: A natural-language question is translated into a safe, read-only Cypher query.
- **AC12**: The LLM cannot modify Neo4j.
- **AC13**: Essential relationships have traceable provenance.
- **AC14**: A failed import produces no inconsistent partial state.
- **AC15**: A developer can understand service and queue relationships without manual repository
  searching.

## 22. Repository structure

```text
architecture-intelligence-poc/
|-- pyproject.toml
|-- Dockerfile
|-- docker-compose.yml
|-- README.md
|-- app/
|   |-- main.py
|   |-- settings.py
|   |-- canonical/
|   |   |-- model.py
|   |   `-- ids.py
|   |-- ingestion/
|   |   |-- scanner.py
|   |   |-- openapi_adapter.py
|   |   |-- asyncapi_adapter.py
|   |   `-- manifest_adapter.py
|   |-- provenance/
|   |   `-- model.py
|   |-- validation/
|   |   |-- source_validation.py
|   |   `-- canonical_validation.py
|   |-- graph/
|   |   |-- repository.py
|   |   |-- importer.py
|   |   |-- reconciliation.py
|   |   `-- schema.py
|   |-- analysis/
|   |   |-- queues.py
|   |   |-- dependencies.py
|   |   `-- blast_radius.py
|   |-- ai/
|   |   |-- question_service.py
|   |   |-- provider.py
|   |   |-- cypher_generator.py
|   |   |-- cypher_validator.py
|   |   `-- answer_composer.py
|   `-- api/
|       |-- services.py
|       |-- queues.py
|       |-- messages.py
|       |-- analysis.py
|       |-- import_api.py
|       `-- query.py
|-- tests/
|   |-- unit/
|   |-- integration/
|   `-- fixtures/
`-- examples/
    |-- order-service/
    |-- product-service/
    |-- payment-service/
    `-- invoice-service/
```

## 23. Implementation plan

| Iteration | Content | Exit criterion |
|---|---|---|
| 1 | Canonical Model + stable IDs + fixtures | Models validate the example architecture. |
| 2 | OpenAPI adapter | REST operations/schemas are correctly produced. |
| 3 | AsyncAPI queue adapter | Queues/messages/senders/consumers are correctly produced. |
| 4 | Neo4j schema + importer | Idempotent graph import. |
| 5 | Architecture Manifest | REST callers are connected in the graph. |
| 6 | 5 standard analyses | All Cypher analyses pass integration tests. |
| 7 | FastAPI + minimal UI | Service/queue/analysis is visible. |
| 8 | LLM query + validator | Natural-language question -> read-only Cypher -> answer. |
| 9 | PoC review | Value assessed against real specifications. |

### 23.1 Measuring PoC success

1. The platform answers architecture questions faster than manual repository research.
2. The graph discovers at least some non-obvious queue/service dependencies or documentation gaps.
3. The five standard analyses are reproducible without an LLM.
4. The LLM improves usability without replacing the source of facts.
5. The Canonical Model can later absorb OpenTelemetry as a new source without reworking the
   OpenAPI/AsyncAPI adapters.

## 24. Extension beyond the PoC

The first recommended extension is OpenTelemetry. It allows the declared architecture from
OpenAPI/AsyncAPI to be compared against the observed runtime architecture.

```text
DECLARED
OpenAPI + AsyncAPI + Manifest
          vs.
OBSERVED
OpenTelemetry
```

### 24.1 New analyses

- Observed − Declared: real but undocumented dependencies.
- Declared − Observed: declared but potentially stale or unused dependencies.
- Causal end-to-end flows across REST and queues.
- Runtime-based blast radius.
- Comparison of logical and physical locality after a later Kubernetes/cloud integration.

### 24.2 A later Architecture Intelligence Platform

```text
Static Architecture Graph
       +
Observed Runtime Graph
       +
Document / Vector Knowledge
       +
LLM Query and Wiki
       =
Architecture Intelligence Platform
```

Promise Theory and Semantic Spacetime could later be explored as a semantic interpretation layer on
top of the technically established graph model. For the PoC, they deliberately stay outside the
implemented core model.

## Appendix A — Dependency semantics

### A.1 Synchronous dependency

```text
A -[:CALLS]-> O <-[:PROVIDES]- B
=> A synchronously depends on B through operation O
```

### A.2 Asynchronous flow

```text
A -[:SENDS]-> Q <-[:RECEIVES_FROM]- B
=> message flow A -> Q -> B
```

With multiple instances of B, the graph still only describes the logical consumer service B.
Competing-consumer instances are only modeled in a later runtime/deployment extension.

### A.3 Queue and Message

```text
Q -[:CARRIES]-> M -[:CONFORMS_TO]-> S
```

This separation is required so that the queue's transport parameters and the message's semantic
payload properties can be analyzed and versioned independently.

## Appendix B — Design decisions

| Decision | Rationale |
|---|---|
| Python over Java | The PoC's focus is on parsing, transformation, graph analysis, and LLM integration. |
| FastAPI over microservice-splitting | A modular monolith reduces operational and integration overhead. |
| Pydantic Canonical Model | Clear validation and technology decoupling. |
| Neo4j property graph | Direct modeling of typed relationships and Cypher analyses. |
| Queue as its own entity | Buffering, DLQ, competing consumers, and queue-specific properties are architecturally relevant. |
| Message separate from Queue | Semantics/schema and transport are not mixed together. |
| Architecture Manifest for REST callers | OpenAPI alone typically only knows providers, not callers. |
| LLM read-only only | Facts stay deterministic and auditable. |
| Provenance from day one | Later LLM answers must be traceable back to sources. |
| OpenTelemetry only after the PoC | Prove static value first, then DECLARED vs OBSERVED. |

*End of specification.*
