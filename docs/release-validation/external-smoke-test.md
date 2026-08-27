# External Smoke Test

**Date:** 2026-08-27
**Repository:** `michaelegner/architecture-intelligence-platform`
**Commit tested:** `main` @ `7a541a93` (exact commit — this file was written and merged one commit
later, `65264a12`, once the result was known)

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

- This smoke test ran against `main` directly, not a tagged release/published GHCR image. The
  tagged-artifact pull-and-run check (authenticated and unauthenticated, non-root confirmation) is
  covered separately in
  [`v0.1.0-alpha.2-verification.md`](v0.1.0-alpha.2-verification.md).
