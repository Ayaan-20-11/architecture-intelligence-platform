from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from testcontainers.community.neo4j import Neo4jContainer

from app.canonical import ids
from app.graph.importer import import_all_sources
from app.main import create_app
from app.settings import AppConfig, Secrets, Settings

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


class FakeProvider:
    """No real OpenAI calls: fixed Cypher, deterministic answer."""

    def __init__(self, cypher: str = "MATCH (s:Service) RETURN s.name AS name"):
        self.cypher = cypher

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        return self.cypher

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        return f"Found {len(rows)} row(s)."


def _build_app(driver, *, llm_provider=None):
    app = create_app()
    app.state.driver = driver
    app.state.llm_provider = llm_provider
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


@pytest.fixture
def client_with_llm(driver):
    return TestClient(_build_app(driver, llm_provider=FakeProvider()))


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_neo4j(client):
    response = client.get("/health/neo4j")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_services(client):
    response = client.get("/api/services")
    assert response.status_code == 200
    names = {s["name"] for s in response.json()}
    assert names == {"OrderService", "ProductService", "PaymentService", "InvoiceService"}


def test_get_service(client):
    response = client.get(f"/api/services/{ids.service_id('order-service')}")
    assert response.status_code == 200
    assert response.json()["name"] == "OrderService"


def test_get_service_not_found(client):
    response = client.get("/api/services/service:does-not-exist")
    assert response.status_code == 404


def test_list_queues(client):
    response = client.get("/api/queues")
    assert response.status_code == 200
    names = {q["name"] for q in response.json()}
    assert names == {"payment-q", "invoice-q", "unused-q", "unknown-producer-q", "payment-dlq"}


def test_get_queue(client):
    response = client.get(f"/api/queues/{ids.queue_id('payment-q')}")
    assert response.status_code == 200
    assert response.json()["name"] == "payment-q"


def test_get_queue_not_found(client):
    response = client.get("/api/queues/queue:does-not-exist")
    assert response.status_code == 404


def test_list_messages(client):
    response = client.get("/api/messages")
    assert response.status_code == 200
    names = {m["name"] for m in response.json()}
    assert names == {
        "PaymentRequested",
        "InvoiceCreated",
        "UnusedMessage",
        "UnknownProducerMessage",
    }


def test_get_message(client):
    response = client.get(f"/api/messages/{ids.message_id('PaymentRequested', 'v2')}")
    assert response.status_code == 200
    assert response.json()["version"] == "v2"


def test_get_message_not_found(client):
    response = client.get("/api/messages/message:does-not-exist")
    assert response.status_code == 404


def test_a1_senders_endpoint(client):
    response = client.get(f"/api/analysis/queues/{ids.queue_id('payment-q')}/senders")
    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == [ids.service_id("order-service")]


def test_a2_consumers_endpoint(client):
    response = client.get(f"/api/analysis/queues/{ids.queue_id('payment-q')}/consumers")
    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == [ids.service_id("payment-service")]


def test_a3_queues_without_consumers_endpoint(client):
    response = client.get("/api/analysis/queues/without-consumers")
    assert response.status_code == 200
    assert [q["id"] for q in response.json()] == [ids.queue_id("unused-q")]


def test_a4_queues_without_senders_endpoint(client):
    response = client.get("/api/analysis/queues/without-senders")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["queue_id"] == ids.queue_id("unknown-producer-q")


def test_a5_blast_radius_endpoint_default_depth(client):
    response = client.get(f"/api/analysis/services/{ids.service_id('order-service')}/blast-radius")
    assert response.status_code == 200
    reached = {e["service_id"] for e in response.json()}
    assert reached == {
        ids.service_id("product-service"),
        ids.service_id("payment-service"),
        ids.service_id("invoice-service"),
    }


def test_a5_blast_radius_endpoint_depth_param(client):
    response = client.get(
        f"/api/analysis/services/{ids.service_id('order-service')}/blast-radius",
        params={"depth": 1},
    )
    assert response.status_code == 200
    reached = {e["service_id"] for e in response.json()}
    assert reached == {ids.service_id("product-service"), ids.service_id("payment-service")}


def test_post_import_all(client):
    response = client.post("/api/import")
    assert response.status_code == 200
    body = response.json()
    assert "import_id" in body
    assert set(body["services"]) == {
        "order-service",
        "product-service",
        "payment-service",
        "invoice-service",
    }


def test_post_import_service(client):
    response = client.post("/api/import/service/order-service")
    assert response.status_code == 200
    body = response.json()
    assert "import_id" in body
    assert body["service"]["service_id"] == "order-service"


def test_post_import_service_not_found(client):
    response = client.post("/api/import/service/does-not-exist")
    assert response.status_code == 404


def test_post_query_without_provider_configured_returns_503(client):
    response = client.post("/api/query", json={"question": "who sends payment-q?"})
    assert response.status_code == 503


def test_post_query_with_configured_provider_returns_real_answer(client_with_llm):
    response = client_with_llm.post("/api/query", json={"question": "who sends payment-q?"})
    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "who sends payment-q?"
    assert body["cypher"] == "MATCH (s:Service) RETURN s.name AS name LIMIT 100"
    assert len(body["rows"]) == 4
    assert body["answer"] == "Found 4 row(s)."


def test_ui_index_lists_services_and_queues(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "OrderService" in response.text
    assert "payment-q" in response.text


def test_ui_service_explorer(client):
    response = client.get(f"/services/{ids.service_id('order-service')}")
    assert response.status_code == 200
    assert "OrderService" in response.text
    assert "ProductService / getProduct" in response.text
    assert "payment-q" in response.text


def test_ui_service_explorer_not_found(client):
    response = client.get("/services/service:does-not-exist")
    assert response.status_code == 404


def test_ui_queue_explorer(client):
    response = client.get(f"/queues/{ids.queue_id('payment-q')}")
    assert response.status_code == 200
    assert "OrderService" in response.text  # sender
    assert "PaymentService" in response.text  # consumer
    assert "PaymentRequested" in response.text
    assert "payment-dlq" in response.text  # DLQ


def test_ui_queue_explorer_not_found(client):
    response = client.get("/queues/queue:does-not-exist")
    assert response.status_code == 404


def test_ui_query_page_empty_state(client):
    response = client.get("/query")
    assert response.status_code == 200
    assert "Natural Language Query" in response.text


def test_ui_query_page_with_question_and_no_provider_shows_not_configured(client):
    response = client.get("/query", params={"question": "who sends payment-q?"})
    assert response.status_code == 200
    assert "who sends payment-q?" in response.text
    assert "not configured" in response.text


def test_ui_query_page_with_question_and_provider_shows_real_answer(client_with_llm):
    response = client_with_llm.get("/query", params={"question": "who sends payment-q?"})
    assert response.status_code == 200
    assert "who sends payment-q?" in response.text
    assert "Found 4 row(s)." in response.text
