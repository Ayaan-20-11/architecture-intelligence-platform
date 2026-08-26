# Specification – Architecture Intelligence Platform
## H4 – Observed Architecture / OpenTelemetry Integration

**Version:** 0.3  
**Status:** Implementation Specification  
**Basis:** PoC Iterations 0–10C / H1–H3 abgeschlossen  
**Technologie:** Python 3.13, FastAPI, Pydantic, Neo4j, OpenTelemetry Collector  
**Scope:** Ergänzung des bestehenden Evidence-backed Architecture Knowledge Graph um tatsächlich beobachtete Runtime-Beziehungen

---

## 1. Ausgangslage

Nach Abschluss von H1–H3 besitzt die Plattform:

- einen Evidence-backed Architecture Knowledge Graph,
- vollständige Provenance für deklarierte Architekturbeziehungen,
- deterministische Analysen A1–A5,
- einen Intent Router, der bekannte Fragestellungen ohne LLM beantwortet,
- einen Security Validator für Cypher,
- einen Semantic Query Validator für Domain/Range-Beziehungen.

Alle H1-, H2- und H3-Kriterien sind erfüllt. Die aktuelle Testsuite umfasst **300 erfolgreiche Tests**, davon 221 Unit- und 79 Neo4j/Testcontainers-Integrationstests.

Der bestehende Zustand entspricht damit:

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

Die Hardening-Iteration hat insbesondere erreicht, dass Fakten auf ihre Quelle zurückgeführt werden können, bekannte Fragestellungen deterministisch beantwortet werden und semantisch falsche Graphbeziehungen nicht mehr bis Neo4j gelangen.

H4 ergänzt nun:

\[
\boxed{OBSERVED}
\]

Architecture Evidence aus OpenTelemetry.

---

## 2. Zielsetzung

H4 soll die bestehende deklarierte Architektur mit der **tatsächlich zur Laufzeit beobachteten Architektur** verbinden.

Aus:

```text
OpenAPI
AsyncAPI
Manifest
    |
    v
DECLARED Architecture
```

wird:

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

Damit sollen insbesondere drei Zustände unterscheidbar werden:

\[
\boxed{DECLARED\_ONLY}
\]

\[
\boxed{OBSERVED\_ONLY}
\]

\[
\boxed{CONFIRMED}
\]

Beispiel:

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

## 3. Kernhypothese von H4

Die zentrale Hypothese lautet:

\[
\boxed{
DeclaredArchitecture
\neq
ObservedArchitecture
}
\]

und gerade ihre Differenz enthält wertvolles Architekturwissen.

Insbesondere:

\[
Observed-Declared
\]

findet potenziell **undokumentierte reale Abhängigkeiten**.

Dagegen liefert:

\[
Declared-Observed
\]

Beziehungen, für die innerhalb eines definierten Beobachtungsfensters keine Laufzeitevidenz vorhanden ist.

Wichtig:

\[
Declared-Observed
\not\Rightarrow
obsolete.
\]

„Nicht beobachtet“ darf nicht automatisch als „ungenutzt“ oder „veraltet“ interpretiert werden.

---

## 4. Scope

### 4.1 Bestandteil von H4

H4 unterstützt:

- OpenTelemetry Traces,
- Service-Identifikation,
- REST Client-/Server-Kommunikation,
- Queue-basierte Messaging-Kommunikation,
- Observed Evidence,
- Zeitfenster,
- Umgebungen,
- Matching zu vorhandenen Graph-Entities,
- Erstellung beobachteter, bislang unbekannter Architektur-Fakten,
- Vergleich `DECLARED` vs. `OBSERVED`,
- deterministische Runtime-Analysen.

### 4.2 Nicht Bestandteil von H4

Bewusst nicht implementiert werden:

