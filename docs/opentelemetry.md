# OpenTelemetry Runtime Observation

AIP is an **additional telemetry consumer, not the primary observability backend**. See the
project README's "Runtime telemetry" section and [`security-model.md`](security-model.md) for the
production failure-isolation topology this implies (a Collector should fan out to a real
observability backend *and* AIP in parallel, never to AIP alone).

## Ingestion contract

`POST /v1/traces` accepts a protobuf `ExportTraceServiceRequest`
(`Content-Type: application/x-protobuf`) — OTLP/HTTP, the standard export format any OpenTelemetry
Collector or SDK can produce. It decodes the batch, resolves each span against whatever the graph
already has declared, and persists observed facts and evidence. A malformed payload or wrong
content-type is rejected (400/415) before any Neo4j access happens, so a bad request can never
partially write.

## Attribute allowlist

Only these OTel semantic-convention attributes are ever read — nothing else is inspected, and
nothing outside this list is ever persisted:

**Resource identity** (`app/telemetry/semconv/resources.py`): `service.name`,
`service.namespace`, `service.version`, `service.instance.id`, `deployment.environment.name`.

**HTTP** (`app/telemetry/semconv/http.py`): `http.request.method`, `http.route`, `url.template`
(fallback for `http.route`), `server.address`/`server.port` (defined but never used to *resolve*
anything — see below), `peer.service` (the sole allowlisted way to identify a CLIENT-only call's
target).

**Messaging** (`app/telemetry/semconv/messaging.py`): `messaging.system`,
`messaging.destination.name`, `messaging.destination.template`, `messaging.operation.name`,
`messaging.operation.type`.

Never read, never persisted: authorization headers, cookies, request/response bodies, message
bodies, query parameters, full URLs, or any other raw span attribute. `server.address`/
`server.port` exist as constants but are deliberately never used for identity resolution — a
CLIENT-only call's target must come from `peer.service`, never guessed from a network address (the
"no guessing" rule below).

## Correlation modes

An HTTP call observation's `correlation_mode` records how confidently it was correlated:

| Mode | Meaning |
|---|---|
| `CLIENT_SERVER` | Strongest signal — a matched CLIENT+SERVER span pair, whether they arrived in the same OTLP batch or were matched across two separate batches |
| `CLIENT_ONLY` | Partial instrumentation — a CLIENT span with a stable target identity (`peer.service`) whose SERVER counterpart never arrived |
| `SERVER_ONLY` | Only ever recorded when the caller's identity is reliable — since nothing in the current attribute allowlist can identify a caller from a SERVER span alone, a SERVER-only observation today always ends up `UNRESOLVED` rather than producing a fact; the mode exists in the model for when a future signal makes caller identification possible |
| `UNRESOLVED` | Not a correlation mode itself, but the outcome for any observation whose identity is insufficient — recorded as an `UnresolvedObservation` with a reason code (below), never guessed at |

Messaging observations get their own three modes (`MESSAGING_SEND`/`MESSAGING_RECEIVE`/
`MESSAGING_PROCESS`) — see [`evidence.md`](evidence.md).

### Cross-batch correlation

A real CLIENT span and its matching SERVER span very often arrive in *separate* OTLP batches — a
Collector's batch processor flushes by time/size, not trace completeness. AIP supports this: a
bounded, TTL-based `HttpCorrelationBuffer` (`app/telemetry/correlation_buffer.py`) holds a CLIENT or
SERVER span in memory, waiting for its counterpart to arrive in a *later* `POST /v1/traces` request,
and correlates them the moment it does. If the TTL expires first, the still-unmatched span is
instead evaluated as a `CLIENT_ONLY`/`SERVER_ONLY` observation rather than silently discarded. See
[`security-model.md`](security-model.md) for exactly what this buffer does and does not persist.

### No-guessing rule

Every resolution path either finds a real, stable identity signal or reports an unresolved reason —
it never fabricates one. The fixed reason-code set (`app/telemetry/adapter.py`):

| Reason | When |
|---|---|
| `no_environment` | No `deployment.environment.name` on the span |
| `no_stable_route` | No usable `http.route`/`url.template`, or the operation couldn't be resolved |
| `no_destination_name` | A messaging span with no `messaging.destination.name` |
| `missing_target_identity` | A CLIENT-only span with method+route but no `peer.service` |
| `missing_caller_identity` | A SERVER-only span — its caller can never be identified from the current allowlist |
| `correlation_expired` | A CLIENT-only span that aged out of the buffer with not even method/route present |

## Declared vs. observed, and coverage qualification

See [`graph-model.md`](graph-model.md) for the full `CONFIRMED`/`OBSERVED_ONLY`/
`NOT_OBSERVED_IN_WINDOW` status model this feeds. `NOT_OBSERVED_IN_WINDOW` on its own conflates two
very different situations — "we watched for this and it didn't happen" vs. "we have no real
telemetry coverage to judge by" — so it can be qualified with a coverage classification
(`app/analysis/runtime.py::_classify_coverage`):

| Coverage | Meaning |
|---|---|
| `SUFFICIENT` | The subject has observed traffic of the *same* relation kind (HTTP vs. messaging) in this environment/window — a not-observed edge of a well-covered kind is real evidence |
| `PARTIAL` | The subject emits *some* telemetry, just not of this specific kind |
| `NONE` | The subject emitted no usable telemetry at all in this environment/window |
| `UNKNOWN` | Qualification is disabled (`telemetry.coverage.qualification-enabled: false`) or there's no coverage data for the subject at all |

This is a coarse, deliberately non-numeric classification — never interpreted as `obsolete`,
`unused`, or `dead`.

## `observation_count` is not a request counter

`observation_count` (summed per evidence bucket, alongside up to 5 `sample_trace_ids`) is an
**architecture-evidence indicator**, not an exact, billing- or SLO-grade traffic count. It exists to
answer "did this happen, roughly how much, and when" for architecture-discovery purposes — never to
answer "exactly how many requests occurred."
