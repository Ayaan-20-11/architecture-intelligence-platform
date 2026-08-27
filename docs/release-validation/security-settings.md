# Repository Security Settings

**Date:** 2026-08-27
**Repository:** `michaelegner/architecture-intelligence-platform`

Verified via the GitHub API (`gh api repos/.../...`), not the Settings UI — each value below is a
real API response captured this session, not a checklist marked from memory.

| Feature | Status | Evidence |
|---|---|---|
| Secret scanning | Enabled | `security_and_analysis.secret_scanning.status = "enabled"` |
| Secret scanning push protection | Enabled | `security_and_analysis.secret_scanning_push_protection.status = "enabled"` |
| Dependabot alerts | Enabled | `GET /vulnerability-alerts` → `204` (enabling it: `PUT /vulnerability-alerts` → `204`) |
| Dependabot security updates | Enabled | `security_and_analysis.dependabot_security_updates.status = "enabled"` |
| Private vulnerability reporting | Enabled | `GET /private-vulnerability-reporting` → `200` |
| CodeQL | Enabled, 0 open alerts | `.github/workflows/codeql.yml`; `GET /code-scanning/alerts` → 1 finding total, found and fixed same day (see `v0.1.0-alpha.1-verification.md`), 0 currently open |
| Dependency graph | Enabled | `Dependency Graph` workflow runs visible in Actions (Dependabot's own update-check runs) |
| Discussions | Enabled | `has_discussions = true`; default categories present (Announcements, General, Ideas, Polls, Q&A, Show and tell) |
| Repository topics | Set | `architecture`, `architecture-drift`, `architecture-intelligence`, `asyncapi`, `dependency-analysis`, `knowledge-graph`, `microservices`, `neo4j`, `openapi`, `opentelemetry`, `platform-engineering`, `software-architecture` |
| Branch protection (`main`) | Enabled | Required status check (`lint + test`), force-push blocked, deletion blocked. Deliberately **no required PR review** — solo-maintainer project, direct pushes to `main` are the working model; see `docs/gaps/` (not tracked) for the reasoning. |

## Not independently API-verifiable

- **Social Preview image**: GitHub exposes no API for this setting — `images/AIP.png` has been
  generated and committed, but whether it's been uploaded under Settings → General → Social preview
  can only be confirmed by a human looking at the setting (or the rendered link-unfurl).
