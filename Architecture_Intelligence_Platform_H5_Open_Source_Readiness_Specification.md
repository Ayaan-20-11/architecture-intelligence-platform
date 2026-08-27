# Specification – Architecture Intelligence Platform
## H5 – Open Source Readiness

**Version:** 0.5  
**Status:** Implementation Specification  
**Basis:** PoC Iterations 0–11G / H1–H4 abgeschlossen + Iteration 11H Runtime Correctness & Robustness  
**Lizenz:** Apache License 2.0 (`Apache-2.0`)  
**Zielplattform:** GitHub  
**Primärtechnologie:** Python 3.13, FastAPI, Pydantic, Neo4j, OpenTelemetry Collector  
**Scope:** Vorbereitung des bestehenden Projekts für eine öffentliche Open-Source-Veröffentlichung auf GitHub

---

## 1. Ausgangslage

Nach Abschluss von H1–H4 und der anschließenden Iteration 11H besitzt die Architecture Intelligence Platform einen technisch belastbaren, runtime-gehärteten Kern:

```text
OpenAPI
AsyncAPI
Architecture Manifest
      |
      v
Canonical Architecture Model
      |
      v
Evidence-backed Architecture Knowledge Graph
      ^
      |
Observed Architecture Evidence
      ^
      |
AIP OTLP ingestion
      ^
      |
OpenTelemetry Collector
      ^
      |
Instrumented Services
```

Darauf arbeiten:

```text
deterministic analyses A1-A5
runtime analyses O1-O5
declared vs observed comparison
semantic Cypher validation
constrained natural-language query layer
```

11H verschärft dabei die Runtime-Semantik insbesondere durch:

```text
independent DECLARED / OBSERVED evidence
safe relation reconciliation
cross-batch HTTP correlation
partial-instrumentation handling
observed provider semantics
coverage qualification
realistic Collector-based demo topology
```

H5 führt **keine neue fachliche Architecture-Intelligence-Funktion** ein.

Stattdessen wird der durch H1–H4 + 11H erreichte Stand so vorbereitet, dass externe Entwickler ihn verstehen, legal nutzen, sicher starten, reproduzierbar testen, erweitern und Beiträge liefern können.

H5 ist damit eine Produktisierungs- und Veröffentlichungsphase.

---

## 2. Zielsetzung

Der Zielzustand lautet:

\[
H1-H4
\rightarrow
11H\ Runtime\ Correctness\ \&\ Robustness
\rightarrow
H5\ Open\ Source\ Readiness
\rightarrow
v0.1.0
\rightarrow
Public\ GitHub\ Repository
\]

Das Projekt soll nach H5:

- legally publishable,
- secure by default,
- easy to understand,
- easy to start,
- easy to test,
- easy to contribute to,
- easy to extend

sein.

Das Release wird als `Experimental` oder `Alpha` gekennzeichnet.

---

## 3. Lizenzmodell

### 3.1 Projektlizenz

Das Projekt wird unter der:

**Apache License 2.0**

veröffentlicht.

SPDX-Identifier:

```text
Apache-2.0
```

Repository-Datei:

```text
LICENSE
```

Die Datei muss den vollständigen unveränderten Standardtext der Apache License 2.0 enthalten.

### 3.2 Gründe für Apache 2.0

Die Lizenz wird gewählt, weil sie:

- kommerzielle Nutzung erlaubt,
- Änderungen und Weiterverteilung erlaubt,
- private Nutzung erlaubt,
- explizite Patentregelungen enthält,
- in Infrastruktur-, Cloud- und Enterprise-Projekten verbreitet ist,
- zu einem möglichen späteren Consulting- oder Enterprise-Geschäft passt.

### 3.3 SPDX-Header

Quelldateien können optional enthalten:

```text
SPDX-License-Identifier: Apache-2.0
```

Optional zusätzlich:

```text
Copyright <YEAR> <PROJECT OWNER>
```

### 3.4 NOTICE

Es wird geprüft, ob eine Datei:

```text
NOTICE
```

erforderlich oder sinnvoll ist.

### 3.5 Drittanbieter-Lizenzen

Neue Datei:

```text
THIRD_PARTY_LICENSES.md
```

Sie dokumentiert mindestens:

```text
dependency
version
license
source/project URL
notes
```

Alle direkten Produktionsabhängigkeiten müssen vor Release geprüft werden.

---

## 4. Veröffentlichung nur aus bereinigtem Codebestand

Vor Veröffentlichung muss das Repository vollständig geprüft werden auf:

- Kundendaten,
- interne Firmennamen,
- reale Service-Namen,
- Queue-Namen,
- interne URLs,
- Hostnamen,
- API-Schlüssel,
- Passwörter,
- `.env`-Dateien,
- Tokens,
- Zertifikate,
- private Schlüssel,
- Cloud-Ressourcen-IDs,
- interne Architekturdiagramme,
- reale OpenAPI-/AsyncAPI-Dateien,
- reale OpenTelemetry-Traces.

Die Prüfung gilt ausdrücklich für die gesamte Git-Historie.

Wenn die bestehende Historie nicht zweifelsfrei veröffentlichbar ist, wird ein neues öffentliches Repository aus einem bereinigten Export aufgebaut.

---

## 5. Secret Scanning

Vor dem ersten öffentlichen Push wird ein lokaler Secret Scan durchgeführt.

Mindestens zu prüfen:

```text
OpenAI keys
Azure credentials
AWS credentials
GitHub tokens
Neo4j passwords
JWT secrets
private keys
certificates
connection strings
```

Nach Veröffentlichung wird GitHub Secret Scanning aktiviert, soweit verfügbar.

---

## 6. Repository-Struktur

Zielstruktur:

```text
architecture-intelligence/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/
│   ├── dependabot.yml
│   └── pull_request_template.md
├── docs/
│   ├── architecture.md
│   ├── canonical-model.md
│   ├── graph-model.md
│   ├── evidence.md
│   ├── ingestion.md
│   ├── opentelemetry.md
│   ├── security-model.md
│   ├── development.md
│   ├── adapter-development.md
│   └── adr/
├── examples/
│   ├── declared/
│   └── runtime-demo/
├── src/
│   └── architecture_intelligence/
├── tests/
│   ├── unit/
│   └── integration/
├── LICENSE
├── NOTICE
├── THIRD_PARTY_LICENSES.md
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── SUPPORT.md
├── ROADMAP.md
├── CHANGELOG.md
├── pyproject.toml
├── docker-compose.yml
└── Dockerfile
```

---

## 7. Projektname

Arbeitsname:

```text
architecture-intelligence
```

Anforderungen:

- kurz,
- eindeutig,
- technisch verständlich,
- nicht mit bestehender Marke kollidierend,
- GitHub-Suche geeignet,
- optional später als Python-Paket nutzbar.

Vor Veröffentlichung ist eine Namens- und Markenprüfung erforderlich.

---

## 8. Repository Description

Vorgeschlagen:

```text
Evidence-backed architecture intelligence from OpenAPI, AsyncAPI and OpenTelemetry.
```

Alternative:

```text
Compare declared and observed microservice architecture using OpenAPI, AsyncAPI, OpenTelemetry and Neo4j.
```

---

## 9. Positionierung

Das Projekt wird nicht primär als LLM Tool, Neo4j Tool, API Parser oder Service Catalog positioniert.

Kernbotschaft:

```text
Declared Architecture vs. Observed Architecture
```

Kurzform:

```text
Know what your architecture says.
Know what it actually does.
```

---

## 10. README

Ein neuer Besucher soll innerhalb von ungefähr zwei Minuten verstehen:

- welches Problem gelöst wird,
- wie die Plattform funktioniert,
- warum sie anders ist,
- wie sie gestartet wird.

Empfohlene Struktur:

```text
# Architecture Intelligence
Short value proposition
Hero architecture diagram
## Why?
## Features
## Declared vs Observed
## Quick Start
## Example
## Architecture
## Deterministic Analyses
## OpenTelemetry
## Natural Language Queries
## Documentation
## Contributing
## Project Status
## License
```

Hero Message:

```text
Build an evidence-backed architecture knowledge graph from
OpenAPI, AsyncAPI and OpenTelemetry — and discover where
declared and observed architecture diverge.
```

