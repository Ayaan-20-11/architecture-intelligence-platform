# Specification – Architecture Intelligence Platform
## Iteration 12G – Public Repository Activation

**Version:** 0.2  
**Status:** Implementation Specification  
**Basis:** H5 Open Source Readiness Review / Iterations 12A–12F  
**Target:** Public GitHub repository activation and first public alpha release  
**License:** Apache License 2.0 (`Apache-2.0`)  
**Release target:** `v0.1.0-alpha.1` followed by `v0.1.0` after external smoke validation  
**Scope:** Operational activation of the already prepared Open-Source project on real GitHub infrastructure

---

## 1. Motivation

H5 has completed the substantive Open-Source readiness work:

```text
legal/IP review
repository sanitization
Apache-2.0 licensing
documentation
runtime demo
security model
community files
CI workflows
container build workflow
release metadata
```

The remaining open items are not product-development gaps. They depend on a live GitHub repository and therefore cannot be completed purely in the local development environment.

Iteration 12G closes this final activation gap.

The transition is:

\[
\boxed{
H5\ Release\ Ready
\rightarrow
12G\ Public\ Repository\ Activation
\rightarrow
v0.1.0\text{-alpha.1}
\rightarrow
External\ Verification
\rightarrow
v0.1.0
}
\]

---

## 2. Goal

12G turns the locally prepared OSS codebase into a real publicly usable GitHub project.

After completion:

```text
public repository exists
git remote configured
main branch pushed
GitHub Actions executed successfully
CodeQL executed successfully
GHCR publishing verified
repository settings configured
GitHub Discussions enabled
security reporting enabled
good-first-issues created
social preview configured
fresh-clone smoke test passed
v0.1.0-alpha.1 published
```

The iteration does **not** add product features.

---

## 3. Non-Goals

12G explicitly does not implement:

```text
new application features
new runtime analyses
new LLM functionality
new architecture model
Desired State
DDD integration
Promise model
GraphRAG
SaaS
multi-tenancy
enterprise SSO
billing
managed hosting
```

No application feature work is permitted in 12G unless required to fix a release-blocking defect discovered by the public activation process.

---

## 4. Preconditions

Before starting 12G, the following must already be true:

```text
LICENSE exists and is Apache-2.0
THIRD_PARTY_LICENSES.md exists
README.md is complete
SECURITY.md exists
CONTRIBUTING.md exists
CODE_OF_CONDUCT.md exists
SUPPORT.md exists
ROADMAP.md exists
CHANGELOG.md exists
Docker build succeeds locally
docker compose quick start succeeds locally
runtime demo succeeds locally
full test suite is green
ruff check is clean
ruff format --check is clean
dependency audit is clean
secret/history review is complete
```

If one of these preconditions is no longer true, 12G pauses until it is restored.

---

## 5. Release Principle

12G distinguishes explicitly between:

\[
ReleaseReady
\]

and:

\[
ReleaseVerified.
\]

Before 12G:

```text
ReleaseReady = true
ReleaseVerified = false
```

After 12G:

```text
ReleaseReady = true
ReleaseVerified = true
```

`ReleaseVerified` means that the repository has been exercised on actual GitHub infrastructure and from an external clone path.

---

## 6. 12G.1 – Create Public GitHub Repository

Create a new GitHub repository for the project.

Recommended repository name:

```text
architecture-intelligence
```

Repository visibility:

```text
Public
```

Initial repository creation should **not** auto-generate conflicting files such as:

```text
README.md
LICENSE
.gitignore
```

because the local repository already contains the canonical versions.

Required repository description:

```text
Evidence-backed architecture intelligence from OpenAPI, AsyncAPI and OpenTelemetry.
```

Alternative:

```text
Compare declared and observed microservice architecture using OpenAPI, AsyncAPI, OpenTelemetry and Neo4j.
```

---

## 7. 12G.2 – Review Public Git Identity

Before the first push, explicitly review:

```text
git log --format='%an <%ae>'
```

