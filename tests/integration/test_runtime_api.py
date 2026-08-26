from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from testcontainers.community.neo4j import Neo4jContainer

from app.canonical import ids
from app.graph.importer import import_all_sources
from app.main import create_app
from app.provenance.model import ObservedEvidence
from app.settings import AppConfig, Secrets, Settings
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.model import ObservationBatch, ObservedFactCandidate, ObservedOnlyEntity

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"
ENVIRONMENT = "production"
TIMESTAMP = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
SINCE = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5") as container:
        yield container


@pytest.fixture(scope="module")
def driver(neo4j_container):
    drv = neo4j_container.get_driver()
    yield drv
    drv.close()


def _fact(
    *, subject_id: str, relation_type: str, object_id: str, trace_id: str
) -> ObservedFactCandidate:
    evidence = ObservedEvidence(
        id=ids.observed_evidence_id(
            ENVIRONMENT, datetime(2026, 8, 26, tzinfo=UTC), subject_id, relation_type, object_id
        ),
        environment=ENVIRONMENT,
        bucket_start=datetime(2026, 8, 26, tzinfo=UTC),
        bucket_end=datetime(2026, 8, 27, tzinfo=UTC),
        first_seen=TIMESTAMP,
        last_seen=TIMESTAMP,
        observation_count=721,
        sample_trace_ids=[trace_id],
    )
    return ObservedFactCandidate(
        subject_id=subject_id,
        relation_type=relation_type,
        object_id=object_id,
        environment=ENVIRONMENT,
        timestamp=TIMESTAMP,
        trace_id=trace_id,
        evidence=evidence,
    )


@pytest.fixture(scope="module", autouse=True)
def populated_graph(driver):
    """Implements spec §63's Testlandscape verbatim: OrderService -> ProductService CONFIRMED
    (declared + observed), OrderService -> LegacyPricingService OBSERVED_ONLY, PaymentService ->
    invoice-q DECLARED_ONLY (declared, nothing observed in this window/environment)."""
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    import_all_sources(driver, database=DATABASE, root=EXAMPLES_DIR)

    order_id = ids.service_id("order-service")
    product_operation_id = ids.operation_id("product-service", "GET", "/products/{id}")
    legacy_provider_id = ids.service_id("legacy-pricing-service")
    legacy_operation_id = ids.operation_id(legacy_provider_id, "GET", "/pricing")

    batch = ObservationBatch(
        entities=[
            ObservedOnlyEntity(id=legacy_provider_id, label="Service", name="LegacyPricingService"),
            ObservedOnlyEntity(id=legacy_operation_id, label="Operation", name="GET /pricing"),
        ],
        facts=[
            _fact(
                subject_id=order_id,
                relation_type="CALLS",
                object_id=product_operation_id,
                trace_id="1" * 32,
            ),
            _fact(
                subject_id=order_id,
                relation_type="CALLS",
                object_id=legacy_operation_id,
                trace_id="2" * 32,
            ),
        ],
    )
    persist_observation_batch(driver, DATABASE, batch)


def _build_app(driver):
    app = create_app()
    app.state.driver = driver
    app.state.llm_provider = None
    app.state.settings = Settings(
        config=AppConfig.model_validate(
            {
                "sources": {"directories": [str(EXAMPLES_DIR)]},
                "graph": {"uri": "bolt://ignored:7687", "database": DATABASE},
            }
        ),
        secrets=Secrets(neo4j_user="neo4j", neo4j_password="ignored", openai_api_key=None),
    )
    return app


@pytest.fixture
def client(driver):
    return TestClient(_build_app(driver))


def _ids():
    return {
        "order": ids.service_id("order-service"),
        "product": ids.service_id("product-service"),
        "product_operation": ids.operation_id("product-service", "GET", "/products/{id}"),
        "legacy_operation": ids.operation_id(
            ids.service_id("legacy-pricing-service"), "GET", "/pricing"
        ),
        "payment": ids.service_id("payment-service"),
        "invoice_q": ids.queue_id("invoice-q"),
    }


# --- Runtime API ----------------------------------------------------------------------------------


def test_get_observed_relations_envelope_and_camelcase_keys(client):
    response = client.get("/api/runtime/relations", params={"environment": ENVIRONMENT})
    assert response.status_code == 200
    body = response.json()
    assert "environment" in body
    assert "window" in body
    assert set(body["window"]) == {"from", "to"}
    assert body["relations"]
    row = body["relations"][0]
    assert set(row) >= {
        "sourceId",
        "source",
        "relation",
        "targetId",
        "target",
        "status",
        "firstSeen",
        "lastSeen",
        "observationCount",
    }
    ids_map = _ids()
    target_ids = {r["targetId"] for r in body["relations"]}
    assert ids_map["product"] in target_ids
    assert ids_map["legacy_operation"] in target_ids


def test_get_service_runtime_profile(client):
    ids_map = _ids()
    response = client.get(f"/api/runtime/services/{ids_map['order']}")
    assert response.status_code == 200
    body = response.json()
    statuses = {r["status"] for r in body["relations"]}
    assert "CONFIRMED" in statuses
    assert "OBSERVED_ONLY" in statuses
    assert "coverage" in body
    assert body["coverage"]["httpObserved"] is True


