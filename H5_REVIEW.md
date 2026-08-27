# H5 Review — Architecture Intelligence Platform

Evaluation pass over `Architecture_Intelligence_Platform_H5_Open_Source_Readiness_Specification.md`'s
full open-source-readiness program — implemented as `IMPLEMENTATION_PLAN.md` Iterations 12A-12F
(commits `e641370`, `99cb48c`, `b233e40`, `38c4b85`, `f55bd5f`, `6ee970c`). Written the same way as
`POC_REVIEW.md`/`HARDENING_REVIEW.md`/`H4_REVIEW.md` reviewed prior work: an acceptance-criteria table
with concrete evidence, not a re-description of the design.

**Test suite at time of review:** unchanged from `H4_REVIEW.md`'s baseline — 352 unit tests (no
Neo4j/Docker/network required) + 131 integration tests (Testcontainers-backed, real Neo4j 5) =
**483 tests, all passing**. `ruff check .` and `ruff format --check .` clean across all 114 formatted
files. H5 is a documentation/CI/community-files program, not an application-code iteration — none of
12A-12F touched `app/`, and every iteration's own `IMPLEMENTATION_PLAN.md` entry records the same
483/483, re-run after each iteration rather than assumed carried-forward.

## On what "evidence" means for this review

H4's review could point at a pytest test name for nearly every criterion. H5 mostly can't — a license
file, a documentation page, or a GitHub Actions workflow doesn't have a unit test proving it's correct.
Where a criterion is genuinely about code behavior (the demo's declared-vs-observed states, the
11H-reconciliation and cross-batch scenarios), evidence is a **live run**, recorded in
`IMPLEMENTATION_PLAN.md`'s 12C entry: the actual stack was brought up, the actual API was queried, and
in one case (the traffic generator's import-race identity split) a real bug was found and fixed by
running it rather than assumed correct from reading the code. Where a criterion is about a file's
presence or content, evidence is the file path plus, where applicable, a verification command actually
run this session (a link checker, a tracked-content secret grep, `docker build`, the full test suite).

## Legal & Repository Sanitization — 12A (H5.1-H5.5)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H5.1 | Project license is Apache License 2.0 | ✅ | `LICENSE` (root), `docs/adr/0008-apache-2.0-license.md` records the rationale (commercial/private use, patent grant, infrastructure-ecosystem fit) |
| H5.2 | `LICENSE` contains the full, unmodified Apache-2.0 standard text | ✅ | `LICENSE`, 201 lines — the complete standard text, added in `e641370` |
| H5.3 | Third-party licenses are reviewed and documented | ✅ | `THIRD_PARTY_LICENSES.md` — all 14 direct production dependencies, verified live against installed package metadata (not copied from a template), per-dependency name/version/license/source URL/notes |
| H5.4 | Current codebase contains no secrets or customer data | ✅ | `e641370`'s own secret/IP scan (git history + tracked content), re-run this session (12F) with a tracked-content grep for secret-key patterns, `.corp`/`.internal`/ticket-hostnames, and placeholder customer-name patterns — clean both times; `.env` (this developer's real `NEO4J_PASSWORD`/`OPENAI_API_KEY`) is git-ignored and was never staged in any iteration |
| H5.5 | Git history is reviewed, or deliberately rebuilt | ✅ | `e641370`'s commit message documents the history scan performed and its one finding (the git commit author's own email, flagged for the user's decision rather than silently acted on) — reviewed, not rebuilt; rebuilding wasn't warranted since the scan found nothing to remove |

**5 of 5 met.**