---

## 11. README Feature-Liste

Mindestens:

```text
✓ OpenAPI ingestion
✓ AsyncAPI queue topology
✓ Architecture manifest support
✓ Evidence / provenance
✓ independent DECLARED and OBSERVED evidence
✓ Neo4j architecture knowledge graph
✓ deterministic dependency analyses
✓ architecture blast radius
✓ semantic Cypher validation
✓ natural-language architecture queries
✓ OpenTelemetry runtime discovery
✓ cross-batch HTTP correlation
✓ partial-instrumentation tolerance
✓ declared vs observed architecture
✓ architecture drift detection
✓ telemetry coverage qualification
```

Die README darf diese Punkte in nutzerfreundlicher Form gruppieren; die internen Begriffe `CLIENT_SERVER`, `CLIENT_ONLY` und `SERVER_ONLY` müssen nicht Teil des Hero-Abschnitts sein, sollen aber in der OpenTelemetry-Dokumentation erklärt werden.

---

## 12. Quick Start

Ideal:

```bash
git clone <repository>
cd architecture-intelligence
docker compose up
```

Danach:

```text
http://localhost:8000
```

Voraussetzungen:

```text
Docker
Docker Compose
```

Optional für lokale Entwicklung:

```text
Python 3.13
```

---

## 13. Demo-Daten

Alle öffentlichen Demo-Daten müssen vollständig synthetisch sein.

Beispiel:

```text
examples/
├── order-service/
│   ├── openapi.yaml
│   ├── asyncapi.yaml
│   └── architecture.yaml
├── product-service/
│   └── openapi.yaml
├── payment-service/
│   └── asyncapi.yaml
└── invoice-service/
    └── asyncapi.yaml
```

---

## 14. Demo-Landschaft

```text
OrderService
   |
   +---- REST ----> ProductService
   |
   +---- SENDS ---> payment-q
                        |
                        v
                  PaymentService
                        |
                        v
                    invoice-q
                        |
                        v
                  InvoiceService
```

Zusätzlich H4:

```text
OrderService
    |
    +---- OBSERVED ONLY ---> LegacyPricingService
```

---

## 15. Runtime Demo

Die öffentliche Runtime-Demo ist nach 11H verbindlich Collector-basiert.

Neue Demo:

```text
examples/runtime-demo/
```

Enthält mindestens:

```text
sample services
OpenTelemetry instrumentation
OTel Collector config
traffic generator
synthetic declared architecture
```

Start:

```bash
docker compose -f docker-compose.demo.yml up
```

Referenztopologie:

```text
Demo Services
      |
      v
OpenTelemetry Collector
      |
      +--------------------+
      |                    |
      v                    v
Architecture            optional
Intelligence            trace backend /
Platform                debug exporter
      |
      v
Neo4j
```

Die Demo muss klar machen:

```text
AIP is an additional telemetry consumer,
not the primary observability backend.
```

Erwartete Zustände:

```text
CONFIRMED
OBSERVED_ONLY
NOT_OBSERVED_IN_WINDOW
```

Mindestens ein Szenario muss die 11H-Reconciliation-Invariante demonstrieren:

```text
initially:
DECLARED + OBSERVED = CONFIRMED

remove declaration on re-import:
OBSERVED remains = OBSERVED_ONLY
```

Optional, aber empfohlen, ist zusätzlich ein Cross-Batch-Szenario, bei dem CLIENT- und SERVER-Span in getrennten OTLP-Requests eintreffen und dennoch zu derselben beobachteten REST-Abhängigkeit korreliert werden.

---

## 16. Dokumentation

Zielstruktur:

```text
docs/
├── architecture.md
├── canonical-model.md
├── graph-model.md
├── evidence.md
├── ingestion.md
├── analyses.md
├── semantic-validation.md
├── opentelemetry.md
├── configuration.md
├── security-model.md
├── development.md
└── adapter-development.md
```

Optional:

```text
docs/specifications/
├── poc.md
├── h1-h3-hardening.md
├── h4-opentelemetry.md
├── 11h-runtime-correctness-robustness.md
└── h5-open-source-readiness.md
```

