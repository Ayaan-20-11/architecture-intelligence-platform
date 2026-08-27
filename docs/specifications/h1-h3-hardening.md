# Specification – Architecture Intelligence Platform
## Core Hardening Iteration: Evidence, Semantic Validation & Deterministic Intent Routing

**Version:** 0.2  
**Status:** Implementation Specification  
**Basis:** PoC Iterations 0–9  
**Technology:** Python 3.13, FastAPI, Pydantic, Neo4j  
**Scope:** Further development of the existing PoC without Vector DB, Wiki, GraphRAG, or OpenTelemetry

---

## 1. Starting Point

The existing PoC has confirmed the core hypothesis:

```text
OpenAPI + AsyncAPI + ArchitectureManifest
→ CanonicalModel
→ Neo4j
→ ArchitectureAnalysis
```

The implementation currently has 143 unit tests and 55 Neo4j/Testcontainers integration tests; a total of 198 tests pass successfully.

Of AC1–AC15, 14 criteria are fully met. AC13 is partially met: provenance is generated in the adapters, but it is not persisted as queryable evidence in the Neo4j knowledge graph.

In addition, a live test revealed a second important limitation: the LLM generated syntactically valid and safe Cypher, but semantically misinterpreted the direction of the `SENDS` relation. As expected, the existing security validator could not detect this.

This iteration therefore addresses three requirements:

\[
\boxed{
\begin{aligned}
H1 &: \text{Evidence / Provenance}\\
H2 &: \text{Semantic Query Validation}\\
H3 &: \text{Deterministic Intent Routing}
\end{aligned}}
\]

---

## 2. Goals of the Iteration

The next iteration is intended to **harden** the existing Architecture Knowledge Graph before further AI components are introduced.

The target pipeline is:

```text
                       Architecture Sources
                 OpenAPI / AsyncAPI / Manifest
                              |
                              v
                      Canonical Model
                              |
                              v
                  +----------------------+
                  | Architecture Graph   |
                  | + Evidence           |
                  +----------+-----------+
                             |
            +----------------+----------------+
            |                                 |
            v                                 v
    Deterministic Analysis             NL Query Interface
        A1 ... A5                              |
            ^                                  v
            |                           Intent Router
            |                          /             \
            +-------------------------+               \
                           Known Intent                Unknown Intent
                                |                          |
                                v                          v
                       Deterministic Query              LLM Cypher
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

The three core goals are:

### G1 – Evidence

Every relevant architecture claim must be able to traceably answer:

> Where does the platform know this from?

### G2 – Semantic Query Safety

Not only dangerous Cypher, but also structurally incorrect Cypher should be detected.

### G3 – Determinism before AI

Questions that correspond to a known architecture query must not be unnecessarily answered via generated Cypher.

---

## 3. Out of Scope

The following features are explicitly **not** implemented:

- OpenTelemetry
- `OBSERVED` Runtime Facts
- Vector Database
- GraphRAG
- Wiki
- ADR-RAG
- Source Code RAG
- autonomous agents
- generic ontology
- OWL / RDF / SHACL
- additional analyses A6+
- automatic REST caller detection

This keeps the scope at:

\[
\boxed{
Declared\ Architecture
+
Evidence
+
Deterministic\ Reasoning
+
Controlled\ NL\ Interface
}
\]

---

# 4. Subproject H1 – Provenance / Evidence

## 4.1 Problem

The existing canonical layer already generates:

```text
source_type
source_file
source_revision
evidence_type
```

However, this provenance data is currently not stored in a form that allows a graph query to determine which specific specification an architecture relationship originates from. The importer only stores `sources[]` for reimport purposes.

That is not sufficient for an Architecture Knowledge Graph.

---

## 4.2 Architectural Principle

Going forward, an architecture fact is understood as a combination of

\[
\boxed{
Fact + Evidence
}
\]

.

Example:

\[
OrderService
\xrightarrow{SENDS}
paymentQueue
\]

is the fact.

The evidence is:

```text
sourceType       ASYNCAPI
sourceFile       order-service/asyncapi.yaml
sourceRevision   abc123
evidenceType     DECLARED
```

---

## 4.3 Evidence Model

Canonical Model:

```python
from enum import StrEnum
from pydantic import BaseModel