- Metrics,
- Logs,
- Speicherung vollständiger Traces in Neo4j,
- Trace-Waterfall-UI,
- vollständiger Event-/Causality-Graph,
- Vector Database,
- GraphRAG,
- Architecture Wiki,
- Anomaly Detection durch ML,
- automatische Architekturänderungen,
- SLO-Auswertung,
- Performance-Analyse,
- Langzeit-Telemetriespeicher.

H4 ist:

\[
\boxed{
Runtime\ Architecture\ Discovery
}
\]

und **kein Observability Backend**.

---

## 5. Architektur

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

Der OpenTelemetry Collector soll die vorhandene Observability-Lösung **nicht ersetzen**.

Architecture Intelligence ist lediglich ein zusätzlicher Telemetry Consumer.

---

## 6. OpenTelemetry Collector

Der Collector bildet die Grenze zwischen den instrumentierten Services und der Architecture Intelligence Platform.

```text
Microservices
    |
   OTLP
    |
    v
OpenTelemetry Collector
    |
    +----> Jaeger / Tempo / bestehendes Backend
    |
    +----> Architecture Intelligence
```

Damit bleibt die Architekturplattform unabhängig davon, welches Trace Backend produktiv verwendet wird.

---

## 7. Unterstützte Signale

H4 verarbeitet ausschließlich:

```text
TRACE / SPAN
```

Nicht verarbeitet werden:

```text
METRIC
LOG
```

Die Architekturinformation entsteht aus Operationen **zwischen Systemkomponenten**, die OpenTelemetry als Spans beschreibt.

---

## 8. OTLP Ingestion

Neue Komponente:

```text
app/
  telemetry/
      otlp_receiver.py
```

Primärer Eingang:

```text
POST /v1/traces
```

Unterstütztes Format für H4:

```text
OTLP/HTTP
application/x-protobuf
```

Der Receiver dekodiert die Traces mit den OpenTelemetry-Protobuf-Typen und transformiert sie anschließend in ein internes Modell.

---

## 9. Keine direkte Graph-Persistenz aus OTLP

Es gilt weiterhin das zentrale Architekturprinzip:

```text
External Format
      |
      v
Canonical Representation
      |
      v
Neo4j
```

also **nicht**:

```text
OTLP -> Neo4j
```

sondern:

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

Neue Pydantic-Strukturen:

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

Diese Struktur ist nur ein temporäres Ingestion-Modell.

Sie wird **nicht als Node in Neo4j gespeichert**.

---

## 11. Service Identity

Primäre Service-ID aus OpenTelemetry ist:

```text
service.name
```

optional ergänzt durch:

```text
service.namespace
```

Daher gilt:

```text
service.name = PaymentService

instance 1 ┐
instance 2 ├──> one Service node
instance 3 ┘
```

Nicht:

```text
PaymentService-1
PaymentService-2
PaymentService-3
```

---

## 12. Service Resolver

Neue Komponente:

```text
telemetry/
    service_resolver.py
```

Aufgabe:

```text
OTel Resource
     |
     v
Service Identity
     |
     v
Existing Graph Service
```

Matching-Reihenfolge:

1. `service.namespace + service.name`
2. `service.name`
3. konfigurierter Alias
4. ansonsten observed-only Service.

---

## 13. Observed-only Services

Wird beispielsweise beobachtet:

```text
service.name = FraudService
```

aber im deklarativen Graph existiert kein Service, wird ein neuer:

```text
(:Service)
```

erzeugt.

Properties:

```text
id
name
discoveryStatus = OBSERVED_ONLY
```

Dazu gehört ausschließlich `OBSERVED` Evidence.

Das ermöglicht die Analyse:

> Welche Services existieren zur Laufzeit, sind aber in keinem Architekturartefakt bekannt?

---

## 14. Environment

Runtime-Architektur muss nach Umgebung getrennt werden.

Primär verwendet wird:

```text
deployment.environment.name
```

Also:

```text
PaymentService
```

bleibt ein Service.

Die Beobachtung besitzt:

```text
environment = production
```

oder:

```text
environment = staging
```

---

## 15. Evidence-Modell erweitern