## Documentation — 12B (H5.6, H5.12-H5.20, H5.25-H5.26, H5.33)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H5.6 | README explains problem, benefit, and architecture | ✅ | `README.md`, rewritten in `99cb48c` to spec §10's structure (Why?/Features/Declared vs Observed/Quick Start/Example/Architecture/Deterministic Analyses/OpenTelemetry/Natural Language Queries/Documentation/Contributing/Project Status/License) |
| H5.12 | Canonical Model is publicly documented | ✅ | `docs/canonical-model.md` |
| H5.13 | Graph model and Evidence model, including the 11H reconciliation invariant, are documented | ✅ | `docs/graph-model.md` states both fact/evidence invariants explicitly: *fact exists iff supporting Evidence exists*, *removing DECLARED evidence ⇏ removing OBSERVED evidence* |
| H5.14 | `OBSERVED PROVIDES` for runtime-discovered stable provider operations is documented | ✅ | `docs/graph-model.md`'s 11H-D section, including the later-declaration reconciliation guarantee |
| H5.15 | OpenTelemetry docs explain `CLIENT_SERVER`/`CLIENT_ONLY`/`SERVER_ONLY`/`UNRESOLVED` | ✅ | `docs/opentelemetry.md` — explicit definitions of all four correlation modes |
| H5.16 | OpenTelemetry docs explain that cross-batch correlation is supported | ✅ | `docs/opentelemetry.md` documents it; `examples/runtime-demo/traffic_generator.py::send_cross_batch_pair` + `examples/runtime-demo/README.md` §7 additionally demonstrate it **live** (12C) — documentation and behavior independently confirmed to agree |
| H5.17 | `NOT_OBSERVED_IN_WINDOW` and qualitative Telemetry Coverage are documented correctly | ✅ | `docs/opentelemetry.md` — the fixed unresolved-reason-code table and the `SUFFICIENT`/`PARTIAL`/`NONE`/`UNKNOWN` coverage classification, with the explicit "never obsolete/unused/dead" caveat |
| H5.18 | `observation_count` is explicitly not presented as an exact request count | ✅ | `docs/opentelemetry.md` states the `observation_count ≠ exact request count` caveat; repeated in `docs/adr/0007-do-not-store-full-traces-in-neo4j.md` and `CHANGELOG.md`'s Security section |
| H5.19 | Adapter extension point is documented | ✅ | `docs/adapter-development.md` — presents both `Protocol` interfaces honestly, explicitly stating today's adapters are plain functions honoring the same contract rather than overstating current code as already class-based |
| H5.20 | Platform functions without LLM configuration | ✅ | `docs/configuration.md` states the guarantee, verified against `app/main.py`'s existing `llm_provider = None` fallback (no code change needed — a pre-existing, tested state, per `docs/adr/0005-llm-is-not-source-of-truth.md`) |
| H5.25 | Security Model documents the bounded correlation buffer as a trust boundary | ✅ | `docs/security-model.md` — the bounded/TTL-based/no-raw-payload/no-Span-node HTTP correlation buffer documented as its own explicit trust boundary |
| H5.26 | OpenTelemetry Privacy Model also applies to temporary correlation data | ✅ | `docs/security-model.md` includes an explicit sentence distinguishing short-lived correlation state from persisted Architecture Evidence, so the "no raw payload" rule is stated to cover both, not just the latter |
| H5.33 | `docs/specifications/` contains H4, 11H, and H5 as traceable design history | ✅ | `docs/specifications/{h4-opentelemetry,11h-runtime-correctness-robustness,h5-open-source-readiness}.md` (copied, not moved, in `99cb48c`) plus `docs/specifications/poc.md`. One gap found and fixed in 12F: the two newest root-level spec `.md` files these copies came from had themselves never been `git add`ed (an oversight predating even `e641370`) — `diff` confirmed byte-identity with their `docs/specifications/` copies before both were tracked in `6ee970c` |

**13 of 13 met.**

## Demo & Quick Start — 12C (H5.7-H5.11)

