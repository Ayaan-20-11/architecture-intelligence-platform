# Specification – Architecture Intelligence Platform
## Core Hardening Iteration: Evidence, Semantic Validation & Deterministic Intent Routing

**Version:** 0.2  
**Status:** Implementation Specification  
**Basis:** PoC Iterations 0–9  
**Technologie:** Python 3.13, FastAPI, Pydantic, Neo4j  
**Scope:** Weiterentwicklung des bestehenden PoC ohne Vector DB, Wiki, GraphRAG oder OpenTelemetry

---

## 1. Ausgangslage

Der bestehende PoC hat die Kernhypothese bestätigt:

```text
OpenAPI + AsyncAPI + ArchitectureManifest
→ CanonicalModel
→ Neo4j
→ ArchitectureAnalysis
```

Die Implementierung verfügt derzeit über 143 Unit Tests und 55 Neo4j/Testcontainers-Integrationstests; insgesamt laufen 198 Tests erfolgreich.

Von AC1–AC15 sind 14 Kriterien vollständig erfüllt. AC13 ist teilweise erfüllt: Provenance wird in den Adaptern erzeugt, jedoch nicht als abfragbare Evidenz im Neo4j Knowledge Graph persistiert.

Außerdem zeigte ein Live-Test eine zweite wichtige Grenze: Das LLM erzeugte syntaktisch gültiges und sicheres Cypher, interpretierte jedoch die Richtung der Relation `SENDS` semantisch falsch. Der vorhandene Security Validator konnte dies erwartungsgemäß nicht erkennen.

Diese Iteration adressiert deshalb drei Anforderungen:

\[
\boxed{
\begin{aligned}
H1 &: \text{Evidence / Provenance}\\
H2 &: \text{Semantic Query Validation}\\
H3 &: \text{Deterministic Intent Routing}
\end{aligned}}
\]

---

## 2. Ziele der Iteration

Die nächste Iteration soll den bestehenden Architecture Knowledge Graph **härten**, bevor weitere AI-Komponenten eingeführt werden.

Die Zielpipeline lautet:

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

Die drei Kernziele sind:

### G1 – Evidence

Jede relevante Architekturbehauptung muss nachvollziehbar beantworten können:

> Woher weiß die Plattform das?

### G2 – Semantic Query Safety

Nicht nur gefährliches Cypher, sondern auch strukturell falsches Cypher soll erkannt werden.

### G3 – Determinism before AI

Fragen, die einer bekannten Architekturabfrage entsprechen, dürfen nicht unnötig über generiertes Cypher beantwortet werden.

---

## 3. Nicht im Scope

Folgende Funktionen werden ausdrücklich **nicht** implementiert:

- OpenTelemetry
- `OBSERVED` Runtime Facts
- Vector Database
- GraphRAG
- Wiki
- ADR-RAG
- Source-Code-RAG
- autonome Agents
- generische Ontologie
- OWL / RDF / SHACL
- weitere Analysen A6+
- automatische REST-Caller-Erkennung

Damit bleibt der Scope:

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

# 4. Teilprojekt H1 – Provenance / Evidence

## 4.1 Problem

Der bestehende Canonical Layer erzeugt bereits:

```text
source_type
source_file
source_revision
evidence_type
```

Diese Provenance-Daten werden derzeit jedoch nicht in einer Form gespeichert, mit der eine Graphabfrage feststellen kann, aus welcher konkreten Spezifikation eine Architekturbeziehung stammt. Der Importer speichert lediglich `sources[]` für Reimport-Zwecke.

Das ist für einen Architecture Knowledge Graph nicht ausreichend.

---

## 4.2 Architekturprinzip

Ein Architektur-Fakt wird zukünftig als Kombination aus

\[
\boxed{
Fact + Evidence
}
\]

verstanden.

Beispiel:

\[
OrderService
\xrightarrow{SENDS}
paymentQueue
\]

ist der Fakt.

Die Evidence ist:

```text
sourceType       ASYNCAPI
sourceFile       order-service/asyncapi.yaml
sourceRevision   abc123
evidenceType     DECLARED
```

---

## 4.3 Evidence-Modell

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

Eine Evidence besitzt eine stabile ID.

Beispielsweise:

```text
evidence:asyncapi:order-service:abc123
```

---

## 4.4 Graph-Modell

Es wird ein neuer Knotentyp eingeführt:

```text
(:Evidence)
```

mit:

```text
id
sourceType
sourceFile
sourceRevision
evidenceType
```

Beispiel:

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

## 4.5 Evidence für Beziehungen

Die wichtigste Provenance betrifft nicht primär Nodes, sondern Aussagen.

Beispiel:

```text
OrderService -[:SENDS]-> payment-q
```

Diese Relation soll mindestens folgende Properties erhalten:

```text
evidenceIds
```

Beispiel:

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

Dadurch können mehrere Quellen denselben Fakt bestätigen.

---

## 4.6 Warum Evidence nicht ausschließlich als Relationship-Properties?

Langfristig müssen Fragen möglich sein wie:

> Zeige alle Fakten aus einer bestimmten AsyncAPI-Version.

oder:

> Welche Architekturinformationen stammen aus Manifesten?

Ein eigener `Evidence`-Node erlaubt:

```cypher
MATCH (e:Evidence {sourceType:'ASYNCAPI'})
RETURN e
```

und ermöglicht spätere Erweiterungen um:

```text
OpenTelemetry
ADR
Source Code
Kubernetes
Manual Assertion
```

Deshalb:

\[
Evidence = FirstClassEntity.
\]

---

## 4.7 Optionales zukünftiges Statement-Modell

Für diese Iteration **nicht zwingend erforderlich**, aber das Modell soll kompatibel damit bleiben:

```text
(:ArchitectureFact)
```

etwa:

```text
Fact
  subject   = OrderService
  predicate = SENDS
  object    = payment-q
```

mit:

```text
Fact -[:SUPPORTED_BY]-> Evidence
```

Der aktuelle PoC darf zunächst bei Relationships + `evidenceIds` bleiben.

---

## 4.8 Importverhalten

Beim Import:

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

Der GraphImporter muss:

1. `Evidence` mit `MERGE` persistieren.
2. die Architekturrelation mit `MERGE` erzeugen,
3. Evidence-IDs dedupliziert hinzufügen,
4. beim Reimport veraltete Evidence entfernen.

---

## 4.9 Reconciliation

Wenn Revision

```text
abc123
```

durch

```text
def456
```

ersetzt wird, darf eine obsolete Evidence nicht dauerhaft einen nicht mehr vorhandenen Fakt legitimieren.

Deshalb:

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

Regel:

\[
EvidenceSet(F)=\emptyset
\Rightarrow
delete(F)
\]

sofern der Fakt nicht anderweitig administrativ erzeugt wurde.

---

## 4.10 Evidence API

Neue REST-Endpunkte:

```text
GET /api/evidence
```

```text
GET /api/evidence/{evidenceId}
```

zusätzlich:

```text
GET /api/services/{serviceId}/evidence
```

```text
GET /api/queues/{queueId}/evidence
```

Optional wichtiger:

```text
GET /api/relations/{relationId}/evidence
```

falls Relations später eigene IDs erhalten.

---

## 4.11 Service Explorer

Die UI soll beispielsweise anzeigen:

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

Damit ist erstmals sichtbar:

\[
Architecture\ Claim
\rightarrow
Source.
\]

---

## 4.12 Akzeptanzkriterien H1

**AC-H1-1**  
Alle Adapter erzeugen Evidence.

**AC-H1-2**  
Evidence wird als `Evidence` Node in Neo4j persistiert.

**AC-H1-3**  
Wesentliche Architekturrelations besitzen mindestens eine Evidence-Referenz.

**AC-H1-4**  
Mehrfachimporte erzeugen keine duplizierte Evidence.

**AC-H1-5**  
Eine veraltete Revision wird korrekt reconciled.

**AC-H1-6**  
Eine API-Abfrage kann für einen Fakt Quelle und Revision ermitteln.

**AC-H1-7**  
AC13 des ursprünglichen PoC gilt danach als vollständig erfüllt.

---

# 5. Teilprojekt H2 – Semantic Query Validator

## 5.1 Problemstellung

Der aktuelle CypherValidator beantwortet:

\[
IsReadOnly(q)?
\]

nicht aber:

\[
IsSemanticallyValid(q,GSchema)?
\]

Im Live-Test war beispielsweise:

```text
Queue -[:SENDS]-> Service
```

zulässig, obwohl das tatsächliche Modell nur

```text
Service -[:SENDS]-> Queue
```

definiert.

---