class SourceType(StrEnum):
    OPENAPI = "OPENAPI"
    ASYNCAPI = "ASYNCAPI"
    MANIFEST = "MANIFEST"


class EvidenceType(StrEnum):
    DECLARED = "DECLARED"


class Evidence(BaseModel):
    id: str
    source_type: SourceType
    source_file: str
    source_revision: str | None = None
    evidence_type: EvidenceType = EvidenceType.DECLARED
```

An Evidence has a stable ID.

For example:

```text
evidence:asyncapi:order-service:abc123
```

---

## 4.4 Graph Model

A new node type is introduced:

```text
(:Evidence)
```

with:

```text
id
sourceType
sourceFile
sourceRevision
evidenceType
```

Example:

```text
(:Evidence {
    id: "evidence:asyncapi:order-service:abc123",
    sourceType: "ASYNCAPI",
    sourceFile: "order-service/asyncapi.yaml",
    sourceRevision: "abc123",
    evidenceType: "DECLARED"
})
```

---

## 4.5 Evidence for Relationships

The most important provenance concerns not primarily nodes, but statements.

Example:

```text
OrderService -[:SENDS]-> payment-q
```

This relation should receive at least the following property:

```text
evidenceIds
```

Example:

```text
OrderService
     |
     | SENDS
     | evidenceIds = [
     |   "evidence:asyncapi:order-service:abc123"
     | ]
     v
payment-q
```

This allows multiple sources to confirm the same fact.

---

## 4.6 Why Not Model Evidence Exclusively as Relationship Properties?

In the long run, questions like the following must be possible:

> Show all facts from a specific AsyncAPI version.

or:

> Which architecture information originates from manifests?

A dedicated `Evidence` node allows:

```cypher
MATCH (e:Evidence {sourceType:'ASYNCAPI'})
RETURN e
```

and enables future extensions with:

```text
OpenTelemetry
ADR
Source Code
Kubernetes
Manual Assertion
```

Therefore:

\[
Evidence = FirstClassEntity.
\]

---

## 4.7 Optional Future Statement Model

Not strictly required for this iteration, but the model should remain compatible with it:

```text
(:ArchitectureFact)
```

for example:

```text
Fact
  subject   = OrderService
  predicate = SENDS
  object    = payment-q
```

with:

```text
Fact -[:SUPPORTED_BY]-> Evidence
```

The current PoC may, for now, remain at relationships + `evidenceIds`.

---

## 4.8 Import Behavior

During import:

```text
Adapter
   |
   v
Canonical Entity / Relation
   +
Evidence
   |
   v
Graph Importer
```

The GraphImporter must:

1. persist `Evidence` with `MERGE`.
2. create the architecture relation with `MERGE`,
3. add evidence IDs deduplicated,
4. remove stale evidence on reimport.

---

## 4.9 Reconciliation

When revision

```text
abc123
```

is replaced by

```text
def456
```

an obsolete evidence must not permanently legitimize a fact that no longer exists.

Therefore:

```text
import source
     |
     v
determine current evidence
     |
     v
remove stale evidence references
     |
     v
remove unsupported facts
```

Rule:

\[
EvidenceSet(F)=\emptyset
\Rightarrow
delete(F)
\]

provided the fact was not otherwise created administratively.

---

## 4.10 Evidence API

New REST endpoints:

```text
GET /api/evidence
```

```text
GET /api/evidence/{evidenceId}
```

additionally:

```text
GET /api/services/{serviceId}/evidence
```

```text
GET /api/queues/{queueId}/evidence
```

Optionally more important:

```text
GET /api/relations/{relationId}/evidence
```

should relations later receive their own IDs.

---

## 4.11 Service Explorer

The UI should, for example, display:

```text
OrderService