Decision required:

```text
public author email acceptable
```

or:

```text
history rewrite / noreply identity required
```

If an author email must not become public, fix the history **before** pushing the repository.

After first public release, history rewriting should be avoided except for serious security/privacy reasons.

---

## 8. 12G.3 – Configure Git Remote

Add the public GitHub repository as remote:

```bash
git remote add origin git@github.com:<owner>/architecture-intelligence.git
```

or HTTPS equivalent.

Verify:

```bash
git remote -v
```

Expected:

```text
origin  <repository-url> (fetch)
origin  <repository-url> (push)
```

---

## 9. 12G.4 – Verify Default Branch

The public default branch shall be:

```text
main
```

If necessary:

```bash
git branch -M main
```

Before push:

```text
git status
```

must show:

```text
working tree clean
```

---

## 10. 12G.5 – Final Pre-Push Sanitization

Immediately before the first public push, re-run:

```text
secret scan
tracked-content scan
git history scan
customer/internal name scan
```

At minimum verify absence of:

```text
API keys
passwords
tokens
private keys
certificates
connection strings
customer names
internal domains
internal URLs
real production traces
real service names
real queue names
private architecture documents
```

If any release-blocking finding is discovered:

```text
STOP
```

and remediate before continuing.

---

## 10A. Public Repository Content Policy

Before the first public push, the project must explicitly decide which files belong to the public product and which files are local/internal development material.

The guiding rule is:

\[
\boxed{
PublicRepo
=
SourceCode
+
ReproducibleDemo
+
PublicArchitectureDocumentation
+
CommunityAndReleaseFiles
}
\]

and not:

\[
\boxed{
PublicRepo \neq EntireLocalDevelopmentWorkspace
}
\]

The repository content review is a release gate, not merely a `.gitignore` hygiene task.

### 10A.1 Files that must not be published

The following categories must not be tracked or present anywhere in the public Git history:

```text
Secrets and local credentials
  .env
  .env.local
  .env.* containing real values
  API keys
  access tokens
  passwords
  connection strings
  cloud credentials

Private keys and sensitive certificates
  *.key
  private *.pem
  *.p12
  *.pfx
  *.jks
  SSH private keys

Real customer/internal artifacts
  customer OpenAPI specifications
  customer AsyncAPI specifications
  private architecture manifests
  internal ADRs not approved for publication
  customer service/queue/domain names
  internal URLs/hostnames/domains
  production infrastructure configuration

Runtime data
  Neo4j data/log/import directories
  Docker volumes
  database dumps
  real OTLP captures
  real traces/spans/logs
  production telemetry exports

Local development artifacts
  .venv
  __pycache__
  .pytest_cache
  .ruff_cache
  .mypy_cache
  IDE-local metadata
  local logs
  temporary files
  coverage/build artifacts

Local security-analysis artifacts
  local SARIF files
  CodeQL databases
  temporary vulnerability reports
```

A credential remains prohibited even if it has expired or been revoked.

---

## 10B. Environment Configuration Policy

Real `.env` files must never be committed.

The public repository may contain:

```text
.env.example
```

only if it contains placeholders or safe development defaults.

Example:

```dotenv
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change-me

LLM_ENABLED=false
OPENAI_API_KEY=
```

Forbidden:

```dotenv
OPENAI_API_KEY=<real key>
NEO4J_PASSWORD=<real private password>
```

Verification must include both current tracked files and Git history.

---

## 10C. Synthetic Fixtures and Telemetry Policy

All files under public example/test/demo areas must be reviewed for provenance.

Examples:

```text
examples/
tests/fixtures/
examples/runtime-demo/
```

They must contain only synthetic data created for the project.

In particular, do not publish sanitized copies of real production traces merely because payloads were removed. Trace metadata can still reveal:

```text
service.name
host.name
server.address
deployment.environment
trace IDs
cloud resource identifiers
internal URLs
tenant identifiers
```

Required principle:

\[
\boxed{
PublicDemoData = SyntheticByConstruction
}
\]

not merely:

\[
PublicDemoData = RedactedProductionData.
\]

---

## 10D. OpenAPI / AsyncAPI Publication Policy

Only specifications created specifically for the public demo may be published.

Allowed examples:

```text
OrderService
ProductService
PaymentService
InvoiceService
LegacyPricingService
payment-q
invoice-q
```

The names and schemas must be synthetic and independent of customer systems.

Do not publish copied-and-renamed customer specifications unless their provenance and publication rights are independently clear.

---

## 10E. Internal Development Documents

Internal development-history artifacts must be reviewed separately from public design documentation.

Default recommendation for the first public release:

```text
DO NOT publish by default:
  IMPLEMENTATION_PLAN.md
  POC_REVIEW.md
  HARDENING_REVIEW.md
  H4_REVIEW.md
  H5_REVIEW.md
  local investigation notes
  temporary review reports
```

These files typically contain internal iteration history, local implementation detail, transient findings, commit references, and information not required to understand or extend the released product.

Relevant durable information should instead live in:

```text
README.md
ROADMAP.md
CHANGELOG.md
docs/architecture.md
docs/specifications/
docs/adr/
GitHub Issues
```

A deliberate project decision may publish review documents later, but this must be explicit rather than accidental.

---

## 10F. Public Design History

The following design artifacts are intentionally public unless a separate IP/privacy review rejects a specific file:

```text
docs/specifications/
docs/adr/
docs/architecture.md
docs/canonical-model.md
docs/graph-model.md
docs/evidence.md
docs/opentelemetry.md
docs/security-model.md
```

This distinction is intentional:

\[
\boxed{
Specifications + ADRs = ProductKnowledge
}
\]

while:

\[
\boxed{
ImplementationDiary + InternalReview = InternalProcessKnowledge
}
\]

---

## 10G. Required `.gitignore`

A project-level `.gitignore` must exist before the first public push.

At minimum it should cover the actual local artifacts used by the project.

Recommended baseline:

```gitignore
# Secrets / local configuration
.env
.env.*
!.env.example

*.key
*.p12
*.pfx
*.jks
secrets/
credentials/

# Python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
.coverage.*
coverage.xml
htmlcov/
dist/
build/
*.egg-info/

# IDE / OS
.idea/
*.iml
.vscode/*
!.vscode/extensions.json
!.vscode/settings.json
.DS_Store
Thumbs.db
Desktop.ini

# Logs / temporary output
*.log
*.tmp
*.bak
*.swp
*.pid
logs/
tmp/

# Neo4j / local runtime data
neo4j-data/
neo4j-logs/
neo4j-import/
volumes/

# Runtime captures
trace-dumps/
otel-dumps/

# Local security/build reports
*.sarif
security-reports/
codeql-db/

# Local Docker overrides
docker-compose.override.yml
```

Do not globally ignore file extensions such as `*.pb` if legitimate synthetic protobuf fixtures may later be versioned. Prefer dedicated local dump directories.

---

## 10H. Required `.dockerignore`

A `.dockerignore` must exist so the Docker build context cannot accidentally include local/private artifacts.

Recommended baseline:

```dockerignore
.git
.venv
__pycache__
.pytest_cache
.ruff_cache
.mypy_cache
.idea
.vscode
.env
.env.*
htmlcov
.coverage
*.log
neo4j-data
neo4j-logs
trace-dumps
otel-dumps
security-reports
codeql-db
```

`docs/` and `tests/` may only be excluded if the image build/runtime does not require them.

---

## 10I. Tracked-File Manifest Review

Before the first push, explicitly inspect the complete set of files that will become public.

Required command or equivalent:

```bash
git ls-files
```

Review at least:

```text
all YAML/YML files
all JSON files
all example fixtures
all certificates/keys
all environment files
all telemetry samples
all architecture specifications
all root-level Markdown files
```

The objective is to detect files that are technically safe from a secret scanner but still unsuitable for publication.

