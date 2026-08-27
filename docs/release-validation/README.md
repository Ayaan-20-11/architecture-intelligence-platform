# Release Validation

Evidence that a release actually satisfied the H5/12G specifications (`docs/specifications/`), not
just that CI passed. The distinction that matters:

```text
docs/specifications/     what the system/release must satisfy
docs/release-validation/ evidence that a release actually satisfied it
```

CI green, CodeQL green, and a successful GHCR publish prove the build pipeline works. They don't by
themselves prove an external user can actually clone this repository, follow the README, and get a
working system — that requires running the same steps an external user would, from a clean
environment, and recording what happened. That's what these files are.

| File | Covers |
|---|---|
| [`v0.1.0-alpha.1-verification.md`](v0.1.0-alpha.1-verification.md) | Fresh-clone Quick Start, fresh-clone runtime demo, GHCR image pull/run (authenticated and unauthenticated), non-root container check, the CodeQL finding found and fixed along the way. |
| [`security-settings.md`](security-settings.md) | Repository security feature configuration, verified via the GitHub API rather than assumed. |
| [`public-repository-content-gate.md`](public-repository-content-gate.md) | Sign-off record for the pre-push secret/customer-data/history review performed before the repository went public. |
