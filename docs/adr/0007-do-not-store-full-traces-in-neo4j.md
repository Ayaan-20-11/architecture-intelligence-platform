# 7. Never store full traces or raw span payloads in Neo4j

Status: Accepted

## Context

Once OpenTelemetry ingestion (H4) existed, the easy implementation path would have been to persist
incoming spans close to as-is — full attributes, request/response data if present, maybe even a
`Span` node per observation — and derive architecture facts from that later. That would turn AIP
into an ad-hoc, unofficial second trace store: exactly what it's explicitly not meant to be (spec:
"AIP is an additional telemetry consumer, not the primary observability backend"), and a much larger
privacy/security surface than an architecture-fact store needs.

## Decision

Persist only architecture facts and their evidence — never raw trace/span data:

- Only an explicit, documented attribute allowlist is read from incoming OTLP spans (16 semconv
  constants across `resources.py`/`http.py`/`messaging.py`) — never authorization headers, cookies,
  request/response bodies, message bodies, query parameters, or full URLs.
- No raw trace storage in Neo4j, and no `Span` node label at all.
- The HTTP correlation buffer (11H-B) — the one place a CLIENT span's data waits, briefly, for its
  matching SERVER span — is bounded, TTL-based (60s default), in-memory only, and holds no raw
  payload: it's short-lived correlation *logic*, structurally distinct from persisted Architecture
  Evidence, and explicitly documented as its own trust boundary rather than an implicit extension of
  the "no raw traces" rule.
- `observation_count` is documented as an architecture-evidence indicator, explicitly not an exact
  request count and not billing/SLO-grade traffic measurement — so nobody downstream mistakes it for
  something it structurally can't guarantee.

## Consequences

- A compromise of the graph, or of the correlation buffer, exposes architecture facts (who calls
  whom) but not request contents, credentials, or business data — a materially smaller blast radius
  than a trace store would have.
- New runtime-observation code (a future adapter beyond OpenTelemetry) inherits this constraint by
  default: read from an explicit allowlist, never persist a raw payload — see
  [`adapter-development.md`](../adapter-development.md)'s runtime-source-adapter rules, which state
  this as a requirement, not a suggestion.
- See [`security-model.md`](../security-model.md) and [`opentelemetry.md`](../opentelemetry.md) for
  the full allowlist and the correlation buffer's exact bounds.