---

## 10J. Ignore Rules Do Not Sanitize History

Adding a path to `.gitignore` or `.dockerignore` does not remove files already committed.

For sensitive paths, verify Git history explicitly, for example:

```bash
git log --all -- .env
git log --all -- '*.key'
git log --all -- examples/
git log --all -- trace-dumps/
```

Use dedicated secret/history scanning tooling in addition to these spot checks.

If prohibited data exists in history, either:

```text
rewrite history safely
```

or:

```text
create a new sanitized public repository history
```

before the first public push.

---

## 10K. Publication Decision Matrix

Use this classification before first push:

| Category | Default decision |
|---|---|
| Source code | PUBLIC |
| Synthetic tests/fixtures | PUBLIC |
| Synthetic runtime demo | PUBLIC |
| README / security / community files | PUBLIC |
| Specifications / ADRs | PUBLIC after IP review |
| `.env.example` | PUBLIC with placeholders only |
| Real `.env` / credentials | PRIVATE / NEVER COMMIT |
| Raw real telemetry | PRIVATE / NEVER COMMIT |
| Customer OpenAPI/AsyncAPI | PRIVATE unless explicit rights exist |
| Neo4j/runtime data | PRIVATE / GENERATED |
| Local IDE/cache/log files | PRIVATE / GENERATED |
| Local security reports | PRIVATE / GENERATED |
| Internal implementation plans/reviews | PRIVATE by default |

---

## 10L. Public Repository Content Gate

Before `git push -u origin main`, all of the following must be true:

```text
.gitignore reviewed
.dockerignore reviewed
tracked-file manifest reviewed
history scan clean
no real .env tracked
no raw real telemetry tracked
no customer API specifications tracked
no local DB/runtime data tracked
examples are synthetic by construction
internal review/implementation files have an explicit publication decision
public specifications/ADRs intentionally retained
working tree clean
```

Failure of this gate is a:

```text
RELEASE_BLOCKER
```

---

## 11. 12G.6 – Push Main Branch

Push the prepared repository:

```bash
git push -u origin main
```

No public release tag is created yet.

The first goal is to validate the repository on GitHub infrastructure.

---

## 12. 12G.7 – Verify GitHub Actions

After push, verify all workflows triggered by `push`.

Expected checks include at least:

```text
ruff check
ruff format --check
unit tests
integration tests
dependency audit
CodeQL
```

All mandatory jobs must complete successfully.

A locally green run is not sufficient for this criterion.

Required result:

```text
GitHub Actions = GREEN
```

---

## 13. GitHub-Specific Failure Handling

If CI fails only on GitHub infrastructure:

```text
reproduce if possible
fix minimally
push correction
re-run workflow
```

Typical areas to inspect:

```text
Testcontainers networking
Docker availability
permissions
working directory
Python version resolution
dependency cache
GitHub token permissions
CodeQL configuration
SARIF upload permissions
```

No unrelated refactoring should be mixed into the fix.

---

## 14. 12G.8 – Enable Repository Security Features

Enable, where available:

```text
Private Vulnerability Reporting
Secret Scanning
Push Protection
Dependabot Alerts
Dependabot Security Updates
Code Scanning
```

These settings shall align with `SECURITY.md`.

Security reports must not require posting secrets or exploit details in public Issues.

---

## 15. 12G.9 – Enable GitHub Discussions

Enable GitHub Discussions.

Recommended categories:

```text
Announcements
Q&A
Ideas
Show and tell
Architecture
Adapters
```

Usage:

```text
Issues       -> actionable bugs/features
Discussions  -> questions, ideas, design discussions
Security     -> private vulnerability reporting
```

---

## 16. 12G.10 – Configure Repository Topics

Set repository topics:

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

The exact set may be reduced to comply with GitHub limits, but must cover:

```text
architecture
microservices
opentelemetry
openapi
asyncapi
neo4j
```

---

## 17. 12G.11 – Configure Social Preview