## 5.2 Ziel

Ein neuer Semantic Validator soll prüfen:

\[
domain(Relation)
\]

und

\[
range(Relation).
\]

Beispielsweise:

\[
domain(SENDS)=Service
\]

\[
range(SENDS)=Queue.
\]

Damit ist

\[
Service\xrightarrow{SENDS}Queue
\]

gültig und

\[
Queue\xrightarrow{SENDS}Service
\]

ungültig.

---

## 5.3 Graph Schema Registry

Neue Komponente:

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

## 5.4 Validierungspipeline

Neue Pipeline:

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

Der bestehende Validator bleibt bestehen.

Der neue Validator ersetzt ihn **nicht**.

---

## 5.5 Prüfung

Beispiel gültig:

```cypher
MATCH (s:Service)-[:SENDS]->(q:Queue)
RETURN s, q
```

Ergebnis:

```text
VALID
```

Beispiel ungültig:

```cypher
MATCH (q:Queue)-[:SENDS]->(s:Service)
RETURN q
```

Ergebnis:

```text
SemanticValidationError:

Relation SENDS expects

Service -> Queue

but query contains

Queue -> Service
```

---

## 5.6 Weitere semantische Prüfungen

Im Scope:

### Relation exists

```text
FOO_BAR
```

muss abgelehnt werden.

### Source type valid

```text
Queue -[:PROVIDES]-> Operation
```

ungültig.

### Target type valid

```text
Service -[:SENDS]-> Message
```

ungültig.

### Direction valid

```text
Queue -[:SENDS]-> Service
```

ungültig.

---

## 5.7 Noch nicht im Scope

Nicht geprüft werden:

- fachliche Bedeutung einer Frage,
- komplexe Cypher-Äquivalenz,
- Korrektheit von `WHERE`-Logik,
- Aggregationssemantik,
- Optimierung,
- Vollständigkeit einer Antwort.

Damit garantiert der Validator:

\[
SchemaCorrect(q)
\]

nicht:

\[
AnswerCorrect(q,Question).
\]

---

## 5.8 Parser

Der bisherige handgeschriebene Security Validator wird bewusst nur als Allow-/Blocklist verwendet.

Für den Semantic Validator soll die Implementierung so strukturiert sein, dass später ein Cypher-AST-Parser eingebunden werden kann.

Für diese Iteration sind zwei Varianten zulässig:

**Variante A:** eingeschränkte Parser-Implementierung für die vom LLM erlaubte Cypher-Teilmenge.

**Variante B:** etablierter Cypher Parser, sofern Python-Integration praktikabel ist.

Die Architektur darf nicht von Regex-spezifischem Verhalten abhängen.

---

## 5.9 Semantic Validator API

Primär intern:

```python
class SemanticQueryValidator:

    def validate(self, cypher: str) -> None:
        ...
```

Optional Debug:

```text
POST /api/debug/validate-cypher
```

nur im Development Mode.

---

## 5.10 Fehlerverhalten

Bei semantisch falschem Query:

```http
HTTP 422
```

Antwort:

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

Mindestens:

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

Zusätzlich:

- unbekannte Relation
- fehlende Labels
- Alias-Nutzung
- mehrere MATCH-Blöcke
- OPTIONAL MATCH
- variable-length traversal, soweit erlaubt.

---

## 5.12 Akzeptanzkriterien H2

**AC-H2-1**  
Alle freigegebenen Relationstypen besitzen Domain/Range-Definitionen.

**AC-H2-2**  
Der Live-Test-Fehler `Queue -[:SENDS]-> Service` wird automatisch erkannt.

**AC-H2-3**  
Gültige A1–A5-Cypher-Queries bleiben zulässig.

**AC-H2-4**  
Unbekannte Relationstypen werden abgelehnt.

**AC-H2-5**  
Security Validator und Semantic Validator werden separat getestet.

**AC-H2-6**  
Keine semantisch ungültige Query erreicht Neo4j.

---

# 6. Teilprojekt H3 – Intent Router

## 6.1 Problemstellung

Das System besitzt bereits fünf verlässliche Analysen:

```text
A1 Queue Senders
A2 Queue Consumers
A3 Queues without Consumers
A4 Queues without Senders
A5 Blast Radius
```

Diese sind reproduzierbar und vollständig unabhängig vom LLM.

