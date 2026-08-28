# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/) — see [`ROADMAP.md`](ROADMAP.md) for which
parts of the surface (Canonical Model, REST API, Graph Schema, Adapter SPI, configuration format)
aren't yet guaranteed stable pre-1.0.

## [Unreleased]

## [0.1.0-alpha.2] - 2026-08-27

Second public pre-release, cut specifically to give the fixed release pipeline (single Docker
workflow trigger) one clean run, and to re-verify the non-root container fix against the actual
published GHCR image rather than only a local build — both gaps left open by `v0.1.0-alpha.1`'s own
verification. See
[`docs/release-validation/v0.1.0-alpha.2-verification.md`](docs/release-validation/v0.1.0-alpha.2-verification.md).

### Fixed

- The container ran as `root` — no `USER` instruction in `Dockerfile`. Found via `v0.1.0-alpha.1`'s
  GHCR pull-and-run verification (spec §29's non-root check). Fixed: builds/runs as a dedicated `app`
  (uid 1000) user; verified end-to-end (health checks, import, an analysis) both standalone and in
  the runtime demo — and now also against the actual pulled, tagged `v0.1.0-alpha.2` GHCR image, not
  only a local build.
- `docker.yml` fired twice per release (`release: published` and `push: tags: "v*"` both matched one
  tag push), racing two builds from the same commit and letting whichever finished last silently
  overwrite the other's GHCR tag pointer — this is exactly what happened to `v0.1.0-alpha.1`. Now
  triggered only by `release: published`; confirmed under `v0.1.0-alpha.2`'s own release that exactly
  one run fires.
- README Quick Start referenced a placeholder clone URL and the wrong directory name, and never
  mentioned creating `.env` before `docker compose up`. Fixed with the real clone URL and a
  documented local-only default password (`.env.example`).
- `pyproject.toml` still carried the PoC-era package name/description
  (`architecture-intelligence-poc`); `uv.lock` regenerated to match.
- `tests/integration/test_runtime_api.py` used hardcoded absolute-datetime fixtures that would
  silently fall outside the runtime API's default rolling analysis window and start failing CI once
  enough real time had passed. Fixtures now compute their timestamps relative to "now".

### Added

- Branch protection on `main` (required CI status check, no force-push, no deletion — no required PR
  review, to preserve the direct-push-to-main workflow used throughout this solo-maintainer project).
- A demo screenshot in `README.md` and `examples/runtime-demo/README.md`'s runtime demo walkthrough.

## [0.1.0-alpha.1] - 2026-08-27

First public pre-release, cut to validate the complete release pipeline (GitHub Actions, CodeQL,
GHCR publishing, a fresh-clone Quick Start and runtime demo) before promoting to `v0.1.0`.

### Added

**Core PoC** — OpenAPI and AsyncAPI adapters, an Architecture Manifest adapter for REST-caller
information neither spec format can express, a shared Canonical Model (Pydantic) decoupling every
adapter from Neo4j persistence, a Neo4j importer with deterministic stable IDs and atomic
per-service reimport, five deterministic Cypher analyses (queue senders/consumers, orphan queues,
mixed sync/async blast radius), a minimal FastAPI UI, and a read-only natural-language query layer
(question → validated Cypher → explanation, LLM never a source of truth and never able to write to
the graph).

**H1–H3 hardening** — persisted `Evidence`/`Provenance` (previously in-memory only), a Graph Schema
+ Semantic Query Validator for the LLM layer, and a deterministic intent router for common questions
that don't need an LLM round-trip at all.

**H4 — OpenTelemetry** — an OTLP/HTTP ingestion endpoint (`/v1/traces`) that resolves observed spans
against declared architecture and persists observed facts/evidence alongside declared ones; service
and environment resolution; REST (CLIENT/SERVER correlation) and queue (send/receive) observation
paths; evidence aggregation; declared-vs-observed comparison (`CONFIRMED`/`OBSERVED_ONLY`/
`NOT_OBSERVED_IN_WINDOW`); a runtime API, runtime UI, and intent-router integration.

**11H — Runtime Correctness & Robustness** — fixed a stale-evidence relation-deletion bug in the
evidence-reconciliation path; hardened HTTP correlation (bounded, TTL-based, cross-batch-capable);
explicit handling for partial/single-sided HTTP instrumentation; an `OBSERVED PROVIDES` relation for
runtime-discovered operations with no declared provider, with later-declaration reconciliation;
qualitative telemetry-coverage classification (`SUFFICIENT`/`PARTIAL`/`NONE`/`UNKNOWN`) for
`NOT_OBSERVED_IN_WINDOW` findings, so a negative finding is never overstated as "unused"/"dead"; a
Collector-based OpenTelemetry demo topology.

**H5 — Open Source Readiness**:
- Apache License 2.0, `THIRD_PARTY_LICENSES.md` covering all direct dependencies, a repository
  secret/IP scan.
- A full public-facing `docs/` set (architecture, canonical model, graph/evidence model, ingestion,
  analyses, semantic validation, OpenTelemetry, configuration, security model, development, adapter
  development) plus `docs/specifications/` preserving the original design documents as design
  history.
- A self-demonstrating runtime demo: an undeclared `OrderService -> LegacyPricingService` call
  (`OBSERVED_ONLY`), periodic cross-batch HTTP correlation, and a documented walkthrough
  (`examples/runtime-demo/README.md`) covering all three declared-vs-observed states plus the 11H
  evidence-reconciliation scenario end-to-end.
- GitHub Actions CI (lint, unit + integration tests, `pip-audit`), CodeQL (Python + GitHub Actions),
  a release/tag-triggered Docker build published to GHCR with Trivy image scanning, and Dependabot
  (`uv`, `github-actions`, `docker`).
- `CONTRIBUTING.md`, `SECURITY.md` (GitHub private vulnerability reporting), `CODE_OF_CONDUCT.md`
  (Contributor Covenant v2.1), `SUPPORT.md`, four issue-report forms, and a pull request template.
- `CHANGELOG.md`, `ROADMAP.md`, and Architecture Decision Records under `docs/adr/`.

### Fixed

- A stale-`OBSERVED`-evidence relation could be incorrectly deleted during reconciliation (11H-A).
- The demo's traffic generator could send observed spans before `POST /api/import` ran, permanently
  splitting a service's declared and observed identities into two never-merging graph nodes (12C) —
  the generator now waits for the declared import before sending anything.
- `ruff format --check .` failed because ruff 0.16 formats Markdown code fences by default and
  wanted to rewrite `Protocol` stubs inside frozen historical spec documents (12D) — `*.md` is now
  excluded from ruff's formatting scope.
- `GET /health/neo4j` returned a raw exception message (`str(exc)`) to the caller on failure,
  which for a Neo4j driver error could include connection details — found by CodeQL
  (`py/stack-trace-exposure`) on its first run against real GitHub infrastructure (12G). Now
  logged server-side only; the response is a generic `{"status": "error"}`.
- `docker-compose.yml` required `OPENAI_API_KEY` (`:?` syntax), contradicting the documented
  LLM-optional guarantee — a fresh clone following the README's own Quick Start (which leaves the
  key blank) would fail to start at all. Found via 12G's fresh-clone validation.
- The natural-language query page and any O1-O5 API call without an explicit `environment`
  parameter silently returned zero rows against the runtime demo's data, because
  `config.yaml`'s `runtime_analysis.default_environment` (`production`) didn't match the demo's
  own `environment=demo` traffic tag. `docker-compose.demo.yml` now points the demo at
  `config.demo.yaml`, identical except for that one value.

### Security

- The LLM query layer treats LLM output as untrusted input: generated Cypher is restricted to a
  read-only allowlist (`MATCH`/`OPTIONAL MATCH`/`WHERE`/`WITH`/`RETURN`/`ORDER BY`/`LIMIT`) with
  depth/result-row limits, and the LLM never receives direct Neo4j credentials.
- The OTLP ingestion path and its bounded, TTL-based HTTP correlation buffer read only an explicit
  attribute allowlist and never persist raw span payloads, authorization headers, cookies, request/
  response bodies, or full URLs — see `docs/security-model.md`.
