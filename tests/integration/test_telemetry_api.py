from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span
from testcontainers.community.neo4j import Neo4jContainer

from app.canonical import ids
from app.graph.importer import import_all_sources
from app.main import create_app
from app.settings import AppConfig, Secrets, Settings
from app.telemetry.correlation_buffer import HttpCorrelationBuffer

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"
_CONTENT_TYPE = "application/x-protobuf"


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5") as container:
        yield container


@pytest.fixture(scope="module")
def driver(neo4j_container):
    drv = neo4j_container.get_driver()
    yield drv
    drv.close()


@pytest.fixture(scope="module", autouse=True)
def populated_graph(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    import_all_sources(driver, database=DATABASE, root=EXAMPLES_DIR)


@pytest.fixture
def session(driver):
    with driver.session(database=DATABASE) as s:
        yield s


def _build_app(driver):
    app = create_app()
    app.state.driver = driver
    app.state.settings = Settings(
        config=AppConfig.model_validate(
            {
                "sources": {"directories": [str(EXAMPLES_DIR)]},
                "graph": {"uri": "bolt://ignored:7687", "database": DATABASE},
            }
        ),
        secrets=Secrets(neo4j_user="neo4j", neo4j_password="ignored"),
    )
    return app


@pytest.fixture
def client(driver):
    return TestClient(_build_app(driver))


_CLIENT_SPAN_ID = bytes.fromhex("b7ad6b7169203331")
_SERVER_SPAN_ID = bytes.fromhex("00f067aa0ba902b7")
_TRACE_ID = bytes.fromhex("4bf92f3577b34da6a3ce929d0e0e4736")


def _client_resource_spans(*, client_service: str, method: str, route: str) -> ResourceSpans:
    resource = Resource(
        attributes=[KeyValue(key="service.name", value=AnyValue(string_value=client_service))]
    )
    span = Span(
        trace_id=_TRACE_ID,
        span_id=_CLIENT_SPAN_ID,
        name=f"{method} {route}",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=1_700_000_000_000_000_000,
        end_time_unix_nano=1_700_000_000_050_000_000,
    )
    return ResourceSpans(resource=resource, scope_spans=[ScopeSpans(spans=[span])])


def _server_resource_spans(*, server_service: str, method: str, route: str) -> ResourceSpans:
    resource = Resource(
        attributes=[
            KeyValue(key="service.name", value=AnyValue(string_value=server_service)),
            KeyValue(key="deployment.environment.name", value=AnyValue(string_value="production")),
        ]
    )
    span = Span(
        trace_id=_TRACE_ID,
        span_id=_SERVER_SPAN_ID,
        parent_span_id=_CLIENT_SPAN_ID,
        name=f"{method} {route}",
        kind=Span.SPAN_KIND_SERVER,
        start_time_unix_nano=1_700_000_000_010_000_000,
        end_time_unix_nano=1_700_000_000_040_000_000,
        attributes=[
            KeyValue(key="http.request.method", value=AnyValue(string_value=method)),
            KeyValue(key="http.route", value=AnyValue(string_value=route)),
        ],
    )
    return ResourceSpans(resource=resource, scope_spans=[ScopeSpans(spans=[span])])


def _resource_spans(*, client_service: str, server_service: str, method: str, route: str) -> bytes:
    request = ExportTraceServiceRequest(
        resource_spans=[
            _client_resource_spans(client_service=client_service, method=method, route=route),
            _server_resource_spans(server_service=server_service, method=method, route=route),
        ]
    )
    return request.SerializeToString()


def test_valid_payload_persists_an_observed_call_and_returns_200(client, session):
    payload = _resource_spans(
        client_service="OrderService",
        server_service="ProductService",
        method="GET",
        route="/products/{id}",
    )

    response = client.post("/v1/traces", content=payload, headers={"content-type": _CONTENT_TYPE})
    assert response.status_code == 200
    assert response.headers["content-type"] == _CONTENT_TYPE

    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id("product-service", "GET", "/products/{id}")
    record = session.run(
        "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) RETURN r.evidence_ids AS ids",
        subject_id=subject_id,
        object_id=object_id,
    ).single()
    assert record is not None
    assert len(record["ids"]) >= 1

    evidence_id = record["ids"][-1]
    evidence = session.run(
        "MATCH (e:Evidence {id: $id}) RETURN e.source_type AS source_type, "
        "e.evidence_type AS evidence_type, e.environment AS environment",
        id=evidence_id,
    ).single()
    assert evidence["source_type"] == "OPENTELEMETRY"
    assert evidence["evidence_type"] == "OBSERVED"
    assert evidence["environment"] == "production"


def _build_app_with_correlation_buffer(driver):
    app = _build_app(driver)
    app.state.http_correlation_buffer = HttpCorrelationBuffer(
        ttl_seconds=60, max_pending_spans=10000
    )
    return app


@pytest.fixture
def client_with_correlation_buffer(driver):
    return TestClient(_build_app_with_correlation_buffer(driver))


def test_cross_batch_client_and_server_in_separate_requests_produce_one_calls_relation(
    client_with_correlation_buffer, session
):
    # 11H-B / I2: a CLIENT span delivered in one POST /v1/traces and its matching SERVER span
    # delivered in a later, separate POST must still produce exactly one CALLS relation. Targets
    # an undeclared ReviewService/route, distinct from the module's other test's declared
    # order-service -> product-service relation, since this module has no per-test Neo4j reset.
    client_only = ExportTraceServiceRequest(
        resource_spans=[
            _client_resource_spans(
                client_service="OrderService", method="GET", route="/reviews/{id}"
            )
        ]
    ).SerializeToString()
    server_only = ExportTraceServiceRequest(
        resource_spans=[
            _server_resource_spans(
                server_service="ReviewService", method="GET", route="/reviews/{id}"
            )
        ]
    ).SerializeToString()

    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id(ids.service_id("reviewservice"), "GET", "/reviews/{id}")
    count_query = "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) RETURN count(r) AS c"

    response_a = client_with_correlation_buffer.post(
        "/v1/traces", content=client_only, headers={"content-type": _CONTENT_TYPE}
    )
    assert response_a.status_code == 200
    assert session.run(count_query, subject_id=subject_id, object_id=object_id).single()["c"] == 0

    response_b = client_with_correlation_buffer.post(
        "/v1/traces", content=server_only, headers={"content-type": _CONTENT_TYPE}
    )
    assert response_b.status_code == 200
    assert session.run(count_query, subject_id=subject_id, object_id=object_id).single()["c"] == 1