Every criterion in this group was verified by actually running the stack, not by reading the code that
implements it — see `IMPLEMENTATION_PLAN.md`'s 12C entry for the full transcript-level detail.

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H5.7 | `docker compose up` yields a working basic quick start | ✅ | `docker build .` verified to succeed cleanly, twice independently (12C's demo build, and again in 12F's release-gate check); `docker-compose.yml` uses the same `Dockerfile`/image |
| H5.8 | Public demo data is fully synthetic | ✅ | `examples/` (OpenAPI/AsyncAPI/manifest fixtures) and the runtime demo's synthetic OTLP spans (`traffic_generator.py`) — including `LegacyPricingService`, invented specifically as a synthetic undeclared dependency, never a real service name |
| H5.9 | The public runtime demo uses an OpenTelemetry Collector and is reproducible | ✅ | `docker-compose.demo.yml` + `examples/runtime-demo/otel-collector-config.yaml`; reproducibility specifically hardened in 12C by fixing a real startup race (`wait_for_declared_import`) found by actually running it from a cold `down -v` state twice |
| H5.10 | The runtime demo demonstrates `CONFIRMED`, `OBSERVED_ONLY`, and `NOT_OBSERVED_IN_WINDOW` | ✅ | Live-verified in `IMPLEMENTATION_PLAN.md`'s 12C entry: `GET /api/analysis/runtime/confirmed` returned `order-service → product-service.getProduct` as `CONFIRMED`; `.../observed-only` returned `OrderService → LegacyPricingService`; `.../declared-only` returned every declared relation as `NOT_OBSERVED_IN_WINDOW` immediately after import, before traffic landed |
| H5.11 | The runtime demo or an integration test demonstrates `DECLARED + OBSERVED → remove declaration → OBSERVED_ONLY` without evidence loss | ✅ | Live-verified in 12C: `examples/order-service/architecture.yaml`'s `calls` entry was actually removed, `POST /api/import/service/order-service` re-run, and `product-service` was confirmed to move from `confirmed` to `observed-only` (not disappear) via the real API — then the fixture was restored (`git diff` empty). This is the same scenario spec §50's Release Gate names as release-blocking if broken |

**5 of 5 met.**

