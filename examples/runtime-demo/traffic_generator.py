"""Synthetic OTLP/HTTP traffic generator for the 11H-F Runtime Demo (spec §9).

This PoC's `examples/` fixture services are OpenAPI/AsyncAPI *documents*, not runnable
applications (see repository root CLAUDE.md - standing up real network services for a demo is
explicitly out of scope). This script plays the role of "Demo Services" in the topology diagram
by emitting the same realistic CLIENT/SERVER and messaging spans those services would produce if
they were real and instrumented, directly to an OTel Collector's OTLP/HTTP receiver - proving the
"Demo Services -> OTel Collector -> AIP" forwarding path end-to-end without requiring real HTTP
traffic between real processes.

Builds the same declared topology as `examples/`: order-service calls product-service's
GET /products/{id}, order-service sends to payment-q, payment-service receives payment-q and
sends invoice-q. Uses only `opentelemetry-proto` (already a project dependency, used identically
by AIP's own decoder and this repo's test suite) - no OpenTelemetry SDK, no extra dependencies.

Before sending any traffic, this script blocks until `order-service` shows up as a *declared*
Service in AIP's graph (`wait_for_declared_import`) - i.e. until `POST /api/import` has actually
run. Sending observed spans for "OrderService" before that import exists would make AIP's exact-
name service resolver (`app/telemetry/service_resolver.py`) mint its own observed-only Service
node for the name; the later `POST /api/import` then creates a *second*, differently-ID'd Service
node with the same declared name, and the two never merge (the resolver's tier-2 name match only
fires when the name is unique across all Service nodes) - permanently splitting "OrderService"'s
declared and observed identities. Waiting removes that race instead of just documenting it.

Two extra behaviors exist purely to make the H5 demo (spec §14-15) self-demonstrating rather than
requiring a contrived side scenario:

- Every cycle additionally emits an OrderService -> LegacyPricingService CLIENT/SERVER pair
  (spec §14's "Zusätzlich H4" topology addendum). LegacyPricingService is never declared anywhere
  in `examples/` or its OpenAPI/manifest, so this call surfaces as `OBSERVED_ONLY` - a live,
  undocumented-dependency finding, not just a described one.
- Every `CROSS_BATCH_EVERY_N`-th cycle, the OrderService -> ProductService CLIENT and SERVER spans
  are additionally sent as two separate OTLP export requests a few seconds apart (see
  `send_cross_batch_pair`), instead of bundled in one request - demonstrating the optional
  cross-batch HTTP correlation scenario from spec §15's last paragraph. This is additive: the
  regular bundled pair each cycle already keeps the relation `CONFIRMED` on its own.

See `examples/runtime-demo/README.md` for the full walkthrough, including the NOT_OBSERVED_IN_WINDOW
and 11H reconciliation scenarios (which are timing/reimport-driven, not something this generator
itself needs to produce).
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
TRACES_URL = f"{OTLP_ENDPOINT.rstrip('/')}/v1/traces"
AIP_BASE_URL = os.environ.get("AIP_BASE_URL", "http://architecture-intelligence:8000")
AIP_SERVICES_URL = f"{AIP_BASE_URL.rstrip('/')}/api/services"
READINESS_SERVICE_ID = "service:order-service"
READINESS_POLL_SECONDS = 3.0
ENVIRONMENT = os.environ.get("DEMO_ENVIRONMENT", "demo")
INTERVAL_SECONDS = float(os.environ.get("TRAFFIC_INTERVAL_SECONDS", "5"))
CONTENT_TYPE = "application/x-protobuf"

# Every Nth cycle, additionally demonstrate cross-batch HTTP correlation (spec §15) by sending the
# OrderService -> ProductService CLIENT and SERVER spans as two separate OTLP requests instead of
# one. Comfortably inside the default 60s correlation-buffer TTL (app/settings.py).
CROSS_BATCH_EVERY_N = 4
CROSS_BATCH_GAP_SECONDS = 3.0


def _kv(key: str, value: str) -> KeyValue:
    return KeyValue(key=key, value=AnyValue(string_value=value))


def _resource(service_name: str, *, environment: str = ENVIRONMENT) -> Resource:
    return Resource(
        attributes=[
            _kv("service.name", service_name),
            _kv("deployment.environment.name", environment),
        ]
    )


def _now_nanos() -> int:
    return int(time.time() * 1e9)


def _http_pair(
    *, client_service: str, server_service: str, method: str, route: str
) -> tuple[ResourceSpans, ResourceSpans]:
    """One realistic CLIENT+SERVER span pair for a synchronous REST call (spec §20's
    CLIENT_SERVER correlation mode - the strongest signal AIP recognizes). Returned as a
    (client, server) tuple rather than a combined list so callers can choose to send both in one
    OTLP request (the common case) or in two separate requests (the cross-batch demo below)."""
    trace_id = uuid.uuid4().bytes
    client_span_id = uuid.uuid4().bytes[:8]
    server_span_id = uuid.uuid4().bytes[:8]
    start = _now_nanos()
    end = start + random.randint(5_000_000, 50_000_000)  # 5-50ms, synthetic but plausible

    client_span = Span(
        trace_id=trace_id,
        span_id=client_span_id,
        name=f"{method} {route}",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=start,
        end_time_unix_nano=end,
        attributes=[_kv("http.request.method", method), _kv("http.route", route)],
    )
    server_span = Span(
        trace_id=trace_id,
        span_id=server_span_id,
        parent_span_id=client_span_id,
        name=f"{method} {route}",
        kind=Span.SPAN_KIND_SERVER,
        start_time_unix_nano=start + 1_000_000,
        end_time_unix_nano=end - 1_000_000,
        attributes=[_kv("http.request.method", method), _kv("http.route", route)],
    )
    return (
        ResourceSpans(
            resource=_resource(client_service), scope_spans=[ScopeSpans(spans=[client_span])]
        ),
        ResourceSpans(
            resource=_resource(server_service), scope_spans=[ScopeSpans(spans=[server_span])]
        ),
    )


def _messaging_span(
    *, service: str, operation_type: str, destination: str, system: str = "demo-broker"
) -> ResourceSpans:
    """One send/receive messaging span (spec §24-26 - independently derivable, no correlation
    needed, unlike the HTTP CLIENT/SERVER pair above)."""
    start = _now_nanos()
    span = Span(
        trace_id=uuid.uuid4().bytes,
        span_id=uuid.uuid4().bytes[:8],
        name=f"{operation_type} {destination}",
        kind=Span.SPAN_KIND_PRODUCER if operation_type == "send" else Span.SPAN_KIND_CONSUMER,
        start_time_unix_nano=start,
        end_time_unix_nano=start + random.randint(1_000_000, 10_000_000),
        attributes=[
            _kv("messaging.operation.type", operation_type),
            _kv("messaging.destination.name", destination),
            _kv("messaging.system", system),
        ],
    )
    return ResourceSpans(resource=_resource(service), scope_spans=[ScopeSpans(spans=[span])])


def build_batch() -> ExportTraceServiceRequest:
    resource_spans: list[ResourceSpans] = []
    resource_spans.extend(
        _http_pair(
            client_service="OrderService",
            server_service="ProductService",
            method="GET",
            route="/products/{id}",
        )
    )
    # Undeclared REST dependency (spec §14's "Zusätzlich H4" addendum) - never appears in
    # examples/'s OpenAPI/manifest, so this surfaces as OBSERVED_ONLY (see README's O3 walkthrough).
    resource_spans.extend(
        _http_pair(
            client_service="OrderService",
            server_service="LegacyPricingService",
            method="GET",
            route="/pricing/{sku}",
        )
    )
    resource_spans.append(
        _messaging_span(service="OrderService", operation_type="send", destination="payment-q")
    )
    resource_spans.append(
        _messaging_span(service="PaymentService", operation_type="receive", destination="payment-q")
    )
    resource_spans.append(
        _messaging_span(service="PaymentService", operation_type="send", destination="invoice-q")
    )
    resource_spans.append(
        _messaging_span(service="InvoiceService", operation_type="receive", destination="invoice-q")
    )
    return ExportTraceServiceRequest(resource_spans=resource_spans)


def send_batch(request: ExportTraceServiceRequest) -> None:
    body = request.SerializeToString()
    http_request = urllib.request.Request(
        TRACES_URL, data=body, headers={"Content-Type": CONTENT_TYPE}, method="POST"
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:
        response.read()


def send_cross_batch_pair() -> None:
    """Sends one OrderService -> ProductService CLIENT/SERVER pair as two separate OTLP export
    requests, `CROSS_BATCH_GAP_SECONDS` apart, instead of bundled in one request - the optional
    cross-batch correlation scenario from spec §15. AIP's HttpCorrelationBuffer (60s default TTL)
    holds the CLIENT span until the SERVER span arrives in the later request and still correlates
    them into the same observed REST dependency."""
    client_rs, server_rs = _http_pair(
        client_service="OrderService",
        server_service="ProductService",
        method="GET",
        route="/products/{id}",
    )
    send_batch(ExportTraceServiceRequest(resource_spans=[client_rs]))
    print(
        f"[traffic-generator] {datetime.now(UTC).isoformat()} cross-batch demo: sent CLIENT span, "
        f"waiting {CROSS_BATCH_GAP_SECONDS}s before the matching SERVER span",
        flush=True,
    )
    time.sleep(CROSS_BATCH_GAP_SECONDS)
    send_batch(ExportTraceServiceRequest(resource_spans=[server_rs]))
    print(
        f"[traffic-generator] {datetime.now(UTC).isoformat()} cross-batch demo: sent matching "
        "SERVER span in a separate request",
        flush=True,
    )


def wait_for_declared_import() -> None:
    """Blocks until `READINESS_SERVICE_ID` (order-service) exists as a declared Service - i.e.
    until `POST /api/import` has run - to avoid the observed/declared identity-split race
    described in this module's docstring. Polls forever (this is a demo, not a production
    readiness probe); a friendly reminder is logged periodically while waiting."""
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(AIP_SERVICES_URL, timeout=10) as response:
                services = json.loads(response.read())
            if any(s.get("id") == READINESS_SERVICE_ID for s in services):
                print(
                    f"[traffic-generator] {READINESS_SERVICE_ID} is declared - starting traffic",
                    flush=True,
                )
                return
        except (urllib.error.URLError, json.JSONDecodeError):
            pass
        if attempt % 5 == 1:
            print(
                "[traffic-generator] waiting for declared architecture - run "
                "`curl -X POST http://localhost:8000/api/import` to load examples/",
                flush=True,
            )
        time.sleep(READINESS_POLL_SECONDS)


def main() -> None:
    print(
        f"[traffic-generator] sending synthetic OTLP traces to {TRACES_URL} "
        f"every {INTERVAL_SECONDS}s (environment={ENVIRONMENT})",
        flush=True,
    )
    wait_for_declared_import()
    cycle = 0
    while True:
        cycle += 1
        batch = build_batch()
        try:
            send_batch(batch)
            print(
                f"[traffic-generator] {datetime.now(UTC).isoformat()} sent "
                f"{len(batch.resource_spans)} resource span blocks",
                flush=True,
            )
            if cycle % CROSS_BATCH_EVERY_N == 0:
                send_cross_batch_pair()
        except urllib.error.URLError as exc:
            print(f"[traffic-generator] send failed (collector not ready yet?): {exc}", flush=True)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