Sends to

payment-q
    Source:
        order-service/asyncapi.yaml
    Revision:
        abc123
    Evidence:
        DECLARED
```

This makes visible for the first time:

\[
Architecture\ Claim
\rightarrow
Source.
\]

---

## 4.12 Acceptance Criteria H1

**AC-H1-1**  
All adapters generate evidence.

**AC-H1-2**  
Evidence is persisted as an `Evidence` node in Neo4j.

**AC-H1-3**  
Essential architecture relations possess at least one evidence reference.

**AC-H1-4**  
Multiple imports do not create duplicated evidence.

**AC-H1-5**  
An outdated revision is correctly reconciled.

**AC-H1-6**  
An API query can determine the source and revision for a fact.

**AC-H1-7**  
AC13 of the original PoC is then considered fully met.

---

# 5. Subproject H2 – Semantic Query Validator

## 5.1 Problem Statement

The current CypherValidator answers:

\[
IsReadOnly(q)?
\]

but not:

\[
IsSemanticallyValid(q,GSchema)?
\]

In the live test, for example:

```text
Queue -[:SENDS]-> Service
```

was permitted, even though the actual model only defines

```text
Service -[:SENDS]-> Queue
```

---

## 5.2 Goal

A new Semantic Validator should check:

\[
domain(Relation)
\]

and

\[
range(Relation).
\]

For example:

\[
domain(SENDS)=Service
\]

\[
range(SENDS)=Queue.
\]

This makes

\[
Service\xrightarrow{SENDS}Queue
\]

valid and

\[
Queue\xrightarrow{SENDS}Service
\]

invalid.

---

## 5.3 Graph Schema Registry

New component:

```text
app/
  graph_schema/
      model.py
      registry.py
```

Canonical Definition:

```python
class RelationDefinition(BaseModel):
    name: str
    source_labels: set[str]
    target_labels: set[str]
```

Registry:

```python
RELATIONS = {
    "PROVIDES": RelationDefinition(
        name="PROVIDES",
        source_labels={"Service"},
        target_labels={"Operation"},
    ),

    "CALLS": RelationDefinition(
        name="CALLS",
        source_labels={"Service"},
        target_labels={"Operation"},
    ),

    "SENDS": RelationDefinition(
        name="SENDS",
        source_labels={"Service"},
        target_labels={"Queue"},
    ),

    "RECEIVES_FROM": RelationDefinition(
        name="RECEIVES_FROM",
        source_labels={"Service"},
        target_labels={"Queue"},
    ),

    "CARRIES": RelationDefinition(
        name="CARRIES",
        source_labels={"Queue"},
        target_labels={"Message"},
    ),

    "CONFORMS_TO": RelationDefinition(
        name="CONFORMS_TO",
        source_labels={"Message"},
        target_labels={"Schema"},
    ),

    "REQUEST_SCHEMA": RelationDefinition(
        name="REQUEST_SCHEMA",
        source_labels={"Operation"},
        target_labels={"Schema"},
    ),

    "RESPONSE_SCHEMA": RelationDefinition(
        name="RESPONSE_SCHEMA",
        source_labels={"Operation"},
        target_labels={"Schema"},
    ),

    "DEAD_LETTERS_TO": RelationDefinition(
        name="DEAD_LETTERS_TO",
        source_labels={"Queue"},
        target_labels={"Queue"},
    ),
}
```

---

## 5.4 Validation Pipeline

New pipeline:

```text
Generated Cypher
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

The existing validator remains in place.

The new validator does **not** replace it.

---

## 5.5 Checking

Valid example:

```cypher
MATCH (s:Service)-[:SENDS]->(q:Queue)
RETURN s, q
```

Result:

```text
VALID
```

Invalid example:

```cypher
MATCH (q:Queue)-[:SENDS]->(s:Service)
RETURN q
```