Bestehend:

```python
class EvidenceType(StrEnum):
    DECLARED = "DECLARED"
```

wird:

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

Observed Evidence erweitert die bisherigen Provenance-Daten.

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

Ein wichtiger Entwurfsentscheid:

**Nicht jeder Span erzeugt einen Evidence Node.**

Bei beispielsweise:

```text
20.000 REST-Aufrufen / Stunde
```

dürfen nicht:

```text
20.000 Evidence Nodes
```

entstehen.

Stattdessen wird aggregiert.

Für den PoC:

\[
bucket=1\ day.
\]

Beispiel:

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

## 18. Begrenzte Trace Samples

Ein Evidence Node speichert maximal:

```text
5 trace IDs
```

beispielsweise:

```json
{
  "sampleTraceIds": [
    "abc...",
    "def...",
    "123..."
  ]
}
```

Damit bleibt eine Stichprobe zur technischen Nachprüfung verfügbar.

Der Architecture Graph wird jedoch **kein Trace Store**.

---

## 19. Observation Count

`observationCount` dient als Hinweis:

```text
CALLS relation observed approximately 12,431 times
```

Nicht als Billing-/Monitoring-Metrik.

OTLP-Wiederholungen können zu Mehrfachzählung führen.

Daher:

\[
observationCount=best\ effort.
\]

Für die Architekturklassifikation genügt:

\[
count>0.
\]

---

## 20. REST – Observed Architecture

REST-Kommunikation wird primär aus HTTP Client-/Server-Spans abgeleitet.

Beispiel:

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

Daraus:

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

Die zuverlässigste Zuordnung entsteht über korrelierte Client-/Server-Spans:

```text
Client Span
   |
 trace / parent-child
   |
   v
Server Span
```

Der Server Span besitzt:

```text
resource.service.name
```

und identifiziert damit den tatsächlichen Ziel-Service.

Dadurch muss nicht aus Hostnamen geraten werden.

---

## 22. HTTP Operation Resolution

Operation Identity:

```text
provider service
+
HTTP method
+
route/template
```

Beispiel:

```text
operation:product-service:GET:/products/{id}
```

Verwendete Attribute:

```text
http.request.method
http.route
url.template
```

Daher darf beispielsweise:

```text
/products/4711
```

nicht automatisch einen neuen `Operation`-Node erzeugen.

---

## 23. REST Mapping

### Fall A – bestehende deklarierte Operation

```text
GET /products/{id}
```

existiert bereits aus OpenAPI.

Dann:

```text
OrderService -[:CALLS]-> Operation
```

erhält zusätzliche:

```text
OBSERVED Evidence
```

### Fall B – Operation beobachtet, aber nicht deklariert

Wenn ein stabiles Route/Template vorhanden ist:

```text
GET /internal/products/{id}
```

kann ein:

```text
Observed-only Operation
```

erzeugt werden.

Status:

```text
OBSERVED_ONLY
```

### Fall C – keine stabile Route

Nur:

```text
/products/4711
```

bekannt.

Dann:

```text
UNRESOLVED observation
```

und **kein Operation Node**.

Dies verhindert:

```text
/products/4711
/products/4712
/products/4713
...
```

als Graphknoten.

---

## 24. Messaging / Queue Architecture

Der bestehende Graph besitzt:

```text
Service -[:SENDS]-> Queue

Service -[:RECEIVES_FROM]-> Queue
```

Diese Relationen werden aus OpenTelemetry Messaging Spans bestätigt oder neu entdeckt.

---

## 25. Queue SEND Detection

Ein Producer-/Send-Span wie:

```text
service.name = OrderService

messaging.system = ...
messaging.destination.name = payment-q
messaging.operation.type = send
```

führt zu:

```text
OrderService
     |
   SENDS
     |
     v
 payment-q
```

mit:

```text
OBSERVED Evidence
```

---

## 26. Queue RECEIVE Detection

Consumer-/Process-Spans:

