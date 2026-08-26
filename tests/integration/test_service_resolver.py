from datetime import UTC, datetime
from pathlib import Path

import pytest
from testcontainers.community.neo4j import Neo4jContainer

from app.canonical import ids
from app.graph.importer import import_all_sources
from app.telemetry.model import DiscoveryStatus, RuntimeSpan
from app.telemetry.service_resolver import fetch_candidates, resolve_runtime_span

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
        "start_time": datetime(2026, 8, 26, tzinfo=UTC),
        "end_time": datetime(2026, 8, 26, tzinfo=UTC),
    }
    defaults.update(overrides)
    return RuntimeSpan(**defaults)


def test_fetch_candidates_returns_declared_services_with_no_namespace(session):
    candidates = fetch_candidates(session)
    by_name = {c.name for c in candidates}
    assert by_name == {"OrderService", "ProductService", "PaymentService", "InvoiceService"}
    assert all(c.namespace is None for c in candidates)


def test_resolve_runtime_span_matches_known_declared_service(session):
    candidates = fetch_candidates(session)
    span = _span(service_name="OrderService")
    result = resolve_runtime_span(candidates, span, aliases={})
    assert result.service_id == ids.service_id("order-service")
    assert result.discovery_status == DiscoveryStatus.DECLARED
    assert result.environment == "production"


def test_resolve_runtime_span_mints_observed_only_for_unknown_service(session):
    candidates = fetch_candidates(session)
    span = _span(service_name="FraudService")
    result = resolve_runtime_span(candidates, span, aliases={})
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY
    assert result.service_id == "service:fraudservice"

    # nothing was written to the graph - the resolver is read-only in this iteration
    count = session.run(
        "MATCH (s:Service {id: $id}) RETURN count(s) AS c", id=result.service_id
    ).single()["c"]
    assert count == 0