Upload a repository Social Preview image.

Recommended concept:

```text
DECLARED                      OBSERVED

OpenAPI                       OpenTelemetry
AsyncAPI              ≠
Manifest

        Architecture Intelligence
```

The preview should:

```text
be readable at small size
avoid dense text
contain no customer branding
contain no proprietary diagrams
```

---

## 18. 12G.12 – Verify README Rendering

Inspect the README on GitHub, not only locally.

Verify:

```text
headings
tables
code blocks
diagrams
relative links
badges
LICENSE link
documentation links
Quick Start
project status
```

No broken relative link may remain.

---

## 19. 12G.13 – Create Good First Issues

Create at least five actual GitHub Issues from the prepared H5 candidates.

Each must:

```text
have a concrete scope
be independently understandable
avoid hidden project knowledge
define expected outcome
be small enough for a first contribution
```

Apply labels:

```text
good first issue
help wanted
```

and a domain label where appropriate:

```text
documentation
docker
adapter
developer-experience
```

---

## 20. Suggested Good First Issues

At least five of the following may be used:

```text
Add .dockerignore
Add Dockerfile HEALTHCHECK
Improve adapter development example
Expand local development documentation
Add troubleshooting section for runtime demo
Improve CLI output
Add one additional synthetic adapter fixture
Improve configuration examples
```

Only file issues that correspond to real, verified gaps.

---

## 21. 12G.14 – Produce Demo Screenshot or GIF

Create at least one visual demonstration before the public announcement.

Minimum content:

```text
OrderService

Declared
  ProductService
  payment-q

Observed
  ProductService
  payment-q
  LegacyPricingService

Architecture Drift
  1 observed-only dependency
```

Preferred:

```text
short GIF
```

Acceptable:

```text
high-quality screenshot
```

The visual must use synthetic demo data only.

---

## 22. 12G.15 – Verify Runtime Demo from GitHub Clone

Use a fresh directory or clean machine/container.

Execute:

```bash
git clone <public-repository>
cd architecture-intelligence
docker compose -f docker-compose.demo.yml up
```

Do not reuse:

```text
existing local volumes
existing virtualenv
existing Neo4j data
local untracked files
developer .env
```

The demo must reproduce the documented states.

---

## 23. Required Demo States

Fresh-clone runtime demo must demonstrate:

```text
CONFIRMED
OBSERVED_ONLY
NOT_OBSERVED_IN_WINDOW
```

and the OpenTelemetry path:

```text
Demo Services
      |
      v
OTel Collector
      |
      v
Architecture Intelligence Platform
      |
      v
Neo4j
```

---

## 24. 12G.16 – Verify Basic Quick Start from Fresh Clone

Separately verify the standard quick start:

```bash
git clone <public-repository>
cd architecture-intelligence
docker compose up
```

Expected:

```text
application starts
Neo4j starts
health endpoint responds
README instructions are sufficient
```

This test must be performed using only publicly available repository contents.

---

## 25. 12G.17 – Create `v0.1.0-alpha.1`

After GitHub CI and fresh-clone tests are green, create the first public pre-release:

```text
v0.1.0-alpha.1
```

This tag is intentionally used to validate the complete release pipeline before `v0.1.0`.

---

## 26. Alpha Release Notes

Release notes should include:

```text
Project status: Experimental / Alpha
License: Apache-2.0

Highlights:
- OpenAPI ingestion
- AsyncAPI queue topology
- evidence/provenance
- deterministic architecture analyses
- semantic query validation
- OpenTelemetry runtime discovery
- declared vs observed architecture
- architecture drift detection
- runtime evidence reconciliation
- cross-batch HTTP correlation
```

Also include:

```text
Known limitations
Quick Start
Documentation link
Security reporting link
```

---

## 27. 12G.18 – Verify GHCR Publishing

The alpha tag must trigger the Docker release workflow.

Verify that a package appears under:

```text
ghcr.io/<owner>/architecture-intelligence
```