def test_get_service_runtime_profile_not_found(client):
    response = client.get("/api/runtime/services/service:does-not-exist")
    assert response.status_code == 404


def test_get_confirmed(client):
    response = client.get("/api/analysis/runtime/confirmed", params={"environment": ENVIRONMENT})
    assert response.status_code == 200
    body = response.json()
    assert body["relations"]
    assert all(r["status"] == "CONFIRMED" for r in body["relations"])


def test_get_observed_only_pins_spec_48_literal_json_contract(client):
    response = client.get(
        "/api/analysis/runtime/observed-only", params={"environment": ENVIRONMENT}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == ENVIRONMENT
    assert set(body["window"]) == {"from", "to"}
    assert body["relations"]
    row = body["relations"][0]
    assert row["status"] == "OBSERVED_ONLY"
    for key in (
        "source",
        "relation",
        "target",
        "status",
        "firstSeen",
        "lastSeen",
        "observationCount",
    ):
        assert key in row


def test_get_declared_only_status_is_literal_not_observed_in_window(client):
    response = client.get(
        "/api/analysis/runtime/declared-only", params={"environment": ENVIRONMENT}
    )
    assert response.status_code == 200
    body = response.json()
    ids_map = _ids()
    row = next(r for r in body["relations"] if r["targetId"] == ids_map["invoice_q"])
    assert row["status"] == "NOT_OBSERVED_IN_WINDOW"
    assert "telemetryCoverageAvailable" in row


def test_get_coverage(client):
    response = client.get("/api/analysis/runtime/coverage", params={"environment": ENVIRONMENT})
    assert response.status_code == 200
    body = response.json()
    ids_map = _ids()
    row = next(s for s in body["services"] if s["serviceId"] == ids_map["order"])
    assert row["httpObserved"] is True
    assert "messagingObserved" in row
    assert "spansObserved" in row


# --- Service Explorer UI --------------------------------------------------------------------------


def test_ui_service_explorer_shows_observed_section_with_confirmed_and_observed_only(client):
    ids_map = _ids()
    response = client.get(f"/services/{ids_map['order']}")
    assert response.status_code == 200
    text = response.text
    assert "Observed" in text
    assert "CONFIRMED" in text
    assert "OBSERVED_ONLY" in text
    # "obsolete"/"dead" only, not "unused": order-service's own declared fixture data legitimately
    # sends to a queue literally named "unused-q" (the A3 fixture) - the payment-service test below
    # covers the full H4.16 negative-wording assertion on a page with no such name collision.
    for forbidden in ("obsolete", "dead"):
        assert forbidden not in text.lower()


def test_ui_service_explorer_shows_not_observed_in_window_for_declared_only(client):
    ids_map = _ids()
    response = client.get(f"/services/{ids_map['payment']}")
    assert response.status_code == 200
    text = response.text
    assert "NOT_OBSERVED_IN_WINDOW" in text
    for forbidden in ("obsolete", "unused", "dead"):
        assert forbidden not in text.lower()


def test_ui_service_explorer_shows_observed_evidence_block(client):
    ids_map = _ids()
    response = client.get(f"/services/{ids_map['order']}")
    assert response.status_code == 200
    text = response.text
    assert "OpenTelemetry" in text
    assert "first seen" in text
    assert "observations" in text


# --- O1-O5 NL intents ------------------------------------------------------------------------------


def test_post_query_o3_deterministic_routing(client):
    response = client.post(
        "/api/query",
        json={
            "question": "Welche undokumentierten REST-Abhängigkeiten wurden in Production beobachtet?"
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_mode"] == "DETERMINISTIC"
    assert body["intent"] == "O3_OBSERVED_ONLY_RELATIONS"
    ids_map = _ids()
    row_targets = {row["target_id"] for row in body["rows"]}
    assert ids_map["legacy_operation"] in row_targets


def test_post_query_o4_deterministic_routing(client):
    response = client.post(
        "/api/query",
        json={
            "question": "Welche deklarierte Kommunikation wurde in den letzten sieben Tagen nicht beobachtet?"
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_mode"] == "DETERMINISTIC"
    assert body["intent"] == "O4_DECLARED_ONLY_RELATIONS"


def test_post_query_o5_deterministic_routing(client):
    response = client.post(
        "/api/query", json={"question": "Für welche Services haben wir keine Telemetrie?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_mode"] == "DETERMINISTIC"
    assert body["intent"] == "O5_TELEMETRY_COVERAGE"


def test_post_query_o1_and_o2_deterministic_routing(client):
    r1 = client.post(
        "/api/query",
        json={"question": "Welche Architekturbeziehungen wurden tatsächlich beobachtet?"},
    )
    assert r1.json()["execution_mode"] == "DETERMINISTIC"
    assert r1.json()["intent"] == "O1_OBSERVED_RELATIONS"

    r2 = client.post("/api/query", json={"question": "Welche Beziehungen sind bestätigt?"})
    assert r2.json()["execution_mode"] == "DETERMINISTIC"
    assert r2.json()["intent"] == "O2_CONFIRMED_RELATIONS"