Result:

```text
SemanticValidationError:

Relation SENDS expects

Service -> Queue

but query contains

Queue -> Service
```

---

## 5.6 Additional Semantic Checks

In scope:

### Relation exists

```text
FOO_BAR
```

must be rejected.

### Source type valid

```text
Queue -[:PROVIDES]-> Operation
```

invalid.

### Target type valid

```text
Service -[:SENDS]-> Message
```

invalid.

### Direction valid

```text
Queue -[:SENDS]-> Service
```

invalid.

---

## 5.7 Not Yet in Scope

Not checked:

- the domain meaning of a question,
- complex Cypher equivalence,
- correctness of `WHERE` logic,
- aggregation semantics,
- optimization,
- completeness of an answer.

This means the validator guarantees:

\[
SchemaCorrect(q)
\]

not:

\[
AnswerCorrect(q,Question).
\]

---

## 5.8 Parser

The previous hand-written security validator is deliberately used only as an allow-/blocklist.

For the Semantic Validator, the implementation should be structured so that a Cypher AST parser can be integrated later.

For this iteration, two variants are permitted:

**Variant A:** a restricted parser implementation for the subset of Cypher permitted for the LLM.

**Variant B:** an established Cypher parser, provided Python integration is practical.

The architecture must not depend on regex-specific behavior.

---

## 5.9 Semantic Validator API

Primarily internal:

```python
class SemanticQueryValidator:

    def validate(self, cypher: str) -> None:
        ...
```

Optional debug:

```text
POST /api/debug/validate-cypher
```

development mode only.

---

## 5.10 Error Behavior

For a semantically incorrect query:

```http
HTTP 422
```

Response:

```json
{
  "code": "SEMANTIC_QUERY_INVALID",
  "message": "Relation SENDS expects Service -> Queue",
  "relation": "SENDS",
  "expectedSource": ["Service"],
  "expectedTarget": ["Queue"]
}
```

---

## 5.11 Tests H2

At minimum:

```text
Service SENDS Queue              -> valid
Queue SENDS Service              -> invalid

Service RECEIVES_FROM Queue      -> valid
Queue RECEIVES_FROM Service      -> invalid

Service PROVIDES Operation       -> valid
Operation PROVIDES Service       -> invalid

Service CALLS Operation          -> valid

Queue CARRIES Message            -> valid
Message CARRIES Queue            -> invalid

Message CONFORMS_TO Schema       -> valid

Queue DEAD_LETTERS_TO Queue      -> valid
```

Additionally:

- unknown relation
- missing labels
- alias usage
- multiple MATCH blocks
- OPTIONAL MATCH
- variable-length traversal, where permitted.

---

## 5.12 Acceptance Criteria H2

**AC-H2-1**  
All approved relation types have domain/range definitions.

**AC-H2-2**  
The live-test error `Queue -[:SENDS]-> Service` is automatically detected.

**AC-H2-3**  
Valid A1–A5 Cypher queries remain permitted.

**AC-H2-4**  
Unknown relation types are rejected.

**AC-H2-5**  
The security validator and semantic validator are tested separately.

**AC-H2-6**  
No semantically invalid query reaches Neo4j.

---

# 6. Subproject H3 – Intent Router

## 6.1 Problem Statement

The system already has five reliable analyses:

```text
A1 Queue Senders
A2 Queue Consumers
A3 Queues without Consumers
A4 Queues without Senders
A5 Blast Radius
```

These are reproducible and completely independent of the LLM.

It is therefore unnecessary and riskier to have new Cypher generated for equivalent natural-language questions.

---

## 6.2 Architectural Principle

\[
\boxed{
KnownIntent
\rightarrow
DeterministicAnalysis
}
\]

and only:

\[
\boxed{
UnknownIntent
\rightarrow
LLMGeneratedCypher
}
\]

---

## 6.3 New Pipeline