Expected tag:

```text
0.1.0-alpha.1
```

or project-specific equivalent.

---

## 28. GHCR Permission Verification

If publishing fails, inspect:

```text
packages: write
contents: read
GITHUB_TOKEN permissions
package visibility
repository/package linkage
```

The workflow must not require a manually configured long-lived personal access token unless clearly justified.

Prefer:

```text
GITHUB_TOKEN
```

with minimal required permissions.

---

## 29. 12G.19 – Pull and Run the Published Image

Do not stop after successful GHCR upload.

From a fresh environment:

```bash
docker pull ghcr.io/<owner>/architecture-intelligence:0.1.0-alpha.1
```

Then run the image using the documented configuration.

Verify:

```text
container starts
non-root runtime works
health endpoint responds
Neo4j connectivity works
no local source checkout is required
```

This proves the published artifact itself is usable.

---

## 30. 12G.20 – Verify Release Assets and Links

Inspect the GitHub Release page.

Verify:

```text
tag correct
release marked pre-release
README links work
GHCR image exists
LICENSE visible
CHANGELOG consistent
documentation links resolve
security reporting path works
```

---

## 31. 12G.21 – External Smoke Test

Before promoting to `v0.1.0`, perform at least one smoke test from outside the maintainer's existing workspace.

Acceptable:

```text
different machine
clean VM
clean container environment
independent developer
```

Required scenario:

```text
clone
read README
start quick start
run one documented analysis
```

The tester should not require undocumented knowledge.

---

## 32. External Smoke Test Questions

Capture at least:

```text
Was installation understandable?
Did docker compose start successfully?
Was the value proposition clear?
Could the demo be understood?
Were any undocumented environment variables required?
Were any links broken?
Was the declared-vs-observed concept understandable?
```

Any blocker must be fixed before `v0.1.0`.

---

## 33. 12G.22 – Release Promotion Decision

After the alpha validation, decide whether:

```text
v0.1.0
```

can be published.

Promotion requires:

```text
GitHub CI green
CodeQL green or findings reviewed
dependency audit clean
GHCR publish works
published image runs
fresh clone quick start works
runtime demo works
repository settings complete
good first issues filed
security reporting enabled
no release-blocking feedback from smoke test
```

---

## 34. 12G.23 – Create `v0.1.0`

If all promotion criteria are met:

```text
tag: v0.1.0
```

Release status:

```text
Public
Experimental
```

Do not claim:

```text
API stability
production certification
enterprise support SLA
backward compatibility before v1.0
```

unless separately guaranteed.

---

## 35. `v0.1.0` Release Notes

Recommended structure:

```text
Architecture Intelligence Platform v0.1.0

What it does
Highlights
Quick Start
Declared vs Observed
Runtime Demo
Security Model
Known Limitations
Roadmap
Contributing
License
```

---

## 36. 12G.24 – Verify Final Release Pipeline

After creating `v0.1.0`, verify:

```text
GitHub Release exists
Docker workflow succeeded
GHCR v0.1.0 image exists
latest/version tags are correct
Trivy report uploaded
CodeQL remains green
```

---

## 37. 12G.25 – Public Announcement Readiness

Prepare, but do not necessarily execute automatically, the first public announcement.

Channels may include:

```text
LinkedIn
Hacker News / Show HN
OpenTelemetry community
AsyncAPI community
Neo4j community
relevant architecture/platform-engineering communities
```

The announcement should focus on:

```text
problem
working demo
declared vs observed architecture
architecture drift
open-source repository
```

not on implementation details alone.

---

## 38. Repository Positioning

Preferred value proposition:

```text
Know what your architecture says.
Know what it actually does.
```

Longer form:

```text
Build an evidence-backed architecture knowledge graph from
OpenAPI, AsyncAPI and OpenTelemetry — and discover where
declared and observed architecture diverge.
```

---

## 39. Public Architecture Message

The public architecture should show:

```text
OpenAPI
AsyncAPI
Manifest
    |
    v
Declared Architecture
    |
    +--------------------+
                         |
                         v
                   Evidence Graph
                         ^
                         |
Observed Architecture   |
      ^                  |
      |                  |
OpenTelemetry Collector |
      ^                  |
      |                  |
   Services -------------+
```

AIP must be presented as:

```text
architecture telemetry consumer
```

not:

```text
general tracing backend
```

---

## 40. Security Release Gate

Public release is blocked if any of the following is true:

```text
known secret in repository/history
unknown ownership/IP issue
critical failing tests
GitHub Actions failing
critical unreviewed dependency vulnerability
critical unreviewed CodeQL finding
published container cannot start
fresh clone quick start fails
runtime demo fails
security reporting path unavailable
customer/internal data found
raw real telemetry or production captures found
real `.env` / credentials tracked
customer OpenAPI/AsyncAPI fixtures found without explicit publication rights
local Neo4j/runtime data tracked
internal development/review files published without explicit decision
missing or ineffective `.gitignore` / `.dockerignore`
```

---

## 41. GitHub Infrastructure Gate

Public `v0.1.0` is also blocked if:

```text
GHCR publishing has never succeeded
CI has never succeeded on GitHub
fresh clone was never tested
```

Local validation alone is insufficient for final H5 closure.

---

## 42. Acceptance Criteria

| ID | Criterion |
|---|---|
| 12G.1 | Public GitHub repository exists |
| 12G.2 | Public Git identity / author email has been explicitly reviewed |
| 12G.3 | `origin` remote is configured correctly |
| 12G.4 | `main` is the public default branch |
| 12G.5 | Final pre-push secret/IP/history scan is clean |
| 12G.6 | Main branch has been pushed successfully |
| 12G.7 | GitHub Actions lint/unit/integration pipeline is green |
| 12G.8 | Dependency audit workflow is green |
| 12G.9 | CodeQL has executed successfully or findings are explicitly reviewed |
| 12G.10 | Repository security features are enabled where available |
| 12G.11 | GitHub Discussions are enabled |
| 12G.12 | Repository topics are configured |
| 12G.13 | Social Preview is configured |
| 12G.14 | README renders correctly on GitHub with no broken internal links |
| 12G.15 | At least five actual `good first issue` tickets exist |
| 12G.16 | At least one synthetic demo screenshot/GIF exists |
| 12G.17 | Fresh-clone runtime demo works |
| 12G.18 | Fresh-clone standard `docker compose up` quick start works |
| 12G.19 | `v0.1.0-alpha.1` GitHub pre-release exists |
| 12G.20 | Alpha tag successfully publishes a GHCR image |
| 12G.21 | Published GHCR image can be pulled and started from a clean environment |
| 12G.22 | Release page links and assets are verified |
| 12G.23 | At least one external/clean-environment smoke test is completed |
| 12G.24 | Smoke test produced no unresolved release blocker |
| 12G.25 | `v0.1.0` promotion decision is explicitly made |
| 12G.26 | If approved, `v0.1.0` GitHub Release exists |
| 12G.27 | `v0.1.0` GHCR image exists and is runnable |
| 12G.28 | H5.31 repository topics/social preview is fully satisfied |
| 12G.29 | H5.32 good-first-issues requirement is fully satisfied |
| 12G.30 | H5.34 release execution is completed, not merely release-ready |
| 12G.31 | `.gitignore` exists and excludes secrets, local runtime data, caches, logs, and generated artifacts |
| 12G.32 | `.dockerignore` exists and excludes local/private build-context content |
| 12G.33 | No real `.env`, credential, private-key, or sensitive certificate file is tracked or present in public history |
| 12G.34 | No real/raw OpenTelemetry trace or production telemetry capture is published |
| 12G.35 | No customer/internal OpenAPI, AsyncAPI, infrastructure, or architecture artifact is published without explicit rights |
| 12G.36 | All public examples and telemetry fixtures are synthetic by construction |
| 12G.37 | Neo4j data, Docker volumes, IDE files, caches, logs, local scan reports, and similar generated artifacts are untracked |
| 12G.38 | Internal implementation plans/review documents have an explicit publication decision and are private by default |
| 12G.39 | Public specifications and ADRs intentionally remain available as product/design documentation |
| 12G.40 | `git ls-files` tracked-file manifest has been manually reviewed before first push |
| 12G.41 | Git history has been checked for prohibited files; ignore rules are not relied on as history sanitization |
| 12G.42 | Public Repository Content Gate passes before the first push |