---

## 17. Canonical Model Dokumentation

Mindestens folgende Entitäten:

```text
Service
Operation
Queue
Message
Schema
Evidence
```

und Relationen:

```text
PROVIDES
CALLS
SENDS
RECEIVES_FROM
CARRIES
CONFORMS_TO
REQUEST_SCHEMA
RESPONSE_SCHEMA
DEAD_LETTERS_TO
```

---

## 18. Graph Model Dokumentation

Explizit dokumentieren:

```text
Service -[:PROVIDES]-> Operation
Service -[:CALLS]-> Operation
Service -[:SENDS]-> Queue
Service -[:RECEIVES_FROM]-> Queue
Queue -[:CARRIES]-> Message
Message -[:CONFORMS_TO]-> Schema
```

Zusätzlich:

```text
Fact + Evidence
DECLARED
OBSERVED
CONFIRMED
OBSERVED_ONLY
NOT_OBSERVED_IN_WINDOW
```

Nach 11H muss die öffentliche Graph-/Evidence-Dokumentation außerdem folgende Invarianten explizit machen:

\[
Fact\ exists\ iff\ supporting\ Evidence\ exists
\]

und:

\[
Removing\ DECLARED\ evidence
\not\Rightarrow
removing\ OBSERVED\ evidence
\]

Das bedeutet insbesondere:

```text
DECLARED + OBSERVED
       |
remove stale declaration
       v
OBSERVED_ONLY
```

Eine Relation darf erst gelöscht werden, wenn keinerlei unterstützende Evidence mehr vorhanden ist.

Für runtime-entdeckte stabile Provider-Operationen ist zu dokumentieren, dass auch:

```text
Service -[:PROVIDES {OBSERVED evidence}]-> ObservedOnlyOperation
```

zulässig ist. Eine spätere OpenAPI-Deklaration muss mit derselben logischen Operation reconciliert werden können, ohne die beobachtete Evidence zu verlieren.

---

## 19. Adapter Extension Point

Konzeptionelle Schnittstelle:

```python
class ArchitectureSourceAdapter(Protocol):
    def supports(self, source: Source) -> bool:
        ...
    def load(self, source: Source) -> ArchitectureModel:
        ...
```

Für Runtime-Quellen:

```python
class ObservationSourceAdapter(Protocol):
    def ingest(self, source: Any) -> ObservationBatch:
        ...
```

Neue Dokumentation:

```text
docs/adapter-development.md
```

---

## 20. Konfiguration externalisieren

Alle installationsabhängigen Werte müssen über Konfiguration oder Environment Variables steuerbar sein.

Beispiel:

```yaml
architecture-intelligence:
  neo4j:
    uri: bolt://neo4j:7687

  telemetry:
    enabled: true
    retention-days: 90
    bucket-size: 1d

    http-correlation:
      enabled: true
      ttl-seconds: 60
      max-pending-spans: 10000

    coverage:
      qualification-enabled: true

  llm:
    enabled: false
```

11H-spezifische Einstellungen müssen optional sein und sichere Defaults besitzen. Fehlende neue Properties dürfen den Start einer bestehenden Konfiguration nicht verhindern.

---

## 21. LLM bleibt optional

Fundamentale OSS-Anforderung:

```text
Core Platform Works Without LLM
```

Die Plattform muss ohne OpenAI, Azure OpenAI, Anthropic oder Ollama vollständig starten können.

Deterministische Analysen müssen unabhängig vom LLM funktionieren.

---

## 22. LLM Provider Abstraction

```python
class LLMProvider(Protocol):
    def generate_cypher(self, question: str, schema: str) -> str:
        ...

    def compose_answer(
        self,
        question: str,
        rows: list[dict],
    ) -> str:
        ...
```

Der erste Release darf weiterhin nur einen Provider implementieren.

---

## 23. Python Packaging

`pyproject.toml` muss vollständige Projektmetadaten enthalten.

Beispiel:

```toml
[project]
name = "architecture-intelligence"
version = "0.1.0"
description = "Evidence-backed architecture intelligence from OpenAPI, AsyncAPI and OpenTelemetry"
license = {text = "Apache-2.0"}
requires-python = ">=3.13"
```

