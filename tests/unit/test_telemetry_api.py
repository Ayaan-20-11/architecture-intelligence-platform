from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from app.main import create_app
from app.settings import AppConfig, Secrets, Settings

# FastAPI resolves a route's Depends() before the route body runs, regardless of where in the body
# an early HTTPException is raised - so app.state.driver/settings must still be set to *something*,
# even though these two failure cases never actually use them (the route raises before reaching any
# Neo4j access). A real driver/Testcontainers Neo4j is not needed here - only the "valid payload ->
# 200" happy path needs that, and lives in tests/integration/test_telemetry_api.py since Iteration
# 11E wired POST /v1/traces through to real persistence.


def _build_app():
    app = create_app()
    app.state.driver = None
    app.state.settings = Settings(
        config=AppConfig(), secrets=Secrets(neo4j_user="unused", neo4j_password="unused")
    )
    return app


client = TestClient(_build_app())

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
