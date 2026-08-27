# Security Policy

## Supported releases

Architecture Intelligence Platform is currently pre-1.0 (PoC / hardening stage). Only the latest
release receives security fixes — there is no long-term support branch yet.

## Reporting a vulnerability

**Please do not open a public GitHub issue for a security report.**

Report vulnerabilities privately using GitHub's [private vulnerability reporting][advisories]
feature on this repository ("Security" tab -> "Report a vulnerability"). This opens a private
GitHub Security Advisory visible only to you and the maintainers — nothing is public until a fix is
released and the advisory is published.

Please include:

- the affected version/commit,
- a description of the vulnerability and its impact,
- reproduction steps or a proof of concept, if available.

[advisories]: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability

## Disclosure process

1. You report privately via GitHub Security Advisories.
2. A maintainer acknowledges the report and investigates.
3. A fix is developed and reviewed in the private advisory (not in a public PR) until ready.
4. The fix is released, and the advisory is published with credit to the reporter (unless they
   request otherwise).

There is no fixed SLA at this project stage; reports are handled as promptly as possible.

## Scope

Two specific trust boundaries are worth knowing before reporting — see
[`docs/security-model.md`](docs/security-model.md) for the full picture:

- The LLM query layer treats LLM output as untrusted input; generated Cypher is validated against
  an allowlist and executed read-only. A bypass of that validator is a valid security report.
- The OTLP ingestion path (`/v1/traces`) and its bounded, TTL-based HTTP correlation buffer never
  persist raw span payloads — only an explicit attribute allowlist. Anything that causes raw
  payload data to reach Neo4j or long-lived storage is a valid security report.
