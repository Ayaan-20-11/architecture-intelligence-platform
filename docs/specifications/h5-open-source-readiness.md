# Specification – Architecture Intelligence Platform
## H5 – Open Source Readiness

**Version:** 0.5  
**Status:** Implementation Specification  
**Basis:** PoC Iterations 0–11G / H1–H4 completed + Iteration 11H Runtime Correctness & Robustness  
**License:** Apache License 2.0 (`Apache-2.0`)  
**Target Platform:** GitHub  
**Primary Technology:** Python 3.13, FastAPI, Pydantic, Neo4j, OpenTelemetry Collector  
**Scope:** Preparing the existing project for a public open-source release on GitHub

---

## 1. Starting Point

After completion of H1–H4 and the subsequent Iteration 11H, the Architecture Intelligence Platform has a technically robust, runtime-hardened core:

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

Building on this:

```text
deterministic analyses A1-A5
runtime analyses O1-O5
declared vs observed comparison
semantic Cypher validation
constrained natural-language query layer
```

11H tightens the runtime semantics in particular through:

```text
independent DECLARED / OBSERVED evidence
safe relation reconciliation
cross-batch HTTP correlation
partial-instrumentation handling
observed provider semantics
coverage qualification
realistic Collector-based demo topology
```

H5 does not introduce **any new functional Architecture Intelligence capability**.

Instead, the state reached through H1–H4 + 11H is prepared so that external developers can understand it, use it legally, start it safely, test it reproducibly, extend it, and contribute to it.

H5 is therefore a productization and release phase.

---

## 2. Objective

The target state is:

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

After H5, the project should be:

- legally publishable,
- secure by default,
- easy to understand,
- easy to start,
- easy to test,
- easy to contribute to,
- easy to extend

The release will be labeled as `Experimental` or `Alpha`.

---

## 3. Licensing Model

### 3.1 Project License

The project is published under the:

**Apache License 2.0**

SPDX identifier:

```text
Apache-2.0
```

Repository file:

```text
LICENSE
```

The file must contain the complete, unmodified standard text of the Apache License 2.0.

### 3.2 Reasons for Apache 2.0

The license was chosen because it:

- allows commercial use,
- allows modification and redistribution,
- allows private use,
- contains explicit patent provisions,
- is widely used in infrastructure, cloud, and enterprise projects,
- fits a possible future consulting or enterprise business.

### 3.3 SPDX Header

Source files may optionally include:

```text
SPDX-License-Identifier: Apache-2.0
```

Optionally, in addition:

```text
Copyright <YEAR> <PROJECT OWNER>
```

### 3.4 NOTICE

It will be checked whether a file:

```text
NOTICE
```

is required or useful.

### 3.5 Third-Party Licenses

New file:

```text
THIRD_PARTY_LICENSES.md
```

It documents at least:

```text
dependency
version
license
source/project URL
notes
```

All direct production dependencies must be reviewed before release.

---

## 4. Publication Only from a Sanitized Codebase

Before publication, the repository must be fully checked for:

- customer data,
- internal company names,
- real service names,
- queue names,
- internal URLs,
- hostnames,
- API keys,
- passwords,
- `.env` files,
- tokens,
- certificates,
- private keys,
- cloud resource IDs,
- internal architecture diagrams,
- real OpenAPI/AsyncAPI files,
- real OpenTelemetry traces.

This review explicitly applies to the entire Git history.

If the existing history cannot be published beyond doubt, a new public repository will be built from a sanitized export.

---

## 5. Secret Scanning

Before the first public push, a local secret scan is performed.

At minimum, check for:

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

After publication, GitHub Secret Scanning is enabled where available.

---

## 6. Repository Structure

Target structure:

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

## 7. Project Name

Working name:

```text
architecture-intelligence
```

Requirements:

- short,
- unambiguous,
- technically understandable,
- does not conflict with an existing trademark,
- suitable for GitHub search,
- optionally usable later as a Python package.

Before publication, a name and trademark check is required.

---

## 8. Repository Description

Proposed:

```text
Evidence-backed architecture intelligence from OpenAPI, AsyncAPI and OpenTelemetry.
```

Alternative:

```text
Compare declared and observed microservice architecture using OpenAPI, AsyncAPI, OpenTelemetry and Neo4j.
```

---

## 9. Positioning

The project is not primarily positioned as an LLM tool, Neo4j tool, API parser, or service catalog.

Core message:

```text
Declared Architecture vs. Observed Architecture
```

Short form:

```text
Know what your architecture says.
Know what it actually does.
```

---

## 10. README