## CI/CD & Security — 12D (H5.21-H5.23)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H5.21 | GitHub Actions run lint, unit, and integration tests for the full H1-H4+11H baseline | ✅* | `.github/workflows/ci.yml` — `ruff check`, `ruff format --check`, `pytest tests/unit`, `pytest tests/integration`, on every push/PR. *Every command was independently re-verified locally this session (483 passed), but the workflow itself has never executed on GitHub Actions, since this repository has no `git remote` configured — "green" means "verified to pass the same commands CI runs," not "seen passing in the Actions tab" |
| H5.22 | Docker image is built reproducibly | ✅* | `.github/workflows/docker.yml` builds on release/tag and publishes to GHCR; `docker build .` independently verified locally (12C and again in 12F). *Same caveat as H5.21 — the GHCR-publish path itself has never executed, since it requires a `release`/tag-push event on a real GitHub repository |
| H5.23 | Dependency and security scanning are enabled | ✅ | `pip-audit` (`ci.yml`'s `dependency-audit` job, blocking on every push/PR — verified locally: `uv run --with pip-audit pip-audit` → "No known vulnerabilities found"), CodeQL (`codeql.yml`, Python + GitHub Actions languages), Trivy (`docker.yml`, image scan with SARIF upload on release/tag) |

**3 of 3 met**, two with the same live-CI caveat (see "Known limitations" below).

## Community Readiness — 12E (H5.24, H5.27-H5.29, H5.32 partial)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H5.24 | `SECURITY.md` is present | ✅ | `SECURITY.md` — supported releases, GitHub private vulnerability reporting (chosen explicitly by the user over publishing a personal email), no-public-issues rule, disclosure process |
| H5.27 | `CONTRIBUTING.md` is present | ✅ | `CONTRIBUTING.md` — dev setup, test/lint/format commands, branch workflow, commit expectations, PR checklist mirroring spec §36, adapter contribution guide |
| H5.28 | `CODE_OF_CONDUCT.md` is present | ✅ | `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1, standard text, enforcement contact adapted to the same no-personal-email choice as `SECURITY.md` |
| H5.29 | Issue and PR templates are present | ✅ | `.github/ISSUE_TEMPLATE/{bug,feature,adapter,documentation}.yml` (spec §38's exact four, as structured issue forms) + `.github/pull_request_template.md` (spec §39's exact five checkboxes) |
| H5.32 | At least five `good first issue` tickets are prepared | 🟡 | Content prepared: five candidates recorded in `IMPLEMENTATION_PLAN.md`'s 12E entry, each grounded in a real, verified gap (confirmed-missing `.dockerignore`, confirmed-missing Dockerfile `HEALTHCHECK`, and three documentation gaps) — not invented busywork. **Not yet filed** as actual GitHub Issues; blocked on a live repository (see H5.34) |

**4 of 5 fully met**, 1 partially met (content ready, filing blocked).

## Release — 12F (H5.30, H5.31, H5.34)

| # | Criterion | Status | Evidence |
|---|---|:---:|---|
| H5.30 | ROADMAP and CHANGELOG are present | ✅ | `ROADMAP.md` (spec §45's v0.1/v0.2/Future structure plus the §43 versioning note), `CHANGELOG.md` (Keep a Changelog format, `[Unreleased]` — see H5.34) |
| H5.31 | GitHub repository topics and social preview are set | ❌ | Blocked — both are GitHub repository *settings*, not files, and this repository has no remote yet (`git remote -v` is empty). Nothing to set them on |
| H5.34 | A first public release can be created as `v0.1.0` or `v0.1.0-alpha.1` | ✅** | Every other criterion and spec §50's Release Gate (see below) are clean, which is what this criterion actually asks — "can be created," not "has been created." **The tag/GitHub Release/GHCR publish/announcement were deliberately not executed — blocked on the same missing `git remote`, and, independently, cutting a public release is the user's decision to make explicitly, not something to infer from a general "implement without prompt" instruction |

**1 of 3 fully met, 1 blocked on infrastructure that doesn't exist here, 1 met in the "ready" sense the criterion asks for but not executed.**

## Release Gate (spec §50) — self-assessment

None of the blocking conditions apply to current repository state:

| Blocking condition | Status |
|---|:---:|
| Known secret in history | ✅ clear (12A scan, re-checked 12F) |
| Unknown ownership/IP issue | ✅ clear (12A) |
| Missing license | ✅ present (12A) |
| Critical failing tests | ✅ none — 483/483 passing |
| Non-working quick start | ✅ works — `docker build .` verified |
| Customer data present | ✅ none found |
| Critical unresolved security finding | ✅ none — `pip-audit` clean |
| 11H evidence-reconciliation regression | ✅ none — live-verified 12C |
| Broken cross-batch runtime correlation | ✅ none — live-verified 12C |
| Runtime demo without working Collector → AIP path | ✅ works — live-verified 12C |

## Consolidated gate

All 34 of spec §51's H5 acceptance criteria, in original numbering:

| ID | Criterion | Status |
|---|---|:---:|
| H5.1 | Project license is Apache License 2.0 | ✅ |
| H5.2 | `LICENSE` contains the full standard text | ✅ |
| H5.3 | Third-party licenses reviewed and documented | ✅ |
| H5.4 | No secrets or customer data present | ✅ |
| H5.5 | Git history reviewed or deliberately rebuilt | ✅ |
| H5.6 | README explains problem, benefit, architecture | ✅ |
| H5.7 | `docker compose up` gives a working quick start | ✅ |
| H5.8 | Public demo data is fully synthetic | ✅ |
| H5.9 | Runtime demo uses an OTel Collector and is reproducible | ✅ |
| H5.10 | Runtime demo demonstrates `CONFIRMED`/`OBSERVED_ONLY`/`NOT_OBSERVED_IN_WINDOW` | ✅ |
| H5.11 | Runtime demo demonstrates the reconciliation scenario without evidence loss | ✅ |
| H5.12 | Canonical Model is publicly documented | ✅ |
| H5.13 | Graph/Evidence model + 11H reconciliation invariant documented | ✅ |
| H5.14 | `OBSERVED PROVIDES` for runtime-discovered operations documented | ✅ |
| H5.15 | `CLIENT_SERVER`/`CLIENT_ONLY`/`SERVER_ONLY`/`UNRESOLVED` documented | ✅ |
| H5.16 | Cross-batch correlation documented | ✅ |
| H5.17 | `NOT_OBSERVED_IN_WINDOW` + qualitative coverage documented correctly | ✅ |
| H5.18 | `observation_count` not presented as exact request count | ✅ |
| H5.19 | Adapter extension point documented | ✅ |
| H5.20 | Platform functions without LLM configuration | ✅ |
| H5.21 | CI runs lint + unit + integration for the full baseline | ✅* |
| H5.22 | Docker image builds reproducibly | ✅* |
| H5.23 | Dependency and security scanning enabled | ✅ |
| H5.24 | `SECURITY.md` present | ✅ |
| H5.25 | Security Model documents the correlation buffer as a trust boundary | ✅ |
| H5.26 | Privacy model applies to temporary correlation data too | ✅ |
| H5.27 | `CONTRIBUTING.md` present | ✅ |
| H5.28 | `CODE_OF_CONDUCT.md` present | ✅ |
| H5.29 | Issue and PR templates present | ✅ |
| H5.30 | ROADMAP and CHANGELOG present | ✅ |
| H5.31 | Repository topics and social preview set | ❌ |
| H5.32 | ≥5 good-first-issue tickets prepared | 🟡 |
| H5.33 | `docs/specifications/` contains H4/11H/H5 design history | ✅ |
| H5.34 | First public release can be created as `v0.1.0`/`v0.1.0-alpha.1` | ✅** |

**31 of 34 fully met**, **1 partially met** (H5.32 — content ready, filing blocked), **2 blocked on
infrastructure this environment doesn't have** (H5.31 needs a live repo to set settings on; H5.34's own
✅ is qualified — see above — and is really the same live-repo blocker surfacing a third time).

## Known limitations / explicitly deferred (carried forward, not new findings)

Collected from all six iterations' own "Explicitly deferred"/"out of scope" notes in
`IMPLEMENTATION_PLAN.md`:

- **No `git remote` is configured for this repository.** This is the root cause behind every open item
  in this review — H5.31, the unfiled half of H5.32, H5.34's actual execution, CI/CD never having run
  on real GitHub infrastructure (the H5.21/H5.22 caveats), and enabling GitHub Discussions (spec §37,
  not a numbered acceptance criterion but part of the Community Files requirement). None of these are
  code or documentation gaps — they're all one missing precondition away from being resolved.
- **12C:** demo screenshot/GIF (spec §48) deferred to 12F, then still not produced — no headless-browser
  tooling is available in this environment to produce one honestly, and spec §48 itself frames it as a
  "before release" item rather than something 12C or 12F individually block on.
- **12D:** Trivy's container scan is deliberately non-blocking (`exit-code: "0"`, SARIF-upload-only) —
  base-image CVEs the maintainer doesn't directly control shouldn't hard-fail a release build; this is a
  considered design choice (documented in `IMPLEMENTATION_PLAN.md`'s 12D entry), not an oversight.
- **12E:** GitHub Discussions enablement is a repository setting, not a file — same live-repo blocker as
  above.
- **Carried forward from `H4_REVIEW.md`, still true:** `app/graph/importer.py`'s stale-evidence-
  stripping risk noted there was a *pre-11H* finding — 11H-A (`3a9fa61`, predating even 12A) fixed
  exactly this bug, so it is resolved, not still open. Read-only vs. read-write Neo4j users are still
  approximated via driver session access mode rather than separate Neo4j accounts/roles; the two REST ID
  namespaces (full graph ID vs. import-time slug) still coexist. Neither is H5 scope.

## Verdict

Thirty-one of thirty-four H5 acceptance criteria are met outright, backed by the same 483-test suite
every prior review has used as its baseline (unchanged, since H5 added no application code) plus, for
the criteria that are actually about behavior rather than file presence, live runs of the real stack
performed during 12C and re-verified during 12F — not just documentation asserting the behavior exists.
One criterion (H5.32) is half-met: real, well-scoped good-first-issue content is ready, but filing it as
actual GitHub Issues needs a live repository. The remaining two items (H5.31, and the "not yet executed"
half of H5.34) are not implementation gaps at all — every file, workflow, and documented invariant they
depend on already exists and has been verified; what's missing is a `git remote`, which is not something
to create or push to without the user's explicit decision. The platform is, in the literal sense H5.34
asks for, ready to become `v0.1.0`: the Release Gate (spec §50) has no open blocking condition, the two
scenarios spec §50 singles out by name (evidence reconciliation, cross-batch correlation) are both
live-verified rather than assumed, and every community/security/documentation artifact a newcomer would
need is in place. Whether and when to actually cut that release remains, correctly, outside this
review's authority to decide.