```text
service.name = PaymentService

messaging.destination.name = payment-q
messaging.operation.type = receive
```

oder:

```text
process
```

führen zu:

```text
PaymentService
       |
RECEIVES_FROM
       |
       v
 payment-q
```

mit `OBSERVED` Evidence.

---

## 27. Queue Identity

Queue Identity wird bestimmt aus:

```text
messaging.system
+
broker/system instance
+
messaging.destination.name
```

Beispiel:

```text
queue:<system>:<namespace>:payment-q
```

Dabei soll derselbe ID-Generator verwendet werden wie beim AsyncAPI-Importer.

Ziel:

```text
AsyncAPI Queue
       =
OpenTelemetry Queue
```

und nicht zwei parallele Nodes.

---

## 28. Messaging Destination Resolver

Neue Komponente:

```text
telemetry/
    queue_resolver.py
```

Matching:

1. exakte Canonical Queue ID,
2. Messaging-System + Destination Name,
3. konfigurierter Namespace/Alias,
4. sonst observed-only Queue.

---

## 29. Observed-only Queue

Wird beobachtet:

```text
legacy-payment-q
```

aber ist nirgendwo in AsyncAPI vorhanden:

```text
(:Queue {
    name: "legacy-payment-q",
    discoveryStatus: "OBSERVED_ONLY"
})
```

mit:

```text
OBSERVED Evidence
```

Damit wird unmittelbar:

\[
Observed-Declared
\]

sichtbar.

---

## 30. Message-Typen

OpenTelemetry liefert nicht zwingend den fachlichen Message-Typ, der in AsyncAPI als:

```text
PaymentRequested
```

modelliert wird.

Daher ist H4 zunächst auf:

```text
Service -> Queue
```

beschränkt.

Nicht garantiert wird:

```text
Service -> exact Message Type
```

Eine spätere Erweiterung kann ein projektspezifisches Low-Cardinality-Attribut einführen, beispielsweise:

```text
architecture.message.type
```

Dies ist **nicht Bestandteil von H4**.

---

## 31. Keine Payloads

Nicht gespeichert werden:

- Message Body,
- HTTP Request Body,
- HTTP Response Body,
- Authorization Header,
- Cookies,
- Query Parameter,
- personenbezogene Werte,
- vollständige URLs,
- Exception Stack Traces.

Architecture Intelligence verwendet eine explizite **Attribute Allowlist**.

---

## 32. Attribute Allowlist

REST beispielsweise:

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

Der Adapter darf keine OTel-Attributnamen quer über den Code verteilen.

Neue Komponente:

```text
telemetry/
    semconv/
        http.py
        messaging.py
        resources.py
```

Damit können unterschiedliche Semantic-Convention-Versionen zentral normalisiert werden.

---

## 34. ObservedFactCandidate

Canonical Runtime Model:

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

Beispiel:

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

Damit bleibt die Telemetry-Pipeline ähnlich zum bisherigen Adapter-Modell:

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

Neue Komponente:

```text
telemetry/
    aggregator.py
```

Aufgaben:

1. Fact normalisieren,
2. Evidence Bucket bestimmen,
3. vorhandene Relation suchen,
4. `OBSERVED` Evidence hinzufügen,
5. Counter aktualisieren,
6. `first_seen` / `last_seen` aktualisieren,
7. Trace-Samples begrenzen.

---

## 37. Keine neuen Relationstypen für Observed

Wichtige Designentscheidung:

Nicht:

```text
OBSERVED_CALLS
DECLARED_CALLS
```

sondern weiterhin:

```text
CALLS
SENDS
RECEIVES_FROM
```

Die Evidenz entscheidet über den Status.

Beispiel:

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

Der Status wird **abgeleitet**, nicht als primäre Wahrheit gespeichert.

Für Fakt \(F\):

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

Dann:

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

## 39. Beobachtungsfenster

Runtime-Fragen benötigen immer ein Zeitfenster.

Standard:

```text
last 24h
```

oder konfigurierbar:

```text
7d
30d
```

Beispiel:

```text
Declared but not observed
during production / last 7 days
```

Nicht:

```text
Declared but never used
```

---

## 40. Unobserved ist keine negative Evidence

Fundamentale Regel:

\[
\boxed{
Absence\ of\ observation
\neq
evidence\ of\ absence
}
\]

Daher dürfen UI und API niemals automatisch formulieren:

```text
unused
dead
obsolete
```

sondern ausschließlich:

```text
NOT_OBSERVED_IN_WINDOW
```

---

## 41. Telemetry Coverage

Zur Interpretation wird zusätzlich Coverage ermittelt.

Beispiel:

```text
PaymentService

environment: production
window: 7d

telemetry:
  spansObserved: true
  httpObserved: true
  messagingObserved: true
```

Dadurch kann unterschieden werden zwischen:

```text
Relation not observed
```

und:

```text
Service emitted no usable telemetry at all
```

---

## 42. Analyse O1 – Observed Relations

Neue deterministische Analyse:

> Welche Architekturbeziehungen wurden tatsächlich beobachtet?

```text
O1 OBSERVED_RELATIONS
```

Filter:

```text
environment
from
to
relationType
timeWindow
```

---

## 43. Analyse O2 – Confirmed Architecture

```text
O2 CONFIRMED_RELATIONS
```

Gesucht:

\[
Declared\cap Observed.
\]

Beispiel:

```text
OrderService -> payment-q

DECLARED AsyncAPI
OBSERVED OpenTelemetry
```

---

## 44. Analyse O3 – Observed but not Declared

```text
O3 OBSERVED_ONLY_RELATIONS
```

Gesucht:

\[
Observed-Declared.
\]

Beispiel:

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

Ergebnis:

> Undokumentierte Runtime-Abhängigkeit.

Dies dürfte die wichtigste H4-Analyse sein.

---

## 45. Analyse O4 – Declared but not Observed

```text
O4 DECLARED_ONLY_RELATIONS
```

Gesucht:

\[
Declared-Observed.
\]

Ausgabe muss immer enthalten:

```text
environment
observation window
telemetry coverage
```

Beispiel:

```text
ProductService CALLS PricingService

Declared: yes
Observed in production / last 7d: no
Coverage: available
```

Interpretation:

> Keine Beobachtung im angegebenen Zeitraum.

Nicht:

> Dependency is obsolete.

---

## 46. Analyse O5 – Telemetry Coverage

```text
O5 TELEMETRY_COVERAGE
```

Beispiel:

```text
OrderService          HTTP ✓ Messaging ✓
PaymentService        HTTP ✓ Messaging ✓
InvoiceService        HTTP - Messaging ✓
LegacyService         no telemetry
```

Damit lässt sich die Vertrauenswürdigkeit von O4 einschätzen.

---

## 47. REST API

Neue Endpunkte:

```text
GET /api/runtime/relations
```

Parameter:

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

## 48. Beispiel O3 Response

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

Bestehende Seite wird erweitert.

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

Legende:

```text
✓ CONFIRMED
! OBSERVED_ONLY
○ DECLARED_ONLY
```

---

## 50. UI – Relation Detail

Beispiel:

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

Die H3-Architektur bleibt bestehen.

Neue deterministische Intents:

```python
OBSERVED_RELATIONS
CONFIRMED_RELATIONS
OBSERVED_ONLY_RELATIONS
DECLARED_ONLY_RELATIONS
TELEMETRY_COVERAGE
```

Beispiele:

> Welche undokumentierten REST-Abhängigkeiten wurden in Production beobachtet?

→ O3.

> Welche deklarierte Kommunikation wurde in den letzten sieben Tagen nicht beobachtet?

→ O4.

> Für welche Services haben wir keine Telemetrie?

→ O5.

Diese Fragen sollen **kein LLM-generiertes Cypher benötigen**.

---