A new visitor should understand, within about two minutes:

- what problem is being solved,
- how the platform works,
- why it is different,
- how to start it.

Recommended structure:

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

## 11. README Feature List

At least:

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

The README may group these points in a user-friendly form; the internal terms `CLIENT_SERVER`, `CLIENT_ONLY`, and `SERVER_ONLY` do not need to be part of the hero section, but should be explained in the OpenTelemetry documentation.

---

## 12. Quick Start

Ideally:

```bash
git clone <repository>
cd architecture-intelligence
docker compose up
```

Then:

```text
http://localhost:8000
```

Prerequisites:

```text
Docker
Docker Compose
```

Optional for local development:

```text
Python 3.13
```

---

## 13. Demo Data

All public demo data must be fully synthetic.

Example:

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

## 14. Demo Landscape

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

Additionally in H4:

```text
OrderService
    |
    +---- OBSERVED ONLY ---> LegacyPricingService
```

---

## 15. Runtime Demo

Following 11H, the public runtime demo is mandatorily Collector-based.

New demo:

```text
examples/runtime-demo/
```

Contains at least:

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

Reference topology:

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

The demo must make clear:

```text
AIP is an additional telemetry consumer,
not the primary observability backend.
```

Expected states:

```text
CONFIRMED
OBSERVED_ONLY
NOT_OBSERVED_IN_WINDOW
```

At least one scenario must demonstrate the 11H reconciliation invariant:

```text
initially:
DECLARED + OBSERVED = CONFIRMED

remove declaration on re-import:
OBSERVED remains = OBSERVED_ONLY
```

Optionally, but recommended, an additional cross-batch scenario is included, in which CLIENT and SERVER spans arrive in separate OTLP requests and are nonetheless correlated to the same observed REST dependency.

---

## 16. Documentation

Target structure:

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

## 17. Canonical Model Documentation

At least the following entities:

```text
Service
Operation
Queue
Message
Schema
Evidence
```

and relations:

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

## 18. Graph Model Documentation

Explicitly document:

```text
Service -[:PROVIDES]-> Operation
Service -[:CALLS]-> Operation
Service -[:SENDS]-> Queue
Service -[:RECEIVES_FROM]-> Queue
Queue -[:CARRIES]-> Message
Message -[:CONFORMS_TO]-> Schema
```

Additionally:

```text
Fact + Evidence
DECLARED
OBSERVED
CONFIRMED
OBSERVED_ONLY
NOT_OBSERVED_IN_WINDOW
```

Following 11H, the public graph/evidence documentation must also make the following invariants explicit:

\[
Fact\ exists\ iff\ supporting\ Evidence\ exists
\]

and:

\[
Removing\ DECLARED\ evidence
\not\Rightarrow
removing\ OBSERVED\ evidence
\]

This means in particular:

```text
DECLARED + OBSERVED
       |
remove stale declaration
       v
OBSERVED_ONLY
```

A relation may only be deleted once no supporting evidence remains at all.

For runtime-discovered stable provider operations, it must also be documented that:

```text
Service -[:PROVIDES {OBSERVED evidence}]-> ObservedOnlyOperation
```

is permitted. A later OpenAPI declaration must be reconcilable with the same logical operation without losing the observed evidence.

---

## 19. Adapter Extension Point

Conceptual interface:

```python
class ArchitectureSourceAdapter(Protocol):
    def supports(self, source: Source) -> bool:
        ...
    def load(self, source: Source) -> ArchitectureModel:
        ...
```

For runtime sources:

```python
class ObservationSourceAdapter(Protocol):
    def ingest(self, source: Any) -> ObservationBatch:
        ...
```

New documentation:

```text
docs/adapter-development.md
```

---

## 20. Externalize Configuration

All installation-dependent values must be controllable via configuration or environment variables.

Example:

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

11H-specific settings must be optional and have safe defaults. Missing new properties must not prevent an existing configuration from starting.

---

## 21. LLM Remains Optional

Fundamental OSS requirement:

```text
Core Platform Works Without LLM
```

The platform must be able to start fully without OpenAI, Azure OpenAI, Anthropic, or Ollama.

Deterministic analyses must function independently of the LLM.

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

The first release may still implement only a single provider.

---

## 23. Python Packaging

`pyproject.toml` must contain complete project metadata.

Example:

```toml
[project]
name = "architecture-intelligence"
version = "0.1.0"
description = "Evidence-backed architecture intelligence from OpenAPI, AsyncAPI and OpenTelemetry"
license = {text = "Apache-2.0"}
requires-python = ">=3.13"
```