Zusätzlich:

```text
authors
keywords
classifiers
project URLs
```

---

## 24. Docker Image

Ziel:

```text
ghcr.io/<owner>/architecture-intelligence:<version>
```

Anforderungen:

- Multi-stage build,
- kein Root-User im Runtime-Container,
- minimale Runtime-Abhängigkeiten,
- reproduzierbarer Build,
- explizite Versionierung.

---

## 25. Health Endpoints

Mindestens:

```text
GET /health
```

Optional:

```text
GET /ready
```

`/ready` prüft zusätzlich Neo4j und erforderliche Initialisierung.

---

## 26. GitHub Actions – CI

Neue Datei:

```text
.github/workflows/ci.yml
```

Trigger:

```text
push
pull_request
```

Pipeline:

```text
checkout
   |
   v
Python setup
   |
   +--> dependency install
   +--> ruff check
   +--> ruff format --check
   +--> unit tests
   +--> integration tests
```

Die CI muss die vollständige Testbaseline aus H1–H4 **und** Iteration 11H ausführen. Die H5-Spezifikation bindet sich bewusst nicht an eine feste Testanzahl; der konkrete Testbestand wird im jeweiligen Release Report dokumentiert.

---

## 27. Docker Build Workflow

Neue Datei:

```text
.github/workflows/docker.yml
```

Bei Release oder Tag wird das Image gebaut und nach GHCR veröffentlicht.

---

## 28. Dependency Updates

Dependabot konfigurieren für:

```text
pip
github-actions
docker
```

---

## 29. Dependency Security

CI erhält Dependency-Security-Scanning, z. B.:

```text
pip-audit
```

Ein Release darf keine ungeprüfte kritische Dependency-Schwachstelle enthalten.

---

## 30. Static Security Analysis

GitHub CodeQL wird aktiviert, soweit passend.

Mindestens:

```text
Python
GitHub Actions
```

---

## 31. Container Security

Docker Images werden automatisiert auf bekannte Schwachstellen geprüft, z. B. mit:

```text
Trivy
```

---

## 32. SECURITY.md

Muss enthalten:

- unterstützte Releases,
- Meldeweg für Schwachstellen,
- keine Security Reports als öffentliche Issues,
- Kontaktweg,
- Disclosure-Prozess.

---

## 33. Security Model

Neue Datei:

```text
docs/security-model.md
```

Trust Boundaries:

```text
User input
LLM output
Cypher validation
Neo4j read path
OTLP input
bounded HTTP correlation buffer
filesystem imports
```

Fundamentale Regel:

```text
LLM Output = Untrusted Input
```

Für den 11H-Correlation Buffer muss dokumentiert werden:

```text
bounded
TTL-based
no raw payload persistence
no Neo4j Span nodes
allowlisted architecture metadata only
```

Die Dokumentation muss klar unterscheiden zwischen kurzlebiger Korrelationslogik und persistierter Architecture Evidence.

---

## 34. OpenTelemetry Privacy Model

Dokumentieren:

```text
attribute allowlist
no payload persistence
no authorization headers
no cookies
no request/response bodies
no message bodies
no query parameters
no full URLs
no raw trace storage in Neo4j
```

Diese Regeln gelten ebenfalls für den 11H-Correlation Buffer. Der Buffer darf kein alternativer Rohdaten- oder Trace-Speicher werden.

Zusätzlich sind die Runtime-Evidence-Semantiken zu dokumentieren:

```text
CLIENT_SERVER  strongest correlated HTTP observation
CLIENT_ONLY    partial instrumentation with stable target identity
SERVER_ONLY    only when caller identity is reliable
UNRESOLVED     insufficient identity; do not guess
```

Weiterhin muss öffentlich festgehalten werden:

\[
ObservationCount \neq ExactRequestCount
\]

`observation_count` ist ein Architektur-Evidence-Indikator und keine abrechnungs- oder SLO-taugliche Verkehrszählung.

Für negative Findings gilt:

```text
NOT_OBSERVED_IN_WINDOW
```

kann durch qualitative Telemetry Coverage ergänzt werden, etwa:

```text
SUFFICIENT
PARTIAL
NONE
UNKNOWN
```

Es darf daraus nicht automatisch `obsolete`, `unused` oder `dead` abgeleitet werden.

---

## 35. CONTRIBUTING.md

Muss enthalten:

```text
development setup
test commands
lint commands
format commands
branch workflow
pull request rules
commit expectations
adapter contribution guide
```

---

## 36. Pull Request Requirements

Ein PR muss mindestens erfüllen:

```text
tests green
lint green
format green
no secrets
documentation updated when applicable
```

Für neue Adapter zusätzlich:

```text
unit tests
integration fixture
adapter documentation
```

---

## 37. Community Files

Mindestens:

```text
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
SUPPORT.md
```

GitHub Discussions werden für Q&A, Ideen, Show-and-Tell und Adapter-Vorschläge aktiviert.

---

## 38. Issue Templates

```text
.github/ISSUE_TEMPLATE/
├── bug.yml
├── feature.yml
├── adapter.yml
└── documentation.yml
```

---

## 39. Pull Request Template

Neue Datei:

```text
.github/pull_request_template.md
```

Checkboxen:

```text
[ ] tests added/updated
[ ] documentation updated
[ ] no secrets included
[ ] licensing compatible
[ ] backwards compatibility considered
```

---

## 40. Good First Issues

Vor Launch mindestens fünf kleine, klar beschriebene Aufgaben vorbereiten.

Labels:

```text
good first issue
help wanted
documentation
adapter
```

---

## 41. Repository Topics

Empfohlen:

```text
architecture
software-architecture
microservices
opentelemetry
openapi
asyncapi
neo4j
knowledge-graph
platform-engineering
architecture-intelligence
architecture-drift
dependency-analysis
```

---

## 42. Social Preview

GitHub Social Preview erstellen, z. B.:

```text
DECLARED                      OBSERVED

OpenAPI                       OpenTelemetry
AsyncAPI              ≠
Manifest

        Architecture Intelligence
```

---

## 43. Versionierung

Semantic Versioning.

Erster öffentlicher Release:

```text
v0.1.0
```

Alternativ:

```text
v0.1.0-alpha.1
```

Noch nicht garantiert stabil:

```text
Canonical Model
REST API
Graph Schema
Adapter SPI
Configuration format
```

---

## 44. CHANGELOG

Neue Datei:

```text
CHANGELOG.md
```

Struktur:

```text
Added
Changed
Fixed
Security
Deprecated
Removed
```

---

## 45. ROADMAP.md

Mindestens:

```text
v0.1
✓ OpenAPI
✓ AsyncAPI
✓ Evidence
✓ deterministic analyses
✓ semantic validation
✓ OpenTelemetry
✓ declared vs observed

v0.2
○ Kubernetes discovery
○ additional adapters
○ improved runtime analysis

Future
○ architecture trajectories
○ causal runtime flow analysis
○ GraphRAG
○ Architecture Wiki
○ Backstage integration
```

---

## 46. Architecture Decision Records

Neue Struktur:

```text
docs/adr/
```

Empfohlene ADRs:

```text
0001-use-neo4j.md
0002-canonical-model.md
0003-evidence-as-first-class-concept.md
0004-deterministic-before-generative.md
0005-llm-is-not-source-of-truth.md
0006-declared-vs-observed.md
0007-do-not-store-full-traces-in-neo4j.md
0008-apache-2.0-license.md
```

---

## 47. OSS Architekturprinzipien

1. Canonical model before backend-specific persistence.
2. Evidence before assertion.
3. Deterministic before generative.
4. LLM output is untrusted.
5. Declared and observed architecture are independent evidence sources.
6. Open-source core must work without a commercial API.

---

## 48. Demo Screenshot / GIF

Vor Release mindestens ein visuelles Demo-Artefakt erzeugen.

Beispiel:

```text
OrderService

Declared
  ✓ ProductService
  ✓ payment-q

Observed
  ✓ ProductService
  ✓ payment-q
  ! LegacyPricingService

Architecture Drift
  1 undocumented dependency
```

---

## 49. Veröffentlichungssicherheit

