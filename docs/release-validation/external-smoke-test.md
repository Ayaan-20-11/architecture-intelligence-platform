# External Smoke Test

**Date:** 2026-08-27
**Repository:** `michaelegner/architecture-intelligence-platform`
**Commit tested:** `main` @ `7a541a9` (or later — see `git log` if this file predates the exact
commit at test time)

Test performed independently of the environment that built and verified the repository (see
`docs/release-validation/README.md` for why that independence matters — everything else in this
directory was verified by the same session that built the fixes).

## Scope

The standard 8-step script: read the README, run the Quick Start, open the application, import the
synthetic example architecture, inspect a deterministic analysis, run the runtime demo, locate the
documentation, find the security-reporting path — using only what's publicly documented, no
maintainer intervention.

## Result

**Pass — executed without significant issues.**

## Not yet covered

- `v0.1.0-alpha.2` doesn't exist yet — this smoke test ran against `main` directly, not a tagged
  release/published GHCR image. `v0.1.0-alpha.2`'s own verification (once cut) will include a fresh
  pull-and-run check of the actual release artifact.