Additionally:

```text
authors
keywords
classifiers
project URLs
```

---

## 24. Docker Image

Target:

```text
ghcr.io/<owner>/architecture-intelligence:<version>
```

Requirements:

- Multi-stage build,
- no root user in the runtime container,
- minimal runtime dependencies,
- reproducible build,
- explicit versioning.

---

## 25. Health Endpoints

At least:

```text
GET /health
```

Optional:

```text
GET /ready
```

`/ready` additionally checks Neo4j and required initialization.

---

## 26. GitHub Actions – CI

New file:

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

The CI must run the complete test baseline from H1–H4 **and** Iteration 11H. The H5 specification deliberately does not commit to a fixed test count; the concrete test suite is documented in the respective release report.

---

## 27. Docker Build Workflow

New file:

```text
.github/workflows/docker.yml
```

On release or tag, the image is built and published to GHCR.

---

## 28. Dependency Updates

Configure Dependabot for:

```text
pip
github-actions
docker
```

---

## 29. Dependency Security

CI receives dependency security scanning, e.g.:

```text
pip-audit
```

A release must not contain any unreviewed critical dependency vulnerability.

---

## 30. Static Security Analysis

GitHub CodeQL is enabled where applicable.

At least:

```text
Python
GitHub Actions
```

---

## 31. Container Security

Docker images are automatically scanned for known vulnerabilities, e.g. with:

```text
Trivy
```

---

## 32. SECURITY.md

Must contain:

- supported releases,
- reporting path for vulnerabilities,
- no security reports as public issues,
- contact channel,
- disclosure process.

---

## 33. Security Model

New file:

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

Fundamental rule:

```text
LLM Output = Untrusted Input
```

For the 11H correlation buffer, the following must be documented:

```text
bounded
TTL-based
no raw payload persistence
no Neo4j Span nodes
allowlisted architecture metadata only
```

The documentation must clearly distinguish between short-lived correlation logic and persisted architecture evidence.

---

## 34. OpenTelemetry Privacy Model

Document:

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

These rules also apply to the 11H correlation buffer. The buffer must not become an alternative store for raw data or traces.

Additionally, the runtime evidence semantics must be documented:

```text
CLIENT_SERVER  strongest correlated HTTP observation
CLIENT_ONLY    partial instrumentation with stable target identity
SERVER_ONLY    only when caller identity is reliable
UNRESOLVED     insufficient identity; do not guess
```

Furthermore, it must be publicly stated that:

\[
ObservationCount \neq ExactRequestCount
\]

`observation_count` is an architecture evidence indicator, not a billing- or SLO-grade traffic count.

For negative findings, the following applies:

```text
NOT_OBSERVED_IN_WINDOW
```

can be supplemented by qualitative telemetry coverage, such as:

```text
SUFFICIENT
PARTIAL
NONE
UNKNOWN
```

It must not be automatically inferred from this that something is `obsolete`, `unused`, or `dead`.

---

## 35. CONTRIBUTING.md

Must contain:

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

A PR must at least satisfy:

```text
tests green
lint green
format green
no secrets
documentation updated when applicable
```

Additionally, for new adapters:

```text
unit tests
integration fixture
adapter documentation
```

---

## 37. Community Files

At least:

```text
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
SUPPORT.md
```

GitHub Discussions is enabled for Q&A, ideas, show-and-tell, and adapter proposals.

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

New file:

```text
.github/pull_request_template.md
```

Checkboxes:

```text
[ ] tests added/updated
[ ] documentation updated
[ ] no secrets included
[ ] licensing compatible
[ ] backwards compatibility considered
```

---

## 40. Good First Issues

Before launch, prepare at least five small, clearly described tasks.

Labels:

```text
good first issue
help wanted
documentation
adapter
```

---

## 41. Repository Topics

Recommended:

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

Create a GitHub social preview, e.g.:

```text
DECLARED                      OBSERVED

OpenAPI                       OpenTelemetry
AsyncAPI              ≠
Manifest

        Architecture Intelligence
```

---

## 43. Versioning

Semantic Versioning.

First public release:

```text
v0.1.0
```

Alternatively:

```text
v0.1.0-alpha.1
```

Not yet guaranteed stable:

```text
Canonical Model
REST API
Graph Schema
Adapter SPI
Configuration format
```

---

## 44. CHANGELOG

New file:

```text
CHANGELOG.md
```

Structure:

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

At least:

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

New structure:

```text
docs/adr/
```

Recommended ADRs:

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

## 47. OSS Architecture Principles