Vor Public Release prüfen:

```text
README links
LICENSE present
NOTICE reviewed
third-party licenses reviewed
no secrets
no customer names
no internal URLs
demo works
CI green
Docker image builds
security docs present
11H runtime correctness scenarios green
Collector-based runtime demo verified
```

---

## 50. Release Gate

Release wird blockiert bei:

```text
known secret in history
unknown ownership/IP issue
missing license
critical failing tests
non-working quick start
customer data present
critical unresolved security finding
11H evidence-reconciliation regression
broken cross-batch runtime correlation
runtime demo without working Collector -> AIP path
```

Vor Release müssen insbesondere folgende 11H-Szenarien grün sein:

```text
DECLARED + OBSERVED
→ declaration removed
→ OBSERVED evidence remains
→ OBSERVED_ONLY
```

und:

```text
CLIENT span in OTLP request A
SERVER span in OTLP request B
→ one correctly resolved observed REST dependency
```

---

## 51. H5 Akzeptanzkriterien

| ID | Kriterium |
|---|---|
| H5.1 | Projektlizenz ist Apache License 2.0 |
| H5.2 | `LICENSE` enthält den vollständigen Apache-2.0-Standardtext |
| H5.3 | Drittanbieter-Lizenzen sind geprüft und dokumentiert |
| H5.4 | Aktueller Codebestand enthält keine Secrets oder Kundendaten |
| H5.5 | Git-Historie ist geprüft oder bewusst neu aufgebaut |
| H5.6 | README erklärt Problem, Nutzen und Architektur |
| H5.7 | `docker compose up` liefert einen funktionierenden Basis-Quick-Start |
| H5.8 | Öffentliche Demo-Daten sind vollständig synthetisch |
| H5.9 | Die öffentliche Runtime-Demo verwendet einen OpenTelemetry Collector und ist reproduzierbar |
| H5.10 | Die Runtime-Demo demonstriert `CONFIRMED`, `OBSERVED_ONLY` und `NOT_OBSERVED_IN_WINDOW` |
| H5.11 | Die Runtime-Demo oder ein Integrationstest demonstriert `DECLARED + OBSERVED -> remove declaration -> OBSERVED_ONLY` ohne Evidence-Verlust |
| H5.12 | Canonical Model ist öffentlich dokumentiert |
| H5.13 | Graphmodell und Evidence-Modell einschließlich der 11H-Reconciliation-Invariante sind dokumentiert |
| H5.14 | `OBSERVED PROVIDES` für runtime-entdeckte stabile Provider-Operationen ist dokumentiert |
| H5.15 | OpenTelemetry-Dokumentation erklärt `CLIENT_SERVER`, `CLIENT_ONLY`, `SERVER_ONLY` und `UNRESOLVED` |
| H5.16 | OpenTelemetry-Dokumentation erklärt, dass Cross-Batch-Korrelation unterstützt wird |
| H5.17 | `NOT_OBSERVED_IN_WINDOW` und qualitative Telemetry Coverage werden korrekt dokumentiert |
| H5.18 | `observation_count` wird ausdrücklich nicht als exakte Request-Anzahl dargestellt |
| H5.19 | Adapter-Erweiterungspunkt ist dokumentiert |
| H5.20 | Plattform funktioniert ohne LLM-Konfiguration |
| H5.21 | GitHub Actions führen Lint, Unit- und Integrationstests für die vollständige H1–H4+11H-Baseline aus |
| H5.22 | Docker Image wird reproduzierbar gebaut |
| H5.23 | Dependency- und Security-Scanning sind aktiviert |
| H5.24 | `SECURITY.md` ist vorhanden |
| H5.25 | Security Model dokumentiert den bounded Correlation Buffer als Trust Boundary |
| H5.26 | OpenTelemetry Privacy Model gilt auch für temporäre Korrelationsdaten |
| H5.27 | `CONTRIBUTING.md` ist vorhanden |
| H5.28 | `CODE_OF_CONDUCT.md` ist vorhanden |
| H5.29 | Issue- und PR-Templates sind vorhanden |
| H5.30 | ROADMAP und CHANGELOG sind vorhanden |
| H5.31 | GitHub Repository Topics und Social Preview sind gesetzt |
| H5.32 | mindestens fünf `good first issue`-Tickets sind vorbereitet |
| H5.33 | `docs/specifications/` enthält H4, 11H und H5 als nachvollziehbare Designhistorie |
| H5.34 | erster öffentlicher Release kann als `v0.1.0` oder `v0.1.0-alpha.1` erstellt werden |

