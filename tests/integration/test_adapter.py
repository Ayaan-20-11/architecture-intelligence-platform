from datetime import UTC, datetime
from pathlib import Path

import pytest
from testcontainers.community.neo4j import Neo4jContainer

from app.canonical import ids
from app.graph.importer import import_all_sources
from app.telemetry.adapter import correlate_http_call_observations, correlate_queue_observations
from app.telemetry.model import RuntimeSpan
from app.telemetry.operation_resolver import fetch_operation_candidates
from app.telemetry.queue_resolver import fetch_queue_candidates
from app.telemetry.service_resolver import fetch_candidates

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"


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


def _span(**overrides) -> RuntimeSpan:
    defaults = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "span_name": "op",
        "span_kind": "CLIENT",
        "service_name": "OrderService",
        "service_namespace": None,
        "service_version": None,
        "service_instance_id": None,
        "environment": "production",
        "start_time": datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        "end_time": datetime(2026, 8, 26, 12, 0, 1, tzinfo=UTC),
        "attributes": {},
    }
    defaults.update(overrides)
    return RuntimeSpan(**defaults)


def test_declared_call_reuses_the_real_declared_operation(session):
    # Mirrors examples/order-service/architecture.yaml's real declared CALLS: order-service ->
    # product-service's GET /products/{id} (H4.6: existing OpenAPI operations are reused).
    client = _span(span_id="c1" * 8, span_kind="CLIENT", service_name="OrderService")
    server = _span(
        parent_span_id=client.span_id,
        span_kind="SERVER",
        service_name="ProductService",
        attributes={"http.request.method": "GET", "http.route": "/products/{id}"},
    )

    service_candidates = fetch_candidates(session)
    operation_candidates = fetch_operation_candidates(session)
    batch = correlate_http_call_observations(
        [client, server],
        service_candidates=service_candidates,
        operation_candidates=operation_candidates,
        service_aliases={},
    )

    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == ids.service_id("order-service")
    assert fact.object_id == ids.operation_id(
        ids.service_id("product-service"), "GET", "/products/{id}"
    )
    assert batch.entities == []  # both sides and the operation are all declared - nothing new
    assert batch.unresolved == []


def test_unknown_route_mints_observed_only_operation_against_real_service_data(session):
    client = _span(span_id="c2" * 8, span_kind="CLIENT", service_name="OrderService")
    server = _span(
        parent_span_id=client.span_id,
        span_kind="SERVER",
        service_name="ProductService",
        attributes={"http.request.method": "GET", "http.route": "/internal/products/{id}"},
    )

    service_candidates = fetch_candidates(session)
    operation_candidates = fetch_operation_candidates(session)
    batch = correlate_http_call_observations(
        [client, server],
        service_candidates=service_candidates,
        operation_candidates=operation_candidates,
        service_aliases={},
    )

    # 11H-D: an OBSERVED_ONLY resolution now also earns an observed PROVIDES fact alongside CALLS.
    assert len(batch.facts) == 2
    fact = next(f for f in batch.facts if f.relation_type == "CALLS")
    provider_id = ids.service_id("product-service")
    assert fact.object_id == ids.operation_id(provider_id, "GET", "/internal/products/{id}")
    provides_fact = next(f for f in batch.facts if f.relation_type == "PROVIDES")
    assert provides_fact.subject_id == provider_id
    assert provides_fact.object_id == fact.object_id
    operation_entities = [e for e in batch.entities if e.label == "Operation"]
    assert len(operation_entities) == 1
    assert operation_entities[0].id == fact.object_id

    # nothing written to the graph - Iteration 11C stays read-only, like 11A/11B
    count = session.run(
        "MATCH (o:Operation {id: $id}) RETURN count(o) AS c", id=fact.object_id
    ).single()["c"]
    assert count == 0


def test_fetch_queue_candidates_returns_declared_queues_with_no_namespace(session):
    candidates = fetch_queue_candidates(session)
    by_name = {c.name for c in candidates}
    assert {"payment-q", "invoice-q", "unused-q", "unknown-producer-q"} <= by_name
    assert all(c.namespace is None for c in candidates)


def test_send_observation_reuses_the_real_declared_queue(session):
    # Mirrors examples/order-service/asyncapi.yaml's real declared SENDS: order-service -> payment-q
    # (H4.9: existing AsyncAPI queues are reused).
    span = _span(
        span_id="q1" * 8,
        service_name="OrderService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )

    service_candidates = fetch_candidates(session)
    queue_candidates = fetch_queue_candidates(session)
    batch = correlate_queue_observations(
        [span],
        service_candidates=service_candidates,
        queue_candidates=queue_candidates,
        service_aliases={},
        queue_aliases={},
    )

    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == ids.service_id("order-service")
    assert fact.relation_type == "SENDS"
    assert fact.object_id == ids.queue_id("payment-q")
    assert batch.entities == []


def test_unknown_destination_mints_observed_only_queue_against_real_service_data(session):
    span = _span(
        span_id="q2" * 8,
        service_name="OrderService",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "legacy-payment-q",
        },
    )

    service_candidates = fetch_candidates(session)
    queue_candidates = fetch_queue_candidates(session)
    batch = correlate_queue_observations(
        [span],
        service_candidates=service_candidates,
        queue_candidates=queue_candidates,
        service_aliases={},
        queue_aliases={},
    )

    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.object_id == ids.queue_id("legacy-payment-q")
    queue_entities = [e for e in batch.entities if e.label == "Queue"]
    assert len(queue_entities) == 1
    assert queue_entities[0].id == fact.object_id

    # nothing written to the graph - Iteration 11D stays read-only, like 11A-11C
    count = session.run(
        "MATCH (q:Queue {id: $id}) RETURN count(q) AS c", id=fact.object_id
    ).single()["c"]
    assert count == 0