```text
Natural Language Question
          |
          v
     Intent Router
       /      \
      /        \
Known Intent    UNKNOWN
    |              |
    v              v
A1–A5 Analysis     LLM
    |              |
    |              v
    |       Security Validator
    |              |
    |              v
    |       Semantic Validator
    |              |
    +--------+-----+
             |
             v
      Result Formatter
             |
             v
        User Response
```

---

## 6.4 Intent Types

```python
class ArchitectureIntent(StrEnum):

    QUEUE_SENDERS = "A1_QUEUE_SENDERS"

    QUEUE_CONSUMERS = "A2_QUEUE_CONSUMERS"

    QUEUES_WITHOUT_CONSUMERS = "A3_QUEUES_WITHOUT_CONSUMERS"

    QUEUES_WITHOUT_SENDERS = "A4_QUEUES_WITHOUT_SENDERS"

    BLAST_RADIUS = "A5_BLAST_RADIUS"

    UNKNOWN = "UNKNOWN"
```

---

## 6.5 Intent Result

```python
class IntentResult(BaseModel):
    intent: ArchitectureIntent
    confidence: float
    parameters: dict[str, str | int]
```

Examples:

```json
{
  "intent": "A1_QUEUE_SENDERS",
  "confidence": 0.99,
  "parameters": {
    "queue": "payment-q"
  }
}
```

or:

```json
{
  "intent": "A5_BLAST_RADIUS",
  "confidence": 0.96,
  "parameters": {
    "service": "OrderService",
    "depth": 5
  }
}
```

---

## 6.6 Intent Recognition

For A1–A5, **no second generative LLM is introduced as a prerequisite**.

The router can initially operate with:

1. rule-based patterns,
2. normalized entity extraction,
3. optional LLM classification only as a fallback.

Examples:

```text
"Who sends to payment-q?"
```

→ A1

```text
"Which services send to payment-q?"
```

→ A1

```text
"Who consumes from payment-q?"
```

→ A2

```text
"Which queues have no consumer?"
```

→ A3

```text
"Queues with a consumer but no sender"
```

→ A4

```text
"Which services depend on OrderService?"
```

→ A5

---

## 6.7 Deterministic Query Registry

New component:

```text
analysis/
    registry.py
```

Example:

```python
INTENT_HANDLERS = {
    ArchitectureIntent.QUEUE_SENDERS:
        QueueProducerAnalysis,

    ArchitectureIntent.QUEUE_CONSUMERS:
        QueueConsumerAnalysis,

    ArchitectureIntent.QUEUES_WITHOUT_CONSUMERS:
        QueueWithoutConsumerAnalysis,

    ArchitectureIntent.QUEUES_WITHOUT_SENDERS:
        QueueWithoutSenderAnalysis,

    ArchitectureIntent.BLAST_RADIUS:
        BlastRadiusAnalysis,
}
```

The Intent Router itself generates **no Cypher**.

It selects an existing, tested analysis.

---

## 6.8 Confidence Threshold

Configuration:

```yaml
intent-router:
  deterministic-threshold: 0.90
```

If:

\[
confidence\ge0.90
\]

the deterministic analysis is executed.

Otherwise:

```text
UNKNOWN
```

and control is handed off to LLM query generation.

---

## 6.9 Ambiguity

Example:

> What depends on payment?

could mean:

- Queue `payment-q`,
- Service `PaymentService`,
- Message `PaymentRequested`.

The router must not guess here.

Result:

```text
UNKNOWN
```

or:

```text
AMBIGUOUS
```

Optional future extension:

```python
AMBIGUOUS = "AMBIGUOUS"
```

---

## 6.10 Entity Resolution

The router needs access to known graph entities:

```text
Service
Queue
Message
```

Example:

```text
payment q
```

should be normalized to:

```text
payment-q
```

if exactly one unambiguous queue exists.

Not permitted:

unsafe automatic assignment when there are multiple matches.

---

## 6.11 Query Response

The response should additionally contain:

```json
{
  "executionMode": "DETERMINISTIC",
  "intent": "A4_QUEUES_WITHOUT_SENDERS",
  "result": [
    {
      "queue": "unknown-producer-q"
    }
  ]
}
```

For the LLM:

```json
{
  "executionMode": "LLM",
  "generatedCypher": "...",
  "result": [...]
}
```

This makes it always visible to users and tests:

\[
\text{How was the answer generated?}
\]

---

## 6.12 UI

The query page shows:

```text
Question
────────────────────────────────
Which queues have no known sender?


Execution
────────────────────────────────
Deterministic Analysis A4


Result
────────────────────────────────
unknown-producer-q
```

For a free-form query:

```text
Execution
────────────────────────────────
LLM-generated Cypher

Semantic validation: passed
```

---

## 6.13 The Concrete Live Test Must Subsequently Behave Differently

The previously problematic question:

> What queues have a consumer but no known sender?

should henceforth result in:

```text
Intent:
A4_QUEUES_WITHOUT_SENDERS
```

and directly execute the existing analysis.

This means no generated Cypher is needed at all anymore.

Expected result:

```text
unknown-producer-q
```

---

## 6.14 Acceptance Criteria H3

**AC-H3-1**  
All A1–A5 analyses have an intent.

**AC-H3-2**  
German- and English-language standard phrasings are recognized.

**AC-H3-3**  
Known intents do not generate LLM Cypher.

**AC-H3-4**  
A1–A5 return the same result via `/api/query` as their deterministic REST endpoints.

**AC-H3-5**  
Uncertain questions are treated as `UNKNOWN`.

**AC-H3-6**  
The execution mode field shows `DETERMINISTIC` or `LLM`.

**AC-H3-7**  
The A4 error observed in Iteration 9 is no longer reproducible via the normal NL endpoint.

---

# 7. Interaction of the Three Extensions

The new system then has three levels of safety/trust.

## Level 1 – Evidence

\[
\boxed{
Where\ did\ this\ fact\ come\ from?
}
\]

## Level 2 – Deterministic Semantics

\[
\boxed{
Is\ there\ already\ a\ trusted\ analysis?
}
\]

## Level 3 – Controlled Generative Query

\[
\boxed{
If\ AI\ generates\ a\ query,\ is\ it
syntactically,\ safely\ and\ structurally\ valid?
}
\]

Overall:

```text
Question
   |
   v
Intent Router
   |
   +------ known ------> Deterministic Analysis
   |
   +------ unknown ----> LLM
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

All resulting facts, in turn, possess:

```text
Evidence
```

---

# 8. New Python Package Structure

```text
app/
│
├── canonical/
│   ├── model.py
│   └── ids.py
│
├── evidence/
│   ├── model.py
│   ├── repository.py
│   └── service.py
│
├── graph_schema/
│   ├── model.py
│   └── registry.py
│
├── validation/
│   ├── canonical_validator.py
│   ├── cypher_security_validator.py
│   └── semantic_query_validator.py
│
├── intent/
│   ├── model.py
│   ├── router.py
│   ├── patterns.py
│   └── entity_resolver.py
│
├── analysis/
│   ├── registry.py
│   ├── queue_senders.py
│   ├── queue_consumers.py
│   ├── orphan_queues.py
│   ├── missing_senders.py
│   └── blast_radius.py
│
├── ai/
│   ├── question_service.py
│   ├── cypher_generator.py
│   └── answer_generator.py
│
└── graph/
    ├── importer.py
    └── repository.py
```

---

# 9. Revised QuestionService

Conceptually:

```python
def ask(question: str) -> ArchitectureAnswer:

    intent = intent_router.classify(question)

    if intent.is_deterministic:
        rows = analysis_registry.execute(
            intent.intent,
            intent.parameters
        )

        return answer_from_deterministic_analysis(
            question,
            intent,
            rows
        )

    cypher = llm.generate_cypher(question)

    security_validator.validate(cypher)

    semantic_validator.validate(cypher)

    rows = graph.execute_readonly(cypher)

    return llm.explain(
        question=question,
        rows=rows
    )