---

## 52. Empfohlene Implementierungsreihenfolge

### Iteration 12A – Legal & Repository Sanitization

```text
Apache-2.0 LICENSE
      ↓
dependency licenses
      ↓
secret scan
      ↓
IP/customer-content review
      ↓
history cleanup
```

### Iteration 12B – Documentation

```text
README
   ↓
architecture docs
   ↓
canonical model
   ↓
graph/evidence model
   ↓
security model
   ↓
OTel runtime / correlation semantics
   ↓
Evidence reconciliation invariant
   ↓
adapter guide
```

### Iteration 12C – Demo & Quick Start

```text
synthetic examples
      ↓
base docker compose
      ↓
Collector-based runtime demo
      ↓
CONFIRMED / OBSERVED_ONLY / NOT_OBSERVED_IN_WINDOW
      ↓
11H reconciliation scenario
      ↓
screenshots/GIF
```

### Iteration 12D – CI/CD & Security

```text
GitHub Actions
      ↓
tests
      ↓
lint
      ↓
dependency audit
      ↓
CodeQL
      ↓
container scan
      ↓
GHCR image
```

### Iteration 12E – Community Readiness

```text
CONTRIBUTING
SECURITY
CODE_OF_CONDUCT
SUPPORT
issue templates
PR template
good first issues
Discussions
```

### Iteration 12F – Release

```text
release gate
     ↓
tag
     ↓
v0.1.0
     ↓
GitHub Release
     ↓
GHCR image
     ↓
public announcement
```

---

## 53. Definition of Done

H5 ist abgeschlossen, wenn ein bisher unbeteiligter Entwickler:

```text
discover
   ↓
clone
   ↓
start
   ↓
understand
   ↓
test
   ↓
modify
   ↓
contribute
```

kann, ohne internes Wissen über das ursprüngliche Projekt zu benötigen.

Der zentrale Einstieg:

```bash
git clone <public repository>
cd architecture-intelligence
docker compose up
```

muss reproduzierbar funktionieren.

---

## 54. Zielzustand nach H5

Vor H5:

```text
Working Architecture Intelligence Project
```

Nach H5:

```text
Open Source Architecture Intelligence Project
```

mit:

```text
Apache-2.0
clean public codebase
reproducible Collector-based runtime demo
11H-hardened evidence semantics
CI
security controls
community documentation
extension points
versioned releases
```

---

## 55. Nicht-Ziele von H5

H5 implementiert ausdrücklich nicht:

```text
new architecture analyses
new AI functions
GraphRAG
Wiki
SaaS
multi-tenancy
commercial licensing
enterprise SSO
billing
managed cloud hosting
```

---

## 56. Strategische Bedeutung

Open Source wird nicht nur als Code-Veröffentlichung verstanden.

Das eigentliche Ziel lautet:

```text
Code
+
Documentation
+
Trust
+
Reproducibility
+
Extensibility
+
Community Entry Point
```

---

## 57. Lizenzangabe für README und Repository

README Footer:

```markdown
## License

Licensed under the Apache License, Version 2.0.
See [LICENSE](LICENSE).
```

SPDX:

```text
Apache-2.0
```

---

## 58. Release Recommendation

Empfohlene erste Veröffentlichung:

```text
v0.1.0
```

mit:

```text
Project Status: Experimental
License: Apache-2.0
```

Alternativ für frühes Community-Feedback:

```text
v0.1.0-alpha.1
```

Die Veröffentlichung soll nicht auf spätere Funktionen wie GraphRAG oder Architecture Wiki warten.

H1–H4 bilden zusammen mit Iteration 11H einen ausreichend eigenständigen, runtime-gehärteten technischen und fachlichen Kern für ein öffentliches Open-Source-Projekt.