1. Canonical model before backend-specific persistence.
2. Evidence before assertion.
3. Deterministic before generative.
4. LLM output is untrusted.
5. Declared and observed architecture are independent evidence sources.
6. Open-source core must work without a commercial API.

---

## 48. Demo Screenshot / GIF

Before release, produce at least one visual demo artifact.

Example:

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

## 49. Publication Safety

Check before public release:

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

Release is blocked in case of:

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

Before release, in particular the following 11H scenarios must be green:

```text
DECLARED + OBSERVED
→ declaration removed
→ OBSERVED evidence remains
→ OBSERVED_ONLY
```

and:

```text
CLIENT span in OTLP request A
SERVER span in OTLP request B
→ one correctly resolved observed REST dependency
```

---

## 51. H5 Acceptance Criteria

| ID | Criterion |
|---|---|
| H5.1 | Project license is Apache License 2.0 |
| H5.2 | `LICENSE` contains the complete Apache-2.0 standard text |
| H5.3 | Third-party licenses are reviewed and documented |
| H5.4 | The current codebase contains no secrets or customer data |
| H5.5 | Git history is reviewed or deliberately rebuilt |
| H5.6 | README explains the problem, benefit, and architecture |
| H5.7 | `docker compose up` provides a working basic quick start |
| H5.8 | Public demo data is fully synthetic |
| H5.9 | The public runtime demo uses an OpenTelemetry Collector and is reproducible |
| H5.10 | The runtime demo demonstrates `CONFIRMED`, `OBSERVED_ONLY`, and `NOT_OBSERVED_IN_WINDOW` |
| H5.11 | The runtime demo or an integration test demonstrates `DECLARED + OBSERVED -> remove declaration -> OBSERVED_ONLY` without loss of evidence |
| H5.12 | Canonical Model is publicly documented |
| H5.13 | Graph model and Evidence model, including the 11H reconciliation invariant, are documented |
| H5.14 | `OBSERVED PROVIDES` for runtime-discovered stable provider operations is documented |
| H5.15 | OpenTelemetry documentation explains `CLIENT_SERVER`, `CLIENT_ONLY`, `SERVER_ONLY`, and `UNRESOLVED` |
| H5.16 | OpenTelemetry documentation explains that cross-batch correlation is supported |
| H5.17 | `NOT_OBSERVED_IN_WINDOW` and qualitative telemetry coverage are correctly documented |
| H5.18 | `observation_count` is explicitly not presented as an exact request count |
| H5.19 | Adapter extension point is documented |
| H5.20 | Platform functions without LLM configuration |
| H5.21 | GitHub Actions run lint, unit, and integration tests for the complete H1–H4+11H baseline |
| H5.22 | Docker image is built reproducibly |
| H5.23 | Dependency and security scanning are enabled |
| H5.24 | `SECURITY.md` is present |
| H5.25 | Security Model documents the bounded correlation buffer as a trust boundary |
| H5.26 | OpenTelemetry Privacy Model also applies to temporary correlation data |
| H5.27 | `CONTRIBUTING.md` is present |
| H5.28 | `CODE_OF_CONDUCT.md` is present |
| H5.29 | Issue and PR templates are present |
| H5.30 | ROADMAP and CHANGELOG are present |
| H5.31 | GitHub repository topics and social preview are set |
| H5.32 | at least five `good first issue` tickets are prepared |
| H5.33 | `docs/specifications/` contains H4, 11H, and H5 as a traceable design history |
| H5.34 | the first public release can be created as `v0.1.0` or `v0.1.0-alpha.1` |

---

## 52. Recommended Implementation Order

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

H5 is complete when a previously uninvolved developer can:

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

without needing any internal knowledge of the original project.

The central entry point:

```bash
git clone <public repository>
cd architecture-intelligence
docker compose up
```

must work reproducibly.

---

## 54. Target State After H5

Before H5:

```text
Working Architecture Intelligence Project
```

After H5:

```text
Open Source Architecture Intelligence Project
```

with:

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

## 55. Non-Goals of H5

H5 explicitly does not implement:

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

## 56. Strategic Significance

Open source is not understood merely as a code release.

The actual goal is:

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

## 57. License Statement for README and Repository

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

Recommended first release:

```text
v0.1.0
```

with:

```text
Project Status: Experimental
License: Apache-2.0
```

Alternatively, for early community feedback:

```text
v0.1.0-alpha.1
```

The release should not wait for later features such as GraphRAG or Architecture Wiki.

H1–H4, together with Iteration 11H, form a sufficiently self-contained, runtime-hardened technical and functional core for a public open-source project.