## 52. LLM bleibt Fallback

Neue Pipeline:

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

H4 erhöht also nicht die Abhängigkeit vom LLM.

---

## 53. Graph Schema Registry

H2 wird um keine parallelen `OBSERVED_*`-Relations erweitert.

Die bisherigen Domain/Range-Definitionen bleiben gültig:

```text
Service -> CALLS -> Operation
Service -> SENDS -> Queue
Service -> RECEIVES_FROM -> Queue
```

Neu ist lediglich:

```text
EvidenceType = OBSERVED
```

Dadurch bleibt Semantic Validation unverändert einsetzbar.

---

## 54. Python-Paketstruktur

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

PoC-Laufzeit:

```text
docker-compose.yml

architecture-intelligence
neo4j
otel-collector
```

Optional existierendes Trace Backend:

```text
jaeger / tempo
```

---

## 56. Collector-Konzept

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

Damit beeinflusst ein Fehler der Architecture Intelligence Platform nicht den normalen Telemetry-Pfad.

---

## 57. Backpressure / Fehler

Fällt Architecture Intelligence aus:

```text
OpenTelemetry Collector
        |
        X architecture exporter
        |
        +---- normal trace backend continues
```

Architecture Intelligence darf **nicht zum Single Point of Failure für Observability** werden.

---

## 58. Datenschutz und Sicherheit

H4 verarbeitet ausschließlich Metadaten, die zur Ermittlung von Architekturbeziehungen notwendig sind.

Grundsatz:

\[
\boxed{Minimum\ Telemetry\ Principle}
\]

Persistiert werden keine:

- Payloads,
- Header,
- User IDs,
- Query Strings,
- Message Bodies,
- Stack Traces.

---

## 59. Retention

Neo4j speichert lediglich aggregierte Observed Evidence.

PoC-Vorschlag:

```text
observed evidence retention = 90 days
```

Konfigurierbar:

```yaml
telemetry:
  evidence-retention-days: 90
  bucket-size: 1d
  sample-trace-ids: 5
```

---

## 60. Cleanup

Periodischer Job:

```text
EvidenceCleanupJob
```

entfernt:

```text
OBSERVED Evidence older than retention
```

Wenn ein `OBSERVED_ONLY` Fact anschließend überhaupt keine Evidence mehr besitzt, kann er gelöscht werden.

Ein `DECLARED` Fact bleibt erhalten.

---

## 61. Tests – Unit

Neue Unit Tests mindestens für:

### OTLP Decoder

- Resource extraction
- Span extraction
- malformed payload

### Service Resolver

- exact match
- namespace match
- instance ignored
- observed-only service

### HTTP Resolver

- client/server pair
- existing operation
- observed-only operation
- raw URI rejected

### Messaging Resolver

- SEND
- RECEIVE
- PROCESS
- existing queue
- observed-only queue

### Aggregator

- bucket aggregation
- evidence deduplication
- first/last seen
- trace sample limit

---

## 62. Integration Tests

Mit:

```text
real Neo4j 5
+
FastAPI
+
OTLP protobuf
```

Testpfad:

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

## 63. Testlandscape

Bestehende Services:

```text
OrderService
ProductService
PaymentService
InvoiceService
```

Zusätzlich Runtime-Testfälle:

```text
OrderService -> ProductService
```

deklarativ + beobachtet:

```text
CONFIRMED
```

```text
OrderService -> LegacyPricingService
```

nur beobachtet:

```text
OBSERVED_ONLY
```

```text
PaymentService -> invoice-q
```

deklarativ, aber im Testfenster nicht beobachtet:

```text
DECLARED_ONLY
```

---

## 64. Regression

Alle bisherigen:

\[
300
\]

Tests müssen weiterhin erfolgreich laufen.

H4 darf:

- H1 Evidence nicht brechen,
- H2 Semantic Validation nicht umgehen,
- H3 Intent Routing nicht umgehen.

---

## 65. H4 Akzeptanzkriterien

