from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from app.main import create_app

# No app.state.driver/settings needed: /v1/traces has no Depends() at all, and create_app() itself
# never touches Neo4j (only lifespan() does, which doesn't run under a plain TestClient(app)).
client = TestClient(create_app())

_CONTENT_TYPE = "application/x-protobuf"


def _valid_payload() -> bytes:
    resource = Resource(
        attributes=[KeyValue(key="service.name", value=AnyValue(string_value="OrderService"))]
    )
    span = Span(
        trace_id=bytes.fromhex("4bf92f3577b34da6a3ce929d0e0e4736"),
        span_id=bytes.fromhex("b7ad6b7169203331"),
        name="GET /products/{id}",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=1_700_000_000_000_000_000,
        end_time_unix_nano=1_700_000_000_100_000_000,
    )
    request = ExportTraceServiceRequest(
        resource_spans=[ResourceSpans(resource=resource, scope_spans=[ScopeSpans(spans=[span])])]
    )
    return request.SerializeToString()


def test_valid_payload_returns_200_with_empty_protobuf_ack():
    response = client.post(
        "/v1/traces", content=_valid_payload(), headers={"content-type": _CONTENT_TYPE}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == _CONTENT_TYPE
    ack = ExportTraceServiceResponse()
    ack.ParseFromString(response.content)  # must not raise


def test_wrong_content_type_returns_415():
    response = client.post(
        "/v1/traces", content=_valid_payload(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 415


def test_malformed_body_returns_400():
    response = client.post(
        "/v1/traces", content=b"not protobuf", headers={"content-type": _CONTENT_TYPE}
    )
    assert response.status_code == 400