---

## 43. Recommended Execution Order

```text
12G-A  Repository creation
       ↓
12G-B  Identity/history review
       ↓
12G-B2 Public repository content gate
       (.gitignore/.dockerignore, tracked files, fixtures, internal docs)
       ↓
12G-C  Remote + first push
       ↓
12G-D  GitHub Actions verification
       ↓
12G-E  Repository settings/security
       ↓
12G-F  Discussions/topics/social preview
       ↓
12G-G  Good first issues
       ↓
12G-H  Screenshot/GIF
       ↓
12G-I  Fresh-clone validation
       ↓
12G-J  v0.1.0-alpha.1
       ↓
12G-K  GHCR pull/run verification
       ↓
12G-L  External smoke test
       ↓
12G-M  v0.1.0 decision/release
```

---

## 44. Failure Policy

If 12G exposes a defect, classify it as:

```text
RELEASE_BLOCKER
NON_BLOCKING
DOCUMENTATION
INFRASTRUCTURE
```

Examples:

```text
CI does not run on GitHub               RELEASE_BLOCKER
fresh clone cannot start                RELEASE_BLOCKER
GHCR image cannot start                 RELEASE_BLOCKER
broken README link                      DOCUMENTATION
real `.env` or credential tracked        RELEASE_BLOCKER
real production telemetry tracked        RELEASE_BLOCKER
customer spec published without rights   RELEASE_BLOCKER
internal review note accidentally public RELEASE_BLOCKER until reviewed
missing social preview                  NON_BLOCKING before alpha,
                                        required before H5 closure
GitHub transient outage                 INFRASTRUCTURE
```

Do not bypass a release blocker merely to complete the iteration.

---

## 45. Definition of Done

Iteration 12G is complete when:

\[
\boxed{
Local\ OSS\ Readiness
\rightarrow
Public\ GitHub\ OSS\ Reality
}
\]

has been demonstrated.

Concretely, an independent user must be able to:

```text
find repository
      ↓
clone repository
      ↓
read README
      ↓
start project
      ↓
run demo
      ↓
understand declared vs observed
      ↓
open issue/discussion
      ↓
use published container
```

without private knowledge or local maintainer state.

---

## 46. H5 Closure

After successful 12G completion:

```text
H5.31 = COMPLETE
H5.32 = COMPLETE
H5.34 = EXECUTED
```

H5 may then be marked:

\[
\boxed{
34/34\ COMPLETE
}
\]

and:

```text
Open Source Readiness = DONE
```

---

## 47. Target State

Final state:

```text
Architecture Intelligence Platform

GitHub:
  Public

License:
  Apache-2.0

Release:
  v0.1.0

Status:
  Experimental

CI:
  Green

Container:
  Published on GHCR

Demo:
  Reproducible

Security:
  Reporting enabled

Community:
  Discussions + Issues enabled
```

---

## 48. Strategic Outcome

12G is intentionally operational rather than architectural.

Its purpose is to cross the boundary:

\[
\boxed{
Project\ prepared\ for\ Open\ Source
}
\]

to:

\[
\boxed{
Actual\ Open\ Source\ Project
}
\]

Only after this transition should further feature iterations resume.

The next development phase should be informed not only by the internal roadmap, but also by:

```text
external feedback
GitHub issues
community questions
real deployment friction
adapter requests
architecture use cases
```

This prevents the project from continuing purely as an internally designed system after its public release.