| ID | Kriterium |
|---|---|
| H4.1 | OTLP Trace-Batches können über den Collector ingestiert werden |
| H4.2 | `service.name` wird korrekt auf logische Service-Nodes gemappt |
| H4.3 | `service.instance.id` erzeugt keine zusätzlichen Service-Nodes |
| H4.4 | `deployment.environment.name` trennt Observations nach Umgebung |
| H4.5 | HTTP Client-/Server-Spans erzeugen beobachtete REST-Beziehungen |
| H4.6 | vorhandene OpenAPI-Operationen werden korrekt wiederverwendet |
| H4.7 | Messaging SEND erzeugt/aktualisiert `SENDS` |
| H4.8 | Messaging RECEIVE/PROCESS erzeugt/aktualisiert `RECEIVES_FROM` |
| H4.9 | bekannte AsyncAPI-Queues werden wiederverwendet |
| H4.10 | unbekannte Runtime-Services/Queues können als `OBSERVED_ONLY` angelegt werden |
| H4.11 | Observed Evidence enthält Environment, FirstSeen, LastSeen und Count |
| H4.12 | Spans werden aggregiert und nicht einzeln als Neo4j-Nodes gespeichert |
| H4.13 | `DECLARED ∩ OBSERVED` wird als `CONFIRMED` erkannt |
| H4.14 | `OBSERVED - DECLARED` wird deterministisch ermittelt |
| H4.15 | `DECLARED - OBSERVED` wird zeitfensterbezogen ermittelt |
| H4.16 | `DECLARED_ONLY` wird nicht automatisch als „obsolete“ klassifiziert |
| H4.17 | Telemetry Coverage ist separat abfragbar |
| H4.18 | O1–O5 funktionieren vollständig ohne LLM |
| H4.19 | sensible Span-Attribute werden nicht persistiert |
| H4.20 | bestehende 300 Tests bleiben grün |

---

## 66. Erfolgskriterien

H4 gilt fachlich als erfolgreich, wenn mindestens ein realer Anwendungsfall gefunden wird, in dem:

\[
Observed-Declared\neq\emptyset.
\]

Also beispielsweise eine reale REST- oder Queue-Abhängigkeit, die im deklarativen Knowledge Graph nicht vorhanden war.

Ein zweites wichtiges Ergebnis wäre:

\[
Declared-Observed\neq\emptyset,
\]

wobei die Plattform korrekt nur sagt:

> „Nicht im ausgewählten Beobachtungszeitraum gesehen.“

---

## 67. Implementierungsreihenfolge

### Iteration 11A – OTLP Foundation

```text
Collector
   ↓
OTLP Receiver
   ↓
RuntimeSpan
```

Noch kein Graphupdate.

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

Implementieren:

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

Nach H4 besitzt die Plattform folgende Datenpipeline:

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

und kann deterministisch unterscheiden:

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

## 69. Zielzustand nach H4

Vor H4:

\[
\boxed{
Architecture\ Knowledge\ Graph
}
\]

Nach H4:

\[
\boxed{
Architecture\ Intelligence\ Platform
}
\]

weil die Plattform dann nicht mehr ausschließlich beantworten kann:

> Was behaupten unsere Architekturartefakte?

sondern zusätzlich:

> Was passiert tatsächlich?

und insbesondere:

\[
\boxed{
\text{Wo unterscheiden sich deklarierte und beobachtete Architektur?}
}
\]

Genau diese Differenz ist der entscheidende zusätzliche Erkenntnisgewinn von H4.

Ein weiterer konzeptionell wichtiger Schritt folgt daraus: Sobald `OBSERVED`-Evidence über Zeit vorliegt, besitzt die Plattform erstmals eine belastbare **zeitliche Dimension der Architektur**. Damit wäre anschließend H5 denkbar: nicht mehr nur „welche Relation wurde beobachtet?“, sondern **kausale Runtime-Flows und Architecture Trajectories**.