Es ist deshalb unnötig und riskanter, für äquivalente natürlichsprachliche Fragen neues Cypher generieren zu lassen.

---

## 6.2 Architekturprinzip

\[
\boxed{
KnownIntent
\rightarrow
DeterministicAnalysis
}
\]

und nur:

\[
\boxed{
UnknownIntent
\rightarrow
LLMGeneratedCypher
}
\]

---

## 6.3 Neue Pipeline

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

Beispiele:

```json
{
  "intent": "A1_QUEUE_SENDERS",
  "confidence": 0.99,
  "parameters": {
    "queue": "payment-q"
  }
}
```

oder:

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

## 6.6 Intent-Erkennung

Für A1–A5 wird **kein zweites generatives LLM als Voraussetzung** eingeführt.

Der Router kann zunächst arbeiten mit:

1. regelbasierten Patterns,
2. normalisierter Entity Extraction,
3. optional LLM Classification nur als Fallback.

Beispiele:

```text
"Who sends to payment-q?"
```

→ A1

```text
"Welche Services senden an payment-q?"
```

→ A1

```text
"Who consumes from payment-q?"
```

→ A2

```text
"Welche Queues haben keinen Consumer?"
```

→ A3

```text
"Queues with a consumer but no sender"
```

→ A4

```text
"Welche Services hängen vom OrderService ab?"
```

→ A5

---

## 6.7 Deterministic Query Registry

Neue Komponente:

```text
analysis/
    registry.py
```

Beispiel:

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

Der Intent Router erzeugt selbst **kein Cypher**.

Er wählt eine bestehende getestete Analyse aus.

---

## 6.8 Confidence Threshold

Konfiguration:

```yaml
intent-router:
  deterministic-threshold: 0.90
```

Wenn:

\[
confidence\ge0.90
\]

wird die deterministische Analyse ausgeführt.

Andernfalls:

```text
UNKNOWN
```

und Übergabe an LLM Query Generation.

---

## 6.9 Ambiguität

Beispiel:

> What depends on payment?

kann bedeuten:

- Queue `payment-q`,
- Service `PaymentService`,
- Message `PaymentRequested`.

Der Router darf hier nicht raten.

Ergebnis:

```text
UNKNOWN
```

oder:

```text
AMBIGUOUS
```

Optional spätere Erweiterung:

```python
AMBIGUOUS = "AMBIGUOUS"
```

---

## 6.10 Entity Resolution

Der Router benötigt Zugriff auf bekannte Graph-Entities:

```text
Service
Queue
Message
```

Beispiel:

```text
payment q
```

soll normalisiert werden zu:

```text
payment-q
```

wenn genau eine eindeutige Queue existiert.

Nicht erlaubt:

unsichere automatische Zuordnung bei mehreren Treffern.

---

## 6.11 Query Response

Antwort soll zusätzlich enthalten:

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

Beim LLM:

```json
{
  "executionMode": "LLM",
  "generatedCypher": "...",
  "result": [...]
}
```

Damit ist für Benutzer und Tests immer sichtbar:

\[
\text{Wie wurde die Antwort erzeugt?}
\]

---

## 6.12 UI

Die Query-Seite zeigt:

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

Bei freiem Query:

```text
Execution
────────────────────────────────
LLM-generated Cypher

Semantic validation: passed
```

---

## 6.13 Der konkrete Live-Test muss danach anders laufen

Die zuvor problematische Frage:

> What queues have a consumer but no known sender?

soll künftig ergeben:

```text
Intent:
A4_QUEUES_WITHOUT_SENDERS
```

und direkt die bestehende Analyse ausführen.

Damit wird überhaupt kein generiertes Cypher mehr benötigt.

Erwartetes Resultat:

```text
unknown-producer-q
```

---

## 6.14 Akzeptanzkriterien H3

**AC-H3-1**  
Alle A1–A5-Analysen besitzen einen Intent.

**AC-H3-2**  
Deutsch- und englischsprachige Standardformulierungen werden erkannt.

**AC-H3-3**  
Bekannte Intents erzeugen kein LLM-Cypher.

**AC-H3-4**  
A1–A5 liefern über `/api/query` dasselbe Ergebnis wie ihre deterministischen REST-Endpunkte.

**AC-H3-5**  
Unsichere Fragen werden als `UNKNOWN` behandelt.

**AC-H3-6**  
Das Execution Mode Feld zeigt `DETERMINISTIC` oder `LLM`.

