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
"""

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
ENVIRONMENT = os.environ.get("DEMO_ENVIRONMENT", "demo")
INTERVAL_SECONDS = float(os.environ.get("TRAFFIC_INTERVAL_SECONDS", "5"))
CONTENT_TYPE = "application/x-protobuf"


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
) -> list[ResourceSpans]:
    """One realistic CLIENT+SERVER span pair for a synchronous REST call (spec §20's
    CLIENT_SERVER correlation mode - the strongest signal AIP recognizes)."""
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
    return [
        ResourceSpans(
            resource=_resource(client_service), scope_spans=[ScopeSpans(spans=[client_span])]
        ),
        ResourceSpans(
            resource=_resource(server_service), scope_spans=[ScopeSpans(spans=[server_span])]
        ),
    ]


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


def main() -> None:
    print(
        f"[traffic-generator] sending synthetic OTLP traces to {TRACES_URL} "
        f"every {INTERVAL_SECONDS}s (environment={ENVIRONMENT})",
        flush=True,
    )
    while True:
        batch = build_batch()
        try:
            send_batch(batch)
            print(
                f"[traffic-generator] {datetime.now(UTC).isoformat()} sent "
                f"{len(batch.resource_spans)} resource span blocks",
                flush=True,
            )
        except urllib.error.URLError as exc:
            print(f"[traffic-generator] send failed (collector not ready yet?): {exc}", flush=True)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