```

The LLM is now truly:

\[
fallback
\]

and not the default path.

---

# 10. Test Strategy

The existing test suite must not be replaced.

New tests are added.

## Unit

### Evidence

- ID generation
- Merge
- Reconciliation
- Multiple sources

### Semantic Validator

at least 30 positive/negative cases.

### Intent Router

at least:

- 5 intents
- DE/EN
- synonyms
- entity extraction
- ambiguity
- UNKNOWN

---

## Integration

With real Neo4j:

```text
Import
   |
Evidence persisted
   |
Query
```

as well as:

```text
NL Question
   |
Intent Router
   |
A1-A5
   |
exact expected results
```

---

## Regression Test of the Live Error

Explicit test:

```python
question = (
    "What queues have a consumer "
    "but no known sender?"
)
```

Expectation:

```text
executionMode = DETERMINISTIC
intent        = A4_QUEUES_WITHOUT_SENDERS
result        = ["unknown-producer-q"]
```

`generate_cypher()` must **not** be called.

---

# 11. New Acceptance Criteria

The iteration is considered complete when:

| ID | Criterion |
|---|---|
| H1.1 | Provenance is queryable in Neo4j |
| H1.2 | Every essential relation possesses evidence |
| H1.3 | Evidence revision changes are reconciled |
| H1.4 | the original AC13 is fully met |
| H2.1 | Domain/range of all graph relations defined |
| H2.2 | incorrect relation direction is detected |
| H2.3 | unknown relations are blocked |
| H2.4 | semantically invalid Cypher does not reach Neo4j |
| H3.1 | A1–A5 possess deterministic intents |
| H3.2 | known questions bypass LLM query generation |
| H3.3 | UNKNOWN continues to use controlled LLM Cypher |
| H3.4 | `/api/query` shows execution mode |
| H3.5 | the live A4 regression test yields the correct result |
| H3.6 | the existing 198 tests remain green |

---

# 12. Recommended Implementation Order

The three points are not implemented in parallel.

## Iteration 10A – Evidence

```text
Canonical Provenance
      ↓
Evidence Nodes
      ↓
Relationship Evidence
      ↓
Reconciliation
      ↓
Evidence API/UI
```

Goal:

\[
AC13=\checkmark
\]

## Iteration 10B – Graph Schema + Semantic Validator

```text
Schema Registry
     ↓
Cypher structure extraction
     ↓
Domain/Range checking
     ↓
Integration into QuestionService
```

Goal:

The incorrect `SENDS` path observed in Iteration 9 is blocked.

## Iteration 10C – Intent Router

```text
A1-A5 Intent Model
     ↓
Patterns + Entity Resolution
     ↓
Deterministic Query Registry
     ↓
QuestionService routing
```

Goal:

The problematic query is, under normal circumstances, no longer generated by the LLM at all.

---

# 13. Definition of Done

Upon completion, the architecture query pipeline is:

\[
\boxed{
Question
\rightarrow
Intent
\rightarrow
\begin{cases}
DeterministicAnalysis\\
LLMQuery
\end{cases}
}
\]

additionally for LLM queries:

\[
\boxed{
Cypher
\rightarrow
SecurityValidation
\rightarrow
SemanticValidation
\rightarrow
Neo4j
}
\]

and for all architecture information:

\[
\boxed{
Fact
\rightarrow
Evidence
\rightarrow
Source
}
\]

This qualitatively transforms the platform from:

\[
\text{Architecture Graph + AI Query}
\]

to:

\[
\boxed{
\text{Evidence-backed Architecture Knowledge Graph}
+
\text{Deterministic Reasoning}
+
\text{Semantically constrained AI}
}
\]

This is the stable foundation before OpenTelemetry, and with it `OBSERVED` architecture facts, are added.