**AC-H3-7**  
Der in Iteration 9 beobachtete A4-Fehler ist über den normalen NL-Endpunkt nicht mehr reproduzierbar.

---

# 7. Zusammenspiel der drei Erweiterungen

Das neue System hat anschließend drei Sicherheits-/Vertrauensstufen.

## Stufe 1 – Evidenz

\[
\boxed{
Where\ did\ this\ fact\ come\ from?
}
\]

## Stufe 2 – deterministische Semantik

\[
\boxed{
Is\ there\ already\ a\ trusted\ analysis?
}
\]

## Stufe 3 – kontrollierte generative Abfrage

\[
\boxed{
If\ AI\ generates\ a\ query,\ is\ it
syntactically,\ safely\ and\ structurally\ valid?
}
\]

Gesamt:

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

Alle resultierenden Fakten besitzen wiederum:

```text
Evidence
```

---

# 8. Neue Python-Paketstruktur

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

# 9. Überarbeiteter QuestionService

Konzeptionell:

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

Das LLM ist jetzt tatsächlich:

\[
fallback
\]

und nicht der Standardpfad.

---

# 10. Teststrategie

Die bestehende Testsuite darf nicht ersetzt werden.

Neue Tests kommen hinzu.

## Unit

### Evidence

- ID-Erzeugung
- Merge
- Reconciliation
- Mehrfachquellen

### Semantic Validator

mindestens 30 positive/negative Fälle.

### Intent Router

mindestens:

- 5 Intents
- DE/EN
- Synonyme
- Entity Extraction
- Ambiguität
- UNKNOWN

---

## Integration

Mit realem Neo4j:

```text
Import
   |
Evidence persisted
   |
Query
```

sowie:

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

## Regression Test des Live-Fehlers

Expliziter Test:

```python
question = (
    "What queues have a consumer "
    "but no known sender?"
)
```

Erwartung:

```text
executionMode = DETERMINISTIC
intent        = A4_QUEUES_WITHOUT_SENDERS
result        = ["unknown-producer-q"]
```

Es darf **kein** `generate_cypher()` aufgerufen werden.

---

# 11. Neue Akzeptanzkriterien

Die Iteration gilt als abgeschlossen, wenn:

| ID | Kriterium |
|---|---|
| H1.1 | Provenance ist in Neo4j querybar |
| H1.2 | Jede wesentliche Relation besitzt Evidence |
| H1.3 | Evidence-Revisionswechsel wird reconciled |
| H1.4 | ursprüngliches AC13 ist vollständig erfüllt |
| H2.1 | Domain/Range aller Graphrelationen definiert |
| H2.2 | falsche Relationsrichtung wird erkannt |
| H2.3 | unbekannte Relations werden blockiert |
| H2.4 | semantisch ungültiges Cypher erreicht Neo4j nicht |
| H3.1 | A1–A5 besitzen deterministic intents |
| H3.2 | bekannte Fragen umgehen die LLM-Query-Generation |
| H3.3 | UNKNOWN benutzt weiterhin kontrolliertes LLM-Cypher |
| H3.4 | `/api/query` zeigt Execution Mode |
| H3.5 | Live-A4-Regressionstest liefert korrektes Ergebnis |
| H3.6 | bestehende 198 Tests bleiben grün |

---

# 12. Empfohlene Implementierungsreihenfolge

Die drei Punkte werden nicht parallel implementiert.

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

Ziel:

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

Ziel:

Der in Iteration 9 beobachtete falsche `SENDS`-Pfad wird blockiert.

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

Ziel:

Der problematische Query wird im Normalfall gar nicht mehr vom LLM erzeugt.

---

# 13. Definition of Done

Nach Abschluss lautet die Architecture-Query-Pipeline:

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

für LLM-Queries zusätzlich:

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

und für alle Architekturinformationen:

\[
\boxed{
Fact
\rightarrow
Evidence
\rightarrow
Source
}
\]

Damit verändert sich die Plattform qualitativ von:

\[
\text{Architecture Graph + AI Query}
\]

zu:

\[
\boxed{
\text{Evidence-backed Architecture Knowledge Graph}
+
\text{Deterministic Reasoning}
+
\text{Semantically constrained AI}
}
\]

Das ist die stabile Grundlage, bevor OpenTelemetry und damit `OBSERVED` Architecture Facts hinzukommen.
